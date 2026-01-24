from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple

from app.services.ai.model_registry import MODEL_REGISTRY
from app.services.ai.perplexity_config import (
    normalize_perplexity_context_size,
    normalize_perplexity_search_type,
)
from app.core.time_utils import utcnow


_BILLING_CONFIG_PATH = Path(__file__).resolve().parents[1] / "core" / "billing_config.json"


@lru_cache(maxsize=1)
def load_billing_config() -> Dict[str, Any]:
    try:
        with open(_BILLING_CONFIG_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        data = {}
    return data


def get_billing_config() -> Dict[str, Any]:
    return load_billing_config()


def get_default_deep_research_effort() -> str:
    config = load_billing_config()
    tool_cfg = (config.get("tool_points") or {}).get("deep_research") or {}
    return str(tool_cfg.get("default_effort") or "medium").lower()


def resolve_plan_key(plan: Optional[str]) -> str:
    config = load_billing_config()
    plans = config.get("plans") or {}
    if not plan:
        return "free" if "free" in plans else next(iter(plans.keys()), "free")
    raw_value = getattr(plan, "value", plan)
    raw = str(raw_value).strip()
    if not raw:
        return "free" if "free" in plans else next(iter(plans.keys()), "free")
    lowered = raw.lower()
    if lowered in plans:
        return lowered
    aliases = config.get("plan_aliases") or {}
    for key in (raw, raw.upper(), raw.lower()):
        alias = aliases.get(key)
        if alias and alias in plans:
            return alias
    return "free" if "free" in plans else lowered


def get_plan_caps(plan_key: str) -> Dict[str, Any]:
    config = load_billing_config()
    return (config.get("caps_by_plan") or {}).get(plan_key) or {}


def get_plan_cap(
    plan_key: str,
    cap_key: str,
    default: Optional[int] = None,
) -> Optional[int]:
    caps = get_plan_caps(plan_key)
    value = caps.get(cap_key)
    if value is None:
        return default
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("unlimited", "infinite", "inf"):
            return None
        try:
            return int(lowered)
        except ValueError:
            return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _plan_index(plan_key: str, config: Optional[Dict[str, Any]] = None) -> int:
    cfg = config or load_billing_config()
    order = cfg.get("plan_order") or []
    try:
        return order.index(plan_key)
    except ValueError:
        return -1


def is_plan_at_least(plan_key: str, minimum_plan: str) -> bool:
    config = load_billing_config()
    if not minimum_plan:
        return True
    return _plan_index(plan_key, config) >= _plan_index(minimum_plan, config)


def resolve_deep_research_billing(
    plan_key: str,
    requested_effort: Optional[str],
) -> Tuple[Optional[str], float]:
    config = load_billing_config()
    tool_cfg = (config.get("tool_points") or {}).get("deep_research") or {}
    effort_points = tool_cfg.get("effort_points") or {}
    default_effort = str(tool_cfg.get("default_effort") or "medium").lower()
    effort = normalize_effort(requested_effort, default_effort, effort_points)

    caps = (config.get("caps_by_plan") or {}).get(plan_key) or {}
    cap_effort_raw = str(caps.get("deep_research_effort_max") or "").strip().lower()
    if cap_effort_raw in ("", "none"):
        return None, 1.0
    cap_effort = normalize_effort(cap_effort_raw, default_effort, effort_points)
    if cap_effort and cap_effort in effort_points:
        if _effort_rank(effort) > _effort_rank(cap_effort):
            effort = cap_effort

    multiplier = 1.0
    gate = (config.get("feature_gates") or {}).get("deep_research") or {}
    min_plan = gate.get("min_plan")
    if min_plan and not is_plan_at_least(plan_key, min_plan):
        multiplier = float(gate.get("else_multiplier") or 1.0)

    return effort, multiplier


def normalize_effort(
    value: Optional[str],
    default: str,
    effort_points: Optional[Dict[str, Any]] = None,
) -> str:
    raw = str(value).strip().lower() if value is not None else ""
    if raw in ("1", "low"):
        return "low"
    if raw in ("2", "medium"):
        return "medium"
    if raw in ("3", "high"):
        return "high"
    if effort_points and raw in effort_points:
        return raw
    return default


def _effort_rank(effort: str) -> int:
    if effort == "high":
        return 3
    if effort == "medium":
        return 2
    return 1


def _month_window(now: datetime) -> Tuple[datetime, datetime]:
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    year = start.year
    month = start.month
    if month == 12:
        end = start.replace(year=year + 1, month=1)
    else:
        end = start.replace(month=month + 1)
    return start, end


async def get_deep_research_monthly_status(
    db: Any,
    *,
    user_id: Optional[str],
    plan_key: str,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    cap = get_plan_cap(plan_key, "max_deep_research_per_month", default=None)
    if cap is None:
        return {"allowed": True, "cap": None, "used": None, "remaining": None}
    if not user_id or not db:
        return {"allowed": True, "cap": cap, "used": None, "remaining": None}

    try:
        cap_value = int(cap)
    except (TypeError, ValueError):
        cap_value = 0
    cap_value = max(0, cap_value)

    try:
        from sqlalchemy import select, func
        from app.models.api_usage import ApiCallUsage
    except Exception:
        return {"allowed": True, "cap": cap_value, "used": None, "remaining": None}

    anchor = now or utcnow()
    period_start, period_end = _month_window(anchor)
    result = await db.execute(
        select(func.count(ApiCallUsage.id)).where(
            ApiCallUsage.user_id == str(user_id),
            ApiCallUsage.kind == "deep_research",
            ApiCallUsage.created_at >= period_start,
            ApiCallUsage.created_at < period_end,
        )
    )
    used = int(result.scalar() or 0)
    remaining = max(0, cap_value - used)
    return {"allowed": used < cap_value, "cap": cap_value, "used": used, "remaining": remaining}


def normalize_model_id(model: Optional[str]) -> Optional[str]:
    if not model:
        return None
    raw = str(model).strip()
    if not raw:
        return None
    lowered = raw.lower()
    if lowered.startswith("gpt-5-mini"):
        return "gpt-5-mini"
    if lowered.startswith("gpt-5.2-instant"):
        return "gpt-5.2-instant"
    if lowered.startswith("gpt-5.2-chat"):
        return "gpt-5.2"
    if lowered.startswith("gemini-3-flash"):
        return "gemini-3-flash"
    cfg = MODEL_REGISTRY.get(raw)
    if cfg:
        return cfg.id
    for candidate in MODEL_REGISTRY.values():
        if candidate.api_model and candidate.api_model == raw:
            return candidate.id
    return raw.lower()


def resolve_node_size(node: Optional[str]) -> Optional[str]:
    if not node:
        return None
    config = load_billing_config()
    node_cfg = (config.get("workflow_node_defaults") or {}).get(node) or {}
    size = node_cfg.get("size")
    return str(size).strip().upper() if size else None


def resolve_context_multiplier(context_tokens: Optional[int]) -> float:
    if not context_tokens:
        return 1.0
    config = load_billing_config()
    policy = config.get("context_multiplier_policy") or []
    for rule in policy:
        try:
            max_tokens = int(rule.get("max_context_tokens") or 0)
            multiplier = float(rule.get("multiplier") or 1.0)
        except (TypeError, ValueError):
            continue
        if context_tokens <= max_tokens:
            return multiplier
    return 1.0


def _get_perplexity_grounded_config(config: Dict[str, Any]) -> Dict[str, Any]:
    pplx_cfg = config.get("perplexity") or {}
    grounded = pplx_cfg.get("grounded_llm") or {}
    if grounded:
        return grounded
    return config.get("perplexity_grounded_llm") or {}


def _get_llm_rate_card(config: Dict[str, Any], model_key: Optional[str]) -> Dict[str, Any]:
    if not model_key:
        return {}
    return (config.get("llm_rate_cards") or {}).get(model_key) or {}


def _coerce_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def calculate_points(
    *,
    kind: str,
    provider: str,
    model: Optional[str],
    meta: Optional[Dict[str, Any]] = None,
) -> Optional[int]:
    config = load_billing_config()
    meta_payload = dict(meta) if isinstance(meta, dict) else {}
    points_override = meta_payload.get("points")
    if isinstance(points_override, (int, float)):
        return int(round(points_override))

    multiplier = meta_payload.get("points_multiplier") or 1.0
    try:
        multiplier = float(multiplier)
    except (TypeError, ValueError):
        multiplier = 1.0

    if kind == "web_search":
        base = (config.get("tool_points") or {}).get("web_search_request")
        if isinstance(base, (int, float)):
            return int(round(float(base) * multiplier))
        return None

    if kind == "deep_research":
        variable_cfg = (config.get("perplexity") or {}).get("deep_research_pricing") or {}
        token_rates = variable_cfg.get("token_points_per_1k") or {}
        search_query_points = variable_cfg.get("search_query_points")

        tokens_in = _coerce_int(meta_payload.get("tokens_in"))
        tokens_out = _coerce_int(meta_payload.get("tokens_out"))
        citation_tokens = _coerce_int(meta_payload.get("citation_tokens"))
        reasoning_tokens = _coerce_int(meta_payload.get("reasoning_tokens"))
        search_queries = _coerce_int(meta_payload.get("search_queries"))

        if token_rates or search_query_points:
            total = 0.0
            in_rate = _coerce_float(token_rates.get("input"))
            out_rate = _coerce_float(token_rates.get("output"))
            citation_rate = _coerce_float(token_rates.get("citation"))
            reasoning_rate = _coerce_float(token_rates.get("reasoning"))

            if tokens_in is not None and in_rate is not None:
                total += (float(tokens_in) / 1000.0) * float(in_rate)
            if tokens_out is not None and out_rate is not None:
                total += (float(tokens_out) / 1000.0) * float(out_rate)
            if citation_tokens is not None and citation_rate is not None:
                total += (float(citation_tokens) / 1000.0) * float(citation_rate)
            if reasoning_tokens is not None and reasoning_rate is not None:
                total += (float(reasoning_tokens) / 1000.0) * float(reasoning_rate)
            if search_queries is not None and search_query_points is not None:
                total += float(search_queries) * float(search_query_points)

            if total > 0:
                return int(math.ceil(total * float(multiplier)))

        tool_cfg = (config.get("tool_points") or {}).get("deep_research") or {}
        effort_points = tool_cfg.get("effort_points") or {}
        default_effort = str(tool_cfg.get("default_effort") or "medium").lower()
        effort = normalize_effort(meta_payload.get("effort"), default_effort, effort_points)
        base = effort_points.get(effort)
        if isinstance(base, (int, float)):
            return int(round(float(base) * multiplier))
        return None

    context_tokens = meta_payload.get("context_tokens")
    try:
        context_tokens = int(context_tokens) if context_tokens is not None else None
    except (TypeError, ValueError):
        context_tokens = None
    context_multiplier = meta_payload.get("context_multiplier")
    if context_multiplier is not None:
        try:
            context_multiplier = float(context_multiplier)
        except (TypeError, ValueError):
            context_multiplier = None
    if context_multiplier is None:
        context_multiplier = resolve_context_multiplier(context_tokens)

    if kind != "llm":
        return None

    size = meta_payload.get("size") or meta_payload.get("size_class")
    if not size:
        size = resolve_node_size(meta_payload.get("node"))
    if not size:
        size = (config.get("defaults") or {}).get("llm_size") or "M"
    size = str(size).strip().upper()

    model_key = normalize_model_id(model)
    rate_card = _get_llm_rate_card(config, model_key)
    tokens_in = _coerce_int(meta_payload.get("tokens_in"))
    tokens_out = _coerce_int(meta_payload.get("tokens_out"))
    cached_tokens_in = _coerce_int(meta_payload.get("cached_tokens_in")) or 0
    cache_write_tokens_in = _coerce_int(meta_payload.get("cache_write_tokens_in")) or 0
    seconds_audio = _coerce_float(meta_payload.get("seconds_audio")) or 0.0
    seconds_video = _coerce_float(meta_payload.get("seconds_video")) or 0.0
    context_tokens_usage = context_tokens
    if context_tokens_usage is None and tokens_in is not None:
        context_tokens_usage = tokens_in

    if rate_card:
        media_rates = rate_card.get("media_points_per_second") or {}
        audio_rate = _coerce_float(media_rates.get("audio"))
        video_rate = _coerce_float(media_rates.get("video"))
        total = 0.0
        if (seconds_audio or seconds_video) and (audio_rate or video_rate):
            if audio_rate:
                total += float(seconds_audio) * float(audio_rate)
            if video_rate:
                total += float(seconds_video) * float(video_rate)

        token_rates = rate_card.get("token_points_per_1k") or {}
        in_rate = _coerce_float(token_rates.get("input") or token_rates.get("in"))
        out_rate = _coerce_float(token_rates.get("output") or token_rates.get("out"))
        if (tokens_in is not None or tokens_out is not None) and (in_rate is not None or out_rate is not None):
            uncached_in = max(0, int(tokens_in or 0) - int(cached_tokens_in))
            cached_mult = _coerce_float(token_rates.get("cached_input_multiplier"))
            if cached_mult is None:
                cached_mult = 1.0

            apply_context_multiplier = rate_card.get("apply_context_multiplier")
            if apply_context_multiplier is False:
                in_mult = 1.0
                out_mult = 1.0
            else:
                in_mult = context_multiplier
                out_mult = context_multiplier
            threshold = _coerce_int(rate_card.get("over_context_threshold"))
            if threshold and context_tokens_usage and int(context_tokens_usage) > int(threshold):
                in_mult = _coerce_float(rate_card.get("over_context_input_multiplier")) or 1.0
                out_mult = _coerce_float(rate_card.get("over_context_output_multiplier")) or 1.0

            if in_rate is not None:
                total += (float(uncached_in) / 1000.0) * float(in_rate) * float(in_mult)
                total += (
                    (float(cached_tokens_in) / 1000.0)
                    * float(in_rate)
                    * float(cached_mult)
                    * float(in_mult)
                )
                cache_write_mult = _coerce_float(rate_card.get("cache_write_input_multiplier"))
                if cache_write_tokens_in and cache_write_mult:
                    extra = (float(cache_write_tokens_in) / 1000.0) * float(in_rate) * float(in_mult)
                    total += extra * (float(cache_write_mult) - 1.0)
            if out_rate is not None:
                total += (float(tokens_out or 0) / 1000.0) * float(out_rate) * float(out_mult)
        if total > 0:
            return int(math.ceil(total * float(multiplier)))
    if provider == "perplexity" or (model_key or "") in ("sonar", "sonar-pro", "sonar-reasoning-pro"):
        grounded_cfg = _get_perplexity_grounded_config(config)
        token_rates = (grounded_cfg.get("token_points_per_1k") or {}).get(model_key or "")
        base_fee_cfg = (grounded_cfg.get("base_fee_points") or {}).get(model_key or "")
        if token_rates:
            in_rate = _coerce_float(token_rates.get("input"))
            out_rate = _coerce_float(token_rates.get("output"))
            if (tokens_in is not None or tokens_out is not None) and (in_rate is not None or out_rate is not None):
                context_size = meta_payload.get("search_context_size") or meta_payload.get("perplexity_search_context_size")
                normalized_context = normalize_perplexity_context_size(context_size) or "low"
                disable_search = bool(
                    meta_payload.get("disable_search")
                    or meta_payload.get("perplexity_disable_search")
                )
                base_fee_points = 0.0
                if not disable_search and isinstance(base_fee_cfg, dict):
                    base_fee_points = float(base_fee_cfg.get(normalized_context) or 0)
                total = 0.0
                if in_rate is not None:
                    total += (float(tokens_in or 0) / 1000.0) * float(in_rate)
                if out_rate is not None:
                    total += (float(tokens_out or 0) / 1000.0) * float(out_rate)
                total += base_fee_points
                return int(math.ceil(total * float(multiplier)))
        token_points_cfg = (grounded_cfg.get("token_points_per_call") or {}).get(model_key or "")
        if token_points_cfg:
            token_points = token_points_cfg.get(size)
            if token_points is None:
                return None
            defaults = grounded_cfg.get("defaults") or {}
            context_size = meta_payload.get("search_context_size") or meta_payload.get("perplexity_search_context_size")
            normalized_context = normalize_perplexity_context_size(context_size)
            if not normalized_context:
                normalized_context = normalize_perplexity_context_size(defaults.get("search_context_size")) or "low"

            disable_search = bool(
                meta_payload.get("disable_search")
                or meta_payload.get("perplexity_disable_search")
            )
            request_fee_points = 0
            if not disable_search:
                request_fee_cfg = (grounded_cfg.get("request_fee_points_per_call") or {}).get(model_key or "")
                if model_key == "sonar-pro":
                    raw_search_type = meta_payload.get("search_type") or meta_payload.get("perplexity_search_type")
                    normalized_type = normalize_perplexity_search_type(raw_search_type)
                    if not normalized_type:
                        normalized_type = normalize_perplexity_search_type(defaults.get("sonar_pro_search_type")) or "fast"
                    if normalized_type == "auto":
                        auto_estimate = defaults.get("auto_search_type_estimate")
                        if not auto_estimate and isinstance(request_fee_cfg, dict):
                            auto_cfg = request_fee_cfg.get("auto")
                            if isinstance(auto_cfg, dict):
                                auto_estimate = auto_cfg.get("estimate")
                        normalized_type = (auto_estimate or "pro").strip().lower()
                    if isinstance(request_fee_cfg, dict):
                        request_fee_cfg = request_fee_cfg.get(normalized_type)
                if isinstance(request_fee_cfg, dict):
                    request_fee_points = request_fee_cfg.get(normalized_context)
                    if request_fee_points is None:
                        request_fee_points = request_fee_cfg.get("low")
                if request_fee_points is None:
                    return None

            token_total = float(token_points) * float(context_multiplier)
            total = (token_total + float(request_fee_points)) * float(multiplier)
            return int(round(total))

    points_table = (config.get("llm_points_per_call") or {}).get(model_key or "")
    if not points_table:
        return None
    base_points = points_table.get(size)
    if base_points is None:
        return None

    total = float(base_points) * float(context_multiplier) * float(multiplier)
    return int(round(total))


DEFAULT_MAX_POINTS_PER_MESSAGE = 16_000


def get_usd_per_point(config: Optional[Dict[str, Any]] = None) -> float:
    cfg = config or load_billing_config()
    anchor = cfg.get("points_anchor") or {}
    usd_per_point = anchor.get("usd_per_point")
    if isinstance(usd_per_point, (int, float)) and float(usd_per_point) > 0:
        return float(usd_per_point)
    usd_per_1m = anchor.get("usd_per_1m_points")
    if isinstance(usd_per_1m, (int, float)) and float(usd_per_1m) > 0:
        return float(usd_per_1m) / 1_000_000
    return 0.00003


def get_plan_quota_points(plan_key: str, config: Optional[Dict[str, Any]] = None) -> Optional[int]:
    cfg = config or load_billing_config()
    plan_cfg = (cfg.get("plans") or {}).get(plan_key) or {}
    quota = plan_cfg.get("quota_points")
    try:
        return int(quota) if quota is not None else None
    except (TypeError, ValueError):
        return None


def get_plan_period(plan_key: str, config: Optional[Dict[str, Any]] = None) -> str:
    cfg = config or load_billing_config()
    plan_cfg = (cfg.get("plans") or {}).get(plan_key) or {}
    period = str(plan_cfg.get("period") or "").strip().lower()
    if period in ("daily", "monthly", "one_off"):
        return period
    return "monthly"


def _day_window(now: datetime) -> Tuple[datetime, datetime]:
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return start, end


def get_plan_period_window(
    plan_key: str,
    *,
    now: Optional[datetime] = None,
    config: Optional[Dict[str, Any]] = None,
) -> Tuple[datetime, datetime]:
    anchor = now or utcnow()
    period = get_plan_period(plan_key, config=config)
    if period == "daily":
        return _day_window(anchor)
    return _month_window(anchor)


async def get_points_used_for_period(
    db: Any,
    *,
    user_id: Optional[str],
    plan_key: str,
    now: Optional[datetime] = None,
) -> int:
    if not user_id or not db:
        return 0

    try:
        from sqlalchemy import select
        from app.models.api_usage import ApiCallUsage
    except Exception:
        return 0

    period_start, period_end = get_plan_period_window(plan_key, now=now)
    result = await db.execute(
        select(ApiCallUsage.meta).where(
            ApiCallUsage.user_id == str(user_id),
            ApiCallUsage.created_at >= period_start,
            ApiCallUsage.created_at < period_end,
        )
    )
    metas = result.scalars().all()
    total = 0
    for meta in metas:
        if not isinstance(meta, dict):
            continue
        value = meta.get("points")
        if value is None:
            continue
        try:
            total += int(value)
        except (TypeError, ValueError):
            continue
    return max(0, int(total))


async def get_points_summary(
    db: Any,
    *,
    user_id: Optional[str],
    plan_key: str,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    cfg = load_billing_config()
    quota = get_plan_quota_points(plan_key, config=cfg)
    period = get_plan_period(plan_key, config=cfg)
    period_start, period_end = get_plan_period_window(plan_key, now=now, config=cfg)
    used = await get_points_used_for_period(db, user_id=user_id, plan_key=plan_key, now=now)
    available = max(0, int(quota) - int(used)) if isinstance(quota, int) else None
    return {
        "plan_key": plan_key,
        "period": period,
        "quota_points": quota,
        "used_points": used,
        "available_points": available,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "usd_per_point": get_usd_per_point(cfg),
    }


def resolve_chat_max_points_per_message(
    chat_context: Optional[Dict[str, Any]],
    *,
    default: int = DEFAULT_MAX_POINTS_PER_MESSAGE,
) -> int:
    if isinstance(chat_context, dict):
        raw = chat_context.get("max_points_per_message")
        if raw is None:
            raw = chat_context.get("message_budget_points")
        if raw is not None:
            try:
                value = int(raw)
                if value > 0:
                    return value
            except (TypeError, ValueError):
                pass
    return int(default)


def pick_size_from_context_tokens(context_tokens: Optional[int]) -> str:
    cfg = load_billing_config()
    profiles = cfg.get("size_profiles") or {}
    try:
        s_in = int((profiles.get("S") or {}).get("input_tokens") or 0)
        m_in = int((profiles.get("M") or {}).get("input_tokens") or 0)
        l_in = int((profiles.get("L") or {}).get("input_tokens") or 0)
    except (TypeError, ValueError):
        s_in, m_in, l_in = 800, 2500, 4000

    tokens = context_tokens or 0
    if s_in > 0 and tokens <= s_in:
        return "S"
    if m_in > 0 and tokens <= m_in:
        return "M"
    if l_in > 0 and tokens <= l_in:
        return "L"
    return "M"
