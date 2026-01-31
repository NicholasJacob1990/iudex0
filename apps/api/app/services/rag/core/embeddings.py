"""
Embeddings Service for RAG Pipeline

Provides cached embedding generation using OpenAI's text-embedding-3-large model.
Features:
- Thread-safe TTL cache for query embeddings
- Batch embedding support for document ingestion
- Configurable via RAGConfig
- Comprehensive monitoring and statistics
"""

from __future__ import annotations

import hashlib
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import openai
from openai import OpenAI

from app.services.rag.config import get_rag_config

logger = logging.getLogger(__name__)

try:
    from sentence_transformers import SentenceTransformer  # type: ignore
except Exception:
    SentenceTransformer = None  # type: ignore


@dataclass
class CacheEntry:
    """Single cache entry with embedding and metadata."""
    embedding: List[float]
    created_at: float
    access_count: int = 0
    last_accessed: float = field(default_factory=time.time)


@dataclass
class CacheStats:
    """Statistics for cache monitoring."""
    hits: int = 0
    misses: int = 0
    evictions: int = 0
    total_entries: int = 0
    total_bytes_estimate: int = 0

    @property
    def hit_rate(self) -> float:
        """Calculate cache hit rate."""
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0

    def to_dict(self) -> Dict:
        """Convert stats to dictionary for JSON serialization."""
        return {
            "hits": self.hits,
            "misses": self.misses,
            "evictions": self.evictions,
            "hit_rate": round(self.hit_rate, 4),
            "total_entries": self.total_entries,
            "total_bytes_estimate": self.total_bytes_estimate,
        }


