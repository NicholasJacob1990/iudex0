from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from threading import Lock
from typing import Any, Deque, Dict, Optional
import time


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return float(values[0])
    p = max(0.0, min(100.0, float(p)))
    sorted_values = sorted(values)
    idx = (p / 100.0) * (len(sorted_values) - 1)
    low = int(idx)
    high = min(low + 1, len(sorted_values) - 1)
    if low == high:
        return float(sorted_values[low])
    frac = idx - low
    return float(sorted_values[low] + (sorted_values[high] - sorted_values[low]) * frac)


@dataclass
class _RequestMetric:
    timestamp: float
    execution_path: str
    latency_ms: float
    success: bool
    cost_usd: float


class AgentObservabilityMetrics:
    """
    In-memory collector para métricas operacionais do plano 4.2.
    """

    def __init__(self, *, max_points: int = 5000) -> None:
        self._max_points = max(100, int(max_points))
        self._lock = Lock()
        self._requests: Deque[_RequestMetric] = deque(maxlen=self._max_points)
        self._tool_approvals: Dict[str, int] = {"allow": 0, "ask": 0, "deny": 0}
        self._fallback: Dict[str, Dict[str, int]] = {}

    def record_request(
        self,
        *,
        execution_path: str,
        latency_ms: float,
        success: bool,
        cost_usd: float = 0.0,
    ) -> None:
        metric = _RequestMetric(
            timestamp=time.time(),
            execution_path=str(execution_path or "unknown"),
            latency_ms=max(0.0, float(latency_ms)),
            success=bool(success),
            cost_usd=max(0.0, float(cost_usd)),
        )
        with self._lock:
            self._requests.append(metric)

    def record_tool_approval(self, decision: str) -> None:
        key = str(decision or "").strip().lower()
        if key not in ("allow", "ask", "deny"):
            return
        with self._lock:
            self._tool_approvals[key] += 1

    def record_fallback(self, kind: str, *, used_fallback: bool) -> None:
        key = str(kind or "unknown").strip().lower() or "unknown"
        with self._lock:
            bucket = self._fallback.setdefault(key, {"attempts": 0, "fallbacks": 0})
            bucket["attempts"] += 1
            if used_fallback:
                bucket["fallbacks"] += 1

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            requests = list(self._requests)
            approvals = dict(self._tool_approvals)
            fallback = {k: dict(v) for k, v in self._fallback.items()}

        latencies = [m.latency_ms for m in requests]
        costs = [m.cost_usd for m in requests]
        total = len(requests)
        success_count = sum(1 for m in requests if m.success)
        success_rate = (success_count / total) if total else 0.0

        approval_total = sum(approvals.values())
        approval_rates = {
            "allow_rate": (approvals["allow"] / approval_total) if approval_total else 0.0,
            "ask_rate": (approvals["ask"] / approval_total) if approval_total else 0.0,
            "deny_rate": (approvals["deny"] / approval_total) if approval_total else 0.0,
        }

        fallback_rates: Dict[str, Dict[str, float | int]] = {}
        for kind, values in fallback.items():
            attempts = int(values.get("attempts", 0) or 0)
            fallbacks = int(values.get("fallbacks", 0) or 0)
            fallback_rates[kind] = {
                "attempts": attempts,
                "fallbacks": fallbacks,
                "rate": (fallbacks / attempts) if attempts else 0.0,
            }

        return {
            "requests": {
                "total": total,
                "success_count": success_count,
                "success_rate": success_rate,
                "cost_avg_usd": (sum(costs) / len(costs)) if costs else 0.0,
                "latency_ms": {
                    "min": min(latencies) if latencies else 0.0,
                    "avg": (sum(latencies) / len(latencies)) if latencies else 0.0,
                    "p50": _percentile(latencies, 50),
                    "p95": _percentile(latencies, 95),
                    "p99": _percentile(latencies, 99),
                    "max": max(latencies) if latencies else 0.0,
                },
            },
            "tool_approvals": {
                "total": approval_total,
                "allow": approvals["allow"],
                "ask": approvals["ask"],
                "deny": approvals["deny"],
                **approval_rates,
            },
            "fallback_rates": fallback_rates,
        }

    def reset(self) -> None:
        with self._lock:
            self._requests.clear()
            self._tool_approvals = {"allow": 0, "ask": 0, "deny": 0}
            self._fallback = {}


_metrics_singleton: Optional[AgentObservabilityMetrics] = None


def get_observability_metrics() -> AgentObservabilityMetrics:
    global _metrics_singleton
    if _metrics_singleton is None:
        _metrics_singleton = AgentObservabilityMetrics()
    return _metrics_singleton


def reset_observability_metrics() -> None:
    get_observability_metrics().reset()
