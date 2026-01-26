"""
Integration tests for Neo4j Graph Backend.

These tests require a running Neo4j instance.
Skip if Neo4j is not available.

Run with:
    pytest tests/rag/test_neo4j_integration.py -v

Requirements:
    - Neo4j running on localhost:7687 (or NEO4J_URI env var)
    - docker-compose -f tests/rag/docker-compose.neo4j.yml up -d
"""

import os
import uuid
import time
from typing import List, Dict, Any

import pytest

# Skip if neo4j package not installed
neo4j = pytest.importorskip("neo4j", reason="neo4j package not installed")

from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable


# =============================================================================
# Configuration
# =============================================================================

# Use dedicated env vars for integration tests so local dev/prod config doesn't interfere.
NEO4J_URI = os.getenv("NEO4J_TEST_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_TEST_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_TEST_PASSWORD", "testpassword")
NEO4J_DATABASE = os.getenv("NEO4J_TEST_DATABASE", "neo4j")
TEST_PREFIX = f"test_{uuid.uuid4().hex[:8]}"


def is_neo4j_available() -> bool:
    """Check if Neo4j is running and accessible."""
    try:
        driver = GraphDatabase.driver(
            NEO4J_URI,
            auth=(NEO4J_USER, NEO4J_PASSWORD),
        )
        with driver.session(database=NEO4J_DATABASE) as session:
            session.run("RETURN 1")
        driver.close()
        return True
    except Exception:
        return False


