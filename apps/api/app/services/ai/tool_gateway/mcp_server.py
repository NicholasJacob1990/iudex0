"""
MCP Server - Model Context Protocol server for legal tools.

Implements MCP JSON-RPC 2.0 over HTTP/SSE:
- tools/list: List all available tools
- tools/call: Execute a tool

This server is the single source of truth for all legal tools,
consumed by Claude (native MCP), Gemini (via ADK), and OpenAI (via adapter).
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any, Dict, List, Optional, Callable, AsyncGenerator
from datetime import datetime
from dataclasses import dataclass, asdict

from loguru import logger
from fastapi import Request
from sse_starlette.sse import EventSourceResponse

from .tool_registry import tool_registry, ToolDefinition
from .policy_engine import policy_engine, PolicyContext, PolicyDecision


@dataclass
class MCPError:
    code: int
    message: str
    data: Optional[Dict[str, Any]] = None


@dataclass
class MCPResponse:
    jsonrpc: str = "2.0"
    id: Optional[int] = None
    result: Optional[Any] = None
    error: Optional[MCPError] = None


class MCPToolServer:
    """
    MCP Server that exposes legal tools via JSON-RPC.

    Supports both synchronous HTTP and streaming SSE responses.
    """

    def __init__(self):
        self.server_info = {
            "name": "iudex-legal-tools",
            "version": "1.0.0",
            "capabilities": {
                "tools": True,
                "resources": False,
                "prompts": False,
            }
        }
        self._pending_approvals: Dict[str, asyncio.Event] = {}
        self._approval_results: Dict[str, bool] = {}

    async def handle_request(
        self,
        request: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> MCPResponse:
        """
        Handle an MCP JSON-RPC request.

        Args:
            request: JSON-RPC request dict
            context: Optional context (user_id, tenant_id, etc.)

        Returns:
            MCPResponse
        """
        method = request.get("method", "")
        params = request.get("params", {})
        req_id = request.get("id")

        try:
            if method == "initialize":
                result = await self._handle_initialize(params)
            elif method == "tools/list":
                result = await self._handle_tools_list(params, context)
            elif method == "tools/call":
                result = await self._handle_tools_call(params, context)
            elif method == "ping":
                result = {"pong": True}
            else:
                return MCPResponse(
                    id=req_id,
                    error=MCPError(code=-32601, message=f"Method not found: {method}"),
                )

            return MCPResponse(id=req_id, result=result)

        except Exception as e:
            logger.error(f"[MCPToolServer] Error handling {method}: {e}")
            return MCPResponse(
                id=req_id,
                error=MCPError(code=-32603, message=str(e)),
            )

    async def _handle_initialize(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle initialize request."""
        tool_registry.initialize()
        return self.server_info

    async def _handle_tools_list(
        self,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Handle tools/list request."""
        tool_registry.initialize()

        tools = tool_registry.list_tools()

        # Format for MCP
        formatted = [
            {
                "name": t.name,
                "description": t.description,
                "inputSchema": {
                    "type": "object",
                    **t.input_schema,
                },
            }
            for t in tools
        ]

        return {"tools": formatted}

    async def _handle_tools_call(
        self,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Handle tools/call request."""
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        tool_registry.initialize()
        tool = tool_registry.get(tool_name)

        if not tool:
            return {
                "isError": True,
                "content": [{"type": "text", "text": f"Tool not found: {tool_name}"}],
            }

        # Build policy context
        ctx = context or {}
        policy_ctx = PolicyContext(
            user_id=ctx.get("user_id", "anonymous"),
            tenant_id=ctx.get("tenant_id", "default"),
            tool_name=tool_name,
            arguments=arguments,
            session_id=ctx.get("session_id"),
            case_id=ctx.get("case_id"),
        )

        # Check policy
        policy_result = await policy_engine.check_policy(policy_ctx)

        if policy_result.decision == PolicyDecision.DENY:
            return {
                "isError": True,
                "content": [{"type": "text", "text": f"Denied: {policy_result.reason}"}],
            }

        if policy_result.decision == PolicyDecision.RATE_LIMITED:
            return {
                "isError": True,
                "content": [{"type": "text", "text": "Rate limit exceeded. Try again later."}],
            }

        if policy_result.decision == PolicyDecision.ASK:
            # Wait for approval if needed
            approved = await self._wait_for_approval(policy_ctx, policy_result)
            if not approved:
                return {
                    "isError": True,
                    "content": [{"type": "text", "text": "Tool execution not approved by user."}],
                }

        # Execute tool
        try:
            # Inject context into arguments
            arguments["case_id"] = policy_ctx.case_id
            arguments["tenant_id"] = policy_ctx.tenant_id
            arguments["user_id"] = policy_ctx.user_id

            # Call the tool function
            if asyncio.iscoroutinefunction(tool.function):
                result = await tool.function(**arguments)
            else:
                result = tool.function(**arguments)

            # Record call for audit
            policy_engine.record_call(policy_ctx)

            # Format result
            if isinstance(result, dict):
                text = json.dumps(result, ensure_ascii=False, indent=2)
            else:
                text = str(result)

            return {
                "content": [{"type": "text", "text": text}],
            }

        except Exception as e:
            logger.error(f"[MCPToolServer] Tool execution failed: {e}")
            return {
                "isError": True,
                "content": [{"type": "text", "text": f"Error: {str(e)}"}],
            }

    async def _wait_for_approval(
        self,
        context: PolicyContext,
        policy_result,
    ) -> bool:
        """Wait for user approval (timeout 60s)."""
        approval_id = str(uuid.uuid4())
        event = asyncio.Event()
        self._pending_approvals[approval_id] = event

        # Emit approval request event (to be picked up by SSE)
        logger.info(f"[MCPToolServer] Waiting for approval: {approval_id} for {context.tool_name}")

        try:
            await asyncio.wait_for(event.wait(), timeout=60.0)
            return self._approval_results.get(approval_id, False)
        except asyncio.TimeoutError:
            return False
        finally:
            self._pending_approvals.pop(approval_id, None)
            self._approval_results.pop(approval_id, None)

    def approve_tool(self, approval_id: str, approved: bool = True) -> bool:
        """Approve or deny a pending tool execution."""
        if approval_id not in self._pending_approvals:
            return False

        self._approval_results[approval_id] = approved
        self._pending_approvals[approval_id].set()
        return True

    async def stream_events(
        self,
        request: Request,
        context: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Stream MCP events over SSE.

        Used for real-time notifications like approval requests.
        """
        while True:
            if await request.is_disconnected():
                break

            # Check for pending approvals
            for approval_id, event in list(self._pending_approvals.items()):
                if not event.is_set():
                    yield {
                        "event": "approval_request",
                        "data": json.dumps({
                            "approval_id": approval_id,
                            "tool_name": "pending",  # Would need more context
                            "message": "Tool execution requires approval",
                        }),
                    }

            await asyncio.sleep(1)


# Global MCP server instance
mcp_server = MCPToolServer()


# FastAPI route helpers
async def handle_mcp_http(request_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """Handle MCP request via HTTP POST."""
    response = await mcp_server.handle_request(request_data, context)
    return asdict(response)


async def handle_mcp_sse(request: Request, context: Dict[str, Any]) -> EventSourceResponse:
    """Handle MCP SSE stream."""
    return EventSourceResponse(mcp_server.stream_events(request, context))
