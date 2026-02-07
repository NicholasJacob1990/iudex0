from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from app.services.ai.citations.metadata import (
    build_numeric_prefix,
    extract_reference_metadata,
    short_month_name,
)

def _format_case_bluebook(meta: Mapping[str, Any]) -> str:
    case_name = str(meta.get("title") or "Case").strip()
    reporter = str(meta.get("reporter") or meta.get("citation") or "").strip()
    year = str(meta.get("year") or "n.d.").strip()
    court = str(meta.get("court") or "").strip()
    pin_cite = meta.get("pin_cite")

    if reporter:
        pin_part = f", {pin_cite}" if pin_cite else ""
        court_part = f"{court} " if court else ""
        return f"{case_name}, {reporter}{pin_part} ({court_part}{year})."

    docket = str(meta.get("docket") or "").strip()
    if docket:
        court_part = f", {court}" if court else ""
        return f"{case_name}, No. {docket}{court_part} ({year})."

    return ""


def format_bluebook_reference(
    source: Mapping[str, Any],
    *,
    accessed_at: datetime | None = None,
    number: int | None = None,
) -> str:
    meta = extract_reference_metadata(source, accessed_at=accessed_at)
    dt = meta["accessed_at"] if isinstance(meta.get("accessed_at"), datetime) else datetime.now()
    month = short_month_name(dt.month)
    prefix = build_numeric_prefix(number)

    case_line = _format_case_bluebook(meta)
    if case_line:
        return f"{prefix}{case_line}"

    author = str(meta.get("author") or "").strip()
    title = str(meta.get("title") or "Source").strip()
    url = str(meta.get("url") or "").strip()
    year = str(meta.get("year") or "n.d.").strip()
    site = str(meta.get("site") or "").strip()

    parts = []
    if author:
        parts.append(author)
    parts.append(f"*{title}*")
    if site:
        parts.append(site)
    parts.append(f"({year})")
    base = ", ".join(parts[:-1] + [parts[-1]]) if parts else f"*{title}* ({year})"

    if not url:
        return f"{prefix}{base}."
    return f"{prefix}{base}, {url} (last visited {month} {dt.day}, {dt.year})."
