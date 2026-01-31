"""
Claude MCP Adapter - Native MCP support for Claude.

Claude supports MCP natively, so this adapter is minimal.
It primarily handles context injection and result formatting.
"""

from typing import Any, Dict, List, Optional
from loguru import logger

from .base_adapter import BaseMCPAdapter
from ..mcp_server import mcp_server
from ..tool_registry import tool_registry


class ClaudeMCPAdapter(BaseMCPAdapter):
    """
    Adapter for Claude's native MCP support.

    Claude can consume MCP tools directly, so this adapter
    just translates between our server and Claude's format.
    """

    def __init__(self, context: Optional[Dict[str, Any]] = None):
        self.context = context or {}

    async def get_tools(self) -> List[Dict[str, Any]]:
        """
        Get tools in Claude/Anthropic format.

        Claude uses the same format as MCP, just with slight differences
        in the schema structure.
        """
        tool_registry.initialize()
        tools = tool_registry.list_tools()

        return [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": {
                    "type": "object",
                    **t.input_schema,
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

    def format_tool_result(self, result: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Format result for Claude tool_result.

        Claude expects content blocks.
        """
        if result.get("isError"):
            content = result.get("content", [{"type": "text", "text": "Error"}])
        else:
            content = result.get("content", [])

        return content

    async def handle_tool_use(
        self,
        tool_use_block: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Handle a Claude tool_use block.

        Args:
            tool_use_block: The tool_use content block from Claude
            context: Execution context

        Returns:
            tool_result block for Claude
        """
        tool_name = tool_use_block.get("name", "")
        tool_input = tool_use_block.get("input", {})
        tool_use_id = tool_use_block.get("id", "")

        result = await self.execute_tool(tool_name, tool_input, context)
        formatted = self.format_tool_result(result)

        return {
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": formatted,
        }
