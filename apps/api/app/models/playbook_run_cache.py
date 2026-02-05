"""
PlaybookRunCache — Cache temporario para redlines de analise de playbook.

Armazena os redlines gerados por uma execucao de playbook para que possam
ser recuperados posteriormente pelos endpoints de apply/reject.
TTL de 24 horas com limpeza automatica de registros expirados.
"""

import uuid
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.time_utils import utcnow


def default_expires_at() -> datetime:
    """Retorna datetime 24h no futuro para TTL padrao."""
    return utcnow() + timedelta(hours=24)


class PlaybookRunCache(Base):
    """
    Cache temporario de uma execucao de playbook.

    Armazena os redlines e resultados de analise para que possam ser
    recuperados pelos endpoints de apply individual/batch.

    TTL padrao de 24 horas. Registros expirados devem ser limpos periodicamente.
    """
    __tablename__ = "playbook_run_cache"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id"), nullable=False, index=True
    )
    playbook_id: Mapped[str] = mapped_column(
        String, ForeignKey("playbooks.id"), nullable=False, index=True
    )

    # Hash do documento para identificar se e o mesmo documento
    document_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True,
        doc="SHA256 hash do conteudo do documento analisado"
    )

    # Dados serializados como JSON string
    redlines_json: Mapped[str] = mapped_column(
        Text, nullable=False,
        doc="JSON serializado dos RedlineItems"
    )
    analysis_result_json: Mapped[str] = mapped_column(
        Text, nullable=False,
        doc="JSON serializado do resultado completo da analise"
    )

    # Timestamps e TTL
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime, default=default_expires_at, nullable=False, index=True,
        doc="Expira apos 24h por padrao"
    )

    # Relationships
    user = relationship("User", backref="playbook_run_caches")
    playbook = relationship("Playbook", backref="run_caches")

    __table_args__ = (
        Index("ix_playbook_run_cache_user_playbook", "user_id", "playbook_id"),
        Index("ix_playbook_run_cache_expires", "expires_at"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "playbook_id": self.playbook_id,
            "document_hash": self.document_hash,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }

    @property
    def is_expired(self) -> bool:
        """Verifica se o cache expirou."""
        return utcnow() > self.expires_at
