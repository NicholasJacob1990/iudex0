"""
CogGRAG Memory Nodes — Consultation memory for context reuse.

Implements Phase 2.5 memory pattern from Cog-RAG (2511.13201):
- memory_check_node: Look up similar past consultations
- memory_store_node: Store current consultation for future retrieval

Memory is optional and feature-flagged. When disabled, nodes pass through.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.services.rag.config import get_rag_config

logger = logging.getLogger("rag.cograg.memory")

def _get_graph_memory():
    """
    Lazy import to avoid hard dependency on Neo4j in environments/tests.
    Returns CognitiveMemory instance or None.
    """
    try:
        from app.services.rag.core.cograg.memory import CognitiveMemory
        return CognitiveMemory.from_neo4j_service()
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════════════════
# Memory Backend (Simple File-Based for MVP)
# ═══════════════════════════════════════════════════════════════════════════

class ConsultationMemory:
    """
    Simple file-based memory store for consultation history.

    Production: Replace with Redis, PostgreSQL, or vector store.
    MVP: JSON files in data directory, keyed by query hash.
    """

    def __init__(self, data_dir: Optional[Path] = None):
        if data_dir is None:
            # Default to app/data/cograg_memory
            self.data_dir = Path(__file__).parent.parent.parent.parent.parent / "data" / "cograg_memory"
        else:
            self.data_dir = data_dir

        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._index_file = self.data_dir / "_index.json"
        self._index: Dict[str, Dict[str, Any]] = self._load_index()

    def _load_index(self) -> Dict[str, Dict[str, Any]]:
        """Load the memory index from disk."""
        if self._index_file.exists():
            try:
                with open(self._index_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                logger.warning("[CogGRAG:Memory] Failed to load index, starting fresh")
        return {}

    def _save_index(self) -> None:
        """Save the memory index to disk."""
        try:
            with open(self._index_file, "w", encoding="utf-8") as f:
                json.dump(self._index, f, ensure_ascii=False, indent=2)
        except IOError as e:
            logger.error(f"[CogGRAG:Memory] Failed to save index: {e}")

    def _query_hash(self, query: str) -> str:
        """Generate a hash for a query."""
        normalized = query.lower().strip()
        return hashlib.md5(normalized.encode("utf-8")).hexdigest()[:16]

    def _extract_keywords(self, query: str) -> List[str]:
        """Extract keywords from query for similarity matching."""
        import re

        # Remove common words
        stopwords = {
            "o", "a", "os", "as", "um", "uma", "uns", "umas",
            "de", "da", "do", "das", "dos", "em", "na", "no", "nas", "nos",
            "para", "por", "com", "sem", "sobre", "entre", "até", "como",
            "que", "qual", "quais", "quando", "onde", "porque", "porquê",
            "e", "ou", "mas", "se", "não", "é", "são", "foi", "foram",
            "ser", "estar", "ter", "haver", "pode", "podem", "deve", "devem",
        }

        words = re.findall(r"\b\w{3,}\b", query.lower())
        keywords = [w for w in words if w not in stopwords]
        return keywords[:20]  # Limit to 20 keywords

    def find_similar(
        self,
        query: str,
        tenant_id: str,
        threshold: float = 0.5,
        limit: int = 3,
    ) -> List[Dict[str, Any]]:
        """
        Find similar past consultations.

        Uses keyword overlap (Jaccard similarity) for MVP.
        Production: Use embedding similarity with vector store.
        """
        query_keywords = set(self._extract_keywords(query))
        if not query_keywords:
            return []

        candidates: List[tuple] = []

        for entry_id, meta in self._index.items():
            # Filter by tenant
            if meta.get("tenant_id") != tenant_id:
                continue

            # Compute keyword overlap
            stored_keywords = set(meta.get("keywords", []))
            if not stored_keywords:
                continue

            intersection = query_keywords & stored_keywords
            union = query_keywords | stored_keywords
            similarity = len(intersection) / len(union) if union else 0.0

            if similarity >= threshold:
                candidates.append((similarity, entry_id, meta))

        # Sort by similarity descending
        candidates.sort(key=lambda x: x[0], reverse=True)

        results = []
        for similarity, entry_id, meta in candidates[:limit]:
            # Load full consultation data
            entry_file = self.data_dir / f"{entry_id}.json"
            if entry_file.exists():
                try:
                    with open(entry_file, "r", encoding="utf-8") as f:
                        full_data = json.load(f)
                    results.append({
                        "entry_id": entry_id,
                        "similarity": round(similarity, 3),
                        "query": meta.get("query", ""),
                        "created_at": meta.get("created_at", ""),
                        "mind_map": full_data.get("mind_map"),
                        "sub_questions": full_data.get("sub_questions", []),
                        "answer_summary": full_data.get("answer_summary"),
                    })
                except (json.JSONDecodeError, IOError):
                    continue

        return results

    def store(
        self,
        query: str,
        tenant_id: str,
        mind_map: Optional[Dict[str, Any]],
        sub_questions: List[Dict[str, Any]],
        evidence_map: Dict[str, Any],
        answer_summary: Optional[str] = None,
    ) -> str:
        """
        Store a consultation in memory.

        Returns the entry ID.
        """
        import datetime

        entry_id = self._query_hash(query)
        keywords = self._extract_keywords(query)
        created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # Store metadata in index
        self._index[entry_id] = {
            "query": query[:200],  # Truncate for index
            "tenant_id": tenant_id,
            "keywords": keywords,
            "created_at": created_at,
            "sub_question_count": len(sub_questions),
        }
        self._save_index()

        # Store full data in separate file
        full_data = {
            "query": query,
            "tenant_id": tenant_id,
            "mind_map": mind_map,
            "sub_questions": sub_questions,
            "evidence_map": evidence_map,
            "answer_summary": answer_summary,
            "created_at": created_at,
        }

        entry_file = self.data_dir / f"{entry_id}.json"
        try:
            with open(entry_file, "w", encoding="utf-8") as f:
                json.dump(full_data, f, ensure_ascii=False, indent=2)
            logger.debug(f"[CogGRAG:Memory] Stored consultation {entry_id}")
        except IOError as e:
            logger.error(f"[CogGRAG:Memory] Failed to store consultation: {e}")

        return entry_id

    def count(self, tenant_id: Optional[str] = None) -> int:
        """Count stored consultations, optionally filtered by tenant."""
        if tenant_id is None:
            return len(self._index)
        return sum(1 for m in self._index.values() if m.get("tenant_id") == tenant_id)


# Global memory instance (lazy init)
_memory_instance: Optional[ConsultationMemory] = None


def get_consultation_memory() -> ConsultationMemory:
    """Get or create the global consultation memory instance."""
    global _memory_instance
    if _memory_instance is None:
        _memory_instance = ConsultationMemory()
    return _memory_instance


# ═══════════════════════════════════════════════════════════════════════════
# Memory Check Node
# ═══════════════════════════════════════════════════════════════════════════

async def memory_check_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    LangGraph node: check for similar past consultations.

    Reads from state:
        - query: original query
        - tenant_id
        - cograg_memory_enabled (from config injection)

    Writes to state:
        - similar_consultation: Dict with similar past consultation or None
        - metrics.memory_check_*
    """
    query: str = state.get("query", "")
    tenant_id: str = state.get("tenant_id", "default")
    memory_enabled: bool = state.get("cograg_memory_enabled", False)
    backend: str = str(state.get("cograg_memory_backend", "auto") or "auto").strip().lower()
    # Respect explicit backend choice; only force Neo4j when backend is auto.
    try:
        if backend in ("", "auto") and get_rag_config().neo4j_only:
            backend = "neo4j"
    except Exception:
        pass
    threshold: float = float(state.get("cograg_memory_similarity_threshold", 0.85))
    start = time.time()

    if not memory_enabled:
        logger.debug("[CogGRAG:MemoryCheck] Memory disabled → skip")
        return {
            "similar_consultation": None,
            "metrics": {
                **state.get("metrics", {}),
                "memory_check_latency_ms": 0,
                "memory_check_enabled": False,
            },
        }

    if not query:
        return {
            "similar_consultation": None,
            "metrics": {
                **state.get("metrics", {}),
                "memory_check_latency_ms": 0,
            },
        }

    logger.info(f"[CogGRAG:MemoryCheck] Searching for similar consultations")

    # Prefer Neo4j memory if available (PLANO_COGRAG.md expectation).
    similar_best: Optional[Dict[str, Any]] = None
    memory_source = "neo4j" if backend == "neo4j" else "file"

    graph_memory = _get_graph_memory() if backend in ("auto", "neo4j") else None
    if graph_memory is not None:
        try:
            hit = graph_memory.find_similar_consultation(
                query=query,
                tenant_id=tenant_id,
                threshold=threshold,
                limit=1,
            )
            if hit is not None:
                similar_best = hit.to_dict()
                memory_source = "neo4j"
        except Exception as e:
            logger.warning(f"[CogGRAG:MemoryCheck] Neo4j memory lookup failed, fallback to file: {e}")

    if similar_best is None and backend in ("auto", "file"):
        memory = get_consultation_memory()
        similar = memory.find_similar(query, tenant_id, threshold=0.5, limit=1)
        if similar:
            best_match = similar[0]
            similar_best = best_match
            memory_source = "file"

    latency = int((time.time() - start) * 1000)

    if similar_best:
        logger.info(
            f"[CogGRAG:MemoryCheck] Found similar consultation: "
            f"similarity={similar_best.get('similarity')}, id={similar_best.get('consulta_id') or similar_best.get('entry_id')}"
        )
        return {
            "similar_consultation": similar_best,
            "metrics": {
                **state.get("metrics", {}),
                "memory_check_latency_ms": latency,
                "memory_check_enabled": True,
                "memory_check_found": True,
                "memory_check_similarity": similar_best.get("similarity"),
                "memory_check_backend": memory_source,
            },
        }

    logger.info(f"[CogGRAG:MemoryCheck] No similar consultation found, {latency}ms")
    return {
        "similar_consultation": None,
        "metrics": {
            **state.get("metrics", {}),
            "memory_check_latency_ms": latency,
            "memory_check_enabled": True,
            "memory_check_found": False,
            "memory_check_backend": memory_source,
        },
    }


