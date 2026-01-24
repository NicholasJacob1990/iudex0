"""
RAG Core Components

Contains the core processing components for the RAG pipeline:
- CRAG gate for relevance validation
- Query expansion services (HyDE, multi-query)
- Reranking with cross-encoders
- Context compression
- Chunk expansion (parent-child retrieval)
- Legal knowledge graph (NetworkX + Neo4j MVP)
- Embedding service
- Knowledge graph embedding training
- Hybrid router (rules + optional LLM fallback)
- Agentic orchestrator (deep research, comparison, open-ended)
- Resilience patterns (circuit breaker, retry with backoff)
"""

# Import from existing modules
from .reranker import CrossEncoderReranker, RerankerConfig, RerankerResult

# Budget tracker imports
from .budget_tracker import (
    BudgetTracker,
    BudgetExceededError,
    LLMCallRecord,
    EmbeddingRecord,
    estimate_tokens,
    TOKEN_ESTIMATES,
)

from .context_compressor import (
    ContextCompressor,
    CompressionConfig,
    CompressionResult,
    TokenBudgetManager,
    compress_context,
)
from .embeddings import EmbeddingsService, get_embeddings_service

# CRAG Gate imports
from .crag_gate import (
    CRAGConfig,
    CRAGGate,
    CRAGOrchestrator,
    CRAGIntegration,
    CRAGEvaluation,
    CRAGAuditTrail,
    EvidenceLevel,
    RetryParameters,
    RetryStrategyBuilder,
    CorrectiveAction,
    evaluate_crag_gate,
    get_retry_strategy,
    create_crag_orchestrator,
)

# Chunk expander imports
from .chunk_expander import (
    ChunkExpander,
    ParentChunkExpander,
    ExpansionConfig,
    ExpansionResult,
    ChunkLocation,
    expand_chunks,
    create_expander_with_qdrant,
    create_expander_with_opensearch,
    create_expander_from_rag_config,
)

# Query expansion imports
from .query_expansion import (
    QueryExpansionConfig,
    TTLCache,
    rrf_score,
    merge_results_rrf,
    merge_lexical_vector_rrf,
    expand_legal_abbreviations,
    LEGAL_ABBREVIATIONS,
    QueryExpansionService,
    get_query_expansion_service,
    reset_query_expansion_service,
)

# GraphRAG imports
from .graph_rag import (
    # Enums
    EntityType,
    RelationType,
    ArgumentType,
    Scope,
    # Data classes
    Entity,
    Relation,
    ArgumentNode,
    ScopedGraphRef,
    GraphSchema,
    # Main classes
    LegalKnowledgeGraph,
    ArgumentGraph,
    LegalEntityExtractor,
    ArgumentExtractor,
    LegalPack,
    ScopedGraphManager,
    # Helper functions
    get_scoped_knowledge_graph,
    get_global_knowledge_graph,
    get_tenant_knowledge_graph,
    get_group_knowledge_graph,
    get_case_knowledge_graph,
    get_case_argument_graph,
    # Integration functions
    enrich_chunk_with_graph,
    ingest_to_graph,
)


# Neo4j MVP imports (optional - requires neo4j driver)
try:
    from .neo4j_mvp import (
        Neo4jMVPConfig,
        Neo4jMVPService,
        LegalEntityExtractor as Neo4jLegalEntityExtractor,
        EntityType as Neo4jEntityType,
        Scope as Neo4jScope,
        get_neo4j_mvp,
        close_neo4j_mvp,
        enrich_rag_with_graph,
        build_graph_context,
    )
    _neo4j_available = True
except ImportError:
    _neo4j_available = False

# Embedding trainer imports (for knowledge graph embeddings)
try:
    from .embedding_trainer import (
        EmbeddingMethod,
        NegativeSamplingStrategy,
        TrainingConfig,
        TrainingMetrics,
        Checkpoint,
        TripleDataset,
        EmbeddingTrainer,
        Neo4jEmbeddingPipeline,
        EmbeddingScheduler,
    )
    _embedding_trainer_available = True
except ImportError:
    _embedding_trainer_available = False

# Alias for backward compatibility
EmbeddingService = EmbeddingsService

# Hybrid Router imports
from .hybrid_router import (
    QueryIntent,
    RetrievalStrategy,
    RoutingDecision,
    HybridRouter,
    get_hybrid_router,
    reset_hybrid_router,
)

# Agentic Orchestrator imports
from .agentic_orchestrator import (
    OrchestrationMode,
    ResearchPhase,
    ResearchStep,
    OrchestrationResult,
    AgenticOrchestrator,
)

# Resilience imports
from .resilience import (
    CircuitState,
    CircuitBreakerConfig,
    CircuitBreakerStats,
    CircuitBreaker,
    CircuitBreakerOpenError,
    RetryConfig,
    calculate_backoff_delay,
    retry_with_backoff,
    retry_with_backoff_async,
    ResilientService,
    get_circuit_breaker,
    get_all_circuit_breakers,
    get_circuit_breaker_status,
    reset_all_circuit_breakers,
    with_circuit_breaker,
    with_retry,
    with_resilience,
)


