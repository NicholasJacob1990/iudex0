"""fix_guest_sessions_chain

Revision ID: t1u2v3w4x5y6
Revises: t0u1v2w3x4y5
Create Date: 2026-02-02

Re-creates the guest_sessions table properly chained after shared_spaces,
since the original d9a3f7e2c1b4 migration was orphaned (branched from
wrong point and referenced shared_spaces which didn't exist at that point).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "t1u2v3w4x5y6"
down_revision: Union[str, None] = "t0u1v2w3x4y5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("guest_sessions"):
        op.create_table(
            "guest_sessions",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("guest_token", sa.String(128), unique=True, nullable=False),
            sa.Column(
                "display_name",
                sa.String(200),
                nullable=False,
                server_default="Visitante",
            ),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("permissions", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("created_from_share_token", sa.String(128), nullable=True),
            sa.Column(
                "space_id",
                sa.String(),
                sa.ForeignKey("shared_spaces.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("ip_address", sa.String(45), nullable=True),
            sa.Column("user_agent", sa.Text(), nullable=True),
            sa.Column(
                "is_active",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("1"),
            ),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column("last_accessed_at", sa.DateTime(), nullable=True),
        )
        op.create_index("idx_guest_session_token", "guest_sessions", ["guest_token"])
        op.create_index("idx_guest_session_expires", "guest_sessions", ["expires_at"])
        op.create_index(
            "idx_guest_session_space", "guest_sessions", ["space_id", "is_active"]
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("guest_sessions"):
        op.drop_index("idx_guest_session_space", table_name="guest_sessions")
        op.drop_index("idx_guest_session_expires", table_name="guest_sessions")
        op.drop_index("idx_guest_session_token", table_name="guest_sessions")
        op.drop_table("guest_sessions")
