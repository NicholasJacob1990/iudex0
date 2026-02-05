"""Add review_table_templates and review_tables for structured data extraction

Revision ID: n5o6p7q8r9s0
Revises: n4o5p6q7r8s9
Create Date: 2026-02-02
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "n5o6p7q8r9s0"
down_revision: Union[str, None] = "n4o5p6q7r8s9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -- review_table_templates --
    op.create_table(
        "review_table_templates",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("area", sa.String(100), nullable=True),
        sa.Column("columns", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("is_system", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("created_by", sa.String(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("organization_id", sa.String(), sa.ForeignKey("organizations.id"), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_review_table_templates_area", "review_table_templates", ["area"])
    op.create_index("ix_review_table_templates_system", "review_table_templates", ["is_system"])
    op.create_index("ix_review_table_templates_created_by", "review_table_templates", ["created_by"])
    op.create_index("ix_review_table_templates_organization_id", "review_table_templates", ["organization_id"])

    # -- review_tables --
    op.create_table(
        "review_tables",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("template_id", sa.String(), sa.ForeignKey("review_table_templates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("organization_id", sa.String(), sa.ForeignKey("organizations.id"), nullable=True),
        sa.Column("status", sa.String(50), server_default="created", nullable=False),
        sa.Column("document_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("results", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("total_documents", sa.Integer(), server_default="0", nullable=False),
        sa.Column("processed_documents", sa.Integer(), server_default="0", nullable=False),
        sa.Column("accuracy_score", sa.Float(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_review_tables_template", "review_tables", ["template_id"])
    op.create_index("ix_review_tables_user_id", "review_tables", ["user_id"])
    op.create_index("ix_review_tables_organization_id", "review_tables", ["organization_id"])
    op.create_index("ix_review_tables_user_status", "review_tables", ["user_id", "status"])


def downgrade() -> None:
    op.drop_table("review_tables")
    op.drop_table("review_table_templates")
