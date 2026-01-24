from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from app.services.ai.model_registry import get_model_config
from app.services.billing_service import (
    calculate_points,
    get_usd_per_point,
    load_billing_config,
    pick_size_from_context_tokens,
)
from app.services.poe_like_billing import CostEstimator


class FixedPointsEstimator(CostEstimator):
    def __init__(self, *, usd_per_point: float, breakdown: Optional[Dict[str, Any]] = None):
        self.usd_per_point = float(usd_per_point)
        self._breakdown = dict(breakdown) if isinstance(breakdown, dict) else {}

    def quote_usd(self, req: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
        points = int(req.get("points_estimate", 0) or 0)
        usd = float(points) * float(self.usd_per_point)
        breakdown = dict(self._breakdown)
        breakdown.setdefault("pricing_type", "points_fixed")
        breakdown.setdefault("points_estimate", points)
        breakdown.setdefault("usd_per_point", self.usd_per_point)
        breakdown.setdefault("usd_estimate", usd)
        return usd, breakdown


def _estimate_tokens_for_size(size: str, context_tokens: Optional[int]) -> Tuple[int, int]:
    config = load_billing_config()
    profiles = config.get("size_profiles") or {}
    profile = profiles.get(size) or {}
    output_tokens = int(profile.get("output_tokens") or 0)
    if context_tokens is None:
        tokens_in = int(profile.get("input_tokens") or 0)
    else:
        tokens_in = max(0, int(context_tokens))
    return tokens_in, output_tokens


def _max_llm_points_for_models(
    *,
    model_ids: list[str],
    size: str,
    context_tokens: Optional[int],
) -> int:
    best = 0
    tokens_in, tokens_out = _estimate_tokens_for_size(size, context_tokens)
    context_tokens_est = context_tokens if context_tokens is not None else tokens_in
    for model_id in model_ids:
        mid = str(model_id or "").strip()
        if not mid:
            continue
        cfg = get_model_config(mid)
        provider = cfg.provider if cfg else ""
        pts = (
            calculate_points(
                kind="llm",
                provider=provider,
                model=mid,
                meta={
                    "size": size,
                    "context_tokens": context_tokens_est,
                    "tokens_in": tokens_in,
                    "tokens_out": tokens_out,
                },
            )
            or 0
        )
        best = max(best, int(pts))
    return int(best)


def estimate_langgraph_job_points(
    *,
    prompt: str,
    context_tokens: Optional[int] = None,
    model_ids: list[str],
    use_multi_agent: bool,
    drafter_models: list[str],
    reviewer_models: list[str],
    hyde_enabled: bool,
    web_search: bool,
    multi_query: bool,
    max_web_search_requests: Optional[int],
    dense_research: bool,
    deep_research_effort: Optional[str],
    deep_research_points_multiplier: float,
    target_pages: int,
    max_style_loops: int,
    max_final_review_loops: int,
    max_granular_passes: int,
) -> Tuple[int, Dict[str, Any]]:
    used_context_tokens = (
        max(0, int(context_tokens))
        if context_tokens is not None
        else max(0, int(len(prompt or "") / 3.5))
    )
    context_tokens_source = "override" if context_tokens is not None else "prompt_heuristic"
    sections_est = 6
    if target_pages > 0:
        sections_est = max(4, min(14, int(target_pages) * 2))

    n_drafters = len([m for m in drafter_models if str(m).strip()]) or (3 if use_multi_agent else 1)
    n_reviewers = len([m for m in reviewer_models if str(m).strip()]) or (3 if use_multi_agent else 1)

    llm_s = _max_llm_points_for_models(model_ids=model_ids, size="S", context_tokens=used_context_tokens)
    llm_m = _max_llm_points_for_models(model_ids=model_ids, size="M", context_tokens=used_context_tokens)
    llm_l = _max_llm_points_for_models(model_ids=model_ids, size="L", context_tokens=used_context_tokens)

    components: list[Dict[str, Any]] = []
    total = 0

    def add(label: str, points: int, **meta: Any) -> None:
        nonlocal total
        points_i = int(points)
        total += points_i
        payload = {"label": label, "points": points_i}
        payload.update(meta)
        components.append(payload)

    add("outline_node", llm_s, calls=1, size="S")
    add("planner_node", llm_s, calls=1, size="S")
    if hyde_enabled:
        add("hyde_query", llm_s, calls=1, size="S")

    per_section = (
        (llm_m * n_drafters)  # draft
        + (llm_m * n_reviewers)  # critique
        + (llm_m * max(1, n_drafters))  # revision
        + llm_s  # judge
    )
    add(
        "sections",
        per_section * sections_est,
        sections_est=sections_est,
        n_drafters=n_drafters,
        n_reviewers=n_reviewers,
    )

    # Granular passes (iteration per section)
    if max_granular_passes and max_granular_passes > 1:
        extra_passes = max(0, int(max_granular_passes) - 1)
        add("granular_passes", per_section * sections_est * extra_passes, extra_passes=extra_passes)

    # Final review loops
    if max_final_review_loops and max_final_review_loops > 0:
        final_reviews = max(2, n_reviewers)
        add(
            "final_committee_review_parallel",
            llm_m * final_reviews * int(max_final_review_loops),
            loops=int(max_final_review_loops),
            reviewers=int(final_reviews),
        )
        add(
            "final_committee_consolidation",
            llm_s * int(max_final_review_loops),
            loops=int(max_final_review_loops),
        )

    # Style loop
    if max_style_loops and max_style_loops > 0:
        add("style_check_node", llm_l, calls=1, size="L")
        add("style_refine_node", llm_m * int(max_style_loops), loops=int(max_style_loops), size="M")

    # Tools (estimates)
    if web_search and (max_web_search_requests is None or max_web_search_requests > 0):
        per_request = calculate_points(kind="web_search", provider="tool", model=None, meta=None) or 0
        est_requests = 1
        if multi_query:
            est_requests = 2
        if isinstance(max_web_search_requests, int):
            est_requests = max(1, min(est_requests, int(max_web_search_requests)))
        add("web_search", int(per_request) * int(est_requests), n_requests_est=est_requests)

    if dense_research and deep_research_effort:
        dr_points = (
            calculate_points(
                kind="deep_research",
                provider="tool",
                model=None,
                meta={"effort": deep_research_effort, "points_multiplier": deep_research_points_multiplier},
            )
            or 0
        )
        add(
            "deep_research",
            int(dr_points),
            effort=str(deep_research_effort),
            points_multiplier=float(deep_research_points_multiplier),
        )

    breakdown = {
        "estimator": "langgraph_job_v1",
        "context_tokens_est": int(used_context_tokens),
        "context_tokens_source": context_tokens_source,
        "model_ids": [m for m in model_ids if str(m).strip()],
        "sections_est": int(sections_est),
        "components": components,
        "points_total_base": int(total),
    }
    return int(total), breakdown


def estimate_chat_turn_points(
    *,
    model_id: str,
    context_tokens: Optional[int],
    web_search: bool,
    max_web_search_requests: Optional[int],
    multi_query: bool,
    dense_research: bool,
    deep_research_effort: Optional[str],
    deep_research_points_multiplier: float = 1.0,
    perplexity_search_type: Optional[str] = None,
    perplexity_search_context_size: Optional[str] = None,
    perplexity_disable_search: bool = False,
) -> Tuple[int, Dict[str, Any]]:
    cfg = get_model_config(model_id)
    provider = cfg.provider if cfg else ""

    size = pick_size_from_context_tokens(context_tokens)
    tokens_in, tokens_out = _estimate_tokens_for_size(size, context_tokens)
    context_tokens_est = context_tokens if context_tokens is not None else tokens_in
    meta: Dict[str, Any] = {
        "size": size,
        "context_tokens": context_tokens_est,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
    }
    if provider == "perplexity":
        meta.update(
            {
                "perplexity_search_type": perplexity_search_type,
                "perplexity_search_context_size": perplexity_search_context_size,
                "perplexity_disable_search": bool(perplexity_disable_search),
            }
        )

    components = []
    total = 0

    llm_points = calculate_points(kind="llm", provider=provider, model=model_id, meta=meta) or 0
    total += int(llm_points)
    components.append(
        {
            "kind": "llm",
            "provider": provider,
            "model": model_id,
            "size": size,
            "context_tokens": context_tokens_est,
            "tokens_in_est": int(tokens_in),
            "tokens_out_est": int(tokens_out),
            "points": int(llm_points),
        }
    )

    if web_search and (max_web_search_requests is None or max_web_search_requests > 0):
        per_request = calculate_points(kind="web_search", provider="tool", model=None, meta=None) or 0
        est_requests = 1
        if multi_query:
            est_requests = 2
        if isinstance(max_web_search_requests, int):
            est_requests = max(1, min(est_requests, max_web_search_requests))
        ws_points = int(per_request) * int(est_requests)
        total += ws_points
        components.append(
            {
                "kind": "web_search",
                "n_requests_est": int(est_requests),
                "points_per_request": int(per_request),
                "points": int(ws_points),
            }
        )

    if dense_research and deep_research_effort:
        dr_points = (
            calculate_points(
                kind="deep_research",
                provider="tool",
                model=None,
                meta={
                    "effort": deep_research_effort,
                    "points_multiplier": deep_research_points_multiplier,
                },
            )
            or 0
        )
        total += int(dr_points)
        components.append(
            {
                "kind": "deep_research",
                "effort": deep_research_effort,
                "points_multiplier": float(deep_research_points_multiplier),
                "points": int(dr_points),
            }
        )

    breakdown = {
        "estimator": "chat_turn_v1",
        "provider": provider,
        "model": model_id,
        "size": size,
        "context_tokens": context_tokens_est,
        "components": components,
        "points_total_base": int(total),
    }
    return int(total), breakdown


def estimate_chat_turn_usd(
    *,
    model_id: str,
    context_tokens: Optional[int],
    web_search: bool,
    max_web_search_requests: Optional[int],
    multi_query: bool,
    dense_research: bool,
    deep_research_effort: Optional[str],
    deep_research_points_multiplier: float = 1.0,
    perplexity_search_type: Optional[str] = None,
    perplexity_search_context_size: Optional[str] = None,
    perplexity_disable_search: bool = False,
) -> Tuple[float, Dict[str, Any]]:
    usd_per_point = get_usd_per_point()
    points, breakdown = estimate_chat_turn_points(
        model_id=model_id,
        context_tokens=context_tokens,
        web_search=web_search,
        max_web_search_requests=max_web_search_requests,
        multi_query=multi_query,
        dense_research=dense_research,
        deep_research_effort=deep_research_effort,
        deep_research_points_multiplier=deep_research_points_multiplier,
        perplexity_search_type=perplexity_search_type,
        perplexity_search_context_size=perplexity_search_context_size,
        perplexity_disable_search=perplexity_disable_search,
    )
    usd = float(points) * float(usd_per_point)
    breakdown["usd_per_point"] = float(usd_per_point)
    breakdown["usd_total_base"] = usd
    return usd, breakdown
