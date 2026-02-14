"""add_graph_risk_reports

Revision ID: y7z8a9b0c1d2
Revises: x6y7z8a9b0c3
Create Date: 2026-02-08

Creates table graph_risk_reports for persisted fraud/audit scan results.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "y7z8a9b0c1d2"
down_revision: Union[str, None] = "x6y7z8a9b0c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "graph_risk_reports",
        sa.Column("id", sa.String(), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="completed"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("signals", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_graph_risk_reports_tenant_id", "graph_risk_reports", ["tenant_id"])
    op.create_index("ix_graph_risk_reports_user_id", "graph_risk_reports", ["user_id"])
    op.create_index("ix_graph_risk_reports_expires_at", "graph_risk_reports", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_graph_risk_reports_expires_at", table_name="graph_risk_reports")
    op.drop_index("ix_graph_risk_reports_user_id", table_name="graph_risk_reports")
    op.drop_index("ix_graph_risk_reports_tenant_id", table_name="graph_risk_reports")
    op.drop_table("graph_risk_reports")
