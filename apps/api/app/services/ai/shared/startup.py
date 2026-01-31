"""
AI Services Startup - Inicialização dos serviços de AI.

Este módulo deve ser chamado no startup da aplicação para:
1. Registrar todas as tools no ToolRegistry global
2. Configurar handlers
3. Inicializar conexões com MCP servers
"""

import asyncio
from typing import Optional
from loguru import logger

from app.services.ai.shared.tool_registry import get_global_registry, ToolRegistry
from app.services.ai.shared.unified_tools import (
    register_all_tools,
    ALL_UNIFIED_TOOLS,
    TOOLS_BY_NAME,
)
from app.services.ai.shared.tool_handlers import (
    ToolHandlers,
    get_tool_handlers,
)


_initialized = False


def init_ai_services(
    register_tools: bool = True,
    init_mcp: bool = True,
) -> ToolRegistry:
    """
    Inicializa serviços de AI.

    Deve ser chamado no startup da aplicação (main.py ou lifespan).

    Args:
        register_tools: Se deve registrar tools no registry global
        init_mcp: Se deve inicializar conexões MCP

    Returns:
        ToolRegistry global configurado
    """
    global _initialized

    if _initialized:
        logger.info("AI Services já inicializados")
        return get_global_registry()

    logger.info("Inicializando AI Services...")

    # 1. Registrar todas as tools
    if register_tools:
        registry = register_all_tools()
        logger.info(f"Registradas {len(ALL_UNIFIED_TOOLS)} tools unificadas")
    else:
        registry = get_global_registry()

    # 2. Configurar handlers padrão
    handlers = get_tool_handlers()
    logger.info("Tool handlers configurados")

    # 3. Inicializar MCP (se disponível)
    if init_mcp:
        try:
            from app.services.mcp_hub import mcp_hub
            # MCP já inicializa lazy, apenas log
            logger.info("MCP Hub disponível para conexões")
        except ImportError:
            logger.warning("MCP Hub não disponível")

    _initialized = True
    logger.info("AI Services inicializados com sucesso")

    return registry


async def init_ai_services_async(
    register_tools: bool = True,
    init_mcp: bool = True,
) -> ToolRegistry:
    """
    Versão assíncrona da inicialização.

    Use quando precisar inicializar conexões async (ex: MCP servers).
    """
    global _initialized

    if _initialized:
        return get_global_registry()

    # Inicialização síncrona básica
    registry = init_ai_services(register_tools=register_tools, init_mcp=False)

    # Inicializações assíncronas
    if init_mcp:
        try:
            from app.services.mcp_hub import mcp_hub
            await mcp_hub.initialize()
            logger.info("MCP Hub inicializado")
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"Erro inicializando MCP Hub: {e}")

    return registry


def shutdown_ai_services():
    """
    Cleanup dos serviços de AI.

    Deve ser chamado no shutdown da aplicação.
    """
    global _initialized

    logger.info("Finalizando AI Services...")

    # Cleanup MCP connections
    try:
        from app.services.mcp_hub import mcp_hub
        # mcp_hub.close() se existir
        pass
    except ImportError:
        pass

    # Limpar registry se necessário
    # get_global_registry().clear()

    _initialized = False
    logger.info("AI Services finalizados")


def get_tools_summary() -> dict:
    """
    Retorna resumo das tools disponíveis.

    Útil para debugging e APIs de info.
    """
    from app.services.ai.shared.unified_tools import (
        list_tools_by_category,
        list_tools_by_risk,
        ToolRiskLevel,
    )
    from app.services.ai.shared.tool_registry import ToolCategory

    return {
        "total_tools": len(ALL_UNIFIED_TOOLS),
        "by_category": {
            cat.value: list_tools_by_category(cat)
            for cat in ToolCategory
        },
        "by_risk": {
            risk.value: list_tools_by_risk(risk)
            for risk in ToolRiskLevel
        },
        "tool_names": list(TOOLS_BY_NAME.keys()),
    }
