import json

import pytest

from app.services.ai.claude_agent import sdk_tools
from app.services.ai.shared.tool_handlers import ToolHandlers
from app.services.ai.shared.unified_tools import TOOLS_BY_NAME, ToolRiskLevel


def test_unified_tools_include_search_jusbrasil():
    tool = TOOLS_BY_NAME.get("search_jusbrasil")
    assert tool is not None
    assert tool.risk_level == ToolRiskLevel.LOW


@pytest.mark.asyncio
async def test_tool_handler_search_jusbrasil(monkeypatch):
    async def _fake_search(**kwargs):
        assert kwargs["query"] == "dano moral"
        assert kwargs["tribunal"] == "STJ"
        return {
            "success": True,
            "query": kwargs["query"],
            "results": [{"title": "REsp 1.234.567", "url": "https://www.jusbrasil.com.br/teste"}],
            "total": 1,
            "source": "jusbrasil_api",
        }

    from app.services import jusbrasil_service as service_module

    monkeypatch.setattr(service_module.jusbrasil_service, "search", _fake_search)

    handlers = ToolHandlers()
    result = await handlers.handle_search_jusbrasil(
        {"query": "dano moral", "tribunal": "STJ", "max_results": 5}
    )

    assert result["success"] is True
    assert result["total"] == 1
    assert result["results"][0]["title"] == "REsp 1.234.567"


@pytest.mark.asyncio
async def test_sdk_search_jusbrasil_tool(monkeypatch):
    async def _fake_search(**kwargs):
        return {
            "success": True,
            "query": kwargs["query"],
            "results": [{"title": "Resultado JusBrasil"}],
            "total": 1,
            "source": "jusbrasil_api",
        }

    from app.services import jusbrasil_service as service_module

    monkeypatch.setattr(service_module.jusbrasil_service, "search", _fake_search)

    response = await sdk_tools.search_jusbrasil({"query": "precedente vinculante"})
    payload = json.loads(response["content"][0]["text"])

    assert payload["success"] is True
    assert payload["total"] == 1
    assert sdk_tools.search_jusbrasil in sdk_tools._ALL_TOOLS

