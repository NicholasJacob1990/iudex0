"""
LegalRegexExtractor — neo4j-graphrag Component wrapping LegalEntityExtractor.

Converts regex-extracted legal entities from LegalEntityExtractor into the
Neo4jGraph format expected by neo4j-graphrag pipelines. Runs deterministically
(no LLM call) and can be composed in parallel with LLMEntityRelationExtractor.

Usage in pipeline:
    pipe.add_component(LegalRegexExtractor(), "regex_extractor")
    pipe.connect("splitter", "regex_extractor", input_config={"chunks": "splitter.chunks"})
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    from neo4j_graphrag.experimental.pipeline import Component, DataModel

    _HAS_NEO4J_GRAPHRAG = True
except ImportError:
    _HAS_NEO4J_GRAPHRAG = False

    # Fallback stubs for import-time compatibility
    class DataModel:  # type: ignore[no-redef]
        pass

    class Component:  # type: ignore[no-redef]
        pass


# =============================================================================
# DATA MODELS
# =============================================================================

if _HAS_NEO4J_GRAPHRAG:
    from neo4j_graphrag.experimental.pipeline import DataModel as _DM

    class RegexExtractionResult(_DM):
        """Result of regex extraction: nodes and relationships."""
        nodes: List[Dict[str, Any]]
        relationships: List[Dict[str, Any]]
else:
    class RegexExtractionResult:  # type: ignore[no-redef]
        def __init__(self, nodes: list, relationships: list):
            self.nodes = nodes
            self.relationships = relationships


# =============================================================================
# COMPONENT
# =============================================================================

class LegalRegexExtractor(Component if _HAS_NEO4J_GRAPHRAG else object):  # type: ignore[misc]
    """
    neo4j-graphrag Component that extracts legal entities via regex.

    Wraps the existing LegalEntityExtractor from neo4j_mvp.py, converting
    its output to the Neo4jGraph format (nodes + relationships).

    This component runs deterministically (no LLM) and is designed to be
    composed in parallel with LLMEntityRelationExtractor in a pipeline.
    """

    def __init__(self, *, create_relationships: bool = True):
        """
        Args:
            create_relationships: If True, create RELATED_TO relationships
                between entities extracted from the same chunk.
        """
        if _HAS_NEO4J_GRAPHRAG:
            super().__init__()
        self._create_relationships = create_relationships

    async def run(self, chunks: List[Dict[str, Any]]) -> RegexExtractionResult:
        """
        Extract legal entities from chunks using regex patterns.

        Args:
            chunks: List of chunk dicts with at least 'text' (and optionally 'chunk_uid').

        Returns:
            RegexExtractionResult with nodes and relationships.
        """
        from app.services.rag.core.neo4j_mvp import LegalEntityExtractor

        all_nodes: List[Dict[str, Any]] = []
        all_rels: List[Dict[str, Any]] = []
        seen_ids: set = set()

        for chunk in chunks:
            text = chunk.get("text", "")
            if not text:
                continue

            chunk_uid = chunk.get("chunk_uid", "")
            entities = LegalEntityExtractor.extract(text)

            chunk_entity_ids = []
            for ent in entities:
                entity_id = ent["entity_id"]
                if entity_id not in seen_ids:
                    seen_ids.add(entity_id)

                    # Map entity_type to neo4j-graphrag label
                    label = _entity_type_to_label(ent["entity_type"])
                    all_nodes.append({
                        "id": entity_id,
                        "label": label,
                        "properties": {
                            "name": ent["name"],
                            "normalized": ent.get("normalized", ""),
                            "entity_type": ent["entity_type"],
                            **(ent.get("metadata") or {}),
                        },
                    })

                chunk_entity_ids.append(entity_id)

                # Chunk -> Entity relationship
                if chunk_uid:
                    all_rels.append({
                        "start": chunk_uid,
                        "end": entity_id,
                        "type": "MENTIONS",
                        "properties": {},
                    })

            # Co-occurrence relationships within same chunk
            if self._create_relationships and len(chunk_entity_ids) > 1:
                for i, eid1 in enumerate(chunk_entity_ids):
                    for eid2 in chunk_entity_ids[i + 1:]:
                        all_rels.append({
                            "start": eid1,
                            "end": eid2,
                            "type": "RELATED_TO",
                            "properties": {"source": "co_occurrence"},
                        })

        logger.info(
            "LegalRegexExtractor: %d nodes, %d relationships from %d chunks",
            len(all_nodes), len(all_rels), len(chunks),
        )

        return RegexExtractionResult(nodes=all_nodes, relationships=all_rels)


# =============================================================================
# HELPERS
# =============================================================================

_LABEL_MAP = {
    "lei": "Lei",
    "artigo": "Artigo",
    "sumula": "Sumula",
    "processo": "Processo",
    "tribunal": "Tribunal",
    "tema": "Tema",
    "parte": "Actor",
    "oab": "OAB",
}


def _entity_type_to_label(entity_type: str) -> str:
    """Map entity_type string to Neo4j label (PascalCase)."""
    return _LABEL_MAP.get(entity_type.lower(), "Entity")