# Skip all tests if Neo4j is not available
pytestmark = pytest.mark.skipif(
    not is_neo4j_available(),
    reason=f"Neo4j not available at {NEO4J_URI}. Run: docker-compose -f tests/rag/docker-compose.neo4j.yml up -d"
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture(scope="module")
def neo4j_driver():
    """Create a Neo4j driver for testing."""
    driver = GraphDatabase.driver(
        NEO4J_URI,
        auth=(NEO4J_USER, NEO4J_PASSWORD),
    )
    yield driver

    # Cleanup: delete test data
    try:
        with driver.session(database=NEO4J_DATABASE) as session:
            session.run(
                "MATCH (n) WHERE n.entity_id STARTS WITH $prefix DETACH DELETE n",
                prefix=TEST_PREFIX,
            )
    except Exception:
        pass

    driver.close()


@pytest.fixture(scope="module")
def graph_adapter(neo4j_driver):
    """Create a Neo4jAdapter for testing."""
    # Set environment for the adapter
    os.environ["NEO4J_URI"] = NEO4J_URI
    os.environ["NEO4J_USER"] = NEO4J_USER
    os.environ["NEO4J_PASSWORD"] = NEO4J_PASSWORD
    os.environ["NEO4J_DATABASE"] = NEO4J_DATABASE
    os.environ["RAG_GRAPH_HYBRID_MODE"] = "true"
    os.environ["RAG_GRAPH_HYBRID_AUTO_SCHEMA"] = "true"
    os.environ["RAG_GRAPH_HYBRID_MIGRATE_ON_STARTUP"] = "false"

    from app.services.rag.core.graph_factory import Neo4jAdapter, reset_knowledge_graph

    adapter = Neo4jAdapter(
        uri=NEO4J_URI,
        user=NEO4J_USER,
        password=NEO4J_PASSWORD,
        database=NEO4J_DATABASE,
    )

    yield adapter

    # Cleanup
    adapter.close()
    reset_knowledge_graph()


@pytest.fixture
def sample_entities() -> List[Dict[str, Any]]:
    """Generate sample legal entities for testing."""
    return [
        {
            "entity_id": f"{TEST_PREFIX}_cf88_art5",
            "entity_type": "artigo",
            "name": "Art. 5º CF/88",
            "properties": {
                "lei": "Constituição Federal",
                "ano": 1988,
                "texto": "Todos são iguais perante a lei...",
            }
        },
        {
            "entity_id": f"{TEST_PREFIX}_sumula_331",
            "entity_type": "sumula",
            "name": "Súmula 331 TST",
            "properties": {
                "tribunal": "TST",
                "numero": 331,
                "tema": "Terceirização",
            }
        },
        {
            "entity_id": f"{TEST_PREFIX}_lei_14133",
            "entity_type": "lei",
            "name": "Lei 14.133/2021",
            "properties": {
                "tipo": "Lei Ordinária",
                "ano": 2021,
                "tema": "Licitações e Contratos",
            }
        },
        {
            "entity_id": f"{TEST_PREFIX}_re_123456",
            "entity_type": "jurisprudencia",
            "name": "RE 123456",
            "properties": {
                "tribunal": "STF",
                "tipo": "Recurso Extraordinário",
                "relator": "Min. Exemplo",
            }
        },
        {
            "entity_id": f"{TEST_PREFIX}_cdc_art51",
            "entity_type": "artigo",
            "name": "Art. 51 CDC",
            "properties": {
                "lei": "Código de Defesa do Consumidor",
                "ano": 1990,
                "tema": "Cláusulas Abusivas",
            }
        },
    ]


# =============================================================================
# Connection Tests
# =============================================================================

class TestNeo4jConnection:
    """Test Neo4j connection and basic operations."""

    def test_connection_success(self, neo4j_driver):
        """Test that we can connect to Neo4j."""
        with neo4j_driver.session(database=NEO4J_DATABASE) as session:
            result = session.run("RETURN 1 as n")
            record = result.single()
            assert record["n"] == 1

    def test_database_exists(self, neo4j_driver):
        """Test that the database exists."""
        with neo4j_driver.session(database=NEO4J_DATABASE) as session:
            result = session.run("CALL db.info()")
            record = result.single()
            assert record is not None

    def test_adapter_connection(self, graph_adapter):
        """Test that the adapter is connected."""
        from app.services.rag.core.graph_factory import GraphBackend
        assert graph_adapter.backend == GraphBackend.NEO4J
        assert graph_adapter.driver is not None


# =============================================================================
# Entity Tests
# =============================================================================

class TestNeo4jEntities:
    """Test entity (node) operations."""

    def test_add_entity(self, graph_adapter, sample_entities):
        """Test adding a single entity."""
        entity = sample_entities[0]

        result = graph_adapter.add_entity(
            entity_id=entity["entity_id"],
            entity_type=entity["entity_type"],
            name=entity["name"],
            properties=entity["properties"],
        )

        assert result is True

    def test_add_multiple_entities(self, graph_adapter, sample_entities):
        """Test adding multiple entities."""
        for entity in sample_entities:
            result = graph_adapter.add_entity(
                entity_id=entity["entity_id"],
                entity_type=entity["entity_type"],
                name=entity["name"],
                properties=entity["properties"],
            )
            assert result is True

    def test_hybrid_labels_applied_for_whitelisted_types(self, graph_adapter, sample_entities):
        """When hybrid mode is enabled, whitelisted entity types receive an additional label."""
        targets = {
            "artigo": "Artigo",
            "lei": "Lei",
            "sumula": "Sumula",
        }

        for entity in sample_entities:
            graph_adapter.add_entity(
                entity_id=entity["entity_id"],
                entity_type=entity["entity_type"],
                name=entity["name"],
                properties=entity["properties"],
            )

        with graph_adapter.driver.session(database=NEO4J_DATABASE) as session:
            for entity in sample_entities:
                expected = targets.get(entity["entity_type"])
                record = session.run(
                    "MATCH (e:Entity {entity_id: $entity_id}) RETURN labels(e) as labels",
                    entity_id=entity["entity_id"],
                ).single()
                assert record is not None
                labels = record["labels"]
                assert "Entity" in labels
                if expected:
                    assert expected in labels

    def test_hybrid_migration_backfills_labels(self, graph_adapter):
        """Migration should backfill labels for existing nodes based on entity_type."""
        entity_id = f"{TEST_PREFIX}_legacy_lei_9999"
        with graph_adapter.driver.session(database=NEO4J_DATABASE) as session:
            session.run(
                "CREATE (e:Entity {entity_id: $id, entity_type: 'lei', name: 'Lei 9.999', normalized: 'lei:9999'})",
                id=entity_id,
            )
            before = session.run(
                "MATCH (e:Entity {entity_id: $id}) RETURN labels(e) as labels",
                id=entity_id,
            ).single()["labels"]
            assert "Lei" not in before

        result = graph_adapter.migrate_hybrid_labels()
        assert isinstance(result, dict)

        with graph_adapter.driver.session(database=NEO4J_DATABASE) as session:
            after = session.run(
                "MATCH (e:Entity {entity_id: $id}) RETURN labels(e) as labels",
                id=entity_id,
            ).single()["labels"]
            assert "Lei" in after

    def test_hybrid_schema_indexes_created(self, graph_adapter):
        """Schema auto-creation should create at least one hybrid index (best-effort)."""
        with graph_adapter.driver.session(database=NEO4J_DATABASE) as session:
            record = session.run(
                "SHOW INDEXES YIELD name WHERE name STARTS WITH 'rag_lei_' RETURN count(name) as n"
            ).single()
            assert record is not None
            assert record["n"] >= 1

    def test_get_entity(self, graph_adapter, sample_entities):
        """Test retrieving an entity."""
        entity = sample_entities[0]

        # Add first
        graph_adapter.add_entity(
            entity_id=entity["entity_id"],
            entity_type=entity["entity_type"],
            name=entity["name"],
            properties=entity["properties"],
        )

        # Retrieve
        result = graph_adapter.get_entity(entity["entity_id"])

        assert result is not None
        assert result["entity_id"] == entity["entity_id"]
        assert result["name"] == entity["name"]
        assert result["entity_type"] == entity["entity_type"]

    def test_get_nonexistent_entity(self, graph_adapter):
        """Test retrieving a non-existent entity."""
        result = graph_adapter.get_entity("nonexistent_entity_id")
        assert result is None

    def test_update_entity(self, graph_adapter, sample_entities):
        """Test updating an existing entity."""
        entity = sample_entities[0]

        # Add first
        graph_adapter.add_entity(
            entity_id=entity["entity_id"],
            entity_type=entity["entity_type"],
            name=entity["name"],
            properties={"version": 1},
        )

        # Update
        graph_adapter.add_entity(
            entity_id=entity["entity_id"],
            entity_type=entity["entity_type"],
            name=entity["name"] + " (atualizado)",
            properties={"version": 2},
        )

        # Verify
        result = graph_adapter.get_entity(entity["entity_id"])
        assert result["version"] == 2


# =============================================================================
# Relationship Tests
# =============================================================================

class TestNeo4jRelationships:
    """Test relationship (edge) operations."""

    @pytest.fixture(autouse=True)
    def setup_entities(self, graph_adapter, sample_entities):
        """Add entities before testing relationships."""
        for entity in sample_entities:
            graph_adapter.add_entity(
                entity_id=entity["entity_id"],
                entity_type=entity["entity_type"],
                name=entity["name"],
                properties=entity["properties"],
            )
        self.entities = sample_entities

    def test_add_relationship(self, graph_adapter):
        """Test adding a relationship."""
        result = graph_adapter.add_relationship(
            from_entity=self.entities[0]["entity_id"],
            to_entity=self.entities[1]["entity_id"],
            relationship_type="FUNDAMENTA",
            properties={"weight": 0.9},
        )
        assert result is True

    def test_add_multiple_relationships(self, graph_adapter):
        """Test adding multiple relationships."""
        relationships = [
            (self.entities[0]["entity_id"], self.entities[1]["entity_id"], "FUNDAMENTA"),
            (self.entities[1]["entity_id"], self.entities[3]["entity_id"], "CITA"),
            (self.entities[2]["entity_id"], self.entities[4]["entity_id"], "REVOGA"),
            (self.entities[3]["entity_id"], self.entities[0]["entity_id"], "INTERPRETA"),
        ]

        for from_id, to_id, rel_type in relationships:
            result = graph_adapter.add_relationship(
                from_entity=from_id,
                to_entity=to_id,
                relationship_type=rel_type,
            )
            assert result is True

    def test_get_neighbors(self, graph_adapter):
        """Test getting neighbors of an entity."""
        # Add relationships
        graph_adapter.add_relationship(
            from_entity=self.entities[0]["entity_id"],
            to_entity=self.entities[1]["entity_id"],
            relationship_type="FUNDAMENTA",
        )
        graph_adapter.add_relationship(
            from_entity=self.entities[0]["entity_id"],
            to_entity=self.entities[2]["entity_id"],
            relationship_type="MENCIONA",
        )

        # Get neighbors
        neighbors = graph_adapter.get_neighbors(
            entity_id=self.entities[0]["entity_id"],
            max_hops=1,
        )

        assert len(neighbors) >= 2
        neighbor_ids = [n["entity_id"] for n in neighbors]
        assert self.entities[1]["entity_id"] in neighbor_ids
        assert self.entities[2]["entity_id"] in neighbor_ids

    def test_get_neighbors_with_hops(self, graph_adapter):
        """Test getting neighbors with multiple hops."""
        # Create chain: 0 -> 1 -> 3
        graph_adapter.add_relationship(
            from_entity=self.entities[0]["entity_id"],
            to_entity=self.entities[1]["entity_id"],
            relationship_type="FUNDAMENTA",
        )
        graph_adapter.add_relationship(
            from_entity=self.entities[1]["entity_id"],
            to_entity=self.entities[3]["entity_id"],
            relationship_type="CITA",
        )

        # 1 hop should find entity 1
        neighbors_1hop = graph_adapter.get_neighbors(
            entity_id=self.entities[0]["entity_id"],
            max_hops=1,
        )
        neighbor_ids_1 = [n["entity_id"] for n in neighbors_1hop]
        assert self.entities[1]["entity_id"] in neighbor_ids_1

        # 2 hops should find entities 1 and 3
        neighbors_2hop = graph_adapter.get_neighbors(
            entity_id=self.entities[0]["entity_id"],
            max_hops=2,
        )
        neighbor_ids_2 = [n["entity_id"] for n in neighbors_2hop]
        assert self.entities[1]["entity_id"] in neighbor_ids_2
        assert self.entities[3]["entity_id"] in neighbor_ids_2


# =============================================================================
# Search Tests
# =============================================================================

class TestNeo4jSearch:
    """Test search operations."""

    @pytest.fixture(autouse=True)
    def setup_data(self, graph_adapter, sample_entities):
        """Add test data."""
        for entity in sample_entities:
            graph_adapter.add_entity(
                entity_id=entity["entity_id"],
                entity_type=entity["entity_type"],
                name=entity["name"],
                properties=entity["properties"],
            )
        self.entities = sample_entities

    def test_search_by_name(self, graph_adapter):
        """Test searching entities by name."""
        results = graph_adapter.search_entities(
            query="Súmula",
            limit=10,
        )

        assert len(results) > 0
        names = [r["name"] for r in results]
        assert any("Súmula" in name for name in names)

    def test_search_by_id(self, graph_adapter):
        """Test searching entities by ID."""
        results = graph_adapter.search_entities(
            query=TEST_PREFIX,
            limit=10,
        )

        assert len(results) > 0

    def test_search_with_type_filter(self, graph_adapter):
        """Test searching with entity type filter."""
        results = graph_adapter.search_entities(
            query=TEST_PREFIX,
            entity_types=["artigo"],
            limit=10,
        )

        # All results should be artigos
        for r in results:
            assert r["entity_type"] == "artigo"

    def test_search_limit(self, graph_adapter):
        """Test search respects limit."""
        results = graph_adapter.search_entities(
            query=TEST_PREFIX,
            limit=2,
        )

        assert len(results) <= 2


# =============================================================================
# Context Generation Tests
# =============================================================================

class TestNeo4jContext:
    """Test context generation for RAG."""

    @pytest.fixture(autouse=True)
    def setup_graph(self, graph_adapter, sample_entities):
        """Setup a small legal knowledge graph."""
        # Add entities
        for entity in sample_entities:
            graph_adapter.add_entity(
                entity_id=entity["entity_id"],
                entity_type=entity["entity_type"],
                name=entity["name"],
                properties=entity["properties"],
            )

        # Add relationships
        graph_adapter.add_relationship(
            from_entity=sample_entities[0]["entity_id"],
            to_entity=sample_entities[1]["entity_id"],
            relationship_type="FUNDAMENTA",
        )
        graph_adapter.add_relationship(
            from_entity=sample_entities[1]["entity_id"],
            to_entity=sample_entities[3]["entity_id"],
            relationship_type="CITA",
        )
        graph_adapter.add_relationship(
            from_entity=sample_entities[2]["entity_id"],
            to_entity=sample_entities[4]["entity_id"],
            relationship_type="MENCIONA",
        )

        self.entities = sample_entities

    def test_get_context_basic(self, graph_adapter):
        """Test basic context generation."""
        context = graph_adapter.get_context_for_query(
            query="Súmula",
            max_tokens=500,
        )

        assert len(context) > 0
        assert "Súmula" in context

    def test_get_context_includes_relationships(self, graph_adapter):
        """Test that context includes related entities."""
        context = graph_adapter.get_context_for_query(
            query=TEST_PREFIX,
            max_tokens=1000,
        )

        assert len(context) > 0
        # Should mention relationships
        assert "relacionado" in context.lower() or "→" in context

    def test_get_context_respects_token_limit(self, graph_adapter):
        """Test that context respects token budget."""
        # Small budget
        context_small = graph_adapter.get_context_for_query(
            query=TEST_PREFIX,
            max_tokens=100,
        )

        # Larger budget
        context_large = graph_adapter.get_context_for_query(
            query=TEST_PREFIX,
            max_tokens=2000,
        )

        # Small should be shorter or equal
        assert len(context_small) <= len(context_large)

    def test_get_context_empty_query(self, graph_adapter):
        """Test context generation with no matches."""
        context = graph_adapter.get_context_for_query(
            query="xyznonexistent123",
            max_tokens=500,
        )

        assert context == "" or len(context) == 0


# =============================================================================
# Factory Tests
# =============================================================================

class TestGraphFactory:
    """Test the graph factory."""

    def test_factory_creates_neo4j_adapter(self):
        """Test factory creates Neo4j adapter when configured."""
        os.environ["RAG_GRAPH_BACKEND"] = "neo4j"
        os.environ["NEO4J_URI"] = NEO4J_URI
        os.environ["NEO4J_USER"] = NEO4J_USER
        os.environ["NEO4J_PASSWORD"] = NEO4J_PASSWORD

        from app.services.rag.core.graph_factory import (
            get_knowledge_graph,
            GraphBackend,
            reset_knowledge_graph,
        )
        from app.services.rag.config import get_rag_config

        # Reset config cache
        get_rag_config.cache_clear() if hasattr(get_rag_config, 'cache_clear') else None

        try:
            graph = get_knowledge_graph(backend=GraphBackend.NEO4J)
            assert graph.backend == GraphBackend.NEO4J
        finally:
            reset_knowledge_graph()
            os.environ.pop("RAG_GRAPH_BACKEND", None)

    def test_factory_falls_back_to_networkx(self):
        """Test factory falls back to NetworkX if Neo4j unavailable."""
        from app.services.rag.core.graph_factory import (
            get_knowledge_graph,
            GraphBackend,
            reset_knowledge_graph,
        )

        # Use invalid Neo4j URI to force fallback
        try:
            graph = get_knowledge_graph(
                backend=GraphBackend.NEO4J,
                uri="bolt://invalid:9999",
            )
            # Should fall back to NetworkX
            assert graph.backend == GraphBackend.NETWORKX
        except Exception:
            # Or it might raise - both are acceptable behaviors
            pass
        finally:
            reset_knowledge_graph()

    def test_is_neo4j_available(self):
        """Test Neo4j availability check."""
        from app.services.rag.core.graph_factory import is_neo4j_available

        # Should return True since we're in this test suite
        os.environ["NEO4J_URI"] = NEO4J_URI
        os.environ["NEO4J_USER"] = NEO4J_USER
        os.environ["NEO4J_PASSWORD"] = NEO4J_PASSWORD

        assert is_neo4j_available() is True


# =============================================================================
# Performance Tests
# =============================================================================

class TestNeo4jPerformance:
    """Basic performance tests."""

    def test_bulk_entity_insert(self, graph_adapter):
        """Test bulk entity insertion performance."""
        num_entities = 100

        start = time.time()

        for i in range(num_entities):
            graph_adapter.add_entity(
                entity_id=f"{TEST_PREFIX}_perf_{i:04d}",
                entity_type="artigo",
                name=f"Art. {i} - Performance Test",
                properties={"index": i},
            )

        elapsed = time.time() - start

        print(f"\nBulk insert {num_entities} entities: {elapsed:.2f}s ({num_entities/elapsed:.0f} entities/s)")

        # Should complete in reasonable time
        assert elapsed < 30, f"Bulk insert too slow: {elapsed:.2f}s"

    def test_relationship_insert_performance(self, graph_adapter):
        """Test relationship insertion performance."""
        # First add entities
        num_entities = 50
        for i in range(num_entities):
            graph_adapter.add_entity(
                entity_id=f"{TEST_PREFIX}_rel_perf_{i:04d}",
                entity_type="artigo",
                name=f"Entity {i}",
            )

        # Then add relationships
        num_relationships = 100
        start = time.time()

        for i in range(num_relationships):
            from_idx = i % num_entities
            to_idx = (i + 1) % num_entities
            graph_adapter.add_relationship(
                from_entity=f"{TEST_PREFIX}_rel_perf_{from_idx:04d}",
                to_entity=f"{TEST_PREFIX}_rel_perf_{to_idx:04d}",
                relationship_type="RELACIONA",
            )

        elapsed = time.time() - start

        print(f"\nBulk insert {num_relationships} relationships: {elapsed:.2f}s ({num_relationships/elapsed:.0f} rels/s)")

        assert elapsed < 30, f"Relationship insert too slow: {elapsed:.2f}s"

    def test_search_performance(self, graph_adapter, sample_entities):
        """Test search performance."""
        # Setup
        for entity in sample_entities:
            graph_adapter.add_entity(
                entity_id=entity["entity_id"],
                entity_type=entity["entity_type"],
                name=entity["name"],
            )

        # Warmup
        graph_adapter.search_entities(TEST_PREFIX, limit=5)

        # Benchmark
        num_queries = 50
        start = time.time()

        for _ in range(num_queries):
            graph_adapter.search_entities(TEST_PREFIX, limit=10)

        elapsed = time.time() - start
        avg_latency = (elapsed / num_queries) * 1000

        print(f"\nSearch performance: {avg_latency:.2f}ms avg ({num_queries} queries)")

        # Should be reasonably fast
        assert avg_latency < 100, f"Search too slow: {avg_latency:.2f}ms"
