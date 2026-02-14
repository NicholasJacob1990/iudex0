"""
Contextual Retrieval: LLM-generated prefix for each chunk.

Uses Gemini Flash to generate a short context that includes:
- Source normative (Lei, Código)
- Device (Artigo, §, inciso)
- Discipline and topic
"""

from __future__ import annotations

import logging
import re
from typing import List, Optional

from ..config import settings

logger = logging.getLogger(__name__)

CONTEXT_PROMPT = """Documento: {doc_prefix}

Chunk: {chunk_text}

Gere 2-3 frases curtas situando este trecho no documento. OBRIGATÓRIO incluir:
1. FONTE NORMATIVA: Identifique TODA lei, código ou norma mencionada (usar sigla canônica: CF, CTN, CC, CPC, etc.)
2. DISPOSITIVO: Identifique TODOS os artigos discutidos, com cadeia completa (ex: "Art. 150, § 1º do CTN", nunca "§ 1º" isolado)
3. DISCIPLINA e TEMA: área do direito e assunto específico
4. Se o chunk menciona §, inciso ou alínea sem artigo explícito, INFIRA o artigo a partir do contexto.

Formato: "[FONTE: {{sigla}}] [DISPOSITIVO: Art. X, § Y do {{sigla}}] [TEMA: ...]"
Responda SOMENTE o contexto, sem explicações."""

# Regex fallback for when LLM is not available
_RE_ART_WITH_LEI = re.compile(
    r"Art\.?\s*(\d+[A-Za-z]?)"
    r"(?:\s*,?\s*(?:par\.|§)\s*(\d+[ºo]?))?"
    r"(?:\s*,?\s*(?:inc\.|inciso)\s*([IVXLCDM]+))?"
    r"\s+(?:do|da|dos|das)\s+"
    r"([A-Z][A-Za-z0-9./\s]{1,30}?)(?:\s*[,;.\)]|$)",
    re.MULTILINE,
)


def build_context_prefix_regex(chunk_text: str) -> str:
    """Lightweight regex-based context prefix (no LLM cost)."""
    refs = []
    for m in _RE_ART_WITH_LEI.finditer(chunk_text):
        art = f"Art. {m.group(1)}"
        if m.group(2):
            art += f", § {m.group(2)}"
        if m.group(3):
            art += f", inc. {m.group(3)}"
        lei = m.group(4).strip()
        refs.append(f"{art} do {lei}" if "do" not in art else art)

    if not refs:
        return ""

    seen = set()
    unique = []
    for r in refs:
        if r.lower() not in seen:
            seen.add(r.lower())
            unique.append(r)

    return "[" + " | ".join(unique[:5]) + "]"


def build_context_prefix_llm(
    chunk_text: str,
    doc_text_prefix: str,
    *,
    model: Optional[str] = None,
) -> str:
    """Use Gemini Flash to generate a rich contextual prefix."""
    try:
        import httpx

        model = model or settings.contextual_llm_model
        api_key = settings.google_api_key
        if not api_key:
            return build_context_prefix_regex(chunk_text)

        prompt = CONTEXT_PROMPT.format(
            doc_prefix=doc_text_prefix[:3000],
            chunk_text=chunk_text[:2000],
        )

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={api_key}"
        )
        resp = httpx.post(
            url,
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"maxOutputTokens": 200, "temperature": 0.1},
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        return text.strip()

    except Exception as e:
        logger.warning(f"LLM context prefix failed, falling back to regex: {e}")
        return build_context_prefix_regex(chunk_text)


def build_context_prefixes(
    chunks_texts: List[str],
    doc_text_prefix: str,
    *,
    use_llm: bool = False,
) -> List[str]:
    """Build context prefixes for a batch of chunks."""
    if use_llm and settings.google_api_key:
        return [
            build_context_prefix_llm(text, doc_text_prefix)
            for text in chunks_texts
        ]
    return [build_context_prefix_regex(text) for text in chunks_texts]
