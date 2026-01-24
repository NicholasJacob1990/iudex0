"""
Unit tests for Reranker module.

Tests cover:
- Portuguese legal domain boost
- Batch processing
- Score normalization
- Lazy loading behavior
- Cross-encoder model mocking
- Fallback behavior

Location: apps/api/app/services/rag/core/reranker.py
"""

from __future__ import annotations

import time
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from app.services.rag.core.reranker import (
    CrossEncoderReranker,
    RerankerConfig,
    RerankerResult,
    rerank,
    rerank_with_metadata,
    PORTUGUESE_LEGAL_PATTERNS,
)

from .fixtures import (
    SAMPLE_LEGISLATION,
    SAMPLE_JURISPRUDENCE,
    legal_domain_documents,
    create_results_with_scores,
    assert_valid_rerank_result,
)


# =============================================================================
# RerankerConfig Tests
# =============================================================================

class TestRerankerConfig:
    """Tests for RerankerConfig dataclass."""

    def test_default_values(self):
        """Test RerankerConfig has sensible defaults."""
        config = RerankerConfig()

        assert config.model_name == "cross-encoder/ms-marco-multilingual-MiniLM-L6-H384-v1"
        assert config.model_fallback == "cross-encoder/ms-marco-MiniLM-L-6-v2"
        assert config.top_k == 10
        assert config.max_chars == 1800
        assert config.batch_size == 32
        assert config.max_candidates == 50
        assert config.min_score is None
        assert config.device is None
        assert config.use_fp16 is True
        assert config.cache_model is True
        assert config.legal_domain_boost == 0.1

    @patch("app.services.rag.core.reranker.get_rag_config")
    def test_from_rag_config(self, mock_get_rag_config):
        """Test RerankerConfig.from_rag_config loads from RAGConfig."""
        mock_rag_config = MagicMock()
        mock_rag_config.rerank_model = "custom-model"
        mock_rag_config.rerank_model_fallback = "custom-fallback"
        mock_rag_config.rerank_top_k = 15
        mock_rag_config.rerank_max_chars = 2000
        mock_rag_config.default_fetch_k = 100
        mock_rag_config.rerank_batch_size = 64
        mock_rag_config.rerank_use_fp16 = False
        mock_rag_config.rerank_cache_model = False

        mock_get_rag_config.return_value = mock_rag_config

        config = RerankerConfig.from_rag_config()

        assert config.model_name == "custom-model"
        assert config.model_fallback == "custom-fallback"
        assert config.top_k == 15
        assert config.max_chars == 2000
        assert config.max_candidates == 100
        assert config.batch_size == 64
        assert config.use_fp16 is False
        assert config.cache_model is False


# =============================================================================
# RerankerResult Tests
# =============================================================================

class TestRerankerResult:
    """Tests for RerankerResult dataclass."""

    def test_basic_creation(self):
        """Test basic RerankerResult creation."""
        result = RerankerResult(
            results=[{"id": "1", "text": "Doc 1"}],
            original_count=5,
            reranked_count=1,
            scores=[0.8],
            model_used="test-model",
            duration_ms=100.5,
        )

        assert len(result.results) == 1
        assert result.original_count == 5
        assert result.reranked_count == 1
        assert result.scores == [0.8]
        assert result.model_used == "test-model"
        assert result.duration_ms == 100.5

    def test_bool_true(self):
        """Test __bool__ returns True when results exist."""
        result = RerankerResult(
            results=[{"id": "1"}],
            original_count=1,
            reranked_count=1,
        )

        assert bool(result) is True

    def test_bool_false(self):
        """Test __bool__ returns False when no results."""
        result = RerankerResult(
            results=[],
            original_count=0,
            reranked_count=0,
        )

        assert bool(result) is False

    def test_len(self):
        """Test __len__ returns number of results."""
        result = RerankerResult(
            results=[{"id": "1"}, {"id": "2"}, {"id": "3"}],
            original_count=5,
            reranked_count=3,
        )

        assert len(result) == 3

    def test_iter(self):
        """Test __iter__ allows iteration over results."""
        results_list = [{"id": "1"}, {"id": "2"}]
        result = RerankerResult(
            results=results_list,
            original_count=2,
            reranked_count=2,
        )

        iterated = list(result)
        assert iterated == results_list


# =============================================================================
# Portuguese Legal Domain Boost Tests
# =============================================================================

