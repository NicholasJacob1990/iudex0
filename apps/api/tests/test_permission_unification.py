from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.ai.shared.sse_protocol import SSEEventType


def _make_mock_response(
    *,
    text: str = "ok",
    stop_reason: str = "end_turn",
    tool_uses: list | None = None,
):
    content_blocks = []
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = text
    content_blocks.append(text_block)

    for tool in tool_uses or []:
        block = MagicMock()
        block.type = "tool_use"
        block.id = tool["id"]
        block.name = tool["name"]
        block.input = tool["input"]
        del block.text
        content_blocks.append(block)

    resp = MagicMock()
    resp.content = content_blocks
    resp.stop_reason = stop_reason
    resp.usage = SimpleNamespace(input_tokens=10, output_tokens=5)
    return resp


@pytest.mark.asyncio
async def test_raw_api_path_uses_permission_manager_for_tool_calls():
    from app.services.ai.claude_agent.executor import AgentConfig, ClaudeAgentExecutor

    tool_resp = _make_mock_response(
        text="vou chamar tool",
        stop_reason="tool_use",
        tool_uses=[
            {
                "id": "tool-1",
                "name": "search_rag",
                "input": {"query": "precedentes"},
            }
        ],
    )
    end_resp = _make_mock_response(text="fim", stop_reason="end_turn")

    async_client = AsyncMock()
    async_client.messages.create = AsyncMock(side_effect=[tool_resp, end_resp])

    executor = ClaudeAgentExecutor(
        config=AgentConfig(use_sdk=False, enable_thinking=False, enable_checkpoints=False, max_iterations=3),
        client=MagicMock(),
    )
    executor.async_client = async_client
    executor.register_tool(
        name="search_rag",
        description="Busca RAG",
        input_schema={"type": "object"},
        executor=AsyncMock(return_value={"ok": True}),
    )

    pm = SimpleNamespace(
        check=AsyncMock(return_value=SimpleNamespace(decision="deny")),
    )
    executor._permission_manager = pm

    events = [e async for e in executor._run_with_raw_api(prompt="teste", job_id="job-1")]

    pm.check.assert_awaited_once_with("search_rag", {"query": "precedentes"})
    tool_call = next(e for e in events if e.type == SSEEventType.TOOL_CALL)
    assert tool_call.data["permission_mode"] == "deny"


@pytest.mark.asyncio
async def test_sdk_path_uses_permission_manager_for_tool_calls(monkeypatch):
    from app.services.ai.claude_agent import executor as executor_module
    from app.services.ai.claude_agent.executor import AgentConfig, ClaudeAgentExecutor

    class DummyToolBlock:
        def __init__(self, *, name: str, tool_input: dict, tool_id: str):
            self.name = name
            self.input = tool_input
            self.id = tool_id

    class DummyTextBlock:
        def __init__(self, text: str):
            self.text = text

    class DummyAssistantMessage:
        def __init__(self, content):
            self.content = content

    class DummyResultMessage:
        def __init__(self, content):
            self.content = content

    class DummySystemMessage:
        def __init__(self, subtype=None, data=None):
            self.subtype = subtype
            self.data = data or {}

    class DummyOptions:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    async def fake_query(prompt: str, options: DummyOptions):
        yield DummySystemMessage(subtype="init", data={"session_id": "s-1"})
        yield DummyAssistantMessage(
            [
                DummyToolBlock(
                    name="mcp__iudex-legal__search_rag",
                    tool_input={"query": "jurisprudência"},
                    tool_id="sdk-tool-1",
                )
            ]
        )
        yield DummyResultMessage([DummyTextBlock("resultado sdk")])

    monkeypatch.setattr(executor_module, "query", fake_query, raising=False)
    monkeypatch.setattr(executor_module, "ClaudeAgentOptions", DummyOptions, raising=False)
    monkeypatch.setattr(executor_module, "AssistantMessage", DummyAssistantMessage, raising=False)
    monkeypatch.setattr(executor_module, "ResultMessage", DummyResultMessage, raising=False)
    monkeypatch.setattr(executor_module, "SystemMessage", DummySystemMessage, raising=False)
    monkeypatch.setattr(executor_module, "create_iudex_mcp_server", lambda: None, raising=False)
    monkeypatch.setattr(executor_module, "set_iudex_tool_context", lambda *_a, **_k: None, raising=False)
    monkeypatch.setattr(executor_module, "CLAUDE_SDK_AVAILABLE", True)

    executor = ClaudeAgentExecutor(
        config=AgentConfig(use_sdk=True, enable_thinking=False, enable_checkpoints=False),
        client=MagicMock(),
    )
    pm = SimpleNamespace(
        check=AsyncMock(return_value=SimpleNamespace(decision="ask")),
    )
    executor._permission_manager = pm

    events = [
        e
        async for e in executor._run_with_sdk(
            prompt="teste sdk",
            system_prompt="system",
            context=None,
            job_id="job-sdk",
            user_id=None,
            case_id=None,
            db=None,
        )
    ]

    pm.check.assert_awaited_once_with("mcp__iudex-legal__search_rag", {"query": "jurisprudência"})
    tool_call = next(e for e in events if e.type == SSEEventType.TOOL_CALL)
    assert tool_call.data["permission_mode"] == "ask"

