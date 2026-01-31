"""
SSE Protocol - Standardized Server-Sent Events for Iudex AI Services

This module defines a unified protocol for SSE events used across:
- LangGraph workflows
- Claude Agent SDK executor
- Parallel orchestration

Event format follows the existing JobManager pattern (v1 envelope).
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, TypedDict, Union
import json


class SSEEventType(str, Enum):
    """
    All supported SSE event types.

    Existing events (LangGraph compatibility):
    - token: Streaming text chunks
    - outline: Document structure
    - hil_required: Human-in-the-loop required
    - audit_done: Audit completed
    - thinking: Extended thinking/reasoning
    - done: Workflow completed
    - error: Error occurred

    New events (Claude Agent SDK):
    - agent_iteration: Agent loop iteration
    - tool_call: Agent called a tool
    - tool_result: Tool execution result
    - tool_approval_required: Tool needs user approval
    - context_warning: Context limit approaching
    - compaction_done: Context compacted
    - checkpoint_created: Checkpoint saved

    Parallel execution events:
    - parallel_start: Parallel execution started
    - parallel_complete: Parallel execution finished
    - node_start: LangGraph node started
    - node_complete: LangGraph node completed
    """
    # Existing events
    TOKEN = "token"
    OUTLINE = "outline"
    HIL_REQUIRED = "hil_required"
    AUDIT_DONE = "audit_done"
    THINKING = "thinking"
    DONE = "done"
    ERROR = "error"

    # Agent events
    AGENT_ITERATION = "agent_iteration"
    AGENT_START = "agent_start"
    AGENT_END = "agent_end"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    TOOL_APPROVAL_REQUIRED = "tool_approval_required"
    TOOL_APPROVED = "tool_approved"
    TOOL_DENIED = "tool_denied"

    # Context management
    CONTEXT_WARNING = "context_warning"
    COMPACTION_DONE = "compaction_done"

    # Checkpoints
    CHECKPOINT_CREATED = "checkpoint_created"
    CHECKPOINT_RESTORED = "checkpoint_restored"

    # Parallel execution
    PARALLEL_START = "parallel_start"
    PARALLEL_COMPLETE = "parallel_complete"
    NODE_START = "node_start"
    NODE_COMPLETE = "node_complete"

    # Research
    RESEARCH_START = "research_start"
    RESEARCH_RESULT = "research_result"
    RESEARCH_COMPLETE = "research_complete"

    # CogGRAG Events
    COGRAG_DECOMPOSE_START = "cograg_decompose_start"
    COGRAG_DECOMPOSE_NODE = "cograg_decompose_node"
    COGRAG_DECOMPOSE_COMPLETE = "cograg_decompose_complete"
    COGRAG_RETRIEVAL_START = "cograg_retrieval_start"
    COGRAG_RETRIEVAL_NODE = "cograg_retrieval_node"
    COGRAG_RETRIEVAL_COMPLETE = "cograg_retrieval_complete"
    COGRAG_VERIFY_START = "cograg_verify_start"
    COGRAG_VERIFY_NODE = "cograg_verify_node"
    COGRAG_VERIFY_COMPLETE = "cograg_verify_complete"
    COGRAG_INTEGRATE_START = "cograg_integrate_start"
    COGRAG_INTEGRATE_COMPLETE = "cograg_integrate_complete"


class ToolApprovalMode(str, Enum):
    """Permission modes for tool execution."""
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"


@dataclass
class ToolCallData:
    """Data for a tool call event."""
    tool_name: str
    tool_input: Dict[str, Any]
    tool_id: str = ""
    description: str = ""
    permission_mode: ToolApprovalMode = ToolApprovalMode.ASK


@dataclass
class ToolResultData:
    """Data for a tool result event."""
    tool_name: str
    tool_id: str
    result: Any
    success: bool = True
    error: Optional[str] = None
    execution_time_ms: int = 0


@dataclass
class ContextWarningData:
    """Data for context warning event."""
    current_tokens: int
    max_tokens: int
    usage_percent: float
    recommended_action: str = "compact"


@dataclass
class CheckpointData:
    """Data for checkpoint events."""
    checkpoint_id: str
    turn_id: Optional[str] = None
    description: str = ""
    snapshot_type: Literal["auto", "manual", "hil"] = "auto"
    is_restorable: bool = True


@dataclass
class SSEEvent:
    """
    Standard SSE event envelope following JobManager v1 format.

    Attributes:
        type: Event type from SSEEventType
        data: Event-specific payload
        job_id: Associated job/session ID
        phase: Current workflow phase (optional)
        node: Current node name (optional)
        section: Document section being processed (optional)
        agent: Agent identifier (optional)
        ts: Timestamp in ISO format
        v: Protocol version (always 1)
        id: Event sequence ID (set by JobManager)
    """
    type: SSEEventType
    data: Dict[str, Any]
    job_id: str = ""
    phase: Optional[str] = None
    node: Optional[str] = None
    section: Optional[str] = None
    agent: Optional[str] = None
    ts: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
    v: int = 1
    id: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "v": self.v,
            "type": self.type.value if isinstance(self.type, SSEEventType) else str(self.type),
            "data": self.data,
            "job_id": self.job_id,
            "ts": self.ts,
            "phase": self.phase,
            "node": self.node,
            "section": self.section,
            "agent": self.agent,
            "channel": self.phase,  # Compatibility with JobManager
        }

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False, default=str)

    def to_sse_format(self) -> str:
        """Format as SSE data line."""
        return f"data: {self.to_json()}\n\n"


# =============================================================================
# EVENT FACTORY FUNCTIONS
# =============================================================================

def create_sse_event(
    event_type: Union[SSEEventType, str],
    data: Dict[str, Any],
    job_id: str = "",
    phase: Optional[str] = None,
    node: Optional[str] = None,
    section: Optional[str] = None,
    agent: Optional[str] = None,
) -> SSEEvent:
    """
    Create a standardized SSE event.

    Args:
        event_type: Type of event
        data: Event payload
        job_id: Job/session identifier
        phase: Current workflow phase
        node: Current node
        section: Document section
        agent: Agent identifier

    Returns:
        SSEEvent instance
    """
    if isinstance(event_type, str):
        try:
            event_type = SSEEventType(event_type)
        except ValueError:
            # Keep as string for custom event types
            pass

    return SSEEvent(
        type=event_type,
        data=data,
        job_id=job_id,
        phase=phase,
        node=node,
        section=section,
        agent=agent,
    )


# =============================================================================
# AGENT-SPECIFIC EVENT BUILDERS
# =============================================================================

def agent_iteration_event(
    job_id: str,
    iteration: int,
    status: str = "running",
    message: str = "",
    **kwargs
) -> SSEEvent:
    """Create an agent iteration event."""
    return create_sse_event(
        SSEEventType.AGENT_ITERATION,
        {
            "iteration": iteration,
            "status": status,
            "message": message,
        },
        job_id=job_id,
        phase="agent",
        agent=kwargs.get("agent", "claude"),
        **{k: v for k, v in kwargs.items() if k not in ["agent"]}
    )


def tool_call_event(
    job_id: str,
    tool_name: str,
    tool_input: Dict[str, Any],
    tool_id: str = "",
    description: str = "",
    permission_mode: ToolApprovalMode = ToolApprovalMode.ASK,
    **kwargs
) -> SSEEvent:
    """Create a tool call event."""
    return create_sse_event(
        SSEEventType.TOOL_CALL,
        {
            "tool_name": tool_name,
            "tool_input": tool_input,
            "tool_id": tool_id,
            "description": description,
            "permission_mode": permission_mode.value if isinstance(permission_mode, ToolApprovalMode) else permission_mode,
        },
        job_id=job_id,
        phase="agent",
        **kwargs
    )


def tool_result_event(
    job_id: str,
    tool_name: str,
    tool_id: str,
    result: Any,
    success: bool = True,
    error: Optional[str] = None,
    execution_time_ms: int = 0,
    **kwargs
) -> SSEEvent:
    """Create a tool result event."""
    return create_sse_event(
        SSEEventType.TOOL_RESULT,
        {
            "tool_name": tool_name,
            "tool_id": tool_id,
            "result": result,
            "success": success,
            "error": error,
            "execution_time_ms": execution_time_ms,
        },
        job_id=job_id,
        phase="agent",
        **kwargs
    )


def tool_approval_required_event(
    job_id: str,
    tool_name: str,
    tool_input: Dict[str, Any],
    tool_id: str,
    description: str = "",
    risk_level: str = "medium",
    **kwargs
) -> SSEEvent:
    """Create a tool approval required event."""
    return create_sse_event(
        SSEEventType.TOOL_APPROVAL_REQUIRED,
        {
            "tool_name": tool_name,
            "tool_input": tool_input,
            "tool_id": tool_id,
            "description": description,
            "risk_level": risk_level,
            "awaiting_approval": True,
        },
        job_id=job_id,
        phase="agent",
        **kwargs
    )


def context_warning_event(
    job_id: str,
    current_tokens: int,
    max_tokens: int,
    usage_percent: float,
    recommended_action: str = "compact",
    **kwargs
) -> SSEEvent:
    """Create a context warning event."""
    return create_sse_event(
        SSEEventType.CONTEXT_WARNING,
        {
            "current_tokens": current_tokens,
            "max_tokens": max_tokens,
            "usage_percent": round(usage_percent, 2),
            "recommended_action": recommended_action,
        },
        job_id=job_id,
        **kwargs
    )


def checkpoint_created_event(
    job_id: str,
    checkpoint_id: str,
    description: str = "",
    snapshot_type: str = "auto",
    **kwargs
) -> SSEEvent:
    """Create a checkpoint created event."""
    return create_sse_event(
        SSEEventType.CHECKPOINT_CREATED,
        {
            "checkpoint_id": checkpoint_id,
            "description": description,
            "snapshot_type": snapshot_type,
        },
        job_id=job_id,
        **kwargs
    )


# =============================================================================
# STREAMING EVENT BUILDERS
# =============================================================================

def token_event(
    job_id: str,
    token: str,
    **kwargs
) -> SSEEvent:
    """Create a token streaming event."""
    return create_sse_event(
        SSEEventType.TOKEN,
        {"token": token},
        job_id=job_id,
        **kwargs
    )


def thinking_event(
    job_id: str,
    content: str,
    is_final: bool = False,
    **kwargs
) -> SSEEvent:
    """Create a thinking/reasoning event."""
    return create_sse_event(
        SSEEventType.THINKING,
        {
            "content": content,
            "is_final": is_final,
        },
        job_id=job_id,
        **kwargs
    )


def done_event(
    job_id: str,
    final_text: str = "",
    metadata: Optional[Dict[str, Any]] = None,
    **kwargs
) -> SSEEvent:
    """Create a completion event."""
    data = {"status": "completed"}
    if final_text:
        data["final_text"] = final_text
    if metadata:
        data["metadata"] = metadata
    return create_sse_event(
        SSEEventType.DONE,
        data,
        job_id=job_id,
        **kwargs
    )


def error_event(
    job_id: str,
    error: str,
    error_type: str = "unknown",
    recoverable: bool = False,
    **kwargs
) -> SSEEvent:
    """Create an error event."""
    return create_sse_event(
        SSEEventType.ERROR,
        {
            "error": error,
            "error_type": error_type,
            "recoverable": recoverable,
        },
        job_id=job_id,
        **kwargs
    )


# =============================================================================
# COGRAG EVENT BUILDERS
# =============================================================================

@dataclass
class CogRAGNodeData:
    """Data for a CogRAG mind map node."""
    node_id: str
    question: str
    level: int
    parent_id: Optional[str] = None
    state: str = "pending"  # pending | decomposing | retrieving | verifying | complete | error
    children_count: int = 0
    evidence_count: int = 0
    confidence: float = 0.0


def cograg_decompose_start_event(
    job_id: str,
    query: str,
    max_depth: int = 3,
    **kwargs
) -> SSEEvent:
    """Create a CogRAG decomposition start event."""
    return create_sse_event(
        SSEEventType.COGRAG_DECOMPOSE_START,
        {
            "query": query,
            "max_depth": max_depth,
            "status": "decomposing",
        },
        job_id=job_id,
        phase="cograg",
        node="decomposer",
        **kwargs
    )


def cograg_decompose_node_event(
    job_id: str,
    node_id: str,
    question: str,
    level: int,
    parent_id: Optional[str] = None,
    **kwargs
) -> SSEEvent:
    """Create a CogRAG decomposition node event."""
    return create_sse_event(
        SSEEventType.COGRAG_DECOMPOSE_NODE,
        {
            "node_id": node_id,
            "question": question,
            "level": level,
            "parent_id": parent_id,
            "state": "decomposing",
        },
        job_id=job_id,
        phase="cograg",
        node="decomposer",
        **kwargs
    )


def cograg_decompose_complete_event(
    job_id: str,
    total_nodes: int,
    max_level: int,
    leaf_count: int,
    **kwargs
) -> SSEEvent:
    """Create a CogRAG decomposition complete event."""
    return create_sse_event(
        SSEEventType.COGRAG_DECOMPOSE_COMPLETE,
        {
            "total_nodes": total_nodes,
            "max_level": max_level,
            "leaf_count": leaf_count,
            "status": "complete",
        },
        job_id=job_id,
        phase="cograg",
        node="decomposer",
        **kwargs
    )


def cograg_retrieval_start_event(
    job_id: str,
    node_count: int,
    **kwargs
) -> SSEEvent:
    """Create a CogRAG retrieval start event."""
    return create_sse_event(
        SSEEventType.COGRAG_RETRIEVAL_START,
        {
            "node_count": node_count,
            "status": "retrieving",
        },
        job_id=job_id,
        phase="cograg",
        node="retriever",
        **kwargs
    )


def cograg_retrieval_node_event(
    job_id: str,
    node_id: str,
    question: str,
    evidence_count: int,
    local_count: int = 0,
    global_count: int = 0,
    **kwargs
) -> SSEEvent:
    """Create a CogRAG retrieval node event."""
    return create_sse_event(
        SSEEventType.COGRAG_RETRIEVAL_NODE,
        {
            "node_id": node_id,
            "question": question,
            "evidence_count": evidence_count,
            "local_count": local_count,
            "global_count": global_count,
            "state": "retrieved",
        },
        job_id=job_id,
        phase="cograg",
        node="retriever",
        **kwargs
    )


def cograg_retrieval_complete_event(
    job_id: str,
    total_evidence: int,
    nodes_with_evidence: int,
    latency_ms: int = 0,
    **kwargs
) -> SSEEvent:
    """Create a CogRAG retrieval complete event."""
    return create_sse_event(
        SSEEventType.COGRAG_RETRIEVAL_COMPLETE,
        {
            "total_evidence": total_evidence,
            "nodes_with_evidence": nodes_with_evidence,
            "latency_ms": latency_ms,
            "status": "complete",
        },
        job_id=job_id,
        phase="cograg",
        node="retriever",
        **kwargs
    )


def cograg_verify_start_event(
    job_id: str,
    answer_count: int,
    **kwargs
) -> SSEEvent:
    """Create a CogRAG verification start event."""
    return create_sse_event(
        SSEEventType.COGRAG_VERIFY_START,
        {
            "answer_count": answer_count,
            "status": "verifying",
        },
        job_id=job_id,
        phase="cograg",
        node="verifier",
        **kwargs
    )


def cograg_verify_node_event(
    job_id: str,
    node_id: str,
    is_consistent: bool,
    confidence: float,
    issues: List[str],
    **kwargs
) -> SSEEvent:
    """Create a CogRAG verification node event."""
    return create_sse_event(
        SSEEventType.COGRAG_VERIFY_NODE,
        {
            "node_id": node_id,
            "is_consistent": is_consistent,
            "confidence": confidence,
            "issues": issues,
            "state": "verified" if is_consistent else "rejected",
        },
        job_id=job_id,
        phase="cograg",
        node="verifier",
        **kwargs
    )


def cograg_verify_complete_event(
    job_id: str,
    status: str,  # approved | rejected | abstain
    approved_count: int,
    rejected_count: int,
    **kwargs
) -> SSEEvent:
    """Create a CogRAG verification complete event."""
    return create_sse_event(
        SSEEventType.COGRAG_VERIFY_COMPLETE,
        {
            "verification_status": status,
            "approved_count": approved_count,
            "rejected_count": rejected_count,
            "status": "complete",
        },
        job_id=job_id,
        phase="cograg",
        node="verifier",
        **kwargs
    )


def cograg_integrate_start_event(
    job_id: str,
    sub_answer_count: int,
    **kwargs
) -> SSEEvent:
    """Create a CogRAG integration start event."""
    return create_sse_event(
        SSEEventType.COGRAG_INTEGRATE_START,
        {
            "sub_answer_count": sub_answer_count,
            "status": "integrating",
        },
        job_id=job_id,
        phase="cograg",
        node="integrator",
        **kwargs
    )


def cograg_integrate_complete_event(
    job_id: str,
    citations_count: int,
    abstained: bool = False,
    **kwargs
) -> SSEEvent:
    """Create a CogRAG integration complete event."""
    return create_sse_event(
        SSEEventType.COGRAG_INTEGRATE_COMPLETE,
        {
            "citations_count": citations_count,
            "abstained": abstained,
            "status": "complete",
        },
        job_id=job_id,
        phase="cograg",
        node="integrator",
        **kwargs
    )
