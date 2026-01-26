import pytest


def test_label_for_entity_type_whitelist():
    from app.services.rag.core.graph_hybrid import label_for_entity_type

    # Core types from LegalEntityExtractor
    assert label_for_entity_type("lei") == "Lei"
    assert label_for_entity_type("  sumula  ") == "Sumula"
    assert label_for_entity_type("ARTIGO") == "Artigo"
    assert label_for_entity_type("jurisprudencia") == "Jurisprudencia"
    assert label_for_entity_type("documento") == "Documento"
    assert label_for_entity_type("processo") == "Processo"
    assert label_for_entity_type("tribunal") == "Tribunal"
    assert label_for_entity_type("tema") == "Tema"


def test_label_for_entity_type_non_whitelisted():
    from app.services.rag.core.graph_hybrid import label_for_entity_type

    # Types not in whitelist or invalid
    assert label_for_entity_type("unknown_type") is None
    assert label_for_entity_type("") is None
    assert label_for_entity_type(None) is None
    # Cypher injection attempt should be blocked
    assert label_for_entity_type("lei; MATCH (n) DETACH DELETE n") is None


def test_label_for_entity_type_forbidden_labels():
    """Ensure structural labels cannot be used as hybrid labels."""
    from app.services.rag.core.graph_hybrid import (
        FORBIDDEN_LABELS,
        HYBRID_LABELS_BY_ENTITY_TYPE,
        label_for_entity_type,
    )

    # Verify FORBIDDEN_LABELS contains expected structural labels
    assert "Entity" in FORBIDDEN_LABELS
    assert "Document" in FORBIDDEN_LABELS
    assert "Chunk" in FORBIDDEN_LABELS
    assert "Relationship" in FORBIDDEN_LABELS

    # Ensure no whitelisted type maps to a forbidden label
    for entity_type, label in HYBRID_LABELS_BY_ENTITY_TYPE.items():
        assert label not in FORBIDDEN_LABELS, (
            f"entity_type '{entity_type}' maps to forbidden label '{label}'"
        )


def test_hybrid_schema_statements_include_labels():
    from app.services.rag.core.graph_hybrid import hybrid_schema_statements

    stmts = hybrid_schema_statements(["Lei"])
    assert any("FOR (e:Lei)" in s for s in stmts)
    assert any("rag_lei_normalized" in s for s in stmts)