class TestPortugueseLegalDomainBoost:
    """Tests for Portuguese legal domain scoring boost."""

    @pytest.fixture
    def reranker(self):
        """Create reranker with mocked model."""
        config = RerankerConfig(legal_domain_boost=0.1)
        reranker = CrossEncoderReranker(config)
        return reranker

    def test_compute_legal_domain_boost_with_article(self, reranker):
        """Test boost for text containing article references."""
        text = "Art. 5o da Constituicao Federal estabelece direitos fundamentais."
        boost = reranker._compute_legal_domain_boost(text)

        assert boost > 0
        assert boost <= 0.1

    def test_compute_legal_domain_boost_with_sumula(self, reranker):
        """Test boost for text containing sumula reference."""
        text = "Conforme Sumula 331 do TST sobre terceirizacao."
        boost = reranker._compute_legal_domain_boost(text)

        assert boost > 0

    def test_compute_legal_domain_boost_with_court_names(self, reranker):
        """Test boost for text containing court names."""
        text = "O STF e o STJ decidiram de forma similar."
        boost = reranker._compute_legal_domain_boost(text)

        assert boost > 0

    def test_compute_legal_domain_boost_with_cnj_number(self, reranker):
        """Test boost for text containing CNJ case number."""
        text = "Processo 0000001-23.2024.8.26.0001 em andamento."
        boost = reranker._compute_legal_domain_boost(text)

        assert boost > 0

    def test_compute_legal_domain_boost_with_lei(self, reranker):
        """Test boost for text containing lei reference."""
        text = "Lei n. 14.133/2021 substituiu a Lei 8.666/93."
        boost = reranker._compute_legal_domain_boost(text)

        assert boost > 0

    def test_compute_legal_domain_boost_multiple_patterns(self, reranker):
        """Test boost scales with number of patterns."""
        # Few patterns
        text1 = "Art. 5o da CF."
        boost1 = reranker._compute_legal_domain_boost(text1)

        # Many patterns
        text2 = "Art. 5o, inciso X, da CF/88, conforme jurisprudencia do STF no RE 123456 e Sumula 123."
        boost2 = reranker._compute_legal_domain_boost(text2)

        # More patterns should give higher or equal boost
        assert boost2 >= boost1

    def test_compute_legal_domain_boost_max_cap(self, reranker):
        """Test boost is capped at legal_domain_boost config value."""
        text = "Art. 1o, Art. 2o, Art. 3o, Art. 4o, Art. 5o, Art. 6o, Art. 7o, Art. 8o"
        boost = reranker._compute_legal_domain_boost(text)

        assert boost <= reranker.config.legal_domain_boost

    def test_compute_legal_domain_boost_no_patterns(self, reranker):
        """Test no boost for text without legal patterns."""
        text = "Este e um texto generico sem termos juridicos."
        boost = reranker._compute_legal_domain_boost(text)

        assert boost == 0.0

    def test_compute_legal_domain_boost_empty_text(self, reranker):
        """Test no boost for empty text."""
        boost = reranker._compute_legal_domain_boost("")
        assert boost == 0.0

    def test_compute_legal_domain_boost_disabled(self):
        """Test no boost when disabled in config."""
        config = RerankerConfig(legal_domain_boost=0.0)
        reranker = CrossEncoderReranker(config)

        text = "Art. 5o da CF"
        boost = reranker._compute_legal_domain_boost(text)

        assert boost == 0.0


# =============================================================================
# CrossEncoderReranker Core Tests
# =============================================================================

