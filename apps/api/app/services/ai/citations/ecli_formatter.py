from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from app.services.ai.citations.metadata import (
    build_numeric_prefix,
    extract_reference_metadata,
    french_month_name,
)


def format_ecli_reference(
    source: Mapping[str, Any],
    *,
    accessed_at: datetime | None = None,
    number: int | None = None,
) -> str:
    meta = extract_reference_metadata(source, accessed_at=accessed_at)
    dt = meta["accessed_at"] if isinstance(meta.get("accessed_at"), datetime) else datetime.now()
    month = french_month_name(dt.month)
    prefix = build_numeric_prefix(number)

    ecli = str(meta.get("ecli") or "").strip()
    title = str(meta.get("title") or "Case").strip()
    court = str(meta.get("court") or "").strip()
    year = str(meta.get("year") or "").strip()
    reporter = str(meta.get("reporter") or meta.get("citation") or "").strip()
    url = str(meta.get("url") or "").strip()

    if ecli:
        bits = [f"ECLI:{ecli}" if not ecli.upper().startswith("ECLI:") else ecli]
        bits.append(title)
        if reporter:
            bits.append(reporter)
        if court or year:
            bits.append(f"({court + ', ' if court else ''}{year})".replace(", )", ")"))
        if url:
            bits.append(f"<{url}>")
        return f"{prefix}{', '.join(bits[:-1])} {bits[-1]}.".replace("  ", " ")

    if url:
        if court or year:
            return f"{prefix}{title} ({court + ', ' if court else ''}{year}). <{url}> accessed {dt.day} {month} {dt.year}."
        return f"{prefix}{title}. <{url}> accessed {dt.day} {month} {dt.year}."
    return f"{prefix}{title}."
