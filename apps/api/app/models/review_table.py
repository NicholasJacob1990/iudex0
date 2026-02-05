"""
ReviewTable Models — Extração estruturada de dados de documentos em tabelas.

Inspirado no Harvey AI Vault Review Tables: permite selecionar um template
de extração e aplicá-lo a múltiplos documentos, gerando uma tabela (planilha)
com dados extraídos automaticamente por IA.

ReviewTableTemplate: Define as colunas de extração (reutilizável).
ReviewTable: Instância de execução — documentos + resultados extraídos.
"""

import enum
import uuid
from datetime import datetime
from typing import Optional

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


class ReviewTableStatus(str, enum.Enum):
    CREATED = "created"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ColumnType(str, enum.Enum):
    TEXT = "text"
    DATE = "date"
    CURRENCY = "currency"
    NUMBER = "number"
    VERBATIM = "verbatim"
    BOOLEAN = "boolean"
    # Novos tipos — Column Builder estilo Harvey AI
    SUMMARY = "summary"
    DATE_EXTRACTION = "date_extraction"
    YES_NO_CLASSIFICATION = "yes_no_classification"
    VERBATIM_EXTRACTION = "verbatim_extraction"
    RISK_RATING = "risk_rating"
    COMPLIANCE_CHECK = "compliance_check"
    CUSTOM = "custom"


# ---------------------------------------------------------------------------
# ReviewTableTemplate
# ---------------------------------------------------------------------------


class ReviewTableTemplate(Base):
    """Template reutilizável de extração — define as colunas a extrair."""
    __tablename__ = "review_table_templates"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(
        String(255), nullable=False,
        doc="Nome do template: 'Contratos de Trabalho', 'Due Diligence M&A', etc."
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    area: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True,
        doc="Área jurídica: trabalhista, ti, societario, imobiliario, etc."
    )

    # Definição das colunas como JSON
    # Cada coluna: {name: str, type: ColumnType, extraction_prompt: str}
    columns: Mapped[list] = mapped_column(
        JSON, default=list, nullable=False,
        doc="Lista de colunas: [{name, type, extraction_prompt}]"
    )

    is_system: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
        doc="True para templates pré-construídos pelo Iudex"
    )
    created_by: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("users.id"), nullable=True
    )
    organization_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("organizations.id"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    # Relationships
    creator = relationship("User", backref="review_table_templates", foreign_keys=[created_by])
    organization = relationship("Organization", backref="review_table_templates")
    reviews = relationship(
        "ReviewTable", back_populates="template", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_review_table_templates_area", "area"),
        Index("ix_review_table_templates_system", "is_system"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "area": self.area,
            "columns": self.columns,
            "is_system": self.is_system,
            "created_by": self.created_by,
            "organization_id": self.organization_id,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# ---------------------------------------------------------------------------
# ReviewTable (instância de execução)
# ---------------------------------------------------------------------------


class ReviewTable(Base):
    """Instância de extração — aplica um template a documentos selecionados."""
    __tablename__ = "review_tables"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    template_id: Mapped[str] = mapped_column(
        String, ForeignKey("review_table_templates.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id"), nullable=False, index=True
    )
    organization_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("organizations.id"), nullable=True, index=True
    )

    status: Mapped[str] = mapped_column(
        SQLEnum(ReviewTableStatus), default=ReviewTableStatus.CREATED, nullable=False,
        doc="Status: created, processing, completed, failed"
    )

    # IDs dos documentos selecionados
    document_ids: Mapped[list] = mapped_column(
        JSON, default=list, nullable=False,
        doc="Lista de IDs de documentos sendo revisados"
    )

    # Resultados extraídos
    # Formato: [{document_id: str, document_name: str, columns: {col_name: valor_extraído}}]
    results: Mapped[list] = mapped_column(
        JSON, default=list, nullable=False,
        doc="Linhas extraídas: [{document_id, document_name, columns: {col: val}}]"
    )

    total_documents: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    processed_documents: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    accuracy_score: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True,
        doc="Score de confiança da extração (0.0 a 1.0)"
    )

    error_message: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
        doc="Mensagem de erro se o processamento falhar"
    )

    # Cell change history tracking
    cell_history: Mapped[list] = mapped_column(
        JSON, default=list, nullable=False,
        doc="Histórico de edições de células: [{document_id, column_name, old_value, new_value, changed_by, changed_at}]"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    # Relationships
    template = relationship("ReviewTableTemplate", back_populates="reviews")
    user = relationship("User", backref="review_tables", foreign_keys=[user_id])
    organization = relationship("Organization", backref="review_tables")

    __table_args__ = (
        Index("ix_review_tables_template", "template_id"),
        Index("ix_review_tables_user_status", "user_id", "status"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "template_id": self.template_id,
            "name": self.name,
            "user_id": self.user_id,
            "organization_id": self.organization_id,
            "status": self.status,
            "document_ids": self.document_ids,
            "results": self.results,
            "total_documents": self.total_documents,
            "processed_documents": self.processed_documents,
            "accuracy_score": self.accuracy_score,
            "error_message": self.error_message,
            "cell_history": self.cell_history or [],
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
