"""
Shared utilities for AI services.

Contains:
- SSE Protocol: Standardized event types and builders
- Tool Registry: Unified tool definitions for all agents
- Unified Tools: SDK + Legal + MCP tools
- Tool Handlers: Implementations for all tools
- Context Protocol: Case bundle handling
"""

from .sse_protocol import (
    SSEEventType,
    SSEEvent,
    ToolApprovalMode,
    create_sse_event,
    # Agent-specific events
    agent_iteration_event,
    tool_call_event,
    tool_result_event,
    tool_approval_required_event,
    context_warning_event,
    checkpoint_created_event,
    # Streaming events
    token_event,
    thinking_event,
    done_event,
    error_event,
)

from .tool_registry import (
    ToolRegistry,
    ToolDefinition,
    ToolCategory,
    get_global_registry,
)

from .unified_tools import (
    # Types
    UnifiedTool,
    ToolRiskLevel,
    # Tool collections
    ALL_UNIFIED_TOOLS,
    TOOLS_BY_NAME,
    # Functions
    register_all_tools,
    get_tools_for_claude,
    get_tools_for_openai,
    get_default_permissions,
    get_tool_risk_level,
    list_tools_by_category,
    list_tools_by_risk,
)

from .tool_handlers import (
    ToolExecutionContext,
    ToolHandlers,
    get_tool_handlers,
    execute_tool,
)

from .langgraph_integration import (
    LangGraphToolBridge,
    create_tool_node,
    get_tools_for_langgraph_agent,
    execute_tool_in_workflow,
    list_available_tools_for_model,
)

__all__ = [
    # SSE Protocol
    "SSEEventType",
    "SSEEvent",
    "ToolApprovalMode",
    "create_sse_event",
    "agent_iteration_event",
    "tool_call_event",
    "tool_result_event",
    "tool_approval_required_event",
    "context_warning_event",
    "checkpoint_created_event",
    "token_event",
    "thinking_event",
    "done_event",
    "error_event",
    # Tool Registry
    "ToolRegistry",
    "ToolDefinition",
    "ToolCategory",
    "get_global_registry",
    # Unified Tools
    "UnifiedTool",
    "ToolRiskLevel",
    "ALL_UNIFIED_TOOLS",
    "TOOLS_BY_NAME",
    "register_all_tools",
    "get_tools_for_claude",
    "get_tools_for_openai",
    "get_default_permissions",
    "get_tool_risk_level",
    "list_tools_by_category",
    "list_tools_by_risk",
    # Tool Handlers
    "ToolExecutionContext",
    "ToolHandlers",
    "get_tool_handlers",
    "execute_tool",
    # LangGraph Integration
    "LangGraphToolBridge",
    "create_tool_node",
    "get_tools_for_langgraph_agent",
    "execute_tool_in_workflow",
    "list_available_tools_for_model",
]
