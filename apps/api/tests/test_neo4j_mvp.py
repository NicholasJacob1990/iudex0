"""
Tests for Neo4j MVP GraphRAG Service

Tests entity extraction, service instantiation, and integration helpers.
Neo4j connection tests are skipped if Neo4j is not available.
"""

import pytest
from typing import List, Dict, Any


class TestLegalEntityExtractor:
    """Tests for LegalEntityExtractor regex-based entity extraction."""

    @pytest.fixture
    def extractor(self):
        from app.services.rag.core.neo4j_mvp import LegalEntityExtractor
        return LegalEntityExtractor

    def test_extract_lei_with_dot(self, extractor):
        """Test extraction of Lei with dot in number."""
        entities = extractor.extract("Lei 8.666/93")
        assert len(entities) >= 1
        lei = next((e for e in entities if e["entity_type"] == "lei"), None)
        assert lei is not None
        assert "8666" in lei["entity_id"]
        assert "1993" in lei["entity_id"]

    def test_extract_lei_full_year(self, extractor):
        """Test extraction of Lei with full year."""
        entities = extractor.extract("Lei nº 14.133/2021")
        assert len(entities) >= 1
        lei = next((e for e in entities if e["entity_type"] == "lei"), None)
        assert lei is not None
        assert "14133" in lei["entity_id"]
        assert "2021" in lei["entity_id"]

    def test_extract_artigo_simple(self, extractor):
        """Test extraction of simple article reference."""
        entities = extractor.extract("Art. 5º da Constituição")
        assert len(entities) >= 1
        art = next((e for e in entities if e["entity_type"] == "artigo"), None)
        assert art is not None
        assert art["entity_id"] == "art_5"

    def test_extract_artigo_with_paragrafo(self, extractor):
        """Test extraction of article with paragraph."""
        entities = extractor.extract("Art. 37, § 4º")
        assert len(entities) >= 1
        art = next((e for e in entities if e["entity_type"] == "artigo"), None)
        assert art is not None
        assert "art_37" in art["entity_id"]
        assert "p4" in art["entity_id"]

    def test_extract_artigo_with_inciso(self, extractor):
        """Test extraction of article with inciso."""
        entities = extractor.extract("Art. 5º, inciso II")
        assert len(entities) >= 1
        art = next((e for e in entities if e["entity_type"] == "artigo"), None)
        assert art is not None
        assert "iII" in art["entity_id"]

    def test_extract_sumula(self, extractor):
        """Test extraction of súmula."""
        entities = extractor.extract("Súmula 331 do TST")
        assert len(entities) >= 1
        sumula = next((e for e in entities if e["entity_type"] == "sumula"), None)
        assert sumula is not None
        assert "331" in sumula["entity_id"]
        assert "TST" in sumula["entity_id"]

    def test_extract_sumula_vinculante(self, extractor):
        """Test extraction of súmula vinculante."""
        entities = extractor.extract("Súmula Vinculante 13 do STF")
        assert len(entities) >= 1
        sumula = next((e for e in entities if e["entity_type"] == "sumula"), None)
        assert sumula is not None
        assert "13" in sumula["entity_id"]

    def test_extract_processo_cnj(self, extractor):
        """Test extraction of CNJ process number."""
        entities = extractor.extract("Processo 0001234-56.2023.8.26.0100")
        assert len(entities) >= 1
        proc = next((e for e in entities if e["entity_type"] == "processo"), None)
        assert proc is not None
        assert "0001234" in proc["entity_id"]

    def test_extract_tribunal(self, extractor):
        """Test extraction of tribunal references."""
        entities = extractor.extract("Decisão do STF e STJ")
        tribunais = [e for e in entities if e["entity_type"] == "tribunal"]
        assert len(tribunais) >= 2
        siglas = [t["name"] for t in tribunais]
        assert "STF" in siglas
        assert "STJ" in siglas

    def test_extract_tema(self, extractor):
        """Test extraction of tema de repercussão geral."""
        entities = extractor.extract("Tema 1234 do STF")
        assert len(entities) >= 1
        tema = next((e for e in entities if e["entity_type"] == "tema"), None)
        assert tema is not None
        assert "1234" in tema["entity_id"]

    def test_extract_oab(self, extractor):
        """Test extraction of OAB number."""
        entities = extractor.extract("OAB/SP 123.456")
        assert len(entities) >= 1
        oab = next((e for e in entities if e["entity_type"] == "oab"), None)
        assert oab is not None
        assert "SP" in oab["entity_id"]
        assert "123456" in oab["entity_id"]

    def test_extract_multiple_entities(self, extractor):
        """Test extraction of multiple entities from text."""
        text = """
        Conforme Art. 5º da Lei 8.666/93, em consonância com a
        Súmula 331 do TST, o Tema 1234 do STF estabelece...
        """
        entities = extractor.extract(text)
        entity_types = [e["entity_type"] for e in entities]
        assert "artigo" in entity_types
        assert "lei" in entity_types
        assert "sumula" in entity_types
        assert "tema" in entity_types

    def test_extract_no_entities(self, extractor):
        """Test extraction from text with no legal entities."""
        entities = extractor.extract("Como funciona o processo de licitação?")
        # May have some false positives, but should be minimal
        assert len(entities) <= 1

    def test_extract_deduplication(self, extractor):
        """Test that duplicate entities are deduplicated."""
        entities = extractor.extract("Art. 5 e Art. 5 e Art. 5")
        art_entities = [e for e in entities if e["entity_type"] == "artigo"]
        assert len(art_entities) == 1


