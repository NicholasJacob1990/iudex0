"""
Extraction Jobs — Batch processing endpoints for Review Tables.

Scalable batch processing for 2000+ documents with:
- Async job queue with progress tracking
- Pause/resume capability
- Real-time SSE progress updates
- Per-document retry logic
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.extraction_job import (
    ExtractionJob,
    ExtractionJobStatus,
    ExtractionJobType,
)
from app.models.review_table import ReviewTable
from app.models.user import User
from app.services.batch_extraction_service import batch_extraction_service

logger = logging.getLogger("ExtractionJobsEndpoints")

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class StartExtractionRequest(BaseModel):
    """Request to start a batch extraction job."""
    column_ids: Optional[List[str]] = Field(
        None,
        description="Optional list of column IDs to extract. If not provided, extracts all columns.",
    )
    document_ids: Optional[List[str]] = Field(
        None,
        description="Optional list of specific document IDs to process. If not provided, processes all documents.",
    )
    max_concurrent: int = Field(
        10,
        ge=1,
        le=50,
        description="Maximum concurrent document extractions (1-50).",
    )
    batch_size: int = Field(
        50,
        ge=10,
        le=200,
        description="Number of documents per batch commit (10-200).",
    )


class ExtractionJobResponse(BaseModel):
    """Response for extraction job status."""
    id: str
    review_table_id: str
    job_type: str
    status: str
    total_documents: int
    processed_documents: int
    failed_documents: int
    skipped_documents: int
    progress_percent: float
    documents_per_second: float
    estimated_time_remaining: Optional[int] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    paused_at: Optional[str] = None
    error_message: Optional[str] = None
    can_resume: bool
    created_at: str


class JobProgressResponse(BaseModel):
    """Detailed progress response for a job."""
    job_id: str
    status: str
    total_documents: int
    processed_documents: int
    failed_documents: int
    skipped_documents: int
    progress_percent: float
    estimated_time_remaining: Optional[int] = None
    current_rate: float
    documents_by_status: Dict[str, int]
    recent_errors: List[Dict[str, Any]]
    can_resume: bool
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    paused_at: Optional[str] = None


class JobListResponse(BaseModel):
    """List of extraction jobs."""
    items: List[ExtractionJobResponse]
    total: int


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/{table_id}/extract", response_model=ExtractionJobResponse, status_code=201)
async def start_extraction(
    table_id: str,
    request: StartExtractionRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Start a batch extraction job for a review table.

    This endpoint creates a new extraction job and starts processing documents
    in the background. Designed for handling 2000+ documents efficiently.

    Features:
    - Concurrent processing with configurable parallelism
    - Progress tracking with ETA calculation
    - Pause/resume capability
    - Per-document retry with exponential backoff
    - Incremental result storage

    Returns the created job with initial status.
    Use GET /{table_id}/jobs/{job_id}/progress for detailed progress tracking.
    Use GET /{table_id}/jobs/{job_id}/stream for real-time SSE updates.
    """
    from app.workers.tasks.extraction_tasks import process_job_background

    review = await db.get(ReviewTable, table_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review table nao encontrada")

    user_id = str(current_user.id)
    org_id = getattr(current_user, "organization_id", None)
    if review.user_id != user_id and review.organization_id != org_id:
        raise HTTPException(status_code=403, detail="Sem permissao")

    try:
        # Determine job type
        job_type = ExtractionJobType.FULL_EXTRACTION
        if request.column_ids:
            job_type = ExtractionJobType.COLUMN_EXTRACTION
        elif request.document_ids:
            job_type = ExtractionJobType.INCREMENTAL

        job = await batch_extraction_service.create_extraction_job(
            review_table_id=table_id,
            user_id=user_id,
            db=db,
            column_id=request.column_ids[0] if request.column_ids else None,
            job_type=job_type,
            document_ids=request.document_ids,
            max_concurrent=request.max_concurrent,
            batch_size=request.batch_size,
        )

        # Start processing in background
        background_tasks.add_task(process_job_background, job.id)

        return _job_to_response(job)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Erro ao criar job de extracao: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno ao criar job de extracao.")


@router.get("/{table_id}/jobs", response_model=JobListResponse)
async def list_jobs(
    table_id: str,
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List extraction jobs for a review table.

    Returns jobs in order of creation (most recent first).
    """
    review = await db.get(ReviewTable, table_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review table nao encontrada")

    user_id = str(current_user.id)
    org_id = getattr(current_user, "organization_id", None)
    if review.user_id != user_id and review.organization_id != org_id:
        raise HTTPException(status_code=403, detail="Sem permissao")

    jobs = await batch_extraction_service.list_jobs_for_table(
        review_table_id=table_id,
        db=db,
        limit=limit,
    )

    return JobListResponse(
        items=[_job_to_response(job) for job in jobs],
        total=len(jobs),
    )


@router.get("/{table_id}/jobs/{job_id}", response_model=ExtractionJobResponse)
async def get_job(
    table_id: str,
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get details of a specific extraction job."""
    review = await db.get(ReviewTable, table_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review table nao encontrada")

    user_id = str(current_user.id)
    org_id = getattr(current_user, "organization_id", None)
    if review.user_id != user_id and review.organization_id != org_id:
        raise HTTPException(status_code=403, detail="Sem permissao")

    job = await db.get(ExtractionJob, job_id)
    if not job or job.review_table_id != table_id:
        raise HTTPException(status_code=404, detail="Job nao encontrado")

    return _job_to_response(job)


@router.get("/{table_id}/jobs/{job_id}/progress", response_model=JobProgressResponse)
async def get_job_progress(
    table_id: str,
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get detailed progress information for an extraction job.

    Returns:
    - Document counts by status
    - Processing rate (docs/second)
    - Estimated time remaining
    - Recent errors
    """
    review = await db.get(ReviewTable, table_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review table nao encontrada")

    user_id = str(current_user.id)
    org_id = getattr(current_user, "organization_id", None)
    if review.user_id != user_id and review.organization_id != org_id:
        raise HTTPException(status_code=403, detail="Sem permissao")

    job = await db.get(ExtractionJob, job_id)
    if not job or job.review_table_id != table_id:
        raise HTTPException(status_code=404, detail="Job nao encontrado")

    progress = await batch_extraction_service.get_job_progress(job_id, db)
    return JobProgressResponse(**progress)


@router.post("/{table_id}/jobs/{job_id}/pause", response_model=ExtractionJobResponse)
async def pause_job(
    table_id: str,
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Pause a running extraction job.

    The job can be resumed later with POST /{table_id}/jobs/{job_id}/resume.
    Progress is preserved and extraction will continue from where it stopped.
    """
    review = await db.get(ReviewTable, table_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review table nao encontrada")

    user_id = str(current_user.id)
    org_id = getattr(current_user, "organization_id", None)
    if review.user_id != user_id and review.organization_id != org_id:
        raise HTTPException(status_code=403, detail="Sem permissao")

    job = await db.get(ExtractionJob, job_id)
    if not job or job.review_table_id != table_id:
        raise HTTPException(status_code=404, detail="Job nao encontrado")

    try:
        job = await batch_extraction_service.pause_job(job_id, db)
        return _job_to_response(job)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{table_id}/jobs/{job_id}/resume", response_model=ExtractionJobResponse)
async def resume_job(
    table_id: str,
    job_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Resume a paused or failed extraction job.

    For failed jobs, this resets failed documents for retry.
    Processing continues from where it stopped.
    """
    from app.workers.tasks.extraction_tasks import process_job_background

    review = await db.get(ReviewTable, table_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review table nao encontrada")

    user_id = str(current_user.id)
    org_id = getattr(current_user, "organization_id", None)
    if review.user_id != user_id and review.organization_id != org_id:
        raise HTTPException(status_code=403, detail="Sem permissao")

    job = await db.get(ExtractionJob, job_id)
    if not job or job.review_table_id != table_id:
        raise HTTPException(status_code=404, detail="Job nao encontrado")

    try:
        job = await batch_extraction_service.resume_job(job_id, db)

        # Start processing in background
        background_tasks.add_task(process_job_background, job.id)

        return _job_to_response(job)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{table_id}/jobs/{job_id}/cancel", response_model=ExtractionJobResponse)
async def cancel_job(
    table_id: str,
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Cancel an extraction job.

    This stops the job permanently. Partial results are preserved
    in the review table.
    """
    review = await db.get(ReviewTable, table_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review table nao encontrada")

    user_id = str(current_user.id)
    org_id = getattr(current_user, "organization_id", None)
    if review.user_id != user_id and review.organization_id != org_id:
        raise HTTPException(status_code=403, detail="Sem permissao")

    job = await db.get(ExtractionJob, job_id)
    if not job or job.review_table_id != table_id:
        raise HTTPException(status_code=404, detail="Job nao encontrado")

    try:
        job = await batch_extraction_service.cancel_job(job_id, db)
        return _job_to_response(job)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{table_id}/jobs/{job_id}/stream")
async def stream_job_progress(
    table_id: str,
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Stream real-time progress updates via Server-Sent Events (SSE).

    Events:
    - progress: Periodic progress updates
    - completed: Job finished successfully
    - failed: Job failed
    - paused: Job was paused

    Example event:
    ```
    data: {"processed": 150, "total": 2000, "percent": 7.5, "rate": 2.3}
    ```
    """
    review = await db.get(ReviewTable, table_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review table nao encontrada")

    user_id = str(current_user.id)
    org_id = getattr(current_user, "organization_id", None)
    if review.user_id != user_id and review.organization_id != org_id:
        raise HTTPException(status_code=403, detail="Sem permissao")

    job = await db.get(ExtractionJob, job_id)
    if not job or job.review_table_id != table_id:
        raise HTTPException(status_code=404, detail="Job nao encontrado")

    async def event_generator():
        import asyncio
        from app.core.database import AsyncSessionLocal

        while True:
            async with AsyncSessionLocal() as session:
                current_job = await session.get(ExtractionJob, job_id)
                if not current_job:
                    yield f"event: error\ndata: {{\"error\": \"Job not found\"}}\n\n"
                    break

                progress_data = {
                    "processed": current_job.processed_documents,
                    "total": current_job.total_documents,
                    "failed": current_job.failed_documents,
                    "percent": round(current_job.progress_percent, 2),
                    "rate": round(current_job.documents_per_second, 2),
                    "eta_seconds": current_job.estimated_time_remaining,
                    "status": current_job.status,
                }

                if current_job.status == ExtractionJobStatus.COMPLETED.value:
                    yield f"event: completed\ndata: {json.dumps(progress_data)}\n\n"
                    break
                elif current_job.status == ExtractionJobStatus.FAILED.value:
                    progress_data["error"] = current_job.error_message
                    yield f"event: failed\ndata: {json.dumps(progress_data)}\n\n"
                    break
                elif current_job.status == ExtractionJobStatus.PAUSED.value:
                    yield f"event: paused\ndata: {json.dumps(progress_data)}\n\n"
                    break
                elif current_job.status == ExtractionJobStatus.CANCELLED.value:
                    yield f"event: cancelled\ndata: {json.dumps(progress_data)}\n\n"
                    break
                else:
                    yield f"event: progress\ndata: {json.dumps(progress_data)}\n\n"

            await asyncio.sleep(2)  # Update every 2 seconds

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _job_to_response(job: ExtractionJob) -> ExtractionJobResponse:
    """Convert ExtractionJob model to response schema."""
    return ExtractionJobResponse(
        id=job.id,
        review_table_id=job.review_table_id,
        job_type=job.job_type,
        status=job.status,
        total_documents=job.total_documents,
        processed_documents=job.processed_documents,
        failed_documents=job.failed_documents,
        skipped_documents=job.skipped_documents,
        progress_percent=round(job.progress_percent, 2),
        documents_per_second=round(job.documents_per_second, 2),
        estimated_time_remaining=job.estimated_time_remaining,
        started_at=job.started_at.isoformat() if job.started_at else None,
        completed_at=job.completed_at.isoformat() if job.completed_at else None,
        paused_at=job.paused_at.isoformat() if job.paused_at else None,
        error_message=job.error_message,
        can_resume=job.can_resume,
        created_at=job.created_at.isoformat() if job.created_at else "",
    )
