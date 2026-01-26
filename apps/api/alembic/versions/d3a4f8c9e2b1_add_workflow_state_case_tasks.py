"""add_workflow_state_case_tasks

Revision ID: d3a4f8c9e2b1
Revises: b7c42f9a3b1d
Create Date: 2026-01-24 15:00:00

Adds:
- workflow_states table for persisting LangGraph DocumentState
- case_tasks table for derived tasks with deadlines
- New columns on cases: cnj_number, classe, assunto, partes (JSONB)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d3a4f8c9e2b1"
down_revision: Union[str, None] = "b7c42f9a3b1d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # ===== WORKFLOW_STATES TABLE =====
    if not inspector.has_table("workflow_states"):
        op.create_table(
            "workflow_states",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("case_id", sa.String(), sa.ForeignKey("cases.id"), nullable=True, index=True),
            sa.Column("job_id", sa.String(), nullable=False, unique=True, index=True),
            sa.Column("chat_id", sa.String(), nullable=True, index=True),
            sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("status", sa.String(), default="completed"),

            # Retrieval & Sources
            sa.Column("retrieval_queries", sa.JSON(), default=list),
            sa.Column("sources", sa.JSON(), default=list),
            sa.Column("citations_map", sa.JSON(), default=dict),

            # Drafts
            sa.Column("final_document_ref", sa.String(), nullable=True),
            sa.Column("final_document_chars", sa.Integer(), nullable=True),
            sa.Column("drafts_history", sa.JSON(), default=list),

            # Decisions
            sa.Column("routing_decisions", sa.JSON(), default=dict),
            sa.Column("alert_decisions", sa.JSON(), default=dict),
            sa.Column("citation_decisions", sa.JSON(), default=dict),
            sa.Column("audit_decisions", sa.JSON(), default=dict),
            sa.Column("quality_decisions", sa.JSON(), default=dict),

            # HIL & Sections
            sa.Column("hil_history", sa.JSON(), default=list),
            sa.Column("processed_sections", sa.JSON(), default=list),

            # Config & Metrics
            sa.Column("workflow_config", sa.JSON(), default=dict),
            sa.Column("metrics", sa.JSON(), default=dict),

            # Timestamps
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
        )

    # ===== CASE_TASKS TABLE =====
    if not inspector.has_table("case_tasks"):
        op.create_table(
            "case_tasks",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("case_id", sa.String(), sa.ForeignKey("cases.id"), nullable=False, index=True),
            sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False, index=True),

            # Identification
            sa.Column("title", sa.String(), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("task_type", sa.String(), default="other"),

            # Priority & Status
            sa.Column("priority", sa.String(), default="medium"),
            sa.Column("status", sa.String(), default="pending"),

            # Deadlines
            sa.Column("deadline", sa.DateTime(), nullable=True, index=True),
            sa.Column("reminder_at", sa.DateTime(), nullable=True),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("completed_at", sa.DateTime(), nullable=True),

            # Source
            sa.Column("source", sa.String(), default="manual"),
            sa.Column("source_ref", sa.String(), nullable=True),

            # Related document
            sa.Column("document_ref", sa.String(), nullable=True),
            sa.Column("workflow_state_id", sa.String(), sa.ForeignKey("workflow_states.id"), nullable=True),

            # Extra data
            sa.Column("extra_data", sa.JSON(), default=dict),

            # Recurrence
            sa.Column("is_recurring", sa.Boolean(), default=False),
            sa.Column("recurrence_rule", sa.String(), nullable=True),

            # Ordering
            sa.Column("order_index", sa.Integer(), default=0),

            # Timestamps
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )

    # ===== NEW COLUMNS ON CASES TABLE =====
    existing_columns = [col["name"] for col in inspector.get_columns("cases")]
    existing_indexes = [idx["name"] for idx in inspector.get_indexes("cases")]

    if "cnj_number" not in existing_columns:
        op.add_column("cases", sa.Column("cnj_number", sa.String(), nullable=True))
        # Create index separately to avoid issues with add_column index=True
        if "ix_cases_cnj_number" not in existing_indexes:
            op.create_index("ix_cases_cnj_number", "cases", ["cnj_number"])

    if "classe" not in existing_columns:
        op.add_column("cases", sa.Column("classe", sa.String(), nullable=True))

    if "assunto" not in existing_columns:
        op.add_column("cases", sa.Column("assunto", sa.String(), nullable=True))

    if "partes" not in existing_columns:
        op.add_column("cases", sa.Column("partes", sa.JSON(), default=dict))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Drop new columns from cases
    existing_columns = [col["name"] for col in inspector.get_columns("cases")]

    if "cnj_number" in existing_columns:
        op.drop_index("ix_cases_cnj_number", table_name="cases")
        op.drop_column("cases", "cnj_number")

    if "classe" in existing_columns:
        op.drop_column("cases", "classe")

    if "assunto" in existing_columns:
        op.drop_column("cases", "assunto")

    if "partes" in existing_columns:
        op.drop_column("cases", "partes")

    # Drop tables
    if inspector.has_table("case_tasks"):
        op.drop_table("case_tasks")

    if inspector.has_table("workflow_states"):
        op.drop_table("workflow_states")
