"""
Tests for OrchestrationRouter - routing decisions and execution.

Tests:
- Router selects correct executor type based on model ID
- claude-agent -> ClaudeAgentExecutor
- openai-agent -> OpenAIAgentExecutor
- google-agent -> GoogleAgentExecutor
- Unknown model -> falls back to LangGraph
- Router execute() yields SSE events
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.ai.orchestration.router import (
    OrchestrationRouter,
    ExecutorType,
    RoutingDecision,
    OrchestrationContext,
)
from app.services.ai.observability.metrics import (
    get_observability_metrics,
    reset_observability_metrics,
)
from app.services.ai.shared.quotas import TenantQuotaManager
from app.services.ai.shared.sse_protocol import SSEEvent, SSEEventType


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def router():
    """Create OrchestrationRouter with all agents enabled."""
    with patch.dict("os.environ", {
        "CLAUDE_AGENT_ENABLED": "true",
        "OPENAI_AGENT_ENABLED": "true",
        "GOOGLE_AGENT_ENABLED": "true",
        "PARALLEL_EXECUTION_ENABLED": "true",
    }):
        r = OrchestrationRouter()
        r.CLAUDE_AGENT_ENABLED = True
        r.OPENAI_AGENT_ENABLED = True
        r.GOOGLE_AGENT_ENABLED = True
        r.PARALLEL_EXECUTION_ENABLED = True
        return r


@pytest.fixture
def router_agents_disabled():
    """Create OrchestrationRouter with all agents disabled."""
    r = OrchestrationRouter()
    r.CLAUDE_AGENT_ENABLED = False
    r.OPENAI_AGENT_ENABLED = False
    r.GOOGLE_AGENT_ENABLED = False
    return r


# =============================================================================
# ROUTING DECISION TESTS
# =============================================================================


class TestDetermineExecutor:
    """Tests for determine_executor method."""

    def test_claude_agent_selected(self, router):
        """claude-agent model routes to CLAUDE_AGENT executor."""
        decision = router.determine_executor(["claude-agent"], "chat")

        assert decision.executor_type == ExecutorType.CLAUDE_AGENT
        assert "claude-agent" in decision.primary_models
        assert decision.secondary_models == []

    def test_openai_agent_selected(self, router):
        """openai-agent model routes to OPENAI_AGENT executor."""
        decision = router.determine_executor(["openai-agent"], "chat")

        assert decision.executor_type == ExecutorType.OPENAI_AGENT
        assert "openai-agent" in decision.primary_models

    def test_google_agent_selected(self, router):
        """google-agent model routes to GOOGLE_AGENT executor."""
        decision = router.determine_executor(["google-agent"], "chat")

        assert decision.executor_type == ExecutorType.GOOGLE_AGENT
        assert "google-agent" in decision.primary_models

    def test_unknown_model_falls_back_to_langgraph(self, router):
        """Unknown/normal models fall back to LangGraph executor."""
        decision = router.determine_executor(["gpt-4o", "gemini-3-flash"], "chat")

        assert decision.executor_type == ExecutorType.LANGGRAPH
        assert "gpt-4o" in decision.primary_models
        assert "gemini-3-flash" in decision.primary_models

    def test_minuta_mode_always_langgraph(self, router):
        """Minuta mode always uses LangGraph regardless of model."""
        decision = router.determine_executor(["claude-agent"], "minuta")

        assert decision.executor_type == ExecutorType.LANGGRAPH
        assert "minuta" in decision.reason.lower()

    def test_agent_plus_others_routes_to_parallel(self, router):
        """Agent + other models routes to PARALLEL executor."""
        decision = router.determine_executor(
            ["claude-agent", "gpt-4o", "gemini-3-flash"], "chat"
        )

        assert decision.executor_type == ExecutorType.PARALLEL
        assert "claude-agent" in decision.primary_models
        assert "gpt-4o" in decision.secondary_models
        assert "gemini-3-flash" in decision.secondary_models

    def test_disabled_agents_fallback_to_langgraph(self, router_agents_disabled):
        """Disabled agents fall back to LangGraph."""
        decision = router_agents_disabled.determine_executor(
            ["claude-agent"], "chat"
        )

        assert decision.executor_type == ExecutorType.LANGGRAPH

    def test_force_executor_overrides(self, router):
        """force_executor parameter overrides all routing logic."""
        decision = router.determine_executor(
            ["gpt-4o"],
            "chat",
            force_executor=ExecutorType.CLAUDE_AGENT,
        )

        assert decision.executor_type == ExecutorType.CLAUDE_AGENT

    def test_parallel_disabled_uses_agent_only(self, router):
        """When parallel is disabled, agent + others uses agent only."""
        router.PARALLEL_EXECUTION_ENABLED = False

        decision = router.determine_executor(
            ["claude-agent", "gpt-4o"], "chat"
        )

        assert decision.executor_type == ExecutorType.CLAUDE_AGENT
        assert decision.secondary_models == []

    def test_empty_models_returns_langgraph(self, router):
        """Empty model list returns LangGraph."""
        decision = router.determine_executor([], "chat")

        assert decision.executor_type == ExecutorType.LANGGRAPH

    def test_large_document_forces_langgraph_even_with_agent(self, router):
        """Large documents (>500 pages) force LangGraph routing."""
        ctx = OrchestrationContext(
            prompt="texto",
            job_id="job-1",
            max_pages=800,
        )
        decision = router.determine_executor(["claude-agent"], "chat", context=ctx)

        assert decision.executor_type == ExecutorType.LANGGRAPH
        assert decision.document_route == "chunked_rag"
        assert decision.estimated_pages == 800
        assert decision.primary_models == ["gemini-3-flash"]

    def test_medium_document_keeps_agent_route_with_rag_enhanced_hint(self, router):
        """Medium documents (<=500 pages) keep normal routing decisions."""
        ctx = OrchestrationContext(
            prompt="texto",
            job_id="job-2",
            max_pages=320,
        )
        decision = router.determine_executor(["claude-agent"], "chat", context=ctx)

        assert decision.executor_type == ExecutorType.CLAUDE_AGENT
        assert decision.document_route == "rag_enhanced"
        assert decision.estimated_pages == 320

    def test_huge_document_multi_pass_uses_non_agent_models(self, router):
        """Very large documents should route to LangGraph multi_pass without agent IDs."""
        ctx = OrchestrationContext(
            prompt="texto",
            job_id="job-3",
            max_pages=2500,
        )
        decision = router.determine_executor(
            ["claude-agent", "gpt-4o", "gemini-3-flash"],
            "chat",
            context=ctx,
        )

        assert decision.executor_type == ExecutorType.LANGGRAPH
        assert decision.document_route == "multi_pass"
        assert "claude-agent" not in decision.primary_models
        assert "gpt-4o" in decision.primary_models
        assert "gemini-3-flash" in decision.primary_models

    def test_skill_prefer_workflow_forces_langgraph(self, router):
        """Matched skills can force workflow path even on agent model selection."""
        ctx = OrchestrationContext(
            prompt="texto",
            job_id="job-skill-workflow",
            skill_matched=True,
            skill_prefer_workflow=True,
            skill_name="document-drafting",
        )
        decision = router.determine_executor(["claude-agent"], "chat", context=ctx)

        assert decision.executor_type == ExecutorType.LANGGRAPH
        assert "prefer_workflow" in decision.reason

    def test_skill_prefer_agent_routes_to_provider_agent(self, router):
        """Matched skills can route normal models to native provider agent executors."""
        ctx = OrchestrationContext(
            prompt="texto",
            job_id="job-skill-agent",
            skill_matched=True,
            skill_prefer_agent=True,
            skill_name="petition-analysis",
        )
        decision = router.determine_executor(["gpt-5.2"], "chat", context=ctx)

        assert decision.executor_type == ExecutorType.OPENAI_AGENT
        assert decision.primary_models == ["openai-agent"]


class TestValidateModelSelection:
    """Tests for validate_model_selection."""

    def test_valid_selection(self, router):
        assert router.validate_model_selection(["gpt-4o"]) is True

    def test_empty_selection_invalid(self, router):
        assert router.validate_model_selection([]) is False


class TestRoutingDecisionDataclass:
    """Tests for RoutingDecision dataclass."""

    def test_decision_fields(self):
        decision = RoutingDecision(
            executor_type=ExecutorType.CLAUDE_AGENT,
            primary_models=["claude-agent"],
            secondary_models=[],
            reason="test reason",
        )
        assert decision.executor_type == ExecutorType.CLAUDE_AGENT
        assert decision.reason == "test reason"


# =============================================================================
# EXECUTE TESTS
# =============================================================================


class TestExecute:
    """Tests for execute() async generator."""

    @pytest.mark.asyncio
    async def test_execute_yields_sse_events(self, router):
        """execute() yields SSEEvent instances."""
        mock_executor = AsyncMock()

        async def fake_claude_events(ctx):
            from app.services.ai.shared.sse_protocol import done_event
            yield done_event(job_id="test-job", final_text="resultado")

        with patch.object(
            router, "_execute_claude_agent", side_effect=fake_claude_events
        ):
            events = []
            async for event in router.execute(
                prompt="teste",
                selected_models=["claude-agent"],
                mode="chat",
                job_id="test-job",
            ):
                events.append(event)

        assert len(events) >= 2  # At least NODE_START + NODE_COMPLETE
        assert any(e.type == SSEEventType.NODE_START for e in events)
        assert any(e.type == SSEEventType.NODE_COMPLETE for e in events)

    @pytest.mark.asyncio
    async def test_execute_error_yields_error_event(self, router):
        """execute() yields error event on exception."""

        async def failing_executor(ctx):
            raise RuntimeError("Boom")
            yield  # noqa - makes it an async generator

        with patch.object(
            router, "_execute_claude_agent", side_effect=failing_executor
        ):
            events = []
            async for event in router.execute(
                prompt="teste",
                selected_models=["claude-agent"],
                mode="chat",
                job_id="test-job",
            ):
                events.append(event)

        assert any(e.type == SSEEventType.ERROR for e in events)

    @pytest.mark.asyncio
    async def test_execute_langgraph_for_normal_models(self, router):
        """Normal models trigger LangGraph executor."""
        async def fake_langgraph(ctx, models, mode):
            from app.services.ai.shared.sse_protocol import done_event
            yield done_event(job_id="test-job", final_text="lg result")

        with patch.object(
            router, "_execute_langgraph", side_effect=fake_langgraph
        ):
            events = []
            async for event in router.execute(
                prompt="teste",
                selected_models=["gpt-4o"],
                mode="chat",
                job_id="test-job",
            ):
                events.append(event)

        # Should have NODE_START with executor=langgraph
        start_events = [
            e for e in events
            if e.type == SSEEventType.NODE_START
            and e.data.get("executor") == "langgraph"
        ]
        assert len(start_events) >= 1

    @pytest.mark.asyncio
    async def test_execute_records_observability_metrics_on_success(self, router):
        """execute() records latency/success/cost metrics for successful runs."""
        reset_observability_metrics()

        async def fake_claude_events(ctx):
            from app.services.ai.shared.sse_protocol import done_event
            yield done_event(job_id="test-job", final_text="ok")

        with patch.object(router, "_execute_claude_agent", side_effect=fake_claude_events):
            events = []
            async for event in router.execute(
                prompt="teste",
                selected_models=["claude-agent"],
                context={"user_id": "tenant-test", "estimated_cost_usd": 1.25},
                mode="chat",
                job_id="test-job",
            ):
                events.append(event)

        assert any(e.type == SSEEventType.NODE_COMPLETE for e in events)
        snapshot = get_observability_metrics().snapshot()
        assert snapshot["requests"]["total"] == 1
        assert snapshot["requests"]["success_count"] == 1
        assert snapshot["requests"]["success_rate"] == 1.0
        assert snapshot["requests"]["cost_avg_usd"] == pytest.approx(1.25)

    @pytest.mark.asyncio
    async def test_execute_records_observability_metrics_on_quota_block(self, router):
        """execute() records a failed request metric when quota blocks execution."""
        reset_observability_metrics()
        router.tenant_quotas = TenantQuotaManager(
            max_requests_per_window=0,
            max_delegated_tokens_per_window=1000,
            max_concurrent_subagents=1,
            window_seconds=60,
        )

        events = []
        async for event in router.execute(
            prompt="teste",
            selected_models=["claude-agent"],
            context={"user_id": "tenant-test"},
            mode="chat",
            job_id="test-job",
        ):
            events.append(event)

        assert any(
            e.type == SSEEventType.ERROR and e.data.get("error_type") == "quota_exceeded"
            for e in events
        )
        snapshot = get_observability_metrics().snapshot()
        assert snapshot["requests"]["total"] == 1
        assert snapshot["requests"]["success_count"] == 0
        assert snapshot["requests"]["success_rate"] == 0.0

    @pytest.mark.asyncio
    async def test_execute_claude_agent_uses_registry_model_in_config(self, router, monkeypatch):
        """_execute_claude_agent should inject registry model explicitly into AgentConfig."""
        from app.services.ai.shared.sse_protocol import done_event

        captured = {}

        class DummyAgentConfig:
            def __init__(self, **kwargs):
                self.__dict__.update(kwargs)

        class DummyClaudeExecutor:
            def __init__(self, config=None):
                captured["config"] = config

            def load_unified_tools(self, **kwargs):
                captured["load_unified_tools_kwargs"] = kwargs
                return None

            async def run(self, **kwargs):
                yield done_event(job_id="test-job", final_text="ok")

        monkeypatch.setattr(
            "app.services.ai.model_registry.get_api_model_name",
            lambda model_id: "claude-opus-4-6" if model_id == "claude-agent" else model_id,
        )
        monkeypatch.setattr(
            "app.services.ai.claude_agent.executor.AgentConfig",
            DummyAgentConfig,
        )
        monkeypatch.setattr(
            "app.services.ai.claude_agent.executor.ClaudeAgentExecutor",
            DummyClaudeExecutor,
        )

        ctx = OrchestrationContext(prompt="teste", job_id="test-job")
        events = [event async for event in router._execute_claude_agent(ctx)]

        assert any(e.type == SSEEventType.DONE for e in events)
        assert captured["config"] is not None
        assert captured["config"].model == "claude-opus-4-6"
        assert "tool_names" in captured.get("load_unified_tools_kwargs", {})


    @pytest.mark.asyncio
    async def test_execute_claude_agent_tool_allowlist_enables_ask_graph_in_graph_ui(self, router, monkeypatch):
        """Graph UI extra_instructions should allow ask_graph but keep risk tools disabled by default."""
        from app.services.ai.shared.sse_protocol import done_event

        captured = {}

        class DummyClaudeExecutor:
            def __init__(self, config=None):
                pass

            def load_unified_tools(self, **kwargs):
                captured["tool_names"] = kwargs.get("tool_names")
                return None

            async def run(self, **kwargs):
                yield done_event(job_id="test-job", final_text="ok")

        monkeypatch.setattr(
            "app.services.ai.claude_agent.executor.ClaudeAgentExecutor",
            DummyClaudeExecutor,
        )

        ctx = OrchestrationContext(
            prompt="mostre comunidades",
            job_id="test-job",
            user_id="tenant-test",
            extra_instructions="MODO GRAFO (UI)",
        )
        events = [event async for event in router._execute_claude_agent(ctx)]
        assert any(e.type == SSEEventType.DONE for e in events)
        assert isinstance(captured.get("tool_names"), list)
        assert "ask_graph" in captured["tool_names"]
        assert "scan_graph_risk" not in captured["tool_names"]


# =============================================================================
# ORCHESTRATION CONTEXT TESTS
# =============================================================================


class TestOrchestrationContext:
    """Tests for OrchestrationContext dataclass."""

    def test_from_dict(self):
        data = {
            "prompt": "test prompt",
            "job_id": "job-123",
            "user_id": "user-1",
            "temperature": 0.5,
            "web_search": True,
        }
        ctx = OrchestrationContext.from_dict(data)

        assert ctx.prompt == "test prompt"
        assert ctx.job_id == "job-123"
        assert ctx.user_id == "user-1"
        assert ctx.temperature == 0.5
        assert ctx.web_search is True

    def test_from_dict_defaults(self):
        ctx = OrchestrationContext.from_dict({})

        assert ctx.prompt == ""
        assert ctx.job_id == ""
        assert ctx.temperature == 0.3
        assert ctx.web_search is False
        assert ctx.chat_personality == "juridico"

    def test_from_dict_pages_fields(self):
        ctx = OrchestrationContext.from_dict(
            {
                "target_pages": 120,
                "min_pages": 80,
                "max_pages": 200,
                "estimated_pages": 140,
                "document_route": "rag_enhanced",
            }
        )

        assert ctx.target_pages == 120
        assert ctx.min_pages == 80
        assert ctx.max_pages == 200
        assert ctx.estimated_pages == 140
        assert ctx.document_route == "rag_enhanced"
