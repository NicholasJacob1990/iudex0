"""Add playbook_versions table for version history tracking

Revision ID: r8s9t0u1v2w3
Revises: p6q7r8s9t0u1
Create Date: 2026-02-02
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "r8s9t0u1v2w3"
down_revision: Union[str, None] = "q7r8s9t0u1v2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "playbook_versions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "playbook_id",
            sa.String(),
            sa.ForeignKey("playbooks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column(
            "changed_by",
            sa.String(),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("changes_summary", sa.Text(), nullable=False),
        sa.Column("previous_rules", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_playbook_versions_playbook_id",
        "playbook_versions",
        ["playbook_id"],
    )
    op.create_index(
        "ix_playbook_versions_changed_by",
        "playbook_versions",
        ["changed_by"],
    )
    op.create_index(
        "ix_playbook_versions_playbook_version",
        "playbook_versions",
        ["playbook_id", "version_number"],
    )


def downgrade() -> None:
    op.drop_index("ix_playbook_versions_playbook_version", table_name="playbook_versions")
    op.drop_index("ix_playbook_versions_changed_by", table_name="playbook_versions")
    op.drop_index("ix_playbook_versions_playbook_id", table_name="playbook_versions")
    op.drop_table("playbook_versions")
