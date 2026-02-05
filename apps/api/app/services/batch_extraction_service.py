"""
BatchExtractionService — Scalable batch processing for Review Tables.

Designed to handle 2000+ documents efficiently with:
- Async job queue with progress tracking
- Semaphore-based concurrency control
- Incremental result storage
- Pause/resume capability
- Exponential backoff retry logic
- Real-time progress updates via SSE
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time_utils import utcnow
from app.models.document import Document
from app.models.extraction_job import (
    DocumentExtractionStatus,
    ExtractionJob,
    ExtractionJobDocument,
    ExtractionJobStatus,
    ExtractionJobType,
)
from app.models.review_table import (
    ReviewTable,
    ReviewTableStatus,
    ReviewTableTemplate,
)

logger = logging.getLogger("BatchExtractionService")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_MAX_CONCURRENT = 10  # Process 10 docs in parallel
DEFAULT_BATCH_SIZE = 50  # Commit every 50 docs
DEFAULT_MAX_RETRIES = 3
AI_TIMEOUT = 90
MAX_DOC_TEXT_LENGTH = 30000

# Backoff configuration (in seconds)
RETRY_BASE_DELAY = 5
RETRY_MAX_DELAY = 300  # 5 minutes max


# ---------------------------------------------------------------------------
# BatchExtractionService
# ---------------------------------------------------------------------------


class BatchExtractionService:
    """
    Service for scalable batch processing of Review Table extractions.

    Supports:
    - Processing 2000+ documents efficiently
    - Concurrent extraction with semaphore control
    - Progress tracking with ETA calculation
    - Pause/resume functionality
    - Per-document retry with exponential backoff
    - Incremental result storage
    """

    def __init__(
        self,
        max_concurrent: int = DEFAULT_MAX_CONCURRENT,
        batch_size: int = DEFAULT_BATCH_SIZE,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ):
        self.max_concurrent = max_concurrent
        self.batch_size = batch_size
        self.max_retries = max_retries

        # Active job tracking (for pause/cancel)
        self._active_jobs: Dict[str, bool] = {}  # job_id -> should_continue
        self._job_semaphores: Dict[str, asyncio.Semaphore] = {}

    # -----------------------------------------------------------------------
    # Job Creation
    # -----------------------------------------------------------------------

    async def create_extraction_job(
        self,
        review_table_id: str,
        user_id: str,
        db: AsyncSession,
        column_id: Optional[str] = None,
        job_type: ExtractionJobType = ExtractionJobType.FULL_EXTRACTION,
        document_ids: Optional[List[str]] = None,
        max_concurrent: Optional[int] = None,
        batch_size: Optional[int] = None,
    ) -> ExtractionJob:
        """
        Create a new extraction job and queue all documents.

        Args:
            review_table_id: ID of the review table to process.
            user_id: ID of the user creating the job.
            db: Database session.
            column_id: Optional column ID for column-specific extraction.
            job_type: Type of extraction job.
            document_ids: Optional list of specific documents to process.
            max_concurrent: Override default max concurrent extractions.
            batch_size: Override default batch size.

        Returns:
            The created ExtractionJob.
        """
        # Validate review table exists
        review_table = await db.get(ReviewTable, review_table_id)
        if not review_table:
            raise ValueError(f"Review table {review_table_id} not found")

        # Check for existing active jobs
        existing_job_stmt = select(ExtractionJob).where(
            and_(
                ExtractionJob.review_table_id == review_table_id,
                ExtractionJob.status.in_([
                    ExtractionJobStatus.PENDING.value,
                    ExtractionJobStatus.RUNNING.value,
                ]),
            )
        )
        existing_result = await db.execute(existing_job_stmt)
        existing_job = existing_result.scalar_one_or_none()

        if existing_job:
            raise ValueError(
                f"An active extraction job already exists for this table. "
                f"Job ID: {existing_job.id}, Status: {existing_job.status}"
            )

        # Determine documents to process
        target_doc_ids = document_ids or review_table.document_ids or []
        if not target_doc_ids:
            raise ValueError("No documents to process")

        # Create job
        job = ExtractionJob(
            id=str(uuid.uuid4()),
            review_table_id=review_table_id,
            column_id=column_id,
            job_type=job_type.value if isinstance(job_type, ExtractionJobType) else job_type,
            status=ExtractionJobStatus.PENDING.value,
            total_documents=len(target_doc_ids),
            processed_documents=0,
            failed_documents=0,
            skipped_documents=0,
            progress_percent=0.0,
            max_concurrent=max_concurrent or self.max_concurrent,
            batch_size=batch_size or self.batch_size,
            max_retries=self.max_retries,
            created_by=user_id,
            organization_id=review_table.organization_id,
        )
        db.add(job)
        await db.flush()

        # Queue all documents
        for position, doc_id in enumerate(target_doc_ids):
            job_doc = ExtractionJobDocument(
                id=str(uuid.uuid4()),
                job_id=job.id,
                document_id=doc_id,
                status=DocumentExtractionStatus.PENDING.value,
                queue_position=position,
            )
            db.add(job_doc)

        await db.commit()
        await db.refresh(job)

        logger.info(
            "Created extraction job: id=%s, table=%s, docs=%d",
            job.id, review_table_id, len(target_doc_ids),
        )

        return job

    # -----------------------------------------------------------------------
    # Job Processing
    # -----------------------------------------------------------------------

    async def process_job(
        self,
        job_id: str,
        db: AsyncSession,
    ) -> ExtractionJob:
        """
        Main processing loop for an extraction job.

        Uses semaphore for concurrency control, updates progress incrementally,
        and handles failures gracefully.

        Args:
            job_id: ID of the job to process.
            db: Database session.

        Returns:
            The updated ExtractionJob.
        """
        job = await db.get(ExtractionJob, job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        if job.status not in (
            ExtractionJobStatus.PENDING.value,
            ExtractionJobStatus.PAUSED.value,
        ):
            raise ValueError(f"Job {job_id} is not in a processable state: {job.status}")

        # Load template for column definitions
        review_table = await db.get(ReviewTable, job.review_table_id)
        if not review_table:
            raise ValueError(f"Review table {job.review_table_id} not found")

        template = await db.get(ReviewTableTemplate, review_table.template_id)
        if not template:
            raise ValueError(f"Template {review_table.template_id} not found")

        columns = template.columns or []
        if not columns:
            raise ValueError("Template has no columns defined")

        # Mark job as running
        job.status = ExtractionJobStatus.RUNNING.value
        job.started_at = job.started_at or utcnow()
        job.paused_at = None
        job.updated_at = utcnow()
        await db.commit()

        # Update review table status
        review_table.status = ReviewTableStatus.PROCESSING.value
        review_table.updated_at = utcnow()
        await db.commit()

        # Initialize active job tracking
        self._active_jobs[job_id] = True
        self._job_semaphores[job_id] = asyncio.Semaphore(job.max_concurrent)

        try:
            await self._process_documents(job, review_table, columns, db)
        except Exception as e:
            logger.error("Job %s failed: %s", job_id, e, exc_info=True)
            job.status = ExtractionJobStatus.FAILED.value
            job.error_message = str(e)
            job.completed_at = utcnow()
            job.updated_at = utcnow()
            review_table.status = ReviewTableStatus.FAILED.value
            review_table.error_message = str(e)
            review_table.updated_at = utcnow()
            await db.commit()
        finally:
            # Cleanup
            self._active_jobs.pop(job_id, None)
            self._job_semaphores.pop(job_id, None)

        await db.refresh(job)
        return job

    async def _process_documents(
        self,
        job: ExtractionJob,
        review_table: ReviewTable,
        columns: List[Dict[str, Any]],
        db: AsyncSession,
    ) -> None:
        """Process all pending documents for a job."""
        from app.services.review_table_service import review_table_service

        semaphore = self._job_semaphores.get(job.id)
        if not semaphore:
            semaphore = asyncio.Semaphore(job.max_concurrent)

        start_time = time.time()
        processed_count = 0
        batch_results: List[Dict[str, Any]] = list(review_table.results or [])

        # Keep existing results indexed by document_id
        existing_results = {r["document_id"]: r for r in batch_results}

        while True:
            # Check if job should continue
            if not self._active_jobs.get(job.id, True):
                logger.info("Job %s was paused/cancelled", job.id)
                break

            # Fetch next batch of pending documents
            pending_docs_stmt = (
                select(ExtractionJobDocument)
                .where(
                    and_(
                        ExtractionJobDocument.job_id == job.id,
                        ExtractionJobDocument.status.in_([
                            DocumentExtractionStatus.PENDING.value,
                            DocumentExtractionStatus.QUEUED.value,
                        ]),
                    )
                )
                .order_by(ExtractionJobDocument.queue_position)
                .limit(job.batch_size)
            )
            result = await db.execute(pending_docs_stmt)
            pending_docs = result.scalars().all()

            if not pending_docs:
                # Check for retryable documents
                retryable_stmt = (
                    select(ExtractionJobDocument)
                    .where(
                        and_(
                            ExtractionJobDocument.job_id == job.id,
                            ExtractionJobDocument.status == DocumentExtractionStatus.FAILED.value,
                            ExtractionJobDocument.retry_count < job.max_retries,
                            ExtractionJobDocument.next_retry_at <= utcnow(),
                        )
                    )
                    .limit(job.batch_size)
                )
                retry_result = await db.execute(retryable_stmt)
                pending_docs = retry_result.scalars().all()

                if not pending_docs:
                    # All done
                    break

            # Process batch in parallel
            tasks = []
            for job_doc in pending_docs:
                task = self._process_single_document(
                    job_doc=job_doc,
                    columns=columns,
                    semaphore=semaphore,
                    db=db,
                )
                tasks.append(task)

            # Wait for batch to complete
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Process results
            for job_doc, result in zip(pending_docs, results):
                if isinstance(result, Exception):
                    logger.error(
                        "Document %s failed: %s",
                        job_doc.document_id, result
                    )
                    continue

                if result:
                    # Update or add to results
                    existing_results[job_doc.document_id] = result
                    processed_count += 1

            # Update job progress
            elapsed = time.time() - start_time
            job.processed_documents = processed_count
            job.documents_per_second = processed_count / elapsed if elapsed > 0 else 0
            job.progress_percent = (
                (processed_count / job.total_documents) * 100
                if job.total_documents > 0 else 0
            )

            # Count failed documents
            failed_count_stmt = select(func.count()).select_from(
                select(ExtractionJobDocument)
                .where(
                    and_(
                        ExtractionJobDocument.job_id == job.id,
                        ExtractionJobDocument.status == DocumentExtractionStatus.FAILED.value,
                        ExtractionJobDocument.retry_count >= job.max_retries,
                    )
                ).subquery()
            )
            failed_result = await db.execute(failed_count_stmt)
            job.failed_documents = failed_result.scalar() or 0

            job.updated_at = utcnow()

            # Update review table with incremental results
            review_table.results = list(existing_results.values())
            review_table.processed_documents = processed_count
            review_table.updated_at = utcnow()

            await db.commit()

            logger.info(
                "Job %s progress: %d/%d (%.1f%%), rate: %.2f docs/sec",
                job.id, processed_count, job.total_documents,
                job.progress_percent, job.documents_per_second,
            )

        # Finalize job
        if self._active_jobs.get(job.id, True):
            job.status = ExtractionJobStatus.COMPLETED.value
            job.completed_at = utcnow()
            review_table.status = ReviewTableStatus.COMPLETED.value
        else:
            job.status = ExtractionJobStatus.PAUSED.value
            job.paused_at = utcnow()

        job.updated_at = utcnow()
        review_table.updated_at = utcnow()
        await db.commit()

    async def _process_single_document(
        self,
        job_doc: ExtractionJobDocument,
        columns: List[Dict[str, Any]],
        semaphore: asyncio.Semaphore,
        db: AsyncSession,
    ) -> Optional[Dict[str, Any]]:
        """Process a single document extraction."""
        from app.services.review_table_service import (
            COLUMN_TYPE_DESCRIPTIONS,
            EXTRACTION_PROMPT,
            _call_ai,
            _safe_json_parse,
        )

        async with semaphore:
            # Mark as processing
            job_doc.status = DocumentExtractionStatus.PROCESSING.value
            job_doc.started_at = utcnow()
            job_doc.updated_at = utcnow()
            await db.commit()

            start_time = time.time()

            try:
                # Load document
                doc = await db.get(Document, job_doc.document_id)
                if not doc:
                    job_doc.status = DocumentExtractionStatus.FAILED.value
                    job_doc.error_message = "Document not found"
                    job_doc.processed_at = utcnow()
                    job_doc.updated_at = utcnow()
                    await db.commit()
                    return None

                doc_text = doc.extracted_text or doc.content or ""
                if not doc_text.strip():
                    job_doc.status = DocumentExtractionStatus.SKIPPED.value
                    job_doc.error_message = "Document has no text content"
                    job_doc.processed_at = utcnow()
                    job_doc.updated_at = utcnow()
                    await db.commit()
                    return {
                        "document_id": job_doc.document_id,
                        "document_name": getattr(doc, "name", job_doc.document_id),
                        "columns": {col["name"]: "Erro: sem texto extraido" for col in columns},
                    }

                doc_text_truncated = doc_text[:MAX_DOC_TEXT_LENGTH]
                doc_name = getattr(doc, "name", None) or getattr(doc, "title", None) or job_doc.document_id

                # Extract all columns in parallel
                row_data = await self._extract_row_with_retry(
                    doc_text=doc_text_truncated,
                    columns=columns,
                )

                # Simplify results
                simplified_columns = {}
                for col_name, col_result in row_data.items():
                    if isinstance(col_result, dict):
                        simplified_columns[col_name] = col_result.get("value", "Nao encontrado")
                    else:
                        simplified_columns[col_name] = str(col_result)

                # Mark as completed
                processing_time = int((time.time() - start_time) * 1000)
                job_doc.status = DocumentExtractionStatus.COMPLETED.value
                job_doc.processed_at = utcnow()
                job_doc.processing_time_ms = processing_time
                job_doc.error_message = None
                job_doc.updated_at = utcnow()
                await db.commit()

                return {
                    "document_id": job_doc.document_id,
                    "document_name": doc_name,
                    "columns": simplified_columns,
                }

            except Exception as e:
                logger.error(
                    "Error processing document %s: %s",
                    job_doc.document_id, e, exc_info=True
                )

                # Handle retry logic
                job_doc.retry_count += 1
                job_doc.last_retry_at = utcnow()
                job_doc.error_message = str(e)

                if job_doc.retry_count < self.max_retries:
                    # Calculate next retry with exponential backoff
                    delay = min(
                        RETRY_BASE_DELAY * (2 ** job_doc.retry_count),
                        RETRY_MAX_DELAY
                    )
                    job_doc.next_retry_at = utcnow() + timedelta(seconds=delay)
                    job_doc.status = DocumentExtractionStatus.FAILED.value
                else:
                    job_doc.status = DocumentExtractionStatus.FAILED.value

                job_doc.updated_at = utcnow()
                await db.commit()
                return None

    async def _extract_row_with_retry(
        self,
        doc_text: str,
        columns: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Extract all columns from a document with internal retry."""
        from app.services.review_table_service import (
            COLUMN_TYPE_DESCRIPTIONS,
            EXTRACTION_PROMPT,
            _call_ai,
            _safe_json_parse,
        )

        inner_semaphore = asyncio.Semaphore(5)  # Limit parallel column extractions

        async def extract_one(col: Dict[str, Any]) -> Tuple[str, Any]:
            async with inner_semaphore:
                col_name = col["name"]
                col_type = col.get("type", "text")
                extraction_prompt = col.get("extraction_prompt", f"Extraia: {col_name}")

                prompt = EXTRACTION_PROMPT.format(
                    document_text=doc_text,
                    extraction_prompt=extraction_prompt,
                    data_type=COLUMN_TYPE_DESCRIPTIONS.get(col_type, "Texto livre"),
                )

                response = await _call_ai(
                    prompt=prompt,
                    system_instruction=(
                        "Voce e um assistente juridico especializado em extracao "
                        "precisa de dados de documentos. Responda em JSON valido."
                    ),
                    temperature=0.1,
                )

                parsed = _safe_json_parse(response) if response else None

                if parsed and isinstance(parsed, dict):
                    return col_name, {
                        "value": parsed.get("value", "Nao encontrado"),
                        "confidence": min(max(float(parsed.get("confidence", 0.5)), 0.0), 1.0),
                        "source_excerpt": parsed.get("source_excerpt", ""),
                    }

                return col_name, {
                    "value": response.strip() if response else "Erro na extracao",
                    "confidence": 0.3,
                    "source_excerpt": "",
                }

        tasks = [extract_one(col) for col in columns]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        row: Dict[str, Any] = {}
        for result in results:
            if isinstance(result, Exception):
                logger.error("Column extraction error: %s", result)
                continue
            col_name, col_data = result
            row[col_name] = col_data

        return row

    # -----------------------------------------------------------------------
    # Job Control
    # -----------------------------------------------------------------------

    async def pause_job(self, job_id: str, db: AsyncSession) -> ExtractionJob:
        """Pause a running job."""
        job = await db.get(ExtractionJob, job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        if job.status != ExtractionJobStatus.RUNNING.value:
            raise ValueError(f"Can only pause running jobs. Current status: {job.status}")

        # Signal the job to stop
        self._active_jobs[job_id] = False

        # Update status (will be finalized by process loop)
        job.status = ExtractionJobStatus.PAUSED.value
        job.paused_at = utcnow()
        job.updated_at = utcnow()
        await db.commit()
        await db.refresh(job)

        logger.info("Paused job %s", job_id)
        return job

    async def resume_job(self, job_id: str, db: AsyncSession) -> ExtractionJob:
        """Resume a paused or failed job."""
        job = await db.get(ExtractionJob, job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        if not job.can_resume:
            raise ValueError(
                f"Cannot resume job with status: {job.status}. "
                f"Only paused or failed jobs can be resumed."
            )

        # Reset failed documents for retry
        if job.status == ExtractionJobStatus.FAILED.value:
            await db.execute(
                update(ExtractionJobDocument)
                .where(
                    and_(
                        ExtractionJobDocument.job_id == job_id,
                        ExtractionJobDocument.status == DocumentExtractionStatus.FAILED.value,
                        ExtractionJobDocument.retry_count < job.max_retries,
                    )
                )
                .values(
                    status=DocumentExtractionStatus.PENDING.value,
                    next_retry_at=None,
                )
            )

        job.status = ExtractionJobStatus.PENDING.value
        job.error_message = None
        job.paused_at = None
        job.updated_at = utcnow()
        await db.commit()
        await db.refresh(job)

        logger.info("Resumed job %s", job_id)
        return job

    async def cancel_job(self, job_id: str, db: AsyncSession) -> ExtractionJob:
        """Cancel a job and cleanup."""
        job = await db.get(ExtractionJob, job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        # Signal the job to stop
        self._active_jobs[job_id] = False

        job.status = ExtractionJobStatus.CANCELLED.value
        job.completed_at = utcnow()
        job.updated_at = utcnow()
        await db.commit()
        await db.refresh(job)

        logger.info("Cancelled job %s", job_id)
        return job

    # -----------------------------------------------------------------------
    # Progress Tracking
    # -----------------------------------------------------------------------

    async def get_job_progress(
        self,
        job_id: str,
        db: AsyncSession,
    ) -> Dict[str, Any]:
        """Get detailed progress information for a job."""
        job = await db.get(ExtractionJob, job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        # Count documents by status
        status_counts_stmt = (
            select(
                ExtractionJobDocument.status,
                func.count(ExtractionJobDocument.id),
            )
            .where(ExtractionJobDocument.job_id == job_id)
            .group_by(ExtractionJobDocument.status)
        )
        status_result = await db.execute(status_counts_stmt)
        status_counts = {row[0]: row[1] for row in status_result.fetchall()}

        # Get recent errors
        recent_errors_stmt = (
            select(ExtractionJobDocument)
            .where(
                and_(
                    ExtractionJobDocument.job_id == job_id,
                    ExtractionJobDocument.status == DocumentExtractionStatus.FAILED.value,
                )
            )
            .order_by(ExtractionJobDocument.updated_at.desc())
            .limit(10)
        )
        errors_result = await db.execute(recent_errors_stmt)
        recent_errors = [
            {
                "document_id": e.document_id,
                "error": e.error_message,
                "retry_count": e.retry_count,
            }
            for e in errors_result.scalars().all()
        ]

        return {
            "job_id": job.id,
            "status": job.status,
            "total_documents": job.total_documents,
            "processed_documents": job.processed_documents,
            "failed_documents": job.failed_documents,
            "skipped_documents": job.skipped_documents,
            "progress_percent": round(job.progress_percent, 2),
            "estimated_time_remaining": job.estimated_time_remaining,
            "current_rate": round(job.documents_per_second, 2),
            "documents_by_status": status_counts,
            "recent_errors": recent_errors,
            "can_resume": job.can_resume,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "paused_at": job.paused_at.isoformat() if job.paused_at else None,
        }

    async def list_jobs_for_table(
        self,
        review_table_id: str,
        db: AsyncSession,
        limit: int = 20,
    ) -> List[ExtractionJob]:
        """List extraction jobs for a review table."""
        stmt = (
            select(ExtractionJob)
            .where(ExtractionJob.review_table_id == review_table_id)
            .order_by(ExtractionJob.created_at.desc())
            .limit(limit)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    # -----------------------------------------------------------------------
    # Background Worker Helper
    # -----------------------------------------------------------------------

    async def get_next_pending_job(self, db: AsyncSession) -> Optional[ExtractionJob]:
        """Get the next pending job to process (for worker loop)."""
        stmt = (
            select(ExtractionJob)
            .where(ExtractionJob.status == ExtractionJobStatus.PENDING.value)
            .order_by(ExtractionJob.created_at)
            .limit(1)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

batch_extraction_service = BatchExtractionService()
