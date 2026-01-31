"""
Base adapter interface for MCP tool consumption.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

class BaseMCPAdapter(ABC):
    """Base class for MCP adapters."""

    @abstractmethod
    async def get_tools(self) -> List[Dict[str, Any]]:
        """Get tools in provider-specific format."""
        pass

    @abstractmethod
    async def execute_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Execute a tool and return result."""
        pass

    @abstractmethod
    def format_tool_result(self, result: Dict[str, Any]) -> Any:
        """Format result for provider."""
        pass
