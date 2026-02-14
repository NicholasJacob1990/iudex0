"""
Microsoft SSO user mapping - links Azure AD accounts to Iudex users.
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.time_utils import utcnow


class MicrosoftUser(Base):
    __tablename__ = "microsoft_users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    microsoft_oid: Mapped[str] = mapped_column(String(36), nullable=False)
    microsoft_tid: Mapped[str] = mapped_column(String(36), nullable=False)
    microsoft_email: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    __table_args__ = (
        UniqueConstraint("microsoft_oid", "microsoft_tid", name="uq_ms_oid_tid"),
    )

    user = relationship("User", backref="microsoft_accounts")
