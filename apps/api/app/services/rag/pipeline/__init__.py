"""
RAG Pipeline

Main orchestration layer that combines all RAG components:
- Hybrid search (lexical + vector)
- CRAG gating with retry logic
- Query expansion (HyDE / multi-query)
- Reranking with cross-encoders
- Context compression
- Chunk expansion (parent-child retrieval)
- Knowledge graph enrichment
- Full tracing for observability

Pipeline Architecture:
    Query -> Lexical Search -> Vector Search (conditional) -> Merge (RRF)
    -> CRAG Gate -> [Retry if needed] -> Rerank -> Expand
    -> Compress -> Graph Enrich -> Trace -> Response
"""

from __future__ import annotations

from .rag_pipeline import (
    # Enums
    SearchMode,
    PipelineStage,
    CRAGDecision,
    # Config
    RAGPipelineConfig,
    # Data classes
    StageTrace,
    CRAGEvaluation,
    PipelineTrace,
    GraphContext,
    PipelineResult,
    # Main class
    RAGPipeline,
    # Module functions
    get_rag_pipeline,
    reset_rag_pipeline,
    search,
    search_sync,
)

from .orchestrator import (
    RetrievalOrchestrator,
    EnhancedRetrievalPipeline,
    create_orchestrator,
    create_enhanced_pipeline,
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
    # Orchestrator
    "RetrievalOrchestrator",
    "EnhancedRetrievalPipeline",
    "create_orchestrator",
    "create_enhanced_pipeline",
]
