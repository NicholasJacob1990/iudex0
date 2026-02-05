"""
Workflows — CRUD + execution endpoints for visual workflow builder.

POST   /workflows                    — Create workflow
GET    /workflows                    — List user's workflows
GET    /workflows/{id}               — Get workflow detail
PUT    /workflows/{id}               — Update workflow
DELETE /workflows/{id}               — Delete workflow
POST   /workflows/{id}/run           — Execute workflow (SSE stream)
POST   /workflows/{id}/test          — Test workflow (transient run, SSE stream)
POST   /workflows/runs/{run_id}/resume — Resume after HIL
POST   /workflows/runs/{run_id}/follow-up — Ask follow-up about a completed run
POST   /workflows/runs/{run_id}/share — Share run output with other users
GET    /workflows/{id}/runs          — List runs for a workflow
"""

from __future__ import annotations

import hmac
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.core.database import get_db
from app.core.security import get_current_user, get_current_user_optional, require_role
from app.core.time_utils import utcnow
from app.models.user import User
from app.models.workflow import Workflow, WorkflowRun, WorkflowRunStatus, WorkflowStatus, WorkflowVersion
from app.services.ai.workflow_compiler import validate_graph, GraphValidationError
from app.services.ai.workflow_runner import WorkflowRunner

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class WorkflowCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    graph_json: Dict[str, Any] = Field(..., description="React Flow nodes + edges")
    tags: List[str] = Field(default_factory=list)
    is_template: bool = False
    category: Optional[str] = None
    practice_area: Optional[str] = None
    output_type: Optional[str] = None


class WorkflowUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    graph_json: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None
    is_active: Optional[bool] = None
    category: Optional[str] = None
    practice_area: Optional[str] = None
    output_type: Optional[str] = None


class WorkflowResponse(BaseModel):
    id: str
    user_id: str
    name: str
    description: Optional[str] = None
    graph_json: Dict[str, Any]
    is_active: bool
    is_template: bool
    tags: List[str]
    embedded_files: List[Dict[str, Any]] = Field(default_factory=list)
    status: str = "draft"
    published_version: Optional[int] = None
    submitted_at: Optional[str] = None
    approved_at: Optional[str] = None
    rejection_reason: Optional[str] = None
    published_slug: Optional[str] = None
    published_config: Optional[Dict[str, Any]] = None
    category: Optional[str] = None
    practice_area: Optional[str] = None
    output_type: Optional[str] = None
    run_count: int = 0
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class WorkflowRunResponse(BaseModel):
    id: str
    workflow_id: str
    status: str
    input_data: Dict[str, Any]
    output_data: Optional[Dict[str, Any]] = None
    current_node: Optional[str] = None
    logs: List[Dict[str, Any]]
    error_message: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    created_at: str


class RunWorkflowRequest(BaseModel):
    input_data: Dict[str, Any] = Field(default_factory=dict)
    context_session_id: Optional[str] = Field(
        None, description="Unified context session to inject"
    )


class ResumeHILRequest(BaseModel):
    approved: bool = True
    human_edits: Optional[Dict[str, Any]] = None


class FollowUpRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)


class ShareRunRequest(BaseModel):
    user_ids: List[str] = Field(..., min_length=1)
    message: Optional[str] = None


# ---------------------------------------------------------------------------
# SSE helper
# ---------------------------------------------------------------------------


def sse_line(data: dict, event: str = "message") -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# ---------------------------------------------------------------------------
# CRUD Endpoints
# ---------------------------------------------------------------------------


