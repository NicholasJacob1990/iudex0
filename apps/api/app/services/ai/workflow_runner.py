"""
Workflow Runner — Executes compiled LangGraph workflows with SSE streaming + HIL.

Handles:
- Streaming execution events via SSE (node start/end, tool calls, LLM responses)
- Human-in-the-Loop pauses (interrupt_before on human_review nodes)
- State snapshot persistence for resume after HIL approval
- Execution logging and error handling
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from contextlib import suppress
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
        # Note: for triggered workflows (Teams/Outlook/DJEN/webhook), Celery passes
        # the event payload as `input_data`. We preserve it in `trigger_event` so
        # the `trigger` node can expose fields as variables and set the input text.
        initial_state: WorkflowState = {
            "job_id": job_id,
            "input": input_data.get("input", ""),
            "output": "",
            "current_node": "",
            "files": input_data.get("files", []),
            "selections": input_data.get("selections", {}),
            "trigger_event": input_data.get("trigger_event") or input_data,
            "rag_results": [],
            "llm_responses": {},
            "tool_results": {},
            "human_edits": {},
            "logs": [],
            "error": None,
            "variables": {},
            "step_outputs": {},
            "user_id": input_data.get("user_id"),
            # Optional context for tool execution (graph tools, etc.)
            "tenant_id": input_data.get("tenant_id"),
            "case_id": input_data.get("case_id"),
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

        queue: asyncio.Queue[SSEEvent] = asyncio.Queue()
        stop_event = asyncio.Event()

        # Poll JobManager events (e.g. hard deep research token streaming)
        job_after_id = 0
        ignore_job_types = {"workflow_node_start", "workflow_node_end"}

        async def _poll_job_events() -> None:
            nonlocal job_after_id
            try:
                while not stop_event.is_set():
                    try:
                        events = job_manager.list_events(job_id, after_id=job_after_id)
                        for ev in events:
                            ev_id = int(ev.get("id") or 0)
                            if ev_id > job_after_id:
                                job_after_id = ev_id

                            ev_type = str(ev.get("type") or "")
                            if not ev_type or ev_type in ignore_job_types:
                                continue

                            payload = ev.get("data") if isinstance(ev.get("data"), dict) else {}

                            # Special-case token events so RunViewer streams the text.
                            if ev_type == "token" and isinstance(payload, dict) and payload.get("token"):
                                await queue.put(token_event(job_id=job_id, token=str(payload.get("token") or "")))
                                continue

                            await queue.put(
                                create_sse_event(
                                    ev_type,
                                    payload if isinstance(payload, dict) else {"data": payload},
                                    job_id=job_id,
                                    phase=str(ev.get("phase") or "workflow"),
                                )
                            )
                    except Exception:
                        # Best-effort: never break workflow execution due to event polling issues.
                        pass

                    await asyncio.sleep(0.12)

                # Final flush
                try:
                    events = job_manager.list_events(job_id, after_id=job_after_id)
                    for ev in events:
                        ev_type = str(ev.get("type") or "")
                        if not ev_type or ev_type in ignore_job_types:
                            continue
                        payload = ev.get("data") if isinstance(ev.get("data"), dict) else {}
                        if ev_type == "token" and isinstance(payload, dict) and payload.get("token"):
                            await queue.put(token_event(job_id=job_id, token=str(payload.get("token") or "")))
                        else:
                            await queue.put(
                                create_sse_event(
                                    ev_type,
                                    payload if isinstance(payload, dict) else {"data": payload},
                                    job_id=job_id,
                                    phase=str(ev.get("phase") or "workflow"),
                                )
                            )
                except Exception:
                    pass
            except asyncio.CancelledError:
                return

        async def _push_compiled_events() -> None:
            nonlocal current_step
            errored = False
            try:
                async for event in compiled.astream_events(
                    initial_state, config=config, version="v2"
                ):
                    if budget.check_timeout():
                        errored = True
                        await queue.put(
                            error_event(
                                job_id=job_id,
                                error="Workflow timeout exceeded",
                                error_type="timeout_error",
                                recoverable=False,
                            )
                        )
                        break

                    event_kind = event.get("event", "")
                    event_name = event.get("name", "")
                    event_data = event.get("data", {})

                    if event_kind == "on_chain_start" and event_name != "LangGraph":
                        current_step += 1
                        node_id = event_name
                        await queue.put(
                            workflow_node_start_event(
                                job_id, node_id, "node",
                                step_number=current_step, total_steps=total_steps,
                            )
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
                        await queue.put(
                            workflow_node_end_event(
                                job_id, node_id, output,
                                step_number=current_step, total_steps=total_steps,
                            )
                        )

                        job_manager.emit_event(
                            job_id,
                            "workflow_node_end",
                            {"node_id": node_id, "step_number": current_step, "total_steps": total_steps},
                            phase="workflow",
                        )

                        # HIL pause detection
                        if isinstance(output, dict) and output.get("current_node"):
                            node_logs = output.get("logs", [])
                            for log in node_logs:
                                if log.get("event") == "human_review_reached":
                                    await queue.put(
                                        workflow_hil_pause_event(
                                            job_id,
                                            output["current_node"],
                                            log.get("instructions", ""),
                                        )
                                    )
                                    stop_event.set()
                                    return

                    elif event_kind == "on_chat_model_stream":
                        chunk = event_data.get("chunk", {})
                        if hasattr(chunk, "content") and chunk.content:
                            await queue.put(token_event(job_id=job_id, token=chunk.content))

                if not errored and not stop_event.is_set():
                    elapsed_seconds = round(time.time() - start_time, 2)
                    await queue.put(
                        done_event(
                            job_id=job_id,
                            metadata={
                                "type": "workflow",
                                "run_id": run_id,
                                "status": "completed",
                                "elapsed_seconds": elapsed_seconds,
                                "total_steps": total_steps,
                            },
                        )
                    )

            except BudgetExceededError as e:
                logger.warning(f"[WorkflowRunner] Budget/timeout exceeded: {e}")
                await queue.put(
                    error_event(
                        job_id=job_id,
                        error="Tempo limite de execução excedido. Tente simplificar o workflow.",
                        error_type="timeout_error",
                        recoverable=False,
                    )
                )
            except Exception as e:
                logger.exception(f"[WorkflowRunner] Execution error: {e}")
                await queue.put(
                    error_event(
                        job_id=job_id,
                        error=str(e),
                        error_type="execution_error",
                        recoverable=False,
                    )
                )
            finally:
                stop_event.set()

        compiled_task = asyncio.create_task(_push_compiled_events())
        poller_task = asyncio.create_task(_poll_job_events())

        try:
            # Drain queue until compilation finishes and no more events remain.
            while True:
                # Important: also wait for the poller to flush final JobManager events,
                # otherwise token streams emitted by nodes can be dropped.
                if compiled_task.done() and poller_task.done() and queue.empty():
                    break
                try:
                    evt = await asyncio.wait_for(queue.get(), timeout=0.25)
                except asyncio.TimeoutError:
                    continue
                yield evt
        finally:
            stop_event.set()
            # Give poller a chance to flush once (it exits quickly once stop_event is set).
            with suppress(Exception):
                await asyncio.wait_for(poller_task, timeout=2.0)
            if not poller_task.done():
                poller_task.cancel()
                with suppress(Exception):
                    await poller_task
            with suppress(Exception):
                await compiled_task

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
