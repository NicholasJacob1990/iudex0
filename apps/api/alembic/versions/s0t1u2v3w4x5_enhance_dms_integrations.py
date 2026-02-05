"""Enhance dms_integrations with connection_status and provider_metadata

Revision ID: s0t1u2v3w4x5
Revises: r8s9t0u1v2w3
Create Date: 2026-02-02
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "s0t1u2v3w4x5"
down_revision: Union[str, None] = "r8s9t0u1v2w3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "dms_integrations",
        sa.Column(
            "connection_status",
            sa.String(20),
            nullable=True,
            server_default="connected",
        ),
    )
    op.add_column(
        "dms_integrations",
        sa.Column("provider_metadata", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("dms_integrations", "provider_metadata")
    op.drop_column("dms_integrations", "connection_status")
