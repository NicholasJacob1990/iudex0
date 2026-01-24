"""
RAG Utilities

Provides utility functions for the RAG pipeline:
- Tracing and observability
- TTL cleanup for local documents
"""

from .trace import (
    trace_event,
    TraceEventType,
    TracePayload,
    TraceTimer,
    AsyncTraceTimer,
    generate_request_id,
    trace_query_received,
    trace_search_complete,
    trace_error,
    trace_crag_gate,
    trace_rerank_complete,
    trace_compression_applied,
    trace_response_sent,
    is_tracing_enabled,
    get_trace_config,
)

from .ttl_cleanup import (
    CleanupStats,
    CleanupMetrics,
    TTLCleanupScheduler,
    cleanup_local_opensearch,
    cleanup_local_qdrant,
    run_ttl_cleanup,
    run_ttl_cleanup_async,
    schedule_ttl_cleanup,
    stop_ttl_cleanup_scheduler,
    get_ttl_cleanup_scheduler,
    get_cleanup_metrics,
    create_celery_task,
)

from .ingest import (
    Chunk,
    chunk_text,
    extract_pdf_pages,
    chunk_document,
    chunk_pdf,
)

from .audit import (
    QueryRewriteType,
    EvidenceLevel,
    SourceAttribution,
    QueryRewriteRecord,
    CRAGGateResult,
    RAGAuditRecord,
    RAGAuditContext,
    write_audit_record,
    create_audit_context,
    calculate_evidence_level,
    audit_search_request,
    audit_search_response,
    audit_query_rewrite,
)

__all__ = [
    # Core tracing
    "trace_event",
    "TraceEventType",
    "TracePayload",
    # Context managers
    "TraceTimer",
    "AsyncTraceTimer",
    # Utility functions
    "generate_request_id",
    "is_tracing_enabled",
    "get_trace_config",
    # Convenience functions
    "trace_query_received",
    "trace_search_complete",
    "trace_error",
    "trace_crag_gate",
    "trace_rerank_complete",
    "trace_compression_applied",
    "trace_response_sent",
    # TTL Cleanup - Stats and metrics
    "CleanupStats",
    "CleanupMetrics",
    "get_cleanup_metrics",
    # TTL Cleanup - Functions
    "cleanup_local_opensearch",
    "cleanup_local_qdrant",
    "run_ttl_cleanup",
    "run_ttl_cleanup_async",
    # TTL Cleanup - Scheduler
    "TTLCleanupScheduler",
    "schedule_ttl_cleanup",
    "stop_ttl_cleanup_scheduler",
    "get_ttl_cleanup_scheduler",
    # TTL Cleanup - Celery integration
    "create_celery_task",
    # Ingest utilities
    "Chunk",
    "chunk_text",
    "extract_pdf_pages",
    "chunk_document",
    "chunk_pdf",
    # Audit
    "QueryRewriteType",
    "EvidenceLevel",
    "SourceAttribution",
    "QueryRewriteRecord",
    "CRAGGateResult",
    "RAGAuditRecord",
    "RAGAuditContext",
    "write_audit_record",
    "create_audit_context",
    "calculate_evidence_level",
    "audit_search_request",
    "audit_search_response",
    "audit_query_rewrite",
]
