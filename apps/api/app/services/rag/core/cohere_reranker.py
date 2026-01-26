"""
Cohere Rerank integration with Portuguese legal domain boost.

Provides cloud-based reranking using Cohere's multilingual models,
with post-processing boost for Brazilian legal content.

Features:
- Cohere Rerank v3 multilingual support
- Portuguese legal domain scoring boost (applied post-rerank)
- Configurable model selection
- Batch processing with chunking for API limits
- Automatic retry with exponential backoff
- Hybrid mode: Cohere (prod) vs Local (dev)
"""

from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.services.rag.config import get_rag_config

logger = logging.getLogger("CohereReranker")

# Portuguese legal domain patterns (same as local reranker)
PORTUGUESE_LEGAL_PATTERNS = [
    r"\bart\.?\s*\d+",  # Art. 5, artigo 10
    r"\b§\s*\d+",  # Paragraphs
    r"\binciso\s+[IVXLCDM]+",  # Inciso I, II, etc.
    r"\blei\s+n?[º°\.]?\s*[\d\.]+",  # Lei 8.666, Lei n. 14.133, Lei nº 14.133
    r"\bsúmula\s+n?\.?\s*\d+",  # Sumula 331
    r"\bstf\b|\bstj\b|\btst\b|\btrf\b|\btjsp\b",  # Court names
    r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}",  # CNJ case number
    r"\bcódigo\s+(civil|penal|processo|tributário)",  # Brazilian codes
    r"\bconstitui[çc][ãa]o\s+federal",  # Constitution
    r"\bjurisprud[êe]ncia",  # Jurisprudence
    r"\bacórd[ãa]o",  # Court decision
    r"\brecurso\s+(especial|extraordin[áa]rio|ordin[áa]rio)",  # Appeal types
    r"\bhabeas\s+corpus",  # HC
    r"\bmandado\s+de\s+seguran[çc]a",  # MS
    r"\ba[çc][ãa]o\s+(civil|penal|popular|direta)",  # Action types
    r"\bcontrato\s+administrativo",  # Administrative contract
    r"\blicita[çc][ãa]o",  # Bidding process
    r"\bpreg[ãa]o\s+(eletr[ôo]nico|presencial)",  # Auction types
]

_LEGAL_PATTERN_COMPILED = re.compile(
    "|".join(PORTUGUESE_LEGAL_PATTERNS), re.IGNORECASE
)


@dataclass
class CohereRerankerConfig:
    """Configuration for Cohere Reranker."""

    # API settings
    api_key: str = ""
    model: str = "rerank-multilingual-v3.0"  # Best for PT-BR

    # Reranking settings
    top_k: int = 10
    max_candidates: int = 100  # Cohere limit: num_docs * max_chunks <= 10000

    # Retry settings
    max_retries: int = 3
    retry_delay: float = 1.0

    # Legal domain boost (applied post-Cohere)
    legal_domain_boost: float = 0.1

    # Timeout
    timeout_seconds: int = 30

    @classmethod
    def from_env(cls) -> "CohereRerankerConfig":
        """Load config from environment variables."""
        rag_config = get_rag_config()
        return cls(
            api_key=os.getenv("COHERE_API_KEY", ""),
            model=os.getenv("COHERE_RERANK_MODEL", "rerank-multilingual-v3.0"),
            top_k=rag_config.rerank_top_k,
            max_candidates=int(os.getenv("COHERE_RERANK_MAX_CANDIDATES", "100")),
            legal_domain_boost=float(os.getenv("COHERE_LEGAL_BOOST", "0.1")),
            timeout_seconds=int(os.getenv("COHERE_TIMEOUT", "30")),
        )


@dataclass
class CohereRerankerResult:
    """Result of Cohere reranking."""

    results: List[Dict[str, Any]]
    original_count: int
    reranked_count: int
    scores: List[float] = field(default_factory=list)
    model_used: str = ""
    duration_ms: float = 0.0
    api_calls: int = 0

    def __bool__(self) -> bool:
        return bool(self.results)

    def __len__(self) -> int:
        return len(self.results)

    def __iter__(self):
        return iter(self.results)


