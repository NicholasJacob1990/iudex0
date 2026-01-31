"""
Tool Gateway - MCP-compatible tool management for legal AI agents.

This module provides:
- ToolRegistry: Unified registration of all legal tools
- PolicyEngine: Enforcement of tool execution policies
- ToolDefinition: Schema and metadata for tools
- ToolPolicy/ToolCategory: Enums for tool classification

Usage:
    from app.services.ai.tool_gateway import (
        tool_registry,
        policy_engine,
        ToolDefinition,
        ToolPolicy,
        ToolCategory,
        PolicyContext,
    )

    # Initialize tools
    tool_registry.initialize()

    # Check policy before execution
    result = await policy_engine.check_policy(context)
    if result.decision == PolicyDecision.ALLOW:
        # Execute tool
        ...
"""

from .tool_registry import (
    ToolRegistry,
    ToolDefinition,
    ToolPolicy,
    ToolCategory,
    tool_registry,
)

from .policy_engine import (
    PolicyEngine,
    PolicyContext,
    PolicyResult,
    PolicyDecision,
    policy_engine,
)

from .mcp_server import (
    MCPToolServer,
    MCPError,
    MCPResponse,
    mcp_server,
    handle_mcp_http,
    handle_mcp_sse,
)

__all__ = [
    # Registry
    "ToolRegistry",
    "ToolDefinition",
    "ToolPolicy",
    "ToolCategory",
    "tool_registry",
    # Policy
    "PolicyEngine",
    "PolicyContext",
    "PolicyResult",
    "PolicyDecision",
    "policy_engine",
    # MCP Server
    "MCPToolServer",
    "MCPError",
    "MCPResponse",
    "mcp_server",
    "handle_mcp_http",
    "handle_mcp_sse",
]
