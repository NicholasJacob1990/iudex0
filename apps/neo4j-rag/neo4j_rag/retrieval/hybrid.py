"""
Hybrid retrieval: Vector + Fulltext + Graph fusion via RRF.

Three signals:
1. Vector search (voyage-4-large HNSW index)
2. Fulltext search (BM25 with brazilian analyzer)
3. Graph traversal (beam search from mentioned entities)

Fused via Reciprocal Rank Fusion: score = Σ 1/(k + rank_i)
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

from neo4j import GraphDatabase

from ..config import settings
from ..models import SearchResult
from .traversal import beam_traverse

logger = logging.getLogger(__name__)


def _vector_search(
    session,
    query_embedding: List[float],
    top_k: int,
) -> List[Tuple[str, float, str]]:
    """Vector search using Neo4j HNSW index. Returns (chunk_id, score, text)."""
    try:
        results = session.run(
            "CALL db.index.vector.queryNodes('chunk_embedding', $top_k, $embedding) "
            "YIELD node, score "
            "RETURN node.id AS id, score, node.text AS text, "
            "       node.doc_id AS doc_id, node.hierarchy AS hierarchy",
            top_k=top_k,
            embedding=query_embedding,
        )
        return [
            (r["id"], float(r["score"]), r["text"])
            for r in results
        ]
    except Exception as e:
        if "chunk_embedding" in str(e).lower() or "index" in str(e).lower():
            logger.error(
                "Vector index 'chunk_embedding' not found. "
                "Run 'make setup' to create indexes first."
            )
        else:
            logger.error(f"Vector search failed: {e}")
        return []


def _fulltext_search(
    session,
    query: str,
    top_k: int,
) -> List[Tuple[str, float, str]]:
    """BM25 fulltext search. Returns (chunk_id, score, text)."""
    try:
        results = session.run(
            "CALL db.index.fulltext.queryNodes('chunk_fulltext', $query) "
            "YIELD node, score "
            "WHERE score > 0.1 "
            "RETURN node.id AS id, score, node.text AS text "
            "LIMIT $limit",
            query=query,
            limit=top_k,
        )
        return [
            (r["id"], float(r["score"]), r["text"])
            for r in results
        ]
    except Exception as e:
        if "chunk_fulltext" in str(e).lower() or "index" in str(e).lower():
            logger.error(
                "Fulltext index 'chunk_fulltext' not found. "
                "Run 'make setup' to create indexes first."
            )
        else:
            logger.error(f"Fulltext search failed: {e}")
        return []


def _rrf_fusion(
    *result_lists: List[Tuple[str, float, str]],
    k: int = 60,
) -> List[Tuple[str, float, str]]:
    """
    Reciprocal Rank Fusion: score = Σ 1/(k + rank_i) for each result list.

    Returns deduplicated results sorted by fused score descending.
    """
    scores: Dict[str, float] = {}
    texts: Dict[str, str] = {}

    for results in result_lists:
        for rank, (chunk_id, _score, text) in enumerate(results):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank + 1)
            texts[chunk_id] = text

    fused = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [(cid, score, texts[cid]) for cid, score in fused]


def hybrid_search(
    session,
    query: str,
    query_embedding: List[float],
    *,
    vector_top_k: Optional[int] = None,
    fulltext_top_k: Optional[int] = None,
    max_hops: Optional[int] = None,
    beam_width: Optional[int] = None,
    rrf_k: Optional[int] = None,
) -> List[SearchResult]:
    """
    Execute hybrid search: vector + fulltext + graph, fused with RRF.

    Returns SearchResult objects sorted by fused score.
    """
    vector_top_k = vector_top_k or settings.vector_top_k
    fulltext_top_k = fulltext_top_k or settings.fulltext_top_k
    max_hops = max_hops or settings.max_hops
    beam_width = beam_width or settings.beam_width
    rrf_k = rrf_k or settings.rrf_k

    # 1. Vector search
    vector_results = _vector_search(session, query_embedding, vector_top_k)
    logger.info(f"Vector search: {len(vector_results)} results")

    # 2. Fulltext search
    fulltext_results = _fulltext_search(session, query, fulltext_top_k)
    logger.info(f"Fulltext search: {len(fulltext_results)} results")

    # 3. Graph traversal from entities mentioned in top vector results
    graph_results = []
    if vector_results:
        top_chunk_ids = [cid for cid, _, _ in vector_results[:10]]
        graph_chunks = beam_traverse(
            session,
            start_chunk_ids=top_chunk_ids,
            query_embedding=query_embedding,
            max_hops=max_hops,
            beam_width=beam_width,
        )
        graph_results = [
            (cid, score, text)
            for cid, score, text in graph_chunks
        ]
        logger.info(f"Graph traversal: {len(graph_results)} results")

    # 4. RRF fusion
    fused = _rrf_fusion(vector_results, fulltext_results, graph_results, k=rrf_k)

    # 5. Convert to SearchResult
    return [
        SearchResult(
            chunk_id=cid,
            text=text,
            score=score,
            source="rrf",
        )
        for cid, score, text in fused
    ]
