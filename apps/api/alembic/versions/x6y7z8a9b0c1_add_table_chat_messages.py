"""Add table_chat_messages table for Ask Table feature

Revision ID: x6y7z8a9b0c1
Revises: w5x6y7z8a9b0
Create Date: 2026-02-03
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "x6y7z8a9b0c1"
down_revision: Union[str, None] = "w5x6y7z8a9b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # TableChatMessage table for Ask Table feature
    op.create_table(
        "table_chat_messages",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "review_table_id",
            sa.String(),
            sa.ForeignKey("review_tables.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.String(),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "role",
            sa.Enum("user", "assistant", "system", name="messagerole"),
            nullable=False,
            server_default="user",
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("query_result", sa.JSON(), nullable=True),
        sa.Column(
            "query_type",
            sa.Enum(
                "filter", "aggregation", "comparison", "summary", "specific", "general",
                name="querytype"
            ),
            nullable=True,
        ),
        sa.Column(
            "documents_referenced",
            sa.JSON(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("visualization_hint", sa.String(50), nullable=True),
        sa.Column("msg_metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )

    # Indexes for performance
    op.create_index(
        "ix_table_chat_messages_table_id",
        "table_chat_messages",
        ["review_table_id"],
    )
    op.create_index(
        "ix_table_chat_messages_user_id",
        "table_chat_messages",
        ["user_id"],
    )
    op.create_index(
        "ix_table_chat_messages_table_created",
        "table_chat_messages",
        ["review_table_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("table_chat_messages")
    # Drop enums (PostgreSQL)
    op.execute("DROP TYPE IF EXISTS messagerole")
    op.execute("DROP TYPE IF EXISTS querytype")
