"""
Integration tests for OpenSearchService with real OpenSearch instance.

These tests require a running OpenSearch instance.
Skip if OpenSearch is not available.

Run with:
    pytest tests/rag/test_opensearch_integration.py -v

Requirements:
    - OpenSearch running on localhost:9200 (or OPENSEARCH_URL env var)
    - docker run -d -p 9200:9200 -e "discovery.type=single-node" \
        -e "DISABLE_SECURITY_PLUGIN=true" opensearchproject/opensearch:2
"""

import os
import uuid
import time
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any

import pytest

# Skip all tests if opensearch-py is not installed
opensearchpy = pytest.importorskip("opensearchpy", reason="opensearch-py not installed")

from opensearchpy import OpenSearch
from opensearchpy.exceptions import NotFoundError, RequestError


# =============================================================================
# Configuration
# =============================================================================

OPENSEARCH_URL = os.getenv("OPENSEARCH_URL", "http://localhost:9200")
OPENSEARCH_USER = os.getenv("OPENSEARCH_USER", "admin")
OPENSEARCH_PASSWORD = os.getenv("OPENSEARCH_PASSWORD", "admin")
OPENSEARCH_USE_SSL = os.getenv("OPENSEARCH_USE_SSL", "false").lower() == "true"
TEST_INDEX = f"test_integration_{uuid.uuid4().hex[:8]}"


def is_opensearch_available() -> bool:
    """Check if OpenSearch is running and accessible."""
    try:
        # Try without auth first (DISABLE_SECURITY_PLUGIN=true)
        client = OpenSearch(
            hosts=[OPENSEARCH_URL],
            use_ssl=OPENSEARCH_USE_SSL,
            verify_certs=False,
            ssl_show_warn=False,
            timeout=5,
        )
        if client.ping():
            return True

        # Try with auth
        client = OpenSearch(
            hosts=[OPENSEARCH_URL],
            http_auth=(OPENSEARCH_USER, OPENSEARCH_PASSWORD),
            use_ssl=OPENSEARCH_USE_SSL,
            verify_certs=False,
            ssl_show_warn=False,
            timeout=5,
        )
        return client.ping()
    except Exception:
        return False


# Skip all tests if OpenSearch is not available
pytestmark = pytest.mark.skipif(
    not is_opensearch_available(),
    reason=f"OpenSearch not available at {OPENSEARCH_URL}. Run: docker run -d -p 9200:9200 -e discovery.type=single-node -e DISABLE_SECURITY_PLUGIN=true opensearchproject/opensearch:2"
)


# =============================================================================
# Index Mapping (matches production RAG_CHUNK_MAPPING)
# =============================================================================

RAG_CHUNK_MAPPING = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
        "analysis": {
            "analyzer": {
                "brazilian_legal": {
                    "type": "custom",
                    "tokenizer": "standard",
                    "filter": [
                        "lowercase",
                        "brazilian_stemmer",
                        "asciifolding"
                    ]
                }
            },
            "filter": {
                "brazilian_stemmer": {
                    "type": "stemmer",
                    "language": "brazilian"
                }
            }
        }
    },
    "mappings": {
        "properties": {
            "chunk_uid": {"type": "keyword"},
            "doc_id": {"type": "keyword"},
            "text": {
                "type": "text",
                "analyzer": "brazilian_legal",
                "fields": {
                    "exact": {"type": "keyword"}
                }
            },
            "scope": {"type": "keyword"},
            "tenant_id": {"type": "keyword"},
            "sigilo": {"type": "keyword"},
            "source_type": {"type": "keyword"},
            "uploaded_at": {"type": "date"},
            "metadata": {"type": "object", "enabled": False},
        }
    }
}


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture(scope="module")
def opensearch_client_real():
    """Create a real OpenSearch client for testing."""
    # Try without auth first (for DISABLE_SECURITY_PLUGIN=true)
    client = OpenSearch(
        hosts=[OPENSEARCH_URL],
        use_ssl=OPENSEARCH_USE_SSL,
        verify_certs=False,
        ssl_show_warn=False,
    )

    # If ping fails, try with auth
    if not client.ping():
        client = OpenSearch(
            hosts=[OPENSEARCH_URL],
            http_auth=(OPENSEARCH_USER, OPENSEARCH_PASSWORD),
            use_ssl=OPENSEARCH_USE_SSL,
            verify_certs=False,
            ssl_show_warn=False,
        )

    yield client
    # Cleanup: delete test index if exists
    try:
        client.indices.delete(index=TEST_INDEX, ignore=[404])
    except Exception:
        pass


