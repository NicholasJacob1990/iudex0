"""
Extraction Tasks — Celery tasks for batch extraction processing.

Provides both Celery-based task execution and async background worker
for processing extraction jobs.
"""

import asyncio
import logging

from loguru import logger

from app.workers.celery_app import celery_app
from app.core.database import AsyncSessionLocal
from app.models.extraction_job import ExtractionJob, ExtractionJobStatus
from app.services.batch_extraction_service import batch_extraction_service


# ---------------------------------------------------------------------------
# Celery Task for Extraction Job Processing
# ---------------------------------------------------------------------------


@celery_app.task(
    name="process_extraction_job",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    time_limit=7200,  # 2 hours max
    soft_time_limit=7000,
)
def process_extraction_job_task(self, job_id: str):
    """
    Celery task to process an extraction job.

    This task is designed for long-running batch extractions (2000+ documents).
    Uses async internally for concurrent document processing.

    Args:
        job_id: ID of the extraction job to process.
    """
    logger.info(f"[TASK] Starting extraction job {job_id}")

    try:
        result = asyncio.run(_process_job_async(job_id))

        logger.info(
            f"[TASK] Extraction job {job_id} completed: "
            f"processed={result.get('processed', 0)}, "
            f"failed={result.get('failed', 0)}"
        )

        return {
            "success": True,
            "job_id": job_id,
            **result,
        }

    except Exception as e:
        logger.error(f"[TASK] Extraction job {job_id} failed: {e}", exc_info=True)

        # Retry on transient errors
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e)

        return {
            "success": False,
            "job_id": job_id,
            "error": str(e),
        }


async def _process_job_async(job_id: str) -> dict:
    """Async wrapper for job processing."""
    async with AsyncSessionLocal() as db:
        job = await batch_extraction_service.process_job(job_id, db)

        return {
            "processed": job.processed_documents,
            "failed": job.failed_documents,
            "skipped": job.skipped_documents,
            "status": job.status,
        }


# ---------------------------------------------------------------------------
# Celery Task for Starting Extraction
# ---------------------------------------------------------------------------


@celery_app.task(name="start_extraction_job")
def start_extraction_job_task(
    review_table_id: str,
    user_id: str,
    column_id: str | None = None,
    document_ids: list[str] | None = None,
    max_concurrent: int = 10,
    batch_size: int = 50,
):
    """
    Celery task to create and start an extraction job.

    Args:
        review_table_id: ID of the review table.
        user_id: ID of the user starting the job.
        column_id: Optional column ID for column-specific extraction.
        document_ids: Optional list of specific documents to process.
        max_concurrent: Maximum concurrent extractions.
        batch_size: Batch size for commits.
    """
    logger.info(f"[TASK] Creating extraction job for table {review_table_id}")

    try:
        result = asyncio.run(
            _create_and_start_job_async(
                review_table_id=review_table_id,
                user_id=user_id,
                column_id=column_id,
                document_ids=document_ids,
                max_concurrent=max_concurrent,
                batch_size=batch_size,
            )
        )

        # Queue the processing task
        process_extraction_job_task.delay(result["job_id"])

        return result

    except Exception as e:
        logger.error(f"[TASK] Failed to create extraction job: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
        }


async def _create_and_start_job_async(
    review_table_id: str,
    user_id: str,
    column_id: str | None,
    document_ids: list[str] | None,
    max_concurrent: int,
    batch_size: int,
) -> dict:
    """Async wrapper for job creation."""
    async with AsyncSessionLocal() as db:
        job = await batch_extraction_service.create_extraction_job(
            review_table_id=review_table_id,
            user_id=user_id,
            db=db,
            column_id=column_id,
            document_ids=document_ids,
            max_concurrent=max_concurrent,
            batch_size=batch_size,
        )

        return {
            "success": True,
            "job_id": job.id,
            "total_documents": job.total_documents,
            "status": job.status,
        }


# ---------------------------------------------------------------------------
# Async Background Worker (Alternative to Celery)
# ---------------------------------------------------------------------------


class ExtractionWorker:
    """
    Async background worker for processing extraction jobs.

    Alternative to Celery for environments where Redis/Celery is not available.
    Can be run as a standalone process or integrated into the FastAPI app.
    """

    def __init__(self, poll_interval: int = 5):
        self.poll_interval = poll_interval
        self._running = False
        self._current_task = None

    async def start(self):
        """Start the worker loop."""
        logger.info("Starting extraction worker")
        self._running = True

        while self._running:
            try:
                async with AsyncSessionLocal() as db:
                    # Get next pending job
                    job = await batch_extraction_service.get_next_pending_job(db)

                    if job:
                        logger.info(f"[WORKER] Processing job {job.id}")
                        try:
                            await batch_extraction_service.process_job(job.id, db)
                            logger.info(f"[WORKER] Job {job.id} completed")
                        except Exception as e:
                            logger.error(f"[WORKER] Job {job.id} failed: {e}", exc_info=True)
                    else:
                        # No pending jobs, wait before polling again
                        await asyncio.sleep(self.poll_interval)

            except Exception as e:
                logger.error(f"[WORKER] Error in worker loop: {e}", exc_info=True)
                await asyncio.sleep(self.poll_interval)

    def stop(self):
        """Stop the worker loop."""
        logger.info("Stopping extraction worker")
        self._running = False


# Global worker instance
extraction_worker = ExtractionWorker()


async def run_extraction_worker():
    """Entry point for running the extraction worker."""
    await extraction_worker.start()


# ---------------------------------------------------------------------------
# FastAPI Background Task Helper
# ---------------------------------------------------------------------------


async def process_job_background(job_id: str) -> None:
    """
    Process an extraction job in FastAPI background task.

    Use this when Celery is not available or for immediate processing.
    """
    async with AsyncSessionLocal() as db:
        try:
            await batch_extraction_service.process_job(job_id, db)
        except Exception as e:
            logger.error(
                "Error in background job processing %s: %s",
                job_id, e, exc_info=True,
            )
