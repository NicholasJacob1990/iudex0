"""
Legacy RAG Tracing Module - DEPRECATED.

This module is deprecated and redirects to the new unified tracing system at:
    app.services.rag.utils.trace

For new code, import directly from the new module:
    from app.services.rag.utils.trace import trace_event, TraceEventType

This wrapper is maintained for backward compatibility with existing code.
"""

from typing import Any, Dict, Optional

# Import from the new unified trace module
from app.services.rag.utils.trace import (
    trace_event_legacy,
    TraceEventType,
    generate_request_id,
    is_tracing_enabled,
)

__all__ = ["trace_event", "TraceEventType", "generate_request_id", "is_tracing_enabled"]


def trace_event(
    event: str,
    payload: Dict[str, Any],
    *,
    request_id: Optional[str] = None,
    user_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
    message_id: Optional[str] = None,
) -> None:
    """
    Record a RAG trace event.

    DEPRECATED: This function is maintained for backward compatibility.
    For new code, use app.services.rag.utils.trace.trace_event directly.

    Args:
        event: String event name (e.g., "query_rewrite", "hyde_generate")
        payload: Dict with event-specific data
        request_id: Unique request identifier
        user_id: User identifier
        tenant_id: Tenant identifier
        conversation_id: Conversation identifier (for chat)
        message_id: Message identifier (for chat)
    """
    trace_event_legacy(
        event=event,
        payload=payload,
        request_id=request_id,
        user_id=user_id,
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        message_id=message_id,
    )
