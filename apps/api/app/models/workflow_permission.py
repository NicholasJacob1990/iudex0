"""
Workflow Permissions — 2-layer access control (Build + Run).

Layer 1: Workspace-level roles (WorkflowBuilderRole on OrganizationMember)
Layer 2: Per-workflow permissions (WorkflowPermission)
"""

import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    ForeignKey,
    Index,
    String,
    DateTime,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Enum as SQLEnum

from app.core.database import Base
from app.core.time_utils import utcnow


class WorkflowBuilderRole(str, enum.Enum):
    """Workspace-level workflow role."""
    WORKFLOW_ADMIN = "workflow_admin"      # Create/edit/approve/publish all workflows
    WORKFLOW_BUILDER = "workflow_builder"  # Create/edit/submit own workflows
    WORKFLOW_USER = "workflow_user"        # Run shared workflows only


class BuildAccess(str, enum.Enum):
    """Per-workflow build access level."""
    NONE = "none"
    VIEW = "view"    # Can view the graph but not edit
    EDIT = "edit"    # Can edit and collaborate
    FULL = "full"    # Can edit, submit, manage permissions


class RunAccess(str, enum.Enum):
    """Per-workflow run access level."""
    NONE = "none"
    RUN = "run"      # Can execute the workflow


class WorkflowPermission(Base):
    """Per-workflow permission grant."""
    __tablename__ = "workflow_permissions"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    workflow_id: Mapped[str] = mapped_column(
        String, ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    organization_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True
    )

    build_access: Mapped[BuildAccess] = mapped_column(
        SQLEnum(BuildAccess), default=BuildAccess.NONE, nullable=False
    )
    run_access: Mapped[RunAccess] = mapped_column(
        SQLEnum(RunAccess), default=RunAccess.NONE, nullable=False
    )

    granted_by: Mapped[str] = mapped_column(String, nullable=False)
    granted_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("workflow_id", "user_id", name="uq_workflow_user_perm"),
        Index("ix_wf_perm_lookup", "workflow_id", "user_id"),
    )

    workflow = relationship("Workflow", backref="permissions")
    user = relationship("User", backref="workflow_permissions")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "workflow_id": self.workflow_id,
            "user_id": self.user_id,
            "organization_id": self.organization_id,
            "build_access": self.build_access.value,
            "run_access": self.run_access.value,
            "granted_by": self.granted_by,
            "granted_at": self.granted_at.isoformat() if self.granted_at else None,
        }
