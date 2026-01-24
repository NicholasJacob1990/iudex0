"""
Modelo de política de acesso ao RAG por escopo (private/group/global).
"""

from datetime import datetime
import uuid
from typing import Optional, List

from sqlalchemy import String, DateTime, Boolean, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.time_utils import utcnow


class RAGAccessPolicy(Base):
    __tablename__ = "rag_access_policies"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    user_id: Mapped[Optional[str]] = mapped_column(String, index=True, nullable=True)

    allow_global: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    allow_groups: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    group_ids: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    def __repr__(self) -> str:
        return (
            f"<RAGAccessPolicy(id={self.id}, tenant_id={self.tenant_id}, "
            f"user_id={self.user_id}, allow_global={self.allow_global}, allow_groups={self.allow_groups})>"
        )
