import json
from types import SimpleNamespace

import pytest

from app.services.ai import mcp_tools


def _openai_response_with_tool_call(
    *,
    tool_name: str,
    arguments: dict,
    call_id: str = "call-1",
):
    tool_call = SimpleNamespace(
        id=call_id,
        type="function",
        function=SimpleNamespace(
            name=tool_name,
            arguments=json.dumps(arguments, ensure_ascii=False),
        ),
    )
    message = SimpleNamespace(content="", tool_calls=[tool_call])
    choice = SimpleNamespace(message=message)
    return SimpleNamespace(choices=[choice])


def _openai_response_with_text(text: str):
    message = SimpleNamespace(content=text, tool_calls=None)
    choice = SimpleNamespace(message=message)
    return SimpleNamespace(choices=[choice])


class _DummyOpenAIClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self._idx = 0

        async def _create(**kwargs):
            if self._idx >= len(self._responses):
                raise AssertionError("No more mocked responses")
            response = self._responses[self._idx]
            self._idx += 1
            return response

        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=_create),
        )


@pytest.mark.asyncio
async def test_openai_mcp_loop_resolves_permission_for_nested_tool(monkeypatch):
    calls = []
    checks = []

    async def fake_execute_mcp_tool(tool_name, arguments, **kwargs):
        calls.append((tool_name, arguments))
        return {"ok": True}

    async def permission_checker(tool_name, tool_input):
        checks.append((tool_name, tool_input))
        return "allow"

    monkeypatch.setattr(
        "app.services.ai.mcp_tools.execute_mcp_tool",
        fake_execute_mcp_tool,
    )

    client = _DummyOpenAIClient(
        [
            _openai_response_with_tool_call(
                tool_name=mcp_tools.MCP_TOOL_CALL_NAME,
                arguments={
                    "server_label": "srv",
                    "tool_name": "search_jurisprudencia",
                    "arguments": {"query": "precedente vinculante"},
                },
            ),
            _openai_response_with_text("resposta final"),
        ]
    )

    text, trace = await mcp_tools.run_openai_tool_loop(
        client=client,
        model="gpt-5.2",
        system_instruction="system",
        user_prompt="prompt",
        max_tokens=512,
        temperature=0.1,
        permission_checker=permission_checker,
    )

    assert text == "resposta final"
    assert checks == [("search_jurisprudencia", {"query": "precedente vinculante"})]
    assert calls == [
        (
            mcp_tools.MCP_TOOL_CALL_NAME,
            {
                "server_label": "srv",
                "tool_name": "search_jurisprudencia",
                "arguments": {"query": "precedente vinculante"},
            },
        )
    ]
    assert trace[0]["permission_mode"] == "allow"
    assert trace[0]["blocked"] is False


@pytest.mark.asyncio
async def test_openai_mcp_loop_blocks_when_permission_is_ask(monkeypatch):
    executed = False

    async def fake_execute_mcp_tool(tool_name, arguments, **kwargs):
        nonlocal executed
        executed = True
        return {"ok": True}

    async def permission_checker(tool_name, tool_input):
        return "ask"

    monkeypatch.setattr(
        "app.services.ai.mcp_tools.execute_mcp_tool",
        fake_execute_mcp_tool,
    )

    client = _DummyOpenAIClient(
        [
            _openai_response_with_tool_call(
                tool_name=mcp_tools.MCP_TOOL_CALL_NAME,
                arguments={
                    "server_label": "srv",
                    "tool_name": "buscar_publicacoes_djen",
                    "arguments": {"numero_processo": "123"},
                },
            ),
            _openai_response_with_text("sem tools"),
        ]
    )

    text, trace = await mcp_tools.run_openai_tool_loop(
        client=client,
        model="gpt-5.2",
        system_instruction="system",
        user_prompt="prompt",
        max_tokens=512,
        temperature=0.1,
        permission_checker=permission_checker,
    )

    assert text == "sem tools"
    assert executed is False
    assert trace[0]["permission_mode"] == "ask"
    assert trace[0]["blocked"] is True
    assert "requires approval" in trace[0]["result_preview"]


@pytest.mark.asyncio
async def test_openai_mcp_loop_blocks_when_permission_is_deny(monkeypatch):
    executed = False
    checked = []

    async def fake_execute_mcp_tool(tool_name, arguments, **kwargs):
        nonlocal executed
        executed = True
        return {"ok": True}

    async def permission_checker(tool_name, tool_input):
        checked.append((tool_name, tool_input))
        return "deny"

    monkeypatch.setattr(
        "app.services.ai.mcp_tools.execute_mcp_tool",
        fake_execute_mcp_tool,
    )

    client = _DummyOpenAIClient(
        [
            _openai_response_with_tool_call(
                tool_name=mcp_tools.MCP_TOOL_SEARCH_NAME,
                arguments={"query": "djen", "limit": 3},
            ),
            _openai_response_with_text("ok"),
        ]
    )

    text, trace = await mcp_tools.run_openai_tool_loop(
        client=client,
        model="gpt-5.2",
        system_instruction="system",
        user_prompt="prompt",
        max_tokens=512,
        temperature=0.1,
        permission_checker=permission_checker,
    )

    assert text == "ok"
    assert executed is False
    assert checked == [(mcp_tools.MCP_TOOL_SEARCH_NAME, {"query": "djen", "limit": 3})]
    assert trace[0]["permission_mode"] == "deny"
    assert trace[0]["blocked"] is True
    assert "denied by permission policy" in trace[0]["result_preview"]
