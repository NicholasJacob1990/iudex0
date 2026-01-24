"""
API Call Usage tracking for billing and analytics.
"""

from datetime import datetime
from typing import Optional, Any, Dict

from sqlalchemy import String, DateTime, Boolean, JSON, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.time_utils import utcnow


class ApiCallUsage(Base):
    __tablename__ = "api_call_usage"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    scope_type: Mapped[str] = mapped_column(String, index=True)
    scope_id: Mapped[str] = mapped_column(String, index=True)
    turn_id: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    user_id: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    provider: Mapped[str] = mapped_column(String, nullable=False)
    model: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    success: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    cached: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    meta: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    __table_args__ = (
        Index("idx_api_call_usage_scope", "scope_type", "scope_id"),
    )
