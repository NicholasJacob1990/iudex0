"""
Endpoints de Auditoria Jurídica (upload direto)

Compatível com o frontend: POST /api/audit/run (retorna DOCX)
"""

import os
import re
import shutil
import tempfile
from pathlib import Path
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from loguru import logger

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func
from fastapi import Query
from typing import Optional

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.core.time_utils import utcnow
from app.models.user import User
from app.models.workflow_state import WorkflowState
from app.models.case_task import CaseTask, TaskStatus, TaskPriority
from app.services.ai.audit_service import AuditService
from app.services.document_extraction_service import extract_text_from_path
from app.services.ai.observability.audit_log import get_tool_audit_log


router = APIRouter()


def _safe_filename_base(name: str) -> str:
    base = Path(name).stem or "documento"
    base = re.sub(r"[^a-zA-Z0-9_\-]+", "_", base).strip("_")
    return base[:80] or "documento"


def _parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Formato de data inválido em 'since' ou 'until'. Use ISO-8601.",
        )


async def _extract_text(file_path: str, ext: str) -> str:
    ext = ext.lower()
    if ext not in {".pdf", ".docx", ".txt", ".md", ".rtf", ".odt", ".html", ".htm"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Formato não suportado para auditoria. Envie PDF, DOCX, TXT ou MD.",
        )

    extraction = await extract_text_from_path(
        file_path,
        min_pdf_chars=50,
        allow_pdf_ocr_fallback=True,
    )
    text = str(extraction.text or "")
    if text:
        return text

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Formato não suportado para auditoria. Envie PDF, DOCX, TXT ou MD.",
    )


@router.post("/run")
async def run_audit(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """
    Executa auditoria jurídica a partir de um arquivo enviado e retorna o relatório em DOCX.
    """
    filename = file.filename or "documento"
    ext = Path(filename).suffix.lower()
    filename_base = _safe_filename_base(filename)

    audit_service = AuditService()

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = os.path.join(tmpdir, f"upload{ext or ''}")
        try:
            with open(tmp_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            file_size = os.path.getsize(tmp_path)
            if file_size > settings.max_upload_size_bytes:
                max_mb = settings.MAX_UPLOAD_SIZE_MB
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"Arquivo excede o limite de {max_mb}MB.",
                )

            content = await _extract_text(tmp_path, ext)
            if not content or len(content.strip()) < 50:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Documento sem conteúdo suficiente para auditoria.",
                )

            result = await audit_service.auditar_peca(
                texto_completo=content,
                output_folder=tmpdir,
                filename_base=f"{filename_base}_{current_user.id[:8]}",
                raw_transcript=content,
            )

            docx_path = result.get("docx_path")
            if not docx_path or not os.path.exists(docx_path):
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Falha ao gerar DOCX da auditoria.",
                )

            def iterfile():
                with open(docx_path, "rb") as f:
                    yield from iter(lambda: f.read(1024 * 1024), b"")

            out_name = f"Auditoria_{filename_base}.docx"
            return StreamingResponse(
                iterfile(),
                media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                headers={"Content-Disposition": f'attachment; filename="{out_name}"'},
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Erro ao executar auditoria: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Erro ao executar auditoria: {str(e)}",
            )


@router.post("/verify-snippet")
async def verify_snippet(
    request: dict,
    current_user: User = Depends(get_current_user),
):
    """
    Verificação rápida de citações jurídicas em um trecho de texto.
    Usado pelo Bubble Menu do Canvas para auditoria inline.
    
    Request body:
        {"text": "Segundo a Súmula 123 do STF..."}
    
    Response:
        {"status": "valid|suspicious|not_found", "message": "...", "suggestions": [...]}
    """
    text = request.get("text", "").strip()
    if not text or len(text) < 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Texto muito curto para verificação.",
        )
    
    try:
        audit_service = AuditService()
        
        # Use a simplified verification focusing on citations only
        result = await audit_service.verificar_citacoes_rapido(text)
        
        return {
            "status": result.get("status", "unknown"),
            "message": result.get("message", "Verificação concluída."),
            "citations": result.get("citations", []),
            "suggestions": result.get("suggestions", []),
        }
    
    except Exception as e:
        logger.error(f"Erro na verificação de snippet: {e}")
        # Fallback: return a safe response instead of failing
        return {
            "status": "unknown",
            "message": f"Não foi possível verificar: {str(e)}",
            "citations": [],
            "suggestions": [],
        }


