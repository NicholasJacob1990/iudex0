"""
ExtractionJob Models — Job queue for scalable batch extraction of Review Tables.

Supports processing 2000+ documents with:
- Async job queue with progress tracking
- Incremental results
- Pause/resume capability
- Per-document status tracking
- Retry logic with exponential backoff
"""

import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    DateTime,
    Enum as SQLEnum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.time_utils import utcnow


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ExtractionJobStatus(str, enum.Enum):
    """Status of the extraction job."""
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ExtractionJobType(str, enum.Enum):
    """Type of extraction job."""
    FULL_EXTRACTION = "full_extraction"  # Extract all columns for all documents
    COLUMN_EXTRACTION = "column_extraction"  # Extract specific column(s)
    REPROCESS = "reprocess"  # Reprocess failed/specific documents
    INCREMENTAL = "incremental"  # Add new documents to existing table


class DocumentExtractionStatus(str, enum.Enum):
    """Status of individual document extraction."""
    PENDING = "pending"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


# ---------------------------------------------------------------------------
# ExtractionJob
# ---------------------------------------------------------------------------


class ExtractionJob(Base):
    """
    Represents a batch extraction job for a Review Table.

    Handles processing of 2000+ documents efficiently with:
    - Progress tracking
    - Pause/resume capability
    - Error handling with retries
    - Incremental result storage
    """
    __tablename__ = "extraction_jobs"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )

    # Reference to review table
    review_table_id: Mapped[str] = mapped_column(
        String, ForeignKey("review_tables.id", ondelete="CASCADE"),
        nullable=False, index=True
    )

    # Optional: specific column to extract (for column_extraction type)
    column_id: Mapped[Optional[str]] = mapped_column(
        String, nullable=True,
        doc="Column ID/name if extracting for specific column"
    )

    # Job type
    job_type: Mapped[str] = mapped_column(
        SQLEnum(ExtractionJobType),
        default=ExtractionJobType.FULL_EXTRACTION.value,
        nullable=False,
        doc="Type: full_extraction, column_extraction, reprocess, incremental"
    )

    # Status
    status: Mapped[str] = mapped_column(
        SQLEnum(ExtractionJobStatus),
        default=ExtractionJobStatus.PENDING.value,
        nullable=False,
        doc="Job status: pending, running, paused, completed, failed, cancelled"
    )

    # Progress tracking
    total_documents: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False,
        doc="Total number of documents to process"
    )
    processed_documents: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False,
        doc="Number of documents processed so far"
    )
    failed_documents: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False,
        doc="Number of documents that failed processing"
    )
    skipped_documents: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False,
        doc="Number of documents skipped (already processed, etc.)"
    )
    progress_percent: Mapped[float] = mapped_column(
        Float, default=0.0, nullable=False,
        doc="Progress percentage (0.0 to 100.0)"
    )

    # Rate tracking for ETA calculation
    documents_per_second: Mapped[float] = mapped_column(
        Float, default=0.0, nullable=False,
        doc="Current processing rate (docs/second)"
    )

    # Timing
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True,
        doc="When the job started processing"
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True,
        doc="When the job completed (success or failure)"
    )
    paused_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True,
        doc="When the job was paused"
    )

    # Error handling
    error_message: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
        doc="Error message if job failed"
    )
    last_error_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True,
        doc="When the last error occurred"
    )

    # Configuration
    max_concurrent: Mapped[int] = mapped_column(
        Integer, default=10, nullable=False,
        doc="Maximum concurrent document extractions"
    )
    batch_size: Mapped[int] = mapped_column(
        Integer, default=50, nullable=False,
        doc="Number of documents per batch commit"
    )
    max_retries: Mapped[int] = mapped_column(
        Integer, default=3, nullable=False,
        doc="Maximum retries per document"
    )

    # Ownership
    created_by: Mapped[str] = mapped_column(
        String, ForeignKey("users.id"), nullable=False, index=True
    )
    organization_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("organizations.id"), nullable=True, index=True
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    # Relationships
    review_table = relationship("ReviewTable", backref="extraction_jobs")
    creator = relationship("User", backref="extraction_jobs", foreign_keys=[created_by])
    organization = relationship("Organization", backref="extraction_jobs")
    job_documents = relationship(
        "ExtractionJobDocument",
        back_populates="job",
        cascade="all, delete-orphan",
        lazy="dynamic"
    )

    __table_args__ = (
        Index("ix_extraction_jobs_review_table", "review_table_id"),
        Index("ix_extraction_jobs_status", "status"),
        Index("ix_extraction_jobs_user_status", "created_by", "status"),
        Index("ix_extraction_jobs_created", "created_at"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "review_table_id": self.review_table_id,
            "column_id": self.column_id,
            "job_type": self.job_type,
            "status": self.status,
            "total_documents": self.total_documents,
            "processed_documents": self.processed_documents,
            "failed_documents": self.failed_documents,
            "skipped_documents": self.skipped_documents,
            "progress_percent": self.progress_percent,
            "documents_per_second": self.documents_per_second,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "paused_at": self.paused_at.isoformat() if self.paused_at else None,
            "error_message": self.error_message,
            "max_concurrent": self.max_concurrent,
            "batch_size": self.batch_size,
            "max_retries": self.max_retries,
            "created_by": self.created_by,
            "organization_id": self.organization_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @property
    def can_resume(self) -> bool:
        """Check if job can be resumed."""
        return self.status in (
            ExtractionJobStatus.PAUSED.value,
            ExtractionJobStatus.FAILED.value,
        )

    @property
    def is_active(self) -> bool:
        """Check if job is currently active."""
        return self.status in (
            ExtractionJobStatus.PENDING.value,
            ExtractionJobStatus.RUNNING.value,
        )

    @property
    def estimated_time_remaining(self) -> Optional[int]:
        """Estimate remaining time in seconds."""
        if self.documents_per_second <= 0:
            return None
        remaining_docs = self.total_documents - self.processed_documents - self.failed_documents
        if remaining_docs <= 0:
            return 0
        return int(remaining_docs / self.documents_per_second)


# ---------------------------------------------------------------------------
# ExtractionJobDocument
# ---------------------------------------------------------------------------


class ExtractionJobDocument(Base):
    """
    Tracks the status of each document within an extraction job.

    Enables:
    - Per-document progress tracking
    - Retry logic with backoff
    - Resume from specific documents
    - Detailed error tracking
    """
    __tablename__ = "extraction_job_documents"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )

    # Reference to job
    job_id: Mapped[str] = mapped_column(
        String, ForeignKey("extraction_jobs.id", ondelete="CASCADE"),
        nullable=False, index=True
    )

    # Reference to document
    document_id: Mapped[str] = mapped_column(
        String, ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False, index=True
    )

    # Status
    status: Mapped[str] = mapped_column(
        SQLEnum(DocumentExtractionStatus),
        default=DocumentExtractionStatus.PENDING.value,
        nullable=False
    )

    # Error tracking
    error_message: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
        doc="Error message if extraction failed"
    )

    # Retry tracking
    retry_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False,
        doc="Number of retry attempts"
    )
    last_retry_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True,
        doc="When the last retry was attempted"
    )
    next_retry_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True,
        doc="When to attempt next retry (for exponential backoff)"
    )

    # Timing
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True,
        doc="When extraction started for this document"
    )
    processed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True,
        doc="When extraction completed for this document"
    )

    # Processing metadata
    processing_time_ms: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True,
        doc="Time taken to process this document in milliseconds"
    )

    # Position in queue (for ordering)
    queue_position: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False,
        doc="Position in the processing queue"
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    # Relationships
    job = relationship("ExtractionJob", back_populates="job_documents")
    document = relationship("Document", backref="extraction_job_documents")

    __table_args__ = (
        Index("ix_extraction_job_documents_job", "job_id"),
        Index("ix_extraction_job_documents_status", "status"),
        Index("ix_extraction_job_documents_job_status", "job_id", "status"),
        Index("ix_extraction_job_documents_queue", "job_id", "queue_position"),
        # Unique constraint: one entry per document per job
        Index("uix_extraction_job_document", "job_id", "document_id", unique=True),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "job_id": self.job_id,
            "document_id": self.document_id,
            "status": self.status,
            "error_message": self.error_message,
            "retry_count": self.retry_count,
            "last_retry_at": self.last_retry_at.isoformat() if self.last_retry_at else None,
            "next_retry_at": self.next_retry_at.isoformat() if self.next_retry_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "processed_at": self.processed_at.isoformat() if self.processed_at else None,
            "processing_time_ms": self.processing_time_ms,
            "queue_position": self.queue_position,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @property
    def can_retry(self) -> bool:
        """Check if document can be retried."""
        from app.models.extraction_job import ExtractionJobStatus
        # Get max_retries from parent job
        max_retries = 3  # Default, actual check happens in service
        return (
            self.status == DocumentExtractionStatus.FAILED.value and
            self.retry_count < max_retries
        )
