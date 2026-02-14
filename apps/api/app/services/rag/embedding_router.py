"""
Embedding Router — Roteamento multi-embedding por jurisdição/idioma/tipo.

Roteia queries e documentos para o modelo de embedding correto:
  - Direito BR → Voyage 4 large (1024d) — padrão desde 2026-02
  - Direito US/UK/INT → Kanon 2 Embedder (Isaacus API)
  - Direito EU → Voyage law-2 com Noxtua (ou Kanon 2 fallback)
  - Conteúdo geral → OpenAI text-embedding-3-large
  - Documento individual (<2000 pgs) → Sem RAG, flag para contexto longo

Arquitetura de 3 camadas:
  Camada 1: Heurística rápida (sem LLM, <1ms) — detecção de idioma + keywords
  Camada 2: LLM routing (Gemini Flash) — quando heurística incerta
  Camada 3: Fallback generalista (OpenAI)

Collections Qdrant separadas por jurisdição:
  - legal_br_v4: Voyage 4 large (1024d) — padrão
  - legal_br: JurisBERT (768d) — legado, consultado via include_legacy
  - legal_international: Kanon 2 (1024d)
  - legal_eu: Voyage law-2 (1024d)
  - general: OpenAI text-embedding-3-large (3072d)
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
import time
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Tuple

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Importação condicional de detecção de idioma
# ---------------------------------------------------------------------------
try:
    from langdetect import detect as _langdetect_detect  # type: ignore
    from langdetect import DetectorFactory  # type: ignore

    DetectorFactory.seed = 42  # Determinístico
    _LANGDETECT_AVAILABLE = True
except ImportError:
    _langdetect_detect = None  # type: ignore
    _LANGDETECT_AVAILABLE = False


# ---------------------------------------------------------------------------
# Enums e tipos
# ---------------------------------------------------------------------------


class Jurisdiction(str, Enum):
    """Jurisdições suportadas pelo router."""

    BR = "BR"  # Brasil
    US = "US"  # Estados Unidos
    UK = "UK"  # Reino Unido
    EU = "EU"  # União Europeia
    INT = "INT"  # Internacional (common law genérico)
    GENERAL = "GENERAL"  # Conteúdo não-jurídico


class DocumentType(str, Enum):
    """Tipos de documento jurídico."""

    LEGISLATION = "legislation"
    JURISPRUDENCE = "jurisprudence"
    CONTRACT = "contract"
    DOCTRINE = "doctrine"
    PLEADING = "pleading"  # Petição/peça processual
    GENERAL = "general"


class EmbeddingProviderName(str, Enum):
    """Nomes dos providers de embedding."""

    JURISBERT = "jurisbert"
    KANON2 = "kanon2"
    VOYAGE_LAW = "voyage_law"
    VOYAGE_CONTEXT = "voyage_context"
    VOYAGE_NOXTUA = "voyage_noxtua"
    VOYAGE_V4 = "voyage_v4"
    OPENAI = "openai"


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class EmbeddingRoutingDecision(BaseModel):
    """Resultado de uma decisão de roteamento."""

    jurisdiction: Jurisdiction
    document_type: DocumentType
    language: str = "unknown"
    provider: EmbeddingProviderName
    collection: str
    confidence: float = Field(ge=0.0, le=1.0)
    method: str = Field(description="Método usado: heuristic, llm, fallback")
    reason: str = Field(description="Justificativa da decisão")
    skip_rag: bool = Field(
        default=False,
        description="Se True, documento é pequeno o suficiente para LLM direto"
    )
    estimated_pages: int = 0


class EmbeddingRoute(BaseModel):
    """Rota de embedding com provider e configuração."""

    provider: EmbeddingProviderName
    collection: str
    dimensions: int
    decision: EmbeddingRoutingDecision


class RoutedEmbeddingResult(BaseModel):
    """Resultado de embedding com metadata de routing."""

    vectors: List[List[float]]
    route: EmbeddingRoute
    processing_time_ms: float
    texts_count: int


class SmartSearchRequest(BaseModel):
    """Request para smart-search com routing automático."""

    query: str = Field(..., min_length=1, max_length=10000)
    tenant_id: str = Field(..., min_length=1)
    case_id: Optional[str] = None
    jurisdiction_hint: Optional[Jurisdiction] = None
    language_hint: Optional[str] = None
    top_k: int = Field(default=10, ge=1, le=100)
    include_routing_info: bool = Field(default=True)
    include_legacy: bool = Field(
        default=True,
        description=(
            "Quando True, busca também nas collections legadas (lei, juris, etc.) "
            "usando embedding OpenAI 3072d. Permite migração gradual."
        ),
    )

    class Config:
        json_schema_extra = {
            "example": {
                "query": "What constitutes a breach of fiduciary duty under US law?",
                "tenant_id": "tenant-123",
                "jurisdiction_hint": "US",
                "top_k": 10,
                "include_legacy": True,
            }
        }


class SmartSearchResult(BaseModel):
    """Resultado de smart-search."""

    chunk_id: str
    text: str
    score: float
    metadata: Dict[str, Any] = Field(default_factory=dict)
    source_collection: str = ""


class SmartSearchResponse(BaseModel):
    """Response de smart-search."""

    results: List[SmartSearchResult] = Field(default_factory=list)
    routing: Optional[EmbeddingRoutingDecision] = None
    processing_time_ms: float = 0.0
    provider_used: str = ""
    collections_searched: List[str] = Field(
        default_factory=list,
        description="Lista de todas as collections consultadas (novas + legadas)",
    )


class SmartIngestRequest(BaseModel):
    """Request para smart-ingest com routing automático."""

    text: str = Field(..., min_length=1)
    tenant_id: str = Field(..., min_length=1)
    case_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    jurisdiction_hint: Optional[Jurisdiction] = None
    language_hint: Optional[str] = None
    chunk_size: int = Field(default=512, ge=100, le=2000)
    chunk_overlap: int = Field(default=50, ge=0, le=500)

    class Config:
        json_schema_extra = {
            "example": {
                "text": "Art. 37, §6º da CF: As pessoas jurídicas de direito público...",
                "tenant_id": "tenant-123",
                "jurisdiction_hint": "BR",
            }
        }


class SmartIngestResponse(BaseModel):
    """Response de smart-ingest."""

    indexed_count: int = 0
    collection: str = ""
    routing: Optional[EmbeddingRoutingDecision] = None
    skip_rag: bool = False
    skip_reason: str = ""
    processing_time_ms: float = 0.0


# ---------------------------------------------------------------------------
# Configuração de collections
# ---------------------------------------------------------------------------

EMBEDDING_COLLECTIONS: Dict[str, Dict[str, Any]] = {
    "legal_br": {
        "provider": EmbeddingProviderName.JURISBERT,
        "dimensions": 768,
        "description": "Direito brasileiro — JurisBERT (legado)",
    },
    "legal_br_v4": {
        "provider": EmbeddingProviderName.VOYAGE_V4,
        "dimensions": 1024,
        "description": "Direito brasileiro — Voyage 4 large (1024d, padrão)",
    },
    # Optional: Voyage Context 3 collection (contextualized chunk embeddings).
    # Keep this as a separate collection to allow gradual migration without breaking
    # existing 768d JurisBERT indexes.
    "legal_br_ctx3": {
        "provider": EmbeddingProviderName.VOYAGE_CONTEXT,
        "dimensions": 1024,
        "description": "Direito brasileiro — Voyage context-3 (contextualized chunks)",
    },
    "legal_international": {
        "provider": EmbeddingProviderName.KANON2,
        "dimensions": 1024,
        "description": "Direito internacional (US/UK/INT) — Kanon 2",
    },
    "legal_eu": {
        "provider": EmbeddingProviderName.VOYAGE_LAW,
        "dimensions": 1024,
        "description": "Direito europeu — Voyage law-2",
    },
    "legal_eu_ctx3": {
        "provider": EmbeddingProviderName.VOYAGE_CONTEXT,
        "dimensions": 1024,
        "description": "Direito europeu — Voyage context-3 (contextualized chunks)",
    },
    "general": {
        "provider": EmbeddingProviderName.OPENAI,
        "dimensions": 3072,
        "description": "Conteúdo geral — OpenAI text-embedding-3-large",
    },
}

# Mapeamento jurisdição -> collection
JURISDICTION_TO_COLLECTION: Dict[Jurisdiction, str] = {
    Jurisdiction.BR: "legal_br_v4",
    Jurisdiction.US: "legal_international",
    Jurisdiction.UK: "legal_international",
    Jurisdiction.INT: "legal_international",
    Jurisdiction.EU: "legal_eu",
    Jurisdiction.GENERAL: "general",
}

# Mapeamento jurisdição -> provider
JURISDICTION_TO_PROVIDER: Dict[Jurisdiction, EmbeddingProviderName] = {
    Jurisdiction.BR: EmbeddingProviderName.VOYAGE_V4,
    Jurisdiction.US: EmbeddingProviderName.KANON2,
    Jurisdiction.UK: EmbeddingProviderName.KANON2,
    Jurisdiction.INT: EmbeddingProviderName.KANON2,
    Jurisdiction.EU: EmbeddingProviderName.VOYAGE_LAW,
    Jurisdiction.GENERAL: EmbeddingProviderName.OPENAI,
}


def _env_provider(value: str) -> Optional[EmbeddingProviderName]:
    raw = (value or "").strip().lower()
    if not raw:
        return None
    try:
        return EmbeddingProviderName(raw)
    except Exception:
        return None


def _routing_overrides(
    jurisdiction: Jurisdiction,
    *,
    default_provider: EmbeddingProviderName,
    default_collection: str,
) -> Tuple[EmbeddingProviderName, str]:
    """
    Optional env-driven overrides for routing.

    Supports:
      - RAG_ROUTER_BR_PROVIDER / RAG_ROUTER_BR_COLLECTION
      - RAG_ROUTER_EU_PROVIDER / RAG_ROUTER_EU_COLLECTION
      - ... (US/UK/INT/GENERAL)

    Example to switch BR to Voyage Context 3 without code changes:
      RAG_ROUTER_BR_PROVIDER=voyage_context
      RAG_ROUTER_BR_COLLECTION=legal_br_ctx3
    """
    j = str(jurisdiction.value or "").strip().upper()
    prov_env = os.getenv(f"RAG_ROUTER_{j}_PROVIDER", "")
    coll_env = os.getenv(f"RAG_ROUTER_{j}_COLLECTION", "")

    provider = _env_provider(prov_env) or default_provider
    collection = (coll_env or "").strip() or default_collection
    return provider, collection

# Threshold para pular RAG (enviar direto ao LLM)
# ~2000 páginas * ~500 palavras/página * ~1.3 tokens/palavra = ~1.3M tokens
# Mas na prática, documentos < ~400k chars (~100 páginas) cabem no contexto
SKIP_RAG_CHAR_THRESHOLD = int(os.getenv("SMART_SKIP_RAG_CHARS", "400000"))

# ---------------------------------------------------------------------------
# Collections legadas — todas usam OpenAI text-embedding-3-large (3072d)
# DEPRECATED: Migrar para collections novas (legal_br_v4 etc.) via
#   EmbeddingRouter.migrate_collection()
# Para desativar buscas legacy, passe include_legacy=False em search_with_routing()
# ---------------------------------------------------------------------------

LEGACY_COLLECTIONS: Dict[str, List[str]] = {
    "BR": ["lei", "juris", "doutrina", "pecas_modelo", "local_chunks"],
    "US": ["local_chunks"],
    "UK": ["local_chunks"],
    "INT": ["local_chunks"],
    "EU": ["local_chunks"],
    "GENERAL": ["lei", "juris", "doutrina", "pecas_modelo", "local_chunks"],
}

LEGACY_EMBEDDING_DIMENSIONS = 3072  # OpenAI text-embedding-3-large

# Track whether we already emitted legacy deprecation warning (log only once)
_legacy_warning_emitted = False


def reciprocal_rank_fusion(
    results_lists: List[List[Dict[str, Any]]],
    k: int = 60,
) -> List[Dict[str, Any]]:
    """
    Merge rankings de multiplas fontes usando Reciprocal Rank Fusion.

    Para cada documento encontrado em qualquer lista, calcula:
        score_rrf = sum(1 / (k + rank + 1)) para cada lista onde aparece.

    Args:
        results_lists: Lista de listas de resultados (cada resultado eh um dict
            com pelo menos 'chunk_id', 'text', 'score', 'metadata',
            'source_collection').
        k: Constante de suavizacao (default 60, valor padrao da literatura).

    Returns:
        Lista de resultados ordenados por score RRF (desc), sem duplicatas.
    """
    scores: Dict[str, float] = {}
    best_result: Dict[str, Dict[str, Any]] = {}

    for results in results_lists:
        for rank, result in enumerate(results):
            doc_id = result.get("chunk_id", "")
            if not doc_id:
                continue
            rrf_score = 1.0 / (k + rank + 1)
            scores[doc_id] = scores.get(doc_id, 0.0) + rrf_score

            # Manter o resultado com melhor score original como representante
            if (
                doc_id not in best_result
                or result.get("score", 0) > best_result[doc_id].get("score", 0)
            ):
                best_result[doc_id] = result

    # Ordenar por score RRF
    sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)

    merged: List[Dict[str, Any]] = []
    for doc_id in sorted_ids:
        item = dict(best_result[doc_id])
        item["rrf_score"] = round(scores[doc_id], 6)
        merged.append(item)

    return merged


# ---------------------------------------------------------------------------
# Keywords de jurisdição (Camada 1: Heurística)
# ---------------------------------------------------------------------------

_BR_KEYWORDS = {
    # Tribunais
    "stf", "stj", "tst", "trf", "tjsp", "tjrj", "tjmg", "tjrs", "tjpr",
    "tjsc", "tjba", "tjpe", "tjce", "tjgo", "tjdf", "tjmt", "tjms", "tjpa",
    "tjam", "tjal", "tjrn", "tjpb", "tjse", "tjpi", "tjma", "tjap", "tjro",
    "tjrr", "tjto", "tjac", "tre", "trt",
    # Legislação
    "lei nº", "lei número", "lei n.", "decreto nº", "decreto-lei",
    "medida provisória", "emenda constitucional", "constituição federal",
    "código civil", "código penal", "código de processo", "cpc", "cpp",
    "clt", "cdc", "eca", "loas",
    # Termos processuais BR
    "recurso especial", "recurso extraordinário", "habeas corpus",
    "mandado de segurança", "ação direta", "adi", "adpf", "adc",
    "súmula vinculante", "repercussão geral",
    # Artigos/incisos
    "art.", "artigo", "inciso", "parágrafo", "alínea", "caput",
}

_US_KEYWORDS = {
    # Tribunais
    "supreme court", "circuit court", "district court", "court of appeals",
    "scotus", "federal court",
    # Legislação
    "usc", "u.s.c.", "cfr", "c.f.r.", "united states code",
    "federal register", "public law", "stat.",
    # Termos
    "amendment", "bill of rights", "due process", "equal protection",
    "commerce clause", "first amendment", "fourth amendment",
    "fifth amendment", "fourteenth amendment",
    "stare decisis", "certiorari", "amicus curiae",
    "federal rules", "frcp", "fre",
}

_UK_KEYWORDS = {
    "house of lords", "house of commons", "privy council",
    "crown court", "high court", "court of appeal",
    "supreme court of the united kingdom",
    "statutory instrument", "act of parliament",
    "queen's bench", "king's bench", "chancery division",
    "common law", "equity", "tort",
    "uksc", "ewca", "ewhc",
}

_EU_KEYWORDS = {
    # Instituições
    "european court of justice", "ecj", "cjeu",
    "european court of human rights", "echr",
    "european commission", "european parliament",
    "court of justice of the european union",
    # Legislação
    "eu regulation", "eu directive", "gdpr",
    "treaty of lisbon", "treaty of rome",
    "richtlinie", "verordnung", "règlement",
    # Termos
    "acquis communautaire", "subsidiarity",
    "preliminary ruling", "infringement procedure",
    "schengen", "erasmus", "horizon",
}

# Pattern para detecção de números CNJ (Brasil)
_CNJ_PATTERN = re.compile(r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}")

# Pattern para citações legais US (e.g., "42 U.S.C. § 1983")
_USC_PATTERN = re.compile(r"\d+\s+U\.?S\.?C\.?\s*§?\s*\d+")

# Pattern para legislação EU (e.g., "Regulation (EU) 2016/679")
_EU_REG_PATTERN = re.compile(
    r"(?:Regulation|Directive|Decision)\s*\((?:EU|EC|EEC)\)\s*(?:No\.?\s*)?\d+/\d+"
)


# ---------------------------------------------------------------------------
# Cache de classificação LLM
# ---------------------------------------------------------------------------


class _ClassificationCache:
    """Cache de classificações LLM por hash de texto."""

    def __init__(self, max_size: int = 1024) -> None:
        self._cache: OrderedDict[str, EmbeddingRoutingDecision] = OrderedDict()
        self._max_size = max_size
        self._lock = threading.Lock()

    @staticmethod
    def _key(text: str) -> str:
        # Usar primeiros 500 chars para hash (suficiente para classificação)
        snippet = text[:500].strip().lower()
        return hashlib.sha256(snippet.encode("utf-8")).hexdigest()

    def get(self, text: str) -> Optional[EmbeddingRoutingDecision]:
        key = self._key(text)
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
            return None

    def set(self, text: str, decision: EmbeddingRoutingDecision) -> None:
        key = self._key(text)
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            else:
                if len(self._cache) >= self._max_size:
                    self._cache.popitem(last=False)
            self._cache[key] = decision


# ---------------------------------------------------------------------------
# Embedding Router
# ---------------------------------------------------------------------------


class EmbeddingRouter:
    """
    Roteia queries para o embedding correto baseado em jurisdição/idioma/tipo.

    3 camadas de decisão:
      1. Heurística rápida (keywords, regex, idioma) — sem custo, <1ms
      2. LLM routing (Gemini Flash) — quando heurística incerta
      3. Fallback generalista (OpenAI text-embedding-3-large)
    """

    def __init__(
        self,
        heuristic_confidence_threshold: float = 0.8,
        llm_model: str = "gemini-2.0-flash",
    ) -> None:
        self._heuristic_threshold = heuristic_confidence_threshold
        self._llm_model = llm_model
        self._classification_cache = _ClassificationCache()

        # Lazy-loaded providers
        self._providers: Dict[EmbeddingProviderName, Any] = {}
        self._providers_lock = threading.Lock()

        # Usage counters for monitoring
        self._usage_lock = threading.Lock()
        self._usage_counts: Dict[str, int] = {}  # provider -> count
        self._usage_by_jurisdiction: Dict[str, int] = {}  # jurisdiction -> count
        self._usage_by_method: Dict[str, int] = {}  # method -> count

        # QdrantClient compartilhado (lazy init) — evita criar conexão a cada busca
        self._qdrant_client: Optional[Any] = None
        self._qdrant_lock = threading.Lock()

        logger.info(
            "EmbeddingRouter inicializado: threshold=%.2f, llm=%s",
            self._heuristic_threshold,
            self._llm_model,
        )

    # ------------------------------------------------------------------
    # Camada 1: Heurística
    # ------------------------------------------------------------------

    def _detect_language(self, text: str) -> Tuple[str, float]:
        """
        Detecta o idioma do texto.

        Returns:
            Tuple (lang_code, confidence). Ex: ("pt", 0.95)
        """
        if not text or not text.strip():
            return "unknown", 0.0

        # Heurística rápida baseada em caracteres
        sample = text[:1000].lower()

        # Português: palavras comuns
        pt_indicators = [
            "de", "da", "do", "dos", "das", "que", "para", "com",
            "não", "uma", "por", "mais", "como", "pelo", "pela",
            "artigo", "lei", "tribunal", "recurso", "direito",
        ]
        pt_count = sum(1 for w in pt_indicators if f" {w} " in f" {sample} ")

        # Inglês: palavras comuns
        en_indicators = [
            "the", "of", "and", "to", "in", "for", "is", "that",
            "with", "by", "court", "law", "section", "shall",
        ]
        en_count = sum(1 for w in en_indicators if f" {w} " in f" {sample} ")

        # Alemão: palavras comuns
        de_indicators = [
            "der", "die", "das", "und", "von", "für", "mit",
            "ist", "nicht", "den", "ein", "eine", "gesetz", "recht",
        ]
        de_count = sum(1 for w in de_indicators if f" {w} " in f" {sample} ")

        # Francês: palavras comuns
        fr_indicators = [
            "le", "la", "les", "de", "du", "des", "un", "une",
            "est", "dans", "par", "pour", "loi", "droit", "tribunal",
        ]
        fr_count = sum(1 for w in fr_indicators if f" {w} " in f" {sample} ")

        counts = {"pt": pt_count, "en": en_count, "de": de_count, "fr": fr_count}
        best_lang = max(counts, key=counts.get)  # type: ignore[arg-type]
        best_count = counts[best_lang]
        total = sum(counts.values())

        if total == 0:
            # Tentar langdetect como backup
            if _LANGDETECT_AVAILABLE:
                try:
                    detected = _langdetect_detect(text[:500])
                    return detected, 0.7
                except Exception:
                    pass
            return "unknown", 0.0

        confidence = min(best_count / max(total, 1) * 1.5, 1.0)

        # Se a confiança é baixa, tentar langdetect
        if confidence < 0.6 and _LANGDETECT_AVAILABLE:
            try:
                detected = _langdetect_detect(text[:500])
                return detected, 0.75
            except Exception:
                pass

        return best_lang, confidence

    def _detect_jurisdiction_heuristic(
        self, text: str, language: str = "unknown"
    ) -> Tuple[Jurisdiction, float]:
        """
        Detecta jurisdição por keywords e padrões.

        Returns:
            Tuple (jurisdiction, confidence)
        """
        if not text:
            return Jurisdiction.GENERAL, 0.0

        text_lower = text[:3000].lower()

        # Scores por jurisdição
        scores: Dict[Jurisdiction, float] = {
            Jurisdiction.BR: 0.0,
            Jurisdiction.US: 0.0,
            Jurisdiction.UK: 0.0,
            Jurisdiction.EU: 0.0,
            Jurisdiction.GENERAL: 0.1,  # Bias mínimo para geral
        }

        # BR keywords
        for kw in _BR_KEYWORDS:
            if kw in text_lower:
                scores[Jurisdiction.BR] += 1.0
        # CNJ pattern (forte indicador BR)
        if _CNJ_PATTERN.search(text):
            scores[Jurisdiction.BR] += 3.0

        # US keywords
        for kw in _US_KEYWORDS:
            if kw in text_lower:
                scores[Jurisdiction.US] += 1.0
        if _USC_PATTERN.search(text):
            scores[Jurisdiction.US] += 3.0

        # UK keywords
        for kw in _UK_KEYWORDS:
            if kw in text_lower:
                scores[Jurisdiction.UK] += 1.0

        # EU keywords
        for kw in _EU_KEYWORDS:
            if kw in text_lower:
                scores[Jurisdiction.EU] += 1.0
        if _EU_REG_PATTERN.search(text):
            scores[Jurisdiction.EU] += 3.0

        # Boost por idioma
        if language == "pt":
            scores[Jurisdiction.BR] += 2.0
        elif language == "en":
            # Pode ser US, UK ou INT
            scores[Jurisdiction.US] += 0.5
            scores[Jurisdiction.UK] += 0.5
        elif language in ("de", "fr", "it", "es", "nl"):
            scores[Jurisdiction.EU] += 1.5

        # Determinar vencedor
        best_juris = max(scores, key=scores.get)  # type: ignore[arg-type]
        best_score = scores[best_juris]
        total = sum(scores.values())

        if best_score == 0:
            return Jurisdiction.GENERAL, 0.3

        confidence = min(best_score / max(total, 1) * 2.0, 1.0)

        # Se US e UK estão próximos, usar INT
        if (
            best_juris in (Jurisdiction.US, Jurisdiction.UK)
            and abs(scores[Jurisdiction.US] - scores[Jurisdiction.UK])
            < max(scores[Jurisdiction.US], scores[Jurisdiction.UK]) * 0.3
            and scores[Jurisdiction.US] > 0
            and scores[Jurisdiction.UK] > 0
        ):
            return Jurisdiction.INT, confidence * 0.9

        return best_juris, confidence

    def _detect_document_type(self, text: str) -> DocumentType:
        """Detecta o tipo de documento jurídico."""
        text_lower = text[:2000].lower()

        # Legislação
        legislation_patterns = [
            r"art(?:igo)?\.?\s*\d+",
            r"§\s*\d+",
            r"lei\s+n",
            r"decreto\s+n",
            r"section\s+\d+",
            r"regulation\s*\(",
        ]
        leg_score = sum(
            1 for p in legislation_patterns if re.search(p, text_lower)
        )

        # Jurisprudência
        juris_patterns = [
            r"acórdão",
            r"ementa",
            r"voto\s+do\s+relator",
            r"tribunal",
            r"holding",
            r"opinion\s+of\s+the\s+court",
            r"dissenting\s+opinion",
            r"judgment",
        ]
        juris_score = sum(
            1 for p in juris_patterns if re.search(p, text_lower)
        )

        # Contrato
        contract_patterns = [
            r"cláusula",
            r"contratante",
            r"contratad[oa]",
            r"clause",
            r"party\s+(?:a|b|of\s+the\s+first)",
            r"hereby\s+agrees",
            r"term\s+(?:of|and)\s+condition",
        ]
        contract_score = sum(
            1 for p in contract_patterns if re.search(p, text_lower)
        )

        # Petição/Peça processual
        pleading_patterns = [
            r"excelentíssimo",
            r"meritíssimo",
            r"requer(?:ente|ida)",
            r"plaintiff",
            r"defendant",
            r"motion\s+(?:to|for)",
            r"prayer\s+for\s+relief",
        ]
        pleading_score = sum(
            1 for p in pleading_patterns if re.search(p, text_lower)
        )

        scores = {
            DocumentType.LEGISLATION: leg_score,
            DocumentType.JURISPRUDENCE: juris_score,
            DocumentType.CONTRACT: contract_score,
            DocumentType.PLEADING: pleading_score,
            DocumentType.GENERAL: 0.5,
        }

        return max(scores, key=scores.get)  # type: ignore[arg-type]

    def _estimate_document_size(self, text: str) -> int:
        """Estima o número de páginas (~500 palavras/página)."""
        word_count = len(text.split())
        return max(1, word_count // 500)

    # ------------------------------------------------------------------
    # Camada 2: LLM routing
    # ------------------------------------------------------------------

    async def _classify_with_llm(self, text: str) -> Optional[EmbeddingRoutingDecision]:
        """
        Usa LLM (Gemini Flash) para classificar jurisdição quando
        a heurística é incerta.
        """
        # Check cache
        cached = self._classification_cache.get(text)
        if cached is not None:
            return cached

        snippet = text[:1500]

        prompt = (
            "You are a legal text classifier. Analyze the following text and classify it.\n\n"
            "TEXT:\n"
            f"{snippet}\n\n"
            "Respond in exactly this format (one line each):\n"
            "JURISDICTION: BR|US|UK|EU|INT|GENERAL\n"
            "DOCUMENT_TYPE: legislation|jurisprudence|contract|doctrine|pleading|general\n"
            "LANGUAGE: pt|en|de|fr|es|other\n"
            "CONFIDENCE: 0.0-1.0\n"
            "REASON: brief explanation\n\n"
            "Rules:\n"
            "- BR = Brazilian law\n"
            "- US = United States law\n"
            "- UK = United Kingdom law\n"
            "- EU = European Union law\n"
            "- INT = International/comparative law\n"
            "- GENERAL = Non-legal or general content\n"
        )

        try:
            from google import genai  # type: ignore

            client = genai.Client()
            response = await asyncio.to_thread(
                client.models.generate_content,
                model=self._llm_model,
                contents=prompt,
            )

            if not response or not response.text:
                return None

            result_text = response.text.strip()
            decision = self._parse_llm_response(result_text)
            if decision:
                self._classification_cache.set(text, decision)
            return decision

        except Exception as e:
            logger.warning("LLM classification falhou: %s", e)
            return None

    def _parse_llm_response(self, response_text: str) -> Optional[EmbeddingRoutingDecision]:
        """Parseia a resposta do LLM de classificação."""
        try:
            lines = response_text.strip().split("\n")
            parsed: Dict[str, str] = {}
            for line in lines:
                if ":" in line:
                    key, value = line.split(":", 1)
                    parsed[key.strip().upper()] = value.strip()

            # Jurisdição
            juris_str = parsed.get("JURISDICTION", "GENERAL").upper()
            jurisdiction_map = {
                "BR": Jurisdiction.BR,
                "US": Jurisdiction.US,
                "UK": Jurisdiction.UK,
                "EU": Jurisdiction.EU,
                "INT": Jurisdiction.INT,
                "GENERAL": Jurisdiction.GENERAL,
            }
            jurisdiction = jurisdiction_map.get(juris_str, Jurisdiction.GENERAL)

            # Tipo de documento
            doc_type_str = parsed.get("DOCUMENT_TYPE", "general").lower()
            doc_type_map = {
                "legislation": DocumentType.LEGISLATION,
                "jurisprudence": DocumentType.JURISPRUDENCE,
                "contract": DocumentType.CONTRACT,
                "doctrine": DocumentType.DOCTRINE,
                "pleading": DocumentType.PLEADING,
                "general": DocumentType.GENERAL,
            }
            document_type = doc_type_map.get(doc_type_str, DocumentType.GENERAL)

            # Confidence
            try:
                confidence = float(parsed.get("CONFIDENCE", "0.7"))
                confidence = max(0.0, min(1.0, confidence))
            except ValueError:
                confidence = 0.7

            language = parsed.get("LANGUAGE", "unknown").lower()
            reason = parsed.get("REASON", "Classificado via LLM")

            # Provider e collection
            provider = JURISDICTION_TO_PROVIDER.get(
                jurisdiction, EmbeddingProviderName.OPENAI
            )
            collection = JURISDICTION_TO_COLLECTION.get(
                jurisdiction, "general"
            )
            provider, collection = _routing_overrides(
                jurisdiction,
                default_provider=provider,
                default_collection=collection,
            )

            return EmbeddingRoutingDecision(
                jurisdiction=jurisdiction,
                document_type=document_type,
                language=language,
                provider=provider,
                collection=collection,
                confidence=confidence,
                method="llm",
                reason=reason,
            )

        except Exception as e:
            logger.warning("Falha ao parsear resposta LLM: %s", e)
            return None

    # ------------------------------------------------------------------
    # Usage tracking
    # ------------------------------------------------------------------

    def _record_usage(self, decision: EmbeddingRoutingDecision) -> None:
        """Record provider usage for monitoring."""
        with self._usage_lock:
            prov = decision.provider.value
            self._usage_counts[prov] = self._usage_counts.get(prov, 0) + 1
            juris = decision.jurisdiction.value
            self._usage_by_jurisdiction[juris] = self._usage_by_jurisdiction.get(juris, 0) + 1
            method = decision.method
            self._usage_by_method[method] = self._usage_by_method.get(method, 0) + 1

    def get_usage_stats(self) -> Dict[str, Any]:
        """Return provider usage statistics for monitoring."""
        with self._usage_lock:
            total = sum(self._usage_counts.values())
            return {
                "total_routes": total,
                "by_provider": dict(self._usage_counts),
                "by_jurisdiction": dict(self._usage_by_jurisdiction),
                "by_method": dict(self._usage_by_method),
            }

    # ------------------------------------------------------------------
    # Método principal: route
    # ------------------------------------------------------------------

    async def route(
        self,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> EmbeddingRoute:
        """
        Roteia um texto para o embedding correto.

        Args:
            text: Texto para classificar.
            metadata: Metadata opcional com hints (jurisdiction, language).

        Returns:
            EmbeddingRoute com provider, collection e decisão.
        """
        metadata = metadata or {}
        start = time.time()

        # Hints explícitos do usuário
        hint_jurisdiction = metadata.get("jurisdiction")
        hint_language = metadata.get("language")

        # Se hint de jurisdição foi fornecido com alta confiança, usar direto
        if hint_jurisdiction:
            try:
                jurisdiction = Jurisdiction(hint_jurisdiction)
                provider = JURISDICTION_TO_PROVIDER[jurisdiction]
                collection = JURISDICTION_TO_COLLECTION[jurisdiction]
                provider, collection = _routing_overrides(
                    jurisdiction,
                    default_provider=provider,
                    default_collection=collection,
                )
                dims = EMBEDDING_COLLECTIONS.get(collection, {"dimensions": 3072})["dimensions"]

                decision = EmbeddingRoutingDecision(
                    jurisdiction=jurisdiction,
                    document_type=self._detect_document_type(text),
                    language=hint_language or "unknown",
                    provider=provider,
                    collection=collection,
                    confidence=1.0,
                    method="user_hint",
                    reason=f"Jurisdição {jurisdiction.value} fornecida pelo usuário",
                    estimated_pages=self._estimate_document_size(text),
                )

                elapsed = (time.time() - start) * 1000
                logger.info(
                    "EmbeddingRouter: hint=%s, provider=%s, collection=%s (%.1fms)",
                    jurisdiction.value,
                    provider.value,
                    collection,
                    elapsed,
                )

                self._record_usage(decision)
                return EmbeddingRoute(
                    provider=provider,
                    collection=collection,
                    dimensions=dims,
                    decision=decision,
                )
            except (ValueError, KeyError):
                logger.warning(
                    "Hint de jurisdição inválido: %s, usando heurística",
                    hint_jurisdiction,
                )

        # Camada 1: Heurística
        language, lang_conf = self._detect_language(text)
        jurisdiction, juris_conf = self._detect_jurisdiction_heuristic(
            text, language=language
        )
        doc_type = self._detect_document_type(text)
        estimated_pages = self._estimate_document_size(text)

        # Verificar se deve pular RAG
        skip_rag = len(text) < SKIP_RAG_CHAR_THRESHOLD and estimated_pages < 100

        combined_confidence = (juris_conf * 0.7 + lang_conf * 0.3)

        if combined_confidence >= self._heuristic_threshold:
            # Heurística é confiante o suficiente
            provider = JURISDICTION_TO_PROVIDER.get(
                jurisdiction, EmbeddingProviderName.OPENAI
            )
            collection = JURISDICTION_TO_COLLECTION.get(jurisdiction, "general")
            provider, collection = _routing_overrides(
                jurisdiction,
                default_provider=provider,
                default_collection=collection,
            )
            dims = EMBEDDING_COLLECTIONS.get(collection, {"dimensions": 3072})["dimensions"]

            decision = EmbeddingRoutingDecision(
                jurisdiction=jurisdiction,
                document_type=doc_type,
                language=language,
                provider=provider,
                collection=collection,
                confidence=combined_confidence,
                method="heuristic",
                reason=(
                    f"Heurística: jurisdição={jurisdiction.value} "
                    f"(conf={juris_conf:.2f}), idioma={language} "
                    f"(conf={lang_conf:.2f})"
                ),
                skip_rag=skip_rag,
                estimated_pages=estimated_pages,
            )

            elapsed = (time.time() - start) * 1000
            logger.info(
                "EmbeddingRouter [heuristic]: juris=%s, lang=%s, provider=%s, "
                "collection=%s, conf=%.2f (%.1fms)",
                jurisdiction.value,
                language,
                provider.value,
                collection,
                combined_confidence,
                elapsed,
            )

            self._record_usage(decision)
            return EmbeddingRoute(
                provider=provider,
                collection=collection,
                dimensions=dims,
                decision=decision,
            )

        # Camada 2: LLM routing
        logger.info(
            "EmbeddingRouter: heurística incerta (conf=%.2f < %.2f), "
            "tentando LLM...",
            combined_confidence,
            self._heuristic_threshold,
        )

        llm_decision = await self._classify_with_llm(text)
        if llm_decision and llm_decision.confidence >= 0.6:
            llm_decision.skip_rag = skip_rag
            llm_decision.estimated_pages = estimated_pages

            collection = llm_decision.collection
            dims = EMBEDDING_COLLECTIONS.get(collection, {"dimensions": 3072})[
                "dimensions"
            ]

            elapsed = (time.time() - start) * 1000
            logger.info(
                "EmbeddingRouter [llm]: juris=%s, provider=%s, "
                "collection=%s, conf=%.2f (%.1fms)",
                llm_decision.jurisdiction.value,
                llm_decision.provider.value,
                collection,
                llm_decision.confidence,
                elapsed,
            )

            self._record_usage(llm_decision)
            return EmbeddingRoute(
                provider=llm_decision.provider,
                collection=collection,
                dimensions=dims,
                decision=llm_decision,
            )

        # Camada 3: Fallback
        # Usar resultado da heurística mesmo com baixa confiança,
        # ou fallback para generalista
        if juris_conf > 0.3:
            provider = JURISDICTION_TO_PROVIDER.get(
                jurisdiction, EmbeddingProviderName.OPENAI
            )
            collection = JURISDICTION_TO_COLLECTION.get(jurisdiction, "general")
        else:
            provider = EmbeddingProviderName.OPENAI
            collection = "general"
            jurisdiction = Jurisdiction.GENERAL

        provider, collection = _routing_overrides(
            jurisdiction,
            default_provider=provider,
            default_collection=collection,
        )
        dims = EMBEDDING_COLLECTIONS.get(collection, {"dimensions": 3072})["dimensions"]

        decision = EmbeddingRoutingDecision(
            jurisdiction=jurisdiction,
            document_type=doc_type,
            language=language,
            provider=provider,
            collection=collection,
            confidence=max(combined_confidence, 0.3),
            method="fallback",
            reason=(
                "Fallback: heurística e LLM incertos, "
                f"melhor palpite: {jurisdiction.value}"
            ),
            skip_rag=skip_rag,
            estimated_pages=estimated_pages,
        )

        elapsed = (time.time() - start) * 1000
        logger.info(
            "EmbeddingRouter [fallback]: juris=%s, provider=%s, "
            "collection=%s (%.1fms)",
            jurisdiction.value,
            provider.value,
            collection,
            elapsed,
        )

        self._record_usage(decision)
        return EmbeddingRoute(
            provider=provider,
            collection=collection,
            dimensions=dims,
            decision=decision,
        )

    # ------------------------------------------------------------------
    # Embed com routing automático
    # ------------------------------------------------------------------

    async def embed_with_routing(
        self,
        texts: List[str],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> RoutedEmbeddingResult:
        """
        Gera embeddings com routing automático.

        Classifica o primeiro texto para decidir o provider,
        e aplica o mesmo provider a todos os textos do batch.

        Args:
            texts: Lista de textos.
            metadata: Metadata com hints opcionais.

        Returns:
            RoutedEmbeddingResult com vetores e info de routing.
        """
        if not texts:
            return RoutedEmbeddingResult(
                vectors=[],
                route=EmbeddingRoute(
                    provider=EmbeddingProviderName.OPENAI,
                    collection="general",
                    dimensions=3072,
                    decision=EmbeddingRoutingDecision(
                        jurisdiction=Jurisdiction.GENERAL,
                        document_type=DocumentType.GENERAL,
                        provider=EmbeddingProviderName.OPENAI,
                        collection="general",
                        confidence=0.0,
                        method="empty",
                        reason="Lista vazia",
                    ),
                ),
                processing_time_ms=0.0,
                texts_count=0,
            )

        start = time.time()

        # Rotear baseado no primeiro texto (ou texto mais representativo)
        sample_text = texts[0] if len(texts) == 1 else " ".join(t[:200] for t in texts[:3])
        route = await self.route(sample_text, metadata=metadata)

        # Obter provider
        provider = await self._get_provider(route.decision.provider)

        # Gerar embeddings
        try:
            if route.decision.provider == EmbeddingProviderName.JURISBERT:
                vectors = await provider.embed_batch(texts)
            elif route.decision.provider == EmbeddingProviderName.KANON2:
                vectors = await provider.embed_batch(texts, task="retrieval/document")
            elif route.decision.provider == EmbeddingProviderName.VOYAGE_V4:
                vectors = await provider.embed_batch(
                    texts, model="voyage-4-large", input_type="document"
                )
            elif route.decision.provider == EmbeddingProviderName.VOYAGE_LAW:
                vectors = await provider.embed_batch(
                    texts, model="voyage-law-2", input_type="document"
                )
            elif route.decision.provider == EmbeddingProviderName.VOYAGE_CONTEXT:
                model = os.getenv("VOYAGE_CONTEXT_MODEL", "voyage-context-3")
                vectors = await provider.embed_batch(
                    texts, model=model, input_type="document"
                )
            else:
                # OpenAI via EmbeddingsService existente
                vectors = await self._embed_openai(texts)
        except Exception as e:
            logger.error(
                "Provider %s falhou, fallback para OpenAI: %s",
                route.decision.provider.value,
                e,
            )
            try:
                vectors = await self._embed_openai(texts)
                route = EmbeddingRoute(
                    provider=EmbeddingProviderName.OPENAI,
                    collection="general",
                    dimensions=3072,
                    decision=EmbeddingRoutingDecision(
                        jurisdiction=route.decision.jurisdiction,
                        document_type=route.decision.document_type,
                        language=route.decision.language,
                        provider=EmbeddingProviderName.OPENAI,
                        collection="general",
                        confidence=route.decision.confidence * 0.5,
                        method="fallback_error",
                        reason=f"Provider {route.decision.provider.value} falhou: {e}",
                    ),
                )
            except Exception as e2:
                logger.error("OpenAI fallback também falhou: %s", e2)
                vectors = [[0.0] * route.dimensions for _ in texts]

        elapsed = (time.time() - start) * 1000

        return RoutedEmbeddingResult(
            vectors=vectors,
            route=route,
            processing_time_ms=round(elapsed, 2),
            texts_count=len(texts),
        )

    # ------------------------------------------------------------------
    # Search com routing automático
    # ------------------------------------------------------------------

    async def search_with_routing(
        self,
        query: str,
        metadata: Optional[Dict[str, Any]] = None,
        top_k: int = 10,
        include_legacy: bool = True,
    ) -> Dict[str, Any]:
        """
        Busca com routing automatico para a collection correta.

        Quando include_legacy=True (padrao), tambem busca nas collections
        legadas (lei, juris, doutrina, etc.) usando embedding OpenAI 3072d
        e faz merge via Reciprocal Rank Fusion (RRF).

        Args:
            query: Query de busca.
            metadata: Metadata com hints.
            top_k: Numero de resultados finais.
            include_legacy: Se True, busca tambem nas collections legadas.

        Returns:
            Dict com resultados (merged se legacy) e metadata de routing.
        """
        start = time.time()
        collections_searched: List[str] = []

        # Rotear query
        route = await self.route(query, metadata=metadata)

        # Gerar embedding da query via provider do routing
        provider = await self._get_provider(route.decision.provider)

        try:
            if route.decision.provider == EmbeddingProviderName.JURISBERT:
                query_vector = await provider.embed_query(query)
            elif route.decision.provider == EmbeddingProviderName.KANON2:
                query_vector = await provider.embed_query(
                    query, task="retrieval/query"
                )
            elif route.decision.provider == EmbeddingProviderName.VOYAGE_V4:
                query_vector = await provider.embed_query(
                    query, model="voyage-4-large", input_type="query"
                )
            elif route.decision.provider == EmbeddingProviderName.VOYAGE_LAW:
                query_vector = await provider.embed_query(
                    query, model="voyage-law-2", input_type="query"
                )
            elif route.decision.provider == EmbeddingProviderName.VOYAGE_CONTEXT:
                model = os.getenv("VOYAGE_CONTEXT_QUERY_MODEL", os.getenv("VOYAGE_CONTEXT_MODEL", "voyage-context-3"))
                query_vector = await provider.embed_query(
                    query, model=model, input_type="query"
                )
            else:
                from app.services.rag.core.embeddings import get_embeddings_service
                svc = get_embeddings_service()
                query_vector = svc.embed_query(query)
        except Exception as e:
            logger.error("Embedding query falhou: %s", e)
            from app.services.rag.core.embeddings import get_embeddings_service
            svc = get_embeddings_service()
            query_vector = svc.embed_query(query)

        # 1) Buscar na collection nova (roteada)
        new_results = await self._search_qdrant(
            collection=route.decision.collection,
            query_vector=query_vector,
            top_k=top_k,
        )
        collections_searched.append(route.decision.collection)

        # 2) Buscar nas collections legadas (se habilitado)
        legacy_results: List[Dict[str, Any]] = []
        if include_legacy:
            legacy_results = await self._search_legacy_collections(
                query=query,
                jurisdiction=route.decision.jurisdiction,
                top_k=top_k,
            )
            # Coletar nomes das collections legadas consultadas
            legacy_colls_set: set[str] = set()
            for r in legacy_results:
                coll = r.get("source_collection", "")
                if coll:
                    legacy_colls_set.add(coll)
            collections_searched.extend(sorted(legacy_colls_set))

        # 3) Merge via RRF (se ha resultados de ambas as fontes)
        if legacy_results and new_results:
            all_results_lists = [new_results, legacy_results]
            merged = reciprocal_rank_fusion(all_results_lists)
            final_results = merged[:top_k]
        elif legacy_results:
            final_results = legacy_results[:top_k]
        else:
            final_results = new_results

        elapsed = (time.time() - start) * 1000

        logger.info(
            "search_with_routing: query=%s..., collections=%s, "
            "new=%d, legacy=%d, final=%d (%.1fms)",
            query[:60],
            collections_searched,
            len(new_results),
            len(legacy_results),
            len(final_results),
            elapsed,
        )

        return {
            "results": final_results,
            "routing": route.decision.model_dump(),
            "collection": route.decision.collection,
            "provider": route.decision.provider.value,
            "processing_time_ms": round(elapsed, 2),
            "collections_searched": collections_searched,
        }

    # ------------------------------------------------------------------
    # Helpers internos
    # ------------------------------------------------------------------

    async def _get_provider(self, name: EmbeddingProviderName) -> Any:
        """Obtém provider de embedding (lazy init)."""
        if name in self._providers:
            return self._providers[name]

        with self._providers_lock:
            if name in self._providers:
                return self._providers[name]

            if name == EmbeddingProviderName.JURISBERT:
                from app.services.rag.jurisbert_embeddings import (
                    get_jurisbert_provider,
                )
                provider = get_jurisbert_provider()

            elif name == EmbeddingProviderName.KANON2:
                from app.services.rag.kanon_embeddings import (
                    get_kanon_provider,
                )
                provider = get_kanon_provider()

            elif name in (
                EmbeddingProviderName.VOYAGE_V4,
                EmbeddingProviderName.VOYAGE_LAW,
                EmbeddingProviderName.VOYAGE_CONTEXT,
                EmbeddingProviderName.VOYAGE_NOXTUA,
            ):
                from app.services.rag.voyage_embeddings import (
                    get_voyage_provider,
                )
                provider = get_voyage_provider()

            else:
                # OpenAI - retornar o EmbeddingsService existente
                from app.services.rag.core.embeddings import (
                    get_embeddings_service,
                )
                provider = get_embeddings_service()

            self._providers[name] = provider
            return provider

    async def _embed_openai(self, texts: List[str]) -> List[List[float]]:
        """Gera embeddings via OpenAI EmbeddingsService existente."""
        from app.services.rag.core.embeddings import get_embeddings_service

        svc = get_embeddings_service()
        return svc.embed_many(texts)

    def _get_qdrant_client(self) -> Any:
        """Retorna QdrantClient compartilhado (lazy init, thread-safe)."""
        if self._qdrant_client is not None:
            return self._qdrant_client

        with self._qdrant_lock:
            if self._qdrant_client is not None:
                return self._qdrant_client

            from qdrant_client import QdrantClient
            from app.services.rag.config import get_rag_config

            config = get_rag_config()
            self._qdrant_client = QdrantClient(
                url=config.qdrant_url,
                api_key=config.qdrant_api_key or None,
            )
            logger.info(
                "QdrantClient compartilhado inicializado: url=%s",
                config.qdrant_url,
            )
            return self._qdrant_client

    async def _search_qdrant(
        self,
        collection: str,
        query_vector: List[float],
        top_k: int = 10,
    ) -> List[Dict[str, Any]]:
        """Busca na collection Qdrant usando client compartilhado."""
        try:
            client = self._get_qdrant_client()

            # Verificar se collection existe
            try:
                client.get_collection(collection)
            except Exception:
                logger.warning(
                    "Collection '%s' não existe no Qdrant, tentando 'general'",
                    collection,
                )
                collection = "general"
                try:
                    client.get_collection(collection)
                except Exception:
                    logger.error("Collection 'general' também não existe")
                    return []

            try:
                from app.services.rag.config import get_rag_config as _get_rag_cfg

                _rcfg = _get_rag_cfg()
                _sparse_enabled = bool(getattr(_rcfg, "qdrant_sparse_enabled", False))
                _dense_name = str(getattr(_rcfg, "qdrant_dense_vector_name", "dense") or "dense")
            except Exception:
                _sparse_enabled = False
                _dense_name = "dense"

            # Hybrid collections use named dense vectors; try to pass a vector name if supported.
            # Keep compatibility with older qdrant-client versions.
            if _sparse_enabled:
                try:
                    results = client.search(
                        collection_name=collection,
                        query_vector=query_vector,
                        vector_name=_dense_name,
                        limit=top_k,
                    )
                except TypeError:
                    results = client.search(
                        collection_name=collection,
                        query_vector=query_vector,
                        limit=top_k,
                    )
            else:
                results = client.search(
                    collection_name=collection,
                    query_vector=query_vector,
                    limit=top_k,
                )

            return [
                {
                    "chunk_id": str(r.id),
                    "text": r.payload.get("text", "") if r.payload else "",
                    "score": float(r.score),
                    "metadata": r.payload or {},
                    "source_collection": collection,
                }
                for r in results
            ]

        except Exception as e:
            logger.error("Qdrant search falhou: %s", e)
            return []

    async def _search_legacy_collections(
        self,
        query: str,
        jurisdiction: Jurisdiction,
        top_k: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Busca nas collections legadas usando embedding OpenAI 3072d.

        As collections legadas (lei, juris, doutrina, pecas_modelo,
        local_chunks) usam todas OpenAI text-embedding-3-large com 3072
        dimensoes, independente do provider do routing.

        Args:
            query: Query de busca.
            jurisdiction: Jurisdicao detectada para selecionar collections.
            top_k: Numero de resultados por collection.

        Returns:
            Lista combinada de resultados de todas as collections legadas.
        """
        global _legacy_warning_emitted
        juris_key = jurisdiction.value
        legacy_colls = LEGACY_COLLECTIONS.get(juris_key, [])
        if not legacy_colls:
            return []

        if not _legacy_warning_emitted:
            logger.warning(
                "DEPRECATED: Searching legacy collections %s (OpenAI 3072d). "
                "Migrate to new collections (legal_br_v4 etc.) via "
                "EmbeddingRouter.migrate_collection(). "
                "Set include_legacy=False to disable.",
                legacy_colls,
            )
            _legacy_warning_emitted = True

        # Gerar embedding OpenAI para as collections legadas
        try:
            from app.services.rag.core.embeddings import get_embeddings_service
            svc = get_embeddings_service()
            legacy_vector = svc.embed_query(query)
        except Exception as e:
            logger.error(
                "Falha ao gerar embedding OpenAI para legacy search: %s", e
            )
            return []

        # Buscar em todas as collections legadas em paralelo
        tasks = []
        for coll_name in legacy_colls:
            tasks.append(
                self._search_qdrant(
                    collection=coll_name,
                    query_vector=legacy_vector,
                    top_k=top_k,
                )
            )

        all_results: List[Dict[str, Any]] = []
        try:
            results_per_coll = await asyncio.gather(*tasks, return_exceptions=True)
            for coll_name, coll_results in zip(legacy_colls, results_per_coll):
                if isinstance(coll_results, Exception):
                    logger.warning(
                        "Legacy search na collection '%s' falhou: %s",
                        coll_name,
                        coll_results,
                    )
                    continue
                if coll_results:
                    all_results.extend(coll_results)
        except Exception as e:
            logger.error("Falha no legacy search paralelo: %s", e)

        logger.info(
            "Legacy search: jurisdiction=%s, collections=%s, total_results=%d",
            juris_key,
            legacy_colls,
            len(all_results),
        )

        return all_results

    async def migrate_collection(
        self,
        source_collection: str,
        target_jurisdiction: Jurisdiction,
        batch_size: int = 100,
        limit: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Re-ingere documentos de uma collection legada na collection nova.

        Leh documentos da collection legada, gera novos embeddings usando
        o provider correto (JurisBERT, Kanon2, etc.) e insere na collection
        nova correspondente a jurisdicao.

        NAO modifica a collection legada.

        Args:
            source_collection: Nome da collection legada (ex: 'lei', 'juris').
            target_jurisdiction: Jurisdicao alvo para roteamento.
            batch_size: Tamanho do batch de migracao.
            limit: Limite de documentos a migrar (None = todos).

        Returns:
            Dict com estatisticas da migracao.
        """
        start = time.time()
        target_collection = JURISDICTION_TO_COLLECTION.get(
            target_jurisdiction, "general"
        )
        target_provider_name = JURISDICTION_TO_PROVIDER.get(
            target_jurisdiction, EmbeddingProviderName.OPENAI
        )
        target_provider_name, target_collection = _routing_overrides(
            target_jurisdiction,
            default_provider=target_provider_name,
            default_collection=target_collection,
        )

        logger.info(
            "migrate_collection: %s -> %s (provider=%s, batch=%d, limit=%s)",
            source_collection,
            target_collection,
            target_provider_name.value,
            batch_size,
            limit,
        )

        stats = {
            "source_collection": source_collection,
            "target_collection": target_collection,
            "target_provider": target_provider_name.value,
            "documents_read": 0,
            "documents_migrated": 0,
            "documents_failed": 0,
            "processing_time_ms": 0.0,
        }

        try:
            client = self._get_qdrant_client()

            # Verificar se source existe
            try:
                client.get_collection(source_collection)
            except Exception:
                logger.error(
                    "Collection legada '%s' nao existe", source_collection
                )
                stats["error"] = f"Collection '{source_collection}' nao encontrada"
                return stats

            # Scroll por todos os documentos
            offset = None
            total_migrated = 0

            while True:
                scroll_result = client.scroll(
                    collection_name=source_collection,
                    limit=batch_size,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False,
                )

                points, next_offset = scroll_result
                if not points:
                    break

                stats["documents_read"] += len(points)

                # Extrair textos e metadata
                texts = []
                payloads = []
                point_ids = []
                for point in points:
                    text = (point.payload or {}).get("text", "")
                    if text.strip():
                        texts.append(text)
                        payloads.append(point.payload or {})
                        point_ids.append(point.id)

                if texts:
                    try:
                        # Optional: contextual embeddings (prefix metadata context before embedding)
                        contextual_enabled = bool(os.getenv("RAG_CONTEXTUAL_EMBEDDINGS_ENABLED", "").strip().lower() in ("1", "true", "yes", "on"))
                        max_prefix = int(os.getenv("RAG_CONTEXTUAL_EMBEDDINGS_MAX_PREFIX_CHARS", "240") or "240")
                        # Avoid double-contextualization when using voyage-context-3.
                        if target_provider_name == EmbeddingProviderName.VOYAGE_CONTEXT:
                            contextual_enabled = False
                        if contextual_enabled:
                            try:
                                from app.services.rag.core.contextual_embeddings import build_embedding_input
                            except Exception:
                                build_embedding_input = None  # type: ignore
                            if build_embedding_input is not None:
                                contextual_texts = []
                                contextual_payload_extras = []
                                for t, pl in zip(texts, payloads):
                                    emb_in, info = build_embedding_input(
                                        t,
                                        {**(pl or {}), "jurisdiction": target_jurisdiction.value},
                                        enabled=True,
                                        max_prefix_chars=max_prefix,
                                    )
                                    contextual_texts.append(emb_in)
                                    contextual_payload_extras.append(info.to_payload_fields())
                                texts = contextual_texts
                            else:
                                contextual_payload_extras = [{"_embedding_variant": "raw"} for _ in texts]
                        else:
                            contextual_payload_extras = [{"_embedding_variant": "raw"} for _ in texts]

                        # Gerar novos embeddings com o provider correto
                        embed_result = await self.embed_with_routing(
                            texts,
                            metadata={
                                "jurisdiction": target_jurisdiction.value,
                            },
                        )

                        # Inserir na collection nova
                        from qdrant_client.models import PointStruct
                        try:
                            from app.services.rag.config import get_rag_config as _get_rag_cfg

                            _rcfg = _get_rag_cfg()
                            _sparse_enabled = bool(getattr(_rcfg, "qdrant_sparse_enabled", False))
                            _dense_name = str(getattr(_rcfg, "qdrant_dense_vector_name", "dense") or "dense")
                        except Exception:
                            _sparse_enabled = False
                            _dense_name = "dense"

                        new_points = []
                        for i, (pid, payload, vector) in enumerate(
                            zip(point_ids, payloads, embed_result.vectors)
                        ):
                            # Adicionar metadata de migracao
                            enriched_payload = dict(payload)
                            enriched_payload["_migrated_from"] = source_collection
                            enriched_payload["_migration_timestamp"] = time.time()
                            try:
                                enriched_payload.update(contextual_payload_extras[i])
                            except Exception:
                                pass

                            vec_any: Any = vector
                            if _sparse_enabled:
                                # Hybrid collections use named dense vectors.
                                vec_any = {_dense_name: vector}
                            new_points.append(PointStruct(id=pid, vector=vec_any, payload=enriched_payload))

                        client.upsert(
                            collection_name=target_collection,
                            points=new_points,
                        )

                        total_migrated += len(new_points)
                        stats["documents_migrated"] = total_migrated

                        logger.info(
                            "migrate_collection: batch migrado %d docs "
                            "(%d total) %s -> %s",
                            len(new_points),
                            total_migrated,
                            source_collection,
                            target_collection,
                        )

                    except Exception as e:
                        stats["documents_failed"] += len(texts)
                        logger.error(
                            "Falha ao migrar batch de %s: %s",
                            source_collection,
                            e,
                        )

                # Verificar limite
                if limit and total_migrated >= limit:
                    break

                if next_offset is None:
                    break
                offset = next_offset

        except Exception as e:
            logger.error("migrate_collection falhou: %s", e)
            stats["error"] = str(e)

        elapsed = (time.time() - start) * 1000
        stats["processing_time_ms"] = round(elapsed, 2)

        logger.info(
            "migrate_collection concluida: %s -> %s, "
            "lidos=%d, migrados=%d, falhas=%d (%.1fms)",
            source_collection,
            target_collection,
            stats["documents_read"],
            stats["documents_migrated"],
            stats["documents_failed"],
            elapsed,
        )

        return stats


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_router: Optional[EmbeddingRouter] = None
_router_lock = threading.Lock()


def get_embedding_router() -> EmbeddingRouter:
    """Retorna o singleton do EmbeddingRouter."""
    global _router
    if _router is not None:
        return _router

    with _router_lock:
        if _router is None:
            _router = EmbeddingRouter()

    return _router


def reset_embedding_router() -> None:
    """Reseta o singleton (útil para testes)."""
    global _router
    with _router_lock:
        _router = None
        logger.info("EmbeddingRouter singleton resetado")
