from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Callable, Dict, Optional
import os
import time


def _as_int(value: object, default: int, *, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except Exception:
        parsed = default
    return max(minimum, min(maximum, parsed))


@dataclass(frozen=True)
class QuotaDecision:
    allowed: bool
    reason: str
    remaining_requests: int
    remaining_tokens: int
    reset_at_unix: int


@dataclass
class _WindowState:
    window_start: int
    requests_used: int = 0
    delegated_tokens_used: int = 0
    concurrent_subagents: int = 0


class TenantQuotaManager:
    """
    Quotas simples por tenant:
    - requests por janela
    - tokens delegados por janela
    - concorrência máxima de subagentes
    """

    def __init__(
        self,
        *,
        max_requests_per_window: Optional[int] = None,
        max_delegated_tokens_per_window: Optional[int] = None,
        max_concurrent_subagents: Optional[int] = None,
        window_seconds: Optional[int] = None,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        self.max_requests_per_window = (
            max_requests_per_window
            if max_requests_per_window is not None
            else _as_int(os.getenv("IUDEX_QUOTA_REQUESTS_PER_WINDOW"), 120, minimum=1, maximum=100_000)
        )
        self.max_delegated_tokens_per_window = (
            max_delegated_tokens_per_window
            if max_delegated_tokens_per_window is not None
            else _as_int(
                os.getenv("IUDEX_QUOTA_DELEGATED_TOKENS_PER_WINDOW"),
                200_000,
                minimum=1_000,
                maximum=50_000_000,
            )
        )
        self.max_concurrent_subagents = (
            max_concurrent_subagents
            if max_concurrent_subagents is not None
            else _as_int(os.getenv("IUDEX_QUOTA_MAX_CONCURRENT_SUBAGENTS"), 8, minimum=1, maximum=200)
        )
        self.window_seconds = (
            window_seconds
            if window_seconds is not None
            else _as_int(os.getenv("IUDEX_QUOTA_WINDOW_SECONDS"), 60, minimum=10, maximum=3600)
        )
        self._clock = clock or time.time
        self._lock = Lock()
        self._state: Dict[str, _WindowState] = {}

    def _window_start(self, now: float) -> int:
        return int(now // self.window_seconds) * self.window_seconds

    def _get_state(self, tenant_id: str, now: float) -> _WindowState:
        key = str(tenant_id or "anonymous")
        window_start = self._window_start(now)
        state = self._state.get(key)
        if state is None or state.window_start != window_start:
            concurrent = state.concurrent_subagents if state else 0
            state = _WindowState(window_start=window_start, concurrent_subagents=concurrent)
            self._state[key] = state
        return state

    def check_and_consume(
        self,
        tenant_id: str,
        *,
        requests_cost: int = 1,
        delegated_tokens_cost: int = 0,
    ) -> QuotaDecision:
        now = self._clock()
        with self._lock:
            state = self._get_state(tenant_id, now)
            next_requests = state.requests_used + max(0, int(requests_cost))
            next_tokens = state.delegated_tokens_used + max(0, int(delegated_tokens_cost))
            if next_requests > self.max_requests_per_window:
                return self._deny("requests_per_window_exceeded", state)
            if next_tokens > self.max_delegated_tokens_per_window:
                return self._deny("delegated_tokens_per_window_exceeded", state)

            state.requests_used = next_requests
            state.delegated_tokens_used = next_tokens
            return self._allow(state)

    def acquire_subagent_slot(self, tenant_id: str) -> bool:
        now = self._clock()
        with self._lock:
            state = self._get_state(tenant_id, now)
            if state.concurrent_subagents >= self.max_concurrent_subagents:
                return False
            state.concurrent_subagents += 1
            return True

    def release_subagent_slot(self, tenant_id: str) -> None:
        now = self._clock()
        with self._lock:
            state = self._get_state(tenant_id, now)
            if state.concurrent_subagents > 0:
                state.concurrent_subagents -= 1

    def _allow(self, state: _WindowState) -> QuotaDecision:
        return QuotaDecision(
            allowed=True,
            reason="ok",
            remaining_requests=max(0, self.max_requests_per_window - state.requests_used),
            remaining_tokens=max(0, self.max_delegated_tokens_per_window - state.delegated_tokens_used),
            reset_at_unix=state.window_start + self.window_seconds,
        )

    def _deny(self, reason: str, state: _WindowState) -> QuotaDecision:
        return QuotaDecision(
            allowed=False,
            reason=reason,
            remaining_requests=max(0, self.max_requests_per_window - state.requests_used),
            remaining_tokens=max(0, self.max_delegated_tokens_per_window - state.delegated_tokens_used),
            reset_at_unix=state.window_start + self.window_seconds,
        )