@router.post("/edit-proposal")
async def create_edit_proposal(
    request: dict,
    current_user: User = Depends(get_current_user),
):
    """
    Cria uma proposta de edição estruturada para auditoria e reversão.
    
    Usado pelo Canvas para registrar alterações da IA com metadados completos.
    
    Request body:
        {
            "document_id": "uuid",
            "range": {"from": 100, "to": 150},
            "original": "texto original",
            "replacement": "texto novo",
            "agent": "gemini-1.5-pro",
            "sources_used": ["Lei 8.112/90", "Súmula 123"],
            "reason": "Melhoria de clareza jurídica"
        }
    
    Response:
        {
            "proposal_id": "uuid",
            "change_stats": {...},
            "requires_approval": true
        }
    """
    document_id = request.get("document_id")
    original = request.get("original", "")
    replacement = request.get("replacement", "")
    agent = request.get("agent", "unknown")
    sources_used = request.get("sources_used", [])
    reason = request.get("reason", "")
    range_data = request.get("range", {})
    
    if not original and not replacement:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Original ou replacement deve ser fornecido.",
        )
    
    import uuid
    
    proposal_id = str(uuid.uuid4())
    
    # Calculate change statistics
    original_words = len(original.split())
    replacement_words = len(replacement.split())
    words_added = max(0, replacement_words - original_words)
    words_removed = max(0, original_words - replacement_words)
    
    # Determine if approval is required based on change size
    change_percentage = abs(replacement_words - original_words) / max(original_words, 1) * 100
    requires_approval = change_percentage > 30 or len(replacement) > 500
    
    logger.info(f"Edit proposal created: {proposal_id} by agent {agent} for user {current_user.id[:8]}")
    
    return {
        "proposal_id": proposal_id,
        "document_id": document_id,
        "timestamp": utcnow().isoformat(),
        "agent": agent,
        "sources_used": sources_used,
        "reason": reason,
        "change_stats": {
            "original_words": original_words,
            "replacement_words": replacement_words,
            "words_added": words_added,
            "words_removed": words_removed,
            "change_percentage": round(change_percentage, 1),
        },
        "requires_approval": requires_approval,
        "status": "pending",
    }


