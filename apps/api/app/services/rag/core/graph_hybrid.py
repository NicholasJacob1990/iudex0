from __future__ import annotations

import logging
import re
from typing import Any, Dict, Iterable, Optional, Tuple

logger = logging.getLogger(__name__)

_SAFE_LABEL_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# Forbidden labels: these are base/structural labels in the graph schema.
# Entity types that would map to these must be rejected to avoid collisions.
FORBIDDEN_LABELS = frozenset({"Entity", "Document", "Chunk", "Relationship"})


# Whitelist: only these entity_type values become Neo4j labels.
# Anything not in this map remains only as (:Entity {entity_type: ...}).
# Must match EntityType enum in graph_rag.py for full coverage.
HYBRID_LABELS_BY_ENTITY_TYPE: Dict[str, str] = {
    # Core legal entities (from LegalEntityExtractor)
    "lei": "Lei",
    "artigo": "Artigo",
    "sumula": "Sumula",
    "jurisprudencia": "Jurisprudencia",
    "tese": "Tese",
    "tema": "Tema",
    "documento": "Documento",
    "parte": "Parte",
    "tribunal": "Tribunal",
    "processo": "Processo",
    "recurso": "Recurso",
    "decisao": "Decisao",
    "acordao": "Acordao",
    "ministro": "Ministro",
    "relator": "Relator",
    # Additional types
    "oab": "OAB",
    # Factual entities
    "pessoa": "Pessoa",
    "empresa": "Empresa",
    "evento": "Evento",
    "cpf": "Pessoa",
    "cnpj": "Empresa",
    "orgao_publico": "OrgaoPublico",
    "prazo": "Prazo",
    "valor_monetario": "ValorMonetario",
    "data_juridica": "DataJuridica",
    "local": "Local",
    # Semantic extraction
    "semanticentity": "SemanticEntity",
    # ArgumentRAG
    "claim": "Claim",
    "evidence": "Evidence",
    "actor": "Actor",
    "issue": "Issue",
}


def register_dynamic_label(entity_type: str, label: str) -> bool:
    """Register a dynamically discovered label into the runtime whitelist.

    Validates safety and idempotently adds to HYBRID_LABELS_BY_ENTITY_TYPE.

    Returns True if registered, False if rejected.
    """
    key = entity_type.strip().lower()
    if not key or len(key) < 3:
        return False

    if not _SAFE_LABEL_RE.fullmatch(label):
        logger.warning("Dynamic label rejected (unsafe): %r", label)
        return False

    if label in FORBIDDEN_LABELS:
        logger.warning("Dynamic label rejected (forbidden): %r", label)
        return False

    if key in HYBRID_LABELS_BY_ENTITY_TYPE:
        return True  # already registered, idempotent

    HYBRID_LABELS_BY_ENTITY_TYPE[key] = label
    logger.info("Registered dynamic label: %s -> %s", key, label)
    return True


def label_for_entity_type(entity_type: Optional[str]) -> Optional[str]:
    """Return a safe Neo4j label for a given entity_type, or None if not allowed.

    Validates against:
    - Empty/None input
    - Non-whitelisted entity types
    - Forbidden structural labels (Entity, Document, Chunk, Relationship)
    - Unsafe characters (Cypher injection prevention)
    """
    if not entity_type:
        return None

    key = entity_type.strip().lower()
    label = HYBRID_LABELS_BY_ENTITY_TYPE.get(key)
    if not label:
        return None

    # Prevent collision with base/structural labels
    if label in FORBIDDEN_LABELS:
        logger.warning("Forbidden hybrid label rejected: %r (collides with structural label)", label)
        return None

    if not _SAFE_LABEL_RE.fullmatch(label):
        logger.warning("Unsafe hybrid label ignored: %r", label)
        return None

    return label


def base_schema_statements() -> Tuple[str, ...]:
    """Schema statements that support the generic (:Entity) model."""
    return (
        "CREATE CONSTRAINT rag_entity_id IF NOT EXISTS FOR (e:Entity) REQUIRE e.entity_id IS UNIQUE",
        "CREATE INDEX rag_entity_type IF NOT EXISTS FOR (e:Entity) ON (e.entity_type)",
        "CREATE INDEX rag_entity_normalized IF NOT EXISTS FOR (e:Entity) ON (e.normalized)",
    )


def hybrid_schema_statements(labels: Iterable[str]) -> Tuple[str, ...]:
    """Schema statements for the hybrid model (labels per entity type)."""
    stmts = []
    for label in labels:
        if not _SAFE_LABEL_RE.fullmatch(label):
            continue
        lname = label.lower()
        stmts.extend(
            [
                f"CREATE CONSTRAINT rag_{lname}_entity_id IF NOT EXISTS FOR (e:{label}) REQUIRE e.entity_id IS UNIQUE",
                f"CREATE INDEX rag_{lname}_normalized IF NOT EXISTS FOR (e:{label}) ON (e.normalized)",
                f"CREATE INDEX rag_{lname}_name IF NOT EXISTS FOR (e:{label}) ON (e.name)",
            ]
        )
    return tuple(stmts)


def ensure_neo4j_schema(session: Any, *, hybrid: bool) -> None:
    """
    Ensure base schema exists, and (optionally) hybrid schema.

    `session` is a neo4j.Session (kept untyped to avoid importing neo4j at import time).
    """
    statements = list(base_schema_statements())
    if hybrid:
        labels = sorted(set(HYBRID_LABELS_BY_ENTITY_TYPE.values()))
        statements.extend(hybrid_schema_statements(labels))

    for stmt in statements:
        try:
            session.run(stmt)
        except Exception as e:
            logger.debug("Neo4j schema statement skipped/failed: %s (%s)", stmt, e)


def migrate_hybrid_labels(session: Any) -> Dict[str, int]:
    """
    Backfill hybrid labels based on Entity.entity_type.

    Uses an explicit transaction for atomicity - all labels are migrated
    together or none are (rollback on failure).

    Returns a dict mapping label -> updated count.
    """
    results: Dict[str, int] = {}
    tx = None
    try:
        tx = session.begin_transaction()
        for entity_type, label in HYBRID_LABELS_BY_ENTITY_TYPE.items():
            if not _SAFE_LABEL_RE.fullmatch(label):
                continue
            query = f"""
            MATCH (e:Entity)
            WHERE e.entity_type = $entity_type AND NOT (e:{label})
            SET e:{label}
            RETURN count(e) as updated
            """
            record = tx.run(query, entity_type=entity_type).single()
            results[label] = int(record["updated"]) if record and "updated" in record else 0
        tx.commit()
        logger.info("Hybrid label migration completed: %s", results)
    except Exception as e:
        logger.error("Neo4j hybrid migration failed, rolling back: %s", e)
        if tx is not None:
            try:
                tx.rollback()
            except Exception:
                pass  # Already closed or failed
        raise
    return results

