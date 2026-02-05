"""Add corpus_retention_configs table for persistent retention policies

Revision ID: n4o5p6q7r8s9
Revises: m3n4o5p6q7r8
Create Date: 2026-02-02
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "n4o5p6q7r8s9"
down_revision: Union[str, None] = "m3n4o5p6q7r8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "corpus_retention_configs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("organization_id", sa.String(), nullable=False),
        sa.Column("scope", sa.String(20), nullable=False),
        sa.Column("collection", sa.String(50), nullable=True),
        sa.Column("retention_days", sa.Integer(), nullable=True),
        sa.Column("auto_delete", sa.Boolean(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint(
            "organization_id",
            "scope",
            "collection",
            name="uq_retention_org_scope_collection",
        ),
    )
    op.create_index(
        "ix_corpus_retention_configs_organization_id",
        "corpus_retention_configs",
        ["organization_id"],
    )
    op.create_index(
        "ix_corpus_retention_configs_scope",
        "corpus_retention_configs",
        ["scope"],
    )
    op.create_index(
        "ix_corpus_retention_configs_auto_delete",
        "corpus_retention_configs",
        ["auto_delete"],
    )


def downgrade() -> None:
    op.drop_table("corpus_retention_configs")
