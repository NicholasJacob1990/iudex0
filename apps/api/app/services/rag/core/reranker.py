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
- Integration with RAG pipeline configuration
- Multilingual model support optimized for Portuguese legal text
- FP16 inference for improved speed
- Model caching singleton for resource efficiency
- Portuguese legal domain scoring boost
"""

from __future__ import annotations

import logging
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from app.services.rag.config import get_rag_config

logger = logging.getLogger("Reranker")

# Portuguese legal domain patterns for scoring boost
PORTUGUESE_LEGAL_PATTERNS = [
    r"\bart\.?\s*\d+",  # Art. 5, artigo 10
    r"\b§\s*\d+",  # Paragraphs
    r"\binciso\s+[IVXLCDM]+",  # Inciso I, II, etc.
    r"\blei\s+n?\.?\s*[\d\.]+",  # Lei 8.666, Lei n. 14.133
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

# Compiled patterns for efficiency
_LEGAL_PATTERN_COMPILED = re.compile(
    "|".join(PORTUGUESE_LEGAL_PATTERNS), re.IGNORECASE
)


@dataclass
class RerankerConfig:
    """Configuration for the reranker service."""

    # Model selection - multilingual model optimized for Portuguese legal text
    model_name: str = "cross-encoder/ms-marco-multilingual-MiniLM-L6-H384-v1"

    # Fallback model if multilingual model fails to load
    model_fallback: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    # Top-k settings
    top_k: int = 10

    # Max characters per chunk for reranking (avoid context overflow)
    max_chars: int = 1800

    # Batch size for cross-encoder inference
    batch_size: int = 32

    # Maximum candidates to consider for reranking
    max_candidates: int = 50

    # Minimum score threshold (optional filtering)
    min_score: Optional[float] = None

    # Device for inference (None = auto-detect)
    device: Optional[str] = None

    # FP16 inference for speed optimization
    use_fp16: bool = True

    # Cache model in singleton for efficiency
    cache_model: bool = True

    # Portuguese legal domain scoring boost factor (0 to disable)
    legal_domain_boost: float = 0.1

    @classmethod
    def from_rag_config(cls) -> "RerankerConfig":
        """Load configuration from RAG config."""
        rag_config = get_rag_config()
        return cls(
            model_name=rag_config.rerank_model,
            model_fallback=rag_config.rerank_model_fallback,
            top_k=rag_config.rerank_top_k,
            max_chars=rag_config.rerank_max_chars,
            max_candidates=rag_config.default_fetch_k,
            batch_size=rag_config.rerank_batch_size,
            use_fp16=rag_config.rerank_use_fp16,
            cache_model=rag_config.rerank_cache_model,
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

    def __bool__(self) -> bool:
        """Return True if there are results."""
        return bool(self.results)

    def __len__(self) -> int:
        """Return number of results."""
        return len(self.results)

    def __iter__(self):
        """Iterate over results."""
        return iter(self.results)


class CrossEncoderReranker:
    """
    Cross-encoder based reranker for improving retrieval precision.

    Uses sentence-transformers CrossEncoder models to score query-document
    pairs directly, providing more accurate relevance scores than embedding
    similarity alone.

    The model is loaded lazily on first use to avoid startup overhead.
    Thread-safe singleton pattern for efficient resource usage.

    Features:
    - Multilingual model support optimized for Portuguese legal text
    - Automatic fallback to English model if multilingual fails
    - FP16 inference for improved speed on compatible hardware
    - Model caching singleton for resource efficiency
    - Portuguese legal domain scoring boost
    """

    _instance: Optional["CrossEncoderReranker"] = None
    _lock = threading.Lock()
    _cached_models: Dict[str, Any] = {}  # Class-level model cache

    def __init__(self, config: Optional[RerankerConfig] = None):
        """
        Initialize the reranker.

        Args:
            config: Optional configuration. If not provided, loads from RAG config.
        """
        self.config = config or RerankerConfig.from_rag_config()
        self._model = None
        self._model_lock = threading.Lock()
        self._model_loaded = False
        self._device: Optional[str] = None
        self._active_model_name: Optional[str] = None
        self._using_fallback: bool = False

    @classmethod
    def get_instance(cls, config: Optional[RerankerConfig] = None) -> "CrossEncoderReranker":
        """
        Get singleton instance of the reranker.

        Args:
            config: Optional configuration (only used if creating new instance)

        Returns:
            Singleton CrossEncoderReranker instance
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(config)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton instance (useful for testing)."""
        with cls._lock:
            if cls._instance is not None:
                cls._instance._model = None
                cls._instance._model_loaded = False
            cls._instance = None

    @classmethod
    def clear_model_cache(cls) -> None:
        """Clear the cached models (useful for testing or memory management)."""
        with cls._lock:
            cls._cached_models.clear()

    def _detect_device(self) -> str:
        """Auto-detect the best available device."""
        if self.config.device:
            return self.config.device

        try:
            import torch

            if torch.cuda.is_available():
                return "cuda"
            elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                return "mps"
        except ImportError:
            pass

        return "cpu"

    def _should_use_fp16(self) -> bool:
        """Determine if FP16 inference should be used."""
        if not self.config.use_fp16:
            return False

        # FP16 works best on CUDA, can work on MPS, skip on CPU
        return self._device in ("cuda", "mps")

    def _load_model(self, model_name: str) -> Optional[Any]:
        """
        Load a cross-encoder model with FP16 support.

        Args:
            model_name: The HuggingFace model identifier

        Returns:
            Loaded CrossEncoder model or None if failed
        """
        try:
            from sentence_transformers import CrossEncoder

            # Check cache first if caching is enabled
            cache_key = f"{model_name}_{self._device}_{self.config.use_fp16}"
            if self.config.cache_model and cache_key in CrossEncoderReranker._cached_models:
                logger.info(f"Using cached cross-encoder model: {model_name}")
                return CrossEncoderReranker._cached_models[cache_key]

            logger.info(
                f"Loading cross-encoder model: {model_name} on {self._device} "
                f"(FP16: {self._should_use_fp16()})"
            )

            # Load model with optional FP16
            model_kwargs = {}
            if self._should_use_fp16():
                try:
                    import torch
                    model_kwargs["torch_dtype"] = torch.float16
                except ImportError:
                    pass

            model = CrossEncoder(
                model_name,
                max_length=512,
                device=self._device,
                **model_kwargs,
            )

            # Enable FP16 for inference if supported
            if self._should_use_fp16() and hasattr(model.model, "half"):
                try:
                    model.model.half()
                    logger.info("FP16 inference enabled for cross-encoder")
                except Exception as e:
                    logger.warning(f"Could not enable FP16: {e}")

            # Cache the model if caching is enabled
            if self.config.cache_model:
                CrossEncoderReranker._cached_models[cache_key] = model
                logger.info(f"Cached cross-encoder model: {model_name}")

            return model

        except Exception as e:
            logger.error(f"Failed to load cross-encoder model {model_name}: {e}")
            return None

    def _ensure_model_loaded(self) -> bool:
        """
        Lazy load the cross-encoder model with fallback support.

        Attempts to load the multilingual model first, falls back to
        English model if that fails.

        Returns:
            True if model is loaded and ready, False otherwise
        """
        if self._model_loaded:
            return True

        with self._model_lock:
            if self._model_loaded:
                return True

            try:
                from sentence_transformers import CrossEncoder  # noqa: F401
            except ImportError as e:
                logger.error(f"sentence-transformers not installed: {e}")
                return False

            self._device = self._detect_device()

            # Try primary model (multilingual)
            self._model = self._load_model(self.config.model_name)
            if self._model is not None:
                self._active_model_name = self.config.model_name
                self._using_fallback = False
                self._model_loaded = True
                logger.info(
                    f"Cross-encoder model loaded successfully: {self.config.model_name}"
                )
                return True

            # Try fallback model
            if self.config.model_fallback and self.config.model_fallback != self.config.model_name:
                logger.warning(
                    f"Primary model failed, trying fallback: {self.config.model_fallback}"
                )
                self._model = self._load_model(self.config.model_fallback)
                if self._model is not None:
                    self._active_model_name = self.config.model_fallback
                    self._using_fallback = True
                    self._model_loaded = True
                    logger.info(
                        f"Fallback cross-encoder model loaded: {self.config.model_fallback}"
                    )
                    return True

            logger.error("Failed to load any cross-encoder model")
            return False

    def _compute_legal_domain_boost(self, text: str) -> float:
        """
        Compute a scoring boost for Portuguese legal domain content.

        Args:
            text: The document text to analyze

        Returns:
            Boost value (0.0 to legal_domain_boost config value)
        """
        if not self.config.legal_domain_boost or self.config.legal_domain_boost <= 0:
            return 0.0

        if not text:
            return 0.0

        # Count legal pattern matches
        matches = _LEGAL_PATTERN_COMPILED.findall(text.lower())
        match_count = len(matches)

        if match_count == 0:
            return 0.0

        # Scale boost based on number of matches (cap at 5 matches for full boost)
        boost_factor = min(match_count / 5.0, 1.0)
        return self.config.legal_domain_boost * boost_factor

    def _truncate_text(self, text: str) -> str:
        """
        Truncate text to max chars, preserving word boundaries.

        Args:
            text: Input text to truncate

        Returns:
            Truncated text
        """
        if not text or len(text) <= self.config.max_chars:
            return text

        truncated = text[: self.config.max_chars]

        # Try to break at word boundary (within last 20% of text)
        last_space = truncated.rfind(" ")
        if last_space > self.config.max_chars * 0.8:
            truncated = truncated[:last_space]

        return truncated.strip()

    def _prepare_pairs(
        self,
        query: str,
        results: List[Dict[str, Any]],
    ) -> Tuple[List[Tuple[str, str]], List[int]]:
        """
        Prepare query-document pairs for cross-encoder.

        Args:
            query: The search query
            results: List of retrieval results with 'text' field

        Returns:
            Tuple of:
            - List of (query, document) pairs
            - List of indices mapping pairs back to original results
        """
        pairs = []
        indices = []

        for idx, result in enumerate(results):
            # Support multiple text field names
            text = (
                result.get("text")
                or result.get("content")
                or result.get("page_content")
                or ""
            )

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
            top_k: Override for number of results to return

        Returns:
            RerankerResult with reranked results and metadata
        """
        start_time = time.perf_counter()
        original_count = len(results)
        top_k_out = top_k or self.config.top_k

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

        # Limit input candidates
        candidates = results[: self.config.max_candidates]

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

        # Combine scores with original results and apply legal domain boost
        scored_results = []
        for idx, score in zip(indices, scores):
            result = candidates[idx].copy()
            base_score = float(score)

            # Apply Portuguese legal domain boost
            text = (
                result.get("text")
                or result.get("content")
                or result.get("page_content")
                or ""
            )
            legal_boost = self._compute_legal_domain_boost(text)
            final_score = base_score + legal_boost

            result["rerank_score"] = final_score
            result["rerank_score_raw"] = base_score
            result["legal_domain_boost"] = legal_boost
            result["original_score"] = (
                result.get("final_score") or result.get("score", 0.0)
            )
            scored_results.append(result)

        # Sort by rerank score (descending)
        scored_results.sort(key=lambda x: x["rerank_score"], reverse=True)

        # Apply minimum score filter if configured
        if self.config.min_score is not None:
            scored_results = [
                r for r in scored_results if r["rerank_score"] >= self.config.min_score
            ]

        # Take top_k results
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
            model_used=self._active_model_name or self.config.model_name,
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

        Args:
            queries: List of search queries
            results_list: List of result lists (one per query)
            top_k: Override for number of results to return per query

        Returns:
            List of RerankerResult objects
        """
        start_time = time.perf_counter()

        if len(queries) != len(results_list):
            raise ValueError("queries and results_list must have same length")

        if not queries:
            return []

        top_k_out = top_k or self.config.top_k

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
        all_pairs: List[Tuple[str, str]] = []
        pair_mapping: List[Tuple[int, int]] = []  # (query_idx, result_idx)

        for q_idx, (query, results) in enumerate(zip(queries, results_list)):
            candidates = results[: self.config.max_candidates]
            for r_idx, result in enumerate(candidates):
                text = (
                    result.get("text")
                    or result.get("content")
                    or result.get("page_content")
                    or ""
                )
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
        output: List[RerankerResult] = []
        for q_idx, (results, scores_list) in enumerate(zip(results_list, query_scores)):
            candidates = results[: self.config.max_candidates]
            scored = []

            for r_idx, score in scores_list:
                result = candidates[r_idx].copy()
                base_score = score

                # Apply Portuguese legal domain boost
                text = (
                    result.get("text")
                    or result.get("content")
                    or result.get("page_content")
                    or ""
                )
                legal_boost = self._compute_legal_domain_boost(text)
                final_score = base_score + legal_boost

                result["rerank_score"] = final_score
                result["rerank_score_raw"] = base_score
                result["legal_domain_boost"] = legal_boost
                result["original_score"] = (
                    result.get("final_score") or result.get("score", 0.0)
                )
                scored.append(result)

            scored.sort(key=lambda x: x["rerank_score"], reverse=True)

            if self.config.min_score is not None:
                scored = [
                    r for r in scored if r["rerank_score"] >= self.config.min_score
                ]

            final = scored[:top_k_out]

            output.append(
                RerankerResult(
                    results=final,
                    original_count=len(results),
                    reranked_count=len(final),
                    scores=[r["rerank_score"] for r in final],
                    model_used=self._active_model_name or self.config.model_name,
                )
            )

        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.info(f"Batch reranked {len(queries)} queries in {duration_ms:.1f}ms")

        return output

    @property
    def is_loaded(self) -> bool:
        """Check if the model is currently loaded."""
        return self._model_loaded

    @property
    def device(self) -> Optional[str]:
        """Get the device the model is running on."""
        return self._device

    @classmethod
    def preload(cls, config: Optional[RerankerConfig] = None) -> float:
        """
        Preload model and run warmup inference to eliminate cold start latency.

        This method should be called during application startup to ensure
        the model is ready for inference when the first request arrives.

        Args:
            config: Optional configuration for the reranker

        Returns:
            Load time in seconds
        """
        start = time.perf_counter()

        instance = cls.get_instance(config)

        # Force model loading
        if not instance._ensure_model_loaded():
            logger.warning("Failed to preload reranker model")
            return time.perf_counter() - start

        # Run warmup inference to compile/optimize model execution path
        try:
            warmup_query = "consulta jurídica sobre contrato administrativo"
            warmup_doc = (
                "Art. 37 da Constituição Federal estabelece os princípios "
                "da administração pública: legalidade, impessoalidade, moralidade, "
                "publicidade e eficiência."
            )

            # Warmup with single pair
            instance._model.predict(
                [(warmup_query, warmup_doc)],
                batch_size=1,
                show_progress_bar=False,
            )

            logger.info("Reranker warmup inference completed successfully")

        except Exception as e:
            logger.warning(f"Reranker warmup inference failed: {e}")

        load_time = time.perf_counter() - start
        logger.info(
            f"Reranker preloaded: model={instance._active_model_name}, "
            f"device={instance._device}, time={load_time:.2f}s"
        )

        return load_time

    @classmethod
    def is_preloaded(cls) -> bool:
        """
        Check if the reranker model is preloaded and ready.

        Returns:
            True if model is loaded and ready for inference
        """
        if cls._instance is None:
            return False
        return cls._instance._model_loaded


def rerank(
    query: str,
    results: List[Dict[str, Any]],
    top_k: Optional[int] = None,
    config: Optional[RerankerConfig] = None,
) -> List[Dict[str, Any]]:
    """
    Convenience function to rerank results.

    Uses the singleton reranker instance for efficiency.

    Args:
        query: The search query
        results: List of retrieval results
        top_k: Number of results to return
        config: Optional reranker configuration

    Returns:
        Reranked list of results

    Example:
        >>> results = [{"text": "doc1", "score": 0.8}, {"text": "doc2", "score": 0.9}]
        >>> reranked = rerank("my query", results, top_k=5)
    """
    if config:
        reranker = CrossEncoderReranker(config)
    else:
        reranker = CrossEncoderReranker.get_instance()

    result = reranker.rerank(query, results, top_k)
    return result.results


def rerank_with_metadata(
    query: str,
    results: List[Dict[str, Any]],
    top_k: Optional[int] = None,
    config: Optional[RerankerConfig] = None,
) -> RerankerResult:
    """
    Rerank results and return full metadata.

    Similar to rerank() but returns the complete RerankerResult
    including scores, timing, and other metadata.

    Args:
        query: The search query
        results: List of retrieval results
        top_k: Number of results to return
        config: Optional reranker configuration

    Returns:
        RerankerResult with full metadata
    """
    if config:
        reranker = CrossEncoderReranker(config)
    else:
        reranker = CrossEncoderReranker.get_instance()

    return reranker.rerank(query, results, top_k)


__all__ = [
    "RerankerConfig",
    "RerankerResult",
    "CrossEncoderReranker",
    "rerank",
    "rerank_with_metadata",
]
