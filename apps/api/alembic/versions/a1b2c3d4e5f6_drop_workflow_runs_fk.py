"""drop_workflow_runs_workflow_id_fk

Drop FK constraint on workflow_runs.workflow_id to allow
builtin workflow slugs (e.g. 'extract-deadlines') as values.

Revision ID: a1b2c3d4e5f6
Revises: 08d7b20d24a2
Create Date: 2026-02-10 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '08d7b20d24a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Naming convention so batch mode can find the unnamed FK
_naming_convention = {
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
}


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    fk_names: list[str] = []
    for fk in insp.get_foreign_keys("workflow_runs"):
        if (
            fk.get("referred_table") == "workflows"
            and fk.get("constrained_columns") == ["workflow_id"]
        ):
            if fk.get("name"):
                fk_names.append(fk["name"])

    # Nothing to do (already dropped or different schema).
    if not fk_names:
        return

    # Batch mode is safe for SQLite and for renaming/recreating constraints.
    with op.batch_alter_table(
        "workflow_runs",
        schema=None,
        naming_convention=_naming_convention,
        recreate="always",
    ) as batch_op:
        for name in fk_names:
            batch_op.drop_constraint(name, type_="foreignkey")


def downgrade() -> None:
    with op.batch_alter_table(
        'workflow_runs',
        schema=None,
        naming_convention=_naming_convention,
        recreate='always',
    ) as batch_op:
        batch_op.create_foreign_key(
            'fk_workflow_runs_workflow_id_workflows',
            'workflows',
            ['workflow_id'],
            ['id'],
        )
