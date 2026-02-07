from __future__ import annotations

from typing import Any, Mapping


def format_inline_reference(
    source: Mapping[str, Any],
    *,
    number: int | None = None,
    **_: Any,
) -> str:
    title = str(source.get("title") or "Fonte").strip()
    url = str(source.get("url") or source.get("source_url") or "").strip()
    prefix = f"[{number}] " if number is not None else ""
    if url:
        return f"{prefix}{title} ({url})"
    return f"{prefix}{title}"
