"""
HMAC tokens for cryptographically-binding approvals in chat/agent flows.

Goal: bind what the user saw (tool_name + tool_input + tool_id + job_id) to what
the server will execute after the user confirms.

This is not meant to be a JWT replacement; it is a short-lived, signed blob.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any, Dict, Optional, Tuple


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(raw: str) -> bytes:
    pad = "=" * (-len(raw) % 4)
    return base64.urlsafe_b64decode((raw + pad).encode("ascii"))


def _token_secret() -> bytes:
    # Prefer dedicated secret, then fall back to shared app secrets.
    secret = (
        os.getenv("TOOL_APPROVAL_TOKEN_SECRET")
        or os.getenv("LINK_ENTITIES_TOKEN_SECRET")
        or os.getenv("JWT_SECRET_KEY")
        or os.getenv("SECRET_KEY")
        or ""
    ).strip()
    if not secret:
        # Dev fallback. In production, set TOOL_APPROVAL_TOKEN_SECRET.
        secret = "dev_insecure_secret_change_me"
    return secret.encode("utf-8")


def _clamp_ttl(ttl_s: int) -> int:
    # Keep it short-lived; approvals should happen quickly.
    return max(60, min(3600, int(ttl_s)))


def make_tool_approval_token(
    *,
    job_id: str,
    tool_id: str,
    tool_name: str,
    tool_input: Dict[str, Any],
    tenant_id: Optional[str] = None,
    ttl_seconds: Optional[int] = None,
) -> str:
    now = int(time.time())
    ttl = _clamp_ttl(int(ttl_seconds or (os.getenv("TOOL_APPROVAL_TTL_SECONDS") or 900)))
    payload: Dict[str, Any] = {
        "v": 1,
        "iat": now,
        "exp": now + ttl,
        "job_id": str(job_id),
        "tool_id": str(tool_id),
        "tool_name": str(tool_name),
        "tool_input": tool_input if isinstance(tool_input, dict) else {},
    }
    if tenant_id:
        payload["tenant_id"] = str(tenant_id)

    blob = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    sig = hmac.new(_token_secret(), blob, hashlib.sha256).digest()
    return f"{_b64url_encode(blob)}.{_b64url_encode(sig)}"


def verify_tool_approval_token(token: str) -> Tuple[bool, Optional[Dict[str, Any]], str]:
    token = (token or "").strip()
    if not token or "." not in token:
        return False, None, "missing_token"

    payload_b64, sig_b64 = token.split(".", 1)
    try:
        blob = _b64url_decode(payload_b64)
        sig = _b64url_decode(sig_b64)
    except Exception:
        return False, None, "invalid_encoding"

    expected = hmac.new(_token_secret(), blob, hashlib.sha256).digest()
    if not hmac.compare_digest(expected, sig):
        return False, None, "bad_signature"

    try:
        payload = json.loads(blob.decode("utf-8"))
    except Exception:
        return False, None, "bad_payload"

    if not isinstance(payload, dict):
        return False, None, "bad_payload"

    now = int(time.time())
    exp = payload.get("exp")
    if isinstance(exp, int) and now > exp:
        return False, payload, "expired"

    return True, payload, ""

