"""
Dynamic Column Models - Colunas dinamicas para Review Tables.

Permite que usuarios criem colunas via perguntas em linguagem natural
(similar ao Harvey AI Column Builder), onde cada coluna extrai dados
especificos de todos os documentos de uma Review Table.

DynamicColumn: Definicao de uma coluna criada via prompt.
CellExtraction: Valor extraido de um documento para uma coluna.
"""

import enum
import uuid
from datetime import datetime
from typing import Optional, List

from sqlalchemy import (
    Enum as SQLEnum,
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.time_utils import utcnow


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ExtractionType(str, enum.Enum):
    """Tipo de dado extraido pela coluna."""
    TEXT = "text"  # Texto livre/resumo
    BOOLEAN = "boolean"  # Sim/Nao
    NUMBER = "number"  # Valor numerico
    DATE = "date"  # Data
    CURRENCY = "currency"  # Valor monetario
    ENUM = "enum"  # Opcoes pre-definidas
    LIST = "list"  # Lista de itens
    VERBATIM = "verbatim"  # Transcricao literal
    RISK_RATING = "risk_rating"  # Baixo/Medio/Alto/Critico
    COMPLIANCE_CHECK = "compliance_check"  # Conforme/Nao Conforme/Parcialmente


class VerificationStatus(str, enum.Enum):
    """Status de verificacao de uma celula extraida."""
    PENDING = "pending"  # Aguardando revisao
    VERIFIED = "verified"  # Confirmado como correto
    REJECTED = "rejected"  # Marcado como incorreto
    CORRECTED = "corrected"  # Corrigido manualmente


# ---------------------------------------------------------------------------
# DynamicColumn - Definicao de coluna dinamica
# ---------------------------------------------------------------------------


class DynamicColumn(Base):
    """Coluna dinamica criada via pergunta em linguagem natural.

    Cada DynamicColumn pertence a uma ReviewTable e define uma pergunta
    que sera respondida para cada documento da tabela.

    Exemplo de uso:
        Prompt: "What type of registration rights are granted?"
        Tipo: enum
        Opcoes: ["Demand", "Piggyback", "S-3", "None"]

    A coluna e processada para todos os documentos da review table,
    gerando uma CellExtraction para cada documento.
    """
    __tablename__ = "dynamic_columns"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    review_table_id: Mapped[str] = mapped_column(
        String, ForeignKey("review_tables.id", ondelete="CASCADE"),
        nullable=False, index=True
    )

    # Identificacao da coluna
    name: Mapped[str] = mapped_column(
        String(255), nullable=False,
        doc="Nome da coluna (gerado ou fornecido pelo usuario)"
    )
    prompt: Mapped[str] = mapped_column(
        Text, nullable=False,
        doc="Pergunta em linguagem natural que define a extracao"
    )

    # Tipo e configuracao de extracao
    extraction_type: Mapped[str] = mapped_column(
        SQLEnum(ExtractionType), default=ExtractionType.TEXT, nullable=False,
        doc="Tipo de dado esperado na resposta"
    )
    enum_options: Mapped[Optional[list]] = mapped_column(
        JSON, nullable=True,
        doc="Opcoes validas para tipo 'enum' (ex: ['Sim', 'Nao', 'N/A'])"
    )

    # Instrucoes adicionais para extracao
    extraction_instructions: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
        doc="Instrucoes adicionais para guiar a extracao (ex: 'Considere apenas clausulas do capitulo 3')"
    )

    # Ordenacao e estado
    order: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False,
        doc="Ordem de exibicao na tabela"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False,
        doc="Se False, a coluna esta desativada mas nao deletada"
    )

    # Metadata de criacao
    created_by: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    # Relationships
    review_table = relationship("ReviewTable", backref="dynamic_columns")
    creator = relationship("User", foreign_keys=[created_by])
    extractions = relationship(
        "CellExtraction",
        back_populates="column",
        cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_dynamic_columns_review_table", "review_table_id"),
        Index("ix_dynamic_columns_active", "review_table_id", "is_active"),
        Index("ix_dynamic_columns_order", "review_table_id", "order"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "review_table_id": self.review_table_id,
            "name": self.name,
            "prompt": self.prompt,
            "extraction_type": self.extraction_type,
            "enum_options": self.enum_options,
            "extraction_instructions": self.extraction_instructions,
            "order": self.order,
            "is_active": self.is_active,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# ---------------------------------------------------------------------------
# CellExtraction - Valor extraido para uma celula
# ---------------------------------------------------------------------------


class CellExtraction(Base):
    """Valor extraido de um documento para uma coluna dinamica.

    Cada CellExtraction representa uma "celula" na review table:
    a intersecao de uma DynamicColumn com um Document.

    Armazena o valor extraido, score de confianca, status de verificacao,
    e o trecho fonte usado para extracao (para citacao/auditoria).
    """
    __tablename__ = "cell_extractions"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )

    # References
    dynamic_column_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("dynamic_columns.id", ondelete="CASCADE"),
        nullable=True, index=True,
        doc="ID da coluna dinamica (null para colunas de template)"
    )
    document_id: Mapped[str] = mapped_column(
        String, ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    review_table_id: Mapped[str] = mapped_column(
        String, ForeignKey("review_tables.id", ondelete="CASCADE"),
        nullable=False, index=True
    )

    # Valor extraido
    extracted_value: Mapped[str] = mapped_column(
        Text, nullable=False,
        doc="Valor extraido (JSON serializado para tipos complexos)"
    )
    raw_value: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
        doc="Valor bruto antes de formatacao (para auditoria)"
    )

    # Confianca e fonte
    confidence: Mapped[float] = mapped_column(
        Float, default=0.5, nullable=False,
        doc="Score de confianca da extracao (0.0 a 1.0)"
    )
    source_snippet: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
        doc="Trecho do documento usado para extracao (max 500 chars)"
    )
    source_page: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True,
        doc="Pagina do documento onde a informacao foi encontrada"
    )

    # Verificacao humana
    verification_status: Mapped[str] = mapped_column(
        SQLEnum(VerificationStatus),
        default=VerificationStatus.PENDING,
        nullable=False,
        doc="Status de verificacao: pending, verified, rejected, corrected"
    )
    verified_by: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("users.id"), nullable=True
    )
    verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    verification_note: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
        doc="Nota do revisor ao verificar/rejeitar"
    )

    # Correcao manual
    corrected_value: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
        doc="Valor corrigido manualmente (se diferente do extraido)"
    )
    correction_note: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
        doc="Nota do usuario explicando a correcao"
    )

    # Posicao no documento fonte
    source_char_start: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True,
        doc="Posicao inicial do trecho no texto do documento"
    )
    source_char_end: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True,
        doc="Posicao final do trecho no texto do documento"
    )

    # Metadata de extracao
    extraction_model: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True,
        doc="Modelo de IA usado na extracao"
    )
    extraction_reasoning: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
        doc="Raciocinio do modelo sobre a extracao"
    )

    # Nome da coluna (para colunas do template, nao apenas dynamic columns)
    column_name: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True,
        doc="Nome da coluna do template (para colunas nao-dinamicas)"
    )

    # Timestamps
    extracted_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    # Relationships
    column = relationship("DynamicColumn", back_populates="extractions")
    document = relationship("Document", foreign_keys=[document_id])
    verifier = relationship("User", foreign_keys=[verified_by])

    __table_args__ = (
        Index("ix_cell_extractions_column_doc", "dynamic_column_id", "document_id", unique=True),
        Index("ix_cell_extractions_review_table", "review_table_id"),
        Index("ix_cell_extractions_verification", "review_table_id", "verification_status"),
        Index("ix_cell_extractions_confidence", "review_table_id", "confidence"),
    )

    @property
    def display_value(self) -> str:
        """Retorna o valor a ser exibido (corrigido se existir, senao extraido)."""
        return self.corrected_value or self.extracted_value

    @property
    def is_verified(self) -> bool:
        """Retorna True se a celula foi verificada ou corrigida."""
        return self.verification_status in (
            VerificationStatus.VERIFIED.value,
            VerificationStatus.CORRECTED.value,
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "dynamic_column_id": self.dynamic_column_id,
            "document_id": self.document_id,
            "review_table_id": self.review_table_id,
            "column_name": self.column_name,
            "extracted_value": self.extracted_value,
            "raw_value": self.raw_value,
            "display_value": self.display_value,
            "confidence": self.confidence,
            "source_snippet": self.source_snippet,
            "source_page": self.source_page,
            "source_char_start": self.source_char_start,
            "source_char_end": self.source_char_end,
            "verification_status": self.verification_status,
            "is_verified": self.is_verified,
            "verified_by": self.verified_by,
            "verified_at": self.verified_at.isoformat() if self.verified_at else None,
            "verification_note": self.verification_note,
            "corrected_value": self.corrected_value,
            "correction_note": self.correction_note,
            "extraction_model": self.extraction_model,
            "extraction_reasoning": self.extraction_reasoning,
            "extracted_at": self.extracted_at.isoformat() if self.extracted_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