@router.post("", response_model=WorkflowResponse, status_code=201)
async def create_workflow(
    request: WorkflowCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new workflow."""
    # Only validate graph if it has nodes (empty graph = new draft)
    nodes = (request.graph_json or {}).get("nodes", [])
    if nodes:
        errors = validate_graph(request.graph_json)
        if errors:
            raise HTTPException(status_code=422, detail={"validation_errors": errors})

    workflow = Workflow(
        id=str(uuid.uuid4()),
        user_id=str(current_user.id),
        organization_id=getattr(current_user, "organization_id", None),
        name=request.name,
        description=request.description,
        graph_json=request.graph_json,
        tags=request.tags,
        is_template=request.is_template,
        category=request.category,
        practice_area=request.practice_area,
        output_type=request.output_type,
    )
    db.add(workflow)
    await db.commit()
    await db.refresh(workflow)

    return _workflow_to_response(workflow)


@router.get("", response_model=List[WorkflowResponse])
async def list_workflows(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all workflows for the current user."""
    stmt = (
        select(Workflow)
        .where(Workflow.user_id == str(current_user.id))
        .order_by(Workflow.updated_at.desc())
    )
    result = await db.execute(stmt)
    workflows = result.scalars().all()
    return [_workflow_to_response(w) for w in workflows]


@router.get("/catalog")
async def workflow_catalog(
    category: Optional[str] = None,
    practice_area: Optional[str] = None,
    output_type: Optional[str] = None,
    search: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Browse published workflows catalog with filters."""
    stmt = select(Workflow).where(
        Workflow.is_active == True,
        Workflow.status == "published",
    )
    if category:
        stmt = stmt.where(Workflow.category == category)
    if practice_area:
        stmt = stmt.where(Workflow.practice_area == practice_area)
    if output_type:
        stmt = stmt.where(Workflow.output_type == output_type)
    if search:
        stmt = stmt.where(
            Workflow.name.ilike(f"%{search}%") | Workflow.description.ilike(f"%{search}%")
        )
    stmt = stmt.order_by(Workflow.run_count.desc()).limit(50)
    result = await db.execute(stmt)
    workflows = result.scalars().all()
    return [_workflow_to_response(w) for w in workflows]


@router.post("/{workflow_id}/clone", response_model=WorkflowResponse)
async def clone_workflow_template(
    workflow_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Clone a template or existing workflow to user's workspace."""
    result = await db.execute(select(Workflow).where(Workflow.id == workflow_id))
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Workflow not found")

    # Authorization: only allow cloning templates, own workflows, or same-org workflows
    is_template = getattr(source, "is_template", False)
    is_own = source.user_id == str(current_user.id)
    same_org = (
        getattr(current_user, "organization_id", None)
        and source.organization_id == getattr(current_user, "organization_id", None)
    )
    if not (is_template or is_own or same_org):
        raise HTTPException(status_code=403, detail="Not authorized to clone this workflow")

    cloned = Workflow(
        id=str(uuid.uuid4()),
        user_id=str(current_user.id),
        organization_id=getattr(current_user, "organization_id", None),
        name=f"{source.name} (Cópia)",
        description=source.description,
        graph_json=source.graph_json,
        is_template=False,
        is_active=True,
        tags=source.tags or [],
        category=source.category,
        practice_area=source.practice_area,
        output_type=source.output_type,
        embedded_files=[],
    )
    db.add(cloned)

    # Track clone usage (separate from run_count)
    source.clone_count = (getattr(source, "clone_count", 0) or 0) + 1
    db.add(source)

    await db.commit()
    await db.refresh(cloned)
    return _workflow_to_response(cloned)


class WorkflowImproveResponse(BaseModel):
    suggestions: List[Dict[str, Any]]
    summary: str


@router.post("/{workflow_id}/improve", response_model=WorkflowImproveResponse)
async def improve_workflow(
    workflow_id: str = Path(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Use AI to analyze workflow and suggest improvements."""
    org_id = getattr(current_user, "organization_id", None)
    result = await db.execute(
        select(Workflow).where(
            Workflow.id == workflow_id,
            or_(
                Workflow.user_id == str(current_user.id),
                Workflow.organization_id == org_id if org_id else False,
            ),
        )
    )
    workflow = result.scalar_one_or_none()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    graph = workflow.graph_json or {}
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])

    # Build analysis prompt
    analysis_prompt = f"""Analise este workflow jurídico e sugira melhorias.

Nome: {workflow.name}
Descrição: {workflow.description or 'N/A'}

Nós ({len(nodes)}):
"""
    for n in nodes:
        nd = n.get("data", {})
        analysis_prompt += f"- [{n.get('type')}] {nd.get('label', 'sem label')}"
        if nd.get("prompt"):
            analysis_prompt += f" | prompt: {nd['prompt'][:200]}"
        analysis_prompt += "\n"

    analysis_prompt += f"\nConexões ({len(edges)}):\n"
    for e in edges:
        analysis_prompt += f"- {e.get('source')} → {e.get('target')}\n"

    analysis_prompt += """
Retorne um JSON com:
{
  "summary": "resumo geral em português",
  "suggestions": [
    {
      "type": "prompt_improvement" | "structure" | "missing_node" | "performance",
      "node_id": "id do nó afetado ou null",
      "title": "título curto",
      "description": "descrição da melhoria",
      "suggested_change": "mudança sugerida (texto do prompt melhorado, novo nó, etc.)",
      "impact": "high" | "medium" | "low"
    }
  ]
}
Responda SOMENTE o JSON, sem markdown.
"""

    response_text = ""
    try:
        from app.services.ai.agent_clients import (
            init_anthropic_client,
            call_anthropic_async,
        )
        from app.services.ai.model_registry import get_api_model_name

        client = init_anthropic_client()
        if not client:
            raise HTTPException(
                status_code=500, detail="LLM client indisponível"
            )

        response_text = await call_anthropic_async(
            client=client,
            prompt=analysis_prompt,
            model=get_api_model_name("claude-4.5-sonnet"),
            max_tokens=2000,
            temperature=0.3,
            system_instruction="Você é um especialista em otimização de workflows jurídicos. Analise e sugira melhorias práticas.",
        )

        if not response_text:
            return WorkflowImproveResponse(
                suggestions=[],
                summary="Não foi possível obter análise do modelo",
            )

        # Try to parse JSON from response
        clean = response_text.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        result_data = json.loads(clean)

        return WorkflowImproveResponse(
            suggestions=result_data.get("suggestions", []),
            summary=result_data.get("summary", "Análise concluída"),
        )
    except json.JSONDecodeError:
        return WorkflowImproveResponse(
            suggestions=[],
            summary=response_text[:500] if response_text else "Erro na análise",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[ImproveWorkflow] Error: {e}")
        raise HTTPException(status_code=500, detail="Erro ao analisar workflow")


class GenerateFromNLRequest(BaseModel):
    description: str = Field(..., min_length=10, max_length=5000)
    model: str = "claude"


@router.post("/generate-from-nl")
async def generate_from_nl(
    request: GenerateFromNLRequest,
    current_user: User = Depends(get_current_user),
):
    """Generate a workflow graph from a natural language description using AI."""
    from app.services.ai.nl_to_graph import NLToGraphParser

    parser = NLToGraphParser()
    try:
        graph = await parser.parse(request.description, model=request.model)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error(f"[Workflows] generate-from-nl error: {e}")
        raise HTTPException(status_code=500, detail="Erro ao gerar workflow. Tente novamente.")

    return {"graph_json": graph}


# ---------------------------------------------------------------------------
# Admin Monitoring Dashboard
# ---------------------------------------------------------------------------


@router.get("/admin/dashboard")
async def admin_dashboard(
    current_user: User = Depends(require_role("ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    """Get admin dashboard data for all workflows in the organization."""
    org_id = getattr(current_user, "organization_id", None)

    # Scope to user's organization or own workflows only
    stmt = select(Workflow).where(Workflow.is_active == True)
    if org_id:
        stmt = stmt.where(Workflow.organization_id == org_id)
    else:
        stmt = stmt.where(Workflow.user_id == str(current_user.id))
    stmt = stmt.order_by(Workflow.updated_at.desc()).limit(100)

    result = await db.execute(stmt)
    workflows = result.scalars().all()

    # Compute counts per status
    by_status: Dict[str, int] = {}
    for w in workflows:
        status = getattr(w, "status", "draft") or "draft"
        by_status[status] = by_status.get(status, 0) + 1

    return {
        "workflows": [
            {
                "id": w.id,
                "name": w.name,
                "status": getattr(w, "status", "draft") or "draft",
                "category": getattr(w, "category", None),
                "run_count": getattr(w, "run_count", 0) or 0,
                "created_by": w.user_id,
                "updated_at": w.updated_at.isoformat() if w.updated_at else None,
            }
            for w in workflows
        ],
        "total": len(workflows),
        "by_status": by_status,
    }


@router.get("/admin/approval-queue")
async def approval_queue(
    current_user: User = Depends(require_role("ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    """Get workflows pending approval."""
    org_id = getattr(current_user, "organization_id", None)

    # Scope to user's organization
    stmt = select(Workflow).where(Workflow.status == "pending_approval")
    if org_id:
        stmt = stmt.where(Workflow.organization_id == org_id)
    else:
        stmt = stmt.where(Workflow.user_id == str(current_user.id))
    stmt = stmt.order_by(Workflow.submitted_at.desc())
    result = await db.execute(stmt)
    workflows = result.scalars().all()
    return {
        "pending": [
            {
                "id": w.id,
                "name": w.name,
                "submitted_by": getattr(w, "submitted_by", None),
                "submitted_at": w.submitted_at.isoformat() if getattr(w, "submitted_at", None) else None,
                "description": w.description,
            }
            for w in workflows
        ],
        "count": len(workflows),
    }


@router.get("/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(
    workflow_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a workflow by ID."""
    workflow = await _get_user_workflow(workflow_id, current_user, db)
    return _workflow_to_response(workflow)


@router.put("/{workflow_id}", response_model=WorkflowResponse)
async def update_workflow(
    workflow_id: str,
    request: WorkflowUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a workflow."""
    workflow = await _get_user_workflow(workflow_id, current_user, db)

    if request.graph_json is not None:
        nodes = (request.graph_json or {}).get("nodes", [])
        if nodes:
            errors = validate_graph(request.graph_json)
            if errors:
                raise HTTPException(status_code=422, detail={"validation_errors": errors})
        workflow.graph_json = request.graph_json

    if request.name is not None:
        workflow.name = request.name
    if request.description is not None:
        workflow.description = request.description
    if request.tags is not None:
        workflow.tags = request.tags
    if request.is_active is not None:
        workflow.is_active = request.is_active
    if request.category is not None:
        workflow.category = request.category
    if request.practice_area is not None:
        workflow.practice_area = request.practice_area
    if request.output_type is not None:
        workflow.output_type = request.output_type

    await db.commit()
    await db.refresh(workflow)
    return _workflow_to_response(workflow)


@router.delete("/{workflow_id}", status_code=204)
async def delete_workflow(
    workflow_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a workflow."""
    workflow = await _get_user_workflow(workflow_id, current_user, db)
    await db.delete(workflow)
    await db.commit()


# ---------------------------------------------------------------------------
# Embedded Files
# ---------------------------------------------------------------------------


@router.get("/{workflow_id}/files")
async def list_workflow_files(
    workflow_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List embedded files for a workflow."""
    workflow = await _get_user_workflow(workflow_id, current_user, db)
    return {"files": workflow.embedded_files or [], "count": len(workflow.embedded_files or [])}


@router.post("/{workflow_id}/files")
async def upload_workflow_file(
    workflow_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload a file to embed in a workflow (max 50 files, max 10MB each)."""
    workflow = await _get_user_workflow(workflow_id, current_user, db)

    current_files = list(workflow.embedded_files or [])
    if len(current_files) >= 50:
        raise HTTPException(400, "Maximum 50 embedded files per workflow")

    # Read file content with size limit (10MB)
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(413, f"File too large (max {MAX_FILE_SIZE // (1024*1024)}MB)")
    file_id = str(uuid.uuid4())

    # Store file (use simple local storage for now)
    import os
    storage_dir = os.path.join(os.path.dirname(__file__), "..", "..", "storage", "workflow_files")
    os.makedirs(storage_dir, exist_ok=True)
    storage_path = os.path.join(storage_dir, file_id)
    with open(storage_path, "wb") as f:
        f.write(content)

    file_meta = {
        "id": file_id,
        "name": file.filename or "unnamed",
        "size": len(content),
        "mime_type": file.content_type or "application/octet-stream",
        "storage_ref": file_id,
        "uploaded_at": utcnow().isoformat(),
    }

    current_files.append(file_meta)
    workflow.embedded_files = current_files
    await db.commit()

    return {"file": file_meta, "total": len(current_files)}


@router.delete("/{workflow_id}/files/{file_id}")
async def remove_workflow_file(
    workflow_id: str,
    file_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove an embedded file from a workflow."""
    workflow = await _get_user_workflow(workflow_id, current_user, db)

    current_files = list(workflow.embedded_files or [])
    new_files = [f for f in current_files if f.get("id") != file_id]

    if len(new_files) == len(current_files):
        raise HTTPException(404, "File not found")

    # Validate file_id is a safe UUID before using in path
    import os
    import re as _re
    if not _re.match(r'^[0-9a-f\-]{36}$', file_id):
        raise HTTPException(400, "Invalid file ID format")

    # Clean up storage
    storage_dir = os.path.join(os.path.dirname(__file__), "..", "..", "storage", "workflow_files")
    storage_path = os.path.join(storage_dir, file_id)
    # Extra safety: ensure resolved path stays within storage_dir
    if not os.path.realpath(storage_path).startswith(os.path.realpath(storage_dir)):
        raise HTTPException(400, "Invalid file path")
    if os.path.exists(storage_path):
        os.remove(storage_path)

    workflow.embedded_files = new_files
    await db.commit()

    return {"status": "ok", "remaining": len(new_files)}


# ---------------------------------------------------------------------------
# Versioning
# ---------------------------------------------------------------------------


class CreateVersionRequest(BaseModel):
    change_notes: Optional[str] = None


@router.post("/{workflow_id}/versions")
async def create_version(
    workflow_id: str,
    request: CreateVersionRequest = CreateVersionRequest(),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new version snapshot of the workflow."""
    workflow = await _get_user_workflow(workflow_id, current_user, db)

    # Get next version number
    result = await db.execute(
        select(func.max(WorkflowVersion.version)).where(
            WorkflowVersion.workflow_id == workflow_id
        )
    )
    max_version = result.scalar() or 0

    version = WorkflowVersion(
        id=str(uuid.uuid4()),
        workflow_id=workflow_id,
        version=max_version + 1,
        graph_json=workflow.graph_json,
        embedded_files=workflow.embedded_files or [],
        change_notes=request.change_notes,
        created_by=str(current_user.id),
    )
    db.add(version)
    await db.commit()
    return version.to_dict()


@router.get("/{workflow_id}/versions")
async def list_versions(
    workflow_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all versions of a workflow."""
    await _get_user_workflow(workflow_id, current_user, db)
    stmt = (
        select(WorkflowVersion)
        .where(WorkflowVersion.workflow_id == workflow_id)
        .order_by(WorkflowVersion.version.desc())
    )
    result = await db.execute(stmt)
    versions = result.scalars().all()
    return [v.to_dict() for v in versions]


@router.get("/{workflow_id}/versions/{version_number}")
async def get_version(
    workflow_id: str,
    version_number: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific version of a workflow."""
    await _get_user_workflow(workflow_id, current_user, db)
    stmt = select(WorkflowVersion).where(
        WorkflowVersion.workflow_id == workflow_id,
        WorkflowVersion.version == version_number,
    )
    result = await db.execute(stmt)
    version = result.scalar_one_or_none()
    if not version:
        raise HTTPException(404, f"Version {version_number} not found")
    return version.to_dict()


@router.post("/{workflow_id}/versions/{version_number}/restore")
async def restore_version(
    workflow_id: str,
    version_number: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Restore a workflow to a previous version."""
    workflow = await _get_user_workflow(workflow_id, current_user, db)
    stmt = select(WorkflowVersion).where(
        WorkflowVersion.workflow_id == workflow_id,
        WorkflowVersion.version == version_number,
    )
    result = await db.execute(stmt)
    version = result.scalar_one_or_none()
    if not version:
        raise HTTPException(404, f"Version {version_number} not found")

    workflow.graph_json = version.graph_json
    workflow.embedded_files = version.embedded_files
    await db.commit()
    return {"status": "restored", "version": version_number}


# ---------------------------------------------------------------------------
# Publishing & Approval
# ---------------------------------------------------------------------------


class SubmitForApprovalRequest(BaseModel):
    notes: Optional[str] = None


@router.post("/{workflow_id}/submit")
async def submit_for_approval(
    workflow_id: str,
    request: SubmitForApprovalRequest = SubmitForApprovalRequest(),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Submit workflow for admin approval."""
    workflow = await _get_user_workflow(workflow_id, current_user, db)
    if workflow.status not in ("draft", "rejected"):
        raise HTTPException(400, f"Cannot submit workflow with status '{workflow.status}'")
    workflow.status = "pending_approval"
    workflow.submitted_at = utcnow()
    workflow.submitted_by = str(current_user.id)
    await db.commit()
    return {"status": "pending_approval", "submitted_at": workflow.submitted_at.isoformat()}


class ApprovalDecision(BaseModel):
    approved: bool
    reason: Optional[str] = None


@router.post("/{workflow_id}/approve")
async def approve_workflow(
    workflow_id: str,
    decision: ApprovalDecision,
    current_user: User = Depends(require_role("ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    """Approve or reject a workflow (admin only)."""
    # Check org first to avoid leaking workflow existence
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(403, "Organization membership required for approvals")

    result = await db.execute(
        select(Workflow).where(
            Workflow.id == workflow_id,
            Workflow.organization_id == org_id,
        )
    )
    workflow = result.scalar_one_or_none()
    if not workflow:
        raise HTTPException(404, "Workflow not found")
    if workflow.status != "pending_approval":
        raise HTTPException(400, "Workflow is not pending approval")
    if decision.approved:
        workflow.status = "approved"
        workflow.approved_at = utcnow()
        workflow.approved_by = str(current_user.id)
        workflow.rejection_reason = None
    else:
        workflow.status = "rejected"
        workflow.rejection_reason = decision.reason
    await db.commit()
    return {"status": workflow.status}


class PublishWorkflowRequest(BaseModel):
    slug: Optional[str] = None  # custom URL slug, auto-generated if empty
    title: Optional[str] = None  # display title (defaults to workflow name)
    description: Optional[str] = None
    require_auth: bool = True  # require login to access
    allow_org: bool = True  # allow anyone in org


def _slugify(text: str) -> str:
    """Generate a URL-safe slug from text."""
    import re
    import unicodedata
    slug = unicodedata.normalize("NFD", text.lower())
    slug = re.sub(r"[\u0300-\u036f]", "", slug)
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")[:60]
    return slug or "workflow"


@router.post("/{workflow_id}/publish")
async def publish_workflow(
    workflow_id: str,
    request: PublishWorkflowRequest = PublishWorkflowRequest(),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Publish workflow as a standalone app with a dedicated URL."""
    workflow = await _get_user_workflow(workflow_id, current_user, db)

    # Determine slug
    slug = request.slug.strip() if request.slug else None
    if not slug:
        slug = _slugify(workflow.name)

    # Sanitize slug
    import re
    slug = re.sub(r"[^a-z0-9-]", "-", slug.lower()).strip("-")[:60]
    if not slug:
        slug = f"workflow-{workflow_id[:8]}"

    # Check slug uniqueness (skip if same workflow already has this slug)
    existing = await db.execute(
        select(Workflow).where(
            Workflow.published_slug == slug,
            Workflow.id != workflow_id,
        )
    )
    if existing.scalar_one_or_none():
        # Append short id to make unique
        slug = f"{slug}-{workflow_id[:8]}"

    # Store publish config
    workflow.published_slug = slug
    workflow.published_config = {
        "title": request.title or workflow.name,
        "description": request.description or workflow.description or "",
        "require_auth": request.require_auth,
        "allow_org": request.allow_org,
    }

    # Set status to published
    current_version = workflow.published_version or 0
    workflow.status = "published"
    workflow.published_version = current_version + 1

    await db.commit()
    return {
        "status": "published",
        "version": workflow.published_version,
        "slug": workflow.published_slug,
        "app_url": f"/app/{workflow.published_slug}",
    }


@router.post("/{workflow_id}/unpublish")
async def unpublish_workflow(
    workflow_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Unpublish a workflow, removing its standalone app URL."""
    workflow = await _get_user_workflow(workflow_id, current_user, db)
    workflow.published_slug = None
    workflow.published_config = None
    workflow.status = "draft"
    await db.commit()
    return {"status": "unpublished"}


@router.get("/app/{slug}")
async def get_published_workflow(
    slug: str,
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """Get a published workflow by its slug for the standalone app runner."""
    result = await db.execute(
        select(Workflow).where(
            Workflow.published_slug == slug,
            Workflow.is_active == True,
        )
    )
    workflow = result.scalar_one_or_none()
    if not workflow:
        raise HTTPException(404, "App not found")

    config = workflow.published_config or {}

    # Check auth requirements
    if config.get("require_auth", True) and not current_user:
        raise HTTPException(401, "Authentication required to access this app")

    # Check access control (owner always has access)
    if current_user and workflow.user_id != str(current_user.id):
        if config.get("allow_org", True):
            # Org mode: org members can access
            if not (
                workflow.organization_id
                and workflow.organization_id == getattr(current_user, "organization_id", None)
            ):
                raise HTTPException(403, "You don't have access to this app")
        else:
            # Private mode: only owner can access
            raise HTTPException(403, "You don't have access to this app")

    return {
        "id": workflow.id,
        "name": config.get("title", workflow.name),
        "description": config.get("description", workflow.description or ""),
        "slug": workflow.published_slug,
        "graph_json": workflow.graph_json,
        "require_auth": config.get("require_auth", True),
    }


@router.post("/{workflow_id}/archive")
async def archive_workflow(
    workflow_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Archive a workflow."""
    workflow = await _get_user_workflow(workflow_id, current_user, db)
    workflow.status = "archived"
    await db.commit()
    return {"status": "archived"}


# ---------------------------------------------------------------------------
# Execution Endpoints
# ---------------------------------------------------------------------------


@router.post("/{workflow_id}/run")
async def run_workflow(
    workflow_id: str,
    request: RunWorkflowRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Execute a workflow with SSE streaming."""
    workflow = await _get_user_workflow(workflow_id, current_user, db)

    # Inject context session if provided
    input_data = dict(request.input_data)
    # Inject user_id for per-user credential resolution (PJe, etc.)
    input_data["user_id"] = str(current_user.id)
    if request.context_session_id:
        from app.services.unified_context_store import unified_context
        ctx_str = await unified_context.get_context_string(
            str(current_user.id), request.context_session_id
        )
        if ctx_str:
            input_data["input"] = f"{input_data.get('input', '')}\n\n## Contexto\n{ctx_str}"

    # Increment run count
    workflow.run_count = (workflow.run_count or 0) + 1

    # Create run record
    run = WorkflowRun(
        id=str(uuid.uuid4()),
        workflow_id=workflow.id,
        user_id=str(current_user.id),
        status=WorkflowRunStatus.RUNNING,
        input_data=input_data,
        started_at=utcnow(),
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    runner = WorkflowRunner(db=db)

    async def event_generator():
        final_status = WorkflowRunStatus.COMPLETED
        try:
            async for event in runner.run_streaming(
                graph_json=workflow.graph_json,
                input_data=input_data,
                job_id=run.id,
                run_id=run.id,
            ):
                event_type = event.get("type", "message")
                yield sse_line(event, event=event_type)

                # Detect HIL pause
                data = event.get("data", {})
                if data.get("status") == "paused_hil":
                    final_status = WorkflowRunStatus.PAUSED_HIL
                    run.current_node = data.get("node_id")
                elif data.get("error"):
                    final_status = WorkflowRunStatus.ERROR
                    run.error_message = data.get("error")

        except Exception as e:
            final_status = WorkflowRunStatus.ERROR
            run.error_message = str(e)
            yield sse_line({"error": str(e)}, event="error")

        # Update run status
        run.status = final_status
        if final_status in (WorkflowRunStatus.COMPLETED, WorkflowRunStatus.ERROR):
            run.completed_at = utcnow()
        await db.commit()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@router.post("/{workflow_id}/test")
async def test_workflow(
    workflow_id: str,
    request: RunWorkflowRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Test a workflow without creating a persistent run record."""
    workflow = await _get_user_workflow(workflow_id, current_user, db)

    input_data = dict(request.input_data)
    input_data["user_id"] = str(current_user.id)
    if request.context_session_id:
        from app.services.unified_context_store import unified_context
        ctx_str = await unified_context.get_context_string(
            str(current_user.id), request.context_session_id
        )
        if ctx_str:
            input_data["input"] = f"{input_data.get('input', '')}\n\n## Contexto\n{ctx_str}"

    # Create transient run (trigger_type=test)
    run = WorkflowRun(
        id=str(uuid.uuid4()),
        workflow_id=workflow.id,
        user_id=str(current_user.id),
        status=WorkflowRunStatus.RUNNING,
        input_data=input_data,
        trigger_type="test",
        started_at=utcnow(),
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    runner = WorkflowRunner(db=db)

    async def event_generator():
        final_status = WorkflowRunStatus.COMPLETED
        try:
            async for event in runner.run_streaming(
                graph_json=workflow.graph_json,
                input_data=input_data,
                job_id=run.id,
                run_id=run.id,
            ):
                event_type = event.get("type", "message")
                yield sse_line(event, event=event_type)

                data = event.get("data", {})
                if data.get("status") == "paused_hil":
                    final_status = WorkflowRunStatus.PAUSED_HIL
                    run.current_node = data.get("node_id")
                elif data.get("error"):
                    final_status = WorkflowRunStatus.ERROR
                    run.error_message = data.get("error")
        except Exception as e:
            final_status = WorkflowRunStatus.ERROR
            run.error_message = str(e)
            yield sse_line({"error": str(e)}, event="error")

        run.status = final_status
        if final_status in (WorkflowRunStatus.COMPLETED, WorkflowRunStatus.ERROR):
            run.completed_at = utcnow()
        await db.commit()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@router.get("/runs/{run_id}/export/{format}")
async def export_run(
    run_id: str,
    format: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Export a workflow run result in the specified format (docx, xlsx, pdf)."""
    run = await _get_user_run(run_id, current_user, db)

    if run.status != WorkflowRunStatus.COMPLETED:
        raise HTTPException(400, "Só é possível exportar execuções concluídas")

    mime_types = {
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "pdf": "application/pdf",
    }

    if format not in mime_types:
        raise HTTPException(400, f"Formato não suportado: {format}. Use docx, xlsx ou pdf")

    from app.services.workflow_export_service import WorkflowExportService

    svc = WorkflowExportService()

    run_data = {
        "input_data": run.input_data or {},
        "output_data": run.output_data or {},
        "logs": run.logs or [],
        "status": run.status.value,
    }

    # Get workflow name for the filename
    workflow = await db.get(Workflow, run.workflow_id)
    run_data["workflow_name"] = workflow.name if workflow else "workflow"

    try:
        export_fn = getattr(svc, f"export_to_{format}")
        buffer = await export_fn(run_data)
    except RuntimeError as e:
        raise HTTPException(500, str(e))

    from fastapi.responses import Response

    filename = f"{run_data['workflow_name']}_{run_id[:8]}.{format}"
    return Response(
        content=buffer.getvalue(),
        media_type=mime_types[format],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/runs/{run_id}/resume")
async def resume_workflow_run(
    run_id: str,
    request: ResumeHILRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Resume a paused workflow run after HIL approval."""
    run = await _get_user_run(run_id, current_user, db)

    if run.status != WorkflowRunStatus.PAUSED_HIL:
        raise HTTPException(
            status_code=400,
            detail=f"Run not paused (status: {run.status.value})",
        )

    # Get workflow
    workflow = await db.get(Workflow, run.workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    runner = WorkflowRunner(db=db)
    run.status = WorkflowRunStatus.RUNNING

    async def event_generator():
        final_status = WorkflowRunStatus.COMPLETED
        try:
            async for event in runner.resume_after_hil(
                graph_json=workflow.graph_json,
                state_snapshot=run.state_snapshot or run.input_data,  # fallback to input_data if no snapshot (first pause)
                approved=request.approved,
                human_edits=request.human_edits,
                job_id=run.id,
                user_id=str(current_user.id),
            ):
                yield sse_line(event)

                data = event.get("data", {})
                if data.get("status") == "paused_hil":
                    final_status = WorkflowRunStatus.PAUSED_HIL
                    run.current_node = data.get("node_id")
                elif data.get("error"):
                    final_status = WorkflowRunStatus.ERROR

        except Exception as e:
            final_status = WorkflowRunStatus.ERROR
            run.error_message = str(e)
            yield sse_line({"error": str(e)}, event="error")

        run.status = final_status
        if final_status in (WorkflowRunStatus.COMPLETED, WorkflowRunStatus.ERROR):
            run.completed_at = utcnow()
        await db.commit()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@router.post("/runs/{run_id}/follow-up")
async def follow_up_run(
    run_id: str,
    request: FollowUpRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Ask a follow-up question about a completed run."""
    run = await _get_user_run(run_id, current_user, db)

    if run.status != WorkflowRunStatus.COMPLETED:
        raise HTTPException(400, "Follow-ups só estão disponíveis para execuções concluídas")

    # Build context from run output (truncate to 8k chars)
    context = json.dumps(run.output_data or {}, ensure_ascii=False)[:8000]

    async def stream():
        try:
            from app.services.ai.agent_clients import (
                init_anthropic_client,
                stream_anthropic_async,
            )
            from app.services.ai.model_registry import get_api_model_name

            client = init_anthropic_client()
            if not client:
                yield sse_line({"type": "error", "data": {"error": "LLM client indisponível"}})
                return

            prompt = (
                f"Baseado no resultado do workflow:\n\n{context}\n\n"
                f"Pergunta do usuário: {request.question}"
            )
            system_instruction = (
                "Você é um assistente jurídico. Responda perguntas sobre o resultado "
                "de um workflow de forma clara e objetiva em português brasileiro."
            )

            accumulated = ""
            async for chunk in stream_anthropic_async(
                client=client,
                prompt=prompt,
                model=get_api_model_name("claude-4.5-sonnet"),
                max_tokens=4000,
                temperature=0.3,
                system_instruction=system_instruction,
            ):
                if isinstance(chunk, dict):
                    token = chunk.get("token", chunk.get("content", ""))
                else:
                    token = str(chunk)
                if token:
                    accumulated += token
                    yield sse_line({"type": "token", "data": {"token": token}})

            yield sse_line({"type": "done", "data": {"status": "completed"}})
        except Exception as e:
            yield sse_line({"type": "error", "data": {"error": str(e)}})

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@router.post("/runs/{run_id}/share")
async def share_run(
    run_id: str,
    request: ShareRunRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Share a workflow run output with other users."""
    run = await _get_user_run(run_id, current_user, db)

    # Store share record in output_data
    shares = run.output_data.get("_shares", []) if run.output_data else []
    for uid in request.user_ids:
        shares.append({
            "user_id": uid,
            "shared_by": str(current_user.id),
            "shared_at": utcnow().isoformat(),
            "message": request.message,
        })

    if not run.output_data:
        run.output_data = {}
    run.output_data["_shares"] = shares
    await db.commit()

    return {"status": "shared", "shared_with": request.user_ids}


class ShareRunOrgRequest(BaseModel):
    message: Optional[str] = None


@router.post("/runs/{run_id}/share-org")
async def share_run_with_org(
    run_id: str,
    request: ShareRunOrgRequest = ShareRunOrgRequest(),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Share a workflow run output with the entire organization."""
    run = await _get_user_run(run_id, current_user, db)

    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(400, "Usuário não pertence a uma organização")

    # Store org-wide share in output_data
    shares = run.output_data.get("_shares", []) if run.output_data else []
    shares.append({
        "organization_id": org_id,
        "shared_by": str(current_user.id),
        "shared_at": utcnow().isoformat(),
        "message": request.message,
        "org_wide": True,
    })

    if not run.output_data:
        run.output_data = {}
    run.output_data["_shares"] = shares
    await db.commit()

    return {"status": "shared", "organization_id": org_id}


@router.get("/{workflow_id}/audit")
async def get_workflow_audit(
    workflow_id: str = Path(...),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get audit trail of all runs for a workflow with user info."""
    # Verify access (owner or same org)
    result = await db.execute(
        select(Workflow).where(
            Workflow.id == workflow_id,
            or_(
                Workflow.user_id == str(current_user.id),
                Workflow.organization_id == current_user.organization_id,
            ),
        )
    )
    workflow = result.scalar_one_or_none()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    # Query runs with user join, ordered by most recent
    offset = (page - 1) * limit
    stmt = (
        select(WorkflowRun, User)
        .join(User, WorkflowRun.user_id == User.id)
        .where(WorkflowRun.workflow_id == workflow_id)
        .order_by(WorkflowRun.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(stmt)
    rows = result.all()

    # Count total
    count_stmt = select(func.count()).select_from(WorkflowRun).where(
        WorkflowRun.workflow_id == workflow_id
    )
    total = (await db.execute(count_stmt)).scalar() or 0

    items = []
    for run, user in rows:
        # Compute duration
        duration_ms = None
        if run.started_at and run.completed_at:
            delta = run.completed_at - run.started_at
            duration_ms = int(delta.total_seconds() * 1000)

        # Summarize input (first 200 chars)
        input_summary = ""
        if run.input_data:
            input_text = run.input_data.get("input", "")
            if not input_text and isinstance(run.input_data, dict):
                input_text = json.dumps(run.input_data, ensure_ascii=False)
            input_summary = str(input_text)[:200]

        # Summarize output (first 200 chars)
        output_summary = ""
        if run.output_data:
            out = run.output_data.get("output", run.output_data.get("result", ""))
            if not out and isinstance(run.output_data, dict):
                out = json.dumps(run.output_data, ensure_ascii=False)
            output_summary = str(out)[:200]

        items.append({
            "id": run.id,
            "user_name": user.name,
            "user_email": user.email,
            "started_at": run.started_at.isoformat() if run.started_at else run.created_at.isoformat(),
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            "status": run.status.value if hasattr(run.status, "value") else str(run.status),
            "input_summary": input_summary,
            "output_summary": output_summary,
            "duration_ms": duration_ms,
            "error_message": run.error_message,
            "trigger_type": run.trigger_type or "manual",
        })

    return {
        "items": items,
        "total": total,
        "page": page,
        "limit": limit,
        "pages": (total + limit - 1) // limit if limit else 1,
    }


@router.get("/{workflow_id}/runs", response_model=List[WorkflowRunResponse])
async def list_workflow_runs(
    workflow_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all runs for a workflow."""
    await _get_user_workflow(workflow_id, current_user, db)

    stmt = (
        select(WorkflowRun)
        .where(
            WorkflowRun.workflow_id == workflow_id,
            WorkflowRun.user_id == str(current_user.id),
        )
        .order_by(WorkflowRun.created_at.desc())
        .limit(50)
    )
    result = await db.execute(stmt)
    runs = result.scalars().all()
    return [_run_to_response(r) for r in runs]


# ---------------------------------------------------------------------------
# Schedule / Trigger Endpoints
# ---------------------------------------------------------------------------


class ScheduleConfig(BaseModel):
    cron: Optional[str] = Field(
        None, description="Cron expression e.g. '0 6 * * *'", max_length=100
    )
    enabled: bool = False
    timezone: str = "America/Sao_Paulo"


@router.get("/{workflow_id}/schedule")
async def get_schedule(
    workflow_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get schedule configuration for a workflow."""
    wf = await _get_user_workflow(workflow_id, current_user, db)
    return {
        "cron": wf.schedule_cron,
        "enabled": wf.schedule_enabled,
        "timezone": wf.schedule_timezone or "America/Sao_Paulo",
        "last_run": (
            wf.last_scheduled_run.isoformat() if wf.last_scheduled_run else None
        ),
        "webhook_url": (
            f"/workflows/{workflow_id}/trigger" if wf.webhook_secret else None
        ),
    }


@router.put("/{workflow_id}/schedule")
async def update_schedule(
    workflow_id: str,
    config: ScheduleConfig,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update schedule configuration for a workflow."""
    wf = await _get_user_workflow(workflow_id, current_user, db)

    # Validate cron expression
    if config.cron:
        try:
            from croniter import croniter

            croniter(config.cron)
        except (ValueError, KeyError):
            raise HTTPException(400, "Invalid cron expression")

    wf.schedule_cron = config.cron
    wf.schedule_enabled = config.enabled
    wf.schedule_timezone = config.timezone
    await db.commit()
    return {"status": "ok", "schedule": config.model_dump()}


@router.post("/{workflow_id}/trigger")
async def webhook_trigger(
    workflow_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Trigger a workflow via webhook. Requires X-Webhook-Secret header."""
    wf = await db.get(Workflow, workflow_id)
    if not wf or not wf.is_active:
        raise HTTPException(404, "Workflow not found")

    # Verify webhook secret
    secret = request.headers.get("X-Webhook-Secret", "")
    if not wf.webhook_secret or not hmac.compare_digest(secret, wf.webhook_secret):
        raise HTTPException(403, "Invalid webhook secret")

    # Parse optional input data
    try:
        input_data = await request.json()
    except Exception:
        input_data = {}

    from app.workers.tasks.workflow_tasks import run_webhook_workflow

    # Inject workflow owner's user_id for per-user credential resolution
    input_data["user_id"] = wf.user_id
    result = run_webhook_workflow.delay(wf.id, wf.user_id, input_data)

    return {"status": "accepted", "task_id": result.id}


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------


class GrantPermissionRequest(BaseModel):
    user_id: str
    build_access: str = "none"  # none, view, edit, full
    run_access: str = "none"    # none, run


@router.get("/{workflow_id}/permissions")
async def list_permissions(
    workflow_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all permissions for a workflow."""
    await _get_user_workflow(workflow_id, current_user, db)
    from app.services.workflow_permission_service import WorkflowPermissionService
    svc = WorkflowPermissionService(db)
    return await svc.list_permissions(workflow_id)


@router.post("/{workflow_id}/permissions")
async def grant_permission(
    workflow_id: str,
    request: GrantPermissionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Grant access to a user for this workflow."""
    await _get_user_workflow(workflow_id, current_user, db)
    from app.services.workflow_permission_service import WorkflowPermissionService
    from app.models.workflow_permission import BuildAccess, RunAccess
    svc = WorkflowPermissionService(db)
    perm = await svc.grant_access(
        workflow_id=workflow_id,
        user_id=request.user_id,
        granted_by=str(current_user.id),
        build=BuildAccess(request.build_access),
        run=RunAccess(request.run_access),
    )
    await db.commit()
    return perm.to_dict()


@router.delete("/{workflow_id}/permissions/{user_id}")
async def revoke_permission(
    workflow_id: str,
    user_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke a user's access to this workflow."""
    await _get_user_workflow(workflow_id, current_user, db)
    from app.services.workflow_permission_service import WorkflowPermissionService
    svc = WorkflowPermissionService(db)
    revoked = await svc.revoke_access(workflow_id, user_id)
    await db.commit()
    if not revoked:
        raise HTTPException(404, "Permission not found")
    return {"status": "revoked"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_user_workflow(
    workflow_id: str, user: User, db: AsyncSession
) -> Workflow:
    workflow = await db.get(Workflow, workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    if workflow.user_id != str(user.id):
        raise HTTPException(status_code=403, detail="Not authorized")
    return workflow


async def _get_user_run(
    run_id: str, user: User, db: AsyncSession
) -> WorkflowRun:
    run = await db.get(WorkflowRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.user_id != str(user.id):
        raise HTTPException(status_code=403, detail="Not authorized")
    return run


def _workflow_to_response(w: Workflow) -> WorkflowResponse:
    return WorkflowResponse(
        id=w.id,
        user_id=w.user_id,
        name=w.name,
        description=w.description,
        graph_json=w.graph_json,
        is_active=w.is_active,
        is_template=w.is_template,
        tags=w.tags or [],
        embedded_files=w.embedded_files or [],
        status=getattr(w, "status", None) or "draft",
        published_version=getattr(w, "published_version", None),
        submitted_at=w.submitted_at.isoformat() if getattr(w, "submitted_at", None) else None,
        approved_at=w.approved_at.isoformat() if getattr(w, "approved_at", None) else None,
        rejection_reason=getattr(w, "rejection_reason", None),
        published_slug=getattr(w, "published_slug", None),
        published_config=getattr(w, "published_config", None),
        category=getattr(w, "category", None),
        practice_area=getattr(w, "practice_area", None),
        output_type=getattr(w, "output_type", None),
        run_count=getattr(w, "run_count", None) or 0,
        created_at=w.created_at.isoformat() if w.created_at else "",
        updated_at=w.updated_at.isoformat() if w.updated_at else "",
    )


def _run_to_response(r: WorkflowRun) -> WorkflowRunResponse:
    return WorkflowRunResponse(
        id=r.id,
        workflow_id=r.workflow_id,
        status=r.status.value,
        input_data=r.input_data or {},
        output_data=r.output_data,
        current_node=r.current_node,
        logs=r.logs or [],
        error_message=r.error_message,
        started_at=r.started_at.isoformat() if r.started_at else None,
        completed_at=r.completed_at.isoformat() if r.completed_at else None,
        created_at=r.created_at.isoformat() if r.created_at else "",
    )
