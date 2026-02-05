"""add_playbook_run_cache_table

Revision ID: v4w5x6y7z8a9
Revises: u3v4w5x6y7z8
Create Date: 2026-02-03

Creates the playbook_run_cache table for temporarily storing playbook run
results (redlines) to be retrieved by apply/reject endpoints.
TTL of 24 hours with automatic cleanup of expired records.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "v4w5x6y7z8a9"
down_revision: Union[str, None] = "u3v4w5x6y7z8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "playbook_run_cache",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(),
            sa.ForeignKey("users.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "playbook_id",
            sa.String(),
            sa.ForeignKey("playbooks.id"),
            nullable=False,
            index=True,
        ),
        # Hash do documento para identificar se e o mesmo
        sa.Column("document_hash", sa.String(64), nullable=False, index=True),
        # Dados serializados
        sa.Column("redlines_json", sa.Text(), nullable=False),
        sa.Column("analysis_result_json", sa.Text(), nullable=False),
        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(),
            nullable=False,
            index=True,
        ),
    )

    # Indice composto para busca por usuario + playbook
    op.create_index(
        "ix_playbook_run_cache_user_playbook",
        "playbook_run_cache",
        ["user_id", "playbook_id"],
    )

    # Indice para limpeza de registros expirados
    op.create_index(
        "ix_playbook_run_cache_expires",
        "playbook_run_cache",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_playbook_run_cache_expires",
        table_name="playbook_run_cache",
    )
    op.drop_index(
        "ix_playbook_run_cache_user_playbook",
        table_name="playbook_run_cache",
    )
    op.drop_table("playbook_run_cache")
