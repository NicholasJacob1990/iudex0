"""
Legal Query Classifier — Dynamic Sparse/Dense Weights

Classifies legal search queries into MECE categories and returns
optimal sparse/dense weight pairs for hybrid SPLADE+Dense retrieval.

Categories are organized by **search behavior** (sparse→dense gradient),
not by legal domain type.

Flow:
  1. Fast-path regex for deterministic patterns (CNJ number, Art./§)
  2. LLM classification (Gemini Flash) with LRU cache
  3. Fallback → GENERAL (0.50/0.50) on any failure
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from enum import Enum
from functools import lru_cache
from typing import Dict, Optional, Tuple

logger = logging.getLogger("rag.query_classifier")

# ---------------------------------------------------------------------------
# Taxonomy
# ---------------------------------------------------------------------------


class QueryCategory(str, Enum):
    """MECE legal query categories ordered by sparse→dense gradient."""

    # Sparse-dominant (exact terms matter most)
    IDENTIFICADOR = "identificador"
    DISPOSITIVO = "dispositivo"
    NORMA = "norma"
    FACTUAL = "factual"

    # Balanced
    PROCEDIMENTO = "procedimento"
    JURISPRUDENCIA = "jurisprudencia"
    GENERAL = "general"

    # Dense-dominant (semantics matter most)
    ARGUMENTATIVO = "argumentativo"
    CONCEITUAL = "conceitual"


CATEGORY_WEIGHTS: Dict[QueryCategory, Tuple[float, float]] = {
    #                                  sparse, dense
    QueryCategory.IDENTIFICADOR: (0.90, 0.10),
    QueryCategory.DISPOSITIVO: (0.75, 0.25),
    QueryCategory.NORMA: (0.65, 0.35),
    QueryCategory.FACTUAL: (0.60, 0.40),
    QueryCategory.PROCEDIMENTO: (0.55, 0.45),
    QueryCategory.JURISPRUDENCIA: (0.40, 0.60),
    QueryCategory.GENERAL: (0.50, 0.50),
    QueryCategory.ARGUMENTATIVO: (0.35, 0.65),
    QueryCategory.CONCEITUAL: (0.25, 0.75),
}

# ---------------------------------------------------------------------------
# Fast-path regex (deterministic, 0ms)
# ---------------------------------------------------------------------------

# CNJ process number: 0001234-56.2024.8.26.0100
_CNJ_RE = re.compile(r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}")
# Legal article / paragraph: Art. 927, § 5º, inciso III
_DISPOSITIVO_RE = re.compile(
    r"(?:art\.?\s*\d|§\s*\d|inciso\s+[IVXLCDM]+|alínea\s+[a-z]|súmula\s+(?:vinculante\s+)?n?\.?\s*\d)",
    re.IGNORECASE,
)


def _fast_path(text: str) -> Optional[QueryCategory]:
    """Deterministic regex classification for unambiguous patterns."""
    if _CNJ_RE.search(text):
        return QueryCategory.IDENTIFICADOR
    if _DISPOSITIVO_RE.search(text):
        return QueryCategory.DISPOSITIVO
    return None


# ---------------------------------------------------------------------------
# LLM classification (Gemini Flash, cached)
# ---------------------------------------------------------------------------

_LLM_PROMPT = """\
Classify this legal SEARCH QUERY into exactly one category.

QUERY: {text}

Categories:
- identificador: busca por número (processo CNJ, OAB, CNPJ, protocolo)
- dispositivo: busca por artigo, parágrafo, inciso, súmula específica
- norma: busca por lei, decreto, código, MP por nome/número
- factual: busca por fatos, provas, evidências, nomes, datas, valores
- procedimento: busca por prazo, competência, rito, recurso, protocolar
- jurisprudencia: busca por precedentes, decisões, entendimento de tribunal
- argumentativo: busca por tese, fundamentação, argumentos, contra-razões
- conceitual: busca por doutrina, teoria, princípio, conceito, comparação conceitual
- general: outros / misto

