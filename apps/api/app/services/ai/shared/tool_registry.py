"""
ToolRegistry - Registry unificado de tools.

Centraliza o registro e acesso a tools disponíveis para
Claude Agent SDK e LangGraph.
"""

from typing import Dict, Any, List, Optional, Callable, TypeVar, Generic
from dataclasses import dataclass, field
from enum import Enum
import logging

logger = logging.getLogger(__name__)

T = TypeVar('T')


class ToolCategory(str, Enum):
    """Categoria da tool."""
    SEARCH = "search"
    DOCUMENT = "document"
    CITATION = "citation"
    ANALYSIS = "analysis"
    SYSTEM = "system"


@dataclass
class ToolDefinition:
    """
    Definição de uma tool.

    Attributes:
        name: Nome único da tool
        description: Descrição para o LLM
        category: Categoria da tool
        parameters: Schema dos parâmetros (JSON Schema)
        handler: Função que implementa a tool
        requires_approval: Se requer aprovação do usuário
        is_async: Se o handler é assíncrono
    """
    name: str
    description: str
    category: ToolCategory
    parameters: Dict[str, Any]
    handler: Optional[Callable] = None
    requires_approval: bool = False
    is_async: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_claude_format(self) -> Dict[str, Any]:
        """
        Converte para formato esperado pelo Claude API.

        Returns:
            Dict no formato de tool definition do Claude
        """
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": self.parameters.get("properties", {}),
                "required": self.parameters.get("required", [])
            }
        }

    def to_openai_format(self) -> Dict[str, Any]:
        """
        Converte para formato esperado pelo OpenAI API.

        Returns:
            Dict no formato de function definition do OpenAI
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters
            }
        }


class ToolRegistry:
    """
    Registry centralizado de tools.

    Gerencia todas as tools disponíveis para uso pelos agentes,
    permitindo registro dinâmico e acesso unificado.
    """

    def __init__(self):
        """Inicializa o registry."""
        self._tools: Dict[str, ToolDefinition] = {}
        self._categories: Dict[ToolCategory, List[str]] = {
            category: [] for category in ToolCategory
        }

    def register(self, tool: ToolDefinition) -> None:
        """
        Registra uma tool no registry.

        Args:
            tool: Definição da tool
        """
        if tool.name in self._tools:
            logger.warning(f"Tool {tool.name} já registrada, sobrescrevendo")

        self._tools[tool.name] = tool

        if tool.name not in self._categories[tool.category]:
            self._categories[tool.category].append(tool.name)

        logger.info(f"Tool registrada: {tool.name} ({tool.category.value})")

    def get(self, name: str) -> Optional[ToolDefinition]:
        """
        Obtém tool pelo nome.

        Args:
            name: Nome da tool

        Returns:
            ToolDefinition ou None se não encontrada
        """
        return self._tools.get(name)

    def get_all(self) -> List[ToolDefinition]:
        """
        Retorna todas as tools registradas.

        Returns:
            Lista de ToolDefinition
        """
        return list(self._tools.values())

    def get_by_category(self, category: ToolCategory) -> List[ToolDefinition]:
        """
        Retorna tools de uma categoria.

        Args:
            category: Categoria desejada

        Returns:
            Lista de ToolDefinition da categoria
        """
        tool_names = self._categories.get(category, [])
        return [self._tools[name] for name in tool_names if name in self._tools]

    def get_names(self) -> List[str]:
        """Retorna nomes de todas as tools."""
        return list(self._tools.keys())

    def get_for_claude(self, tool_names: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        Retorna tools no formato Claude API.

        Args:
            tool_names: Lista de nomes para filtrar (None = todas)

        Returns:
            Lista de tool definitions para Claude
        """
        tools = self.get_all() if tool_names is None else [
            self._tools[name] for name in tool_names if name in self._tools
        ]
        return [t.to_claude_format() for t in tools]

    def get_for_openai(self, tool_names: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        Retorna tools no formato OpenAI API.

        Args:
            tool_names: Lista de nomes para filtrar (None = todas)

        Returns:
            Lista de function definitions para OpenAI
        """
        tools = self.get_all() if tool_names is None else [
            self._tools[name] for name in tool_names if name in self._tools
        ]
        return [t.to_openai_format() for t in tools]

    async def execute(
        self,
        tool_name: str,
        parameters: Dict[str, Any]
    ) -> Any:
        """
        Executa uma tool.

        Args:
            tool_name: Nome da tool
            parameters: Parâmetros para a tool

        Returns:
            Resultado da execução

        Raises:
            ValueError: Se tool não encontrada ou sem handler
        """
        tool = self.get(tool_name)
        if not tool:
            raise ValueError(f"Tool não encontrada: {tool_name}")

        if not tool.handler:
            raise ValueError(f"Tool sem handler: {tool_name}")

        if tool.is_async:
            return await tool.handler(**parameters)
        else:
            return tool.handler(**parameters)

    def unregister(self, name: str) -> bool:
        """
        Remove tool do registry.

        Args:
            name: Nome da tool

        Returns:
            True se removida, False se não existia
        """
        if name not in self._tools:
            return False

        tool = self._tools.pop(name)
        self._categories[tool.category].remove(name)
        logger.info(f"Tool removida: {name}")
        return True

    def clear(self) -> None:
        """Remove todas as tools do registry."""
        self._tools.clear()
        for category in self._categories:
            self._categories[category].clear()
        logger.info("Registry limpo")


# Registry global singleton
_global_registry: Optional[ToolRegistry] = None


def get_global_registry() -> ToolRegistry:
    """
    Obtém o registry global.

    Returns:
        Instância singleton do ToolRegistry
    """
    global _global_registry
    if _global_registry is None:
        _global_registry = ToolRegistry()
    return _global_registry
