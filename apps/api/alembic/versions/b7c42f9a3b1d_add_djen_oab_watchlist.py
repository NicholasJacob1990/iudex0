"""add_djen_oab_watchlist

Revision ID: b7c42f9a3b1d
Revises: c4f2d6b1a7c2
Create Date: 2026-01-19 09:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b7c42f9a3b1d"
down_revision: Union[str, None] = "c4f2d6b1a7c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("djen_oab_watchlist"):
        op.create_table(
            "djen_oab_watchlist",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("numero_oab", sa.String(), nullable=False),
            sa.Column("uf_oab", sa.String(), nullable=False),
            sa.Column("sigla_tribunal", sa.String(), nullable=True),
            sa.Column("meio", sa.String(), nullable=True),
            sa.Column("max_pages", sa.Integer(), nullable=True),
            sa.Column("last_sync_date", sa.Date(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        )

    existing_oab_indexes = {idx["name"] for idx in inspector.get_indexes("djen_oab_watchlist") if idx.get("name")}
    if "ix_djen_oab_watchlist_user_id" not in existing_oab_indexes:
        op.create_index("ix_djen_oab_watchlist_user_id", "djen_oab_watchlist", ["user_id"])

    existing_cols = {col["name"] for col in inspector.get_columns("djen_intimations")}
    if "oab_watchlist_id" not in existing_cols:
        op.add_column("djen_intimations", sa.Column("oab_watchlist_id", sa.String(), nullable=True))

    existing_indexes = {idx["name"] for idx in inspector.get_indexes("djen_intimations") if idx.get("name")}
    if "ix_djen_intimations_oab_watchlist_id" not in existing_indexes:
        op.create_index("ix_djen_intimations_oab_watchlist_id", "djen_intimations", ["oab_watchlist_id"])

    if bind.dialect.name != "sqlite":
        existing_fks = {fk["name"] for fk in inspector.get_foreign_keys("djen_intimations") if fk.get("name")}
        if "fk_djen_intimations_oab_watchlist_id" not in existing_fks:
            op.create_foreign_key(
                "fk_djen_intimations_oab_watchlist_id",
                "djen_intimations",
                "djen_oab_watchlist",
                ["oab_watchlist_id"],
                ["id"],
            )


def downgrade() -> None:
    op.drop_constraint("fk_djen_intimations_oab_watchlist_id", "djen_intimations", type_="foreignkey")
    op.drop_index("ix_djen_intimations_oab_watchlist_id", table_name="djen_intimations")
    op.drop_column("djen_intimations", "oab_watchlist_id")

    op.drop_index("ix_djen_oab_watchlist_user_id", table_name="djen_oab_watchlist")
    op.drop_table("djen_oab_watchlist")
