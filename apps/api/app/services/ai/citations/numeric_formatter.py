from __future__ import annotations

from typing import Any, Mapping


def format_numeric_reference(
    source: Mapping[str, Any],
    *,
    number: int | None = None,
    **_: Any,
) -> str:
    n = number if number is not None else source.get("number")
    title = str(source.get("title") or "Fonte").strip()
    url = str(source.get("url") or source.get("source_url") or "").strip()
    if url:
        return f"[{n}] {title}. {url}." if n is not None else f"{title}. {url}."
    return f"[{n}] {title}." if n is not None else f"{title}."
