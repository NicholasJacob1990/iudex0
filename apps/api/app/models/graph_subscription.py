"""Graph webhook subscription tracking."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.time_utils import utcnow


class GraphSubscription(Base):
    __tablename__ = "graph_subscriptions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    subscription_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    resource: Mapped[str] = mapped_column(String(255), nullable=False)
    change_types: Mapped[str] = mapped_column(String(100), nullable=False)
    expiration_datetime: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    client_state: Mapped[str] = mapped_column(String(255), nullable=False)
    notification_url: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    renewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user = relationship("User", backref="graph_subscriptions")

    __table_args__ = (
        Index("ix_graph_subs_expiry", "expiration_datetime"),
    )
