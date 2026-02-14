from typing import Any, Mapping


def extract_stream_token_text(payload: Mapping[str, Any] | None) -> str:
    """
    Extract incremental streamed text from a payload that may use either:
    - `delta` (preferred contract)
    - `token` (legacy contract)
    """
    if not isinstance(payload, Mapping):
        return ""
    raw = payload.get("delta") or payload.get("token") or ""
    return str(raw) if raw else ""


def build_compat_token_event(token_text: str, *, phase: str = "generation") -> dict[str, Any]:
    """
    Build a token SSE payload with both `delta` and `token` fields.
    Keeps backward compatibility while standardizing on `delta`.
    """
    normalized = str(token_text or "")
    return {
        "type": "token",
        "delta": normalized,
        "token": normalized,
        "phase": phase,
    }

