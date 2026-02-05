"""
Schemas Pydantic para verificação de citações (Shepardização BR).
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class VerifyCitationsRequest(BaseModel):
    """Request para POST /knowledge/verify-citations."""
    text: Optional[str] = Field(
        None,
        description="Texto jurídico para extrair e verificar citações",
    )
    citations: Optional[List[str]] = Field(
        None,
        description="Lista explícita de citações para verificar",
    )
    use_llm_extraction: bool = Field(
        True,
        description="Usar LLM para extrair citações além do regex",
    )
    use_cache: bool = Field(
        True,
        description="Usar cache de verificações anteriores (TTL 7 dias)",
    )


class ShepardizeRequest(BaseModel):
    """Request para POST /knowledge/shepardize."""
    document_id: str = Field(
        ...,
        description="ID do documento a shepardizar",
    )
    use_cache: bool = Field(
        True,
        description="Usar cache de verificações anteriores",
    )


class CitationVerificationItem(BaseModel):
    """Uma citação verificada no response."""
    citation_text: str
    citation_type: str
    citation_normalized: Optional[str] = None
    status: str
    confidence: float = 0.0
    details: Optional[str] = None
    source_url: Optional[str] = None
    verification_sources: Dict[str, Any] = Field(default_factory=dict)
    verified_at: str


class VerifyCitationsResponse(BaseModel):
    """Response para verify-citations."""
    total_citations: int = 0
    verified: int = 0
    vigentes: int = 0
    problematic: int = 0
    citations: List[CitationVerificationItem] = Field(default_factory=list)
    summary: Optional[str] = None
    generated_at: str


class ShepardizeResponse(BaseModel):
    """Response para shepardize."""
    document_id: Optional[str] = None
    total_citations: int = 0
    verified: int = 0
    vigentes: int = 0
    problematic: int = 0
    citations: List[CitationVerificationItem] = Field(default_factory=list)
    summary: Optional[str] = None
    generated_at: str
