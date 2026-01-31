"""
AI Agent Executors - Executores unificados para múltiplos providers.

Este módulo fornece executores para:
- Anthropic (Claude Agent SDK)
- OpenAI (Agents SDK / Chat Completions)
- Google (Gemini / Vertex AI)

Todos os executores:
- Usam as mesmas tools unificadas
- Compartilham sistema de permissões
- Suportam checkpoints/rewind
- Emitem eventos SSE padronizados
"""

from app.services.ai.executors.base import (
    AgentProvider,
    ExecutorStatus,
    ExecutorConfig,
    ExecutorState,
    BaseAgentExecutor,
)

from app.services.ai.executors.openai_agent import (
    OpenAIAgentExecutor,
    OpenAIAgentConfig,
    OPENAI_AVAILABLE,
)

from app.services.ai.executors.google_agent import (
    GoogleAgentExecutor,
    GoogleAgentConfig,
    GENAI_AVAILABLE,
    VERTEX_AVAILABLE,
)

# Import Claude executor from existing location
try:
    from app.services.ai.claude_agent.executor import (
        ClaudeAgentExecutor,
        AgentConfig as ClaudeAgentConfig,
    )
    CLAUDE_AVAILABLE = True
except ImportError:
    CLAUDE_AVAILABLE = False
    ClaudeAgentExecutor = None
    ClaudeAgentConfig = None


def get_executor_for_provider(
    provider: str,
    config: dict = None,
    **kwargs,
) -> BaseAgentExecutor:
    """
    Factory para criar executor baseado no provider.

    Args:
        provider: "anthropic", "openai", ou "google"
        config: Configuração específica do provider
        **kwargs: Argumentos adicionais

    Returns:
        Executor apropriado para o provider

    Raises:
        ValueError: Se provider não suportado
    """
    provider = provider.lower()

    if provider in ("anthropic", "claude"):
        if not CLAUDE_AVAILABLE:
            raise ValueError("Claude Agent not available. Check anthropic SDK.")
        cfg = ClaudeAgentConfig(**(config or {}))
        return ClaudeAgentExecutor(config=cfg, **kwargs)

    elif provider == "openai":
        if not OPENAI_AVAILABLE:
            raise ValueError("OpenAI Agent not available. Check openai SDK.")
        cfg = OpenAIAgentConfig(**(config or {}))
        return OpenAIAgentExecutor(config=cfg, **kwargs)

    elif provider in ("google", "gemini", "vertex"):
        if not GENAI_AVAILABLE and not VERTEX_AVAILABLE:
            raise ValueError("Google Agent not available. Check google-generativeai SDK.")
        cfg = GoogleAgentConfig(**(config or {}))
        return GoogleAgentExecutor(config=cfg, **kwargs)

    else:
        raise ValueError(f"Unknown provider: {provider}")


def get_available_providers() -> list:
    """
    Retorna lista de providers disponíveis.

    Returns:
        Lista de nomes de providers
    """
    providers = []

    if CLAUDE_AVAILABLE:
        providers.append("anthropic")

    if OPENAI_AVAILABLE:
        providers.append("openai")

    if GENAI_AVAILABLE or VERTEX_AVAILABLE:
        providers.append("google")

    return providers


__all__ = [
    # Base
    "AgentProvider",
    "ExecutorStatus",
    "ExecutorConfig",
    "ExecutorState",
    "BaseAgentExecutor",
    # OpenAI
    "OpenAIAgentExecutor",
    "OpenAIAgentConfig",
    "OPENAI_AVAILABLE",
    # Google
    "GoogleAgentExecutor",
    "GoogleAgentConfig",
    "GENAI_AVAILABLE",
    "VERTEX_AVAILABLE",
    # Claude
    "ClaudeAgentExecutor",
    "ClaudeAgentConfig",
    "CLAUDE_AVAILABLE",
    # Factory
    "get_executor_for_provider",
    "get_available_providers",
]
