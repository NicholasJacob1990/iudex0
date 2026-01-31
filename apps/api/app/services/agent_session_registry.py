"""
Agent Session Registry - Track active agent executors by job_id.

Allows endpoints (e.g. tool-approval) to find the running executor
for a given job and interact with it (approve/deny tool calls, etc.)
"""
from typing import Any, Dict, Optional
from loguru import logger


class AgentSessionRegistry:
    """Global registry of active agent executor sessions."""

    def __init__(self):
        self._sessions: Dict[str, Any] = {}

    def register(self, job_id: str, executor: Any) -> None:
        self._sessions[job_id] = executor
        logger.debug(f"Agent session registered: {job_id}")

    def unregister(self, job_id: str) -> None:
        self._sessions.pop(job_id, None)
        logger.debug(f"Agent session unregistered: {job_id}")

    def get(self, job_id: str) -> Optional[Any]:
        return self._sessions.get(job_id)

    def is_active(self, job_id: str) -> bool:
        return job_id in self._sessions

    @property
    def active_count(self) -> int:
        return len(self._sessions)


agent_session_registry = AgentSessionRegistry()