class TTLCache:
    """
    Thread-safe TTL cache for embeddings.

    Uses a dictionary with timestamps for expiration tracking.
    Cleanup happens lazily on access and periodically during operations.
    """

    def __init__(self, ttl_seconds: int = 3600, max_size: int = 10000):
        """
        Initialize the TTL cache.

        Args:
            ttl_seconds: Time-to-live for cache entries in seconds
            max_size: Maximum number of entries before forced eviction
        """
        self._cache: Dict[str, CacheEntry] = {}
        self._lock = threading.RLock()
        self._ttl = ttl_seconds
        self._max_size = max_size
        self._stats = CacheStats()
        self._last_cleanup = time.time()
        self._cleanup_interval = 300  # Cleanup every 5 minutes

    def _compute_key(self, text: str) -> str:
        """Compute a hash key for the given text."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _is_expired(self, entry: CacheEntry) -> bool:
        """Check if a cache entry has expired."""
        return (time.time() - entry.created_at) > self._ttl

    def _maybe_cleanup(self) -> None:
        """
        Perform cleanup if enough time has passed.
        Must be called with lock held.
        """
        now = time.time()
        if (now - self._last_cleanup) < self._cleanup_interval:
            return

        expired_keys = [
            key for key, entry in self._cache.items()
            if self._is_expired(entry)
        ]

        for key in expired_keys:
            del self._cache[key]
            self._stats.evictions += 1

        self._last_cleanup = now
        self._stats.total_entries = len(self._cache)

        if expired_keys:
            logger.debug(f"Cache cleanup: evicted {len(expired_keys)} expired entries")

    def _evict_oldest(self) -> None:
        """
        Evict oldest entries when cache is full.
        Must be called with lock held.
        """
        if len(self._cache) < self._max_size:
            return

        # Sort by last accessed time and remove oldest 10%
        entries_to_remove = max(1, len(self._cache) // 10)
        sorted_keys = sorted(
            self._cache.keys(),
            key=lambda k: self._cache[k].last_accessed
        )

        for key in sorted_keys[:entries_to_remove]:
            del self._cache[key]
            self._stats.evictions += 1

        logger.debug(f"Cache eviction: removed {entries_to_remove} oldest entries")

    def get(self, text: str) -> Optional[List[float]]:
        """
        Get embedding from cache if present and not expired.

        Args:
            text: The text to look up

        Returns:
            The cached embedding or None if not found/expired
        """
        key = self._compute_key(text)

        with self._lock:
            self._maybe_cleanup()

            entry = self._cache.get(key)
            if entry is None:
                self._stats.misses += 1
                return None

            if self._is_expired(entry):
                del self._cache[key]
                self._stats.misses += 1
                self._stats.evictions += 1
                self._stats.total_entries = len(self._cache)
                return None

            # Update access metadata
            entry.access_count += 1
            entry.last_accessed = time.time()
            self._stats.hits += 1
            return entry.embedding

    def set(self, text: str, embedding: List[float]) -> None:
        """
        Store embedding in cache.

        Args:
            text: The original text
            embedding: The embedding vector to cache
        """
        key = self._compute_key(text)
        now = time.time()

        with self._lock:
            self._evict_oldest()

            self._cache[key] = CacheEntry(
                embedding=embedding,
                created_at=now,
                access_count=1,
                last_accessed=now,
            )
            self._stats.total_entries = len(self._cache)
            # Estimate: 8 bytes per float + overhead
            self._stats.total_bytes_estimate = (
                len(self._cache) * len(embedding) * 8 + len(self._cache) * 100
            )

    def clear(self) -> int:
        """
        Clear all cache entries.

        Returns:
            Number of entries cleared
        """
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            self._stats.total_entries = 0
            self._stats.total_bytes_estimate = 0
            logger.info(f"Cache cleared: removed {count} entries")
            return count

    def get_stats(self) -> CacheStats:
        """Get a copy of current cache statistics."""
        with self._lock:
            self._stats.total_entries = len(self._cache)
            return CacheStats(
                hits=self._stats.hits,
                misses=self._stats.misses,
                evictions=self._stats.evictions,
                total_entries=self._stats.total_entries,
                total_bytes_estimate=self._stats.total_bytes_estimate,
            )


class EmbeddingsService:
    """
    Production-ready embeddings service with caching.

    Uses OpenAI embeddings by default, but supports a local SentenceTransformer
    fallback for development and integration tests.

    Provider selection (env `RAG_EMBEDDINGS_PROVIDER`):
      - `openai`: always use OpenAI (requires API key)
      - `local`: always use SentenceTransformer
      - `auto` (default): use OpenAI if key present, else local
    Implements TTL caching for query embeddings and batch processing for ingestion.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        dimensions: Optional[int] = None,
        cache_ttl: Optional[int] = None,
        batch_size: Optional[int] = None,
    ):
        """
        Initialize the embeddings service.

        Args:
            api_key: OpenAI API key (defaults to OPENAI_API_KEY env var)
            model: Embedding model name (defaults to config)
            dimensions: Embedding dimensions (defaults to config)
            cache_ttl: Cache TTL in seconds (defaults to config)
            batch_size: Batch size for bulk operations (defaults to config)
        """
        config = get_rag_config()

        provider = (os.getenv("RAG_EMBEDDINGS_PROVIDER") or "auto").strip().lower()
        if provider not in ("auto", "openai", "local"):
            provider = "auto"

        # Prefer explicit arg, then env, then whatever config provides.
        api_key = api_key if api_key is not None else (os.getenv("OPENAI_API_KEY") or None)
        has_openai_key = bool(api_key and str(api_key).strip())
        if provider == "auto":
            provider = "openai" if has_openai_key else "local"

        self._provider = provider

        self._model = model or config.embedding_model
        self._dimensions = dimensions or config.embedding_dimensions
        self._batch_size = batch_size or config.embedding_batch_size
        cache_ttl_seconds = cache_ttl or config.embedding_cache_ttl_seconds

        self._client: Optional[OpenAI] = None
        self._local_model: Optional["SentenceTransformer"] = None

        if self._provider == "openai":
            if not has_openai_key:
                raise ValueError("RAG_EMBEDDINGS_PROVIDER=openai requires OPENAI_API_KEY")
            self._client = OpenAI(api_key=api_key)
        else:
            if SentenceTransformer is None:
                raise ImportError(
                    "SentenceTransformer not available. Install: pip install sentence-transformers"
                )
            local_model_name = (
                os.getenv("RAG_LOCAL_EMBEDDING_MODEL")
                or os.getenv("EMBEDDING_MODEL")
                or self._model
                or "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"
            )
            self._local_model = SentenceTransformer(str(local_model_name))
            try:
                local_dim = int(self._local_model.get_sentence_embedding_dimension())
            except Exception:
                local_dim = self._dimensions
            if self._dimensions != local_dim:
                logger.warning(
                    "EmbeddingsService local dim mismatch: config=%s model=%s; "
                    "set EMBEDDING_DIMENSIONS to %s for Qdrant compatibility.",
                    self._dimensions,
                    local_dim,
                    local_dim,
                )

        # Initialize cache
        self._cache = TTLCache(ttl_seconds=cache_ttl_seconds)

        # Track API calls for monitoring
        self._api_calls = 0
        self._api_tokens = 0
        self._api_lock = threading.Lock()

        logger.info(
            "EmbeddingsService initialized: provider=%s, model=%s, dimensions=%s, cache_ttl=%ss",
            self._provider,
            self._model,
            self._dimensions,
            cache_ttl_seconds,
        )

    def _adapt_dimensions(self, vector: List[float]) -> List[float]:
        if not vector:
            return [0.0] * int(self._dimensions or 0)
        dim = int(self._dimensions or len(vector))
        if len(vector) == dim:
            return vector
        if len(vector) > dim:
            return vector[:dim]
        return vector + [0.0] * (dim - len(vector))

    def _embed_local(self, texts: List[str]) -> List[List[float]]:
        if self._local_model is None:
            raise RuntimeError("Local embedding model not initialized")
        vectors = self._local_model.encode(
            texts,
            batch_size=max(1, int(self._batch_size or 32)),
            show_progress_bar=False,
            normalize_embeddings=True,
        )
        # sentence-transformers may return a numpy array; normalize to Python lists.
        out: List[List[float]] = []
        for v in vectors:
            try:
                vec = v.tolist()  # type: ignore[attr-defined]
            except Exception:
                vec = list(v)  # type: ignore[arg-type]
            out.append(self._adapt_dimensions([float(x) for x in vec]))
        return out

    def embed_query(self, text: str, use_cache: bool = True) -> List[float]:
        """
        Generate embedding for a single query with caching.

        Args:
            text: The text to embed
            use_cache: Whether to use cache (default True)

        Returns:
            Embedding vector as list of floats

        Raises:
            openai.OpenAIError: If API call fails
            ValueError: If text is empty
        """
        if not text or not text.strip():
            raise ValueError("Cannot embed empty text")

        text = text.strip()

        # Check cache first
        if use_cache:
            cached = self._cache.get(text)
            if cached is not None:
                logger.debug(f"Cache hit for query embedding (len={len(text)})")
                return cached

        # Generate embedding via API
        try:
            if self._provider == "openai":
                embedding = self._call_api([text])[0]
            else:
                embedding = self._embed_local([text])[0]

            # Store in cache
            if use_cache:
                self._cache.set(text, embedding)

            logger.debug(f"Generated embedding for query (len={len(text)})")
            return embedding

        except openai.APIConnectionError as e:
            logger.error(f"OpenAI connection error: {e}")
            raise
        except openai.RateLimitError as e:
            logger.error(f"OpenAI rate limit exceeded: {e}")
            raise
        except openai.APIStatusError as e:
            logger.error(f"OpenAI API error: {e.status_code} - {e.message}")
            raise

    def embed_many(
        self,
        texts: List[str],
        show_progress: bool = False,
    ) -> List[List[float]]:
        """
        Generate embeddings for multiple texts in batches.

        Designed for document ingestion - does NOT use cache.

        Args:
            texts: List of texts to embed
            show_progress: Whether to log progress (for long operations)

        Returns:
            List of embedding vectors

        Raises:
            openai.OpenAIError: If API call fails
            ValueError: If texts list is empty
        """
        if not texts:
            raise ValueError("Cannot embed empty list of texts")

        # Filter and track empty texts
        processed_texts: List[Tuple[int, str]] = []
        for i, text in enumerate(texts):
            if text and text.strip():
                processed_texts.append((i, text.strip()))
            else:
                logger.warning(f"Skipping empty text at index {i}")

        if not processed_texts:
            raise ValueError("All texts are empty")

        # Process in batches
        all_embeddings: Dict[int, List[float]] = {}
        total_batches = (len(processed_texts) + self._batch_size - 1) // self._batch_size

        for batch_num in range(total_batches):
            start_idx = batch_num * self._batch_size
            end_idx = min(start_idx + self._batch_size, len(processed_texts))
            batch = processed_texts[start_idx:end_idx]

            batch_texts = [t[1] for t in batch]
            batch_indices = [t[0] for t in batch]

            try:
                embeddings = self._call_api(batch_texts) if self._provider == "openai" else self._embed_local(batch_texts)

                for idx, embedding in zip(batch_indices, embeddings):
                    all_embeddings[idx] = embedding

                if show_progress:
                    logger.info(
                        f"Embedding progress: batch {batch_num + 1}/{total_batches} "
                        f"({len(all_embeddings)}/{len(processed_texts)} texts)"
                    )

            except openai.OpenAIError as e:
                logger.error(f"Batch {batch_num + 1} failed: {e}")
                raise

        # Return embeddings in original order, with empty vectors for skipped texts
        result: List[List[float]] = []
        empty_embedding = [0.0] * self._dimensions

        for i in range(len(texts)):
            if i in all_embeddings:
                result.append(all_embeddings[i])
            else:
                result.append(empty_embedding)
                logger.debug(f"Using zero embedding for empty text at index {i}")

        logger.info(f"Generated {len(processed_texts)} embeddings for {len(texts)} texts")
        return result

    def embed_queries(
        self,
        texts: List[str],
        *,
        use_cache: bool = True,
    ) -> List[List[float]]:
        """
        Generate embeddings for multiple short queries with optional cache reuse.

        Unlike `embed_many`, this method:
        - Reuses the TTL cache for already-seen queries (when enabled)
        - Batches only the cache-misses into a single provider call (when possible)

        Returns embeddings aligned with the input order.
        """
        if not texts:
            return []

        empty_embedding = [0.0] * int(self._dimensions or 0)
        out: List[List[float]] = [empty_embedding for _ in range(len(texts))]

        # Deduplicate while preserving index mapping
        misses: Dict[str, List[int]] = {}
        for idx, raw in enumerate(texts):
            cleaned = (raw or "").strip()
            if not cleaned:
                continue

            if use_cache:
                cached = self._cache.get(cleaned)
                if cached is not None:
                    out[idx] = cached
                    continue

            misses.setdefault(cleaned, []).append(idx)

        if not misses:
            return out

        miss_texts = list(misses.keys())
        try:
            vectors = self._call_api(miss_texts) if self._provider == "openai" else self._embed_local(miss_texts)
        except Exception:
            # Fallback: per-query embedding to avoid failing the whole request
            vectors = []
            for t in miss_texts:
                try:
                    vectors.append(self.embed_query(t, use_cache=use_cache))
                except Exception:
                    vectors.append(empty_embedding)

        for text, vec in zip(miss_texts, vectors):
            vec = self._adapt_dimensions([float(x) for x in (vec or empty_embedding)])
            if use_cache and text:
                try:
                    self._cache.set(text, vec)
                except Exception:
                    pass
            for idx in misses.get(text, []):
                out[idx] = vec

        return out

    def _call_api(self, texts: List[str]) -> List[List[float]]:
        """
        Make API call to generate embeddings.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors
        """
        response = self._client.embeddings.create(
            model=self._model,
            input=texts,
            dimensions=self._dimensions,
        )

        # Track API usage
        with self._api_lock:
            self._api_calls += 1
            if hasattr(response, "usage") and response.usage:
                self._api_tokens += response.usage.total_tokens

        # Sort by index to maintain order (API may return out of order)
        sorted_data = sorted(response.data, key=lambda x: x.index)
        return [item.embedding for item in sorted_data]

    def get_cache_stats(self) -> Dict:
        """
        Get cache statistics for monitoring.

        Returns:
            Dictionary with cache stats and API usage
        """
        cache_stats = self._cache.get_stats()

        with self._api_lock:
            api_calls = self._api_calls
            api_tokens = self._api_tokens

        return {
            "cache": cache_stats.to_dict(),
            "api": {
                "total_calls": api_calls,
                "total_tokens": api_tokens,
            },
            "config": {
                "model": self._model,
                "dimensions": self._dimensions,
                "batch_size": self._batch_size,
            },
        }

    def clear_cache(self) -> Dict:
        """
        Clear the embedding cache.

        Returns:
            Dictionary with cleared entries count
        """
        cleared = self._cache.clear()
        return {"cleared_entries": cleared}


