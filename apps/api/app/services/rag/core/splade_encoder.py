"""
SPLADE Sparse Encoder

Generates sparse lexical representations using SPLADE model.
Combines benefits of neural retrieval with lexical matching.

SPLADE (Sparse Lexical and Expansion Model) produces term-level importance
weights using masked language model heads. This gives:
- Better semantic matching than BM25 (learned representations)
- Better interpretability than dense embeddings (explicit term weights)
- Native support for term expansion (model learns synonyms)
- Efficient storage and retrieval using inverted indices

Reference: https://arxiv.org/abs/2109.10086
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger("rag.splade")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class SPLADEConfig:
    """Configuration for SPLADE encoder."""

    # Model settings
    model_name: str = "naver/splade-cocondenser-ensembledistil"
    max_length: int = 256
    use_fp16: bool = True

    # Sparsity settings
    top_k_tokens: int = 100  # Keep only top-k non-zero dimensions
    min_weight: float = 0.01  # Minimum weight to include in sparse vector
    apply_log1p: bool = True  # Apply log(1+x) to RELU activations

    # Batch processing
    batch_size: int = 32

    # Cache settings
    cache_enabled: bool = True
    cache_ttl_seconds: int = 3600
    cache_max_items: int = 10000

    # Device settings
    device: str = "auto"  # "auto", "cpu", "cuda", "mps"


@dataclass
class SPLADEResult:
    """Result from SPLADE encoding."""

    sparse_vector: Dict[str, float]  # term -> weight
    num_active_terms: int
    encoding_time_ms: float
    from_cache: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "sparse_vector": self.sparse_vector,
            "num_active_terms": self.num_active_terms,
            "encoding_time_ms": round(self.encoding_time_ms, 2),
            "from_cache": self.from_cache,
        }


# ---------------------------------------------------------------------------
# Cache Implementation
# ---------------------------------------------------------------------------


class SPLADECache:
    """Thread-safe TTL cache for SPLADE encodings."""

    def __init__(self, max_items: int = 10000, ttl_seconds: int = 3600):
        self._cache: Dict[str, Tuple[float, Dict[str, float]]] = {}
        self._lock = threading.RLock()
        self._max_items = max_items
        self._ttl = ttl_seconds
        self._hits = 0
        self._misses = 0

    def _compute_key(self, text: str) -> str:
        """Compute cache key from text."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]

    def get(self, text: str) -> Optional[Dict[str, float]]:
        """Get cached sparse vector if present and not expired."""
        key = self._compute_key(text)
        now = time.time()

        with self._lock:
            entry = self._cache.get(key)
            if entry and entry[0] > now:
                self._hits += 1
                return entry[1].copy()  # Return copy to prevent modification
            elif entry:
                # Expired
                self._cache.pop(key, None)
            self._misses += 1
            return None

    def set(self, text: str, sparse_vector: Dict[str, float]) -> None:
        """Store sparse vector in cache."""
        key = self._compute_key(text)
        now = time.time()

        with self._lock:
            # Evict if at capacity
            if len(self._cache) >= self._max_items:
                self._evict(now)

            self._cache[key] = (now + self._ttl, sparse_vector.copy())

    def _evict(self, now: float) -> None:
        """Evict expired and oldest entries."""
        # Remove expired entries
        expired = [k for k, (exp, _) in self._cache.items() if exp <= now]
        for k in expired[:500]:  # Limit to avoid long pauses
            self._cache.pop(k, None)

        # If still full, remove oldest 20%
        if len(self._cache) >= self._max_items:
            sorted_items = sorted(self._cache.items(), key=lambda x: x[1][0])
            to_remove = len(sorted_items) // 5 or 1
            for k, _ in sorted_items[:to_remove]:
                self._cache.pop(k, None)

    def stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            total = self._hits + self._misses
            hit_rate = self._hits / total if total > 0 else 0.0
            return {
                "entries": len(self._cache),
                "max_entries": self._max_items,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(hit_rate, 4),
            }

    def clear(self) -> int:
        """Clear cache and return number of cleared entries."""
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            return count


# ---------------------------------------------------------------------------
# SPLADE Encoder
# ---------------------------------------------------------------------------