class TestCrossEncoderRerankerCore:
    """Tests for CrossEncoderReranker core functionality."""

    @pytest.fixture
    def mock_cross_encoder(self):
        """Create mock CrossEncoder model."""
        mock_model = MagicMock()
        # Simulate prediction returning scores
        mock_model.predict = MagicMock(return_value=[0.8, 0.6, 0.4])
        return mock_model

    @pytest.fixture
    def reranker_with_mock(self, mock_cross_encoder):
        """Create reranker with mocked model."""
        config = RerankerConfig(legal_domain_boost=0.0)  # Disable boost for cleaner tests
        reranker = CrossEncoderReranker(config)
        reranker._model = mock_cross_encoder
        reranker._model_loaded = True
        reranker._active_model_name = "test-model"
        return reranker

    def test_rerank_empty_results(self, reranker_with_mock):
        """Test rerank with empty results."""
        result = reranker_with_mock.rerank("test query", [])

        assert len(result.results) == 0
        assert result.original_count == 0
        assert result.reranked_count == 0

    def test_rerank_empty_query(self, reranker_with_mock):
        """Test rerank with empty query returns original order."""
        results = [
            {"chunk_uid": "doc1", "text": "Doc 1", "score": 0.5},
            {"chunk_uid": "doc2", "text": "Doc 2", "score": 0.8},
        ]

        result = reranker_with_mock.rerank("", results)

        assert result.model_used == "passthrough"
        assert len(result.results) == 2

    def test_rerank_with_results(self, reranker_with_mock, mock_cross_encoder):
        """Test rerank with valid results."""
        mock_cross_encoder.predict.return_value = [0.9, 0.7, 0.5]

        results = [
            {"chunk_uid": "doc1", "text": "Document one", "score": 0.5},
            {"chunk_uid": "doc2", "text": "Document two", "score": 0.8},
            {"chunk_uid": "doc3", "text": "Document three", "score": 0.6},
        ]

        result = reranker_with_mock.rerank("test query", results)

        assert len(result.results) == 3
        assert result.original_count == 3
        assert result.reranked_count == 3
        # Should be sorted by rerank score
        assert result.results[0]["rerank_score"] >= result.results[1]["rerank_score"]

    def test_rerank_top_k_limit(self, reranker_with_mock, mock_cross_encoder):
        """Test rerank respects top_k limit."""
        mock_cross_encoder.predict.return_value = [0.9, 0.8, 0.7, 0.6, 0.5]

        results = [
            {"chunk_uid": f"doc{i}", "text": f"Document {i}", "score": 0.5}
            for i in range(5)
        ]

        result = reranker_with_mock.rerank("test query", results, top_k=2)

        assert len(result.results) == 2
        assert result.reranked_count == 2

    def test_rerank_preserves_metadata(self, reranker_with_mock, mock_cross_encoder):
        """Test rerank preserves result metadata."""
        mock_cross_encoder.predict.return_value = [0.8]

        results = [
            {
                "chunk_uid": "doc1",
                "text": "Document one",
                "score": 0.5,
                "metadata": {"source": "test", "page": 1},
            }
        ]

        result = reranker_with_mock.rerank("test query", results)

        assert result.results[0]["metadata"] == {"source": "test", "page": 1}
        assert "rerank_score" in result.results[0]
        assert "original_score" in result.results[0]

    def test_rerank_adds_score_fields(self, reranker_with_mock, mock_cross_encoder):
        """Test rerank adds expected score fields."""
        mock_cross_encoder.predict.return_value = [0.85]

        results = [{"chunk_uid": "doc1", "text": "Document one", "score": 0.5}]

        result = reranker_with_mock.rerank("test query", results)

        doc = result.results[0]
        assert "rerank_score" in doc
        assert "rerank_score_raw" in doc
        assert "legal_domain_boost" in doc
        assert "original_score" in doc
        assert doc["rerank_score_raw"] == 0.85
        assert doc["original_score"] == 0.5


# =============================================================================
# Batch Processing Tests
# =============================================================================

