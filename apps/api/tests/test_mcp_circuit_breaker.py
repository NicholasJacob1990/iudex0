import pytest

from app.services.mcp_hub import MCPHub, MCPHubError


@pytest.mark.asyncio
async def test_circuit_breaker_opens_after_consecutive_failures(monkeypatch):
    hub = MCPHub()
    label = next(iter(hub._servers.keys()))
    hub._circuit_failures = 2
    hub._circuit_cooldown_seconds = 60

    calls = {"count": 0}

    async def fail_rpc(*args, **kwargs):
        calls["count"] += 1
        raise MCPHubError("network down")

    monkeypatch.setattr(hub, "_rpc", fail_rpc)

    with pytest.raises(MCPHubError):
        await hub.list_tools(label, refresh=True)
    with pytest.raises(MCPHubError):
        await hub.list_tools(label, refresh=True)

    status = hub.get_circuit_status()[label]
    assert status["is_open"] is True
    assert calls["count"] == 4  # 2 list_tools invocations * (tools/list + tools.list fallback)

    with pytest.raises(MCPHubError, match="Circuit breaker open"):
        await hub.list_tools(label, refresh=True)
    assert calls["count"] == 4  # fail-fast: no new RPC attempt


@pytest.mark.asyncio
async def test_circuit_breaker_closes_after_cooldown(monkeypatch):
    hub = MCPHub()
    label = next(iter(hub._servers.keys()))
    now = {"t": 100.0}
    hub._clock = lambda: now["t"]
    hub._circuit_failures = 1
    hub._circuit_cooldown_seconds = 10

    async def fail_rpc(*args, **kwargs):
        raise MCPHubError("temporary failure")

    monkeypatch.setattr(hub, "_rpc", fail_rpc)
    with pytest.raises(MCPHubError):
        await hub.list_tools(label, refresh=True)

    assert hub.get_circuit_status()[label]["is_open"] is True

    now["t"] = 112.0

    async def ok_rpc(*args, **kwargs):
        return {"tools": [{"name": "ok_tool"}]}

    monkeypatch.setattr(hub, "_rpc", ok_rpc)
    tools = await hub.list_tools(label, refresh=True)
    assert tools and tools[0]["name"] == "ok_tool"
    assert hub.get_circuit_status()[label]["is_open"] is False
