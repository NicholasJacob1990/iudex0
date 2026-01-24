
from __future__ import annotations

import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


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


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # OpenAI / Embeddings
    openai_api_key: str = ""
    openai_embedding_model: str = "text-embedding-3-large"
    openai_embedding_dimensions: int | None = None
    gemini_api_key: str = ""

    # OpenSearch
    opensearch_url: str = "https://localhost:9200"
    opensearch_user: str = "admin"
    opensearch_pass: str = "admin"

    # Qdrant
    qdrant_url: str = "http://localhost:6333"
    local_ttl_days: int = 7

    # RAG Pipeline Feature Flags
    rag_enable_crag: bool = True
    rag_enable_hyde: bool = True
    rag_enable_multiquery: bool = True
    rag_enable_rerank: bool = True
    rag_enable_compression: bool = True
    rag_enable_graph_enrich: bool = True
    rag_enable_tracing: bool = True
    rag_enable_chunk_expansion: bool = True

    # CRAG Gate thresholds
    rag_crag_min_best_score: float = 0.5
    rag_crag_min_avg_score: float = 0.35
    rag_crag_max_retries: int = 2

    # HyDE settings
    rag_hyde_model: str = "gemini-2.0-flash"
    rag_hyde_max_tokens: int = 300

    # Multi-query settings
    rag_multiquery_max: int = 3

    # Reranking settings
    rag_rerank_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    rag_rerank_top_k: int = 10
    rag_rerank_max_chars: int = 1800

    # Compression settings
    rag_compression_max_chars: int = 900
    rag_compression_min_chars: int = 100

    # Chunk expansion settings
    rag_chunk_expansion_window: int = 1
    rag_chunk_expansion_max_extra: int = 12

    # Graph enrichment settings
    rag_graph_hops: int = 2
    rag_graph_max_nodes: int = 50

    # Tracing settings
    rag_trace_log_path: str = "rag_trace.jsonl"
    rag_trace_export: str = ""  # "otel", "langsmith", "both"

    # RRF settings
    rag_rrf_k: int = 60
    rag_lexical_weight: float = 0.5
    rag_vector_weight: float = 0.5


class RAGPipelineConfig:
    """
    Runtime configuration for the RAG pipeline.
    Reads from environment variables with fallback to defaults.
    """

    def __init__(self) -> None:
        self._reload()

    def _reload(self) -> None:
        # Feature flags
        self.enable_crag = _env_bool("RAG_ENABLE_CRAG", True)
        self.enable_hyde = _env_bool("RAG_ENABLE_HYDE", True)
        self.enable_multiquery = _env_bool("RAG_ENABLE_MULTIQUERY", True)
        self.enable_rerank = _env_bool("RAG_ENABLE_RERANK", True)
        self.enable_compression = _env_bool("RAG_ENABLE_COMPRESSION", True)
        self.enable_graph_enrich = _env_bool("RAG_ENABLE_GRAPH_ENRICH", True)
        self.enable_tracing = _env_bool("RAG_ENABLE_TRACING", True)
        self.enable_chunk_expansion = _env_bool("RAG_ENABLE_CHUNK_EXPANSION", True)

        # CRAG settings
        self.crag_min_best_score = _env_float("RAG_CRAG_MIN_BEST_SCORE", 0.5)
        self.crag_min_avg_score = _env_float("RAG_CRAG_MIN_AVG_SCORE", 0.35)
        self.crag_max_retries = _env_int("RAG_CRAG_MAX_RETRIES", 2)

        # HyDE settings
        self.hyde_model = os.getenv("RAG_HYDE_MODEL", "gemini-2.0-flash")
        self.hyde_max_tokens = _env_int("RAG_HYDE_MAX_TOKENS", 300)

        # Multi-query settings
        self.multiquery_max = _env_int("RAG_MULTIQUERY_MAX", 3)

        # Reranking settings
        self.rerank_model = os.getenv("RAG_RERANK_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")
        self.rerank_top_k = _env_int("RAG_RERANK_TOP_K", 10)
        self.rerank_max_chars = _env_int("RAG_RERANK_MAX_CHARS", 1800)

        # Compression settings
        self.compression_max_chars = _env_int("RAG_COMPRESSION_MAX_CHARS", 900)
        self.compression_min_chars = _env_int("RAG_COMPRESSION_MIN_CHARS", 100)

        # Chunk expansion settings
        self.chunk_expansion_window = _env_int("RAG_CHUNK_EXPANSION_WINDOW", 1)
        self.chunk_expansion_max_extra = _env_int("RAG_CHUNK_EXPANSION_MAX_EXTRA", 12)

        # Graph enrichment settings
        self.graph_hops = _env_int("RAG_GRAPH_HOPS", 2)
        self.graph_max_nodes = _env_int("RAG_GRAPH_MAX_NODES", 50)

        # Tracing settings
        self.trace_log_path = os.getenv("RAG_TRACE_LOG_PATH", "rag_trace.jsonl")
        self.trace_export = os.getenv("RAG_TRACE_EXPORT", "")

        # RRF settings
        self.rrf_k = _env_int("RAG_RRF_K", 60)
        self.lexical_weight = _env_float("RAG_LEXICAL_WEIGHT", 0.5)
        self.vector_weight = _env_float("RAG_VECTOR_WEIGHT", 0.5)


# Singleton config instance
_pipeline_config: Optional[RAGPipelineConfig] = None


def get_pipeline_config() -> RAGPipelineConfig:
    """Get or create the pipeline configuration singleton."""
    global _pipeline_config
    if _pipeline_config is None:
        _pipeline_config = RAGPipelineConfig()
    return _pipeline_config


def get_settings() -> Settings:
    return Settings(
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        openai_embedding_model=os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-large"),
        openai_embedding_dimensions=(int(os.getenv("OPENAI_EMBEDDING_DIMENSIONS")) if os.getenv("OPENAI_EMBEDDING_DIMENSIONS") else None),
        gemini_api_key=os.getenv("GEMINI_API_KEY", os.getenv("GOOGLE_API_KEY", "")),
        opensearch_url=os.getenv("OPENSEARCH_URL", "https://localhost:9200"),
        opensearch_user=os.getenv("OPENSEARCH_USER", "admin"),
        opensearch_pass=os.getenv("OPENSEARCH_PASS", os.getenv("OPENSEARCH_INITIAL_ADMIN_PASSWORD", "admin")),
        qdrant_url=os.getenv("QDRANT_URL", "http://localhost:6333"),
        local_ttl_days=int(os.getenv("LOCAL_TTL_DAYS", "7")),
        # Pipeline settings from env
        rag_enable_crag=_env_bool("RAG_ENABLE_CRAG", True),
        rag_enable_hyde=_env_bool("RAG_ENABLE_HYDE", True),
        rag_enable_multiquery=_env_bool("RAG_ENABLE_MULTIQUERY", True),
        rag_enable_rerank=_env_bool("RAG_ENABLE_RERANK", True),
        rag_enable_compression=_env_bool("RAG_ENABLE_COMPRESSION", True),
        rag_enable_graph_enrich=_env_bool("RAG_ENABLE_GRAPH_ENRICH", True),
        rag_enable_tracing=_env_bool("RAG_ENABLE_TRACING", True),
        rag_enable_chunk_expansion=_env_bool("RAG_ENABLE_CHUNK_EXPANSION", True),
    )
