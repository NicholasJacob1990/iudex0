from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from app.services.ai.citations.metadata import (
    build_numeric_prefix,
    extract_reference_metadata,
)

def format_forense_br_reference(
    source: Mapping[str, Any],
    *,
    accessed_at: datetime | None = None,
    number: int | None = None,
) -> str:
    meta = extract_reference_metadata(source, accessed_at=accessed_at)
    dt = meta["accessed_at"] if isinstance(meta.get("accessed_at"), datetime) else datetime.now()

    title = str(meta.get("title") or "Fonte").strip()
    tribunal = str(meta.get("court") or "").strip()
    processo = str(meta.get("docket") or "").strip()
    year = str(meta.get("year") or "").strip()
    url = str(meta.get("url") or "").strip()
    page = meta.get("pin_cite")
    prefix = build_numeric_prefix(number)

    parts = [f"{prefix}{title}."]
    if tribunal:
        parts.append(f"{tribunal}.")
    if processo:
        parts.append(f"Processo {processo}.")
    if year and year != "n.d.":
        parts.append(f"{year}.")
    if page:
        parts.append(f"p. {page}.")
    if url:
        parts.append(f"Disponível em: {url}.")
        parts.append(f"Acesso em: {dt.day:02d}/{dt.month:02d}/{dt.year}.")
    return " ".join(parts).replace("..", ".")
