"""Execution limits and resource budgets for workflows and agent runs."""
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ExecutionLimits:
    """Configurable execution limits."""
    # Per-node limits
    node_timeout_seconds: int = 120
    max_llm_calls_per_node: int = 5
    max_tool_calls_per_node: int = 10

    # Per-workflow limits
    workflow_timeout_seconds: int = 1800  # 30 min
    max_nodes_per_workflow: int = 50
    max_total_llm_calls: int = 50
    max_total_tool_calls: int = 100

    # Per-user limits
    max_concurrent_workflows: int = 5
    max_concurrent_agents: int = 10
    max_runs_per_hour: int = 30

    # Resource limits
    max_output_size_bytes: int = 10 * 1024 * 1024  # 10 MB
    max_state_size_bytes: int = 50 * 1024 * 1024  # 50 MB


# Global default limits
DEFAULT_LIMITS = ExecutionLimits()


@dataclass
class ExecutionBudget:
    """Tracks resource usage during a single workflow/agent run."""
    limits: ExecutionLimits = field(default_factory=lambda: DEFAULT_LIMITS)
    started_at: Optional[datetime] = None
    llm_calls: int = 0
    tool_calls: int = 0
    node_count: int = 0
    output_bytes: int = 0

    def start(self):
        self.started_at = datetime.now(timezone.utc)

    def check_timeout(self) -> bool:
        """Returns True if timed out."""
        if not self.started_at:
            return False
        elapsed = (datetime.now(timezone.utc) - self.started_at).total_seconds()
        return elapsed > self.limits.workflow_timeout_seconds

    def record_llm_call(self):
        self.llm_calls += 1
        if self.llm_calls > self.limits.max_total_llm_calls:
            raise BudgetExceededError(
                f"LLM call limit exceeded: {self.llm_calls}/{self.limits.max_total_llm_calls}"
            )

    def record_tool_call(self):
        self.tool_calls += 1
        if self.tool_calls > self.limits.max_total_tool_calls:
            raise BudgetExceededError(
                f"Tool call limit exceeded: {self.tool_calls}/{self.limits.max_total_tool_calls}"
            )

    def record_node(self):
        self.node_count += 1
        if self.node_count > self.limits.max_nodes_per_workflow:
            raise BudgetExceededError(
                f"Node limit exceeded: {self.node_count}/{self.limits.max_nodes_per_workflow}"
            )

    def record_output(self, size_bytes: int):
        self.output_bytes += size_bytes
        if self.output_bytes > self.limits.max_output_size_bytes:
            raise BudgetExceededError(
                f"Output size limit exceeded: {self.output_bytes}/{self.limits.max_output_size_bytes} bytes"
            )


class BudgetExceededError(Exception):
    """Raised when an execution budget is exceeded."""
    pass


def validate_workflow_graph(graph_json: dict, limits: ExecutionLimits | None = None) -> list[str]:
    """Validate a workflow graph against limits. Returns list of warnings/errors."""
    limits = limits or DEFAULT_LIMITS
    errors: list[str] = []
    nodes = graph_json.get("nodes", [])
    edges = graph_json.get("edges", [])

    if len(nodes) > limits.max_nodes_per_workflow:
        errors.append(f"Workflow has {len(nodes)} nodes, max is {limits.max_nodes_per_workflow}")

    if len(nodes) == 0:
        errors.append("Workflow has no nodes")

    # Check for cycles (simple DFS)
    adj: dict[str, list[str]] = {}
    for edge in edges:
        src = edge.get("source", "")
        tgt = edge.get("target", "")
        adj.setdefault(src, []).append(tgt)

    visited: set[str] = set()
    in_stack: set[str] = set()

    def has_cycle(node: str) -> bool:
        if node in in_stack:
            return True
        if node in visited:
            return False
        visited.add(node)
        in_stack.add(node)
        for neighbor in adj.get(node, []):
            if has_cycle(neighbor):
                return True
        in_stack.discard(node)
        return False

    for n in nodes:
        if has_cycle(n.get("id", "")):
            errors.append("Workflow contains a cycle — this may cause infinite loops")
            break

    return errors


async def enforce_workflow_limits(user_id: str, limits: ExecutionLimits | None = None) -> None:
    """Check if user can start a new workflow run. Raises if limits exceeded."""
    limits = limits or DEFAULT_LIMITS

    from app.core.database import AsyncSessionLocal
    from app.models.workflow import WorkflowRun, WorkflowRunStatus
    from sqlalchemy import select, func
    from datetime import timedelta

    async with AsyncSessionLocal() as db:
        # Check concurrent workflows
        running = await db.execute(
            select(func.count()).where(
                WorkflowRun.user_id == user_id,
                WorkflowRun.status.in_([
                    WorkflowRunStatus.RUNNING,
                    WorkflowRunStatus.PAUSED_HIL,
                ]),
            )
        )
        count = running.scalar() or 0
        if count >= limits.max_concurrent_workflows:
            raise BudgetExceededError(
                f"Max concurrent workflows ({limits.max_concurrent_workflows}) reached"
            )

        # Check runs per hour
        one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
        recent = await db.execute(
            select(func.count()).where(
                WorkflowRun.user_id == user_id,
                WorkflowRun.created_at >= one_hour_ago,
            )
        )
        hourly = recent.scalar() or 0
        if hourly >= limits.max_runs_per_hour:
            raise BudgetExceededError(
                f"Max runs per hour ({limits.max_runs_per_hour}) reached"
            )
