from __future__ import annotations

from datetime import datetime
import re
from typing import Any, Mapping

from app.services.ai.citations.metadata import (
    build_numeric_prefix,
    extract_reference_metadata,
    short_month_name,
)

def _compress_author_vancouver(name: str) -> str:
    raw = str(name or "").strip()
    if not raw:
        return ""

    if "," in raw:
        last, _, first = raw.partition(",")
        last = last.strip()
        initials = "".join(tok[0].upper() for tok in re.split(r"\s+", first.strip()) if tok)
        return f"{last} {initials}".strip()

    tokens = [tok for tok in re.split(r"\s+", raw) if tok]
    if len(tokens) == 1:
        return tokens[0]

    last = tokens[-1]
    initials = "".join(tok[0].upper() for tok in tokens[:-1] if tok)
    return f"{last} {initials}".strip()


def format_vancouver_reference(
    source: Mapping[str, Any],
    *,
    accessed_at: datetime | None = None,
    number: int | None = None,
) -> str:
    meta = extract_reference_metadata(source, accessed_at=accessed_at)
    dt = meta["accessed_at"] if isinstance(meta.get("accessed_at"), datetime) else datetime.now()
    month = short_month_name(dt.month).replace(".", "")
    prefix = build_numeric_prefix(number)

    authors = [str(author).strip() for author in meta.get("authors") or [] if str(author).strip()]
    compressed = [_compress_author_vancouver(author) for author in authors]
    compressed = [author for author in compressed if author]
    author_part = ", ".join(compressed[:6]) + (", et al." if len(compressed) > 6 else "")

    title = str(meta.get("title") or "Untitled").strip()
    place = str(meta.get("place") or "").strip()
    publisher = str(meta.get("publisher") or str(meta.get("site") or "")).strip()
    year = str(meta.get("year") or "n.d.").strip()
    volume = str(meta.get("volume") or "").strip()
    issue = str(meta.get("issue") or "").strip()
    pages = str(meta.get("pages") or "").strip()
    url = str(meta.get("url") or "").strip()

    line_parts = []
    if author_part:
        line_parts.append(f"{author_part}.")
    line_parts.append(f"{title}.")
    line_parts.append("[Internet].")
    if place or publisher:
        line_parts.append(f"{place + ': ' if place else ''}{publisher}; {year}.")
    else:
        line_parts.append(f"{year}.")

    journal_segment = ""
    if volume:
        journal_segment = volume
        if issue:
            journal_segment += f"({issue})"
        if pages:
            journal_segment += f":{pages}"
    elif pages:
        journal_segment = pages
    if journal_segment:
        line_parts.append(f"{journal_segment}.")

    if url:
        line_parts.append(f"[cited {dt.year} {month} {dt.day:02d}].")
        line_parts.append(f"Available from: {url}.")

    return f"{prefix}{' '.join(line_parts)}"
