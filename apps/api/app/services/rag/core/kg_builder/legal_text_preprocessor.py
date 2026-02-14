"""
Legal text pre-processing helpers for KG Builder.

Ported from the standalone neo4j-ingestor `ingest_v2.py`:
- Remove common PDF artifacts (TOC lines, page numbers, course headers, emojis)
- Split long text into smaller segments to reduce cross-segment contamination
- Filter low-quality segments before LLM extraction

These helpers are intentionally conservative and should be enabled primarily
for the legal domain.
"""

from __future__ import annotations

import re
from typing import List, Tuple

_EMOJI_RE = re.compile(
    "[\U0001F300-\U0001F9FF\U00002702-\U000027B0\U0001FA00-\U0001FA6F"
    "\U0001FA70-\U0001FAFF\U00002600-\U000026FF\U0000FE00-\U0000FE0F"
    "\U0000200D\U00002B50\U00002B55\U000023CF\U000023E9-\U000023F3"
    "\U000023F8-\U000023FA\U0000231A\U0000231B]+",
    re.UNICODE,
)
_TOC_LINE_RE = re.compile(r"^.*?\.{3,}.*$", re.MULTILINE)
_PAGE_NUM_RE = re.compile(r"^\s*\d{1,4}\s*$", re.MULTILINE)
_EXCESS_BLANK_RE = re.compile(r"\n{4,}")

_HEADER_PATTERNS = [
    re.compile(r"^\s*Curso Intensivo:.*$", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^\s*Turma de Reta Final.*$", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^\s*PGM-?RJ\s*\(?Procurador\)?\s*$", re.MULTILINE | re.IGNORECASE),
]


def clean_legal_text(text: str) -> str:
    """Remove common PDF artifacts and normalize whitespace."""
    if not text:
        return text
    text = _TOC_LINE_RE.sub("", text)
    text = _EMOJI_RE.sub("", text)
    text = _PAGE_NUM_RE.sub("", text)
    for p in _HEADER_PATTERNS:
        text = p.sub("", text)
    text = _EXCESS_BLANK_RE.sub("\n\n", text)
    # Drop empty lines
    lines = [l for l in text.split("\n") if l.strip()]
    return "\n".join(lines).strip()


def is_quality_segment(segment: str, *, min_chars: int = 200) -> bool:
    """Heuristic quality check to skip TOC/garbage segments."""
    if not segment:
        return False
    stripped = segment.strip()
    if len(stripped) < min_chars:
        return False

    # Require reasonable alnum density
    alnum = sum(1 for c in stripped if c.isalnum())
    if len(stripped) > 0 and (alnum / len(stripped)) < 0.4:
        return False

    # Very short segments that look like TOC should be dropped
    if len(stripped) < 600:
        lower = stripped.lower()
        if any(w in lower for w in ("sumario", "sum\u00e1rio", "indice", "\u00edndice", "table of contents")):
            return False
    return True


def split_text_into_segments(
    text: str,
    *,
    segment_size: int,
    overlap: int = 200,
) -> List[str]:
    """
    Split text into segments of ~segment_size chars with overlap.

    Tries to split on paragraph/newline boundaries to keep local context.
    """
    if not text:
        return []
    if len(text) <= segment_size:
        return [text]

    segments: List[str] = []
    start = 0
    while start < len(text):
        end = start + segment_size
        if end < len(text):
            # Prefer paragraph boundary
            nl = text.rfind("\n\n", start + int(segment_size * 0.6), end + 200)
            if nl > start:
                end = nl
            else:
                # Fallback to single newline
                nl = text.rfind("\n", start + int(segment_size * 0.8), end + 100)
                if nl > start:
                    end = nl
        seg = text[start:end].strip()
        if seg:
            segments.append(seg)
        start = max(0, end - overlap)

    # Deduplicate empty/whitespace-only segments
    return [s for s in segments if s and s.strip()]


def prepare_segments(
    raw_text: str,
    *,
    segment_size: int,
    overlap: int,
    quality_filter: bool,
) -> Tuple[List[str], int]:
    """
    Clean + split + optional quality filter.

    Returns: (segments, skipped_count)
    """
    cleaned = clean_legal_text(raw_text)
    segments = split_text_into_segments(cleaned, segment_size=segment_size, overlap=overlap)
    if not quality_filter:
        return segments, 0
    kept = [s for s in segments if is_quality_segment(s)]
    return kept, max(0, len(segments) - len(kept))

