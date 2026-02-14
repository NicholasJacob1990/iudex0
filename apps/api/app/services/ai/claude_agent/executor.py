"""
Claude Agent Executor - Core agent loop implementation

This module implements the main agent executor that:
1. Receives user prompts and context
2. Calls Claude with tools enabled
3. Processes tool_use blocks from responses
4. Verifies permissions before executing tools
5. Emits SSE events for each action
6. Supports pause/resume for tool approval

Architecture follows the Claude Agent SDK pattern with agentic loop.
"""

import asyncio
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import (
    Any,
    AsyncGenerator,
    Callable,
    Dict,
    List,
    Literal,
    Optional,
    Tuple,
    TypeVar,
    Union,
)

# Anthropic SDK
try:
    import anthropic
    from anthropic import Anthropic, AsyncAnthropic
    from anthropic.types import (
        Message,
        MessageParam,
        ContentBlock,
        TextBlock,
        ToolUseBlock,
        ToolResultBlockParam,
    )
except ImportError:
    anthropic = None  # type: ignore
    Anthropic = None  # type: ignore
    AsyncAnthropic = None  # type: ignore

from loguru import logger

# Claude Agent SDK (optional — dual mode)
try:
    from claude_agent_sdk import query, ClaudeAgentOptions, AssistantMessage, ResultMessage, SystemMessage
    from .sdk_tools import (
        create_iudex_mcp_server,
        set_iudex_tool_context,
        CLAUDE_SDK_TOOLS_AVAILABLE,
    )
    from .template_loader import load_agent_templates
    CLAUDE_SDK_AVAILABLE = True
except ImportError:
    CLAUDE_SDK_AVAILABLE = False
    CLAUDE_SDK_TOOLS_AVAILABLE = False

# Internal imports
from app.services.job_manager import job_manager
from app.services.ai.tool_gateway.adapters import ClaudeMCPAdapter
from app.services.api_call_tracker import record_api_call, billing_context
from app.services.ai.shared.sse_protocol import (
    SSEEvent,
    SSEEventType,
    ToolApprovalMode,
    create_sse_event,
    agent_iteration_event,
    tool_call_event,
    tool_result_event,
    tool_approval_required_event,
    context_warning_event,
    checkpoint_created_event,
    token_event,
    thinking_event,
    done_event,
    error_event,
    # Code Artifacts
    artifact_start_event,
    artifact_token_event,
    artifact_done_event,
)
from app.services.ai.observability import (
    langsmith_trace,
    extract_langsmith_run_metadata,
)
from app.services.ai.observability.audit_log import get_tool_audit_log
from app.services.ai.shared.security_profile import SecurityProfile

# =============================================================================
# CONFIGURATION
# =============================================================================

# Environment variables
CLAUDE_AGENT_ENABLED = os.getenv("CLAUDE_AGENT_ENABLED", "true").lower() == "true"
CLAUDE_AGENT_DEFAULT_MODEL = os.getenv("CLAUDE_AGENT_DEFAULT_MODEL", "claude-opus-4-6")
CLAUDE_AGENT_MAX_ITERATIONS = int(os.getenv("CLAUDE_AGENT_MAX_ITERATIONS", "50"))
CLAUDE_AGENT_PERMISSION_MODE = os.getenv("CLAUDE_AGENT_PERMISSION_MODE", "ask")
CONTEXT_COMPACTION_THRESHOLD = float(os.getenv("CONTEXT_COMPACTION_THRESHOLD", "0.7"))
CLAUDE_AGENT_PROMPT_CACHING_ENABLED = (
    os.getenv("CLAUDE_AGENT_PROMPT_CACHING_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")
)
CLAUDE_AGENT_PROMPT_CACHE_CONTROL = os.getenv("CLAUDE_AGENT_PROMPT_CACHE_CONTROL", "ephemeral").strip().lower() or "ephemeral"

SYSTEM_CONTEXT_MARKER = "\n\n## CONTEXTO DISPONÍVEL\n\n"

# Model context windows
MODEL_CONTEXT_WINDOWS = {
    # Claude 4.6 (current)
    "claude-opus-4-6": 200_000,
    "claude-opus-4-6-20260115": 200_000,
    # Claude 4.5 (current)
    "claude-sonnet-4-5-20250929": 200_000,
    "claude-sonnet-4-5": 200_000,
    "claude-opus-4-5-20251101": 200_000,
    "claude-opus-4-5": 200_000,
    "claude-haiku-4-5-20251001": 200_000,
    "claude-haiku-4-5": 200_000,
    # Claude 4.x (legacy)
    "claude-opus-4-1-20250805": 200_000,
    "claude-opus-4-1": 200_000,
    "claude-sonnet-4-20250514": 200_000,
    "claude-sonnet-4-0": 200_000,
    "claude-opus-4-20250514": 200_000,
    "claude-opus-4-0": 200_000,
    # Claude 3.x (deprecated)
    "claude-3-7-sonnet-20250219": 200_000,
    "claude-3-5-sonnet-20241022": 200_000,
    "claude-3-5-haiku-20241022": 200_000,
    "claude-3-haiku-20240307": 200_000,
    "claude-3-opus-20240229": 200_000,
}

# Default tool permissions
DEFAULT_TOOL_PERMISSIONS: Dict[str, ToolApprovalMode] = {
    # Read operations: allow by default
    "search_jurisprudencia": ToolApprovalMode.ALLOW,
    "search_legislacao": ToolApprovalMode.ALLOW,
    "search_rag": ToolApprovalMode.ALLOW,
    "search_templates": ToolApprovalMode.ALLOW,
    "read_document": ToolApprovalMode.ALLOW,
    "verify_citation": ToolApprovalMode.ALLOW,
    "find_citation_source": ToolApprovalMode.ALLOW,
    "web_search": ToolApprovalMode.ALLOW,

    # Write operations: ask by default
    "edit_document": ToolApprovalMode.ASK,
    "create_section": ToolApprovalMode.ASK,
    "update_section": ToolApprovalMode.ASK,

    # High risk: deny by default
    "bash": ToolApprovalMode.DENY,
    "file_write": ToolApprovalMode.DENY,
    "file_delete": ToolApprovalMode.DENY,
}


class AgentStatus(str, Enum):
    """Agent execution status."""
    IDLE = "idle"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    PAUSED = "paused"
    COMPLETED = "completed"
    ERROR = "error"
    CANCELLED = "cancelled"


@dataclass
class AgentConfig:
    """
    Configuration for the Claude Agent Executor.

    Attributes:
        model: Claude model to use
        max_iterations: Maximum agent loop iterations
        max_tokens: Maximum output tokens per response
        temperature: Sampling temperature
        context_window: Model context window size
        compaction_threshold: Context usage threshold for compaction warning
        default_permission_mode: Default permission mode for unknown tools
        tool_permissions: Custom permissions per tool
        enable_thinking: Enable extended thinking
        thinking_budget_tokens: Token budget for thinking
        system_prompt_prefix: Prefix added to all system prompts
        enable_checkpoints: Enable automatic checkpointing
        checkpoint_interval: Iterations between auto-checkpoints
    """
    model: str = CLAUDE_AGENT_DEFAULT_MODEL
    max_iterations: int = CLAUDE_AGENT_MAX_ITERATIONS
    max_tokens: int = 16384
    temperature: float = 0.7
    context_window: int = 200_000
    compaction_threshold: float = CONTEXT_COMPACTION_THRESHOLD
    default_permission_mode: ToolApprovalMode = ToolApprovalMode.ASK
    tool_permissions: Dict[str, ToolApprovalMode] = field(default_factory=dict)
    enable_thinking: bool = True
    thinking_budget_tokens: int = 10000
    system_prompt_prefix: str = ""
    enable_checkpoints: bool = True
    checkpoint_interval: int = 5
    use_sdk: bool = True  # Use Claude Agent SDK when available (fallback to raw API)
    enable_code_execution: bool = True  # Anthropic code execution server tool (beta)
    code_execution_effort: Optional[str] = None  # "low" | "medium" | "high" | "max" (Opus 4.6 adaptive supports max)
    enable_prompt_caching: bool = CLAUDE_AGENT_PROMPT_CACHING_ENABLED
    prompt_cache_control: str = CLAUDE_AGENT_PROMPT_CACHE_CONTROL

    def __post_init__(self):
        # Merge default permissions with custom ones
        merged = dict(DEFAULT_TOOL_PERMISSIONS)
        merged.update(self.tool_permissions)
        self.tool_permissions = merged

        if self.prompt_cache_control not in ("ephemeral",):
            self.prompt_cache_control = "ephemeral"

        # Set context window from model
        if self.model in MODEL_CONTEXT_WINDOWS:
            self.context_window = MODEL_CONTEXT_WINDOWS[self.model]


