from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx

from app.services.mcp_config import MCPServerConfig, load_mcp_servers_from_env, load_builtin_mcp_servers
from app.services.ai.shared.mcp_contracts import get_mcp_contracts
from app.services.ai.observability.audit_log import get_tool_audit_log

logger = logging.getLogger(__name__)


class MCPHubError(RuntimeError):
    pass


@dataclass
class _CircuitState:
    failures: int = 0
    opened_until: float = 0.0
    last_error: str = ""


class MCPHub:
    """
    Minimal MCP client hub for Streamable HTTP-style JSON-RPC servers.

    NOTE: This is a pragmatic subset used to power two app-tools:
      - mcp_tool_search
      - mcp_tool_call
    """

    def __init__(self) -> None:
        env_servers = {s.label: s for s in load_mcp_servers_from_env()}
        builtin_servers = {s.label: s for s in load_builtin_mcp_servers()}
        self._servers: Dict[str, MCPServerConfig] = {**builtin_servers, **env_servers}
        self._builtin_handlers: Dict[str, Any] = {}
        self._tools_cache: Dict[str, List[Dict[str, Any]]] = {}
        self._lock = asyncio.Lock()
        self._circuit_state: Dict[str, _CircuitState] = {}
        self._clock = time.monotonic
        self._circuit_failures = self._safe_int_env(
            "IUDEX_MCP_CIRCUIT_BREAKER_FAILURES",
            default=3,
            minimum=1,
            maximum=20,
        )
        self._circuit_cooldown_seconds = self._safe_int_env(
            "IUDEX_MCP_CIRCUIT_BREAKER_COOLDOWN_SECONDS",
            default=30,
            minimum=1,
            maximum=600,
        )
        self._contracts = get_mcp_contracts()

    @staticmethod
    def _safe_int_env(name: str, *, default: int, minimum: int, maximum: int) -> int:
        try:
            value = int(os.getenv(name, str(default)) or default)
        except Exception:
            value = default
        return max(minimum, min(maximum, value))

    def _circuit_is_open(self, server_label: str) -> bool:
        state = self._circuit_state.get(server_label)
        if not state:
            return False
        now = float(self._clock())
        if state.opened_until <= 0:
            return False
        if now >= state.opened_until:
            state.opened_until = 0.0
            state.failures = 0
            state.last_error = ""
            return False
        return True

    def _record_success(self, server_label: str) -> None:
        state = self._circuit_state.get(server_label)
        if not state:
            return
        if state.failures or state.opened_until:
            state.failures = 0
            state.opened_until = 0.0
            state.last_error = ""

    def _record_failure(self, server_label: str, exc: Exception) -> None:
        state = self._circuit_state.setdefault(server_label, _CircuitState())
        state.failures += 1
        state.last_error = str(exc)
        if state.failures >= self._circuit_failures:
            state.opened_until = float(self._clock()) + float(self._circuit_cooldown_seconds)
            logger.warning(
                "MCP circuit breaker aberto para %s por %ss após %s falhas: %s",
                server_label,
                self._circuit_cooldown_seconds,
                state.failures,
                state.last_error,
            )

    def _ensure_circuit_closed(self, server_label: str) -> None:
        if not self._circuit_is_open(server_label):
            return
        state = self._circuit_state.get(server_label) or _CircuitState()
        remaining = max(0, int(state.opened_until - float(self._clock())))
        raise MCPHubError(
            f"Circuit breaker open for server '{server_label}' ({remaining}s remaining)"
        )

    def _is_builtin(self, server: MCPServerConfig) -> bool:
        """Check if a server is a built-in (in-process) server."""
        return server.url.startswith("builtin://")

    def _get_builtin_handler(self, server: MCPServerConfig) -> Any:
        """Lazily instantiate and return the handler for a built-in server."""
        label = server.label
        if label not in self._builtin_handlers:
            auth = server.auth or {}
            handler_class_path = str(auth.get("handler_class", ""))
            if not handler_class_path:
                raise MCPHubError(f"No handler_class for built-in server: {label}")
            module_path, class_name = handler_class_path.rsplit(".", 1)
            import importlib
            mod = importlib.import_module(module_path)
            cls = getattr(mod, class_name)
            self._builtin_handlers[label] = cls()
        return self._builtin_handlers[label]

    def list_servers(self) -> List[Dict[str, Any]]:
        return [
            {
                "label": s.label,
                "url": s.url,
                "allowed_tools": s.allowed_tools,
                "circuit_open": self._circuit_is_open(s.label),
            }
            for s in self._servers.values()
        ]

    def get_circuit_status(self) -> Dict[str, Dict[str, Any]]:
        now = float(self._clock())
        status: Dict[str, Dict[str, Any]] = {}
        for label in self._servers.keys():
            state = self._circuit_state.get(label) or _CircuitState()
            open_remaining = 0
            is_open = False
            if state.opened_until > 0 and now < state.opened_until:
                is_open = True
                open_remaining = int(state.opened_until - now)
            status[label] = {
                "is_open": is_open,
                "open_remaining_seconds": open_remaining,
                "failures": state.failures,
                "last_error": state.last_error,
            }
        return status

    async def initialize(self, *, refresh_tools: bool = False) -> Dict[str, Any]:
        """
        Warm-up MCP hub state.

        Loads tool catalogs for all configured servers in parallel so the first
        runtime tool search/call does not pay the full discovery cost.
        """
        labels = list(self._servers.keys())

        async def _warm_server(label: str) -> Dict[str, Any]:
            try:
                tools = await self.list_tools(label, refresh=refresh_tools)
                return {
                    "label": label,
                    "status": "ok",
                    "tools_count": len(tools),
                }
            except Exception as exc:
                return {
                    "label": label,
                    "status": "error",
                    "tools_count": 0,
                    "error": str(exc),
                }

        warmed = await asyncio.gather(*[_warm_server(lbl) for lbl in labels])
        servers_ready = sum(1 for item in warmed if item["status"] == "ok")

        return {
            "servers_total": len(labels),
            "servers_ready": servers_ready,
            "servers": warmed,
        }

    def _headers_for(self, server: MCPServerConfig, *, tenant_id: Optional[str] = None) -> Dict[str, str]:
        try:
            headers = self._contracts.resolve_auth_headers(
                tenant_id=tenant_id,
                server_label=server.label,
                auth=server.auth,
            )
            if headers:
                return headers
        except Exception:
            # Fail-open para compatibilidade com configs antigas de auth.
            pass

        auth = server.auth or {}
        if not auth:
            return {}
        kind = str(auth.get("type") or "").strip().lower()
        if kind == "bearer":
            # Support both env-based (token_env) and direct (token) values
            env_name = str(auth.get("token_env") or "").strip()
            token = (os.getenv(env_name) or "").strip() if env_name else ""
            if not token:
                token = str(auth.get("token") or "").strip()
            if token:
                return {"Authorization": f"Bearer {token}"}
            return {}
        if kind == "header":
            name = str(auth.get("name") or "").strip()
            # Support both env-based (value_env) and direct (value) values
            env_name = str(auth.get("value_env") or "").strip()
            value = (os.getenv(env_name) or "").strip() if env_name else ""
            if not value:
                value = str(auth.get("value") or "").strip()
            if name and value:
                return {name: value}
            return {}
        return {}

    async def _rpc(
        self,
        server: MCPServerConfig,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        *,
        tenant_id: Optional[str] = None,
    ) -> Any:
        # Built-in servers: route directly to in-process handler
        if self._is_builtin(server):
            handler = self._get_builtin_handler(server)
            result = await handler.handle_request(method, params)
            if isinstance(result, dict) and result.get("error"):
                raise MCPHubError(str(result["error"]))
            return result

        # Best-effort JSON-RPC 2.0 over HTTP POST. Many MCP servers expose Streamable HTTP endpoints.
        payload: Dict[str, Any] = {"jsonrpc": "2.0", "id": 1, "method": method}
        if params is not None:
            payload["params"] = params
        timeout = httpx.Timeout(30.0, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.post(
                server.url,
                json=payload,
                headers=self._headers_for(server, tenant_id=tenant_id),
            )
            resp.raise_for_status()
            data = resp.json()
        if isinstance(data, dict) and data.get("error"):
            raise MCPHubError(str(data["error"]))
        if isinstance(data, dict) and "result" in data:
            return data["result"]
        return data

    async def list_tools(
        self,
        server_label: str,
        *,
        refresh: bool = False,
        tenant_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        server = self._servers.get(server_label)
        if not server:
            raise MCPHubError(f"Unknown MCP server: {server_label}")
        self._ensure_circuit_closed(server_label)
        raw_tools: Optional[List[Dict[str, Any]]] = None
        async with self._lock:
            if not refresh and server_label in self._tools_cache:
                raw_tools = list(self._tools_cache[server_label])

        if raw_tools is None:
            # Common MCP method names: "tools/list" (some servers may use dot notation).
            try:
                try:
                    result = await self._rpc(server, "tools/list", params={}, tenant_id=tenant_id)
                except Exception:
                    result = await self._rpc(server, "tools.list", params={}, tenant_id=tenant_id)
            except Exception as exc:
                self._record_failure(server_label, exc)
                raise
            self._record_success(server_label)
            raw_tools = result.get("tools") if isinstance(result, dict) else None
            if not isinstance(raw_tools, list):
                raw_tools = []
            # Apply server allowlist once.
            if server.allowed_tools:
                allowed = set(server.allowed_tools)
                raw_tools = [t for t in raw_tools if str(t.get("name") or "") in allowed]
            async with self._lock:
                self._tools_cache[server_label] = list(raw_tools)

        filtered_tools: List[Dict[str, Any]] = []
        for tool in raw_tools:
            name = str(tool.get("name") or "").strip()
            acl = self._contracts.check_acl(tenant_id, server_label, name)
            if acl.allowed:
                filtered_tools.append(tool)
        return filtered_tools

    async def tool_search(
        self,
        query: str,
        *,
        server_labels: Optional[List[str]] = None,
        limit: int = 20,
        tenant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        q = (query or "").strip().lower()
        labels = server_labels or list(self._servers.keys())
        labels = [lbl for lbl in labels if lbl in self._servers]
        matches: List[Dict[str, Any]] = []
        server_errors: Dict[str, str] = {}
        for lbl in labels:
            try:
                tools = await self.list_tools(lbl, tenant_id=tenant_id)
            except Exception as exc:
                server_errors[lbl] = str(exc)
                continue
            for tool in tools:
                name = str(tool.get("name") or "")
                desc = str(tool.get("description") or "")
                hay = f"{name}\n{desc}".lower()
                if q and q not in hay:
                    continue
                matches.append(
                    {
                        "server_label": lbl,
                        "name": name,
                        "description": desc,
                        "input_schema": tool.get("inputSchema") or tool.get("input_schema"),
                    }
                )
        matches = matches[: max(1, min(int(limit), 100))]
        return {
            "query": query,
            "matches": matches,
            "servers_considered": labels,
            "server_errors": server_errors,
        }

    async def tool_call(
        self,
        server_label: str,
        tool_name: str,
        arguments: Dict[str, Any],
        *,
        tenant_id: Optional[str] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        server = self._servers.get(server_label)
        if not server:
            raise MCPHubError(f"Unknown MCP server: {server_label}")
        self._ensure_circuit_closed(server_label)
        if server.allowed_tools and tool_name not in set(server.allowed_tools):
            raise MCPHubError(f"Tool not allowed: {server_label}.{tool_name}")

        tool_input = arguments if isinstance(arguments, dict) else {}
        full_tool_name = f"{server_label}.{tool_name}"
        audit = get_tool_audit_log()
        started = time.perf_counter()

        acl = self._contracts.check_acl(tenant_id, server_label, tool_name)
        try:
            audit.record_permission_decision(
                tool_name=full_tool_name,
                decision="allow" if acl.allowed else "deny",
                user_id=user_id,
                tenant_id=tenant_id,
                session_id=session_id,
                provider="mcp",
                tool_input=tool_input,
                source="mcp_contract_acl",
                metadata={"reason": acl.reason},
            )
        except Exception:
            pass
        if not acl.allowed:
            raise MCPHubError(f"Tool blocked by tenant ACL: {full_tool_name}")

        cached = self._contracts.get_cached_result(
            tenant_id=tenant_id,
            server_label=server_label,
            tool_name=tool_name,
            arguments=tool_input,
        )
        if cached is not None:
            try:
                audit.record_tool_execution(
                    tool_name=full_tool_name,
                    success=True,
                    user_id=user_id,
                    tenant_id=tenant_id,
                    session_id=session_id,
                    provider="mcp",
                    duration_ms=int((time.perf_counter() - started) * 1000),
                    tool_input=tool_input,
                    permission_decision="allow",
                    metadata={"cached": True, "source": "mcp_contract_cache"},
                )
            except Exception:
                pass
            return {
                "server_label": server_label,
                "tool_name": tool_name,
                "result": cached.get("value", cached),
                "cached": True,
            }

        rate = self._contracts.consume_rate_limit(tenant_id, server_label, tool_name)
        if not rate.allowed:
            try:
                audit.record_permission_decision(
                    tool_name=full_tool_name,
                    decision="deny",
                    user_id=user_id,
                    tenant_id=tenant_id,
                    session_id=session_id,
                    provider="mcp",
                    tool_input=tool_input,
                    source="mcp_contract_rate_limit",
                    metadata={
                        "reason": rate.reason,
                        "retry_after_seconds": rate.retry_after_seconds,
                        "limit_per_minute": rate.limit_per_minute,
                    },
                )
            except Exception:
                pass
            raise MCPHubError(
                f"Rate limit exceeded for {full_tool_name} "
                f"(retry in {rate.retry_after_seconds}s)"
            )

        # Common MCP method name: "tools/call" (some servers may use dot notation).
        params = {"name": tool_name, "arguments": tool_input}
        error_text: Optional[str] = None
        result: Optional[Dict[str, Any]] = None
        try:
            try:
                result = await self._rpc(
                    server,
                    "tools/call",
                    params=params,
                    tenant_id=tenant_id,
                )
            except Exception:
                result = await self._rpc(
                    server,
                    "tools.call",
                    params=params,
                    tenant_id=tenant_id,
                )
            self._record_success(server_label)
            self._contracts.set_cached_result(
                tenant_id=tenant_id,
                server_label=server_label,
                tool_name=tool_name,
                arguments=tool_input,
                value={"value": result},
            )
            return {
                "server_label": server_label,
                "tool_name": tool_name,
                "result": result,
                "cached": False,
            }
        except Exception as exc:
            self._record_failure(server_label, exc)
            error_text = str(exc)
            raise
        finally:
            try:
                audit.record_tool_execution(
                    tool_name=full_tool_name,
                    success=error_text is None,
                    user_id=user_id,
                    tenant_id=tenant_id,
                    session_id=session_id,
                    provider="mcp",
                    duration_ms=int((time.perf_counter() - started) * 1000),
                    error=error_text,
                    tool_input=tool_input,
                    permission_decision="allow",
                    metadata={"cached": False, "source": "mcp_hub"},
                )
            except Exception:
                pass


    def with_user_servers(self, user_preferences: dict) -> "MCPHub":
        """Return a new hub instance that includes user-configured servers."""
        from app.services.mcp_config import load_user_mcp_servers

        user_servers = load_user_mcp_servers(user_preferences)
        if not user_servers:
            return self
        merged = MCPHub.__new__(MCPHub)
        merged._servers = {**self._servers}
        for s in user_servers:
            merged._servers[s.label] = s
        merged._builtin_handlers = dict(getattr(self, "_builtin_handlers", {}))
        merged._tools_cache: Dict[str, List[Dict[str, Any]]] = {}
        merged._lock = asyncio.Lock()
        merged._circuit_state = dict(getattr(self, "_circuit_state", {}))
        merged._clock = getattr(self, "_clock", time.monotonic)
        merged._circuit_failures = getattr(self, "_circuit_failures", 3)
        merged._circuit_cooldown_seconds = getattr(self, "_circuit_cooldown_seconds", 30)
        merged._contracts = getattr(self, "_contracts", get_mcp_contracts())
        return merged


mcp_hub = MCPHub()
