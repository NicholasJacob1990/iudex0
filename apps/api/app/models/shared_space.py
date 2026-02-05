"""
Modelos de Shared Spaces — Espaços compartilhados com clientes externos

Permite que organizações criem workspaces branded para convidar
clientes (guests) com acesso controlado a workflows, documentos e runs.
"""

from datetime import datetime
from typing import Optional
import enum
import uuid

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Index,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.time_utils import utcnow


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class SpaceRole(str, enum.Enum):
    """Papel do membro dentro do space."""
    ADMIN = "admin"            # Gerencia space, convida membros
    CONTRIBUTOR = "contributor" # Pode adicionar recursos
    VIEWER = "viewer"          # Somente visualização


class InviteStatus(str, enum.Enum):
    """Status do convite."""
    PENDING = "pending"
    ACCEPTED = "accepted"
    REVOKED = "revoked"


# ---------------------------------------------------------------------------
# SharedSpace
# ---------------------------------------------------------------------------

class SharedSpace(Base):
    __tablename__ = "shared_spaces"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    organization_id: Mapped[str] = mapped_column(
        String, ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(
        String(200), nullable=False, index=True
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Branding personalizado: {logo_url, primary_color, accent_color}
    branding: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    created_by: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    # Relationships
    invites = relationship(
        "SpaceInvite", back_populates="space", cascade="all, delete-orphan"
    )
    resources = relationship(
        "SpaceResource", back_populates="space", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("organization_id", "slug", name="uq_space_org_slug"),
    )

    def __repr__(self) -> str:
        return f"<SharedSpace(id={self.id}, name={self.name}, org={self.organization_id})>"


# ---------------------------------------------------------------------------
# SpaceInvite
# ---------------------------------------------------------------------------

class SpaceInvite(Base):
    __tablename__ = "space_invites"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    space_id: Mapped[str] = mapped_column(
        String, ForeignKey("shared_spaces.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    role: Mapped[SpaceRole] = mapped_column(
        SQLEnum(SpaceRole), default=SpaceRole.VIEWER, nullable=False
    )
    status: Mapped[InviteStatus] = mapped_column(
        SQLEnum(InviteStatus), default=InviteStatus.PENDING, nullable=False
    )
    token: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    invited_by: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    user_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
        doc="Preenchido quando o convite é aceito"
    )
    accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    # Relationships
    space = relationship("SharedSpace", back_populates="invites")

    __table_args__ = (
        Index("idx_space_invite_email", "space_id", "email"),
    )

    def __repr__(self) -> str:
        return f"<SpaceInvite(space={self.space_id}, email={self.email}, status={self.status})>"


# ---------------------------------------------------------------------------
# SpaceResource
# ---------------------------------------------------------------------------

class SpaceResource(Base):
    __tablename__ = "space_resources"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    space_id: Mapped[str] = mapped_column(
        String, ForeignKey("shared_spaces.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    resource_type: Mapped[str] = mapped_column(
        String(50), nullable=False,
        doc="Tipo: workflow, document, run, folder"
    )
    resource_id: Mapped[str] = mapped_column(String, nullable=False)
    resource_name: Mapped[Optional[str]] = mapped_column(
        String(300), nullable=True,
        doc="Nome cacheado para exibição rápida"
    )
    added_by: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    added_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    # Relationships
    space = relationship("SharedSpace", back_populates="resources")

    __table_args__ = (
        UniqueConstraint("space_id", "resource_type", "resource_id", name="uq_space_resource"),
        Index("idx_space_resource_lookup", "space_id", "resource_type"),
    )

    def __repr__(self) -> str:
        return f"<SpaceResource(space={self.space_id}, type={self.resource_type}, res={self.resource_id})>"
