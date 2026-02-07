from __future__ import annotations

from typing import Any, Mapping

from app.services.ai.citations.metadata import build_numeric_prefix, extract_reference_metadata


def format_numeric_reference(
    source: Mapping[str, Any],
    *,
    number: int | None = None,
    **_: Any,
) -> str:
    meta = extract_reference_metadata(source)
    n = number if number is not None else source.get("number")
    title = str(meta.get("title") or "Fonte").strip()
    url = str(meta.get("url") or "").strip()
    page = meta.get("pin_cite")
    court = str(meta.get("court") or "").strip()
    prefix = build_numeric_prefix(int(n) if isinstance(n, int) or str(n).isdigit() else None)

    suffix_parts = []
    if court:
        suffix_parts.append(court)
    if page:
        suffix_parts.append(f"p. {page}")
    suffix = f" ({'; '.join(suffix_parts)})" if suffix_parts else ""

    if url:
        return f"{prefix}{title}.{suffix} {url}.".replace("..", ".")
    return f"{prefix}{title}.{suffix}".replace("..", ".")
