"""
Tests for ColPali Visual Document Retrieval Service
"""

import pytest
import numpy as np
from unittest.mock import MagicMock, patch, AsyncMock
from dataclasses import dataclass


class TestColPaliConfig:
    """Tests for ColPaliConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        from app.services.rag.core.colpali_service import ColPaliConfig

        config = ColPaliConfig()

        assert config.model_name == "vidore/colqwen2.5-v1"
        assert config.device == "auto"
        assert config.embedding_dim == 128
        assert config.batch_size == 4
        assert config.enabled is False  # Disabled by default
        assert config.qdrant_collection == "visual_docs"

    def test_config_from_env(self, monkeypatch):
        """Test loading configuration from environment."""
        from app.services.rag.core.colpali_service import ColPaliConfig

        monkeypatch.setenv("COLPALI_ENABLED", "true")
        monkeypatch.setenv("COLPALI_MODEL", "vidore/colpali")
        monkeypatch.setenv("COLPALI_DEVICE", "cuda")
        monkeypatch.setenv("COLPALI_BATCH_SIZE", "8")
        monkeypatch.setenv("COLPALI_QDRANT_COLLECTION", "my_visual_docs")

        config = ColPaliConfig.from_env()

        assert config.enabled is True
        assert config.model_name == "vidore/colpali"
        assert config.device == "cuda"
        assert config.batch_size == 8
        assert config.qdrant_collection == "my_visual_docs"


class TestColPaliService:
    """Tests for ColPaliService."""

    def test_service_instantiation(self):
        """Test service can be instantiated."""
        from app.services.rag.core.colpali_service import ColPaliService, ColPaliConfig

        config = ColPaliConfig(enabled=False)
        service = ColPaliService(config)

        assert service.config.enabled is False
        assert service._loaded is False

    def test_singleton_pattern(self):
        """Test singleton pattern works correctly."""
        from app.services.rag.core.colpali_service import ColPaliService, ColPaliConfig

        # Reset singleton
        ColPaliService._instance = None

        config = ColPaliConfig(enabled=False)
        service1 = ColPaliService.get_instance(config)
        service2 = ColPaliService.get_instance()

        assert service1 is service2

        # Cleanup
        ColPaliService._instance = None

    def test_health_check_disabled(self):
        """Test health check when disabled."""
        from app.services.rag.core.colpali_service import ColPaliService, ColPaliConfig

        config = ColPaliConfig(enabled=False)
        service = ColPaliService(config)

        health = service.health_check()

        assert health["enabled"] is False
        assert health["model_loaded"] is False
        assert health["model_name"] == "vidore/colqwen2.5-v1"


class TestLateInteraction:
    """Tests for late interaction scoring."""

    def test_late_interaction_score(self):
        """Test late interaction (MaxSim) scoring."""
        from app.services.rag.core.colpali_service import ColPaliService, ColPaliConfig

        service = ColPaliService(ColPaliConfig(enabled=False))

        # Create mock embeddings
        # Query: 3 tokens, each with 4-dim embedding
        query_emb = np.array([
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0],
        ])

        # Doc: 4 patches, each with 4-dim embedding
        doc_emb = np.array([
            [1.0, 0.0, 0.0, 0.0],  # Matches token 0
            [0.0, 1.0, 0.0, 0.0],  # Matches token 1
            [0.0, 0.0, 1.0, 0.0],  # Matches token 2
            [0.5, 0.5, 0.0, 0.0],  # Mixed
        ])

        score = service._late_interaction_score(query_emb, doc_emb)

        # Each token should find a perfect match (similarity = 1.0)
        # Total score = 3.0
        assert score == pytest.approx(3.0, rel=0.01)

    def test_late_interaction_score_no_match(self):
        """Test late interaction with poor matches."""
        from app.services.rag.core.colpali_service import ColPaliService, ColPaliConfig

        service = ColPaliService(ColPaliConfig(enabled=False))

        # Query and doc are orthogonal
        query_emb = np.array([
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
        ])

        doc_emb = np.array([
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ])

        score = service._late_interaction_score(query_emb, doc_emb)

        # No matches, score should be 0
        assert score == pytest.approx(0.0, abs=0.01)


class TestComputeHighlights:
    """Tests for highlight computation."""

    def test_compute_highlights(self):
        """Test highlight computation."""
        from app.services.rag.core.colpali_service import ColPaliService, ColPaliConfig

        service = ColPaliService(ColPaliConfig(enabled=False))

        query = "test query"
        query_emb = np.array([
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
        ])

        # 4 patches (2x2 grid)
        doc_emb = np.array([
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 0.5, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
        ])

        highlights = service._compute_highlights(query, query_emb, doc_emb)

        assert len(highlights) == 2
        assert highlights[0]["token"] == "test"
        assert highlights[0]["patch_idx"] == 0  # Best match for first token
        assert highlights[1]["token"] == "query"
        assert highlights[1]["patch_idx"] == 3  # Best match for second token


class TestVisualRetrievalResult:
    """Tests for VisualRetrievalResult dataclass."""

    def test_to_dict(self):
        """Test conversion to dictionary."""
        from app.services.rag.core.colpali_service import VisualRetrievalResult

        result = VisualRetrievalResult(
            doc_id="doc1",
            page_num=5,
            score=0.85,
            tenant_id="tenant1",
            metadata={"title": "Test Doc"},
        )

        d = result.to_dict()

        assert d["doc_id"] == "doc1"
        assert d["page_num"] == 5
        assert d["score"] == 0.85
        assert d["tenant_id"] == "tenant1"
        assert d["metadata"]["title"] == "Test Doc"


class TestGetColPaliService:
    """Tests for singleton getter."""

    def test_get_colpali_service(self):
        """Test singleton getter function."""
        import app.services.rag.core.colpali_service as module

        # Reset singleton
        module._service_instance = None

        service = module.get_colpali_service()
        assert service is not None

        service2 = module.get_colpali_service()
        assert service is service2

        # Cleanup
        module._service_instance = None


@pytest.mark.asyncio
class TestAsyncOperations:
    """Tests for async operations (mocked)."""

    async def test_load_model_disabled(self):
        """Test model loading when disabled."""
        from app.services.rag.core.colpali_service import ColPaliService, ColPaliConfig

        config = ColPaliConfig(enabled=False)
        service = ColPaliService(config)

        result = await service.load_model()

        assert result is False
        assert service._loaded is False

    async def test_search_when_disabled(self):
        """Test search returns empty when disabled."""
        from app.services.rag.core.colpali_service import ColPaliService, ColPaliConfig

        config = ColPaliConfig(enabled=False)
        service = ColPaliService(config)

        results = await service.search("test query", "tenant1")

        assert results == []

    async def test_index_pdf_when_disabled(self):
        """Test indexing returns disabled status when disabled."""
        from app.services.rag.core.colpali_service import ColPaliService, ColPaliConfig

        config = ColPaliConfig(enabled=False)
        service = ColPaliService(config)

        result = await service.index_pdf("/path/to/doc.pdf", "doc1", "tenant1")

        assert result["status"] == "disabled"
        assert result["pages_indexed"] == 0


class TestEnvParsing:
    """Tests for environment variable parsing."""

    def test_env_bool_true(self, monkeypatch):
        """Test boolean env parsing for true values."""
        from app.services.rag.core.colpali_service import _env_bool

        for val in ["1", "true", "TRUE", "yes", "YES", "on", "ON"]:
            monkeypatch.setenv("TEST_BOOL", val)
            assert _env_bool("TEST_BOOL") is True

    def test_env_bool_false(self, monkeypatch):
        """Test boolean env parsing for false values."""
        from app.services.rag.core.colpali_service import _env_bool

        for val in ["0", "false", "no", "off", "anything"]:
            monkeypatch.setenv("TEST_BOOL", val)
            assert _env_bool("TEST_BOOL") is False

    def test_env_bool_default(self):
        """Test boolean env parsing with default."""
        from app.services.rag.core.colpali_service import _env_bool

        assert _env_bool("NONEXISTENT_VAR", True) is True
        assert _env_bool("NONEXISTENT_VAR", False) is False

    def test_env_int(self, monkeypatch):
        """Test integer env parsing."""
        from app.services.rag.core.colpali_service import _env_int

        monkeypatch.setenv("TEST_INT", "42")
        assert _env_int("TEST_INT", 0) == 42

        monkeypatch.setenv("TEST_INT", "invalid")
        assert _env_int("TEST_INT", 10) == 10

    def test_env_float(self, monkeypatch):
        """Test float env parsing."""
        from app.services.rag.core.colpali_service import _env_float

        monkeypatch.setenv("TEST_FLOAT", "3.14")
        assert _env_float("TEST_FLOAT", 0.0) == pytest.approx(3.14)

        monkeypatch.setenv("TEST_FLOAT", "invalid")
        assert _env_float("TEST_FLOAT", 1.5) == 1.5
