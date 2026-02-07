from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from app.services.ai.citations.metadata import (
    build_numeric_prefix,
    extract_reference_metadata,
    short_month_name,
)

def _format_case_alwd(meta: Mapping[str, Any]) -> str:
    case_name = str(meta.get("title") or "Case").strip()
    reporter = str(meta.get("reporter") or meta.get("citation") or "").strip()
    year = str(meta.get("year") or "n.d.").strip()
    court = str(meta.get("court") or "").strip()
    pin_cite = meta.get("pin_cite")

    if not reporter:
        return ""

    pin_part = f" at {pin_cite}" if pin_cite else ""
    court_part = f"{court} " if court else ""
    return f"{case_name}, {reporter}{pin_part} ({court_part}{year})."


def format_alwd_reference(
    source: Mapping[str, Any],
    *,
    accessed_at: datetime | None = None,
    number: int | None = None,
) -> str:
    meta = extract_reference_metadata(source, accessed_at=accessed_at)
    dt = meta["accessed_at"] if isinstance(meta.get("accessed_at"), datetime) else datetime.now()
    month = short_month_name(dt.month)
    prefix = build_numeric_prefix(number)

    case_line = _format_case_alwd(meta)
    if case_line:
        return f"{prefix}{case_line}"

    author = str(meta.get("author") or "").strip()
    title = str(meta.get("title") or "Source").strip()
    url = str(meta.get("url") or "").strip()
    site = str(meta.get("site") or "").strip()
    year = str(meta.get("year") or "n.d.").strip()

    bits = [part for part in [author, title, site, f"({year})"] if part]
    base = ", ".join(bits) if bits else title

    if not url:
        return f"{prefix}{base}."
    return f"{prefix}{base}, {url} (visited {month} {dt.day}, {dt.year})."