class SPLADEEncoder:
    """
    SPLADE sparse vector encoder.

    Produces sparse representations where each dimension corresponds to a
    vocabulary term, with learned importance weights. This enables:
    - Semantic matching through learned term expansion
    - Efficient retrieval using inverted indices
    - Interpretable relevance signals

    Usage:
        encoder = SPLADEEncoder()
        sparse_vec = encoder.encode("legal document text")
        # sparse_vec = {"court": 0.85, "judgment": 0.72, "defendant": 0.65, ...}
    """

    def __init__(self, config: Optional[SPLADEConfig] = None):
        """
        Initialize SPLADE encoder.

        Args:
            config: Configuration options. Uses defaults if not provided.
        """
        self.config = config or SPLADEConfig()
        self._model = None
        self._tokenizer = None
        self._device = None
        self._lock = threading.Lock()
        self._initialized = False

        # Cache
        self._cache = (
            SPLADECache(
                max_items=self.config.cache_max_items,
                ttl_seconds=self.config.cache_ttl_seconds,
            )
            if self.config.cache_enabled
            else None
        )

        # Statistics
        self._encode_count = 0
        self._total_encode_time_ms = 0.0

        logger.info(
            f"SPLADEEncoder created: model={self.config.model_name}, "
            f"top_k={self.config.top_k_tokens}, cache={'enabled' if self._cache else 'disabled'}"
        )

    def _lazy_init(self) -> None:
        """Lazy initialization of model and tokenizer."""
        if self._initialized:
            return

        with self._lock:
            if self._initialized:
                return

            try:
                import torch
                from transformers import AutoModelForMaskedLM, AutoTokenizer

                # Determine device
                if self.config.device == "auto":
                    if torch.cuda.is_available():
                        self._device = torch.device("cuda")
                    elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                        self._device = torch.device("mps")
                    else:
                        self._device = torch.device("cpu")
                else:
                    self._device = torch.device(self.config.device)

                logger.info(f"Loading SPLADE model on device: {self._device}")

                # Load tokenizer
                self._tokenizer = AutoTokenizer.from_pretrained(self.config.model_name)

                # Load model
                self._model = AutoModelForMaskedLM.from_pretrained(self.config.model_name)
                self._model = self._model.to(self._device)
                self._model.eval()

                # Apply FP16 if configured (except on CPU)
                if self.config.use_fp16 and self._device.type != "cpu":
                    self._model = self._model.half()

                self._initialized = True
                logger.info(f"SPLADE model loaded: {self.config.model_name}")

            except ImportError as e:
                raise ImportError(
                    "SPLADE encoder requires 'transformers' and 'torch'. "
                    f"Install with: pip install transformers torch. Error: {e}"
                )
            except Exception as e:
                logger.error(f"Failed to load SPLADE model: {e}")
                raise

    def encode(self, text: str, use_cache: bool = True) -> Dict[str, float]:
        """
        Encode text to sparse vector representation.

        Args:
            text: Input text to encode.
            use_cache: Whether to use caching.

        Returns:
            Dictionary mapping tokens to importance weights.
            Example: {"court": 0.85, "legal": 0.72, "defendant": 0.65}
        """
        if not text or not text.strip():
            return {}

        text = text.strip()

        # Check cache
        if use_cache and self._cache:
            cached = self._cache.get(text)
            if cached is not None:
                logger.debug(f"SPLADE cache hit for text (len={len(text)})")
                return cached

        # Encode
        self._lazy_init()
        start_time = time.time()

        try:
            sparse_vector = self._encode_single(text)

            # Update stats
            elapsed_ms = (time.time() - start_time) * 1000
            self._encode_count += 1
            self._total_encode_time_ms += elapsed_ms

            # Cache result
            if use_cache and self._cache:
                self._cache.set(text, sparse_vector)

            logger.debug(
                f"SPLADE encoded text (len={len(text)}) -> "
                f"{len(sparse_vector)} terms in {elapsed_ms:.1f}ms"
            )
            return sparse_vector

        except Exception as e:
            logger.error(f"SPLADE encoding failed: {e}")
            raise

    def _encode_single(self, text: str) -> Dict[str, float]:
        """Internal: encode single text to sparse vector."""
        import torch

        # Tokenize
        inputs = self._tokenizer(
            text,
            return_tensors="pt",
            max_length=self.config.max_length,
            truncation=True,
            padding=True,
        ).to(self._device)

        # Forward pass
        with torch.no_grad():
            outputs = self._model(**inputs)
            logits = outputs.logits  # [batch_size, seq_len, vocab_size]

            # SPLADE aggregation: max over sequence positions, then RELU
            # This gives importance weights for each vocabulary term
            max_logits = torch.max(logits, dim=1).values  # [batch_size, vocab_size]

            # Apply ReLU to get non-negative weights
            activations = torch.relu(max_logits)

            # Apply log(1+x) for better scaling (as in original SPLADE)
            if self.config.apply_log1p:
                activations = torch.log1p(activations)

            # Get sparse vector
            activations = activations.squeeze(0)  # [vocab_size]

        # Convert to sparse representation
        sparse_vector = self._to_sparse_dict(activations)

        return sparse_vector

    def _to_sparse_dict(self, activations: "torch.Tensor") -> Dict[str, float]:
        """Convert activation tensor to sparse dictionary."""
        import torch

        # Get non-zero indices and values
        non_zero_mask = activations > self.config.min_weight
        indices = torch.where(non_zero_mask)[0]
        values = activations[indices]

        # Keep only top-k if needed
        if len(indices) > self.config.top_k_tokens:
            _, top_indices = torch.topk(values, self.config.top_k_tokens)
            indices = indices[top_indices]
            values = values[top_indices]

        # Convert to dictionary
        sparse_dict: Dict[str, float] = {}
        indices_cpu = indices.cpu().numpy()
        values_cpu = values.cpu().numpy()

        for idx, val in zip(indices_cpu, values_cpu):
            token = self._tokenizer.decode([int(idx)]).strip()
            if token and not token.startswith("[") and not token.startswith("##"):
                # Skip special tokens and subword prefixes
                sparse_dict[token.lower()] = float(val)

        return sparse_dict

    def encode_batch(
        self, texts: List[str], use_cache: bool = True
    ) -> List[Dict[str, float]]:
        """
        Batch encode multiple texts.

        Args:
            texts: List of texts to encode.
            use_cache: Whether to use caching.

        Returns:
            List of sparse vectors, one per input text.
        """
        if not texts:
            return []

        results: List[Dict[str, float]] = []
        to_encode: List[Tuple[int, str]] = []

        # Check cache for each text
        for i, text in enumerate(texts):
            text = text.strip() if text else ""
            if not text:
                results.append({})
                continue

            if use_cache and self._cache:
                cached = self._cache.get(text)
                if cached is not None:
                    results.append(cached)
                    continue

            # Track index for later insertion
            to_encode.append((i, text))
            results.append({})  # Placeholder

        if not to_encode:
            return results

        # Batch encode uncached texts
        self._lazy_init()
        start_time = time.time()

        try:
            # Process in batches
            for batch_start in range(0, len(to_encode), self.config.batch_size):
                batch_end = min(batch_start + self.config.batch_size, len(to_encode))
                batch = to_encode[batch_start:batch_end]

                batch_texts = [t[1] for t in batch]
                batch_results = self._encode_batch_internal(batch_texts)

                for (orig_idx, text), sparse_vec in zip(batch, batch_results):
                    results[orig_idx] = sparse_vec
                    if use_cache and self._cache:
                        self._cache.set(text, sparse_vec)

            elapsed_ms = (time.time() - start_time) * 1000
            self._encode_count += len(to_encode)
            self._total_encode_time_ms += elapsed_ms

            logger.info(
                f"SPLADE batch encoded {len(to_encode)} texts "
                f"({len(texts) - len(to_encode)} from cache) in {elapsed_ms:.1f}ms"
            )

        except Exception as e:
            logger.error(f"SPLADE batch encoding failed: {e}")
            raise

        return results

    def _encode_batch_internal(self, texts: List[str]) -> List[Dict[str, float]]:
        """Internal: batch encode texts."""
        import torch

        # Tokenize batch
        inputs = self._tokenizer(
            texts,
            return_tensors="pt",
            max_length=self.config.max_length,
            truncation=True,
            padding=True,
        ).to(self._device)

        # Forward pass
        with torch.no_grad():
            outputs = self._model(**inputs)
            logits = outputs.logits  # [batch_size, seq_len, vocab_size]

            # SPLADE aggregation
            max_logits = torch.max(logits, dim=1).values
            activations = torch.relu(max_logits)

            if self.config.apply_log1p:
                activations = torch.log1p(activations)

        # Convert each to sparse dict
        results = []
        for i in range(len(texts)):
            sparse_vec = self._to_sparse_dict(activations[i])
            results.append(sparse_vec)

        return results

    def encode_with_result(
        self, text: str, use_cache: bool = True
    ) -> SPLADEResult:
        """
        Encode text and return detailed result object.

        Args:
            text: Input text to encode.
            use_cache: Whether to use caching.

        Returns:
            SPLADEResult with sparse vector and metadata.
        """
        start_time = time.time()

        # Check cache
        from_cache = False
        if use_cache and self._cache:
            cached = self._cache.get(text)
            if cached is not None:
                from_cache = True
                elapsed_ms = (time.time() - start_time) * 1000
                return SPLADEResult(
                    sparse_vector=cached,
                    num_active_terms=len(cached),
                    encoding_time_ms=elapsed_ms,
                    from_cache=True,
                )

        # Encode
        sparse_vector = self.encode(text, use_cache=use_cache)
        elapsed_ms = (time.time() - start_time) * 1000

        return SPLADEResult(
            sparse_vector=sparse_vector,
            num_active_terms=len(sparse_vector),
            encoding_time_ms=elapsed_ms,
            from_cache=from_cache,
        )

    # ---------------------------------------------------------------------------
    # Sparse Vector Operations
    # ---------------------------------------------------------------------------

    @staticmethod
    def sparse_dot_product(
        vec1: Dict[str, float], vec2: Dict[str, float]
    ) -> float:
        """
        Compute sparse dot product between two sparse vectors.

        Args:
            vec1: First sparse vector (term -> weight).
            vec2: Second sparse vector (term -> weight).

        Returns:
            Dot product score (sum of products for overlapping terms).
        """
        if not vec1 or not vec2:
            return 0.0

        # Use smaller dict for iteration
        if len(vec1) > len(vec2):
            vec1, vec2 = vec2, vec1

        score = 0.0
        for term, weight1 in vec1.items():
            weight2 = vec2.get(term)
            if weight2 is not None:
                score += weight1 * weight2

        return score

    @staticmethod
    def sparse_cosine_similarity(
        vec1: Dict[str, float], vec2: Dict[str, float]
    ) -> float:
        """
        Compute cosine similarity between two sparse vectors.

        Args:
            vec1: First sparse vector.
            vec2: Second sparse vector.

        Returns:
            Cosine similarity score in [0, 1].
        """
        if not vec1 or not vec2:
            return 0.0

        dot = SPLADEEncoder.sparse_dot_product(vec1, vec2)

        norm1 = np.sqrt(sum(w**2 for w in vec1.values()))
        norm2 = np.sqrt(sum(w**2 for w in vec2.values()))

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return dot / (norm1 * norm2)

    @staticmethod
    def merge_sparse_vectors(
        vectors: List[Dict[str, float]], weights: Optional[List[float]] = None
    ) -> Dict[str, float]:
        """
        Merge multiple sparse vectors with optional weights.

        Args:
            vectors: List of sparse vectors to merge.
            weights: Optional weights for each vector. Defaults to equal weights.

        Returns:
            Merged sparse vector.
        """
        if not vectors:
            return {}

        if len(vectors) == 1:
            return vectors[0].copy()

        if weights is None:
            weights = [1.0 / len(vectors)] * len(vectors)

        merged: Dict[str, float] = {}

        for vec, weight in zip(vectors, weights):
            for term, value in vec.items():
                merged[term] = merged.get(term, 0.0) + value * weight

        return merged

    @staticmethod
    def filter_sparse_vector(
        vec: Dict[str, float],
        top_k: Optional[int] = None,
        min_weight: Optional[float] = None,
    ) -> Dict[str, float]:
        """
        Filter sparse vector by top-k terms and/or minimum weight.

        Args:
            vec: Sparse vector to filter.
            top_k: Keep only top-k terms by weight.
            min_weight: Minimum weight threshold.

        Returns:
            Filtered sparse vector.
        """
        if not vec:
            return {}

        filtered = dict(vec)

        # Apply minimum weight filter
        if min_weight is not None:
            filtered = {t: w for t, w in filtered.items() if w >= min_weight}

        # Apply top-k filter
        if top_k is not None and len(filtered) > top_k:
            sorted_items = sorted(filtered.items(), key=lambda x: x[1], reverse=True)
            filtered = dict(sorted_items[:top_k])

        return filtered

    # ---------------------------------------------------------------------------
    # Utility Methods
    # ---------------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Get encoder statistics."""
        stats = {
            "model": self.config.model_name,
            "device": str(self._device) if self._device else "not_initialized",
            "initialized": self._initialized,
            "encode_count": self._encode_count,
            "avg_encode_time_ms": (
                round(self._total_encode_time_ms / self._encode_count, 2)
                if self._encode_count > 0
                else 0.0
            ),
        }

        if self._cache:
            stats["cache"] = self._cache.stats()

        return stats

    def clear_cache(self) -> Dict[str, int]:
        """Clear the encoding cache."""
        if self._cache:
            cleared = self._cache.clear()
            return {"cleared_entries": cleared}
        return {"cleared_entries": 0}


# ---------------------------------------------------------------------------
# Module-Level Singleton
# ---------------------------------------------------------------------------


_encoder: Optional[SPLADEEncoder] = None
_encoder_lock = threading.Lock()


def get_splade_encoder(config: Optional[SPLADEConfig] = None) -> SPLADEEncoder:
    """
    Get or create the SPLADE encoder singleton.

    Args:
        config: Optional configuration. Used only on first call.

    Returns:
        SPLADEEncoder instance.
    """
    global _encoder

    if _encoder is not None:
        return _encoder

    with _encoder_lock:
        if _encoder is None:
            _encoder = SPLADEEncoder(config)

    return _encoder


def reset_splade_encoder() -> None:
    """Reset the SPLADE encoder singleton."""
    global _encoder

    with _encoder_lock:
        _encoder = None
        logger.info("SPLADE encoder singleton reset")
