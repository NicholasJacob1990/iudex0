from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Optional, Dict, Any
import asyncio
import logging
import uuid

from app.services.job_manager import job_manager
from app.services.billing_service import calculate_points

logger = logging.getLogger("ApiCallTracker")

_job_id_ctx: ContextVar[Optional[str]] = ContextVar("api_call_job_id", default=None)
_billing_meta_ctx: ContextVar[Optional[Dict[str, Any]]] = ContextVar("api_call_billing_meta", default=None)
_points_total_ctx: ContextVar[int] = ContextVar("api_call_points_total", default=0)


@dataclass(frozen=True)
class UsageScope:
    scope_type: str
    scope_id: str
    user_id: Optional[str] = None
    turn_id: Optional[str] = None


_usage_scope_ctx: ContextVar[Optional[UsageScope]] = ContextVar("api_call_scope", default=None)
_background_loop: Optional[asyncio.AbstractEventLoop] = None


def set_background_loop(loop: Optional[asyncio.AbstractEventLoop]) -> None:
    global _background_loop
    _background_loop = loop


def set_job_id(job_id: Optional[str]) -> Optional[Token]:
    if not job_id:
        return None
    return _job_id_ctx.set(job_id)


def reset_job_id(token: Optional[Token]) -> None:
    if token is None:
        return
    _job_id_ctx.reset(token)


def get_job_id() -> Optional[str]:
    return _job_id_ctx.get()


def set_usage_scope(
    scope_type: Optional[str],
    scope_id: Optional[str],
    *,
    user_id: Optional[str] = None,
    turn_id: Optional[str] = None,
) -> Optional[Token]:
    if not scope_type or not scope_id:
        return None
    return _usage_scope_ctx.set(
        UsageScope(
            scope_type=scope_type,
            scope_id=scope_id,
            user_id=user_id,
            turn_id=turn_id,
        )
    )


def reset_usage_scope(token: Optional[Token]) -> None:
    if token is None:
        return
    _usage_scope_ctx.reset(token)


def get_usage_scope() -> Optional[UsageScope]:
    return _usage_scope_ctx.get()


@contextmanager
def billing_context(**meta: Any):
    current = _billing_meta_ctx.get() or {}
    merged = dict(current)
    for key, value in meta.items():
        if value is not None:
            merged[key] = value
    token = _billing_meta_ctx.set(merged)
    try:
        yield
    finally:
        _billing_meta_ctx.reset(token)


def get_billing_meta() -> Dict[str, Any]:
    return dict(_billing_meta_ctx.get() or {})


@contextmanager
def usage_context(
    scope_type: Optional[str],
    scope_id: Optional[str],
    *,
    user_id: Optional[str] = None,
    turn_id: Optional[str] = None,
):
    token = set_usage_scope(scope_type, scope_id, user_id=user_id, turn_id=turn_id)
    try:
        yield
    finally:
        reset_usage_scope(token)


@contextmanager
def job_context(job_id: Optional[str], *, user_id: Optional[str] = None):
    job_token = set_job_id(job_id)
    usage_token = set_usage_scope("job", job_id, user_id=user_id) if job_id else None
    try:
        yield
    finally:
        reset_usage_scope(usage_token)
        reset_job_id(job_token)


@contextmanager
def points_counter_context():
    token = _points_total_ctx.set(0)
    try:
        yield
    finally:
        _points_total_ctx.reset(token)


def get_points_total() -> int:
    try:
        return int(_points_total_ctx.get() or 0)
    except Exception:
        return 0


async def _persist_api_call(payload: Dict[str, Any]) -> None:
    try:
        from app.core.database import AsyncSessionLocal
        from app.models.api_usage import ApiCallUsage
    except Exception as exc:
        logger.warning(f"ApiCallUsage unavailable: {exc}")
        return

    try:
        async with AsyncSessionLocal() as session:
            session.add(ApiCallUsage(**payload))
            await session.commit()
    except Exception as exc:
        logger.warning(f"Failed to persist api call usage: {exc}")


def _schedule_persist(payload: Dict[str, Any]) -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        loop.create_task(_persist_api_call(payload))
        return

    if _background_loop and _background_loop.is_running():
        asyncio.run_coroutine_threadsafe(_persist_api_call(payload), _background_loop)
        return

    logger.debug("ApiCallTracker: no event loop available to persist usage.")


def record_api_call(
    *,
    kind: str,
    provider: str,
    model: Optional[str] = None,
    success: Optional[bool] = None,
    cached: Optional[bool] = None,
    meta: Optional[Dict[str, Any]] = None,
    job_id: Optional[str] = None,
    scope_type: Optional[str] = None,
    scope_id: Optional[str] = None,
    turn_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> None:
    resolved_job_id = job_id or get_job_id()
    scope = None
    if scope_type and scope_id:
        scope = UsageScope(scope_type=scope_type, scope_id=scope_id, user_id=user_id, turn_id=turn_id)
    else:
        scope = get_usage_scope()
        if not scope and resolved_job_id:
            scope = UsageScope(scope_type="job", scope_id=resolved_job_id, user_id=user_id, turn_id=turn_id)

    if not scope:
        return

    merged_meta: Dict[str, Any] = get_billing_meta()
    if isinstance(meta, dict):
        merged_meta.update(meta)

    explicit_points_override = isinstance((meta or {}).get("points"), (int, float))
    has_usage_signals = any(
        merged_meta.get(key) is not None
        for key in (
            "tokens_in",
            "tokens_out",
            "cached_tokens_in",
            "cache_write_tokens_in",
            "seconds_audio",
            "seconds_video",
            "search_queries",
            "citation_tokens",
            "reasoning_tokens",
            "n_requests",
        )
    )
    should_compute_points = True
    if success is False and not explicit_points_override and not has_usage_signals:
        should_compute_points = False

    points = (
        calculate_points(
            kind=kind,
            provider=provider,
            model=model,
            meta=merged_meta,
        )
        if should_compute_points
        else None
    )
    if points is not None:
        merged_meta["points"] = points
        try:
            _points_total_ctx.set(int(_points_total_ctx.get() or 0) + int(points))
        except Exception:
            _points_total_ctx.set(0)

    if resolved_job_id:
        job_manager.record_api_call(
            resolved_job_id,
            kind=kind,
            provider=provider,
            model=model,
            success=success,
            cached=cached,
            meta=merged_meta,
            points=points,
        )

    payload = {
        "id": str(uuid.uuid4()),
        "scope_type": scope.scope_type,
        "scope_id": scope.scope_id,
        "turn_id": scope.turn_id,
        "user_id": scope.user_id,
        "kind": kind,
        "provider": provider,
        "model": model,
        "success": success,
        "cached": cached,
        "meta": dict(merged_meta),
    }
    _schedule_persist(payload)
