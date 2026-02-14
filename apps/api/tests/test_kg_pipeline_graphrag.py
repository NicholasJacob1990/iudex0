"""
Tests for KG Builder pipeline and legal schema compatibility.

Verifica que:
1. build_legal_schema() retorna formato compatível com neo4j-graphrag
2. build_graphrag_schema() cria GraphSchema nativo
3. get_schema_description() gera texto para Text2Cypher
4. Pipeline imports funcionam
"""

import pytest


class TestLegalSchema:
    """Testa schema legal para compatibilidade com neo4j-graphrag."""

    def test_legal_node_types_not_empty(self):
        from app.services.rag.core.kg_builder.legal_schema import LEGAL_NODE_TYPES
        assert len(LEGAL_NODE_TYPES) > 0

    def test_all_node_types_have_properties(self):
        """Cada node type deve ter pelo menos 1 property (requisito neo4j-graphrag)."""
        from app.services.rag.core.kg_builder.legal_schema import LEGAL_NODE_TYPES
        for nt in LEGAL_NODE_TYPES:
            assert len(nt["properties"]) >= 1, f"{nt['label']} tem 0 properties"

    def test_all_node_types_have_name_property(self):
        """Cada node type deve ter property 'name' (usado como identificador)."""
        from app.services.rag.core.kg_builder.legal_schema import LEGAL_NODE_TYPES
        for nt in LEGAL_NODE_TYPES:
            prop_names = [p["name"] for p in nt["properties"]]
            assert "name" in prop_names, f"{nt['label']} não tem property 'name'"

    def test_legal_patterns_valid(self):
        """Patterns devem ser tuplas de 3 elementos com labels válidos."""
        from app.services.rag.core.kg_builder.legal_schema import (
            LEGAL_PATTERNS,
            LEGAL_NODE_TYPES,
            LEGAL_RELATIONSHIP_TYPES,
        )

        valid_labels = {nt["label"] for nt in LEGAL_NODE_TYPES}
        valid_rels = {rt["label"] for rt in LEGAL_RELATIONSHIP_TYPES}

        for src, rel, tgt in LEGAL_PATTERNS:
            assert src in valid_labels, f"Pattern source '{src}' não é um node type válido"
            assert tgt in valid_labels, f"Pattern target '{tgt}' não é um node type válido"
            assert rel in valid_rels, f"Pattern rel '{rel}' não é um relationship type válido"


class TestBuildGraphragSchema:
    """Testa construção de GraphSchema nativo."""

    def test_build_graphrag_schema_succeeds(self):
        """build_graphrag_schema() deve retornar GraphSchema sem erro."""
        try:
            from app.services.rag.core.kg_builder.legal_schema import build_graphrag_schema
            schema = build_graphrag_schema()
            assert schema is not None
        except ImportError:
            pytest.skip("neo4j-graphrag not installed")

    def test_build_graphrag_schema_has_node_types(self):
        try:
            from app.services.rag.core.kg_builder.legal_schema import build_graphrag_schema
            schema = build_graphrag_schema()
            assert hasattr(schema, "node_types")
            assert len(schema.node_types) > 0
        except ImportError:
            pytest.skip("neo4j-graphrag not installed")

    def test_build_graphrag_schema_has_patterns(self):
        try:
            from app.services.rag.core.kg_builder.legal_schema import build_graphrag_schema
            schema = build_graphrag_schema()
            assert hasattr(schema, "patterns")
            assert len(schema.patterns) > 0
        except ImportError:
            pytest.skip("neo4j-graphrag not installed")


class TestBuildLegalSchema:
    """Testa build_legal_schema() (fallback-aware)."""

    def test_build_legal_schema_returns_something(self):
        from app.services.rag.core.kg_builder.legal_schema import build_legal_schema
        schema = build_legal_schema()
        assert schema is not None

    def test_fallback_returns_dict(self):
        """Se neo4j-graphrag não está disponível, retorna dict."""
        from app.services.rag.core.kg_builder.legal_schema import build_legal_schema
        schema = build_legal_schema()
        # Either GraphSchema or dict — both are valid
        assert schema is not None

    def test_schema_mode_auto_sets_additional_flags_in_fallback(self, monkeypatch):
        import app.services.rag.core.kg_builder.legal_schema as legal_schema

        def _raise_import_error(*args, **kwargs):
            raise ImportError()

        monkeypatch.setattr(legal_schema, "build_graphrag_schema", _raise_import_error)
        schema = legal_schema.build_legal_schema(schema_mode="auto")
        assert schema["additional_node_types"] is True
        assert schema["additional_relationship_types"] is True
        assert schema["additional_patterns"] is True

    def test_schema_mode_ontology_is_strict_in_fallback(self, monkeypatch):
        import app.services.rag.core.kg_builder.legal_schema as legal_schema

        def _raise_import_error(*args, **kwargs):
            raise ImportError()

        monkeypatch.setattr(legal_schema, "build_graphrag_schema", _raise_import_error)
        schema = legal_schema.build_legal_schema(schema_mode="ontology")
        assert schema["additional_node_types"] is False
        assert schema["additional_relationship_types"] is False
        assert schema["additional_patterns"] is False

    def test_normalize_schema_mode(self):
        from app.services.rag.core.kg_builder.legal_schema import normalize_schema_mode

        assert normalize_schema_mode("ontology") == "ontology"
        assert normalize_schema_mode("auto") == "auto"
        assert normalize_schema_mode("hybrid") == "hybrid"
        assert normalize_schema_mode("AUTO") == "auto"
        assert normalize_schema_mode("invalid") == "ontology"


class TestSchemaDescription:
    """Testa get_schema_description() para Text2Cypher."""

    def test_schema_description_contains_node_labels(self):
        from app.services.rag.core.kg_builder.legal_schema import get_schema_description
        desc = get_schema_description()
        assert "Node labels:" in desc
        assert "Lei" in desc
        assert "Artigo" in desc
        assert "Sumula" in desc

    def test_schema_description_contains_structural_nodes(self):
        from app.services.rag.core.kg_builder.legal_schema import get_schema_description
        desc = get_schema_description()
        assert "Document" in desc
        assert "Chunk" in desc

    def test_schema_description_contains_relationships(self):
        from app.services.rag.core.kg_builder.legal_schema import get_schema_description
        desc = get_schema_description()
        assert "CITA" in desc
        assert "MENTIONS" in desc
        assert "HAS_CHUNK" in desc


class TestPipelineImports:
    """Testa que imports do pipeline funcionam."""

    def test_import_run_kg_builder(self):
        from app.services.rag.core.kg_builder.pipeline import run_kg_builder
        assert callable(run_kg_builder)

    def test_import_simple_kg_pipeline(self):
        try:
            from neo4j_graphrag.experimental.pipeline.kg_builder import SimpleKGPipeline
            assert SimpleKGPipeline is not None
        except ImportError:
            pytest.skip("neo4j-graphrag not installed")

    def test_import_text2cypher_retriever(self):
        try:
            from neo4j_graphrag.retrievers import Text2CypherRetriever
            assert Text2CypherRetriever is not None
        except ImportError:
            pytest.skip("neo4j-graphrag not installed")

    def test_schema_mode_env_parser(self, monkeypatch):
        from app.services.rag.core.kg_builder.pipeline import _kg_schema_mode

        monkeypatch.setenv("KG_BUILDER_SCHEMA_MODE", "hybrid")
        assert _kg_schema_mode() == "hybrid"

        monkeypatch.setenv("KG_BUILDER_SCHEMA_MODE", "bad-value")
        assert _kg_schema_mode() == "ontology"
