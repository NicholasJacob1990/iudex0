"""add_shared_spaces_tables

Revision ID: t0u1v2w3x4y5
Revises: s9t0u1v2w3x4
Create Date: 2026-02-02
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "t0u1v2w3x4y5"
down_revision: Union[str, None] = "s9t0u1v2w3x4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "shared_spaces",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(200), unique=True, nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("branding", sa.JSON(), nullable=True),
        sa.Column(
            "created_by",
            sa.String(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_shared_spaces_org_id", "shared_spaces", ["organization_id"])
    op.create_index("ix_shared_spaces_slug", "shared_spaces", ["slug"])

    op.create_table(
        "space_invites",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "space_id",
            sa.String(),
            sa.ForeignKey("shared_spaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False, server_default="viewer"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("token", sa.String(255), unique=True, nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column(
            "invited_by",
            sa.String(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column(
            "user_id",
            sa.String(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("accepted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_space_invites_space_id", "space_invites", ["space_id"])
    op.create_index("ix_space_invites_email", "space_invites", ["email"])

    op.create_table(
        "space_resources",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "space_id",
            sa.String(),
            sa.ForeignKey("shared_spaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("resource_type", sa.String(50), nullable=False),
        sa.Column("resource_id", sa.String(), nullable=False),
        sa.Column("resource_name", sa.String(255), nullable=True),
        sa.Column(
            "added_by",
            sa.String(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("added_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_space_resources_space_id", "space_resources", ["space_id"])


def downgrade() -> None:
    op.drop_index("ix_space_resources_space_id", table_name="space_resources")
    op.drop_table("space_resources")

    op.drop_index("ix_space_invites_email", table_name="space_invites")
    op.drop_index("ix_space_invites_space_id", table_name="space_invites")
    op.drop_table("space_invites")

    op.drop_index("ix_shared_spaces_slug", table_name="shared_spaces")
    op.drop_index("ix_shared_spaces_org_id", table_name="shared_spaces")
    op.drop_table("shared_spaces")
