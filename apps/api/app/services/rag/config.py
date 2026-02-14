"""
RAG Pipeline Configuration

All settings configurable via environment variables with sensible defaults.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


def _env_bool(name: str, default: bool = False) -> bool:
    """Parse boolean environment variable."""
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    """Parse integer environment variable."""
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    """Parse float environment variable."""
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


@dataclass
class RAGConfig:
    """
    Complete RAG pipeline configuration.

    Sections:
    - Feature flags (enable/disable components)
    - CRAG gate settings
    - Query expansion (HyDE, multi-query)
    - Reranking
    - Compression
    - Chunk expansion
    - Graph enrichment
    - Storage (OpenSearch, Qdrant)
    - Tracing
    - RRF fusion
    """

    # ==========================================================================
    # Feature Flags
    # ==========================================================================
    enable_crag: bool = True
    enable_hyde: bool = True
    enable_multiquery: bool = True
    enable_rerank: bool = True
    enable_compression: bool = True
    enable_graph_enrich: bool = True
    enable_tracing: bool = True
    enable_chunk_expansion: bool = True
    enable_lexical_first_gating: bool = True  # MVP: skip vector if lexical strong
    enable_graph_retrieval: bool = True  # Neo4j as 3rd RRF source (conforme rag.md)

    # ==========================================================================
    # CRAG Gate Settings
    # ==========================================================================
    crag_min_best_score: float = 0.5
    crag_min_avg_score: float = 0.35
    crag_max_retries: int = 2

    # ==========================================================================
    # Query Expansion (HyDE + Multi-query)
    # ==========================================================================
    hyde_model: str = "gemini-2.0-flash"
    hyde_max_tokens: int = 300
    multiquery_max: int = 3
    multiquery_model: str = "gemini-2.0-flash"
    query_enhancement_preflight: bool = True  # Preflight lexical before HyDE/MultiQuery
    query_enhancement_preflight_top_k: int = 6
    multiquery_apply_to_lexical: bool = False  # Default: keep multiquery for vector-only

    # ==========================================================================
    # Reranking (Hybrid: Local or Cohere)
    # ==========================================================================
    # Provider: "auto" (dev=local, prod=cohere), "local", "cohere"
    rerank_provider: str = "auto"

    # Local cross-encoder settings
    # Keep defaults to public, stable model ids (avoid runtime 404s on HF).
    rerank_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    rerank_model_fallback: str = "cross-encoder/ms-marco-TinyBERT-L-2-v2"
    rerank_batch_size: int = 32
    rerank_use_fp16: bool = True
    rerank_cache_model: bool = True
    rerank_top_k: int = 10
    rerank_max_chars: int = 1800

    # Cohere Rerank settings
    cohere_rerank_model: str = "rerank-v4.0-pro"
    cohere_rerank_max_candidates: int = 100
    cohere_fallback_to_local: bool = True

    # Legal domain boost (applied by both providers)
    rerank_legal_boost: float = 0.1

    # ==========================================================================
    # Compression
    # ==========================================================================
    compression_max_chars: int = 900
    compression_min_chars: int = 100
    compression_token_budget: int = 4000
    compression_preserve_full_text: bool = True

    # ==========================================================================
    # Chunk Expansion
    # ==========================================================================
    chunk_expansion_window: int = 1
    chunk_expansion_max_extra: int = 12
    chunk_expansion_merge_adjacent: bool = True

    # ==========================================================================
    # Graph Enrichment
    # ==========================================================================
    graph_hops: int = 2
    graph_max_nodes: int = 50

    # ==========================================================================
    # Graph Backend (NetworkX or Neo4j)
    # ==========================================================================
    graph_backend: str = "neo4j"  # "neo4j" (default conforme rag.md) or "networkx"
    neo4j_only: bool = True  # Enforce Neo4j-only (no NetworkX/file fallback)
    # Local dev default: Iudex Docker maps Bolt to 8687 to avoid conflicting with Neo4j Desktop (7687).
    neo4j_uri: str = "bolt://localhost:8687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "password"
    neo4j_database: str = "iudex"
    neo4j_max_connection_pool_size: int = 50
    neo4j_connection_timeout: int = 30
    graph_hybrid_mode: bool = False
    graph_hybrid_auto_schema: bool = True
    graph_hybrid_migrate_on_startup: bool = False

    # ==========================================================================
    # Storage - OpenSearch
    # ==========================================================================
    opensearch_url: str = "https://localhost:9200"
    opensearch_user: str = "admin"
    opensearch_password: str = "admin"
    opensearch_verify_certs: bool = False

    # OpenSearch indices
    opensearch_index_lei: str = "rag-lei"
    opensearch_index_juris: str = "rag-juris"
    opensearch_index_pecas: str = "rag-pecas_modelo"
    opensearch_index_doutrina: str = "rag-doutrina"
    opensearch_index_sei: str = "rag-sei"
    opensearch_index_local: str = "rag-local"

    # ==========================================================================
    # Storage - Qdrant
    # ==========================================================================
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""
    vector_query_max_concurrency: int = 4  # Max concurrent vector queries (per request)

    # Qdrant collections
    qdrant_collection_lei: str = "lei"
    qdrant_collection_juris: str = "juris"
    qdrant_collection_pecas: str = "pecas_modelo"
    qdrant_collection_doutrina: str = "doutrina"
    qdrant_collection_sei: str = "sei"
    qdrant_collection_local: str = "local_chunks"

    # Qdrant Hybrid Sparse (SPLADE)
    # When enabled, Qdrant collections should be created with `sparse_vectors_config`
    # and points upserted with both dense + sparse vectors.
    qdrant_sparse_enabled: bool = False
    qdrant_dense_vector_name: str = "dense"
    qdrant_sparse_vector_name: str = "sparse"
    qdrant_hybrid_fusion: str = "rrf"  # "rrf" | "dbsf"
    qdrant_hybrid_prefetch_limit: int = 40

    # Hybrid query classifier (dynamic sparse/dense weights)
    hybrid_default_sparse_weight: float = 0.50
    hybrid_default_dense_weight: float = 0.50
    hybrid_query_classifier_llm: bool = True
    hybrid_query_classifier_model: str = "gemini-2.0-flash"

    # ==========================================================================
    # Embeddings — Provider primário (OpenAI) usado pelas collections legadas
    # Dimensão 3072 corresponde ao modelo text-embedding-3-large.
    # IMPORTANTE: Dimensões por provider são hardcodadas nos respectivos módulos:
    #   - Voyage V4 large: 1024d (voyage_embeddings.py MODEL_DIMENSIONS)
    #   - JurisBERT: 768d (jurisbert_embeddings.py)
    #   - Kanon 2: 1024d (kanon_embeddings.py)
    #   - OpenAI fallback: 3072d (hardcoded nos fallback paths)
    # Para o provider local SentenceTransformers (768d), ver:
    #   app/core/config.py → Settings.EMBEDDING_DIMENSION
    # ==========================================================================
    embedding_model: str = "text-embedding-3-large"
    embedding_dimensions: int = 3072
    embedding_cache_ttl_seconds: int = 3600  # 1 hour
    embedding_batch_size: int = 100

    # ==========================================================================
    # Contextual Retrieval (Contextual Embeddings)
    # ==========================================================================
    # When enabled for ingestion/migration, chunks are embedded with a short
    # metadata-derived context prefix prepended to the chunk text. This improves
    # retrieval for ambiguous chunks, but requires re-embedding existing corpora
    # to be fully consistent.
    enable_contextual_embeddings: bool = False
    contextual_embeddings_max_prefix_chars: int = 240

    # ==========================================================================
    # TTL Settings
    # ==========================================================================
    local_ttl_days: int = 7
    ttl_cleanup_interval_hours: int = 6

    # ==========================================================================
    # Tracing
    # ==========================================================================
    trace_log_path: str = "logs/rag_trace.jsonl"
    trace_persist_db: bool = False
    trace_export_otel: bool = False
    trace_export_langsmith: bool = False

    # ==========================================================================
    # RRF Fusion
    # ==========================================================================
    rrf_k: int = 60
    lexical_weight: float = 0.5
    vector_weight: float = 0.5
    graph_weight: float = 0.3  # Neo4j graph retrieval weight in RRF
    graph_retrieval_limit: int = 20  # Max chunks from Neo4j graph search

    # ==========================================================================
    # Citation Grounding (post-generation verification)
    # ==========================================================================
    enable_citation_grounding: bool = True      # Verify legal citations in LLM output
    citation_grounding_threshold: float = 0.85  # Min fidelity index before warning
    citation_grounding_neo4j: bool = True       # Also check Neo4j entity store
    citation_grounding_annotate: bool = True    # Annotate text with [NÃO VERIFICADO]

    # ==========================================================================
    # Budget Caps (Cost Control)
    # ==========================================================================
    max_tokens_per_request: int = 50000  # Total token budget per RAG request
    max_llm_calls_per_request: int = 5   # Limit HyDE + multi-query calls
    warn_at_budget_percent: float = 0.8  # Warn when 80% of budget used

    # ==========================================================================
    # Search Defaults
    # ==========================================================================
    default_fetch_k: int = 50
    default_top_k: int = 10

    # ==========================================================================
    # Graph Embedding Training
    # ==========================================================================
    graph_embedding_method: str = "rotate"  # transe, rotate, complex, distmult
    graph_embedding_dim: int = 128
    graph_embedding_epochs: int = 200
    graph_embedding_batch_size: int = 512
    graph_embedding_lr: float = 0.001
    graph_embedding_negative_samples: int = 10
    graph_embedding_negative_strategy: str = "self_adv"  # uniform, self_adv, bernoulli
    graph_embedding_patience: int = 20
    graph_embedding_checkpoint_dir: str = "data/embeddings/checkpoints"
    graph_embedding_retrain_hours: int = 24
    graph_embedding_min_new_triples: int = 100

    # ==========================================================================
    # Result Cache
    # ==========================================================================
    enable_result_cache: bool = True
    result_cache_ttl_seconds: int = 300  # 5 minutes
    result_cache_max_size: int = 5000

    # ==========================================================================
    # Per-Database Timeouts (seconds)
    # ==========================================================================
    lexical_timeout_seconds: float = 0.5
    vector_timeout_seconds: float = 1.0
    graph_search_timeout_seconds: float = 0.5
    min_sources_required: int = 1

    # ==========================================================================
    # Warm-Start
    # ==========================================================================
    warmup_on_startup: bool = True

    # ==========================================================================
    # CogGRAG — Cognitive Graph RAG
    # ==========================================================================
    enable_cograg: bool = False
    cograg_max_depth: int = 3
    cograg_max_children: int = 4
    cograg_decomposer_model: str = "gemini-2.0-flash"
    cograg_similarity_threshold: float = 0.7
    cograg_complexity_threshold: float = 0.5

    # Cognitive RAG Enhancements (Phase 2.5)
    cograg_theme_retrieval_enabled: bool = False
    cograg_evidence_refinement_enabled: bool = False
    cograg_memory_enabled: bool = False
    cograg_memory_backend: str = "auto"  # auto | neo4j | file
    cograg_memory_similarity_threshold: float = 0.85
    cograg_abstain_mode: bool = True
    cograg_abstain_threshold: float = 0.3
    cograg_graph_evidence_enabled: bool = True
    cograg_graph_evidence_max_hops: int = 2
    cograg_graph_evidence_limit: int = 10
    cograg_mindmap_explain_enabled: bool = False
    cograg_mindmap_explain_format: str = "json"  # json | mermaid | both
    cograg_audit_mode: bool = False

    # Verification (Phase 3)
    cograg_verification_enabled: bool = False
    cograg_verification_model: str = "gemini-2.0-flash"
    cograg_max_rethink_attempts: int = 2
    cograg_hallucination_loop: bool = False
    cograg_llm_max_concurrency: int = 6  # cap parallel LLM calls in CogGRAG nodes

    # ==========================================================================
    # Lexical-First Gating (MVP optimization)
    # ==========================================================================
    lexical_strong_threshold: float = 0.7  # If best lexical score > this, skip vector
    lexical_citation_patterns: List[str] = field(default_factory=lambda: [
        r"art\.?\s*\d+",
        r"§\s*\d+",
        r"inciso\s+[IVXLCDM]+",
        r"lei\s+n?\.?\s*\d+",
        r"súmula\s+n?\.?\s*\d+",
        r"stf|stj|tst|trf|tjsp",
        r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}",  # CNJ number
    ])

    @classmethod
    def from_env(cls) -> "RAGConfig":
        """Load configuration from environment variables."""
        return cls(
            # Feature flags
            enable_crag=_env_bool("RAG_ENABLE_CRAG", True),
            enable_hyde=_env_bool("RAG_ENABLE_HYDE", True),
            enable_multiquery=_env_bool("RAG_ENABLE_MULTIQUERY", True),
            enable_rerank=_env_bool("RAG_ENABLE_RERANK", True),
            enable_compression=_env_bool("RAG_ENABLE_COMPRESSION", True),
            enable_graph_enrich=_env_bool("RAG_ENABLE_GRAPH_ENRICH", True),
            enable_tracing=_env_bool("RAG_ENABLE_TRACING", True),
            enable_chunk_expansion=_env_bool("RAG_ENABLE_CHUNK_EXPANSION", True),
            enable_lexical_first_gating=_env_bool("RAG_ENABLE_LEXICAL_FIRST", True),
            enable_graph_retrieval=_env_bool("RAG_ENABLE_GRAPH_RETRIEVAL", True),

            # CRAG
            crag_min_best_score=_env_float("RAG_CRAG_MIN_BEST_SCORE", 0.5),
            crag_min_avg_score=_env_float("RAG_CRAG_MIN_AVG_SCORE", 0.35),
            crag_max_retries=_env_int("RAG_CRAG_MAX_RETRIES", 2),

            # Query expansion
            hyde_model=os.getenv("RAG_HYDE_MODEL", "gemini-2.0-flash"),
            hyde_max_tokens=_env_int("RAG_HYDE_MAX_TOKENS", 300),
            multiquery_max=_env_int("RAG_MULTIQUERY_MAX", 3),
            multiquery_model=os.getenv("RAG_MULTIQUERY_MODEL", "gemini-2.0-flash"),
            query_enhancement_preflight=_env_bool("RAG_QUERY_ENHANCEMENT_PREFLIGHT", True),
            query_enhancement_preflight_top_k=_env_int("RAG_QUERY_ENHANCEMENT_PREFLIGHT_TOP_K", 6),
            multiquery_apply_to_lexical=_env_bool("RAG_MULTIQUERY_APPLY_TO_LEXICAL", False),

            # Reranking (Hybrid)
            rerank_provider=os.getenv("RERANK_PROVIDER", "auto"),
            rerank_model=os.getenv("RAG_RERANK_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2"),
            rerank_model_fallback=os.getenv("RAG_RERANK_MODEL_FALLBACK", "cross-encoder/ms-marco-TinyBERT-L-2-v2"),
            rerank_batch_size=_env_int("RAG_RERANK_BATCH_SIZE", 32),
            rerank_use_fp16=_env_bool("RAG_RERANK_USE_FP16", True),
            rerank_cache_model=_env_bool("RAG_RERANK_CACHE_MODEL", True),
            rerank_top_k=_env_int("RAG_RERANK_TOP_K", 10),
            rerank_max_chars=_env_int("RAG_RERANK_MAX_CHARS", 1800),
            cohere_rerank_model=os.getenv("COHERE_RERANK_MODEL", "rerank-v4.0-pro"),
            cohere_rerank_max_candidates=_env_int("COHERE_RERANK_MAX_CANDIDATES", 100),
            cohere_fallback_to_local=_env_bool("RERANK_FALLBACK_LOCAL", True),
            rerank_legal_boost=_env_float("RERANK_LEGAL_BOOST", 0.1),

            # Compression
            compression_max_chars=_env_int("RAG_COMPRESSION_MAX_CHARS", 900),
            compression_min_chars=_env_int("RAG_COMPRESSION_MIN_CHARS", 100),
            compression_token_budget=_env_int("RAG_COMPRESSION_TOKEN_BUDGET", 4000),
            compression_preserve_full_text=_env_bool("RAG_COMPRESSION_PRESERVE_FULL", True),

            # Chunk expansion
            chunk_expansion_window=_env_int("RAG_CHUNK_EXPANSION_WINDOW", 1),
            chunk_expansion_max_extra=_env_int("RAG_CHUNK_EXPANSION_MAX_EXTRA", 12),
            chunk_expansion_merge_adjacent=_env_bool("RAG_CHUNK_EXPANSION_MERGE", True),

            # Graph
            graph_hops=_env_int("RAG_GRAPH_HOPS", 2),
            graph_max_nodes=_env_int("RAG_GRAPH_MAX_NODES", 50),

            # Graph Backend
            graph_backend=os.getenv("RAG_GRAPH_BACKEND", "neo4j"),
            neo4j_only=_env_bool("RAG_NEO4J_ONLY", True),
            neo4j_uri=os.getenv("NEO4J_URI", "bolt://localhost:8687"),
            # Aura typically provides NEO4J_USERNAME; accept it as an alias.
            neo4j_user=os.getenv("NEO4J_USER", os.getenv("NEO4J_USERNAME", "neo4j")),
            neo4j_password=os.getenv("NEO4J_PASSWORD", "password"),
            neo4j_database=os.getenv("NEO4J_DATABASE", "iudex"),
            neo4j_max_connection_pool_size=_env_int("NEO4J_MAX_POOL_SIZE", 50),
            neo4j_connection_timeout=_env_int("NEO4J_CONNECTION_TIMEOUT", 30),
            graph_hybrid_mode=_env_bool("RAG_GRAPH_HYBRID_MODE", False),
            graph_hybrid_auto_schema=_env_bool("RAG_GRAPH_HYBRID_AUTO_SCHEMA", True),
            graph_hybrid_migrate_on_startup=_env_bool("RAG_GRAPH_HYBRID_MIGRATE_ON_STARTUP", False),

            # OpenSearch
            opensearch_url=os.getenv("OPENSEARCH_URL", "https://localhost:9200"),
            opensearch_user=os.getenv("OPENSEARCH_USER", "admin"),
            opensearch_password=os.getenv("OPENSEARCH_PASS", os.getenv("OPENSEARCH_INITIAL_ADMIN_PASSWORD", "admin")),
            opensearch_verify_certs=_env_bool("OPENSEARCH_VERIFY_CERTS", False),
            opensearch_index_lei=os.getenv("OPENSEARCH_INDEX_LEI", "rag-lei"),
            opensearch_index_juris=os.getenv("OPENSEARCH_INDEX_JURIS", "rag-juris"),
            opensearch_index_pecas=os.getenv("OPENSEARCH_INDEX_PECAS", "rag-pecas_modelo"),
            opensearch_index_doutrina=os.getenv("OPENSEARCH_INDEX_DOUTRINA", "rag-doutrina"),
            opensearch_index_sei=os.getenv("OPENSEARCH_INDEX_SEI", "rag-sei"),
            opensearch_index_local=os.getenv("OPENSEARCH_INDEX_LOCAL", "rag-local"),

            # Qdrant
            qdrant_url=os.getenv("QDRANT_URL", "http://localhost:6333"),
            qdrant_api_key=os.getenv("QDRANT_API_KEY", ""),
            vector_query_max_concurrency=_env_int("RAG_VECTOR_QUERY_MAX_CONCURRENCY", 4),
            qdrant_collection_lei=os.getenv("QDRANT_COLLECTION_LEI", "lei"),
            qdrant_collection_juris=os.getenv("QDRANT_COLLECTION_JURIS", "juris"),
            qdrant_collection_pecas=os.getenv("QDRANT_COLLECTION_PECAS", "pecas_modelo"),
            qdrant_collection_doutrina=os.getenv("QDRANT_COLLECTION_DOUTRINA", "doutrina"),
            qdrant_collection_sei=os.getenv("QDRANT_COLLECTION_SEI", "sei"),
            qdrant_collection_local=os.getenv("QDRANT_COLLECTION_LOCAL", "local_chunks"),
            qdrant_sparse_enabled=_env_bool("RAG_QDRANT_SPARSE_ENABLED", False),
            qdrant_dense_vector_name=os.getenv("RAG_QDRANT_DENSE_VECTOR_NAME", "dense"),
            qdrant_sparse_vector_name=os.getenv("RAG_QDRANT_SPARSE_VECTOR_NAME", "sparse"),
            qdrant_hybrid_fusion=os.getenv("RAG_QDRANT_HYBRID_FUSION", "rrf"),
            qdrant_hybrid_prefetch_limit=_env_int("RAG_QDRANT_HYBRID_PREFETCH_LIMIT", 40),

            # Hybrid query classifier
            hybrid_default_sparse_weight=_env_float("RAG_HYBRID_SPARSE_WEIGHT", 0.50),
            hybrid_default_dense_weight=_env_float("RAG_HYBRID_DENSE_WEIGHT", 0.50),
            hybrid_query_classifier_llm=_env_bool("RAG_HYBRID_QUERY_CLASSIFIER_LLM", True),
            hybrid_query_classifier_model=os.getenv("RAG_HYBRID_CLASSIFIER_MODEL", "gemini-2.0-flash"),

            # Embeddings
            embedding_model=os.getenv("EMBEDDING_MODEL", "text-embedding-3-large"),
            embedding_dimensions=_env_int("EMBEDDING_DIMENSIONS", 3072),
            embedding_cache_ttl_seconds=_env_int("EMBEDDING_CACHE_TTL", 3600),
            embedding_batch_size=_env_int("EMBEDDING_BATCH_SIZE", 100),
            enable_contextual_embeddings=_env_bool("RAG_CONTEXTUAL_EMBEDDINGS_ENABLED", False),
            contextual_embeddings_max_prefix_chars=_env_int("RAG_CONTEXTUAL_EMBEDDINGS_MAX_PREFIX_CHARS", 240),

            # TTL
            local_ttl_days=_env_int("LOCAL_TTL_DAYS", 7),
            ttl_cleanup_interval_hours=_env_int("TTL_CLEANUP_INTERVAL_HOURS", 6),

            # Tracing
            trace_log_path=os.getenv("RAG_TRACE_LOG_PATH", "logs/rag_trace.jsonl"),
            trace_persist_db=_env_bool("RAG_TRACE_PERSIST_DB", False),
            trace_export_otel=_env_bool("RAG_TRACE_EXPORT_OTEL", False),
            trace_export_langsmith=_env_bool("RAG_TRACE_EXPORT_LANGSMITH", False),

            # RRF
            rrf_k=_env_int("RAG_RRF_K", 60),
            lexical_weight=_env_float("RAG_LEXICAL_WEIGHT", 0.5),
            vector_weight=_env_float("RAG_VECTOR_WEIGHT", 0.5),
            graph_weight=_env_float("RAG_GRAPH_WEIGHT", 0.3),
            graph_retrieval_limit=_env_int("RAG_GRAPH_RETRIEVAL_LIMIT", 20),

            # Citation Grounding
            enable_citation_grounding=_env_bool("CITATION_GROUNDING_ENABLED", True),
            citation_grounding_threshold=_env_float("CITATION_GROUNDING_THRESHOLD", 0.85),
            citation_grounding_neo4j=_env_bool("CITATION_GROUNDING_NEO4J", True),
            citation_grounding_annotate=_env_bool("CITATION_GROUNDING_ANNOTATE", True),

            # Search
            default_fetch_k=_env_int("RAG_DEFAULT_FETCH_K", 50),
            default_top_k=_env_int("RAG_DEFAULT_TOP_K", 10),

            # Budget caps
            max_tokens_per_request=_env_int("RAG_MAX_TOKENS_PER_REQUEST", 50000),
            max_llm_calls_per_request=_env_int("RAG_MAX_LLM_CALLS_PER_REQUEST", 5),
            warn_at_budget_percent=_env_float("RAG_WARN_AT_BUDGET_PERCENT", 0.8),

            # Result cache
            enable_result_cache=_env_bool("RAG_ENABLE_RESULT_CACHE", True),
            result_cache_ttl_seconds=_env_int("RAG_RESULT_CACHE_TTL", 300),
            result_cache_max_size=_env_int("RAG_RESULT_CACHE_MAX", 5000),

            # Per-database timeouts
            lexical_timeout_seconds=_env_float("RAG_LEXICAL_TIMEOUT", 0.5),
            vector_timeout_seconds=_env_float("RAG_VECTOR_TIMEOUT", 1.0),
            graph_search_timeout_seconds=_env_float("RAG_GRAPH_SEARCH_TIMEOUT", 0.5),
            min_sources_required=_env_int("RAG_MIN_SOURCES", 1),

            # Warm-start
            warmup_on_startup=_env_bool("RAG_WARMUP_ON_STARTUP", True),

            # CogGRAG
            enable_cograg=_env_bool("RAG_ENABLE_COGRAG", False),
            cograg_max_depth=_env_int("RAG_COGRAG_MAX_DEPTH", 3),
            cograg_max_children=_env_int("RAG_COGRAG_MAX_CHILDREN", 4),
            cograg_decomposer_model=os.getenv("RAG_COGRAG_DECOMPOSER_MODEL", "gemini-2.0-flash"),
            cograg_similarity_threshold=_env_float("RAG_COGRAG_SIMILARITY_THRESHOLD", 0.7),
            cograg_complexity_threshold=_env_float("RAG_COGRAG_COMPLEXITY_THRESHOLD", 0.5),
            cograg_theme_retrieval_enabled=_env_bool("RAG_COGRAG_THEME_RETRIEVAL", False),
            cograg_evidence_refinement_enabled=_env_bool("RAG_COGRAG_EVIDENCE_REFINEMENT", False),
            cograg_memory_enabled=_env_bool("RAG_COGRAG_MEMORY", False),
            cograg_memory_backend=os.getenv("RAG_COGRAG_MEMORY_BACKEND", "auto"),
            cograg_memory_similarity_threshold=_env_float("RAG_COGRAG_MEMORY_SIMILARITY_THRESHOLD", 0.85),
            cograg_abstain_mode=_env_bool("RAG_COGRAG_ABSTAIN_MODE", True),
            cograg_abstain_threshold=_env_float("RAG_COGRAG_ABSTAIN_THRESHOLD", 0.3),
            cograg_graph_evidence_enabled=_env_bool("RAG_COGRAG_GRAPH_EVIDENCE", True),
            cograg_graph_evidence_max_hops=_env_int("RAG_COGRAG_GRAPH_EVIDENCE_MAX_HOPS", 2),
            cograg_graph_evidence_limit=_env_int("RAG_COGRAG_GRAPH_EVIDENCE_LIMIT", 10),
            cograg_mindmap_explain_enabled=_env_bool("RAG_COGRAG_MINDMAP_EXPLAIN", False),
            cograg_mindmap_explain_format=os.getenv("RAG_COGRAG_MINDMAP_EXPLAIN_FORMAT", "json"),
            cograg_audit_mode=_env_bool("RAG_COGRAG_AUDIT_MODE", False),
            cograg_verification_enabled=_env_bool("RAG_COGRAG_VERIFICATION", False),
            cograg_verification_model=os.getenv("RAG_COGRAG_VERIFICATION_MODEL", "gemini-2.0-flash"),
            cograg_max_rethink_attempts=_env_int("RAG_COGRAG_MAX_RETHINK", 2),
            cograg_hallucination_loop=_env_bool("RAG_COGRAG_HALLUCINATION_LOOP", False),
            cograg_llm_max_concurrency=_env_int("RAG_COGRAG_LLM_MAX_CONCURRENCY", 6),

            # Lexical-first
            lexical_strong_threshold=_env_float("RAG_LEXICAL_STRONG_THRESHOLD", 0.7),

            # Graph embedding training
            graph_embedding_method=os.getenv("GRAPH_EMBEDDING_METHOD", "rotate"),
            graph_embedding_dim=_env_int("GRAPH_EMBEDDING_DIM", 128),
            graph_embedding_epochs=_env_int("GRAPH_EMBEDDING_EPOCHS", 200),
            graph_embedding_batch_size=_env_int("GRAPH_EMBEDDING_BATCH_SIZE", 512),
            graph_embedding_lr=_env_float("GRAPH_EMBEDDING_LR", 0.001),
            graph_embedding_negative_samples=_env_int("GRAPH_EMBEDDING_NEG_SAMPLES", 10),
            graph_embedding_negative_strategy=os.getenv("GRAPH_EMBEDDING_NEG_STRATEGY", "self_adv"),
            graph_embedding_patience=_env_int("GRAPH_EMBEDDING_PATIENCE", 20),
            graph_embedding_checkpoint_dir=os.getenv("GRAPH_EMBEDDING_CHECKPOINT_DIR", "data/embeddings/checkpoints"),
            graph_embedding_retrain_hours=_env_int("GRAPH_EMBEDDING_RETRAIN_HOURS", 24),
            graph_embedding_min_new_triples=_env_int("GRAPH_EMBEDDING_MIN_NEW_TRIPLES", 100),
        )

    def get_opensearch_indices(self) -> List[str]:
        """Get list of all OpenSearch indices."""
        return [
            self.opensearch_index_lei,
            self.opensearch_index_juris,
            self.opensearch_index_pecas,
            self.opensearch_index_doutrina,
            self.opensearch_index_sei,
            self.opensearch_index_local,
        ]

    def get_qdrant_collections(self) -> List[str]:
        """Get list of all Qdrant collections."""
        return [
            self.qdrant_collection_lei,
            self.qdrant_collection_juris,
            self.qdrant_collection_pecas,
            self.qdrant_collection_doutrina,
            self.qdrant_collection_sei,
            self.qdrant_collection_local,
        ]

    def get_global_indices(self) -> List[str]:
        """Get list of global OpenSearch indices (not local)."""
        return [
            self.opensearch_index_lei,
            self.opensearch_index_juris,
            self.opensearch_index_pecas,
            self.opensearch_index_doutrina,
            self.opensearch_index_sei,
        ]

    def get_global_collections(self) -> List[str]:
        """Get list of global Qdrant collections (not local)."""
        return [
            self.qdrant_collection_lei,
            self.qdrant_collection_juris,
            self.qdrant_collection_pecas,
            self.qdrant_collection_doutrina,
            self.qdrant_collection_sei,
        ]

    def get_embedding_training_config(self) -> Dict[str, Any]:
        """Get configuration for graph embedding training."""
        return {
            "method": self.graph_embedding_method,
            "embedding_dim": self.graph_embedding_dim,
            "epochs": self.graph_embedding_epochs,
            "batch_size": self.graph_embedding_batch_size,
            "learning_rate": self.graph_embedding_lr,
            "negative_samples": self.graph_embedding_negative_samples,
            "negative_strategy": self.graph_embedding_negative_strategy,
            "patience": self.graph_embedding_patience,
            "checkpoint_dir": self.graph_embedding_checkpoint_dir,
        }


# Singleton instance
_config: Optional[RAGConfig] = None


def get_rag_config() -> RAGConfig:
    """Get or create the RAG configuration singleton."""
    global _config
    if _config is None:
        _config = RAGConfig.from_env()
    return _config


def reset_rag_config() -> None:
    """Reset the configuration singleton (useful for testing)."""
    global _config
    _config = None
