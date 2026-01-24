"""
Tests for TTL cleanup functionality.

Validates that ttl_cleanup uses the correct timestamp field (uploaded_at)
for both OpenSearch and Qdrant.
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch, PropertyMock

from app.services.rag.utils.ttl_cleanup import (
    cleanup_local_opensearch,
    cleanup_local_qdrant,
    run_ttl_cleanup,
    CleanupStats,
)


class TestOpenSearchCleanup:
    """Tests for OpenSearch TTL cleanup."""

    @patch("app.services.rag.utils.ttl_cleanup._get_opensearch_client")
    @patch("app.services.rag.utils.ttl_cleanup.get_rag_config")
    def test_cleanup_uses_uploaded_at_field(self, mock_config, mock_get_client):
        """Verify OpenSearch cleanup queries use 'uploaded_at' field."""
        # Setup mock config
        config = MagicMock()
        config.local_ttl_days = 7
        config.opensearch_index_local = "rag-local"
        mock_config.return_value = config

        # Setup mock client
        mock_client = MagicMock()
        mock_client.indices.exists.return_value = True
        mock_client.delete_by_query.return_value = {"deleted": 5, "failures": []}
        mock_get_client.return_value = mock_client

        # Run cleanup
        deleted, errors = cleanup_local_opensearch(ttl_days=7, dry_run=False)

        # Verify delete_by_query was called
        mock_client.delete_by_query.assert_called_once()
        call_args = mock_client.delete_by_query.call_args

        # Extract the query body
        query_body = call_args.kwargs.get("body") or call_args[1].get("body")

        # Verify the query uses 'uploaded_at' field
        must_clause = query_body["query"]["bool"]["must"]
        assert len(must_clause) == 1
        assert "uploaded_at" in must_clause[0]["range"]

        # Verify it does NOT use old field names
        query_str = str(query_body)
        assert "ingested_at" not in query_str
        assert "created_at" not in query_str
        assert "timestamp" not in query_str or "uploaded_at" in query_str

    @patch("app.services.rag.utils.ttl_cleanup._get_opensearch_client")
    @patch("app.services.rag.utils.ttl_cleanup.get_rag_config")
    def test_dry_run_counts_correctly(self, mock_config, mock_get_client):
        """Verify dry run mode counts documents without deleting."""
        config = MagicMock()
        config.local_ttl_days = 7
        config.opensearch_index_local = "rag-local"
        mock_config.return_value = config

        mock_client = MagicMock()
        mock_client.indices.exists.return_value = True
        mock_client.count.return_value = {"count": 42}
        mock_get_client.return_value = mock_client

        deleted, errors = cleanup_local_opensearch(ttl_days=7, dry_run=True)

        assert deleted == 42
        assert len(errors) == 0
        mock_client.delete_by_query.assert_not_called()


class TestQdrantCleanup:
    """Tests for Qdrant TTL cleanup."""

    def test_timestamp_fields_list_uses_uploaded_at(self):
        """Verify the timestamp_fields list in cleanup code uses 'uploaded_at'."""
        # Read the source code and verify it uses the correct field
        import inspect
        from app.services.rag.utils.ttl_cleanup import cleanup_local_qdrant

        source = inspect.getsource(cleanup_local_qdrant)

        # Verify 'uploaded_at' is in timestamp_fields
        assert 'timestamp_fields = ["uploaded_at"]' in source, (
            "Expected timestamp_fields to use 'uploaded_at'"
        )

        # Verify old incorrect fields are NOT used
        assert 'timestamp_fields = ["ingested_at"' not in source, (
            "Should not use 'ingested_at' as primary field"
        )
        assert '"created_at", "timestamp"' not in source, (
            "Should not use multiple fallback fields that don't exist"
        )


class TestCleanupStats:
    """Tests for CleanupStats dataclass."""

    def test_total_deleted(self):
        """Verify total_deleted property."""
        stats = CleanupStats()
        stats.opensearch_deleted = 10
        stats.qdrant_deleted = 5
        assert stats.total_deleted == 15

    def test_has_errors(self):
        """Verify has_errors property."""
        stats = CleanupStats()
        assert stats.has_errors is False

        stats.opensearch_errors.append("error1")
        assert stats.has_errors is True

    def test_to_dict(self):
        """Verify to_dict serialization."""
        stats = CleanupStats()
        stats.opensearch_deleted = 10
        stats.qdrant_deleted = 5
        stats.completed_at = datetime.now(timezone.utc)

        result = stats.to_dict()
        assert result["opensearch_deleted"] == 10
        assert result["qdrant_deleted"] == 5
        assert result["total_deleted"] == 15
        assert "started_at" in result
        assert "completed_at" in result


class TestRunTTLCleanup:
    """Tests for combined cleanup execution."""

    @patch("app.services.rag.utils.ttl_cleanup.cleanup_local_qdrant")
    @patch("app.services.rag.utils.ttl_cleanup.cleanup_local_opensearch")
    @patch("app.services.rag.utils.ttl_cleanup.get_rag_config")
    def test_runs_both_cleanups(self, mock_config, mock_os_cleanup, mock_qd_cleanup):
        """Verify run_ttl_cleanup executes both cleanups."""
        config = MagicMock()
        config.local_ttl_days = 7
        mock_config.return_value = config

        mock_os_cleanup.return_value = (10, [])
        mock_qd_cleanup.return_value = (5, [])

        stats = run_ttl_cleanup(ttl_days=7)

        assert stats.opensearch_deleted == 10
        assert stats.qdrant_deleted == 5
        assert stats.total_deleted == 15
        assert not stats.has_errors

        mock_os_cleanup.assert_called_once()
        mock_qd_cleanup.assert_called_once()

    @patch("app.services.rag.utils.ttl_cleanup.cleanup_local_qdrant")
    @patch("app.services.rag.utils.ttl_cleanup.cleanup_local_opensearch")
    @patch("app.services.rag.utils.ttl_cleanup.get_rag_config")
    def test_skip_flags_work(self, mock_config, mock_os_cleanup, mock_qd_cleanup):
        """Verify skip flags prevent cleanup execution."""
        config = MagicMock()
        config.local_ttl_days = 7
        mock_config.return_value = config

        mock_os_cleanup.return_value = (0, [])
        mock_qd_cleanup.return_value = (0, [])

        # Skip OpenSearch
        run_ttl_cleanup(skip_opensearch=True)
        mock_os_cleanup.assert_not_called()
        mock_qd_cleanup.assert_called_once()

        mock_qd_cleanup.reset_mock()

        # Skip Qdrant
        run_ttl_cleanup(skip_qdrant=True)
        mock_os_cleanup.assert_called_once()
        mock_qd_cleanup.assert_not_called()
