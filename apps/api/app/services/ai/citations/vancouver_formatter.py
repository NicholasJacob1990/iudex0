from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping


_MONTHS = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]


def format_vancouver_reference(
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
    return f"{prefix}{title} [Internet]. [cited {dt.year} {month} {dt.day:02d}]. Available from: {url}."
