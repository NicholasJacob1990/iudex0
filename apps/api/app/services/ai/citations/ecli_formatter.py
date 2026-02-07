from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping


def format_ecli_reference(
    source: Mapping[str, Any],
    *,
    accessed_at: datetime | None = None,
    number: int | None = None,
) -> str:
    ecli = str(source.get("ecli") or "").strip()
    title = str(source.get("title") or "Case").strip()
    url = str(source.get("url") or source.get("source_url") or "").strip()
    prefix = f"[{number}] " if number is not None else ""

    if ecli:
        if url:
            return f"{prefix}{ecli}. {title}. {url}."
        return f"{prefix}{ecli}. {title}."
    if url:
        dt = accessed_at or datetime.now()
        return f"{prefix}{title}. {url}. Accessed {dt.day:02d}/{dt.month:02d}/{dt.year}."
    return f"{prefix}{title}."
