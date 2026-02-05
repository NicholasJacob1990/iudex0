"""add workflows and workflow_runs tables

Revision ID: h8i9j0k1l2m3
Revises: g7h8i9j0k1l2
Create Date: 2026-02-02
"""
from alembic import op
import sqlalchemy as sa

revision = "h8i9j0k1l2m3"
down_revision = "g7h8i9j0k1l2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workflows",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("graph_json", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("is_active", sa.Boolean, default=True, nullable=False, server_default=sa.text("true")),
        sa.Column("is_template", sa.Boolean, default=False, nullable=False, server_default=sa.text("false")),
        sa.Column("tags", sa.JSON, nullable=False, server_default="[]"),
        # Scheduling
        sa.Column("schedule_cron", sa.String(100), nullable=True),
        sa.Column("schedule_enabled", sa.Boolean, default=False, nullable=False, server_default=sa.text("false")),
        sa.Column("schedule_timezone", sa.String(50), nullable=True, server_default="America/Sao_Paulo"),
        sa.Column("last_scheduled_run", sa.DateTime(timezone=True), nullable=True),
        sa.Column("webhook_secret", sa.String(64), nullable=True),
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    op.create_index("ix_workflows_user_id", "workflows", ["user_id"])
    op.create_index("ix_workflows_is_active", "workflows", ["is_active"])
    op.create_index("ix_workflows_schedule_enabled", "workflows", ["schedule_enabled"])

    op.create_table(
        "workflow_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workflow_id", sa.String(36), sa.ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("input_data", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("output_data", sa.JSON, nullable=True),
        sa.Column("current_node", sa.String(255), nullable=True),
        sa.Column("state_snapshot", sa.JSON, nullable=True),
        sa.Column("logs", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("trigger_type", sa.String(20), nullable=True, server_default="manual"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_workflow_runs_workflow_id", "workflow_runs", ["workflow_id"])
    op.create_index("ix_workflow_runs_status", "workflow_runs", ["status"])
    op.create_index("ix_workflow_runs_user_id", "workflow_runs", ["user_id"])


def downgrade() -> None:
    op.drop_table("workflow_runs")
    op.drop_table("workflows")
