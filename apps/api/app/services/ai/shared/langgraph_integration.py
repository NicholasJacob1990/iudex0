"""
LangGraph Integration - Integra tools unificadas com workflows LangGraph.

Este módulo fornece:
1. Tools no formato OpenAI para LangGraph
2. Executor de tools para nós do grafo
3. Wrapper para usar tools no workflow existente
"""

import asyncio
from typing import Any, Callable, Dict, List, Optional, Tuple

from loguru import logger

from app.services.ai.shared.unified_tools import (
    get_tools_for_openai,
    get_default_permissions,
    TOOLS_BY_NAME,
    ToolRiskLevel,
)
from app.services.ai.shared.tool_handlers import (
    ToolExecutionContext,
    ToolHandlers,
    get_tool_handlers,
    execute_tool,
)
from app.services.ai.shared.sse_protocol import ToolApprovalMode


class LangGraphToolBridge:
    """
    Bridge entre tools unificadas e LangGraph.

    Permite que workflows LangGraph usem as mesmas tools
    que o Claude Agent, com mesma API e permissões.
    """

    def __init__(
        self,
        context: Optional[ToolExecutionContext] = None,
        include_mcp: bool = True,
        allowed_tools: Optional[List[str]] = None,
    ):
        """
        Inicializa o bridge.

        Args:
            context: Contexto de execução (user_id, case_id, etc.)
            include_mcp: Incluir tools MCP
            allowed_tools: Lista de tools permitidas (None = todas)
        """
        self.context = context
        self.include_mcp = include_mcp
        self.allowed_tools = allowed_tools
        self._handlers = get_tool_handlers(context)

    def get_openai_tools(self) -> List[Dict[str, Any]]:
        """
        Retorna tools no formato OpenAI para LangGraph.

        Returns:
            Lista de function definitions
        """
        return get_tools_for_openai(
            tool_names=self.allowed_tools,
            include_mcp=self.include_mcp,
        )

    def get_tool_names(self) -> List[str]:
        """Retorna nomes das tools disponíveis."""
        tools = self.get_openai_tools()
        return [t["function"]["name"] for t in tools]

    async def execute_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Executa uma tool.

        Args:
            tool_name: Nome da tool
            arguments: Argumentos da tool

        Returns:
            Resultado da execução
        """
        # Verificar se tool é permitida
        if self.allowed_tools and tool_name not in self.allowed_tools:
            return {
                "success": False,
                "error": f"Tool '{tool_name}' não permitida",
            }

        return await self._handlers.execute(tool_name, arguments, self.context)

    async def execute_tool_calls(
        self,
        tool_calls: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Executa múltiplas tool calls (formato OpenAI).

        Args:
            tool_calls: Lista de tool_call objects do OpenAI

        Returns:
            Lista de resultados
        """
        results = []

        for call in tool_calls:
            tool_name = call.get("function", {}).get("name", "")
            arguments = call.get("function", {}).get("arguments", {})

            # Parse arguments se for string JSON
            if isinstance(arguments, str):
                import json
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    arguments = {}

            result = await self.execute_tool(tool_name, arguments)
            results.append({
                "tool_call_id": call.get("id", ""),
                "role": "tool",
                "content": str(result),
            })

        return results

    def get_permissions(self) -> Dict[str, ToolApprovalMode]:
        """Retorna mapa de permissões por tool."""
        return get_default_permissions()

    def check_permission(self, tool_name: str) -> ToolApprovalMode:
        """
        Verifica permissão de uma tool.

        Args:
            tool_name: Nome da tool

        Returns:
            ToolApprovalMode (ALLOW, ASK, DENY)
        """
        permissions = self.get_permissions()
        return permissions.get(tool_name, ToolApprovalMode.ASK)


