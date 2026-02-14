"""Email trigger configuration — per-user rules for dispatching workflows via email."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.time_utils import utcnow


class EmailTriggerConfig(Base):
    __tablename__ = "email_trigger_configs"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Matching rules
    command_prefix: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, default="/iudex",
        doc="Prefix that must appear in subject to trigger (e.g. '/iudex')"
    )
    command: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True,
        doc="Specific command to match (e.g. 'extract-deadlines')"
    )
    sender_filter: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True,
        doc="Only match emails from this sender"
    )
    subject_contains: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True,
        doc="Only match emails whose subject contains this string"
    )
    require_attachment: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
        doc="Only match if email has attachments"
    )

    # Authorized senders (JSON array of email addresses)
    authorized_senders: Mapped[list] = mapped_column(
        JSON, default=list, nullable=False,
        doc="List of email addresses authorized to trigger this config"
    )

    # Target workflow
    workflow_id: Mapped[str] = mapped_column(
        String, nullable=False,
        doc="Builtin slug or real workflow UUID to execute"
    )
    workflow_parameters: Mapped[dict] = mapped_column(
        JSON, default=dict, nullable=False,
        doc="Default parameters to pass to the workflow"
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user = relationship("User", backref="email_trigger_configs")

    __table_args__ = (
        Index("ix_email_trigger_configs_active", "user_id", "is_active"),
    )