# Module-level singleton
_service: Optional[EmbeddingsService] = None
_service_lock = threading.Lock()


def get_embeddings_service() -> EmbeddingsService:
    """
    Get or create the embeddings service singleton.

    Thread-safe lazy initialization.

    Returns:
        EmbeddingsService instance
    """
    global _service

    if _service is not None:
        return _service

    with _service_lock:
        # Double-check after acquiring lock
        if _service is None:
            _service = EmbeddingsService()

    return _service


def reset_embeddings_service() -> None:
    """
    Reset the embeddings service singleton.

    Useful for testing or when configuration changes.
    """
    global _service

    with _service_lock:
        _service = None
        logger.info("EmbeddingsService singleton reset")


# Common legal queries for preloading embeddings cache
COMMON_LEGAL_QUERIES = [
    # Constitutional law
    "princípios constitucionais da administração pública",
    "direitos fundamentais Constituição Federal",
    "competência do Supremo Tribunal Federal",
    "controle de constitucionalidade",
    # Civil law
    "responsabilidade civil por danos morais",
    "prazo prescricional código civil",
    "contrato de compra e venda requisitos",
    "obrigações contratuais inadimplemento",
    # Administrative law
    "licitação modalidades Lei 14.133",
    "ato administrativo anulação revogação",
    "servidor público estabilidade demissão",
    "contrato administrativo cláusulas exorbitantes",
    # Labor law
    "verbas rescisórias trabalhistas",
    "justa causa demissão CLT",
    "horas extras cálculo adicional noturno",
    "estabilidade gestante acidente trabalho",
    # Procedural law
    "recurso especial prequestionamento STJ",
    "tutela antecipada requisitos CPC",
    "prescrição intercorrente processo execução",
    "competência foro eleição consumidor",
    # Tax law
    "lançamento tributário decadência",
    "imunidade tributária templos religiosos",
    "ICMS substituição tributária",
    "contribuições previdenciárias patronais",
    # Criminal law
    "prisão preventiva requisitos CPP",
    "prescrição penal retroativa",
    "excludentes ilicitude legítima defesa",
    "dosimetria pena circunstâncias judiciais",
    # Consumer law
    "vício do produto responsabilidade fornecedor",
    "inversão do ônus da prova CDC",
    "dano moral contrato consumo",
]


def preload_embeddings_cache(queries: Optional[List[str]] = None) -> Tuple[float, int]:
    """
    Preload common legal query embeddings into cache.

    This function should be called during application startup to warm up
    the embeddings cache with frequently used legal queries.

    Args:
        queries: Optional list of queries to preload. If not provided,
                uses the default COMMON_LEGAL_QUERIES list.

    Returns:
        Tuple of (load_time_seconds, queries_cached)
    """
    start = time.time()
    queries_to_cache = queries or COMMON_LEGAL_QUERIES

    service = get_embeddings_service()
    cached_count = 0

    for query in queries_to_cache:
        try:
            # This will cache the embedding
            service.embed_query(query, use_cache=True)
            cached_count += 1
        except Exception as e:
            logger.warning(f"Failed to preload embedding for query '{query[:50]}...': {e}")
            continue

    load_time = time.time() - start
    logger.info(
        f"Embeddings cache preloaded: {cached_count}/{len(queries_to_cache)} queries "
        f"in {load_time:.2f}s"
    )

    return load_time, cached_count


def is_embeddings_service_ready() -> bool:
    """
    Check if the embeddings service is initialized and ready.

    Returns:
        True if the service singleton exists
    """
    return _service is not None
