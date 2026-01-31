"""
Tests for Parallel Research Subgraph

Tests the parallel research functionality:
- State management
- Query distribution
- Search node execution
- Result merging and deduplication
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Any, List

from app.services.ai.langgraph.subgraphs.parallel_research import (
    ResearchState,
    distribute_query,
    search_rag_local,
    search_rag_global,
    search_web,
    search_jurisprudencia,
    merge_research_results,
    parallel_search_node,
    create_parallel_research_subgraph,
    run_parallel_research,
    _hash_content,
    _normalize_text,
    _is_duplicate,
    _score_result,
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def base_state() -> ResearchState:
    """Create a base research state for testing."""
    return ResearchState(
        query="responsabilidade civil extracontratual dano moral",
        section_title="Fundamentos Jurídicos",
        thesis="A responsabilidade civil subjetiva exige culpa do agente",
        input_text="Caso de dano moral em acidente de trânsito",
        job_id=None,
        tenant_id="test-tenant",
        processo_id="12345",
        top_k=5,
        max_context_chars=10000,
        query_rag_local=None,
        query_rag_global=None,
        query_web=None,
        query_juris=None,
        results_rag_local=[],
        results_rag_global=[],
        results_web=[],
        results_juris=[],
        merged_context="",
        citations_map={},
        sources_used=[],
        metrics={},
    )


@pytest.fixture
def mock_rag_results() -> List[Dict[str, Any]]:
    """Mock RAG search results."""
    return [
        {
            "text": "Art. 186. Aquele que, por ação ou omissão voluntária, negligência ou imprudência, violar direito e causar dano a outrem, ainda que exclusivamente moral, comete ato ilícito.",
            "score": 0.92,
            "metadata": {"source_type": "lei", "artigo": "186", "numero": "10.406"},
        },
        {
            "text": "Art. 927. Aquele que, por ato ilícito (arts. 186 e 187), causar dano a outrem, fica obrigado a repará-lo.",
            "score": 0.88,
            "metadata": {"source_type": "lei", "artigo": "927", "numero": "10.406"},
        },
    ]


@pytest.fixture
def mock_web_results() -> Dict[str, Any]:
    """Mock web search results."""
    return {
        "success": True,
        "results": [
            {
                "title": "Responsabilidade Civil - STJ",
                "url": "https://www.stj.jus.br/resp/123",
                "snippet": "A jurisprudência do STJ consolidou entendimento sobre responsabilidade civil...",
                "relevance_score": 0.85,
            },
            {
                "title": "Dano Moral no Direito Brasileiro",
                "url": "https://www.conjur.com.br/dano-moral",
                "snippet": "O dano moral é caracterizado pela lesão a direitos da personalidade...",
                "relevance_score": 0.80,
            },
        ],
    }


@pytest.fixture
def mock_juris_results() -> Dict[str, Any]:
    """Mock jurisprudence search results."""
    return {
        "items": [
            {
                "id": "1",
                "court": "STJ",
                "title": "REsp 1.234.567",
                "summary": "CIVIL. RESPONSABILIDADE CIVIL. DANO MORAL. QUANTIFICAÇÃO...",
                "date": "2023-05-15",
                "processNumber": "REsp 1.234.567",
                "relator": "Min. Fulano",
                "tema": "Responsabilidade Civil",
                "url": "https://stj.jus.br/resp/1234567",
                "relevance_score": 0.90,
            },
        ],
        "total": 1,
        "query": "responsabilidade civil",
    }


# =============================================================================
# HELPER FUNCTION TESTS
# =============================================================================

class TestHelperFunctions:
    """Tests for helper functions."""

    def test_hash_content(self):
        """Test content hashing."""
        text = "Test content"
        hash1 = _hash_content(text)
        hash2 = _hash_content(text)

        assert hash1 == hash2
        assert len(hash1) == 12  # MD5 truncated to 12 chars

    def test_normalize_text(self):
        """Test text normalization."""
        text = "  Multiple   spaces   and\n\nnewlines  "
        normalized = _normalize_text(text)

        assert "  " not in normalized
        assert normalized == "multiple spaces and newlines"

    def test_is_duplicate_by_hash(self):
        """Test duplicate detection by hash."""
        seen_hashes = set()
        seen_normalized = set()

        text1 = "Original text content"
        text2 = "Different text content"

        assert not _is_duplicate(text1, seen_hashes, seen_normalized)
        assert _is_duplicate(text1, seen_hashes, seen_normalized)  # Same text
        assert not _is_duplicate(text2, seen_hashes, seen_normalized)  # Different text

    def test_score_result(self):
        """Test result scoring."""
        result = {
            "text": "responsabilidade civil dano moral extracontratual",
            "score": 0.8,
            "source_type": "lei",
        }
        query = "responsabilidade civil"

        score = _score_result(result, query)

        assert score > 0.8  # Should have boost from term matches and source type


# =============================================================================
# NODE TESTS
# =============================================================================

class TestDistributeQuery:
    """Tests for distribute_query node."""

    @pytest.mark.asyncio
    async def test_distribute_creates_source_queries(self, base_state):
        """Test that distribute creates queries for all sources."""
        result = await distribute_query(base_state)

        assert result["query_rag_local"] is not None
        assert result["query_rag_global"] is not None
        assert result["query_web"] is not None
        assert result["query_juris"] is not None

    @pytest.mark.asyncio
    async def test_distribute_includes_processo_in_local(self, base_state):
        """Test that processo_id is included in local query."""
        result = await distribute_query(base_state)

        assert "12345" in result["query_rag_local"]

    @pytest.mark.asyncio
    async def test_distribute_includes_thesis_in_global(self, base_state):
        """Test that thesis is included in global query."""
        result = await distribute_query(base_state)

        assert "responsabilidade" in result["query_rag_global"].lower()

    @pytest.mark.asyncio
    async def test_distribute_metrics(self, base_state):
        """Test that distribute records metrics."""
        result = await distribute_query(base_state)

        assert "distribute_latency_ms" in result["metrics"]


class TestSearchNodes:
    """Tests for search nodes."""

    @pytest.mark.asyncio
    async def test_search_rag_local_with_mock(self, base_state, mock_rag_results):
        """Test RAG local search with mocked manager."""
        mock_manager = MagicMock()
        mock_manager.hybrid_search.return_value = mock_rag_results

        with patch(
            "app.services.ai.langgraph.subgraphs.parallel_research._get_rag_manager",
            return_value=mock_manager
        ):
            result = await search_rag_local(base_state)

        assert len(result["results_rag_local"]) == 2
        assert result["metrics"]["rag_local_count"] == 2

    @pytest.mark.asyncio
    async def test_search_rag_local_handles_unavailable(self, base_state):
        """Test RAG local search handles unavailable service."""
        with patch(
            "app.services.ai.langgraph.subgraphs.parallel_research._get_rag_manager",
            return_value=None
        ):
            result = await search_rag_local(base_state)

        assert result["results_rag_local"] == []
        assert result["metrics"]["rag_local_count"] == 0

    @pytest.mark.asyncio
    async def test_search_web_with_mock(self, base_state, mock_web_results):
        """Test web search with mocked service."""
        mock_service = AsyncMock()
        mock_service.search_legal = AsyncMock(return_value=mock_web_results)

        with patch(
            "app.services.ai.langgraph.subgraphs.parallel_research._get_web_search_service",
            return_value=mock_service
        ):
            result = await search_web(base_state)

        assert len(result["results_web"]) == 2
        assert result["metrics"]["web_count"] == 2

    @pytest.mark.asyncio
    async def test_search_jurisprudencia_with_mock(self, base_state, mock_juris_results):
        """Test jurisprudence search with mocked service."""
        mock_service = MagicMock()
        mock_service.search = AsyncMock(return_value=mock_juris_results)

        with patch(
            "app.services.ai.langgraph.subgraphs.parallel_research._get_jurisprudence_service",
            return_value=mock_service
        ):
            result = await search_jurisprudencia(base_state)

        assert len(result["results_juris"]) == 1
        assert result["metrics"]["juris_count"] == 1


class TestMergeResults:
    """Tests for merge_research_results node."""

    @pytest.mark.asyncio
    async def test_merge_combines_results(self, base_state):
        """Test that merge combines results from all sources."""
        state = {
            **base_state,
            "results_rag_local": [
                {"text": "Local result 1", "score": 0.9, "source_type": "sei", "metadata": {}},
            ],
            "results_rag_global": [
                {"text": "Global result 1", "score": 0.85, "source_type": "lei", "metadata": {}},
            ],
            "results_web": [
                {"text": "Web result 1", "score": 0.8, "source_type": "web", "metadata": {}, "url": "http://example.com"},
            ],
            "results_juris": [
                {"text": "Juris result 1", "score": 0.88, "source_type": "juris", "metadata": {}},
            ],
        }

        result = await merge_research_results(state)

        assert len(result["sources_used"]) == 4
        assert result["merged_context"] != ""
        assert len(result["citations_map"]) > 0

    @pytest.mark.asyncio
    async def test_merge_deduplicates(self, base_state):
        """Test that merge deduplicates similar content."""
        duplicate_text = "This is a duplicate text that appears multiple times"
        state = {
            **base_state,
            "results_rag_local": [
                {"text": duplicate_text, "score": 0.9, "source_type": "sei", "metadata": {}},
            ],
            "results_rag_global": [
                {"text": duplicate_text, "score": 0.85, "source_type": "lei", "metadata": {}},
            ],
            "results_web": [],
            "results_juris": [],
        }

        result = await merge_research_results(state)

        # Should only have 1 unique result
        assert result["metrics"]["unique_results"] == 1

    @pytest.mark.asyncio
    async def test_merge_respects_max_chars(self, base_state):
        """Test that merge respects max_context_chars limit."""
        long_text = "A" * 5000
        state = {
            **base_state,
            "max_context_chars": 1000,
            "results_rag_local": [
                {"text": long_text, "score": 0.9, "source_type": "sei", "metadata": {}},
                {"text": long_text, "score": 0.8, "source_type": "sei", "metadata": {}},
            ],
            "results_rag_global": [],
            "results_web": [],
            "results_juris": [],
        }

        result = await merge_research_results(state)

        assert len(result["merged_context"]) <= 2000  # Some buffer for headers

    @pytest.mark.asyncio
    async def test_merge_handles_empty_results(self, base_state):
        """Test that merge handles no results gracefully."""
        state = {
            **base_state,
            "results_rag_local": [],
            "results_rag_global": [],
            "results_web": [],
            "results_juris": [],
        }

        result = await merge_research_results(state)

        assert "Nenhum resultado" in result["merged_context"]
        assert result["citations_map"] == {}


# =============================================================================
# PARALLEL EXECUTION TESTS
# =============================================================================

class TestParallelSearchNode:
    """Tests for parallel_search_node."""

    @pytest.mark.asyncio
    async def test_parallel_search_executes_all(self, base_state):
        """Test that parallel search executes all searches."""
        with patch(
            "app.services.ai.langgraph.subgraphs.parallel_research._get_rag_manager",
            return_value=None
        ), patch(
            "app.services.ai.langgraph.subgraphs.parallel_research._get_web_search_service",
            return_value=None
        ), patch(
            "app.services.ai.langgraph.subgraphs.parallel_research._get_jurisprudence_service",
            return_value=None
        ):
            result = await parallel_search_node(base_state)

        assert "parallel_search_latency_ms" in result["metrics"]

    @pytest.mark.asyncio
    async def test_parallel_search_handles_errors(self, base_state):
        """Test that parallel search handles individual search failures."""
        mock_rag = MagicMock()
        mock_rag.hybrid_search.side_effect = Exception("RAG error")

        with patch(
            "app.services.ai.langgraph.subgraphs.parallel_research._get_rag_manager",
            return_value=mock_rag
        ), patch(
            "app.services.ai.langgraph.subgraphs.parallel_research._get_web_search_service",
            return_value=None
        ), patch(
            "app.services.ai.langgraph.subgraphs.parallel_research._get_jurisprudence_service",
            return_value=None
        ):
            # Should not raise, errors are captured
            result = await parallel_search_node(base_state)

        assert "rag_local_error" in result["metrics"]


# =============================================================================
# SUBGRAPH TESTS
# =============================================================================

class TestSubgraph:
    """Tests for the complete subgraph."""

    def test_create_subgraph(self):
        """Test subgraph creation."""
        subgraph = create_parallel_research_subgraph()

        assert subgraph is not None

    @pytest.mark.asyncio
    async def test_run_parallel_research_integration(self):
        """Integration test for run_parallel_research."""
        with patch(
            "app.services.ai.langgraph.subgraphs.parallel_research._get_rag_manager",
            return_value=None
        ), patch(
            "app.services.ai.langgraph.subgraphs.parallel_research._get_web_search_service",
            return_value=None
        ), patch(
            "app.services.ai.langgraph.subgraphs.parallel_research._get_jurisprudence_service",
            return_value=None
        ):
            result = await run_parallel_research(
                query="teste de responsabilidade civil",
                section_title="Fundamentos",
                thesis="Tese de teste",
                tenant_id="test-tenant",
                top_k=3,
            )

        assert "merged_context" in result
        assert "citations_map" in result
        assert "sources_used" in result
        assert "metrics" in result


# =============================================================================
# STATE TESTS
# =============================================================================

class TestResearchState:
    """Tests for ResearchState TypedDict."""

    def test_state_has_required_fields(self, base_state):
        """Test that state has all required fields."""
        required_fields = [
            "query",
            "top_k",
            "max_context_chars",
            "results_rag_local",
            "results_rag_global",
            "results_web",
            "results_juris",
            "merged_context",
            "citations_map",
            "sources_used",
            "metrics",
        ]

        for field in required_fields:
            assert field in base_state

    def test_state_default_values(self, base_state):
        """Test state default values."""
        assert base_state["top_k"] == 5
        assert base_state["max_context_chars"] == 10000
        assert base_state["results_rag_local"] == []
        assert base_state["citations_map"] == {}