# ═══════════════════════════════════════════════════════════════════════════
# Memory Store Node
# ═══════════════════════════════════════════════════════════════════════════

async def memory_store_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    LangGraph node: store current consultation in memory.

    Reads from state:
        - query, tenant_id
        - mind_map, sub_questions, evidence_map
        - integrated_response (if available)
        - cograg_memory_enabled

    Writes to state:
        - metrics.memory_store_*
    """
    query: str = state.get("query", "")
    tenant_id: str = state.get("tenant_id", "default")
    memory_enabled: bool = state.get("cograg_memory_enabled", False)
    backend: str = str(state.get("cograg_memory_backend", "auto") or "auto").strip().lower()
    # Respect explicit backend choice; only force Neo4j when backend is auto.
    try:
        if backend in ("", "auto") and get_rag_config().neo4j_only:
            backend = "neo4j"
    except Exception:
        pass
    start = time.time()

    if not memory_enabled:
        logger.debug("[CogGRAG:MemoryStore] Memory disabled → skip")
        return {
            "metrics": {
                **state.get("metrics", {}),
                "memory_store_latency_ms": 0,
                "memory_store_enabled": False,
            },
        }

    if not query:
        return {
            "metrics": {
                **state.get("metrics", {}),
                "memory_store_latency_ms": 0,
            },
        }

    logger.info(f"[CogGRAG:MemoryStore] Storing consultation in memory")

    memory_source = "neo4j" if backend == "neo4j" else "file"
    consulta_id: Optional[str] = None

    # 1) Neo4j (preferred)
    graph_memory = _get_graph_memory() if backend in ("auto", "neo4j") else None
    if graph_memory is not None:
        try:
            consulta_id = graph_memory.store_consultation(
                query=query,
                tenant_id=tenant_id,
                scope=state.get("scope", "global"),
                case_id=state.get("case_id"),
                mind_map=state.get("mind_map"),
                sub_questions=state.get("sub_questions", []),
                evidence_map=state.get("evidence_map", {}),
                sub_answers=state.get("sub_answers", []),
                integrated_response=state.get("integrated_response"),
                citations_used=state.get("citations_used", []),
                verification_status=state.get("verification_status", ""),
                verification_issues=state.get("verification_issues", []),
            )
            memory_source = "neo4j"
        except Exception as e:
            logger.warning(f"[CogGRAG:MemoryStore] Neo4j memory store failed, fallback to file: {e}")

    # 2) File fallback
    entry_id: Optional[str] = None
    if consulta_id is None and backend in ("auto", "file"):
        memory = get_consultation_memory()
        entry_id = memory.store(
            query=query,
            tenant_id=tenant_id,
            mind_map=state.get("mind_map"),
            sub_questions=state.get("sub_questions", []),
            evidence_map=state.get("evidence_map", {}),
            answer_summary=state.get("integrated_response"),
        )
        memory_source = "file"

    latency = int((time.time() - start) * 1000)
    stored_id = consulta_id or entry_id or ""
    logger.info(f"[CogGRAG:MemoryStore] Stored as {stored_id}, {latency}ms ({memory_source})")

    return {
        "metrics": {
            **state.get("metrics", {}),
            "memory_store_latency_ms": latency,
            "memory_store_enabled": True,
            "memory_store_backend": memory_source,
            **({"memory_store_consulta_id": consulta_id} if consulta_id else {}),
            **({"memory_store_entry_id": entry_id} if entry_id else {}),
        },
    }
