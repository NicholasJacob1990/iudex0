"""
Integration tests for QdrantService with real Qdrant instance.

These tests require a running Qdrant instance.
Skip if Qdrant is not available.

Run with:
    pytest tests/rag/test_qdrant_integration.py -v

Requirements:
    - Qdrant running on localhost:6333 (or QDRANT_URL env var)
    - docker run -d -p 6333:6333 qdrant/qdrant
"""

import os
import uuid
import time
from typing import List

import pytest

# Skip all tests if qdrant_client is not installed
qdrant_client = pytest.importorskip("qdrant_client", reason="qdrant_client not installed")

from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse


# =============================================================================
# Configuration
# =============================================================================

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
TEST_COLLECTION = f"test_integration_{uuid.uuid4().hex[:8]}"
EMBEDDING_DIM = 1536  # OpenAI ada-002 dimensions


def is_qdrant_available() -> bool:
    """Check if Qdrant is running and accessible."""
    try:
        client = QdrantClient(url=QDRANT_URL, timeout=5)
        client.get_collections()
        return True
    except Exception:
        return False


# Skip all tests if Qdrant is not available
pytestmark = pytest.mark.skipif(
    not is_qdrant_available(),
    reason=f"Qdrant not available at {QDRANT_URL}. Run: docker run -d -p 6333:6333 qdrant/qdrant"
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture(scope="module")
def qdrant_client_real():
    """Create a real Qdrant client for testing."""
    client = QdrantClient(url=QDRANT_URL)
    yield client
    # Cleanup: delete test collection if exists
    try:
        client.delete_collection(TEST_COLLECTION)
    except Exception:
        pass


def _search(client, *, collection_name, query_vector, limit=10, **kwargs):
    """Compatibility wrapper: use query_points (new API) with search-style kwargs."""
    if hasattr(client, "query_points"):
        resp = client.query_points(
            collection_name=collection_name,
            query=query_vector,
            limit=limit,
            **kwargs,
        )
        return getattr(resp, "points", [])
    return client.search(
        collection_name=collection_name,
        query_vector=query_vector,
        limit=limit,
        **kwargs,
    )


@pytest.fixture(scope="module")
def test_collection(qdrant_client_real):
    """Create a test collection and clean up after tests."""
    from qdrant_client.http.models import Distance, VectorParams

    # Delete if exists from previous failed run
    try:
        qdrant_client_real.delete_collection(TEST_COLLECTION)
    except Exception:
        pass

    # Create collection
    qdrant_client_real.create_collection(
        collection_name=TEST_COLLECTION,
        vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
    )

    yield TEST_COLLECTION

    # Cleanup
    try:
        qdrant_client_real.delete_collection(TEST_COLLECTION)
    except Exception:
        pass


@pytest.fixture
def sample_vectors() -> List[dict]:
    """Generate sample vectors for testing."""
    import random
    random.seed(42)

    return [
        {
            "id": str(uuid.uuid4()),
            "vector": [random.random() for _ in range(EMBEDDING_DIM)],
            "payload": {
                "text": "Artigo 5º da Constituição Federal garante direitos fundamentais.",
                "tenant_id": "tenant-001",
                "scope": "global",
                "sigilo": "publico",
                "doc_id": "doc-cf-001",
                "chunk_uid": f"chunk-{uuid.uuid4().hex[:8]}",
            }
        },
        {
            "id": str(uuid.uuid4()),
            "vector": [random.random() for _ in range(EMBEDDING_DIM)],
            "payload": {
                "text": "Súmula 331 do TST trata de terceirização trabalhista.",
                "tenant_id": "tenant-001",
                "scope": "local",
                "sigilo": "restrito",
                "doc_id": "doc-tst-001",
                "chunk_uid": f"chunk-{uuid.uuid4().hex[:8]}",
            }
        },
        {
            "id": str(uuid.uuid4()),
            "vector": [random.random() for _ in range(EMBEDDING_DIM)],
            "payload": {
                "text": "Lei 8.666/93 sobre licitações e contratos administrativos.",
                "tenant_id": "tenant-002",
                "scope": "global",
                "sigilo": "publico",
                "doc_id": "doc-lic-001",
                "chunk_uid": f"chunk-{uuid.uuid4().hex[:8]}",
            }
        },
    ]


# =============================================================================
# Connection Tests
# =============================================================================

class TestQdrantConnection:
    """Test Qdrant connection and basic operations."""

    def test_connection_success(self, qdrant_client_real):
        """Test that we can connect to Qdrant."""
        collections = qdrant_client_real.get_collections()
        assert collections is not None

    def test_collection_created(self, qdrant_client_real, test_collection):
        """Test that test collection was created."""
        collections = qdrant_client_real.get_collections()
        collection_names = [c.name for c in collections.collections]
        assert test_collection in collection_names

    def test_collection_info(self, qdrant_client_real, test_collection):
        """Test getting collection info."""
        info = qdrant_client_real.get_collection(test_collection)
        assert info.config.params.vectors.size == EMBEDDING_DIM


# =============================================================================
# Upsert Tests
# =============================================================================

class TestQdrantUpsert:
    """Test upsert operations."""

    def test_upsert_single_point(self, qdrant_client_real, test_collection, sample_vectors):
        """Test upserting a single point."""
        from qdrant_client.http.models import PointStruct

        point = sample_vectors[0]
        result = qdrant_client_real.upsert(
            collection_name=test_collection,
            points=[
                PointStruct(
                    id=point["id"],
                    vector=point["vector"],
                    payload=point["payload"],
                )
            ],
        )
        assert result.status == "completed"

    def test_upsert_batch(self, qdrant_client_real, test_collection, sample_vectors):
        """Test batch upsert."""
        from qdrant_client.http.models import PointStruct

        points = [
            PointStruct(id=v["id"], vector=v["vector"], payload=v["payload"])
            for v in sample_vectors
        ]

        result = qdrant_client_real.upsert(
            collection_name=test_collection,
            points=points,
        )
        assert result.status == "completed"

        # Verify count
        info = qdrant_client_real.get_collection(test_collection)
        assert info.points_count >= len(sample_vectors)

    def test_upsert_update_existing(self, qdrant_client_real, test_collection, sample_vectors):
        """Test that upsert updates existing points."""
        from qdrant_client.http.models import PointStruct

        point = sample_vectors[0]
        point_id = point["id"]

        # First upsert
        qdrant_client_real.upsert(
            collection_name=test_collection,
            points=[PointStruct(id=point_id, vector=point["vector"], payload={"version": 1})],
        )

        # Second upsert with same ID
        qdrant_client_real.upsert(
            collection_name=test_collection,
            points=[PointStruct(id=point_id, vector=point["vector"], payload={"version": 2})],
        )

        # Retrieve and verify
        retrieved = qdrant_client_real.retrieve(
            collection_name=test_collection,
            ids=[point_id],
        )
        assert len(retrieved) == 1
        assert retrieved[0].payload["version"] == 2


# =============================================================================
# Search Tests
# =============================================================================

class TestQdrantSearch:
    """Test search operations."""

    @pytest.fixture(autouse=True)
    def setup_data(self, qdrant_client_real, test_collection, sample_vectors):
        """Insert test data before each test."""
        from qdrant_client.http.models import PointStruct

        points = [
            PointStruct(id=v["id"], vector=v["vector"], payload=v["payload"])
            for v in sample_vectors
        ]
        qdrant_client_real.upsert(collection_name=test_collection, points=points)
        time.sleep(0.5)  # Wait for indexing
        self.sample_vectors = sample_vectors

    def test_search_basic(self, qdrant_client_real, test_collection):
        """Test basic vector search."""
        query_vector = self.sample_vectors[0]["vector"]

        results = _search(qdrant_client_real,
            collection_name=test_collection,
            query_vector=query_vector,
            limit=10,
        )

        assert len(results) > 0
        # First result should be the same vector (highest similarity)
        assert results[0].score > 0.9

    def test_search_with_filter_tenant(self, qdrant_client_real, test_collection):
        """Test search with tenant_id filter."""
        from qdrant_client.http.models import Filter, FieldCondition, MatchValue

        query_vector = self.sample_vectors[0]["vector"]

        results = _search(qdrant_client_real,
            collection_name=test_collection,
            query_vector=query_vector,
            query_filter=Filter(
                must=[
                    FieldCondition(key="tenant_id", match=MatchValue(value="tenant-001"))
                ]
            ),
            limit=10,
        )

        # All results should be from tenant-001
        for r in results:
            assert r.payload["tenant_id"] == "tenant-001"

    def test_search_with_filter_scope(self, qdrant_client_real, test_collection):
        """Test search with scope filter."""
        from qdrant_client.http.models import Filter, FieldCondition, MatchValue

        query_vector = self.sample_vectors[0]["vector"]

        results = _search(qdrant_client_real,
            collection_name=test_collection,
            query_vector=query_vector,
            query_filter=Filter(
                must=[
                    FieldCondition(key="scope", match=MatchValue(value="global"))
                ]
            ),
            limit=10,
        )

        # All results should be global scope
        for r in results:
            assert r.payload["scope"] == "global"

    def test_search_with_combined_filters(self, qdrant_client_real, test_collection):
        """Test search with multiple filters (multi-tenant security)."""
        from qdrant_client.http.models import Filter, FieldCondition, MatchValue, MatchAny

        query_vector = self.sample_vectors[0]["vector"]

        # Simulate multi-tenant filter: global OR (local AND tenant-001)
        results = _search(qdrant_client_real,
            collection_name=test_collection,
            query_vector=query_vector,
            query_filter=Filter(
                should=[
                    FieldCondition(key="scope", match=MatchValue(value="global")),
                    Filter(
                        must=[
                            FieldCondition(key="scope", match=MatchValue(value="local")),
                            FieldCondition(key="tenant_id", match=MatchValue(value="tenant-001")),
                        ]
                    ),
                ]
            ),
            limit=10,
        )

        # Verify filter worked
        for r in results:
            is_global = r.payload["scope"] == "global"
            is_local_tenant = (
                r.payload["scope"] == "local" and
                r.payload["tenant_id"] == "tenant-001"
            )
            assert is_global or is_local_tenant

    def test_search_score_threshold(self, qdrant_client_real, test_collection):
        """Test search with score threshold."""
        query_vector = self.sample_vectors[0]["vector"]

        results = _search(qdrant_client_real,
            collection_name=test_collection,
            query_vector=query_vector,
            score_threshold=0.5,
            limit=10,
        )

        # All results should be above threshold
        for r in results:
            assert r.score >= 0.5

    def test_search_with_payload_selection(self, qdrant_client_real, test_collection):
        """Test search returning specific payload fields."""
        query_vector = self.sample_vectors[0]["vector"]

        results = _search(qdrant_client_real,
            collection_name=test_collection,
            query_vector=query_vector,
            with_payload=["text", "doc_id"],
            limit=5,
        )

        assert len(results) > 0
        # Should have text and doc_id
        assert "text" in results[0].payload
        assert "doc_id" in results[0].payload


# =============================================================================
# Delete Tests
# =============================================================================

class TestQdrantDelete:
    """Test delete operations."""

    def test_delete_by_id(self, qdrant_client_real, test_collection, sample_vectors):
        """Test deleting points by ID."""
        from qdrant_client.http.models import PointStruct

        # Insert a point
        point = sample_vectors[0]
        qdrant_client_real.upsert(
            collection_name=test_collection,
            points=[PointStruct(id=point["id"], vector=point["vector"], payload=point["payload"])],
        )

        # Delete it
        qdrant_client_real.delete(
            collection_name=test_collection,
            points_selector=[point["id"]],
        )

        # Verify deletion
        retrieved = qdrant_client_real.retrieve(
            collection_name=test_collection,
            ids=[point["id"]],
        )
        assert len(retrieved) == 0

    def test_delete_by_filter(self, qdrant_client_real, test_collection, sample_vectors):
        """Test deleting points by filter."""
        from qdrant_client.http.models import PointStruct, Filter, FieldCondition, MatchValue

        # Insert points with specific doc_id
        doc_id = f"delete-test-{uuid.uuid4().hex[:8]}"
        for i, v in enumerate(sample_vectors):
            v["payload"]["doc_id"] = doc_id
            qdrant_client_real.upsert(
                collection_name=test_collection,
                points=[PointStruct(id=v["id"], vector=v["vector"], payload=v["payload"])],
            )

        time.sleep(0.5)

        # Delete by doc_id filter
        qdrant_client_real.delete(
            collection_name=test_collection,
            points_selector=Filter(
                must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]
            ),
        )

        # Verify deletion - search should return nothing for that doc_id
        results = qdrant_client_real.scroll(
            collection_name=test_collection,
            scroll_filter=Filter(
                must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]
            ),
            limit=100,
        )
        assert len(results[0]) == 0


