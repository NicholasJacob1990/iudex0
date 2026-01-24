"""
RAG Tracing Module - Event tracing for RAG operations.

Provides:
- JSONL logging format
- Optional DB persistence (feature-flagged)
- OpenTelemetry export option
- Event-based tracing for all RAG pipeline stages
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4


# ---------------------------------------------------------------------------
# Configuration via environment variables
# ---------------------------------------------------------------------------

_TRACE_LOG_PATH = os.getenv("RAG_TRACE_LOG_PATH", "logs/rag_trace.jsonl")
_TRACE_PERSIST_DB = os.getenv("RAG_TRACE_PERSIST_DB", "false").lower() in ("1", "true", "yes", "on")
_TRACE_ENABLED = os.getenv("RAG_TRACE_ENABLED", "true").lower() in ("1", "true", "yes", "on")
_TRACE_EXPORT_OTEL = os.getenv("RAG_TRACE_EXPORT_OTEL", "false").lower() in ("1", "true", "yes", "on")
_TRACE_EXPORT_LANGSMITH = os.getenv("RAG_TRACE_EXPORT_LANGSMITH", "false").lower() in ("1", "true", "yes", "on")


# ---------------------------------------------------------------------------
# Trace Event Types
# ---------------------------------------------------------------------------

class TraceEventType(str, Enum):
    """Enumeration of all RAG trace event types."""
    QUERY_RECEIVED = "QUERY_RECEIVED"
    LEXICAL_SEARCH_COMPLETE = "LEXICAL_SEARCH_COMPLETE"
    VECTOR_SEARCH_COMPLETE = "VECTOR_SEARCH_COMPLETE"
    MERGE_COMPLETE = "MERGE_COMPLETE"
    CRAG_GATE_EVALUATED = "CRAG_GATE_EVALUATED"
    RERANK_COMPLETE = "RERANK_COMPLETE"
    COMPRESSION_APPLIED = "COMPRESSION_APPLIED"
    GRAPH_ENRICHED = "GRAPH_ENRICHED"
    RESPONSE_SENT = "RESPONSE_SENT"
    # Additional events for query rewrites
    QUERY_REWRITE_HYDE = "QUERY_REWRITE_HYDE"
    QUERY_REWRITE_MULTI = "QUERY_REWRITE_MULTI"
    QUERY_REWRITE_CRAG = "QUERY_REWRITE_CRAG"
    # Error events
    ERROR_OCCURRED = "ERROR_OCCURRED"
    # Ingestion events
    INGEST_STARTED = "INGEST_STARTED"
    INGEST_COMPLETE = "INGEST_COMPLETE"


# ---------------------------------------------------------------------------
# Trace Payload Structure
# ---------------------------------------------------------------------------

class TracePayload:
    """
    Standardized trace payload structure.

    Attributes:
        request_id: Unique identifier for the request (UUID)
        timestamp: ISO 8601 timestamp of the event
        event_type: Type of trace event
        query_original: Original user query
        query_rewritten: Rewritten query (if applicable)
        sources: List of datasets/collections searched
        top_scores: Top N scores from retrieval
        evidence_level: Confidence/evidence level (0.0-1.0)
        actions_taken: List of actions performed
        latency_ms: Operation latency in milliseconds
        metadata: Additional context-specific metadata
    """

    def __init__(
        self,
        event_type: TraceEventType,
        request_id: Optional[str] = None,
        query_original: Optional[str] = None,
        query_rewritten: Optional[str] = None,
        sources: Optional[List[str]] = None,
        top_scores: Optional[List[float]] = None,
        evidence_level: Optional[float] = None,
        actions_taken: Optional[List[str]] = None,
        latency_ms: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.request_id = request_id or str(uuid4())
        self.timestamp = datetime.now(timezone.utc).isoformat()
        self.event_type = event_type.value if isinstance(event_type, TraceEventType) else event_type
        self.query_original = query_original
        self.query_rewritten = query_rewritten
        self.sources = sources or []
        self.top_scores = top_scores or []
        self.evidence_level = evidence_level
        self.actions_taken = actions_taken or []
        self.latency_ms = latency_ms
        self.metadata = metadata or {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert payload to dictionary for serialization."""
        return {
            "request_id": self.request_id,
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "query_original": self.query_original,
            "query_rewritten": self.query_rewritten,
            "sources": self.sources,
            "top_scores": self.top_scores,
            "evidence_level": self.evidence_level,
            "actions_taken": self.actions_taken,
            "latency_ms": self.latency_ms,
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# JSONL Writer
# ---------------------------------------------------------------------------

def _write_jsonl(record: Dict[str, Any]) -> None:
    """Write a record to the JSONL log file."""
    if not _TRACE_ENABLED:
        return
    try:
        log_dir = os.path.dirname(_TRACE_LOG_PATH)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        with open(_TRACE_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    except Exception:
        # Silently fail - tracing should not break the main application
        pass


# ---------------------------------------------------------------------------
# OpenTelemetry Export
# ---------------------------------------------------------------------------

def _emit_otel(event_type: str, payload: Dict[str, Any]) -> None:
    """Emit trace to OpenTelemetry if enabled."""
    if not _TRACE_EXPORT_OTEL:
        return
    try:
        from opentelemetry import trace
        tracer = trace.get_tracer("rag-trace")
        with tracer.start_as_current_span(f"rag.{event_type}") as span:
            span.set_attribute("request_id", payload.get("request_id", ""))
            span.set_attribute("event_type", event_type)
            if payload.get("query_original"):
                span.set_attribute("query_original", payload["query_original"])
            if payload.get("latency_ms") is not None:
                span.set_attribute("latency_ms", payload["latency_ms"])
            if payload.get("evidence_level") is not None:
                span.set_attribute("evidence_level", payload["evidence_level"])
            if payload.get("sources"):
                span.set_attribute("sources", json.dumps(payload["sources"]))
            if payload.get("top_scores"):
                span.set_attribute("top_scores", json.dumps(payload["top_scores"]))
            for key, value in payload.get("metadata", {}).items():
                try:
                    span.set_attribute(f"meta.{key}", value if isinstance(value, (str, int, float, bool)) else str(value))
                except Exception:
                    pass
    except ImportError:
        pass
    except Exception:
        pass


# ---------------------------------------------------------------------------
# LangSmith Export
# ---------------------------------------------------------------------------

def _emit_langsmith(event_type: str, payload: Dict[str, Any]) -> None:
    """Emit trace to LangSmith if enabled."""
    if not _TRACE_EXPORT_LANGSMITH:
        return
    try:
        from langsmith import Client
        client = Client()
        client.create_run(
            name=f"rag.{event_type}",
            run_type="tool",
            inputs={"query": payload.get("query_original"), "sources": payload.get("sources")},
            outputs={"evidence_level": payload.get("evidence_level"), "top_scores": payload.get("top_scores")},
            extra=payload.get("metadata"),
        )
    except ImportError:
        pass
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Database Persistence (Feature-Flagged)
# ---------------------------------------------------------------------------

async def _persist_db_async(record: Dict[str, Any]) -> None:
    """Persist trace record to database asynchronously."""
    if not _TRACE_PERSIST_DB:
        return
    try:
        # Import database models - adjust path as needed for your DB setup
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy import Column, String, DateTime, Float, JSON
        from sqlalchemy.orm import declarative_base

        db_url = os.getenv("RAG_TRACE_DB_URL", "sqlite+aiosqlite:///logs/rag_trace.db")

        Base = declarative_base()

        class RAGTraceRecord(Base):
            __tablename__ = "rag_trace_events"
            request_id = Column(String(36), primary_key=True, index=True)
            timestamp = Column(String(32), nullable=False)
            event_type = Column(String(64), nullable=False, index=True)
            query_original = Column(String(2000), nullable=True)
            query_rewritten = Column(String(2000), nullable=True)
            evidence_level = Column(Float, nullable=True)
            latency_ms = Column(Float, nullable=True)
            payload = Column(JSON, nullable=True)

        engine = create_async_engine(db_url, echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with async_session() as session:
            trace_record = RAGTraceRecord(
                request_id=record.get("request_id", str(uuid4())),
                timestamp=record.get("timestamp", datetime.now(timezone.utc).isoformat()),
                event_type=record.get("event_type", "UNKNOWN"),
                query_original=record.get("query_original"),
                query_rewritten=record.get("query_rewritten"),
                evidence_level=record.get("evidence_level"),
                latency_ms=record.get("latency_ms"),
                payload=record,
            )
            session.add(trace_record)
            await session.commit()
    except ImportError:
        pass
    except Exception:
        pass


def _schedule_db_persist(record: Dict[str, Any]) -> None:
    """Schedule database persistence in the event loop."""
    if not _TRACE_PERSIST_DB:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        loop.create_task(_persist_db_async(record))
    else:
        try:
            asyncio.run(_persist_db_async(record))
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Main Trace Function
# ---------------------------------------------------------------------------

def trace_event(
    event_type: TraceEventType,
    *,
    request_id: Optional[str] = None,
    query_original: Optional[str] = None,
    query_rewritten: Optional[str] = None,
    sources: Optional[List[str]] = None,
    top_scores: Optional[List[float]] = None,
    evidence_level: Optional[float] = None,
    actions_taken: Optional[List[str]] = None,
    latency_ms: Optional[float] = None,
    metadata: Optional[Dict[str, Any]] = None,
    tenant_id: Optional[str] = None,
    user_id: Optional[str] = None,
    case_id: Optional[str] = None,
) -> str:
    """
    Record a RAG trace event.

    Args:
        event_type: Type of trace event (from TraceEventType enum)
        request_id: Unique request identifier (generated if not provided)
        query_original: Original user query
        query_rewritten: Rewritten query (for CRAG, HyDE, multi-query)
        sources: List of data sources searched
        top_scores: Top retrieval scores
        evidence_level: Confidence/evidence level (0.0-1.0)
        actions_taken: List of actions taken during processing
        latency_ms: Operation latency in milliseconds
        metadata: Additional metadata
        tenant_id: Tenant identifier for multi-tenancy
        user_id: User identifier
        case_id: Case identifier

    Returns:
        The request_id used for this trace event
    """
    if not _TRACE_ENABLED:
        return request_id or str(uuid4())

    payload = TracePayload(
        event_type=event_type,
        request_id=request_id,
        query_original=query_original,
        query_rewritten=query_rewritten,
        sources=sources,
        top_scores=top_scores,
        evidence_level=evidence_level,
        actions_taken=actions_taken,
        latency_ms=latency_ms,
        metadata={
            **(metadata or {}),
            "tenant_id": tenant_id,
            "user_id": user_id,
            "case_id": case_id,
        },
    )

    record = payload.to_dict()

    # Write to JSONL file
    _write_jsonl(record)

    # Export to OpenTelemetry
    _emit_otel(payload.event_type, record)

    # Export to LangSmith
    _emit_langsmith(payload.event_type, record)

    # Persist to database (async, non-blocking)
    _schedule_db_persist(record)

    return payload.request_id


# ---------------------------------------------------------------------------
# Context Manager for Timed Traces
# ---------------------------------------------------------------------------

class TraceTimer:
    """
    Context manager for timing RAG operations and automatically recording trace events.

    Usage:
        with TraceTimer(TraceEventType.LEXICAL_SEARCH_COMPLETE, request_id="abc") as timer:
            results = do_lexical_search()
            timer.set_metadata({"result_count": len(results)})
    """

    def __init__(
        self,
        event_type: TraceEventType,
        request_id: Optional[str] = None,
        query_original: Optional[str] = None,
        sources: Optional[List[str]] = None,
        **kwargs: Any,
    ):
        self.event_type = event_type
        self.request_id = request_id or str(uuid4())
        self.query_original = query_original
        self.sources = sources
        self.kwargs = kwargs
        self._start_time: float = 0
        self._metadata: Dict[str, Any] = {}
        self._top_scores: List[float] = []
        self._evidence_level: Optional[float] = None
        self._actions_taken: List[str] = []

    def __enter__(self) -> "TraceTimer":
        self._start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        latency_ms = (time.perf_counter() - self._start_time) * 1000

        if exc_type is not None:
            self._metadata["error"] = str(exc_val)
            self._metadata["error_type"] = exc_type.__name__

        trace_event(
            self.event_type,
            request_id=self.request_id,
            query_original=self.query_original,
            sources=self.sources,
            top_scores=self._top_scores,
            evidence_level=self._evidence_level,
            actions_taken=self._actions_taken,
            latency_ms=latency_ms,
            metadata=self._metadata,
            **self.kwargs,
        )

    def set_metadata(self, metadata: Dict[str, Any]) -> None:
        """Add metadata to the trace."""
        self._metadata.update(metadata)

    def set_top_scores(self, scores: List[float]) -> None:
        """Set top retrieval scores."""
        self._top_scores = scores

    def set_evidence_level(self, level: float) -> None:
        """Set evidence/confidence level."""
        self._evidence_level = level

    def add_action(self, action: str) -> None:
        """Add an action taken."""
        self._actions_taken.append(action)


# ---------------------------------------------------------------------------
# Convenience Functions
# ---------------------------------------------------------------------------

def generate_request_id() -> str:
    """Generate a new unique request ID."""
    return str(uuid4())


def trace_query_received(
    query: str,
    request_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    user_id: Optional[str] = None,
    case_id: Optional[str] = None,
    datasets: Optional[List[str]] = None,
) -> str:
    """Convenience function to trace a received query."""
    return trace_event(
        TraceEventType.QUERY_RECEIVED,
        request_id=request_id,
        query_original=query,
        sources=datasets,
        tenant_id=tenant_id,
        user_id=user_id,
        case_id=case_id,
        metadata={"datasets_requested": datasets},
    )


def trace_search_complete(
    event_type: TraceEventType,
    request_id: str,
    query: str,
    results_count: int,
    top_scores: List[float],
    latency_ms: float,
    sources: List[str],
    metadata: Optional[Dict[str, Any]] = None,
) -> str:
    """Convenience function to trace search completion."""
    return trace_event(
        event_type,
        request_id=request_id,
        query_original=query,
        sources=sources,
        top_scores=top_scores[:10] if top_scores else [],
        latency_ms=latency_ms,
        metadata={**(metadata or {}), "results_count": results_count},
    )


def trace_error(
    request_id: str,
    error: Exception,
    context: Optional[str] = None,
    query: Optional[str] = None,
) -> str:
    """Convenience function to trace an error."""
    return trace_event(
        TraceEventType.ERROR_OCCURRED,
        request_id=request_id,
        query_original=query,
        metadata={
            "error_type": type(error).__name__,
            "error_message": str(error),
            "context": context,
        },
    )
