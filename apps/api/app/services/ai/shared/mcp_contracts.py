from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Any, Dict, Mapping, Optional
import fnmatch
import json
import os
import time


def _as_bool(value: object, default: bool) -> bool:
    if value is None:
        return default
    raw = str(value).strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return default


def _as_int(value: object, default: int, *, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except Exception:
        parsed = default
    return max(minimum, min(maximum, parsed))


def _parse_json_map(value: object) -> Dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    text = str(value or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _sanitize_token(value: object) -> str:
    token = "".join(ch if ch.isalnum() else "_" for ch in str(value or "").strip())
    token = token.strip("_").upper()
    return token or "DEFAULT"


@dataclass(frozen=True)
class ACLDecision:
    allowed: bool
    reason: str


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    reason: str
    limit_per_minute: int
    remaining: int
    retry_after_seconds: int


@dataclass
class _RateState:
    window_start: int
    used: int = 0


@dataclass
class _CacheEntry:
    expires_at: float
    value: Dict[str, Any]


class MCPContractsManager:
    """
    Contratos operacionais para MCP (fase 4.6):
    - ACL por tenant/server/tool
    - rate limiting por tool
    - cache de resultados com TTL
    - isolamento de segredos por tenant via env
    """

    def __init__(
        self,
        *,
        env: Optional[Mapping[str, str]] = None,
        clock: Optional[callable] = None,
    ) -> None:
        self._env = env if env is not None else os.environ
        self._clock = clock or time.time
        self._lock = Lock()
        self._rate_state: Dict[str, _RateState] = {}
        self._cache_state: Dict[str, _CacheEntry] = {}

    def is_enabled(self) -> bool:
        return _as_bool(self._env.get("IUDEX_MCP_CONTRACTS_ENABLED"), True)

    def _subject(self, server_label: str, tool_name: str) -> str:
        return f"{str(server_label or '').strip()}.{str(tool_name or '').strip()}"

    def _tenant_acl(self, tenant_id: Optional[str]) -> Dict[str, Any]:
        acl_map = _parse_json_map(self._env.get("IUDEX_MCP_ACL_JSON"))
        tenant_key = str(tenant_id or "default")
        acl = acl_map.get(tenant_key)
        if not isinstance(acl, dict):
            acl = acl_map.get("default")
        return acl if isinstance(acl, dict) else {}

    def check_acl(self, tenant_id: Optional[str], server_label: str, tool_name: str) -> ACLDecision:
        if not self.is_enabled():
            return ACLDecision(allowed=True, reason="contracts_disabled")

        subject = self._subject(server_label, tool_name)
        acl = self._tenant_acl(tenant_id)
        allow = acl.get("allow", ["*"])
        deny = acl.get("deny", [])

        allow_patterns = [str(p).strip() for p in allow if str(p).strip()] if isinstance(allow, list) else ["*"]
        deny_patterns = [str(p).strip() for p in deny if str(p).strip()] if isinstance(deny, list) else []

        if any(fnmatch.fnmatch(subject, pattern) for pattern in deny_patterns):
            return ACLDecision(allowed=False, reason="acl_deny_rule")
        if allow_patterns and not any(fnmatch.fnmatch(subject, pattern) for pattern in allow_patterns):
            return ACLDecision(allowed=False, reason="acl_not_in_allowlist")
        return ACLDecision(allowed=True, reason="acl_allow")

    def _resolve_limit_per_minute(self, tenant_id: Optional[str], server_label: str, tool_name: str) -> int:
        default_limit = _as_int(
            self._env.get("IUDEX_MCP_RATE_LIMIT_PER_MINUTE"),
            60,
            minimum=1,
            maximum=10_000,
        )
        subject = self._subject(server_label, tool_name)

        tenant_overrides = self._tenant_acl(tenant_id).get("rate_limits", {})
        global_overrides = _parse_json_map(self._env.get("IUDEX_MCP_RATE_LIMIT_BY_TOOL_JSON"))

        for override_map in (tenant_overrides, global_overrides):
            if not isinstance(override_map, dict):
                continue
            for pattern, value in override_map.items():
                if fnmatch.fnmatch(subject, str(pattern)):
                    return _as_int(value, default_limit, minimum=1, maximum=10_000)
        return default_limit

    def consume_rate_limit(
        self,
        tenant_id: Optional[str],
        server_label: str,
        tool_name: str,
        *,
        cost: int = 1,
    ) -> RateLimitDecision:
        if not self.is_enabled():
            return RateLimitDecision(
                allowed=True,
                reason="contracts_disabled",
                limit_per_minute=0,
                remaining=10_000_000,
                retry_after_seconds=0,
            )

        tenant_key = str(tenant_id or "default")
        subject = self._subject(server_label, tool_name)
        key = f"{tenant_key}:{subject}"
        limit = self._resolve_limit_per_minute(tenant_id, server_label, tool_name)
        now = int(self._clock())
        window_start = now - (now % 60)
        consume = max(1, int(cost))

        with self._lock:
            state = self._rate_state.get(key)
            if state is None or state.window_start != window_start:
                state = _RateState(window_start=window_start, used=0)
                self._rate_state[key] = state

            next_used = state.used + consume
            if next_used > limit:
                retry_after = max(1, (window_start + 60) - now)
                return RateLimitDecision(
                    allowed=False,
                    reason="rate_limit_exceeded",
                    limit_per_minute=limit,
                    remaining=max(0, limit - state.used),
                    retry_after_seconds=retry_after,
                )

            state.used = next_used
            return RateLimitDecision(
                allowed=True,
                reason="rate_limit_ok",
                limit_per_minute=limit,
                remaining=max(0, limit - state.used),
                retry_after_seconds=0,
            )

    def _resolve_cache_ttl_seconds(self, tenant_id: Optional[str], server_label: str, tool_name: str) -> int:
        default_ttl = _as_int(
            self._env.get("IUDEX_MCP_CACHE_TTL_SECONDS"),
            30,
            minimum=0,
            maximum=86_400,
        )
        subject = self._subject(server_label, tool_name)

        tenant_overrides = self._tenant_acl(tenant_id).get("cache_ttl_seconds", {})
        global_overrides = _parse_json_map(self._env.get("IUDEX_MCP_CACHE_TTL_BY_TOOL_JSON"))

        for override_map in (tenant_overrides, global_overrides):
            if not isinstance(override_map, dict):
                continue
            for pattern, value in override_map.items():
                if fnmatch.fnmatch(subject, str(pattern)):
                    return _as_int(value, default_ttl, minimum=0, maximum=86_400)
        return default_ttl

    @staticmethod
    def _cache_key(
        tenant_id: Optional[str],
        server_label: str,
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> str:
        safe_args = arguments if isinstance(arguments, dict) else {}
        serialized = json.dumps(safe_args, ensure_ascii=False, sort_keys=True, default=str)
        return f"{str(tenant_id or 'default')}::{server_label}::{tool_name}::{serialized}"

    def get_cached_result(
        self,
        tenant_id: Optional[str],
        server_label: str,
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        ttl = self._resolve_cache_ttl_seconds(tenant_id, server_label, tool_name)
        if ttl <= 0:
            return None

        key = self._cache_key(tenant_id, server_label, tool_name, arguments)
        now = float(self._clock())
        with self._lock:
            entry = self._cache_state.get(key)
            if not entry:
                return None
            if now >= entry.expires_at:
                self._cache_state.pop(key, None)
                return None
            return dict(entry.value)

    def set_cached_result(
        self,
        tenant_id: Optional[str],
        server_label: str,
        tool_name: str,
        arguments: Dict[str, Any],
        value: Dict[str, Any],
    ) -> None:
        ttl = self._resolve_cache_ttl_seconds(tenant_id, server_label, tool_name)
        if ttl <= 0:
            return
        key = self._cache_key(tenant_id, server_label, tool_name, arguments)
        now = float(self._clock())
        with self._lock:
            self._cache_state[key] = _CacheEntry(
                expires_at=now + float(ttl),
                value=dict(value or {}),
            )

    def resolve_auth_headers(
        self,
        *,
        tenant_id: Optional[str],
        server_label: str,
        auth: Optional[Dict[str, Any]],
    ) -> Dict[str, str]:
        auth = dict(auth or {})
        kind = str(auth.get("type") or "").strip().lower()
        if kind not in {"bearer", "header"}:
            return {}

        tenant_token = _sanitize_token(tenant_id)
        server_token = _sanitize_token(server_label)

        if kind == "bearer":
            token = self._resolve_env_secret(
                base_env=str(auth.get("token_env") or ""),
                tenant_token=tenant_token,
                server_token=server_token,
                fallback_direct=str(auth.get("token") or ""),
                suffix="TOKEN",
            )
            if token:
                return {"Authorization": f"Bearer {token}"}
            return {}

        name = str(auth.get("name") or "").strip()
        value = self._resolve_env_secret(
            base_env=str(auth.get("value_env") or ""),
            tenant_token=tenant_token,
            server_token=server_token,
            fallback_direct=str(auth.get("value") or ""),
            suffix="HEADER_VALUE",
        )
        if name and value:
            return {name: value}
        return {}

    def _resolve_env_secret(
        self,
        *,
        base_env: str,
        tenant_token: str,
        server_token: str,
        fallback_direct: str,
        suffix: str,
    ) -> str:
        candidates: list[str] = []
        candidates.append(f"IUDEX_MCP_SECRET_{tenant_token}_{server_token}_{suffix}")

        base = str(base_env or "").strip()
        if base:
            rendered = (
                base.replace("{tenant_id}", tenant_token)
                .replace("{server_label}", server_token)
                .replace("{tenant}", tenant_token)
                .replace("{server}", server_token)
            )
            candidates.append(rendered)
            candidates.append(f"{base}_{tenant_token}")
            candidates.append(f"{base}_{tenant_token}_{server_token}")

        for env_name in candidates:
            value = str(self._env.get(env_name) or "").strip()
            if value:
                return value
        return str(fallback_direct or "").strip()

    def clear_runtime_state(self) -> None:
        with self._lock:
            self._rate_state.clear()
            self._cache_state.clear()

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "contracts_enabled": self.is_enabled(),
                "rate_entries": len(self._rate_state),
                "cache_entries": len(self._cache_state),
            }


_mcp_contracts_singleton: Optional[MCPContractsManager] = None


def get_mcp_contracts() -> MCPContractsManager:
    global _mcp_contracts_singleton
    if _mcp_contracts_singleton is None:
        _mcp_contracts_singleton = MCPContractsManager()
    return _mcp_contracts_singleton


def reset_mcp_contracts() -> None:
    global _mcp_contracts_singleton
    _mcp_contracts_singleton = None
