"""Harvey AI parity P1 — publishing, versioning, permissions, catalog

Revision ID: j0k1l2m3n4o5
Revises: i9j0k1l2m3n4
Create Date: 2026-02-02
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "j0k1l2m3n4o5"
down_revision: Union[str, None] = "i9j0k1l2m3n4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Workflow publishing fields
    op.add_column("workflows", sa.Column("status", sa.String(20), server_default="draft", nullable=False))
    op.add_column("workflows", sa.Column("published_version", sa.Integer(), nullable=True))
    op.add_column("workflows", sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("workflows", sa.Column("submitted_by", sa.String(), nullable=True))
    op.add_column("workflows", sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("workflows", sa.Column("approved_by", sa.String(), nullable=True))
    op.add_column("workflows", sa.Column("rejection_reason", sa.Text(), nullable=True))

    # Workflow catalog fields
    op.add_column("workflows", sa.Column("category", sa.String(50), nullable=True))
    op.add_column("workflows", sa.Column("practice_area", sa.String(100), nullable=True))
    op.add_column("workflows", sa.Column("output_type", sa.String(50), nullable=True))
    op.add_column("workflows", sa.Column("run_count", sa.Integer(), server_default="0", nullable=False))

    op.create_index("ix_workflows_category", "workflows", ["category"])
    op.create_index("ix_workflows_status", "workflows", ["status"])

    # Workflow versions table
    op.create_table(
        "workflow_versions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("workflow_id", sa.String(), sa.ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("graph_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("embedded_files", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("change_notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("workflow_id", "version", name="uq_workflow_version"),
    )
    op.create_index("ix_workflow_versions_wf", "workflow_versions", ["workflow_id", "version"])

    # Workflow permissions table
    op.create_table(
        "workflow_permissions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("workflow_id", sa.String(), sa.ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("organization_id", sa.String(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True),
        sa.Column("build_access", sa.String(10), server_default="none", nullable=False),
        sa.Column("run_access", sa.String(10), server_default="none", nullable=False),
        sa.Column("granted_by", sa.String(), nullable=False),
        sa.Column("granted_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("workflow_id", "user_id", name="uq_workflow_user_perm"),
    )
    op.create_index("ix_wf_perm_lookup", "workflow_permissions", ["workflow_id", "user_id"])

    # Organization member workflow role
    op.add_column("organization_members", sa.Column("workflow_role", sa.String(30), nullable=True))


def downgrade() -> None:
    op.drop_column("organization_members", "workflow_role")
    op.drop_table("workflow_permissions")
    op.drop_table("workflow_versions")
    op.drop_index("ix_workflows_status", table_name="workflows")
    op.drop_index("ix_workflows_category", table_name="workflows")
    op.drop_column("workflows", "run_count")
    op.drop_column("workflows", "output_type")
    op.drop_column("workflows", "practice_area")
    op.drop_column("workflows", "category")
    op.drop_column("workflows", "rejection_reason")
    op.drop_column("workflows", "approved_by")
    op.drop_column("workflows", "approved_at")
    op.drop_column("workflows", "submitted_by")
    op.drop_column("workflows", "submitted_at")
    op.drop_column("workflows", "published_version")
    op.drop_column("workflows", "status")
