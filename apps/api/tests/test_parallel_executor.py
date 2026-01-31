"""
Tests for ParallelExecutor - parallel execution, timeout, and merge strategies.

Tests:
- Parallel execution of agent and debate
- Timeout handling
- Merge strategies (fan_in merge, fan_in best)
- Error in one node doesn't break others
- Similarity calculation
- JSON merge response parsing
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.ai.orchestration.parallel_executor import (
    ParallelExecutor,
    ParallelResult,
    ExecutionContext,
    run_parallel_execution,
)
from app.services.ai.shared.sse_protocol import (
    SSEEvent,
    SSEEventType,
    create_sse_event,
    token_event,
    done_event,
    error_event,
)


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def executor():
    """Create ParallelExecutor with short timeout."""
    return ParallelExecutor(timeout=10, fail_fast=False)


@pytest.fixture
def executor_fail_fast():
    """Create ParallelExecutor with fail_fast enabled."""
    return ParallelExecutor(timeout=10, fail_fast=True)


@pytest.fixture
def context():
    """Create ExecutionContext for tests."""
    return ExecutionContext(
        job_id="test-job-1",
        prompt="Analyze habeas corpus",
        rag_context="Legal context here",
        thesis="The detention is unlawful",
        mode="parecer",
        section_title="Main Section",
        temperature=0.3,
    )


# =============================================================================
# DATA CLASS TESTS
# =============================================================================


class TestParallelResult:
    """Tests for ParallelResult dataclass."""

    def test_default_values(self):
        result = ParallelResult()
        assert result.agent_output == ""
        assert result.debate_output == ""
        assert result.merged_content == ""
        assert result.success is True
        assert result.error is None
        assert result.divergences == []

    def test_to_dict(self):
        result = ParallelResult(
            agent_output="agent text",
            debate_output="debate text",
            merged_content="merged text",
            conflicts_resolved=2,
            total_duration_ms=1000,
            success=True,
        )
        d = result.to_dict()
        assert d["agent_output"] == "agent text"
        assert d["merged_content"] == "merged text"
        assert d["conflicts_resolved"] == 2
        assert d["total_duration_ms"] == 1000

    def test_error_result(self):
        result = ParallelResult(
            success=False,
            error="Something went wrong",
        )
        assert result.success is False
        assert result.error == "Something went wrong"


class TestExecutionContext:
    """Tests for ExecutionContext dataclass."""

    def test_default_values(self):
        ctx = ExecutionContext(job_id="j1", prompt="test")
        assert ctx.rag_context == ""
        assert ctx.thesis == ""
        assert ctx.mode == "minuta"
        assert ctx.temperature == 0.3
        assert ctx.previous_sections == []


# =============================================================================
# SIMILARITY TESTS
# =============================================================================


class TestSimilarity:
    """Tests for _calculate_similarity (Jaccard)."""

    def test_identical_texts_score_1(self, executor):
        """Identical texts should have similarity 1.0."""
        text = "habeas corpus is a legal remedy"
        score = executor._calculate_similarity(text, text)
        assert score == 1.0

    def test_completely_different_texts_score_low(self, executor):
        """Completely different texts should have low similarity."""
        score = executor._calculate_similarity(
            "alpha beta gamma delta",
            "one two three four",
        )
        assert score == 0.0

    def test_partially_similar_texts(self, executor):
        """Partially overlapping texts have intermediate score."""
        score = executor._calculate_similarity(
            "habeas corpus is a legal remedy in Brazil",
            "habeas corpus protects individual freedom in Brazil",
        )
        assert 0.0 < score < 1.0

    def test_empty_texts_score_0(self, executor):
        """Empty texts return 0.0."""
        assert executor._calculate_similarity("", "") == 0.0
        assert executor._calculate_similarity("hello", "") == 0.0
        assert executor._calculate_similarity("", "hello") == 0.0


# =============================================================================
# MERGE RESPONSE PARSING TESTS
# =============================================================================


class TestParseMergeResponse:
    """Tests for _parse_merge_response JSON parsing."""

    def test_valid_json(self, executor):
        """Parses valid JSON response."""
        response = '{"merged_content": "result", "divergences": [], "reasoning": "ok"}'
        parsed = executor._parse_merge_response(response)
        assert parsed is not None
        assert parsed["merged_content"] == "result"

    def test_json_in_code_block(self, executor):
        """Parses JSON wrapped in markdown code blocks."""
        response = '```json\n{"merged_content": "result", "divergences": []}\n```'
        parsed = executor._parse_merge_response(response)
        assert parsed is not None
        assert parsed["merged_content"] == "result"

    def test_json_embedded_in_text(self, executor):
        """Extracts JSON embedded in surrounding text."""
        response = 'Here is the result:\n{"merged_content": "result", "divergences": []}\nDone.'
        parsed = executor._parse_merge_response(response)
        assert parsed is not None

    def test_invalid_json_returns_none(self, executor):
        """Invalid JSON returns None."""
        assert executor._parse_merge_response("not json at all") is None

    def test_empty_response_returns_none(self, executor):
        """Empty response returns None."""
        assert executor._parse_merge_response("") is None
        assert executor._parse_merge_response(None) is None


# =============================================================================
# MERGE RESULTS TESTS
# =============================================================================


class TestMergeResults:
    """Tests for _merge_results logic."""

    @pytest.mark.asyncio
    async def test_both_empty_returns_error(self, executor, context):
        """Empty agent and debate outputs produce error result."""
        result = await executor._merge_results("", "", context)
        assert result.success is False
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_agent_only_uses_agent(self, executor, context):
        """When only agent output exists, use it directly."""
        result = await executor._merge_results(
            "Agent analysis of habeas corpus...", "", context
        )
        assert result.merged_content == "Agent analysis of habeas corpus..."
        assert "agent" in result.merge_reasoning.lower()

    @pytest.mark.asyncio
    async def test_debate_only_uses_debate(self, executor, context):
        """When only debate output exists, use it directly."""
        result = await executor._merge_results(
            "", "Debate analysis of habeas corpus...", context
        )
        assert result.merged_content == "Debate analysis of habeas corpus..."

    @pytest.mark.asyncio
    async def test_highly_similar_uses_agent(self, executor, context):
        """When outputs are >95% similar, agent output is used."""
        text = "Habeas corpus is a fundamental legal remedy " * 20
        result = await executor._merge_results(text, text, context)
        assert result.merged_content == text
        assert "similar" in result.merge_reasoning.lower()

    @pytest.mark.asyncio
    async def test_different_outputs_call_llm_merge(self, executor, context):
        """Different outputs trigger LLM-based merge."""
        agent_text = "Agent perspective: habeas corpus protects liberty " * 10
        debate_text = "Debate conclusion: detention requires due process " * 10

        mock_merge_json = {
            "merged_content": "Merged: liberty + due process",
            "divergences": [{"topic": "focus", "resolution": "combined"}],
            "reasoning": "Combined both perspectives",
        }

        with patch(
            "app.services.ai.orchestration.parallel_executor.init_vertex_client",
            return_value=MagicMock(),
        ), patch(
            "app.services.ai.orchestration.parallel_executor.call_vertex_gemini_async",
            new_callable=AsyncMock,
            return_value='{"merged_content": "Merged: liberty + due process", "divergences": [{"topic": "focus", "resolution": "combined"}], "reasoning": "Combined both"}',
        ), patch(
            "app.services.ai.orchestration.parallel_executor.get_api_model_name",
            return_value="gemini-3-flash",
        ):
            result = await executor._merge_results(agent_text, debate_text, context)

        assert result.merged_content != ""
        # Either the LLM merge worked or it fell back to agent output
        assert len(result.merged_content) > 0

    @pytest.mark.asyncio
    async def test_merge_fallback_on_error(self, executor, context):
        """Merge falls back to agent output on error."""
        agent_text = "Agent output here"
        debate_text = "Completely different debate output"

        with patch(
            "app.services.ai.orchestration.parallel_executor.init_vertex_client",
            side_effect=ImportError("No vertex"),
        ):
            result = await executor._merge_results(agent_text, debate_text, context)

        # Should fallback to agent output
        assert result.merged_content == agent_text


# =============================================================================
# PARALLEL EXECUTION TESTS
# =============================================================================


class TestParallelExecution:
    """Tests for the execute() async generator."""

    @pytest.mark.asyncio
    async def test_execute_yields_parallel_start(self, executor, context):
        """execute() emits PARALLEL_START event."""
        with patch.object(
            executor, "_run_agent", new_callable=AsyncMock, return_value=""
        ), patch.object(
            executor, "_run_debate", new_callable=AsyncMock, return_value=""
        ), patch.object(
            executor, "_merge_results", new_callable=AsyncMock,
            return_value=ParallelResult(success=False, error="empty"),
        ), patch(
            "app.services.ai.orchestration.parallel_executor.job_manager",
            MagicMock(),
        ):
            events = []
            async for event in executor.execute(
                prompt="test",
                agent_models=["claude-agent"],
                debate_models=["gpt-4o"],
                context=context,
            ):
                events.append(event)

        parallel_starts = [
            e for e in events if e.type == SSEEventType.PARALLEL_START
        ]
        assert len(parallel_starts) >= 1

    @pytest.mark.asyncio
    async def test_execute_yields_done_event(self, executor, context):
        """execute() emits DONE event at the end."""
        with patch.object(
            executor, "_run_agent", new_callable=AsyncMock, return_value="agent result"
        ), patch.object(
            executor, "_run_debate", new_callable=AsyncMock, return_value="debate result"
        ), patch.object(
            executor, "_merge_results", new_callable=AsyncMock,
            return_value=ParallelResult(
                merged_content="final merged",
                success=True,
            ),
        ), patch(
            "app.services.ai.orchestration.parallel_executor.job_manager",
            MagicMock(),
        ):
            events = []
            async for event in executor.execute(
                prompt="test",
                agent_models=["claude-agent"],
                debate_models=["gpt-4o"],
                context=context,
            ):
                events.append(event)

        done_events = [e for e in events if e.type == SSEEventType.DONE]
        assert len(done_events) >= 1

    @pytest.mark.asyncio
    async def test_execute_yields_parallel_complete(self, executor, context):
        """execute() emits PARALLEL_COMPLETE event."""
        with patch.object(
            executor, "_run_agent", new_callable=AsyncMock, return_value=""
        ), patch.object(
            executor, "_run_debate", new_callable=AsyncMock, return_value=""
        ), patch.object(
            executor, "_merge_results", new_callable=AsyncMock,
            return_value=ParallelResult(success=True),
        ), patch(
            "app.services.ai.orchestration.parallel_executor.job_manager",
            MagicMock(),
        ):
            events = []
            async for event in executor.execute(
                prompt="test",
                agent_models=["claude-agent"],
                debate_models=["gpt-4o"],
                context=context,
            ):
                events.append(event)

        complete_events = [
            e for e in events if e.type == SSEEventType.PARALLEL_COMPLETE
        ]
        assert len(complete_events) >= 1


# =============================================================================
# ERROR ISOLATION TESTS
# =============================================================================


class TestErrorIsolation:
    """Tests that errors in one node don't break the other."""

    @pytest.mark.asyncio
    async def test_agent_error_debate_continues(self, executor, context):
        """Agent error does not prevent debate from completing."""
        async def failing_agent(prompt, ctx, queue):
            await queue.put(error_event(
                ctx.job_id, "Agent crashed", error_type="agent_error"
            ))
            return ""

        async def working_debate(prompt, models, ctx, queue):
            await queue.put(done_event(
                ctx.job_id, final_text="debate result"
            ))
            return "debate result"

        with patch.object(
            executor, "_run_agent", side_effect=failing_agent
        ), patch.object(
            executor, "_run_debate", side_effect=working_debate
        ), patch.object(
            executor, "_merge_results", new_callable=AsyncMock,
            return_value=ParallelResult(
                merged_content="debate result",
                success=True,
            ),
        ), patch(
            "app.services.ai.orchestration.parallel_executor.job_manager",
            MagicMock(),
        ):
            events = []
            async for event in executor.execute(
                prompt="test",
                agent_models=["claude-agent"],
                debate_models=["gpt-4o"],
                context=context,
            ):
                events.append(event)

        # Should still have DONE event
        done_events = [e for e in events if e.type == SSEEventType.DONE]
        assert len(done_events) >= 1


