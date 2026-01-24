"""
RAG Audit Module - Request/response logging and source attribution tracking.

Provides:
- Request/response logging for audit trails
- Source attribution tracking
- Score/evidence recording
- Query rewrite tracking (CRAG, HyDE, multi-query)
- Comprehensive audit records for compliance and debugging
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

from .trace import (
    TraceEventType,
    trace_event,
    TraceTimer,
    generate_request_id,
)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_AUDIT_LOG_PATH = os.getenv("RAG_AUDIT_LOG_PATH", "logs/rag_audit.jsonl")
_AUDIT_ENABLED = os.getenv("RAG_AUDIT_ENABLED", "true").lower() in ("1", "true", "yes", "on")
_AUDIT_INCLUDE_CONTENT = os.getenv("RAG_AUDIT_INCLUDE_CONTENT", "true").lower() in ("1", "true", "yes", "on")
_AUDIT_MAX_CONTENT_LENGTH = int(os.getenv("RAG_AUDIT_MAX_CONTENT_LENGTH", "5000"))


# ---------------------------------------------------------------------------
# Query Rewrite Types
# ---------------------------------------------------------------------------

class QueryRewriteType(str, Enum):
    """Types of query rewrites for tracking."""
    NONE = "none"
    HYDE = "hyde"  # Hypothetical Document Embeddings
    MULTI_QUERY = "multi_query"  # Multiple query expansion
    CRAG = "crag"  # Corrective RAG
    STEP_BACK = "step_back"  # Step-back prompting
    DECOMPOSITION = "decomposition"  # Query decomposition


class EvidenceLevel(str, Enum):
    """Evidence quality levels for source attribution."""
    HIGH = "high"  # Strong match, high confidence
    MEDIUM = "medium"  # Moderate match
    LOW = "low"  # Weak match, low confidence
    INSUFFICIENT = "insufficient"  # Not enough evidence
    UNKNOWN = "unknown"  # Unable to determine


# ---------------------------------------------------------------------------
# Source Attribution Data Classes
# ---------------------------------------------------------------------------

@dataclass
class SourceAttribution:
    """Represents a single source attribution with score and evidence."""
    chunk_uid: str
    source_type: str  # e.g., "lexical", "vector", "both"
    dataset: str  # e.g., "lei", "juris", "local"
    score: float
    evidence_level: str = EvidenceLevel.UNKNOWN.value
    doc_id: Optional[str] = None
    doc_hash: Optional[str] = None
    page: Optional[int] = None
    chunk_index: Optional[int] = None
    text_snippet: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)


@dataclass
class QueryRewriteRecord:
    """Records a query rewrite operation."""
    rewrite_type: str
    original_query: str
    rewritten_queries: List[str]
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    latency_ms: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)


@dataclass
class CRAGGateResult:
    """Records the result of a CRAG gate evaluation."""
    gate_passed: bool
    confidence_score: float
    original_result_count: int
    filtered_result_count: int
    action_taken: str  # e.g., "accept", "refine", "web_search", "reject"
    reason: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)


# ---------------------------------------------------------------------------
# Main Audit Record
# ---------------------------------------------------------------------------

@dataclass
class RAGAuditRecord:
    """
    Comprehensive audit record for a RAG request/response cycle.

    This captures the full lifecycle of a RAG operation including:
    - Original request parameters
    - Query rewrites applied
    - Search results from each stage
    - Source attributions
    - CRAG gate evaluations
    - Final response metadata
    """
    request_id: str
    timestamp_start: str
    timestamp_end: Optional[str] = None

    # Request details
    query_original: str = ""
    tenant_id: Optional[str] = None
    user_id: Optional[str] = None
    case_id: Optional[str] = None
    datasets_requested: List[str] = field(default_factory=list)

    # Query rewrites
    query_rewrites: List[QueryRewriteRecord] = field(default_factory=list)

    # Search results
    lexical_results_count: int = 0
    vector_results_count: int = 0
    merged_results_count: int = 0
    final_results_count: int = 0

    # Scores
    lexical_top_scores: List[float] = field(default_factory=list)
    vector_top_scores: List[float] = field(default_factory=list)
    final_top_scores: List[float] = field(default_factory=list)

    # Source attributions
    source_attributions: List[SourceAttribution] = field(default_factory=list)

    # CRAG gate
    crag_gate_results: List[CRAGGateResult] = field(default_factory=list)

    # Evidence assessment
    overall_evidence_level: str = EvidenceLevel.UNKNOWN.value
    evidence_coverage: float = 0.0  # Percentage of query covered by evidence

    # Performance
    total_latency_ms: float = 0.0
    lexical_latency_ms: float = 0.0
    vector_latency_ms: float = 0.0
    merge_latency_ms: float = 0.0
    rerank_latency_ms: float = 0.0

    # Additional metadata
    search_mode: str = "hybrid"  # "lexical_only", "vector_only", "hybrid"
    actions_taken: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        result = asdict(self)
        # Convert nested dataclasses
        result["query_rewrites"] = [qr if isinstance(qr, dict) else qr.to_dict() for qr in self.query_rewrites]
        result["source_attributions"] = [sa if isinstance(sa, dict) else sa.to_dict() for sa in self.source_attributions]
        result["crag_gate_results"] = [cg if isinstance(cg, dict) else cg.to_dict() for cg in self.crag_gate_results]
        return result

    def finalize(self) -> None:
        """Finalize the audit record with end timestamp."""
        self.timestamp_end = datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Audit Writer
# ---------------------------------------------------------------------------

def _write_audit_jsonl(record: Dict[str, Any]) -> None:
    """Write an audit record to the JSONL log file."""
    if not _AUDIT_ENABLED:
        return
    try:
        log_dir = os.path.dirname(_AUDIT_LOG_PATH)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        with open(_AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    except Exception:
        # Silently fail - audit should not break the main application
        pass


def write_audit_record(record: RAGAuditRecord) -> None:
    """Write a complete audit record."""
    record.finalize()
    _write_audit_jsonl(record.to_dict())


# ---------------------------------------------------------------------------
# RAG Audit Context Manager
# ---------------------------------------------------------------------------

class RAGAuditContext:
    """
    Context manager for tracking a complete RAG operation.

    Usage:
        async with RAGAuditContext(query, tenant_id=tid) as audit:
            # Perform RAG operations
            audit.record_lexical_search(results, latency)
            audit.record_vector_search(results, latency)
            audit.record_merge(merged_results)
            audit.add_source_attribution(...)
    """

    def __init__(
        self,
        query: str,
        request_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        user_id: Optional[str] = None,
        case_id: Optional[str] = None,
        datasets: Optional[List[str]] = None,
    ):
        self.record = RAGAuditRecord(
            request_id=request_id or generate_request_id(),
            timestamp_start=datetime.now(timezone.utc).isoformat(),
            query_original=query,
            tenant_id=tenant_id,
            user_id=user_id,
            case_id=case_id,
            datasets_requested=datasets or [],
        )
        self._start_time = time.perf_counter()

    def __enter__(self) -> "RAGAuditContext":
        # Trace query received
        trace_event(
            TraceEventType.QUERY_RECEIVED,
            request_id=self.record.request_id,
            query_original=self.record.query_original,
            sources=self.record.datasets_requested,
            tenant_id=self.record.tenant_id,
            user_id=self.record.user_id,
            case_id=self.record.case_id,
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.record.total_latency_ms = (time.perf_counter() - self._start_time) * 1000

        if exc_type is not None:
            self.record.errors.append(f"{exc_type.__name__}: {exc_val}")

        # Trace response sent
        trace_event(
            TraceEventType.RESPONSE_SENT,
            request_id=self.record.request_id,
            query_original=self.record.query_original,
            sources=self.record.datasets_requested,
            top_scores=self.record.final_top_scores[:10],
            evidence_level=_evidence_level_to_float(self.record.overall_evidence_level),
            latency_ms=self.record.total_latency_ms,
            actions_taken=self.record.actions_taken,
            tenant_id=self.record.tenant_id,
            user_id=self.record.user_id,
            case_id=self.record.case_id,
            metadata={
                "search_mode": self.record.search_mode,
                "final_results_count": self.record.final_results_count,
                "errors": self.record.errors,
            },
        )

        # Write the complete audit record
        write_audit_record(self.record)

    async def __aenter__(self) -> "RAGAuditContext":
        return self.__enter__()

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        self.__exit__(exc_type, exc_val, exc_tb)

    @property
    def request_id(self) -> str:
        """Get the request ID."""
        return self.record.request_id

    def record_query_rewrite(
        self,
        rewrite_type: QueryRewriteType,
        original_query: str,
        rewritten_queries: List[str],
        latency_ms: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record a query rewrite operation."""
        rewrite = QueryRewriteRecord(
            rewrite_type=rewrite_type.value,
            original_query=original_query,
            rewritten_queries=rewritten_queries,
            latency_ms=latency_ms,
            metadata=metadata or {},
        )
        self.record.query_rewrites.append(rewrite)
        self.record.actions_taken.append(f"query_rewrite_{rewrite_type.value}")

        # Trace the rewrite
        event_type_map = {
            QueryRewriteType.HYDE: TraceEventType.QUERY_REWRITE_HYDE,
            QueryRewriteType.MULTI_QUERY: TraceEventType.QUERY_REWRITE_MULTI,
            QueryRewriteType.CRAG: TraceEventType.QUERY_REWRITE_CRAG,
        }
        event_type = event_type_map.get(rewrite_type, TraceEventType.QUERY_REWRITE_MULTI)
        trace_event(
            event_type,
            request_id=self.record.request_id,
            query_original=original_query,
            query_rewritten=rewritten_queries[0] if rewritten_queries else None,
            latency_ms=latency_ms,
            metadata={"all_rewrites": rewritten_queries, **(metadata or {})},
        )

    def record_lexical_search(
        self,
        results: List[Dict[str, Any]],
        latency_ms: float,
        sources: Optional[List[str]] = None,
    ) -> None:
        """Record lexical search results."""
        self.record.lexical_results_count = len(results)
        self.record.lexical_latency_ms = latency_ms
        self.record.lexical_top_scores = [r.get("score", 0.0) for r in results[:10]]

        trace_event(
            TraceEventType.LEXICAL_SEARCH_COMPLETE,
            request_id=self.record.request_id,
            query_original=self.record.query_original,
            sources=sources or self.record.datasets_requested,
            top_scores=self.record.lexical_top_scores,
            latency_ms=latency_ms,
            metadata={"results_count": len(results)},
        )

    def record_vector_search(
        self,
        results: List[Dict[str, Any]],
        latency_ms: float,
        sources: Optional[List[str]] = None,
    ) -> None:
        """Record vector search results."""
        self.record.vector_results_count = len(results)
        self.record.vector_latency_ms = latency_ms
        self.record.vector_top_scores = [r.get("score", 0.0) for r in results[:10]]

        trace_event(
            TraceEventType.VECTOR_SEARCH_COMPLETE,
            request_id=self.record.request_id,
            query_original=self.record.query_original,
            sources=sources or self.record.datasets_requested,
            top_scores=self.record.vector_top_scores,
            latency_ms=latency_ms,
            metadata={"results_count": len(results)},
        )

    def record_merge(
        self,
        merged_results: List[Dict[str, Any]],
        latency_ms: float,
    ) -> None:
        """Record merge operation results."""
        self.record.merged_results_count = len(merged_results)
        self.record.merge_latency_ms = latency_ms
        self.record.final_results_count = len(merged_results)
        self.record.final_top_scores = [r.get("final_score", r.get("score", 0.0)) for r in merged_results[:10]]

        trace_event(
            TraceEventType.MERGE_COMPLETE,
            request_id=self.record.request_id,
            query_original=self.record.query_original,
            top_scores=self.record.final_top_scores,
            latency_ms=latency_ms,
            metadata={"merged_count": len(merged_results)},
        )

    def record_crag_gate(
        self,
        gate_passed: bool,
        confidence_score: float,
        original_count: int,
        filtered_count: int,
        action_taken: str,
        reason: Optional[str] = None,
    ) -> None:
        """Record CRAG gate evaluation."""
        gate_result = CRAGGateResult(
            gate_passed=gate_passed,
            confidence_score=confidence_score,
            original_result_count=original_count,
            filtered_result_count=filtered_count,
            action_taken=action_taken,
            reason=reason,
        )
        self.record.crag_gate_results.append(gate_result)
        self.record.actions_taken.append(f"crag_gate_{action_taken}")

        trace_event(
            TraceEventType.CRAG_GATE_EVALUATED,
            request_id=self.record.request_id,
            query_original=self.record.query_original,
            evidence_level=confidence_score,
            metadata={
                "gate_passed": gate_passed,
                "action_taken": action_taken,
                "original_count": original_count,
                "filtered_count": filtered_count,
                "reason": reason,
            },
        )

    def record_rerank(
        self,
        reranked_results: List[Dict[str, Any]],
        latency_ms: float,
    ) -> None:
        """Record reranking results."""
        self.record.rerank_latency_ms = latency_ms
        self.record.final_results_count = len(reranked_results)
        self.record.final_top_scores = [r.get("score", 0.0) for r in reranked_results[:10]]
        self.record.actions_taken.append("rerank")

        trace_event(
            TraceEventType.RERANK_COMPLETE,
            request_id=self.record.request_id,
            query_original=self.record.query_original,
            top_scores=self.record.final_top_scores,
            latency_ms=latency_ms,
            metadata={"reranked_count": len(reranked_results)},
        )

    def record_compression(
        self,
        original_token_count: int,
        compressed_token_count: int,
        latency_ms: float,
    ) -> None:
        """Record context compression."""
        self.record.actions_taken.append("compression")

        trace_event(
            TraceEventType.COMPRESSION_APPLIED,
            request_id=self.record.request_id,
            query_original=self.record.query_original,
            latency_ms=latency_ms,
            metadata={
                "original_tokens": original_token_count,
                "compressed_tokens": compressed_token_count,
                "compression_ratio": compressed_token_count / original_token_count if original_token_count > 0 else 1.0,
            },
        )

    def record_graph_enrichment(
        self,
        entities_added: int,
        relationships_added: int,
        latency_ms: float,
    ) -> None:
        """Record graph-based enrichment."""
        self.record.actions_taken.append("graph_enrichment")

        trace_event(
            TraceEventType.GRAPH_ENRICHED,
            request_id=self.record.request_id,
            query_original=self.record.query_original,
            latency_ms=latency_ms,
            metadata={
                "entities_added": entities_added,
                "relationships_added": relationships_added,
            },
        )

    def add_source_attribution(
        self,
        chunk_uid: str,
        source_type: str,
        dataset: str,
        score: float,
        evidence_level: EvidenceLevel = EvidenceLevel.UNKNOWN,
        doc_id: Optional[str] = None,
        doc_hash: Optional[str] = None,
        page: Optional[int] = None,
        chunk_index: Optional[int] = None,
        text_snippet: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Add a source attribution to the audit record."""
        # Truncate text snippet if needed
        if text_snippet and len(text_snippet) > _AUDIT_MAX_CONTENT_LENGTH:
            text_snippet = text_snippet[:_AUDIT_MAX_CONTENT_LENGTH] + "..."

        attribution = SourceAttribution(
            chunk_uid=chunk_uid,
            source_type=source_type,
            dataset=dataset,
            score=score,
            evidence_level=evidence_level.value if isinstance(evidence_level, EvidenceLevel) else evidence_level,
            doc_id=doc_id,
            doc_hash=doc_hash,
            page=page,
            chunk_index=chunk_index,
            text_snippet=text_snippet if _AUDIT_INCLUDE_CONTENT else None,
            metadata=metadata or {},
        )
        self.record.source_attributions.append(attribution)

    def add_source_attributions_from_results(
        self,
        results: List[Dict[str, Any]],
        default_evidence_level: EvidenceLevel = EvidenceLevel.MEDIUM,
    ) -> None:
        """Bulk add source attributions from search results."""
        for result in results:
            sources = result.get("sources", [])
            source_type = ",".join(sources) if sources else "unknown"

            self.add_source_attribution(
                chunk_uid=result.get("chunk_uid", ""),
                source_type=source_type,
                dataset=result.get("metadata", {}).get("dataset", "unknown"),
                score=result.get("final_score", result.get("score", 0.0)),
                evidence_level=default_evidence_level,
                doc_id=result.get("metadata", {}).get("doc_id"),
                doc_hash=result.get("metadata", {}).get("doc_hash"),
                page=result.get("metadata", {}).get("page"),
                chunk_index=result.get("metadata", {}).get("chunk_index"),
                text_snippet=result.get("text"),
            )

    def set_search_mode(self, mode: str) -> None:
        """Set the search mode (lexical_only, vector_only, hybrid)."""
        self.record.search_mode = mode

    def set_evidence_level(self, level: EvidenceLevel, coverage: float = 0.0) -> None:
        """Set the overall evidence level and coverage."""
        self.record.overall_evidence_level = level.value if isinstance(level, EvidenceLevel) else level
        self.record.evidence_coverage = coverage

    def add_warning(self, warning: str) -> None:
        """Add a warning message."""
        self.record.warnings.append(warning)

    def add_error(self, error: str) -> None:
        """Add an error message."""
        self.record.errors.append(error)

    def add_action(self, action: str) -> None:
        """Add an action taken."""
        self.record.actions_taken.append(action)

    def set_metadata(self, key: str, value: Any) -> None:
        """Set additional metadata."""
        self.record.metadata[key] = value


# ---------------------------------------------------------------------------
# Utility Functions
# ---------------------------------------------------------------------------

def _evidence_level_to_float(level: str) -> float:
    """Convert evidence level string to float for tracing."""
    mapping = {
        EvidenceLevel.HIGH.value: 0.9,
        EvidenceLevel.MEDIUM.value: 0.6,
        EvidenceLevel.LOW.value: 0.3,
        EvidenceLevel.INSUFFICIENT.value: 0.1,
        EvidenceLevel.UNKNOWN.value: 0.0,
    }
    return mapping.get(level, 0.0)


def calculate_evidence_level(
    top_scores: List[float],
    threshold_high: float = 0.8,
    threshold_medium: float = 0.5,
) -> EvidenceLevel:
    """Calculate evidence level based on top scores."""
    if not top_scores:
        return EvidenceLevel.INSUFFICIENT

    max_score = max(top_scores)
    avg_top3 = sum(top_scores[:3]) / min(3, len(top_scores))

    if max_score >= threshold_high and avg_top3 >= threshold_medium:
        return EvidenceLevel.HIGH
    elif max_score >= threshold_medium:
        return EvidenceLevel.MEDIUM
    elif max_score >= 0.3:
        return EvidenceLevel.LOW
    else:
        return EvidenceLevel.INSUFFICIENT


def create_audit_context(
    query: str,
    request_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    user_id: Optional[str] = None,
    case_id: Optional[str] = None,
    datasets: Optional[List[str]] = None,
) -> RAGAuditContext:
    """Factory function to create an audit context."""
    return RAGAuditContext(
        query=query,
        request_id=request_id,
        tenant_id=tenant_id,
        user_id=user_id,
        case_id=case_id,
        datasets=datasets,
    )


# ---------------------------------------------------------------------------
# Standalone Audit Functions (for simpler use cases)
# ---------------------------------------------------------------------------

def audit_search_request(
    query: str,
    tenant_id: str,
    user_id: Optional[str] = None,
    case_id: Optional[str] = None,
    datasets: Optional[List[str]] = None,
    request_id: Optional[str] = None,
) -> str:
    """Log a search request. Returns request_id."""
    request_id = request_id or generate_request_id()
    record = {
        "type": "search_request",
        "request_id": request_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "query": query,
        "tenant_id": tenant_id,
        "user_id": user_id,
        "case_id": case_id,
        "datasets": datasets or [],
    }
    _write_audit_jsonl(record)
    return request_id


def audit_search_response(
    request_id: str,
    results_count: int,
    top_scores: List[float],
    latency_ms: float,
    search_mode: str,
    source_attributions: Optional[List[Dict[str, Any]]] = None,
) -> None:
    """Log a search response."""
    record = {
        "type": "search_response",
        "request_id": request_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "results_count": results_count,
        "top_scores": top_scores[:10],
        "latency_ms": latency_ms,
        "search_mode": search_mode,
        "source_attributions": source_attributions or [],
    }
    _write_audit_jsonl(record)


def audit_query_rewrite(
    request_id: str,
    rewrite_type: QueryRewriteType,
    original_query: str,
    rewritten_queries: List[str],
    latency_ms: Optional[float] = None,
) -> None:
    """Log a query rewrite operation."""
    record = {
        "type": "query_rewrite",
        "request_id": request_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "rewrite_type": rewrite_type.value,
        "original_query": original_query,
        "rewritten_queries": rewritten_queries,
        "latency_ms": latency_ms,
    }
    _write_audit_jsonl(record)
