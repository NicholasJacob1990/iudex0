"""
ColBERT Late Interaction Reranker

Uses MaxSim scoring for efficient late interaction:
- Pre-compute document embeddings (can be cached)
- Query-time: compute query embeddings, MaxSim against docs
- O(1) per document after initial encoding

ColBERT achieves a better speed/quality trade-off than cross-encoders
by pre-computing document token embeddings and using efficient MaxSim
scoring at query time. This is especially beneficial for:
- Large result sets (50+ documents)
- Repeated queries against the same corpus
- Real-time applications requiring low latency

References:
- ColBERT: Efficient and Effective Passage Search via Contextualized
  Late Interaction over BERT (Khattab & Zaharia, 2020)
- ColBERTv2: Effective and Efficient Retrieval via Lightweight Late
  Interaction (Santhanam et al., 2022)
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger("ColBERTReranker")


@dataclass
class ColBERTConfig:
    """Configuration for ColBERT reranker."""

    # Model selection
    model_name: str = "colbert-ir/colbertv2.0"

    # Token length limits
    query_maxlen: int = 32
    doc_maxlen: int = 180

    # Embedding dimension (ColBERTv2 uses 128)
    dim: int = 128

    # FP16 for faster inference
    use_fp16: bool = True

    # Cache settings
    cache_embeddings: bool = True
    cache_max_size: int = 10000  # Max cached documents
    cache_ttl_seconds: int = 3600  # 1 hour TTL

    # Device selection: "cuda", "mps", "cpu", or "auto"
    device: str = "auto"

    # Batch processing
    batch_size: int = 32

    # Score normalization
    normalize_scores: bool = True

    # Minimum score threshold
    min_score: Optional[float] = None

    # Top-k output
    top_k: int = 10

    # Max candidates to process
    max_candidates: int = 100

    # Text field names to look for in results
    text_fields: List[str] = field(default_factory=lambda: [
        "text", "content", "page_content", "chunk_text"
    ])


@dataclass
class ColBERTResult:
    """Result of ColBERT reranking operation."""

    results: List[Dict[str, Any]]
    query_encoding_ms: float
    scoring_ms: float
    total_ms: float
    cache_hits: int = 0
    cache_misses: int = 0
    model_used: str = ""
    original_count: int = 0
    reranked_count: int = 0

    def __bool__(self) -> bool:
        """Return True if there are results."""
        return bool(self.results)

    def __len__(self) -> int:
        """Return number of results."""
        return len(self.results)

    def __iter__(self):
        """Iterate over results."""
        return iter(self.results)


class TTLCache:
    """
    Thread-safe LRU cache with TTL expiration for document embeddings.

    Uses OrderedDict for LRU behavior and stores (value, timestamp) tuples
    to support TTL expiration.
    """

    def __init__(self, max_size: int = 10000, ttl_seconds: int = 3600):
        self._cache: OrderedDict[str, Tuple[Any, float]] = OrderedDict()
        self._max_size = max_size
        self._ttl_seconds = ttl_seconds
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def _make_key(self, text: str) -> str:
        """Create a cache key from text content."""
        return hashlib.sha256(text.encode()).hexdigest()[:32]

    def get(self, text: str) -> Optional[Any]:
        """
        Get cached embedding for text.

        Args:
            text: Document text

        Returns:
            Cached embedding or None if not found/expired
        """
        key = self._make_key(text)

        with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None

            value, timestamp = self._cache[key]

            # Check TTL
            if time.time() - timestamp > self._ttl_seconds:
                del self._cache[key]
                self._misses += 1
                return None

            # Move to end (most recently used)
            self._cache.move_to_end(key)
            self._hits += 1
            return value

    def set(self, text: str, value: Any) -> None:
        """
        Cache embedding for text.

        Args:
            text: Document text
            value: Embedding tensor to cache
        """
        key = self._make_key(text)

        with self._lock:
            # Remove oldest if at capacity
            while len(self._cache) >= self._max_size:
                self._cache.popitem(last=False)

            self._cache[key] = (value, time.time())

    def clear(self) -> None:
        """Clear all cached entries."""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0

    @property
    def stats(self) -> Dict[str, int]:
        """Get cache statistics."""
        with self._lock:
            return {
                "size": len(self._cache),
                "max_size": self._max_size,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": self._hits / max(1, self._hits + self._misses),
            }


class ColBERTReranker:
    """
    ColBERT reranker with MaxSim scoring.

    Advantages over cross-encoder:
    - Pre-compute doc embeddings (cache)
    - Faster at query time
    - Better for large result sets

    The late interaction mechanism computes similarity as the sum of
    maximum similarities between each query token and all document tokens:

        score = sum(max(q_i . d_j for all j) for all i)

    This allows document embeddings to be pre-computed and cached,
    making query-time scoring O(Q*D) where Q is query length and D is
    doc length, rather than O(N) forward passes through a cross-encoder.
    """

    _instance: Optional["ColBERTReranker"] = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls, config: Optional[ColBERTConfig] = None) -> "ColBERTReranker":
        """
        Singleton pattern for model caching.

        Args:
            config: Optional configuration (only used on first call)

        Returns:
            Singleton ColBERTReranker instance
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
                cls._instance._embedding_cache.clear()
                cls._instance._model = None
                cls._instance._tokenizer = None
                cls._instance._model_loaded = False
            cls._instance = None

    def __init__(self, config: Optional[ColBERTConfig] = None):
        """
        Initialize the ColBERT reranker.

        Args:
            config: Configuration options. Uses defaults if not provided.
        """
        self.config = config or ColBERTConfig()

        # Model state (lazy loaded)
        self._model = None
        self._tokenizer = None
        self._model_loaded = False
        self._model_lock = threading.Lock()
        self._device: Optional[str] = None

        # Embedding cache
        self._embedding_cache = TTLCache(
            max_size=self.config.cache_max_size,
            ttl_seconds=self.config.cache_ttl_seconds,
        )

        # Import torch lazily to avoid startup overhead
        self._torch = None

    def _get_torch(self):
        """Lazy import torch."""
        if self._torch is None:
            import torch
            self._torch = torch
        return self._torch

    def _detect_device(self) -> str:
        """
        Auto-detect the best available device.

        Priority: CUDA > MPS (Mac) > CPU

        Returns:
            Device string for PyTorch
        """
        if self.config.device != "auto":
            return self.config.device

        torch = self._get_torch()

        if torch.cuda.is_available():
            logger.info("CUDA available, using GPU")
            return "cuda"
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            logger.info("MPS available, using Apple Silicon GPU")
            return "mps"
        else:
            logger.info("No GPU available, using CPU")
            return "cpu"

    def _ensure_model_loaded(self) -> bool:
        """
        Lazy load the ColBERT model and tokenizer.

        Returns:
            True if model loaded successfully, False otherwise
        """
        if self._model_loaded:
            return True

        with self._model_lock:
            if self._model_loaded:
                return True

            try:
                torch = self._get_torch()
                from transformers import AutoModel, AutoTokenizer

                self._device = self._detect_device()
                logger.info(
                    f"Loading ColBERT model: {self.config.model_name} on {self._device}"
                )

                # Load tokenizer
                self._tokenizer = AutoTokenizer.from_pretrained(
                    self.config.model_name,
                    trust_remote_code=True,
                )

                # Load model
                self._model = AutoModel.from_pretrained(
                    self.config.model_name,
                    trust_remote_code=True,
                )

                # Move to device
                self._model = self._model.to(self._device)

                # Set evaluation mode
                self._model.eval()

                # Enable FP16 if configured and on appropriate device
                if self.config.use_fp16 and self._device in ("cuda", "mps"):
                    self._model = self._model.half()
                    logger.info("FP16 inference enabled")

                self._model_loaded = True
                logger.info("ColBERT model loaded successfully")
                return True

            except ImportError as e:
                logger.error(f"Required packages not installed: {e}")
                logger.error("Install with: pip install transformers torch")
                return False
            except Exception as e:
                logger.error(f"Failed to load ColBERT model: {e}")
                return False

    def _truncate_text(self, text: str, max_tokens: int) -> str:
        """
        Truncate text to approximately max_tokens.

        Uses a simple character-based heuristic (4 chars per token)
        for efficiency. Actual tokenization happens later.

        Args:
            text: Input text
            max_tokens: Maximum token count

        Returns:
            Truncated text
        """
        if not text:
            return ""

        # Approximate: 4 characters per token on average
        max_chars = max_tokens * 4

        if len(text) <= max_chars:
            return text

        truncated = text[:max_chars]

        # Try to break at word boundary
        last_space = truncated.rfind(" ")
        if last_space > max_chars * 0.8:
            truncated = truncated[:last_space]

        return truncated.strip()

    def _get_text_from_result(self, result: Dict[str, Any]) -> str:
        """
        Extract text content from a result dictionary.

        Args:
            result: Result dictionary

        Returns:
            Text content or empty string
        """
        for field in self.config.text_fields:
            text = result.get(field)
            if text and isinstance(text, str) and text.strip():
                return text.strip()
        return ""

    def encode_query(self, query: str) -> "torch.Tensor":
        """
        Encode query to token embeddings.

        ColBERT uses special [Q] marker tokens and masks padding.

        Args:
            query: Query string

        Returns:
            Query token embeddings [1, seq_len, dim]
        """
        if not self._ensure_model_loaded():
            raise RuntimeError("ColBERT model not loaded")

        torch = self._get_torch()

        # Truncate query
        query = self._truncate_text(query, self.config.query_maxlen)

        # Tokenize with special handling for ColBERT
        # Add [Q] marker for query (ColBERT convention)
        query_text = f"[Q] {query}"

        inputs = self._tokenizer(
            query_text,
            max_length=self.config.query_maxlen,
            padding="max_length",
            truncation=True,
            return_tensors="pt",
        )

        # Move to device
        inputs = {k: v.to(self._device) for k, v in inputs.items()}

        # Get embeddings
        with torch.no_grad():
            outputs = self._model(**inputs)

            # Get last hidden state
            if hasattr(outputs, "last_hidden_state"):
                embeddings = outputs.last_hidden_state
            else:
                embeddings = outputs[0]

            # Normalize embeddings (ColBERT uses L2 normalization)
            embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=-1)

            # Project to lower dimension if needed
            if embeddings.shape[-1] != self.config.dim:
                # Linear projection (simplified - full ColBERT has learned projection)
                embeddings = embeddings[..., :self.config.dim]
                embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=-1)

        return embeddings

    def encode_documents(
        self,
        texts: List[str],
        use_cache: bool = True,
    ) -> List["torch.Tensor"]:
        """
        Encode documents to token embeddings (cacheable).

        Args:
            texts: List of document texts
            use_cache: Whether to use embedding cache

        Returns:
            List of document token embeddings [seq_len, dim]
        """
        if not self._ensure_model_loaded():
            raise RuntimeError("ColBERT model not loaded")

        torch = self._get_torch()

        embeddings = []
        texts_to_encode = []
        text_indices = []

        # Check cache first
        for i, text in enumerate(texts):
            if use_cache and self.config.cache_embeddings:
                cached = self._embedding_cache.get(text)
                if cached is not None:
                    embeddings.append((i, cached))
                    continue

            texts_to_encode.append(text)
            text_indices.append(i)

        # Encode uncached texts in batches
        if texts_to_encode:
            for batch_start in range(0, len(texts_to_encode), self.config.batch_size):
                batch_end = min(batch_start + self.config.batch_size, len(texts_to_encode))
                batch_texts = texts_to_encode[batch_start:batch_end]
                batch_indices = text_indices[batch_start:batch_end]

                # Truncate and add [D] marker for documents
                processed_texts = [
                    f"[D] {self._truncate_text(t, self.config.doc_maxlen)}"
                    for t in batch_texts
                ]

                inputs = self._tokenizer(
                    processed_texts,
                    max_length=self.config.doc_maxlen,
                    padding="max_length",
                    truncation=True,
                    return_tensors="pt",
                )

                # Move to device
                inputs = {k: v.to(self._device) for k, v in inputs.items()}

                with torch.no_grad():
                    outputs = self._model(**inputs)

                    if hasattr(outputs, "last_hidden_state"):
                        batch_embeddings = outputs.last_hidden_state
                    else:
                        batch_embeddings = outputs[0]

                    # Normalize
                    batch_embeddings = torch.nn.functional.normalize(
                        batch_embeddings, p=2, dim=-1
                    )

                    # Project to lower dimension if needed
                    if batch_embeddings.shape[-1] != self.config.dim:
                        batch_embeddings = batch_embeddings[..., :self.config.dim]
                        batch_embeddings = torch.nn.functional.normalize(
                            batch_embeddings, p=2, dim=-1
                        )

                # Store results and cache
                for j, (idx, text) in enumerate(zip(batch_indices, batch_texts)):
                    doc_emb = batch_embeddings[j].cpu()
                    embeddings.append((idx, doc_emb))

                    if use_cache and self.config.cache_embeddings:
                        self._embedding_cache.set(text, doc_emb)

        # Sort by original index and extract embeddings
        embeddings.sort(key=lambda x: x[0])
        return [emb for _, emb in embeddings]

    def maxsim_score(
        self,
        query_emb: "torch.Tensor",
        doc_emb: "torch.Tensor",
    ) -> float:
        """
        Compute MaxSim score between query and document.

        MaxSim: for each query token, find max similarity to any doc token.
        Score = sum of max similarities.

        This is the core late interaction mechanism of ColBERT.

        Args:
            query_emb: Query embeddings [1, q_len, dim] or [q_len, dim]
            doc_emb: Document embeddings [d_len, dim]

        Returns:
            MaxSim score (float)
        """
        torch = self._get_torch()

        # Ensure correct shapes
        if query_emb.dim() == 3:
            query_emb = query_emb.squeeze(0)  # [q_len, dim]

        if doc_emb.dim() == 3:
            doc_emb = doc_emb.squeeze(0)  # [d_len, dim]

        # Move to same device
        doc_emb = doc_emb.to(query_emb.device)

        # Compute similarity matrix: [q_len, d_len]
        # Each entry (i,j) = cosine similarity between query token i and doc token j
        similarity_matrix = torch.matmul(query_emb, doc_emb.transpose(0, 1))

        # MaxSim: for each query token, take max similarity across all doc tokens
        max_similarities = similarity_matrix.max(dim=1).values  # [q_len]

        # Sum of max similarities
        score = max_similarities.sum().item()

        # Optionally normalize by query length
        if self.config.normalize_scores:
            score = score / query_emb.shape[0]

        return float(score)

    def maxsim_scores_batch(
        self,
        query_emb: "torch.Tensor",
        doc_embs: List["torch.Tensor"],
    ) -> List[float]:
        """
        Compute MaxSim scores for multiple documents efficiently.

        Args:
            query_emb: Query embeddings [1, q_len, dim]
            doc_embs: List of document embeddings [d_len, dim]

        Returns:
            List of MaxSim scores
        """
        return [self.maxsim_score(query_emb, doc_emb) for doc_emb in doc_embs]

    def rerank(
        self,
        query: str,
        results: List[Dict[str, Any]],
        top_k: Optional[int] = None,
    ) -> ColBERTResult:
        """
        Rerank results using ColBERT MaxSim.

        Args:
            query: Search query
            results: List of retrieval results with text content
            top_k: Number of results to return (default: config.top_k)

        Returns:
            ColBERTResult with reranked results and timing info
        """
        start_time = time.perf_counter()
        original_count = len(results)
        top_k_out = top_k or self.config.top_k

        # Handle edge cases
        if not results:
            return ColBERTResult(
                results=[],
                query_encoding_ms=0.0,
                scoring_ms=0.0,
                total_ms=0.0,
                model_used=self.config.model_name,
                original_count=0,
                reranked_count=0,
            )

        if not query or not query.strip():
            return ColBERTResult(
                results=results[:top_k_out],
                query_encoding_ms=0.0,
                scoring_ms=0.0,
                total_ms=0.0,
                model_used="passthrough",
                original_count=original_count,
                reranked_count=min(len(results), top_k_out),
            )

        # Check model availability
        if not self._ensure_model_loaded():
            logger.warning("ColBERT model unavailable, returning original order")
            return ColBERTResult(
                results=results[:top_k_out],
                query_encoding_ms=0.0,
                scoring_ms=0.0,
                total_ms=(time.perf_counter() - start_time) * 1000,
                model_used="fallback",
                original_count=original_count,
                reranked_count=min(len(results), top_k_out),
            )

        # Limit candidates
        candidates = results[:self.config.max_candidates]

        # Extract texts
        texts = []
        valid_indices = []
        for i, result in enumerate(candidates):
            text = self._get_text_from_result(result)
            if text:
                texts.append(text)
                valid_indices.append(i)

        if not texts:
            return ColBERTResult(
                results=[],
                query_encoding_ms=0.0,
                scoring_ms=0.0,
                total_ms=(time.perf_counter() - start_time) * 1000,
                model_used=self.config.model_name,
                original_count=original_count,
                reranked_count=0,
            )

        # Encode query
        query_start = time.perf_counter()
        try:
            query_emb = self.encode_query(query)
        except Exception as e:
            logger.error(f"Query encoding failed: {e}")
            return ColBERTResult(
                results=candidates[:top_k_out],
                query_encoding_ms=0.0,
                scoring_ms=0.0,
                total_ms=(time.perf_counter() - start_time) * 1000,
                model_used="error-fallback",
                original_count=original_count,
                reranked_count=min(len(candidates), top_k_out),
            )
        query_encoding_ms = (time.perf_counter() - query_start) * 1000

        # Get cache stats before encoding
        cache_stats_before = self._embedding_cache.stats.copy()

        # Encode documents
        scoring_start = time.perf_counter()
        try:
            doc_embs = self.encode_documents(texts, use_cache=self.config.cache_embeddings)
        except Exception as e:
            logger.error(f"Document encoding failed: {e}")
            return ColBERTResult(
                results=candidates[:top_k_out],
                query_encoding_ms=query_encoding_ms,
                scoring_ms=0.0,
                total_ms=(time.perf_counter() - start_time) * 1000,
                model_used="error-fallback",
                original_count=original_count,
                reranked_count=min(len(candidates), top_k_out),
            )

        # Compute MaxSim scores
        scores = self.maxsim_scores_batch(query_emb, doc_embs)
        scoring_ms = (time.perf_counter() - scoring_start) * 1000

        # Get cache stats after encoding
        cache_stats_after = self._embedding_cache.stats
        cache_hits = cache_stats_after["hits"] - cache_stats_before["hits"]
        cache_misses = cache_stats_after["misses"] - cache_stats_before["misses"]

        # Combine scores with results
        scored_results = []
        for idx, score in zip(valid_indices, scores):
            result = candidates[idx].copy()
            result["colbert_score"] = score
            result["rerank_score"] = score  # Compatibility with CrossEncoderReranker
            result["original_score"] = (
                result.get("final_score") or result.get("score", 0.0)
            )
            scored_results.append(result)

        # Sort by ColBERT score (descending)
        scored_results.sort(key=lambda x: x["colbert_score"], reverse=True)

        # Apply minimum score filter if configured
        if self.config.min_score is not None:
            scored_results = [
                r for r in scored_results
                if r["colbert_score"] >= self.config.min_score
            ]

        # Take top_k
        final_results = scored_results[:top_k_out]

        total_ms = (time.perf_counter() - start_time) * 1000

        logger.info(
            f"ColBERT reranked {len(candidates)} -> {len(final_results)} results "
            f"in {total_ms:.1f}ms (query: {query_encoding_ms:.1f}ms, "
            f"scoring: {scoring_ms:.1f}ms, cache hits: {cache_hits})"
        )

        return ColBERTResult(
            results=final_results,
            query_encoding_ms=query_encoding_ms,
            scoring_ms=scoring_ms,
            total_ms=total_ms,
            cache_hits=cache_hits,
            cache_misses=cache_misses,
            model_used=self.config.model_name,
            original_count=original_count,
            reranked_count=len(final_results),
        )

    def rerank_with_cache(
        self,
        query: str,
        results: List[Dict[str, Any]],
        doc_embeddings_cache: Dict[str, "torch.Tensor"],
        top_k: Optional[int] = None,
    ) -> ColBERTResult:
        """
        Rerank using pre-computed document embeddings.

        This is useful when you have a fixed corpus and want to
        pre-compute all embeddings once, then reuse them for
        multiple queries.

        Args:
            query: Search query
            results: List of retrieval results
            doc_embeddings_cache: Dict mapping text -> embeddings
            top_k: Number of results to return

        Returns:
            ColBERTResult with reranked results
        """
        start_time = time.perf_counter()
        original_count = len(results)
        top_k_out = top_k or self.config.top_k

        if not results or not query or not query.strip():
            return ColBERTResult(
                results=results[:top_k_out] if results else [],
                query_encoding_ms=0.0,
                scoring_ms=0.0,
                total_ms=0.0,
                model_used="passthrough" if results else self.config.model_name,
                original_count=original_count,
                reranked_count=min(len(results), top_k_out) if results else 0,
            )

        if not self._ensure_model_loaded():
            return ColBERTResult(
                results=results[:top_k_out],
                query_encoding_ms=0.0,
                scoring_ms=0.0,
                total_ms=(time.perf_counter() - start_time) * 1000,
                model_used="fallback",
                original_count=original_count,
                reranked_count=min(len(results), top_k_out),
            )

        candidates = results[:self.config.max_candidates]

        # Encode query
        query_start = time.perf_counter()
        try:
            query_emb = self.encode_query(query)
        except Exception as e:
            logger.error(f"Query encoding failed: {e}")
            return ColBERTResult(
                results=candidates[:top_k_out],
                query_encoding_ms=0.0,
                scoring_ms=0.0,
                total_ms=(time.perf_counter() - start_time) * 1000,
                model_used="error-fallback",
                original_count=original_count,
                reranked_count=min(len(candidates), top_k_out),
            )
        query_encoding_ms = (time.perf_counter() - query_start) * 1000

        # Score using pre-computed embeddings
        scoring_start = time.perf_counter()
        scored_results = []
        cache_hits = 0
        cache_misses = 0

        for result in candidates:
            text = self._get_text_from_result(result)
            if not text:
                continue

            # Look up in provided cache
            doc_emb = doc_embeddings_cache.get(text)

            if doc_emb is not None:
                cache_hits += 1
                score = self.maxsim_score(query_emb, doc_emb)
            else:
                cache_misses += 1
                # Compute on the fly
                try:
                    doc_embs = self.encode_documents([text], use_cache=True)
                    score = self.maxsim_score(query_emb, doc_embs[0])
                except Exception:
                    continue

            result_copy = result.copy()
            result_copy["colbert_score"] = score
            result_copy["rerank_score"] = score
            result_copy["original_score"] = (
                result.get("final_score") or result.get("score", 0.0)
            )
            scored_results.append(result_copy)

        scoring_ms = (time.perf_counter() - scoring_start) * 1000

        # Sort and filter
        scored_results.sort(key=lambda x: x["colbert_score"], reverse=True)

        if self.config.min_score is not None:
            scored_results = [
                r for r in scored_results
                if r["colbert_score"] >= self.config.min_score
            ]

        final_results = scored_results[:top_k_out]
        total_ms = (time.perf_counter() - start_time) * 1000

        return ColBERTResult(
            results=final_results,
            query_encoding_ms=query_encoding_ms,
            scoring_ms=scoring_ms,
            total_ms=total_ms,
            cache_hits=cache_hits,
            cache_misses=cache_misses,
            model_used=self.config.model_name,
            original_count=original_count,
            reranked_count=len(final_results),
        )

    def precompute_embeddings(
        self,
        texts: List[str],
    ) -> Dict[str, "torch.Tensor"]:
        """
        Pre-compute embeddings for a corpus.

        Use this to build an embedding cache for a fixed corpus,
        then pass to rerank_with_cache() for efficient query-time
        reranking.

        Args:
            texts: List of document texts

        Returns:
            Dict mapping text -> embedding tensor
        """
        if not self._ensure_model_loaded():
            raise RuntimeError("ColBERT model not loaded")

        # Encode all documents (will use internal cache too)
        embeddings = self.encode_documents(texts, use_cache=True)

        return {text: emb for text, emb in zip(texts, embeddings)}

    @property
    def is_loaded(self) -> bool:
        """Check if model is loaded."""
        return self._model_loaded

    @property
    def device(self) -> Optional[str]:
        """Get the device the model is running on."""
        return self._device

    @property
    def cache_stats(self) -> Dict[str, Any]:
        """Get embedding cache statistics."""
        return self._embedding_cache.stats