@pytest.fixture(scope="module")
def test_index(opensearch_client_real):
    """Create a test index and clean up after tests."""
    # Delete if exists from previous failed run
    try:
        opensearch_client_real.indices.delete(index=TEST_INDEX, ignore=[404])
    except Exception:
        pass

    # Create index with Brazilian legal analyzer
    opensearch_client_real.indices.create(
        index=TEST_INDEX,
        body=RAG_CHUNK_MAPPING,
    )

    yield TEST_INDEX

    # Cleanup
    try:
        opensearch_client_real.indices.delete(index=TEST_INDEX, ignore=[404])
    except Exception:
        pass


@pytest.fixture
def sample_documents() -> List[Dict[str, Any]]:
    """Generate sample documents for testing."""
    now = datetime.now(timezone.utc)

    return [
        {
            "chunk_uid": f"chunk-{uuid.uuid4().hex[:8]}",
            "doc_id": "doc-cf-001",
            "text": "Artigo 5º da Constituição Federal garante que todos são iguais perante a lei.",
            "scope": "global",
            "tenant_id": "tenant-001",
            "sigilo": "publico",
            "source_type": "legislacao",
            "uploaded_at": now.isoformat(),
        },
        {
            "chunk_uid": f"chunk-{uuid.uuid4().hex[:8]}",
            "doc_id": "doc-tst-001",
            "text": "Súmula 331 do TST estabelece responsabilidade subsidiária na terceirização.",
            "scope": "local",
            "tenant_id": "tenant-001",
            "sigilo": "restrito",
            "source_type": "jurisprudencia",
            "uploaded_at": now.isoformat(),
        },
        {
            "chunk_uid": f"chunk-{uuid.uuid4().hex[:8]}",
            "doc_id": "doc-lic-001",
            "text": "Lei 14.133/2021 é a nova lei de licitações e contratos administrativos.",
            "scope": "global",
            "tenant_id": "tenant-002",
            "sigilo": "publico",
            "source_type": "legislacao",
            "uploaded_at": now.isoformat(),
        },
        {
            "chunk_uid": f"chunk-{uuid.uuid4().hex[:8]}",
            "doc_id": "doc-penal-001",
            "text": "O habeas corpus é remédio constitucional para proteger a liberdade de locomoção.",
            "scope": "global",
            "tenant_id": "tenant-001",
            "sigilo": "publico",
            "source_type": "doutrina",
            "uploaded_at": now.isoformat(),
        },
        {
            "chunk_uid": f"chunk-{uuid.uuid4().hex[:8]}",
            "doc_id": "doc-civil-001",
            "text": "Prescrição quinquenal para cobrança de dívidas contratuais conforme Código Civil.",
            "scope": "local",
            "tenant_id": "tenant-002",
            "sigilo": "confidencial",
            "source_type": "parecer",
            "uploaded_at": (now - timedelta(days=10)).isoformat(),  # Old document
        },
    ]


# =============================================================================
# Connection Tests
# =============================================================================

class TestOpenSearchConnection:
    """Test OpenSearch connection and basic operations."""

    def test_connection_success(self, opensearch_client_real):
        """Test that we can connect to OpenSearch."""
        assert opensearch_client_real.ping()

    def test_cluster_health(self, opensearch_client_real):
        """Test cluster health."""
        health = opensearch_client_real.cluster.health()
        assert health["status"] in ["green", "yellow"]

    def test_index_created(self, opensearch_client_real, test_index):
        """Test that test index was created."""
        assert opensearch_client_real.indices.exists(index=test_index)

    def test_index_mapping(self, opensearch_client_real, test_index):
        """Test index mapping has Brazilian analyzer."""
        mapping = opensearch_client_real.indices.get_mapping(index=test_index)
        assert "text" in mapping[test_index]["mappings"]["properties"]
        assert mapping[test_index]["mappings"]["properties"]["text"]["analyzer"] == "brazilian_legal"


