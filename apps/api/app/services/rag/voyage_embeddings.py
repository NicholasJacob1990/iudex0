"""
Voyage AI Embeddings Provider para dominio juridico brasileiro.

Voyage AI oferece modelos especializados que superam OpenAI em benchmarks juridicos:
  - voyage-law-2: Especializado em dominio juridico (16K tokens, +6% vs OpenAI)
  - voyage-3-large: Geral multilingue de alta qualidade (32K tokens)
  - voyage-3-lite: Rapido e barato para uso em massa

Features:
  - Suporte a input_type ("document" vs "query") para otimizacao assimetrica
  - Batch processing com controle de rate limit
  - Retry com backoff exponencial
  - Fallback automatico: voyage-law-2 -> voyage-3-large -> OpenAI
  - Logging de custos (tokens processados)
  - Cache LRU de embeddings recentes
  - Configuracao via env vars: VOYAGE_API_KEY, VOYAGE_DEFAULT_MODEL
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import time
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Importacao condicional do SDK Voyage AI
# ---------------------------------------------------------------------------
try:
    import voyageai  # type: ignore
    from voyageai import AsyncClient as VoyageAsyncClient  # type: ignore

    _VOYAGE_AVAILABLE = True
except ImportError:
    voyageai = None  # type: ignore
    VoyageAsyncClient = None  # type: ignore
    _VOYAGE_AVAILABLE = False

# Fallback OpenAI (para cadeia de fallback)
try:
    from openai import AsyncOpenAI  # type: ignore

    _OPENAI_AVAILABLE = True
except ImportError:
    AsyncOpenAI = None  # type: ignore
    _OPENAI_AVAILABLE = False


# ---------------------------------------------------------------------------
# Tipos e constantes
# ---------------------------------------------------------------------------

InputType = Literal["document", "query"]


class VoyageModel(str, Enum):
    """Modelos Voyage AI disponiveis."""

    LEGAL = "voyage-law-2"
    GENERAL = "voyage-3-large"
    FAST = "voyage-3-lite"


# Mapa de dimensoes por modelo
MODEL_DIMENSIONS: Dict[str, int] = {
    VoyageModel.LEGAL: 1024,
    VoyageModel.GENERAL: 1024,
    VoyageModel.FAST: 512,
}

# Mapa de max tokens por modelo
MODEL_MAX_TOKENS: Dict[str, int] = {
    VoyageModel.LEGAL: 16000,
    VoyageModel.GENERAL: 32000,
    VoyageModel.FAST: 32000,
}

# Custo estimado por 1M tokens (USD) para logging
MODEL_COST_PER_1M_TOKENS: Dict[str, float] = {
    VoyageModel.LEGAL: 0.12,
    VoyageModel.GENERAL: 0.13,
    VoyageModel.FAST: 0.02,
}


# ---------------------------------------------------------------------------
# Cache LRU thread-safe
# ---------------------------------------------------------------------------


class LRUEmbeddingCache:
    """Cache LRU thread-safe para embeddings."""

    def __init__(self, max_size: int = 2048) -> None:
        self._cache: OrderedDict[str, List[float]] = OrderedDict()
        self._max_size = max_size
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    @staticmethod
    def _key(text: str, model: str, input_type: str) -> str:
        raw = f"{model}:{input_type}:{text}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get(self, text: str, model: str, input_type: str) -> Optional[List[float]]:
        key = self._key(text, model, input_type)
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                self._hits += 1
                return self._cache[key]
            self._misses += 1
            return None

    def set(self, text: str, model: str, input_type: str, embedding: List[float]) -> None:
        key = self._key(text, model, input_type)
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
# Metricas de custo
# ---------------------------------------------------------------------------


@dataclass
class VoyageCostTracker:
    """Rastreia custos de uso do Voyage AI."""

    total_tokens: int = 0
    total_requests: int = 0
    total_errors: int = 0
    total_fallbacks: int = 0
    tokens_by_model: Dict[str, int] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def record(self, model: str, tokens: int) -> None:
        with self._lock:
            self.total_tokens += tokens
            self.total_requests += 1
            self.tokens_by_model[model] = self.tokens_by_model.get(model, 0) + tokens

    def record_error(self) -> None:
        with self._lock:
            self.total_errors += 1

    def record_fallback(self) -> None:
        with self._lock:
            self.total_fallbacks += 1

    @property
    def estimated_cost_usd(self) -> float:
        with self._lock:
            cost = 0.0
            for model, tokens in self.tokens_by_model.items():
                rate = MODEL_COST_PER_1M_TOKENS.get(model, 0.12)
                cost += (tokens / 1_000_000) * rate
            return round(cost, 6)

    def to_dict(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "total_tokens": self.total_tokens,
                "total_requests": self.total_requests,
                "total_errors": self.total_errors,
                "total_fallbacks": self.total_fallbacks,
                "tokens_by_model": dict(self.tokens_by_model),
                "estimated_cost_usd": self.estimated_cost_usd,
            }


# ---------------------------------------------------------------------------
# Provider principal
# ---------------------------------------------------------------------------


class VoyageEmbeddingsProvider:
    """
    Provider de embeddings Voyage AI para dominio juridico.

    Modelos disponiveis:
        LEGAL_MODEL  = "voyage-law-2"      # Juridico especifico (16K tokens)
        GENERAL_MODEL = "voyage-3-large"   # Geral multilingue (32K tokens)
        FAST_MODEL   = "voyage-3-lite"     # Rapido e barato

    Uso:
        provider = VoyageEmbeddingsProvider()
        embeddings = await provider.embed_documents(["texto 1", "texto 2"])
        query_emb = await provider.embed_query("minha consulta juridica")
    """

    LEGAL_MODEL: str = VoyageModel.LEGAL
    GENERAL_MODEL: str = VoyageModel.GENERAL
    FAST_MODEL: str = VoyageModel.FAST

    def __init__(
        self,
        api_key: Optional[str] = None,
        default_model: Optional[str] = None,
        fallback_model: Optional[str] = None,
        cache_max_size: int = 2048,
        max_retries: int = 3,
        base_retry_delay: float = 1.0,
    ) -> None:
        """
        Inicializa o provider Voyage AI.

        Args:
            api_key: Chave da API Voyage. Fallback para env VOYAGE_API_KEY.
            default_model: Modelo padrao. Fallback para env VOYAGE_DEFAULT_MODEL.
            fallback_model: Modelo de fallback Voyage. Fallback para env VOYAGE_FALLBACK_MODEL.
            cache_max_size: Tamanho maximo do cache LRU.
            max_retries: Numero maximo de tentativas com backoff.
            base_retry_delay: Delay base para retry em segundos.
        """
        self._api_key = api_key or os.getenv("VOYAGE_API_KEY", "")
        self._default_model = (
            default_model
            or os.getenv("VOYAGE_DEFAULT_MODEL", VoyageModel.LEGAL)
        )
        self._fallback_model = (
            fallback_model
            or os.getenv("VOYAGE_FALLBACK_MODEL", VoyageModel.GENERAL)
        )
        self._max_retries = max_retries
        self._base_retry_delay = base_retry_delay

        # Cache
        self._cache = LRUEmbeddingCache(max_size=cache_max_size)

        # Metricas
        self._cost_tracker = VoyageCostTracker()

        # Cliente async (lazy init)
        self._client: Optional[Any] = None
        self._openai_client: Optional[Any] = None

        self._available = _VOYAGE_AVAILABLE and bool(self._api_key.strip())

        if self._available:
            logger.info(
                "VoyageEmbeddingsProvider inicializado: model=%s, fallback=%s",
                self._default_model,
                self._fallback_model,
            )
        else:
            if not _VOYAGE_AVAILABLE:
                logger.info(
                    "VoyageEmbeddingsProvider: SDK voyageai nao instalado. "
                    "Instale com: pip install voyageai"
                )
            else:
                logger.info(
                    "VoyageEmbeddingsProvider: VOYAGE_API_KEY nao configurada. "
                    "Voyage AI desabilitado, usando fallback OpenAI."
                )

    # ------------------------------------------------------------------
    # Propriedades
    # ------------------------------------------------------------------

    @property
    def is_available(self) -> bool:
        """Verifica se o provider Voyage esta disponivel e configurado."""
        return self._available

    @property
    def default_model(self) -> str:
        return self._default_model

    @property
    def dimensions(self) -> int:
        return MODEL_DIMENSIONS.get(self._default_model, 1024)

    @property
    def cost_tracker(self) -> VoyageCostTracker:
        return self._cost_tracker

    @property
    def cache_stats(self) -> Dict[str, Any]:
        return self._cache.stats

    # ------------------------------------------------------------------
    # Inicializacao lazy de clientes
    # ------------------------------------------------------------------

    def _get_voyage_client(self) -> Any:
        """Retorna o cliente async Voyage (lazy init)."""
        if self._client is None:
            if not _VOYAGE_AVAILABLE:
                raise RuntimeError("voyageai SDK nao instalado")
            self._client = VoyageAsyncClient(api_key=self._api_key)
        return self._client

    def _get_openai_client(self) -> Any:
        """Retorna o cliente async OpenAI para fallback (lazy init)."""
        if self._openai_client is None:
            if not _OPENAI_AVAILABLE:
                raise RuntimeError("openai SDK nao instalado para fallback")
            openai_key = os.getenv("OPENAI_API_KEY", "")
            if not openai_key.strip():
                raise RuntimeError("OPENAI_API_KEY nao configurada para fallback")
            self._openai_client = AsyncOpenAI(api_key=openai_key)
        return self._openai_client

    # ------------------------------------------------------------------
    # API publica
    # ------------------------------------------------------------------

    async def embed_documents(
        self,
        texts: List[str],
        *,
        model: Optional[str] = None,
        input_type: InputType = "document",
    ) -> List[List[float]]:
        """
        Gera embeddings para uma lista de documentos.

        Args:
            texts: Lista de textos para gerar embeddings.
            model: Modelo Voyage a usar. None = default_model.
            input_type: Tipo de input ("document" ou "query").

        Returns:
            Lista de vetores de embedding.
        """
        if not texts:
            return []

        model = model or self._default_model
        return await self._embed_with_fallback(texts, model=model, input_type=input_type)

    async def embed_query(
        self,
        text: str,
        *,
        model: Optional[str] = None,
        input_type: InputType = "query",
    ) -> List[float]:
        """
        Gera embedding para uma unica query.

        Args:
            text: Texto da query.
            model: Modelo Voyage a usar. None = default_model.
            input_type: Tipo de input (default "query" para otimizacao assimetrica).

        Returns:
            Vetor de embedding.
        """
        if not text or not text.strip():
            dim = MODEL_DIMENSIONS.get(model or self._default_model, 1024)
            return [0.0] * dim

        model = model or self._default_model

        # Verificar cache
        cached = self._cache.get(text, model, input_type)
        if cached is not None:
            return cached

        results = await self._embed_with_fallback(
            [text], model=model, input_type=input_type
        )
        if results:
            self._cache.set(text, model, input_type, results[0])
            return results[0]

        dim = MODEL_DIMENSIONS.get(model, 1024)
        return [0.0] * dim

    async def embed_batch(
        self,
        texts: List[str],
        *,
        model: Optional[str] = None,
        input_type: InputType = "document",
        batch_size: int = 128,
    ) -> List[List[float]]:
        """
        Gera embeddings em lotes com controle de rate limit.

        Args:
            texts: Lista de textos.
            model: Modelo Voyage.
            input_type: Tipo de input.
            batch_size: Tamanho de cada lote.

        Returns:
            Lista de vetores de embedding.
        """
        if not texts:
            return []

        model = model or self._default_model
        all_embeddings: List[List[float]] = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            batch_embeddings = await self._embed_with_fallback(
                batch, model=model, input_type=input_type
            )
            all_embeddings.extend(batch_embeddings)

            # Rate limit: aguardar entre batches se nao for o ultimo
            if i + batch_size < len(texts):
                await asyncio.sleep(0.1)

        logger.info(
            "Voyage batch embedding: %d textos em %d lotes (model=%s)",
            len(texts),
            (len(texts) + batch_size - 1) // batch_size,
            model,
        )
        return all_embeddings

    def clear_cache(self) -> int:
        """Limpa o cache de embeddings. Retorna o numero de entradas removidas."""
        return self._cache.clear()

    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatisticas completas do provider."""
        return {
            "available": self._available,
            "default_model": self._default_model,
            "fallback_model": self._fallback_model,
            "dimensions": self.dimensions,
            "cache": self._cache.stats,
            "costs": self._cost_tracker.to_dict(),
        }

    # ------------------------------------------------------------------
    # Logica interna: chamada com fallback
    # ------------------------------------------------------------------

    async def _embed_with_fallback(
        self,
        texts: List[str],
        *,
        model: str,
        input_type: InputType,
    ) -> List[List[float]]:
        """
        Tenta gerar embeddings com cadeia de fallback:
          1. Voyage AI (modelo solicitado)
          2. Voyage AI (modelo de fallback)
          3. OpenAI (text-embedding-3-large)

        Cada nivel tem retry com backoff exponencial.
        """
        # Filtrar textos vazios mantendo indices
        clean_texts = [t.strip() if t else "" for t in texts]

        # Nivel 1: Voyage com modelo solicitado
        if self._available:
            try:
                result = await self._call_voyage_with_retry(
                    clean_texts, model=model, input_type=input_type
                )
                if result is not None:
                    return result
            except Exception as e:
                logger.warning("Voyage AI (%s) falhou: %s", model, e)
                self._cost_tracker.record_error()

        # Nivel 2: Voyage com modelo de fallback
        if self._available and model != self._fallback_model:
            try:
                logger.info(
                    "Tentando fallback Voyage: %s -> %s",
                    model,
                    self._fallback_model,
                )
                self._cost_tracker.record_fallback()
                result = await self._call_voyage_with_retry(
                    clean_texts,
                    model=self._fallback_model,
                    input_type=input_type,
                )
                if result is not None:
                    return result
            except Exception as e:
                logger.warning(
                    "Voyage AI fallback (%s) falhou: %s",
                    self._fallback_model,
                    e,
                )
                self._cost_tracker.record_error()

        # Nivel 3: OpenAI como ultimo recurso
        if _OPENAI_AVAILABLE and os.getenv("OPENAI_API_KEY", "").strip():
            try:
                logger.info("Fallback para OpenAI embeddings")
                self._cost_tracker.record_fallback()
                return await self._call_openai_fallback(clean_texts)
            except Exception as e:
                logger.error("OpenAI fallback tambem falhou: %s", e)
                self._cost_tracker.record_error()

        # Tudo falhou: retornar vetores zero
        dim = MODEL_DIMENSIONS.get(model, 1024)
        logger.error(
            "Todos os providers de embedding falharam. Retornando vetores zero."
        )
        return [[0.0] * dim for _ in texts]

    # ------------------------------------------------------------------
    # Chamada Voyage com retry
    # ------------------------------------------------------------------

    async def _call_voyage_with_retry(
        self,
        texts: List[str],
        *,
        model: str,
        input_type: InputType,
    ) -> Optional[List[List[float]]]:
        """
        Chama a API Voyage com retry e backoff exponencial.

        Returns:
            Lista de embeddings ou None se todas as tentativas falharam.
        """
        client = self._get_voyage_client()
        last_error: Optional[Exception] = None

        for attempt in range(self._max_retries):
            try:
                start = time.time()
                response = await client.embed(
                    texts,
                    model=model,
                    input_type=input_type,
                )
                elapsed_ms = (time.time() - start) * 1000

                embeddings = response.embeddings
                total_tokens = getattr(response, "total_tokens", 0) or 0

                self._cost_tracker.record(model, total_tokens)

                logger.debug(
                    "Voyage embed OK: model=%s, texts=%d, tokens=%d, time=%.1fms",
                    model,
                    len(texts),
                    total_tokens,
                    elapsed_ms,
                )
                return embeddings  # type: ignore[return-value]

            except Exception as e:
                last_error = e
                if attempt < self._max_retries - 1:
                    delay = self._base_retry_delay * (2**attempt)
                    logger.warning(
                        "Voyage embed tentativa %d/%d falhou: %s. Retry em %.1fs",
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
    # Fallback OpenAI
    # ------------------------------------------------------------------

    async def _call_openai_fallback(
        self,
        texts: List[str],
    ) -> List[List[float]]:
        """Fallback para OpenAI embeddings quando Voyage falha."""
        client = self._get_openai_client()

        openai_model = os.getenv("EMBEDDING_MODEL", "text-embedding-3-large")
        openai_dims = int(os.getenv("EMBEDDING_DIMENSIONS", "3072"))

        response = await client.embeddings.create(
            model=openai_model,
            input=texts,
            dimensions=openai_dims,
        )

        sorted_data = sorted(response.data, key=lambda x: x.index)
        return [item.embedding for item in sorted_data]


# ---------------------------------------------------------------------------
# Singleton e factory
# ---------------------------------------------------------------------------

_provider: Optional[VoyageEmbeddingsProvider] = None
_provider_lock = threading.Lock()


def get_voyage_provider() -> VoyageEmbeddingsProvider:
    """Retorna o singleton do VoyageEmbeddingsProvider."""
    global _provider
    if _provider is not None:
        return _provider

    with _provider_lock:
        if _provider is None:
            _provider = VoyageEmbeddingsProvider()

    return _provider


def reset_voyage_provider() -> None:
    """Reseta o singleton (util para testes)."""
    global _provider
    with _provider_lock:
        _provider = None
        logger.info("VoyageEmbeddingsProvider singleton resetado")


def is_voyage_available() -> bool:
    """Verifica se Voyage AI esta disponivel sem inicializar o provider."""
    return _VOYAGE_AVAILABLE and bool(os.getenv("VOYAGE_API_KEY", "").strip())
