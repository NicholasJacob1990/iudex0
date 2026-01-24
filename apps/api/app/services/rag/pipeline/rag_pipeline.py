"""
RAG Pipeline - Main Orchestration Layer

This is the main RAG Pipeline that orchestrates all components in the following flow:

    Query -> Lexical Search -> Vector Search (conditional) -> Merge (RRF)
    -> CRAG Gate -> [Retry if needed] -> Rerank -> Expand
    -> Compress -> Graph Enrich -> Trace -> Response

Key Features:
- Lexical-first gating (MVP optimization): Skip vector search if lexical results are strong
- CRAG (Corrective RAG) gate with retry logic for quality control
- RRF (Reciprocal Rank Fusion) for hybrid result merging
- Cross-encoder reranking for precision
- Context compression to fit token budgets
- Knowledge graph enrichment for legal entities
- Full pipeline tracing for observability

Stage Breakdown:
    Stage 1: Query Enhancement (HyDE / Multi-query) - conditional via gating
    Stage 2: Lexical Search (OpenSearch BM25)
    Stage 3: Vector Search (Qdrant) - conditional, skip if lexical strong
    Stage 4: Merge (RRF fusion by chunk_uid)
    Stage 5: CRAG Gate with retry logic
    Stage 6: Rerank (cross-encoder top N)
    Stage 7: Expand (sibling chunks)
    Stage 8: Compress (keyword extraction)
    Stage 9: Graph Enrich (knowledge graph context)
    Stage 10: Trace (audit trail)
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from app.services.rag.config import RAGConfig, get_rag_config

# Import core components
# These may not all exist yet - imports are designed for forward compatibility
try:
    from app.services.rag.storage.opensearch import OpenSearchService
except ImportError:
    OpenSearchService = None  # type: ignore

try:
    from app.services.rag.storage.qdrant import QdrantService
except ImportError:
    QdrantService = None  # type: ignore

try:
    from app.services.rag.core.crag import CRAGGate, CRAGResult
except ImportError:
    CRAGGate = None  # type: ignore
    CRAGResult = None  # type: ignore

try:
    from app.services.rag.core.query_expansion import QueryExpansionService
except ImportError:
    QueryExpansionService = None  # type: ignore

try:
    from app.services.rag.core.reranker import CrossEncoderReranker, RerankerResult
except ImportError:
    CrossEncoderReranker = None  # type: ignore
    RerankerResult = None  # type: ignore

try:
    from app.services.rag.core.context_compressor import ContextCompressor, CompressionResult
except ImportError:
    ContextCompressor = None  # type: ignore
    CompressionResult = None  # type: ignore

try:
    from app.services.rag.core.chunk_expansion import ChunkExpander
except ImportError:
    ChunkExpander = None  # type: ignore

try:
    from app.services.rag.core.graph import LegalKnowledgeGraph
except ImportError:
    LegalKnowledgeGraph = None  # type: ignore

try:
    from app.services.rag.core.neo4j_mvp import (
        get_neo4j_mvp,
        Neo4jMVPService,
        LegalEntityExtractor as Neo4jEntityExtractor,
        enrich_rag_with_graph,
        build_graph_context,
    )
except ImportError:
    get_neo4j_mvp = None  # type: ignore
    Neo4jMVPService = None  # type: ignore
    Neo4jEntityExtractor = None  # type: ignore
    enrich_rag_with_graph = None  # type: ignore
    build_graph_context = None  # type: ignore

try:
    from app.services.rag.core.embeddings import EmbeddingsService, get_embeddings_service
except ImportError:
    EmbeddingsService = None  # type: ignore
    get_embeddings_service = None  # type: ignore

try:
    from app.services.rag.utils.tracing import trace_event, TraceEventType
except ImportError:
    trace_event = None  # type: ignore
    TraceEventType = None  # type: ignore


logger = logging.getLogger("RAGPipeline")


# =============================================================================
# Enums and Constants
# =============================================================================

class SearchMode(str, Enum):
    """Search mode indicating which retrieval strategies were used."""
    LEXICAL_ONLY = "lexical_only"
    VECTOR_ONLY = "vector_only"
    HYBRID_LEX_VEC = "hybrid_lex+vec"
    HYBRID_EXPANDED = "hybrid_expanded"


class PipelineStage(str, Enum):
    """Enumeration of all pipeline stages for tracing."""
    QUERY_ENHANCEMENT = "query_enhancement"
    LEXICAL_SEARCH = "lexical_search"
    VECTOR_SEARCH = "vector_search"
    MERGE_RRF = "merge_rrf"
    CRAG_GATE = "crag_gate"
    RERANK = "rerank"
    EXPAND = "expand"
    COMPRESS = "compress"
    GRAPH_ENRICH = "graph_enrich"
    TRACE = "trace"


class CRAGDecision(str, Enum):
    """CRAG gate decision outcomes."""
    ACCEPT = "accept"
    RETRY = "retry"
    REJECT = "reject"


# Citation-like patterns for lexical-heavy query detection
CITATION_PATTERNS = [
    re.compile(r"art\.?\s*\d+", re.IGNORECASE),
    re.compile(r"\u00a7\s*\d+"),  # § symbol
    re.compile(r"inciso\s+[IVXLCDM]+", re.IGNORECASE),
    re.compile(r"lei\s+n?\.?\s*\d+", re.IGNORECASE),
    re.compile(r"s[uú]mula\s+n?\.?\s*\d+", re.IGNORECASE),
    re.compile(r"\b(stf|stj|tst|trf|tjsp|tjrj|tjmg)\b", re.IGNORECASE),
    re.compile(r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}"),  # CNJ case number
    re.compile(r"decreto\s+n?\.?\s*\d+", re.IGNORECASE),
    re.compile(r"resolu[çc][aã]o\s+n?\.?\s*\d+", re.IGNORECASE),
    re.compile(r"portaria\s+n?\.?\s*\d+", re.IGNORECASE),
]


# =============================================================================
# Configuration
# =============================================================================

@dataclass
class RAGPipelineConfig:
    """
    Configuration for the RAG Pipeline.

    Extends RAGConfig with pipeline-specific settings that control
    the orchestration behavior across all stages.
    """

    # Base configuration (inherits all RAGConfig settings)
    base_config: RAGConfig = field(default_factory=get_rag_config)

    # Pipeline execution settings
    parallel_search: bool = True  # Run lexical and vector search in parallel when applicable
    fail_open: bool = True  # If components fail, continue with degraded results
    timeout_seconds: float = 30.0  # Overall pipeline timeout

    # Stage-specific timeouts
    search_timeout_seconds: float = 10.0
    rerank_timeout_seconds: float = 5.0
    compress_timeout_seconds: float = 3.0
    graph_timeout_seconds: float = 5.0

    # Result limits
    max_results_per_source: int = 50
    final_top_k: int = 10

    # Lexical-first gating thresholds
    lexical_skip_vector_threshold: float = 0.7
    lexical_min_results_for_skip: int = 3

    # CRAG settings
    crag_enabled: bool = True
    crag_min_relevance_score: float = 0.5
    crag_retry_with_expansion: bool = True

    # Debug and development
    verbose_logging: bool = False
    include_debug_info: bool = False

    @classmethod
    def from_rag_config(cls, config: Optional[RAGConfig] = None) -> "RAGPipelineConfig":
        """Create pipeline config from RAGConfig."""
        base = config or get_rag_config()
        return cls(
            base_config=base,
            crag_enabled=base.enable_crag,
            lexical_skip_vector_threshold=base.lexical_strong_threshold,
            final_top_k=base.default_top_k,
            max_results_per_source=base.default_fetch_k,
        )


# =============================================================================
# Trace and Result Data Structures
# =============================================================================

@dataclass
class StageTrace:
    """Trace information for a single pipeline stage."""

    stage: PipelineStage
    started_at: float
    ended_at: float = 0.0
    duration_ms: float = 0.0

    # Input/output counts
    input_count: int = 0
    output_count: int = 0

    # Stage-specific data
    data: Dict[str, Any] = field(default_factory=dict)

    # Error tracking
    error: Optional[str] = None
    skipped: bool = False
    skip_reason: Optional[str] = None

    def complete(self, output_count: int = 0, data: Optional[Dict[str, Any]] = None) -> None:
        """Mark stage as complete."""
        self.ended_at = time.time()
        self.duration_ms = (self.ended_at - self.started_at) * 1000
        self.output_count = output_count
        if data:
            self.data.update(data)

    def fail(self, error: str) -> None:
        """Mark stage as failed."""
        self.ended_at = time.time()
        self.duration_ms = (self.ended_at - self.started_at) * 1000
        self.error = error

    def skip(self, reason: str) -> None:
        """Mark stage as skipped."""
        self.ended_at = time.time()
        self.duration_ms = 0.0
        self.skipped = True
        self.skip_reason = reason

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "stage": self.stage.value,
            "duration_ms": round(self.duration_ms, 2),
            "input_count": self.input_count,
            "output_count": self.output_count,
            "data": self.data,
            "error": self.error,
            "skipped": self.skipped,
            "skip_reason": self.skip_reason,
        }


@dataclass
class CRAGEvaluation:
    """Results of CRAG gate evaluation."""

    decision: CRAGDecision
    best_score: float = 0.0
    avg_score: float = 0.0
    passed_count: int = 0
    total_count: int = 0
    retry_count: int = 0

    # Detailed scores per result
    scores: List[float] = field(default_factory=list)

    # Retry information
    retry_queries: List[str] = field(default_factory=list)
    retry_improved: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "decision": self.decision.value,
            "best_score": round(self.best_score, 4),
            "avg_score": round(self.avg_score, 4),
            "passed_count": self.passed_count,
            "total_count": self.total_count,
            "retry_count": self.retry_count,
            "retry_improved": self.retry_improved,
        }


@dataclass
class PipelineTrace:
    """
    Complete trace of a pipeline execution.

    Captures timing, decisions, and metadata for all stages.
    Useful for debugging, monitoring, and audit trails.
    """

    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    started_at: float = field(default_factory=time.time)
    ended_at: float = 0.0
    total_duration_ms: float = 0.0

    # Query information
    original_query: str = ""
    enhanced_queries: List[str] = field(default_factory=list)

    # Search mode and decisions
    search_mode: SearchMode = SearchMode.HYBRID_LEX_VEC
    lexical_was_sufficient: bool = False

    # Stage traces
    stages: List[StageTrace] = field(default_factory=list)

    # High-level metrics
    total_candidates: int = 0
    final_results_count: int = 0

    # Sources used
    indices_searched: List[str] = field(default_factory=list)
    collections_searched: List[str] = field(default_factory=list)

    # Errors and warnings
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def start_stage(self, stage: PipelineStage, input_count: int = 0) -> StageTrace:
        """Start tracking a new stage."""
        trace = StageTrace(
            stage=stage,
            started_at=time.time(),
            input_count=input_count,
        )
        self.stages.append(trace)
        return trace

    def complete(self, results_count: int = 0) -> None:
        """Mark pipeline as complete."""
        self.ended_at = time.time()
        self.total_duration_ms = (self.ended_at - self.started_at) * 1000
        self.final_results_count = results_count

    def add_error(self, error: str) -> None:
        """Add an error message."""
        self.errors.append(error)

    def add_warning(self, warning: str) -> None:
        """Add a warning message."""
        self.warnings.append(warning)

    def get_stage(self, stage: PipelineStage) -> Optional[StageTrace]:
        """Get trace for a specific stage."""
        for s in self.stages:
            if s.stage == stage:
                return s
        return None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "trace_id": self.trace_id,
            "total_duration_ms": round(self.total_duration_ms, 2),
            "original_query": self.original_query,
            "search_mode": self.search_mode.value,
            "lexical_was_sufficient": self.lexical_was_sufficient,
            "total_candidates": self.total_candidates,
            "final_results_count": self.final_results_count,
            "indices_searched": self.indices_searched,
            "collections_searched": self.collections_searched,
            "stages": [s.to_dict() for s in self.stages],
            "errors": self.errors,
            "warnings": self.warnings,
        }


@dataclass
class GraphContext:
    """Knowledge graph enrichment context."""

    entities: List[Dict[str, Any]] = field(default_factory=list)
    relationships: List[Dict[str, Any]] = field(default_factory=list)
    related_articles: List[str] = field(default_factory=list)
    related_cases: List[str] = field(default_factory=list)

    # Summary text for LLM context
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "entities_count": len(self.entities),
            "relationships_count": len(self.relationships),
            "related_articles": self.related_articles[:10],
            "related_cases": self.related_cases[:10],
            "summary_length": len(self.summary),
        }


@dataclass
class PipelineResult:
    """
    Complete result of a RAG pipeline execution.

    Contains the retrieved and processed results along with
    all metadata, traces, and enrichment data.
    """

    # Main results (the chunks to use for generation)
    results: List[Dict[str, Any]] = field(default_factory=list)

    # Full trace of execution
    trace: PipelineTrace = field(default_factory=PipelineTrace)

    # Graph enrichment context
    graph_context: Optional[GraphContext] = None

    # CRAG evaluation details
    crag_evaluation: Optional[CRAGEvaluation] = None

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Quick accessors
    @property
    def success(self) -> bool:
        """Check if pipeline completed successfully."""
        return len(self.results) > 0 and not self.trace.errors

    @property
    def search_mode(self) -> SearchMode:
        """Get the search mode used."""
        return self.trace.search_mode

    @property
    def total_duration_ms(self) -> float:
        """Get total pipeline duration."""
        return self.trace.total_duration_ms

    def __len__(self) -> int:
        """Return number of results."""
        return len(self.results)

    def __bool__(self) -> bool:
        """Return True if there are results."""
        return len(self.results) > 0

    def __iter__(self):
        """Iterate over results."""
        return iter(self.results)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "results_count": len(self.results),
            "success": self.success,
            "search_mode": self.search_mode.value,
            "total_duration_ms": round(self.total_duration_ms, 2),
            "trace": self.trace.to_dict(),
            "graph_context": self.graph_context.to_dict() if self.graph_context else None,
            "crag_evaluation": self.crag_evaluation.to_dict() if self.crag_evaluation else None,
            "metadata": self.metadata,
        }

    def get_context_for_llm(self, max_chars: int = 8000) -> str:
        """
        Get formatted context string for LLM consumption.

        Combines RAG results and graph context into a single
        context string suitable for prompting.
        """
        parts = []

        # Add RAG results
        current_chars = 0
        for i, result in enumerate(self.results):
            text = result.get("text", "")
            source = result.get("source", "")
            chunk_type = result.get("type", "unknown")

            header = f"[Source {i+1}: {chunk_type}]"
            if source:
                header += f" ({source})"

            entry = f"{header}\n{text}\n"

            if current_chars + len(entry) > max_chars:
                break

            parts.append(entry)
            current_chars += len(entry)

        # Add graph context summary if available and space permits
        if self.graph_context and self.graph_context.summary:
            remaining = max_chars - current_chars
            if remaining > 200:
                summary = self.graph_context.summary[:remaining - 50]
                parts.append(f"\n[Legal Context]\n{summary}")

        return "\n".join(parts)


# =============================================================================
# Main Pipeline Class
# =============================================================================

class RAGPipeline:
    """
    Main RAG Pipeline orchestrator.

    Coordinates all retrieval and processing stages to produce
    high-quality, relevant context for legal document generation.

    Architecture:
        Query -> Lexical Search -> Vector Search (conditional) -> Merge (RRF)
        -> CRAG Gate -> [Retry if needed] -> Rerank -> Expand
        -> Compress -> Graph Enrich -> Trace -> Response

    Example:
        >>> pipeline = RAGPipeline()
        >>> result = await pipeline.search("Art. 5 da Constituicao Federal")
        >>> print(result.results)
    """

    def __init__(
        self,
        config: Optional[RAGPipelineConfig] = None,
        opensearch: Optional[Any] = None,
        qdrant: Optional[Any] = None,
        embeddings: Optional[Any] = None,
        reranker: Optional[Any] = None,
        compressor: Optional[Any] = None,
        expander: Optional[Any] = None,
        graph: Optional[Any] = None,
        neo4j: Optional[Any] = None,
        crag_gate: Optional[Any] = None,
        query_expander: Optional[Any] = None,
    ):
        """
        Initialize the RAG pipeline.

        Args:
            config: Pipeline configuration
            opensearch: OpenSearch service instance (or will create default)
            qdrant: Qdrant service instance (or will create default)
            embeddings: Embeddings service instance (or will create default)
            reranker: Reranker instance (or will create default)
            compressor: Compressor instance (or will create default)
            expander: Chunk expander instance (or will create default)
            graph: Knowledge graph instance (or will create default)
            neo4j: Neo4j MVP service instance (or will create default)
            crag_gate: CRAG gate instance (or will create default)
            query_expander: Query expansion service (or will create default)
        """
        self.config = config or RAGPipelineConfig.from_rag_config()
        self._base_config = self.config.base_config

        # Initialize or store component instances
        self._opensearch = opensearch
        self._qdrant = qdrant
        self._embeddings = embeddings
        self._reranker = reranker
        self._compressor = compressor
        self._expander = expander
        self._graph = graph
        self._neo4j = neo4j
        self._crag_gate = crag_gate
        self._query_expander = query_expander

        # Lazy initialization flags
        self._components_initialized = False

        logger.info(
            f"RAGPipeline initialized: crag={self.config.crag_enabled}, "
            f"parallel={self.config.parallel_search}, "
            f"top_k={self.config.final_top_k}"
        )

    # =========================================================================
    # Component Initialization (Lazy)
    # =========================================================================

    def _ensure_components(self) -> None:
        """Lazily initialize components that weren't provided."""
        if self._components_initialized:
            return

        # OpenSearch
        if self._opensearch is None and OpenSearchService is not None:
            try:
                self._opensearch = OpenSearchService()
                logger.debug("OpenSearch service initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize OpenSearch: {e}")

        # Qdrant
        if self._qdrant is None and QdrantService is not None:
            try:
                self._qdrant = QdrantService()
                logger.debug("Qdrant service initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize Qdrant: {e}")

        # Embeddings
        if self._embeddings is None and get_embeddings_service is not None:
            try:
                self._embeddings = get_embeddings_service()
                logger.debug("Embeddings service initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize Embeddings: {e}")

        # Reranker
        if self._reranker is None and CrossEncoderReranker is not None:
            try:
                self._reranker = CrossEncoderReranker.get_instance()
                logger.debug("Reranker initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize Reranker: {e}")

        # Compressor
        if self._compressor is None and ContextCompressor is not None:
            try:
                self._compressor = ContextCompressor()
                logger.debug("Compressor initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize Compressor: {e}")

        # Chunk Expander
        if self._expander is None and ChunkExpander is not None:
            try:
                self._expander = ChunkExpander()
                logger.debug("Chunk expander initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize ChunkExpander: {e}")

        # Knowledge Graph (NetworkX-based)
        if self._graph is None and LegalKnowledgeGraph is not None:
            try:
                self._graph = LegalKnowledgeGraph()
                logger.debug("Knowledge graph initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize KnowledgeGraph: {e}")

        # Neo4j MVP (Graph Database)
        if self._neo4j is None and get_neo4j_mvp is not None:
            try:
                self._neo4j = get_neo4j_mvp()
                if self._neo4j.health_check():
                    logger.debug("Neo4j MVP service initialized and healthy")
                else:
                    logger.warning("Neo4j MVP service initialized but unhealthy")
                    self._neo4j = None
            except Exception as e:
                logger.debug(f"Neo4j MVP not available: {e}")
                self._neo4j = None

        # CRAG Gate
        if self._crag_gate is None and CRAGGate is not None:
            try:
                self._crag_gate = CRAGGate()
                logger.debug("CRAG gate initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize CRAGGate: {e}")

        # Query Expander
        if self._query_expander is None and QueryExpansionService is not None:
            try:
                self._query_expander = QueryExpansionService()
                logger.debug("Query expander initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize QueryExpander: {e}")

        self._components_initialized = True

    # =========================================================================
    # Utility Methods
    # =========================================================================

    def is_lexical_heavy(self, query: str) -> bool:
        """
        Determine if a query is likely to benefit more from lexical search.

        Citation-like queries (article references, case numbers, law numbers)
        tend to work better with exact BM25 matching than semantic search.

        Args:
            query: The search query

        Returns:
            True if query contains citation-like patterns
        """
        if not query:
            return False

        # Check against all citation patterns
        for pattern in CITATION_PATTERNS:
            if pattern.search(query):
                return True

        return False

    def _compute_rrf_score(
        self,
        lexical_rank: Optional[int],
        vector_rank: Optional[int],
        k: int = 60,
    ) -> float:
        """
        Compute RRF (Reciprocal Rank Fusion) score.

        RRF formula: 1 / (k + rank)

        Args:
            lexical_rank: Rank in lexical results (1-indexed, None if not present)
            vector_rank: Rank in vector results (1-indexed, None if not present)
            k: RRF constant (default 60)

        Returns:
            Combined RRF score
        """
        score = 0.0

        if lexical_rank is not None:
            score += self._base_config.lexical_weight * (1.0 / (k + lexical_rank))

        if vector_rank is not None:
            score += self._base_config.vector_weight * (1.0 / (k + vector_rank))

        return score

    def _merge_results_rrf(
        self,
        lexical_results: List[Dict[str, Any]],
        vector_results: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Merge lexical and vector results using RRF.

        Results are merged by chunk_uid (or generated from content hash).

        Args:
            lexical_results: Results from lexical search
            vector_results: Results from vector search

        Returns:
            Merged and sorted results
        """
        # Track results by unique identifier
        merged: Dict[str, Dict[str, Any]] = {}

        # Process lexical results
        for rank, result in enumerate(lexical_results, start=1):
            uid = result.get("chunk_uid") or result.get("id") or hash(result.get("text", ""))
            uid = str(uid)

            if uid not in merged:
                merged[uid] = result.copy()
                merged[uid]["_lexical_rank"] = rank
                merged[uid]["_vector_rank"] = None
                merged[uid]["lexical_score"] = result.get("score", 0.0)
            else:
                merged[uid]["_lexical_rank"] = rank
                merged[uid]["lexical_score"] = result.get("score", 0.0)

        # Process vector results
        for rank, result in enumerate(vector_results, start=1):
            uid = result.get("chunk_uid") or result.get("id") or hash(result.get("text", ""))
            uid = str(uid)

            if uid not in merged:
                merged[uid] = result.copy()
                merged[uid]["_lexical_rank"] = None
                merged[uid]["_vector_rank"] = rank
                merged[uid]["vector_score"] = result.get("score", 0.0)
            else:
                merged[uid]["_vector_rank"] = rank
                merged[uid]["vector_score"] = result.get("score", 0.0)

        # Compute RRF scores
        k = self._base_config.rrf_k
        for uid, result in merged.items():
            rrf_score = self._compute_rrf_score(
                result.get("_lexical_rank"),
                result.get("_vector_rank"),
                k=k,
            )
            result["final_score"] = rrf_score
            result["score"] = rrf_score  # Also set generic score field

            # Clean up internal fields
            result.pop("_lexical_rank", None)
            result.pop("_vector_rank", None)

        # Sort by final score descending
        sorted_results = sorted(
            merged.values(),
            key=lambda x: x.get("final_score", 0.0),
            reverse=True,
        )

        return sorted_results

    def _should_skip_vector_search(
        self,
        lexical_results: List[Dict[str, Any]],
        trace: PipelineTrace,
    ) -> bool:
        """
        Determine if vector search can be skipped based on lexical results.

        This is the lexical-first gating optimization for MVP.
        Skip vector search if:
        1. Query is citation-heavy (detected earlier)
        2. Lexical results have high scores
        3. We have enough high-quality results

        Args:
            lexical_results: Results from lexical search
            trace: Pipeline trace for recording decision

        Returns:
            True if vector search should be skipped
        """
        if not self._base_config.enable_lexical_first_gating:
            return False

        if not lexical_results:
            return False

        # Check if we have enough results
        if len(lexical_results) < self.config.lexical_min_results_for_skip:
            return False

        # Check best score
        best_score = max(r.get("score", 0.0) for r in lexical_results)
        if best_score < self.config.lexical_skip_vector_threshold:
            return False

        # Check average score of top results
        top_scores = [r.get("score", 0.0) for r in lexical_results[:5]]
        avg_score = sum(top_scores) / len(top_scores) if top_scores else 0.0

        if avg_score >= self.config.lexical_skip_vector_threshold * 0.8:
            trace.lexical_was_sufficient = True
            trace.add_warning(
                f"Skipping vector search: lexical sufficient (best={best_score:.3f}, avg={avg_score:.3f})"
            )
            return True

        return False

    # =========================================================================
    # Pipeline Stages
    # =========================================================================

    async def _stage_query_enhancement(
        self,
        query: str,
        trace: PipelineTrace,
    ) -> List[str]:
        """
        Stage 1: Query Enhancement (HyDE / Multi-query).

        Conditionally expands the query using HyDE (Hypothetical Document Embeddings)
        and/or multi-query expansion to improve recall.

        Args:
            query: Original query
            trace: Pipeline trace

        Returns:
            List of queries (original + expanded)
        """
        stage = trace.start_stage(PipelineStage.QUERY_ENHANCEMENT, input_count=1)
        queries = [query]

        try:
            # Check if expansion is enabled
            if not (self._base_config.enable_hyde or self._base_config.enable_multiquery):
                stage.skip("Query expansion disabled")
                return queries

            # Check if we have an expander
            if self._query_expander is None:
                stage.skip("Query expander not available")
                return queries

            # Don't expand citation-heavy queries (exact match is better)
            if self.is_lexical_heavy(query):
                stage.skip("Query is citation-heavy, skipping expansion")
                return queries

            # Perform expansion
            if hasattr(self._query_expander, "expand_async"):
                expanded = await self._query_expander.expand_async(
                    query,
                    use_hyde=self._base_config.enable_hyde,
                    use_multiquery=self._base_config.enable_multiquery,
                    max_queries=self._base_config.multiquery_max,
                )
            elif hasattr(self._query_expander, "expand"):
                expanded = self._query_expander.expand(
                    query,
                    use_hyde=self._base_config.enable_hyde,
                    use_multiquery=self._base_config.enable_multiquery,
                    max_queries=self._base_config.multiquery_max,
                )
            else:
                stage.skip("Query expander has no expand method")
                return queries

            if expanded:
                queries.extend(expanded)
                trace.enhanced_queries = expanded

            stage.complete(
                output_count=len(queries),
                data={"expanded_count": len(queries) - 1},
            )

        except Exception as e:
            error_msg = f"Query enhancement failed: {e}"
            logger.warning(error_msg)
            stage.fail(error_msg)
            if not self.config.fail_open:
                raise

        return queries

    async def _stage_lexical_search(
        self,
        queries: List[str],
        indices: List[str],
        filters: Optional[Dict[str, Any]],
        trace: PipelineTrace,
    ) -> List[Dict[str, Any]]:
        """
        Stage 2: Lexical Search (OpenSearch BM25).

        Performs BM25 lexical search across specified indices.

        Args:
            queries: List of queries to search
            indices: OpenSearch indices to search
            filters: Optional filters to apply
            trace: Pipeline trace

        Returns:
            List of search results
        """
        stage = trace.start_stage(PipelineStage.LEXICAL_SEARCH, input_count=len(queries))
        results: List[Dict[str, Any]] = []

        try:
            if self._opensearch is None:
                stage.skip("OpenSearch not available")
                return results

            trace.indices_searched = indices

            # Search with all queries
            for query in queries:
                try:
                    if hasattr(self._opensearch, "search_async"):
                        query_results = await self._opensearch.search_async(
                            query=query,
                            indices=indices,
                            top_k=self.config.max_results_per_source,
                            filters=filters,
                        )
                    elif hasattr(self._opensearch, "search"):
                        query_results = self._opensearch.search(
                            query=query,
                            indices=indices,
                            top_k=self.config.max_results_per_source,
                            filters=filters,
                        )
                    else:
                        continue

                    # Mark source
                    for r in query_results:
                        r["_source_type"] = "lexical"

                    results.extend(query_results)

                except Exception as e:
                    logger.warning(f"Lexical search failed for query: {e}")

            # Deduplicate by chunk_uid
            seen: Set[str] = set()
            unique_results = []
            for r in results:
                uid = str(r.get("chunk_uid") or r.get("id") or hash(r.get("text", "")))
                if uid not in seen:
                    seen.add(uid)
                    unique_results.append(r)

            results = unique_results

            stage.complete(
                output_count=len(results),
                data={
                    "indices": indices,
                    "queries_count": len(queries),
                },
            )

        except Exception as e:
            error_msg = f"Lexical search failed: {e}"
            logger.error(error_msg)
            stage.fail(error_msg)
            trace.add_error(error_msg)
            if not self.config.fail_open:
                raise

        return results

    async def _stage_vector_search(
        self,
        queries: List[str],
        collections: List[str],
        filters: Optional[Dict[str, Any]],
        trace: PipelineTrace,
    ) -> List[Dict[str, Any]]:
        """
        Stage 3: Vector Search (Qdrant).

        Performs semantic vector search across specified collections.
        May be skipped if lexical results are sufficient (lexical-first gating).

        Args:
            queries: List of queries to search
            collections: Qdrant collections to search
            filters: Optional filters to apply
            trace: Pipeline trace

        Returns:
            List of search results
        """
        stage = trace.start_stage(PipelineStage.VECTOR_SEARCH, input_count=len(queries))
        results: List[Dict[str, Any]] = []

        try:
            if self._qdrant is None:
                stage.skip("Qdrant not available")
                return results

            if self._embeddings is None:
                stage.skip("Embeddings service not available")
                return results

            trace.collections_searched = collections

            # Generate embeddings for queries
            for query in queries:
                try:
                    # Get embedding
                    if hasattr(self._embeddings, "embed_query"):
                        embedding = self._embeddings.embed_query(query)
                    else:
                        continue

                    # Search
                    if hasattr(self._qdrant, "search_async"):
                        query_results = await self._qdrant.search_async(
                            vector=embedding,
                            collections=collections,
                            top_k=self.config.max_results_per_source,
                            filters=filters,
                        )
                    elif hasattr(self._qdrant, "search"):
                        query_results = self._qdrant.search(
                            vector=embedding,
                            collections=collections,
                            top_k=self.config.max_results_per_source,
                            filters=filters,
                        )
                    else:
                        continue

                    # Mark source
                    for r in query_results:
                        r["_source_type"] = "vector"

                    results.extend(query_results)

                except Exception as e:
                    logger.warning(f"Vector search failed for query: {e}")

            # Deduplicate by chunk_uid
            seen: Set[str] = set()
            unique_results = []
            for r in results:
                uid = str(r.get("chunk_uid") or r.get("id") or hash(r.get("text", "")))
                if uid not in seen:
                    seen.add(uid)
                    unique_results.append(r)

            results = unique_results

            stage.complete(
                output_count=len(results),
                data={
                    "collections": collections,
                    "queries_count": len(queries),
                },
            )

        except Exception as e:
            error_msg = f"Vector search failed: {e}"
            logger.error(error_msg)
            stage.fail(error_msg)
            trace.add_error(error_msg)
            if not self.config.fail_open:
                raise

        return results

    async def _stage_merge_rrf(
        self,
        lexical_results: List[Dict[str, Any]],
        vector_results: List[Dict[str, Any]],
        trace: PipelineTrace,
    ) -> List[Dict[str, Any]]:
        """
        Stage 4: Merge (RRF fusion by chunk_uid).

        Combines lexical and vector results using Reciprocal Rank Fusion.

        Args:
            lexical_results: Results from lexical search
            vector_results: Results from vector search
            trace: Pipeline trace

        Returns:
            Merged and scored results
        """
        total_input = len(lexical_results) + len(vector_results)
        stage = trace.start_stage(PipelineStage.MERGE_RRF, input_count=total_input)

        try:
            merged = self._merge_results_rrf(lexical_results, vector_results)
            trace.total_candidates = len(merged)

            stage.complete(
                output_count=len(merged),
                data={
                    "lexical_count": len(lexical_results),
                    "vector_count": len(vector_results),
                    "merged_count": len(merged),
                },
            )

            return merged

        except Exception as e:
            error_msg = f"RRF merge failed: {e}"
            logger.error(error_msg)
            stage.fail(error_msg)
            trace.add_error(error_msg)

            # Fallback: return lexical results if available
            if self.config.fail_open:
                return lexical_results or vector_results
            raise

    async def _enrich_from_neo4j(
        self,
        query: str,
        existing_results: List[Dict[str, Any]],
        tenant_id: Optional[str] = None,
        scope: str = "global",
        case_id: Optional[str] = None,
        max_chunks: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Enrich results with chunks from Neo4j graph.

        Used when CRAG gate detects weak evidence to add
        graph-connected chunks.

        Args:
            query: Search query
            existing_results: Current results to enrich
            tenant_id: Tenant identifier
            scope: Access scope
            case_id: Case identifier
            max_chunks: Maximum chunks to add

        Returns:
            Enriched results list
        """
        if self._neo4j is None or Neo4jEntityExtractor is None:
            return existing_results

        try:
            # Extract entities from query
            entities = Neo4jEntityExtractor.extract(query)
            entity_ids = [e["entity_id"] for e in entities]

            if not entity_ids:
                return existing_results

            # Get chunks from Neo4j
            graph_chunks = self._neo4j.query_chunks_by_entities(
                entity_ids=entity_ids,
                tenant_id=tenant_id or "default",
                scope=scope,
                case_id=case_id,
                limit=max_chunks,
            )

            # Track existing chunk UIDs
            existing_uids = {
                r.get("chunk_uid") or r.get("id") for r in existing_results
            }

            # Add new chunks from graph
            added = 0
            for gc in graph_chunks:
                uid = gc.get("chunk_uid")
                if uid and uid not in existing_uids:
                    existing_results.append({
                        "chunk_uid": uid,
                        "text": gc.get("text_preview", ""),
                        "doc_hash": gc.get("doc_hash"),
                        "doc_title": gc.get("doc_title"),
                        "source_type": gc.get("source_type", "graph"),
                        "matched_entities": gc.get("matched_entities", []),
                        "_source_type": "neo4j_graph",
                        "score": 0.5,  # Default graph score
                    })
                    existing_uids.add(uid)
                    added += 1

            if added > 0:
                logger.debug(f"Neo4j enrichment added {added} chunks from graph")

            return existing_results

        except Exception as e:
            logger.warning(f"Neo4j chunk enrichment failed: {e}")
            return existing_results

    async def _stage_crag_gate(
        self,
        query: str,
        results: List[Dict[str, Any]],
        trace: PipelineTrace,
        tenant_id: Optional[str] = None,
        scope: str = "global",
        case_id: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], CRAGEvaluation]:
        """
        Stage 5: CRAG Gate with retry logic.

        Evaluates result quality and optionally retries with
        query expansion if results are insufficient.

        Args:
            query: Original query
            results: Current results
            trace: Pipeline trace

        Returns:
            Tuple of (filtered results, CRAG evaluation)
        """
        stage = trace.start_stage(PipelineStage.CRAG_GATE, input_count=len(results))

        evaluation = CRAGEvaluation(
            decision=CRAGDecision.ACCEPT,
            total_count=len(results),
        )

        try:
            if not self.config.crag_enabled or self._crag_gate is None:
                stage.skip("CRAG gate disabled or not available")
                return results, evaluation

            # Evaluate results
            if hasattr(self._crag_gate, "evaluate_async"):
                crag_result = await self._crag_gate.evaluate_async(query, results)
            elif hasattr(self._crag_gate, "evaluate"):
                crag_result = self._crag_gate.evaluate(query, results)
            else:
                stage.skip("CRAG gate has no evaluate method")
                return results, evaluation

            # Parse CRAG result
            if hasattr(crag_result, "best_score"):
                evaluation.best_score = crag_result.best_score
            if hasattr(crag_result, "avg_score"):
                evaluation.avg_score = crag_result.avg_score
            if hasattr(crag_result, "scores"):
                evaluation.scores = list(crag_result.scores)
            if hasattr(crag_result, "passed_count"):
                evaluation.passed_count = crag_result.passed_count

            # Determine decision
            if evaluation.best_score >= self._base_config.crag_min_best_score:
                evaluation.decision = CRAGDecision.ACCEPT
            elif evaluation.avg_score >= self._base_config.crag_min_avg_score:
                evaluation.decision = CRAGDecision.ACCEPT
            else:
                evaluation.decision = CRAGDecision.RETRY

            # Handle retry logic
            if evaluation.decision == CRAGDecision.RETRY:
                retry_count = 0
                max_retries = self._base_config.crag_max_retries

                while retry_count < max_retries and evaluation.decision == CRAGDecision.RETRY:
                    retry_count += 1
                    evaluation.retry_count = retry_count

                    # Strategy 1: Try Neo4j graph enrichment first (fast, deterministic)
                    if self._neo4j is not None:
                        try:
                            original_count = len(results)
                            results = await self._enrich_from_neo4j(
                                query=query,
                                existing_results=results,
                                tenant_id=tenant_id,
                                scope=scope,
                                case_id=case_id,
                                max_chunks=10,
                            )
                            if len(results) > original_count:
                                trace.add_warning(
                                    f"CRAG retry {retry_count}: Neo4j added "
                                    f"{len(results) - original_count} graph chunks"
                                )
                                evaluation.retry_improved = True
                        except Exception as e:
                            logger.warning(f"CRAG Neo4j retry failed: {e}")

                    # Strategy 2: Try query expansion (slower, uses LLM)
                    if self.config.crag_retry_with_expansion and self._query_expander:
                        try:
                            expanded = []
                            if hasattr(self._query_expander, "expand_async"):
                                expanded = await self._query_expander.expand_async(
                                    query,
                                    use_hyde=True,
                                    max_queries=2,
                                )
                            elif hasattr(self._query_expander, "expand"):
                                expanded = self._query_expander.expand(
                                    query,
                                    use_hyde=True,
                                    max_queries=2,
                                )

                            if expanded:
                                evaluation.retry_queries.extend(expanded)
                                trace.add_warning(
                                    f"CRAG retry {retry_count}: expanded to {len(expanded)} queries"
                                )
                        except Exception as e:
                            logger.warning(f"CRAG retry expansion failed: {e}")

                    # Accept after retries
                    evaluation.decision = CRAGDecision.ACCEPT

            # Filter results based on scores if we have them
            filtered_results = results
            if evaluation.scores and len(evaluation.scores) == len(results):
                # Keep results above minimum threshold
                filtered_results = [
                    r for r, score in zip(results, evaluation.scores)
                    if score >= self.config.crag_min_relevance_score
                ]
                evaluation.passed_count = len(filtered_results)

            stage.complete(
                output_count=len(filtered_results),
                data={
                    "decision": evaluation.decision.value,
                    "best_score": round(evaluation.best_score, 4),
                    "retry_count": evaluation.retry_count,
                },
            )

            return filtered_results, evaluation

        except Exception as e:
            error_msg = f"CRAG gate failed: {e}"
            logger.warning(error_msg)
            stage.fail(error_msg)

            if self.config.fail_open:
                return results, evaluation
            raise

    async def _stage_rerank(
        self,
        query: str,
        results: List[Dict[str, Any]],
        trace: PipelineTrace,
    ) -> List[Dict[str, Any]]:
        """
        Stage 6: Rerank (cross-encoder top N).

        Uses a cross-encoder model to rerank results for higher precision.

        Args:
            query: Search query
            results: Results to rerank
            trace: Pipeline trace

        Returns:
            Reranked results
        """
        stage = trace.start_stage(PipelineStage.RERANK, input_count=len(results))

        try:
            if not self._base_config.enable_rerank or self._reranker is None:
                stage.skip("Reranking disabled or reranker not available")
                return results

            # Limit candidates for efficiency
            candidates = results[:self._base_config.default_fetch_k]

            # Rerank
            if hasattr(self._reranker, "rerank"):
                rerank_result = self._reranker.rerank(
                    query,
                    candidates,
                    top_k=self.config.final_top_k,
                )

                if hasattr(rerank_result, "results"):
                    reranked = rerank_result.results
                else:
                    reranked = rerank_result
            else:
                stage.skip("Reranker has no rerank method")
                return results

            stage.complete(
                output_count=len(reranked),
                data={
                    "model": self._base_config.rerank_model,
                    "candidates": len(candidates),
                },
            )

            return reranked

        except Exception as e:
            error_msg = f"Reranking failed: {e}"
            logger.warning(error_msg)
            stage.fail(error_msg)

            if self.config.fail_open:
                return results[:self.config.final_top_k]
            raise

    async def _stage_expand(
        self,
        results: List[Dict[str, Any]],
        trace: PipelineTrace,
    ) -> List[Dict[str, Any]]:
        """
        Stage 7: Expand (sibling chunks).

        Expands retrieved chunks to include surrounding context
        (parent-child or sibling retrieval).

        Args:
            results: Results to expand
            trace: Pipeline trace

        Returns:
            Expanded results
        """
        stage = trace.start_stage(PipelineStage.EXPAND, input_count=len(results))

        try:
            if not self._base_config.enable_chunk_expansion or self._expander is None:
                stage.skip("Chunk expansion disabled or expander not available")
                return results

            # Expand
            if hasattr(self._expander, "expand_async"):
                expanded = await self._expander.expand_async(
                    results,
                    window=self._base_config.chunk_expansion_window,
                    max_extra=self._base_config.chunk_expansion_max_extra,
                )
            elif hasattr(self._expander, "expand"):
                expanded = self._expander.expand(
                    results,
                    window=self._base_config.chunk_expansion_window,
                    max_extra=self._base_config.chunk_expansion_max_extra,
                )
            else:
                stage.skip("Expander has no expand method")
                return results

            stage.complete(
                output_count=len(expanded),
                data={
                    "original_count": len(results),
                    "expanded_count": len(expanded),
                },
            )

            return expanded

        except Exception as e:
            error_msg = f"Chunk expansion failed: {e}"
            logger.warning(error_msg)
            stage.fail(error_msg)

            if self.config.fail_open:
                return results
            raise

    async def _stage_compress(
        self,
        query: str,
        results: List[Dict[str, Any]],
        trace: PipelineTrace,
    ) -> List[Dict[str, Any]]:
        """
        Stage 8: Compress (keyword extraction).

        Compresses results to fit within token budgets while
        preserving the most relevant content.

        Args:
            query: Search query (for keyword extraction)
            results: Results to compress
            trace: Pipeline trace

        Returns:
            Compressed results
        """
        stage = trace.start_stage(PipelineStage.COMPRESS, input_count=len(results))

        try:
            if not self._base_config.enable_compression or self._compressor is None:
                stage.skip("Compression disabled or compressor not available")
                return results

            # Compress
            if hasattr(self._compressor, "compress_results"):
                compression_result = self._compressor.compress_results(
                    query,
                    results,
                    token_budget=self._base_config.compression_token_budget,
                )

                if hasattr(compression_result, "results"):
                    compressed = compression_result.results
                    compression_ratio = getattr(compression_result, "compression_ratio", 1.0)
                else:
                    compressed = compression_result
                    compression_ratio = 1.0
            else:
                stage.skip("Compressor has no compress_results method")
                return results

            stage.complete(
                output_count=len(compressed),
                data={
                    "compression_ratio": round(compression_ratio, 3),
                    "token_budget": self._base_config.compression_token_budget,
                },
            )

            return compressed

        except Exception as e:
            error_msg = f"Compression failed: {e}"
            logger.warning(error_msg)
            stage.fail(error_msg)

            if self.config.fail_open:
                return results
            raise

    async def _stage_graph_enrich(
        self,
        query: str,
        results: List[Dict[str, Any]],
        trace: PipelineTrace,
        tenant_id: Optional[str] = None,
        scope: str = "global",
        case_id: Optional[str] = None,
    ) -> GraphContext:
        """
        Stage 9: Graph Enrich (knowledge graph context).

        Enriches results with knowledge graph context including
        related legal entities, articles, and case law.

        Uses Neo4j MVP when available for path-based queries,
        falls back to NetworkX for simple lookups.

        Args:
            query: Search query
            results: Results to enrich from
            trace: Pipeline trace
            tenant_id: Tenant identifier for Neo4j security trimming
            scope: Access scope (global, private, group, local)
            case_id: Case identifier for local scope

        Returns:
            GraphContext with enrichment data
        """
        stage = trace.start_stage(PipelineStage.GRAPH_ENRICH, input_count=len(results))
        graph_context = GraphContext()

        try:
            if not self._base_config.enable_graph_enrich:
                stage.skip("Graph enrichment disabled")
                return graph_context

            # Check if we have any graph backend
            has_neo4j = self._neo4j is not None
            has_networkx = self._graph is not None

            if not has_neo4j and not has_networkx:
                stage.skip("No graph backend available")
                return graph_context

            # Extract entities from query and results
            entity_ids: List[str] = []
            entities_to_lookup: List[Tuple[str, str]] = []

            # Use Neo4j entity extractor if available (better patterns)
            if has_neo4j and Neo4jEntityExtractor is not None:
                # Extract from query
                query_entities = Neo4jEntityExtractor.extract(query)
                entity_ids.extend([e["entity_id"] for e in query_entities])

                # Extract from results
                for result in results:
                    text = result.get("text", "")
                    result_entities = Neo4jEntityExtractor.extract(text)
                    for ent in result_entities[:5]:  # Limit per result
                        if ent["entity_id"] not in entity_ids:
                            entity_ids.append(ent["entity_id"])
                            graph_context.entities.append({
                                "type": ent["entity_type"],
                                "name": ent["name"],
                                "id": ent["entity_id"],
                            })
            else:
                # Fallback to simple regex
                for result in results:
                    text = result.get("text", "")
                    for match in re.finditer(r"art\.?\s*(\d+)", text, re.IGNORECASE):
                        entities_to_lookup.append(("article", match.group(0)))
                    for match in re.finditer(r"lei\s+n?\.?\s*(\d+)", text, re.IGNORECASE):
                        entities_to_lookup.append(("law", match.group(0)))

            # Neo4j path-based enrichment (preferred)
            neo4j_paths = []
            if has_neo4j and entity_ids:
                try:
                    # Find paths for explainable context
                    neo4j_paths = self._neo4j.find_paths(
                        entity_ids=entity_ids[:10],  # Limit entities
                        tenant_id=tenant_id or "default",
                        scope=scope,
                        max_hops=self._base_config.graph_hops,
                        limit=15,
                    )

                    # Build relationships from paths
                    for path in neo4j_paths:
                        path_names = path.get("path_names", [])
                        path_rels = path.get("path_relations", [])
                        if len(path_names) >= 2 and path_rels:
                            graph_context.relationships.append({
                                "source": path_names[0],
                                "target": path_names[-1],
                                "relations": path_rels,
                                "path_length": path.get("path_length", 1),
                            })

                    # Find co-occurring entities (chunks with multiple matches)
                    if len(entity_ids) >= 2:
                        cooccur = self._neo4j.find_cooccurrence(
                            entity_ids=entity_ids[:5],
                            tenant_id=tenant_id or "default",
                            scope=scope,
                            min_matches=2,
                            limit=5,
                        )
                        for co in cooccur:
                            matched = co.get("matched_entities", [])
                            if matched:
                                graph_context.related_articles.extend(
                                    [m for m in matched if "art" in m.lower()]
                                )

                    # Build summary from Neo4j paths
                    if neo4j_paths and build_graph_context is not None:
                        graph_context.summary = build_graph_context(
                            neo4j_paths, max_chars=500
                        )

                    logger.debug(
                        f"Neo4j enrichment: {len(entity_ids)} entities, "
                        f"{len(neo4j_paths)} paths, {len(graph_context.relationships)} rels"
                    )

                except Exception as e:
                    logger.warning(f"Neo4j graph enrichment failed: {e}")

            # NetworkX fallback/supplement
            if has_networkx and entities_to_lookup and not neo4j_paths:
                try:
                    if hasattr(self._graph, "get_related_async"):
                        related = await self._graph.get_related_async(
                            entities=entities_to_lookup,
                            hops=self._base_config.graph_hops,
                            max_nodes=self._base_config.graph_max_nodes,
                        )
                    elif hasattr(self._graph, "get_related"):
                        related = self._graph.get_related(
                            entities=entities_to_lookup,
                            hops=self._base_config.graph_hops,
                            max_nodes=self._base_config.graph_max_nodes,
                        )
                    else:
                        related = None

                    if related:
                        if not graph_context.entities:
                            graph_context.entities = related.get("entities", [])
                        graph_context.relationships.extend(related.get("relationships", []))
                        graph_context.related_articles.extend(related.get("articles", []))
                        graph_context.related_cases.extend(related.get("cases", []))

                except Exception as e:
                    logger.warning(f"NetworkX graph lookup failed: {e}")

            # Generate summary if not already set
            if not graph_context.summary and graph_context.entities:
                graph_context.summary = self._generate_graph_summary(graph_context)

            # Deduplicate
            graph_context.related_articles = list(set(graph_context.related_articles))[:10]
            graph_context.related_cases = list(set(graph_context.related_cases))[:10]

            stage.complete(
                output_count=len(graph_context.entities),
                data={
                    "entities_found": len(graph_context.entities),
                    "relationships_found": len(graph_context.relationships),
                    "neo4j_used": has_neo4j and bool(neo4j_paths),
                    "networkx_used": has_networkx and not neo4j_paths,
                },
            )

            return graph_context

        except Exception as e:
            error_msg = f"Graph enrichment failed: {e}"
            logger.warning(error_msg)
            stage.fail(error_msg)

            return graph_context

    def _generate_graph_summary(self, graph_context: GraphContext) -> str:
        """Generate a text summary of graph context for LLM consumption."""
        parts = []

        if graph_context.related_articles:
            articles = ", ".join(graph_context.related_articles[:5])
            parts.append(f"Artigos relacionados: {articles}")

        if graph_context.related_cases:
            cases = ", ".join(graph_context.related_cases[:3])
            parts.append(f"Jurisprudencia relacionada: {cases}")

        if graph_context.entities:
            entity_types = {}
            for entity in graph_context.entities[:10]:
                etype = entity.get("type", "unknown")
                if etype not in entity_types:
                    entity_types[etype] = []
                entity_types[etype].append(entity.get("name", ""))

            for etype, names in entity_types.items():
                parts.append(f"{etype.capitalize()}: {', '.join(names[:3])}")

        return "; ".join(parts)

    async def _stage_trace(
        self,
        trace: PipelineTrace,
        result: PipelineResult,
    ) -> None:
        """
        Stage 10: Trace (audit trail).

        Finalizes the trace and optionally persists it for audit purposes.

        Args:
            trace: Pipeline trace to finalize
            result: Final pipeline result
        """
        stage = trace.start_stage(PipelineStage.TRACE, input_count=len(result.results))

        try:
            if not self._base_config.enable_tracing:
                stage.skip("Tracing disabled")
                return

            # Complete trace
            trace.complete(results_count=len(result.results))

            # Log trace summary
            if self.config.verbose_logging:
                logger.info(
                    f"Pipeline complete: {trace.trace_id} | "
                    f"mode={trace.search_mode.value} | "
                    f"results={len(result.results)} | "
                    f"duration={trace.total_duration_ms:.1f}ms"
                )

            # Persist trace if configured
            if self._base_config.trace_persist_db and trace_event is not None:
                try:
                    trace_event(
                        event_type="pipeline_complete",
                        trace_id=trace.trace_id,
                        data=trace.to_dict(),
                    )
                except Exception as e:
                    logger.warning(f"Failed to persist trace: {e}")

            stage.complete(data={"trace_id": trace.trace_id})

        except Exception as e:
            error_msg = f"Trace finalization failed: {e}"
            logger.warning(error_msg)
            stage.fail(error_msg)

    # =========================================================================
    # Main Entry Points
    # =========================================================================

    async def search(
        self,
        query: str,
        indices: Optional[List[str]] = None,
        collections: Optional[List[str]] = None,
        filters: Optional[Dict[str, Any]] = None,
        top_k: Optional[int] = None,
        include_graph: bool = True,
        tenant_id: Optional[str] = None,
        scope: str = "global",
        case_id: Optional[str] = None,
    ) -> PipelineResult:
        """
        Main search entry point - executes the full RAG pipeline.

        Pipeline flow:
            Query -> Lexical Search -> Vector Search (conditional) -> Merge (RRF)
            -> CRAG Gate -> [Retry if needed] -> Rerank -> Expand
            -> Compress -> Graph Enrich -> Trace -> Response

        Args:
            query: Search query
            indices: OpenSearch indices to search (defaults to all)
            collections: Qdrant collections to search (defaults to all)
            filters: Optional filters (e.g., case_id, document_type)
            top_k: Number of final results (defaults to config)
            include_graph: Whether to include graph enrichment
            tenant_id: Tenant identifier for multi-tenant access control
            scope: Access scope (global, private, group, local)
            case_id: Case identifier for local scope filtering

        Returns:
            PipelineResult with results, trace, and metadata
        """
        # Initialize trace
        trace = PipelineTrace(original_query=query)
        result = PipelineResult(trace=trace)

        try:
            # Ensure components are initialized
            self._ensure_components()

            # Set defaults
            indices = indices or self._base_config.get_opensearch_indices()
            collections = collections or self._base_config.get_qdrant_collections()
            final_top_k = top_k or self.config.final_top_k

            # Detect query characteristics
            is_citation_query = self.is_lexical_heavy(query)

            # Stage 1: Query Enhancement
            queries = await self._stage_query_enhancement(query, trace)

            # Stage 2: Lexical Search
            lexical_results = await self._stage_lexical_search(
                queries, indices, filters, trace
            )

            # Determine if we should skip vector search (lexical-first gating)
            skip_vector = is_citation_query or self._should_skip_vector_search(
                lexical_results, trace
            )

            # Stage 3: Vector Search (conditional)
            vector_results: List[Dict[str, Any]] = []
            if not skip_vector:
                vector_results = await self._stage_vector_search(
                    queries, collections, filters, trace
                )
                trace.search_mode = SearchMode.HYBRID_LEX_VEC
            else:
                trace.search_mode = SearchMode.LEXICAL_ONLY
                vector_stage = trace.start_stage(
                    PipelineStage.VECTOR_SEARCH, input_count=0
                )
                vector_stage.skip(
                    "Lexical results sufficient" if trace.lexical_was_sufficient
                    else "Citation-heavy query"
                )

            # Stage 4: Merge (RRF)
            merged_results = await self._stage_merge_rrf(
                lexical_results, vector_results, trace
            )

            # Stage 5: CRAG Gate
            filtered_results, crag_eval = await self._stage_crag_gate(
                query, merged_results, trace,
                tenant_id=tenant_id,
                scope=scope,
                case_id=case_id,
            )
            result.crag_evaluation = crag_eval

            # Stage 6: Rerank
            reranked_results = await self._stage_rerank(
                query, filtered_results, trace
            )

            # Stage 7: Expand
            expanded_results = await self._stage_expand(reranked_results, trace)

            # Stage 8: Compress
            compressed_results = await self._stage_compress(
                query, expanded_results, trace
            )

            # Stage 9: Graph Enrich
            if include_graph:
                graph_context = await self._stage_graph_enrich(
                    query, compressed_results, trace,
                    tenant_id=tenant_id,
                    scope=scope,
                    case_id=case_id,
                )
                result.graph_context = graph_context

            # Finalize results
            result.results = compressed_results[:final_top_k]

            # Stage 10: Trace
            await self._stage_trace(trace, result)

            # Add metadata
            result.metadata = {
                "query": query,
                "indices": indices,
                "collections": collections,
                "top_k": final_top_k,
                "is_citation_query": is_citation_query,
            }

            return result

        except Exception as e:
            error_msg = f"Pipeline failed: {e}"
            logger.error(error_msg, exc_info=True)
            trace.add_error(error_msg)
            trace.complete(results_count=0)
            result.trace = trace

            if not self.config.fail_open:
                raise

            return result

    def search_sync(
        self,
        query: str,
        indices: Optional[List[str]] = None,
        collections: Optional[List[str]] = None,
        filters: Optional[Dict[str, Any]] = None,
        top_k: Optional[int] = None,
        include_graph: bool = True,
        tenant_id: Optional[str] = None,
        scope: str = "global",
        case_id: Optional[str] = None,
    ) -> PipelineResult:
        """
        Synchronous wrapper for the search method.

        Creates a new event loop if needed and runs the async search.

        Args:
            query: Search query
            indices: OpenSearch indices to search
            collections: Qdrant collections to search
            filters: Optional filters
            top_k: Number of final results
            include_graph: Whether to include graph enrichment
            tenant_id: Tenant identifier for multi-tenant access control
            scope: Access scope (global, private, group, local)
            case_id: Case identifier for local scope filtering

        Returns:
            PipelineResult with results, trace, and metadata
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None:
            # Already in an async context - create a new thread
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    asyncio.run,
                    self.search(
                        query=query,
                        indices=indices,
                        collections=collections,
                        filters=filters,
                        top_k=top_k,
                        include_graph=include_graph,
                        tenant_id=tenant_id,
                        scope=scope,
                        case_id=case_id,
                    )
                )
                return future.result()
        else:
            # No event loop - create one
            return asyncio.run(
                self.search(
                    query=query,
                    indices=indices,
                    collections=collections,
                    filters=filters,
                    top_k=top_k,
                    include_graph=include_graph,
                    tenant_id=tenant_id,
                    scope=scope,
                    case_id=case_id,
                )
            )


# =============================================================================
# Module-level convenience functions
# =============================================================================

_pipeline: Optional[RAGPipeline] = None


def get_rag_pipeline(config: Optional[RAGPipelineConfig] = None) -> RAGPipeline:
    """
    Get or create the RAG pipeline singleton.

    Args:
        config: Optional configuration (only used on first call)

    Returns:
        RAGPipeline instance
    """
    global _pipeline

    if _pipeline is None:
        _pipeline = RAGPipeline(config=config)

    return _pipeline


def reset_rag_pipeline() -> None:
    """Reset the RAG pipeline singleton."""
    global _pipeline
    _pipeline = None


async def search(
    query: str,
    indices: Optional[List[str]] = None,
    collections: Optional[List[str]] = None,
    filters: Optional[Dict[str, Any]] = None,
    top_k: Optional[int] = None,
    tenant_id: Optional[str] = None,
    scope: str = "global",
    case_id: Optional[str] = None,
) -> PipelineResult:
    """
    Convenience function to search using the default pipeline.

    Args:
        query: Search query
        indices: OpenSearch indices to search
        collections: Qdrant collections to search
        filters: Optional filters
        top_k: Number of final results
        tenant_id: Tenant identifier for multi-tenant access control
        scope: Access scope (global, private, group, local)
        case_id: Case identifier for local scope filtering

    Returns:
        PipelineResult with results, trace, and metadata
    """
    pipeline = get_rag_pipeline()
    return await pipeline.search(
        query=query,
        indices=indices,
        collections=collections,
        filters=filters,
        top_k=top_k,
        tenant_id=tenant_id,
        scope=scope,
        case_id=case_id,
    )


def search_sync(
    query: str,
    indices: Optional[List[str]] = None,
    collections: Optional[List[str]] = None,
    filters: Optional[Dict[str, Any]] = None,
    top_k: Optional[int] = None,
    tenant_id: Optional[str] = None,
    scope: str = "global",
    case_id: Optional[str] = None,
) -> PipelineResult:
    """
    Convenience function for synchronous search.

    Args:
        query: Search query
        indices: OpenSearch indices to search
        collections: Qdrant collections to search
        filters: Optional filters
        top_k: Number of final results
        tenant_id: Tenant identifier for multi-tenant access control
        scope: Access scope (global, private, group, local)
        case_id: Case identifier for local scope filtering

    Returns:
        PipelineResult with results, trace, and metadata
    """
    pipeline = get_rag_pipeline()
    return pipeline.search_sync(
        query=query,
        indices=indices,
        collections=collections,
        filters=filters,
        top_k=top_k,
        tenant_id=tenant_id,
        scope=scope,
        case_id=case_id,
    )


__all__ = [
    # Enums
    "SearchMode",
    "PipelineStage",
    "CRAGDecision",
    # Config
    "RAGPipelineConfig",
    # Data classes
    "StageTrace",
    "CRAGEvaluation",
    "PipelineTrace",
    "GraphContext",
    "PipelineResult",
    # Main class
    "RAGPipeline",
    # Module functions
    "get_rag_pipeline",
    "reset_rag_pipeline",
    "search",
    "search_sync",
]
