"""
OpenAI MCP Adapter - Converts MCP tools to OpenAI function calling.

OpenAI uses function calling format, so we:
1. Convert MCP tool schemas to OpenAI function schemas
2. Route function calls to MCP server
3. Format results as function outputs
"""

import json
from typing import Any, Dict, List, Optional
from loguru import logger

from .base_adapter import BaseMCPAdapter
from ..mcp_server import mcp_server
from ..tool_registry import tool_registry


class OpenAIMCPAdapter(BaseMCPAdapter):
    """
    Adapter for OpenAI function calling.

    Converts MCP tools to OpenAI functions and routes execution
    through the MCP server.
    """

    def __init__(self, context: Optional[Dict[str, Any]] = None):
        self.context = context or {}

    async def get_tools(self) -> List[Dict[str, Any]]:
        """
        Get tools in OpenAI function calling format.

        OpenAI uses:
        {
            "type": "function",
            "function": {
                "name": "...",
                "description": "...",
                "parameters": {...}
            }
        }
        """
        tool_registry.initialize()
        tools = tool_registry.list_tools()

        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": {
                        "type": "object",
                        **t.input_schema,
                    },
                },
            }
            for t in tools
        ]

    async def execute_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Execute tool via MCP server."""
        ctx = {**self.context, **(context or {})}

        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
        }

        response = await mcp_server.handle_request(request, ctx)

        if response.error:
            return {
                "success": False,
                "error": response.error.message,
            }

        return response.result or {}

    def format_tool_result(self, result: Dict[str, Any]) -> str:
        """
        Format result for OpenAI function output.

        OpenAI expects a string.
        """
        if result.get("isError"):
            content = result.get("content", [])
            text = content[0].get("text", "Error") if content else "Error"
            return json.dumps({"error": text}, ensure_ascii=False)

        content = result.get("content", [])
        if content:
            # Extract text from content blocks
            texts = [c.get("text", "") for c in content if c.get("type") == "text"]
            return "\n".join(texts)

        return json.dumps(result, ensure_ascii=False)

    async def handle_function_call(
        self,
        function_call: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Handle an OpenAI function call.

        Args:
            function_call: The function object from OpenAI
            context: Execution context

        Returns:
            Dict with role="tool" for OpenAI messages
        """
        name = function_call.get("name", "")
        arguments_str = function_call.get("arguments", "{}")

        try:
            arguments = json.loads(arguments_str)
        except json.JSONDecodeError:
            arguments = {}

        result = await self.execute_tool(name, arguments, context)
        formatted = self.format_tool_result(result)

        return {
            "role": "tool",
            "content": formatted,
        }

    async def handle_tool_calls(
        self,
        tool_calls: List[Dict[str, Any]],
        context: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Handle multiple OpenAI tool_calls.

        Args:
            tool_calls: List of tool call objects from OpenAI
            context: Execution context

        Returns:
            List of tool message dicts for OpenAI
        """
        results = []

        for tc in tool_calls:
            tc_id = tc.get("id", "")
            function = tc.get("function", {})
            name = function.get("name", "")
            arguments_str = function.get("arguments", "{}")

            try:
                arguments = json.loads(arguments_str)
            except json.JSONDecodeError:
                arguments = {}

            result = await self.execute_tool(name, arguments, context)
            formatted = self.format_tool_result(result)

            results.append({
                "role": "tool",
                "tool_call_id": tc_id,
                "content": formatted,
            })

        return results
