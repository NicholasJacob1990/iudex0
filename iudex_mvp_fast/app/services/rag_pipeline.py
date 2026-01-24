"""
RAG Pipeline - Full Retrieval Orchestration

This module provides the complete RAG pipeline that integrates all components:

Query -> Lexical Search -> Vector Search (conditional) -> Merge (RRF)
-> CRAG Gate -> [Retry if needed] -> Rerank -> Expand
-> Compress -> Graph Enrich -> Trace -> Response

Configuration via environment variables:
- RAG_ENABLE_CRAG: Enable CRAG gate (default: true)
- RAG_ENABLE_HYDE: Enable HyDE query expansion (default: true)
- RAG_ENABLE_MULTIQUERY: Enable multi-query expansion (default: true)
- RAG_ENABLE_RERANK: Enable cross-encoder reranking (default: true)
- RAG_ENABLE_COMPRESSION: Enable context compression (default: true)
- RAG_ENABLE_GRAPH_ENRICH: Enable GraphRAG enrichment (default: true)
- RAG_ENABLE_TRACING: Enable pipeline tracing (default: true)
- RAG_ENABLE_CHUNK_EXPANSION: Enable chunk expansion (default: true)
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.settings import get_pipeline_config, RAGPipelineConfig

# Import pipeline components
from app.services.crag_gate import (
    CRAGConfig,
    CRAGGate,
    CRAGOrchestrator,
    CRAGEvaluation,
    EvidenceLevel,
    evaluate_crag_gate,
)
from app.services.query_expansion import (
    QueryExpansionConfig,
    QueryExpansionService,
    get_query_expansion_service,
    merge_lexical_vector_rrf,
    merge_results_rrf,
)
from app.services.reranker import (
    CrossEncoderReranker,
    RerankerConfig,
)
from app.services.context_compressor import (
    ContextCompressor,
    CompressionConfig,
)
from app.services.chunk_expander import (
    ChunkExpander,
    ExpansionConfig,
)
from app.services.graph_rag import (
    LegalKnowledgeGraph,
    get_scoped_knowledge_graph,
    get_global_knowledge_graph,
    get_tenant_knowledge_graph,
    enrich_chunk_with_graph,
    Scope,
)
from app.services.rag_trace import PipelineTracer, trace_event

logger = logging.getLogger("RAGPipeline")


# =============================================================================
# DATA CLASSES
# =============================================================================


@dataclass
class PipelineTrace:
    """Trace data collected throughout the pipeline."""
    request_id: str
    started_at: float = field(default_factory=time.perf_counter)
    events: List[Dict[str, Any]] = field(default_factory=list)

    def add_event(self, name: str, data: Dict[str, Any]) -> None:
        """Add a trace event."""
        self.events.append({
            "event": name,
            "ts": datetime.utcnow().isoformat(),
            "elapsed_ms": int((time.perf_counter() - self.started_at) * 1000),
            **data,
        })

    def to_dict(self) -> Dict[str, Any]:
        """Convert trace to dictionary."""
        return {
            "request_id": self.request_id,
            "total_duration_ms": int((time.perf_counter() - self.started_at) * 1000),
            "events": self.events,
        }


@dataclass
class PipelineResult:
    """Result from the RAG pipeline."""
    results: List[Dict[str, Any]]
    trace: Optional[PipelineTrace] = None
    graph_context: str = ""
    crag_evaluation: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_high_quality(self) -> bool:
        """Check if results passed CRAG gate."""
        if self.crag_evaluation:
            return self.crag_evaluation.get("gate_passed", False)
        return len(self.results) > 0


# =============================================================================
# RAG PIPELINE
# =============================================================================


class RAGPipeline:
    """
    Complete RAG Pipeline with all advanced retrieval features.

    Pipeline stages:
    1. Query Enhancement (HyDE / Multi-query)
    2. Lexical Search (BM25/OpenSearch)
    3. Vector Search (Embeddings/Qdrant)
    4. Merge (RRF fusion)
    5. CRAG Gate (quality check with retry)
    6. Rerank (cross-encoder scoring)
    7. Expand (sibling chunks)
    8. Compress (keyword extraction)
    9. Graph Enrich (knowledge graph context)
    10. Trace (audit trail)
    """

    def __init__(
        self,
        config: Optional[RAGPipelineConfig] = None,
        query_expansion: Optional[QueryExpansionService] = None,
        crag: Optional[CRAGOrchestrator] = None,
        reranker: Optional[CrossEncoderReranker] = None,
        compressor: Optional[ContextCompressor] = None,
        expander: Optional[ChunkExpander] = None,
        knowledge_graph: Optional[LegalKnowledgeGraph] = None,
    ):
        """
        Initialize the RAG pipeline.

        Args:
            config: Pipeline configuration (loads from env if not provided)
            query_expansion: Query expansion service
            crag: CRAG orchestrator
            reranker: Cross-encoder reranker
            compressor: Context compressor
            expander: Chunk expander
            knowledge_graph: Knowledge graph for enrichment
        """
        self.config = config or get_pipeline_config()
        self._query_expansion = query_expansion
        self._crag = crag
        self._reranker = reranker
        self._compressor = compressor
        self._expander = expander
        self._knowledge_graph = knowledge_graph

    # -------------------------------------------------------------------------
    # Lazy Component Initialization
    # -------------------------------------------------------------------------

    @property
    def query_expansion(self) -> QueryExpansionService:
        """Lazy-initialize query expansion service."""
        if self._query_expansion is None:
            self._query_expansion = get_query_expansion_service()
        return self._query_expansion

    @property
    def crag(self) -> CRAGOrchestrator:
        """Lazy-initialize CRAG orchestrator."""
        if self._crag is None:
            crag_config = CRAGConfig(
                min_best_score=self.config.crag_min_best_score,
                min_avg_score=self.config.crag_min_avg_score,
                max_retry_rounds=self.config.crag_max_retries,
            )
            self._crag = CRAGOrchestrator(crag_config)
        return self._crag

    @property
    def reranker(self) -> CrossEncoderReranker:
        """Lazy-initialize reranker."""
        if self._reranker is None:
            rerank_config = RerankerConfig(
                model_name=self.config.rerank_model,
                top_k=self.config.rerank_top_k,
                max_chars=self.config.rerank_max_chars,
            )
            self._reranker = CrossEncoderReranker(rerank_config)
        return self._reranker

    @property
    def compressor(self) -> ContextCompressor:
        """Lazy-initialize compressor."""
        if self._compressor is None:
            compress_config = CompressionConfig(
                max_chars_per_chunk=self.config.compression_max_chars,
                min_chars=self.config.compression_min_chars,
            )
            self._compressor = ContextCompressor(compress_config)
        return self._compressor

    @property
    def expander(self) -> ChunkExpander:
        """Lazy-initialize chunk expander."""
        if self._expander is None:
            expand_config = ExpansionConfig(
                window=self.config.chunk_expansion_window,
                max_extra_total=self.config.chunk_expansion_max_extra,
            )
            self._expander = ChunkExpander(expand_config)
        return self._expander

    # -------------------------------------------------------------------------
    # Tracing
    # -------------------------------------------------------------------------

    def _create_trace(self, request_id: Optional[str] = None) -> PipelineTrace:
        """Create a new pipeline trace."""
        if not request_id:
            request_id = hashlib.md5(f"{time.time()}".encode()).hexdigest()[:12]
        return PipelineTrace(request_id=request_id)

    def _emit_trace(
        self,
        trace: PipelineTrace,
        event: str,
        data: Dict[str, Any],
        request_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> None:
        """Emit a trace event if tracing is enabled."""
        if not self.config.enable_tracing:
            return

        trace.add_event(event, data)

        # Also emit to external tracers
        trace_event(
            event,
            data,
            request_id=request_id or trace.request_id,
            tenant_id=tenant_id,
            user_id=user_id,
        )

    # -------------------------------------------------------------------------
    # Pipeline Stages
    # -------------------------------------------------------------------------

    async def _stage_query_expansion(
        self,
        query: str,
        trace: PipelineTrace,
        use_hyde: bool,
        use_multiquery: bool,
    ) -> Tuple[str, List[str]]:
        """
        Stage 1: Query Enhancement

        Returns:
            Tuple of (search_query, query_variants)
        """
        search_query = query
        query_variants = [query]

        if use_hyde:
            try:
                hyde_doc = await self.query_expansion.generate_hypothetical_document(query)
                if hyde_doc and hyde_doc != query:
                    search_query = f"{query}\n\n{hyde_doc}"
                    self._emit_trace(trace, "hyde_generate", {
                        "original_length": len(query),
                        "hyde_length": len(hyde_doc),
                    })
            except Exception as e:
                logger.warning(f"HyDE generation failed: {e}")

        if use_multiquery:
            try:
                query_variants = await self.query_expansion.generate_query_variants(
                    query,
                    count=self.config.multiquery_max,
                )
                self._emit_trace(trace, "multiquery_generate", {
                    "variant_count": len(query_variants),
                })
            except Exception as e:
                logger.warning(f"Multi-query generation failed: {e}")

        return search_query, query_variants

    async def _stage_search(
        self,
        search_query: str,
        query_variants: List[str],
        lexical_fn: Callable[[str, int], List[Dict[str, Any]]],
        vector_fn: Callable[[str, int], List[Dict[str, Any]]],
        fetch_k: int,
        trace: PipelineTrace,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Stage 2 & 3: Lexical and Vector Search

        Returns:
            Tuple of (lexical_results, vector_results)
        """
        all_lexical: List[Dict[str, Any]] = []
        all_vector: List[Dict[str, Any]] = []

        # Search with all query variants
        for variant in query_variants:
            try:
                lex_results = await asyncio.to_thread(lexical_fn, variant, fetch_k)
                all_lexical.extend(lex_results)
            except Exception as e:
                logger.warning(f"Lexical search failed for variant: {e}")

            try:
                vec_results = await asyncio.to_thread(vector_fn, search_query, fetch_k)
                all_vector.extend(vec_results)
            except Exception as e:
                logger.warning(f"Vector search failed for variant: {e}")

        self._emit_trace(trace, "search_complete", {
            "lexical_count": len(all_lexical),
            "vector_count": len(all_vector),
            "variants_used": len(query_variants),
        })

        return all_lexical, all_vector

    def _stage_merge(
        self,
        lexical: List[Dict[str, Any]],
        vector: List[Dict[str, Any]],
        top_k: int,
        trace: PipelineTrace,
    ) -> List[Dict[str, Any]]:
        """
        Stage 4: Merge with RRF

        Returns:
            Merged and deduplicated results
        """
        # Deduplicate by chunk_uid
        seen_lex = set()
        dedup_lex = []
        for r in lexical:
            uid = r.get("chunk_uid")
            if uid and uid not in seen_lex:
                seen_lex.add(uid)
                dedup_lex.append(r)

        seen_vec = set()
        dedup_vec = []
        for r in vector:
            uid = r.get("chunk_uid")
            if uid and uid not in seen_vec:
                seen_vec.add(uid)
                dedup_vec.append(r)

        merged = merge_lexical_vector_rrf(
            dedup_lex, dedup_vec,
            top_k=top_k * 2,  # Get extra for filtering
            k_rrf=self.config.rrf_k,
            w_lex=self.config.lexical_weight,
            w_vec=self.config.vector_weight,
        )

        self._emit_trace(trace, "merge_rrf", {
            "lexical_dedup": len(dedup_lex),
            "vector_dedup": len(dedup_vec),
            "merged_count": len(merged),
        })

        return merged

    async def _stage_crag_gate(
        self,
        results: List[Dict[str, Any]],
        query: str,
        lexical_fn: Callable[[str, int], List[Dict[str, Any]]],
        vector_fn: Callable[[str, int], List[Dict[str, Any]]],
        fetch_k: int,
        trace: PipelineTrace,
    ) -> Tuple[List[Dict[str, Any]], CRAGEvaluation, int]:
        """
        Stage 5: CRAG Gate with Retry

        Returns:
            Tuple of (results, evaluation, retry_count)
        """
        evaluation = self.crag.evaluate_results(results)
        retries = 0

        self._emit_trace(trace, "crag_gate_initial", {
            "passed": evaluation.gate_passed,
            "evidence_level": evaluation.evidence_level.value,
            "best_score": evaluation.best_score,
            "avg_top3": evaluation.avg_top3,
        })

        # Retry loop if gate failed
        while not evaluation.gate_passed and retries < self.config.crag_max_retries:
            retries += 1

            retry_params = self.crag.get_retry_parameters(
                evaluation,
                fetch_k,
                already_used_multi_query=retries > 0,
                already_used_hyde=False,
                current_round=retries - 1,
            )

            if not retry_params:
                break

            try:
                # Execute retry search
                if retry_params.use_hyde:
                    hyde_doc = await self.query_expansion.generate_hypothetical_document(query)
                    search_query = f"{query}\n\n{hyde_doc}" if hyde_doc else query
                else:
                    search_query = query

                lex_results = await asyncio.to_thread(
                    lexical_fn, search_query, retry_params.top_k
                )
                vec_results = await asyncio.to_thread(
                    vector_fn, search_query, retry_params.top_k
                )

                retry_results = merge_lexical_vector_rrf(
                    lex_results, vec_results,
                    top_k=retry_params.top_k,
                    k_rrf=self.config.rrf_k,
                    w_lex=retry_params.bm25_weight,
                    w_vec=retry_params.semantic_weight,
                )

                retry_eval = self.crag.evaluate_results(retry_results)

                self._emit_trace(trace, f"crag_retry_{retries}", {
                    "strategy": retry_params.strategy_name,
                    "passed": retry_eval.gate_passed,
                    "best_score": retry_eval.best_score,
                })

                if retry_eval.best_score > evaluation.best_score:
                    results = retry_results
                    evaluation = retry_eval

            except Exception as e:
                logger.warning(f"CRAG retry {retries} failed: {e}")

        return results, evaluation, retries

    def _stage_rerank(
        self,
        query: str,
        results: List[Dict[str, Any]],
        top_k: int,
        trace: PipelineTrace,
    ) -> List[Dict[str, Any]]:
        """
        Stage 6: Cross-encoder Reranking

        Returns:
            Reranked results
        """
        try:
            rerank_result = self.reranker.rerank(
                query=query,
                results=results,
                top_k=top_k,
            )

            self._emit_trace(trace, "rerank", {
                "input_count": rerank_result.original_count,
                "output_count": rerank_result.reranked_count,
                "model": rerank_result.model_used,
                "duration_ms": rerank_result.duration_ms,
            })

            return rerank_result.results
        except Exception as e:
            logger.warning(f"Reranking failed: {e}")
            return results

    def _stage_expand(
        self,
        results: List[Dict[str, Any]],
        fetch_siblings_fn: Optional[Callable[[str, int], List[Dict[str, Any]]]],
        trace: PipelineTrace,
    ) -> List[Dict[str, Any]]:
        """
        Stage 7: Chunk Expansion

        Returns:
            Expanded results with sibling chunks
        """
        if not fetch_siblings_fn:
            return results

        try:
            before_count = len(results)
            expansion_result = self.expander.expand_results(
                results=results,
                fetch_fn=fetch_siblings_fn,
            )

            self._emit_trace(trace, "expand", {
                "before": before_count,
                "after": expansion_result.expanded_count,
                "extra_added": expansion_result.extra_chunks_added,
            })

            return expansion_result.results
        except Exception as e:
            logger.warning(f"Chunk expansion failed: {e}")
            return results

    def _stage_compress(
        self,
        query: str,
        results: List[Dict[str, Any]],
        trace: PipelineTrace,
    ) -> List[Dict[str, Any]]:
        """
        Stage 8: Context Compression

        Returns:
            Compressed results
        """
        try:
            compression_result = self.compressor.compress_results(
                query=query,
                results=results,
            )

            self._emit_trace(trace, "compress", {
                "original_chars": compression_result.original_chars,
                "compressed_chars": compression_result.compressed_chars,
                "compression_ratio": compression_result.compression_ratio,
                "chunks_compressed": compression_result.chunks_compressed,
            })

            return compression_result.results
        except Exception as e:
            logger.warning(f"Context compression failed: {e}")
            return results

    def _stage_graph_enrich(
        self,
        query: str,
        results: List[Dict[str, Any]],
        tenant_id: Optional[str],
        group_ids: Optional[List[str]],
        case_id: Optional[str],
        trace: PipelineTrace,
    ) -> str:
        """
        Stage 9: GraphRAG Enrichment

        Returns:
            Graph context string
        """
        try:
            # Combine all chunk texts for context extraction
            combined_text = query + "\n\n" + "\n".join(
                r.get("text", "")[:500] for r in results[:5]
            )

            graph_context = enrich_chunk_with_graph(
                chunk_text=combined_text,
                chunk_metadata={},
                tenant_id=tenant_id,
                group_ids=group_ids,
                case_id=case_id,
                include_global=True,
                token_budget=self.config.graph_max_nodes * 50,  # Rough estimate
            )

            self._emit_trace(trace, "graph_enrich", {
                "context_length": len(graph_context),
                "has_context": bool(graph_context),
            })

            return graph_context
        except Exception as e:
            logger.warning(f"Graph enrichment failed: {e}")
            return ""

    # -------------------------------------------------------------------------
    # Main Pipeline Entry Points
    # -------------------------------------------------------------------------

    async def search(
        self,
        query: str,
        lexical_fn: Callable[[str, int], List[Dict[str, Any]]],
        vector_fn: Callable[[str, int], List[Dict[str, Any]]],
        top_k: int = 10,
        fetch_k: int = 30,
        request_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        user_id: Optional[str] = None,
        group_ids: Optional[List[str]] = None,
        case_id: Optional[str] = None,
        fetch_siblings_fn: Optional[Callable[[str, int], List[Dict[str, Any]]]] = None,
        # Feature flags (None = use config default)
        use_hyde: Optional[bool] = None,
        use_multiquery: Optional[bool] = None,
        use_crag: Optional[bool] = None,
        use_rerank: Optional[bool] = None,
        use_compression: Optional[bool] = None,
        use_expansion: Optional[bool] = None,
        use_graph_enrich: Optional[bool] = None,
    ) -> PipelineResult:
        """
        Execute the full RAG pipeline.

        Args:
            query: Search query
            lexical_fn: Function(query, k) -> lexical results
            vector_fn: Function(query, k) -> vector results
            top_k: Number of final results
            fetch_k: Number of candidates to fetch per source
            request_id: Request ID for tracing
            tenant_id: Tenant ID for scoping
            user_id: User ID for tracing
            group_ids: Group IDs for graph scope
            case_id: Case ID for local graph
            fetch_siblings_fn: Function(doc_hash, chunk_idx) -> sibling chunks

        Returns:
            PipelineResult with results and metadata
        """
        # Initialize trace
        trace = self._create_trace(request_id)
        self._emit_trace(trace, "pipeline_start", {
            "query_length": len(query),
            "top_k": top_k,
            "fetch_k": fetch_k,
        }, tenant_id=tenant_id, user_id=user_id)

        # Resolve feature flags
        use_hyde = use_hyde if use_hyde is not None else self.config.enable_hyde
        use_multiquery = use_multiquery if use_multiquery is not None else self.config.enable_multiquery
        use_crag = use_crag if use_crag is not None else self.config.enable_crag
        use_rerank = use_rerank if use_rerank is not None else self.config.enable_rerank
        use_compression = use_compression if use_compression is not None else self.config.enable_compression
        use_expansion = use_expansion if use_expansion is not None else self.config.enable_chunk_expansion
        use_graph_enrich = use_graph_enrich if use_graph_enrich is not None else self.config.enable_graph_enrich

        # Stage 1: Query Enhancement
        search_query, query_variants = await self._stage_query_expansion(
            query, trace, use_hyde, use_multiquery
        )

        # Stage 2 & 3: Search
        lexical, vector = await self._stage_search(
            search_query, query_variants, lexical_fn, vector_fn, fetch_k, trace
        )

        # Stage 4: Merge
        results = self._stage_merge(lexical, vector, top_k, trace)

        # Stage 5: CRAG Gate
        crag_evaluation = None
        crag_retries = 0
        if use_crag:
            results, evaluation, crag_retries = await self._stage_crag_gate(
                results, query, lexical_fn, vector_fn, fetch_k, trace
            )
            crag_evaluation = evaluation.to_dict() if hasattr(evaluation, 'to_dict') else {
                "gate_passed": evaluation.gate_passed,
                "evidence_level": evaluation.evidence_level.value,
                "best_score": evaluation.best_score,
                "avg_top3": evaluation.avg_top3,
            }

        # Trim to final top_k
        results = results[:top_k]

        # Stage 6: Rerank
        if use_rerank and results:
            results = self._stage_rerank(query, results, top_k, trace)

        # Stage 7: Expand
        if use_expansion and results and fetch_siblings_fn:
            results = self._stage_expand(results, fetch_siblings_fn, trace)

        # Stage 8: Compress
        if use_compression and results:
            results = self._stage_compress(query, results, trace)

        # Stage 9: Graph Enrich
        graph_context = ""
        if use_graph_enrich:
            graph_context = self._stage_graph_enrich(
                query, results, tenant_id, group_ids, case_id, trace
            )

        # Stage 10: Final Trace
        total_duration_ms = int((time.perf_counter() - trace.started_at) * 1000)
        self._emit_trace(trace, "pipeline_complete", {
            "final_count": len(results),
            "total_duration_ms": total_duration_ms,
            "crag_retries": crag_retries,
            "has_graph_context": bool(graph_context),
        }, tenant_id=tenant_id, user_id=user_id)

        return PipelineResult(
            results=results,
            trace=trace if self.config.enable_tracing else None,
            graph_context=graph_context,
            crag_evaluation=crag_evaluation,
            metadata={
                "query": query,
                "top_k": top_k,
                "features_used": {
                    "hyde": use_hyde,
                    "multiquery": use_multiquery,
                    "crag": use_crag,
                    "rerank": use_rerank,
                    "compression": use_compression,
                    "expansion": use_expansion,
                    "graph_enrich": use_graph_enrich,
                },
                "crag_retries": crag_retries,
                "total_duration_ms": total_duration_ms,
            },
        )

    def search_sync(
        self,
        query: str,
        lexical_fn: Callable[[str, int], List[Dict[str, Any]]],
        vector_fn: Callable[[str, int], List[Dict[str, Any]]],
        **kwargs,
    ) -> PipelineResult:
        """Synchronous wrapper for search."""
        return asyncio.run(self.search(query, lexical_fn, vector_fn, **kwargs))


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================


