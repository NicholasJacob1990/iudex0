from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping


_MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def format_harvard_reference(
    source: Mapping[str, Any],
    *,
    accessed_at: datetime | None = None,
    number: int | None = None,
) -> str:
    title = str(source.get("title") or "Untitled").strip()
    author = str(source.get("author") or source.get("institution") or "").strip()
    year = str(source.get("year") or source.get("ano") or "n.d.").strip()
    url = str(source.get("url") or source.get("source_url") or "").strip()
    dt = accessed_at or datetime.now()
    month = _MONTHS[max(0, min(11, dt.month - 1))]
    prefix = f"[{number}] " if number is not None else ""

    author_part = f"{author} " if author else ""
    if not url:
        return f"{prefix}{author_part}({year}) {title}."
    return f"{prefix}{author_part}({year}) {title}. Available at: {url} (Accessed: {dt.day} {month} {dt.year})."