class TestNeo4jMVPConfig:
    """Tests for Neo4jMVPConfig."""

    def test_default_config(self):
        from app.services.rag.core.neo4j_mvp import Neo4jMVPConfig
        config = Neo4jMVPConfig()
        assert config.uri == "bolt://localhost:7687"
        assert config.user == "neo4j"
        assert config.max_hops == 2

    def test_config_from_env(self, monkeypatch):
        from app.services.rag.core.neo4j_mvp import Neo4jMVPConfig
        monkeypatch.setenv("NEO4J_URI", "bolt://custom:7687")
        monkeypatch.setenv("NEO4J_USER", "custom_user")
        monkeypatch.setenv("NEO4J_MAX_HOPS", "3")
        monkeypatch.setenv("RAG_GRAPH_HYBRID_MODE", "true")
        monkeypatch.setenv("RAG_GRAPH_HYBRID_AUTO_SCHEMA", "false")
        monkeypatch.setenv("RAG_GRAPH_HYBRID_MIGRATE_ON_STARTUP", "true")
        monkeypatch.setenv("NEO4J_FULLTEXT_ENABLED", "true")
        monkeypatch.setenv("NEO4J_VECTOR_INDEX_ENABLED", "true")
        monkeypatch.setenv("NEO4J_VECTOR_DIM", "1536")
        monkeypatch.setenv("NEO4J_VECTOR_SIMILARITY", "cosine")
        monkeypatch.setenv("NEO4J_VECTOR_PROPERTY", "embedding")

        config = Neo4jMVPConfig.from_env()
        assert config.uri == "bolt://custom:7687"
        assert config.user == "custom_user"
        assert config.max_hops == 3
        assert config.graph_hybrid_mode is True
        assert config.graph_hybrid_auto_schema is False
        assert config.graph_hybrid_migrate_on_startup is True
        assert config.enable_fulltext_indexes is True
        assert config.enable_vector_index is True
        assert config.vector_dimensions == 1536
        assert config.vector_similarity == "cosine"
        assert config.vector_property == "embedding"


class TestNeo4jMVPService:
    """Tests for Neo4jMVPService."""

    def test_service_instantiation(self):
        """Test that service can be instantiated without connection."""
        from app.services.rag.core.neo4j_mvp import Neo4jMVPService, Neo4jMVPConfig

        config = Neo4jMVPConfig(
            uri="bolt://nonexistent:7687",
            create_indexes=False,
        )
        service = Neo4jMVPService(config)
        assert service is not None
        assert service.config.uri == "bolt://nonexistent:7687"

    def test_health_check_without_connection(self):
        """Test health check returns False without connection."""
        from app.services.rag.core.neo4j_mvp import Neo4jMVPService, Neo4jMVPConfig

        config = Neo4jMVPConfig(
            uri="bolt://nonexistent:7687",
            create_indexes=False,
        )
        service = Neo4jMVPService(config)
        # Should return False, not raise exception
        assert service.health_check() == False


