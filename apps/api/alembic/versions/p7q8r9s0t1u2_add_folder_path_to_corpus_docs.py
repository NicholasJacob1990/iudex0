"""Add folder_path to corpus_project_documents

Revision ID: p7q8r9s0t1u2
Revises: p6q7r8s9t0u1
Create Date: 2026-02-02
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "p7q8r9s0t1u2"
down_revision: Union[str, None] = "p6q7r8s9t0u1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "corpus_project_documents",
        sa.Column("folder_path", sa.String(1024), nullable=True),
    )
    op.create_index(
        "ix_corpus_project_docs_folder",
        "corpus_project_documents",
        ["project_id", "folder_path"],
    )


def downgrade() -> None:
    op.drop_index("ix_corpus_project_docs_folder", table_name="corpus_project_documents")
    op.drop_column("corpus_project_documents", "folder_path")
