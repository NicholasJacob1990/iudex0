"""
Reranking with Cohere Rerank 3.5 (supports Portuguese natively).

Falls back to score-based ordering if Cohere API is unavailable.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from ..config import settings
from ..models import SearchResult

logger = logging.getLogger(__name__)


def rerank(
    query: str,
    results: List[SearchResult],
    *,
    top_n: Optional[int] = None,
) -> List[SearchResult]:
    """
    Rerank search results using Cohere Rerank 3.5.

    Falls back to existing score ordering if Cohere is unavailable.
    """
    top_n = top_n or settings.rerank_top_n
    if not results:
        return []

    if len(results) <= top_n:
        return results

    api_key = settings.cohere_api_key
    if not api_key:
        logger.info("No Cohere API key, using score-based ordering")
        return sorted(results, key=lambda r: r.score, reverse=True)[:top_n]

    try:
        import cohere

        co = cohere.Client(api_key=api_key)
        reranked = co.rerank(
            model="rerank-v3.5",
            query=query,
            documents=[r.text for r in results],
            top_n=top_n,
        )

        reranked_results = []
        for item in reranked.results:
            original = results[item.index]
            reranked_results.append(SearchResult(
                chunk_id=original.chunk_id,
                text=original.text,
                score=item.relevance_score,
                source="reranked",
                doc_title=original.doc_title,
                hierarchy=original.hierarchy,
                entities=original.entities,
            ))

        return reranked_results

    except Exception as e:
        logger.warning(f"Cohere rerank failed, using score-based fallback: {e}")
        return sorted(results, key=lambda r: r.score, reverse=True)[:top_n]