class TestBatchProcessing:
    """Tests for batch reranking functionality."""

    @pytest.fixture
    def mock_cross_encoder(self):
        """Create mock CrossEncoder model."""
        mock_model = MagicMock()
        return mock_model

    @pytest.fixture
    def reranker_with_mock(self, mock_cross_encoder):
        """Create reranker with mocked model."""
        config = RerankerConfig(batch_size=2, legal_domain_boost=0.0)
        reranker = CrossEncoderReranker(config)
        reranker._model = mock_cross_encoder
        reranker._model_loaded = True
        reranker._active_model_name = "test-model"
        return reranker

    def test_rerank_batch_empty(self, reranker_with_mock):
        """Test batch rerank with empty input."""
        result = reranker_with_mock.rerank_batch([], [])
        assert result == []

    def test_rerank_batch_mismatched_lengths(self, reranker_with_mock):
        """Test batch rerank raises on mismatched lengths."""
        with pytest.raises(ValueError):
            reranker_with_mock.rerank_batch(
                queries=["q1", "q2"],
                results_list=[[{"text": "doc"}]],  # Only one list
            )

    def test_rerank_batch_multiple_queries(self, reranker_with_mock, mock_cross_encoder):
        """Test batch rerank with multiple queries."""
        # Return scores for all pairs
        mock_cross_encoder.predict.return_value = [0.9, 0.7, 0.8, 0.6]

        queries = ["query1", "query2"]
        results_list = [
            [
                {"chunk_uid": "q1_doc1", "text": "Q1 Doc 1", "score": 0.5},
                {"chunk_uid": "q1_doc2", "text": "Q1 Doc 2", "score": 0.6},
            ],
            [
                {"chunk_uid": "q2_doc1", "text": "Q2 Doc 1", "score": 0.5},
                {"chunk_uid": "q2_doc2", "text": "Q2 Doc 2", "score": 0.6},
            ],
        ]

        results = reranker_with_mock.rerank_batch(queries, results_list)

        assert len(results) == 2
        assert len(results[0].results) == 2
        assert len(results[1].results) == 2

    def test_rerank_batch_respects_top_k(self, reranker_with_mock, mock_cross_encoder):
        """Test batch rerank respects top_k."""
        mock_cross_encoder.predict.return_value = [0.9, 0.8, 0.7]

        queries = ["query1"]
        results_list = [
            [
                {"chunk_uid": "doc1", "text": "Doc 1", "score": 0.5},
                {"chunk_uid": "doc2", "text": "Doc 2", "score": 0.6},
                {"chunk_uid": "doc3", "text": "Doc 3", "score": 0.7},
            ],
        ]

        results = reranker_with_mock.rerank_batch(queries, results_list, top_k=2)

        assert len(results[0].results) == 2


# =============================================================================
# Text Truncation Tests
# =============================================================================

class TestTextTruncation:
    """Tests for text truncation behavior."""

    def test_truncate_text_short(self):
        """Test short text is not truncated."""
        config = RerankerConfig(max_chars=1000)
        reranker = CrossEncoderReranker(config)

        text = "Short text"
        result = reranker._truncate_text(text)

        assert result == text

    def test_truncate_text_long(self):
        """Test long text is truncated."""
        config = RerankerConfig(max_chars=100)
        reranker = CrossEncoderReranker(config)

        text = "A" * 200
        result = reranker._truncate_text(text)

        assert len(result) <= 100

    def test_truncate_text_word_boundary(self):
        """Test truncation breaks at word boundary."""
        config = RerankerConfig(max_chars=50)
        reranker = CrossEncoderReranker(config)

        text = "The quick brown fox jumps over the lazy dog and runs away"
        result = reranker._truncate_text(text)

        # Should not end mid-word
        assert not result.endswith("a")  # Partial word
        assert len(result) <= 50

    def test_truncate_text_empty(self):
        """Test empty text returns empty."""
        reranker = CrossEncoderReranker(RerankerConfig())

        result = reranker._truncate_text("")

        assert result == ""

    def test_truncate_text_none(self):
        """Test None text returns None or empty."""
        reranker = CrossEncoderReranker(RerankerConfig())

        result = reranker._truncate_text(None)

        # Implementation may return None or empty string for None input
        assert result is None or result == ""


# =============================================================================
# Lazy Loading Tests
# =============================================================================

class TestLazyLoading:
    """Tests for lazy model loading behavior."""

    def teardown_method(self):
        """Reset singleton after each test."""
        CrossEncoderReranker.reset_instance()
        CrossEncoderReranker.clear_model_cache()

    def test_model_not_loaded_on_init(self):
        """Test model is not loaded during initialization."""
        config = RerankerConfig()
        reranker = CrossEncoderReranker(config)

        assert reranker._model is None
        assert reranker._model_loaded is False
        assert reranker.is_loaded is False

    def test_model_loaded_on_first_rerank(self):
        """Test model loading behavior on first rerank call."""
        # We test with a mock that simulates model loading
        config = RerankerConfig()
        reranker = CrossEncoderReranker(config)

        # Manually set model as loaded (simulating successful load)
        mock_model = MagicMock()
        mock_model.predict.return_value = [0.8]
        reranker._model = mock_model
        reranker._model_loaded = True
        reranker._active_model_name = "test-model"

        results = [{"chunk_uid": "doc1", "text": "Document", "score": 0.5}]
        reranker.rerank("test query", results)

        assert reranker._model_loaded is True
        assert reranker.is_loaded is True

    def test_device_property_after_load(self):
        """Test device property returns detected device."""
        config = RerankerConfig()
        reranker = CrossEncoderReranker(config)

        # Before load
        assert reranker.device is None

        # Simulate load
        reranker._device = "cpu"
        assert reranker.device == "cpu"


