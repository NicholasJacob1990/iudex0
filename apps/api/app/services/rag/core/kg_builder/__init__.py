"""
KG Builder — Knowledge Graph construction pipeline using neo4j-graphrag-python.

Custom Components for legal domain extraction, schema definition,
entity resolution, and pipeline orchestration.

Components:
- LegalRegexExtractor: Regex-based legal entity extraction (Art, Lei, Sumula, etc.)
- LegalSchemaBuilder: Schema definition for Brazilian legal entities and relations
- LegalFuzzyResolver: Entity resolution via rapidfuzz (no spaCy dependency)
- LegalKGPipeline: Composed pipeline (Regex + LLM -> Merge -> Resolve -> Write)
"""

from app.services.rag.core.kg_builder.legal_schema import (
    LEGAL_NODE_TYPES,
    LEGAL_RELATIONSHIP_TYPES,
    LEGAL_PATTERNS,
    build_legal_schema,
)

__all__ = [
    "LEGAL_NODE_TYPES",
    "LEGAL_RELATIONSHIP_TYPES",
    "LEGAL_PATTERNS",
    "build_legal_schema",
]
