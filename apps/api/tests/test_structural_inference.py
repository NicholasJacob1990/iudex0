"""
Tests for deterministic structural inference edges in the Legal KG.

Currently:
- SUBDISPOSITIVO_DE: Artigo subdispositivo (paragrafo/inciso) -> artigo-pai
"""

import inspect


def test_subdispositivo_de_in_schema_relationship_types():
    from app.services.rag.core.kg_builder.legal_schema import LEGAL_RELATIONSHIP_TYPES

    labels = {rt["label"] for rt in LEGAL_RELATIONSHIP_TYPES}
    assert "SUBDISPOSITIVO_DE" in labels


def test_subdispositivo_de_in_schema_patterns():
    from app.services.rag.core.kg_builder.legal_schema import LEGAL_PATTERNS

    assert ("Artigo", "SUBDISPOSITIVO_DE", "Artigo") in set(LEGAL_PATTERNS)


def test_postprocessor_infers_subdispositivo_de():
    from app.services.rag.core.kg_builder import legal_postprocessor

    src = inspect.getsource(legal_postprocessor)
    assert "SUBDISPOSITIVO_DE" in src
    assert "KG_BUILDER_INFER_SUBDISPOSITIVO_DE" in src

