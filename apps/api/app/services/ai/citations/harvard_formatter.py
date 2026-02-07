from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from app.services.ai.citations.metadata import (
    build_numeric_prefix,
    extract_reference_metadata,
    long_month_name,
)


def format_harvard_reference(
    source: Mapping[str, Any],
    *,
    accessed_at: datetime | None = None,
    number: int | None = None,
) -> str:
    meta = extract_reference_metadata(source, accessed_at=accessed_at)
    dt = meta["accessed_at"] if isinstance(meta.get("accessed_at"), datetime) else datetime.now()
    month = long_month_name(dt.month)
    prefix = build_numeric_prefix(number)

    author = str(meta.get("author") or "").strip()
    title = str(meta.get("title") or "Untitled").strip()
    year = str(meta.get("year") or "n.d.").strip()
    url = str(meta.get("url") or "").strip()
    site = str(meta.get("site") or "").strip()

    author_part = f"{author} " if author else ""
    container_part = f", {site}" if site else ""
    if not url:
        return f"{prefix}{author_part}({year}) '{title}'{container_part}."
    return (
        f"{prefix}{author_part}({year}) '{title}'{container_part}. "
        f"Available at: {url} (Accessed: {dt.day} {month} {dt.year})."
    )