# =============================================================================
# Multi-Tenant Security Tests
# =============================================================================

class TestQdrantMultiTenant:
    """Test multi-tenant security isolation."""

    @pytest.fixture(autouse=True)
    def setup_multi_tenant_data(self, qdrant_client_real, test_collection):
        """Insert multi-tenant test data."""
        from qdrant_client.http.models import PointStruct
        import random
        random.seed(123)

        tenants = ["tenant-A", "tenant-B", "tenant-C"]
        scopes = ["global", "local"]
        sigilos = ["publico", "restrito", "confidencial"]

        points = []
        for i in range(30):
            tenant = tenants[i % len(tenants)]
            scope = scopes[i % len(scopes)]
            sigilo = sigilos[i % len(sigilos)]

            points.append(PointStruct(
                id=str(uuid.uuid4()),
                vector=[random.random() for _ in range(EMBEDDING_DIM)],
                payload={
                    "text": f"Document {i} for {tenant}",
                    "tenant_id": tenant,
                    "scope": scope,
                    "sigilo": sigilo,
                    "doc_id": f"doc-{i:03d}",
                }
            ))

        qdrant_client_real.upsert(collection_name=test_collection, points=points)
        time.sleep(0.5)
        self.test_collection = test_collection

    def test_tenant_isolation(self, qdrant_client_real, test_collection):
        """Test that tenants cannot see each other's local documents."""
        from qdrant_client.http.models import Filter, FieldCondition, MatchValue
        import random
        random.seed(456)

        query_vector = [random.random() for _ in range(EMBEDDING_DIM)]

        # Tenant A searching - should only see global OR local+tenant-A
        results = _search(qdrant_client_real,
            collection_name=test_collection,
            query_vector=query_vector,
            query_filter=Filter(
                should=[
                    FieldCondition(key="scope", match=MatchValue(value="global")),
                    Filter(
                        must=[
                            FieldCondition(key="scope", match=MatchValue(value="local")),
                            FieldCondition(key="tenant_id", match=MatchValue(value="tenant-A")),
                        ]
                    ),
                ]
            ),
            limit=100,
        )

        # Verify no local docs from other tenants
        for r in results:
            if r.payload["scope"] == "local":
                assert r.payload["tenant_id"] == "tenant-A", \
                    f"Tenant A saw local doc from {r.payload['tenant_id']}"

    def test_sigilo_filtering(self, qdrant_client_real, test_collection):
        """Test that sigilo levels are properly filtered."""
        from qdrant_client.http.models import Filter, FieldCondition, MatchAny
        import random
        random.seed(789)

        query_vector = [random.random() for _ in range(EMBEDDING_DIM)]

        # User with publico+restrito access (not confidencial)
        allowed_sigilo = ["publico", "restrito"]

        results = _search(qdrant_client_real,
            collection_name=test_collection,
            query_vector=query_vector,
            query_filter=Filter(
                must=[
                    FieldCondition(key="sigilo", match=MatchAny(any=allowed_sigilo))
                ]
            ),
            limit=100,
        )

        # Verify no confidencial docs
        for r in results:
            assert r.payload["sigilo"] in allowed_sigilo, \
                f"User saw {r.payload['sigilo']} doc without permission"


