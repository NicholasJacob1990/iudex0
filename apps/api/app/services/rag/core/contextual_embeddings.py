"""
Contextual Embeddings (Contextual Retrieval)

Implements a lightweight "context prefix" strategy for embeddings:
- Keep the stored chunk text unchanged (for citations and UX)
- Prepend a short, metadata-derived context line when generating embeddings

This is designed to be used during ingestion/migration (offline) so that the
vector index is built with contextualized representations.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple


_WS_RE = re.compile(r"\s+")

# Regex patterns for normative chain extraction from chunk text
_RE_ART_WITH_LEI = re.compile(
    r"Art\.?\s*(\d+[A-Za-z]?(?:-[A-Za-z])?)"
    r"(?:\s*,?\s*(?:par\.|§)\s*(\d+[ºo]?))??"
    r"(?:\s*,?\s*(?:inc\.|inciso)\s*([IVXLCDM]+))?"
    r"\s+(?:do|da|dos|das)\s+"
    r"([A-Za-z][A-Za-z0-9./\s]{1,30}?)(?:\s*[,;.\)]|$)",
    re.MULTILINE | re.IGNORECASE,
)

_RE_SUMULA = re.compile(
    r"S[úu]mula(?:\s+Vinculante)?\s+(\d+)\s+(?:do|da)\s+(ST[FJ]|TST|TSE)",
    re.IGNORECASE,
)


def _extract_normative_chain(text: str) -> str:
    """
    Extract normative references from chunk text and format as a chain prefix.
    Returns a compact string like: "[Art. 150, § 1º do CTN | Súmula 435 do STJ]"
    """
    if not text:
        return ""

    refs = []
    # Extract article references with their Lei
    for m in _RE_ART_WITH_LEI.finditer(text):
        art_num = m.group(1)
        par = m.group(2)
        inc = m.group(3)
        lei = m.group(4).strip()
        ref = f"Art. {art_num}"
        if par:
            ref += f", § {par}"
        if inc:
            ref += f", inc. {inc}"
        ref += f" {m.group(0).split(lei)[0].strip().split()[-1]} {lei}"
        refs.append(ref)

    # Extract súmula references
    for m in _RE_SUMULA.finditer(text):
        refs.append(f"Súmula {m.group(1)} do {m.group(2).upper()}")

    if not refs:
        return ""

    # Deduplicate preserving order
    seen = set()
    unique = []
    for r in refs:
        key = r.lower()
        if key not in seen:
            seen.add(key)
            unique.append(r)

    return "[" + " | ".join(unique[:5]) + "]"  # max 5 refs


@dataclass(frozen=True)
class ContextualEmbeddingInfo:
    enabled: bool
    variant: str
    prefix: str

    def to_payload_fields(self) -> Dict[str, Any]:
        # Keep payload small and easily filterable/debuggable.
        if not self.enabled:
            return {"_embedding_variant": "raw"}
        return {
            "_embedding_variant": self.variant,
            "_embedding_prefix": self.prefix,
        }


def _clean(s: str) -> str:
    return _WS_RE.sub(" ", (s or "").strip())


def build_context_prefix(
    metadata: Dict[str, Any],
    *,
    max_chars: int = 240,
    chunk_text: str = "",
) -> str:
    """
    Build a short, human-readable context prefix from chunk/document metadata
    and (optionally) normative references extracted from the chunk text.

    The goal is to disambiguate chunks that are locally ambiguous when embedded
    in isolation (common in legal corpora: article fragments, definitions, etc).
    """
    if not isinstance(metadata, dict):
        return ""

    scope = _clean(str(metadata.get("scope") or ""))
    source_type = _clean(str(metadata.get("source_type") or metadata.get("dataset") or ""))
    title = _clean(str(metadata.get("title") or metadata.get("document_title") or ""))
    filename = _clean(str(metadata.get("filename") or metadata.get("source_file") or ""))
    jurisdiction = _clean(str(metadata.get("jurisdiction") or ""))
    doc_id = _clean(str(metadata.get("doc_id") or metadata.get("document_id") or ""))
    case_id = _clean(str(metadata.get("case_id") or ""))

    parts = []
    if title:
        parts.append(f"Documento: {title}")
    elif filename:
        parts.append(f"Arquivo: {filename}")
    elif doc_id:
        parts.append(f"Documento: {doc_id}")

    if source_type:
        parts.append(f"Fonte: {source_type}")
    if jurisdiction:
        parts.append(f"Jurisdicao: {jurisdiction}")
    if scope:
        if scope == "local" and case_id:
            parts.append(f"Escopo: local (case_id={case_id})")
        else:
            parts.append(f"Escopo: {scope}")

    # Extract normative chain from chunk text (Art. X do Y, Súmula Z do STJ)
    normative_chain = _extract_normative_chain(chunk_text) if chunk_text else ""
    if normative_chain:
        parts.append(normative_chain)

    prefix = " | ".join([p for p in parts if p])
    prefix = _clean(prefix)
    if not prefix:
        return ""

    if max_chars and len(prefix) > max_chars:
        prefix = prefix[: max(0, max_chars - 1)].rstrip() + "…"
    return prefix


def build_embedding_input(
    chunk_text: str,
    metadata: Dict[str, Any],
    *,
    enabled: bool,
    max_prefix_chars: int = 240,
    variant: str = "ctx_v1",
) -> Tuple[str, ContextualEmbeddingInfo]:
    """
    Build the text used for embedding (possibly contextualized) and return
    info that can be stored alongside the chunk for audit/debug.
    """
    raw = (chunk_text or "").strip()
    if not enabled:
        return raw, ContextualEmbeddingInfo(enabled=False, variant="raw", prefix="")

    prefix = build_context_prefix(metadata, max_chars=max_prefix_chars)
    if not prefix:
        return raw, ContextualEmbeddingInfo(enabled=False, variant="raw", prefix="")

    # Ensure the prefix is clearly separated; keep it stable for cosine space.
    embedded = f"{prefix}\n\n{raw}"
    return embedded, ContextualEmbeddingInfo(enabled=True, variant=variant, prefix=prefix)


def is_contextual_variant(payload: Dict[str, Any], *, variant: Optional[str] = None) -> bool:
    v = str((payload or {}).get("_embedding_variant") or "")
    if not v:
        return False
    if variant:
        return v == variant
    return v != "raw"

