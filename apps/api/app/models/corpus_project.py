"""
Corpus Project Models — Projetos dinâmicos de corpus com suporte a Knowledge Base.

Permite criar projetos organizacionais ilimitados (semelhante ao "Vault projects" do Harvey AI),
com opção de marcar como Knowledge Base para consulta workspace-wide.
"""

import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Index,
    Integer,
    BigInteger,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.time_utils import utcnow


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ProjectScope(str, enum.Enum):
    PERSONAL = "personal"
    ORGANIZATION = "organization"


class ProjectDocumentStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    INGESTED = "ingested"
    FAILED = "failed"


class ProjectSharePermission(str, enum.Enum):
    VIEW = "view"
    EDIT = "edit"
    ADMIN = "admin"


# ---------------------------------------------------------------------------
# CorpusProject (container organizacional de documentos)
# ---------------------------------------------------------------------------


class CorpusProject(Base):
    """Projeto dinâmico de corpus — container organizacional para documentos RAG."""
    __tablename__ = "corpus_projects"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    owner_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id"), nullable=False, index=True
    )
    organization_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("organizations.id"), nullable=True, index=True
    )

    # Type
    is_knowledge_base: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
        doc="Se True, disponível para consulta workspace-wide"
    )
    scope: Mapped[str] = mapped_column(
        SQLEnum(ProjectScope), default=ProjectScope.PERSONAL, nullable=False,
        doc="Escopo: personal ou organization"
    )

    # Settings
    collection_name: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False,
        doc="Slug auto-gerado para coleção OpenSearch/Qdrant"
    )
    max_documents: Mapped[int] = mapped_column(
        Integer, default=10000, nullable=False,
        doc="Limite máximo de documentos no projeto"
    )
    retention_days: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True,
        doc="Dias de retenção (None = indefinido)"
    )

    # Stats (cached, updated periodically)
    document_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    chunk_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    storage_size_bytes: Mapped[int] = mapped_column(
        BigInteger, default=0, nullable=False
    )
    last_indexed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )

    # Metadata
    metadata_: Mapped[Optional[dict]] = mapped_column(
        "metadata", JSON, nullable=True,
        doc="Configurações extras e metadados"
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
    owner = relationship("User", backref="corpus_projects", foreign_keys=[owner_id])
    organization = relationship("Organization", backref="corpus_projects")
    project_documents = relationship(
        "CorpusProjectDocument", back_populates="project", cascade="all, delete-orphan"
    )
    shares = relationship(
        "CorpusProjectShare", back_populates="project", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_corpus_projects_owner_active", "owner_id", "is_active"),
        Index("ix_corpus_projects_org_active", "organization_id", "is_active"),
        Index("ix_corpus_projects_kb", "is_knowledge_base"),
        Index("ix_corpus_projects_scope", "scope"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "owner_id": self.owner_id,
            "organization_id": self.organization_id,
            "is_knowledge_base": self.is_knowledge_base,
            "scope": self.scope,
            "collection_name": self.collection_name,
            "max_documents": self.max_documents,
            "retention_days": self.retention_days,
            "document_count": self.document_count,
            "chunk_count": self.chunk_count,
            "storage_size_bytes": self.storage_size_bytes,
            "last_indexed_at": self.last_indexed_at.isoformat() if self.last_indexed_at else None,
            "metadata": self.metadata_,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# ---------------------------------------------------------------------------
# CorpusProjectDocument (associação projeto <-> documento)
# ---------------------------------------------------------------------------


class CorpusProjectDocument(Base):
    """Associação de documento a um projeto de corpus."""
    __tablename__ = "corpus_project_documents"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    project_id: Mapped[str] = mapped_column(
        String, ForeignKey("corpus_projects.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    document_id: Mapped[str] = mapped_column(
        String, ForeignKey("documents.id"), nullable=False, index=True
    )

    # Folder hierarchy
    folder_path: Mapped[Optional[str]] = mapped_column(
        String(1024), nullable=True, index=True,
        doc="Caminho da pasta virtual (ex: 'Contratos/2026/Janeiro')"
    )

    status: Mapped[str] = mapped_column(
        SQLEnum(ProjectDocumentStatus),
        default=ProjectDocumentStatus.PENDING,
        nullable=False,
        doc="Status da ingestão: pending, processing, ingested, failed"
    )
    ingested_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
        doc="Mensagem de erro caso a ingestão falhe"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )

    # Relationships
    project = relationship("CorpusProject", back_populates="project_documents")
    document = relationship("Document", backref="corpus_project_entries")

    __table_args__ = (
        Index("ix_corpus_project_docs_project_doc", "project_id", "document_id", unique=True),
        Index("ix_corpus_project_docs_status", "project_id", "status"),
        Index("ix_corpus_project_docs_folder", "project_id", "folder_path"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "document_id": self.document_id,
            "folder_path": self.folder_path,
            "status": self.status,
            "ingested_at": self.ingested_at.isoformat() if self.ingested_at else None,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ---------------------------------------------------------------------------
# CorpusProjectShare (compartilhamento de projeto)
# ---------------------------------------------------------------------------


class CorpusProjectShare(Base):
    """Compartilhamento de projeto de corpus com usuários ou organizações."""
    __tablename__ = "corpus_project_shares"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    project_id: Mapped[str] = mapped_column(
        String, ForeignKey("corpus_projects.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    shared_with_user_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("users.id"), nullable=True, index=True
    )
    shared_with_org_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("organizations.id"), nullable=True, index=True
    )

    permission: Mapped[str] = mapped_column(
        SQLEnum(ProjectSharePermission),
        default=ProjectSharePermission.VIEW,
        nullable=False,
        doc="Permissão: view, edit, admin"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )

    # Relationships
    project = relationship("CorpusProject", back_populates="shares")
    shared_with_user = relationship(
        "User", backref="corpus_project_shares_received",
        foreign_keys=[shared_with_user_id]
    )
    shared_with_org = relationship(
        "Organization", backref="corpus_project_shares_received"
    )

    __table_args__ = (
        Index("ix_corpus_project_shares_lookup", "project_id", "shared_with_user_id"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "shared_with_user_id": self.shared_with_user_id,
            "shared_with_org_id": self.shared_with_org_id,
            "permission": self.permission,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
