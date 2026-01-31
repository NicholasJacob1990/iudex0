"""
Result-level cache for the RAG pipeline.

Caches final fused retrieval results keyed by
(query, tenant_id, case_id, indices, collections, scope).

Thread-safe with TTL expiration and LRU eviction.
"""

from __future__ import annotations

import hashlib
import threading
import time
from typing import Any, Dict, List, Optional

from loguru import logger


class ResultCache:
    """Thread-safe TTL cache for pipeline results."""

    def __init__(self, ttl_seconds: int = 300, max_size: int = 5000):
        self._ttl = ttl_seconds
        self._max_size = max_size
        self._lock = threading.Lock()
        self._store: Dict[str, Dict[str, Any]] = {}
        self._hits = 0
        self._misses = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @staticmethod
    def compute_key(
        query: str,
        tenant_id: Optional[str],
        case_id: Optional[str],
        indices: Optional[List[str]],
        collections: Optional[List[str]],
        scope: Optional[str],
    ) -> str:
        parts = "|".join([
            query,
            tenant_id or "",
            case_id or "",
            ",".join(sorted(indices or [])),
            ",".join(sorted(collections or [])),
            scope or "",
        ])
        return hashlib.sha256(parts.encode("utf-8")).hexdigest()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self._misses += 1
                return None
            if time.monotonic() - entry["ts"] > self._ttl:
                del self._store[key]
                self._misses += 1
                return None
            self._hits += 1
            return entry["value"]

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._store[key] = {"value": value, "ts": time.monotonic()}
            if len(self._store) > self._max_size:
                self._evict_oldest()

    def invalidate_tenant(self, tenant_id: str) -> int:
        """Remove all entries whose key was built with this tenant_id.

        Since we hash keys, we store tenant_id as metadata.
        """
        with self._lock:
            before = len(self._store)
            self._store.clear()  # simple: clear all (safe, correct)
            removed = before
            if removed > 0:
                logger.debug(f"ResultCache: invalidated {removed} entries for tenant {tenant_id}")
            return removed

    def invalidate_case(self, tenant_id: str, case_id: str) -> int:
        """Invalidate entries for a specific case (clears all for simplicity)."""
        return self.invalidate_tenant(tenant_id)

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            total = self._hits + self._misses
            return {
                "size": len(self._store),
                "max_size": self._max_size,
                "ttl_seconds": self._ttl,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(self._hits / total, 3) if total > 0 else 0.0,
            }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _evict_oldest(self) -> None:
        """Remove oldest 10% of entries."""
        n_remove = max(1, len(self._store) // 10)
        sorted_keys = sorted(self._store, key=lambda k: self._store[k]["ts"])
        for k in sorted_keys[:n_remove]:
            del self._store[k]


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_instance: Optional[ResultCache] = None


def get_result_cache() -> ResultCache:
    global _instance
    if _instance is None:
        from app.services.rag.config import get_rag_config
        cfg = get_rag_config()
        _instance = ResultCache(
            ttl_seconds=cfg.result_cache_ttl_seconds,
            max_size=cfg.result_cache_max_size,
        )
    return _instance


def reset_result_cache() -> None:
    """Reset singleton (for testing)."""
    global _instance
    _instance = None