@dataclass
class PendingToolApproval:
    """Represents a tool call awaiting user approval."""
    tool_id: str
    tool_name: str
    tool_input: Dict[str, Any]
    iteration: int
    approval_token: Optional[str] = None
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass
class AgentState:
    """
    Runtime state of the agent.

    Attributes:
        job_id: Associated job/session ID
        status: Current agent status
        iteration: Current iteration number
        messages: Conversation history (Claude format)
        total_input_tokens: Total input tokens used
        total_output_tokens: Total output tokens used
        tools_called: List of tools called with results
        pending_approvals: Tools awaiting user approval
        checkpoints: List of checkpoint IDs
        last_response: Last Claude response
        final_output: Final generated output
        error: Error message if failed
        start_time: Execution start time
        end_time: Execution end time
        metadata: Additional metadata
    """
    job_id: str
    status: AgentStatus = AgentStatus.IDLE
    iteration: int = 0
    messages: List[Dict[str, Any]] = field(default_factory=list)
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    tools_called: List[Dict[str, Any]] = field(default_factory=list)
    pending_approvals: List[PendingToolApproval] = field(default_factory=list)
    checkpoints: List[str] = field(default_factory=list)
    last_response: Optional[Any] = None
    container_id: Optional[str] = None  # Anthropic code execution container reuse
    final_output: str = ""
    error: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def get_context_usage(self, context_window: int) -> float:
        """Calculate context usage as percentage."""
        if context_window <= 0:
            return 0.0
        total_tokens = self.total_input_tokens + self.total_output_tokens
        return total_tokens / context_window

    def to_dict(self) -> Dict[str, Any]:
        """Serialize state to dictionary."""
        return {
            "job_id": self.job_id,
            "status": self.status.value,
            "iteration": self.iteration,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "tools_called_count": len(self.tools_called),
            "pending_approvals_count": len(self.pending_approvals),
            "checkpoints_count": len(self.checkpoints),
            "final_output_length": len(self.final_output),
            "error": self.error,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "container_id": self.container_id,
            "metadata": self.metadata,
        }


# Type alias for tool executor function
ToolExecutor = Callable[[str, Dict[str, Any]], Any]


