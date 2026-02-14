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

    def test_extract_decisao(self, extractor):
        """Test extraction of decisão judicial (REsp/RE/ADI/etc)."""
        entities = extractor.extract("Conforme REsp 1.134.186 e RE 603.191.")
        decisoes = [e for e in entities if e["entity_type"] == "decisao"]
        assert len(decisoes) >= 2
        ids = {d["entity_id"] for d in decisoes}
        assert any("resp_1134186" in i for i in ids)
        assert any("re_603191" in i for i in ids)

    def test_extract_tese(self, extractor):
        """Test extraction of tese jurídica numerada."""
        entities = extractor.extract("Foi firmada a Tese 390 do STJ.")
        tese = next((e for e in entities if e["entity_type"] == "tese"), None)
        assert tese is not None
        assert "390" in tese["entity_id"]

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
        assert config.uri == "bolt://localhost:8687"
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
        monkeypatch.setenv("NEO4J_MAX_FACTS_PER_CHUNK", "5")
        monkeypatch.setenv("NEO4J_BATCH_SIZE", "200")

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
        assert config.max_facts_per_chunk == 5
        assert config.batch_size == 200

    def test_config_uses_username_alias(self, monkeypatch):
        from app.services.rag.core.neo4j_mvp import Neo4jMVPConfig
        monkeypatch.delenv("NEO4J_USER", raising=False)
        monkeypatch.setenv("NEO4J_USERNAME", "alias_user")

        config = Neo4jMVPConfig.from_env()
        assert config.user == "alias_user"

    def test_config_infers_aura_uri_from_instance_id(self, monkeypatch):
        from app.services.rag.core.neo4j_mvp import Neo4jMVPConfig
        monkeypatch.delenv("NEO4J_URI", raising=False)
        monkeypatch.delenv("NEO4J_URL", raising=False)
        monkeypatch.delenv("NEO4J_BOLT_URL", raising=False)
        monkeypatch.setenv("AURA_INSTANCEID", "24df7574")
        monkeypatch.delenv("NEO4J_DATABASE", raising=False)

        config = Neo4jMVPConfig.from_env()
        assert config.uri == "neo4j+s://24df7574.databases.neo4j.io"
        assert config.database == "neo4j"

    def test_config_prefers_aura_when_uri_is_localhost(self, monkeypatch):
        from app.services.rag.core.neo4j_mvp import Neo4jMVPConfig
        monkeypatch.setenv("NEO4J_URI", "bolt://localhost:7687")
        monkeypatch.setenv("AURA_INSTANCEID", "24df7574")

        config = Neo4jMVPConfig.from_env()
        assert config.uri == "neo4j+s://24df7574.databases.neo4j.io"


class TestFactExtractor:
    def test_extract_prefers_fact_like_sentences(self):
        from app.services.rag.core.neo4j_mvp import FactExtractor

        text = (
            "Em 10/01/2024 as partes celebraram contrato no valor de R$ 1.000,00. "
            "Nos termos do Art. 5º da CF, aplica-se a regra. "
            "O réu inadimpliu o pagamento em 15/02/2024."
        )

        facts = FactExtractor.extract(text, max_facts=2)
        assert len(facts) == 2
        # Should keep at least one sentence with date/value.
        assert any("10/01/2024" in f or "R$" in f for f in facts)


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
            CypherQueries.MERGE_FACT,
            CypherQueries.FIND_CHUNKS_BY_ENTITIES,
            CypherQueries.EXPAND_NEIGHBORS,
            CypherQueries.FIND_PATHS,
            CypherQueries.FIND_PATHS_WITH_ARGUMENTS,
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
        assert "$include_candidates" in CypherQueries.FIND_PATHS
        assert "$include_candidates" in CypherQueries.FIND_PATHS_WITH_ARGUMENTS

        # Document nodes should expose the original app-level id for filtering/export.
        assert "doc_id" in CypherQueries.MERGE_DOCUMENT


def test_find_paths_always_passes_include_candidates_param():
    from app.services.rag.core.neo4j_mvp import Neo4jMVPService

    svc = Neo4jMVPService.__new__(Neo4jMVPService)
    captured = {}

    def _fake_execute_read(_query, params):
        captured["params"] = params
        return []

    svc._execute_read = _fake_execute_read  # type: ignore[attr-defined]

    svc.find_paths(
        entity_ids=["E:1"],
        tenant_id="t1",
        allowed_scopes=["global"],
        include_arguments=False,
    )

    assert captured["params"]["include_candidates"] is False


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
        # Use from_env() to read credentials from environment variables
        config = Neo4jMVPConfig.from_env()
        config.create_indexes = False  # Don't create indexes during availability check
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


