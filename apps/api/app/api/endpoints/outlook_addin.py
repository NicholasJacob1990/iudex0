"""
Endpoints para o modulo Outlook Add-in.

Fornece:
- Sumarizacao de e-mail com SSE streaming
- Classificacao de tipo juridico
- Extracao de prazos
"""

import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.time_utils import utcnow
from app.models.user import User
from app.models.workflow import WorkflowRun, WorkflowRunStatus
from app.schemas.outlook_addin_schemas import (
    SummarizeEmailRequest,
    ClassifyEmailRequest,
    ClassifyEmailResponse,
    ExtractDeadlinesRequest,
    ExtractDeadlinesResponse,
    OutlookWorkflowTriggerRequest,
    OutlookWorkflowRunResponse,
)
from app.services.outlook_addin_service import outlook_addin_service
from app.services.builtin_workflows import is_builtin, get_builtin_name

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/summarize")
async def summarize_email(
    request: SummarizeEmailRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """
    Sumariza e-mail juridico via SSE.
    Retorna tipo juridico, resumo, partes, prazos, acoes.
    """
    # Check cache if internet_message_id provided
    if request.internet_message_id:
        cached = await outlook_addin_service.get_cached_analysis(
            db=db,
            user_id=str(current_user.id),
            message_id=request.internet_message_id,
            analysis_type="summary",
        )
        if cached:
            return JSONResponse(cached)

    async def generate():
        try:
            async for event in outlook_addin_service.summarize_email(
                subject=request.subject,
                from_address=request.from_address,
                to_addresses=request.to_addresses,
                body=request.body,
                body_type=request.body_type,
                attachment_names=request.attachment_names,
                user_id=str(current_user.id),
                db=db,
            ):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error(f"Summarize error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'data': str(e)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/classify", response_model=ClassifyEmailResponse)
async def classify_email(
    request: ClassifyEmailRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ClassifyEmailResponse:
    """Classifica tipo juridico do e-mail."""
    # Check cache
    if request.internet_message_id:
        cached = await outlook_addin_service.get_cached_analysis(
            db=db,
            user_id=str(current_user.id),
            message_id=request.internet_message_id,
            analysis_type="classify",
        )
        if cached:
            return ClassifyEmailResponse(**cached)

    result = await outlook_addin_service.classify_email(
        subject=request.subject,
        from_address=request.from_address,
        body=request.body,
        body_type=request.body_type,
        user_id=str(current_user.id),
        db=db,
    )
    return result


@router.post("/extract-deadlines", response_model=ExtractDeadlinesResponse)
async def extract_deadlines(
    request: ExtractDeadlinesRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ExtractDeadlinesResponse:
    """Extrai prazos do e-mail."""
    if request.internet_message_id:
        cached = await outlook_addin_service.get_cached_analysis(
            db=db,
            user_id=str(current_user.id),
            message_id=request.internet_message_id,
            analysis_type="deadlines",
        )
        if cached:
            return ExtractDeadlinesResponse(**cached)

    result = await outlook_addin_service.extract_deadlines(
        subject=request.subject,
        body=request.body,
        body_type=request.body_type,
        user_id=str(current_user.id),
        db=db,
    )
    return result


# ---------------------------------------------------------------------------
# Workflow trigger & status
# ---------------------------------------------------------------------------


@router.post("/workflow/trigger", response_model=OutlookWorkflowRunResponse)
async def trigger_workflow(
    request: OutlookWorkflowTriggerRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> OutlookWorkflowRunResponse:
    """
    Trigger a workflow from the Outlook Add-in.
    Accepts builtin slugs (e.g. 'extract-deadlines') or real workflow UUIDs.
    Returns immediately with status 'pending'.
    """
    workflow_id = request.workflow_id
    user_id = str(current_user.id)
    now = utcnow()

    if is_builtin(workflow_id):
        workflow_name = get_builtin_name(workflow_id) or workflow_id
    else:
        # Validate real workflow ownership
        from app.models.workflow import Workflow
        from app.models.organization import OrganizationMember
        from sqlalchemy import select

        wf = await db.get(Workflow, workflow_id)
        if not wf:
            raise HTTPException(status_code=404, detail="Workflow not found")
        if wf.user_id != user_id:
            if not wf.organization_id:
                raise HTTPException(
                    status_code=403, detail="Not authorized to run this workflow"
                )

            mem_stmt = select(OrganizationMember).where(
                OrganizationMember.organization_id == wf.organization_id,
                OrganizationMember.user_id == user_id,
                OrganizationMember.is_active == True,  # noqa: E712
            )
            mem_res = await db.execute(mem_stmt)
            if not mem_res.scalar_one_or_none():
                raise HTTPException(
                    status_code=403, detail="Not authorized to run this workflow"
                )
        workflow_name = wf.name

    # Create WorkflowRun record
    run_id = str(uuid.uuid4())
    run = WorkflowRun(
        id=run_id,
        workflow_id=workflow_id,
        user_id=user_id,
        status=WorkflowRunStatus.PENDING,
        input_data={"email_data": request.email_data, "parameters": request.parameters},
        trigger_type="outlook_addin",
        created_at=now,
    )
    db.add(run)
    await db.commit()

    # Enqueue appropriate task
    if is_builtin(workflow_id):
        from app.workers.tasks.workflow_tasks import run_builtin_workflow

        run_builtin_workflow.delay(
            run_id=run_id,
            workflow_id=workflow_id,
            email_data=request.email_data,
            parameters=request.parameters,
            user_id=user_id,
        )
    else:
        # Use send_task to avoid relying on local task registration state in the API process.
        from app.workers.celery_app import celery_app

        celery_app.send_task(
            "run_triggered_workflow",
            kwargs={
                "workflow_id": workflow_id,
                "user_id": user_id,
                "trigger_type": "outlook_addin",
                "event_data": {**(request.email_data or {}), "parameters": request.parameters},
                "run_id": run_id,
            },
        )

    return OutlookWorkflowRunResponse(
        id=run_id,
        workflow_id=workflow_id,
        workflow_name=workflow_name,
        status="pending",
        created_at=now.isoformat(),
        updated_at=now.isoformat(),
    )


@router.get("/workflow/status/{run_id}", response_model=OutlookWorkflowRunResponse)
async def get_workflow_status(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> OutlookWorkflowRunResponse:
    """Get the status of a workflow run triggered from the Outlook Add-in."""
    run = await db.get(WorkflowRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Workflow run not found")
    if run.user_id != str(current_user.id):
        raise HTTPException(status_code=403, detail="Not authorized")

    # Map internal status to frontend-friendly status
    status_map = {
        WorkflowRunStatus.PENDING: "pending",
        WorkflowRunStatus.RUNNING: "running",
        WorkflowRunStatus.COMPLETED: "completed",
        WorkflowRunStatus.ERROR: "failed",
        WorkflowRunStatus.CANCELLED: "failed",
        WorkflowRunStatus.PAUSED_HIL: "running",
    }
    status = status_map.get(run.status, "pending")

    # Resolve workflow name
    workflow_name = get_builtin_name(run.workflow_id)
    if not workflow_name:
        from app.models.workflow import Workflow

        wf = await db.get(Workflow, run.workflow_id)
        workflow_name = wf.name if wf else run.workflow_id

    updated_at = (run.completed_at or run.started_at or run.created_at).isoformat()

    return OutlookWorkflowRunResponse(
        id=run.id,
        workflow_id=run.workflow_id,
        workflow_name=workflow_name,
        status=status,
        result=run.output_data,
        created_at=run.created_at.isoformat(),
        updated_at=updated_at,
    )
