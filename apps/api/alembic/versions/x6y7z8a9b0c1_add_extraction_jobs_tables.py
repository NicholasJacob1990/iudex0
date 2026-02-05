"""add_extraction_jobs_tables

Revision ID: x6y7z8a9b0c1
Revises: w5x6y7z8a9b0
Create Date: 2026-02-03

Creates tables for scalable batch extraction processing:
- extraction_jobs: Main job queue for batch extractions
- extraction_job_documents: Per-document status tracking

Supports processing 2000+ documents with:
- Async job queue with progress tracking
- Pause/resume capability
- Per-document retry logic
- Incremental results storage
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "x6y7z8a9b0c1"
down_revision: Union[str, None] = "w5x6y7z8a9b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # Create enum types for PostgreSQL
    if is_postgres:
        op.execute("""
            CREATE TYPE extractionjobstatus AS ENUM (
                'pending', 'running', 'paused', 'completed', 'failed', 'cancelled'
            )
        """)
        op.execute("""
            CREATE TYPE extractionjobtype AS ENUM (
                'full_extraction', 'column_extraction', 'reprocess', 'incremental'
            )
        """)
        op.execute("""
            CREATE TYPE documentextractionstatus AS ENUM (
                'pending', 'queued', 'processing', 'completed', 'failed', 'skipped'
            )
        """)

    # Create extraction_jobs table
    op.create_table(
        "extraction_jobs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "review_table_id",
            sa.String(),
            sa.ForeignKey("review_tables.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("column_id", sa.String(), nullable=True),
        sa.Column(
            "job_type",
            sa.Enum(
                "full_extraction", "column_extraction", "reprocess", "incremental",
                name="extractionjobtype",
                create_type=False,
            ) if is_postgres else sa.String(30),
            nullable=False,
            default="full_extraction",
        ),
        sa.Column(
            "status",
            sa.Enum(
                "pending", "running", "paused", "completed", "failed", "cancelled",
                name="extractionjobstatus",
                create_type=False,
            ) if is_postgres else sa.String(20),
            nullable=False,
            default="pending",
            index=True,
        ),
        # Progress tracking
        sa.Column("total_documents", sa.Integer(), nullable=False, default=0),
        sa.Column("processed_documents", sa.Integer(), nullable=False, default=0),
        sa.Column("failed_documents", sa.Integer(), nullable=False, default=0),
        sa.Column("skipped_documents", sa.Integer(), nullable=False, default=0),
        sa.Column("progress_percent", sa.Float(), nullable=False, default=0.0),
        sa.Column("documents_per_second", sa.Float(), nullable=False, default=0.0),
        # Timing
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("paused_at", sa.DateTime(), nullable=True),
        # Error handling
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("last_error_at", sa.DateTime(), nullable=True),
        # Configuration
        sa.Column("max_concurrent", sa.Integer(), nullable=False, default=10),
        sa.Column("batch_size", sa.Integer(), nullable=False, default=50),
        sa.Column("max_retries", sa.Integer(), nullable=False, default=3),
        # Ownership
        sa.Column(
            "created_by",
            sa.String(),
            sa.ForeignKey("users.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "organization_id",
            sa.String(),
            sa.ForeignKey("organizations.id"),
            nullable=True,
            index=True,
        ),
        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )

    # Create indexes for extraction_jobs
    op.create_index(
        "ix_extraction_jobs_review_table",
        "extraction_jobs",
        ["review_table_id"],
    )
    op.create_index(
        "ix_extraction_jobs_user_status",
        "extraction_jobs",
        ["created_by", "status"],
    )
    op.create_index(
        "ix_extraction_jobs_created",
        "extraction_jobs",
        ["created_at"],
    )

    # Create extraction_job_documents table
    op.create_table(
        "extraction_job_documents",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "job_id",
            sa.String(),
            sa.ForeignKey("extraction_jobs.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "document_id",
            sa.String(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "pending", "queued", "processing", "completed", "failed", "skipped",
                name="documentextractionstatus",
                create_type=False,
            ) if is_postgres else sa.String(20),
            nullable=False,
            default="pending",
            index=True,
        ),
        # Error tracking
        sa.Column("error_message", sa.Text(), nullable=True),
        # Retry tracking
        sa.Column("retry_count", sa.Integer(), nullable=False, default=0),
        sa.Column("last_retry_at", sa.DateTime(), nullable=True),
        sa.Column("next_retry_at", sa.DateTime(), nullable=True),
        # Timing
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("processed_at", sa.DateTime(), nullable=True),
        sa.Column("processing_time_ms", sa.Integer(), nullable=True),
        # Queue position
        sa.Column("queue_position", sa.Integer(), nullable=False, default=0),
        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )

    # Create indexes for extraction_job_documents
    op.create_index(
        "ix_extraction_job_documents_job_status",
        "extraction_job_documents",
        ["job_id", "status"],
    )
    op.create_index(
        "ix_extraction_job_documents_queue",
        "extraction_job_documents",
        ["job_id", "queue_position"],
    )
    # Unique constraint: one entry per document per job
    op.create_unique_constraint(
        "uix_extraction_job_document",
        "extraction_job_documents",
        ["job_id", "document_id"],
    )


def downgrade() -> None:
    # Drop extraction_job_documents table
    op.drop_constraint(
        "uix_extraction_job_document",
        "extraction_job_documents",
        type_="unique",
    )
    op.drop_index(
        "ix_extraction_job_documents_queue",
        table_name="extraction_job_documents",
    )
    op.drop_index(
        "ix_extraction_job_documents_job_status",
        table_name="extraction_job_documents",
    )
    op.drop_table("extraction_job_documents")

    # Drop extraction_jobs table
    op.drop_index("ix_extraction_jobs_created", table_name="extraction_jobs")
    op.drop_index("ix_extraction_jobs_user_status", table_name="extraction_jobs")
    op.drop_index("ix_extraction_jobs_review_table", table_name="extraction_jobs")
    op.drop_table("extraction_jobs")

    # Drop enum types (PostgreSQL only)
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP TYPE IF EXISTS documentextractionstatus")
        op.execute("DROP TYPE IF EXISTS extractionjobtype")
        op.execute("DROP TYPE IF EXISTS extractionjobstatus")