# =============================================================================
# Index Tests
# =============================================================================

class TestOpenSearchIndex:
    """Test index operations."""

    def test_index_single_document(self, opensearch_client_real, test_index, sample_documents):
        """Test indexing a single document."""
        doc = sample_documents[0]

        result = opensearch_client_real.index(
            index=test_index,
            id=doc["chunk_uid"],
            body=doc,
            refresh=True,
        )

        assert result["result"] in ["created", "updated"]

    def test_bulk_index(self, opensearch_client_real, test_index, sample_documents):
        """Test bulk indexing."""
        from opensearchpy.helpers import bulk

        actions = [
            {
                "_index": test_index,
                "_id": doc["chunk_uid"],
                "_source": doc,
            }
            for doc in sample_documents
        ]

        success, errors = bulk(opensearch_client_real, actions, refresh=True)

        assert success == len(sample_documents)
        assert len(errors) == 0

    def test_get_document(self, opensearch_client_real, test_index, sample_documents):
        """Test retrieving a document by ID."""
        doc = sample_documents[0]

        # Index first
        opensearch_client_real.index(
            index=test_index,
            id=doc["chunk_uid"],
            body=doc,
            refresh=True,
        )

        # Retrieve
        result = opensearch_client_real.get(index=test_index, id=doc["chunk_uid"])

        assert result["found"]
        assert result["_source"]["text"] == doc["text"]


# =============================================================================
# Search Tests (BM25)
# =============================================================================

class TestOpenSearchBM25:
    """Test BM25 lexical search."""

    @pytest.fixture(autouse=True)
    def setup_data(self, opensearch_client_real, test_index, sample_documents):
        """Insert test data before each test."""
        from opensearchpy.helpers import bulk

        actions = [
            {"_index": test_index, "_id": doc["chunk_uid"], "_source": doc}
            for doc in sample_documents
        ]
        bulk(opensearch_client_real, actions, refresh=True)
        self.sample_documents = sample_documents

    def test_search_basic(self, opensearch_client_real, test_index):
        """Test basic text search."""
        result = opensearch_client_real.search(
            index=test_index,
            body={
                "query": {
                    "match": {
                        "text": "Constituição Federal"
                    }
                }
            }
        )

        assert result["hits"]["total"]["value"] > 0
        # First hit should mention Constituição
        assert "constituição" in result["hits"]["hits"][0]["_source"]["text"].lower()

    def test_search_brazilian_stemmer(self, opensearch_client_real, test_index):
        """Test that Brazilian stemmer works (conjugação -> conjugar)."""
        # Search for "terceirização" should find "terceirização"
        result = opensearch_client_real.search(
            index=test_index,
            body={
                "query": {
                    "match": {
                        "text": "terceirizar"  # Stem form
                    }
                }
            }
        )

        # Should find the TST document about terceirização
        hits = result["hits"]["hits"]
        texts = [h["_source"]["text"].lower() for h in hits]
        assert any("terceirização" in t for t in texts)

    def test_search_multi_match(self, opensearch_client_real, test_index):
        """Test multi-match query."""
        result = opensearch_client_real.search(
            index=test_index,
            body={
                "query": {
                    "multi_match": {
                        "query": "lei licitação contratos",
                        "fields": ["text"],
                        "type": "best_fields",
                    }
                }
            }
        )

        assert result["hits"]["total"]["value"] > 0

    def test_search_with_filter_scope(self, opensearch_client_real, test_index):
        """Test search with scope filter."""
        result = opensearch_client_real.search(
            index=test_index,
            body={
                "query": {
                    "bool": {
                        "must": [
                            {"match": {"text": "lei"}}
                        ],
                        "filter": [
                            {"term": {"scope": "global"}}
                        ]
                    }
                }
            }
        )

        # All results should be global scope
        for hit in result["hits"]["hits"]:
            assert hit["_source"]["scope"] == "global"

    def test_search_with_filter_tenant(self, opensearch_client_real, test_index):
        """Test search with tenant_id filter."""
        result = opensearch_client_real.search(
            index=test_index,
            body={
                "query": {
                    "bool": {
                        "must": [
                            {"match_all": {}}
                        ],
                        "filter": [
                            {"term": {"tenant_id": "tenant-001"}}
                        ]
                    }
                }
            }
        )

        # All results should be from tenant-001
        for hit in result["hits"]["hits"]:
            assert hit["_source"]["tenant_id"] == "tenant-001"

    def test_search_multi_tenant_security(self, opensearch_client_real, test_index):
        """Test multi-tenant security filter (global OR local+tenant)."""
        result = opensearch_client_real.search(
            index=test_index,
            body={
                "query": {
                    "bool": {
                        "must": [
                            {"match_all": {}}
                        ],
                        "filter": [
                            {
                                "bool": {
                                    "should": [
                                        {"term": {"scope": "global"}},
                                        {
                                            "bool": {
                                                "must": [
                                                    {"term": {"scope": "local"}},
                                                    {"term": {"tenant_id": "tenant-001"}}
                                                ]
                                            }
                                        }
                                    ],
                                    "minimum_should_match": 1
                                }
                            }
                        ]
                    }
                }
            }
        )

        # Verify filter worked
        for hit in result["hits"]["hits"]:
            source = hit["_source"]
            is_global = source["scope"] == "global"
            is_local_tenant = source["scope"] == "local" and source["tenant_id"] == "tenant-001"
            assert is_global or is_local_tenant, \
                f"Tenant-001 saw local doc from {source.get('tenant_id')}"

    def test_search_sigilo_filtering(self, opensearch_client_real, test_index):
        """Test sigilo level filtering."""
        result = opensearch_client_real.search(
            index=test_index,
            body={
                "query": {
                    "bool": {
                        "must": [
                            {"match_all": {}}
                        ],
                        "filter": [
                            {"terms": {"sigilo": ["publico", "restrito"]}}
                        ]
                    }
                }
            }
        )

        # Should not include confidencial
        for hit in result["hits"]["hits"]:
            assert hit["_source"]["sigilo"] in ["publico", "restrito"]


