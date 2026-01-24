"""
Config endpoints (read-only limits for frontend)
"""

from fastapi import APIRouter

from app.core.config import settings
from app.services.billing_service import get_billing_config
from app.utils.validators import InputValidator

router = APIRouter()


@router.get("/limits")
async def get_limits():
    return {
        "max_upload_size_mb": settings.MAX_UPLOAD_SIZE_MB,
        "max_upload_size_bytes": settings.max_upload_size_bytes,
        "audio_max_size_mb": settings.AUDIO_MAX_SIZE_MB,
        "attachment_injection_max_chars": settings.ATTACHMENT_INJECTION_MAX_CHARS,
        "attachment_injection_max_chars_per_doc": settings.ATTACHMENT_INJECTION_MAX_CHARS_PER_DOC,
        "attachment_injection_max_files": settings.ATTACHMENT_INJECTION_MAX_FILES,
        "attachment_rag_local_max_files": settings.ATTACHMENT_RAG_LOCAL_MAX_FILES,
        "attachment_rag_local_top_k": settings.ATTACHMENT_RAG_LOCAL_TOP_K,
        "rag_context_max_chars": settings.RAG_CONTEXT_MAX_CHARS,
        "rag_context_max_chars_prompt_injection": settings.RAG_CONTEXT_MAX_CHARS_PROMPT_INJECTION,
        "upload_cache_min_bytes": settings.UPLOAD_CACHE_MIN_BYTES,
        "upload_cache_min_files": settings.UPLOAD_CACHE_MIN_FILES,
        "provider_upload_limits_mb": InputValidator.get_provider_upload_limits_mb(),
    }


@router.get("/billing")
async def get_billing():
    return get_billing_config()
