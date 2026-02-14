from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_mock_response():
    response = MagicMock()
    response.content = []
    response.stop_reason = "end_turn"
    response.usage = MagicMock()
    response.usage.input_tokens = 10
    response.usage.output_tokens = 5
    return response


def _make_executor(*, enable_prompt_caching: bool):
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
        with patch("app.services.ai.claude_agent.executor.anthropic", MagicMock()):
            from app.services.ai.claude_agent.executor import AgentConfig, ClaudeAgentExecutor

            config = AgentConfig(
                model="claude-sonnet-4-5",
                max_iterations=2,
                max_tokens=512,
                enable_thinking=False,
                enable_code_execution=False,
                enable_prompt_caching=enable_prompt_caching,
                enable_checkpoints=False,
            )
            executor = ClaudeAgentExecutor(config=config, client=MagicMock())
            mock_client = AsyncMock()
            mock_client.messages = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=_make_mock_response())
            executor.async_client = mock_client
            return executor, mock_client


@pytest.mark.asyncio
async def test_call_claude_uses_cache_control_blocks_for_base_and_context():
    executor, mock_client = _make_executor(enable_prompt_caching=True)

    full_system_prompt = executor._build_system_prompt("BASE PROMPT", "CONTEXTO RAG")
    await executor._call_claude(
        messages=[{"role": "user", "content": "Teste"}],
        system_prompt=full_system_prompt,
    )

    kwargs = mock_client.messages.create.await_args.kwargs
    assert isinstance(kwargs["system"], list)
    assert len(kwargs["system"]) == 2

    base_block = kwargs["system"][0]
    context_block = kwargs["system"][1]

    assert base_block["type"] == "text"
    assert base_block["text"] == "BASE PROMPT"
    assert base_block["cache_control"] == {"type": "ephemeral"}

    assert context_block["type"] == "text"
    assert context_block["text"] == "## CONTEXTO DISPONÍVEL\n\nCONTEXTO RAG"
    assert context_block["cache_control"] == {"type": "ephemeral"}


@pytest.mark.asyncio
async def test_call_claude_keeps_string_system_when_prompt_caching_disabled():
    executor, mock_client = _make_executor(enable_prompt_caching=False)

    full_system_prompt = executor._build_system_prompt("BASE PROMPT", "CONTEXTO RAG")
    await executor._call_claude(
        messages=[{"role": "user", "content": "Teste"}],
        system_prompt=full_system_prompt,
    )

    kwargs = mock_client.messages.create.await_args.kwargs
    assert isinstance(kwargs["system"], str)
    assert "BASE PROMPT" in kwargs["system"]
    assert "CONTEXTO RAG" in kwargs["system"]
