"""
Poe-like Billing (generic): Quote -> Gates -> Execute -> Reconcile.

This module is provider-agnostic. Plug any pricing model by implementing a
CostEstimator that returns a USD estimate + breakdown.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Any, Dict, List, Literal, Optional, Protocol, Tuple


DEFAULT_USD_PER_POINT = 0.00003
DEFAULT_MARGIN = 0.20

ErrorCode = Literal[
    "insufficient_balance",
    "message_budget_exceeded",
    "plan_cap_exceeded",
    "invalid_request",
]


@dataclass
class Quote:
    ok: bool
    estimated_points: int
    estimated_usd: float
    breakdown: Dict[str, Any]
    current_budget: Optional[int] = None
    suggested_budgets: Optional[List[int]] = None
    points_available: Optional[int] = None
    error: Optional[ErrorCode] = None


class CostEstimator(Protocol):
    def quote_usd(self, req: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
        ...


def usd_to_points(
    usd: float,
    *,
    usd_per_point: float = DEFAULT_USD_PER_POINT,
    margin: float = DEFAULT_MARGIN,
) -> int:
    usd_per_point = float(usd_per_point or DEFAULT_USD_PER_POINT)
    if usd_per_point <= 0:
        usd_per_point = DEFAULT_USD_PER_POINT
    # Poe-like: always round UP (never undercharge on estimate)
    return int(ceil((float(usd) * (1.0 + float(margin))) / usd_per_point))


def points_to_usd(points: int, *, usd_per_point: float = DEFAULT_USD_PER_POINT) -> float:
    usd_per_point = float(usd_per_point or DEFAULT_USD_PER_POINT)
    if usd_per_point <= 0:
        usd_per_point = DEFAULT_USD_PER_POINT
    return float(points) * usd_per_point


def round_budget_step(x: int, *, step: int = 10) -> int:
    step = int(step) if int(step) > 0 else 10
    return int(ceil(int(x) / step) * step)


def suggest_budgets(estimated: int) -> List[int]:
    e = round_budget_step(int(estimated))
    return [e, round_budget_step(e * 2), round_budget_step(e * 4)]


class TokenPricedEstimator:
    def __init__(
        self,
        *,
        price_in_per_1m: float,
        price_out_per_1m: float,
        request_fee_usd: float = 0.0,
        cached_input_discount: float = 1.0,
        over_context_threshold: Optional[int] = None,
        over_context_in_mult: float = 1.0,
        over_context_out_mult: float = 1.0,
    ):
        self.price_in = float(price_in_per_1m)
        self.price_out = float(price_out_per_1m)
        self.request_fee = float(request_fee_usd)
        self.cached_disc = float(cached_input_discount)
        self.ctx_thr = int(over_context_threshold) if over_context_threshold else None
        self.ctx_in_mult = float(over_context_in_mult)
        self.ctx_out_mult = float(over_context_out_mult)

    def quote_usd(self, req: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
        tin = int(req.get("tokens_in", 0) or 0)
        tout = int(req.get("tokens_out_pred", 0) or 0)
        cached_in = int(req.get("cached_tokens_in", 0) or 0)
        uncached_in = max(0, tin - cached_in)

        in_mult = 1.0
        out_mult = 1.0
        ctx = int(req.get("context_tokens", 0) or 0)
        if self.ctx_thr and ctx > self.ctx_thr:
            in_mult = self.ctx_in_mult
            out_mult = self.ctx_out_mult

        usd_in = (uncached_in / 1_000_000) * self.price_in * in_mult
        usd_in_cached = (cached_in / 1_000_000) * self.price_in * in_mult * self.cached_disc
        usd_out = (tout / 1_000_000) * self.price_out * out_mult
        usd_total = float(usd_in + usd_in_cached + usd_out + self.request_fee)

        breakdown = {
            "pricing_type": "per_token",
            "tokens_in": tin,
            "tokens_out_pred": tout,
            "cached_tokens_in": cached_in,
            "request_fee_usd": self.request_fee,
            "usd_in": usd_in,
            "usd_in_cached": usd_in_cached,
            "usd_out": usd_out,
            "context_tokens": ctx,
            "context_multipliers": {"in": in_mult, "out": out_mult},
        }
        return usd_total, breakdown


class RequestFeeEstimator:
    def __init__(self, *, price_per_request_usd: float):
        self.price = float(price_per_request_usd)

    def quote_usd(self, req: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
        n = int(req.get("n_requests", 1) or 1)
        usd_total = self.price * max(1, n)
        breakdown = {
            "pricing_type": "per_request",
            "n_requests": n,
            "price_per_request_usd": self.price,
        }
        return float(usd_total), breakdown


class TimePricedEstimator:
    def __init__(self, *, price_per_second_usd: float):
        self.price = float(price_per_second_usd)

    def quote_usd(self, req: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
        seconds = float(req.get("seconds", 0) or 0)
        usd_total = max(0.0, seconds) * self.price
        breakdown = {
            "pricing_type": "per_second",
            "seconds": seconds,
            "price_per_second_usd": self.price,
        }
        return float(usd_total), breakdown


class CompositeEstimator:
    def __init__(self, *estimators: CostEstimator):
        self.estimators = list(estimators)

    def quote_usd(self, req: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
        usd_total = 0.0
        parts = []
        for est in self.estimators:
            usd, br = est.quote_usd(req)
            usd_total += float(usd)
            parts.append(br)
        return float(usd_total), {"pricing_type": "composite", "parts": parts}


def quote_message(
    *,
    estimator: CostEstimator,
    req: Dict[str, Any],
    wallet_points_balance: int,
    chat_max_points_per_message: int,
    usd_per_point: float = DEFAULT_USD_PER_POINT,
    margin: float = DEFAULT_MARGIN,
) -> Quote:
    usd_est, breakdown = estimator.quote_usd(req)
    pts_est = usd_to_points(usd_est, usd_per_point=usd_per_point, margin=margin)

    if int(wallet_points_balance) < int(pts_est):
        return Quote(
            ok=False,
            estimated_points=pts_est,
            estimated_usd=float(usd_est),
            breakdown=breakdown,
            points_available=int(wallet_points_balance),
            error="insufficient_balance",
        )

    if int(pts_est) > int(chat_max_points_per_message):
        return Quote(
            ok=False,
            estimated_points=pts_est,
            estimated_usd=float(usd_est),
            breakdown=breakdown,
            points_available=int(wallet_points_balance),
            current_budget=int(chat_max_points_per_message),
            suggested_budgets=suggest_budgets(pts_est),
            error="message_budget_exceeded",
        )

    return Quote(
        ok=True,
        estimated_points=pts_est,
        estimated_usd=float(usd_est),
        breakdown=breakdown,
        points_available=int(wallet_points_balance),
    )

