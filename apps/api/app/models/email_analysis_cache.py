"""Email analysis cache to avoid re-processing the same email."""

import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, ForeignKey, JSON, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.time_utils import utcnow


class EmailAnalysisCache(Base):
    __tablename__ = "email_analysis_cache"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    internet_message_id: Mapped[str] = mapped_column(String(500), nullable=False)
    analysis_type: Mapped[str] = mapped_column(String(50), nullable=False)
    result: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "internet_message_id", "analysis_type", name="uq_email_cache"),
        Index("ix_email_cache_lookup", "user_id", "internet_message_id", "analysis_type"),
        Index("ix_email_cache_expiry", "expires_at"),
    )
