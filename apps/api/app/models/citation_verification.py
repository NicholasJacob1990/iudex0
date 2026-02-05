"""
Modelo de Verificação de Citações (Shepardização BR)

Persiste resultados de verificação de vigência de citações jurídicas.
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, DateTime, JSON, Text, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
import enum

from app.core.database import Base
from app.core.time_utils import utcnow


class CitationStatus(str, enum.Enum):
    """Status de vigência de uma citação jurídica."""
    VIGENTE = "vigente"
    SUPERADA = "superada"
    REVOGADA = "revogada"
    ALTERADA = "alterada"
    INCONSTITUCIONAL = "inconstitucional"
    NAO_VERIFICADA = "nao_verificada"


class CitationType(str, enum.Enum):
    """Tipo de citação jurídica extraída."""
    SUMULA = "sumula"
    SUMULA_VINCULANTE = "sumula_vinculante"
    LEI = "lei"
    ARTIGO = "artigo"
    JURISPRUDENCIA = "jurisprudencia"
    ACORDAO = "acordao"
    DECRETO = "decreto"
    MEDIDA_PROVISORIA = "medida_provisoria"
    CONSTITUICAO = "constituicao"
    OUTRO = "outro"


class CitationVerification(Base):
    """Resultado persistido de verificação de citação."""
    __tablename__ = "citation_verifications"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    document_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("documents.id"), nullable=True, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id"), nullable=False, index=True
    )

    # Citação original
    citation_text: Mapped[str] = mapped_column(Text, nullable=False)
    citation_type: Mapped[str] = mapped_column(String, nullable=False)
    citation_normalized: Mapped[Optional[str]] = mapped_column(
        String, nullable=True
    )

    # Resultado da verificação
    status: Mapped[str] = mapped_column(String, nullable=False, default="nao_verificada")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    verification_sources: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    # Metadados
    verified_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    extra: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<CitationVerification(id={self.id}, "
            f"citation='{self.citation_text[:50]}...', "
            f"status={self.status})>"
        )