class CohereReranker:
    """
    Cohere-based reranker with Portuguese legal domain boost.

    The legal boost is applied AFTER Cohere returns scores, allowing
    domain-specific relevance adjustment on top of Cohere's semantic scoring.
    """

    def __init__(self, config: Optional[CohereRerankerConfig] = None):
        self.config = config or CohereRerankerConfig.from_env()
        self._client = None
        self._initialized = False

    def _ensure_client(self) -> bool:
        """Lazy initialize Cohere client."""
        if self._initialized:
            return self._client is not None

        self._initialized = True

        if not self.config.api_key:
            logger.warning("COHERE_API_KEY not set, Cohere reranker disabled")
            return False

        try:
            import cohere

            self._client = cohere.Client(
                api_key=self.config.api_key,
                timeout=self.config.timeout_seconds,
            )
            logger.info(f"Cohere client initialized with model: {self.config.model}")
            return True

        except ImportError:
            logger.error("cohere package not installed. Run: pip install cohere")
            return False
        except Exception as e:
            logger.error(f"Failed to initialize Cohere client: {e}")
            return False

    def _compute_legal_boost(self, text: str) -> float:
        """
        Compute Portuguese legal domain boost.

        Applied post-Cohere to boost Brazilian legal content relevance.
        """
        if not self.config.legal_domain_boost or self.config.legal_domain_boost <= 0:
            return 0.0

        if not text:
            return 0.0

        matches = _LEGAL_PATTERN_COMPILED.findall(text.lower())
        match_count = len(matches)

        if match_count == 0:
            return 0.0

        # Scale boost based on matches (cap at 5 for full boost)
        boost_factor = min(match_count / 5.0, 1.0)
        return self.config.legal_domain_boost * boost_factor

    def _prepare_documents(
        self, results: List[Dict[str, Any]]
    ) -> tuple[List[str], List[int]]:
        """
        Prepare documents for Cohere API.

        Returns:
            - List of document texts
            - List of original indices (for mapping back)
        """
        documents = []
        indices = []

        for idx, result in enumerate(results):
            text = (
                result.get("text")
                or result.get("content")
                or result.get("page_content")
                or ""
            )

            if text and text.strip():
                documents.append(text.strip())
                indices.append(idx)

        return documents, indices

    def rerank(
        self,
        query: str,
        results: List[Dict[str, Any]],
        top_k: Optional[int] = None,
    ) -> CohereRerankerResult:
        """
        Rerank results using Cohere API with legal domain boost.

        Args:
            query: Search query
            results: List of retrieval results with 'text' field
            top_k: Number of results to return

        Returns:
            CohereRerankerResult with reranked results
        """
        start_time = time.perf_counter()
        original_count = len(results)
        top_k_out = top_k or self.config.top_k

        # Handle edge cases
        if not results:
            return CohereRerankerResult(
                results=[],
                original_count=0,
                reranked_count=0,
                model_used=self.config.model,
            )

        if not query or not query.strip():
            return CohereRerankerResult(
                results=results[:top_k_out],
                original_count=original_count,
                reranked_count=min(len(results), top_k_out),
                model_used="passthrough",
            )

        # Check client
        if not self._ensure_client():
            logger.warning("Cohere unavailable, returning original order")
            return CohereRerankerResult(
                results=results[:top_k_out],
                original_count=original_count,
                reranked_count=min(len(results), top_k_out),
                model_used="fallback-no-client",
                duration_ms=(time.perf_counter() - start_time) * 1000,
            )

        # Limit candidates
        candidates = results[: self.config.max_candidates]

        # Prepare documents
        documents, indices = self._prepare_documents(candidates)

        if not documents:
            return CohereRerankerResult(
                results=[],
                original_count=original_count,
                reranked_count=0,
                model_used=self.config.model,
                duration_ms=(time.perf_counter() - start_time) * 1000,
            )

        # Call Cohere API with retry
        api_calls = 0
        cohere_results = None

        for attempt in range(self.config.max_retries):
            try:
                api_calls += 1
                cohere_results = self._client.rerank(
                    query=query,
                    documents=documents,
                    model=self.config.model,
                    top_n=min(top_k_out * 2, len(documents)),  # Get extra for filtering
                )
                break

            except Exception as e:
                logger.warning(f"Cohere API error (attempt {attempt + 1}): {e}")
                if attempt < self.config.max_retries - 1:
                    time.sleep(self.config.retry_delay * (attempt + 1))
                else:
                    logger.error("Cohere API failed after all retries")
                    return CohereRerankerResult(
                        results=candidates[:top_k_out],
                        original_count=original_count,
                        reranked_count=min(len(candidates), top_k_out),
                        model_used="fallback-api-error",
                        duration_ms=(time.perf_counter() - start_time) * 1000,
                        api_calls=api_calls,
                    )

        # Process Cohere results and apply legal boost
        scored_results = []

        for cohere_result in cohere_results.results:
            doc_idx = cohere_result.index
            original_idx = indices[doc_idx]
            result = candidates[original_idx].copy()

            # Cohere score (0-1 relevance score)
            cohere_score = cohere_result.relevance_score

            # Apply legal domain boost
            text = documents[doc_idx]
            legal_boost = self._compute_legal_boost(text)
            final_score = cohere_score + legal_boost

            result["rerank_score"] = final_score
            result["cohere_score"] = cohere_score
            result["legal_domain_boost"] = legal_boost
            result["original_score"] = result.get("final_score") or result.get("score", 0.0)

            scored_results.append(result)

        # Sort by final score (Cohere + legal boost)
        scored_results.sort(key=lambda x: x["rerank_score"], reverse=True)

        # Take top_k
        final_results = scored_results[:top_k_out]

        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.info(
            f"Cohere reranked {len(candidates)} -> {len(final_results)} in {duration_ms:.1f}ms"
        )

        return CohereRerankerResult(
            results=final_results,
            original_count=original_count,
            reranked_count=len(final_results),
            scores=[r["rerank_score"] for r in final_results],
            model_used=self.config.model,
            duration_ms=duration_ms,
            api_calls=api_calls,
        )

    @property
    def is_available(self) -> bool:
        """Check if Cohere is available."""
        return self._ensure_client()


# Singleton instance
_cohere_reranker: Optional[CohereReranker] = None


def get_cohere_reranker() -> CohereReranker:
    """Get singleton Cohere reranker instance."""
    global _cohere_reranker
    if _cohere_reranker is None:
        _cohere_reranker = CohereReranker()
    return _cohere_reranker


__all__ = [
    "CohereRerankerConfig",
    "CohereRerankerResult",
    "CohereReranker",
    "get_cohere_reranker",
]