class TestPhase0BugFixes:
    """Tests verifying Phase 0 bug fixes for GraphRAG maturity plan."""

    def test_link_methods_exist(self):
        """Verify that both generic and compatibility link methods exist."""
        from app.services.rag.core.neo4j_mvp import Neo4jMVPService

        assert hasattr(Neo4jMVPService, "link_entities"), (
            "Neo4jMVPService must expose link_entities(relation_type=...)"
        )
        assert hasattr(Neo4jMVPService, "link_related_entities"), (
            "Neo4jMVPService must have link_related_entities method"
        )

    def test_ingest_document_calls_a_valid_link_method(self):
        """Verify ingest_document uses a valid link method."""
        import inspect
        from app.services.rag.core.neo4j_mvp import Neo4jMVPService

        source = inspect.getsource(Neo4jMVPService.ingest_document)
        assert (
            "self.link_related_entities(" in source or "self.link_entities(" in source
        ), (
            "ingest_document should call link_related_entities() or link_entities()"
        )

    def test_find_paths_includes_asserts_refers_to(self):
        """Verify FIND_PATHS query traverses ASSERTS and REFERS_TO relationships.

        Bug: FIND_PATHS only traversed RELATED_TO|MENTIONS, missing Fact paths.
        Fix: Added ASSERTS|REFERS_TO to the traversal pattern.
        """
        from app.services.rag.core.neo4j_mvp import CypherQueries

        find_paths = CypherQueries.FIND_PATHS
        assert "ASSERTS" in find_paths, "FIND_PATHS must traverse ASSERTS relationships"
        assert "REFERS_TO" in find_paths, "FIND_PATHS must traverse REFERS_TO relationships"
        assert "RELATED_TO" in find_paths, "FIND_PATHS must still traverse RELATED_TO"
        assert "MENTIONS" in find_paths, "FIND_PATHS must still traverse MENTIONS"

    def test_semantic_extractor_uses_related_to(self):
        """Verify semantic extractor creates RELATED_TO (not SEMANTICALLY_RELATED).

        Bug: semantic_extractor.py created SEMANTICALLY_RELATED but FIND_PATHS
        only traversed RELATED_TO, so semantic paths were never found.
        Fix: Changed to RELATED_TO with relation_subtype='semantic'.
        """
        from app.services.rag.core.semantic_extractor import SemanticCypherQueries

        query = SemanticCypherQueries.CREATE_SEMANTIC_RELATION
        assert "RELATED_TO" in query, (
            "Semantic relations must use RELATED_TO (aligned with FIND_PATHS)"
        )
        assert "SEMANTICALLY_RELATED" not in query, (
            "SEMANTICALLY_RELATED is deprecated — use RELATED_TO with relation_subtype"
        )
        assert "relation_subtype" in query, (
            "Must set relation_subtype='semantic' for provenance tracking"
        )

    def test_semantic_entity_has_dual_label(self):
        """Verify semantic entities use dual label :Entity:SemanticEntity.

        Bug: Used :SEMANTIC_ENTITY label only, so FIND_PATHS (which matches :Entity)
        could not find semantic entities.
        Fix: Changed to :Entity:SemanticEntity dual label.
        """
        from app.services.rag.core.semantic_extractor import SemanticCypherQueries

        query = SemanticCypherQueries.CREATE_SEMANTIC_ENTITY
        assert ":Entity:SemanticEntity" in query, (
            "Semantic entities must use dual label :Entity:SemanticEntity"
        )
        assert ":SEMANTIC_ENTITY" not in query, (
            "Old :SEMANTIC_ENTITY label should not be used (not traversable by FIND_PATHS)"
        )

    def test_hybrid_labels_include_semantic_entity(self):
        """Verify SemanticEntity is registered in hybrid labels whitelist."""
        from app.services.rag.core.graph_hybrid import HYBRID_LABELS_BY_ENTITY_TYPE

        assert "semanticentity" in HYBRID_LABELS_BY_ENTITY_TYPE, (
            "SemanticEntity must be in HYBRID_LABELS_BY_ENTITY_TYPE"
        )
        assert HYBRID_LABELS_BY_ENTITY_TYPE["semanticentity"] == "SemanticEntity"

    def test_cypher_injection_prevention(self):
        """Verify Neo4jAdapter rejects unknown relationship types."""
        from app.services.rag.core.graph_factory import Neo4jAdapter

        allowed = Neo4jAdapter.ALLOWED_RELATIONSHIP_TYPES
        assert isinstance(allowed, frozenset), "ALLOWED_RELATIONSHIP_TYPES must be a frozenset"
        assert len(allowed) > 10, "Whitelist should have a reasonable number of types"

        # Core types must be present
        for rel in ["RELATED_TO", "MENTIONS", "HAS_CHUNK", "SUPPORTS", "OPPOSES"]:
            assert rel in allowed, f"{rel} must be in ALLOWED_RELATIONSHIP_TYPES"

    def test_requirements_has_neo4j(self):
        """Verify neo4j is listed in requirements.txt."""
        import os

        req_path = os.path.join(
            os.path.dirname(__file__), "..", "requirements.txt"
        )
        with open(req_path) as f:
            content = f.read()
        assert "neo4j>=" in content, "neo4j must be in requirements.txt"


