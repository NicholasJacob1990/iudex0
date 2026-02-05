"""Add playbook_analyses table for persisted analysis results

Revision ID: l2m3n4o5p6q7
Revises: k1l2m3n4o5p6
Create Date: 2026-02-02
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "l2m3n4o5p6q7"
down_revision: Union[str, None] = "k1l2m3n4o5p6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "playbook_analyses",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("playbook_id", sa.String(), sa.ForeignKey("playbooks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_id", sa.String(), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("organization_id", sa.String(), sa.ForeignKey("organizations.id"), nullable=True),
        sa.Column("total_rules", sa.Integer(), nullable=False),
        sa.Column("compliant", sa.Integer(), server_default="0", nullable=False),
        sa.Column("needs_review", sa.Integer(), server_default="0", nullable=False),
        sa.Column("non_compliant", sa.Integer(), server_default="0", nullable=False),
        sa.Column("not_found", sa.Integer(), server_default="0", nullable=False),
        sa.Column("risk_score", sa.Float(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("clause_results", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("reviewed_clauses", sa.JSON(), nullable=True),
        sa.Column("model_used", sa.String(100), nullable=True),
        sa.Column("analysis_duration_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_playbook_analyses_playbook_id", "playbook_analyses", ["playbook_id"])
    op.create_index("ix_playbook_analyses_document_id", "playbook_analyses", ["document_id"])
    op.create_index("ix_playbook_analyses_user_id", "playbook_analyses", ["user_id"])
    op.create_index("ix_playbook_analyses_organization_id", "playbook_analyses", ["organization_id"])
    op.create_index("ix_playbook_analyses_playbook_doc", "playbook_analyses", ["playbook_id", "document_id"])
    op.create_index("ix_playbook_analyses_user_created", "playbook_analyses", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_table("playbook_analyses")