def get_colbert_reranker(config: Optional[ColBERTConfig] = None) -> ColBERTReranker:
    """
    Get singleton ColBERT reranker instance.

    Args:
        config: Optional configuration (only used on first call)

    Returns:
        ColBERTReranker instance
    """
    return ColBERTReranker.get_instance(config)


def colbert_rerank(
    query: str,
    results: List[Dict[str, Any]],
    top_k: Optional[int] = None,
    config: Optional[ColBERTConfig] = None,
) -> List[Dict[str, Any]]:
    """
    Convenience function to rerank results with ColBERT.

    Uses singleton reranker for efficiency.

    Args:
        query: Search query
        results: List of retrieval results
        top_k: Number of results to return
        config: Optional configuration

    Returns:
        Reranked list of results

    Example:
        >>> results = [{"text": "doc1", "score": 0.8}, {"text": "doc2", "score": 0.9}]
        >>> reranked = colbert_rerank("my query", results, top_k=5)
    """
    if config:
        reranker = ColBERTReranker(config)
    else:
        reranker = get_colbert_reranker()

    result = reranker.rerank(query, results, top_k)
    return result.results


def colbert_rerank_with_metadata(
    query: str,
    results: List[Dict[str, Any]],
    top_k: Optional[int] = None,
    config: Optional[ColBERTConfig] = None,
) -> ColBERTResult:
    """
    Rerank results with ColBERT and return full metadata.

    Similar to colbert_rerank() but returns the complete ColBERTResult
    including timing, cache stats, and other metadata.

    Args:
        query: Search query
        results: List of retrieval results
        top_k: Number of results to return
        config: Optional configuration

    Returns:
        ColBERTResult with full metadata
    """
    if config:
        reranker = ColBERTReranker(config)
    else:
        reranker = get_colbert_reranker()

    return reranker.rerank(query, results, top_k)


__all__ = [
    "ColBERTConfig",
    "ColBERTResult",
    "ColBERTReranker",
    "TTLCache",
    "get_colbert_reranker",
    "colbert_rerank",
    "colbert_rerank_with_metadata",
]
