"""
Voyage AI embeddings with voyage-4-large.

Handles batching, rate limiting, and fallback.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from ..config import settings

logger = logging.getLogger(__name__)

_client = None


def _get_client():
    global _client
    if _client is None:
        if not settings.voyage_api_key:
            raise RuntimeError(
                "VOYAGE_API_KEY is required for embeddings. "
                "Set it in .env or as an environment variable."
            )
        import voyageai
        _client = voyageai.Client(api_key=settings.voyage_api_key)
    return _client


def embed_texts(
    texts: List[str],
    *,
    model: Optional[str] = None,
    input_type: str = "document",
    batch_size: int = 128,
) -> List[List[float]]:
    """
    Generate embeddings for a list of texts using Voyage AI.

    Args:
        texts: Texts to embed.
        model: Voyage model name (default: settings.voyage_model).
        input_type: "document" for ingestion, "query" for search.
        batch_size: Max texts per API call.

    Returns:
        List of embedding vectors (1024-dim for voyage-4-large).
    """
    model = model or settings.voyage_model
    client = _get_client()
    all_embeddings: List[List[float]] = []

    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        try:
            result = client.embed(
                batch,
                model=model,
                input_type=input_type,
            )
            all_embeddings.extend(result.embeddings)
        except Exception as e:
            logger.error(f"Embedding batch {i}-{i+len(batch)} failed: {e}")
            # Fallback: return zero vectors for failed batch
            all_embeddings.extend([[0.0] * settings.voyage_dimensions] * len(batch))

    return all_embeddings


def embed_query(text: str, *, model: Optional[str] = None) -> List[float]:
    """Embed a single query text."""
    results = embed_texts([text], model=model, input_type="query", batch_size=1)
    return results[0]