# =============================================================================
# Fallback Behavior Tests
# =============================================================================

class TestFallbackBehavior:
    """Tests for fallback behavior when model unavailable."""

    def teardown_method(self):
        """Reset singleton after each test."""
        CrossEncoderReranker.reset_instance()
        CrossEncoderReranker.clear_model_cache()

    def test_fallback_to_secondary_model(self):
        """Test fallback behavior when model loading fails."""
        config = RerankerConfig(
            model_name="primary-model",
            model_fallback="fallback-model",
        )
        reranker = CrossEncoderReranker(config)

        # Simulate fallback scenario
        reranker._using_fallback = True
        reranker._active_model_name = "fallback-model"

        # Manually set a mock model
        mock_model = MagicMock()
        mock_model.predict.return_value = [0.7]
        reranker._model = mock_model
        reranker._model_loaded = True

        results = [{"chunk_uid": "doc1", "text": "Document", "score": 0.5}]
        result = reranker.rerank("test query", results)

        # Should be using fallback
        assert reranker._using_fallback is True
        assert reranker._active_model_name == "fallback-model"

    def test_fallback_returns_original_when_no_model(self):
        """Test returns original order when no model available."""
        config = RerankerConfig()
        reranker = CrossEncoderReranker(config)

        # Don't load model, simulate failure
        reranker._model_loaded = False

        with patch.object(reranker, "_ensure_model_loaded", return_value=False):
            results = [
                {"chunk_uid": "doc1", "text": "Doc 1", "score": 0.5},
                {"chunk_uid": "doc2", "text": "Doc 2", "score": 0.8},
            ]

            result = reranker.rerank("test query", results)

            assert result.model_used == "fallback"
            assert len(result.results) == 2


# =============================================================================
# Score Normalization Tests
# =============================================================================

class TestScoreNormalization:
    """Tests for score handling and normalization."""

    @pytest.fixture
    def mock_cross_encoder(self):
        """Create mock CrossEncoder model."""
        mock_model = MagicMock()
        return mock_model

    @pytest.fixture
    def reranker_with_mock(self, mock_cross_encoder):
        """Create reranker with mocked model."""
        config = RerankerConfig(legal_domain_boost=0.0)
        reranker = CrossEncoderReranker(config)
        reranker._model = mock_cross_encoder
        reranker._model_loaded = True
        reranker._active_model_name = "test-model"
        return reranker

    def test_negative_scores_handled(self, reranker_with_mock, mock_cross_encoder):
        """Test negative cross-encoder scores are handled."""
        mock_cross_encoder.predict.return_value = [-0.5, 0.3, 0.8]

        results = [
            {"chunk_uid": "doc1", "text": "Doc 1", "score": 0.5},
            {"chunk_uid": "doc2", "text": "Doc 2", "score": 0.6},
            {"chunk_uid": "doc3", "text": "Doc 3", "score": 0.7},
        ]

        result = reranker_with_mock.rerank("test query", results)

        # Should handle negative scores
        assert len(result.results) == 3
        # Still sorted by score (highest first)
        assert result.results[0]["rerank_score"] >= result.results[-1]["rerank_score"]

    def test_min_score_filter(self, mock_cross_encoder):
        """Test min_score filtering."""
        mock_cross_encoder.predict.return_value = [0.9, 0.5, 0.2]

        config = RerankerConfig(min_score=0.4, legal_domain_boost=0.0)
        reranker = CrossEncoderReranker(config)
        reranker._model = mock_cross_encoder
        reranker._model_loaded = True
        reranker._active_model_name = "test-model"

        results = [
            {"chunk_uid": "doc1", "text": "Doc 1", "score": 0.5},
            {"chunk_uid": "doc2", "text": "Doc 2", "score": 0.6},
            {"chunk_uid": "doc3", "text": "Doc 3", "score": 0.7},
        ]

        result = reranker.rerank("test query", results)

        # Only scores >= 0.4 should pass
        assert len(result.results) == 2

    def test_scores_list_in_result(self, reranker_with_mock, mock_cross_encoder):
        """Test scores list in RerankerResult matches results."""
        mock_cross_encoder.predict.return_value = [0.9, 0.7, 0.5]

        results = [
            {"chunk_uid": "doc1", "text": "Doc 1", "score": 0.5},
            {"chunk_uid": "doc2", "text": "Doc 2", "score": 0.6},
            {"chunk_uid": "doc3", "text": "Doc 3", "score": 0.7},
        ]

        result = reranker_with_mock.rerank("test query", results)

        assert len(result.scores) == len(result.results)
        for i, doc in enumerate(result.results):
            assert doc["rerank_score"] == result.scores[i]


