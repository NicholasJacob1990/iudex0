"""
Parallel Agents — Background agent execution pool.

Manages spawning, tracking, and cancelling background Claude Agent tasks.
Each user can have up to MAX_AGENTS_PER_USER concurrent agents.
Results are stored in memory with optional Redis persistence.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from loguru import logger

from app.services.job_manager import job_manager


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_AGENTS_PER_USER = 10


class AgentTaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"
    CANCELLED = "cancelled"


@dataclass
class AgentTask:
    """Represents a background agent task."""

    task_id: str
    user_id: str
    prompt: str
    status: AgentTaskStatus = AgentTaskStatus.QUEUED
    result: Optional[str] = None
    error: Optional[str] = None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    model: str = "claude-sonnet-4-20250514"
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Internal — not serialised
    _asyncio_task: Optional[asyncio.Task] = field(  # type: ignore[type-arg]
        default=None, repr=False, compare=False
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "user_id": self.user_id,
            "prompt": self.prompt,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "model": self.model,
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# AgentPool
# ---------------------------------------------------------------------------


class AgentPool:
    """Pool of background Claude Agent tasks per user."""

    def __init__(self) -> None:
        self._tasks: Dict[str, AgentTask] = {}  # task_id → AgentTask
        self._lock = asyncio.Lock()

    # -- public API ----------------------------------------------------------

    async def spawn(
        self,
        user_id: str,
        prompt: str,
        model: str = "claude-sonnet-4-20250514",
        system_prompt: str = "",
        context: Optional[str] = None,
        db: Optional[Any] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Spawn a new background agent task.

        Returns:
            task_id of the spawned task.

        Raises:
            RuntimeError: If the user has reached the max concurrent agents.
        """
        async with self._lock:
            active = self._active_count(user_id)
            if active >= MAX_AGENTS_PER_USER:
                raise RuntimeError(
                    f"Limite de {MAX_AGENTS_PER_USER} agentes simultâneos atingido"
                )

            task_id = str(uuid.uuid4())
            agent_task = AgentTask(
                task_id=task_id,
                user_id=user_id,
                prompt=prompt,
                model=model,
                metadata=metadata or {},
            )
            self._tasks[task_id] = agent_task

        # Launch in background
        loop = asyncio.get_running_loop()
        asyncio_task = loop.create_task(
            self._run_agent(agent_task, system_prompt, context, db)
        )
        agent_task._asyncio_task = asyncio_task

        logger.info(f"[AgentPool] Spawned task {task_id} for user {user_id}")
        return task_id

    async def list_active(self, user_id: str) -> List[Dict[str, Any]]:
        """List all tasks (active and recent) for a user."""
        return [
            t.to_dict()
            for t in self._tasks.values()
            if t.user_id == user_id
        ]

    async def get_result(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get task status and result."""
        task = self._tasks.get(task_id)
        if not task:
            return None
        return task.to_dict()

    async def cancel(self, task_id: str, user_id: str) -> bool:
        """Cancel a running task. Returns True if cancelled."""
        task = self._tasks.get(task_id)
        if not task or task.user_id != user_id:
            return False

        if task.status in (AgentTaskStatus.COMPLETED, AgentTaskStatus.ERROR, AgentTaskStatus.CANCELLED):
            return False

        # Cancel asyncio task
        if task._asyncio_task and not task._asyncio_task.done():
            task._asyncio_task.cancel()

        task.status = AgentTaskStatus.CANCELLED
        task.completed_at = datetime.now(timezone.utc).isoformat()

        logger.info(f"[AgentPool] Cancelled task {task_id}")
        return True

    async def cleanup_old(self, max_age_hours: int = 24) -> int:
        """Remove completed/error/cancelled tasks older than max_age_hours."""
        now = datetime.now(timezone.utc)
        to_remove = []

        for tid, task in self._tasks.items():
            if task.status in (AgentTaskStatus.COMPLETED, AgentTaskStatus.ERROR, AgentTaskStatus.CANCELLED):
                if task.completed_at:
                    completed = datetime.fromisoformat(task.completed_at)
                    if (now - completed).total_seconds() > max_age_hours * 3600:
                        to_remove.append(tid)

        for tid in to_remove:
            del self._tasks[tid]

        return len(to_remove)

    # -- internal ------------------------------------------------------------

    def _active_count(self, user_id: str) -> int:
        return sum(
            1
            for t in self._tasks.values()
            if t.user_id == user_id
            and t.status in (AgentTaskStatus.QUEUED, AgentTaskStatus.RUNNING)
        )

    async def _run_agent(
        self,
        agent_task: AgentTask,
        system_prompt: str,
        context: Optional[str],
        db: Optional[Any],
    ) -> None:
        """Execute the agent in background."""
        agent_task.status = AgentTaskStatus.RUNNING
        agent_task.started_at = datetime.now(timezone.utc).isoformat()

        job_manager.emit_event(
            agent_task.task_id,
            "agent_background_start",
            {
                "task_id": agent_task.task_id,
                "user_id": agent_task.user_id,
                "model": agent_task.model,
            },
        )

        try:
            from app.services.ai.claude_agent.executor import (
                ClaudeAgentExecutor,
                AgentConfig,
            )

            config = AgentConfig(
                model=agent_task.model,
                use_sdk=True,
            )
            executor = ClaudeAgentExecutor(config=config)

            collected_text: list[str] = []

            async for event in executor.run(
                prompt=agent_task.prompt,
                system_prompt=system_prompt or "",
                context=context,
                job_id=agent_task.task_id,
                user_id=agent_task.user_id,
                db=db,
            ):
                # Forward events to job_manager for optional SSE polling
                event_type = event.get("type", "")
                event_data = event.get("data", {})

                job_manager.emit_event(
                    agent_task.task_id,
                    event_type,
                    event_data,
                )

                # Collect text output
                if event_type == "token":
                    token_text = event_data.get("token", "")
                    if token_text:
                        collected_text.append(token_text)
                elif event_type == "done":
                    final = event_data.get("final_text", "")
                    if final:
                        collected_text = [final]

            agent_task.result = "".join(collected_text)
            agent_task.status = AgentTaskStatus.COMPLETED

        except asyncio.CancelledError:
            agent_task.status = AgentTaskStatus.CANCELLED
            logger.info(f"[AgentPool] Task {agent_task.task_id} was cancelled")

        except Exception as e:
            agent_task.status = AgentTaskStatus.ERROR
            agent_task.error = str(e)
            logger.exception(f"[AgentPool] Task {agent_task.task_id} failed: {e}")

        finally:
            agent_task.completed_at = datetime.now(timezone.utc).isoformat()
            job_manager.emit_event(
                agent_task.task_id,
                "agent_background_done",
                {
                    "task_id": agent_task.task_id,
                    "status": agent_task.status.value,
                    "error": agent_task.error,
                },
            )


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

agent_pool = AgentPool()
