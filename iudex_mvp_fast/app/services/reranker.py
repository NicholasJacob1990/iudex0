"""
Cross-encoder reranking service for RAG pipelines.

Provides semantic reranking using cross-encoder models to improve
retrieval precision by scoring query-document pairs directly.

Features:
- Lazy loading of cross-encoder model (loads on first use)
- Configurable top_k for input/output control
- Max chars per chunk to avoid context overflow
- Batch processing for efficiency
- Metadata preservation through transformations
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("Reranker")


@dataclass
class RerankerConfig:
    """Configuration for the reranker service."""

    # Model selection
    model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    # Top-k settings: fetch top_k_in candidates, return top_k_out after reranking
    top_k_in: int = 20
    top_k_out: int = 10

    # Max characters per chunk for reranking (avoid context overflow)
    max_chars_per_chunk: int = 1500

    # Batch size for cross-encoder inference
    batch_size: int = 32

    # Minimum score threshold (optional filtering)
    min_score: Optional[float] = None

    # Device for inference (None = auto-detect)
    device: Optional[str] = None

    @classmethod
    def from_env(cls) -> "RerankerConfig":
        """Load configuration from environment variables."""
        return cls(
            model_name=os.getenv("RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2"),
            top_k_in=int(os.getenv("RERANKER_TOP_K_IN", "20")),
            top_k_out=int(os.getenv("RERANKER_TOP_K_OUT", "10")),
            max_chars_per_chunk=int(os.getenv("RERANKER_MAX_CHARS", "1500")),
            batch_size=int(os.getenv("RERANKER_BATCH_SIZE", "32")),
            min_score=float(os.getenv("RERANKER_MIN_SCORE")) if os.getenv("RERANKER_MIN_SCORE") else None,
            device=os.getenv("RERANKER_DEVICE"),
        )


@dataclass
class RerankerResult:
    """Result of a reranking operation."""

    results: List[Dict[str, Any]]
    original_count: int
    reranked_count: int
    scores: List[float] = field(default_factory=list)
    model_used: str = ""
    duration_ms: float = 0.0


class CrossEncoderReranker:
    """
    Cross-encoder based reranker for improving retrieval precision.

    Uses sentence-transformers CrossEncoder models to score query-document
    pairs directly, providing more accurate relevance scores than embedding
    similarity alone.

    The model is loaded lazily on first use to avoid startup overhead.
    """

    _instance: Optional["CrossEncoderReranker"] = None
    _lock = threading.Lock()

    def __init__(self, config: Optional[RerankerConfig] = None):
        self.config = config or RerankerConfig.from_env()
        self._model = None
        self._model_lock = threading.Lock()
        self._model_loaded = False

    @classmethod
    def get_instance(cls, config: Optional[RerankerConfig] = None) -> "CrossEncoderReranker":
        """Get singleton instance of the reranker."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(config)
        return cls._instance

    def _ensure_model_loaded(self) -> bool:
        """Lazy load the cross-encoder model."""
        if self._model_loaded:
            return True

        with self._model_lock:
            if self._model_loaded:
                return True

            try:
                from sentence_transformers import CrossEncoder

                device = self.config.device
                if device is None:
                    # Auto-detect device
                    try:
                        import torch
                        if torch.cuda.is_available():
                            device = "cuda"
                        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                            device = "mps"
                        else:
                            device = "cpu"
                    except ImportError:
                        device = "cpu"

                logger.info(f"Loading cross-encoder model: {self.config.model_name} on {device}")
                self._model = CrossEncoder(
                    self.config.model_name,
                    max_length=512,
                    device=device,
                )
                self._model_loaded = True
                logger.info("Cross-encoder model loaded successfully")
                return True

            except ImportError as e:
                logger.error(f"sentence-transformers not installed: {e}")
                return False
            except Exception as e:
                logger.error(f"Failed to load cross-encoder model: {e}")
                return False

    def _truncate_text(self, text: str) -> str:
        """Truncate text to max chars, preserving word boundaries."""
        if not text or len(text) <= self.config.max_chars_per_chunk:
            return text

        truncated = text[:self.config.max_chars_per_chunk]
        # Try to break at word boundary
        last_space = truncated.rfind(" ")
        if last_space > self.config.max_chars_per_chunk * 0.8:
            truncated = truncated[:last_space]

        return truncated.strip()

    def _prepare_pairs(
        self,
        query: str,
        results: List[Dict[str, Any]],
    ) -> Tuple[List[Tuple[str, str]], List[int]]:
        """
        Prepare query-document pairs for cross-encoder.

        Returns:
            - List of (query, document) pairs
            - List of indices mapping pairs back to original results
        """
        pairs = []
        indices = []

        for idx, result in enumerate(results):
            text = result.get("text", "")
            if not text or not text.strip():
                continue

            truncated = self._truncate_text(text.strip())
            pairs.append((query, truncated))
            indices.append(idx)

        return pairs, indices

    def rerank(
        self,
        query: str,
        results: List[Dict[str, Any]],
        top_k: Optional[int] = None,
    ) -> RerankerResult:
        """
        Rerank retrieval results using cross-encoder scoring.

        Args:
            query: The search query
            results: List of retrieval results with 'text' field
            top_k: Override for top_k_out (number of results to return)

        Returns:
            RerankerResult with reranked results and metadata
        """
        import time
        start_time = time.perf_counter()

        original_count = len(results)
        top_k_out = top_k or self.config.top_k_out

        # Handle edge cases
        if not results:
            return RerankerResult(
                results=[],
                original_count=0,
                reranked_count=0,
                model_used=self.config.model_name,
                duration_ms=0.0,
            )

        if not query or not query.strip():
            # No query, return original order
            return RerankerResult(
                results=results[:top_k_out],
                original_count=original_count,
                reranked_count=min(len(results), top_k_out),
                model_used="passthrough",
                duration_ms=0.0,
            )

        # Limit input to top_k_in
        candidates = results[:self.config.top_k_in]

        # Try to load and use cross-encoder
        if not self._ensure_model_loaded():
            # Fallback: return original order if model unavailable
            logger.warning("Cross-encoder unavailable, returning original order")
            return RerankerResult(
                results=candidates[:top_k_out],
                original_count=original_count,
                reranked_count=min(len(candidates), top_k_out),
                model_used="fallback",
                duration_ms=(time.perf_counter() - start_time) * 1000,
            )

        # Prepare pairs
        pairs, indices = self._prepare_pairs(query, candidates)

        if not pairs:
            return RerankerResult(
                results=[],
                original_count=original_count,
                reranked_count=0,
                model_used=self.config.model_name,
                duration_ms=(time.perf_counter() - start_time) * 1000,
            )

        # Score pairs in batches
        try:
            scores = self._model.predict(
                pairs,
                batch_size=self.config.batch_size,
                show_progress_bar=False,
            )
        except Exception as e:
            logger.error(f"Cross-encoder prediction failed: {e}")
            return RerankerResult(
                results=candidates[:top_k_out],
                original_count=original_count,
                reranked_count=min(len(candidates), top_k_out),
                model_used="error-fallback",
                duration_ms=(time.perf_counter() - start_time) * 1000,
            )

        # Combine scores with original results
        scored_results = []
        for idx, score in zip(indices, scores):
            result = candidates[idx].copy()
            result["rerank_score"] = float(score)
            result["original_score"] = result.get("final_score") or result.get("score", 0.0)
            scored_results.append(result)

        # Sort by rerank score
        scored_results.sort(key=lambda x: x["rerank_score"], reverse=True)

        # Apply minimum score filter if configured
        if self.config.min_score is not None:
            scored_results = [r for r in scored_results if r["rerank_score"] >= self.config.min_score]

        # Take top_k_out
        final_results = scored_results[:top_k_out]

        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.info(
            f"Reranked {len(candidates)} -> {len(final_results)} results in {duration_ms:.1f}ms"
        )

        return RerankerResult(
            results=final_results,
            original_count=original_count,
            reranked_count=len(final_results),
            scores=[r["rerank_score"] for r in final_results],
            model_used=self.config.model_name,
            duration_ms=duration_ms,
        )

    def rerank_batch(
        self,
        queries: List[str],
        results_list: List[List[Dict[str, Any]]],
        top_k: Optional[int] = None,
    ) -> List[RerankerResult]:
        """
        Rerank multiple query-results pairs efficiently.

        Batches all pairs together for better GPU utilization.
        """
        import time
        start_time = time.perf_counter()

        if len(queries) != len(results_list):
            raise ValueError("queries and results_list must have same length")

        if not queries:
            return []

        top_k_out = top_k or self.config.top_k_out

        if not self._ensure_model_loaded():
            # Fallback for all queries
            return [
                RerankerResult(
                    results=results[:top_k_out],
                    original_count=len(results),
                    reranked_count=min(len(results), top_k_out),
                    model_used="fallback",
                )
                for results in results_list
            ]

        # Prepare all pairs with tracking
        all_pairs = []
        pair_mapping = []  # (query_idx, result_idx)

        for q_idx, (query, results) in enumerate(zip(queries, results_list)):
            candidates = results[:self.config.top_k_in]
            for r_idx, result in enumerate(candidates):
                text = result.get("text", "")
                if text and text.strip():
                    truncated = self._truncate_text(text.strip())
                    all_pairs.append((query, truncated))
                    pair_mapping.append((q_idx, r_idx))

        if not all_pairs:
            return [
                RerankerResult(
                    results=[],
                    original_count=len(results),
                    reranked_count=0,
                    model_used=self.config.model_name,
                )
                for results in results_list
            ]

        # Score all pairs at once
        try:
            all_scores = self._model.predict(
                all_pairs,
                batch_size=self.config.batch_size,
                show_progress_bar=False,
            )
        except Exception as e:
            logger.error(f"Batch cross-encoder prediction failed: {e}")
            return [
                RerankerResult(
                    results=results[:top_k_out],
                    original_count=len(results),
                    reranked_count=min(len(results), top_k_out),
                    model_used="error-fallback",
                )
                for results in results_list
            ]

        # Distribute scores back to queries
        query_scores: List[List[Tuple[int, float]]] = [[] for _ in queries]
        for (q_idx, r_idx), score in zip(pair_mapping, all_scores):
            query_scores[q_idx].append((r_idx, float(score)))

        # Build results for each query
        output = []
        for q_idx, (results, scores_list) in enumerate(zip(results_list, query_scores)):
            candidates = results[:self.config.top_k_in]
            scored = []

            for r_idx, score in scores_list:
                result = candidates[r_idx].copy()
                result["rerank_score"] = score
                result["original_score"] = result.get("final_score") or result.get("score", 0.0)
                scored.append(result)

            scored.sort(key=lambda x: x["rerank_score"], reverse=True)

            if self.config.min_score is not None:
                scored = [r for r in scored if r["rerank_score"] >= self.config.min_score]

            final = scored[:top_k_out]

            output.append(RerankerResult(
                results=final,
                original_count=len(results),
                reranked_count=len(final),
                scores=[r["rerank_score"] for r in final],
                model_used=self.config.model_name,
            ))

        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.info(f"Batch reranked {len(queries)} queries in {duration_ms:.1f}ms")

        return output


# Convenience function for simple usage
def rerank(
    query: str,
    results: List[Dict[str, Any]],
    top_k: Optional[int] = None,
    config: Optional[RerankerConfig] = None,
) -> List[Dict[str, Any]]:
    """
    Convenience function to rerank results.

    Args:
        query: The search query
        results: List of retrieval results
        top_k: Number of results to return
        config: Optional reranker configuration

    Returns:
        Reranked list of results
    """
    if config:
        reranker = CrossEncoderReranker(config)
    else:
        reranker = CrossEncoderReranker.get_instance()

    result = reranker.rerank(query, results, top_k)
    return result.results
