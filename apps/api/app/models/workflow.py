"""
Workflow Models — Visual workflow builder (React Flow → LangGraph).

Workflow stores the visual graph definition (nodes/edges from React Flow).
WorkflowRun tracks each execution with state snapshots for HIL resume.
"""

import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Index,
    Integer,
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


class WorkflowStatus(str, enum.Enum):
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    PUBLISHED = "published"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class WorkflowRunStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED_HIL = "paused_hil"
    COMPLETED = "completed"
    ERROR = "error"
    CANCELLED = "cancelled"


# ---------------------------------------------------------------------------
# Workflow (graph definition)
# ---------------------------------------------------------------------------


class Workflow(Base):
    __tablename__ = "workflows"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id"), nullable=False, index=True
    )
    organization_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("organizations.id"), nullable=True, index=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # React Flow graph definition: { nodes: [...], edges: [...] }
    graph_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_template: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    tags: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    # Embedded files — persistent files available to all prompt blocks (max 50)
    embedded_files: Mapped[list] = mapped_column(
        JSON, default=list, nullable=False,
        doc="List of embedded file refs [{id, name, size, mime_type, storage_ref}]"
    )

    # ── Publishing & Approval ──────────────────────────────────
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    published_version: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ── Custom Published App ──────────────────────────────────
    published_slug: Mapped[Optional[str]] = mapped_column(
        String(80), nullable=True, unique=True, index=True,
        doc="URL slug for the published standalone app (/app/{slug})"
    )
    published_config: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True,
        doc="Published app config: {title, description, require_auth, allow_org}"
    )

    # ── Scheduling ─────────────────────────────────────────────
    schedule_cron: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, doc="Cron expression e.g. '0 6 * * *'")
    schedule_enabled: Mapped[bool] = mapped_column(Boolean, default=False, doc="Whether scheduled execution is active")
    schedule_timezone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, default="America/Sao_Paulo")
    last_scheduled_run: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    webhook_secret: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, doc="Secret for webhook trigger auth")

    # ── Category & Catalog ────────────────────────────────────────
    category: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, index=True,
        doc="Workflow category: general, transactional, litigation, financial, administrative, labor"
    )
    practice_area: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True,
        doc="Practice area e.g. 'Direito Civil', 'Direito Penal'"
    )
    output_type: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True,
        doc="Output type: table, memo, document, checklist, timeline"
    )
    run_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False,
        doc="Total number of times this workflow has been run"
    )
    clone_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False,
        doc="Total number of times this workflow has been cloned"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    # Relationships
    user = relationship("User", backref="workflows")
    runs = relationship(
        "WorkflowRun", back_populates="workflow", cascade="all, delete-orphan"
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "organization_id": self.organization_id,
            "name": self.name,
            "description": self.description,
            "graph_json": self.graph_json,
            "is_active": self.is_active,
            "is_template": self.is_template,
            "tags": self.tags,
            "embedded_files": self.embedded_files,
            "status": self.status or "draft",
            "published_version": self.published_version,
            "submitted_at": self.submitted_at.isoformat() if self.submitted_at else None,
            "submitted_by": self.submitted_by,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
            "approved_by": self.approved_by,
            "rejection_reason": self.rejection_reason,
            "published_slug": self.published_slug,
            "published_config": self.published_config,
            "schedule_cron": self.schedule_cron,
            "schedule_enabled": self.schedule_enabled,
            "schedule_timezone": self.schedule_timezone,
            "last_scheduled_run": self.last_scheduled_run.isoformat() if self.last_scheduled_run else None,
            "category": self.category,
            "practice_area": self.practice_area,
            "output_type": self.output_type,
            "run_count": self.run_count or 0,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# ---------------------------------------------------------------------------
# WorkflowRun (execution instance)
# ---------------------------------------------------------------------------


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    workflow_id: Mapped[str] = mapped_column(
        String, ForeignKey("workflows.id"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id"), nullable=False, index=True
    )

    status: Mapped[WorkflowRunStatus] = mapped_column(
        SQLEnum(WorkflowRunStatus), default=WorkflowRunStatus.PENDING, nullable=False
    )

    # Input/output data
    input_data: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    output_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # HIL (Human-in-the-Loop) state
    current_node: Mapped[Optional[str]] = mapped_column(
        String, nullable=True
    )  # Node paused at (for HIL)
    state_snapshot: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True
    )  # LangGraph state for resume

    # Execution logs: [{ node, event, timestamp, data }]
    logs: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    # Error info
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    trigger_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, default="manual", doc="manual, scheduled, webhook")

    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )

    # Relationships
    workflow = relationship("Workflow", back_populates="runs")
    user = relationship("User", backref="workflow_runs")

    __table_args__ = (
        Index("ix_workflow_runs_status", "status"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "workflow_id": self.workflow_id,
            "user_id": self.user_id,
            "status": self.status.value,
            "input_data": self.input_data,
            "output_data": self.output_data,
            "current_node": self.current_node,
            "logs": self.logs,
            "error_message": self.error_message,
            "trigger_type": self.trigger_type,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ---------------------------------------------------------------------------
# WorkflowVersion (versioned snapshots)
# ---------------------------------------------------------------------------


class WorkflowVersion(Base):
    """Stores versioned snapshots of a workflow graph."""
    __tablename__ = "workflow_versions"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    workflow_id: Mapped[str] = mapped_column(
        String, ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    graph_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    embedded_files: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    change_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("workflow_id", "version", name="uq_workflow_version"),
        Index("ix_workflow_versions_wf", "workflow_id", "version"),
    )

    workflow = relationship("Workflow", backref="versions")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "workflow_id": self.workflow_id,
            "version": self.version,
            "graph_json": self.graph_json,
            "embedded_files": self.embedded_files,
            "change_notes": self.change_notes,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
