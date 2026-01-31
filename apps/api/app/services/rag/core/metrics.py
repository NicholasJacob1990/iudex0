"""
Latency metrics collector for the RAG pipeline.

Provides percentile tracking (P50/P95/P99) per pipeline stage
using a fixed-size sliding window.
"""

from __future__ import annotations

import bisect
import math
import threading
from collections import deque
from typing import Deque, Dict, List, Optional


class LatencyCollector:
    """Collects latency measurements and computes percentiles."""

    def __init__(self, window_size: int = 1000):
        self._lock = threading.Lock()
        self._window = window_size
        # For each stage we keep:
        # - a FIFO of the last N observations (for sliding-window semantics)
        # - a sorted list of the same observations (for fast percentile reads)
        self._fifo: Dict[str, Deque[float]] = {}
        self._sorted: Dict[str, List[float]] = {}

    def record(self, stage: str, duration_ms: float) -> None:
        with self._lock:
            if stage not in self._fifo:
                self._fifo[stage] = deque()
                self._sorted[stage] = []

            fifo = self._fifo[stage]
            sorted_list = self._sorted[stage]

            fifo.append(duration_ms)
            bisect.insort(sorted_list, duration_ms)

            if len(fifo) > self._window:
                oldest = fifo.popleft()
                idx = bisect.bisect_left(sorted_list, oldest)
                if 0 <= idx < len(sorted_list):
                    sorted_list.pop(idx)

    def percentile(self, stage: str, p: float) -> float:
        """Return the p-th percentile (0-100) for a stage."""
        with self._lock:
            durations = self._sorted.get(stage, [])
            if not durations:
                return 0.0

            if p <= 0:
                return durations[0]
            if p >= 100:
                return durations[-1]

            n = len(durations)
            idx = math.ceil((p / 100.0) * n) - 1
            return durations[min(max(idx, 0), n - 1)]

    def summary(self) -> Dict[str, Dict[str, float]]:
        with self._lock:
            result = {}
            for stage, durations in self._sorted.items():
                n = len(durations)
                if not n:
                    result[stage] = {
                        "p50": 0.0,
                        "p95": 0.0,
                        "p99": 0.0,
                        "count": 0,
                        "avg": 0.0,
                    }
                    continue

                def _idx(frac: float) -> int:
                    return min(max(math.ceil(frac * n) - 1, 0), n - 1)

                result[stage] = {
                    "p50": durations[_idx(0.50)],
                    "p95": durations[_idx(0.95)],
                    "p99": durations[_idx(0.99)],
                    "count": n,
                    "avg": round(sum(durations) / n, 2),
                }
            return result

    def reset(self) -> None:
        with self._lock:
            self._fifo.clear()
            self._sorted.clear()


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_collector: Optional[LatencyCollector] = None


def get_latency_collector() -> LatencyCollector:
    global _collector
    if _collector is None:
        _collector = LatencyCollector()
    return _collector
