from __future__ import annotations

import hashlib
import threading
import time
from typing import Dict, List, Optional, Tuple

from openai import OpenAI


class EmbeddingsClient:
    """
    - Uses OpenAI embeddings API.
    - Adds an in-memory TTL cache for query embeddings (fast win for repeated queries).
    - Supports batch embedding for ingestion (much faster than per-chunk requests).
    """

    def __init__(self, api_key: str, model: str, dimensions: Optional[int]):
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.dimensions = dimensions

        # cache: key -> (expires_at_epoch, embedding)
        self._cache: Dict[str, Tuple[float, List[float]]] = {}
        self._lock = threading.RLock()
        self._max_items = 10_000

    def _make_key(self, text: str) -> str:
        norm = (text or "").replace("\n", " ").strip()
        h = hashlib.sha256(norm.encode("utf-8", errors="ignore")).hexdigest()
        return f"{self.model}|{self.dimensions or 'default'}|{h}"

    def embed_one(self, text: str) -> List[float]:
        """No cache (useful for ingestion)."""
        text = (text or "").replace("\n", " ").strip()
        if not text:
            return []
        kwargs = {"input": [text], "model": self.model}
        if self.dimensions:
            kwargs["dimensions"] = self.dimensions
        resp = self.client.embeddings.create(**kwargs)
        return resp.data[0].embedding

    def embed_query(self, text: str, ttl_seconds: int = 3600) -> List[float]:
        """Cached (useful for repeated user queries)."""
        text = (text or "").replace("\n", " ").strip()
        if not text:
            return []
        key = self._make_key(text)
        now = time.time()

        with self._lock:
            item = self._cache.get(key)
            if item and item[0] > now:
                return item[1]

        vec = self.embed_one(text)

        with self._lock:
            if len(self._cache) >= self._max_items:
                # drop expired first
                expired = [k for k, (exp, _) in self._cache.items() if exp <= now]
                for k in expired[:2000]:
                    self._cache.pop(k, None)
                # still large -> drop a slice
                if len(self._cache) >= self._max_items:
                    for k in list(self._cache.keys())[:1000]:
                        self._cache.pop(k, None)

            self._cache[key] = (now + ttl_seconds, vec)

        return vec

    def embed_many(self, texts: List[str], batch_size: int = 64) -> List[List[float]]:
        """
        Batch embeddings for ingestion.
        Keeps order.
        """
        cleaned = [(t or "").replace("\n", " ").strip() for t in texts]
        embeddings: List[List[float]] = []
        for i in range(0, len(cleaned), batch_size):
            batch = cleaned[i : i + batch_size]
            mask = [bool(x) for x in batch]
            safe_batch = [x if x else " " for x in batch]

            kwargs = {"input": safe_batch, "model": self.model}
            if self.dimensions:
                kwargs["dimensions"] = self.dimensions

            resp = self.client.embeddings.create(**kwargs)
            for ok, item in zip(mask, resp.data):
                embeddings.append(item.embedding if ok else [])

        return embeddings