# =============================================================================
# Delete Tests
# =============================================================================

class TestOpenSearchDelete:
    """Test delete operations."""

    def test_delete_by_id(self, opensearch_client_real, test_index, sample_documents):
        """Test deleting a document by ID."""
        doc = sample_documents[0]

        # Index first
        opensearch_client_real.index(
            index=test_index,
            id=doc["chunk_uid"],
            body=doc,
            refresh=True,
        )

        # Delete
        result = opensearch_client_real.delete(
            index=test_index,
            id=doc["chunk_uid"],
            refresh=True,
        )

        assert result["result"] == "deleted"

        # Verify deletion
        with pytest.raises(NotFoundError):
            opensearch_client_real.get(index=test_index, id=doc["chunk_uid"])

    def test_delete_by_query(self, opensearch_client_real, test_index, sample_documents):
        """Test deleting documents by query."""
        from opensearchpy.helpers import bulk

        # Index documents with specific doc_id
        doc_id = f"delete-test-{uuid.uuid4().hex[:8]}"
        docs = []
        for i, doc in enumerate(sample_documents[:3]):
            doc_copy = doc.copy()
            doc_copy["doc_id"] = doc_id
            doc_copy["chunk_uid"] = f"chunk-del-{i}"
            docs.append(doc_copy)

        actions = [
            {"_index": test_index, "_id": d["chunk_uid"], "_source": d}
            for d in docs
        ]
        bulk(opensearch_client_real, actions, refresh=True)

        # Delete by query
        result = opensearch_client_real.delete_by_query(
            index=test_index,
            body={
                "query": {
                    "term": {"doc_id": doc_id}
                }
            },
            refresh=True,
        )

        assert result["deleted"] >= len(docs)

        # Verify deletion
        search_result = opensearch_client_real.search(
            index=test_index,
            body={"query": {"term": {"doc_id": doc_id}}}
        )
        assert search_result["hits"]["total"]["value"] == 0

    def test_ttl_cleanup_by_date(self, opensearch_client_real, test_index, sample_documents):
        """Test TTL cleanup - delete old local documents."""
        from opensearchpy.helpers import bulk

        now = datetime.now(timezone.utc)
        old_date = (now - timedelta(days=10)).isoformat()
        recent_date = now.isoformat()

        # Use unique tenant to isolate this test
        unique_tenant = f"tenant-ttl-{uuid.uuid4().hex[:8]}"

        # Create old and recent local docs
        docs = [
            {
                "chunk_uid": f"chunk-old-ttl-{i}",
                "doc_id": "ttl-test",
                "text": f"Old document {i}",
                "scope": "local",
                "tenant_id": unique_tenant,
                "sigilo": "publico",
                "source_type": "test",
                "uploaded_at": old_date,
            }
            for i in range(3)
        ] + [
            {
                "chunk_uid": f"chunk-recent-ttl-{i}",
                "doc_id": "ttl-test",
                "text": f"Recent document {i}",
                "scope": "local",
                "tenant_id": unique_tenant,
                "sigilo": "publico",
                "source_type": "test",
                "uploaded_at": recent_date,
            }
            for i in range(2)
        ]

        actions = [
            {"_index": test_index, "_id": d["chunk_uid"], "_source": d}
            for d in docs
        ]
        bulk(opensearch_client_real, actions, refresh=True)

        # TTL cleanup: delete local docs older than 7 days for this tenant
        ttl_cutoff = (now - timedelta(days=7)).isoformat()

        result = opensearch_client_real.delete_by_query(
            index=test_index,
            body={
                "query": {
                    "bool": {
                        "must": [
                            {"term": {"scope": "local"}},
                            {"term": {"tenant_id": unique_tenant}},
                            {"range": {"uploaded_at": {"lt": ttl_cutoff}}}
                        ]
                    }
                }
            },
            refresh=True,
        )

        assert result["deleted"] == 3  # Old docs deleted

        # Verify recent docs still exist
        search_result = opensearch_client_real.search(
            index=test_index,
            body={
                "query": {
                    "bool": {
                        "must": [
                            {"term": {"tenant_id": unique_tenant}}
                        ]
                    }
                }
            }
        )
        assert search_result["hits"]["total"]["value"] == 2  # Only recent docs


