"""add_document_case_rag_fields

Revision ID: e5b6c7d8f9a0
Revises: d3a4f8c9e2b1
Create Date: 2026-01-25 12:00:00

Adds:
- case_id column to documents table (FK to cases)
- RAG ingestion tracking fields: rag_ingested, rag_ingested_at, rag_scope
- Graph ingestion tracking fields: graph_ingested, graph_ingested_at
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e5b6c7d8f9a0"
down_revision: Union[str, None] = "d3a4f8c9e2b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Get existing columns in documents table
    existing_columns = [c["name"] for c in inspector.get_columns("documents")]

    # Add case_id column if not exists
    if "case_id" not in existing_columns:
        op.add_column(
            "documents",
            sa.Column("case_id", sa.String(), sa.ForeignKey("cases.id"), nullable=True)
        )
        op.create_index("ix_documents_case_id", "documents", ["case_id"])

    # Add RAG ingestion tracking fields
    if "rag_ingested" not in existing_columns:
        op.add_column(
            "documents",
            sa.Column("rag_ingested", sa.Boolean(), nullable=False, server_default="false")
        )

    if "rag_ingested_at" not in existing_columns:
        op.add_column(
            "documents",
            sa.Column("rag_ingested_at", sa.DateTime(), nullable=True)
        )

    if "rag_scope" not in existing_columns:
        op.add_column(
            "documents",
            sa.Column("rag_scope", sa.String(), nullable=True)
        )

    # Add Graph ingestion tracking fields
    if "graph_ingested" not in existing_columns:
        op.add_column(
            "documents",
            sa.Column("graph_ingested", sa.Boolean(), nullable=False, server_default="false")
        )

    if "graph_ingested_at" not in existing_columns:
        op.add_column(
            "documents",
            sa.Column("graph_ingested_at", sa.DateTime(), nullable=True)
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = [c["name"] for c in inspector.get_columns("documents")]

    # Remove columns in reverse order
    if "graph_ingested_at" in existing_columns:
        op.drop_column("documents", "graph_ingested_at")

    if "graph_ingested" in existing_columns:
        op.drop_column("documents", "graph_ingested")

    if "rag_scope" in existing_columns:
        op.drop_column("documents", "rag_scope")

    if "rag_ingested_at" in existing_columns:
        op.drop_column("documents", "rag_ingested_at")

    if "rag_ingested" in existing_columns:
        op.drop_column("documents", "rag_ingested")

    # Drop index and column
    try:
        op.drop_index("ix_documents_case_id", "documents")
    except Exception:
        pass

    if "case_id" in existing_columns:
        op.drop_column("documents", "case_id")
