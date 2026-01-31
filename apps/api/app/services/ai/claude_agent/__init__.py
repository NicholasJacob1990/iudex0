"""
Claude Agent SDK - Wrapper for Anthropic's Agent capabilities.

This module implements an autonomous agent using Claude's native tool-use
and extended thinking capabilities, following the Claude Agent SDK pattern.

Components:
- executor.py: Main ClaudeAgentExecutor class (agent loop)
- permissions.py: Tool permission management (Allow/Deny/Ask)
- tools/: Legal-specific tools (research, document editing, etc.)

Usage:
    from app.services.ai.claude_agent import ClaudeAgentExecutor, AgentConfig

    # Create executor
    config = AgentConfig(model="claude-sonnet-4-20250514")
    executor = ClaudeAgentExecutor(config)

    # Register tools
    executor.register_tool("search_rag", "Search documents", schema, search_fn)

    # Run agent loop
    async for event in executor.run(prompt, system_prompt, context):
        job_manager.emit_event(event.job_id, event.type.value, event.data)

Permission Management:
    from app.services.ai.claude_agent import PermissionManager

    manager = PermissionManager(db=session, user_id="user-123")
    result = await manager.check("edit_document", {"path": "/doc.md"})

    if result.is_allowed:
        # Execute tool
        pass
    elif result.needs_approval:
        # Show approval modal
        pass
"""

# Executor classes
from .executor import (
    AgentConfig,
    AgentState,
    AgentStatus,
    ClaudeAgentExecutor,
    create_claude_agent,
)

# Permission classes
from .permissions import (
    # Classes principais
    PermissionManager,
    PermissionRule,
    PermissionCheckResult,
    # Tipos
    PermissionDecision,
    # Constantes
    SYSTEM_DEFAULTS,
    DEFAULT_PERMISSION,
    TOOL_CATEGORIES,
    # Funções utilitárias
    get_default_permission,
    is_high_risk_tool,
    is_read_only_tool,
)

__all__ = [
    # Executor
    "AgentConfig",
    "AgentState",
    "AgentStatus",
    "ClaudeAgentExecutor",
    "create_claude_agent",
    # Permissions - Classes principais
    "PermissionManager",
    "PermissionRule",
    "PermissionCheckResult",
    # Permissions - Tipos
    "PermissionDecision",
    # Permissions - Constantes
    "SYSTEM_DEFAULTS",
    "DEFAULT_PERMISSION",
    "TOOL_CATEGORIES",
    # Permissions - Funções utilitárias
    "get_default_permission",
    "is_high_risk_tool",
    "is_read_only_tool",
]
