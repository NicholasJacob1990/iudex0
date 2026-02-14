"""
Graph Risk Reports — Persisted results for fraud/audit scans.
"""

import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from sqlalchemy import DateTime, String, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.time_utils import utcnow


def _default_expires_at() -> datetime:
    # Default retention: 30 days.
    return utcnow() + timedelta(days=30)


class GraphRiskReport(Base):
    __tablename__ = "graph_risk_reports"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))

    tenant_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    user_id: Mapped[str] = mapped_column(String, index=True, nullable=False)

    status: Mapped[str] = mapped_column(String(20), default="completed", nullable=False)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    params: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
    )
    signals: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
        doc="Raw payload (signals serialized as JSON)",
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, default=_default_expires_at, nullable=False, index=True)

    def __repr__(self) -> str:
        return f"<GraphRiskReport(id={self.id}, tenant={self.tenant_id}, user={self.user_id}, status={self.status})>"