class ClaudeAgentExecutor:
    """
    Main Claude Agent Executor implementing the agentic loop.

    The executor:
    1. Takes user prompts and optional context
    2. Runs an iterative loop calling Claude with tools
    3. Processes tool_use blocks and executes tools
    4. Handles permission checks (Allow/Deny/Ask)
    5. Emits SSE events for real-time UI updates
    6. Supports pause/resume for human-in-the-loop approval

    Usage:
        executor = ClaudeAgentExecutor(config)
        async for event in executor.run(prompt, system_prompt, context):
            # Handle SSE event
            job_manager.emit_event(event.job_id, event.type, event.data)
    """

    def __init__(
        self,
        config: Optional[AgentConfig] = None,
        tool_executor: Optional[ToolExecutor] = None,
        client: Optional[Any] = None,
    ):
        """
        Initialize the Claude Agent Executor.

        Args:
            config: Agent configuration (uses defaults if not provided)
            tool_executor: Custom tool execution function
            client: Pre-initialized Anthropic client (optional)
        """
        self.config = config or AgentConfig()
        self.tool_executor = tool_executor or self._default_tool_executor
        self._tools: List[Dict[str, Any]] = []
        self._tool_registry: Dict[str, Callable] = {}

        # Initialize Anthropic client
        if client:
            self.client = client
            self.async_client = None
        else:
            self.client, self.async_client = self._init_clients()

        # State management
        self._state: Optional[AgentState] = None
        self._cancel_requested = False

        # Tool Gateway adapter
        self._mcp_adapter: Optional[ClaudeMCPAdapter] = None
        self._execution_context: Optional[Dict[str, Any]] = None

        # Permission manager (hierarchical: session > project > global > system)
        self._permission_manager: Optional[Any] = None
        self._audit_context: Dict[str, Optional[str]] = {
            "provider": "anthropic",
            "user_id": None,
            "session_id": None,
            "project_id": None,
            "job_id": None,
        }

        # Claude Agent SDK session (for resume across turns)
        self._sdk_session_id: Optional[str] = None

    def _init_clients(self) -> Tuple[Optional[Any], Optional[Any]]:
        """Initialize Anthropic sync and async clients."""
        if not anthropic:
            logger.warning("Anthropic SDK not installed. pip install anthropic")
            return None, None

        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            logger.warning("ANTHROPIC_API_KEY not set. Claude Agent disabled.")
            return None, None

        try:
            sync_client = Anthropic(api_key=api_key)
            async_client = AsyncAnthropic(api_key=api_key)
            return sync_client, async_client
        except Exception as e:
            logger.error(f"Failed to initialize Anthropic clients: {e}")
            return None, None

    def register_tool(
        self,
        name: str,
        description: str,
        input_schema: Dict[str, Any],
        executor: Callable,
        permission: Optional[ToolApprovalMode] = None,
    ) -> None:
        """
        Register a tool for the agent to use.

        Args:
            name: Tool name (snake_case)
            description: Tool description for Claude
            input_schema: JSON Schema for tool input
            executor: Function to execute the tool
            permission: Permission mode (uses default if not set)
        """
        self._tools.append({
            "name": name,
            "description": description,
            "input_schema": input_schema,
        })
        self._tool_registry[name] = executor

        if permission:
            self.config.tool_permissions[name] = permission

        logger.debug(f"Registered tool: {name}")

    def load_unified_tools(
        self,
        include_mcp: bool = True,
        tool_names: Optional[List[str]] = None,
        execution_context: Optional[Any] = None,
    ) -> None:
        """
        Load all unified tools from the shared registry.

        This loads SDK tools, legal domain tools, and MCP tools
        with their handlers and default permissions.

        Args:
            include_mcp: Whether to include MCP tools
            tool_names: Specific tools to load (None = all)
            execution_context: ToolExecutionContext for handlers
        """
        try:
            from app.services.ai.shared import (
                get_tools_for_claude,
                get_default_permissions,
                get_tool_handlers,
                ToolExecutionContext,
                TOOLS_BY_NAME,
            )

            # Get tools in Claude format
            tools = get_tools_for_claude(
                tool_names=tool_names,
                include_mcp=include_mcp,
            )

            # Get handlers
            handlers = get_tool_handlers(execution_context)

            # Get default permissions
            permissions = get_default_permissions()

            # Register each tool
            for tool_def in tools:
                name = tool_def["name"]

                # Add to tools list (Claude format)
                self._tools.append(tool_def)

                # Create executor with proper closure
                def create_executor(tool_name: str, ctx):
                    async def executor(**kwargs):
                        result = await handlers.execute(tool_name, kwargs, ctx)
                        return result.get("result", result)
                    return executor

                self._tool_registry[name] = create_executor(name, execution_context)

                # Set permission
                if name in permissions:
                    self.config.tool_permissions[name] = permissions[name]

            logger.info(f"Loaded {len(tools)} unified tools")

        except ImportError as e:
            logger.warning(f"Could not load unified tools: {e}")
        except Exception as e:
            logger.error(f"Error loading unified tools: {e}")

    def get_registered_tools(self) -> List[Dict[str, Any]]:
        """Get list of registered tools in Claude format."""
        return self._tools

    # =========================================================================
    # TOOL GATEWAY INTEGRATION
    # =========================================================================

    def _get_context(self) -> Dict[str, Any]:
        """Get current execution context for Tool Gateway."""
        context = self._execution_context.copy() if self._execution_context else {}
        if self._state:
            context.update({
                "job_id": self._state.job_id,
                "iteration": self._state.iteration,
            })
        return context

    def _init_mcp_adapter(self, context: Optional[Dict[str, Any]] = None) -> None:
        """Initialize MCP adapter with context."""
        self._execution_context = context or {}
        self._mcp_adapter = ClaudeMCPAdapter(context=self._execution_context)

    async def load_tools_from_gateway(
        self,
        context: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Load tools from Tool Gateway via MCP adapter.

        This is the recommended way to load tools as it goes through
        the centralized Tool Gateway with policy enforcement.

        Args:
            context: Execution context (user_id, tenant_id, case_id, etc.)

        Returns:
            List of tools in Claude format
        """
        self._init_mcp_adapter(context)
        tools = await self._mcp_adapter.get_tools()

        # Register tools internally
        for tool_def in tools:
            self._tools.append(tool_def)
            name = tool_def.get("name", "")

            # Create executor that routes through MCP adapter
            def create_mcp_executor(tool_name: str, adapter: ClaudeMCPAdapter):
                async def executor(**kwargs):
                    result = await adapter.execute_tool(
                        tool_name,
                        kwargs,
                        self._get_context()
                    )
                    return result
                return executor

            self._tool_registry[name] = create_mcp_executor(name, self._mcp_adapter)

        logger.info(f"Loaded {len(tools)} tools from Tool Gateway")
        return tools

    async def execute_tool_via_gateway(
        self,
        tool_use_block: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Execute a tool via the Tool Gateway.

        Args:
            tool_use_block: Claude tool_use content block

        Returns:
            tool_result block for Claude
        """
        if not self._mcp_adapter:
            self._init_mcp_adapter()

        return await self._mcp_adapter.handle_tool_use(
            tool_use_block,
            self._get_context()
        )

    def _coerce_permission_mode(self, value: Any) -> ToolApprovalMode:
        """Normalize permission values coming from config/DB."""
        if isinstance(value, ToolApprovalMode):
            return value
        raw = str(value or "").strip().lower()
        if raw == ToolApprovalMode.ALLOW.value:
            return ToolApprovalMode.ALLOW
        if raw == ToolApprovalMode.DENY.value:
            return ToolApprovalMode.DENY
        return ToolApprovalMode.ASK

    def _get_tool_permission(self, tool_name: str) -> ToolApprovalMode:
        """Get fallback permission mode from local config."""
        value = self.config.tool_permissions.get(
            tool_name,
            self.config.default_permission_mode,
        )
        return self._coerce_permission_mode(value)

    async def _init_permission_manager(
        self,
        *,
        db: Optional[Any],
        user_id: Optional[str],
        session_id: Optional[str] = None,
        project_id: Optional[str] = None,
        security_profile: Optional[str] = None,
    ) -> None:
        """Initialize PermissionManager for this run when DB/user are available."""
        self._permission_manager = None
        if not db or not user_id:
            return
        try:
            from app.services.ai.claude_agent.permissions import PermissionManager

            self._permission_manager = PermissionManager(
                db=db,
                user_id=user_id,
                session_id=session_id,
                project_id=project_id,
                security_profile=SecurityProfile.from_value(security_profile),
            )
        except Exception as e:
            logger.warning(f"Failed to initialize PermissionManager: {e}")

    async def _resolve_tool_permission(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
    ) -> ToolApprovalMode:
        """
        Resolve permission via PermissionManager first, then local fallback.
        """
        if self._permission_manager:
            try:
                pm_result = await self._permission_manager.check(tool_name, tool_input)
                return self._coerce_permission_mode(pm_result.decision)
            except Exception as e:
                logger.warning(
                    f"PermissionManager check failed for {tool_name}, using local fallback: {e}"
                )
                fallback = self._get_tool_permission(tool_name)
                try:
                    get_tool_audit_log().record_permission_decision(
                        tool_name=tool_name,
                        decision=fallback.value,
                        user_id=self._audit_context.get("user_id"),
                        session_id=self._audit_context.get("session_id"),
                        project_id=self._audit_context.get("project_id"),
                        job_id=self._audit_context.get("job_id"),
                        provider="anthropic",
                        source="permission_manager_fallback",
                        rule_scope="executor_fallback",
                        tool_input=tool_input,
                    )
                except Exception:
                    pass
                return fallback

        fallback = self._get_tool_permission(tool_name)
        try:
            get_tool_audit_log().record_permission_decision(
                tool_name=tool_name,
                decision=fallback.value,
                user_id=self._audit_context.get("user_id"),
                session_id=self._audit_context.get("session_id"),
                project_id=self._audit_context.get("project_id"),
                job_id=self._audit_context.get("job_id"),
                provider="anthropic",
                source="executor_config",
                rule_scope="executor_fallback",
                tool_input=tool_input,
            )
        except Exception:
            pass
        return fallback

    def _attach_trace_metadata_to_done_event(
        self,
        event: SSEEvent,
        trace_metadata: Dict[str, Any],
    ) -> SSEEvent:
        """Attach LangSmith metadata to DONE events so frontend can render trace links."""
        if not trace_metadata or event.type != SSEEventType.DONE:
            return event

        data = dict(event.data or {})
        metadata = dict(data.get("metadata") or {})
        changed = False
        for key, value in trace_metadata.items():
            if not value:
                continue
            if metadata.get(key) in (None, ""):
                metadata[key] = value
                changed = True
            if data.get(key) in (None, ""):
                data[key] = value
                changed = True

        if changed:
            data["metadata"] = metadata
            event.data = data
        return event

    async def _default_tool_executor(
        self,
        tool_name: str,
        tool_input: Dict[str, Any]
    ) -> Any:
        """
        Default tool executor using registered tools.

        Args:
            tool_name: Name of the tool to execute
            tool_input: Input parameters for the tool

        Returns:
            Tool execution result
        """
        if tool_name not in self._tool_registry:
            return {"error": f"Tool '{tool_name}' not registered"}

        executor = self._tool_registry[tool_name]
        try:
            # Check if executor is async
            if asyncio.iscoroutinefunction(executor):
                result = await executor(**tool_input)
            else:
                result = executor(**tool_input)
            return result
        except Exception as e:
            logger.error(f"Tool execution error for {tool_name}: {e}")
            return {"error": str(e)}

    def _build_system_prompt(
        self,
        base_prompt: str,
        context: Optional[str] = None
    ) -> str:
        """Build the complete system prompt."""
        parts = []

        # Add prefix if configured
        if self.config.system_prompt_prefix:
            parts.append(self.config.system_prompt_prefix)

        # Add base prompt
        parts.append(base_prompt)

        # Add context if provided
        if context:
            parts.append(f"{SYSTEM_CONTEXT_MARKER}{context}")

        return "\n\n".join(parts)

    def _build_system_payload(
        self,
        system_prompt: Any,
    ) -> Any:
        """
        Build Anthropic `system` payload with prompt caching blocks when enabled.

        Preserves backward compatibility by returning the original string when
        prompt caching is disabled or input is not a string.
        """
        if not self.config.enable_prompt_caching or not isinstance(system_prompt, str):
            return system_prompt

        if not system_prompt.strip():
            return system_prompt

        base_prompt, marker, context_part = system_prompt.partition(SYSTEM_CONTEXT_MARKER)
        blocks: List[Dict[str, Any]] = []

        base_text = base_prompt.strip()
        if base_text:
            blocks.append(
                {
                    "type": "text",
                    "text": base_text,
                    "cache_control": {"type": self.config.prompt_cache_control},
                }
            )

        context_text = context_part.strip()
        if marker and context_text:
            blocks.append(
                {
                    "type": "text",
                    "text": f"## CONTEXTO DISPONÍVEL\n\n{context_text}",
                    "cache_control": {"type": self.config.prompt_cache_control},
                }
            )

        return blocks or system_prompt

    async def _call_claude(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: Any,
        container_id: Optional[str] = None,
    ) -> Any:
        """
        Call Claude API with messages and tools.

        Args:
            messages: Conversation history
            system_prompt: System prompt
            container_id: Optional container ID for code execution reuse

        Returns:
            Claude Message response
        """
        if not self.async_client:
            raise RuntimeError("Anthropic async client not initialized")

        system_payload = self._build_system_payload(system_prompt)

        # Build API kwargs
        kwargs: Dict[str, Any] = {
            "model": self.config.model,
            "max_tokens": self.config.max_tokens,
            "system": system_payload,
            "messages": messages,
        }

        # Build tools list
        tools = list(self._tools) if self._tools else []

        # Add code execution server tool if enabled (only compatible models)
        _ce_compatible = any(
            self.config.model.startswith(p)
            for p in (
                "claude-sonnet-4",   # Sonnet 4, 4.5
                "claude-opus-4",     # Opus 4, 4.1, 4.5
                "claude-haiku-4",    # Haiku 4.5
                "claude-3-7-sonnet", # 3.7 (deprecated)
                "claude-3-5-haiku",  # 3.5 Haiku (deprecated)
            )
        )
        if self.config.enable_code_execution and _ce_compatible:
            tools.append({
                "type": "code_execution_20250825",
                "name": "code_execution",
            })

        if tools:
            kwargs["tools"] = tools

        is_opus_46 = self.config.model.startswith("claude-opus-4-6")

        # Thinking config:
        # - Opus 4.6: adaptive thinking (opt-in via `thinking`)
        # - Legacy models: extended thinking with budget_tokens
        if self.config.enable_thinking:
            if is_opus_46:
                kwargs["thinking"] = {"type": "adaptive"}
                adaptive_effort = (self.config.code_execution_effort or os.getenv("CLAUDE_ADAPTIVE_THINKING_EFFORT", "high")).strip().lower()
                if adaptive_effort not in ("low", "medium", "high", "max"):
                    adaptive_effort = "high"
                kwargs["output_config"] = {"effort": adaptive_effort}
            else:
                kwargs["thinking"] = {
                    "type": "enabled",
                    "budget_tokens": self.config.thinking_budget_tokens,
                }

        # Add temperature
        if not self.config.enable_thinking:
            # Temperature not compatible with extended thinking
            kwargs["temperature"] = self.config.temperature

        # Use beta API when code execution is enabled and model is compatible
        use_beta = self.config.enable_code_execution and _ce_compatible

        # Pass container_id for code execution state reuse
        if use_beta and container_id:
            kwargs["container"] = container_id

        # Effort parameter (legacy Opus models only, requires separate beta header).
        # Opus 4.6 uses adaptive thinking + output_config without effort beta.
        _effort_betas: List[str] = []
        if (
            not is_opus_46
            and self.config.code_execution_effort
            and self.config.code_execution_effort in ("low", "medium", "high")
            and self.config.model.startswith("claude-opus-4")
        ):
                kwargs["output_config"] = {"effort": self.config.code_execution_effort}
                _effort_betas.append("effort-2025-11-24")

        start_time = time.time()
        try:
            standard_kwargs = dict(kwargs)
            # Standard messages endpoint does not accept beta-only fields.
            standard_kwargs.pop("betas", None)
            standard_kwargs.pop("container", None)

            if use_beta:
                beta_kwargs = dict(kwargs)
                beta_kwargs["betas"] = ["code-execution-2025-08-25"] + _effort_betas

                try:
                    response = await self.async_client.beta.messages.create(**beta_kwargs)
                except Exception as beta_exc:
                    logger.warning(
                        f"Claude beta.messages.create failed ({beta_exc}); falling back to messages.create"
                    )
                    response = await self.async_client.messages.create(**standard_kwargs)
                else:
                    content = getattr(response, "content", None)
                    stop_reason = getattr(response, "stop_reason", None)
                    if not isinstance(content, list) or not isinstance(stop_reason, (str, type(None))):
                        logger.warning(
                            "Claude beta response malformed; falling back to messages.create"
                        )
                        response = await self.async_client.messages.create(**standard_kwargs)
            else:
                response = await self.async_client.messages.create(**standard_kwargs)
            latency_ms = int((time.time() - start_time) * 1000)

            # Record API call for billing
            with billing_context(node="claude_agent", size="L"):
                record_api_call(
                    kind="llm",
                    provider="anthropic",
                    model=self.config.model,
                    success=True,
                    meta={
                        "tokens_in": int(getattr(response.usage, "input_tokens", 0) or 0),
                        "tokens_out": int(getattr(response.usage, "output_tokens", 0) or 0),
                        "latency_ms": latency_ms,
                        "n_requests": 1,
                    },
                )

            return response

        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            record_api_call(
                kind="llm",
                provider="anthropic",
                model=self.config.model,
                success=False,
                meta={
                    "tokens_in": 0,
                    "tokens_out": 0,
                    "latency_ms": latency_ms,
                    "n_requests": 1,
                },
            )
            raise

    def _usage_tokens(self, response: Any) -> Tuple[int, int]:
        """Safely extract usage tokens from SDK responses/mocks."""
        usage = getattr(response, "usage", None)
        raw_in = getattr(usage, "input_tokens", 0) if usage is not None else 0
        raw_out = getattr(usage, "output_tokens", 0) if usage is not None else 0

        try:
            tokens_in = int(raw_in)
        except Exception:
            tokens_in = 0
        try:
            tokens_out = int(raw_out)
        except Exception:
            tokens_out = 0

        return max(0, tokens_in), max(0, tokens_out)

    def _extract_response_content(self, response: Any) -> Tuple[str, List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Extract text, tool_use blocks, and server tool events from response.

        Args:
            response: Claude Message response

        Returns:
            Tuple of (text_content, tool_use_blocks, server_tool_events)
        """
        text_parts = []
        tool_uses = []
        server_tool_events = []

        for block in response.content:
            block_type = getattr(block, "type", None)

            # Standard tool_use (client-side tools)
            if block_type == "tool_use":
                tool_uses.append({
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                })

            # Server tool use (code execution initiated by Claude)
            elif block_type == "server_tool_use":
                server_tool_events.append({
                    "event_type": "code_execution",
                    "id": block.id,
                    "name": getattr(block, "name", "code_execution"),
                    "input": getattr(block, "input", {}),
                })

            # Bash code execution result
            elif block_type == "bash_code_execution_tool_result":
                content = getattr(block, "content", None)
                if content:
                    content_type = getattr(content, "type", "")
                    if content_type == "bash_code_execution_result":
                        server_tool_events.append({
                            "event_type": "code_execution_result",
                            "tool_use_id": getattr(block, "tool_use_id", ""),
                            "stdout": getattr(content, "stdout", ""),
                            "stderr": getattr(content, "stderr", ""),
                            "return_code": getattr(content, "return_code", -1),
                            "files": [
                                {"file_id": f.file_id}
                                for f in getattr(content, "content", [])
                                if hasattr(f, "file_id")
                            ],
                        })

            # Text editor code execution result
            elif block_type == "text_editor_code_execution_tool_result":
                content = getattr(block, "content", None)
                if content:
                    server_tool_events.append({
                        "event_type": "code_execution_result",
                        "tool_use_id": getattr(block, "tool_use_id", ""),
                        "stdout": getattr(content, "content", ""),
                        "stderr": "",
                        "return_code": 0,
                    })

            # Code execution tool result (legacy format)
            elif block_type == "code_execution_tool_result":
                content = getattr(block, "content", None)
                if content:
                    server_tool_events.append({
                        "event_type": "code_execution_result",
                        "tool_use_id": getattr(block, "tool_use_id", ""),
                        "stdout": getattr(content, "stdout", ""),
                        "stderr": getattr(content, "stderr", ""),
                        "return_code": getattr(content, "return_code", -1),
                    })

            elif hasattr(block, "text"):
                text_parts.append(block.text)

        return "\n".join(text_parts), tool_uses, server_tool_events

    async def _process_tool_use(
        self,
        tool_use: Dict[str, Any],
        state: AgentState,
    ) -> AsyncGenerator[SSEEvent, None]:
        """
        Process a tool_use block with permission checking.

        Args:
            tool_use: Tool use block from Claude
            state: Current agent state

        Yields:
            SSE events for tool processing
        """
        tool_id = tool_use["id"]
        tool_name = tool_use["name"]
        tool_input = tool_use["input"]

        # Resolve permission for this tool (hierarchical PM -> local fallback)
        permission = await self._resolve_tool_permission(tool_name, tool_input)

        # Emit tool_call event
        yield tool_call_event(
            job_id=state.job_id,
            tool_name=tool_name,
            tool_input=tool_input,
            tool_id=tool_id,
            permission_mode=permission,
        )

        if permission == ToolApprovalMode.DENY:
            # Tool denied - return error result
            yield tool_result_event(
                job_id=state.job_id,
                tool_name=tool_name,
                tool_id=tool_id,
                result=None,
                success=False,
                error=f"Tool '{tool_name}' is denied by permission settings",
            )
            return

        if permission == ToolApprovalMode.ASK:
            # Need user approval - pause execution
            approval_token: Optional[str] = None
            try:
                from app.services.ai.shared.approval_tokens import make_tool_approval_token
                approval_token = make_tool_approval_token(
                    job_id=state.job_id,
                    tool_id=tool_id,
                    tool_name=tool_name,
                    tool_input=tool_input,
                    tenant_id=(
                        str(self._execution_context.get("tenant_id"))
                        if isinstance(getattr(self, "_execution_context", None), dict) and self._execution_context.get("tenant_id")
                        else None
                    ),
                )
            except Exception:
                approval_token = None
            pending = PendingToolApproval(
                tool_id=tool_id,
                tool_name=tool_name,
                tool_input=tool_input,
                iteration=state.iteration,
                approval_token=approval_token,
            )
            state.pending_approvals.append(pending)
            state.status = AgentStatus.WAITING_APPROVAL

            yield tool_approval_required_event(
                job_id=state.job_id,
                tool_name=tool_name,
                tool_input=tool_input,
                tool_id=tool_id,
                risk_level="medium" if "edit" in tool_name or "write" in tool_name else "low",
                approval_token=approval_token,
            )
            return

        # Permission is ALLOW - execute the tool and emit result event
        result_event = await self._execute_and_emit_tool(tool_id, tool_name, tool_input, state)
        yield result_event

    async def _execute_and_emit_tool(
        self,
        tool_id: str,
        tool_name: str,
        tool_input: Dict[str, Any],
        state: AgentState,
    ) -> SSEEvent:
        """Execute a tool and emit result event."""
        start_time = time.time()
        try:
            if asyncio.iscoroutinefunction(self.tool_executor):
                result = await self.tool_executor(tool_name, tool_input)
            else:
                result = self.tool_executor(tool_name, tool_input)

            execution_time_ms = int((time.time() - start_time) * 1000)
            success = not (isinstance(result, dict) and "error" in result)

            # Record tool call
            state.tools_called.append({
                "tool_id": tool_id,
                "tool_name": tool_name,
                "tool_input": tool_input,
                "result": result,
                "success": success,
                "execution_time_ms": execution_time_ms,
                "iteration": state.iteration,
            })
            try:
                get_tool_audit_log().record_tool_execution(
                    tool_name=tool_name,
                    success=success,
                    user_id=self._audit_context.get("user_id"),
                    session_id=self._audit_context.get("session_id"),
                    project_id=self._audit_context.get("project_id"),
                    job_id=self._audit_context.get("job_id"),
                    provider="anthropic",
                    tool_id=tool_id,
                    duration_ms=execution_time_ms,
                    error=(result.get("error") if isinstance(result, dict) else None),
                    tool_input=tool_input,
                )
            except Exception:
                pass

            return tool_result_event(
                job_id=state.job_id,
                tool_name=tool_name,
                tool_id=tool_id,
                result=result,
                success=success,
                error=result.get("error") if isinstance(result, dict) else None,
                execution_time_ms=execution_time_ms,
            )

        except Exception as e:
            execution_time_ms = int((time.time() - start_time) * 1000)
            logger.error(f"Tool execution failed: {tool_name} - {e}")

            state.tools_called.append({
                "tool_id": tool_id,
                "tool_name": tool_name,
                "tool_input": tool_input,
                "result": None,
                "success": False,
                "error": str(e),
                "execution_time_ms": execution_time_ms,
                "iteration": state.iteration,
            })
            try:
                get_tool_audit_log().record_tool_execution(
                    tool_name=tool_name,
                    success=False,
                    user_id=self._audit_context.get("user_id"),
                    session_id=self._audit_context.get("session_id"),
                    project_id=self._audit_context.get("project_id"),
                    job_id=self._audit_context.get("job_id"),
                    provider="anthropic",
                    tool_id=tool_id,
                    duration_ms=execution_time_ms,
                    error=str(e),
                    tool_input=tool_input,
                )
            except Exception:
                pass

            return tool_result_event(
                job_id=state.job_id,
                tool_name=tool_name,
                tool_id=tool_id,
                result=None,
                success=False,
                error=str(e),
                execution_time_ms=execution_time_ms,
            )

    def _build_tool_result_message(
        self,
        tool_results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Build a user message with tool results."""
        content = []
        for result in tool_results:
            content.append({
                "type": "tool_result",
                "tool_use_id": result["tool_id"],
                "content": str(result.get("result", "")),
                "is_error": not result.get("success", True),
            })
        return {"role": "user", "content": content}

    async def _create_checkpoint(self, state: AgentState, description: str = "") -> str:
        """Create a checkpoint of the current state."""
        checkpoint_id = str(uuid.uuid4())
        state.checkpoints.append(checkpoint_id)

        # TODO: Persist checkpoint to database
        # For now, just return the ID

        logger.info(f"Checkpoint created: {checkpoint_id} at iteration {state.iteration}")
        return checkpoint_id

    # =========================================================================
    # CLAUDE AGENT SDK — DUAL MODE
    # =========================================================================

    async def _run_with_sdk(
        self,
        prompt: str,
        system_prompt: str,
        context: Optional[str],
        job_id: str,
        user_id: Optional[str] = None,
        case_id: Optional[str] = None,
        db: Optional[Any] = None,
    ) -> AsyncGenerator[SSEEvent, None]:
        """
        Run using the Claude Agent SDK with pre-configured MCP tools.

        Falls back to _run_with_raw_api if SDK is not available or fails.

        Args:
            prompt: User prompt
            system_prompt: System prompt for Claude
            context: Additional context
            job_id: Job ID for SSE events
            user_id: User ID for template loading and data scoping
            db: Async database session for template loading
        """
        # Build MCP servers
        mcp_servers: Dict[str, Any] = {}

        # In-process MCP server with Iudex tools
        iudex_server = create_iudex_mcp_server()
        if iudex_server:
            mcp_servers["iudex-legal"] = iudex_server

        # Inject per-run context for SDK tools (tenant/user/case).
        # Uses ContextVar in sdk_tools, so it's safe under concurrency.
        try:
            tenant_id = user_id or "default"
            if user_id and db:
                try:
                    from sqlalchemy import select
                    from app.models.user import User

                    res = await db.execute(
                        select(User.organization_id).where(User.id == user_id)
                    )
                    org_id = res.scalar_one_or_none()
                    if org_id:
                        tenant_id = str(org_id)
                except Exception as e:
                    logger.debug(f"[{job_id}] tenant_id resolve failed: {e}")

            set_iudex_tool_context(
                {
                    "user_id": user_id or "default",
                    "tenant_id": tenant_id,
                    "case_id": case_id,
                    "job_id": job_id,
                }
            )
        except Exception as e:
            logger.debug(f"[{job_id}] SDK tool context injection failed: {e}")

        # Load user's .md agent templates
        user_templates = ""
        if user_id and db:
            try:
                user_templates = await load_agent_templates(user_id, db)
            except Exception as e:
                logger.warning(f"Failed to load agent templates: {e}")
        matched_skill_prompt = ""
        matched_skill_name: Optional[str] = None
        if user_id and db:
            try:
                from app.services.ai.skills.matcher import match_user_skill, render_skill_prompt

                skill_match = await match_user_skill(
                    user_id=user_id,
                    user_input=prompt,
                    db=db,
                    include_builtin=True,
                )
                if skill_match:
                    matched_skill_prompt = render_skill_prompt(skill_match)
                    matched_skill_name = skill_match.skill.name
            except Exception as e:
                logger.warning(f"Failed to match user skill: {e}")

        # Build full system prompt
        full_system = self._build_system_prompt(system_prompt, context)
        if user_templates:
            full_system = f"{full_system}\n\n# INSTRUÇÕES DO USUÁRIO (Templates)\n\n{user_templates}"
        if matched_skill_prompt:
            full_system = f"{full_system}\n\n# SKILL CORRESPONDENTE\n\n{matched_skill_prompt}"

        sdk_permission_mode = (os.getenv("CLAUDE_SDK_PERMISSION_MODE", "default") or "default").strip().lower()
        if sdk_permission_mode not in ("default", "ask", "allow", "deny", "bypass"):
            sdk_permission_mode = "default"
        # When hierarchical PermissionManager is available, keep SDK in safer interactive mode.
        if self._permission_manager and sdk_permission_mode == "default":
            sdk_permission_mode = "ask"

        # Build SDK options
        options = ClaudeAgentOptions(
            model=self.config.model,
            system_prompt=full_system,
            mcp_servers=mcp_servers if mcp_servers else None,
            allowed_tools=["mcp__iudex-legal__*"] if mcp_servers else None,
            permission_mode=sdk_permission_mode,
            max_turns=self.config.max_iterations,
        )

        # Resume session if available
        if self._sdk_session_id:
            options.resume = self._sdk_session_id

        # Emit start event
        yield create_sse_event(
            SSEEventType.AGENT_START,
            {
                "job_id": job_id,
                "model": self.config.model,
                "max_iterations": self.config.max_iterations,
                "sdk_mode": True,
                "tools_count": 7 if mcp_servers else 0,
                "matched_skill": matched_skill_name,
            },
            job_id=job_id,
            phase="agent",
        )

        logger.info(f"[{job_id}] Using Claude Agent SDK (model={self.config.model})")

        try:
            async for message in query(prompt=prompt, options=options):
                if isinstance(message, SystemMessage):
                    subtype = getattr(message, "subtype", None)
                    if subtype == "init":
                        data = getattr(message, "data", {})
                        self._sdk_session_id = data.get("session_id")
                        logger.debug(f"[{job_id}] SDK session: {self._sdk_session_id}")

                elif isinstance(message, AssistantMessage):
                    for block in message.content:
                        if hasattr(block, "text") and block.text:
                            yield token_event(job_id=job_id, token=block.text)
                        elif hasattr(block, "name"):
                            tool_name = str(getattr(block, "name", "") or "")
                            tool_input = getattr(block, "input", {}) or {}
                            if not isinstance(tool_input, dict):
                                tool_input = {}
                            permission_mode = ToolApprovalMode.ASK
                            if self._permission_manager:
                                permission_mode = await self._resolve_tool_permission(tool_name, tool_input)
                            else:
                                if sdk_permission_mode == "allow":
                                    permission_mode = ToolApprovalMode.ALLOW
                                elif sdk_permission_mode == "deny":
                                    permission_mode = ToolApprovalMode.DENY
                                try:
                                    get_tool_audit_log().record_permission_decision(
                                        tool_name=tool_name,
                                        decision=permission_mode.value,
                                        user_id=self._audit_context.get("user_id"),
                                        session_id=self._audit_context.get("session_id"),
                                        project_id=self._audit_context.get("project_id"),
                                        job_id=self._audit_context.get("job_id"),
                                        provider="anthropic",
                                        tool_id=getattr(block, "id", None),
                                        source="sdk_permission_mode",
                                        rule_scope="sdk",
                                        tool_input=tool_input,
                                    )
                                except Exception:
                                    pass

                            # Tool use block
                            yield tool_call_event(
                                job_id=job_id,
                                tool_name=tool_name,
                                tool_input=tool_input,
                                tool_id=getattr(block, "id", str(uuid.uuid4())),
                                permission_mode=permission_mode,
                            )

                elif isinstance(message, ResultMessage):
                    result_text = ""
                    if hasattr(message, "content"):
                        for block in message.content:
                            if hasattr(block, "text"):
                                result_text += block.text
                    elif hasattr(message, "result"):
                        result_text = str(message.result)

                    yield done_event(
                        job_id=job_id,
                        final_text=result_text,
                        metadata={
                            "sdk_mode": True,
                            "session_id": self._sdk_session_id,
                            "matched_skill": matched_skill_name,
                        },
                    )
                    return

            # Stream ended without ResultMessage
            yield done_event(
                job_id=job_id,
                metadata={
                    "sdk_mode": True,
                    "stream_ended": True,
                    "matched_skill": matched_skill_name,
                },
            )

        except Exception as e:
            logger.exception(f"[{job_id}] Claude SDK execution error: {e}")
            raise  # Let the dispatcher handle fallback

    # =========================================================================
    # RAW API MODE (FALLBACK)
    # =========================================================================

    async def run(
        self,
        prompt: str,
        system_prompt: str = "",
        context: Optional[str] = None,
        job_id: Optional[str] = None,
        initial_messages: Optional[List[Dict[str, Any]]] = None,
        user_id: Optional[str] = None,
        case_id: Optional[str] = None,
        session_id: Optional[str] = None,
        db: Optional[Any] = None,
        security_profile: Optional[str] = None,
    ) -> AsyncGenerator[SSEEvent, None]:
        """
        Run the agent loop — dispatcher for SDK vs raw API mode.

        When Claude Agent SDK is available and config.use_sdk is True,
        uses the SDK with pre-configured MCP tools. Falls back to the
        raw Anthropic API loop on failure or when SDK is unavailable.

        Args:
            prompt: User prompt
            system_prompt: System prompt for Claude
            context: Additional context (RAG results, case bundle, etc.)
            job_id: Job ID for SSE events (auto-generated if not provided)
            initial_messages: Previous conversation history (optional)
            user_id: User ID for template loading (SDK mode)
            db: Async database session (SDK mode)

        Yields:
            SSE events for each action in the agent loop
        """
        job_id = job_id or str(uuid.uuid4())
        await self._init_permission_manager(
            db=db,
            user_id=user_id,
            session_id=session_id,
            project_id=case_id,
            security_profile=security_profile,
        )
        self._audit_context = {
            "provider": "anthropic",
            "user_id": str(user_id) if user_id else None,
            "session_id": str(session_id) if session_id else None,
            "project_id": str(case_id) if case_id else None,
            "job_id": str(job_id) if job_id else None,
        }

        trace_metadata = {
            "job_id": job_id,
            "user_id": user_id,
            "session_id": session_id,
            "case_id": case_id,
            "model": self.config.model,
            "use_sdk": bool(CLAUDE_SDK_AVAILABLE and self.config.use_sdk),
        }
        with langsmith_trace(
            "claude_agent_executor.run",
            run_type="agent",
            metadata=trace_metadata,
            tags=["claude-agent", "executor"],
        ) as run_ctx:
            langsmith_metadata = extract_langsmith_run_metadata(run_ctx)
            # Try SDK mode first
            if CLAUDE_SDK_AVAILABLE and self.config.use_sdk:
                try:
                    async for event in self._run_with_sdk(
                        prompt=prompt,
                        system_prompt=system_prompt,
                        context=context,
                        job_id=job_id,
                        user_id=user_id,
                        case_id=case_id,
                        db=db,
                    ):
                        yield self._attach_trace_metadata_to_done_event(
                            event,
                            langsmith_metadata,
                        )
                    return
                except Exception as exc:
                    logger.warning(f"[{job_id}] Claude SDK failed, falling back to raw API: {exc}")

            # Fallback: raw Anthropic API loop
            async for event in self._run_with_raw_api(
                prompt=prompt,
                system_prompt=system_prompt,
                context=context,
                job_id=job_id,
                initial_messages=initial_messages,
                user_id=user_id,
                db=db,
            ):
                yield self._attach_trace_metadata_to_done_event(
                    event,
                    langsmith_metadata,
                )

    async def _run_with_raw_api(
        self,
        prompt: str,
        system_prompt: str = "",
        context: Optional[str] = None,
        job_id: Optional[str] = None,
        initial_messages: Optional[List[Dict[str, Any]]] = None,
        user_id: Optional[str] = None,
        db: Optional[Any] = None,
    ) -> AsyncGenerator[SSEEvent, None]:
        """
        Run the agent loop using the raw Anthropic API.

        This is the original implementation, now used as fallback when
        the Claude Agent SDK is unavailable or fails.

        Args:
            prompt: User prompt
            system_prompt: System prompt for Claude
            context: Additional context (RAG results, case bundle, etc.)
            job_id: Job ID for SSE events (auto-generated if not provided)
            initial_messages: Previous conversation history (optional)

        Yields:
            SSE events for each action in the agent loop
        """
        if not self.async_client:
            yield error_event(
                job_id=job_id or "unknown",
                error="Anthropic client not initialized",
                error_type="initialization_error",
                recoverable=False,
            )
            return

        # Initialize state
        job_id = job_id or str(uuid.uuid4())
        self._state = AgentState(
            job_id=job_id,
            status=AgentStatus.RUNNING,
            start_time=datetime.now(timezone.utc).isoformat(),
            messages=initial_messages or [],
        )
        state = self._state
        self._cancel_requested = False

        # Build complete system prompt
        full_system_prompt = self._build_system_prompt(system_prompt, context)
        matched_skill_name: Optional[str] = None
        if user_id and db:
            try:
                from app.services.ai.skills.matcher import match_user_skill, render_skill_prompt

                skill_match = await match_user_skill(
                    user_id=user_id,
                    user_input=prompt,
                    db=db,
                    include_builtin=True,
                )
                if skill_match:
                    matched_skill_name = skill_match.skill.name
                    skill_prompt = render_skill_prompt(skill_match)
                    full_system_prompt = f"{full_system_prompt}\n\n# SKILL CORRESPONDENTE\n\n{skill_prompt}"
            except Exception as e:
                logger.warning(f"Failed to match user skill (raw mode): {e}")

        # Add user message
        state.messages.append({"role": "user", "content": prompt})

        # Emit start event
        yield create_sse_event(
            SSEEventType.AGENT_START,
            {
                "job_id": job_id,
                "model": self.config.model,
                "max_iterations": self.config.max_iterations,
                "tools_count": len(self._tools),
                "matched_skill": matched_skill_name,
            },
            job_id=job_id,
            phase="agent",
        )

        try:
            # Main agent loop
            while state.iteration < self.config.max_iterations:
                if self._cancel_requested:
                    state.status = AgentStatus.CANCELLED
                    yield done_event(
                        job_id=job_id,
                        metadata={"cancelled": True, "iteration": state.iteration}
                    )
                    return

                state.iteration += 1

                # Emit iteration event
                yield agent_iteration_event(
                    job_id=job_id,
                    iteration=state.iteration,
                    status="calling_claude",
                )

                # Call Claude
                try:
                    response = await self._call_claude(
                        state.messages,
                        full_system_prompt,
                        container_id=state.container_id,
                    )
                except Exception as e:
                    state.status = AgentStatus.ERROR
                    state.error = str(e)
                    yield error_event(
                        job_id=job_id,
                        error=str(e),
                        error_type="api_error",
                        recoverable=True,
                    )
                    return

                # Update token counts (robust to mocked/non-numeric usage payloads)
                tokens_in, tokens_out = self._usage_tokens(response)
                state.total_input_tokens += tokens_in
                state.total_output_tokens += tokens_out
                state.last_response = response

                # Extract container_id for code execution reuse
                _container = getattr(response, "container", None)
                if _container and hasattr(_container, "id"):
                    state.container_id = _container.id

                # Check context usage
                context_usage = state.get_context_usage(self.config.context_window)
                if context_usage >= self.config.compaction_threshold:
                    yield context_warning_event(
                        job_id=job_id,
                        current_tokens=state.total_input_tokens + state.total_output_tokens,
                        max_tokens=self.config.context_window,
                        usage_percent=context_usage * 100,
                    )

                # Extract content
                text_content, tool_uses, server_tool_events = self._extract_response_content(response)

                # Emit text content as tokens
                if text_content:
                    yield token_event(job_id=job_id, token=text_content)

                # Emit server tool events (code execution)
                for ste in server_tool_events:
                    yield create_sse_event(
                        SSEEventType.CODE_EXECUTION if ste["event_type"] == "code_execution" else SSEEventType.CODE_EXECUTION_RESULT,
                        ste,
                        job_id=job_id,
                    )

                # Add assistant message to history
                state.messages.append({
                    "role": "assistant",
                    "content": response.content,
                })

                # Check stop reason
                if response.stop_reason == "end_turn":
                    # Agent finished
                    state.final_output = text_content
                    state.status = AgentStatus.COMPLETED
                    state.end_time = datetime.now(timezone.utc).isoformat()

                    yield done_event(
                        job_id=job_id,
                        final_text=text_content,
                        metadata={
                            "iterations": state.iteration,
                            "total_tokens": state.total_input_tokens + state.total_output_tokens,
                            "tools_called": len(state.tools_called),
                            "matched_skill": matched_skill_name,
                        }
                    )
                    return

                # Handle pause_turn (code execution in progress — continue the turn)
                if response.stop_reason == "pause_turn":
                    # The API paused a long-running code execution turn.
                    # Re-send the assistant response as-is to let Claude continue.
                    continue

                # Process tool uses
                if tool_uses:
                    tool_results = []

                    for tool_use in tool_uses:
                        async for event in self._process_tool_use(tool_use, state):
                            yield event

                            # Check if waiting for approval
                            if state.status == AgentStatus.WAITING_APPROVAL:
                                # Pause and wait for resume
                                return

                        # Collect results for tools that were executed
                        if state.tools_called and state.tools_called[-1]["tool_id"] == tool_use["id"]:
                            tool_results.append(state.tools_called[-1])

                    # Add tool results to messages
                    if tool_results:
                        state.messages.append(
                            self._build_tool_result_message(tool_results)
                        )

                # Create checkpoint if enabled
                if self.config.enable_checkpoints:
                    if state.iteration % self.config.checkpoint_interval == 0:
                        checkpoint_id = await self._create_checkpoint(
                            state,
                            f"Auto-checkpoint at iteration {state.iteration}"
                        )
                        yield checkpoint_created_event(
                            job_id=job_id,
                            checkpoint_id=checkpoint_id,
                            description=f"Iteration {state.iteration}",
                            snapshot_type="auto",
                        )

            # Max iterations reached
            state.status = AgentStatus.COMPLETED
            state.end_time = datetime.now(timezone.utc).isoformat()
            yield done_event(
                job_id=job_id,
                final_text=state.final_output,
                metadata={
                    "max_iterations_reached": True,
                    "iterations": state.iteration,
                    "matched_skill": matched_skill_name,
                }
            )

        except Exception as e:
            state.status = AgentStatus.ERROR
            state.error = str(e)
            state.end_time = datetime.now(timezone.utc).isoformat()
            logger.exception(f"Agent execution error: {e}")
            yield error_event(
                job_id=job_id,
                error=str(e),
                error_type="execution_error",
                recoverable=False,
            )

    async def resume(
        self,
        approval: bool,
        tool_id: Optional[str] = None,
        approval_token: Optional[str] = None,
        remember_choice: bool = False,
        scope: Literal["session", "project", "global"] = "session",
    ) -> AsyncGenerator[SSEEvent, None]:
        """
        Resume execution after tool approval.

        Args:
            approval: True to approve, False to deny
            tool_id: Specific tool ID to approve (approves first pending if not specified)
            approval_token: Optional cryptographically-binding token from TOOL_APPROVAL_REQUIRED event
            remember_choice: Whether to remember this choice
            scope: Scope for remembering choice

        Yields:
            SSE events for continued execution
        """
        if not self._state:
            yield error_event(
                job_id="unknown",
                error="No active agent state to resume",
                error_type="state_error",
            )
            return

        state = self._state

        if state.status != AgentStatus.WAITING_APPROVAL:
            yield error_event(
                job_id=state.job_id,
                error=f"Agent not waiting for approval (status: {state.status})",
                error_type="state_error",
            )
            return

        if not state.pending_approvals:
            yield error_event(
                job_id=state.job_id,
                error="No pending approvals",
                error_type="state_error",
            )
            return

        # Find the pending approval
        if tool_id:
            pending = next(
                (p for p in state.pending_approvals if p.tool_id == tool_id),
                None
            )
        else:
            pending = state.pending_approvals[0]

        if not pending:
            yield error_event(
                job_id=state.job_id,
                error=f"Tool approval not found: {tool_id}",
                error_type="state_error",
            )
            return

        # Optional: verify token binds approval to the exact tool call that was previewed.
        require_token = (os.getenv("TOOL_APPROVAL_REQUIRE_TOKEN", "false") or "false").strip().lower() in ("1", "true", "yes", "y")
        if require_token:
            token = (approval_token or "").strip()
            if not token:
                yield error_event(
                    job_id=state.job_id,
                    error="approval_token is required to resume this tool call",
                    error_type="approval_token_missing",
                )
                return
            try:
                from app.services.ai.shared.approval_tokens import verify_tool_approval_token
                ok, payload, err = verify_tool_approval_token(token)
                if not ok or not isinstance(payload, dict):
                    raise ValueError(err or "invalid")
                if str(payload.get("job_id")) != str(state.job_id) or str(payload.get("tool_id")) != str(pending.tool_id):
                    raise ValueError("mismatch")
                if str(payload.get("tool_name")) != str(pending.tool_name):
                    raise ValueError("mismatch")
            except Exception:
                yield error_event(
                    job_id=state.job_id,
                    error="Invalid approval_token for this tool call",
                    error_type="approval_token_invalid",
                )
                return

        # Remove from pending
        state.pending_approvals.remove(pending)

        if remember_choice:
            # Update permission for this tool
            new_permission = ToolApprovalMode.ALLOW if approval else ToolApprovalMode.DENY
            self.config.tool_permissions[pending.tool_name] = new_permission
            if self._permission_manager:
                try:
                    target_scope: Literal["session", "project", "global"] = scope
                    if target_scope == "session" and not getattr(self._permission_manager, "session_id", None):
                        target_scope = "project" if getattr(self._permission_manager, "project_id", None) else "global"
                    if target_scope == "project" and not getattr(self._permission_manager, "project_id", None):
                        target_scope = "global"

                    await self._permission_manager.add_rule(
                        tool_name=pending.tool_name,
                        mode=new_permission.value,
                        scope=target_scope,
                        description=f"Saved via agent resume ({state.job_id})",
                    )
                except Exception as e:
                    logger.warning(f"Failed to persist permission rule: {e}")

        if approval:
            # Execute the tool
            yield create_sse_event(
                SSEEventType.TOOL_APPROVED,
                {
                    "tool_id": pending.tool_id,
                    "tool_name": pending.tool_name,
                    "remembered": remember_choice,
                    "scope": scope,
                },
                job_id=state.job_id,
            )

            result_event = await self._execute_and_emit_tool(
                pending.tool_id,
                pending.tool_name,
                pending.tool_input,
                state,
            )
            yield result_event

            # Add tool result to messages
            state.messages.append(
                self._build_tool_result_message([state.tools_called[-1]])
            )

        else:
            # Denied - add error result
            yield create_sse_event(
                SSEEventType.TOOL_DENIED,
                {
                    "tool_id": pending.tool_id,
                    "tool_name": pending.tool_name,
                    "remembered": remember_choice,
                    "scope": scope,
                },
                job_id=state.job_id,
            )

            state.tools_called.append({
                "tool_id": pending.tool_id,
                "tool_name": pending.tool_name,
                "tool_input": pending.tool_input,
                "result": None,
                "success": False,
                "error": "Tool execution denied by user",
                "iteration": pending.iteration,
            })

            state.messages.append(
                self._build_tool_result_message([state.tools_called[-1]])
            )

        # Resume execution if no more pending approvals
        if not state.pending_approvals:
            state.status = AgentStatus.RUNNING

            # Continue the agent loop
            async for event in self._continue_run():
                yield event

    async def approve_tool(
        self,
        tool_name: Optional[str],
        approved: bool,
        remember: bool = False,
        *,
        tool_id: Optional[str] = None,
        approval_token: Optional[str] = None,
        scope: Literal["session", "project", "global"] = "session",
    ) -> None:
        """
        Compatibility shim for /chats/{id}/tool-approval endpoint.

        Approves/denies a pending tool call and advances execution by running `resume`.
        This does not stream events by itself; callers should reconnect to SSE stream
        (or handle returned events in a future enhancement).
        """
        # If tool_id not provided, try to find a pending approval matching tool_name.
        if not tool_id and self._state and tool_name:
            for p in (self._state.pending_approvals or []):
                if p.tool_name == tool_name:
                    tool_id = p.tool_id
                    break

        async for _ in self.resume(
            approval=bool(approved),
            tool_id=tool_id,
            approval_token=approval_token,
            remember_choice=bool(remember),
            scope=scope,
        ):
            # Intentionally discard events here. The caller can stream from SSE session.
            pass

    async def _continue_run(self) -> AsyncGenerator[SSEEvent, None]:
        """Continue the agent loop after approval."""
        if not self._state:
            return

        state = self._state
        job_id = state.job_id

        # Get the last system prompt (we don't store it, so use empty for now)
        # In production, this should be stored in state
        full_system_prompt = self.config.system_prompt_prefix

        try:
            while state.iteration < self.config.max_iterations:
                if self._cancel_requested:
                    state.status = AgentStatus.CANCELLED
                    yield done_event(job_id=job_id, metadata={"cancelled": True})
                    return

                state.iteration += 1

                yield agent_iteration_event(
                    job_id=job_id,
                    iteration=state.iteration,
                    status="calling_claude",
                )

                response = await self._call_claude(
                    state.messages,
                    full_system_prompt,
                    container_id=state.container_id,
                )

                tokens_in, tokens_out = self._usage_tokens(response)
                state.total_input_tokens += tokens_in
                state.total_output_tokens += tokens_out
                state.last_response = response

                # Extract container_id for code execution reuse
                _container = getattr(response, "container", None)
                if _container and hasattr(_container, "id"):
                    state.container_id = _container.id

                text_content, tool_uses, server_tool_events = self._extract_response_content(response)

                if text_content:
                    yield token_event(job_id=job_id, token=text_content)

                # Emit server tool events (code execution)
                for ste in server_tool_events:
                    yield create_sse_event(
                        SSEEventType.CODE_EXECUTION if ste["event_type"] == "code_execution" else SSEEventType.CODE_EXECUTION_RESULT,
                        ste,
                        job_id=job_id,
                    )

                state.messages.append({
                    "role": "assistant",
                    "content": response.content,
                })

                if response.stop_reason == "end_turn":
                    state.final_output = text_content
                    state.status = AgentStatus.COMPLETED
                    state.end_time = datetime.now(timezone.utc).isoformat()
                    yield done_event(
                        job_id=job_id,
                        final_text=text_content,
                        metadata={
                            "iterations": state.iteration,
                            "total_tokens": state.total_input_tokens + state.total_output_tokens,
                        }
                    )
                    return

                if tool_uses:
                    tool_results = []

                    for tool_use in tool_uses:
                        async for event in self._process_tool_use(tool_use, state):
                            yield event

                            if state.status == AgentStatus.WAITING_APPROVAL:
                                return

                        if state.tools_called and state.tools_called[-1]["tool_id"] == tool_use["id"]:
                            tool_results.append(state.tools_called[-1])

                    if tool_results:
                        state.messages.append(
                            self._build_tool_result_message(tool_results)
                        )

            # Max iterations
            state.status = AgentStatus.COMPLETED
            state.end_time = datetime.now(timezone.utc).isoformat()
            yield done_event(
                job_id=job_id,
                metadata={"max_iterations_reached": True}
            )

        except Exception as e:
            state.status = AgentStatus.ERROR
            state.error = str(e)
            yield error_event(
                job_id=job_id,
                error=str(e),
                error_type="execution_error",
            )

    def cancel(self) -> None:
        """Request cancellation of the current run."""
        self._cancel_requested = True
        if self._state:
            self._state.status = AgentStatus.CANCELLED

    def get_state(self) -> Optional[AgentState]:
        """Get the current agent state."""
        return self._state

    def get_state_dict(self) -> Optional[Dict[str, Any]]:
        """Get the current agent state as dictionary."""
        if self._state:
            return self._state.to_dict()
        return None


# =============================================================================
# FACTORY FUNCTION
# =============================================================================

def create_claude_agent(
    config: Optional[AgentConfig] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
    tool_executors: Optional[Dict[str, Callable]] = None,
) -> ClaudeAgentExecutor:
    """
    Factory function to create a configured Claude Agent Executor.

    Args:
        config: Agent configuration
        tools: List of tool definitions
        tool_executors: Dictionary mapping tool names to executors

    Returns:
        Configured ClaudeAgentExecutor instance
    """
    executor = ClaudeAgentExecutor(config=config)

    # Register tools if provided
    if tools and tool_executors:
        for tool in tools:
            name = tool["name"]
            if name in tool_executors:
                executor.register_tool(
                    name=name,
                    description=tool.get("description", ""),
                    input_schema=tool.get("input_schema", {}),
                    executor=tool_executors[name],
                )

    return executor