Respond in exactly this format:
CATEGORY: <category>"""

_VALID_CATEGORIES = {c.value for c in QueryCategory}


@lru_cache(maxsize=1024)
def _cached_classify_key(cache_key: str) -> Optional[str]:
    """Placeholder — actual value stored via _cache_set."""
    return None


# Simple dict cache since lru_cache doesn't work well with async set
_llm_cache: Dict[str, QueryCategory] = {}
_LLM_CACHE_MAX = 1024


def _cache_key(text: str) -> str:
    return hashlib.sha256(text[:500].encode("utf-8")).hexdigest()[:32]


async def _classify_with_llm(
    text: str,
    model: str = "gemini-2.0-flash",
) -> Optional[QueryCategory]:
    """Classify query using Gemini Flash LLM with caching."""
    key = _cache_key(text)

    # Cache hit
    cached = _llm_cache.get(key)
    if cached is not None:
        return cached

    prompt = _LLM_PROMPT.format(text=text[:500])

    try:
        from google import genai  # type: ignore

        client = genai.Client()
        response = await asyncio.to_thread(
            client.models.generate_content,
            model=model,
            contents=prompt,
        )

        if not response or not response.text:
            return None

        # Parse response
        result_text = response.text.strip()
        for line in result_text.split("\n"):
            if ":" in line:
                raw_key, value = line.split(":", 1)
                if raw_key.strip().upper() == "CATEGORY":
                    cat_str = value.strip().lower()
                    if cat_str in _VALID_CATEGORIES:
                        category = QueryCategory(cat_str)
                        # Cache
                        if len(_llm_cache) >= _LLM_CACHE_MAX:
                            # Evict oldest 20%
                            keys = list(_llm_cache.keys())
                            for k in keys[: len(keys) // 5 or 1]:
                                _llm_cache.pop(k, None)
                        _llm_cache[key] = category
                        return category

        logger.warning("LLM response unparseable: %s", result_text[:100])
        return None

    except Exception as e:
        logger.warning("LLM query classification failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class ClassificationResult:
    """Result of query classification."""

    __slots__ = ("category", "w_sparse", "w_dense", "used_llm")

    def __init__(
        self,
        category: QueryCategory,
        w_sparse: float,
        w_dense: float,
        used_llm: bool,
    ):
        self.category = category
        self.w_sparse = w_sparse
        self.w_dense = w_dense
        self.used_llm = used_llm

    def __repr__(self) -> str:
        return (
            f"ClassificationResult({self.category.value}, "
            f"sparse={self.w_sparse}, dense={self.w_dense}, llm={self.used_llm})"
        )


async def classify_query(
    text: str,
    *,
    use_llm: bool = True,
    llm_model: str = "gemini-2.0-flash",
    default_sparse: float = 0.50,
    default_dense: float = 0.50,
) -> ClassificationResult:
    """
    Classify a legal search query and return optimal sparse/dense weights.

    Args:
        text: The search query text.
        use_llm: Whether to use LLM classification (if regex doesn't match).
        llm_model: Gemini model to use for classification.
        default_sparse: Default sparse weight (used for GENERAL fallback).
        default_dense: Default dense weight (used for GENERAL fallback).

    Returns:
        ClassificationResult with category and weights.
    """
    text = (text or "").strip()
    if not text:
        return ClassificationResult(
            QueryCategory.GENERAL, default_sparse, default_dense, False
        )

    # 1. Fast-path regex
    fast = _fast_path(text)
    if fast is not None:
        w_s, w_d = CATEGORY_WEIGHTS[fast]
        return ClassificationResult(fast, w_s, w_d, False)

    # 2. LLM classification
    if use_llm:
        category = await _classify_with_llm(text, model=llm_model)
        if category is not None:
            w_s, w_d = CATEGORY_WEIGHTS[category]
            return ClassificationResult(category, w_s, w_d, True)

    # 3. Fallback
    return ClassificationResult(
        QueryCategory.GENERAL, default_sparse, default_dense, False
    )


def classify_query_sync(text: str) -> ClassificationResult:
    """Synchronous version — uses only regex fast-path, no LLM."""
    text = (text or "").strip()
    if not text:
        w_s, w_d = CATEGORY_WEIGHTS[QueryCategory.GENERAL]
        return ClassificationResult(QueryCategory.GENERAL, w_s, w_d, False)

    fast = _fast_path(text)
    if fast is not None:
        w_s, w_d = CATEGORY_WEIGHTS[fast]
        return ClassificationResult(fast, w_s, w_d, False)

    w_s, w_d = CATEGORY_WEIGHTS[QueryCategory.GENERAL]
    return ClassificationResult(QueryCategory.GENERAL, w_s, w_d, False)


def clear_classification_cache() -> int:
    """Clear the LLM classification cache. Returns number of cleared entries."""
    count = len(_llm_cache)
    _llm_cache.clear()
    return count
