from __future__ import annotations

from datetime import datetime
import re
from typing import Any, Iterable, Mapping


_SHORT_MONTHS = (
    "Jan.",
    "Feb.",
    "Mar.",
    "Apr.",
    "May",
    "Jun.",
    "Jul.",
    "Aug.",
    "Sep.",
    "Oct.",
    "Nov.",
    "Dec.",
)

_LONG_MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)

_LONG_MONTHS_FR = (
    "janvier",
    "fevrier",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "aout",
    "septembre",
    "octobre",
    "novembre",
    "decembre",
)


def build_numeric_prefix(number: int | None) -> str:
    return f"[{number}] " if number is not None else ""


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def short_month_name(month: int) -> str:
    idx = max(1, min(12, int(month or 1))) - 1
    return _SHORT_MONTHS[idx]


def long_month_name(month: int) -> str:
    idx = max(1, min(12, int(month or 1))) - 1
    return _LONG_MONTHS[idx]


def french_month_name(month: int) -> str:
    idx = max(1, min(12, int(month or 1))) - 1
    return _LONG_MONTHS_FR[idx]


def pick_first(source: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        if "." in key:
            current: Any = source
            ok = True
            for part in key.split("."):
                if not isinstance(current, Mapping):
                    ok = False
                    break
                current = current.get(part)
            if ok:
                cleaned = clean_text(current)
                if cleaned:
                    return cleaned
            continue

        cleaned = clean_text(source.get(key))
        if cleaned:
            return cleaned
    return ""


def split_authors(value: Any) -> list[str]:
    if value is None:
        return []

    if isinstance(value, Mapping):
        name = clean_text(value.get("name"))
        return [name] if name else []

    if isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
        out: list[str] = []
        for item in value:
            out.extend(split_authors(item))
        return [item for item in out if item]

    raw = clean_text(value)
    if not raw:
        return []

    pieces = re.split(r"\s*(?:;|\s+and\s+|\s*&\s+|\|)\s*", raw, flags=re.IGNORECASE)
    if len(pieces) == 1:
        # Handles "A, B, C" while keeping "Silva, Joao" intact when only one comma.
        if raw.count(",") >= 2:
            pieces = [part.strip() for part in raw.split(",")]
        else:
            pieces = [raw]
    return [clean_text(part) for part in pieces if clean_text(part)]


def parse_year(value: Any) -> str:
    raw = clean_text(value)
    if not raw:
        return ""
    match = re.search(r"\b(19|20)\d{2}\b", raw)
    return match.group(0) if match else ""


def parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    raw = clean_text(value)
    if not raw:
        return None

    normalized = raw.replace("Z", "+00:00")
    for candidate in (normalized, normalized.split("T")[0], normalized.split(" ")[0]):
        try:
            return datetime.fromisoformat(candidate)
        except Exception:
            pass

    match = re.search(r"\b(\d{2})/(\d{2})/((?:19|20)\d{2})\b", raw)
    if match:
        try:
            return datetime(int(match.group(3)), int(match.group(2)), int(match.group(1)))
        except Exception:
            return None
    return None


def parse_int(value: Any) -> int | None:
    raw = clean_text(value)
    if not raw:
        return None
    try:
        parsed = int(raw)
    except Exception:
        return None
    return parsed if parsed > 0 else None


def extract_reference_metadata(
    source: Mapping[str, Any],
    *,
    accessed_at: datetime | None = None,
) -> dict[str, Any]:
    data = source if isinstance(source, Mapping) else {}
    dt = accessed_at or datetime.now()

    title = pick_first(data, "title", "case_name", "name", "document_title")
    if not title:
        title = "Untitled"

    url = pick_first(data, "url", "source_url", "viewer.source_url", "viewer_url", "download_url")
    author = pick_first(data, "author", "institution", "organization", "orgao", "publisher")
    authors = split_authors(data.get("authors") or author)

    year = (
        parse_year(pick_first(data, "year", "ano", "decision_year", "published_year"))
        or parse_year(pick_first(data, "date", "published_at", "decision_date", "issued_at", "created_at"))
    )

    published_dt = (
        parse_datetime(data.get("date"))
        or parse_datetime(data.get("published_at"))
        or parse_datetime(data.get("decision_date"))
        or parse_datetime(data.get("issued_at"))
        or parse_datetime(data.get("created_at"))
    )
    if not year and published_dt:
        year = str(published_dt.year)

    court = pick_first(data, "court", "tribunal", "orgao_julgador", "jurisdiction")
    docket = pick_first(data, "docket", "case_number", "numero_processo", "process_number")
    reporter = pick_first(data, "reporter", "official_citation")
    citation_text = pick_first(data, "citation")
    volume = pick_first(data, "volume")
    issue = pick_first(data, "issue", "number")
    pages = pick_first(data, "pages", "page_range")
    first_page = parse_int(data.get("first_page") or data.get("page_start"))
    pin_cite = (
        parse_int(data.get("pin_cite"))
        or parse_int(data.get("pincite"))
        or parse_int(data.get("source_page"))
        or parse_int(data.get("page"))
    )

    site = pick_first(data, "site_name", "journal", "publication", "periodical")
    if not site:
        site = pick_first(data, "publisher")

    place = pick_first(data, "location", "city", "place")
    ecli = pick_first(data, "ecli")

    return {
        "title": title,
        "url": url,
        "author": author,
        "authors": authors,
        "year": year or "n.d.",
        "published_at": published_dt,
        "court": court,
        "docket": docket,
        "reporter": reporter,
        "citation": citation_text,
        "volume": volume,
        "issue": issue,
        "pages": pages,
        "first_page": first_page,
        "pin_cite": pin_cite,
        "site": site,
        "publisher": pick_first(data, "publisher"),
        "place": place,
        "ecli": ecli,
        "accessed_at": dt,
    }
