"""
JurisBERT Embeddings Provider — Embeddings para direito brasileiro.

Baseado no modelo juridics/bertlaw-base-portuguese-sts-scale (HuggingFace),
um sentence-transformer treinado especificamente para textos jurídicos
brasileiros com STS (Semantic Textual Similarity).

Especificações:
  - Dimensões: 768
  - Max sequence length: 384 tokens
  - Arquitetura: BertModel + Mean Pooling
  - Treinamento: Corpus jurídico brasileiro (STF, STJ, tribunais)

Features:
  - Self-hosted via sentence-transformers (sem API externa)
  - Lazy loading (modelo só carrega quando necessário)
  - GPU support opcional (CUDA)
  - Fallback para voyage-multilingual-2 se modelo não disponível
  - Cache LRU thread-safe
  - Thread-safe para uso em FastAPI
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Importação condicional
# ---------------------------------------------------------------------------
try:
    from sentence_transformers import SentenceTransformer  # type: ignore
    import torch  # type: ignore

    _ST_AVAILABLE = True
except ImportError:
    SentenceTransformer = None  # type: ignore
    torch = None  # type: ignore
    _ST_AVAILABLE = False

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

# Modelo HuggingFace verificado:
# juridics/bertlaw-base-portuguese-sts-scale — sentence-transformer para STS jurídico PT-BR
# Alternativas possíveis:
#   - alfaneo/jurisbert-base-portuguese-sts (mesmo modelo, namespace anterior)
#   - dominguesm/legal-bert-base-cased-ptbr (BERT base, não sentence-transformer)
DEFAULT_MODEL_NAME = "juridics/bertlaw-base-portuguese-sts-scale"

JURISBERT_DIMENSIONS = 768
JURISBERT_MAX_SEQ_LENGTH = 384


# ---------------------------------------------------------------------------
# Cache LRU thread-safe
# ---------------------------------------------------------------------------


class _JurisBERTCache:
    """Cache LRU thread-safe para embeddings JurisBERT."""

    def __init__(self, max_size: int = 4096) -> None:
        self._cache: OrderedDict[str, List[float]] = OrderedDict()
        self._max_size = max_size
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    @staticmethod
    def _key(text: str) -> str:
        return hashlib.sha256(f"jurisbert:{text}".encode("utf-8")).hexdigest()

    def get(self, text: str) -> Optional[List[float]]:
        key = self._key(text)
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                self._hits += 1
                return self._cache[key]
            self._misses += 1
            return None

    def set(self, text: str, embedding: List[float]) -> None:
        key = self._key(text)
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
# Métricas
# ---------------------------------------------------------------------------


@dataclass
class JurisBERTMetrics:
    """Métricas de uso do JurisBERT."""

    total_texts: int = 0
    total_requests: int = 0
    total_errors: int = 0
    total_fallbacks: int = 0
    total_time_ms: float = 0.0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def record(self, texts_count: int, time_ms: float) -> None:
        with self._lock:
            self.total_texts += texts_count
            self.total_requests += 1
            self.total_time_ms += time_ms

    def record_error(self) -> None:
        with self._lock:
            self.total_errors += 1

    def record_fallback(self) -> None:
        with self._lock:
            self.total_fallbacks += 1

    def to_dict(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "total_texts": self.total_texts,
                "total_requests": self.total_requests,
                "total_errors": self.total_errors,
                "total_fallbacks": self.total_fallbacks,
                "avg_time_ms": (
                    round(self.total_time_ms / self.total_requests, 2)
                    if self.total_requests > 0
                    else 0.0
                ),
            }


# ---------------------------------------------------------------------------
# Provider principal
# ---------------------------------------------------------------------------


class JurisBERTProvider:
    """
    Provider de embeddings JurisBERT para direito brasileiro.

    Self-hosted via sentence-transformers. O modelo é carregado
    sob demanda (lazy loading) e mantido em memória.

    Uso:
        provider = JurisBERTProvider()
        embeddings = await provider.embed_documents(["texto jurídico"])
        query_emb = await provider.embed_query("consulta jurídica")
    """

    def __init__(
        self,
        model_name: Optional[str] = None,
        device: Optional[str] = None,
        cache_max_size: int = 4096,
        max_workers: int = 2,
    ) -> None:
        """
        Inicializa o provider JurisBERT.

        Args:
            model_name: Nome do modelo HuggingFace. Default: juridics/bertlaw-base-portuguese-sts-scale
            device: Dispositivo para inferência ("cpu", "cuda", "mps"). Auto-detecta se None.
            cache_max_size: Tamanho máximo do cache LRU.
            max_workers: Threads para inferência assíncrona.
        """
        self._model_name = model_name or os.getenv(
            "JURISBERT_MODEL_NAME", DEFAULT_MODEL_NAME
        )
        self._device = device or os.getenv("JURISBERT_DEVICE", "auto")
        self._max_workers = max_workers

        # Cache
        self._cache = _JurisBERTCache(max_size=cache_max_size)

        # Métricas
        self._metrics = JurisBERTMetrics()

        # Modelo (lazy init)
        self._model: Optional[Any] = None
        self._model_lock = threading.Lock()
        self._model_loaded = False
        self._model_load_error: Optional[str] = None

        # Thread pool para não bloquear event loop
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="jurisbert"
        )

        self._available = _ST_AVAILABLE

        if self._available:
            logger.info(
                "JurisBERTProvider criado (lazy init): model=%s, device=%s",
                self._model_name,
                self._device,
            )
        else:
            logger.info(
                "JurisBERTProvider: sentence-transformers não instalado. "
                "Instale com: pip install sentence-transformers"
            )

    # ------------------------------------------------------------------
    # Propriedades
    # ------------------------------------------------------------------

    @property
    def is_available(self) -> bool:
        """Verifica se o provider está disponível (dependências instaladas)."""
        return self._available

    @property
    def is_loaded(self) -> bool:
        """Verifica se o modelo já foi carregado em memória."""
        return self._model_loaded

    @property
    def dimensions(self) -> int:
        return JURISBERT_DIMENSIONS

    @property
    def metrics(self) -> JurisBERTMetrics:
        return self._metrics

    @property
    def cache_stats(self) -> Dict[str, Any]:
        return self._cache.stats

    # ------------------------------------------------------------------
    # Lazy loading do modelo
    # ------------------------------------------------------------------

    def _ensure_model_loaded(self) -> Any:
        """Carrega o modelo sob demanda (thread-safe)."""
        if self._model is not None:
            return self._model

        with self._model_lock:
            if self._model is not None:
                return self._model

            if not _ST_AVAILABLE:
                raise RuntimeError(
                    "sentence-transformers não instalado. "
                    "Instale com: pip install sentence-transformers"
                )

            try:
                logger.info(
                    "JurisBERT: carregando modelo %s (pode levar alguns segundos)...",
                    self._model_name,
                )
                start = time.time()

                # Detectar device
                device = self._resolve_device()

                self._model = SentenceTransformer(
                    self._model_name, device=device
                )
                self._model_loaded = True
                elapsed = time.time() - start

                actual_dim = self._model.get_sentence_embedding_dimension()
                logger.info(
                    "JurisBERT: modelo carregado em %.1fs (device=%s, dim=%d)",
                    elapsed,
                    device,
                    actual_dim,
                )

                return self._model

            except Exception as e:
                self._model_load_error = str(e)
                logger.error("JurisBERT: falha ao carregar modelo: %s", e)
                raise

    def _resolve_device(self) -> str:
        """Resolve o dispositivo de inferência."""
        if self._device == "auto":
            if torch is not None:
                if torch.cuda.is_available():
                    return "cuda"
                if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                    return "mps"
            return "cpu"
        return self._device

    # ------------------------------------------------------------------
    # API pública (async)
    # ------------------------------------------------------------------

    async def embed_documents(
        self,
        texts: List[str],
    ) -> List[List[float]]:
        """
        Gera embeddings para documentos jurídicos brasileiros.

        Args:
            texts: Lista de textos.

        Returns:
            Lista de vetores de embedding (768d).
        """
        if not texts:
            return []

        return await self._embed_with_fallback(texts)

    async def embed_query(
        self,
        text: str,
    ) -> List[float]:
        """
        Gera embedding para uma query de busca.

        Args:
            text: Texto da query.

        Returns:
            Vetor de embedding (768d).
        """
        if not text or not text.strip():
            return [0.0] * JURISBERT_DIMENSIONS

        # Cache check
        cached = self._cache.get(text)
        if cached is not None:
            return cached

        results = await self._embed_with_fallback([text])
        if results:
            self._cache.set(text, results[0])
            return results[0]

        return [0.0] * JURISBERT_DIMENSIONS

    async def embed_batch(
        self,
        texts: List[str],
        *,
        batch_size: int = 64,
    ) -> List[List[float]]:
        """
        Gera embeddings em lotes.

        Args:
            texts: Lista de textos.
            batch_size: Tamanho de cada lote.

        Returns:
            Lista de vetores de embedding.
        """
        if not texts:
            return []

        all_embeddings: List[List[float]] = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            batch_embeddings = await self._embed_with_fallback(batch)
            all_embeddings.extend(batch_embeddings)

        logger.info(
            "JurisBERT batch: %d textos em %d lotes",
            len(texts),
            (len(texts) + batch_size - 1) // batch_size,
        )
        return all_embeddings

    def clear_cache(self) -> int:
        return self._cache.clear()

    def get_stats(self) -> Dict[str, Any]:
        return {
            "available": self._available,
            "loaded": self._model_loaded,
            "model": self._model_name,
            "device": self._device,
            "dimensions": JURISBERT_DIMENSIONS,
            "load_error": self._model_load_error,
            "cache": self._cache.stats,
            "metrics": self._metrics.to_dict(),
        }

    # ------------------------------------------------------------------
    # Lógica interna
    # ------------------------------------------------------------------

    async def _embed_with_fallback(
        self,
        texts: List[str],
    ) -> List[List[float]]:
        """
        Tenta gerar embeddings com cadeia de fallback:
          1. JurisBERT local (sentence-transformers)
          2. Voyage multilingual-2 (API)
          3. OpenAI text-embedding-3-large
        """
        clean_texts = [t.strip() if t else "" for t in texts]

        # Nível 1: JurisBERT local
        if self._available:
            try:
                result = await self._encode_local(clean_texts)
                if result is not None:
                    return result
            except Exception as e:
                logger.warning("JurisBERT local falhou: %s", e)
                self._metrics.record_error()

        # Nível 2: Voyage multilingual-2
        try:
            logger.info("JurisBERT fallback para voyage-multilingual-2")
            self._metrics.record_fallback()
            return await self._call_voyage_fallback(clean_texts)
        except Exception as e:
            logger.warning("Voyage multilingual fallback falhou: %s", e)
            self._metrics.record_error()

        # Nível 3: OpenAI
        try:
            logger.info("JurisBERT fallback para OpenAI")
            self._metrics.record_fallback()
            return await self._call_openai_fallback(clean_texts)
        except Exception as e:
            logger.error("OpenAI fallback também falhou: %s", e)
            self._metrics.record_error()

        # Tudo falhou
        logger.error("Todos os providers BR falharam. Vetores zero.")
        return [[0.0] * JURISBERT_DIMENSIONS for _ in texts]

    async def _encode_local(
        self,
        texts: List[str],
    ) -> Optional[List[List[float]]]:
        """Gera embeddings usando modelo local em thread separada."""
        loop = asyncio.get_event_loop()

        def _sync_encode() -> List[List[float]]:
            model = self._ensure_model_loaded()
            start = time.time()
            vectors = model.encode(
                texts,
                normalize_embeddings=True,
                show_progress_bar=False,
                batch_size=min(64, len(texts)),
            )
            elapsed_ms = (time.time() - start) * 1000
            self._metrics.record(len(texts), elapsed_ms)

            logger.debug(
                "JurisBERT encode: %d textos em %.1fms", len(texts), elapsed_ms
            )

            return [[float(x) for x in v.tolist()] for v in vectors]

        return await loop.run_in_executor(self._executor, _sync_encode)

    async def _call_voyage_fallback(
        self,
        texts: List[str],
    ) -> List[List[float]]:
        """Fallback para Voyage multilingual quando JurisBERT não disponível."""
        try:
            from app.services.rag.voyage_embeddings import get_voyage_provider

            voyage = get_voyage_provider()
            if voyage.is_available:
                # voyage-3-large é multilingual e tem boa performance em PT-BR
                return await voyage.embed_documents(
                    texts, model="voyage-3-large", input_type="document"
                )
        except Exception as e:
            logger.warning("Voyage multilingual fallback falhou: %s", e)
            raise

        raise RuntimeError("Voyage provider não disponível")

    async def _call_openai_fallback(
        self,
        texts: List[str],
    ) -> List[List[float]]:
        """Fallback para OpenAI."""
        try:
            from openai import AsyncOpenAI

            openai_key = os.getenv("OPENAI_API_KEY", "")
            if not openai_key.strip():
                raise RuntimeError("OPENAI_API_KEY não configurada")

            client = AsyncOpenAI(api_key=openai_key)
            # Matryoshka reduction to match JurisBERT 768d collection
            response = await client.embeddings.create(
                model="text-embedding-3-large",
                input=texts,
                dimensions=JURISBERT_DIMENSIONS,
            )
            sorted_data = sorted(response.data, key=lambda x: x.index)
            return [item.embedding for item in sorted_data]
        except Exception as e:
            logger.error("OpenAI fallback falhou: %s", e)
            raise


# ---------------------------------------------------------------------------
# Singleton e factory
# ---------------------------------------------------------------------------

_provider: Optional[JurisBERTProvider] = None
_provider_lock = threading.Lock()


def get_jurisbert_provider() -> JurisBERTProvider:
    """Retorna o singleton do JurisBERTProvider."""
    global _provider
    if _provider is not None:
        return _provider

    with _provider_lock:
        if _provider is None:
            _provider = JurisBERTProvider()

    return _provider


def reset_jurisbert_provider() -> None:
    """Reseta o singleton (útil para testes)."""
    global _provider
    with _provider_lock:
        _provider = None
        logger.info("JurisBERTProvider singleton resetado")


def is_jurisbert_available() -> bool:
    """Verifica se JurisBERT está disponível sem inicializar."""
    return _ST_AVAILABLE