__all__ = [
    # Budget Tracker
    "BudgetTracker",
    "BudgetExceededError",
    "LLMCallRecord",
    "EmbeddingRecord",
    "estimate_tokens",
    "TOKEN_ESTIMATES",
    # CRAG Gate
    "CRAGConfig",
    "CRAGGate",
    "CRAGOrchestrator",
    "CRAGIntegration",
    "CRAGEvaluation",
    "CRAGAuditTrail",
    "EvidenceLevel",
    "RetryParameters",
    "RetryStrategyBuilder",
    "CorrectiveAction",
    "evaluate_crag_gate",
    "get_retry_strategy",
    "create_crag_orchestrator",
    # Query expansion
    "QueryExpansionConfig",
    "TTLCache",
    "rrf_score",
    "merge_results_rrf",
    "merge_lexical_vector_rrf",
    "expand_legal_abbreviations",
    "LEGAL_ABBREVIATIONS",
    "QueryExpansionService",
    "get_query_expansion_service",
    "reset_query_expansion_service",
    # Reranking
    "CrossEncoderReranker",
    "RerankerConfig",
    "RerankerResult",
    # Compression
    "ContextCompressor",
    "CompressionConfig",
    "CompressionResult",
    "TokenBudgetManager",
    "compress_context",
    # Chunk expansion
    "ChunkExpander",
    "ParentChunkExpander",
    "ExpansionConfig",
    "ExpansionResult",
    "ChunkLocation",
    "expand_chunks",
    "create_expander_with_qdrant",
    "create_expander_with_opensearch",
    "create_expander_from_rag_config",
    # GraphRAG - Enums
    "EntityType",
    "RelationType",
    "ArgumentType",
    "Scope",
    # GraphRAG - Data classes
    "Entity",
    "Relation",
    "ArgumentNode",
    "ScopedGraphRef",
    "GraphSchema",
    # GraphRAG - Main classes
    "LegalKnowledgeGraph",
    "ArgumentGraph",
    "LegalEntityExtractor",
    "ArgumentExtractor",
    "LegalPack",
    "ScopedGraphManager",
    # GraphRAG - Helper functions
    "get_scoped_knowledge_graph",
    "get_global_knowledge_graph",
    "get_tenant_knowledge_graph",
    "get_group_knowledge_graph",
    "get_case_knowledge_graph",
    "get_case_argument_graph",
    # GraphRAG - Integration functions
    "enrich_chunk_with_graph",
    "ingest_to_graph",
    # Embeddings
    "EmbeddingsService",
    "EmbeddingService",  # Alias
    "get_embeddings_service",
    # Hybrid Router
    "QueryIntent",
    "RetrievalStrategy",
    "RoutingDecision",
    "HybridRouter",
    "get_hybrid_router",
    "reset_hybrid_router",
    # Agentic Orchestrator
    "OrchestrationMode",
    "ResearchPhase",
    "ResearchStep",
    "OrchestrationResult",
    "AgenticOrchestrator",
    # Resilience
    "CircuitState",
    "CircuitBreakerConfig",
    "CircuitBreakerStats",
    "CircuitBreaker",
    "CircuitBreakerOpenError",
    "RetryConfig",
    "calculate_backoff_delay",
    "retry_with_backoff",
    "retry_with_backoff_async",
    "ResilientService",
    "get_circuit_breaker",
    "get_all_circuit_breakers",
    "get_circuit_breaker_status",
    "reset_all_circuit_breakers",
    "with_circuit_breaker",
    "with_retry",
    "with_resilience",
]

# Conditionally add Neo4j MVP exports
if _neo4j_available:
    __all__.extend([
        # Neo4j MVP - Config
        "Neo4jMVPConfig",
        # Neo4j MVP - Service
        "Neo4jMVPService",
        # Neo4j MVP - Entity extraction
        "Neo4jLegalEntityExtractor",
        "Neo4jEntityType",
        "Neo4jScope",
        # Neo4j MVP - Helpers
        "get_neo4j_mvp",
        "close_neo4j_mvp",
        "enrich_rag_with_graph",
        "build_graph_context",
    ])

# Conditionally add Embedding Trainer exports
if _embedding_trainer_available:
    __all__.extend([
        # Embedding Trainer - Config
        "EmbeddingMethod",
        "NegativeSamplingStrategy",
        "TrainingConfig",
        "TrainingMetrics",
        "Checkpoint",
        # Embedding Trainer - Dataset
        "TripleDataset",
        # Embedding Trainer - Main
        "EmbeddingTrainer",
        "Neo4jEmbeddingPipeline",
        "EmbeddingScheduler",
    ])
