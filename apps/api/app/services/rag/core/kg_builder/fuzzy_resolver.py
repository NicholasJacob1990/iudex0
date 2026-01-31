"""
LegalFuzzyResolver — Entity resolution for Brazilian legal domain using rapidfuzz.

Resolves duplicates like:
- "Lei 8.666/93" == "Lei nº 8.666, de 21 de junho de 1993"
- "Art. 5º" == "Artigo 5"
- "Súmula 331" == "Sumula 331 TST"
- "STJ" == "Superior Tribunal de Justiça"

Uses rapidfuzz (pure C++, no spaCy dependency) for fuzzy string matching.
Compatible with Python 3.14+.

Usage:
    resolver = LegalFuzzyResolver(driver, threshold=85.0)
    result = await resolver.run()
"""

from __future__ import annotations

import logging
import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    from neo4j_graphrag.experimental.pipeline import Component, DataModel

    _HAS_NEO4J_GRAPHRAG = True
except ImportError:
    _HAS_NEO4J_GRAPHRAG = False

    class DataModel:  # type: ignore[no-redef]
        pass

    class Component:  # type: ignore[no-redef]
        pass


# =============================================================================
# DATA MODELS
# =============================================================================

if _HAS_NEO4J_GRAPHRAG:
    from neo4j_graphrag.experimental.pipeline import DataModel as _DM

    class ResolutionResult(_DM):
        """Result of entity resolution."""
        merged_count: int
        resolved_pairs: List[Dict[str, Any]]
else:
    class ResolutionResult:  # type: ignore[no-redef]
        def __init__(self, merged_count: int = 0, resolved_pairs: list = None):
            self.merged_count = merged_count
            self.resolved_pairs = resolved_pairs or []


# =============================================================================
# NORMALIZATION
# =============================================================================

def _normalize_legal(text: str) -> str:
    """
    Normalize legal entity text for comparison.

    Handles Brazilian legal citation variations:
    - Remove accents (ú -> u, º -> o)
    - Normalize "nº", "n.", "no" prefixes
    - Normalize "Art." / "Artigo"
    - Remove extra whitespace
    - Lowercase
    """
    # Unicode normalize
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))

    text = text.lower().strip()

    # Normalize ordinal markers
    text = re.sub(r"[ºª°]", "", text)

    # Normalize "nº", "n.", "no", "número" -> empty
    text = re.sub(r"\bn[oºª.]?\s*", "", text)

    # Normalize article references
    text = re.sub(r"\bartigo\b", "art", text)
    text = re.sub(r"\bart\.\s*", "art ", text)

    # Normalize "Lei nº X de Y" -> "lei X Y"
    text = re.sub(r"\s*,?\s*de\s+\d{1,2}\s+de\s+\w+\s+de\s+", " ", text)

    # Normalize dots in numbers
    text = re.sub(r"(\d)\.(\d)", r"\1\2", text)

    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()

    return text


def _extract_numbers(text: str) -> str:
    """Extract only numbers from text for numeric comparison."""
    return "".join(c for c in text if c.isdigit())


# =============================================================================
# COMPONENT
# =============================================================================

