"""
Context Bridge — Endpoints for cross-layer context transfer.

POST /context/promote-to-agent   — Promote chat to background agent
POST /context/export-to-workflow — Export agent result to workflow input
GET  /context/session/{id}       — Get context session items
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.services.unified_context_store import (
    unified_context,
    ContextLayer,
)
from app.services.ai.claude_agent.parallel_agents import agent_pool

router = APIRouter()


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class PromoteToAgentRequest(BaseModel):
    chat_id: Optional[str] = None
    messages: List[Dict[str, Any]] = Field(
        ..., min_length=1, max_length=50,
        description="Last N messages from chat to inject as agent context",
    )
    prompt: str = Field(
        ..., min_length=1, max_length=10000,
        description="Task prompt for the background agent",
    )
    model: str = Field(default="claude-sonnet-4-20250514")
    system_prompt: str = Field(default="")


class PromoteToAgentResponse(BaseModel):
    task_id: str
    session_id: str
    status: str


class ExportToWorkflowRequest(BaseModel):
    agent_task_id: str = Field(..., description="Agent task to export")
    workflow_id: Optional[str] = Field(
        None, description="Target workflow (if known)"
    )


class ExportToWorkflowResponse(BaseModel):
    session_id: str
    agent_result: Optional[str] = None
    status: str


class ContextSessionResponse(BaseModel):
    session_id: str
    items: List[Dict[str, Any]]
    meta: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/promote-to-agent", response_model=PromoteToAgentResponse)
async def promote_to_agent(
    request: PromoteToAgentRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Promote a chat conversation to a background agent.

    Takes the last N messages, creates a unified context session,
    and spawns a background agent with that context injected.
    """
    user_id = str(current_user.id)

    # Create unified context session with chat history
    session_id = await unified_context.promote_chat_to_agent(
        user_id=user_id,
        chat_messages=request.messages,
        chat_id=request.chat_id,
    )

    # Build context string from the chat history
    context_str = await unified_context.get_context_string(
        user_id=user_id,
        session_id=session_id,
    )

    # Spawn background agent with injected context
    try:
        task_id = await agent_pool.spawn(
            user_id=user_id,
            prompt=request.prompt,
            model=request.model,
            system_prompt=request.system_prompt,
            context=context_str,
            db=db,
            metadata={
                "context_session_id": session_id,
                "promoted_from_chat": request.chat_id,
            },
        )
    except RuntimeError as e:
        raise HTTPException(status_code=429, detail=str(e))

    return PromoteToAgentResponse(
        task_id=task_id,
        session_id=session_id,
        status="spawned",
    )


@router.post("/export-to-workflow", response_model=ExportToWorkflowResponse)
async def export_to_workflow(
    request: ExportToWorkflowRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Export a completed agent result to a workflow context session.

    The session_id returned can be used as input_data when running a workflow.
    """
    user_id = str(current_user.id)

    # Get agent task result
    task_data = await agent_pool.get_result(request.agent_task_id)
    if not task_data:
        raise HTTPException(status_code=404, detail="Agent task not found")
    if task_data["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    if task_data["status"] != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"Agent task not completed (status: {task_data['status']})",
        )

    agent_result = task_data.get("result", "")

    # Create workflow context session
    session_id = await unified_context.export_agent_to_workflow(
        user_id=user_id,
        agent_task_id=request.agent_task_id,
        agent_result=agent_result,
        agent_metadata={
            "model": task_data.get("model", ""),
            "prompt": task_data.get("prompt", ""),
            "workflow_id": request.workflow_id,
        },
    )

    return ExportToWorkflowResponse(
        session_id=session_id,
        agent_result=agent_result[:500] if agent_result else None,
        status="exported",
    )


@router.get("/session/{session_id}", response_model=ContextSessionResponse)
async def get_context_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get the contents of a unified context session."""
    user_id = str(current_user.id)

    meta = await unified_context.get_session_meta(user_id, session_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Session not found")

    items = await unified_context.get_items(user_id, session_id)

    return ContextSessionResponse(
        session_id=session_id,
        items=[i.to_dict() for i in items],
        meta=meta,
    )