# =============================================================================
# Multi-Tenant Security Tests
# =============================================================================

class TestOpenSearchMultiTenant:
    """Test multi-tenant security isolation."""

    @pytest.fixture(autouse=True)
    def setup_multi_tenant_data(self, opensearch_client_real, test_index):
        """Insert multi-tenant test data."""
        from opensearchpy.helpers import bulk

        now = datetime.now(timezone.utc)
        tenants = ["tenant-A", "tenant-B", "tenant-C"]
        scopes = ["global", "local"]
        sigilos = ["publico", "restrito", "confidencial"]

        docs = []
        for i in range(30):
            tenant = tenants[i % len(tenants)]
            scope = scopes[i % len(scopes)]
            sigilo = sigilos[i % len(sigilos)]

            docs.append({
                "chunk_uid": f"chunk-mt-{i:03d}",
                "doc_id": f"doc-mt-{i:03d}",
                "text": f"Multi-tenant test document {i} for {tenant}",
                "scope": scope,
                "tenant_id": tenant,
                "sigilo": sigilo,
                "source_type": "test",
                "uploaded_at": now.isoformat(),
            })

        actions = [
            {"_index": test_index, "_id": d["chunk_uid"], "_source": d}
            for d in docs
        ]
        bulk(opensearch_client_real, actions, refresh=True)
        self.test_index = test_index

    def test_tenant_a_cannot_see_tenant_b_local(self, opensearch_client_real, test_index):
        """Test that Tenant A cannot see Tenant B's local documents."""
        # Tenant A query with proper security filter
        result = opensearch_client_real.search(
            index=test_index,
            body={
                "query": {
                    "bool": {
                        "must": [{"match_all": {}}],
                        "filter": [
                            {
                                "bool": {
                                    "should": [
                                        {"term": {"scope": "global"}},
                                        {
                                            "bool": {
                                                "must": [
                                                    {"term": {"scope": "local"}},
                                                    {"term": {"tenant_id": "tenant-A"}}
                                                ]
                                            }
                                        }
                                    ],
                                    "minimum_should_match": 1
                                }
                            }
                        ]
                    }
                },
                "size": 100
            }
        )

        # Verify no local docs from tenant-B or tenant-C
        for hit in result["hits"]["hits"]:
            source = hit["_source"]
            if source["scope"] == "local":
                assert source["tenant_id"] == "tenant-A", \
                    f"Tenant-A saw local doc from {source['tenant_id']}"

    def test_global_docs_visible_to_all(self, opensearch_client_real, test_index):
        """Test that global documents are visible to all tenants."""
        # Count global docs
        result = opensearch_client_real.search(
            index=test_index,
            body={
                "query": {"term": {"scope": "global"}},
                "size": 0
            }
        )

        global_count = result["hits"]["total"]["value"]
        assert global_count > 0

        # Each tenant should see all global docs
        for tenant in ["tenant-A", "tenant-B", "tenant-C"]:
            result = opensearch_client_real.search(
                index=test_index,
                body={
                    "query": {
                        "bool": {
                            "filter": [
                                {
                                    "bool": {
                                        "should": [
                                            {"term": {"scope": "global"}},
                                            {
                                                "bool": {
                                                    "must": [
                                                        {"term": {"scope": "local"}},
                                                        {"term": {"tenant_id": tenant}}
                                                    ]
                                                }
                                            }
                                        ],
                                        "minimum_should_match": 1
                                    }
                                }
                            ]
                        }
                    },
                    "size": 0
                }
            )

            # Each tenant sees global docs + their local docs
            assert result["hits"]["total"]["value"] >= global_count


