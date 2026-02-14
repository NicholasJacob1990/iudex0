import json

import pytest

from app.services.ai.shared.mcp_contracts import MCPContractsManager
from app.services.mcp_config import MCPServerConfig
from app.services.mcp_hub import MCPHub, MCPHubError


def test_mcp_contracts_acl_allow_and_deny_patterns():
    env = {
        "IUDEX_MCP_CONTRACTS_ENABLED": "true",
        "IUDEX_MCP_ACL_JSON": json.dumps(
            {
                "default": {
                    "allow": ["srv.allowed_*"],
                    "deny": ["srv.allowed_blocked"],
                }
            }
        ),
    }
    contracts = MCPContractsManager(env=env)

    assert contracts.check_acl("tenant-a", "srv", "allowed_tool").allowed is True
    assert contracts.check_acl("tenant-a", "srv", "allowed_blocked").allowed is False
    assert contracts.check_acl("tenant-a", "srv", "other_tool").allowed is False


def test_mcp_contracts_rate_limit_per_tool_override():
    now = {"t": 120.0}
    env = {
        "IUDEX_MCP_RATE_LIMIT_PER_MINUTE": "5",
        "IUDEX_MCP_RATE_LIMIT_BY_TOOL_JSON": json.dumps({"srv.strict_tool": 1}),
    }
    contracts = MCPContractsManager(env=env, clock=lambda: now["t"])

    first = contracts.consume_rate_limit("tenant-a", "srv", "strict_tool")
    assert first.allowed is True
    second = contracts.consume_rate_limit("tenant-a", "srv", "strict_tool")
    assert second.allowed is False
    assert second.reason == "rate_limit_exceeded"
    assert second.retry_after_seconds > 0

    now["t"] = 181.0
    third = contracts.consume_rate_limit("tenant-a", "srv", "strict_tool")
    assert third.allowed is True


def test_mcp_contracts_cache_ttl_with_override():
    now = {"t": 1000.0}
    env = {
        "IUDEX_MCP_CACHE_TTL_SECONDS": "0",
        "IUDEX_MCP_CACHE_TTL_BY_TOOL_JSON": json.dumps({"srv.cacheable_*": 5}),
    }
    contracts = MCPContractsManager(env=env, clock=lambda: now["t"])
    args = {"query": "precedente"}

    contracts.set_cached_result("tenant-a", "srv", "cacheable_tool", args, {"value": {"ok": True}})
    cached = contracts.get_cached_result("tenant-a", "srv", "cacheable_tool", args)
    assert cached == {"value": {"ok": True}}

    now["t"] = 1006.0
    expired = contracts.get_cached_result("tenant-a", "srv", "cacheable_tool", args)
    assert expired is None


def test_mcp_contracts_resolve_tenant_secret_header():
    env = {
        "IUDEX_MCP_SECRET_TENANT_A_SERVER_X_TOKEN": "tenant-secret-token",
        "BASE_TOKEN": "base-token",
    }
    contracts = MCPContractsManager(env=env)
    headers = contracts.resolve_auth_headers(
        tenant_id="tenant-a",
        server_label="server-x",
        auth={"type": "bearer", "token_env": "BASE_TOKEN"},
    )
    assert headers["Authorization"] == "Bearer tenant-secret-token"


@pytest.mark.asyncio
async def test_mcp_hub_applies_acl_and_cache(monkeypatch):
    env = {
        "IUDEX_MCP_ACL_JSON": json.dumps({"default": {"allow": ["srv.allowed_tool"]}}),
        "IUDEX_MCP_CACHE_TTL_SECONDS": "60",
        "IUDEX_MCP_RATE_LIMIT_PER_MINUTE": "20",
    }
    hub = MCPHub()
    hub._contracts = MCPContractsManager(env=env)
    hub._servers = {"srv": MCPServerConfig(label="srv", url="https://example.invalid/mcp")}
    hub._tools_cache = {}
    hub._circuit_state = {}

    calls = {"count": 0}

    async def fake_rpc(server, method, params=None, tenant_id=None):
        if method in {"tools/list", "tools.list"}:
            return {"tools": [{"name": "allowed_tool"}, {"name": "blocked_tool"}]}
        calls["count"] += 1
        return {"ok": True, "count": calls["count"]}

    monkeypatch.setattr(hub, "_rpc", fake_rpc)

    search = await hub.tool_search("tool", server_labels=["srv"], tenant_id="tenant-a")
    names = [item["name"] for item in search["matches"]]
    assert names == ["allowed_tool"]

    first = await hub.tool_call("srv", "allowed_tool", {"q": "abc"}, tenant_id="tenant-a")
    assert first["cached"] is False
    assert first["result"]["ok"] is True
    assert calls["count"] == 1

    second = await hub.tool_call("srv", "allowed_tool", {"q": "abc"}, tenant_id="tenant-a")
    assert second["cached"] is True
    assert second["result"]["ok"] is True
    assert calls["count"] == 1

    with pytest.raises(MCPHubError, match="Tool blocked by tenant ACL"):
        await hub.tool_call("srv", "blocked_tool", {"q": "abc"}, tenant_id="tenant-a")