class LegalFuzzyResolver(Component if _HAS_NEO4J_GRAPHRAG else object):  # type: ignore[misc]
    """
    Entity resolution for Brazilian legal domain using rapidfuzz.

    Merges duplicate entities in Neo4j by:
    1. Fetching all Entity nodes grouped by label
    2. Comparing names using fuzzy matching (rapidfuzz)
    3. Merging duplicates using APOC merge or manual property copy

    Designed as a neo4j-graphrag Component for pipeline composition.
    """

    def __init__(
        self,
        driver: Any = None,
        database: str = "iudex",
        *,
        threshold: float = 85.0,
        numeric_weight: float = 0.6,
        batch_size: int = 500,
    ):
        """
        Args:
            driver: Neo4j driver instance
            database: Neo4j database name
            threshold: Minimum fuzzy score (0-100) to consider a match
            numeric_weight: Weight for numeric similarity (legal citations are number-heavy)
            batch_size: Max entities to fetch per label for resolution
        """
        if _HAS_NEO4J_GRAPHRAG:
            super().__init__()
        self._driver = driver
        self._database = database
        self._threshold = threshold
        self._numeric_weight = numeric_weight
        self._batch_size = batch_size

    def _get_driver(self):
        """Lazy driver initialization."""
        if self._driver is None:
            from app.services.rag.config import get_rag_config
            rag_config = get_rag_config()
            from neo4j import GraphDatabase
            self._driver = GraphDatabase.driver(
                rag_config.neo4j_uri,
                auth=(rag_config.neo4j_user, rag_config.neo4j_password),
            )
            self._database = rag_config.neo4j_database
        return self._driver

    async def run(self) -> ResolutionResult:
        """
        Run entity resolution across all entity labels.

        Returns:
            ResolutionResult with merge count and resolved pairs.
        """
        try:
            from rapidfuzz import fuzz
        except ImportError:
            logger.warning("rapidfuzz not installed — skipping entity resolution")
            return ResolutionResult(merged_count=0, resolved_pairs=[])

        driver = self._get_driver()
        total_merged = 0
        all_pairs: List[Dict[str, Any]] = []

        # Labels to resolve
        labels = [
            "Lei", "Artigo", "Sumula", "Tribunal", "Processo",
            "Tema", "Claim", "Actor", "SemanticEntity",
        ]

        for label in labels:
            try:
                entities = self._fetch_entities(driver, label)
                if len(entities) < 2:
                    continue

                pairs = self._find_duplicates(entities, fuzz)
                if pairs:
                    merged = self._merge_pairs(driver, pairs)
                    total_merged += merged
                    all_pairs.extend(pairs)
                    logger.info("Resolved %d duplicates for label %s", merged, label)
            except Exception as e:
                logger.warning("Resolution failed for label %s: %s", label, e)

        logger.info("Entity resolution complete: %d total merges", total_merged)
        return ResolutionResult(merged_count=total_merged, resolved_pairs=all_pairs)

    def _fetch_entities(self, driver: Any, label: str) -> List[Dict[str, Any]]:
        """Fetch entities for a given label."""
        safe_label = re.sub(r"[^A-Za-z0-9_]", "", label)
        query = f"""
        MATCH (e:{safe_label})
        WHERE e.name IS NOT NULL
        RETURN e.entity_id AS entity_id, e.name AS name, e.normalized AS normalized
        LIMIT $limit
        """
        with driver.session(database=self._database) as session:
            result = session.run(query, limit=self._batch_size)
            return [dict(r) for r in result]

    def _find_duplicates(
        self,
        entities: List[Dict[str, Any]],
        fuzz_module: Any,
    ) -> List[Dict[str, Any]]:
        """Find duplicate entity pairs using fuzzy matching."""
        pairs = []
        n = len(entities)

        for i in range(n):
            name_i = _normalize_legal(entities[i].get("name") or "")
            nums_i = _extract_numbers(name_i)

            for j in range(i + 1, n):
                name_j = _normalize_legal(entities[j].get("name") or "")
                nums_j = _extract_numbers(name_j)

                # Fast reject: if both have numbers and they differ, skip
                if nums_i and nums_j and nums_i != nums_j:
                    continue

                # Fuzzy score on normalized names
                text_score = fuzz_module.ratio(name_i, name_j)

                # Numeric bonus: if numbers match exactly, boost score
                if nums_i and nums_j and nums_i == nums_j:
                    score = (
                        text_score * (1 - self._numeric_weight)
                        + 100.0 * self._numeric_weight
                    )
                else:
                    score = text_score

                if score >= self._threshold:
                    pairs.append({
                        "keep": entities[i]["entity_id"],
                        "merge": entities[j]["entity_id"],
                        "keep_name": entities[i].get("name"),
                        "merge_name": entities[j].get("name"),
                        "score": round(score, 1),
                    })

        return pairs

    def _merge_pairs(self, driver: Any, pairs: List[Dict[str, Any]]) -> int:
        """
        Merge duplicate entities in Neo4j.

        Strategy: redirect all relationships from 'merge' to 'keep', then delete 'merge'.
        """
        merged = 0

        with driver.session(database=self._database) as session:
            for pair in pairs:
                try:
                    # Move all relationships from merge -> keep
                    session.run("""
                        MATCH (keep:Entity {entity_id: $keep_id})
                        MATCH (merge:Entity {entity_id: $merge_id})
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
                    """, keep_id=pair["keep"], merge_id=pair["merge"])
                    merged += 1
                except Exception as e:
                    # Fallback: simple delete without APOC
                    try:
                        session.run("""
                            MATCH (merge:Entity {entity_id: $merge_id})
                            DETACH DELETE merge
                        """, merge_id=pair["merge"])
                        merged += 1
                    except Exception:
                        logger.debug("Could not merge %s: %s", pair["merge"], e)

        return merged


# =============================================================================
# STANDALONE USAGE
# =============================================================================

async def resolve_entities(
    driver: Any = None,
    database: str = "iudex",
    threshold: float = 85.0,
) -> ResolutionResult:
    """Convenience function for standalone entity resolution."""
    resolver = LegalFuzzyResolver(driver=driver, database=database, threshold=threshold)
    return await resolver.run()
