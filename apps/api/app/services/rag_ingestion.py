import asyncio
import json
import os
from datetime import datetime
from typing import Any, Dict, Optional

from app.services.rag_tracing import emit_trace

_INGEST_LOG_PATH = os.getenv("RAG_INGEST_LOG_PATH", "rag_ingest.jsonl")
_INGEST_PERSIST_DB = os.getenv("RAG_INGEST_PERSIST_DB", "true").lower() in ("1", "true", "yes", "on")


def _write_jsonl(record: Dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(_INGEST_LOG_PATH) or ".", exist_ok=True)
        with open(_INGEST_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        return


async def _persist_db(record: Dict[str, Any]) -> None:
    try:
        from app.core.database import AsyncSessionLocal, init_db
        from app.models.rag_ingestion import RAGIngestionEvent
    except Exception:
        return

    try:
        await init_db()
        async with AsyncSessionLocal() as session:
            payload = record.get("payload") or {}
            session.add(
                RAGIngestionEvent(
                    scope=payload.get("scope", "private"),
                    scope_id=payload.get("scope_id"),
                    tenant_id=payload.get("tenant_id"),
                    group_id=payload.get("group_id"),
                    collection=payload.get("collection", "unknown"),
                    source_type=payload.get("source_type", "unknown"),
                    doc_hash=payload.get("doc_hash"),
                    doc_version=payload.get("doc_version"),
                    chunk_count=payload.get("chunk_count"),
                    skipped_count=payload.get("skipped_count"),
                    status=payload.get("status", "unknown"),
                    error=payload.get("error"),
                    metadata_json=payload.get("metadata") or {},
                )
            )
            await session.commit()
    except Exception:
        return


def _schedule_persist(record: Dict[str, Any]) -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        loop.create_task(_persist_db(record))
        return
    try:
        asyncio.run(_persist_db(record))
    except Exception:
        return


def log_ingestion_event(
    *,
    scope: str,
    collection: str,
    source_type: str,
    status: str,
    scope_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    group_id: Optional[str] = None,
    doc_hash: Optional[str] = None,
    doc_version: Optional[int] = None,
    chunk_count: Optional[int] = None,
    skipped_count: Optional[int] = None,
    error: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    record = {
        "ts": datetime.utcnow().isoformat(),
        "event": "ingestion",
        "payload": {
            "scope": scope,
            "scope_id": scope_id,
            "tenant_id": tenant_id,
            "group_id": group_id,
            "collection": collection,
            "source_type": source_type,
            "status": status,
            "doc_hash": doc_hash,
            "doc_version": doc_version,
            "chunk_count": chunk_count,
            "skipped_count": skipped_count,
            "error": error,
            "metadata": metadata or {},
        },
    }
    _write_jsonl(record)
    emit_trace("ingestion", record)
    if _INGEST_PERSIST_DB:
        _schedule_persist(record)
