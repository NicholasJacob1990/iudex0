"""
Schema Discovery — Post-processing for LLM-discovered entity types.

When the GraphRAG pipeline runs in auto/hybrid mode with additional_node_types=True,
the LLM may produce entity types not in the predefined whitelist. These remain as
generic (:Entity {entity_type: "..."}) nodes.

This module:
1. Queries Neo4j for entity types NOT in the whitelist
2. Validates them via heuristics (min instances, stopwords, label safety)
3. Optionally registers valid types into the runtime whitelist
4. Persists discovered types as (:DiscoveredSchema) for reuse across runs

Usage:
    from app.services.rag.core.kg_builder.schema_discovery import SchemaDiscoveryProcessor

    processor = SchemaDiscoveryProcessor(driver=driver, database="iudex")
    result = processor.discover(tenant_id="t1")
"""

from __future__ import annotations

import logging
import os
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class DiscoveredType:
    """A single discovered entity type."""
    raw_type: str
    normalized_key: str
    proposed_label: str
    instance_count: int
    sample_names: List[str] = field(default_factory=list)
    is_valid: bool = False
    rejection_reason: str = ""


@dataclass
class DiscoveryResult:
    """Stats from a schema discovery run."""
    total_unknown_entities: int = 0
    discovered_types: List[DiscoveredType] = field(default_factory=list)
    rehydrated_types: List[str] = field(default_factory=list)
    registered_types: List[str] = field(default_factory=list)
    skipped_types: List[str] = field(default_factory=list)


# =============================================================================
# CONSTANTS
# =============================================================================

_STOPWORD_TYPES = frozenset({
    "entity", "node", "thing", "object", "unknown", "other",
    "item", "element", "concept", "generic", "misc", "none",
    "null", "undefined", "general", "default",
})

_FORBIDDEN_LABELS = frozenset({
    "Entity", "Document", "Chunk", "Relationship",
    "Community", "TenantEntityMetric", "DiscoveredSchema",
})

_SAFE_LABEL_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


# =============================================================================
# HELPERS
# =============================================================================

def _to_pascal_case(text: str) -> str:
    """Convert a raw entity type string to PascalCase Neo4j label.

    Examples:
        "norma" -> "Norma"
        "orgao_publico" -> "OrgaoPublico"
        "órgão público" -> "OrgaoPublico"
    """
    # Remove accents
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_text = "".join(c for c in nfkd if not unicodedata.combining(c))

    # Split by underscores, spaces, hyphens
    parts = re.split(r"[\s_\-]+", ascii_text.strip())
    result = "".join(p.capitalize() for p in parts if p)
    return result or text.capitalize()


# =============================================================================
# PROCESSOR
# =============================================================================

