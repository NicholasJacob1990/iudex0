"""
GDS Analytics — Graph Data Science algorithms for legal knowledge graph.

Provides PageRank (entity importance), Leiden (community detection),
and Node Similarity (entity resolution complement) via the
graphdatascience Python client.

Requires:
    pip install graphdatascience>=1.6.0
    Neo4j GDS plugin enabled (docker-compose.rag.yml already has it)

Usage:
    from app.services.rag.core.gds_analytics import get_gds_client
    gds = get_gds_client()
    scores = gds.compute_pagerank(tenant_id="t1")
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class PageRankResult:
    """Result of PageRank computation."""
    entity_scores: Dict[str, float]  # {entity_id: score}
    total_entities: int = 0
    iterations: int = 0

    @property
    def top_entities(self) -> List[Tuple[str, float]]:
        """Top 20 entities by PageRank score."""
        return sorted(self.entity_scores.items(), key=lambda x: x[1], reverse=True)[:20]


@dataclass
class CommunityResult:
    """Result of community detection."""
    communities: List[Dict[str, Any]]  # [{id, members, size, ...}]
    total_communities: int = 0
    modularity: float = 0.0


@dataclass
class SimilarityResult:
    """Result of node similarity."""
    pairs: List[Dict[str, Any]]  # [{entity1, entity2, score}]
    total_pairs: int = 0


# =============================================================================
# GDS CLIENT
# =============================================================================

class Neo4jGDSClient:
    """
    Wrapper for Neo4j Graph Data Science algorithms.

    All methods project a tenant-scoped subgraph before running algorithms,
    ensuring multi-tenant isolation.
    """

    def __init__(self, uri: str, user: str, password: str, database: str = "iudex"):
        self._uri = uri
        self._user = user
        self._password = password
        self._database = database
        self._gds = None

    def _get_gds(self):
        """Lazy-load GDS client."""
        if self._gds is None:
            from graphdatascience import GraphDataScience
            self._gds = GraphDataScience(
                self._uri,
                auth=(self._user, self._password),
                database=self._database,
            )
            logger.info("GDS client connected to %s (db=%s)", self._uri, self._database)
        return self._gds

    @classmethod
    def from_env(cls) -> "Neo4jGDSClient":
        """Create from environment variables (same as Neo4jMVPConfig)."""
        from app.services.rag.core.neo4j_mvp import Neo4jMVPConfig
        config = Neo4jMVPConfig.from_env()
        return cls(
            uri=config.uri,
            user=config.user,
            password=config.password,
            database=config.database,
        )

    # =========================================================================
    # GRAPH PROJECTION (tenant-scoped)
    # =========================================================================

    def _project_entity_graph(
        self,
        tenant_id: str,
        graph_name: str = "entity_graph",
    ) -> Any:
        """
        Project a subgraph of Entity nodes connected by RELATED_TO/MENTIONS.

        Filters by tenant_id via Document → Chunk → Entity path.
        Returns the projected graph object.
        """
        gds = self._get_gds()

        # Drop existing projection if present
        try:
            existing = gds.graph.get(graph_name)
            existing.drop()
        except Exception:
            pass

        # Cypher projection: entities connected to chunks of tenant's documents
        node_query = """
            MATCH (d:Document)-[:HAS_CHUNK]->(c:Chunk)-[:MENTIONS]->(e:Entity)
            WHERE d.tenant_id = $tenant_id
            RETURN id(e) AS id, labels(e) AS labels,
                   e.entity_id AS entity_id, e.name AS name
        """
        relationship_query = """
            MATCH (d:Document)-[:HAS_CHUNK]->(c:Chunk)-[:MENTIONS]->(e1:Entity)
            WHERE d.tenant_id = $tenant_id
            WITH collect(DISTINCT e1) AS tenant_entities
            UNWIND tenant_entities AS e1
            MATCH (e1)-[r:RELATED_TO|MENTIONS]-(e2:Entity)
            WHERE e2 IN tenant_entities
            RETURN id(e1) AS source, id(e2) AS target, type(r) AS type
        """

        try:
            G, stats = gds.graph.cypher.project(
                graph_name,
                node_query,
                relationship_query,
                parameters={"tenant_id": tenant_id},
            )
            logger.info(
                "Projected graph '%s': %d nodes, %d rels",
                graph_name, G.node_count(), G.relationship_count(),
            )
            return G
        except Exception as e:
            logger.error("Failed to project graph: %s", e)
            raise

    # =========================================================================
    # PAGERANK
    # =========================================================================

    def compute_pagerank(
        self,
        tenant_id: str,
        *,
        max_iterations: int = 20,
        damping_factor: float = 0.85,
        write_property: bool = True,
    ) -> PageRankResult:
        """
        Compute PageRank for entities in a tenant's graph.

        Entities with more RELATED_TO connections from other frequently-cited
        entities will have higher scores.

        Args:
            tenant_id: Tenant to scope the computation
            max_iterations: PageRank iterations
            damping_factor: PageRank damping factor
            write_property: If True, write scores back to Neo4j entity nodes

        Returns:
            PageRankResult with entity_id → score mapping
        """
        gds = self._get_gds()
        graph_name = f"pr_{tenant_id[:8]}"

        try:
            G = self._project_entity_graph(tenant_id, graph_name)

            if G.node_count() == 0:
                return PageRankResult(entity_scores={}, total_entities=0)

            result = gds.pageRank.stream(
                G,
                maxIterations=max_iterations,
                dampingFactor=damping_factor,
            )

            scores: Dict[str, float] = {}
            for _, row in result.iterrows():
                node_id = row.get("nodeId")
                score = row.get("score", 0.0)
                # Get entity_id from node properties
                props = gds.util.asNode(node_id)
                entity_id = props.get("entity_id", str(node_id)) if hasattr(props, "get") else str(node_id)
                scores[entity_id] = round(score, 6)

            # Optionally write scores back to Neo4j
            if write_property and scores:
                self._write_pagerank_scores(tenant_id, scores)

            return PageRankResult(
                entity_scores=scores,
                total_entities=len(scores),
                iterations=max_iterations,
            )
        finally:
            try:
                gds.graph.get(graph_name).drop()
            except Exception:
                pass

    def _write_pagerank_scores(self, tenant_id: str, scores: Dict[str, float]) -> None:
        """Write tenant-scoped PageRank scores without cross-tenant overwrite."""
        gds = self._get_gds()
        try:
            score_list = [{"entity_id": eid, "score": s} for eid, s in scores.items()]
            gds.run_cypher(
                """
                MATCH (m:TenantEntityMetric {tenant_id: $tenant_id})
                DETACH DELETE m
                """,
                params={"tenant_id": tenant_id},
            )
            gds.run_cypher(
                """
                UNWIND $scores AS item
                MATCH (e:Entity {entity_id: item.entity_id})
                MERGE (m:TenantEntityMetric {tenant_id: $tenant_id, entity_id: item.entity_id})
                SET m.pagerank_score = item.score,
                    m.updated_at = datetime()
                MERGE (e)-[:HAS_TENANT_METRIC]->(m)
                """,
                params={"tenant_id": tenant_id, "scores": score_list},
            )
            logger.info("Wrote PageRank scores for %d entities (tenant=%s)", len(scores), tenant_id)
        except Exception as e:
            logger.warning("Failed to write PageRank scores: %s", e)

    # =========================================================================
    # LEIDEN COMMUNITY DETECTION
    # =========================================================================

    def detect_communities(
        self,
        tenant_id: str,
        *,
        max_levels: int = 10,
        gamma: float = 1.0,
        min_community_size: int = 2,
    ) -> CommunityResult:
        """
        Detect communities of related entities using Leiden algorithm.

        Groups entities that frequently co-occur or are densely connected
        (e.g., a cluster around "licitações": Lei 14.133, Art. 55, STF, etc.)

        Args:
            tenant_id: Tenant scope
            max_levels: Maximum Leiden hierarchy levels
            gamma: Resolution parameter (higher = more communities)
            min_community_size: Minimum entities per community

        Returns:
            CommunityResult with community members
        """
        gds = self._get_gds()
        graph_name = f"leiden_{tenant_id[:8]}"

        try:
            G = self._project_entity_graph(tenant_id, graph_name)

            if G.node_count() < min_community_size:
                return CommunityResult(communities=[], total_communities=0)

            result = gds.leiden.stream(
                G,
                maxLevels=max_levels,
                gamma=gamma,
            )

            # Group by community ID
            community_map: Dict[int, List[Dict[str, Any]]] = {}
            for _, row in result.iterrows():
                comm_id = int(row.get("communityId", 0))
                node_id = row.get("nodeId")
                props = gds.util.asNode(node_id)

                member = {
                    "entity_id": props.get("entity_id", str(node_id)) if hasattr(props, "get") else str(node_id),
                    "name": props.get("name", "") if hasattr(props, "get") else "",
                }

                if comm_id not in community_map:
                    community_map[comm_id] = []
                community_map[comm_id].append(member)

            # Filter by min size and format
            communities = []
            for comm_id, members in community_map.items():
                if len(members) >= min_community_size:
                    communities.append({
                        "community_id": comm_id,
                        "size": len(members),
                        "members": members,
                        "member_names": [m["name"] for m in members[:10]],
                    })

            communities.sort(key=lambda c: c["size"], reverse=True)

            return CommunityResult(
                communities=communities,
                total_communities=len(communities),
            )
        finally:
            try:
                gds.graph.get(graph_name).drop()
            except Exception:
                pass

    # =========================================================================
    # NODE SIMILARITY
    # =========================================================================

    def find_similar_entities(
        self,
        tenant_id: str,
        *,
        top_k: int = 10,
        similarity_cutoff: float = 0.5,
    ) -> SimilarityResult:
        """
        Find structurally similar entities using Node Similarity.

        Two entities are similar if they co-occur with the same neighbors.
        Complements fuzzy string matching in fuzzy_resolver.

        Args:
            tenant_id: Tenant scope
            top_k: Number of similar pairs per entity
            similarity_cutoff: Minimum similarity score

        Returns:
            SimilarityResult with entity pairs and scores
        """
        gds = self._get_gds()
        graph_name = f"sim_{tenant_id[:8]}"

        try:
            G = self._project_entity_graph(tenant_id, graph_name)

            if G.node_count() < 2:
                return SimilarityResult(pairs=[], total_pairs=0)

            result = gds.nodeSimilarity.stream(
                G,
                topK=top_k,
                similarityCutoff=similarity_cutoff,
            )

            pairs = []
            for _, row in result.iterrows():
                node1 = gds.util.asNode(row.get("node1"))
                node2 = gds.util.asNode(row.get("node2"))
                score = row.get("similarity", 0.0)

                e1_id = node1.get("entity_id", "") if hasattr(node1, "get") else ""
                e2_id = node2.get("entity_id", "") if hasattr(node2, "get") else ""
                e1_name = node1.get("name", "") if hasattr(node1, "get") else ""
                e2_name = node2.get("name", "") if hasattr(node2, "get") else ""

                pairs.append({
                    "entity1_id": e1_id,
                    "entity1_name": e1_name,
                    "entity2_id": e2_id,
                    "entity2_name": e2_name,
                    "similarity": round(score, 4),
                })

            return SimilarityResult(pairs=pairs, total_pairs=len(pairs))
        finally:
            try:
                gds.graph.get(graph_name).drop()
            except Exception:
                pass


# =============================================================================
# SINGLETON
# =============================================================================

_gds_client: Optional[Neo4jGDSClient] = None


def get_gds_client() -> Neo4jGDSClient:
    """Get or create singleton GDS client."""
    global _gds_client
    if _gds_client is None:
        _gds_client = Neo4jGDSClient.from_env()
    return _gds_client
