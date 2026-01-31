"""
OrchestrationRouter - Decide qual executor usar baseado nos modelos selecionados.

Regras de decisão:
1. Se só "claude-agent" selecionado -> CLAUDE_AGENT (Agent SDK autônomo)
2. Se "claude-agent" + outros modelos -> PARALLEL (Agent executa + outros validam)
3. Se só modelos normais (GPT, Claude, Gemini) -> LANGGRAPH (workflow existente)
4. Se mode == "minuta" e qualquer seleção -> LANGGRAPH (workflow de minuta)

Este módulo é o ponto de entrada para execução de prompts no Iudex.
Pode ser usado como drop-in replacement no job_manager.
"""

from enum import Enum
from typing import List, Optional, Dict, Any, AsyncGenerator, TYPE_CHECKING
from dataclasses import dataclass
import logging
import os

from app.services.ai.shared.sse_protocol import (
    SSEEvent,
    SSEEventType,
    create_sse_event,
    token_event,
    done_event,
    error_event,
    thinking_event,
)

logger = logging.getLogger(__name__)


class ExecutorType(str, Enum):
    """Tipo de executor a ser usado."""
    LANGGRAPH = "langgraph"
    CLAUDE_AGENT = "claude_agent"
    OPENAI_AGENT = "openai_agent"
    GOOGLE_AGENT = "google_agent"
    PARALLEL = "parallel"


@dataclass
class RoutingDecision:
    """Decisão de routing com metadados."""
    executor_type: ExecutorType
    primary_models: List[str]
    secondary_models: List[str]
    reason: str


@dataclass
class OrchestrationContext:
    """
    Contexto para execução de prompts.
    Encapsula todos os dados necessários para os executors.
    """
    prompt: str
    job_id: str
    user_id: Optional[str] = None
    chat_id: Optional[str] = None
    case_bundle: Optional[Any] = None
    rag_context: str = ""
    template_structure: str = ""
    extra_instructions: str = ""
    conversation_history: Optional[List[Dict[str, Any]]] = None
    chat_personality: str = "juridico"
    reasoning_level: str = "medium"
    temperature: float = 0.3
    web_search: bool = False
    max_tokens: int = 8192

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OrchestrationContext":
        """Cria contexto a partir de um dicionário."""
        return cls(
            prompt=data.get("prompt", ""),
            job_id=data.get("job_id", ""),
            user_id=data.get("user_id"),
            chat_id=data.get("chat_id"),
            case_bundle=data.get("case_bundle"),
            rag_context=data.get("rag_context", ""),
            template_structure=data.get("template_structure", ""),
            extra_instructions=data.get("extra_instructions", ""),
            conversation_history=data.get("conversation_history"),
            chat_personality=data.get("chat_personality", "juridico"),
            reasoning_level=data.get("reasoning_level", "medium"),
            temperature=float(data.get("temperature", 0.3)),
            web_search=bool(data.get("web_search", False)),
            max_tokens=int(data.get("max_tokens", 8192)),
        )