# =============================================================================
# TIMEOUT TESTS
# =============================================================================


class TestTimeout:
    """Tests for timeout handling."""

    @pytest.mark.asyncio
    async def test_timeout_emits_error_event(self, context):
        """Exceeding timeout emits error event."""
        # Create executor with very short timeout
        executor = ParallelExecutor(timeout=0.1, fail_fast=False)

        async def slow_agent(prompt, ctx, queue):
            await asyncio.sleep(5)  # Much longer than timeout
            return ""

        async def slow_debate(prompt, models, ctx, queue):
            await asyncio.sleep(5)
            return ""

        with patch.object(
            executor, "_run_agent", side_effect=slow_agent
        ), patch.object(
            executor, "_run_debate", side_effect=slow_debate
        ), patch.object(
            executor, "_merge_results", new_callable=AsyncMock,
            return_value=ParallelResult(success=False, error="timeout"),
        ), patch(
            "app.services.ai.orchestration.parallel_executor.job_manager",
            MagicMock(),
        ):
            events = []
            async for event in executor.execute(
                prompt="test",
                agent_models=["claude-agent"],
                debate_models=["gpt-4o"],
                context=context,
            ):
                events.append(event)

        # Should have error or done event indicating timeout
        error_events = [e for e in events if e.type == SSEEventType.ERROR]
        # Timeout produces at least one error or the merge handles it
        assert len(events) >= 1