# =============================================================================
# Performance Tests
# =============================================================================

class TestQdrantPerformance:
    """Basic performance tests."""

    def test_bulk_insert_performance(self, qdrant_client_real, test_collection):
        """Test bulk insert performance."""
        from qdrant_client.http.models import PointStruct
        import random
        random.seed(999)

        num_points = 1000
        points = [
            PointStruct(
                id=str(uuid.uuid4()),
                vector=[random.random() for _ in range(EMBEDDING_DIM)],
                payload={"text": f"Bulk document {i}", "tenant_id": "perf-test"},
            )
            for i in range(num_points)
        ]

        start = time.time()

        # Insert in batches
        batch_size = 100
        for i in range(0, len(points), batch_size):
            batch = points[i:i + batch_size]
            qdrant_client_real.upsert(collection_name=test_collection, points=batch)

        elapsed = time.time() - start

        print(f"\nBulk insert {num_points} points: {elapsed:.2f}s ({num_points/elapsed:.0f} points/s)")

        # Should complete in reasonable time
        assert elapsed < 30, f"Bulk insert too slow: {elapsed:.2f}s"

    def test_search_performance(self, qdrant_client_real, test_collection):
        """Test search performance."""
        import random
        random.seed(111)

        query_vector = [random.random() for _ in range(EMBEDDING_DIM)]

        # Warmup
        _search(qdrant_client_real,
            collection_name=test_collection,
            query_vector=query_vector,
            limit=10,
        )

        # Benchmark
        num_queries = 100
        start = time.time()

        for _ in range(num_queries):
            _search(qdrant_client_real,
                collection_name=test_collection,
                query_vector=query_vector,
                limit=10,
            )

        elapsed = time.time() - start
        avg_latency = (elapsed / num_queries) * 1000

        print(f"\nSearch performance: {avg_latency:.2f}ms avg ({num_queries} queries)")

        # Average latency should be under 50ms for local Qdrant
        assert avg_latency < 100, f"Search too slow: {avg_latency:.2f}ms"
