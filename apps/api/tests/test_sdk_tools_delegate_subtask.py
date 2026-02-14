import json

import pytest

from app.services.ai.claude_agent import sdk_tools
from app.services.ai.shared.sse_protocol import done_event, token_event


def _parse_tool_text(response: dict) -> dict:
    text = response["content"][0]["text"]
    return json.loads(text)


@pytest.mark.asyncio
async def test_delegate_subtask_success_with_custom_tools(monkeypatch):
    class DummyAgentConfig:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class DummyExecutor:
        last_init_config = None
        last_load_kwargs = None
        last_run_kwargs = None

        def __init__(self, config=None, client=None):
            DummyExecutor.last_init_config = config

        def load_unified_tools(self, include_mcp=True, tool_names=None, execution_context=None):
            DummyExecutor.last_load_kwargs = {
                "include_mcp": include_mcp,
                "tool_names": tool_names,
                "execution_context": execution_context,
            }

        async def run(
            self,
            prompt: str,
            system_prompt: str = "",
            context=None,
            job_id=None,
            initial_messages=None,
            user_id=None,
            case_id=None,
            session_id=None,
            db=None,
        ):
            DummyExecutor.last_run_kwargs = {
                "prompt": prompt,
                "system_prompt": system_prompt,
                "context": context,
                "user_id": user_id,
                "case_id": case_id,
                "session_id": session_id,
            }
            yield token_event(job_id=job_id or "subjob", token="Parcial ")
            yield done_event(
                job_id=job_id or "subjob",
                final_text="Resposta final do subagente",
                metadata={"iterations": 2},
            )

    monkeypatch.setattr(
        "app.services.ai.claude_agent.executor.AgentConfig",
        DummyAgentConfig,
    )
    monkeypatch.setattr(
        "app.services.ai.claude_agent.executor.ClaudeAgentExecutor",
        DummyExecutor,
    )

    sdk_tools.set_iudex_tool_context(
        {
            "user_id": "user-1",
            "tenant_id": "tenant-1",
            "case_id": "case-9",
            "chat_id": "chat-7",
            "job_id": "job-11",
        }
    )

    response = await sdk_tools.delegate_subtask(
        {
            "task": "Resuma os pontos principais da petição",
            "model": "claude-haiku-4-5",
            "tool_names": "search_rag,search_legislacao",
            "max_tokens": 2048,
            "max_iterations": 4,
        }
    )
    payload = _parse_tool_text(response)

    assert payload["result"] == "Resposta final do subagente"
    assert payload["model"] == "claude-haiku-4-5"
    assert payload["max_tokens"] == 2048
    assert payload["max_iterations"] == 4
    assert payload["tool_names"] == ["search_rag", "search_legislacao"]
    assert payload["subagent_metadata"] == {"iterations": 2}

    assert DummyExecutor.last_load_kwargs is not None
    assert DummyExecutor.last_load_kwargs["include_mcp"] is False
    assert DummyExecutor.last_load_kwargs["tool_names"] == [
        "search_rag",
        "search_legislacao",
    ]
    exec_ctx = DummyExecutor.last_load_kwargs["execution_context"]
    assert exec_ctx.user_id == "user-1"
    assert exec_ctx.tenant_id == "tenant-1"
    assert exec_ctx.case_id == "case-9"

    assert DummyExecutor.last_run_kwargs is not None
    assert DummyExecutor.last_run_kwargs["prompt"] == "Resuma os pontos principais da petição"
    assert DummyExecutor.last_run_kwargs["user_id"] == "user-1"
    assert DummyExecutor.last_run_kwargs["case_id"] == "case-9"
    assert DummyExecutor.last_run_kwargs["session_id"] == "chat-7"


@pytest.mark.asyncio
async def test_delegate_subtask_requires_task():
    response = await sdk_tools.delegate_subtask({})
    payload = _parse_tool_text(response)
    assert payload["error"] == "task é obrigatória"


@pytest.mark.asyncio
async def test_delegate_subtask_rejects_non_claude_model():
    response = await sdk_tools.delegate_subtask(
        {"task": "Teste", "model": "gpt-5.2"}
    )
    payload = _parse_tool_text(response)
    assert "Somente modelos Claude" in payload["error"]


def test_sdk_tool_registry_includes_delegate_subtask():
    assert sdk_tools.delegate_subtask in sdk_tools._ALL_TOOLS
