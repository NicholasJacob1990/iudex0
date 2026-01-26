from __future__ import annotations

import asyncio
import os
from typing import Any, Dict, List, Optional

import httpx

from app.services.mcp_config import MCPServerConfig, load_mcp_servers_from_env


class MCPHubError(RuntimeError):
    pass


class MCPHub:
    """
    Minimal MCP client hub for Streamable HTTP-style JSON-RPC servers.

    NOTE: This is a pragmatic subset used to power two app-tools:
      - mcp_tool_search
      - mcp_tool_call
    """

    def __init__(self) -> None:
        self._servers: Dict[str, MCPServerConfig] = {s.label: s for s in load_mcp_servers_from_env()}
        self._tools_cache: Dict[str, List[Dict[str, Any]]] = {}
        self._lock = asyncio.Lock()

    def list_servers(self) -> List[Dict[str, Any]]:
        return [{"label": s.label, "url": s.url, "allowed_tools": s.allowed_tools} for s in self._servers.values()]

    def _headers_for(self, server: MCPServerConfig) -> Dict[str, str]:
        auth = server.auth or {}
        if not auth:
            return {}
        kind = str(auth.get("type") or "").strip().lower()
        if kind == "bearer":
            env_name = str(auth.get("token_env") or "").strip()
            token = (os.getenv(env_name) or "").strip() if env_name else ""
            if token:
                return {"Authorization": f"Bearer {token}"}
            return {}
        if kind == "header":
            name = str(auth.get("name") or "").strip()
            env_name = str(auth.get("value_env") or "").strip()
            value = (os.getenv(env_name) or "").strip() if env_name else ""
            if name and value:
                return {name: value}
            return {}
        return {}

    async def _rpc(self, server: MCPServerConfig, method: str, params: Optional[Dict[str, Any]] = None) -> Any:
        # Best-effort JSON-RPC 2.0 over HTTP POST. Many MCP servers expose Streamable HTTP endpoints.
        payload: Dict[str, Any] = {"jsonrpc": "2.0", "id": 1, "method": method}
        if params is not None:
            payload["params"] = params
        timeout = httpx.Timeout(30.0, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.post(server.url, json=payload, headers=self._headers_for(server))
            resp.raise_for_status()
            data = resp.json()
        if isinstance(data, dict) and data.get("error"):
            raise MCPHubError(str(data["error"]))
        if isinstance(data, dict) and "result" in data:
            return data["result"]
        return data

    async def list_tools(self, server_label: str, *, refresh: bool = False) -> List[Dict[str, Any]]:
        server = self._servers.get(server_label)
        if not server:
            raise MCPHubError(f"Unknown MCP server: {server_label}")
        async with self._lock:
            if not refresh and server_label in self._tools_cache:
                return self._tools_cache[server_label]
        # Common MCP method names: "tools/list" (some servers may use dot notation).
        try:
            result = await self._rpc(server, "tools/list", params={})
        except Exception:
            result = await self._rpc(server, "tools.list", params={})
        tools = result.get("tools") if isinstance(result, dict) else None
        if not isinstance(tools, list):
            tools = []
        # Apply allowlist if configured.
        if server.allowed_tools:
            allowed = set(server.allowed_tools)
            tools = [t for t in tools if str(t.get("name") or "") in allowed]
        async with self._lock:
            self._tools_cache[server_label] = tools
        return tools

    async def tool_search(
        self,
        query: str,
        *,
        server_labels: Optional[List[str]] = None,
        limit: int = 20,
    ) -> Dict[str, Any]:
        q = (query or "").strip().lower()
        labels = server_labels or list(self._servers.keys())
        labels = [lbl for lbl in labels if lbl in self._servers]
        matches: List[Dict[str, Any]] = []
        for lbl in labels:
            tools = await self.list_tools(lbl)
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
        return {"query": query, "matches": matches, "servers_considered": labels}

    async def tool_call(self, server_label: str, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        server = self._servers.get(server_label)
        if not server:
            raise MCPHubError(f"Unknown MCP server: {server_label}")
        if server.allowed_tools and tool_name not in set(server.allowed_tools):
            raise MCPHubError(f"Tool not allowed: {server_label}.{tool_name}")
        # Common MCP method name: "tools/call" (some servers may use dot notation).
        params = {"name": tool_name, "arguments": arguments or {}}
        try:
            result = await self._rpc(server, "tools/call", params=params)
        except Exception:
            result = await self._rpc(server, "tools.call", params=params)
        return {"server_label": server_label, "tool_name": tool_name, "result": result}


mcp_hub = MCPHub()
