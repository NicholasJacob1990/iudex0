from __future__ import annotations

from typing import Any, Dict, Optional, List, Iterable
from datetime import datetime
import re


_SEARCH_MODES = {"web", "academic", "sec"}
_SEARCH_TYPES = {"fast", "pro", "auto"}
_SEARCH_CONTEXT_SIZES = {"low", "medium", "high"}
_STREAM_MODES = {"full", "concise"}
_RECENCY_FILTERS = {"day", "week", "month", "year"}


def normalize_perplexity_search_mode(value: Optional[str]) -> Optional[str]:
    raw = (value or "").strip().lower()
    return raw if raw in _SEARCH_MODES else None


def normalize_perplexity_search_type(value: Optional[str]) -> Optional[str]:
    raw = (value or "").strip().lower()
    return raw if raw in _SEARCH_TYPES else None


def normalize_perplexity_context_size(value: Optional[str]) -> Optional[str]:
    raw = (value or "").strip().lower()
    return raw if raw in _SEARCH_CONTEXT_SIZES else None


def normalize_perplexity_stream_mode(value: Optional[str]) -> Optional[str]:
    raw = (value or "").strip().lower()
    return raw if raw in _STREAM_MODES else None


def normalize_perplexity_recency(value: Optional[str]) -> Optional[str]:
    raw = (value or "").strip().lower()
    return raw if raw in _RECENCY_FILTERS else None


def normalize_perplexity_date(value: Optional[str]) -> Optional[str]:
    raw = (value or "").strip()
    if not raw:
        return None
    if re.match(r"^\d{4}-\d{2}-\d{2}$", raw):
        try:
            parsed = datetime.strptime(raw, "%Y-%m-%d")
            return f"{parsed.month}/{parsed.day}/{parsed.year}"
        except ValueError:
            return None
    return raw


def parse_csv_list(value: Optional[object], *, max_items: int) -> Optional[List[str]]:
    if value is None:
        return None
    if isinstance(value, list):
        items = [str(item).strip() for item in value]
    else:
        text = str(value)
        items = [part.strip() for part in text.split(",")]
    cleaned = [item for item in items if item]
    if not cleaned:
        return None
    return cleaned[:max_items]


def normalize_float(value: Optional[object]) -> Optional[float]:
    if value is None:
        return None
    try:
        text = str(value).strip()
        if not text:
            return None
        return float(text)
    except (TypeError, ValueError):
        return None


def build_perplexity_chat_kwargs(
    *,
    api_model: str,
    web_search_enabled: bool,
    search_mode: Optional[str] = None,
    search_type: Optional[str] = None,
    search_context_size: Optional[str] = None,
    search_domain_filter: Optional[object] = None,
    search_language_filter: Optional[object] = None,
    search_recency_filter: Optional[str] = None,
    search_after_date: Optional[str] = None,
    search_before_date: Optional[str] = None,
    last_updated_after: Optional[str] = None,
    last_updated_before: Optional[str] = None,
    search_country: Optional[str] = None,
    search_region: Optional[str] = None,
    search_city: Optional[str] = None,
    search_latitude: Optional[object] = None,
    search_longitude: Optional[object] = None,
    return_images: Optional[bool] = None,
    return_videos: Optional[bool] = None,
    enable_search_classifier: bool = False,
    disable_search: bool = False,
    stream_mode: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build Perplexity chat.completions kwargs for Sonar models.
    This keeps app semantics consistent when web_search is disabled.
    """
    params: Dict[str, Any] = {}

    normalized_mode = normalize_perplexity_search_mode(search_mode)
    if normalized_mode:
        params["search_mode"] = normalized_mode

    normalized_stream_mode = normalize_perplexity_stream_mode(stream_mode)
    if normalized_stream_mode:
        params["stream_mode"] = normalized_stream_mode

    disable_effective = bool(disable_search) or not web_search_enabled
    if disable_effective:
        params["disable_search"] = True
        return params

    if enable_search_classifier:
        params["enable_search_classifier"] = True

    web_search_options: Dict[str, Any] = {}
    normalized_context_size = normalize_perplexity_context_size(search_context_size)
    if normalized_context_size:
        web_search_options["search_context_size"] = normalized_context_size

    normalized_type = normalize_perplexity_search_type(search_type)
    if normalized_type:
        api_model_lower = (api_model or "").lower()
        if api_model_lower == "sonar-pro" or api_model_lower.startswith("sonar-pro"):
            web_search_options["search_type"] = normalized_type

    domain_filter = parse_csv_list(search_domain_filter, max_items=20)
    if domain_filter:
        web_search_options["search_domain_filter"] = domain_filter

    language_filter = parse_csv_list(search_language_filter, max_items=10)
    if language_filter:
        web_search_options["search_language_filter"] = language_filter

    normalized_recency = normalize_perplexity_recency(search_recency_filter)
    if normalized_recency and not (search_after_date or search_before_date):
        web_search_options["search_recency_filter"] = normalized_recency

    after_date = normalize_perplexity_date(search_after_date)
    if after_date:
        web_search_options["search_after_date"] = after_date

    before_date = normalize_perplexity_date(search_before_date)
    if before_date:
        web_search_options["search_before_date"] = before_date

    updated_after = normalize_perplexity_date(last_updated_after)
    if updated_after:
        web_search_options["last_updated_after"] = updated_after

    updated_before = normalize_perplexity_date(last_updated_before)
    if updated_before:
        web_search_options["last_updated_before"] = updated_before

    country = (search_country or "").strip()
    if country:
        web_search_options["search_country"] = country.upper()

    region = (search_region or "").strip()
    if region:
        web_search_options["search_region"] = region

    city = (search_city or "").strip()
    if city:
        web_search_options["search_city"] = city

    latitude = normalize_float(search_latitude)
    longitude = normalize_float(search_longitude)
    if latitude is not None and longitude is not None:
        web_search_options["search_latitude"] = latitude
        web_search_options["search_longitude"] = longitude

    if return_images:
        web_search_options["return_images"] = True
    if return_videos:
        web_search_options["return_videos"] = True

    if web_search_options:
        params["web_search_options"] = web_search_options

    return params
