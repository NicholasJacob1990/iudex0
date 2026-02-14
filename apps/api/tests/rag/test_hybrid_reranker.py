"""
Tests for hybrid reranker (Local + Cohere).
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from app.services.rag.core.hybrid_reranker import (
    RerankerProvider,
    HybridRerankerConfig,
    HybridRerankerResult,
    HybridReranker,
    get_hybrid_reranker,
)
from app.services.rag.core.cohere_reranker import (
    CohereRerankerConfig,
    CohereRerankerResult,
    CohereReranker,
    PORTUGUESE_LEGAL_PATTERNS,
    _LEGAL_PATTERN_COMPILED,
)


class TestRerankerProvider:
    """Tests for RerankerProvider enum."""

    def test_provider_values(self):
        """Verify enum values."""
        assert RerankerProvider.AUTO.value == "auto"
        assert RerankerProvider.LOCAL.value == "local"
        assert RerankerProvider.COHERE.value == "cohere"

    def test_provider_from_string(self):
        """Create provider from string."""
        assert RerankerProvider("auto") == RerankerProvider.AUTO
        assert RerankerProvider("local") == RerankerProvider.LOCAL
        assert RerankerProvider("cohere") == RerankerProvider.COHERE


class TestHybridRerankerConfig:
    """Tests for HybridRerankerConfig."""

    def test_default_config(self):
        """Default configuration values."""
        config = HybridRerankerConfig()
        assert config.provider == RerankerProvider.AUTO
        assert config.fallback_to_local is True
        assert config.legal_domain_boost == 0.1

    @patch.dict("os.environ", {
        "RERANK_PROVIDER": "cohere",
        "ENVIRONMENT": "production",
        "RERANK_FALLBACK_LOCAL": "false",
    })
    def test_config_from_env(self):
        """Load config from environment."""
        config = HybridRerankerConfig.from_env()
        assert config.provider == RerankerProvider.COHERE
        assert config.environment == "production"
        assert config.fallback_to_local is False


class TestCohereReranker:
    """Tests for CohereReranker."""

    def test_legal_patterns_compiled(self):
        """Legal patterns should compile correctly."""
        assert _LEGAL_PATTERN_COMPILED is not None
        # Test some patterns
        assert _LEGAL_PATTERN_COMPILED.search("art. 5")
        assert _LEGAL_PATTERN_COMPILED.search("Lei 8.666")
        assert _LEGAL_PATTERN_COMPILED.search("STF")
        assert _LEGAL_PATTERN_COMPILED.search("0000000-00.0000.0.00.0000")

    def test_compute_legal_boost(self):
        """Legal boost computation."""
        config = CohereRerankerConfig(legal_domain_boost=0.1)
        reranker = CohereReranker(config)

        # No legal terms
        boost = reranker._compute_legal_boost("texto comum sem termos jurídicos")
        assert boost == 0.0

        # Some legal terms
        boost = reranker._compute_legal_boost("art. 5 da Lei 8.666")
        assert boost > 0.0

        # Many legal terms (should cap at max boost)
        boost = reranker._compute_legal_boost(
            "art. 5 Lei 8.666 STF súmula 331 § 1º inciso I"
        )
        assert boost == pytest.approx(0.1, abs=0.01)

    def test_cohere_unavailable_without_api_key(self):
        """Cohere should be unavailable without API key."""
        config = CohereRerankerConfig(api_key="")
        reranker = CohereReranker(config)
        assert reranker.is_available is False


class TestHybridReranker:
    """Tests for HybridReranker."""

    @pytest.fixture
    def mock_local_result(self):
        """Mock result from local reranker."""
        return MagicMock(
            results=[
                {"text": "result 1", "rerank_score": 0.9},
                {"text": "result 2", "rerank_score": 0.8},
            ],
            reranked_count=2,
            scores=[0.9, 0.8],
            model_used="cross-encoder/ms-marco-multilingual-MiniLM-L6-H384-v1",
            duration_ms=50.0,
        )

    @pytest.fixture
    def mock_cohere_result(self):
        """Mock result from Cohere reranker."""
        return CohereRerankerResult(
            results=[
                {"text": "result 1", "rerank_score": 0.95, "cohere_score": 0.9},
                {"text": "result 2", "rerank_score": 0.85, "cohere_score": 0.8},
            ],
            original_count=2,
            reranked_count=2,
            scores=[0.95, 0.85],
            model_used="rerank-v4.0-pro",
            duration_ms=100.0,
            api_calls=1,
        )

    def test_auto_selects_local_in_development(self):
        """Auto mode selects local in development."""
        config = HybridRerankerConfig(
            provider=RerankerProvider.AUTO,
            environment="development",
        )
        reranker = HybridReranker(config)

        # Force selection
        provider = reranker._select_provider()
        assert provider == "local"

    @patch("app.services.rag.core.hybrid_reranker.HybridReranker._get_cohere_reranker")
    def test_auto_selects_cohere_in_production_if_available(self, mock_get_cohere):
        """Auto mode selects Cohere in production if available."""
        # Mock Cohere as available
        mock_cohere = MagicMock()
        mock_cohere.is_available = True
        mock_get_cohere.return_value = mock_cohere

        config = HybridRerankerConfig(
            provider=RerankerProvider.AUTO,
            environment="production",
        )
        reranker = HybridReranker(config)

        provider = reranker._select_provider()
        assert provider == "cohere"

    @patch("app.services.rag.core.hybrid_reranker.HybridReranker._get_cohere_reranker")
    def test_auto_falls_back_to_local_when_cohere_unavailable(self, mock_get_cohere):
        """Auto mode falls back to local if Cohere unavailable."""
        mock_cohere = MagicMock()
        mock_cohere.is_available = False
        mock_get_cohere.return_value = mock_cohere

        config = HybridRerankerConfig(
            provider=RerankerProvider.AUTO,
            environment="production",
        )
        reranker = HybridReranker(config)

        provider = reranker._select_provider()
        assert provider == "local"

    @patch("app.services.rag.core.hybrid_reranker.HybridReranker._get_local_reranker")
    def test_rerank_with_local(self, mock_get_local, mock_local_result):
        """Rerank using local provider."""
        mock_local = MagicMock()
        mock_local.rerank.return_value = mock_local_result
        mock_get_local.return_value = mock_local

        config = HybridRerankerConfig(provider=RerankerProvider.LOCAL)
        reranker = HybridReranker(config)

        results = [{"text": "doc 1"}, {"text": "doc 2"}]
        result = reranker.rerank("query", results)

        assert result.provider_used == "local"
        assert len(result.results) == 2
        assert result.used_fallback is False

    @patch("app.services.rag.core.hybrid_reranker.HybridReranker._get_cohere_reranker")
    @patch("app.services.rag.core.hybrid_reranker.HybridReranker._get_local_reranker")
    def test_cohere_fallback_to_local_on_error(
        self, mock_get_local, mock_get_cohere, mock_local_result
    ):
        """Fallback to local when Cohere fails."""
        # Cohere fails
        mock_cohere = MagicMock()
        mock_cohere.is_available = True
        mock_cohere.rerank.side_effect = Exception("API Error")
        mock_get_cohere.return_value = mock_cohere

        # Local works
        mock_local = MagicMock()
        mock_local.rerank.return_value = mock_local_result
        mock_get_local.return_value = mock_local

        config = HybridRerankerConfig(
            provider=RerankerProvider.COHERE,
            fallback_to_local=True,
        )
        reranker = HybridReranker(config)

        results = [{"text": "doc 1"}, {"text": "doc 2"}]
        result = reranker.rerank("query", results)

        assert result.provider_used == "local"
        assert result.used_fallback is True

    def test_empty_results(self):
        """Handle empty results."""
        config = HybridRerankerConfig(provider=RerankerProvider.LOCAL)
        reranker = HybridReranker(config)

        result = reranker.rerank("query", [])
        assert len(result) == 0
        assert result.provider_used == "none"

    def test_empty_query(self):
        """Handle empty query."""
        config = HybridRerankerConfig(provider=RerankerProvider.LOCAL)
        reranker = HybridReranker(config)

        results = [{"text": "doc 1"}]
        result = reranker.rerank("", results)
        assert result.provider_used == "passthrough"
        assert len(result.results) == 1

    def test_get_status(self):
        """Get provider status."""
        config = HybridRerankerConfig(
            provider=RerankerProvider.AUTO,
            environment="development",
        )
        reranker = HybridReranker(config)

        status = reranker.get_status()
        assert status["configured_provider"] == "auto"
        assert status["environment"] == "development"
        assert status["fallback_enabled"] is True


class TestLegalBoostIntegration:
    """Tests for legal domain boost across providers."""

    def test_local_has_legal_boost(self):
        """Local reranker has legal patterns."""
        from app.services.rag.core.reranker import PORTUGUESE_LEGAL_PATTERNS as local_patterns

        # Should have similar patterns
        assert len(local_patterns) > 0
        assert any("art" in p.lower() for p in local_patterns)

    def test_cohere_has_legal_boost(self):
        """Cohere reranker has legal patterns."""
        assert len(PORTUGUESE_LEGAL_PATTERNS) > 0
        assert any("art" in p.lower() for p in PORTUGUESE_LEGAL_PATTERNS)

    def test_patterns_match_brazilian_legal_terms(self):
        """Patterns match Brazilian legal terminology."""
        test_cases = [
            ("art. 5º da CF", True),
            ("Lei nº 14.133/2021", True),
            ("Súmula 331 do TST", True),
            ("processo nº 0000001-00.2024.8.26.0000", True),
            ("Código Civil", True),
            ("habeas corpus", True),
            ("mandado de segurança", True),
            ("licitação pública", True),
            ("texto comum sem termos jurídicos", False),
        ]

        for text, should_match in test_cases:
            has_match = bool(_LEGAL_PATTERN_COMPILED.search(text.lower()))
            assert has_match == should_match, f"Failed for: {text}"
