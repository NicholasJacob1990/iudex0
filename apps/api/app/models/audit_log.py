"""
Modelo de Audit Log para rastreamento de ações no sistema.

Registra todas as ações significativas dos usuários para
compliance, segurança e análise de uso.
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.time_utils import utcnow


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id"), nullable=False, index=True
    )
    action: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # create, read, update, delete, export, share, login, analyze
    resource_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # playbook, corpus_project, review_table, document, chat, dms, user, organization
    resource_id: Mapped[Optional[str]] = mapped_column(
        String, nullable=True
    )
    details: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True
    )  # Contexto extra: nome do recurso, campos alterados, etc.
    ip_address: Mapped[Optional[str]] = mapped_column(
        String(45), nullable=True  # suporta IPv6
    )
    user_agent: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow
    )

    __table_args__ = (
        Index("ix_audit_logs_created_at", "created_at"),
        Index("ix_audit_logs_user_action", "user_id", "action"),
        Index("ix_audit_logs_resource", "resource_type", "resource_id"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "action": self.action,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "details": self.details,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