_pipeline_instance: Optional[RAGPipeline] = None


def get_rag_pipeline(config: Optional[RAGPipelineConfig] = None) -> RAGPipeline:
    """Get or create the singleton RAG pipeline instance."""
    global _pipeline_instance
    if _pipeline_instance is None:
        _pipeline_instance = RAGPipeline(config)
    return _pipeline_instance


def reset_rag_pipeline() -> None:
    """Reset the singleton pipeline instance."""
    global _pipeline_instance
    _pipeline_instance = None


async def rag_search(
    query: str,
    lexical_fn: Callable[[str, int], List[Dict[str, Any]]],
    vector_fn: Callable[[str, int], List[Dict[str, Any]]],
    **kwargs,
) -> PipelineResult:
    """
    Convenience function to perform RAG search with the default pipeline.

    Args:
        query: Search query
        lexical_fn: Function(query, k) -> lexical results
        vector_fn: Function(query, k) -> vector results
        **kwargs: Additional arguments passed to RAGPipeline.search()

    Returns:
        PipelineResult
    """
    pipeline = get_rag_pipeline()
    return await pipeline.search(query, lexical_fn, vector_fn, **kwargs)


# =============================================================================
# MODULE EXPORTS
# =============================================================================

__all__ = [
    "RAGPipeline",
    "PipelineResult",
    "PipelineTrace",
    "get_rag_pipeline",
    "reset_rag_pipeline",
    "rag_search",
]
