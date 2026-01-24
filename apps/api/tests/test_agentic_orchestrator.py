"""
Tests for Agentic RAG Orchestrator - Multi-step orchestration for complex queries.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from app.services.rag.core.agentic_orchestrator import (
    AgenticOrchestrator,
    OrchestrationMode,
    ResearchPhase,
    ResearchStep,
    OrchestrationResult,
)


class TestAgenticOrchestratorDeepResearch:
    """Tests for deep research mode."""

    @pytest.fixture
    def mock_retriever(self):
        """Mock retriever that returns sample documents."""
        async def retriever(query, top_k, context=None):
            return [
                {
                    "text": f"Documento sobre {query}. Lorem ipsum dolor sit amet.",
                    "metadata": {"source": "doc1.pdf", "chunk_id": 1},
                },
                {
                    "text": f"Outro documento relacionado a {query}.",
                    "metadata": {"source": "doc2.pdf", "chunk_id": 2},
                },
            ]
        return retriever

    @pytest.fixture
    def mock_llm(self):
        """Mock LLM that returns sample responses."""
        async def llm(prompt, max_tokens):
            if "lacunas" in prompt.lower() or "gaps" in prompt.lower():
                return '{"gaps": ["aspecto não coberto"], "confidence": 0.8, "reasoning": "test"}'
            elif "sintetize" in prompt.lower() or "synthesize" in prompt.lower():
                return "Síntese das informações encontradas sobre o tema."
            elif "query de busca" in prompt.lower():
                return "query refinada sobre o tema"
            else:
                return "Resposta genérica do LLM"
        return llm

    @pytest.fixture
    def orchestrator(self, mock_retriever, mock_llm):
        return AgenticOrchestrator(
            retriever_fn=mock_retriever,
            llm_fn=mock_llm,
            max_iterations=3,
            min_confidence=0.7,
        )

    @pytest.mark.asyncio
    async def test_deep_research_returns_result(self, orchestrator):
        """Deep research should return OrchestrationResult."""
        result = await orchestrator.orchestrate(
            query="Abandono afetivo na jurisprudência",
            mode=OrchestrationMode.DEEP_RESEARCH,
        )

        assert isinstance(result, OrchestrationResult)
        assert result.mode == OrchestrationMode.DEEP_RESEARCH
        assert result.original_query == "Abandono afetivo na jurisprudência"
        assert len(result.steps) >= 1
        assert result.final_context != ""

    @pytest.mark.asyncio
    async def test_deep_research_has_steps(self, orchestrator):
        """Deep research should record research steps."""
        result = await orchestrator.orchestrate(
            query="Evolução da responsabilidade civil",
            mode=OrchestrationMode.DEEP_RESEARCH,
        )

        assert len(result.steps) >= 1
        first_step = result.steps[0]
        assert first_step.phase == ResearchPhase.INITIAL_SEARCH
        assert first_step.query != ""
        assert len(first_step.results) >= 1

    @pytest.mark.asyncio
    async def test_deep_research_deduplicates_sources(self, orchestrator):
        """Deep research should deduplicate sources."""
        result = await orchestrator.orchestrate(
            query="Tema de direito",
            mode=OrchestrationMode.DEEP_RESEARCH,
        )

        # Sources should be deduplicated
        source_texts = [s.get("text", "")[:50] for s in result.sources]
        assert len(source_texts) == len(set(source_texts))

    @pytest.mark.asyncio
    async def test_deep_research_respects_max_iterations(self):
        """Deep research should respect max_iterations."""
        async def low_confidence_llm(prompt, max_tokens):
            return '{"gaps": ["gap"], "confidence": 0.1, "reasoning": "low"}'

        async def mock_retriever(query, top_k, context=None):
            return [{"text": "doc", "metadata": {}}]

        orchestrator = AgenticOrchestrator(
            retriever_fn=mock_retriever,
            llm_fn=low_confidence_llm,
            max_iterations=2,
            min_confidence=0.9,
        )

        result = await orchestrator.orchestrate(
            query="Query qualquer",
            mode=OrchestrationMode.DEEP_RESEARCH,
        )

        # Should stop at max_iterations even with low confidence
        assert result.total_iterations <= 2


class TestAgenticOrchestratorComparison:
    """Tests for comparison mode."""

    @pytest.fixture
    def mock_retriever(self):
        async def retriever(query, top_k, context=None):
            if "STF" in query:
                return [{"text": "Posição do STF sobre o tema", "metadata": {"source": "stf.pdf"}}]
            elif "STJ" in query:
                return [{"text": "Posição do STJ sobre o tema", "metadata": {"source": "stj.pdf"}}]
            else:
                return [{"text": f"Doc sobre {query}", "metadata": {"source": "doc.pdf"}}]
        return retriever

    @pytest.fixture
    def mock_llm(self):
        async def llm(prompt, max_tokens):
            if "partes sendo comparadas" in prompt.lower():
                return '{"parts": ["STF sobre tema", "STJ sobre tema"]}'
            elif "pontos-chave" in prompt.lower():
                return "- Ponto 1\n- Ponto 2\n- Ponto 3"
            elif "aspectos para comparar" in prompt.lower():
                return "- Entendimento sobre prescrição\n- Requisitos de prova"
            elif "análise comparativa" in prompt.lower():
                return "Análise: O STF e STJ divergem em aspectos..."
            else:
                return "Resposta genérica"
        return llm

    @pytest.fixture
    def orchestrator(self, mock_retriever, mock_llm):
        return AgenticOrchestrator(
            retriever_fn=mock_retriever,
            llm_fn=mock_llm,
            max_iterations=3,
        )

    @pytest.mark.asyncio
    async def test_comparison_returns_result(self, orchestrator):
        """Comparison should return OrchestrationResult."""
        result = await orchestrator.orchestrate(
            query="Compare STF vs STJ sobre prescrição",
            mode=OrchestrationMode.COMPARISON,
            sub_queries=["STF prescrição", "STJ prescrição"],
        )

        assert isinstance(result, OrchestrationResult)
        assert result.mode == OrchestrationMode.COMPARISON

    @pytest.mark.asyncio
    async def test_comparison_has_multiple_steps(self, orchestrator):
        """Comparison should have steps for each sub-query."""
        result = await orchestrator.orchestrate(
            query="Compare STF vs STJ",
            mode=OrchestrationMode.COMPARISON,
            sub_queries=["STF tema", "STJ tema"],
        )

        # Should have at least one step per sub-query
        assert len(result.steps) >= 2

    @pytest.mark.asyncio
    async def test_comparison_builds_table(self, orchestrator):
        """Comparison should build comparison table."""
        result = await orchestrator.orchestrate(
            query="Compare STF vs STJ",
            mode=OrchestrationMode.COMPARISON,
            sub_queries=["STF tema", "STJ tema"],
        )

        assert result.comparison_table is not None
        assert "headers" in result.comparison_table

    @pytest.mark.asyncio
    async def test_comparison_extracts_parts_if_not_provided(self, orchestrator):
        """Comparison should extract parts if sub_queries not provided."""
        result = await orchestrator.orchestrate(
            query="STF versus STJ sobre dano moral",
            mode=OrchestrationMode.COMPARISON,
        )

        assert len(result.steps) >= 1


class TestAgenticOrchestratorOpenEnded:
    """Tests for open-ended mode."""

    @pytest.fixture
    def mock_retriever(self):
        async def retriever(query, top_k, context=None):
            return [
                {"text": f"Informação sobre {query}", "metadata": {"source": "doc.pdf"}},
                {"text": "Outra perspectiva sobre o tema", "metadata": {"source": "doc2.pdf"}},
            ]
        return retriever

    @pytest.fixture
    def mock_llm(self):
        async def llm(prompt, max_tokens):
            if "decomponha" in prompt.lower():
                return "- Perspectiva jurídica\n- Perspectiva prática\n- Casos similares"
            elif "recomendações" in prompt.lower():
                return "- Recomendação 1\n- Recomendação 2\n- Recomendação 3"
            elif "sintetize" in prompt.lower():
                return "Síntese com análise de prós e contras..."
            else:
                return "Resposta genérica"
        return llm

    @pytest.fixture
    def orchestrator(self, mock_retriever, mock_llm):
        return AgenticOrchestrator(
            retriever_fn=mock_retriever,
            llm_fn=mock_llm,
            max_iterations=3,
        )

    @pytest.mark.asyncio
    async def test_open_ended_returns_result(self, orchestrator):
        """Open-ended should return OrchestrationResult."""
        result = await orchestrator.orchestrate(
            query="Qual a melhor estratégia para este caso?",
            mode=OrchestrationMode.OPEN_ENDED,
        )

        assert isinstance(result, OrchestrationResult)
        assert result.mode == OrchestrationMode.OPEN_ENDED

    @pytest.mark.asyncio
    async def test_open_ended_has_recommendations(self, orchestrator):
        """Open-ended should generate recommendations."""
        result = await orchestrator.orchestrate(
            query="Qual a melhor abordagem?",
            mode=OrchestrationMode.OPEN_ENDED,
        )

        assert len(result.recommendations) >= 1

    @pytest.mark.asyncio
    async def test_open_ended_searches_perspectives(self, orchestrator):
        """Open-ended should search multiple perspectives."""
        result = await orchestrator.orchestrate(
            query="Como devo proceder?",
            mode=OrchestrationMode.OPEN_ENDED,
        )

        # Should have multiple steps for different perspectives
        assert len(result.steps) >= 1


class TestAgenticOrchestratorStreaming:
    """Tests for streaming mode."""

    @pytest.fixture
    def mock_retriever(self):
        async def retriever(query, top_k, context=None):
            return [{"text": "Doc", "metadata": {}}]
        return retriever

    @pytest.fixture
    def mock_llm(self):
        async def llm(prompt, max_tokens):
            return '{"gaps": [], "confidence": 0.9}'
        return llm

    @pytest.fixture
    def orchestrator(self, mock_retriever, mock_llm):
        return AgenticOrchestrator(
            retriever_fn=mock_retriever,
            llm_fn=mock_llm,
            max_iterations=2,
        )

    @pytest.mark.asyncio
    async def test_streaming_yields_updates(self, orchestrator):
        """Streaming should yield progress updates."""
        updates = []
        async for update in orchestrator.orchestrate_stream(
            query="Pesquisa sobre tema",
            mode=OrchestrationMode.DEEP_RESEARCH,
        ):
            updates.append(update)

        assert len(updates) >= 1
        assert any(u.get("type") == "phase" for u in updates)
        assert any(u.get("type") == "complete" for u in updates)

    @pytest.mark.asyncio
    async def test_streaming_includes_results(self, orchestrator):
        """Streaming should include result counts."""
        updates = []
        async for update in orchestrator.orchestrate_stream(
            query="Query",
            mode=OrchestrationMode.DEEP_RESEARCH,
        ):
            updates.append(update)

        result_updates = [u for u in updates if u.get("type") == "results"]
        assert len(result_updates) >= 1


class TestAgenticOrchestratorHelpers:
    """Tests for helper methods."""

    @pytest.fixture
    def orchestrator(self):
        return AgenticOrchestrator(
            retriever_fn=lambda q, k, c=None: [],
            llm_fn=lambda p, m: "",
            max_iterations=3,
        )

    def test_deduplicate_sources(self, orchestrator):
        """Should deduplicate sources by content."""
        docs = [
            {"text": "Same content here", "metadata": {}},
            {"text": "Same content here", "metadata": {}},
            {"text": "Different content", "metadata": {}},
        ]

        unique = orchestrator._deduplicate_sources(docs)
        assert len(unique) == 2

    def test_deduplicate_sources_empty(self, orchestrator):
        """Should handle empty list."""
        unique = orchestrator._deduplicate_sources([])
        assert unique == []


class TestResearchStep:
    """Tests for ResearchStep dataclass."""

    def test_research_step_defaults(self):
        """ResearchStep should have correct defaults."""
        step = ResearchStep(
            phase=ResearchPhase.INITIAL_SEARCH,
            query="test query",
        )
        assert step.results == []
        assert step.gaps_identified == []
        assert step.tokens_used == 0

    def test_research_step_with_results(self):
        """ResearchStep should store results."""
        step = ResearchStep(
            phase=ResearchPhase.TARGETED_SEARCH,
            query="refined query",
            results=[{"text": "doc1"}, {"text": "doc2"}],
            gaps_identified=["gap1"],
        )
        assert len(step.results) == 2
        assert len(step.gaps_identified) == 1


class TestOrchestrationResult:
    """Tests for OrchestrationResult dataclass."""

    def test_orchestration_result_defaults(self):
        """OrchestrationResult should have correct defaults."""
        result = OrchestrationResult(
            mode=OrchestrationMode.DEEP_RESEARCH,
            original_query="test",
        )
        assert result.steps == []
        assert result.final_context == ""
        assert result.sources == []
        assert result.comparison_table is None
        assert result.recommendations == []
        assert result.total_iterations == 0
        assert result.total_tokens == 0
        assert result.duration_ms == 0