class SchemaDiscoveryProcessor:
    """Discovers and validates new entity types from LLM extraction."""

    def __init__(
        self,
        driver: Any = None,
        database: str = "iudex",
        *,
        min_instances: int = 0,
        auto_register: bool = True,
    ):
        self._driver = driver
        self._database = database
        self._min_instances = min_instances or int(
            os.getenv("KG_BUILDER_SCHEMA_DISCOVERY_MIN_INSTANCES", "2")
        )
        self._auto_register = auto_register if auto_register is not None else (
            os.getenv("KG_BUILDER_SCHEMA_DISCOVERY_AUTO_REGISTER", "true").lower()
            in ("1", "true", "yes")
        )

    def _get_driver(self):
        if self._driver is None:
            from app.services.rag.core.neo4j_mvp import get_neo4j_mvp
            neo4j = get_neo4j_mvp()
            self._driver = neo4j.driver
            self._database = neo4j.config.database
        return self._driver

    def discover(self, tenant_id: str) -> DiscoveryResult:
        """Run schema discovery for a tenant.

        1. Query unknown entity types from Neo4j
        2. Validate each type
        3. Optionally register valid types into the whitelist
        """
        from app.services.rag.core.graph_hybrid import HYBRID_LABELS_BY_ENTITY_TYPE

        result = DiscoveryResult()
        known_types = set(HYBRID_LABELS_BY_ENTITY_TYPE.keys())

        # 0. Rehydrate persisted schema (so discovery is reusable across runs)
        if self._auto_register:
            try:
                rehydrated = self.rehydrate(tenant_id)
                if rehydrated:
                    result.rehydrated_types = rehydrated
                    known_types.update(rehydrated)
            except Exception as e:
                logger.debug("Schema rehydrate skipped: %s", e)

        # 1. Query unknown types
        try:
            unknown_types = self._query_unknown_types(tenant_id, known_types)
        except Exception as e:
            logger.warning("Schema discovery query failed: %s", e)
            return result

        result.total_unknown_entities = sum(t["count"] for t in unknown_types)

        # 2. Validate each type
        for raw in unknown_types:
            discovered = self._validate_type(raw, known_types)
            result.discovered_types.append(discovered)

            if discovered.is_valid:
                if self._auto_register:
                    registered = self._register_type(discovered, known_types)
                    if registered:
                        result.registered_types.append(discovered.normalized_key)
                        known_types.add(discovered.normalized_key)
                    else:
                        result.skipped_types.append(
                            f"{discovered.normalized_key}:register_failed"
                        )
            else:
                result.skipped_types.append(
                    f"{discovered.normalized_key}:{discovered.rejection_reason}"
                )

        # 3. Persist to Neo4j
        if result.registered_types:
            try:
                self._persist_discovered_schema(tenant_id, result)
            except Exception as e:
                logger.debug("Could not persist discovered schema: %s", e)

        logger.info(
            "Schema discovery for tenant %s: %d unknown entities, %d types found, "
            "%d rehydrated, %d registered, %d skipped",
            tenant_id, result.total_unknown_entities,
            len(result.discovered_types), len(result.rehydrated_types),
            len(result.registered_types),
            len(result.skipped_types),
        )
        return result

    def rehydrate(self, tenant_id: str) -> List[str]:
        """Load persisted discovered types and register into runtime whitelist."""
        import json
        from app.services.rag.core.graph_hybrid import register_dynamic_label

        driver = self._get_driver()
        query = """
            MATCH (ds:DiscoveredSchema {tenant_id: $tenant_id})
            RETURN ds.types_json AS types_json
            LIMIT 1
        """
        with driver.session(database=self._database) as session:
            record = session.run(query, tenant_id=tenant_id).single()

        if not record:
            return []

        payload = record.get("types_json")
        if not payload:
            return []

        try:
            data = json.loads(payload)
        except Exception:
            logger.debug("Invalid types_json payload for tenant %s", tenant_id)
            return []

        rehydrated: List[str] = []
        for item in data if isinstance(data, list) else []:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key", "")).strip().lower()
            label = str(item.get("label", "")).strip()
            if not key or not label:
                continue
            if register_dynamic_label(key, label):
                rehydrated.append(key)

        if rehydrated:
            logger.info(
                "Schema discovery rehydrated %d types for tenant %s",
                len(rehydrated),
                tenant_id,
            )
        return rehydrated

    def _query_unknown_types(
        self,
        tenant_id: str,
        known_types: set,
    ) -> List[Dict[str, Any]]:
        """Query Neo4j for entity types not in the whitelist."""
        driver = self._get_driver()
        query = """
            MATCH (d:Document {tenant_id: $tenant_id})-[:HAS_CHUNK]->(:Chunk)-[:MENTIONS]->(e:Entity)
            WHERE e.entity_type IS NOT NULL
              AND NOT toLower(e.entity_type) IN $known_types
            WITH toLower(e.entity_type) AS etype,
                 collect(DISTINCT e.name)[..5] AS samples,
                 count(DISTINCT e) AS cnt
            WHERE cnt >= $min_instances
            RETURN etype AS type, cnt AS count, samples
            ORDER BY cnt DESC
            LIMIT 50
        """
        with driver.session(database=self._database) as session:
            records = session.run(
                query,
                tenant_id=tenant_id,
                known_types=list(known_types),
                min_instances=self._min_instances,
            )
            return [dict(r) for r in records]

    def _validate_type(
        self,
        raw: Dict[str, Any],
        known_types: set,
    ) -> DiscoveredType:
        """Validate a discovered type against heuristics."""
        raw_type = str(raw.get("type", ""))
        normalized = raw_type.strip().lower()
        label = _to_pascal_case(raw_type)
        count = int(raw.get("count", 0))
        samples = list(raw.get("samples", []))

        discovered = DiscoveredType(
            raw_type=raw_type,
            normalized_key=normalized,
            proposed_label=label,
            instance_count=count,
            sample_names=samples[:5],
        )

        # Check stopword
        if normalized in _STOPWORD_TYPES:
            discovered.rejection_reason = "stopword"
            return discovered

        # Check length
        if len(normalized) < 3:
            discovered.rejection_reason = "too_short"
            return discovered

        # Check forbidden label
        if label in _FORBIDDEN_LABELS:
            discovered.rejection_reason = "forbidden_label"
            return discovered

        # Check label safety (Cypher injection prevention)
        if not _SAFE_LABEL_RE.fullmatch(label):
            discovered.rejection_reason = "unsafe_label"
            return discovered

        # Check minimum instances
        if count < self._min_instances:
            discovered.rejection_reason = "low_count"
            return discovered

        # Check sample quality: at least 1 sample with > 2 chars
        valid_samples = [s for s in samples if s and len(str(s).strip()) > 2]
        if not valid_samples:
            discovered.rejection_reason = "low_quality_names"
            return discovered

        # Check already registered (in case of concurrent runs)
        if normalized in known_types:
            discovered.rejection_reason = "already_known"
            return discovered

        discovered.is_valid = True
        return discovered

    def _register_type(self, discovered: DiscoveredType, known_types: set) -> bool:
        """Register a valid discovered type into the runtime whitelist."""
        from app.services.rag.core.graph_hybrid import register_dynamic_label
        return register_dynamic_label(discovered.normalized_key, discovered.proposed_label)

    def _persist_discovered_schema(
        self,
        tenant_id: str,
        result: DiscoveryResult,
    ) -> None:
        """Persist discovered types to Neo4j for reuse across runs."""
        import json
        driver = self._get_driver()

        registered_keys = set(result.registered_types)
        types_data = [
            {
                "key": dt.normalized_key,
                "label": dt.proposed_label,
                "count": dt.instance_count,
                "samples": dt.sample_names[:3],
            }
            for dt in result.discovered_types
            if dt.normalized_key in registered_keys
        ]

        query = """
            MERGE (ds:DiscoveredSchema {tenant_id: $tenant_id})
            SET ds.types_json = $types_json,
                ds.updated_at = datetime()
        """
        with driver.session(database=self._database) as session:
            session.run(query, tenant_id=tenant_id, types_json=json.dumps(types_data))
