"""
Cross-Extractor Entity Merger — Deduplication between extraction pipelines.

Regex, GLiNER, and LLM extractors may produce different entity_ids for the
same real-world entity (e.g., "lei_8666_1993" vs "gliner_abc123" for "Lei 8.666").

The fuzzy_resolver only resolves within a single Neo4j label. This module
resolves across labels and across extractors by:
1. Querying entities with same normalized name but different entity_ids
2. Comparing with rapidfuzz (reuses _normalize_legal from fuzzy_resolver)
3. Resolving cross-type conflicts via TYPE_EQUIVALENCE_MAP
4. Merging: redirect relationships + DETACH DELETE (same as fuzzy_resolver)

Usage:
    from app.services.rag.core.kg_builder.cross_merger import cross_merge_entities

    result = await cross_merge_entities(tenant_id="t1")
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class CrossMergeResult:
    """Stats from a cross-extractor merge run."""
    candidates: int = 0
    merged: int = 0
    conflicts: int = 0
    errors: List[str] = field(default_factory=list)


# =============================================================================
# TYPE EQUIVALENCE MAP
# =============================================================================

TYPE_EQUIVALENCE_MAP: Dict[str, str] = {
    "norma": "lei",
    "diploma": "lei",
    "estatuto": "lei",
    "codigo": "lei",
    "regulamento": "lei",
    "dispositivo": "artigo",
    "paragrafo": "artigo",
    "inciso": "artigo",
    "alinea": "artigo",
    "corte": "tribunal",
    "vara": "tribunal",
    "juizo": "tribunal",
    "julgado": "decisao",
    "voto": "decisao",
    "acordao": "decisao",
    "precedente": "decisao",
    "enunciado": "sumula",
    # Factual equivalences
    "parte_autora": "pessoa",
    "parte_re": "pessoa",
    "reclamante": "pessoa",
    "reclamado": "pessoa",
    "requerente": "pessoa",
    "requerido": "pessoa",
    "impetrante": "pessoa",
    "impetrado": "pessoa",
    "empresa_re": "empresa",
    "empregador": "empresa",
    "empregadora": "empresa",
    "companhia": "empresa",
    "audiencia": "evento",
    "pericia": "evento",
    "citacao": "evento",
}


# =============================================================================
# HELPERS (reuse normalization from fuzzy_resolver)
# =============================================================================

def _get_canonical_type(entity_type: str) -> str:
    """Resolve entity type to canonical form via equivalence map."""
    key = (entity_type or "").strip().lower()
    return TYPE_EQUIVALENCE_MAP.get(key, key)


def _types_are_mergeable(type_a: str, type_b: str) -> bool:
    """Check if two entity types are mergeable (same or equivalent)."""
    canon_a = _get_canonical_type(type_a)
    canon_b = _get_canonical_type(type_b)
    if canon_a == canon_b:
        return True
    # Both empty = generic Entity, mergeable
    if not canon_a and not canon_b:
        return True
    return False


def _pick_keeper(entities: List[Dict[str, Any]]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Pick the entity to keep and the ones to merge into it.

    Priority:
    1. Predefined type (in whitelist) wins over discovered/unknown
    2. Shorter entity_id (regex-generated = more canonical)
    """
    from app.services.rag.core.graph_hybrid import HYBRID_LABELS_BY_ENTITY_TYPE

    known_types = set(HYBRID_LABELS_BY_ENTITY_TYPE.keys())

    def _sort_key(e: Dict[str, Any]) -> Tuple[int, int]:
        etype = (e.get("entity_type") or "").strip().lower()
        is_known = 0 if etype in known_types else 1
        eid_len = len(e.get("entity_id") or "")
        return (is_known, eid_len)

    sorted_entities = sorted(entities, key=_sort_key)
    return sorted_entities[0], sorted_entities[1:]


# =============================================================================
# MERGER
# =============================================================================

