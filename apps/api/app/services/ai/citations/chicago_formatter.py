from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from app.services.ai.citations.metadata import (
    build_numeric_prefix,
    extract_reference_metadata,
    long_month_name,
)

def _format_case_chicago(meta: Mapping[str, Any]) -> str:
    case_name = str(meta.get("title") or "Case").strip()
    reporter = str(meta.get("reporter") or meta.get("citation") or "").strip()
    year = str(meta.get("year") or "n.d.").strip()
    court = str(meta.get("court") or "").strip()
    pin_cite = meta.get("pin_cite")

    if not reporter:
        return ""

    pin = f", {pin_cite}" if pin_cite else ""
    court_part = f", {court}" if court else ""
    return f"{case_name}. {reporter}{pin} ({year}{court_part})."


def format_chicago_reference(
    source: Mapping[str, Any],
    *,
    accessed_at: datetime | None = None,
    number: int | None = None,
) -> str:
    meta = extract_reference_metadata(source, accessed_at=accessed_at)
    dt = meta["accessed_at"] if isinstance(meta.get("accessed_at"), datetime) else datetime.now()
    month = long_month_name(dt.month)
    prefix = build_numeric_prefix(number)

    case_line = _format_case_chicago(meta)
    if case_line:
        return f"{prefix}{case_line}"

    author = str(meta.get("author") or "").strip()
    title = str(meta.get("title") or "Untitled").strip()
    site = str(meta.get("site") or "").strip()
    published = meta.get("published_at")
    url = str(meta.get("url") or "").strip()

    parts = []
    if author:
        parts.append(f"{author}.")
    parts.append(f"\"{title}.\"")
    if site:
        parts.append(f"{site}.")

    if isinstance(published, datetime):
        pub_month = long_month_name(published.month)
        parts.append(f"{pub_month} {published.day}, {published.year}.")
    else:
        parts.append(f"Accessed {month} {dt.day}, {dt.year}.")

    if url:
        parts.append(f"{url}.")

    return f"{prefix}{' '.join(parts)}"
