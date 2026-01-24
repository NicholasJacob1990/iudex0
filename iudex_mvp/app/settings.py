
from __future__ import annotations

import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    openai_api_key: str = ""
    openai_embedding_model: str = "text-embedding-3-large"
    openai_embedding_dimensions: int | None = None

    opensearch_url: str = "https://localhost:9200"
    opensearch_user: str = "admin"
    opensearch_pass: str = "admin"

    qdrant_url: str = "http://localhost:6333"
    local_ttl_days: int = 7


def get_settings() -> Settings:
    return Settings(
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        openai_embedding_model=os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-large"),
        openai_embedding_dimensions=(int(os.getenv("OPENAI_EMBEDDING_DIMENSIONS")) if os.getenv("OPENAI_EMBEDDING_DIMENSIONS") else None),
        opensearch_url=os.getenv("OPENSEARCH_URL", "https://localhost:9200"),
        opensearch_user=os.getenv("OPENSEARCH_USER", "admin"),
        opensearch_pass=os.getenv("OPENSEARCH_PASS", os.getenv("OPENSEARCH_INITIAL_ADMIN_PASSWORD", "admin")),
        qdrant_url=os.getenv("QDRANT_URL", "http://localhost:6333"),
        local_ttl_days=int(os.getenv("LOCAL_TTL_DAYS", "7")),
    )