class CrossExtractorMerger:
    """Merges duplicate entities across extractors."""

    def __init__(
        self,
        driver: Any = None,
        database: str = "iudex",
        tenant_id: Optional[str] = None,
        *,
        threshold: float = 0.0,
        batch_limit: int = 200,
    ):
        self._driver = driver
        self._database = database
        self._tenant_id = tenant_id
        self._threshold = threshold or float(
            os.getenv("KG_BUILDER_CROSS_MERGER_THRESHOLD", "88.0")
        )
        self._batch_limit = batch_limit

    def _get_driver(self):
        if self._driver is None:
            from app.services.rag.core.neo4j_mvp import get_neo4j_mvp
            neo4j = get_neo4j_mvp()
            self._driver = neo4j.driver
            self._database = neo4j.config.database
        return self._driver

    def run(self) -> CrossMergeResult:
        """Run cross-extractor entity deduplication."""
        if not self._tenant_id:
            logger.warning("Cross-merger skipped: tenant_id is required")
            return CrossMergeResult(errors=["tenant_id_required"])

        try:
            from rapidfuzz import fuzz
        except ImportError:
            logger.warning("rapidfuzz not installed — skipping cross-merger")
            return CrossMergeResult()

        from app.services.rag.core.kg_builder.fuzzy_resolver import (
            _normalize_legal,
            _extract_numbers,
        )

        result = CrossMergeResult()
        driver = self._get_driver()

        # 1. Fetch candidate groups (same normalized, multiple entity_ids)
        candidates = self._fetch_candidates(driver)
        result.candidates = len(candidates)

        # 2. For each group, check mergeability and fuzzy score
        merge_pairs: List[Dict[str, Any]] = []
        for group in candidates:
            entities = group.get("entities", [])
            if len(entities) < 2:
                continue

            # Check type compatibility within the group
            mergeable_entities = self._filter_mergeable(entities)
            if len(mergeable_entities) < 2:
                result.conflicts += len(entities) - len(mergeable_entities)
                continue

            # Fuzzy-verify the names match
            verified = self._verify_fuzzy(
                mergeable_entities, fuzz, _normalize_legal, _extract_numbers,
            )
            if len(verified) < 2:
                continue

            keeper, to_merge = _pick_keeper(verified)
            for entity in to_merge:
                merge_pairs.append({
                    "keep": keeper["entity_id"],
                    "merge": entity["entity_id"],
                    "keep_name": keeper.get("name"),
                    "merge_name": entity.get("name"),
                })

        # 3. Execute merges
        if merge_pairs:
            merged = self._execute_merges(driver, merge_pairs)
            result.merged = merged

        logger.info(
            "Cross-merger: %d candidate groups, %d merged, %d conflicts",
            result.candidates, result.merged, result.conflicts,
        )
        return result

    def _fetch_candidates(self, driver: Any) -> List[Dict[str, Any]]:
        """Fetch entity groups that share the same normalized name."""
        query = """
            MATCH (e:Entity)<-[:MENTIONS]-(:Chunk)<-[:HAS_CHUNK]-(d_seed:Document {tenant_id: $tenant_id})
            WITH DISTINCT e
            MATCH (e)<-[:MENTIONS]-(:Chunk)<-[:HAS_CHUNK]-(d_all:Document)
            WITH e, collect(DISTINCT d_all.tenant_id) AS tenants
            WHERE size(tenants) = 1 AND tenants[0] = $tenant_id
              AND e.normalized IS NOT NULL AND e.name IS NOT NULL
            WITH e.normalized AS norm, collect({
                entity_id: e.entity_id,
                name: e.name,
                entity_type: e.entity_type
            }) AS entities
            WHERE size(entities) >= 2
            RETURN norm, entities
            ORDER BY size(entities) DESC
            LIMIT $limit
        """
        with driver.session(database=self._database) as session:
            records = session.run(
                query,
                limit=self._batch_limit,
                tenant_id=self._tenant_id,
            )
            return [dict(r) for r in records]

    def _filter_mergeable(
        self, entities: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Filter to only entities with compatible types."""
        if not entities:
            return []

        # Group by canonical type
        by_canon: Dict[str, List[Dict[str, Any]]] = {}
        for e in entities:
            canon = _get_canonical_type(e.get("entity_type") or "")
            by_canon.setdefault(canon, []).append(e)

        # Return the largest compatible group
        largest = max(by_canon.values(), key=len)
        return largest if len(largest) >= 2 else []

    def _verify_fuzzy(
        self,
        entities: List[Dict[str, Any]],
        fuzz_module: Any,
        normalize_fn: Any,
        extract_numbers_fn: Any,
    ) -> List[Dict[str, Any]]:
        """Verify entities in a group are actually similar via fuzzy matching."""
        if len(entities) < 2:
            return entities

        # Use the first entity as the anchor
        anchor = entities[0]
        anchor_norm = normalize_fn(anchor.get("name") or "")
        anchor_nums = extract_numbers_fn(anchor_norm)

        verified = [anchor]
        for e in entities[1:]:
            name = normalize_fn(e.get("name") or "")
            nums = extract_numbers_fn(name)

            # Fast reject: different numbers
            if anchor_nums and nums and anchor_nums != nums:
                continue

            score = fuzz_module.ratio(anchor_norm, name)

            # Numeric bonus
            if anchor_nums and nums and anchor_nums == nums:
                score = score * 0.4 + 100.0 * 0.6

            if score >= self._threshold:
                verified.append(e)

        return verified

    def _execute_merges(
        self, driver: Any, pairs: List[Dict[str, Any]]
    ) -> int:
        """Execute relationship redirection + delete (same pattern as fuzzy_resolver)."""
        merged = 0
        with driver.session(database=self._database) as session:
            for pair in pairs:
                try:
                    run_result = session.run("""
                        MATCH (keep:Entity {entity_id: $keep_id})
                        MATCH (merge:Entity {entity_id: $merge_id})
                        CALL {
                            WITH keep
                            MATCH (keep)<-[:MENTIONS]-(:Chunk)<-[:HAS_CHUNK]-(d:Document)
                            RETURN collect(DISTINCT d.tenant_id) AS keep_tenants
                        }
                        CALL {
                            WITH merge
                            MATCH (merge)<-[:MENTIONS]-(:Chunk)<-[:HAS_CHUNK]-(d:Document)
                            RETURN collect(DISTINCT d.tenant_id) AS merge_tenants
                        }
                        WITH keep, merge, keep_tenants, merge_tenants
                        WHERE size(keep_tenants) = 1 AND keep_tenants[0] = $tenant_id
                          AND size(merge_tenants) = 1 AND merge_tenants[0] = $tenant_id
                        CALL {
                            WITH keep, merge
                            MATCH (merge)-[r]->(other)
                            WHERE other <> keep
                            WITH keep, type(r) AS rel_type, properties(r) AS props, other
                            CALL apoc.create.relationship(keep, rel_type, props, other)
                            YIELD rel
                            RETURN count(rel) AS outgoing
                        }
                        CALL {
                            WITH keep, merge
                            MATCH (other)-[r]->(merge)
                            WHERE other <> keep
                            WITH keep, type(r) AS rel_type, properties(r) AS props, other
                            CALL apoc.create.relationship(other, rel_type, props, keep)
                            YIELD rel
                            RETURN count(rel) AS incoming
                        }
                        DETACH DELETE merge
                    """, keep_id=pair["keep"], merge_id=pair["merge"], tenant_id=self._tenant_id)
                    summary = run_result.consume()
                    if summary.counters.nodes_deleted > 0:
                        merged += 1
                except Exception as e:
                    try:
                        run_result = session.run("""
                            MATCH (merge:Entity {entity_id: $merge_id})<-[:MENTIONS]-(:Chunk)<-[:HAS_CHUNK]-(d:Document)
                            WITH merge, collect(DISTINCT d.tenant_id) AS tenants
                            WHERE size(tenants) = 1 AND tenants[0] = $tenant_id
                            DETACH DELETE merge
                        """, merge_id=pair["merge"], tenant_id=self._tenant_id)
                        summary = run_result.consume()
                        if summary.counters.nodes_deleted > 0:
                            merged += 1
                    except Exception:
                        logger.debug("Cross-merge failed for %s: %s", pair["merge"], e)

        return merged


# =============================================================================
# STANDALONE USAGE
# =============================================================================

async def cross_merge_entities(
    driver: Any = None,
    database: str = "iudex",
    tenant_id: Optional[str] = None,
    threshold: float = 0.0,
) -> CrossMergeResult:
    """Convenience async wrapper for cross-extractor merge."""
    import asyncio
    merger = CrossExtractorMerger(
        driver=driver,
        database=database,
        tenant_id=tenant_id,
        threshold=threshold,
    )
    return await asyncio.to_thread(merger.run)
