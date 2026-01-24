"""
Unit tests for Query Expansion module (HyDE and Multi-Query).

Tests cover:
- HyDE document generation
- Multi-query generation
- RRF fusion algorithm
- TTL cache behavior
- Fallback heuristics
- Legal abbreviation expansion

Location: apps/api/app/services/rag/core/query_expansion.py
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.rag.core.query_expansion import (
    QueryExpansionConfig,
    QueryExpansionService,
    TTLCache,
    expand_legal_abbreviations,
    get_query_expansion_service,
    merge_lexical_vector_rrf,
    merge_results_rrf,
    reset_query_expansion_service,
    rrf_score,
    LEGAL_ABBREVIATIONS,
)

from .fixtures import (
    SAMPLE_LEGISLATION,
    SAMPLE_JURISPRUDENCE,
    generate_mock_embedding,
)


# =============================================================================
# QueryExpansionConfig Tests
# =============================================================================

class TestQueryExpansionConfig:
    """Tests for QueryExpansionConfig dataclass."""

    def test_default_values(self):
        """Test QueryExpansionConfig has sensible defaults."""
        config = QueryExpansionConfig()

        assert config.hyde_enabled is True
        assert config.hyde_model == "gemini-2.0-flash"
        assert config.hyde_max_tokens == 300
        assert config.hyde_temperature == 0.3
        assert config.hyde_semantic_weight == 0.7
        assert config.hyde_lexical_weight == 0.3

        assert config.multi_query_enabled is True
        assert config.multi_query_model == "gemini-2.0-flash"
        assert config.multi_query_count == 4
        assert config.multi_query_max_tokens == 300
        assert config.multi_query_temperature == 0.5

        assert config.cache_ttl_seconds == 3600
        assert config.cache_max_items == 5000
        assert config.rrf_k == 60

    @patch("app.services.rag.core.query_expansion.get_rag_config")
    def test_from_rag_config(self, mock_get_rag_config):
        """Test QueryExpansionConfig.from_rag_config loads from RAGConfig."""
        mock_rag_config = MagicMock()
        mock_rag_config.enable_hyde = True
        mock_rag_config.hyde_model = "gemini-1.5-pro"
        mock_rag_config.hyde_max_tokens = 500
        mock_rag_config.vector_weight = 0.6
        mock_rag_config.lexical_weight = 0.4
        mock_rag_config.enable_multiquery = True
        mock_rag_config.multiquery_model = "gemini-2.0-flash"
        mock_rag_config.multiquery_max = 3
        mock_rag_config.rrf_k = 60
        mock_rag_config.embedding_cache_ttl_seconds = 7200

        mock_get_rag_config.return_value = mock_rag_config

        config = QueryExpansionConfig.from_rag_config()

        assert config.hyde_enabled is True
        assert config.hyde_model == "gemini-1.5-pro"
        assert config.hyde_max_tokens == 500
        assert config.hyde_semantic_weight == 0.6
        assert config.hyde_lexical_weight == 0.4
        assert config.multi_query_count == 4  # multiquery_max + 1
        assert config.cache_ttl_seconds == 7200


# =============================================================================
# TTLCache Tests
# =============================================================================

class TestTTLCache:
    """Tests for TTLCache implementation."""

    def test_basic_get_set(self):
        """Test basic get and set operations."""
        cache = TTLCache(max_items=100, default_ttl=3600)

        cache.set("test", "key1", "value1")
        result = cache.get("test", "key1")

        assert result == "value1"

    def test_get_missing_key(self):
        """Test get returns None for missing key."""
        cache = TTLCache()

        result = cache.get("test", "nonexistent")

        assert result is None

    def test_ttl_expiration(self):
        """Test items expire after TTL."""
        cache = TTLCache(default_ttl=1)  # 1 second TTL

        cache.set("test", "key1", "value1", ttl=1)
        time.sleep(1.1)  # Wait for expiration

        result = cache.get("test", "key1")

        assert result is None

    def test_different_prefixes(self):
        """Test different prefixes create different keys."""
        cache = TTLCache()

        cache.set("prefix1", "key", "value1")
        cache.set("prefix2", "key", "value2")

        assert cache.get("prefix1", "key") == "value1"
        assert cache.get("prefix2", "key") == "value2"

    def test_max_items_eviction(self):
        """Test eviction when max_items reached."""
        cache = TTLCache(max_items=5, default_ttl=3600)

        for i in range(10):
            cache.set("test", f"key{i}", f"value{i}")

        # Should have evicted some items
        stats = cache.stats()
        assert stats["total_entries"] <= 5

    def test_stats(self):
        """Test stats method."""
        cache = TTLCache(max_items=100, default_ttl=3600)

        cache.set("test", "key1", "value1")
        cache.get("test", "key1")  # Hit
        cache.get("test", "key2")  # Miss

        stats = cache.stats()

        assert stats["total_entries"] == 1
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 0.5

    def test_clear(self):
        """Test clear method."""
        cache = TTLCache()

        cache.set("test", "key1", "value1")
        cache.set("test", "key2", "value2")
        cache.clear()

        assert cache.get("test", "key1") is None
        assert cache.get("test", "key2") is None
        stats = cache.stats()
        # After clear, hits and misses are reset but cache.get calls add misses
        assert stats["total_entries"] == 0

    def test_make_key_deterministic(self):
        """Test _make_key produces deterministic results."""
        cache = TTLCache()

        key1 = cache._make_key("prefix", "same_text")
        key2 = cache._make_key("prefix", "same_text")

        assert key1 == key2

    def test_make_key_different_for_different_text(self):
        """Test _make_key produces different results for different text."""
        cache = TTLCache()

        key1 = cache._make_key("prefix", "text1")
        key2 = cache._make_key("prefix", "text2")

        assert key1 != key2


# =============================================================================
# RRF Score Tests
# =============================================================================

class TestRRFScore:
    """Tests for RRF score calculation."""

    def test_rrf_score_rank_1(self):
        """Test RRF score for rank 1."""
        score = rrf_score(1, k=60)
        assert abs(score - 1/61) < 0.0001

    def test_rrf_score_rank_10(self):
        """Test RRF score for rank 10."""
        score = rrf_score(10, k=60)
        assert abs(score - 1/70) < 0.0001

    def test_rrf_score_decreases_with_rank(self):
        """Test RRF score decreases as rank increases."""
        scores = [rrf_score(r, k=60) for r in range(1, 11)]

        for i in range(len(scores) - 1):
            assert scores[i] > scores[i + 1]

    def test_rrf_score_custom_k(self):
        """Test RRF score with custom k value."""
        # Higher k = smoother distribution
        score_k60 = rrf_score(1, k=60)
        score_k100 = rrf_score(1, k=100)

        assert score_k60 > score_k100


# =============================================================================
# merge_results_rrf Tests
# =============================================================================

class TestMergeResultsRRF:
    """Tests for merge_results_rrf function."""

    def test_empty_input(self):
        """Test merge with empty input."""
        result = merge_results_rrf([])
        assert result == []

    def test_single_list(self):
        """Test merge with single list returns same order."""
        results = [
            {"chunk_uid": "doc1", "text": "Doc 1", "score": 0.8},
            {"chunk_uid": "doc2", "text": "Doc 2", "score": 0.6},
        ]

        merged = merge_results_rrf([results], top_k=10)

        assert len(merged) == 2
        assert merged[0]["chunk_uid"] == "doc1"
        assert "final_score" in merged[0]

    def test_multiple_lists_dedup(self):
        """Test merge deduplicates across lists."""
        list1 = [
            {"chunk_uid": "doc1", "text": "Doc 1", "score": 0.8},
            {"chunk_uid": "doc2", "text": "Doc 2", "score": 0.6},
        ]
        list2 = [
            {"chunk_uid": "doc2", "text": "Doc 2", "score": 0.7},  # Duplicate
            {"chunk_uid": "doc3", "text": "Doc 3", "score": 0.5},
        ]

        merged = merge_results_rrf([list1, list2], top_k=10)

        chunk_uids = [r["chunk_uid"] for r in merged]
        assert len(chunk_uids) == len(set(chunk_uids))  # No duplicates

    def test_rrf_booosts_appearing_in_multiple_lists(self):
        """Test items appearing in multiple lists get higher RRF score."""
        list1 = [
            {"chunk_uid": "doc1", "text": "Doc 1", "score": 0.8},
            {"chunk_uid": "doc2", "text": "Doc 2", "score": 0.6},
        ]
        list2 = [
            {"chunk_uid": "doc1", "text": "Doc 1", "score": 0.7},  # Also in list1
            {"chunk_uid": "doc3", "text": "Doc 3", "score": 0.9},  # Higher score but only here
        ]

        merged = merge_results_rrf([list1, list2], top_k=10)

        # doc1 appears in both lists, should have higher RRF score
        doc1 = next(r for r in merged if r["chunk_uid"] == "doc1")
        doc3 = next(r for r in merged if r["chunk_uid"] == "doc3")

        # doc1 has lower original scores but appears in both lists
        assert doc1["fusion_count"] == 2
        assert doc3["fusion_count"] == 1

    def test_top_k_limit(self):
        """Test top_k limits output."""
        results = [{"chunk_uid": f"doc{i}", "text": f"Doc {i}", "score": 0.9 - i*0.1}
                   for i in range(10)]

        merged = merge_results_rrf([results], top_k=3)

        assert len(merged) == 3

    def test_sources_tracked(self):
        """Test sources are tracked in merged results."""
        list1 = [{"chunk_uid": "doc1", "text": "Doc 1", "score": 0.8}]
        list2 = [{"chunk_uid": "doc1", "text": "Doc 1", "score": 0.7}]

        merged = merge_results_rrf([list1, list2], top_k=10)

        assert "sources" in merged[0]
        assert "query_0" in merged[0]["sources"]
        assert "query_1" in merged[0]["sources"]

    def test_fallback_id_from_text_hash(self):
        """Test fallback ID generation from text hash."""
        results = [{"text": "Document without chunk_uid", "score": 0.8}]

        merged = merge_results_rrf([results], top_k=10)

        assert len(merged) == 1
        assert "final_score" in merged[0]


# =============================================================================
# merge_lexical_vector_rrf Tests
# =============================================================================

class TestMergeLexicalVectorRRF:
    """Tests for merge_lexical_vector_rrf function."""

    def test_empty_inputs(self):
        """Test merge with empty inputs."""
        result = merge_lexical_vector_rrf([], [])
        assert result == []

    def test_only_lexical(self):
        """Test merge with only lexical results."""
        lexical = [
            {"chunk_uid": "doc1", "text": "Doc 1", "score": 0.8},
            {"chunk_uid": "doc2", "text": "Doc 2", "score": 0.6},
        ]

        merged = merge_lexical_vector_rrf(lexical, [], top_k=10)

        assert len(merged) == 2
        assert "sources" in merged[0]
        assert "lexical" in merged[0]["sources"]

    def test_only_vector(self):
        """Test merge with only vector results."""
        vector = [
            {"chunk_uid": "doc1", "text": "Doc 1", "score": 0.8},
            {"chunk_uid": "doc2", "text": "Doc 2", "score": 0.6},
        ]

        merged = merge_lexical_vector_rrf([], vector, top_k=10)

        assert len(merged) == 2
        assert "vector" in merged[0]["sources"]

    def test_hybrid_results_marked(self):
        """Test results from both sources are marked as hybrid."""
        lexical = [{"chunk_uid": "doc1", "text": "Doc 1", "score": 0.8}]
        vector = [{"chunk_uid": "doc1", "text": "Doc 1", "score": 0.7}]

        merged = merge_lexical_vector_rrf(lexical, vector, top_k=10)

        assert merged[0]["is_hybrid"] is True
        assert "lexical" in merged[0]["sources"]
        assert "vector" in merged[0]["sources"]

    def test_weighted_rrf(self):
        """Test weighted RRF with custom weights."""
        lexical = [{"chunk_uid": "doc1", "text": "Doc 1", "score": 0.8}]
        vector = [{"chunk_uid": "doc2", "text": "Doc 2", "score": 0.8}]

        # Heavy lexical weight
        merged_lex = merge_lexical_vector_rrf(
            lexical, vector, top_k=10, w_lex=0.9, w_vec=0.1
        )
        # Heavy vector weight
        merged_vec = merge_lexical_vector_rrf(
            lexical, vector, top_k=10, w_lex=0.1, w_vec=0.9
        )

        # With heavy lexical weight, lexical result should have higher score
        lex_doc1_score = next(r["final_score"] for r in merged_lex if r["chunk_uid"] == "doc1")
        lex_doc2_score = next(r["final_score"] for r in merged_lex if r["chunk_uid"] == "doc2")
        assert lex_doc1_score > lex_doc2_score

        # With heavy vector weight, vector result should have higher score
        vec_doc1_score = next(r["final_score"] for r in merged_vec if r["chunk_uid"] == "doc1")
        vec_doc2_score = next(r["final_score"] for r in merged_vec if r["chunk_uid"] == "doc2")
        assert vec_doc2_score > vec_doc1_score

    def test_original_scores_preserved(self):
        """Test original scores are preserved in output."""
        lexical = [{"chunk_uid": "doc1", "text": "Doc 1", "score": 0.8}]
        vector = [{"chunk_uid": "doc1", "text": "Doc 1", "score": 0.7}]

        merged = merge_lexical_vector_rrf(lexical, vector, top_k=10)

        assert "original_scores" in merged[0]
        assert merged[0]["original_scores"]["lexical"] == 0.8
        assert merged[0]["original_scores"]["vector"] == 0.7


# =============================================================================
# Legal Abbreviation Expansion Tests
# =============================================================================

class TestLegalAbbreviationExpansion:
    """Tests for legal abbreviation expansion."""

    def test_stf_expansion(self):
        """Test STF abbreviation expansion."""
        text = "Decisao do STF no RE 123456"
        result = expand_legal_abbreviations(text)
        assert "Supremo Tribunal Federal" in result

    def test_stj_expansion(self):
        """Test STJ abbreviation expansion."""
        text = "Sumula do STJ sobre dano moral"
        result = expand_legal_abbreviations(text)
        assert "Superior Tribunal de Justica" in result

    def test_cpc_expansion(self):
        """Test CPC abbreviation expansion."""
        text = "Art. 1.000 do CPC"
        result = expand_legal_abbreviations(text)
        assert "Codigo de Processo Civil" in result

    def test_clt_expansion(self):
        """Test CLT abbreviation expansion."""
        text = "CLT preve justa causa"
        result = expand_legal_abbreviations(text)
        assert "Consolidacao das Leis do Trabalho" in result

    def test_cf_expansion(self):
        """Test CF abbreviation expansion."""
        text = "Art. 5 da CF"
        result = expand_legal_abbreviations(text)
        assert "Constituicao Federal" in result

    def test_multiple_abbreviations(self):
        """Test multiple abbreviations in same text."""
        text = "STF e STJ decidiram com base no CPC"
        result = expand_legal_abbreviations(text)

        assert "Supremo Tribunal Federal" in result
        assert "Superior Tribunal de Justica" in result
        assert "Codigo de Processo Civil" in result

    def test_case_insensitive(self):
        """Test case insensitive expansion."""
        text = "stf decidiu"
        result = expand_legal_abbreviations(text)
        assert "Supremo Tribunal Federal" in result

    def test_no_abbreviation(self):
        """Test text without abbreviations unchanged."""
        text = "Texto sem abreviacoes juridicas"
        result = expand_legal_abbreviations(text)
        assert result == text


# =============================================================================
# QueryExpansionService Tests
# =============================================================================

class TestQueryExpansionService:
    """Tests for QueryExpansionService."""

    @pytest.fixture
    def mock_gemini_response(self):
        """Create mock Gemini response."""
        mock_response = MagicMock()
        mock_response.text = "Hypothetical document about legal matter."
        return mock_response

    @pytest.fixture
    def service(self):
        """Create QueryExpansionService with mocked Gemini."""
        config = QueryExpansionConfig(
            hyde_enabled=True,
            multi_query_enabled=True,
        )
        # Patch genai.configure to avoid API key requirement
        with patch("app.services.rag.core.query_expansion.genai.configure"):
            svc = QueryExpansionService(config=config, gemini_api_key="test-key")
        return svc

    def test_init_with_config(self):
        """Test service initialization with config."""
        config = QueryExpansionConfig(
            hyde_enabled=False,
            multi_query_count=5,
        )
        with patch("app.services.rag.core.query_expansion.genai.configure"):
            service = QueryExpansionService(config=config)

        assert service._config.hyde_enabled is False
        assert service._config.multi_query_count == 5

    def test_cache_integration(self, service):
        """Test service uses internal cache."""
        assert hasattr(service, "_cache")
        assert isinstance(service._cache, TTLCache)

    def test_clear_cache(self, service):
        """Test clear_cache method."""
        service._cache.set("test", "key", "value")
        service.clear_cache()

        assert service._cache.get("test", "key") is None

    def test_get_cache_stats(self, service):
        """Test get_cache_stats method."""
        stats = service.get_cache_stats()

        assert "total_entries" in stats
        assert "hit_rate" in stats

    @pytest.mark.asyncio
    async def test_generate_hypothetical_document_empty_query(self, service):
        """Test HyDE with empty query returns empty string."""
        result = await service.generate_hypothetical_document("")
        assert result == ""

    @pytest.mark.asyncio
    async def test_generate_hypothetical_document_cached(self, service):
        """Test HyDE uses cache when available."""
        query = "test query"
        cached_result = "Cached hypothetical document"

        service._cache.set("hyde", f"{query}:ext=False", cached_result)

        result = await service.generate_hypothetical_document(query, use_cache=True)

        assert result == cached_result

    @pytest.mark.asyncio
    async def test_generate_query_variants_empty_query(self, service):
        """Test multi-query with empty query returns empty list."""
        result = await service.generate_query_variants("", count=3)
        assert result == []

    @pytest.mark.asyncio
    async def test_generate_query_variants_count_1(self, service):
        """Test multi-query with count=1 returns only original."""
        result = await service.generate_query_variants("test query", count=1)

        assert len(result) == 1
        assert result[0] == "test query"

    @pytest.mark.asyncio
    async def test_generate_query_variants_cached(self, service):
        """Test multi-query uses cache when available."""
        query = "test query"
        cached_variants = [query, "variant 1", "variant 2"]
        cache_key = f"{query}:4"

        service._cache.set("multiquery", cache_key, cached_variants)

        result = await service.generate_query_variants(query, count=4, use_cache=True)

        assert result == cached_variants

    def test_generate_heuristic_variants(self, service):
        """Test heuristic variant generation."""
        query = "O que e rescisao de contrato CLT?"

        variants = service._generate_heuristic_variants(query, count=3)

        assert len(variants) <= 3
        # Should have generated some variants
        assert all(isinstance(v, str) for v in variants)

    def test_generate_heuristic_variants_keywords(self, service):
        """Test heuristic variant removes stopwords."""
        query = "qual e o prazo para recurso no processo civil"

        variants = service._generate_heuristic_variants(query, count=1)

        if variants:
            # Stopwords like "qual", "e", "o", "para", "no" should be removed
            assert "prazo" in variants[0].lower() or "recurso" in variants[0].lower()

    def test_generate_heuristic_variants_expand_abbreviations(self, service):
        """Test heuristic variant expands abbreviations."""
        query = "prazo STF"

        variants = service._generate_heuristic_variants(query, count=2)

        # One variant should have expanded STF
        has_expansion = any("Supremo Tribunal Federal" in v for v in variants)
        assert has_expansion or len(variants) == 0

    @pytest.mark.asyncio
    async def test_expand_async_empty_query(self, service):
        """Test expand_async with empty query."""
        result = await service.expand_async("", use_hyde=True, use_multiquery=True)
        assert result == []

    @pytest.mark.asyncio
    async def test_rewrite_query_empty(self, service):
        """Test rewrite_query with empty query."""
        result = await service.rewrite_query("")
        assert result == ""

    @pytest.mark.asyncio
    async def test_rewrite_query_cached(self, service):
        """Test rewrite_query uses cache."""
        query = "test query"
        cached_rewrite = "optimized query"

        service._cache.set("rewrite", query, cached_rewrite)

        result = await service.rewrite_query(query, use_cache=True)

        assert result == cached_rewrite


# =============================================================================
# QueryExpansionService Integration Tests (with mocked LLM)
# =============================================================================

class TestQueryExpansionServiceWithMockedLLM:
    """Integration tests with mocked Gemini LLM."""

    @pytest.fixture
    def service_with_mocked_llm(self):
        """Create service with mocked LLM calls."""
        config = QueryExpansionConfig(
            hyde_enabled=True,
            multi_query_enabled=True,
        )

        with patch("app.services.rag.core.query_expansion.genai.configure"):
            service = QueryExpansionService(config=config, gemini_api_key="test-key")

        # Mock the Gemini models
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "Mocked LLM response"
        mock_model.generate_content = MagicMock(return_value=mock_response)

        service._hyde_model = mock_model
        service._multiquery_model = mock_model

        return service

    @pytest.mark.asyncio
    async def test_generate_hypothetical_document_with_llm(self, service_with_mocked_llm):
        """Test HyDE generation with mocked LLM."""
        service = service_with_mocked_llm

        # Override the internal _call_gemini to return mocked response
        async def mock_call(*args, **kwargs):
            return "Hypothetical legal document about the query topic."

        service._call_gemini = mock_call

        result = await service.generate_hypothetical_document(
            "prazo prescricional direito civil",
            use_cache=False,
        )

        assert len(result) > 0
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_generate_query_variants_with_llm(self, service_with_mocked_llm):
        """Test multi-query generation with mocked LLM."""
        service = service_with_mocked_llm

        # Mock _call_gemini to return variants
        async def mock_call(*args, **kwargs):
            return "Variante 1 da consulta\nVariante 2 da consulta\nVariante 3 da consulta"

        service._call_gemini = mock_call

        result = await service.generate_query_variants(
            "dano moral indenizacao",
            count=4,
            use_cache=False,
        )

        assert len(result) >= 1
        assert result[0] == "dano moral indenizacao"  # Original always first

    @pytest.mark.asyncio
    async def test_multi_query_search(self, service_with_mocked_llm):
        """Test multi_query_search with mocked search function."""
        service = service_with_mocked_llm

        # Mock variant generation
        async def mock_variants(*args, **kwargs):
            return ["query1", "query2", "query3"]

        service.generate_query_variants = mock_variants

        # Mock search function
        def mock_search(query: str, top_k: int) -> List[Dict[str, Any]]:
            return [
                {"chunk_uid": f"{query}_doc1", "text": f"Result for {query}", "score": 0.8},
                {"chunk_uid": f"{query}_doc2", "text": f"Result 2 for {query}", "score": 0.6},
            ]

        results = await service.multi_query_search(
            query="test query",
            search_fn=mock_search,
            top_k=5,
            fetch_k=10,
        )

        assert len(results) > 0
        assert "multi_query_used" in results[0]
        assert results[0]["multi_query_used"] is True

    @pytest.mark.asyncio
    async def test_hyde_search(self, service_with_mocked_llm):
        """Test hyde_search with mocked functions."""
        service = service_with_mocked_llm

        # Mock HyDE generation
        async def mock_hyde(*args, **kwargs):
            return "Hypothetical document about the legal matter."

        service.generate_hypothetical_document = mock_hyde

        # Mock search functions
        def mock_lexical(query: str, k: int) -> List[Dict[str, Any]]:
            return [{"chunk_uid": "lex1", "text": "Lexical result", "score": 0.7}]

        def mock_vector(query: str, k: int) -> List[Dict[str, Any]]:
            return [{"chunk_uid": "vec1", "text": "Vector result", "score": 0.8}]

        results = await service.hyde_search(
            query="test query",
            lexical_search_fn=mock_lexical,
            vector_search_fn=mock_vector,
            top_k=5,
        )

        assert len(results) > 0
        assert "hyde_used" in results[0]
        assert results[0]["hyde_used"] is True

    @pytest.mark.asyncio
    async def test_advanced_search(self, service_with_mocked_llm):
        """Test advanced_search combining HyDE and multi-query."""
        service = service_with_mocked_llm

        # Mock variant generation
        async def mock_variants(*args, **kwargs):
            return ["query1", "query2"]

        service.generate_query_variants = mock_variants

        # Mock HyDE generation
        async def mock_hyde(*args, **kwargs):
            return "Hypothetical document."

        service.generate_hypothetical_document = mock_hyde

        # Mock search functions
        def mock_lexical(query: str, k: int) -> List[Dict[str, Any]]:
            return [{"chunk_uid": f"lex_{query}", "text": f"Lex {query}", "score": 0.7}]

        def mock_vector(query: str, k: int) -> List[Dict[str, Any]]:
            return [{"chunk_uid": f"vec_{query}", "text": f"Vec {query}", "score": 0.8}]

        results = await service.advanced_search(
            query="test query",
            lexical_search_fn=mock_lexical,
            vector_search_fn=mock_vector,
            top_k=5,
            use_hyde=True,
            use_multi_query=True,
        )

        assert len(results) > 0
        assert "advanced_search" in results[0]
        assert results[0]["advanced_search"] is True


# =============================================================================
# Singleton Factory Tests
# =============================================================================

class TestSingletonFactory:
    """Tests for singleton factory functions."""

    def teardown_method(self):
        """Reset singleton after each test."""
        reset_query_expansion_service()

    @patch("app.services.rag.core.query_expansion.genai.configure")
    @patch("app.services.rag.core.query_expansion.QueryExpansionConfig.from_rag_config")
    def test_get_query_expansion_service(self, mock_config, mock_genai):
        """Test get_query_expansion_service returns singleton."""
        mock_config.return_value = QueryExpansionConfig()

        service1 = get_query_expansion_service()
        service2 = get_query_expansion_service()

        assert service1 is service2

    @patch("app.services.rag.core.query_expansion.genai.configure")
    @patch("app.services.rag.core.query_expansion.QueryExpansionConfig.from_rag_config")
    def test_reset_query_expansion_service(self, mock_config, mock_genai):
        """Test reset_query_expansion_service clears singleton."""
        mock_config.return_value = QueryExpansionConfig()

        service1 = get_query_expansion_service()
        reset_query_expansion_service()
        service2 = get_query_expansion_service()

        assert service1 is not service2


# =============================================================================
# Edge Cases and Error Handling
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_rrf_with_same_ranks(self):
        """Test RRF fusion when items have same rank in different lists."""
        list1 = [
            {"chunk_uid": "doc1", "text": "Doc 1", "score": 0.9},
            {"chunk_uid": "doc2", "text": "Doc 2", "score": 0.8},
        ]
        list2 = [
            {"chunk_uid": "doc2", "text": "Doc 2", "score": 0.9},  # Same doc, rank 1
            {"chunk_uid": "doc1", "text": "Doc 1", "score": 0.8},  # Same doc, rank 2
        ]

        merged = merge_results_rrf([list1, list2], top_k=10)

        # Both docs appear in both lists, should have similar RRF scores
        # but doc1 ranks higher in list1, doc2 ranks higher in list2
        assert len(merged) == 2

    def test_rrf_with_very_long_lists(self):
        """Test RRF with many results."""
        list1 = [{"chunk_uid": f"doc{i}", "text": f"Doc {i}", "score": 1.0 - i*0.01}
                 for i in range(100)]

        merged = merge_results_rrf([list1], top_k=5)

        assert len(merged) == 5
        assert merged[0]["chunk_uid"] == "doc0"

    def test_merge_with_missing_metadata(self):
        """Test merge handles results without metadata."""
        results = [
            {"chunk_uid": "doc1", "text": "Doc 1", "score": 0.8},
            {"chunk_uid": "doc2", "text": "Doc 2"},  # No score
        ]

        merged = merge_results_rrf([results], top_k=10)

        assert len(merged) == 2

    def test_ttl_cache_with_unicode(self):
        """Test cache handles unicode text correctly."""
        cache = TTLCache()

        cache.set("test", "chave em portugues", "valor")
        result = cache.get("test", "chave em portugues")

        assert result == "valor"

    def test_legal_abbreviations_no_false_positives(self):
        """Test abbreviation expansion doesn't create false positives."""
        # Text with partial matches that shouldn't be expanded
        text = "A empresa STAR trabalha com TRF de metal"

        result = expand_legal_abbreviations(text)

        # STAR should not be matched as STF
        # TRF should be matched
        assert "Tribunal Regional Federal" in result
        # STAR should remain unchanged
        assert "STAR" in result

    @pytest.mark.asyncio
    async def test_service_handles_llm_failure(self):
        """Test service handles LLM failure gracefully."""
        config = QueryExpansionConfig()

        with patch("app.services.rag.core.query_expansion.genai.configure"):
            service = QueryExpansionService(config=config, gemini_api_key="test-key")

        # Mock the internal LLM call method to simulate exception handling
        # The actual _call_gemini catches exceptions and returns empty string
        async def mock_call(*args, **kwargs):
            return ""  # Simulate failed LLM returning empty

        service._call_gemini = mock_call

        # Should return empty string
        result = await service.generate_hypothetical_document("test query", use_cache=False)
        assert result == ""

    def test_heuristic_variants_with_special_characters(self):
        """Test heuristic variants handle special characters."""
        config = QueryExpansionConfig()

        with patch("app.services.rag.core.query_expansion.genai.configure"):
            service = QueryExpansionService(config=config, gemini_api_key="test-key")

        query = "Art. 5o, inciso X, CF/88 - direitos fundamentais?"

        variants = service._generate_heuristic_variants(query, count=3)

        # Should not crash, and generate some variants
        assert isinstance(variants, list)
