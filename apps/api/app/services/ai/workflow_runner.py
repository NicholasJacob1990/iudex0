"""
Workflow Runner — Executes compiled LangGraph workflows with SSE streaming + HIL.

Handles:
- Streaming execution events via SSE (node start/end, tool calls, LLM responses)
- Human-in-the-Loop pauses (interrupt_before on human_review nodes)
- State snapshot persistence for resume after HIL approval
- Execution logging and error handling
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, List, Optional

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ai.workflow_compiler import WorkflowCompiler, WorkflowState
from app.services.ai.shared.sse_protocol import (
    SSEEvent,
    SSEEventType,
    create_sse_event,
    token_event,
    done_event,
    error_event,
)
from app.services.job_manager import job_manager

try:
    from langgraph.graph.state import CompiledStateGraph
    LANGGRAPH_AVAILABLE = True
except ImportError:
    LANGGRAPH_AVAILABLE = False
    CompiledStateGraph = None


# ---------------------------------------------------------------------------
# SSE Event helpers
# ---------------------------------------------------------------------------


def workflow_node_start_event(
    job_id: str, node_id: str, node_type: str,
    step_number: int = 0, total_steps: int = 0,
) -> SSEEvent:
    return create_sse_event(
        SSEEventType.WORKFLOW_NODE_START if hasattr(SSEEventType, "WORKFLOW_NODE_START") else SSEEventType.AGENT_START,
        {
            "node_id": node_id,
            "node_type": node_type,
            "status": "running",
            "step_number": step_number,
            "total_steps": total_steps,
        },
        job_id=job_id,
        phase="workflow",
    )


def workflow_node_end_event(
    job_id: str, node_id: str, output: Any,
    step_number: int = 0, total_steps: int = 0,
) -> SSEEvent:
    return create_sse_event(
        SSEEventType.WORKFLOW_NODE_END if hasattr(SSEEventType, "WORKFLOW_NODE_END") else SSEEventType.AGENT_START,
        {
            "node_id": node_id,
            "status": "completed",
            "output_preview": str(output)[:200],
            "step_number": step_number,
            "total_steps": total_steps,
        },
        job_id=job_id,
        phase="workflow",
    )


def workflow_hil_pause_event(job_id: str, node_id: str, instructions: str) -> SSEEvent:
    return create_sse_event(
        SSEEventType.TOOL_APPROVAL_REQUIRED if hasattr(SSEEventType, "TOOL_APPROVAL_REQUIRED") else SSEEventType.AGENT_START,
        {
            "node_id": node_id,
            "status": "paused_hil",
            "instructions": instructions,
            "requires_approval": True,
        },
        job_id=job_id,
        phase="workflow",
    )


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


class WorkflowRunner:
    """Executes a compiled LangGraph workflow with streaming events."""

    def __init__(self, db: Optional[AsyncSession] = None) -> None:
        self.db = db
        self._compiler = WorkflowCompiler()

    async def run_streaming(
        self,
        graph_json: Dict[str, Any],
        input_data: Dict[str, Any],
        job_id: Optional[str] = None,
        run_id: Optional[str] = None,
    ) -> AsyncGenerator[SSEEvent, None]:
        """
        Execute a workflow with streaming SSE events.

        Args:
            graph_json: React Flow graph definition
            input_data: Initial state values
            job_id: Job ID for SSE events
            run_id: WorkflowRun ID for persistence

        Yields:
            SSE events for each workflow step.
        """
        if not LANGGRAPH_AVAILABLE:
            yield error_event(
                job_id=job_id or "unknown",
                error="LangGraph not installed",
                error_type="dependency_error",
                recoverable=False,
            )
            return

        job_id = job_id or str(uuid.uuid4())

        # Progress tracking
        total_steps = len(graph_json.get("nodes", []))
        current_step = 0
        start_time = time.time()

        # Initialize execution budget for timeout enforcement
        from app.services.ai.sandbox.execution_limits import ExecutionBudget, BudgetExceededError
        budget = ExecutionBudget()
        budget.start()

        try:
            compiled = self._compiler.compile(graph_json)
        except Exception as e:
            yield error_event(
                job_id=job_id,
                error=f"Compilation failed: {e}",
                error_type="compilation_error",
                recoverable=False,
            )
            return

        # Build initial state
        initial_state: WorkflowState = {
            "input": input_data.get("input", ""),
            "output": "",
            "current_node": "",
            "files": input_data.get("files", []),
            "selections": input_data.get("selections", {}),
            "rag_results": [],
            "llm_responses": {},
            "tool_results": {},
            "human_edits": {},
            "logs": [],
            "error": None,
            "variables": {},
            "step_outputs": {},
            "user_id": input_data.get("user_id"),
        }

        config = {"configurable": {"thread_id": job_id}}

        # Emit workflow start
        yield create_sse_event(
            SSEEventType.AGENT_START,
            {
                "job_id": job_id,
                "run_id": run_id,
                "type": "workflow",
                "nodes_count": len(graph_json.get("nodes", [])),
            },
            job_id=job_id,
            phase="workflow",
        )

        try:
            async for event in compiled.astream_events(
                initial_state, config=config, version="v2"
            ):
                # Check workflow timeout
                if budget.check_timeout():
                    yield error_event(
                        job_id=job_id,
                        error="Workflow timeout exceeded",
                        error_type="timeout_error",
                        recoverable=False,
                    )
                    break

                event_kind = event.get("event", "")
                event_name = event.get("name", "")
                event_data = event.get("data", {})

                if event_kind == "on_chain_start" and event_name != "LangGraph":
                    # Node starting
                    current_step += 1
                    node_id = event_name
                    yield workflow_node_start_event(
                        job_id, node_id, "node",
                        step_number=current_step, total_steps=total_steps,
                    )

                    job_manager.emit_event(
                        job_id,
                        "workflow_node_start",
                        {"node_id": node_id, "step_number": current_step, "total_steps": total_steps},
                        phase="workflow",
                    )

                elif event_kind == "on_chain_end" and event_name != "LangGraph":
                    node_id = event_name
                    output = event_data.get("output", {})
                    yield workflow_node_end_event(
                        job_id, node_id, output,
                        step_number=current_step, total_steps=total_steps,
                    )

                    job_manager.emit_event(
                        job_id,
                        "workflow_node_end",
                        {"node_id": node_id, "step_number": current_step, "total_steps": total_steps},
                        phase="workflow",
                    )

                    # Check for HIL pause
                    if isinstance(output, dict) and output.get("current_node"):
                        node_logs = output.get("logs", [])
                        for log in node_logs:
                            if log.get("event") == "human_review_reached":
                                yield workflow_hil_pause_event(
                                    job_id,
                                    output["current_node"],
                                    log.get("instructions", ""),
                                )
                                return  # Pause execution

                elif event_kind == "on_chat_model_stream":
                    # LLM token streaming
                    chunk = event_data.get("chunk", {})
                    if hasattr(chunk, "content") and chunk.content:
                        yield token_event(job_id=job_id, token=chunk.content)

            # Workflow completed
            elapsed_seconds = round(time.time() - start_time, 2)
            yield done_event(
                job_id=job_id,
                metadata={
                    "type": "workflow",
                    "run_id": run_id,
                    "status": "completed",
                    "elapsed_seconds": elapsed_seconds,
                    "total_steps": total_steps,
                },
            )

        except BudgetExceededError as e:
            logger.warning(f"[WorkflowRunner] Budget/timeout exceeded: {e}")
            yield error_event(
                job_id=job_id,
                error="Tempo limite de execução excedido. Tente simplificar o workflow.",
                error_type="timeout_error",
                recoverable=False,
            )
        except Exception as e:
            logger.exception(f"[WorkflowRunner] Execution error: {e}")
            yield error_event(
                job_id=job_id,
                error=str(e),
                error_type="execution_error",
                recoverable=False,
            )

    async def resume_after_hil(
        self,
        graph_json: Dict[str, Any],
        state_snapshot: Dict[str, Any],
        approved: bool,
        human_edits: Optional[Dict[str, Any]] = None,
        job_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> AsyncGenerator[SSEEvent, None]:
        """
        Resume workflow execution after HIL approval.

        Args:
            graph_json: The original graph definition
            state_snapshot: Saved state from the paused run
            approved: Whether the human approved
            human_edits: Optional edits from the human reviewer
            job_id: Job ID for SSE events

        Yields:
            SSE events for remaining workflow steps.
        """
        job_id = job_id or str(uuid.uuid4())

        if not approved:
            yield done_event(
                job_id=job_id,
                metadata={"type": "workflow", "status": "rejected_by_human"},
            )
            return

        # Ensure user_id is present in state for credential resolution
        if user_id and not state_snapshot.get("user_id"):
            state_snapshot["user_id"] = user_id

        # Inject human edits into state
        if human_edits:
            state_snapshot["human_edits"] = {
                **state_snapshot.get("human_edits", {}),
                **human_edits,
            }
            # If edits include output override
            if "output" in human_edits:
                state_snapshot["output"] = human_edits["output"]

        try:
            compiled = self._compiler.compile(graph_json)
        except Exception as e:
            yield error_event(
                job_id=job_id,
                error=f"Recompilation failed: {e}",
                error_type="compilation_error",
            )
            return

        config = {"configurable": {"thread_id": job_id}}

        try:
            # Update state and continue
            await compiled.aupdate_state(config, state_snapshot)

            async for event in compiled.astream_events(
                None, config=config, version="v2"
            ):
                event_kind = event.get("event", "")
                event_name = event.get("name", "")
                event_data = event.get("data", {})

                if event_kind == "on_chain_start" and event_name != "LangGraph":
                    yield workflow_node_start_event(job_id, event_name, "node")
                elif event_kind == "on_chain_end" and event_name != "LangGraph":
                    yield workflow_node_end_event(
                        job_id, event_name, event_data.get("output", {})
                    )
                elif event_kind == "on_chat_model_stream":
                    chunk = event_data.get("chunk", {})
                    if hasattr(chunk, "content") and chunk.content:
                        yield token_event(job_id=job_id, token=chunk.content)

            yield done_event(
                job_id=job_id,
                metadata={"type": "workflow", "status": "completed_after_hil"},
            )

        except Exception as e:
            logger.exception(f"[WorkflowRunner] Resume error: {e}")
            yield error_event(
                job_id=job_id,
                error=str(e),
                error_type="execution_error",
            )
