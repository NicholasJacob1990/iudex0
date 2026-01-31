"""
Gemini MCP Adapter - Connects Gemini/ADK to MCP tools.

Google ADK supports MCP via MCPToolset. This adapter:
1. Provides tools in Gemini function declaration format
2. Routes calls through MCP server
3. Integrates with ADK's MCPToolset when available
"""

import json
from typing import Any, Dict, List, Optional
from loguru import logger

from .base_adapter import BaseMCPAdapter
from ..mcp_server import mcp_server
from ..tool_registry import tool_registry


class GeminiMCPAdapter(BaseMCPAdapter):
    """
    Adapter for Gemini/Google ADK.

    Supports both direct function calling and ADK MCPToolset integration.
    """

    def __init__(self, context: Optional[Dict[str, Any]] = None):
        self.context = context or {}
        self._adk_toolset = None

    async def get_tools(self) -> List[Dict[str, Any]]:
        """
        Get tools in Gemini function declaration format.

        Gemini uses FunctionDeclaration with:
        - name
        - description
        - parameters (JSON Schema)
        """
        tool_registry.initialize()
        tools = tool_registry.list_tools()

        return [
            {
                "name": t.name,
                "description": t.description,
                "parameters": {
                    "type": "object",
                    **t.input_schema,
                },
            }
            for t in tools
        ]

    def get_genai_tools(self):
        """
        Get tools as google.genai.types.Tool objects.

        For direct use with Gemini SDK.
        """
        try:
            from google.genai import types

            tool_registry.initialize()
            tools = tool_registry.list_tools()

            function_decls = [
                types.FunctionDeclaration(
                    name=t.name,
                    description=t.description,
                    parameters=t.input_schema,
                )
                for t in tools
            ]

            return [types.Tool(function_declarations=function_decls)]

        except ImportError:
            logger.warning("google-genai not installed")
            return []

    def get_adk_toolset(self):
        """
        Get ADK MCPToolset for integration with ADK agents.

        This creates an MCPToolset that wraps our MCP server.
        """
        if self._adk_toolset is not None:
            return self._adk_toolset

        try:
            from google.adk.tools.mcp_tool import MCPToolset

            # Create toolset pointing to our MCP server
            # Note: This requires the MCP server to be running on HTTP
            self._adk_toolset = MCPToolset(
                connection_params={
                    "url": "http://localhost:8000/api/mcp/rpc",
                    "headers": {},
                }
            )
            return self._adk_toolset

        except ImportError:
            logger.warning("google-adk MCPToolset not available")
            return None

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

    def format_tool_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format result for Gemini FunctionResponse.

        Gemini expects a dict response.
        """
        if result.get("isError"):
            content = result.get("content", [])
            text = content[0].get("text", "Error") if content else "Error"
            return {"error": text}

        content = result.get("content", [])
        if content:
            texts = [c.get("text", "") for c in content if c.get("type") == "text"]
            text = "\n".join(texts)
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return {"result": text}

        return result

    async def handle_function_call(
        self,
        function_call: Any,
        context: Optional[Dict[str, Any]] = None,
    ):
        """
        Handle a Gemini function call.

        Args:
            function_call: The FunctionCall from Gemini
            context: Execution context

        Returns:
            FunctionResponse for Gemini
        """
        try:
            from google.genai import types

            name = getattr(function_call, "name", "")
            args = getattr(function_call, "args", {})
            call_id = getattr(function_call, "id", None)

            result = await self.execute_tool(name, args or {}, context)
            formatted = self.format_tool_result(result)

            return types.Part(
                function_response=types.FunctionResponse(
                    id=call_id,
                    name=name,
                    response=formatted,
                )
            )

        except ImportError:
            logger.error("google-genai not installed")
            return None

    async def handle_function_calls(
        self,
        function_calls: List[Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> List[Any]:
        """Handle multiple Gemini function calls."""
        results = []
        for fc in function_calls:
            result = await self.handle_function_call(fc, context)
            if result:
                results.append(result)
        return results
