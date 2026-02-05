"""add_citation_verifications_table

Revision ID: u3v4w5x6y7z8
Revises: t2u3v4w5x6y7
Create Date: 2026-02-02

Creates the citation_verifications table for persisting citation verification
results (Shepardização BR). References documents and users tables via ForeignKeys.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "u3v4w5x6y7z8"
down_revision: Union[str, None] = "t2u3v4w5x6y7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "citation_verifications",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "document_id",
            sa.String(),
            sa.ForeignKey("documents.id"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "user_id",
            sa.String(),
            sa.ForeignKey("users.id"),
            nullable=False,
            index=True,
        ),
        # Citação original
        sa.Column("citation_text", sa.Text(), nullable=False),
        sa.Column("citation_type", sa.String(), nullable=False),
        sa.Column("citation_normalized", sa.String(), nullable=True),
        # Resultado da verificação
        sa.Column(
            "status",
            sa.String(),
            nullable=False,
            server_default="nao_verificada",
        ),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("source_url", sa.String(), nullable=True),
        sa.Column(
            "verification_sources",
            sa.JSON(),
            nullable=False,
            server_default="{}",
        ),
        # Metadados
        sa.Column(
            "verified_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("extra", sa.JSON(), nullable=False, server_default="{}"),
        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # Índice composto para busca por usuário + status
    op.create_index(
        "ix_citation_verifications_user_status",
        "citation_verifications",
        ["user_id", "status"],
    )

    # Índice para busca por tipo de citação
    op.create_index(
        "ix_citation_verifications_citation_type",
        "citation_verifications",
        ["citation_type"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_citation_verifications_citation_type",
        table_name="citation_verifications",
    )
    op.drop_index(
        "ix_citation_verifications_user_status",
        table_name="citation_verifications",
    )
    op.drop_table("citation_verifications")