class TestPhase1ArgumentRAG:
    """Tests for Phase 1: ArgumentRAG unified schema in Neo4j."""

    def test_argument_neo4j_service_importable(self):
        """Verify ArgumentNeo4jService can be imported."""
        from app.services.rag.core.argument_neo4j import (
            ArgumentNeo4jService,
            ArgumentCypher,
            get_argument_neo4j,
        )
        assert ArgumentNeo4jService is not None
        assert ArgumentCypher is not None

    def test_argument_cypher_schema_constraints(self):
        """Verify schema constraints cover all argument node types."""
        from app.services.rag.core.argument_neo4j import ArgumentCypher

        constraints = ArgumentCypher.SCHEMA_CONSTRAINTS
        assert len(constraints) == 4, "Must have constraints for Claim, Evidence, Actor, Issue"

        constraint_text = " ".join(constraints)
        for label in ("Claim", "Evidence", "Actor", "Issue"):
            assert label in constraint_text, f"Missing constraint for {label}"

    def test_argument_cypher_schema_indexes(self):
        """Verify schema indexes for tenant isolation and queries."""
        from app.services.rag.core.argument_neo4j import ArgumentCypher

        indexes = ArgumentCypher.SCHEMA_INDEXES
        index_text = " ".join(indexes)
        assert "tenant_id" in index_text, "Must index tenant_id for isolation"
        assert "case_id" in index_text, "Must index case_id for case scoping"

    def test_neo4j_mvp_schema_includes_argument_constraints(self):
        """Verify neo4j_mvp CypherQueries includes ArgumentRAG constraints."""
        from app.services.rag.core.neo4j_mvp import CypherQueries

        constraints = CypherQueries.CREATE_CONSTRAINTS
        for label in ("Claim", "Evidence", "Actor", "Issue"):
            assert label in constraints, (
                f"CypherQueries.CREATE_CONSTRAINTS must include {label} constraint"
            )

    def test_neo4j_mvp_schema_includes_argument_indexes(self):
        """Verify neo4j_mvp CypherQueries includes ArgumentRAG indexes."""
        from app.services.rag.core.neo4j_mvp import CypherQueries

        indexes = CypherQueries.CREATE_INDEXES
        assert "arg_claim_tenant" in indexes, "Missing arg_claim_tenant index"
        assert "arg_evidence_tenant" in indexes, "Missing arg_evidence_tenant index"
        assert "arg_issue_case" in indexes, "Missing arg_issue_case index"

    def test_find_paths_with_arguments_includes_argument_relationships(self):
        """Verify FIND_PATHS_WITH_ARGUMENTS traverses argument relationships."""
        from app.services.rag.core.neo4j_mvp import CypherQueries

        find_paths = CypherQueries.FIND_PATHS_WITH_ARGUMENTS
        for rel in ("SUPPORTS", "OPPOSES", "EVIDENCES", "ARGUES", "CONTAINS_CLAIM"):
            assert rel in find_paths, (
                f"FIND_PATHS_WITH_ARGUMENTS must traverse {rel} for argument graph reachability"
            )

    def test_find_paths_entity_only_excludes_argument_relationships(self):
        """Verify entity-only FIND_PATHS does NOT traverse argument relationships."""
        from app.services.rag.core.neo4j_mvp import CypherQueries

        find_paths = CypherQueries.FIND_PATHS
        for rel in ("SUPPORTS", "OPPOSES", "EVIDENCES", "ARGUES", "CONTAINS_CLAIM"):
            assert rel not in find_paths, (
                f"Entity-only FIND_PATHS must NOT traverse {rel}"
            )

    def test_find_paths_with_arguments_matches_argument_targets(self):
        """Verify FIND_PATHS_WITH_ARGUMENTS matches Claim and Evidence as targets."""
        from app.services.rag.core.neo4j_mvp import CypherQueries

        find_paths = CypherQueries.FIND_PATHS_WITH_ARGUMENTS
        assert "target:Claim" in find_paths, "Must match Claim targets"
        assert "target:Evidence" in find_paths, "Must match Evidence targets"

    def test_hybrid_labels_include_argument_types(self):
        """Verify graph_hybrid.py includes Claim/Evidence/Actor/Issue labels."""
        from app.services.rag.core.graph_hybrid import HYBRID_LABELS_BY_ENTITY_TYPE

        expected = {
            "claim": "Claim",
            "evidence": "Evidence",
            "actor": "Actor",
            "issue": "Issue",
        }
        for key, value in expected.items():
            assert key in HYBRID_LABELS_BY_ENTITY_TYPE, f"Missing hybrid label: {key}"
            assert HYBRID_LABELS_BY_ENTITY_TYPE[key] == value, (
                f"Wrong hybrid label value for {key}: expected {value}"
            )

    def test_graph_factory_whitelist_includes_argument_types(self):
        """Verify graph_factory ALLOWED_RELATIONSHIP_TYPES includes argument types."""
        from app.services.rag.core.graph_factory import Neo4jAdapter

        for rel in ("SUPPORTS", "OPPOSES", "EVIDENCES", "ARGUES", "RAISES", "CITES", "CONTAINS_CLAIM"):
            assert rel in Neo4jAdapter.ALLOWED_RELATIONSHIP_TYPES, (
                f"Missing {rel} in ALLOWED_RELATIONSHIP_TYPES"
            )

    def test_claim_extraction_heuristic(self):
        """Test that ArgumentNeo4jService extracts claims from legal text."""
        from app.services.rag.core.argument_neo4j import ArgumentNeo4jService

        svc = ArgumentNeo4jService.__new__(ArgumentNeo4jService)
        svc.config = __import__("app.services.rag.core.argument_neo4j", fromlist=["ArgumentNeo4jConfig"]).ArgumentNeo4jConfig()

        text = (
            "O réu contesta a pretensão autoral. "
            "A testemunha confirma que o dano foi causado pelo réu. "
            "O valor é razoável."
        )
        claims = svc._extract_claims(text)
        assert len(claims) >= 1, "Should extract at least one claim"
        # "confirma" is an assert cue => polarity should be 1
        confirm_claim = next((c for c in claims if "confirma" in c["text"].lower()), None)
        if confirm_claim:
            assert confirm_claim["polarity"] == 1

    def test_stance_inference(self):
        """Test stance inference from legal text."""
        from app.services.rag.core.argument_neo4j import ArgumentNeo4jService, ArgumentNeo4jConfig

        svc = ArgumentNeo4jService.__new__(ArgumentNeo4jService)
        svc.config = ArgumentNeo4jConfig()

        assert svc._infer_stance("O réu contesta a pretensão") == "disputes"
        assert svc._infer_stance("A perícia confirma o dano") == "asserts"
        assert svc._infer_stance("Documento anexado aos autos") == "neutral"

    def test_debate_context_no_doc_ids(self):
        """Test get_debate_context returns empty when results have no doc_ids."""
        from app.services.rag.core.argument_neo4j import ArgumentNeo4jService, ArgumentNeo4jConfig

        svc = ArgumentNeo4jService.__new__(ArgumentNeo4jService)
        svc.config = ArgumentNeo4jConfig()

        results = [{"text": "some text", "metadata": {}}]
        ctx, stats = svc.get_debate_context(results, "tenant1")
        assert ctx == ""
        assert stats["status"] == "no_doc_ids"

    def test_rag_pipeline_argument_backend_env(self):
        """Verify rag_pipeline reads RAG_ARGUMENT_BACKEND env var."""
        import inspect
        from app.services.rag.pipeline.rag_pipeline import RAGPipeline

        source = inspect.getsource(RAGPipeline._stage_graph_enrich)
        assert "RAG_ARGUMENT_BACKEND" in source, (
            "rag_pipeline must read RAG_ARGUMENT_BACKEND env var"
        )
        assert "get_argument_neo4j" in source, (
            "rag_pipeline must import get_argument_neo4j for Neo4j backend"
        )
        assert "ARGUMENT_PACK" in source, (
            "rag_pipeline must keep ARGUMENT_PACK for legacy fallback"
        )
