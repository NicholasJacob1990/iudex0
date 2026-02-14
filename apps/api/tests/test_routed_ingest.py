"""
Tests for routed ingest pipeline — EmbeddingRouter ↔ ingest_to_collection integration.

Validates that:
- Pre-computed embedding_vectors (plural) are used when count matches chunks
- Fallback to default embeddings when count mismatches
- Backward compat: embedding_vector (singular) still works for single-chunk docs
- Qdrant collection creation uses correct dimensions for routed collections
- ingest_local/ingest_global propagate embedding_vectors
"""

import asyncio
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pipeline(embeddings_mock=None):
    """Create a minimal RAGPipeline with mocked backends."""
    from app.services.rag.pipeline.rag_pipeline import RAGPipeline

    config = MagicMock()
    config.max_results_per_source = 10

    # OpenSearch mock
    os_mock = MagicMock()
    os_mock.ensure_index.return_value = None
    os_mock.index_chunks_bulk.return_value = {"success": 1, "failed": 0}

    # Qdrant mock
    q_mock = MagicMock()
    q_mock.collection_exists.return_value = True
    q_mock.upsert_batch.return_value = (1, 0)

    emb = embeddings_mock or MagicMock()

    pipeline = RAGPipeline.__new__(RAGPipeline)
    pipeline._embeddings = emb
    pipeline._qdrant = q_mock
    pipeline._opensearch = os_mock
    pipeline._base_config = MagicMock()
    pipeline._base_config.enable_contextual_embeddings = False
    pipeline._base_config.qdrant_sparse_enabled = False
    pipeline._base_config.opensearch_index_lei = "lei"
    pipeline._base_config.opensearch_index_juris = "juris"
    pipeline._base_config.opensearch_index_pecas = "pecas_modelo"
    pipeline._base_config.opensearch_index_doutrina = "doutrina"
    pipeline._base_config.opensearch_index_sei = "sei"
    pipeline._base_config.opensearch_index_local = "local_chunks"
    pipeline._base_config.embedding_batch_size = 100
    pipeline.config = config
    pipeline._components_initialized = True
    return pipeline, emb


def _meta(tenant_id="t1", scope="global"):
    return {"tenant_id": tenant_id, "scope": scope, "doc_id": "doc1"}


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# Test 1: embedding_vectors used when count matches chunks
# ---------------------------------------------------------------------------
class TestIngestWithEmbeddingVectors:
    def test_vectors_used_single_chunk(self):
        """Pre-computed vectors used (not embed_many) when count == chunks."""
        pipeline, emb = _make_pipeline()
        text = "Artigo 1. O Estado é democrático de direito."
        pre_vectors = [[0.1] * 768]

        result = _run(pipeline.ingest_to_collection(
            text=text,
            collection="legal_br",
            metadata=_meta(),
            embedding_vectors=pre_vectors,
        ))

        emb.embed_many.assert_not_called()
        assert result["indexed"] >= 0

    def test_vectors_used_multi_chunk(self):
        """Pre-computed vectors for multi-chunk document."""
        pipeline, emb = _make_pipeline()

        text = "Capítulo I. " + ("Lorem ipsum dolor sit amet. " * 200)
        from app.services.rag.utils.ingest import chunk_document
        chunks = chunk_document(text, chunk_chars=1200, overlap=200)
        n_chunks = len(chunks)
        assert n_chunks > 1, "Test requires multi-chunk document"

        pre_vectors = [[0.1] * 1024 for _ in range(n_chunks)]

        result = _run(pipeline.ingest_to_collection(
            text=text,
            collection="legal_international",
            metadata=_meta(),
            embedding_vectors=pre_vectors,
        ))

        emb.embed_many.assert_not_called()
        assert result["indexed"] >= 0


# ---------------------------------------------------------------------------
# Test 2: Fallback when count mismatches
# ---------------------------------------------------------------------------
class TestEmbeddingVectorsMismatch:
    def test_fallback_on_count_mismatch(self):
        """When embedding_vectors count != chunks, fallback to embed_many."""
        emb = MagicMock()
        emb.embed_many.return_value = [[0.5] * 3072]
        pipeline, _ = _make_pipeline(emb)

        text = "Artigo 1. Texto curto."
        wrong_vectors = [[0.1] * 768, [0.2] * 768, [0.3] * 768]

        result = _run(pipeline.ingest_to_collection(
            text=text,
            collection="legal_br",
            metadata=_meta(),
            embedding_vectors=wrong_vectors,
        ))

        emb.embed_many.assert_called_once()


