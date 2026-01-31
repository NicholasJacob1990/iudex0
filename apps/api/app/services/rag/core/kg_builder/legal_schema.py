"""
Legal Schema — Entity types, relationship types, and patterns for Brazilian legal domain.

Used by both SimpleKGPipeline (dict-based schema) and SchemaBuilder (component-based).
Follows neo4j-graphrag-python schema API (node_types, relationship_types, patterns).
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple


# =============================================================================
# NODE TYPES
# =============================================================================

LEGAL_NODE_TYPES: List[Dict[str, Any]] = [
    # Core legal entities (regex-extractable)
    {
        "label": "Lei",
        "description": "Lei, Decreto, MP, LC, Portaria, Resolução (legislação brasileira)",
        "properties": [
            {"name": "name", "type": "STRING", "required": True},
            {"name": "numero", "type": "STRING"},
            {"name": "ano", "type": "STRING"},
            {"name": "tipo", "type": "STRING"},
        ],
    },
    {
        "label": "Artigo",
        "description": "Artigo de lei, com parágrafo e inciso opcionais",
        "properties": [
            {"name": "name", "type": "STRING", "required": True},
            {"name": "artigo", "type": "STRING"},
            {"name": "paragrafo", "type": "STRING"},
            {"name": "inciso", "type": "STRING"},
        ],
    },
    {
        "label": "Sumula",
        "description": "Súmula (vinculante ou não) de tribunal superior",
        "properties": [
            {"name": "name", "type": "STRING", "required": True},
            {"name": "numero", "type": "STRING"},
            {"name": "tribunal", "type": "STRING"},
        ],
    },
    {
        "label": "Tribunal",
        "description": "Tribunal (STF, STJ, TST, TRF, TJ, TRT)",
        "properties": [
            {"name": "name", "type": "STRING", "required": True},
            {"name": "sigla", "type": "STRING"},
        ],
    },
    {
        "label": "Processo",
        "description": "Processo judicial (número CNJ)",
        "properties": [
            {"name": "name", "type": "STRING", "required": True},
            {"name": "numero_cnj", "type": "STRING"},
        ],
    },
    {
        "label": "Tema",
        "description": "Tema de repercussão geral (STF/STJ)",
        "properties": [
            {"name": "name", "type": "STRING", "required": True},
            {"name": "numero", "type": "STRING"},
            {"name": "tribunal", "type": "STRING"},
        ],
    },
    # ArgumentRAG entities (LLM-extractable)
    {
        "label": "Claim",
        "description": "Tese ou contratese jurídica, alegação ou proposição",
        "properties": [
            {"name": "name", "type": "STRING", "required": True},
            {"name": "claim_type", "type": "STRING"},
            {"name": "polarity", "type": "INTEGER"},
        ],
    },
    {
        "label": "Evidence",
        "description": "Evidência documental, jurisprudencial ou doutrinária",
        "properties": [
            {"name": "name", "type": "STRING", "required": True},
            {"name": "evidence_type", "type": "STRING"},
            {"name": "weight", "type": "FLOAT"},
        ],
    },
    {
        "label": "Actor",
        "description": "Parte, advogado, juiz, relator ou outro ator processual",
        "properties": [
            {"name": "name", "type": "STRING", "required": True},
            {"name": "role", "type": "STRING"},
        ],
    },
    {
        "label": "Issue",
        "description": "Questão jurídica controvertida",
        "properties": [
            {"name": "name", "type": "STRING", "required": True},
            {"name": "domain", "type": "STRING"},
        ],
    },
    # Semantic entities (LLM-extractable)
    {
        "label": "SemanticEntity",
        "description": "Conceito, princípio, instituto ou tese jurídica extraída por LLM",
        "properties": [
            {"name": "name", "type": "STRING", "required": True},
            {"name": "category", "type": "STRING"},
        ],
    },
]


# =============================================================================
# RELATIONSHIP TYPES
# =============================================================================

LEGAL_RELATIONSHIP_TYPES: List[Dict[str, Any]] = [
    # Core graph relationships
    {"label": "MENTIONS", "description": "Chunk menciona entidade"},
    {"label": "RELATED_TO", "description": "Relação genérica entre entidades"},
    {"label": "CITA", "description": "Entidade cita outra (ex: acórdão cita lei)"},
    {"label": "APLICA", "description": "Entidade aplica outra (ex: tribunal aplica súmula)"},
    {"label": "REVOGA", "description": "Entidade revoga outra (ex: lei nova revoga antiga)"},
    {"label": "ALTERA", "description": "Entidade altera outra"},
    {"label": "FUNDAMENTA", "description": "Entidade fundamenta decisão"},
    {"label": "INTERPRETA", "description": "Entidade interpreta outra"},
    # ArgumentRAG relationships
    {"label": "SUPPORTS", "description": "Claim ou Evidence suporta outra Claim"},
    {"label": "OPPOSES", "description": "Claim ou Evidence contesta outra Claim"},
    {"label": "EVIDENCES", "description": "Evidence fundamenta Claim"},
    {"label": "ARGUES", "description": "Actor argumenta Claim"},
    {"label": "RAISES", "description": "Claim levanta Issue"},
    {"label": "CITES", "description": "Claim ou Evidence cita Entity"},
    {"label": "CONTAINS_CLAIM", "description": "Chunk contém Claim"},
]


# =============================================================================
# PATTERNS (allowed triplets)
# =============================================================================

LEGAL_PATTERNS: List[Tuple[str, str, str]] = [
    # Core legal relationships
    ("Lei", "CITA", "Lei"),
    ("Lei", "REVOGA", "Lei"),
    ("Lei", "ALTERA", "Lei"),
    ("Artigo", "RELATED_TO", "Lei"),
    ("Sumula", "FUNDAMENTA", "Claim"),
    ("Sumula", "INTERPRETA", "Lei"),
    ("Tribunal", "APLICA", "Sumula"),
    ("Tribunal", "APLICA", "Lei"),
    ("Processo", "RELATED_TO", "Tribunal"),
    ("Tema", "RELATED_TO", "Tribunal"),
    # ArgumentRAG patterns
    ("Claim", "SUPPORTS", "Claim"),
    ("Claim", "OPPOSES", "Claim"),
    ("Evidence", "EVIDENCES", "Claim"),
    ("Actor", "ARGUES", "Claim"),
    ("Claim", "RAISES", "Issue"),
    ("Claim", "CITES", "Lei"),
    ("Claim", "CITES", "Sumula"),
    ("Claim", "CITES", "Artigo"),
    ("Evidence", "CITES", "Lei"),
    ("Evidence", "CITES", "Sumula"),
    # Semantic relationships
    ("SemanticEntity", "RELATED_TO", "SemanticEntity"),
    ("SemanticEntity", "RELATED_TO", "Lei"),
    ("SemanticEntity", "RELATED_TO", "Sumula"),
]


# =============================================================================
# SCHEMA BUILDER HELPER
# =============================================================================

def build_legal_schema() -> Dict[str, Any]:
    """
    Build a schema dict compatible with SimpleKGPipeline.

    Usage:
        from app.services.rag.core.kg_builder.legal_schema import build_legal_schema
        schema = build_legal_schema()
        pipeline = SimpleKGPipeline(schema=schema, ...)
    """
    return {
        "node_types": LEGAL_NODE_TYPES,
        "relationship_types": LEGAL_RELATIONSHIP_TYPES,
        "patterns": LEGAL_PATTERNS,
        "additional_node_types": False,
    }
