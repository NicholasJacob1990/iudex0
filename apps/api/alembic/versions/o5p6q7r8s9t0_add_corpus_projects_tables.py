"""Add corpus_projects, corpus_project_documents and corpus_project_shares tables

Revision ID: o5p6q7r8s9t0
Revises: n4o5p6q7r8s9
Create Date: 2026-02-02
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "o5p6q7r8s9t0"
down_revision: Union[str, None] = "n5o6p7q8r9s0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # CorpusProject
    op.create_table(
        "corpus_projects",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("owner_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("organization_id", sa.String(), sa.ForeignKey("organizations.id"), nullable=True),
        sa.Column(
            "is_knowledge_base", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "scope",
            sa.Enum("personal", "organization", name="projectscope"),
            nullable=False,
            server_default="personal",
        ),
        sa.Column("collection_name", sa.String(255), nullable=False, unique=True),
        sa.Column("max_documents", sa.Integer(), nullable=False, server_default="10000"),
        sa.Column("retention_days", sa.Integer(), nullable=True),
        sa.Column("document_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("storage_size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("last_indexed_at", sa.DateTime(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_corpus_projects_owner_id", "corpus_projects", ["owner_id"])
    op.create_index("ix_corpus_projects_organization_id", "corpus_projects", ["organization_id"])
    op.create_index("ix_corpus_projects_owner_active", "corpus_projects", ["owner_id", "is_active"])
    op.create_index("ix_corpus_projects_org_active", "corpus_projects", ["organization_id", "is_active"])
    op.create_index("ix_corpus_projects_kb", "corpus_projects", ["is_knowledge_base"])
    op.create_index("ix_corpus_projects_scope", "corpus_projects", ["scope"])

    # CorpusProjectDocument
    op.create_table(
        "corpus_project_documents",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(),
            sa.ForeignKey("corpus_projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("document_id", sa.String(), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "processing", "ingested", "failed", name="projectdocumentstatus"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("ingested_at", sa.DateTime(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_corpus_project_docs_project_id", "corpus_project_documents", ["project_id"])
    op.create_index("ix_corpus_project_docs_document_id", "corpus_project_documents", ["document_id"])
    op.create_index(
        "ix_corpus_project_docs_project_doc",
        "corpus_project_documents",
        ["project_id", "document_id"],
        unique=True,
    )
    op.create_index(
        "ix_corpus_project_docs_status",
        "corpus_project_documents",
        ["project_id", "status"],
    )

    # CorpusProjectShare
    op.create_table(
        "corpus_project_shares",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(),
            sa.ForeignKey("corpus_projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("shared_with_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column(
            "shared_with_org_id",
            sa.String(),
            sa.ForeignKey("organizations.id"),
            nullable=True,
        ),
        sa.Column(
            "permission",
            sa.Enum("view", "edit", "admin", name="projectsharepermission"),
            nullable=False,
            server_default="view",
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_corpus_project_shares_project_id", "corpus_project_shares", ["project_id"])
    op.create_index(
        "ix_corpus_project_shares_user_id", "corpus_project_shares", ["shared_with_user_id"]
    )
    op.create_index(
        "ix_corpus_project_shares_org_id", "corpus_project_shares", ["shared_with_org_id"]
    )
    op.create_index(
        "ix_corpus_project_shares_lookup",
        "corpus_project_shares",
        ["project_id", "shared_with_user_id"],
    )


def downgrade() -> None:
    op.drop_table("corpus_project_shares")
    op.drop_table("corpus_project_documents")
    op.drop_table("corpus_projects")

    # Drop enums
    sa.Enum(name="projectscope").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="projectdocumentstatus").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="projectsharepermission").drop(op.get_bind(), checkfirst=True)
