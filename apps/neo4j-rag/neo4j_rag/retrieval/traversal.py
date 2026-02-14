"""
Graph beam search traversal.

Starting from entities mentioned in initial chunks, traverse the graph
up to N hops using beam search (keep top-K by embedding score per hop).

Uses a whitelist/blacklist of relation types to control noise.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# Relations to traverse (prioritized)
RELATION_WHITELIST: Set[str] = {
    # Priority: maximum (always traverse)
    "INTERPRETA", "FIXA_TESE", "FUNDAMENTA", "APLICA_SUMULA",
    "JULGA_TEMA", "APLICA", "PROFERIDA_POR",
    # Priority: high
    "REMETE_A", "PARTE_DE", "PERTENCE_A", "SUBDISPOSITIVO_DE",
    "CITA", "CONFIRMA", "SUPERA", "DISTINGUE",
    # Priority: medium
    "REGULAMENTA", "REVOGA", "ALTERA",
    "CITA_DOUTRINA", "FUNDAMENTA_SE_EM",
    "MENCIONA", "DEFENDE", "INCIDE_SOBRE",
}

# Relations to NEVER traverse
RELATION_BLACKLIST: Set[str] = {
    "CO_OCORRE", "TRATA_DE",
    "PART_OF", "NEXT",
    "FROM_CHUNK", "FROM_DOCUMENT", "NEXT_CHUNK",
}

# Build the Cypher type filter string once
_WHITELIST_TYPES = "|".join(sorted(RELATION_WHITELIST))


def _dot_product(a: List[float], b: List[float]) -> float:
    """Compute dot product between two vectors."""
    return sum(x * y for x, y in zip(a, b))


def beam_traverse(
    session,
    *,
    start_chunk_ids: List[str],
    query_embedding: List[float],
    max_hops: int = 5,
    beam_width: int = 5,
) -> List[Tuple[str, float, str]]:
    """
    Beam search graph traversal starting from chunks.

    1. Get entities mentioned by start chunks
    2. At each hop, expand via whitelisted relations
    3. Score expanded nodes by embedding similarity to query
    4. Keep top-K (beam_width) at each hop
    5. Collect chunks that mention discovered entities

    Returns: list of (chunk_id, score, text) from graph-discovered chunks.
    """
    if not start_chunk_ids:
        return []

    # Step 1: Get entities mentioned by start chunks
    entity_rows = list(session.run(
        "MATCH (c:Chunk)-[:MENTIONS]->(e:Entity) "
        "WHERE c.id IN $chunk_ids "
        "RETURN DISTINCT e.id AS eid, e.name AS name",
        chunk_ids=start_chunk_ids,
    ))

    if not entity_rows:
        return []

    current_entity_ids = [r["eid"] for r in entity_rows]
    visited_entities: Set[str] = set(current_entity_ids)
    all_discovered_entities: Set[str] = set(current_entity_ids)

    # Step 2-4: Beam search
    for hop in range(max_hops):
        if not current_entity_ids:
            break

        # Expand one hop via whitelisted relations
        neighbors = list(session.run(
            f"MATCH (e:Entity)-[r:{_WHITELIST_TYPES}]-(neighbor:Entity) "
            "WHERE e.id IN $eids AND NOT neighbor.id IN $visited "
            "RETURN DISTINCT neighbor.id AS nid, neighbor.name AS name, "
            "       type(r) AS rel_type",
            eids=current_entity_ids,
            visited=list(visited_entities),
        ))

        if not neighbors:
            break

        # Score neighbors: try to get their chunk embeddings for scoring
        neighbor_ids = list({r["nid"] for r in neighbors})

        # Get chunks that mention these neighbors and use their embeddings for scoring
        chunk_scores = list(session.run(
            "MATCH (c:Chunk)-[:MENTIONS]->(e:Entity) "
            "WHERE e.id IN $eids AND c.embedding IS NOT NULL "
            "RETURN e.id AS eid, c.embedding AS emb "
            "LIMIT 50",
            eids=neighbor_ids[:50],
        ))

        # Score each neighbor by best chunk embedding similarity
        scores: Dict[str, float] = {}
        for row in chunk_scores:
            eid = row["eid"]
            emb = row["emb"]
            if emb and query_embedding:
                score = _dot_product(query_embedding, emb)
                scores[eid] = max(scores.get(eid, -1.0), score)

        # For neighbors without chunk embeddings, assign a small default score
        for nid in neighbor_ids:
            if nid not in scores:
                scores[nid] = 0.01

        # Beam: keep top-K by score
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        beam = [eid for eid, _ in ranked[:beam_width]]

        visited_entities.update(beam)
        all_discovered_entities.update(beam)
        current_entity_ids = beam

        logger.debug(
            f"Hop {hop + 1}: expanded to {len(neighbors)} neighbors, "
            f"kept {len(beam)} in beam"
        )

    # Step 5: Get chunks that mention any discovered entity (excluding start chunks)
    if not all_discovered_entities:
        return []

    result_rows = list(session.run(
        "MATCH (c:Chunk)-[:MENTIONS]->(e:Entity) "
        "WHERE e.id IN $eids AND NOT c.id IN $start_ids "
        "  AND c.embedding IS NOT NULL "
        "RETURN DISTINCT c.id AS cid, c.text AS text, c.embedding AS emb",
        eids=list(all_discovered_entities),
        start_ids=start_chunk_ids,
    ))

    # Score results by embedding similarity
    results = []
    for row in result_rows:
        emb = row["emb"]
        score = _dot_product(query_embedding, emb) if emb else 0.0
        results.append((row["cid"], score, row["text"]))

    results.sort(key=lambda x: x[1], reverse=True)
    return results[:50]  # Cap at 50 graph results
