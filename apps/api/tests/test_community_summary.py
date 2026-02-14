"""
Tests for Community Summary — Leiden clustering + LLM summarization.

Mocks GDS, LLM, and Neo4j to test without external dependencies.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Any, List


class TestDetectAndSummarizeCommunities:
    """Tests for the main community detection + summarization pipeline."""

    @pytest.fixture
    def mock_gds(self):
        """Mock GDS client returning 2 communities."""
        from app.services.rag.core.gds_analytics import CommunityResult
        gds = MagicMock()
        gds.detect_communities.return_value = CommunityResult(
            communities=[
                {
                    "community_id": 0,
                    "size": 3,
                    "members": [
                        {"entity_id": "e1", "name": "Lei 8.666"},
                        {"entity_id": "e2", "name": "Art. 55"},
                        {"entity_id": "e3", "name": "STF"},
                    ],
                    "member_names": ["Lei 8.666", "Art. 55", "STF"],
                },
                {
                    "community_id": 1,
                    "size": 2,
                    "members": [
                        {"entity_id": "e4", "name": "Lei 14.133"},
                        {"entity_id": "e5", "name": "TCU"},
                    ],
                    "member_names": ["Lei 14.133", "TCU"],
                },
            ],
            total_communities=2,
        )
        return gds

    @pytest.mark.asyncio
    async def test_pipeline_success(self, mock_gds):
        """Test full pipeline: detect → summarize → write."""
        mock_neo4j = MagicMock()
        mock_neo4j._execute_write.return_value = None

        with patch(
            "app.services.rag.core.gds_analytics.get_gds_client",
            return_value=mock_gds,
        ), patch(
            "app.services.rag.core.neo4j_mvp.get_neo4j_mvp",
            return_value=mock_neo4j,
        ):
            from app.services.rag.core.community_summary import detect_and_summarize_communities

            stats = await detect_and_summarize_communities(
                tenant_id="test_tenant",
                llm_provider="fallback",  # heuristic, no LLM call
            )

        assert stats.communities_detected == 2
        assert stats.communities_summarized == 2
        assert stats.entities_clustered == 5  # 3 + 2
        assert len(stats.errors) == 0

    @pytest.mark.asyncio
    async def test_gds_unavailable(self):
        """Test graceful fallback when GDS is unavailable."""
        with patch(
            "app.services.rag.core.gds_analytics.get_gds_client",
            side_effect=ImportError("GDS not installed"),
        ):
            from app.services.rag.core.community_summary import detect_and_summarize_communities

            stats = await detect_and_summarize_communities(tenant_id="t1")

        assert stats.communities_detected == 0
        assert len(stats.errors) >= 1

    @pytest.mark.asyncio
    async def test_no_communities_detected(self):
        """Test when Leiden finds no communities."""
        from app.services.rag.core.gds_analytics import CommunityResult
        mock_gds = MagicMock()
        mock_gds.detect_communities.return_value = CommunityResult(
            communities=[], total_communities=0,
        )

        with patch(
            "app.services.rag.core.gds_analytics.get_gds_client",
            return_value=mock_gds,
        ):
            from app.services.rag.core.community_summary import detect_and_summarize_communities

            stats = await detect_and_summarize_communities(tenant_id="t1")

        assert stats.communities_detected == 0
        assert stats.communities_summarized == 0


class TestSummarizeCommunity:
    """Tests for individual community summarization."""

    @pytest.mark.asyncio
    async def test_heuristic_fallback(self):
        """Test heuristic summary when LLM provider is 'fallback'."""
        from app.services.rag.core.community_summary import _summarize_community

        community = {
            "size": 3,
            "member_names": ["Lei 8.666", "Art. 55", "STF"],
        }
        result = await _summarize_community(community, llm_provider="fallback")

        assert result is not None
        assert "3" in result  # mentions size
        assert "Lei 8.666" in result

    @pytest.mark.asyncio
    async def test_empty_members_returns_none(self):
        """Test that empty member names returns None."""
        from app.services.rag.core.community_summary import _summarize_community

        result = await _summarize_community({"size": 0, "member_names": []})
        assert result is None


class TestGetCommunitySummariesForEntities:
    """Tests for community summary retrieval."""

    @pytest.mark.asyncio
    async def test_returns_summaries(self):
        """Test that retrieval returns community summaries."""
        mock_neo4j = MagicMock()
        mock_neo4j._execute_read.return_value = [
            {
                "community_id": "c1",
                "summary": "Cluster sobre licitações",
                "size": 5,
                "name": "Licitações",
            }
        ]

        with patch(
            "app.services.rag.core.neo4j_mvp.get_neo4j_mvp",
            return_value=mock_neo4j,
        ):
            from app.services.rag.core.community_summary import get_community_summaries_for_entities

            results = await get_community_summaries_for_entities(
                entity_ids=["e1", "e2"],
                tenant_id="t1",
            )

        assert len(results) == 1
        assert results[0]["summary"] == "Cluster sobre licitações"

    @pytest.mark.asyncio
    async def test_empty_entity_ids(self):
        """Test that empty entity_ids returns empty list."""
        from app.services.rag.core.community_summary import get_community_summaries_for_entities

        results = await get_community_summaries_for_entities(
            entity_ids=[], tenant_id="t1",
        )
        assert results == []

    @pytest.mark.asyncio
    async def test_neo4j_unavailable(self):
        """Test graceful fallback when Neo4j unavailable."""
        with patch(
            "app.services.rag.core.neo4j_mvp.get_neo4j_mvp",
            side_effect=Exception("Connection refused"),
        ):
            from app.services.rag.core.community_summary import get_community_summaries_for_entities

            results = await get_community_summaries_for_entities(
                entity_ids=["e1"], tenant_id="t1",
            )
        assert results == []


class TestCommunitySummaryStats:
    """Tests for the stats dataclass."""

    def test_default_errors_list(self):
        from app.services.rag.core.community_summary import CommunitySummaryStats
        stats = CommunitySummaryStats()
        assert stats.errors == []
        assert stats.communities_detected == 0


class TestNeo4jAsyncWrappers:
    @pytest.mark.asyncio
    async def test_execute_write_prefers_async_api(self):
        from app.services.rag.core.community_summary import _neo4j_execute_write

        neo4j = AsyncMock()
        neo4j._execute_write_async.return_value = [{"ok": 1}]

        result = await _neo4j_execute_write(neo4j, "RETURN 1", {})
        assert result == [{"ok": 1}]
        neo4j._execute_write_async.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_execute_read_prefers_async_api(self):
        from app.services.rag.core.community_summary import _neo4j_execute_read

        neo4j = AsyncMock()
        neo4j._execute_read_async.return_value = [{"ok": 1}]

        result = await _neo4j_execute_read(neo4j, "RETURN 1", {})
        assert result == [{"ok": 1}]
        neo4j._execute_read_async.assert_awaited_once()
