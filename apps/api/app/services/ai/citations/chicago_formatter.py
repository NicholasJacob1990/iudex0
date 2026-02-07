from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping


_MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def format_chicago_reference(
    source: Mapping[str, Any],
    *,
    accessed_at: datetime | None = None,
    number: int | None = None,
) -> str:
    title = str(source.get("title") or "Untitled").strip()
    url = str(source.get("url") or source.get("source_url") or "").strip()
    dt = accessed_at or datetime.now()
    month = _MONTHS[max(0, min(11, dt.month - 1))]
    prefix = f"[{number}] " if number is not None else ""

    if not url:
        return f"{prefix}{title}."
    return f"{prefix}{title}. Accessed {month} {dt.day}, {dt.year}. {url}."