class OrchestrationRouter:
    """
    Router que decide qual executor usar baseado na seleção de modelos e modo.

    Este é o ponto de entrada principal para execução de prompts.
    Substitui o fluxo direto no job_manager com uma camada de abstração
    que permite múltiplos backends de execução.

    Uso básico:
        router = OrchestrationRouter()
        decision = router.determine_executor(["claude-agent"], "chat")

        async for event in router.execute(prompt, models, context, mode):
            # Processar evento SSE
            pass
    """

    # Modelos de agentes por provider
    CLAUDE_AGENT_MODEL = "claude-agent"
    OPENAI_AGENT_MODEL = "openai-agent"
    GOOGLE_AGENT_MODEL = "google-agent"

    # Todos os modelos de agentes
    AGENT_MODELS = {CLAUDE_AGENT_MODEL, OPENAI_AGENT_MODEL, GOOGLE_AGENT_MODEL}

    # Mapeamento de modelo de agente para executor
    AGENT_TO_EXECUTOR = {
        CLAUDE_AGENT_MODEL: ExecutorType.CLAUDE_AGENT,
        OPENAI_AGENT_MODEL: ExecutorType.OPENAI_AGENT,
        GOOGLE_AGENT_MODEL: ExecutorType.GOOGLE_AGENT,
    }

    # Configurações de ambiente
    CLAUDE_AGENT_ENABLED = os.getenv("CLAUDE_AGENT_ENABLED", "true").lower() == "true"
    OPENAI_AGENT_ENABLED = os.getenv("OPENAI_AGENT_ENABLED", "true").lower() == "true"
    GOOGLE_AGENT_ENABLED = os.getenv("GOOGLE_AGENT_ENABLED", "true").lower() == "true"
    PARALLEL_EXECUTION_ENABLED = os.getenv("PARALLEL_EXECUTION_ENABLED", "true").lower() == "true"
    PARALLEL_EXECUTION_TIMEOUT = int(os.getenv("PARALLEL_EXECUTION_TIMEOUT", "300"))

    def __init__(self):
        """Inicializa o router."""
        self._parallel_executor = None
        self._event_merger = None
        self._executors = {}  # Cache de executores
        logger.info(
            f"OrchestrationRouter inicializado. "
            f"Claude Agent: {self.CLAUDE_AGENT_ENABLED}, "
            f"OpenAI Agent: {self.OPENAI_AGENT_ENABLED}, "
            f"Google Agent: {self.GOOGLE_AGENT_ENABLED}, "
            f"Parallel: {self.PARALLEL_EXECUTION_ENABLED}"
        )

    def _is_agent_enabled(self, agent_model: str) -> bool:
        """Verifica se um agente está habilitado."""
        if agent_model == self.CLAUDE_AGENT_MODEL:
            return self.CLAUDE_AGENT_ENABLED
        elif agent_model == self.OPENAI_AGENT_MODEL:
            return self.OPENAI_AGENT_ENABLED
        elif agent_model == self.GOOGLE_AGENT_MODEL:
            return self.GOOGLE_AGENT_ENABLED
        return False

    def determine_executor(
        self,
        selected_models: List[str],
        mode: str = "chat",
        force_executor: Optional[ExecutorType] = None
    ) -> RoutingDecision:
        """
        Determina qual executor usar baseado nos modelos selecionados.

        Args:
            selected_models: Lista de IDs de modelos selecionados
            mode: Modo de operação ("chat", "minuta", etc.)
            force_executor: Força uso de um executor específico

        Returns:
            RoutingDecision com o executor escolhido e metadados
        """
        if force_executor:
            return RoutingDecision(
                executor_type=force_executor,
                primary_models=selected_models,
                secondary_models=[],
                reason=f"Executor forçado: {force_executor.value}"
            )

        # Modo minuta sempre usa LangGraph
        if mode == "minuta":
            return RoutingDecision(
                executor_type=ExecutorType.LANGGRAPH,
                primary_models=selected_models,
                secondary_models=[],
                reason="Modo minuta requer workflow LangGraph completo"
            )

        # Identificar agentes selecionados
        selected_agents = [m for m in selected_models if m in self.AGENT_MODELS]
        other_models = [m for m in selected_models if m not in self.AGENT_MODELS]
        has_other_models = len(other_models) > 0

        # Verificar se algum agente foi selecionado
        if selected_agents:
            # Encontrar o primeiro agente habilitado
            enabled_agent = None
            for agent in selected_agents:
                if self._is_agent_enabled(agent):
                    enabled_agent = agent
                    break

            if not enabled_agent:
                logger.warning(f"Agentes {selected_agents} desabilitados. Usando LangGraph.")
                return RoutingDecision(
                    executor_type=ExecutorType.LANGGRAPH,
                    primary_models=other_models if other_models else ["gemini-3-flash"],
                    secondary_models=[],
                    reason="Agentes desabilitados, fallback para LangGraph"
                )

            # Determinar executor baseado no agente
            executor_type = self.AGENT_TO_EXECUTOR.get(enabled_agent, ExecutorType.LANGGRAPH)

            # Só agente selecionado (sem outros modelos)
            if not has_other_models:
                return RoutingDecision(
                    executor_type=executor_type,
                    primary_models=[enabled_agent],
                    secondary_models=[],
                    reason=f"{enabled_agent} autônomo selecionado"
                )

            # Agente + outros modelos = execução paralela
            if not self.PARALLEL_EXECUTION_ENABLED:
                logger.warning("Execução paralela desabilitada. Usando apenas agente.")
                return RoutingDecision(
                    executor_type=executor_type,
                    primary_models=[enabled_agent],
                    secondary_models=[],
                    reason="Execução paralela desabilitada"
                )

            return RoutingDecision(
                executor_type=ExecutorType.PARALLEL,
                primary_models=[enabled_agent],
                secondary_models=other_models,
                reason=f"{enabled_agent} + modelos para validação paralela"
            )

        # Apenas modelos normais = LangGraph
        return RoutingDecision(
            executor_type=ExecutorType.LANGGRAPH,
            primary_models=selected_models,
            secondary_models=[],
            reason="Workflow LangGraph com modelos selecionados"
        )

    def validate_model_selection(self, selected_models: List[str]) -> bool:
        """
        Valida se a seleção de modelos é válida.

        Args:
            selected_models: Lista de modelos selecionados

        Returns:
            True se válido, False caso contrário
        """
        if not selected_models:
            return False

        # Pelo menos um modelo deve estar selecionado
        return len(selected_models) > 0

    async def execute(
        self,
        prompt: str,
        selected_models: List[str],
        context: Optional[Dict[str, Any]] = None,
        mode: str = "chat",
        job_id: str = "",
    ) -> AsyncGenerator[SSEEvent, None]:
        """
        Executa o prompt usando o executor apropriado.

        Este é o método principal de entrada. Determina qual executor usar
        e delega a execução, retornando um stream de eventos SSE.

        Args:
            prompt: Prompt do usuário
            selected_models: Lista de modelos selecionados
            context: Contexto adicional (case_bundle, rag_context, etc.)
            mode: Modo de operação ("chat", "minuta", etc.)
            job_id: ID do job para tracking

        Yields:
            SSEEvent para cada evento gerado durante a execução
        """
        context = context or {}
        context["job_id"] = job_id

        # Criar contexto de orquestração
        orchestration_ctx = OrchestrationContext(
            prompt=prompt,
            job_id=job_id,
            **{k: v for k, v in context.items() if k != "job_id" and k != "prompt"}
        )

        # Determinar executor
        decision = self.determine_executor(selected_models, mode)

        logger.info(
            f"Routing decision: {decision.executor_type.value} "
            f"(primary={decision.primary_models}, secondary={decision.secondary_models}, "
            f"reason={decision.reason})"
        )

        # Emitir evento de início
        yield create_sse_event(
            SSEEventType.NODE_START,
            {
                "executor": decision.executor_type.value,
                "models": decision.primary_models,
                "reason": decision.reason,
            },
            job_id=job_id,
            phase="orchestration",
            node="router",
        )

        try:
            # Delegar para o executor apropriado
            if decision.executor_type == ExecutorType.CLAUDE_AGENT:
                async for event in self._execute_claude_agent(
                    orchestration_ctx
                ):
                    yield event

            elif decision.executor_type == ExecutorType.OPENAI_AGENT:
                async for event in self._execute_openai_agent(
                    orchestration_ctx
                ):
                    yield event

            elif decision.executor_type == ExecutorType.GOOGLE_AGENT:
                async for event in self._execute_google_agent(
                    orchestration_ctx
                ):
                    yield event

            elif decision.executor_type == ExecutorType.PARALLEL:
                async for event in self._execute_parallel(
                    orchestration_ctx,
                    decision.primary_models,
                    decision.secondary_models,
                ):
                    yield event

            else:  # LANGGRAPH
                async for event in self._execute_langgraph(
                    orchestration_ctx,
                    decision.primary_models,
                    mode,
                ):
                    yield event

        except Exception as e:
            logger.exception(f"Erro na execução: {e}")
            yield error_event(
                job_id=job_id,
                error=str(e),
                error_type="execution_error",
                recoverable=False,
            )

        # Emitir evento de conclusão
        yield create_sse_event(
            SSEEventType.NODE_COMPLETE,
            {"executor": decision.executor_type.value},
            job_id=job_id,
            phase="orchestration",
            node="router",
        )

    async def _execute_claude_agent(
        self,
        context: OrchestrationContext,
    ) -> AsyncGenerator[SSEEvent, None]:
        """
        Executa usando o Claude Agent SDK.

        O Claude Agent executa de forma autônoma com tools customizados
        para pesquisa jurídica, edição de documentos, etc.

        Args:
            context: Contexto de orquestração

        Yields:
            SSEEvent para cada evento do agent
        """
        job_id = context.job_id

        yield create_sse_event(
            SSEEventType.AGENT_START,
            {
                "agent": "claude",
                "message": "Iniciando Claude Agent autônomo...",
            },
            job_id=job_id,
            phase="agent",
            agent="claude",
        )

        try:
            # Import dinâmico para evitar circular imports
            from app.services.ai.claude_agent.executor import ClaudeAgentExecutor

            executor = ClaudeAgentExecutor()

            # Build system prompt jurídico
            system_prompt = self._build_legal_system_prompt(context)

            # Executar agent
            async for event in executor.execute(
                prompt=context.prompt,
                system_prompt=system_prompt,
                job_id=job_id,
                context={
                    "case_bundle": context.case_bundle,
                    "rag_context": context.rag_context,
                    "template_structure": context.template_structure,
                    "conversation_history": context.conversation_history,
                    "chat_personality": context.chat_personality,
                    "reasoning_level": context.reasoning_level,
                    "temperature": context.temperature,
                    "web_search": context.web_search,
                },
            ):
                yield event

        except ImportError:
            logger.warning("ClaudeAgentExecutor não disponível. Usando fallback.")
            # Fallback para execução simples via agent_clients
            async for event in self._execute_claude_fallback(context):
                yield event

        except Exception as e:
            logger.exception(f"Erro no Claude Agent: {e}")
            yield error_event(
                job_id=job_id,
                error=str(e),
                error_type="claude_agent_error",
                recoverable=True,
            )

    async def _execute_claude_fallback(
        self,
        context: OrchestrationContext,
    ) -> AsyncGenerator[SSEEvent, None]:
        """
        Fallback quando ClaudeAgentExecutor não está disponível.
        Usa agent_clients diretamente para chamada simples.
        """
        job_id = context.job_id

        yield thinking_event(
            job_id=job_id,
            content="Claude Agent SDK não disponível. Usando modo direto...",
            is_final=False,
        )

        try:
            from app.services.ai.agent_clients import (
                init_anthropic_client,
                stream_anthropic_async,
            )
            from app.services.ai.model_registry import get_api_model_name

            client = init_anthropic_client()
            if not client:
                yield error_event(
                    job_id=job_id,
                    error="Anthropic client não disponível",
                    error_type="client_error",
                )
                return

            system_prompt = self._build_legal_system_prompt(context)
            full_prompt = self._build_full_prompt(context)

            # Stream response
            accumulated_text = ""
            async for chunk in stream_anthropic_async(
                client=client,
                prompt=full_prompt,
                model=get_api_model_name("claude-4.5-sonnet"),
                max_tokens=context.max_tokens,
                temperature=context.temperature,
                system_instruction=system_prompt,
            ):
                if isinstance(chunk, dict):
                    token = chunk.get("token", chunk.get("content", ""))
                else:
                    token = str(chunk)

                if token:
                    accumulated_text += token
                    yield token_event(job_id=job_id, token=token, phase="generation")

            yield done_event(
                job_id=job_id,
                final_text=accumulated_text,
                metadata={"mode": "claude_fallback"},
            )

        except Exception as e:
            logger.exception(f"Erro no fallback Claude: {e}")
            yield error_event(
                job_id=job_id,
                error=str(e),
                error_type="fallback_error",
            )

    async def _execute_openai_agent(
        self,
        context: OrchestrationContext,
    ) -> AsyncGenerator[SSEEvent, None]:
        """
        Executa usando o OpenAI Agent SDK.

        O OpenAI Agent executa de forma autônoma com tools customizados
        para pesquisa jurídica, edição de documentos, etc.

        Args:
            context: Contexto de orquestração

        Yields:
            SSEEvent para cada evento do agent
        """
        job_id = context.job_id

        yield create_sse_event(
            SSEEventType.AGENT_START,
            {
                "agent": "openai",
                "message": "Iniciando OpenAI Agent autônomo...",
            },
            job_id=job_id,
            phase="agent",
            agent="openai",
        )

        try:
            # Import dinâmico para evitar circular imports
            from app.services.ai.executors import (
                OpenAIAgentExecutor,
                OpenAIAgentConfig,
                OPENAI_AVAILABLE,
            )
            from app.services.ai.shared import ToolExecutionContext

            if not OPENAI_AVAILABLE:
                raise ImportError("OpenAI SDK not available")

            # Criar contexto de execução para tools
            tool_context = ToolExecutionContext(
                user_id=context.user_id or "anonymous",
                case_id=context.case_bundle.processo_id if context.case_bundle and hasattr(context.case_bundle, "processo_id") else None,
                chat_id=context.chat_id,
                job_id=job_id,
            )

            # Configurar executor
            config = OpenAIAgentConfig(
                model="gpt-4o",
                temperature=context.temperature,
                max_tokens=context.max_tokens,
                max_iterations=30,
            )
            executor = OpenAIAgentExecutor(config=config)

            # Carregar tools unificadas
            executor.load_unified_tools(
                execution_context=tool_context,
                include_mcp=True,
            )

            # Build system prompt jurídico
            system_prompt = self._build_legal_system_prompt(context)
            full_prompt = self._build_full_prompt(context)

            # Executar agent
            async for event in executor.run(
                prompt=full_prompt,
                system_prompt=system_prompt,
                job_id=job_id,
            ):
                # Converter eventos do executor para SSE
                event_type = event.get("type", "")
                event_data = event.get("data", {})

                if event_type == "token":
                    yield token_event(
                        job_id=job_id,
                        token=event_data.get("token", ""),
                        phase="generation",
                    )
                elif event_type == "thinking":
                    yield thinking_event(
                        job_id=job_id,
                        content=event_data.get("content", ""),
                        is_final=event_data.get("is_final", False),
                    )
                elif event_type == "tool_call":
                    yield create_sse_event(
                        SSEEventType.TOOL_CALL,
                        event_data,
                        job_id=job_id,
                        phase="agent",
                        agent="openai",
                    )
                elif event_type == "tool_result":
                    yield create_sse_event(
                        SSEEventType.TOOL_RESULT,
                        event_data,
                        job_id=job_id,
                        phase="agent",
                        agent="openai",
                    )
                elif event_type == "done":
                    yield done_event(
                        job_id=job_id,
                        final_text=event_data.get("final_text", ""),
                        metadata={"mode": "openai_agent", **event_data.get("metadata", {})},
                    )
                elif event_type == "error":
                    yield error_event(
                        job_id=job_id,
                        error=event_data.get("error", "Unknown error"),
                        error_type="openai_agent_error",
                        recoverable=event_data.get("recoverable", True),
                    )

        except ImportError:
            logger.warning("OpenAIAgentExecutor não disponível. Usando fallback.")
            # Fallback para execução simples
            async for event in self._execute_openai_fallback(context):
                yield event

        except Exception as e:
            logger.exception(f"Erro no OpenAI Agent: {e}")
            yield error_event(
                job_id=job_id,
                error=str(e),
                error_type="openai_agent_error",
                recoverable=True,
            )

    async def _execute_openai_fallback(
        self,
        context: OrchestrationContext,
    ) -> AsyncGenerator[SSEEvent, None]:
        """
        Fallback quando OpenAIAgentExecutor não está disponível.
        Usa agent_clients diretamente para chamada simples.
        """
        job_id = context.job_id

        yield thinking_event(
            job_id=job_id,
            content="OpenAI Agent SDK não disponível. Usando modo direto...",
            is_final=False,
        )

        try:
            from app.services.ai.agent_clients import (
                init_openai_client,
                stream_openai_async,
            )

            client = init_openai_client()
            if not client:
                yield error_event(
                    job_id=job_id,
                    error="OpenAI client não disponível",
                    error_type="client_error",
                )
                return

            system_prompt = self._build_legal_system_prompt(context)
            full_prompt = self._build_full_prompt(context)

            # Stream response
            accumulated_text = ""
            async for chunk in stream_openai_async(
                client=client,
                prompt=full_prompt,
                model="gpt-4o",
                max_tokens=context.max_tokens,
                temperature=context.temperature,
                system_instruction=system_prompt,
            ):
                if isinstance(chunk, dict):
                    token = chunk.get("token", chunk.get("content", ""))
                else:
                    token = str(chunk)

                if token:
                    accumulated_text += token
                    yield token_event(job_id=job_id, token=token, phase="generation")

            yield done_event(
                job_id=job_id,
                final_text=accumulated_text,
                metadata={"mode": "openai_fallback"},
            )

        except Exception as e:
            logger.exception(f"Erro no fallback OpenAI: {e}")
            yield error_event(
                job_id=job_id,
                error=str(e),
                error_type="fallback_error",
            )

    async def _execute_google_agent(
        self,
        context: OrchestrationContext,
    ) -> AsyncGenerator[SSEEvent, None]:
        """
        Executa usando o Google Agent (Gemini/Vertex AI/ADK).

        O Google Agent executa de forma autônoma com tools customizados
        para pesquisa jurídica, edição de documentos, etc.

        Args:
            context: Contexto de orquestração

        Yields:
            SSEEvent para cada evento do agent
        """
        job_id = context.job_id

        yield create_sse_event(
            SSEEventType.AGENT_START,
            {
                "agent": "google",
                "message": "Iniciando Google Agent autônomo...",
            },
            job_id=job_id,
            phase="agent",
            agent="google",
        )

        try:
            # Import dinâmico para evitar circular imports
            from app.services.ai.executors import (
                GoogleAgentExecutor,
                GoogleAgentConfig,
                GENAI_AVAILABLE,
                VERTEX_AVAILABLE,
            )
            from app.services.ai.shared import ToolExecutionContext

            if not GENAI_AVAILABLE and not VERTEX_AVAILABLE:
                raise ImportError("Google GenAI/Vertex SDK not available")

            # Criar contexto de execução para tools
            tool_context = ToolExecutionContext(
                user_id=context.user_id or "anonymous",
                case_id=context.case_bundle.processo_id if context.case_bundle and hasattr(context.case_bundle, "processo_id") else None,
                chat_id=context.chat_id,
                job_id=job_id,
            )

            # Configurar executor
            config = GoogleAgentConfig(
                model="gemini-2.0-flash-exp",
                temperature=context.temperature,
                max_tokens=context.max_tokens,
                max_iterations=30,
                use_vertex=VERTEX_AVAILABLE,
                use_adk=True,  # Preferir ADK se disponível
            )
            executor = GoogleAgentExecutor(config=config)

            # Carregar tools unificadas
            executor.load_unified_tools(
                execution_context=tool_context,
                include_mcp=True,
            )

            # Build system prompt jurídico
            system_prompt = self._build_legal_system_prompt(context)
            full_prompt = self._build_full_prompt(context)

            # Executar agent
            async for event in executor.run(
                prompt=full_prompt,
                system_prompt=system_prompt,
                job_id=job_id,
            ):
                # Converter eventos do executor para SSE
                event_type = event.get("type", "")
                event_data = event.get("data", {})

                if event_type == "token":
                    yield token_event(
                        job_id=job_id,
                        token=event_data.get("token", ""),
                        phase="generation",
                    )
                elif event_type == "thinking":
                    yield thinking_event(
                        job_id=job_id,
                        content=event_data.get("content", ""),
                        is_final=event_data.get("is_final", False),
                    )
                elif event_type == "tool_call":
                    yield create_sse_event(
                        SSEEventType.TOOL_CALL,
                        event_data,
                        job_id=job_id,
                        phase="agent",
                        agent="google",
                    )
                elif event_type == "tool_result":
                    yield create_sse_event(
                        SSEEventType.TOOL_RESULT,
                        event_data,
                        job_id=job_id,
                        phase="agent",
                        agent="google",
                    )
                elif event_type == "done":
                    yield done_event(
                        job_id=job_id,
                        final_text=event_data.get("final_text", ""),
                        metadata={"mode": "google_agent", **event_data.get("metadata", {})},
                    )
                elif event_type == "error":
                    yield error_event(
                        job_id=job_id,
                        error=event_data.get("error", "Unknown error"),
                        error_type="google_agent_error",
                        recoverable=event_data.get("recoverable", True),
                    )

        except ImportError:
            logger.warning("GoogleAgentExecutor não disponível. Usando fallback.")
            # Fallback para execução simples
            async for event in self._execute_google_fallback(context):
                yield event

        except Exception as e:
            logger.exception(f"Erro no Google Agent: {e}")
            yield error_event(
                job_id=job_id,
                error=str(e),
                error_type="google_agent_error",
                recoverable=True,
            )

    async def _execute_google_fallback(
        self,
        context: OrchestrationContext,
    ) -> AsyncGenerator[SSEEvent, None]:
        """
        Fallback quando GoogleAgentExecutor não está disponível.
        Usa agent_clients diretamente para chamada simples.
        """
        job_id = context.job_id

        yield thinking_event(
            job_id=job_id,
            content="Google Agent SDK não disponível. Usando modo direto...",
            is_final=False,
        )

        try:
            from app.services.ai.agent_clients import (
                get_gemini_client,
                stream_vertex_gemini_async,
            )

            client = get_gemini_client()
            if not client:
                yield error_event(
                    job_id=job_id,
                    error="Google Gemini client não disponível",
                    error_type="client_error",
                )
                return

            system_prompt = self._build_legal_system_prompt(context)
            full_prompt = self._build_full_prompt(context)

            # Stream response
            accumulated_text = ""
            async for chunk in stream_vertex_gemini_async(
                client=client,
                prompt=full_prompt,
                model="gemini-2.0-flash-exp",
                temperature=context.temperature,
                system_instruction=system_prompt,
            ):
                if isinstance(chunk, dict):
                    token = chunk.get("token", chunk.get("content", ""))
                else:
                    token = str(chunk)

                if token:
                    accumulated_text += token
                    yield token_event(job_id=job_id, token=token, phase="generation")

            yield done_event(
                job_id=job_id,
                final_text=accumulated_text,
                metadata={"mode": "google_fallback"},
            )

        except Exception as e:
            logger.exception(f"Erro no fallback Google: {e}")
            yield error_event(
                job_id=job_id,
                error=str(e),
                error_type="fallback_error",
            )

    async def _execute_langgraph(
        self,
        context: OrchestrationContext,
        models: List[str],
        mode: str,
    ) -> AsyncGenerator[SSEEvent, None]:
        """
        Executa usando o workflow LangGraph existente.

        Delega para o langgraph_legal_workflow que já implementa
        todo o fluxo de outline -> research -> debate -> audit.

        Args:
            context: Contexto de orquestração
            models: Lista de modelos para o workflow
            mode: Modo de operação

        Yields:
            SSEEvent para cada evento do workflow
        """
        job_id = context.job_id

        yield create_sse_event(
            SSEEventType.NODE_START,
            {
                "workflow": "langgraph",
                "models": models,
                "mode": mode,
            },
            job_id=job_id,
            phase="langgraph",
            node="workflow_start",
        )

        try:
            # Import dinâmico para evitar circular imports
            from app.services.ai.langgraph_legal_workflow import (
                run_workflow_async,
                DocumentState,
            )

            # Preparar state inicial
            initial_state: Dict[str, Any] = {
                "job_id": job_id,
                "input_text": context.prompt,
                "chat_personality": context.chat_personality,
                "reasoning_level": context.reasoning_level,
                "selected_models": models,
                "mode": mode,
            }

            # Adicionar contexto adicional se disponível
            if context.case_bundle:
                if hasattr(context.case_bundle, "processo_id"):
                    initial_state["case_bundle_processo_id"] = context.case_bundle.processo_id
                if hasattr(context.case_bundle, "text_pack"):
                    initial_state["case_bundle_text_pack"] = context.case_bundle.text_pack

            if context.rag_context:
                initial_state["rag_context"] = context.rag_context

            if context.template_structure:
                initial_state["template_structure"] = context.template_structure

            if context.extra_instructions:
                initial_state["extra_agent_instructions"] = context.extra_instructions

            if context.web_search:
                initial_state["web_search"] = True

            # Executar workflow
            # O workflow usa job_manager.emit_event internamente
            # Precisamos converter para nosso formato SSE
            final_state = await run_workflow_async(initial_state)

            # Extrair resultado final
            final_document = final_state.get("full_document", "")
            if not final_document:
                # Tentar recuperar de sections
                sections = final_state.get("processed_sections", [])
                if sections:
                    final_document = "\n\n".join(
                        s.get("content", "") for s in sections if isinstance(s, dict)
                    )

            yield done_event(
                job_id=job_id,
                final_text=final_document,
                metadata={
                    "mode": "langgraph",
                    "sections_count": len(final_state.get("processed_sections", [])),
                    "outline": final_state.get("outline", []),
                },
            )

        except ImportError as e:
            logger.warning(f"LangGraph workflow não disponível: {e}. Usando fallback simples.")
            async for event in self._execute_langgraph_fallback(context, models):
                yield event

        except Exception as e:
            logger.exception(f"Erro no LangGraph: {e}")
            yield error_event(
                job_id=job_id,
                error=str(e),
                error_type="langgraph_error",
                recoverable=False,
            )

    async def _execute_langgraph_fallback(
        self,
        context: OrchestrationContext,
        models: List[str],
    ) -> AsyncGenerator[SSEEvent, None]:
        """
        Fallback simples quando LangGraph não está disponível.
        Usa o primeiro modelo disponível para geração direta.
        """
        job_id = context.job_id

        yield thinking_event(
            job_id=job_id,
            content="LangGraph não disponível. Usando geração direta...",
            is_final=False,
        )

        try:
            from app.services.ai.agent_clients import (
                init_openai_client,
                init_anthropic_client,
                get_gemini_client,
                stream_openai_async,
                stream_anthropic_async,
                stream_vertex_gemini_async,
            )
            from app.services.ai.model_registry import get_model_config, get_api_model_name

            # Escolher primeiro modelo disponível
            model_id = models[0] if models else "gemini-3-flash"
            config = get_model_config(model_id)

            if not config:
                yield error_event(
                    job_id=job_id,
                    error=f"Modelo {model_id} não encontrado no registry",
                    error_type="model_error",
                )
                return

            system_prompt = self._build_legal_system_prompt(context)
            full_prompt = self._build_full_prompt(context)

            accumulated_text = ""

            # Escolher client e stream baseado no provider
            if config.provider == "google":
                client = get_gemini_client()
                async for chunk in stream_vertex_gemini_async(
                    client,
                    full_prompt,
                    model=model_id,
                    temperature=context.temperature,
                    system_instruction=system_prompt,
                ):
                    token = chunk.get("token", "") if isinstance(chunk, dict) else str(chunk)
                    if token:
                        accumulated_text += token
                        yield token_event(job_id=job_id, token=token)

            elif config.provider == "anthropic":
                client = init_anthropic_client()
                async for chunk in stream_anthropic_async(
                    client,
                    full_prompt,
                    model=get_api_model_name(model_id),
                    temperature=context.temperature,
                    system_instruction=system_prompt,
                ):
                    token = chunk.get("token", "") if isinstance(chunk, dict) else str(chunk)
                    if token:
                        accumulated_text += token
                        yield token_event(job_id=job_id, token=token)

            else:  # OpenAI e outros compatíveis
                client = init_openai_client()
                async for chunk in stream_openai_async(
                    client,
                    full_prompt,
                    model=get_api_model_name(model_id),
                    temperature=context.temperature,
                    system_instruction=system_prompt,
                ):
                    token = chunk.get("token", "") if isinstance(chunk, dict) else str(chunk)
                    if token:
                        accumulated_text += token
                        yield token_event(job_id=job_id, token=token)

            yield done_event(
                job_id=job_id,
                final_text=accumulated_text,
                metadata={"mode": "langgraph_fallback", "model": model_id},
            )

        except Exception as e:
            logger.exception(f"Erro no fallback LangGraph: {e}")
            yield error_event(
                job_id=job_id,
                error=str(e),
                error_type="fallback_error",
            )

    async def _execute_parallel(
        self,
        context: OrchestrationContext,
        primary_models: List[str],
        secondary_models: List[str],
    ) -> AsyncGenerator[SSEEvent, None]:
        """
        Executa Claude Agent e LangGraph Debate em paralelo.

        Estratégia:
        1. Agent faz research + draft inicial (autonomamente)
        2. Debate models validam/refinam em paralelo
        3. Merge com resolução de conflitos (usando LLM como juiz)

        Args:
            context: Contexto de orquestração
            primary_models: Modelos primários (Claude Agent)
            secondary_models: Modelos para o debate paralelo

        Yields:
            SSEEvent para cada evento da execução paralela
        """
        job_id = context.job_id

        try:
            # Import dinâmico
            from app.services.ai.orchestration.parallel_executor import (
                ParallelExecutor,
                ExecutionContext,
            )

            # Criar contexto de execução para o ParallelExecutor
            execution_context = ExecutionContext(
                job_id=job_id,
                prompt=context.prompt,
                rag_context=context.rag_context,
                thesis=context.extra_instructions or "",
                mode="minuta" if "minuta" in context.chat_personality.lower() else "parecer",
                section_title="Documento Principal",
                previous_sections=[],
                temperature=context.temperature,
            )

            # Inicializar executor paralelo
            parallel_executor = ParallelExecutor(
                timeout=self.PARALLEL_EXECUTION_TIMEOUT,
                fail_fast=False,
            )

            # Executar em paralelo e emitir eventos
            async for event in parallel_executor.execute(
                prompt=context.prompt,
                agent_models=primary_models,
                debate_models=secondary_models,
                context=execution_context,
                mode="parallel",
            ):
                yield event

        except ImportError as e:
            logger.warning(f"ParallelExecutor não disponível: {e}. Usando fallback.")
            # Fallback: executa apenas Claude Agent
            async for event in self._execute_parallel_fallback(
                context, primary_models, secondary_models
            ):
                yield event

        except Exception as e:
            logger.exception(f"Erro na execução paralela: {e}")
            yield error_event(
                job_id=job_id,
                error=str(e),
                error_type="parallel_error",
                recoverable=True,
            )
            # Fallback para execução apenas do Claude Agent
            logger.info("Fallback para execução apenas do Claude Agent")
            async for event in self._execute_claude_agent(context):
                yield event

    async def _execute_parallel_fallback(
        self,
        context: OrchestrationContext,
        primary_models: List[str],
        secondary_models: List[str],
    ) -> AsyncGenerator[SSEEvent, None]:
        """
        Fallback simplificado quando ParallelExecutor completo não está disponível.
        Executa Agent primeiro, depois faz review com modelos secundários.
        """
        job_id = context.job_id

        yield create_sse_event(
            SSEEventType.PARALLEL_START,
            {
                "primary": primary_models,
                "secondary": secondary_models,
                "timeout": self.PARALLEL_EXECUTION_TIMEOUT,
                "mode": "fallback",
            },
            job_id=job_id,
            phase="parallel",
        )

        # Executar Claude Agent primeiro
        primary_content = ""
        async for event in self._execute_claude_agent(context):
            yield event
            # Capturar conteúdo final
            if event.type == SSEEventType.DONE:
                primary_content = event.data.get("final_text", "")

        # Se temos modelos secundários e conteúdo primário, fazer review
        if secondary_models and primary_content:
            yield create_sse_event(
                SSEEventType.NODE_START,
                {
                    "phase": "parallel_review",
                    "models": secondary_models,
                },
                job_id=job_id,
                phase="parallel",
                node="review",
            )

            # Fazer review paralelo com os modelos secundários
            review_prompt = f"""
Revise o seguinte documento jurídico e identifique:
1. Problemas de fundamentação ou citações
2. Inconsistências lógicas
3. Pontos que podem ser melhorados

DOCUMENTO:
{primary_content[:8000]}

Responda com uma análise estruturada.
"""
            review_context = OrchestrationContext(
                prompt=review_prompt,
                job_id=job_id,
                chat_personality=context.chat_personality,
                reasoning_level="medium",
                temperature=0.2,
            )

            reviews = []
            for model_id in secondary_models[:2]:  # Limitar a 2 reviews
                review_text = ""
                async for event in self._execute_langgraph_fallback(
                    review_context, [model_id]
                ):
                    if event.type == SSEEventType.DONE:
                        review_text = event.data.get("final_text", "")
                    # Não re-yield os eventos de review, apenas capturar
                if review_text:
                    reviews.append({
                        "model": model_id,
                        "review": review_text[:2000],
                    })

            yield create_sse_event(
                SSEEventType.NODE_COMPLETE,
                {
                    "phase": "parallel_review",
                    "reviews_count": len(reviews),
                    "reviews": reviews,
                },
                job_id=job_id,
                phase="parallel",
                node="review",
            )

        yield create_sse_event(
            SSEEventType.PARALLEL_COMPLETE,
            {
                "primary_executor": "claude-agent",
                "reviews_completed": len(secondary_models) if primary_content else 0,
            },
            job_id=job_id,
            phase="parallel",
        )

    def _build_legal_system_prompt(self, context: OrchestrationContext) -> str:
        """
        Constrói o system prompt para contexto jurídico.

        Inclui instruções específicas para:
        - Modo (juridico/geral)
        - Nível de raciocínio
        - Formatação
        - Citações

        Args:
            context: Contexto de orquestração

        Returns:
            System prompt formatado
        """
        personality = context.chat_personality.lower()

        if personality == "geral":
            base_prompt = """Você é um assistente inteligente e versátil.

ESTILO:
- Use linguagem clara e acessível
- Seja direto e objetivo
- Explique conceitos quando necessário
- Adapte o tom ao contexto da pergunta"""
        else:
            base_prompt = """Você é um especialista jurídico brasileiro altamente qualificado.

FORMAÇÃO:
- Especialista em Direito Brasileiro
- Conhecimento profundo de legislação, jurisprudência e doutrina
- Experiência em redação de peças processuais

ESTILO:
- Use linguagem técnica e formal
- Estruture argumentos de forma clara e lógica
- Cite fontes quando disponíveis
- Siga as normas da ABNT para referências

REGRAS DE CITAÇÃO:
- Cite leis no formato: Lei nº X.XXX/AAAA, art. XX
- Cite jurisprudência: Tribunal, Recurso nº, Relator, Data
- Use [n] para referenciar fontes da pesquisa web
- Marque afirmações sem fonte com [VERIFICAR]"""

        # Adicionar instruções de raciocínio
        reasoning = context.reasoning_level.lower()
        if reasoning == "high" or reasoning == "xhigh":
            base_prompt += """

RACIOCÍNIO PROFUNDO:
- Analise todos os ângulos do problema
- Considere argumentos contrários
- Explore nuances e exceções
- Seja exaustivo na fundamentação"""
        elif reasoning == "low":
            base_prompt += """

RACIOCÍNIO DIRETO:
- Vá direto ao ponto
- Seja conciso
- Foque na resposta principal"""

        # Adicionar contexto do template se disponível
        if context.template_structure:
            base_prompt += f"""

ESTRUTURA DO DOCUMENTO:
{context.template_structure}

Siga esta estrutura na sua resposta."""

        # Adicionar instruções extras se disponíveis
        if context.extra_instructions:
            base_prompt += f"""

INSTRUÇÕES ADICIONAIS:
{context.extra_instructions}"""

        return base_prompt

    def _build_full_prompt(self, context: OrchestrationContext) -> str:
        """
        Constrói o prompt completo com contexto.

        Args:
            context: Contexto de orquestração

        Returns:
            Prompt completo formatado
        """
        parts = []

        # Contexto RAG se disponível
        if context.rag_context:
            parts.append(f"## FONTES DISPONÍVEIS\n{context.rag_context}")

        # Case bundle se disponível
        if context.case_bundle:
            bundle_text = ""
            if hasattr(context.case_bundle, "to_agent_context"):
                bundle_text = context.case_bundle.to_agent_context()
            elif hasattr(context.case_bundle, "text_pack"):
                bundle_text = context.case_bundle.text_pack
            if bundle_text:
                parts.append(f"## CONTEXTO DO CASO\n{bundle_text}")

        # Histórico de conversa se disponível
        if context.conversation_history:
            history_text = "\n".join(
                f"{'Usuário' if m.get('role') == 'user' else 'Assistente'}: {m.get('content', '')}"
                for m in context.conversation_history[-5:]  # Últimas 5 mensagens
            )
            if history_text:
                parts.append(f"## HISTÓRICO\n{history_text}")

        # Prompt principal
        parts.append(f"## SOLICITAÇÃO\n{context.prompt}")

        return "\n\n".join(parts)


# Instância global do router (singleton)
_router_instance: Optional[OrchestrationRouter] = None


def get_orchestration_router() -> OrchestrationRouter:
    """
    Retorna a instância global do OrchestrationRouter.

    Uso:
        router = get_orchestration_router()
        async for event in router.execute(...):
            ...

    Returns:
        Instância do OrchestrationRouter
    """
    global _router_instance
    if _router_instance is None:
        _router_instance = OrchestrationRouter()
    return _router_instance
