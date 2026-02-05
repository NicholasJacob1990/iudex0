"""add_redline_states_table

Revision ID: w5x6y7z8a9b0
Revises: v4w5x6y7z8a9
Create Date: 2026-02-03

Creates the redline_states table for persisting redline state
(pending, applied, rejected) across Add-in sessions.
This allows users to close and reopen the Word Add-in without losing
their review progress.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "w5x6y7z8a9b0"
down_revision: Union[str, None] = "v4w5x6y7z8a9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create enum type for redline status (PostgreSQL only)
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE TYPE redlinestatus AS ENUM ('pending', 'applied', 'rejected')")

    op.create_table(
        "redline_states",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(),
            sa.ForeignKey("users.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "playbook_run_id",
            sa.String(),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "redline_id",
            sa.String(100),
            nullable=False,
        ),
        # Status: usar tipo nativo se PostgreSQL, senao String
        sa.Column(
            "status",
            sa.Enum("pending", "applied", "rejected", name="redlinestatus", create_type=False)
            if bind.dialect.name == "postgresql"
            else sa.String(20),
            nullable=False,
            default="pending",
        ),
        # Timestamps de acao
        sa.Column("applied_at", sa.DateTime(), nullable=True),
        sa.Column("rejected_at", sa.DateTime(), nullable=True),
        # Audit timestamps
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )

    # Indice composto para busca por playbook_run_id + status
    op.create_index(
        "ix_redline_state_run_status",
        "redline_states",
        ["playbook_run_id", "status"],
    )

    # Constraint de unicidade: cada redline_id e unico dentro de um playbook_run
    op.create_unique_constraint(
        "uq_run_redline",
        "redline_states",
        ["playbook_run_id", "redline_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_run_redline", "redline_states", type_="unique")
    op.drop_index("ix_redline_state_run_status", table_name="redline_states")
    op.drop_table("redline_states")

    # Drop enum type (PostgreSQL only)
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP TYPE IF EXISTS redlinestatus")
