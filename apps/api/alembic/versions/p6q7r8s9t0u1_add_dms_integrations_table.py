"""Add dms_integrations table

Revision ID: p6q7r8s9t0u1
Revises: o5p6q7r8s9t0
Create Date: 2026-02-02
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "p6q7r8s9t0u1"
down_revision: Union[str, None] = "o5p6q7r8s9t0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "dms_integrations",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "org_id",
            sa.String(),
            sa.ForeignKey("organizations.id"),
            nullable=True,
        ),
        sa.Column(
            "user_id",
            sa.String(),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("credentials_encrypted", sa.Text(), nullable=False),
        sa.Column("root_folder_id", sa.String(500), nullable=True),
        sa.Column(
            "sync_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("last_sync_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_dms_integrations_user_id", "dms_integrations", ["user_id"])
    op.create_index("ix_dms_integrations_org_id", "dms_integrations", ["org_id"])
    op.create_index("ix_dms_integrations_provider", "dms_integrations", ["provider"])
    op.create_index(
        "ix_dms_integrations_user_provider",
        "dms_integrations",
        ["user_id", "provider"],
    )


def downgrade() -> None:
    op.drop_index("ix_dms_integrations_user_provider", table_name="dms_integrations")
    op.drop_index("ix_dms_integrations_provider", table_name="dms_integrations")
    op.drop_index("ix_dms_integrations_org_id", table_name="dms_integrations")
    op.drop_index("ix_dms_integrations_user_id", table_name="dms_integrations")
    op.drop_table("dms_integrations")