def create_tool_node(
    context: Optional[ToolExecutionContext] = None,
    include_mcp: bool = True,
) -> Callable:
    """
    Cria um node LangGraph para executar tools.

    Uso no workflow:
        from app.services.ai.shared.langgraph_integration import create_tool_node

        tool_node = create_tool_node(context)

        builder.add_node("tools", tool_node)
        builder.add_edge("agent", "tools")
        builder.add_edge("tools", "agent")

    Args:
        context: Contexto de execução
        include_mcp: Incluir MCP tools

    Returns:
        Função node para LangGraph
    """
    bridge = LangGraphToolBridge(context=context, include_mcp=include_mcp)

    async def tool_node(state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Node que executa tools pendentes no estado.

        Espera estado com:
        - messages: Lista de mensagens
        - tool_calls: Lista de tool calls pendentes (opcional)

        Retorna estado atualizado com resultados.
        """
        messages = state.get("messages", [])
        tool_calls = state.get("tool_calls", [])

        # Se não há tool_calls explícitas, verificar última mensagem
        if not tool_calls and messages:
            last_msg = messages[-1]
            if hasattr(last_msg, "tool_calls"):
                tool_calls = last_msg.tool_calls
            elif isinstance(last_msg, dict) and "tool_calls" in last_msg:
                tool_calls = last_msg["tool_calls"]

        if not tool_calls:
            return state

        # Executar todas as tools
        results = await bridge.execute_tool_calls(tool_calls)

        # Adicionar resultados às mensagens
        new_messages = messages.copy()
        new_messages.extend(results)

        return {
            **state,
            "messages": new_messages,
            "tool_calls": [],  # Limpar tool calls processadas
        }

    return tool_node


def get_tools_for_langgraph_agent(
    context: Optional[ToolExecutionContext] = None,
    include_mcp: bool = True,
    tool_names: Optional[List[str]] = None,
) -> Tuple[List[Dict[str, Any]], Callable]:
    """
    Retorna tools e executor para usar com create_react_agent.

    Uso:
        from app.services.ai.shared.langgraph_integration import get_tools_for_langgraph_agent

        tools, tool_executor = get_tools_for_langgraph_agent(context)

        agent = create_react_agent(model, tools)

    Args:
        context: Contexto de execução
        include_mcp: Incluir MCP tools
        tool_names: Filtrar por nomes

    Returns:
        Tupla (tools no formato OpenAI, função executor)
    """
    bridge = LangGraphToolBridge(
        context=context,
        include_mcp=include_mcp,
        allowed_tools=tool_names,
    )

    tools = bridge.get_openai_tools()

    async def tool_executor(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        return await bridge.execute_tool(tool_name, arguments)

    return tools, tool_executor


# =============================================================================
# CONVENIENCE FUNCTIONS FOR EXISTING WORKFLOW
# =============================================================================

async def execute_tool_in_workflow(
    tool_name: str,
    arguments: Dict[str, Any],
    user_id: str,
    case_id: Optional[str] = None,
    chat_id: Optional[str] = None,
    db_session: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Função de conveniência para executar tool em workflow existente.

    Pode ser usada diretamente em nodes do langgraph_legal_workflow.py
    sem precisar criar o contexto manualmente.

    Args:
        tool_name: Nome da tool
        arguments: Argumentos
        user_id: ID do usuário
        case_id: ID do caso (opcional)
        chat_id: ID do chat (opcional)
        db_session: Sessão do banco (opcional)

    Returns:
        Resultado da execução
    """
    context = ToolExecutionContext(
        user_id=user_id,
        case_id=case_id,
        chat_id=chat_id,
        db_session=db_session,
    )

    return await execute_tool(tool_name, arguments, context)


def list_available_tools_for_model(
    model_id: str,
    include_mcp: bool = True,
) -> List[str]:
    """
    Lista tools disponíveis para um modelo específico.

    Alguns modelos podem não suportar todas as tools.

    Args:
        model_id: ID do modelo (ex: 'gpt-4', 'claude-3-opus')
        include_mcp: Incluir MCP tools

    Returns:
        Lista de nomes de tools disponíveis
    """
    # Por enquanto, todos os modelos têm acesso às mesmas tools
    # No futuro, pode-se filtrar por capabilities do modelo
    all_tools = get_tools_for_openai(include_mcp=include_mcp)
    return [t["function"]["name"] for t in all_tools]
