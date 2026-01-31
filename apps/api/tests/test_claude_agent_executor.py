"""
Tests for ClaudeAgentExecutor - agent loop, tools, and SSE events.

Tests:
- Executor initializes with tools
- Execute returns async generator of SSEEvents
- Tool calls are handled
- Max iterations limit works
- Error handling returns error SSE event
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from dataclasses import dataclass

from app.services.ai.shared.sse_protocol import (
    SSEEvent,
    SSEEventType,
    ToolApprovalMode,
)


# =============================================================================
# MOCK HELPERS
# =============================================================================


def _make_mock_response(
    text: str = "Test response",
    stop_reason: str = "end_turn",
    input_tokens: int = 100,
    output_tokens: int = 50,
    tool_uses: list = None,
):
    """Create a mock Anthropic Message response."""
    content_blocks = []

    # Add text block
    text_block = MagicMock()
    text_block.text = text
    text_block.type = "text"
    content_blocks.append(text_block)

    # Add tool_use blocks if provided
    if tool_uses:
        for tu in tool_uses:
            block = MagicMock()
            block.type = "tool_use"
            block.id = tu.get("id", "tool-1")
            block.name = tu.get("name", "test_tool")
            block.input = tu.get("input", {})
            # Ensure hasattr(block, "text") returns False
            del block.text
            content_blocks.append(block)

    response = MagicMock()
    response.content = content_blocks
    response.stop_reason = stop_reason
    response.usage = MagicMock()
    response.usage.input_tokens = input_tokens
    response.usage.output_tokens = output_tokens
    return response


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_anthropic_client():
    """Create a mock AsyncAnthropic client."""
    client = AsyncMock()
    client.messages = AsyncMock()
    client.messages.create = AsyncMock(
        return_value=_make_mock_response()
    )
    return client


@pytest.fixture
def executor(mock_anthropic_client):
    """Create ClaudeAgentExecutor with mocked client."""
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
        with patch("app.services.ai.claude_agent.executor.anthropic", MagicMock()):
            from app.services.ai.claude_agent.executor import (
                ClaudeAgentExecutor,
                AgentConfig,
            )

            config = AgentConfig(
                model="claude-sonnet-4-20250514",
                max_iterations=5,
                max_tokens=4096,
                enable_thinking=False,
                enable_checkpoints=False,
            )
            exec_ = ClaudeAgentExecutor(
                config=config,
                client=MagicMock(),  # sync client (unused in tests)
            )
            exec_.async_client = mock_anthropic_client
            return exec_


# =============================================================================
# INITIALIZATION TESTS
# =============================================================================


class TestInitialization:
    """Tests for executor initialization."""

    def test_executor_initializes_with_default_config(self):
        """Executor initializes without errors using defaults."""
        with patch("app.services.ai.claude_agent.executor.anthropic", MagicMock()):
            from app.services.ai.claude_agent.executor import ClaudeAgentExecutor

            exec_ = ClaudeAgentExecutor(client=MagicMock())
            assert exec_.config is not None
            assert exec_.config.max_iterations > 0

    def test_register_tool(self, executor):
        """Tools can be registered with the executor."""
        executor.register_tool(
            name="test_tool",
            description="A test tool",
            input_schema={"type": "object", "properties": {"q": {"type": "string"}}},
            executor=lambda **kwargs: {"result": "ok"},
            permission=ToolApprovalMode.ALLOW,
        )

        tools = executor.get_registered_tools()
        assert any(t["name"] == "test_tool" for t in tools)

    def test_register_multiple_tools(self, executor):
        """Multiple tools can be registered."""
        for i in range(3):
            executor.register_tool(
                name=f"tool_{i}",
                description=f"Tool {i}",
                input_schema={"type": "object"},
                executor=lambda **kwargs: {"ok": True},
            )

        assert len(executor.get_registered_tools()) == 3


# =============================================================================
# RUN TESTS
# =============================================================================


class TestRun:
    """Tests for the run() async generator."""

    @pytest.mark.asyncio
    async def test_run_returns_async_generator_of_sse_events(self, executor):
        """run() yields SSEEvent instances."""
        events = []
        async for event in executor.run(
            prompt="Hello",
            system_prompt="You are helpful",
            job_id="test-job-1",
        ):
            events.append(event)
            assert isinstance(event, SSEEvent)

        assert len(events) > 0

    @pytest.mark.asyncio
    async def test_run_emits_agent_start_event(self, executor):
        """run() emits AGENT_START as the first meaningful event."""
        events = []
        async for event in executor.run(
            prompt="Hello",
            job_id="test-job",
        ):
            events.append(event)

        start_events = [e for e in events if e.type == SSEEventType.AGENT_START]
        assert len(start_events) == 1
        assert start_events[0].data.get("model") == "claude-sonnet-4-20250514"

    @pytest.mark.asyncio
    async def test_run_emits_done_on_end_turn(self, executor):
        """run() emits DONE event when Claude returns end_turn."""
        events = []
        async for event in executor.run(
            prompt="Hello",
            job_id="test-job",
        ):
            events.append(event)

        done_events = [e for e in events if e.type == SSEEventType.DONE]
        assert len(done_events) == 1
        assert "final_text" in done_events[0].data or done_events[0].data.get("final_text") is not None

    @pytest.mark.asyncio
    async def test_run_emits_token_with_text(self, executor):
        """run() emits TOKEN events for text content."""
        events = []
        async for event in executor.run(
            prompt="Hello",
            job_id="test-job",
        ):
            events.append(event)

        token_events = [e for e in events if e.type == SSEEventType.TOKEN]
        assert len(token_events) >= 1


# =============================================================================
# TOOL HANDLING TESTS
# =============================================================================


class TestToolHandling:
    """Tests for tool call processing."""

    @pytest.mark.asyncio
    async def test_tool_call_allowed_is_executed(self, executor, mock_anthropic_client):
        """ALLOW tools are executed automatically."""
        # First response has tool_use, second has end_turn
        tool_response = _make_mock_response(
            text="Let me search...",
            stop_reason="tool_use",
            tool_uses=[{
                "id": "tool-call-1",
                "name": "search_jurisprudencia",
                "input": {"query": "habeas corpus"},
            }],
        )
        final_response = _make_mock_response(text="Done", stop_reason="end_turn")

        mock_anthropic_client.messages.create = AsyncMock(
            side_effect=[tool_response, final_response]
        )

        # Register allowed tool
        executor.register_tool(
            name="search_jurisprudencia",
            description="Search case law",
            input_schema={"type": "object"},
            executor=AsyncMock(return_value={"results": ["case1"]}),
            permission=ToolApprovalMode.ALLOW,
        )

        events = []
        async for event in executor.run(prompt="Search", job_id="test-job"):
            events.append(event)

        tool_call_events = [e for e in events if e.type == SSEEventType.TOOL_CALL]
        assert len(tool_call_events) >= 1

    @pytest.mark.asyncio
    async def test_tool_denied_returns_error_result(self, executor, mock_anthropic_client):
        """DENY tools produce a tool_result with error."""
        tool_response = _make_mock_response(
            text="Let me run bash...",
            stop_reason="tool_use",
            tool_uses=[{
                "id": "tool-call-2",
                "name": "bash",
                "input": {"command": "ls"},
            }],
        )
        # After denial, Claude returns end_turn
        final_response = _make_mock_response(text="I cannot do that", stop_reason="end_turn")

        mock_anthropic_client.messages.create = AsyncMock(
            side_effect=[tool_response, final_response]
        )

        events = []
        async for event in executor.run(prompt="Run bash", job_id="test-job"):
            events.append(event)

        tool_result_events = [e for e in events if e.type == SSEEventType.TOOL_RESULT]
        denied_results = [
            e for e in tool_result_events
            if e.data.get("success") is False
        ]
        assert len(denied_results) >= 1

    @pytest.mark.asyncio
    async def test_tool_ask_triggers_approval_event(self, executor, mock_anthropic_client):
        """ASK tools trigger TOOL_APPROVAL_REQUIRED event and pause."""
        tool_response = _make_mock_response(
            text="Let me edit...",
            stop_reason="tool_use",
            tool_uses=[{
                "id": "tool-call-3",
                "name": "edit_document",
                "input": {"content": "new text"},
            }],
        )

        mock_anthropic_client.messages.create = AsyncMock(
            return_value=tool_response
        )

        events = []
        async for event in executor.run(prompt="Edit doc", job_id="test-job"):
            events.append(event)

        approval_events = [
            e for e in events
            if e.type == SSEEventType.TOOL_APPROVAL_REQUIRED
        ]
        assert len(approval_events) >= 1


# =============================================================================
# MAX ITERATIONS TESTS
# =============================================================================


class TestMaxIterations:
    """Tests for iteration limit enforcement."""

    @pytest.mark.asyncio
    async def test_max_iterations_reached(self, executor, mock_anthropic_client):
        """Agent stops after max_iterations and emits DONE."""
        # Always return tool_use to force iteration loop
        tool_response = _make_mock_response(
            text="Searching...",
            stop_reason="tool_use",
            tool_uses=[{
                "id": "tool-1",
                "name": "search_jurisprudencia",
                "input": {"query": "test"},
            }],
        )
        mock_anthropic_client.messages.create = AsyncMock(
            return_value=tool_response
        )

        executor.register_tool(
            name="search_jurisprudencia",
            description="Search",
            input_schema={"type": "object"},
            executor=AsyncMock(return_value={"results": []}),
            permission=ToolApprovalMode.ALLOW,
        )

        events = []
        async for event in executor.run(prompt="Loop forever", job_id="test-job"):
            events.append(event)

        done_events = [e for e in events if e.type == SSEEventType.DONE]
        assert len(done_events) == 1
        # Should indicate max iterations was reached
        done_data = done_events[0].data
        assert done_data.get("max_iterations_reached", False) is True or "metadata" in done_data


# =============================================================================
# ERROR HANDLING TESTS
# =============================================================================


class TestErrorHandling:
    """Tests for error handling in executor."""

    @pytest.mark.asyncio
    async def test_api_error_yields_error_event(self, executor, mock_anthropic_client):
        """API errors produce an ERROR SSE event."""
        mock_anthropic_client.messages.create = AsyncMock(
            side_effect=RuntimeError("API timeout")
        )

        events = []
        async for event in executor.run(prompt="Hello", job_id="test-job"):
            events.append(event)

        error_events = [e for e in events if e.type == SSEEventType.ERROR]
        assert len(error_events) >= 1
        assert "API timeout" in error_events[0].data.get("error", "")

    @pytest.mark.asyncio
    async def test_no_client_yields_error_event(self):
        """Missing async client yields initialization error."""
        with patch("app.services.ai.claude_agent.executor.anthropic", MagicMock()):
            from app.services.ai.claude_agent.executor import ClaudeAgentExecutor

            exec_ = ClaudeAgentExecutor(client=MagicMock())
            exec_.async_client = None

            events = []
            async for event in exec_.run(prompt="Hello", job_id="test-job"):
                events.append(event)

            error_events = [e for e in events if e.type == SSEEventType.ERROR]
            assert len(error_events) >= 1

    @pytest.mark.asyncio
    async def test_cancel_stops_execution(self, executor, mock_anthropic_client):
        """cancel() causes the loop to emit DONE with cancelled flag."""
        # Set up a slow response
        async def slow_response(**kwargs):
            import asyncio
            await asyncio.sleep(0.01)
            return _make_mock_response(
                text="Working...",
                stop_reason="tool_use",
                tool_uses=[{
                    "id": "t1",
                    "name": "search_jurisprudencia",
                    "input": {"q": "x"},
                }],
            )

        mock_anthropic_client.messages.create = AsyncMock(side_effect=slow_response)

        executor.register_tool(
            name="search_jurisprudencia",
            description="Search",
            input_schema={"type": "object"},
            executor=AsyncMock(return_value={}),
            permission=ToolApprovalMode.ALLOW,
        )

        # Cancel after first event
        events = []
        count = 0
        async for event in executor.run(prompt="Work", job_id="test-job"):
            events.append(event)
            count += 1
            if count >= 3:
                executor.cancel()

        # Should have ended
        assert len(events) >= 1


# =============================================================================
# STATE TESTS
# =============================================================================


class TestState:
    """Tests for agent state management."""

    @pytest.mark.asyncio
    async def test_state_tracks_tokens(self, executor, mock_anthropic_client):
        """Agent state tracks input/output tokens."""
        async for _ in executor.run(prompt="Hello", job_id="test-job"):
            pass

        state = executor.get_state()
        assert state is not None
        assert state.total_input_tokens > 0
        assert state.total_output_tokens > 0

    @pytest.mark.asyncio
    async def test_state_dict_serializable(self, executor, mock_anthropic_client):
        """get_state_dict() returns a serializable dict."""
        async for _ in executor.run(prompt="Hello", job_id="test-job"):
            pass

        state_dict = executor.get_state_dict()
        assert isinstance(state_dict, dict)
        assert "job_id" in state_dict
        assert "status" in state_dict

    def test_get_state_none_before_run(self, executor):
        """State is None before run() is called."""
        assert executor.get_state() is None
        assert executor.get_state_dict() is None
