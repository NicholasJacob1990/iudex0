"""Add party_perspective to playbooks and cell_history to review_tables

Revision ID: s9t0u1v2w3x4
Revises: s0t1u2v3w4x5
Create Date: 2026-02-02
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "s9t0u1v2w3x4"
down_revision: Union[str, None] = "s0t1u2v3w4x5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Task 2: Add party_perspective to playbooks
    op.add_column(
        "playbooks",
        sa.Column("party_perspective", sa.String(20), nullable=False, server_default="neutro"),
    )

    # Task 4: Add cell_history to review_tables
    op.add_column(
        "review_tables",
        sa.Column("cell_history", sa.JSON(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("review_tables", "cell_history")
    op.drop_column("playbooks", "party_perspective")