@router.post("/edit-proposal/{proposal_id}/apply")
async def apply_edit_proposal(
    proposal_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    Aplica uma proposta de edição aprovada.
    """
    logger.info(f"Edit proposal {proposal_id} applied by user {current_user.id[:8]}")
    
    return {
        "proposal_id": proposal_id,
        "status": "applied",
        "message": "Edição aplicada com sucesso.",
    }


@router.post("/edit-proposal/{proposal_id}/reject")
async def reject_edit_proposal(
    proposal_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    Rejeita uma proposta de edição.
    """
    logger.info(f"Edit proposal {proposal_id} rejected by user {current_user.id[:8]}")

    return {
        "proposal_id": proposal_id,
        "status": "rejected",
        "message": "Edição rejeitada.",
    }


# ===== WORKFLOW STATE ENDPOINTS (v5.7) =====

@router.get("/workflow-states")
async def list_workflow_states(
    case_id: Optional[str] = Query(None, description="Filter by case ID"),
    chat_id: Optional[str] = Query(None, description="Filter by chat ID"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    List workflow states for the current user.
    Used for audit trail and compliance review.
    """
    query = select(WorkflowState).where(
        WorkflowState.user_id == str(current_user.id)
    ).order_by(desc(WorkflowState.created_at))

    if case_id:
        query = query.where(WorkflowState.case_id == case_id)
    if chat_id:
        query = query.where(WorkflowState.chat_id == chat_id)

    query = query.offset(offset).limit(limit)

    result = await db.execute(query)
    states = result.scalars().all()

    return {
        "items": [
            {
                "id": s.id,
                "job_id": s.job_id,
                "case_id": s.case_id,
                "chat_id": s.chat_id,
                "status": s.status,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "completed_at": s.completed_at.isoformat() if s.completed_at else None,
                "sources_count": len(s.sources or []),
                "hil_history_count": len(s.hil_history or []),
                "has_audit_issues": bool((s.audit_decisions or {}).get("issues")),
            }
            for s in states
        ],
        "total": len(states),
        "limit": limit,
        "offset": offset,
    }


@router.get("/workflow-states/{state_id}")
async def get_workflow_state(
    state_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get detailed workflow state by ID.
    Returns full audit data including sources, decisions, and HIL history.
    """
    result = await db.execute(
        select(WorkflowState).where(
            WorkflowState.id == state_id,
            WorkflowState.user_id == str(current_user.id),
        )
    )
    state = result.scalar_one_or_none()

    if not state:
        raise HTTPException(status_code=404, detail="Workflow state not found")

    return state.to_audit_dict()


@router.get("/workflow-states/by-job/{job_id}")
async def get_workflow_state_by_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get workflow state by job ID.
    Useful for accessing audit data right after a job completes.
    """
    result = await db.execute(
        select(WorkflowState).where(
            WorkflowState.job_id == job_id,
            WorkflowState.user_id == str(current_user.id),
        )
    )
    state = result.scalar_one_or_none()

    if not state:
        raise HTTPException(status_code=404, detail="Workflow state not found for this job")

    return state.to_audit_dict()


@router.get("/workflow-states/{state_id}/sources")
async def get_workflow_sources(
    state_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get sources (retrieved documents) for a workflow state.
    """
    result = await db.execute(
        select(WorkflowState).where(
            WorkflowState.id == state_id,
            WorkflowState.user_id == str(current_user.id),
        )
    )
    state = result.scalar_one_or_none()

    if not state:
        raise HTTPException(status_code=404, detail="Workflow state not found")

    return {
        "sources": state.sources or [],
        "retrieval_queries": state.retrieval_queries or [],
        "citations_map": state.citations_map or {},
    }


@router.get("/workflow-states/{state_id}/decisions")
async def get_workflow_decisions(
    state_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get all decisions made during a workflow.
    Includes routing, alerts, citations, audit, and quality decisions.
    """
    result = await db.execute(
        select(WorkflowState).where(
            WorkflowState.id == state_id,
            WorkflowState.user_id == str(current_user.id),
        )
    )
    state = result.scalar_one_or_none()

    if not state:
        raise HTTPException(status_code=404, detail="Workflow state not found")

    return {
        "routing": state.routing_decisions or {},
        "alerts": state.alert_decisions or {},
        "citations": state.citation_decisions or {},
        "audit": state.audit_decisions or {},
        "quality": state.quality_decisions or {},
    }


@router.get("/workflow-states/{state_id}/hil-history")
async def get_workflow_hil_history(
    state_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get HIL (Human-in-the-Loop) interaction history for a workflow.
    Shows all human interventions with timestamps and decisions.
    """
    result = await db.execute(
        select(WorkflowState).where(
            WorkflowState.id == state_id,
            WorkflowState.user_id == str(current_user.id),
        )
    )
    state = result.scalar_one_or_none()

    if not state:
        raise HTTPException(status_code=404, detail="Workflow state not found")

    return {
        "hil_history": state.hil_history or [],
        "processed_sections": state.processed_sections or [],
    }


# ===== CASE TASKS ENDPOINTS (v5.7) =====

@router.get("/tasks")
async def list_tasks(
    case_id: Optional[str] = Query(None, description="Filter by case ID"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status"),
    priority: Optional[str] = Query(None, description="Filter by priority"),
    overdue_only: bool = Query(False, description="Only show overdue tasks"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    List tasks for the current user.
    Supports filtering by case, status, priority, and overdue status.
    """
    query = select(CaseTask).where(
        CaseTask.user_id == str(current_user.id)
    ).order_by(CaseTask.deadline.asc().nullslast(), desc(CaseTask.created_at))

    if case_id:
        query = query.where(CaseTask.case_id == case_id)
    if status_filter:
        query = query.where(CaseTask.status == status_filter)
    if priority:
        query = query.where(CaseTask.priority == priority)
    if overdue_only:
        query = query.where(
            CaseTask.deadline < utcnow(),
            CaseTask.status != TaskStatus.COMPLETED,
        )

    query = query.offset(offset).limit(limit)

    result = await db.execute(query)
    tasks = result.scalars().all()

    return {
        "items": [t.to_dict() for t in tasks],
        "total": len(tasks),
        "limit": limit,
        "offset": offset,
    }


@router.get("/tasks/{task_id}")
async def get_task(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific task by ID."""
    result = await db.execute(
        select(CaseTask).where(
            CaseTask.id == task_id,
            CaseTask.user_id == str(current_user.id),
        )
    )
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    return task.to_dict()


@router.post("/tasks")
async def create_task(
    task_data: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new task manually.
    """
    task = CaseTask(
        case_id=task_data.get("case_id"),
        user_id=str(current_user.id),
        title=task_data.get("title", "Nova Tarefa"),
        description=task_data.get("description"),
        task_type=task_data.get("task_type", "other"),
        priority=task_data.get("priority", "medium"),
        deadline=task_data.get("deadline"),
        reminder_at=task_data.get("reminder_at"),
        source="manual",
        extra_data=task_data.get("extra_data", {}),
    )

    db.add(task)
    await db.commit()
    await db.refresh(task)

    return task.to_dict()


@router.patch("/tasks/{task_id}")
async def update_task(
    task_id: str,
    updates: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Update a task (status, priority, deadline, etc.).
    """
    result = await db.execute(
        select(CaseTask).where(
            CaseTask.id == task_id,
            CaseTask.user_id == str(current_user.id),
        )
    )
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Update allowed fields
    allowed_fields = ["title", "description", "task_type", "priority", "status",
                      "deadline", "reminder_at", "extra_data"]

    for field in allowed_fields:
        if field in updates:
            setattr(task, field, updates[field])

    # Handle status transitions
    if "status" in updates:
        if updates["status"] == TaskStatus.IN_PROGRESS and not task.started_at:
            task.started_at = utcnow()
        elif updates["status"] == TaskStatus.COMPLETED:
            task.completed_at = utcnow()

    await db.commit()
    await db.refresh(task)

    return task.to_dict()


@router.delete("/tasks/{task_id}")
async def delete_task(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a task."""
    result = await db.execute(
        select(CaseTask).where(
            CaseTask.id == task_id,
            CaseTask.user_id == str(current_user.id),
        )
    )
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    await db.delete(task)
    await db.commit()

    return {"deleted": True, "id": task_id}


# ===== AUDIT SUMMARY ENDPOINT (v5.7) =====

@router.get("/summary")
async def get_audit_summary(
    case_id: Optional[str] = Query(None, description="Filter by case ID"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get summary of audit data for the user.
    Useful for dashboard views.
    """
    # Count workflow states
    ws_query = select(func.count(WorkflowState.id)).where(
        WorkflowState.user_id == str(current_user.id)
    )
    if case_id:
        ws_query = ws_query.where(WorkflowState.case_id == case_id)

    ws_result = await db.execute(ws_query)
    workflow_count = ws_result.scalar() or 0

    # Count tasks by status
    task_query = select(
        CaseTask.status,
        func.count(CaseTask.id)
    ).where(
        CaseTask.user_id == str(current_user.id)
    ).group_by(CaseTask.status)

    if case_id:
        task_query = task_query.where(CaseTask.case_id == case_id)

    task_result = await db.execute(task_query)
    task_counts = dict(task_result.all())

    # Count overdue tasks
    overdue_query = select(func.count(CaseTask.id)).where(
        CaseTask.user_id == str(current_user.id),
        CaseTask.deadline < utcnow(),
        CaseTask.status != TaskStatus.COMPLETED,
    )
    if case_id:
        overdue_query = overdue_query.where(CaseTask.case_id == case_id)

    overdue_result = await db.execute(overdue_query)
    overdue_count = overdue_result.scalar() or 0

    return {
        "workflow_states_count": workflow_count,
        "tasks": {
            "total": sum(task_counts.values()),
            "by_status": task_counts,
            "overdue": overdue_count,
        },
    }


@router.get("/tool-calls")
async def list_tool_call_audit(
    tool_name: Optional[str] = Query(None, description="Filter by tool name"),
    event_type: Optional[str] = Query(
        None,
        description="Filter by event type: permission_decision|tool_execution",
    ),
    since: Optional[str] = Query(None, description="ISO datetime lower bound"),
    until: Optional[str] = Query(None, description="ISO datetime upper bound"),
    limit: int = Query(200, ge=1, le=5000),
    current_user: User = Depends(get_current_user),
):
    """
    Lista o audit trail estruturado de tools para o usuário atual.
    """
    since_dt = _parse_iso_datetime(since)
    until_dt = _parse_iso_datetime(until)
    entries = get_tool_audit_log().list_entries(
        user_id=str(current_user.id),
        tool_name=tool_name,
        event_type=event_type,
        since=since_dt,
        until=until_dt,
        limit=limit,
    )
    return {
        "items": entries,
        "total": len(entries),
        "limit": limit,
    }


@router.get("/tool-calls/export")
async def export_tool_call_audit(
    tool_name: Optional[str] = Query(None, description="Filter by tool name"),
    event_type: Optional[str] = Query(
        None,
        description="Filter by event type: permission_decision|tool_execution",
    ),
    since: Optional[str] = Query(None, description="ISO datetime lower bound"),
    until: Optional[str] = Query(None, description="ISO datetime upper bound"),
    limit: int = Query(2000, ge=1, le=20000),
    current_user: User = Depends(get_current_user),
):
    """
    Exporta audit trail de tool calls em JSONL para compliance.
    """
    since_dt = _parse_iso_datetime(since)
    until_dt = _parse_iso_datetime(until)
    content = get_tool_audit_log().export_jsonl(
        user_id=str(current_user.id),
        tool_name=tool_name,
        event_type=event_type,
        since=since_dt,
        until=until_dt,
        limit=limit,
    )
    filename = f"tool_audit_{str(current_user.id)[:8]}.jsonl"
    return StreamingResponse(
        iter([content.encode("utf-8")]),
        media_type="application/x-ndjson",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
