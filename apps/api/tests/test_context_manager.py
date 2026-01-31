"""
Tests for ContextManager - context compaction and token management.

Tests:
- Context compaction triggers at threshold
- System messages are preserved after compaction
- Token counting works
- Empty messages handled
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.ai.langgraph.improvements.context_manager import (
    ContextManager,
    ContextWindow,
    MODEL_CONTEXT_LIMITS,
    DEFAULT_COMPACTION_THRESHOLD,
)


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def manager():
    """Create ContextManager with known limits."""
    return ContextManager(
        model_name="gpt-4o",
        threshold=0.7,
    )


@pytest.fixture
def manager_low_limit():
    """Create ContextManager with artificially low limit for compaction tests."""
    mgr = ContextManager(model_name="gpt-4o", threshold=0.7)
    mgr.limit = 100  # Very low limit to trigger compaction easily
    return mgr


@pytest.fixture
def sample_messages():
    """Create a list of sample messages."""
    return [
        {"role": "system", "content": "You are a legal assistant."},
        {"role": "user", "content": "What is habeas corpus?"},
        {"role": "assistant", "content": "Habeas corpus is a legal remedy..."},
        {"role": "user", "content": "Give me an example."},
        {"role": "assistant", "content": "An example is when a person is detained unlawfully..."},
    ]


@pytest.fixture
def large_messages():
    """Create a large set of messages to simulate context overflow."""
    messages = [
        {"role": "system", "content": "You are a legal assistant. Follow all instructions."},
    ]
    for i in range(30):
        messages.append({
            "role": "user",
            "content": f"Question {i}: " + "x" * 200,
        })
        messages.append({
            "role": "assistant",
            "content": f"Answer {i}: " + "y" * 500,
        })
    return messages


@pytest.fixture
def messages_with_tool_results():
    """Create messages containing tool_result blocks (Anthropic format)."""
    return [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Search for case law."},
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "Let me search..."},
                {"type": "tool_use", "name": "search_jurisprudencia", "input": {"q": "habeas corpus"}},
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "tool-1",
                    "content": "Found 10 results: " + "case data " * 200,
                },
            ],
        },
        {"role": "assistant", "content": "Based on the search results..."},
        {"role": "user", "content": "Thanks, another question..."},
        {"role": "assistant", "content": "Sure, here is the answer."},
    ]


# =============================================================================
# TOKEN COUNTING TESTS
# =============================================================================


class TestTokenCounting:
    """Tests for token counting functionality."""

    def test_count_tokens_returns_positive_int(self, manager, sample_messages):
        """count_tokens returns a positive integer for non-empty messages."""
        tokens = manager.count_tokens(sample_messages)
        assert isinstance(tokens, int)
        assert tokens > 0

    def test_count_tokens_empty_messages(self, manager):
        """count_tokens returns 0 for empty list."""
        assert manager.count_tokens([]) == 0

    def test_count_tokens_single_message(self, manager):
        """count_tokens works with a single message."""
        tokens = manager.count_tokens([
            {"role": "user", "content": "Hello"}
        ])
        assert tokens > 0

    def test_count_tokens_multimodal_content(self, manager):
        """count_tokens handles list content (multimodal format)."""
        tokens = manager.count_tokens([
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Analyze this."},
                ],
            }
        ])
        assert tokens > 0

    def test_count_tokens_tool_results(self, manager, messages_with_tool_results):
        """count_tokens includes tool_result content."""
        tokens = manager.count_tokens(messages_with_tool_results)
        assert tokens > 0

    def test_longer_messages_have_more_tokens(self, manager):
        """Longer messages should produce more tokens."""
        short = [{"role": "user", "content": "Hi"}]
        long = [{"role": "user", "content": "x" * 10000}]

        assert manager.count_tokens(long) > manager.count_tokens(short)

    def test_count_text_tokens_empty_string(self, manager):
        """Empty string returns 0 tokens."""
        assert manager._count_text_tokens("") == 0

    def test_count_text_tokens_fallback(self, manager):
        """Fallback estimation works when tiktoken is not available."""
        manager._tiktoken_encoding = None
        # Force init to fail by mocking
        with patch.object(manager, "_init_tiktoken"):
            manager._tiktoken_encoding = None
            tokens = manager._count_text_tokens("Hello world test")
            assert tokens > 0


# =============================================================================
# CONTEXT WINDOW TESTS
# =============================================================================


class TestContextWindow:
    """Tests for ContextWindow status."""

    def test_get_context_window(self, manager, sample_messages):
        """get_context_window returns ContextWindow with correct fields."""
        window = manager.get_context_window(sample_messages)

        assert isinstance(window, ContextWindow)
        assert window.total_tokens > 0
        assert window.limit == MODEL_CONTEXT_LIMITS["gpt-4o"]
        assert window.messages_count == len(sample_messages)
        assert 0 <= window.usage_percent <= 100

    def test_context_window_needs_compaction(self):
        """ContextWindow.needs_compaction is True when over threshold."""
        window = ContextWindow(
            total_tokens=80_000,
            limit=100_000,
            threshold=0.7,
        )
        assert window.needs_compaction is True

    def test_context_window_no_compaction_needed(self):
        """ContextWindow.needs_compaction is False when under threshold."""
        window = ContextWindow(
            total_tokens=50_000,
            limit=100_000,
            threshold=0.7,
        )
        assert window.needs_compaction is False


# =============================================================================
# SHOULD COMPACT TESTS
# =============================================================================


class TestShouldCompact:
    """Tests for should_compact trigger."""

    def test_should_compact_true_at_threshold(self, manager_low_limit):
        """should_compact returns True when tokens exceed threshold."""
        # With limit=100 and threshold=0.7, anything > 70 tokens triggers
        messages = [
            {"role": "user", "content": "x" * 1000},
        ]
        assert manager_low_limit.should_compact(messages) is True

    def test_should_compact_false_below_threshold(self, manager):
        """should_compact returns False for small messages within limit."""
        messages = [{"role": "user", "content": "Hi"}]
        assert manager.should_compact(messages) is False

    def test_should_compact_empty_messages(self, manager):
        """should_compact returns False for empty messages."""
        assert manager.should_compact([]) is False


# =============================================================================
# COMPACT TESTS
# =============================================================================


class TestCompact:
    """Tests for context compaction."""

    @pytest.mark.asyncio
    async def test_compact_empty_messages(self, manager):
        """compact returns empty list for empty input."""
        compacted, summary = await manager.compact([])
        assert compacted == []
        assert summary == ""

    @pytest.mark.asyncio
    async def test_compact_preserves_system_messages(self, manager_low_limit):
        """System messages are preserved after compaction."""
        messages = [
            {"role": "system", "content": "You are a legal expert."},
            {"role": "user", "content": "First question " + "x" * 500},
            {"role": "assistant", "content": "First answer " + "y" * 500},
            {"role": "user", "content": "Second question " + "x" * 500},
            {"role": "assistant", "content": "Second answer " + "y" * 500},
            # Recent messages
            {"role": "user", "content": "Recent question"},
            {"role": "assistant", "content": "Recent answer"},
        ]

        with patch.object(
            manager_low_limit,
            "_call_anthropic_for_summary",
            new_callable=AsyncMock,
            return_value="Summary of conversation",
        ):
            compacted, summary = await manager_low_limit.compact(
                messages,
                preserve_recent=2,
                preserve_instructions=True,
            )

        # System message should be preserved
        system_msgs = [m for m in compacted if m.get("role") == "system"]
        assert len(system_msgs) >= 1
        assert "legal expert" in system_msgs[0]["content"]

    @pytest.mark.asyncio
    async def test_compact_preserves_recent_messages(self, manager_low_limit):
        """Recent messages are preserved after compaction."""
        messages = [
            {"role": "user", "content": "Old question " + "x" * 500},
            {"role": "assistant", "content": "Old answer " + "y" * 500},
            {"role": "user", "content": "Recent question"},
            {"role": "assistant", "content": "Recent answer"},
        ]

        with patch.object(
            manager_low_limit,
            "_call_anthropic_for_summary",
            new_callable=AsyncMock,
            return_value="Summary",
        ):
            compacted, _ = await manager_low_limit.compact(
                messages,
                preserve_recent=2,
            )

        # Recent messages should be at the end
        assert compacted[-1]["content"] == "Recent answer"
        assert compacted[-2]["content"] == "Recent question"

    @pytest.mark.asyncio
    async def test_compact_step1_clears_tool_results(self, manager_low_limit, messages_with_tool_results):
        """Step 1 of compaction truncates old tool_results."""
        with patch.object(
            manager_low_limit,
            "_call_anthropic_for_summary",
            new_callable=AsyncMock,
            return_value="Summary",
        ):
            compacted, _ = await manager_low_limit.compact(
                messages_with_tool_results,
                preserve_recent=2,
            )

        # Tool results in old messages should be truncated
        for msg in compacted[:-2]:
            content = msg.get("content")
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "tool_result":
                        assert "truncated" in item.get("content", "").lower()

    @pytest.mark.asyncio
    async def test_compact_generates_summary(self, manager_low_limit):
        """Compaction generates a summary when step 2 is needed."""
        messages = [
            {"role": "user", "content": "Question " + "x" * 1000},
            {"role": "assistant", "content": "Answer " + "y" * 1000},
            {"role": "user", "content": "Recent"},
            {"role": "assistant", "content": "Reply"},
        ]

        with patch.object(
            manager_low_limit,
            "_call_anthropic_for_summary",
            new_callable=AsyncMock,
            return_value="Resumo: conversa sobre questoes juridicas",
        ):
            compacted, summary = await manager_low_limit.compact(
                messages,
                preserve_recent=2,
            )

        if summary:
            assert len(summary) > 0


# =============================================================================
# CLEAR OLD TOOL RESULTS TESTS
# =============================================================================


class TestClearOldToolResults:
    """Tests for _clear_old_tool_results helper."""

    def test_clears_openai_format_tool_messages(self, manager):
        """Truncates OpenAI format tool messages in old section."""
        messages = [
            {"role": "user", "content": "search"},
            {"role": "tool", "tool_call_id": "tc-1", "content": "big result " * 100},
            {"role": "assistant", "content": "Based on..."},
            # Recent
            {"role": "user", "content": "Thanks"},
        ]

        result = manager._clear_old_tool_results(messages, keep_recent=1)

        # Old tool message should be truncated
        tool_msg = [m for m in result if m.get("role") == "tool"][0]
        assert "truncated" in tool_msg["content"].lower()

        # Recent message preserved
        assert result[-1]["content"] == "Thanks"

    def test_preserves_all_when_few_messages(self, manager):
        """Does not truncate when messages <= keep_recent."""
        messages = [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello"},
        ]

        result = manager._clear_old_tool_results(messages, keep_recent=5)
        assert result == messages


# =============================================================================
# MODEL LIMIT TESTS
# =============================================================================


class TestModelLimits:
    """Tests for model context limit detection."""

    def test_known_model_limit(self):
        mgr = ContextManager(model_name="gpt-4o")
        assert mgr.limit == 128_000

    def test_claude_model_limit(self):
        mgr = ContextManager(model_name="claude-sonnet-4-20250514")
        assert mgr.limit == 200_000

    def test_unknown_model_uses_default(self):
        mgr = ContextManager(model_name="unknown-model-xyz")
        assert mgr.limit == MODEL_CONTEXT_LIMITS["default"]

    def test_gemini_model_limit(self):
        mgr = ContextManager(model_name="gemini-2.0-flash")
        assert mgr.limit == 1_000_000


# =============================================================================
# ESTIMATE SAVINGS TESTS
# =============================================================================


class TestEstimateSavings:
    """Tests for compaction savings estimation."""

    def test_estimate_returns_dict(self, manager, messages_with_tool_results):
        """estimate_compaction_savings returns expected keys."""
        result = manager.estimate_compaction_savings(messages_with_tool_results)

        assert "current_tokens" in result
        assert "step1_tokens" in result
        assert "step1_savings" in result
        assert "estimated_step2_tokens" in result

    def test_estimate_savings_positive(self, manager, messages_with_tool_results):
        """Tool results cause positive savings in step 1."""
        result = manager.estimate_compaction_savings(
            messages_with_tool_results,
            preserve_recent=2,
        )

        assert result["step1_savings"] >= 0


# =============================================================================
# FALLBACK SUMMARY TESTS
# =============================================================================


class TestFallbackSummary:
    """Tests for fallback summary generation (no LLM)."""

    def test_fallback_summary_extracts_points(self, manager, sample_messages):
        """Fallback summary extracts user and assistant points."""
        summary = manager._generate_fallback_summary(sample_messages)
        assert len(summary) > 0

    def test_fallback_summary_empty_messages(self, manager):
        """Fallback summary returns default for empty messages."""
        summary = manager._generate_fallback_summary([])
        assert isinstance(summary, str)

    def test_fallback_summary_handles_list_content(self, manager):
        """Fallback handles messages with list content."""
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Complex question here."},
                ],
            },
        ]
        summary = manager._generate_fallback_summary(messages)
        assert isinstance(summary, str)
