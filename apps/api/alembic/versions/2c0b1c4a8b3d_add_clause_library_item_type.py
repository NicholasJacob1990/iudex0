"""add_clause_library_item_type

Revision ID: 2c0b1c4a8b3d
Revises: 491a07bb915f
Create Date: 2026-01-13 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "2c0b1c4a8b3d"
down_revision: Union[str, None] = "491a07bb915f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    for enum_name in ("libraryitemtype", "LibraryItemType"):
        try:
            op.execute(f"ALTER TYPE {enum_name} ADD VALUE IF NOT EXISTS 'CLAUSE'")
            break
        except Exception:
            continue


def downgrade() -> None:
    # Nao e possivel remover valores de ENUM no Postgres sem recriar o tipo.
    pass
