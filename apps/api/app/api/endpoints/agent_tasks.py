"""
Agent Tasks — Endpoints for spawning and managing background Claude agents.

POST   /agent/spawn       — Start a background agent task
GET    /agent/tasks        — List user's tasks
GET    /agent/tasks/{id}   — Get task status/result
DELETE /agent/tasks/{id}   — Cancel a running task
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.services.ai.claude_agent.parallel_agents import agent_pool

router = APIRouter()


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class SpawnAgentRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=10000)
    model: str = Field(default="claude-sonnet-4-20250514")
    system_prompt: str = Field(default="")
    context: Optional[str] = Field(default=None)
    metadata: Optional[Dict[str, Any]] = Field(default=None)


class SpawnAgentResponse(BaseModel):
    task_id: str
    status: str


class AgentTaskResponse(BaseModel):
    task_id: str
    user_id: str
    prompt: str
    status: str
    result: Optional[str] = None
    error: Optional[str] = None
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    model: str
    metadata: Dict[str, Any] = {}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/spawn", response_model=SpawnAgentResponse)
async def spawn_agent(
    request: SpawnAgentRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Spawn a background Claude agent task."""
    try:
        task_id = await agent_pool.spawn(
            user_id=str(current_user.id),
            prompt=request.prompt,
            model=request.model,
            system_prompt=request.system_prompt,
            context=request.context,
            db=db,
            metadata=request.metadata,
        )
        return SpawnAgentResponse(task_id=task_id, status="queued")
    except RuntimeError as e:
        raise HTTPException(status_code=429, detail=str(e))


@router.get("/tasks", response_model=list[AgentTaskResponse])
async def list_agent_tasks(
    current_user: User = Depends(get_current_user),
):
    """List all agent tasks for the current user."""
    tasks = await agent_pool.list_active(user_id=str(current_user.id))
    return tasks


@router.get("/tasks/{task_id}", response_model=AgentTaskResponse)
async def get_agent_task(
    task_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get status and result of an agent task."""
    result = await agent_pool.get_result(task_id)
    if not result:
        raise HTTPException(status_code=404, detail="Task not found")
    if result["user_id"] != str(current_user.id):
        raise HTTPException(status_code=403, detail="Not authorized")
    return result


@router.delete("/tasks/{task_id}")
async def cancel_agent_task(
    task_id: str,
    current_user: User = Depends(get_current_user),
):
    """Cancel a running agent task."""
    cancelled = await agent_pool.cancel(
        task_id=task_id,
        user_id=str(current_user.id),
    )
    if not cancelled:
        raise HTTPException(
            status_code=404,
            detail="Task not found or already completed",
        )
    return {"task_id": task_id, "status": "cancelled"}
