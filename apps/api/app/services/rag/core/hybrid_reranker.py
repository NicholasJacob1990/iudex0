"""
Hybrid Reranker: Automatic selection between Local and Cohere.

Strategy:
- Development: Local cross-encoder (free, no API key needed)
- Production: Cohere Rerank (better quality, scales without GPU)
- Fallback: If Cohere fails, falls back to local

Configuration via environment:
- RERANK_PROVIDER: "auto" | "local" | "cohere"
- COHERE_API_KEY: Required for Cohere
- ENVIRONMENT: "development" | "production" (used by "auto")

Both providers apply Portuguese legal domain boost for Brazilian legal content.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from app.services.rag.config import get_rag_config

logger = logging.getLogger("HybridReranker")


class RerankerProvider(str, Enum):
    """Available reranker providers."""

    AUTO = "auto"  # Auto-select based on environment
    LOCAL = "local"  # Local cross-encoder
    COHERE = "cohere"  # Cohere API


@dataclass
class HybridRerankerConfig:
    """Configuration for hybrid reranker."""

    # Provider selection
    provider: RerankerProvider = RerankerProvider.AUTO

    # Environment detection (for auto mode)
    environment: str = "development"

    # Fallback behavior
    fallback_to_local: bool = True  # If Cohere fails, use local

    # Top-k settings
    top_k: int = 10

    # Legal domain boost
    legal_domain_boost: float = 0.1

    @classmethod
    def from_env(cls) -> "HybridRerankerConfig":
        """Load config from environment."""
        rag_config = get_rag_config()

        provider_str = os.getenv("RERANK_PROVIDER", "auto").lower()
        try:
            provider = RerankerProvider(provider_str)
        except ValueError:
            logger.warning(f"Invalid RERANK_PROVIDER '{provider_str}', using 'auto'")
            provider = RerankerProvider.AUTO

        return cls(
            provider=provider,
            environment=os.getenv("ENVIRONMENT", "development").lower(),
            fallback_to_local=os.getenv("RERANK_FALLBACK_LOCAL", "true").lower() == "true",
            top_k=rag_config.rerank_top_k,
            legal_domain_boost=float(os.getenv("RERANK_LEGAL_BOOST", "0.1")),
        )


@dataclass
class HybridRerankerResult:
    """Result of hybrid reranking."""

    results: List[Dict[str, Any]]
    original_count: int
    reranked_count: int
    scores: List[float] = field(default_factory=list)
    provider_used: str = ""
    model_used: str = ""
    duration_ms: float = 0.0
    used_fallback: bool = False

    def __bool__(self) -> bool:
        return bool(self.results)

    def __len__(self) -> int:
        return len(self.results)

    def __iter__(self):
        return iter(self.results)


class HybridReranker:
    """
    Hybrid reranker with automatic provider selection.

    Automatically chooses between local cross-encoder and Cohere API
    based on configuration and availability.

    Usage:
        reranker = HybridReranker()
        result = reranker.rerank(query, results)
        print(f"Used: {result.provider_used}")
    """

    def __init__(self, config: Optional[HybridRerankerConfig] = None):
        self.config = config or HybridRerankerConfig.from_env()
        self._local_reranker = None
        self._cohere_reranker = None
        self._selected_provider: Optional[str] = None

    def _get_local_reranker(self):
        """Lazy load local cross-encoder reranker."""
        if self._local_reranker is None:
            from app.services.rag.core.reranker import CrossEncoderReranker

            self._local_reranker = CrossEncoderReranker.get_instance()
        return self._local_reranker

    def _get_cohere_reranker(self):
        """Lazy load Cohere reranker."""
        if self._cohere_reranker is None:
            from app.services.rag.core.cohere_reranker import get_cohere_reranker

            self._cohere_reranker = get_cohere_reranker()
        return self._cohere_reranker

    def _select_provider(self) -> str:
        """
        Select which provider to use based on config and availability.

        Returns:
            "local" or "cohere"
        """
        if self._selected_provider:
            return self._selected_provider

        provider = self.config.provider

        if provider == RerankerProvider.LOCAL:
            self._selected_provider = "local"

        elif provider == RerankerProvider.COHERE:
            # Check if Cohere is available
            cohere = self._get_cohere_reranker()
            if cohere.is_available:
                self._selected_provider = "cohere"
            elif self.config.fallback_to_local:
                logger.warning("Cohere unavailable, falling back to local")
                self._selected_provider = "local"
            else:
                self._selected_provider = "cohere"  # Will fail gracefully

        else:  # AUTO
            # Production: prefer Cohere if available
            # Development: prefer local (free, no API key)
            is_prod = self.config.environment in ("production", "prod", "prd")

            if is_prod:
                cohere = self._get_cohere_reranker()
                if cohere.is_available:
                    self._selected_provider = "cohere"
                    logger.info("Auto-selected Cohere reranker (production)")
                else:
                    self._selected_provider = "local"
                    logger.info("Auto-selected local reranker (Cohere unavailable)")
            else:
                self._selected_provider = "local"
                logger.info("Auto-selected local reranker (development)")

        return self._selected_provider

    def rerank(
        self,
        query: str,
        results: List[Dict[str, Any]],
        top_k: Optional[int] = None,
    ) -> HybridRerankerResult:
        """
        Rerank results using the selected provider.

        Args:
            query: Search query
            results: List of retrieval results
            top_k: Number of results to return

        Returns:
            HybridRerankerResult with provider info
        """
        start_time = time.perf_counter()
        original_count = len(results)
        top_k_out = top_k or self.config.top_k
        used_fallback = False

        # Handle edge cases
        if not results:
            return HybridRerankerResult(
                results=[],
                original_count=0,
                reranked_count=0,
                provider_used="none",
            )

        if not query or not query.strip():
            return HybridRerankerResult(
                results=results[:top_k_out],
                original_count=original_count,
                reranked_count=min(len(results), top_k_out),
                provider_used="passthrough",
            )

        # Select provider
        provider = self._select_provider()

        # Try primary provider
        if provider == "cohere":
            try:
                cohere = self._get_cohere_reranker()
                result = cohere.rerank(query, results, top_k_out)

                if result.results:
                    return HybridRerankerResult(
                        results=result.results,
                        original_count=original_count,
                        reranked_count=result.reranked_count,
                        scores=result.scores,
                        provider_used="cohere",
                        model_used=result.model_used,
                        duration_ms=result.duration_ms,
                        used_fallback=False,
                    )

                # Cohere returned empty, try fallback
                if self.config.fallback_to_local:
                    logger.warning("Cohere returned empty, falling back to local")
                    provider = "local"
                    used_fallback = True

            except Exception as e:
                logger.error(f"Cohere rerank failed: {e}")
                if self.config.fallback_to_local:
                    logger.info("Falling back to local reranker")
                    provider = "local"
                    used_fallback = True
                else:
                    raise

        # Local reranker
        if provider == "local":
            local = self._get_local_reranker()
            result = local.rerank(query, results, top_k_out)

            return HybridRerankerResult(
                results=result.results,
                original_count=original_count,
                reranked_count=result.reranked_count,
                scores=result.scores,
                provider_used="local",
                model_used=result.model_used,
                duration_ms=result.duration_ms,
                used_fallback=used_fallback,
            )

        # Shouldn't reach here
        return HybridRerankerResult(
            results=results[:top_k_out],
            original_count=original_count,
            reranked_count=min(len(results), top_k_out),
            provider_used="fallback",
            duration_ms=(time.perf_counter() - start_time) * 1000,
        )

    def get_status(self) -> Dict[str, Any]:
        """Get status of available providers."""
        status = {
            "configured_provider": self.config.provider.value,
            "environment": self.config.environment,
            "fallback_enabled": self.config.fallback_to_local,
            "selected_provider": self._selected_provider,
            "local_available": False,
            "cohere_available": False,
        }

        # Check local
        try:
            local = self._get_local_reranker()
            status["local_available"] = True
            status["local_model"] = local.config.model_name
        except Exception:
            pass

        # Check Cohere
        try:
            cohere = self._get_cohere_reranker()
            status["cohere_available"] = cohere.is_available
            if cohere.is_available:
                status["cohere_model"] = cohere.config.model
        except Exception:
            pass

        return status


# Singleton instance
_hybrid_reranker: Optional[HybridReranker] = None


def get_hybrid_reranker() -> HybridReranker:
    """Get singleton hybrid reranker instance."""
    global _hybrid_reranker
    if _hybrid_reranker is None:
        _hybrid_reranker = HybridReranker()
    return _hybrid_reranker


def rerank(
    query: str,
    results: List[Dict[str, Any]],
    top_k: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Convenience function for hybrid reranking.

    Uses the singleton instance for efficiency.

    Args:
        query: Search query
        results: List of retrieval results
        top_k: Number of results to return

    Returns:
        Reranked list of results
    """
    reranker = get_hybrid_reranker()
    result = reranker.rerank(query, results, top_k)
    return result.results


def rerank_with_metadata(
    query: str,
    results: List[Dict[str, Any]],
    top_k: Optional[int] = None,
) -> HybridRerankerResult:
    """
    Rerank with full metadata including provider info.

    Args:
        query: Search query
        results: List of retrieval results
        top_k: Number of results to return

    Returns:
        HybridRerankerResult with full metadata
    """
    reranker = get_hybrid_reranker()
    return reranker.rerank(query, results, top_k)


__all__ = [
    "RerankerProvider",
    "HybridRerankerConfig",
    "HybridRerankerResult",
    "HybridReranker",
    "get_hybrid_reranker",
    "rerank",
    "rerank_with_metadata",
]
