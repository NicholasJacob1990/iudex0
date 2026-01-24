"""
Configurações da aplicação usando Pydantic Settings
"""

from typing import List, Optional
import os
from pathlib import Path
from dotenv import load_dotenv
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

def _resolve_env_file() -> Path:
    """
    Resolve which .env file to load.

    Prefer an explicit IUDEX_ENV_FILE, otherwise try common monorepo locations:
    - apps/api/app/.env (legacy)
    - apps/api/.env
    - repo root .env
    """
    override_path = os.getenv("IUDEX_ENV_FILE")
    if override_path:
        candidate = Path(override_path).expanduser()
        if candidate.exists():
            return candidate

    candidates = [
        Path(__file__).resolve().parents[2] / ".env",
        Path(__file__).resolve().parents[3] / ".env",
        Path(__file__).resolve().parents[5] / ".env",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


ENV_FILE = _resolve_env_file()
if ENV_FILE.exists():
    load_dotenv(ENV_FILE, override=False)


class Settings(BaseSettings):
    """Configurações da aplicação"""
    
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )
    
    # Ambiente
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    SECRET_KEY: str
    
    # Servidor
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    WORKERS: int = 4
    
    # CORS
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:3002",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        "http://127.0.0.1:3002",
        "http://0.0.0.0:3000",
        "http://0.0.0.0:3001",
        "http://0.0.0.0:3002",
    ]
    
    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v
    
    # Banco de Dados
    DATABASE_URL: str
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 10
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # Celery
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"
    
    # JWT
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # OpenAI (opcional - usado como fallback)
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-4-turbo-preview"
    OPENAI_TEMPERATURE: float = 0.7
    OPENAI_MAX_TOKENS: int = 4000
    
    # Anthropic (Claude) - opcional
    ANTHROPIC_API_KEY: Optional[str] = None
    # Use canonical id; provider name is resolved via model_registry.get_api_model_name()
    ANTHROPIC_MODEL: str = "claude-4.5-sonnet"
    ANTHROPIC_TEMPERATURE: float = 0.7
    ANTHROPIC_MAX_TOKENS: int = 4000
    
    # Google (Gemini)
    GOOGLE_CLOUD_PROJECT: Optional[str] = None
    VERTEX_AI_LOCATION: Optional[str] = None
    GOOGLE_API_KEY: Optional[str] = None
    # Alias comum em setups locais (aceitar também)
    GEMINI_API_KEY: Optional[str] = None
    GOOGLE_MODEL: str = "gemini-2.5-pro"
    GOOGLE_TEMPERATURE: float = 0.7
    GOOGLE_MAX_TOKENS: int = 4000
    
    # Embeddings
    EMBEDDING_MODEL: str = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"
    EMBEDDING_DIMENSION: int = 768
    
    # Vector Database
    PINECONE_API_KEY: Optional[str] = None
    PINECONE_ENVIRONMENT: Optional[str] = None
    PINECONE_INDEX_NAME: Optional[str] = "iudex-documents"
    
    QDRANT_URL: Optional[str] = None
    QDRANT_API_KEY: Optional[str] = None
    QDRANT_COLLECTION_NAME: str = "iudex-documents"
    
    CHROMA_PATH: str = "./data/chroma"
    
    # Storage
    S3_ENDPOINT_URL: Optional[str] = None
    S3_ACCESS_KEY_ID: Optional[str] = None
    S3_SECRET_ACCESS_KEY: Optional[str] = None
    S3_BUCKET_NAME: Optional[str] = None
    S3_REGION: str = "us-east-1"
    
    LOCAL_STORAGE_PATH: str = "./storage"
    
    # OCR
    TESSERACT_CMD: str = "/usr/bin/tesseract"
    TESSERACT_LANG: str = "por"
    OCR_DPI: int = 300
    
    # Processamento de Áudio
    WHISPER_MODEL: str = "base"
    AUDIO_MAX_SIZE_MB: int = 4096
    
    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_PER_MINUTE: int = 60
    RATE_LIMIT_PER_HOUR: int = 1000
    
    # Cache
    CACHE_TTL_SECONDS: int = 3600
    CACHE_ENABLED: bool = True
    
    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"
    
    # Sentry
    SENTRY_DSN: Optional[str] = None
    
    # Limites
    MAX_UPLOAD_SIZE_MB: int = 4096

    # Attachment context limits (chars ≈ tokens * 4)
    ATTACHMENT_INJECTION_MAX_CHARS: int = 120000
    ATTACHMENT_INJECTION_MAX_CHARS_PER_DOC: int = 40000
    ATTACHMENT_INJECTION_MAX_FILES: int = 20
    ATTACHMENT_RAG_LOCAL_MAX_FILES: int = 200
    ATTACHMENT_RAG_LOCAL_TOP_K: int = 25
    RAG_CONTEXT_MAX_CHARS: int = 20000
    RAG_CONTEXT_MAX_CHARS_PROMPT_INJECTION: int = 40000
    UPLOAD_CACHE_MIN_BYTES: int = 2 * 1024 * 1024
    UPLOAD_CACHE_MIN_FILES: int = 4
    MENTION_MAX_ITEMS: int = 10
    MENTION_MAX_CONTENT_CHARS: int = 40000
    MAX_DOCUMENTS_PER_USER: int = 1000
    MAX_CONTEXT_TOKENS: int = 3000000
    
    # Feature Flags
    ENABLE_MULTI_AGENT: bool = True
    ENABLE_WEB_SEARCH: bool = True
    ENABLE_OCR: bool = True
    ENABLE_TRANSCRIPTION: bool = True
    ENABLE_PODCAST_GENERATION: bool = True
    
    # APIs Externas
    CNJ_API_URL: Optional[str] = None
    CNJ_API_KEY: Optional[str] = None
    DJEN_API_URL: Optional[str] = None
    DJEN_API_KEY: Optional[str] = None
    JURISPRUDENCE_API_URL: Optional[str] = None
    JURISPRUDENCE_API_KEY: Optional[str] = None
    
    @property
    def max_upload_size_bytes(self) -> int:
        """Retorna o tamanho máximo de upload em bytes"""
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    
    @property
    def is_production(self) -> bool:
        """Verifica se está em produção"""
        return self.ENVIRONMENT.lower() == "production"
    
    @property
    def is_development(self) -> bool:
        """Verifica se está em desenvolvimento"""
        return self.ENVIRONMENT.lower() == "development"
    
    @property
    def ACCESS_TOKEN_EXPIRE_MINUTES(self) -> int:
        """Alias para JWT_ACCESS_TOKEN_EXPIRE_MINUTES"""
        return self.JWT_ACCESS_TOKEN_EXPIRE_MINUTES

    @model_validator(mode="after")
    def validate_google_api_key(self):
        # Aceitar GEMINI_API_KEY como alias de GOOGLE_API_KEY para compatibilidade.
        if not self.GOOGLE_API_KEY and self.GEMINI_API_KEY:
            self.GOOGLE_API_KEY = self.GEMINI_API_KEY

        # Último fallback: ler do ambiente (caso Pydantic ignore por config)
        if not self.GOOGLE_API_KEY:
            env_alias = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
            if env_alias:
                self.GOOGLE_API_KEY = env_alias

        if not self.GOOGLE_API_KEY and not self.GOOGLE_CLOUD_PROJECT:
            raise ValueError("GOOGLE_API_KEY (ou GEMINI_API_KEY) é obrigatória quando GOOGLE_CLOUD_PROJECT não está definido")
        return self


# Instância global de configurações
settings = Settings()

def _promote_settings_env() -> None:
    """Ensure critical provider keys are available via os.getenv for legacy clients."""
    key_map = {
        "OPENAI_API_KEY": settings.OPENAI_API_KEY,
        "ANTHROPIC_API_KEY": settings.ANTHROPIC_API_KEY,
        "GOOGLE_API_KEY": settings.GOOGLE_API_KEY,
        "GEMINI_API_KEY": settings.GEMINI_API_KEY,
        "GOOGLE_CLOUD_PROJECT": settings.GOOGLE_CLOUD_PROJECT,
        "VERTEX_AI_LOCATION": settings.VERTEX_AI_LOCATION,
        "OPENROUTER_API_KEY": getattr(settings, "OPENROUTER_API_KEY", None),
        "XAI_API_KEY": getattr(settings, "XAI_API_KEY", None),
    }
    for key, value in key_map.items():
        if value and not os.getenv(key):
            os.environ[key] = str(value)

_promote_settings_env()