class TestCypherQueries:
    """Tests for Cypher query templates."""

    def test_queries_are_valid_strings(self):
        from app.services.rag.core.neo4j_mvp import CypherQueries

        queries = [
            CypherQueries.CREATE_CONSTRAINTS,
            CypherQueries.MERGE_DOCUMENT,
            CypherQueries.MERGE_CHUNK,
            CypherQueries.MERGE_ENTITY,
            CypherQueries.FIND_CHUNKS_BY_ENTITIES,
            CypherQueries.EXPAND_NEIGHBORS,
            CypherQueries.FIND_PATHS,
            CypherQueries.FIND_COOCCURRENCE,
        ]

        for query in queries:
            assert isinstance(query, str)
            assert len(query) > 10
            # Should contain Cypher keywords
            assert any(kw in query.upper() for kw in ["MATCH", "MERGE", "CREATE", "RETURN"])

        # Sanity checks for explainable-path query
        assert "path_nodes" in CypherQueries.FIND_PATHS
        assert "path_edges" in CypherQueries.FIND_PATHS


class TestBuildGraphContext:
    """Tests for build_graph_context helper."""

    def test_build_context_with_paths(self):
        from app.services.rag.core.neo4j_mvp import build_graph_context

        paths = [
            {
                "start_entity": "Art. 5",
                "end_name": "Súmula 331",
                "path_names": ["Art. 5", "Lei 8.666", "Súmula 331"],
                "path_relations": ["FUNDAMENTA", "CITA"],
                "path_length": 2,
            },
        ]

        context = build_graph_context(paths, max_chars=500)
        assert "Relações do Grafo" in context
        assert "Art. 5" in context
        assert "FUNDAMENTA" in context

    def test_build_context_empty_paths(self):
        from app.services.rag.core.neo4j_mvp import build_graph_context

        context = build_graph_context([], max_chars=500)
        assert context == ""

    def test_build_context_respects_max_chars(self):
        from app.services.rag.core.neo4j_mvp import build_graph_context

        paths = [
            {
                "start_entity": f"Entity{i}",
                "end_name": f"Target{i}",
                "path_names": [f"Entity{i}", f"Middle{i}", f"Target{i}"],
                "path_relations": ["REL1", "REL2"],
                "path_length": 2,
            }
            for i in range(100)
        ]

        context = build_graph_context(paths, max_chars=200)
        assert len(context) <= 250  # Some tolerance for header


class TestEmbeddingTrainer:
    """Tests for EmbeddingTrainer."""

    def test_trainer_with_small_dataset(self):
        from app.services.rag.core.embedding_trainer import (
            EmbeddingTrainer,
            TrainingConfig,
            EmbeddingMethod,
        )

        triples = [
            ("a", "r1", "b"),
            ("b", "r2", "c"),
            ("c", "r1", "d"),
            ("a", "r2", "d"),
        ]

        config = TrainingConfig(
            embedding_dim=16,
            method=EmbeddingMethod.TRANSE,
            epochs=5,
            batch_size=2,
            negative_samples=1,
            validation_split=0.25,
        )

        trainer = EmbeddingTrainer(triples, config)
        assert trainer.dataset.n_entities == 4
        assert trainer.dataset.n_relations == 2

        results = trainer.train()
        assert "entity_embeddings" in results
        assert results["entity_embeddings"].shape[0] == 4

    def test_get_entity_embedding(self):
        from app.services.rag.core.embedding_trainer import (
            EmbeddingTrainer,
            TrainingConfig,
            EmbeddingMethod,
        )

        triples = [("a", "r", "b"), ("b", "r", "c")]
        config = TrainingConfig(embedding_dim=16, epochs=2, batch_size=2)

        trainer = EmbeddingTrainer(triples, config)
        trainer.train()

        emb = trainer.get_entity_embedding("a")
        assert emb is not None
        assert emb.shape == (32,)  # RotatE uses 2x dim for complex

        emb_none = trainer.get_entity_embedding("nonexistent")
        assert emb_none is None

    def test_get_similar_entities(self):
        from app.services.rag.core.embedding_trainer import (
            EmbeddingTrainer,
            TrainingConfig,
        )

        triples = [
            ("a", "r", "b"),
            ("a", "r", "c"),
            ("b", "r", "d"),
        ]
        config = TrainingConfig(embedding_dim=16, epochs=5, batch_size=2)

        trainer = EmbeddingTrainer(triples, config)
        trainer.train()

        similar = trainer.get_similar_entities("a", top_k=2)
        assert len(similar) == 2
        assert all(isinstance(s[0], str) for s in similar)
        assert all(isinstance(s[1], float) for s in similar)


