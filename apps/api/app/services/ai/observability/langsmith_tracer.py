"""Optional LangSmith tracing helpers (fail-open)."""

from __future__ import annotations

from contextlib import contextmanager, nullcontext
from typing import Any, Dict, Iterator, Optional
import os


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def is_langsmith_enabled() -> bool:
    """Returns True only when tracing is enabled and API key is configured."""

    enabled = _env_bool("IUDEX_LANGSMITH_ENABLED", _env_bool("LANGSMITH_TRACING", False))
    has_key = bool((os.getenv("LANGSMITH_API_KEY") or "").strip())
    return enabled and has_key


def _load_trace_callable():
    try:
        from langsmith import trace  # type: ignore

        return trace
    except Exception:
        return None


def extract_langsmith_run_metadata(run_ctx: Any) -> Dict[str, str]:
    """
    Extract best-effort identifiers/URL from a LangSmith run context.

    Returns an empty dict when tracing is disabled/unavailable.
    """

    if run_ctx is None:
        return {}

    metadata: Dict[str, str] = {}

    run_id = None
    for attr in ("id", "run_id", "trace_id"):
        value = getattr(run_ctx, attr, None)
        if value:
            run_id = str(value)
            break
    if not run_id and isinstance(run_ctx, dict):
        for key in ("id", "run_id", "trace_id"):
            value = run_ctx.get(key)
            if value:
                run_id = str(value)
                break
    if run_id:
        metadata["langsmith_run_id"] = run_id

    trace_url = None
    for attr in ("url", "run_url", "trace_url"):
        value = getattr(run_ctx, attr, None)
        if value:
            trace_url = str(value)
            break
    if not trace_url and isinstance(run_ctx, dict):
        for key in ("url", "run_url", "trace_url"):
            value = run_ctx.get(key)
            if value:
                trace_url = str(value)
                break
    if trace_url and trace_url.startswith(("http://", "https://")):
        metadata["langsmith_trace_url"] = trace_url

    return metadata


@contextmanager
def langsmith_trace(
    name: str,
    *,
    run_type: str = "chain",
    metadata: Optional[Dict[str, Any]] = None,
    tags: Optional[list[str]] = None,
) -> Iterator[Any]:
    """
    Wrap code in a LangSmith trace span.

    This helper is intentionally fail-open: when LangSmith is unavailable,
    disabled, or invocation fails, execution proceeds without tracing.
    """

    if not is_langsmith_enabled():
        with nullcontext():
            yield None
        return

    trace_callable = _load_trace_callable()
    if trace_callable is None:
        with nullcontext():
            yield None
        return

    project = (os.getenv("LANGSMITH_PROJECT") or "iudex-legal-ai").strip() or "iudex-legal-ai"
    kwargs: Dict[str, Any] = {
        "name": name,
        "run_type": run_type,
        "project_name": project,
        "metadata": metadata or {},
    }
    if tags:
        kwargs["tags"] = tags

    try:
        with trace_callable(**kwargs) as run_ctx:
            yield run_ctx
            return
    except TypeError:
        # Compatibility fallback for older LangSmith signatures.
        try:
            with trace_callable(name):
                yield None
                return
        except Exception:
            pass
    except Exception:
        pass

    with nullcontext():
        yield None
