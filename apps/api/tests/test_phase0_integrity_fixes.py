import pytest
from unittest.mock import AsyncMock

from app.services.ai.shared.sse_protocol import ToolApprovalMode
from app.services.ai.shared.tool_handlers import ToolExecutionContext, ToolHandlers
from app.services.ai.shared.unified_tools import RISK_TO_PERMISSION, ToolRiskLevel
from app.services.mcp_hub import MCPHub


def test_risk_to_permission_defaults_are_safe():
    assert RISK_TO_PERMISSION[ToolRiskLevel.LOW] == ToolApprovalMode.ALLOW
    assert RISK_TO_PERMISSION[ToolRiskLevel.MEDIUM] == ToolApprovalMode.ASK
    assert RISK_TO_PERMISSION[ToolRiskLevel.HIGH] == ToolApprovalMode.DENY


@pytest.mark.asyncio
async def test_mcp_hub_initialize_warms_tool_catalog(monkeypatch):
    hub = MCPHub()

    async def fake_list_tools(server_label: str, refresh: bool = False):
        assert refresh is True
        return [{"name": f"{server_label}_tool"}]

    monkeypatch.setattr(hub, "list_tools", fake_list_tools)

    result = await hub.initialize(refresh_tools=True)

    assert result["servers_total"] >= 1
    assert result["servers_ready"] == result["servers_total"]
    assert len(result["servers"]) == result["servers_total"]
    assert all(item["status"] == "ok" for item in result["servers"])
    assert all(item["tools_count"] == 1 for item in result["servers"])


@pytest.mark.asyncio
async def test_mcp_handlers_use_tool_search_and_tool_call(monkeypatch):
    handlers = ToolHandlers()

    from app.services import mcp_hub as mcp_hub_module

    search_mock = AsyncMock(
        return_value={
            "query": "jurisprudencia",
            "matches": [{"server_label": "bnp", "name": "buscar_precedentes"}],
            "servers_considered": ["bnp"],
        }
    )
    call_mock = AsyncMock(
        return_value={
            "server_label": "bnp",
            "tool_name": "buscar_precedentes",
            "result": {"ok": True},
        }
    )

    monkeypatch.setattr(mcp_hub_module.mcp_hub, "tool_search", search_mock)
    monkeypatch.setattr(mcp_hub_module.mcp_hub, "tool_call", call_mock)

    search_result = await handlers.handle_mcp_tool_search(
        {"query": "jurisprudencia", "server_labels": ["bnp"], "limit": 5}
    )
    assert search_result["count"] == 1
    assert search_result["tools"][0]["name"] == "buscar_precedentes"
    search_mock.assert_awaited_once_with(
        query="jurisprudencia",
        server_labels=["bnp"],
        limit=5,
        tenant_id=None,
    )

    call_result = await handlers.handle_mcp_tool_call(
        {
            "server_label": "bnp",
            "tool_name": "buscar_precedentes",
            "arguments": {"tema": "1118"},
        }
    )
    assert call_result["success"] is True
    assert call_result["tool"] == "buscar_precedentes"
    call_mock.assert_awaited_once_with(
        server_label="bnp",
        tool_name="buscar_precedentes",
        arguments={"tema": "1118"},
        tenant_id=None,
        user_id=None,
        session_id=None,
    )


@pytest.mark.asyncio
async def test_delegate_research_calls_parallel_subgraph_with_query(monkeypatch):
    handlers = ToolHandlers()
    ctx = ToolExecutionContext(user_id="user-1", tenant_id="tenant-1", case_id="case-1")

    calls = []

    async def fake_run_parallel_research(**kwargs):
        calls.append(kwargs)
        return {
            "merged_context": f"contexto:{kwargs['query']}",
            "citations_map": {},
            "sources_used": ["rag_local"],
            "metrics": {},
        }

    import app.services.ai.langgraph.subgraphs as subgraphs_module

    monkeypatch.setattr(
        subgraphs_module,
        "run_parallel_research",
        fake_run_parallel_research,
    )

    result = await handlers.handle_delegate_research(
        {
            "research_queries": [
                {"source": "rag", "query": "responsabilidade civil"},
                {"source": "jurisprudencia", "query": "tema 1118 stf"},
            ],
            "max_results_per_source": 3,
            "consolidate": False,
        },
        ctx,
    )

    assert result["queries"] == 2
    assert len(result["results"]) == 2
    assert len(calls) == 2
    assert calls[0]["query"] == "responsabilidade civil"
    assert calls[1]["query"] == "tema 1118 stf"
    assert calls[0]["tenant_id"] == "tenant-1"
    assert calls[0]["processo_id"] == "case-1"
    assert calls[0]["top_k"] == 3


@pytest.mark.asyncio
async def test_init_ai_services_async_calls_mcp_initialize(monkeypatch):
    from app.services.ai.shared import startup as startup_module
    from app.services import mcp_hub as mcp_hub_module

    initialize_mock = AsyncMock(
        return_value={"servers_total": 1, "servers_ready": 1, "servers": []}
    )
    monkeypatch.setattr(mcp_hub_module.mcp_hub, "initialize", initialize_mock)

    startup_module._initialized = False
    try:
        await startup_module.init_ai_services_async(
            register_tools=False,
            init_mcp=True,
        )
    finally:
        startup_module._initialized = False

    initialize_mock.assert_awaited_once()
