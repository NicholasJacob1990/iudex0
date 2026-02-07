from __future__ import annotations

from datetime import datetime
import re
from typing import Any, Mapping

from app.services.ai.citations.metadata import (
    build_numeric_prefix,
    extract_reference_metadata,
    long_month_name,
)

def _format_single_author_apa(name: str) -> str:
    raw = str(name or "").strip()
    if not raw:
        return ""

    if "," in raw:
        last, _, first = raw.partition(",")
        last = last.strip()
        tokens = [tok for tok in re.split(r"\s+", first.strip()) if tok]
        initials = " ".join(f"{tok[0].upper()}." for tok in tokens if tok)
        return f"{last}, {initials}".strip(", ")

    tokens = [tok for tok in re.split(r"\s+", raw) if tok]
    if len(tokens) == 1:
        return tokens[0]

    last = tokens[-1]
    initials = " ".join(f"{tok[0].upper()}." for tok in tokens[:-1])
    return f"{last}, {initials}".strip(", ")


def _format_authors_apa(authors: list[str], fallback: str) -> str:
    names = [_format_single_author_apa(name) for name in authors if str(name or "").strip()]
    names = [name for name in names if name]
    if not names and fallback:
        names = [_format_single_author_apa(fallback)]

    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]}, & {names[1]}"
    return ", ".join(names[:-1]) + f", & {names[-1]}"


def format_apa_reference(
    source: Mapping[str, Any],
    *,
    accessed_at: datetime | None = None,
    number: int | None = None,
) -> str:
    meta = extract_reference_metadata(source, accessed_at=accessed_at)
    dt = meta["accessed_at"] if isinstance(meta.get("accessed_at"), datetime) else datetime.now()
    prefix = build_numeric_prefix(number)

    author_part = _format_authors_apa(meta.get("authors") or [], str(meta.get("author") or ""))
    title = str(meta.get("title") or "Untitled").strip()
    year = str(meta.get("year") or "n.d.").strip()
    site = str(meta.get("site") or "").strip()
    url = str(meta.get("url") or "").strip()

    parts = []
    if author_part:
        parts.append(f"{author_part}.")
    parts.append(f"({year}).")
    parts.append(f"{title}.")
    if site:
        parts.append(f"{site}.")

    if url:
        if year.lower() == "n.d.":
            month = long_month_name(dt.month)
            parts.append(f"Retrieved {month} {dt.day}, {dt.year}, from {url}")
        else:
            parts.append(url)

    return f"{prefix}{' '.join(parts).strip()}"
