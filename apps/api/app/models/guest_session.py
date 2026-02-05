"""
Modelo de Sessao de Visitante (Guest Session)

Sessoes anonimas/temporarias com acesso limitado (somente leitura)
vinculadas opcionalmente a um SharedSpace ou convite de compartilhamento.
"""

from datetime import datetime
from typing import Optional
import uuid

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.time_utils import utcnow


class GuestSession(Base):
    __tablename__ = "guest_sessions"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )

    # Token unico URL-safe para identificar a sessao guest
    guest_token: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False, index=True
    )

    # Nome de exibicao (opcional - "Visitante" por padrao)
    display_name: Mapped[str] = mapped_column(
        String(200), default="Visitante", nullable=False
    )

    # Expiracao da sessao
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # Permissoes do guest (JSON): quais recursos pode acessar
    # Formato: {"spaces": ["space_id_1"], "resources": ["res_id_1"], "permissions": ["read"]}
    permissions: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    # Vinculo com compartilhamento (opcional)
    created_from_share_token: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True,
        doc="Token do SpaceInvite que originou esta sessao guest"
    )
    space_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("shared_spaces.id", ondelete="SET NULL"),
        nullable=True, index=True,
        doc="SharedSpace ao qual o guest tem acesso"
    )

    # IP / User Agent para auditoria
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )
    last_accessed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )

    __table_args__ = (
        Index("idx_guest_session_expires", "expires_at"),
        Index("idx_guest_session_space", "space_id", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<GuestSession(id={self.id}, space={self.space_id}, expires={self.expires_at})>"

    @property
    def is_expired(self) -> bool:
        return utcnow() > self.expires_at
