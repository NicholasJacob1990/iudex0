"""
Base Agent Executor - Interface comum para todos os executores de agentes.

Todos os executores (Claude, OpenAI, Google) implementam esta interface,
garantindo comportamento consistente e integração com:
- Tools unificadas
- Sistema de permissões
- Checkpoints/rewind
- Compactação de contexto
- Eventos SSE
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional, TypeVar

from loguru import logger


class AgentProvider(str, Enum):
    """Provider do agente."""
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    GOOGLE = "google"


class ExecutorStatus(str, Enum):
    """Status do executor."""
    IDLE = "idle"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    PAUSED = "paused"
    COMPLETED = "completed"
    ERROR = "error"
    CANCELLED = "cancelled"


@dataclass
class ExecutorConfig:
    """
    Configuração base para executores.

    Subclasses podem estender com configs específicas do provider.
    """
    # Modelo
    model: str = ""
    max_tokens: int = 4096
    temperature: float = 0.7

    # Limites
    max_iterations: int = 50
    max_tool_calls_per_iteration: int = 10
    timeout_seconds: int = 300

    # Context
    context_window: int = 200_000
    compaction_threshold: float = 0.7

    # Permissões
    default_permission_mode: str = "ask"  # ask, allow, deny
    tool_permissions: Dict[str, str] = field(default_factory=dict)

    # Features
    enable_checkpoints: bool = True
    enable_compaction: bool = True
    enable_streaming: bool = True

    # Provider-specific (override em subclasses)
    provider_config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutorState:
    """
    Estado do executor durante execução.

    Compartilhado entre todos os providers.
    """
    job_id: str
    status: ExecutorStatus = ExecutorStatus.IDLE
    iteration: int = 0

    # Tokens
    total_input_tokens: int = 0
    total_output_tokens: int = 0

    # Tools
    tools_called: List[Dict[str, Any]] = field(default_factory=list)
    pending_approvals: List[Dict[str, Any]] = field(default_factory=list)

    # Checkpoints
    checkpoints: List[str] = field(default_factory=list)

    # Output
    messages: List[Dict[str, Any]] = field(default_factory=list)
    final_output: str = ""
    error: Optional[str] = None

    # Timing
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    def get_context_usage(self, context_window: int) -> float:
        """Calcula uso do contexto como percentual."""
        if context_window <= 0:
            return 0.0
        total = self.total_input_tokens + self.total_output_tokens
        return total / context_window

    def to_dict(self) -> Dict[str, Any]:
        """Serializa estado."""
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
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
        }


class BaseAgentExecutor(ABC):
    """
    Interface base para executores de agentes.

    Todos os executores (Claude, OpenAI, Google) devem implementar
    esta interface para garantir comportamento consistente.
    """

    def __init__(
        self,
        config: Optional[ExecutorConfig] = None,
        tool_executor: Optional[Callable] = None,
    ):
        """
        Inicializa o executor.

        Args:
            config: Configuração do executor
            tool_executor: Função customizada para executar tools
        """
        self.config = config or ExecutorConfig()
        self.tool_executor = tool_executor
        self._state: Optional[ExecutorState] = None
        self._cancel_requested = False
        self._tools: List[Dict[str, Any]] = []
        self._tool_registry: Dict[str, Callable] = {}

    @property
    @abstractmethod
    def provider(self) -> AgentProvider:
        """Retorna o provider deste executor."""
        pass

    @property
    def state(self) -> Optional[ExecutorState]:
        """Retorna o estado atual."""
        return self._state

    @abstractmethod
    async def run(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        context: Optional[str] = None,
        job_id: Optional[str] = None,
        **kwargs,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Executa o agente com o prompt dado.

        Args:
            prompt: Prompt do usuário
            system_prompt: System prompt opcional
            context: Contexto adicional (RAG, documentos, etc.)
            job_id: ID do job para tracking
            **kwargs: Argumentos adicionais específicos do provider

        Yields:
            Eventos SSE durante a execução
        """
        pass

    @abstractmethod
    async def resume(
        self,
        job_id: str,
        tool_results: Optional[List[Dict[str, Any]]] = None,
        **kwargs,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Resume execução após pausa (ex: aprovação de tool).

        Args:
            job_id: ID do job a resumir
            tool_results: Resultados de tools aprovadas
            **kwargs: Argumentos adicionais

        Yields:
            Eventos SSE durante a execução
        """
        pass

    def cancel(self) -> None:
        """Solicita cancelamento da execução atual."""
        self._cancel_requested = True
        if self._state:
            self._state.status = ExecutorStatus.CANCELLED

    def register_tool(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Any],
        handler: Callable,
        permission: Optional[str] = None,
    ) -> None:
        """
        Registra uma tool para uso pelo agente.

        Args:
            name: Nome da tool
            description: Descrição para o LLM
            parameters: Schema dos parâmetros
            handler: Função que executa a tool
            permission: Modo de permissão (ask/allow/deny)
        """
        # Subclasses implementam formato específico do provider
        self._tool_registry[name] = handler
        if permission:
            self.config.tool_permissions[name] = permission

    def load_unified_tools(
        self,
        execution_context: Optional[Any] = None,
        tool_names: Optional[List[str]] = None,
        include_mcp: bool = True,
    ) -> None:
        """
        Carrega tools unificadas do registry compartilhado.

        Args:
            execution_context: Contexto para execução (user_id, case_id, etc.)
            tool_names: Lista de tools específicas (None = todas)
            include_mcp: Incluir tools MCP
        """
        try:
            from app.services.ai.shared import (
                get_default_permissions,
                get_tool_handlers,
                TOOLS_BY_NAME,
            )

            # Obter tools no formato do provider
            tools = self._get_tools_for_provider(tool_names, include_mcp)

            # Obter handlers
            handlers = get_tool_handlers(execution_context)

            # Obter permissões
            permissions = get_default_permissions()

            # Registrar cada tool
            for tool_def in tools:
                name = self._extract_tool_name(tool_def)
                self._tools.append(tool_def)

                # Criar executor com closure
                def create_executor(tool_name: str, ctx):
                    async def executor(**kwargs):
                        result = await handlers.execute(tool_name, kwargs, ctx)
                        return result.get("result", result)
                    return executor

                self._tool_registry[name] = create_executor(name, execution_context)

                if name in permissions:
                    self.config.tool_permissions[name] = permissions[name].value

            logger.info(f"[{self.provider.value}] Loaded {len(tools)} unified tools")

        except ImportError as e:
            logger.warning(f"Could not load unified tools: {e}")

    @abstractmethod
    def _get_tools_for_provider(
        self,
        tool_names: Optional[List[str]] = None,
        include_mcp: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Retorna tools no formato específico do provider.

        Args:
            tool_names: Filtrar por nomes
            include_mcp: Incluir MCP tools

        Returns:
            Lista de tools no formato do provider
        """
        pass

    @abstractmethod
    def _extract_tool_name(self, tool_def: Dict[str, Any]) -> str:
        """Extrai nome da tool da definição."""
        pass

    async def _check_permission(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
    ) -> str:
        """
        Verifica permissão para executar tool.

        Args:
            tool_name: Nome da tool
            tool_input: Input da tool

        Returns:
            Modo de permissão: 'allow', 'deny', 'ask'
        """
        # Verificar permissão específica da tool
        permission = self.config.tool_permissions.get(
            tool_name,
            self.config.default_permission_mode
        )

        # TODO: Integrar com PermissionManager para hierarquia completa
        # session > project > global > system

        return permission

    async def _execute_tool(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Executa uma tool.

        Args:
            tool_name: Nome da tool
            tool_input: Parâmetros

        Returns:
            Resultado da execução
        """
        if self.tool_executor:
            return await self.tool_executor(tool_name, tool_input)

        if tool_name not in self._tool_registry:
            return {"error": f"Tool '{tool_name}' not found"}

        handler = self._tool_registry[tool_name]
        try:
            import asyncio
            if asyncio.iscoroutinefunction(handler):
                return await handler(**tool_input)
            else:
                return handler(**tool_input)
        except Exception as e:
            logger.error(f"Tool execution error for {tool_name}: {e}")
            return {"error": str(e)}

    async def _create_checkpoint(
        self,
        description: Optional[str] = None,
    ) -> Optional[str]:
        """
        Cria checkpoint do estado atual.

        Args:
            description: Descrição do checkpoint

        Returns:
            ID do checkpoint ou None
        """
        if not self.config.enable_checkpoints or not self._state:
            return None

        try:
            from app.models import Checkpoint
            import uuid

            checkpoint_id = str(uuid.uuid4())

            # TODO: Persistir checkpoint no banco
            # checkpoint = Checkpoint.create_auto_checkpoint(...)

            self._state.checkpoints.append(checkpoint_id)
            logger.debug(f"Checkpoint created: {checkpoint_id}")

            return checkpoint_id

        except Exception as e:
            logger.warning(f"Failed to create checkpoint: {e}")
            return None

    async def _check_context_usage(self) -> bool:
        """
        Verifica se contexto precisa de compactação.

        Returns:
            True se precisa compactar
        """
        if not self._state:
            return False

        usage = self._state.get_context_usage(self.config.context_window)
        return usage >= self.config.compaction_threshold

    async def _compact_context(self) -> None:
        """Executa compactação do contexto se necessário."""
        if not self.config.enable_compaction:
            return

        if not await self._check_context_usage():
            return

        try:
            from app.services.ai.langgraph.improvements import ContextManager

            # TODO: Implementar compactação usando ContextManager
            logger.info(f"[{self.provider.value}] Context compaction triggered")

        except ImportError:
            logger.warning("ContextManager not available for compaction")