class TestRAGPipelineIntegration:
    """Tests for RAG Pipeline integration with Neo4j."""

    def test_pipeline_initializes_without_neo4j(self):
        from app.services.rag.pipeline.rag_pipeline import RAGPipeline

        pipeline = RAGPipeline()
        pipeline._ensure_components()

        # Neo4j should be None or unhealthy (no connection)
        # Pipeline should still work

    def test_is_lexical_heavy(self):
        from app.services.rag.pipeline.rag_pipeline import RAGPipeline

        pipeline = RAGPipeline()

        assert pipeline.is_lexical_heavy("Art. 5 da CF") == True
        assert pipeline.is_lexical_heavy("Lei 8.666/93") == True
        assert pipeline.is_lexical_heavy("Súmula 331 TST") == True
        assert pipeline.is_lexical_heavy("0001234-56.2023.8.26.0100") == True
        assert pipeline.is_lexical_heavy("Como funciona?") == False
        assert pipeline.is_lexical_heavy("Quais são os requisitos?") == False


# Pytest markers for integration tests that require Neo4j
@pytest.fixture
def neo4j_available():
    """Check if Neo4j is available."""
    try:
        from app.services.rag.core.neo4j_mvp import get_neo4j_mvp
        neo4j = get_neo4j_mvp()
        return neo4j.health_check()
    except Exception:
        return False


def _is_neo4j_available():
    """Helper to check if Neo4j is available."""
    try:
        from app.services.rag.core.neo4j_mvp import Neo4jMVPService, Neo4jMVPConfig
        config = Neo4jMVPConfig(create_indexes=False)
        service = Neo4jMVPService(config)
        return service.health_check()
    except Exception:
        return False


@pytest.mark.skipif(
    not _is_neo4j_available(),
    reason="Neo4j not available"
)
class TestNeo4jIntegration:
    """Integration tests that require a running Neo4j instance."""

    def test_ingest_and_query(self, neo4j_available):
        if not neo4j_available:
            pytest.skip("Neo4j not available")

        from app.services.rag.core.neo4j_mvp import get_neo4j_mvp

        neo4j = get_neo4j_mvp()

        # Ingest a test document
        stats = neo4j.ingest_document(
            doc_hash="test_doc_001",
            chunks=[
                {
                    "chunk_uid": "chunk_001",
                    "text": "Art. 5º da Lei 8.666/93 estabelece requisitos.",
                    "chunk_index": 0,
                },
                {
                    "chunk_uid": "chunk_002",
                    "text": "Conforme Súmula 331 do TST, a terceirização...",
                    "chunk_index": 1,
                },
            ],
            metadata={"title": "Test Document"},
            tenant_id="test_tenant",
            scope="global",
        )

        assert stats["document"] == 1
        assert stats["chunks"] == 2
        assert stats["entities"] > 0

        # Query by entity
        results = neo4j.query_chunks_by_entities(
            entity_ids=["art_5"],
            tenant_id="test_tenant",
            scope="global",
        )

        assert len(results) >= 1