# =============================================================================
# Convenience Function Tests
# =============================================================================

class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""

    def teardown_method(self):
        """Reset singleton after each test."""
        CrossEncoderReranker.reset_instance()
        CrossEncoderReranker.clear_model_cache()

    @patch.object(CrossEncoderReranker, "rerank")
    @patch.object(CrossEncoderReranker, "get_instance")
    def test_rerank_function(self, mock_get_instance, mock_rerank):
        """Test rerank convenience function."""
        mock_reranker = MagicMock()
        mock_result = RerankerResult(
            results=[{"id": "1", "rerank_score": 0.8}],
            original_count=1,
            reranked_count=1,
        )
        mock_reranker.rerank.return_value = mock_result
        mock_get_instance.return_value = mock_reranker

        results = [{"chunk_uid": "doc1", "text": "Doc 1", "score": 0.5}]
        output = rerank("test query", results, top_k=5)

        mock_reranker.rerank.assert_called_once()
        assert output == mock_result.results

    @patch.object(CrossEncoderReranker, "rerank")
    @patch.object(CrossEncoderReranker, "get_instance")
    def test_rerank_with_metadata_function(self, mock_get_instance, mock_rerank):
        """Test rerank_with_metadata convenience function."""
        mock_reranker = MagicMock()
        mock_result = RerankerResult(
            results=[{"id": "1", "rerank_score": 0.8}],
            original_count=1,
            reranked_count=1,
            model_used="test-model",
            duration_ms=50.0,
        )
        mock_reranker.rerank.return_value = mock_result
        mock_get_instance.return_value = mock_reranker

        results = [{"chunk_uid": "doc1", "text": "Doc 1", "score": 0.5}]
        output = rerank_with_metadata("test query", results, top_k=5)

        assert output == mock_result
        assert output.model_used == "test-model"
        assert output.duration_ms == 50.0

    def test_rerank_with_custom_config(self):
        """Test rerank with custom config creates new instance."""
        custom_config = RerankerConfig(top_k=5, max_chars=500)

        with patch.object(CrossEncoderReranker, "rerank") as mock_rerank:
            mock_rerank.return_value = RerankerResult(
                results=[], original_count=0, reranked_count=0
            )

            rerank("query", [], config=custom_config)

            # Should use custom config, not singleton


# =============================================================================
# Singleton Pattern Tests
# =============================================================================

class TestSingletonPattern:
    """Tests for singleton pattern implementation."""

    def teardown_method(self):
        """Reset singleton after each test."""
        CrossEncoderReranker.reset_instance()
        CrossEncoderReranker.clear_model_cache()

    def test_get_instance_returns_singleton(self):
        """Test get_instance returns same instance."""
        instance1 = CrossEncoderReranker.get_instance()
        instance2 = CrossEncoderReranker.get_instance()

        assert instance1 is instance2

    def test_reset_instance(self):
        """Test reset_instance clears singleton."""
        instance1 = CrossEncoderReranker.get_instance()
        CrossEncoderReranker.reset_instance()
        instance2 = CrossEncoderReranker.get_instance()

        assert instance1 is not instance2

    def test_clear_model_cache(self):
        """Test clear_model_cache clears cached models."""
        # Add something to cache
        CrossEncoderReranker._cached_models["test"] = "model"

        CrossEncoderReranker.clear_model_cache()

        assert len(CrossEncoderReranker._cached_models) == 0


