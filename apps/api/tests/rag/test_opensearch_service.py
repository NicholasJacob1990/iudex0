"""
Unit tests for OpenSearchService.

Tests cover:
- Connection management
- Index operations
- Lexical search with BM25
- Brazilian analyzer behavior
- Multi-tenant security filtering (scope, sigilo)
- Bulk indexing
- Delete operations (delete_by_query, TTL cleanup)
- Error handling

Note: Tests use pytest.importorskip to gracefully skip if opensearch-py is not installed.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
from unittest.mock import MagicMock, Mock, patch, PropertyMock

import pytest

# Skip all tests if opensearch-py is not installed
opensearchpy = pytest.importorskip("opensearchpy", reason="opensearch-py not installed")

from opensearchpy.exceptions import NotFoundError, RequestError

from app.services.rag.storage.opensearch_service import (
    OpenSearchService,
    RAG_CHUNK_MAPPING,
    SearchResult,
    ScopeFilter,
    get_opensearch_service,
    reset_opensearch_service,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_opensearch_client():
    """Create a mocked OpenSearch client."""
    client = MagicMock()

    # Mock ping for connection check
    client.ping.return_value = True

    # Mock indices operations
    client.indices = MagicMock()
    client.indices.exists.return_value = False
    client.indices.create.return_value = {"acknowledged": True}
    client.indices.refresh.return_value = {"_shards": {"successful": 1}}

    return client


@pytest.fixture
def mock_rag_config():
    """Create a mocked RAG config."""
    config = MagicMock()
    config.opensearch_url = "https://localhost:9200"
    config.opensearch_user = "admin"
    config.opensearch_password = "admin"
    config.opensearch_verify_certs = False
    config.opensearch_index_lei = "rag-lei"
    config.opensearch_index_juris = "rag-juris"
    config.opensearch_index_pecas = "rag-pecas_modelo"
    config.opensearch_index_sei = "rag-sei"
    config.opensearch_index_local = "rag-local"
    config.local_ttl_days = 7
    config.get_opensearch_indices.return_value = [
        "rag-lei", "rag-juris", "rag-pecas_modelo", "rag-sei", "rag-local"
    ]
    return config


@pytest.fixture
def opensearch_service(mock_opensearch_client, mock_rag_config):
    """Create an OpenSearchService with mocked dependencies."""
    with patch("app.services.rag.storage.opensearch_service.get_rag_config", return_value=mock_rag_config):
        service = OpenSearchService()
        service._client = mock_opensearch_client
        yield service
        # Cleanup
        reset_opensearch_service()


@pytest.fixture
def sample_chunks() -> List[Dict[str, Any]]:
    """Create sample chunks for testing."""
    return [
        {
            "chunk_uid": "chunk-001",
            "text": "Artigo 1o do Codigo Civil brasileiro trata da personalidade.",
            "doc_id": "doc-001",
            "scope": "global",
            "tenant_id": "tenant-123",
            "sigilo": "publico",
            "source_type": "lei",
            "title": "Codigo Civil",
            "chunk_index": 0,
        },
        {
            "chunk_uid": "chunk-002",
            "text": "Jurisprudencia do STJ sobre responsabilidade civil.",
            "doc_id": "doc-002",
            "scope": "global",
            "tenant_id": "tenant-123",
            "sigilo": "publico",
            "source_type": "juris",
            "title": "STJ - REsp 123456",
            "chunk_index": 0,
        },
        {
            "chunk_uid": "chunk-003",
            "text": "Documento restrito sobre processo sigiloso.",
            "doc_id": "doc-003",
            "scope": "private",
            "tenant_id": "tenant-123",
            "sigilo": "restrito",
            "source_type": "local",
            "allowed_users": ["user-001"],
            "chunk_index": 0,
        },
    ]


@pytest.fixture
def sample_search_response():
    """Create sample search response from OpenSearch."""
    return {
        "took": 5,
        "timed_out": False,
        "hits": {
            "total": {"value": 2, "relation": "eq"},
            "max_score": 10.5,
            "hits": [
                {
                    "_index": "rag-lei",
                    "_id": "chunk-001",
                    "_score": 10.5,
                    "_source": {
                        "chunk_uid": "chunk-001",
                        "text": "Artigo 1o do Codigo Civil brasileiro.",
                        "doc_id": "doc-001",
                        "scope": "global",
                        "tenant_id": "tenant-123",
                        "sigilo": "publico",
                        "source_type": "lei",
                        "title": "Codigo Civil",
                    },
                    "highlight": {
                        "text": ["<mark>Artigo 1o</mark> do Codigo Civil brasileiro."]
                    },
                },
                {
                    "_index": "rag-juris",
                    "_id": "chunk-002",
                    "_score": 8.2,
                    "_source": {
                        "chunk_uid": "chunk-002",
                        "text": "Jurisprudencia sobre responsabilidade civil.",
                        "doc_id": "doc-002",
                        "scope": "global",
                        "tenant_id": "tenant-123",
                        "sigilo": "publico",
                        "source_type": "juris",
                    },
                },
            ],
        },
    }


# =============================================================================
# Connection Management Tests
# =============================================================================


class TestConnectionManagement:
    """Tests for connection management."""

    def test_client_lazy_initialization(self, mock_rag_config):
        """Test client is lazily initialized."""
        with patch("app.services.rag.storage.opensearch_service.get_rag_config", return_value=mock_rag_config):
            with patch("app.services.rag.storage.opensearch_service.OpenSearch") as mock_os:
                mock_client = MagicMock()
                mock_os.return_value = mock_client

                service = OpenSearchService()
                assert service._client is None

                # Access client property triggers initialization
                _ = service.client
                assert service._client is not None

    def test_ping_success(self, opensearch_service, mock_opensearch_client):
        """Test successful ping."""
        mock_opensearch_client.ping.return_value = True
        assert opensearch_service.ping() is True

    def test_ping_failure(self, opensearch_service, mock_opensearch_client):
        """Test ping failure."""
        mock_opensearch_client.ping.side_effect = Exception("Connection error")
        assert opensearch_service.ping() is False

    def test_close(self, opensearch_service, mock_opensearch_client):
        """Test closing connection."""
        opensearch_service.close()

        mock_opensearch_client.close.assert_called_once()
        assert opensearch_service._client is None

    def test_client_creation_with_ssl(self, mock_rag_config):
        """Test client creation with SSL configuration."""
        mock_rag_config.opensearch_url = "https://localhost:9200"

        with patch("app.services.rag.storage.opensearch_service.get_rag_config", return_value=mock_rag_config):
            with patch("app.services.rag.storage.opensearch_service.OpenSearch") as mock_os:
                service = OpenSearchService()
                _ = service.client

                call_kwargs = mock_os.call_args.kwargs
                assert call_kwargs["use_ssl"] is True


# =============================================================================
# Index Management Tests
# =============================================================================


class TestIndexManagement:
    """Tests for index management."""

    def test_get_index_name_by_type(self, opensearch_service):
        """Test getting index name by source type."""
        assert opensearch_service.get_index_name("lei") == "rag-lei"
        assert opensearch_service.get_index_name("juris") == "rag-juris"
        assert opensearch_service.get_index_name("pecas") == "rag-pecas_modelo"
        assert opensearch_service.get_index_name("local") == "rag-local"

    def test_get_index_name_default(self, opensearch_service):
        """Test getting default index for unknown type."""
        assert opensearch_service.get_index_name("unknown") == "rag-local"

    def test_ensure_index_creates_new(self, opensearch_service, mock_opensearch_client):
        """Test ensure_index creates new index."""
        mock_opensearch_client.indices.exists.return_value = False

        result = opensearch_service.ensure_index("rag-test")

        assert result is True
        mock_opensearch_client.indices.create.assert_called_once()

    def test_ensure_index_already_exists(self, opensearch_service, mock_opensearch_client):
        """Test ensure_index when index already exists."""
        mock_opensearch_client.indices.exists.return_value = True

        result = opensearch_service.ensure_index("rag-test")

        assert result is True
        mock_opensearch_client.indices.create.assert_not_called()

    def test_ensure_index_handles_race_condition(self, opensearch_service, mock_opensearch_client):
        """Test ensure_index handles race condition (index created between check and create)."""
        mock_opensearch_client.indices.exists.return_value = False
        mock_opensearch_client.indices.create.side_effect = RequestError(
            400, "resource_already_exists_exception", {}
        )

        result = opensearch_service.ensure_index("rag-test")

        assert result is True

    def test_ensure_index_failure(self, opensearch_service, mock_opensearch_client):
        """Test ensure_index failure."""
        mock_opensearch_client.indices.exists.return_value = False
        mock_opensearch_client.indices.create.side_effect = RequestError(
            400, "Invalid mapping", {}
        )

        result = opensearch_service.ensure_index("rag-test")

        assert result is False

    def test_ensure_all_indices(self, opensearch_service, mock_opensearch_client, mock_rag_config):
        """Test ensuring all RAG indices exist."""
        mock_opensearch_client.indices.exists.return_value = False

        with patch("app.services.rag.storage.opensearch_service.get_rag_config", return_value=mock_rag_config):
            results = opensearch_service.ensure_all_indices()

        assert len(results) == 5
        assert all(v is True for v in results.values())

    def test_refresh_single_index(self, opensearch_service, mock_opensearch_client):
        """Test refreshing a single index."""
        result = opensearch_service.refresh("rag-lei")

        assert result is True
        mock_opensearch_client.indices.refresh.assert_called_once_with(index="rag-lei")

    def test_refresh_all_indices(self, opensearch_service, mock_opensearch_client, mock_rag_config):
        """Test refreshing all indices."""
        with patch("app.services.rag.storage.opensearch_service.get_rag_config", return_value=mock_rag_config):
            result = opensearch_service.refresh()

        assert result is True


# =============================================================================
# Scope Filter Building Tests
# =============================================================================


class TestBuildScopeFilter:
    """Tests for build_scope_filter() security filtering."""

    def test_basic_tenant_filter(self):
        """Test basic tenant isolation."""
        filters = OpenSearchService.build_scope_filter(tenant_id="tenant-123")

        assert len(filters) > 0
        tenant_filter = next((f for f in filters if "term" in f and "tenant_id" in f.get("term", {})), None)
        assert tenant_filter is not None
        assert tenant_filter["term"]["tenant_id"] == "tenant-123"

    def test_global_scope_filter(self):
        """Test global scope filter."""
        filters = OpenSearchService.build_scope_filter(
            scope="global",
            tenant_id="tenant-123",
        )

        scope_filter = next((f for f in filters if "term" in f and "scope" in f.get("term", {})), None)
        assert scope_filter is not None
        assert scope_filter["term"]["scope"] == "global"

    def test_local_scope_with_case_id(self):
        """Test local scope filter with case_id."""
        filters = OpenSearchService.build_scope_filter(
            scope="local",
            tenant_id="tenant-123",
            case_id="case-456",
        )

        scope_filter = next((f for f in filters if "term" in f and "scope" in f.get("term", {})), None)
        case_filter = next((f for f in filters if "term" in f and "case_id" in f.get("term", {})), None)

        assert scope_filter["term"]["scope"] == "local"
        assert case_filter["term"]["case_id"] == "case-456"

    def test_private_scope_with_user(self):
        """Test private scope filter with user permission."""
        filters = OpenSearchService.build_scope_filter(
            scope="private",
            tenant_id="tenant-123",
            user_id="user-001",
        )

        scope_filter = next((f for f in filters if "term" in f and "scope" in f.get("term", {})), None)
        user_filter = next((f for f in filters if "term" in f and "allowed_users" in f.get("term", {})), None)

        assert scope_filter["term"]["scope"] == "private"
        assert user_filter["term"]["allowed_users"] == "user-001"

    def test_group_scope_with_groups(self):
        """Test group scope filter with group membership."""
        filters = OpenSearchService.build_scope_filter(
            scope="group",
            tenant_id="tenant-123",
            group_ids=["group-A", "group-B"],
        )

        scope_filter = next((f for f in filters if "term" in f and "scope" in f.get("term", {})), None)
        group_filter = next((f for f in filters if "terms" in f and "group_ids" in f.get("terms", {})), None)

        assert scope_filter["term"]["scope"] == "group"
        assert group_filter["terms"]["group_ids"] == ["group-A", "group-B"]

    def test_no_specific_scope_builds_visibility_rules(self):
        """Test that no specific scope builds comprehensive visibility rules."""
        filters = OpenSearchService.build_scope_filter(
            tenant_id="tenant-123",
            user_id="user-001",
            group_ids=["group-A"],
            case_id="case-456",
            include_global=True,
        )

        # Should have a bool filter with should clauses
        bool_filter = next((f for f in filters if "bool" in f and "should" in f.get("bool", {})), None)
        assert bool_filter is not None

    def test_sigilo_publico_filter(self):
        """Test sigilo filter for publico only."""
        filters = OpenSearchService.build_scope_filter(
            tenant_id="tenant-123",
            sigilo="publico",
        )

        sigilo_filter = next((f for f in filters if "term" in f and "sigilo" in f.get("term", {})), None)
        assert sigilo_filter["term"]["sigilo"] == "publico"

    def test_sigilo_visibility_rules_without_specific_sigilo(self):
        """Test default sigilo visibility rules."""
        filters = OpenSearchService.build_scope_filter(
            tenant_id="tenant-123",
            user_id="user-001",
            group_ids=["group-A"],
        )

        # Should have sigilo visibility rules (publico visible, restrito/sigiloso conditional)
        sigilo_bool = next(
            (f for f in filters if "bool" in f and "should" in f.get("bool", {}) and
             any("sigilo" in str(s) for s in f.get("bool", {}).get("should", []))),
            None
        )
        assert sigilo_bool is not None

    def test_exclude_global_scope(self):
        """Test excluding global scope from visibility."""
        filters = OpenSearchService.build_scope_filter(
            tenant_id="tenant-123",
            user_id="user-001",
            include_global=False,
        )

        # Check that global is not in the should clauses
        bool_filter = next((f for f in filters if "bool" in f and "should" in f.get("bool", {})), None)
        if bool_filter:
            should_clauses = bool_filter["bool"]["should"]
            global_clause = next(
                (c for c in should_clauses if c.get("term", {}).get("scope") == "global"),
                None
            )
            assert global_clause is None


# =============================================================================
# Lexical Search Tests
# =============================================================================


class TestLexicalSearch:
    """Tests for lexical (BM25) search."""

    def test_search_basic(self, opensearch_service, mock_opensearch_client, sample_search_response, mock_rag_config):
        """Test basic lexical search."""
        mock_opensearch_client.search.return_value = sample_search_response

        with patch("app.services.rag.storage.opensearch_service.get_rag_config", return_value=mock_rag_config):
            results = opensearch_service.search_lexical(
                query="Codigo Civil artigo",
                tenant_id="tenant-123",
                top_k=10,
            )

        assert len(results) == 2
        assert results[0]["chunk_uid"] == "chunk-001"
        assert results[0]["score"] == 10.5
        assert results[0]["engine"] == "opensearch_bm25"

    def test_search_with_scope_filter(self, opensearch_service, mock_opensearch_client, sample_search_response, mock_rag_config):
        """Test search with scope filter."""
        mock_opensearch_client.search.return_value = sample_search_response

        with patch("app.services.rag.storage.opensearch_service.get_rag_config", return_value=mock_rag_config):
            results = opensearch_service.search_lexical(
                query="direito civil",
                scope="global",
                tenant_id="tenant-123",
            )

        mock_opensearch_client.search.assert_called_once()
        call_body = mock_opensearch_client.search.call_args.kwargs["body"]
        assert "filter" in call_body["query"]["bool"]

    def test_search_with_sigilo_filter(self, opensearch_service, mock_opensearch_client, sample_search_response, mock_rag_config):
        """Test search with sigilo filter."""
        mock_opensearch_client.search.return_value = sample_search_response

        with patch("app.services.rag.storage.opensearch_service.get_rag_config", return_value=mock_rag_config):
            opensearch_service.search_lexical(
                query="processo",
                sigilo="restrito",
                tenant_id="tenant-123",
                user_id="user-001",
            )

        call_body = mock_opensearch_client.search.call_args.kwargs["body"]
        filters = call_body["query"]["bool"]["filter"]

        # Check sigilo filter is included
        sigilo_filter = next((f for f in filters if "term" in f and "sigilo" in f.get("term", {})), None)
        assert sigilo_filter is not None

    def test_search_with_highlight(self, opensearch_service, mock_opensearch_client, sample_search_response, mock_rag_config):
        """Test search includes highlights."""
        mock_opensearch_client.search.return_value = sample_search_response

        with patch("app.services.rag.storage.opensearch_service.get_rag_config", return_value=mock_rag_config):
            results = opensearch_service.search_lexical(
                query="artigo",
                tenant_id="tenant-123",
                highlight=True,
            )

        # First result should have highlights
        assert "highlights" in results[0]["metadata"]
        assert "<mark>" in results[0]["metadata"]["highlights"][0]

    def test_search_without_highlight(self, opensearch_service, mock_opensearch_client, sample_search_response, mock_rag_config):
        """Test search without highlights."""
        # Remove highlights from response
        for hit in sample_search_response["hits"]["hits"]:
            hit.pop("highlight", None)

        mock_opensearch_client.search.return_value = sample_search_response

        with patch("app.services.rag.storage.opensearch_service.get_rag_config", return_value=mock_rag_config):
            results = opensearch_service.search_lexical(
                query="artigo",
                tenant_id="tenant-123",
                highlight=False,
            )

        call_body = mock_opensearch_client.search.call_args.kwargs["body"]
        assert "highlight" not in call_body

    def test_search_specific_indices(self, opensearch_service, mock_opensearch_client, sample_search_response, mock_rag_config):
        """Test search on specific indices."""
        mock_opensearch_client.search.return_value = sample_search_response

        with patch("app.services.rag.storage.opensearch_service.get_rag_config", return_value=mock_rag_config):
            opensearch_service.search_lexical(
                query="lei",
                indices=["rag-lei", "rag-juris"],
                tenant_id="tenant-123",
            )

        call_kwargs = mock_opensearch_client.search.call_args.kwargs
        assert call_kwargs["index"] == "rag-lei,rag-juris"

    def test_search_index_not_found(self, opensearch_service, mock_opensearch_client, mock_rag_config):
        """Test search returns empty on NotFoundError."""
        mock_opensearch_client.search.side_effect = NotFoundError(404, "index_not_found", {})

        with patch("app.services.rag.storage.opensearch_service.get_rag_config", return_value=mock_rag_config):
            results = opensearch_service.search_lexical(
                query="test",
                tenant_id="tenant-123",
            )

        assert results == []

    def test_search_error_returns_empty(self, opensearch_service, mock_opensearch_client, mock_rag_config):
        """Test search returns empty on general error."""
        mock_opensearch_client.search.side_effect = Exception("Search error")

        with patch("app.services.rag.storage.opensearch_service.get_rag_config", return_value=mock_rag_config):
            results = opensearch_service.search_lexical(
                query="test",
                tenant_id="tenant-123",
            )

        assert results == []

    def test_search_uses_brazilian_analyzer(self, mock_rag_config):
        """Test that index mapping uses Brazilian analyzer."""
        # Verify mapping configuration
        text_mapping = RAG_CHUNK_MAPPING["mappings"]["properties"]["text"]

        assert text_mapping["analyzer"] == "brazilian_analyzer"
        assert text_mapping["search_analyzer"] == "brazilian_analyzer"

    def test_brazilian_analyzer_configuration(self):
        """Test Brazilian analyzer has correct filters."""
        analyzer_config = RAG_CHUNK_MAPPING["settings"]["analysis"]["analyzer"]["brazilian_analyzer"]

        assert "brazilian_stop" in analyzer_config["filter"]
        assert "brazilian_stemmer" in analyzer_config["filter"]
        assert "lowercase" in analyzer_config["filter"]
        assert "asciifolding" in analyzer_config["filter"]


# =============================================================================
# Indexing Tests
# =============================================================================


class TestIndexing:
    """Tests for indexing operations."""

    def test_index_single_chunk(self, opensearch_service, mock_opensearch_client):
        """Test indexing a single chunk."""
        mock_opensearch_client.index.return_value = {"result": "created"}

        result = opensearch_service.index_chunk(
            chunk_uid="chunk-001",
            text="Texto de teste.",
            index="rag-local",
            doc_id="doc-001",
            scope="local",
            tenant_id="tenant-123",
            sigilo="publico",
        )

        assert result is True
        mock_opensearch_client.index.assert_called_once()

    def test_index_chunk_with_all_fields(self, opensearch_service, mock_opensearch_client):
        """Test indexing with all optional fields."""
        mock_opensearch_client.index.return_value = {"result": "created"}

        result = opensearch_service.index_chunk(
            chunk_uid="chunk-001",
            text="Texto completo.",
            index="rag-local",
            doc_id="doc-001",
            scope="private",
            tenant_id="tenant-123",
            case_id="case-456",
            group_ids=["group-A"],
            allowed_users=["user-001"],
            sigilo="restrito",
            doc_hash="abc123",
            doc_version=2,
            chunk_index=5,
            page=10,
            title="Documento Teste",
            source_type="local",
            metadata={"custom": "value"},
            refresh=True,
        )

        assert result is True

        call_kwargs = mock_opensearch_client.index.call_args.kwargs
        body = call_kwargs["body"]

        assert body["scope"] == "private"
        assert body["case_id"] == "case-456"
        assert body["group_ids"] == ["group-A"]
        assert body["allowed_users"] == ["user-001"]
        assert body["sigilo"] == "restrito"
        assert body["page"] == 10
        assert body["metadata"] == {"custom": "value"}
        assert call_kwargs["refresh"] is True

    def test_index_chunk_failure(self, opensearch_service, mock_opensearch_client):
        """Test indexing failure."""
        mock_opensearch_client.index.side_effect = Exception("Indexing failed")

        result = opensearch_service.index_chunk(
            chunk_uid="chunk-001",
            text="Test",
            index="rag-local",
            doc_id="doc-001",
        )

        assert result is False

    def test_bulk_index_success(self, opensearch_service, mock_opensearch_client, sample_chunks):
        """Test bulk indexing success."""
        with patch("opensearchpy.helpers.bulk") as mock_bulk:
            mock_bulk.return_value = (3, [])

            results = opensearch_service.index_chunks_bulk(
                chunks=sample_chunks,
                index="rag-local",
                refresh=True,
            )

        assert results["success"] == 3
        assert results["failed"] == 0

    def test_bulk_index_partial_failure(self, opensearch_service, mock_opensearch_client, sample_chunks):
        """Test bulk indexing with partial failures."""
        with patch("opensearchpy.helpers.bulk") as mock_bulk:
            mock_bulk.return_value = (2, [{"error": "some error"}])

            results = opensearch_service.index_chunks_bulk(
                chunks=sample_chunks,
                index="rag-local",
            )

        assert results["success"] == 2
        assert results["failed"] == 1

    def test_bulk_index_complete_failure(self, opensearch_service, mock_opensearch_client, sample_chunks):
        """Test bulk indexing complete failure."""
        with patch("opensearchpy.helpers.bulk") as mock_bulk:
            mock_bulk.side_effect = Exception("Bulk failed")

            results = opensearch_service.index_chunks_bulk(
                chunks=sample_chunks,
                index="rag-local",
            )

        assert results["success"] == 0
        assert results["failed"] == 3


# =============================================================================
# Delete Operations Tests
# =============================================================================


class TestDeleteOperations:
    """Tests for delete operations."""

    def test_delete_local_older_than(self, opensearch_service, mock_opensearch_client, mock_rag_config):
        """Test TTL cleanup for local chunks."""
        mock_opensearch_client.delete_by_query.return_value = {"deleted": 5}

        with patch("app.services.rag.storage.opensearch_service.get_rag_config", return_value=mock_rag_config):
            deleted = opensearch_service.delete_local_older_than(days=7)

        assert deleted == 5
        mock_opensearch_client.delete_by_query.assert_called_once()

    def test_delete_local_older_than_with_tenant(self, opensearch_service, mock_opensearch_client, mock_rag_config):
        """Test TTL cleanup filtered by tenant."""
        mock_opensearch_client.delete_by_query.return_value = {"deleted": 3}

        with patch("app.services.rag.storage.opensearch_service.get_rag_config", return_value=mock_rag_config):
            deleted = opensearch_service.delete_local_older_than(
                days=7,
                tenant_id="tenant-123",
            )

        assert deleted == 3

        call_body = mock_opensearch_client.delete_by_query.call_args.kwargs["body"]
        must_clauses = call_body["query"]["bool"]["must"]

        tenant_clause = next((c for c in must_clauses if c.get("term", {}).get("tenant_id")), None)
        assert tenant_clause is not None

    def test_delete_local_older_than_index_not_found(self, opensearch_service, mock_opensearch_client, mock_rag_config):
        """Test TTL cleanup when index not found."""
        mock_opensearch_client.delete_by_query.side_effect = NotFoundError(404, "index_not_found", {})

        with patch("app.services.rag.storage.opensearch_service.get_rag_config", return_value=mock_rag_config):
            deleted = opensearch_service.delete_local_older_than(days=7)

        assert deleted == 0

    def test_delete_by_doc_id(self, opensearch_service, mock_opensearch_client, mock_rag_config):
        """Test deleting chunks by document ID."""
        mock_opensearch_client.delete_by_query.return_value = {"deleted": 10}

        with patch("app.services.rag.storage.opensearch_service.get_rag_config", return_value=mock_rag_config):
            deleted = opensearch_service.delete_by_doc_id(doc_id="doc-001")

        assert deleted == 10

    def test_delete_by_doc_id_with_tenant(self, opensearch_service, mock_opensearch_client, mock_rag_config):
        """Test deleting chunks by document ID with tenant filter."""
        mock_opensearch_client.delete_by_query.return_value = {"deleted": 5}

        with patch("app.services.rag.storage.opensearch_service.get_rag_config", return_value=mock_rag_config):
            deleted = opensearch_service.delete_by_doc_id(
                doc_id="doc-001",
                tenant_id="tenant-123",
            )

        assert deleted == 5

        call_body = mock_opensearch_client.delete_by_query.call_args.kwargs["body"]
        must_clauses = call_body["query"]["bool"]["must"]

        assert len(must_clauses) == 2  # doc_id + tenant_id

    def test_delete_by_doc_id_specific_index(self, opensearch_service, mock_opensearch_client, mock_rag_config):
        """Test deleting from specific index."""
        mock_opensearch_client.delete_by_query.return_value = {"deleted": 3}

        with patch("app.services.rag.storage.opensearch_service.get_rag_config", return_value=mock_rag_config):
            deleted = opensearch_service.delete_by_doc_id(
                doc_id="doc-001",
                index="rag-local",
            )

        call_kwargs = mock_opensearch_client.delete_by_query.call_args.kwargs
        assert call_kwargs["index"] == "rag-local"

    def test_delete_by_doc_id_failure(self, opensearch_service, mock_opensearch_client, mock_rag_config):
        """Test delete failure returns 0."""
        mock_opensearch_client.delete_by_query.side_effect = Exception("Delete failed")

        with patch("app.services.rag.storage.opensearch_service.get_rag_config", return_value=mock_rag_config):
            deleted = opensearch_service.delete_by_doc_id(doc_id="doc-001")

        assert deleted == 0


# =============================================================================
# Utility Methods Tests
# =============================================================================


class TestUtilityMethods:
    """Tests for utility methods."""

    def test_get_chunk_success(self, opensearch_service, mock_opensearch_client):
        """Test getting a single chunk."""
        mock_opensearch_client.get.return_value = {
            "_source": {
                "chunk_uid": "chunk-001",
                "text": "Test text",
            }
        }

        chunk = opensearch_service.get_chunk("chunk-001", "rag-local")

        assert chunk is not None
        assert chunk["chunk_uid"] == "chunk-001"

    def test_get_chunk_not_found(self, opensearch_service, mock_opensearch_client):
        """Test getting non-existent chunk."""
        mock_opensearch_client.get.side_effect = NotFoundError(404, "not_found", {})

        chunk = opensearch_service.get_chunk("nonexistent", "rag-local")

        assert chunk is None

    def test_count_chunks_all(self, opensearch_service, mock_opensearch_client, mock_rag_config):
        """Test counting all chunks."""
        mock_opensearch_client.count.return_value = {"count": 1000}

        with patch("app.services.rag.storage.opensearch_service.get_rag_config", return_value=mock_rag_config):
            count = opensearch_service.count_chunks()

        assert count == 1000

    def test_count_chunks_with_filters(self, opensearch_service, mock_opensearch_client, mock_rag_config):
        """Test counting chunks with filters."""
        mock_opensearch_client.count.return_value = {"count": 50}

        with patch("app.services.rag.storage.opensearch_service.get_rag_config", return_value=mock_rag_config):
            count = opensearch_service.count_chunks(
                scope="global",
                tenant_id="tenant-123",
            )

        assert count == 50

        call_body = mock_opensearch_client.count.call_args.kwargs["body"]
        assert "bool" in call_body["query"]

    def test_count_chunks_specific_index(self, opensearch_service, mock_opensearch_client, mock_rag_config):
        """Test counting chunks in specific index."""
        mock_opensearch_client.count.return_value = {"count": 100}

        with patch("app.services.rag.storage.opensearch_service.get_rag_config", return_value=mock_rag_config):
            count = opensearch_service.count_chunks(index="rag-lei")

        call_kwargs = mock_opensearch_client.count.call_args.kwargs
        assert call_kwargs["index"] == "rag-lei"


# =============================================================================
# Singleton Tests
# =============================================================================


class TestSingleton:
    """Tests for singleton management."""

    def test_get_opensearch_service_creates_singleton(self, mock_rag_config):
        """Test get_opensearch_service creates singleton."""
        reset_opensearch_service()

        with patch("app.services.rag.storage.opensearch_service.get_rag_config", return_value=mock_rag_config):
            service1 = get_opensearch_service()
            service2 = get_opensearch_service()

            assert service1 is service2

        reset_opensearch_service()

    def test_reset_opensearch_service(self, mock_rag_config):
        """Test reset_opensearch_service clears singleton."""
        with patch("app.services.rag.storage.opensearch_service.get_rag_config", return_value=mock_rag_config):
            with patch("app.services.rag.storage.opensearch_service.OpenSearch") as mock_os:
                mock_client = MagicMock()
                mock_os.return_value = mock_client

                service = get_opensearch_service()
                _ = service.client  # Trigger client creation

                reset_opensearch_service()

                mock_client.close.assert_called()


# =============================================================================
# Index Mapping Tests
# =============================================================================


class TestIndexMapping:
    """Tests for index mapping configuration."""

    def test_mapping_has_required_fields(self):
        """Test mapping has all required fields."""
        props = RAG_CHUNK_MAPPING["mappings"]["properties"]

        required_fields = [
            "chunk_uid", "doc_id", "text", "scope", "tenant_id",
            "sigilo", "uploaded_at", "source_type"
        ]

        for field in required_fields:
            assert field in props, f"Missing required field: {field}"

    def test_text_field_has_raw_subfield(self):
        """Test text field has raw keyword subfield."""
        text_props = RAG_CHUNK_MAPPING["mappings"]["properties"]["text"]

        assert "fields" in text_props
        assert "raw" in text_props["fields"]
        assert text_props["fields"]["raw"]["type"] == "keyword"

    def test_security_fields_are_keyword(self):
        """Test security fields are keyword type for exact matching."""
        props = RAG_CHUNK_MAPPING["mappings"]["properties"]

        security_fields = ["scope", "tenant_id", "sigilo", "group_ids", "allowed_users"]

        for field in security_fields:
            assert props[field]["type"] == "keyword", f"{field} should be keyword type"

    def test_settings_has_shards_and_replicas(self):
        """Test settings has shards and replicas configured."""
        settings = RAG_CHUNK_MAPPING["settings"]

        assert "number_of_shards" in settings
        assert "number_of_replicas" in settings
        assert settings["number_of_shards"] >= 1
        assert settings["number_of_replicas"] >= 0
