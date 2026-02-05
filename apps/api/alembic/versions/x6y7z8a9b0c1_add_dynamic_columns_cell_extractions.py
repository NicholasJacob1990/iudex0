"""add_dynamic_columns_and_cell_extractions_tables

Revision ID: x6y7z8a9b0c1
Revises: w5x6y7z8a9b0
Create Date: 2026-02-03

Creates tables for:
1. dynamic_columns - User-created columns via natural language prompts
2. cell_extractions - Individual cell values with confidence and verification

These enable Harvey AI-style Review Tables with:
- Column Builder: Create columns via prompts
- Cell-level verification (verified/rejected/corrected)
- Confidence scores for each extraction
- Source traceability back to document snippets
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "x6y7z8a9b0c1"
down_revision: Union[str, None] = "w5x6y7z8a9b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # Create enums for PostgreSQL
    if is_postgres:
        op.execute("""
            DO $$ BEGIN
                CREATE TYPE extractiontype AS ENUM (
                    'text', 'boolean', 'number', 'date', 'currency',
                    'enum', 'list', 'verbatim', 'risk_rating', 'compliance_check'
                );
            EXCEPTION WHEN duplicate_object THEN null;
            END $$;
        """)
        op.execute("""
            DO $$ BEGIN
                CREATE TYPE verificationstatus AS ENUM (
                    'pending', 'verified', 'rejected', 'corrected'
                );
            EXCEPTION WHEN duplicate_object THEN null;
            END $$;
        """)

    # -------------------------------------------------------------------------
    # dynamic_columns table
    # -------------------------------------------------------------------------
    op.create_table(
        "dynamic_columns",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "review_table_id",
            sa.String(),
            sa.ForeignKey("review_tables.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column(
            "extraction_type",
            sa.Enum(
                "text", "boolean", "number", "date", "currency",
                "enum", "list", "verbatim", "risk_rating", "compliance_check",
                name="extractiontype",
                create_type=False,
            ) if is_postgres else sa.String(30),
            nullable=False,
            server_default="text",
        ),
        sa.Column("enum_options", sa.JSON(), nullable=True),
        sa.Column("extraction_instructions", sa.Text(), nullable=True),
        sa.Column("order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column(
            "created_by",
            sa.String(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
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

    op.create_index(
        "ix_dynamic_columns_review_table",
        "dynamic_columns",
        ["review_table_id"],
    )
    op.create_index(
        "ix_dynamic_columns_active",
        "dynamic_columns",
        ["review_table_id", "is_active"],
    )
    op.create_index(
        "ix_dynamic_columns_order",
        "dynamic_columns",
        ["review_table_id", "order"],
    )

    # -------------------------------------------------------------------------
    # cell_extractions table
    # -------------------------------------------------------------------------
    op.create_table(
        "cell_extractions",
        sa.Column("id", sa.String(), primary_key=True),
        # References
        sa.Column(
            "dynamic_column_id",
            sa.String(),
            sa.ForeignKey("dynamic_columns.id", ondelete="CASCADE"),
            nullable=True,  # Pode ser null para colunas de template
        ),
        sa.Column(
            "document_id",
            sa.String(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "review_table_id",
            sa.String(),
            sa.ForeignKey("review_tables.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Nome da coluna (para colunas de template, nao dinamicas)
        sa.Column("column_name", sa.String(255), nullable=True),
        # Valores extraidos
        sa.Column("extracted_value", sa.Text(), nullable=False),
        sa.Column("raw_value", sa.Text(), nullable=True),
        # Confianca e verificacao
        sa.Column(
            "confidence",
            sa.Float(),
            nullable=False,
            server_default="0.5",
        ),
        sa.Column(
            "verification_status",
            sa.Enum(
                "pending", "verified", "rejected", "corrected",
                name="verificationstatus",
                create_type=False,
            ) if is_postgres else sa.String(20),
            nullable=False,
            server_default="pending",
        ),
        # Fonte/proveniencia
        sa.Column("source_snippet", sa.Text(), nullable=True),
        sa.Column("source_page", sa.Integer(), nullable=True),
        sa.Column("source_char_start", sa.Integer(), nullable=True),
        sa.Column("source_char_end", sa.Integer(), nullable=True),
        # Verificacao humana
        sa.Column(
            "verified_by",
            sa.String(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("verified_at", sa.DateTime(), nullable=True),
        sa.Column("verification_note", sa.Text(), nullable=True),
        # Correcao manual
        sa.Column("corrected_value", sa.Text(), nullable=True),
        sa.Column("correction_note", sa.Text(), nullable=True),
        # Metadata de extracao
        sa.Column("extraction_model", sa.String(100), nullable=True),
        sa.Column("extraction_reasoning", sa.Text(), nullable=True),
        # Timestamps
        sa.Column(
            "extracted_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
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

    # Indices
    op.create_index(
        "ix_cell_extractions_column_doc",
        "cell_extractions",
        ["dynamic_column_id", "document_id"],
        unique=True,
    )
    op.create_index(
        "ix_cell_extractions_review_table",
        "cell_extractions",
        ["review_table_id"],
    )
    op.create_index(
        "ix_cell_extractions_document",
        "cell_extractions",
        ["document_id"],
    )
    op.create_index(
        "ix_cell_extractions_verification",
        "cell_extractions",
        ["review_table_id", "verification_status"],
    )
    op.create_index(
        "ix_cell_extractions_confidence",
        "cell_extractions",
        ["review_table_id", "confidence"],
    )
    # Indice para colunas de template (por nome)
    op.create_index(
        "ix_cell_extractions_column_name",
        "cell_extractions",
        ["review_table_id", "document_id", "column_name"],
    )


def downgrade() -> None:
    # Drop cell_extractions
    op.drop_index("ix_cell_extractions_column_name", table_name="cell_extractions")
    op.drop_index("ix_cell_extractions_confidence", table_name="cell_extractions")
    op.drop_index("ix_cell_extractions_verification", table_name="cell_extractions")
    op.drop_index("ix_cell_extractions_document", table_name="cell_extractions")
    op.drop_index("ix_cell_extractions_review_table", table_name="cell_extractions")
    op.drop_index("ix_cell_extractions_column_doc", table_name="cell_extractions")
    op.drop_table("cell_extractions")

    # Drop dynamic_columns
    op.drop_index("ix_dynamic_columns_order", table_name="dynamic_columns")
    op.drop_index("ix_dynamic_columns_active", table_name="dynamic_columns")
    op.drop_index("ix_dynamic_columns_review_table", table_name="dynamic_columns")
    op.drop_table("dynamic_columns")

    # Drop enums (PostgreSQL only)
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP TYPE IF EXISTS verificationstatus")
        op.execute("DROP TYPE IF EXISTS extractiontype")
