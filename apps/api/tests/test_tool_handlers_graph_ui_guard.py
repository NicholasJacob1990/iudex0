import pytest

from app.services.ai.shared.tool_handlers import ToolExecutionContext, ToolHandlers


@pytest.mark.asyncio
async def test_ask_graph_blocks_writes_in_graph_ui_mode():
    handlers = ToolHandlers()
    ctx = ToolExecutionContext(
        user_id="u1",
        tenant_id="t1",
        services={"extra_instructions": "MODO GRAFO (UI)"},
    )
    res = await handlers.handle_ask_graph(
        {"operation": "link_entities", "params": {"source_id": "a", "target_id": "b"}},
        ctx,
    )
    assert res.get("success") is False
    assert "bloqueada" in (res.get("error") or "").lower()