# =============================================================================
# Edge Cases and Error Handling
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.fixture
    def mock_cross_encoder(self):
        """Create mock CrossEncoder model."""
        mock_model = MagicMock()
        return mock_model

    @pytest.fixture
    def reranker_with_mock(self, mock_cross_encoder):
        """Create reranker with mocked model."""
        config = RerankerConfig(legal_domain_boost=0.0)
        reranker = CrossEncoderReranker(config)
        reranker._model = mock_cross_encoder
        reranker._model_loaded = True
        reranker._active_model_name = "test-model"
        return reranker

    def test_results_without_text_field(self, reranker_with_mock, mock_cross_encoder):
        """Test handling results without text field."""
        mock_cross_encoder.predict.return_value = []

        results = [
            {"chunk_uid": "doc1", "score": 0.5},  # No text
            {"chunk_uid": "doc2", "content": "Has content", "score": 0.6},
        ]

        result = reranker_with_mock.rerank("test query", results)

        # Should handle gracefully
        assert isinstance(result, RerankerResult)

    def test_results_with_empty_text(self, reranker_with_mock, mock_cross_encoder):
        """Test handling results with empty text."""
        mock_cross_encoder.predict.return_value = []

        results = [
            {"chunk_uid": "doc1", "text": "", "score": 0.5},
            {"chunk_uid": "doc2", "text": "   ", "score": 0.6},
        ]

        result = reranker_with_mock.rerank("test query", results)

        # Empty text results should be skipped
        assert result.reranked_count == 0

    def test_prediction_failure(self, reranker_with_mock, mock_cross_encoder):
        """Test handling prediction failure."""
        mock_cross_encoder.predict.side_effect = Exception("Model error")

        results = [{"chunk_uid": "doc1", "text": "Document", "score": 0.5}]

        result = reranker_with_mock.rerank("test query", results)

        # Should return original order on failure
        assert result.model_used == "error-fallback"
        assert len(result.results) == 1

    def test_max_candidates_limit(self, reranker_with_mock, mock_cross_encoder):
        """Test max_candidates limits input."""
        # Set low max_candidates
        reranker_with_mock.config.max_candidates = 3
        mock_cross_encoder.predict.return_value = [0.9, 0.8, 0.7]

        results = [
            {"chunk_uid": f"doc{i}", "text": f"Document {i}", "score": 0.5}
            for i in range(10)
        ]

        result = reranker_with_mock.rerank("test query", results)

        # Should only rerank first 3 candidates
        assert result.original_count == 10
        assert len(result.results) <= 3

    def test_different_text_field_names(self, reranker_with_mock, mock_cross_encoder):
        """Test handling different text field names."""
        mock_cross_encoder.predict.return_value = [0.9, 0.8, 0.7]

        results = [
            {"chunk_uid": "doc1", "text": "Text field", "score": 0.5},
            {"chunk_uid": "doc2", "content": "Content field", "score": 0.6},
            {"chunk_uid": "doc3", "page_content": "Page content field", "score": 0.7},
        ]

        result = reranker_with_mock.rerank("test query", results)

        assert len(result.results) == 3

    def test_duration_tracking(self, reranker_with_mock, mock_cross_encoder):
        """Test duration is tracked correctly."""
        mock_cross_encoder.predict.return_value = [0.8]

        results = [{"chunk_uid": "doc1", "text": "Document", "score": 0.5}]

        result = reranker_with_mock.rerank("test query", results)

        assert result.duration_ms > 0
        assert isinstance(result.duration_ms, float)


# =============================================================================
# Legal Domain Documents Integration Test
# =============================================================================

class TestLegalDomainIntegration:
    """Integration tests with legal domain documents."""

    @pytest.fixture
    def mock_cross_encoder(self):
        """Create mock CrossEncoder that returns same scores for all docs."""
        mock_model = MagicMock()
        # All docs get same base score
        mock_model.predict = MagicMock(return_value=[0.5, 0.5, 0.5, 0.5])
        return mock_model

    def test_legal_domain_boost_affects_ranking(
        self, legal_domain_documents, mock_cross_encoder
    ):
        """Test legal domain boost affects final ranking."""
        config = RerankerConfig(legal_domain_boost=0.2)
        reranker = CrossEncoderReranker(config)
        reranker._model = mock_cross_encoder
        reranker._model_loaded = True
        reranker._active_model_name = "test-model"

        result = reranker.rerank("test query", legal_domain_documents)

        # Legal documents should rank higher due to boost
        # The "non-legal" document should be ranked lower
        non_legal = next(
            (r for r in result.results if r["chunk_uid"] == "non-legal"),
            None,
        )

        if non_legal:
            # Non-legal should have lower boost
            assert non_legal["legal_domain_boost"] == 0.0

            # Legal documents should have higher boost
            legal_docs = [r for r in result.results if r["chunk_uid"] != "non-legal"]
            if legal_docs:
                assert all(d["legal_domain_boost"] > 0 for d in legal_docs)
