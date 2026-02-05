"""Add published_slug and published_config to workflows for custom published apps

Revision ID: m3n4o5p6q7r8
Revises: l2m3n4o5p6q7
Create Date: 2026-02-02
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "m3n4o5p6q7r8"
down_revision: Union[str, None] = "l2m3n4o5p6q7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "workflows",
        sa.Column("published_slug", sa.String(80), nullable=True, unique=True),
    )
    op.add_column(
        "workflows",
        sa.Column("published_config", sa.JSON(), nullable=True),
    )
    op.create_index("ix_workflows_published_slug", "workflows", ["published_slug"])


def downgrade() -> None:
    op.drop_index("ix_workflows_published_slug", table_name="workflows")
    op.drop_column("workflows", "published_config")
    op.drop_column("workflows", "published_slug")
