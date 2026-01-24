"""add_djen_tables_actual

Revision ID: c4f2d6b1a7c2
Revises: 8bae1a269027
Create Date: 2026-01-18 10:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c4f2d6b1a7c2"
down_revision: Union[str, None] = "8bae1a269027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "process_watchlist",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("case_id", sa.String(), nullable=True),
        sa.Column("npu", sa.String(), nullable=False),
        sa.Column("npu_formatted", sa.String(), nullable=True),
        sa.Column("tribunal_sigla", sa.String(), nullable=False),
        sa.Column("tribunal_alias", sa.String(), nullable=False),
        sa.Column("last_datajud_check", sa.DateTime(), nullable=True),
        sa.Column("last_mov_datetime", sa.String(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"]),
    )
    op.create_index("ix_process_watchlist_user_id", "process_watchlist", ["user_id"])
    op.create_index("ix_process_watchlist_case_id", "process_watchlist", ["case_id"])
    op.create_index("ix_process_watchlist_npu", "process_watchlist", ["npu"])

    op.create_table(
        "djen_intimations",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("watchlist_id", sa.String(), nullable=True),
        sa.Column("hash", sa.String(), nullable=False),
        sa.Column("comunicacao_id", sa.Integer(), nullable=True),
        sa.Column("numero_processo", sa.String(), nullable=False),
        sa.Column("numero_processo_mascara", sa.String(), nullable=True),
        sa.Column("tribunal_sigla", sa.String(), nullable=False),
        sa.Column("tipo_comunicacao", sa.String(), nullable=True),
        sa.Column("nome_orgao", sa.String(), nullable=True),
        sa.Column("texto", sa.Text(), nullable=True),
        sa.Column("data_disponibilizacao", sa.Date(), nullable=True),
        sa.Column("meio", sa.String(), nullable=True),
        sa.Column("link", sa.String(), nullable=True),
        sa.Column("tipo_documento", sa.String(), nullable=True),
        sa.Column("nome_classe", sa.String(), nullable=True),
        sa.Column("numero_comunicacao", sa.Integer(), nullable=True),
        sa.Column("ativo", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["watchlist_id"], ["process_watchlist.id"]),
    )
    op.create_index("ix_djen_intimations_user_id", "djen_intimations", ["user_id"])
    op.create_index("ix_djen_intimations_watchlist_id", "djen_intimations", ["watchlist_id"])
    op.create_index("ix_djen_intimations_hash", "djen_intimations", ["hash"])
    op.create_index("ix_djen_intimations_numero_processo", "djen_intimations", ["numero_processo"])
    op.create_unique_constraint(
        "uq_djen_intimations_user_hash",
        "djen_intimations",
        ["user_id", "hash"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_djen_intimations_user_hash", "djen_intimations", type_="unique")
    op.drop_index("ix_djen_intimations_numero_processo", table_name="djen_intimations")
    op.drop_index("ix_djen_intimations_hash", table_name="djen_intimations")
    op.drop_index("ix_djen_intimations_watchlist_id", table_name="djen_intimations")
    op.drop_index("ix_djen_intimations_user_id", table_name="djen_intimations")
    op.drop_table("djen_intimations")

    op.drop_index("ix_process_watchlist_npu", table_name="process_watchlist")
    op.drop_index("ix_process_watchlist_case_id", table_name="process_watchlist")
    op.drop_index("ix_process_watchlist_user_id", table_name="process_watchlist")
    op.drop_table("process_watchlist")