# ---------------------------------------------------------------------------
# Test 3: No vectors → unchanged behavior
# ---------------------------------------------------------------------------
class TestNoVectorsBackwardCompat:
    def test_no_vectors_uses_embed_many(self):
        """Without embedding_vectors, behavior identical to before."""
        emb = MagicMock()
        emb.embed_many.return_value = [[0.5] * 3072]
        pipeline, _ = _make_pipeline(emb)

        result = _run(pipeline.ingest_to_collection(
            text="Artigo 1. Texto.",
            collection="lei",
            metadata=_meta(),
        ))

        emb.embed_many.assert_called_once()


# ---------------------------------------------------------------------------
# Test 4: Single-chunk embedding_vector (singular) still works
# ---------------------------------------------------------------------------
class TestSingularEmbeddingVector:
    def test_singular_vector_single_chunk(self):
        """embedding_vector (singular) works for 1-chunk docs (backward compat)."""
        pipeline, emb = _make_pipeline()

        result = _run(pipeline.ingest_to_collection(
            text="Artigo 1. Texto.",
            collection="lei",
            metadata=_meta(),
            embedding_vector=[0.9] * 3072,
        ))

        emb.embed_many.assert_not_called()


# ---------------------------------------------------------------------------
# Test 5: create_collection for routed collection uses correct dimensions
# ---------------------------------------------------------------------------
class TestCreateCollectionDimensions:
    def test_legal_br_768d(self):
        """legal_br should be created with 768 dimensions (JurisBERT)."""
        from app.services.rag.storage.qdrant_service import QdrantService

        config = MagicMock()
        config.embedding_dimensions = 3072
        config.qdrant_url = "http://localhost:6333"
        config.qdrant_api_key = ""
        config.qdrant_collection_lei = "lei"
        config.qdrant_collection_juris = "juris"
        config.qdrant_collection_pecas = "pecas_modelo"
        config.qdrant_collection_sei = "sei"
        config.qdrant_collection_local = "local_chunks"
        config.qdrant_sparse_enabled = False

        with patch("app.services.rag.storage.qdrant_service.get_rag_config", return_value=config):
            with patch("app.services.rag.storage.qdrant_service.QdrantClient") as mock_client:
                svc = QdrantService(url="http://localhost:6333")
                svc._client = mock_client()
                svc._client.collection_exists.return_value = False

                svc.create_collection("legal_br")

                call_args = svc._client.create_collection.call_args
                assert call_args is not None
                vectors_config = call_args.kwargs.get("vectors_config")
                assert vectors_config.size == 768, f"Expected 768, got {vectors_config.size}"

    def test_lei_3072d(self):
        """lei (legacy) should keep 3072 dimensions (OpenAI)."""
        from app.services.rag.storage.qdrant_service import QdrantService

        config = MagicMock()
        config.embedding_dimensions = 3072
        config.qdrant_url = "http://localhost:6333"
        config.qdrant_api_key = ""
        config.qdrant_collection_lei = "lei"
        config.qdrant_collection_juris = "juris"
        config.qdrant_collection_pecas = "pecas_modelo"
        config.qdrant_collection_sei = "sei"
        config.qdrant_collection_local = "local_chunks"
        config.qdrant_sparse_enabled = False

        with patch("app.services.rag.storage.qdrant_service.get_rag_config", return_value=config):
            with patch("app.services.rag.storage.qdrant_service.QdrantClient") as mock_client:
                svc = QdrantService(url="http://localhost:6333")
                svc._client = mock_client()
                svc._client.collection_exists.return_value = False

                svc.create_collection("lei")

                call_args = svc._client.create_collection.call_args
                assert call_args is not None
                vectors_config = call_args.kwargs.get("vectors_config")
                assert vectors_config.size == 3072, f"Expected 3072, got {vectors_config.size}"


# ---------------------------------------------------------------------------
# Test 7: ingest_local propagates embedding_vectors
# ---------------------------------------------------------------------------
class TestIngestLocalPropagation:
    def test_ingest_local_passes_vectors(self):
        """ingest_local should forward embedding_vectors to ingest_to_collection."""
        pipeline, emb = _make_pipeline()
        pre_vectors = [[0.1] * 768]

        result = _run(pipeline.ingest_local(
            text="Artigo curto.",
            metadata={},
            tenant_id="t1",
            case_id="case1",
            embedding_vectors=pre_vectors,
        ))

        emb.embed_many.assert_not_called()


# ---------------------------------------------------------------------------
# Test 8: ingest_global propagates embedding_vectors
# ---------------------------------------------------------------------------
class TestIngestGlobalPropagation:
    def test_ingest_global_passes_vectors(self):
        """ingest_global should forward embedding_vectors to ingest_to_collection."""
        pipeline, emb = _make_pipeline()
        pre_vectors = [[0.1] * 1024]

        result = _run(pipeline.ingest_global(
            text="Artigo curto.",
            metadata={"tenant_id": "t1", "scope": "global"},
            dataset="juris",
            embedding_vectors=pre_vectors,
        ))

        emb.embed_many.assert_not_called()
