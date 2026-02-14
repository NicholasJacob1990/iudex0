"""
Tests for GDS Analytics — Neo4j Graph Data Science wrapper.

Mocks the graphdatascience client to test without Neo4j.
"""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from typing import Dict, Any


class TestNeo4jGDSClient:
    """Tests for Neo4jGDSClient algorithms wrapper."""

    @pytest.fixture
    def mock_gds(self):
        """Create a mock GDS client."""
        gds = MagicMock()
        # Mock graph projection
        mock_graph = MagicMock()
        mock_graph.node_count.return_value = 10
        mock_graph.relationship_count.return_value = 25
        gds.graph.cypher.project.return_value = (mock_graph, {})
        gds.graph.get.return_value = mock_graph
        return gds

    @pytest.fixture
    def client(self, mock_gds):
        """Create a Neo4jGDSClient with mocked GDS."""
        from app.services.rag.core.gds_analytics import Neo4jGDSClient
        c = Neo4jGDSClient(
            uri="bolt://localhost:8687",
            user="neo4j",
            password="test",
            database="iudex",
        )
        c._gds = mock_gds
        return c

    def test_init_stores_config(self):
        """Test that constructor stores config."""
        from app.services.rag.core.gds_analytics import Neo4jGDSClient
        c = Neo4jGDSClient(uri="bolt://host:7687", user="u", password="p", database="db")
        assert c._uri == "bolt://host:7687"
        assert c._user == "u"
        assert c._database == "db"
        assert c._gds is None  # lazy

    def test_compute_pagerank_returns_scores(self, client, mock_gds):
        """Test PageRank returns valid entity_scores dict."""
        import pandas as pd

        # Mock PageRank stream result
        pr_df = pd.DataFrame({
            "nodeId": [1, 2, 3],
            "score": [0.85, 0.42, 0.15],
        })
        mock_gds.pageRank.stream.return_value = pr_df

        # Mock node lookup — return different entity_id for each node
        entity_ids = ["lei_8666_1993", "art_5", "stf"]
        call_idx = {"i": 0}

        def mock_as_node(nid):
            n = MagicMock()
            eid = entity_ids[call_idx["i"] % len(entity_ids)]
            call_idx["i"] += 1
            n.get.side_effect = lambda key, default="": {
                "entity_id": eid,
                "name": f"Entity {eid}",
            }.get(key, default)
            return n

        mock_gds.util.asNode.side_effect = mock_as_node

        # Mock write (no-op)
        mock_gds.run_cypher.return_value = None

        result = client.compute_pagerank("tenant_abc")

        assert result.total_entities == 3
        assert len(result.entity_scores) == 3
        assert all(isinstance(v, float) for v in result.entity_scores.values())
        mock_gds.pageRank.stream.assert_called_once()

    def test_compute_pagerank_empty_graph(self, client, mock_gds):
        """Test PageRank with empty graph returns empty."""
        mock_graph = MagicMock()
        mock_graph.node_count.return_value = 0
        mock_gds.graph.cypher.project.return_value = (mock_graph, {})

        result = client.compute_pagerank("tenant_empty")

        assert result.total_entities == 0
        assert result.entity_scores == {}

    def test_detect_communities_returns_groups(self, client, mock_gds):
        """Test Leiden community detection groups entities."""
        import pandas as pd

        leiden_df = pd.DataFrame({
            "nodeId": [1, 2, 3, 4, 5],
            "communityId": [0, 0, 0, 1, 1],
        })
        mock_gds.leiden.stream.return_value = leiden_df

        mock_node = MagicMock()
        call_count = {"n": 0}
        names = ["Lei 8.666", "Art. 5", "STF", "Lei 14.133", "Art. 37"]

        def mock_as_node(nid):
            n = MagicMock()
            idx = call_count["n"]
            call_count["n"] += 1
            n.get.side_effect = lambda key, default="": {
                "entity_id": f"e_{nid}",
                "name": names[idx % len(names)],
            }.get(key, default)
            return n

        mock_gds.util.asNode.side_effect = mock_as_node

        result = client.detect_communities("tenant_test", min_community_size=2)

        assert result.total_communities == 2
        assert len(result.communities) == 2
        # First community should be larger (3 members)
        assert result.communities[0]["size"] == 3
        assert result.communities[1]["size"] == 2

    def test_detect_communities_filters_small(self, client, mock_gds):
        """Test that communities below min_size are filtered out."""
        import pandas as pd

        leiden_df = pd.DataFrame({
            "nodeId": [1, 2, 3],
            "communityId": [0, 1, 2],  # each community has 1 member
        })
        mock_gds.leiden.stream.return_value = leiden_df

        mock_gds.util.asNode.return_value = MagicMock(
            get=lambda key, default="": {"entity_id": "e_1", "name": "X"}.get(key, default)
        )

        result = client.detect_communities("t1", min_community_size=2)

        assert result.total_communities == 0

    def test_find_similar_entities(self, client, mock_gds):
        """Test node similarity returns entity pairs."""
        import pandas as pd

        sim_df = pd.DataFrame({
            "node1": [1, 2],
            "node2": [3, 4],
            "similarity": [0.92, 0.78],
        })
        mock_gds.nodeSimilarity.stream.return_value = sim_df

        call_count = {"n": 0}
        ids = ["e_1", "e_2", "e_3", "e_4"]
        nms = ["Lei A", "Lei B", "Lei C", "Lei D"]

        def mock_as_node(nid):
            n = MagicMock()
            idx = call_count["n"]
            call_count["n"] += 1
            n.get.side_effect = lambda key, default="": {
                "entity_id": ids[idx % len(ids)],
                "name": nms[idx % len(nms)],
            }.get(key, default)
            return n

        mock_gds.util.asNode.side_effect = mock_as_node

        result = client.find_similar_entities("t1", top_k=5)

        assert result.total_pairs == 2
        assert result.pairs[0]["similarity"] == 0.92

    def test_project_graph_drops_existing(self, client, mock_gds):
        """Test that graph projection drops existing before creating new."""
        mock_existing = MagicMock()
        mock_gds.graph.get.return_value = mock_existing

        client._project_entity_graph("t1", "test_graph")

        mock_existing.drop.assert_called_once()
        mock_gds.graph.cypher.project.assert_called_once()


class TestPageRankResult:
    """Tests for PageRankResult dataclass."""

    def test_top_entities_sorted(self):
        from app.services.rag.core.gds_analytics import PageRankResult
        pr = PageRankResult(
            entity_scores={"a": 0.1, "b": 0.9, "c": 0.5},
            total_entities=3,
        )
        top = pr.top_entities
        assert top[0] == ("b", 0.9)
        assert top[1] == ("c", 0.5)
        assert len(top) == 3


class TestSingleton:
    """Test singleton pattern."""

    def test_get_gds_client_caches(self):
        from app.services.rag.core import gds_analytics
        # Reset
        gds_analytics._gds_client = None
        with patch.object(gds_analytics.Neo4jGDSClient, "from_env") as mock_from_env:
            mock_from_env.return_value = MagicMock()
            c1 = gds_analytics.get_gds_client()
            c2 = gds_analytics.get_gds_client()
            assert c1 is c2
            mock_from_env.assert_called_once()
        gds_analytics._gds_client = None  # cleanup
