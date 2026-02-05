"""
Modelo de configuração de retenção do Corpus por organização.

Permite que cada organização tenha políticas de retenção customizadas
para diferentes escopos e coleções, em vez de depender apenas da
configuração estática do RAGConfig.
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.time_utils import utcnow


class CorpusRetentionConfig(Base):
    """
    Configuração de retenção persistida por organização.

    Cada registro define a política de retenção para um par (scope, collection)
    dentro de uma organização. Se collection for NULL, aplica-se a todas as
    coleções daquele escopo.
    """

    __tablename__ = "corpus_retention_configs"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "scope",
            "collection",
            name="uq_retention_org_scope_collection",
        ),
    )

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    organization_id: Mapped[str] = mapped_column(
        String, index=True, nullable=False
    )
    scope: Mapped[str] = mapped_column(
        String(20), nullable=False, doc="global | private | local"
    )
    collection: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        doc="Nome da colecao ou NULL para todas",
    )
    retention_days: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        doc="Dias de retencao. NULL = indefinido.",
    )
    auto_delete: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<CorpusRetentionConfig(id={self.id}, org={self.organization_id}, "
            f"scope={self.scope}, collection={self.collection}, "
            f"retention_days={self.retention_days}, auto_delete={self.auto_delete})>"
        )
