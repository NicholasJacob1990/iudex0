"""
Kanon 2 Embedder Provider — Embeddings para direito internacional (US/UK/EU/INT).

Kanon 2 Embedder (Isaacus) é o modelo #1 no MLEB (Massive Legal Embedding Benchmark),
superando OpenAI text-embedding-3-large em 9% e sendo 30% mais rápido que
text-embedding-3-small.

Especificações:
  - Dimensões: 1792 (nativo), usamos 1024 via Matryoshka (bom equilíbrio performance/tamanho)
  - Suporta Matryoshka: 1024, 768, 512, 256
  - Contexto: 16384 tokens
  - Task types: "retrieval/document", "retrieval/query"
  - NDCG@10 score: 86.03 no MLEB

Features:
  - SDK nativo Isaacus (async)
  - Retry com backoff exponencial
  - Fallback para voyage-law-2 se Kanon falhar
  - Cache LRU thread-safe
  - Configuração via env: ISAACUS_API_KEY
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Importação condicional do SDK Isaacus
# ---------------------------------------------------------------------------
try:
    from isaacus import AsyncIsaacus  # type: ignore

    _ISAACUS_AVAILABLE = True
except ImportError:
    AsyncIsaacus = None  # type: ignore
    _ISAACUS_AVAILABLE = False

# Fallback: httpx para chamada REST direta caso SDK não esteja instalado
try:
    import httpx  # type: ignore

    _HTTPX_AVAILABLE = True
except ImportError:
    httpx = None  # type: ignore
    _HTTPX_AVAILABLE = False


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

KANON_MODEL = "kanon-2-embedder"
KANON_DEFAULT_DIMENSIONS = 1024  # Bom equilíbrio performance/tamanho (Matryoshka)
KANON_MAX_DIMENSIONS = 1792
KANON_MAX_TOKENS = 16384
KANON_API_BASE = "https://api.isaacus.com/v1"

KanonTaskType = Literal["retrieval/document", "retrieval/query"]


# ---------------------------------------------------------------------------
# Cache LRU thread-safe
# ---------------------------------------------------------------------------


class _KanonLRUCache:
    """Cache LRU thread-safe para embeddings Kanon."""

    def __init__(self, max_size: int = 2048) -> None:
        self._cache: OrderedDict[str, List[float]] = OrderedDict()
        self._max_size = max_size
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    @staticmethod
    def _key(text: str, task: str) -> str:
        raw = f"kanon:{task}:{text}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get(self, text: str, task: str) -> Optional[List[float]]:
        key = self._key(text, task)
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                self._hits += 1
                return self._cache[key]
            self._misses += 1
            return None

    def set(self, text: str, task: str, embedding: List[float]) -> None:
        key = self._key(text, task)
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            else:
                if len(self._cache) >= self._max_size:
                    self._cache.popitem(last=False)
            self._cache[key] = embedding

    def clear(self) -> int:
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            return count

    @property
    def stats(self) -> Dict[str, Any]:
        with self._lock:
            total = self._hits + self._misses
            return {
                "size": len(self._cache),
                "max_size": self._max_size,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(self._hits / total, 4) if total > 0 else 0.0,
            }


# ---------------------------------------------------------------------------
# Métricas de custo
# ---------------------------------------------------------------------------


@dataclass
class KanonCostTracker:
    """Rastreia uso do Kanon 2 Embedder."""

    total_tokens: int = 0
    total_requests: int = 0
    total_errors: int = 0
    total_fallbacks: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def record(self, tokens: int) -> None:
        with self._lock:
            self.total_tokens += tokens
            self.total_requests += 1

    def record_error(self) -> None:
        with self._lock:
            self.total_errors += 1

    def record_fallback(self) -> None:
        with self._lock:
            self.total_fallbacks += 1

    def to_dict(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "total_tokens": self.total_tokens,
                "total_requests": self.total_requests,
                "total_errors": self.total_errors,
                "total_fallbacks": self.total_fallbacks,
            }


# ---------------------------------------------------------------------------
# Provider principal
# ---------------------------------------------------------------------------


class KanonEmbeddingsProvider:
    """
    Provider de embeddings Kanon 2 Embedder (Isaacus) para direito estrangeiro.

    Kanon 2 é o #1 no MLEB benchmark para embeddings jurídicos, com suporte a
    US, UK, EU, Australia, Irlanda e Singapura.

    Uso:
        provider = KanonEmbeddingsProvider()
        embeddings = await provider.embed_documents(["legal text"])
        query_emb = await provider.embed_query("search query")
    """

    MODEL = KANON_MODEL
    BASE_URL = KANON_API_BASE

    def __init__(
        self,
        api_key: Optional[str] = None,
        dimensions: int = KANON_DEFAULT_DIMENSIONS,
        cache_max_size: int = 2048,
        max_retries: int = 3,
        base_retry_delay: float = 1.0,
    ) -> None:
        self._api_key = api_key or os.getenv("ISAACUS_API_KEY", "")
        self._dimensions = dimensions
        self._max_retries = max_retries
        self._base_retry_delay = base_retry_delay

        # Cache
        self._cache = _KanonLRUCache(max_size=cache_max_size)

        # Métricas
        self._cost_tracker = KanonCostTracker()

        # Clientes (lazy init)
        self._isaacus_client: Optional[Any] = None
        self._httpx_client: Optional[Any] = None

        self._available = bool(self._api_key.strip()) and (
            _ISAACUS_AVAILABLE or _HTTPX_AVAILABLE
        )

        if self._available:
            logger.info(
                "KanonEmbeddingsProvider inicializado: model=%s, dimensions=%d, sdk=%s",
                self.MODEL,
                self._dimensions,
                "isaacus" if _ISAACUS_AVAILABLE else "httpx",
            )
        else:
            if not self._api_key.strip():
                logger.info(
                    "KanonEmbeddingsProvider: ISAACUS_API_KEY não configurada. "
                    "Kanon 2 desabilitado."
                )
            else:
                logger.info(
                    "KanonEmbeddingsProvider: nem isaacus SDK nem httpx disponíveis. "
                    "Instale com: pip install isaacus"
                )

    # ------------------------------------------------------------------
    # Propriedades
    # ------------------------------------------------------------------

    @property
    def is_available(self) -> bool:
        return self._available

    @property
    def dimensions(self) -> int:
        return self._dimensions

    @property
    def cost_tracker(self) -> KanonCostTracker:
        return self._cost_tracker

    @property
    def cache_stats(self) -> Dict[str, Any]:
        return self._cache.stats

    # ------------------------------------------------------------------
    # Lazy init clientes
    # ------------------------------------------------------------------

    def _get_isaacus_client(self) -> Any:
        if self._isaacus_client is None:
            if not _ISAACUS_AVAILABLE:
                raise RuntimeError("isaacus SDK não instalado")
            self._isaacus_client = AsyncIsaacus(api_key=self._api_key)
        return self._isaacus_client

    async def _get_httpx_client(self) -> Any:
        if self._httpx_client is None:
            if not _HTTPX_AVAILABLE:
                raise RuntimeError("httpx não instalado para fallback REST")
            self._httpx_client = httpx.AsyncClient(
                base_url=self.BASE_URL,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                timeout=60.0,
            )
        return self._httpx_client

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    async def embed_documents(
        self,
        texts: List[str],
        *,
        task: KanonTaskType = "retrieval/document",
    ) -> List[List[float]]:
        """
        Gera embeddings para documentos jurídicos.

        Args:
            texts: Lista de textos.
            task: Tipo de tarefa Isaacus.

        Returns:
            Lista de vetores de embedding.
        """
        if not texts:
            return []

        return await self._embed_with_fallback(texts, task=task)

    async def embed_query(
        self,
        text: str,
        *,
        task: KanonTaskType = "retrieval/query",
    ) -> List[float]:
        """
        Gera embedding para uma query de busca.

        Args:
            text: Texto da query.
            task: Tipo de tarefa Isaacus.

        Returns:
            Vetor de embedding.
        """
        if not text or not text.strip():
            return [0.0] * self._dimensions

        # Cache check
        cached = self._cache.get(text, task)
        if cached is not None:
            return cached

        results = await self._embed_with_fallback([text], task=task)
        if results:
            self._cache.set(text, task, results[0])
            return results[0]

        return [0.0] * self._dimensions

    async def embed_batch(
        self,
        texts: List[str],
        *,
        task: KanonTaskType = "retrieval/document",
        batch_size: int = 128,
    ) -> List[List[float]]:
        """
        Gera embeddings em lotes com controle de rate limit.

        Args:
            texts: Lista de textos.
            task: Tipo de tarefa.
            batch_size: Tamanho de cada lote.

        Returns:
            Lista de vetores de embedding.
        """
        if not texts:
            return []

        all_embeddings: List[List[float]] = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            batch_embeddings = await self._embed_with_fallback(batch, task=task)
            all_embeddings.extend(batch_embeddings)

            if i + batch_size < len(texts):
                await asyncio.sleep(0.1)

        logger.info(
            "Kanon batch embedding: %d textos em %d lotes",
            len(texts),
            (len(texts) + batch_size - 1) // batch_size,
        )
        return all_embeddings

    def clear_cache(self) -> int:
        return self._cache.clear()

    def get_stats(self) -> Dict[str, Any]:
        return {
            "available": self._available,
            "model": self.MODEL,
            "dimensions": self._dimensions,
            "cache": self._cache.stats,
            "costs": self._cost_tracker.to_dict(),
        }

    # ------------------------------------------------------------------
    # Lógica interna: chamada com fallback
    # ------------------------------------------------------------------

    async def _embed_with_fallback(
        self,
        texts: List[str],
        *,
        task: KanonTaskType,
    ) -> List[List[float]]:
        """
        Tenta gerar embeddings com cadeia de fallback:
          1. Kanon 2 via SDK Isaacus
          2. Kanon 2 via REST (httpx)
          3. Voyage law-2 (fallback)
        """
        clean_texts = [t.strip() if t else "" for t in texts]

        # Nível 1: SDK Isaacus
        if self._available and _ISAACUS_AVAILABLE:
            try:
                result = await self._call_isaacus_sdk(clean_texts, task=task)
                if result is not None:
                    return result
            except Exception as e:
                logger.warning("Kanon SDK falhou: %s", e)
                self._cost_tracker.record_error()

        # Nível 2: REST via httpx
        if self._available and _HTTPX_AVAILABLE and not _ISAACUS_AVAILABLE:
            try:
                result = await self._call_isaacus_rest(clean_texts, task=task)
                if result is not None:
                    return result
            except Exception as e:
                logger.warning("Kanon REST falhou: %s", e)
                self._cost_tracker.record_error()

        # Nível 3: Fallback Voyage law-2
        try:
            logger.info("Kanon fallback para voyage-law-2")
            self._cost_tracker.record_fallback()
            return await self._call_voyage_fallback(clean_texts)
        except Exception as e:
            logger.error("Voyage fallback também falhou: %s", e)
            self._cost_tracker.record_error()

        # Tudo falhou
        logger.error(
            "Todos os providers de embedding internacional falharam. Vetores zero."
        )
        return [[0.0] * self._dimensions for _ in texts]

    # ------------------------------------------------------------------
    # Chamada Isaacus SDK com retry
    # ------------------------------------------------------------------

    async def _call_isaacus_sdk(
        self,
        texts: List[str],
        *,
        task: KanonTaskType,
    ) -> Optional[List[List[float]]]:
        """Chama Isaacus via SDK com retry e backoff."""
        client = self._get_isaacus_client()
        last_error: Optional[Exception] = None

        for attempt in range(self._max_retries):
            try:
                start = time.time()
                response = await client.embeddings.create(
                    model=self.MODEL,
                    texts=texts,
                    task=task,
                )
                elapsed_ms = (time.time() - start) * 1000

                # Extrair embeddings da resposta
                embeddings: List[List[float]] = []
                if hasattr(response, "embeddings"):
                    for emb_item in response.embeddings:
                        if hasattr(emb_item, "embedding"):
                            vec = emb_item.embedding
                        else:
                            vec = emb_item
                        # Truncar para dimensão configurada (Matryoshka)
                        if len(vec) > self._dimensions:
                            vec = vec[: self._dimensions]
                        embeddings.append(vec)

                # Tokens
                total_tokens = 0
                if hasattr(response, "usage"):
                    total_tokens = getattr(response.usage, "total_tokens", 0) or 0
                self._cost_tracker.record(total_tokens)

                logger.debug(
                    "Kanon embed OK: texts=%d, tokens=%d, time=%.1fms",
                    len(texts),
                    total_tokens,
                    elapsed_ms,
                )
                return embeddings

            except Exception as e:
                last_error = e
                if attempt < self._max_retries - 1:
                    delay = self._base_retry_delay * (2**attempt)
                    logger.warning(
                        "Kanon SDK tentativa %d/%d falhou: %s. Retry em %.1fs",
                        attempt + 1,
                        self._max_retries,
                        e,
                        delay,
                    )
                    await asyncio.sleep(delay)

        if last_error:
            raise last_error
        return None

    # ------------------------------------------------------------------
    # Chamada Isaacus REST com retry
    # ------------------------------------------------------------------

    async def _call_isaacus_rest(
        self,
        texts: List[str],
        *,
        task: KanonTaskType,
    ) -> Optional[List[List[float]]]:
        """Chama Isaacus via REST (httpx) com retry e backoff."""
        client = await self._get_httpx_client()
        last_error: Optional[Exception] = None

        for attempt in range(self._max_retries):
            try:
                start = time.time()
                response = await client.post(
                    "/embeddings",
                    json={
                        "model": self.MODEL,
                        "texts": texts,
                        "task": task,
                    },
                )
                response.raise_for_status()
                data = response.json()
                elapsed_ms = (time.time() - start) * 1000

                embeddings: List[List[float]] = []
                for emb_item in data.get("embeddings", []):
                    vec = emb_item.get("embedding", emb_item) if isinstance(emb_item, dict) else emb_item
                    if isinstance(vec, list) and len(vec) > self._dimensions:
                        vec = vec[: self._dimensions]
                    embeddings.append(vec)

                total_tokens = data.get("usage", {}).get("total_tokens", 0)
                self._cost_tracker.record(total_tokens)

                logger.debug(
                    "Kanon REST OK: texts=%d, tokens=%d, time=%.1fms",
                    len(texts),
                    total_tokens,
                    elapsed_ms,
                )
                return embeddings

            except Exception as e:
                last_error = e
                if attempt < self._max_retries - 1:
                    delay = self._base_retry_delay * (2**attempt)
                    logger.warning(
                        "Kanon REST tentativa %d/%d falhou: %s. Retry em %.1fs",
                        attempt + 1,
                        self._max_retries,
                        e,
                        delay,
                    )
                    await asyncio.sleep(delay)

        if last_error:
            raise last_error
        return None

    # ------------------------------------------------------------------
    # Fallback Voyage law-2
    # ------------------------------------------------------------------

    async def _call_voyage_fallback(
        self,
        texts: List[str],
    ) -> List[List[float]]:
        """Fallback para Voyage law-2 quando Kanon falha."""
        try:
            from app.services.rag.voyage_embeddings import get_voyage_provider

            voyage = get_voyage_provider()
            if voyage.is_available:
                return await voyage.embed_documents(
                    texts, model="voyage-law-2", input_type="document"
                )
        except Exception as e:
            logger.warning("Voyage fallback import/call falhou: %s", e)

        # Último recurso: OpenAI
        try:
            from openai import AsyncOpenAI

            openai_key = os.getenv("OPENAI_API_KEY", "")
            if openai_key.strip():
                client = AsyncOpenAI(api_key=openai_key)
                openai_model = os.getenv("EMBEDDING_MODEL", "text-embedding-3-large")
                openai_dims = int(os.getenv("EMBEDDING_DIMENSIONS", "3072"))
                response = await client.embeddings.create(
                    model=openai_model,
                    input=texts,
                    dimensions=openai_dims,
                )
                sorted_data = sorted(response.data, key=lambda x: x.index)
                return [item.embedding for item in sorted_data]
        except Exception as e:
            logger.error("OpenAI fallback também falhou: %s", e)

        return [[0.0] * self._dimensions for _ in texts]


# ---------------------------------------------------------------------------
# Singleton e factory
# ---------------------------------------------------------------------------

_provider: Optional[KanonEmbeddingsProvider] = None
_provider_lock = threading.Lock()


def get_kanon_provider() -> KanonEmbeddingsProvider:
    """Retorna o singleton do KanonEmbeddingsProvider."""
    global _provider
    if _provider is not None:
        return _provider

    with _provider_lock:
        if _provider is None:
            _provider = KanonEmbeddingsProvider()

    return _provider


def reset_kanon_provider() -> None:
    """Reseta o singleton (útil para testes)."""
    global _provider
    with _provider_lock:
        _provider = None
        logger.info("KanonEmbeddingsProvider singleton resetado")


def is_kanon_available() -> bool:
    """Verifica se Kanon está disponível sem inicializar o provider."""
    return bool(os.getenv("ISAACUS_API_KEY", "").strip()) and (
        _ISAACUS_AVAILABLE or _HTTPX_AVAILABLE
    )
