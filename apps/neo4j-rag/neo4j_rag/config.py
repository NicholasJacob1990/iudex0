"""Configuration via pydantic-settings (reads from .env or environment)."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Neo4j
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""
    neo4j_database: str = "neo4j"

    # Voyage AI
    voyage_api_key: str = ""
    voyage_model: str = "voyage-4-large"
    voyage_dimensions: int = 1024

    # LLM for contextual prefix
    google_api_key: str = ""
    contextual_llm_model: str = "gemini-2.5-flash"

    # Reranker
    cohere_api_key: str = ""

    # Chunking
    chunk_size: int = 2000
    chunk_overlap: int = 200
    parent_chunk_size: int = 4000

    # Retrieval
    vector_top_k: int = 50
    fulltext_top_k: int = 50
    rerank_top_n: int = 5
    max_hops: int = 5
    beam_width: int = 5
    rrf_k: int = 60


settings = Settings()