# =============================================================================
# Performance Tests
# =============================================================================

class TestOpenSearchPerformance:
    """Basic performance tests."""

    def test_bulk_index_performance(self, opensearch_client_real, test_index):
        """Test bulk indexing performance."""
        from opensearchpy.helpers import bulk

        now = datetime.now(timezone.utc)
        num_docs = 1000

        docs = [
            {
                "_index": test_index,
                "_id": f"perf-{i:06d}",
                "_source": {
                    "chunk_uid": f"perf-{i:06d}",
                    "doc_id": f"doc-perf-{i // 10:04d}",
                    "text": f"Performance test document number {i} with some legal text about direito processual civil e trabalhista.",
                    "scope": "global",
                    "tenant_id": "perf-test",
                    "sigilo": "publico",
                    "source_type": "test",
                    "uploaded_at": now.isoformat(),
                }
            }
            for i in range(num_docs)
        ]

        start = time.time()
        success, errors = bulk(opensearch_client_real, docs, refresh=True)
        elapsed = time.time() - start

        print(f"\nBulk index {num_docs} docs: {elapsed:.2f}s ({num_docs/elapsed:.0f} docs/s)")

        assert success == num_docs
        assert len(errors) == 0
        assert elapsed < 30, f"Bulk index too slow: {elapsed:.2f}s"

    def test_search_performance(self, opensearch_client_real, test_index):
        """Test search performance."""
        # Warmup
        opensearch_client_real.search(
            index=test_index,
            body={"query": {"match": {"text": "direito"}}}
        )

        # Benchmark
        num_queries = 100
        start = time.time()

        for i in range(num_queries):
            opensearch_client_real.search(
                index=test_index,
                body={
                    "query": {
                        "bool": {
                            "must": [
                                {"match": {"text": "direito processual"}}
                            ],
                            "filter": [
                                {"term": {"scope": "global"}}
                            ]
                        }
                    },
                    "size": 10
                }
            )

        elapsed = time.time() - start
        avg_latency = (elapsed / num_queries) * 1000

        print(f"\nSearch performance: {avg_latency:.2f}ms avg ({num_queries} queries)")

        # Average latency should be under 50ms for local OpenSearch
        assert avg_latency < 100, f"Search too slow: {avg_latency:.2f}ms"
