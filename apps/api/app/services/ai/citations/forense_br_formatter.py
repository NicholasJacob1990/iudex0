from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping


def format_forense_br_reference(
    source: Mapping[str, Any],
    *,
    accessed_at: datetime | None = None,
    number: int | None = None,
) -> str:
    title = str(source.get("title") or "Fonte").strip()
    tribunal = str(source.get("tribunal") or "").strip()
    url = str(source.get("url") or source.get("source_url") or "").strip()
    page = source.get("source_page")

    prefix = f"[{number}] " if number is not None else ""
    parts = [f"{prefix}{title}."]
    if tribunal:
        parts.append(f"Tribunal: {tribunal}.")
    if page:
        parts.append(f"Página: {page}.")
    if url:
        dt = accessed_at or datetime.now()
        parts.append(f"Disponível em: {url}.")
        parts.append(f"Acesso em: {dt.day:02d}/{dt.month:02d}/{dt.year}.")
    return " ".join(parts)
