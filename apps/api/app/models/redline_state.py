"""
RedlineState Model — Persistencia de estado de redlines do Word Add-in.

Armazena o estado de cada redline (pending, applied, rejected) para permitir
que o usuario feche e reabra o Add-in sem perder o progresso da revisao.
"""

import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.time_utils import utcnow


class RedlineStatus(str, enum.Enum):
    """Status possíveis de um redline."""
    PENDING = "pending"
    APPLIED = "applied"
    REJECTED = "rejected"


class RedlineState(Base):
    """
    Estado persistido de um redline individual.

    Permite rastrear quais redlines foram aplicados, rejeitados ou ainda
    estao pendentes de revisao para um determinado playbook run.
    """
    __tablename__ = "redline_states"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id"), nullable=False, index=True
    )
    playbook_run_id: Mapped[str] = mapped_column(
        String, nullable=False, index=True,
        doc="ID unico do playbook run (gerado pelo frontend ou backend)"
    )
    redline_id: Mapped[str] = mapped_column(
        String(100), nullable=False,
        doc="ID do redline dentro do playbook run"
    )
    status: Mapped[str] = mapped_column(
        SQLEnum(RedlineStatus), default=RedlineStatus.PENDING, nullable=False,
        doc="Status: pending, applied, rejected"
    )

    # Timestamps de acao
    applied_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True,
        doc="Data/hora em que o redline foi aplicado"
    )
    rejected_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True,
        doc="Data/hora em que o redline foi rejeitado"
    )

    # Audit timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, onupdate=utcnow
    )

    # Relationships
    user = relationship("User", backref="redline_states", foreign_keys=[user_id])

    __table_args__ = (
        # Indice composto para busca rapida por playbook_run_id + status
        Index("ix_redline_state_run_status", "playbook_run_id", "status"),
        # Constraint de unicidade: cada redline_id e unico dentro de um playbook_run
        UniqueConstraint("playbook_run_id", "redline_id", name="uq_run_redline"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "playbook_run_id": self.playbook_run_id,
            "redline_id": self.redline_id,
            "status": self.status.value if isinstance(self.status, RedlineStatus) else self.status,
            "applied_at": self.applied_at.isoformat() if self.applied_at else None,
            "rejected_at": self.rejected_at.isoformat() if self.rejected_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
