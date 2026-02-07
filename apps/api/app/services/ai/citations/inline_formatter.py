from __future__ import annotations

from typing import Any, Mapping

from app.services.ai.citations.metadata import build_numeric_prefix, extract_reference_metadata


def format_inline_reference(
    source: Mapping[str, Any],
    *,
    number: int | None = None,
    **_: Any,
) -> str:
    meta = extract_reference_metadata(source)
    title = str(meta.get("title") or "Fonte").strip()
    url = str(meta.get("url") or "").strip()
    page = meta.get("pin_cite")
    prefix = build_numeric_prefix(number)
    page_part = f", p. {page}" if page else ""
    if url:
        return f"{prefix}{title}{page_part} ({url})"
    return f"{prefix}{title}{page_part}"