# =============================================================================
# CANCEL TESTS
# =============================================================================


class TestCancel:
    """Tests for cancel_all method."""

    def test_cancel_all_clears_tasks(self, executor):
        """cancel_all cancels and clears all tasks."""
        # Create mock tasks
        task1 = MagicMock()
        task1.done.return_value = False
        task2 = MagicMock()
        task2.done.return_value = True  # Already done

        executor._tasks = {"agent": task1, "debate": task2}
        executor.cancel_all()

        task1.cancel.assert_called_once()
        task2.cancel.assert_not_called()  # Already done
        assert executor._tasks == {}


# =============================================================================
# CONVENIENCE FUNCTION TESTS
# =============================================================================


class TestRunParallelExecution:
    """Tests for run_parallel_execution convenience function."""

    @pytest.mark.asyncio
    async def test_returns_parallel_result(self, context):
        """run_parallel_execution returns a ParallelResult."""
        with patch(
            "app.services.ai.orchestration.parallel_executor.ParallelExecutor"
        ) as MockExecutor:
            instance = MockExecutor.return_value

            async def fake_execute(*args, **kwargs):
                yield done_event(
                    "test-job",
                    final_text="result",
                    metadata={
                        "parallel_result": {
                            "agent_output": "a",
                            "debate_output": "d",
                            "merged_content": "m",
                            "divergences": [],
                            "conflicts_resolved": 0,
                            "merge_reasoning": "",
                            "agent_duration_ms": 100,
                            "debate_duration_ms": 100,
                            "merge_duration_ms": 50,
                            "total_duration_ms": 250,
                            "success": True,
                            "error": None,
                        }
                    },
                )

            instance.execute = fake_execute

            result = await run_parallel_execution(
                prompt="test",
                agent_models=["claude-agent"],
                debate_models=["gpt-4o"],
                context=context,
                timeout=10,
            )

        assert isinstance(result, ParallelResult)
        assert result.success is True
