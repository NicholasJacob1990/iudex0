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
import time

from app.services.ai.shared.sse_protocol import (
    SSEEvent,
    SSEEventType,
    create_sse_event,
    token_event,
    done_event,
    error_event,
    thinking_event,
)
from app.services.ai.shared.feature_flags import FeatureFlagManager
from app.services.ai.shared.quotas import TenantQuotaManager
from app.services.ai.observability.metrics import get_observability_metrics
from app.services.ai.orchestration.graph_tool_policy import build_tool_allowlist

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
    document_route: str = "default"
    estimated_pages: int = 0


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
    execution_profile: str = "default"  # "default" | "quick"
    target_pages: int = 0
    min_pages: int = 0
    max_pages: int = 0
    estimated_pages: int = 0
    document_route: str = "default"
    skill_matched: bool = False
    skill_prefer_workflow: bool = False
    skill_prefer_agent: bool = False
    skill_name: Optional[str] = None

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
            execution_profile=str(data.get("execution_profile", "default")),
            target_pages=int(data.get("target_pages", 0) or 0),
            min_pages=int(data.get("min_pages", 0) or 0),
            max_pages=int(data.get("max_pages", 0) or 0),
            estimated_pages=int(data.get("estimated_pages", 0) or 0),
            document_route=str(data.get("document_route", "default") or "default"),
            skill_matched=bool(data.get("skill_matched", False)),
            skill_prefer_workflow=bool(data.get("skill_prefer_workflow", False)),
            skill_prefer_agent=bool(data.get("skill_prefer_agent", False)),
            skill_name=(str(data.get("skill_name") or "").strip() or None),
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

    def _is_quick_profile(self, context: OrchestrationContext) -> bool:
        """Whether request asks for the lightweight quick-agent profile."""
        return (context.execution_profile or "").strip().lower() == "quick"

    def _quick_max_iterations(self, default: int = 6) -> int:
        """Bounded max iterations used by quick profile executors."""
        try:
            value = int(os.getenv("QUICK_AGENT_MAX_ITERATIONS", str(default)) or default)
        except Exception:
            value = default
        return max(2, min(20, value))

    def _estimate_document_pages(self, context: Optional[OrchestrationContext]) -> int:
        """
        Estimate document size in pages for routing decisions.

        Priority:
        1) Explicit values from context (estimated_pages/max_pages/target_pages/min_pages)
        2) Heuristic by text length (prompt + rag_context, ~4k chars/page)
        """
        if not context:
            return 0

        explicit_candidates = [
            int(getattr(context, "estimated_pages", 0) or 0),
            int(getattr(context, "max_pages", 0) or 0),
            int(getattr(context, "target_pages", 0) or 0),
            int(getattr(context, "min_pages", 0) or 0),
        ]
        explicit_pages = max([p for p in explicit_candidates if p > 0], default=0)

        text_chars = len(context.prompt or "") + len(context.rag_context or "")
        inferred_pages = text_chars // 4000 if text_chars > 0 else 0

        return max(explicit_pages, inferred_pages)

    def _route_by_document_size(self, pages: int) -> str:
        """
        Classify routing strategy based on estimated document pages.
        """
        pages = int(pages or 0)
        if pages <= 0:
            return "default"
        if pages <= 100:
            return "direct"
        if pages <= 500:
            return "rag_enhanced"
        if pages <= 2000:
            return "chunked_rag"
        return "multi_pass"

    def _detect_provider_family(self, model_id: str) -> str:
        """Infer provider family from model identifier."""
        model = str(model_id or "").strip().lower()
        if not model:
            return "unknown"
        if "claude" in model or "anthropic" in model:
            return "anthropic"
        if "gpt" in model or model.startswith("o1") or model.startswith("o3") or "openai" in model:
            return "openai"
        if "gemini" in model or "google" in model:
            return "google"
        return "unknown"

    def _infer_skill_agent_executor(
        self,
        selected_models: List[str],
    ) -> Optional[tuple[ExecutorType, str]]:
        """Infer native agent executor when all selected models are same provider family."""
        non_agent_models = [m for m in selected_models if m not in self.AGENT_MODELS]
        if not non_agent_models:
            return None

        families = {self._detect_provider_family(m) for m in non_agent_models}
        if "unknown" in families:
            return None
        if len(families) != 1:
            return None

        family = next(iter(families))
        if family == "anthropic" and self._is_agent_enabled(self.CLAUDE_AGENT_MODEL):
            return ExecutorType.CLAUDE_AGENT, self.CLAUDE_AGENT_MODEL
        if family == "openai" and self._is_agent_enabled(self.OPENAI_AGENT_MODEL):
            return ExecutorType.OPENAI_AGENT, self.OPENAI_AGENT_MODEL
        if family == "google" and self._is_agent_enabled(self.GOOGLE_AGENT_MODEL):
            return ExecutorType.GOOGLE_AGENT, self.GOOGLE_AGENT_MODEL
        return None

    # Configurações de ambiente
    CLAUDE_AGENT_ENABLED = os.getenv("CLAUDE_AGENT_ENABLED", "true").lower() == "true"
    OPENAI_AGENT_ENABLED = os.getenv("OPENAI_AGENT_ENABLED", "true").lower() == "true"
    GOOGLE_AGENT_ENABLED = os.getenv("GOOGLE_AGENT_ENABLED", "true").lower() == "true"
    PARALLEL_EXECUTION_ENABLED = os.getenv("PARALLEL_EXECUTION_ENABLED", "true").lower() == "true"
    PARALLEL_EXECUTION_TIMEOUT = int(os.getenv("PARALLEL_EXECUTION_TIMEOUT", "300"))

    def __init__(self):
        """Inicializa o router."""
        self.feature_flags = FeatureFlagManager()
        self._parallel_executor = None
        self._event_merger = None
        self._executors = {}  # Cache de executores
        self.tenant_quotas = TenantQuotaManager()
        self.CLAUDE_AGENT_ENABLED = (
            self.CLAUDE_AGENT_ENABLED and self.feature_flags.is_executor_enabled("claude_agent")
        )
        self.OPENAI_AGENT_ENABLED = (
            self.OPENAI_AGENT_ENABLED and self.feature_flags.is_executor_enabled("openai_agent")
        )
        self.GOOGLE_AGENT_ENABLED = (
            self.GOOGLE_AGENT_ENABLED and self.feature_flags.is_executor_enabled("google_agent")
        )
        self.PARALLEL_EXECUTION_ENABLED = (
            self.PARALLEL_EXECUTION_ENABLED and self.feature_flags.is_executor_enabled("parallel")
        )
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
            return self.CLAUDE_AGENT_ENABLED and self.feature_flags.is_executor_enabled("claude_agent")
        elif agent_model == self.OPENAI_AGENT_MODEL:
            return self.OPENAI_AGENT_ENABLED and self.feature_flags.is_executor_enabled("openai_agent")
        elif agent_model == self.GOOGLE_AGENT_MODEL:
            return self.GOOGLE_AGENT_ENABLED and self.feature_flags.is_executor_enabled("google_agent")
        return False

    def determine_executor(
        self,
        selected_models: List[str],
        mode: str = "chat",
        force_executor: Optional[ExecutorType] = None,
        context: Optional[OrchestrationContext] = None,
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

        # Global kill switch + canary rollout para trilhas agentic.
        if selected_agents and not self.feature_flags.is_global_enabled():
            return RoutingDecision(
                executor_type=ExecutorType.LANGGRAPH,
                primary_models=other_models if other_models else ["gemini-3-flash"],
                secondary_models=[],
                reason="Kill switch global agentic ativo; fallback para LangGraph",
            )
        if selected_agents:
            actor_id = context.user_id if context else None
            if not self.feature_flags.is_canary_enabled(actor_id):
                return RoutingDecision(
                    executor_type=ExecutorType.LANGGRAPH,
                    primary_models=other_models if other_models else ["gemini-3-flash"],
                    secondary_models=[],
                    reason="Rollout canário: tenant fora da amostra agentic",
                )

        estimated_pages = self._estimate_document_pages(context)
        document_route = self._route_by_document_size(estimated_pages)

        # Large documents should always use LangGraph workflow for chunking/multi-pass.
        if document_route in ("chunked_rag", "multi_pass"):
            langgraph_models = [m for m in selected_models if m not in self.AGENT_MODELS]
            if not langgraph_models:
                langgraph_models = ["gemini-3-flash"]
            return RoutingDecision(
                executor_type=ExecutorType.LANGGRAPH,
                primary_models=langgraph_models,
                secondary_models=[],
                reason=(
                    f"Documento estimado em ~{estimated_pages} páginas exige "
                    f"roteamento {document_route} via LangGraph"
                ),
                document_route=document_route,
                estimated_pages=estimated_pages,
            )

        # Skill can force workflow-first path for complex process requirements.
        if context and context.skill_matched and context.skill_prefer_workflow:
            langgraph_models = [m for m in selected_models if m not in self.AGENT_MODELS]
            if not langgraph_models:
                langgraph_models = ["gemini-3-flash"]
            skill_label = f" ({context.skill_name})" if context.skill_name else ""
            return RoutingDecision(
                executor_type=ExecutorType.LANGGRAPH,
                primary_models=langgraph_models,
                secondary_models=[],
                reason=f"Skill matched{skill_label} com prefer_workflow=true",
                document_route=document_route,
                estimated_pages=estimated_pages,
            )

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
                    reason="Agentes desabilitados, fallback para LangGraph",
                    document_route=document_route,
                    estimated_pages=estimated_pages,
                )

            # Determinar executor baseado no agente
            executor_type = self.AGENT_TO_EXECUTOR.get(enabled_agent, ExecutorType.LANGGRAPH)

            # Só agente selecionado (sem outros modelos)
            if not has_other_models:
                return RoutingDecision(
                    executor_type=executor_type,
                    primary_models=[enabled_agent],
                    secondary_models=[],
                    reason=f"{enabled_agent} autônomo selecionado",
                    document_route=document_route,
                    estimated_pages=estimated_pages,
                )

            # Agente + outros modelos = execução paralela
            if not (self.PARALLEL_EXECUTION_ENABLED and self.feature_flags.is_executor_enabled("parallel")):
                logger.warning("Execução paralela desabilitada. Usando apenas agente.")
                return RoutingDecision(
                    executor_type=executor_type,
                    primary_models=[enabled_agent],
                    secondary_models=[],
                    reason="Execução paralela desabilitada",
                    document_route=document_route,
                    estimated_pages=estimated_pages,
                )

            return RoutingDecision(
                executor_type=ExecutorType.PARALLEL,
                primary_models=[enabled_agent],
                secondary_models=other_models,
                reason=f"{enabled_agent} + modelos para validação paralela",
                document_route=document_route,
                estimated_pages=estimated_pages,
            )

        # Skill-driven native agent routing for single-provider model selections.
        if context and context.skill_matched and context.skill_prefer_agent:
            inferred = self._infer_skill_agent_executor(selected_models)
            if inferred:
                executor_type, agent_model = inferred
                skill_label = f" ({context.skill_name})" if context.skill_name else ""
                return RoutingDecision(
                    executor_type=executor_type,
                    primary_models=[agent_model],
                    secondary_models=[],
                    reason=f"Skill matched{skill_label} com prefer_agent=true",
                    document_route=document_route,
                    estimated_pages=estimated_pages,
                )

        # Apenas modelos normais = LangGraph
        return RoutingDecision(
            executor_type=ExecutorType.LANGGRAPH,
            primary_models=selected_models,
            secondary_models=[],
            reason="Workflow LangGraph com modelos selecionados",
            document_route=document_route,
            estimated_pages=estimated_pages,
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
        started_at = time.monotonic()
        metrics = get_observability_metrics()
        context = context or {}
        context["job_id"] = job_id
        tenant_key = str(
            context.get("tenant_id")
            or context.get("user_id")
            or "anonymous"
        )
        quota_decision = self.tenant_quotas.check_and_consume(tenant_key, requests_cost=1)
        if not quota_decision.allowed:
            metrics.record_request(
                execution_path="router:quota_blocked",
                latency_ms=max(0.0, (time.monotonic() - started_at) * 1000.0),
                success=False,
            )
            yield error_event(
                job_id=job_id,
                error=(
                    "Limite de cota excedido: "
                    f"{quota_decision.reason}. Tente novamente após o reset da janela."
                ),
                error_type="quota_exceeded",
                recoverable=True,
            )
            return

        # Criar contexto de orquestração
        orchestration_ctx = OrchestrationContext.from_dict(
            {
                "prompt": prompt,
                "job_id": job_id,
                **{k: v for k, v in context.items() if k not in {"job_id", "prompt"}},
            }
        )

        # Determinar executor
        decision = self.determine_executor(selected_models, mode, context=orchestration_ctx)
        orchestration_ctx.estimated_pages = int(decision.estimated_pages or orchestration_ctx.estimated_pages or 0)
        orchestration_ctx.document_route = str(decision.document_route or orchestration_ctx.document_route or "default")

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
                "document_route": decision.document_route,
                "estimated_pages": decision.estimated_pages,
            },
            job_id=job_id,
            phase="orchestration",
            node="router",
        )

        execution_success = False
        slot_acquired = False
        execution_path = f"router:{decision.executor_type.value}"
        try:
            requires_slot = decision.executor_type in {
                ExecutorType.CLAUDE_AGENT,
                ExecutorType.OPENAI_AGENT,
                ExecutorType.GOOGLE_AGENT,
                ExecutorType.PARALLEL,
            }
            if requires_slot:
                slot_acquired = self.tenant_quotas.acquire_subagent_slot(tenant_key)
                if not slot_acquired:
                    execution_path = "router:subagent_concurrency_blocked"
                    yield error_event(
                        job_id=job_id,
                        error="Limite de concorrência de subagentes atingido para este tenant.",
                        error_type="quota_subagent_concurrency_exceeded",
                        recoverable=True,
                    )
                    return

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
            execution_success = True

        except Exception as e:
            logger.exception(f"Erro na execução: {e}")
            yield error_event(
                job_id=job_id,
                error=str(e),
                error_type="execution_error",
                recoverable=False,
            )
        finally:
            if slot_acquired:
                self.tenant_quotas.release_subagent_slot(tenant_key)
            metrics.record_request(
                execution_path=execution_path,
                latency_ms=max(0.0, (time.monotonic() - started_at) * 1000.0),
                success=execution_success,
                cost_usd=float(context.get("estimated_cost_usd", 0.0) or 0.0),
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

        executor = None
        registered = False
        try:
            # Import dinâmico para evitar circular imports
            from app.services.ai.claude_agent.executor import ClaudeAgentExecutor, AgentConfig
            from app.services.ai.model_registry import get_api_model_name
            from app.services.ai.shared import ToolExecutionContext
            from app.services.agent_session_registry import agent_session_registry

            claude_agent_model = get_api_model_name(self.CLAUDE_AGENT_MODEL)
            if self._is_quick_profile(context):
                quick_iters = self._quick_max_iterations()
                quick_effort = (os.getenv("QUICK_AGENT_CLAUDE_EFFORT", "medium") or "medium").strip().lower()
                if quick_effort not in ("low", "medium", "high", "max"):
                    quick_effort = "medium"
                executor = ClaudeAgentExecutor(
                    config=AgentConfig(
                        model=claude_agent_model,
                        max_iterations=quick_iters,
                        enable_checkpoints=False,
                        code_execution_effort=quick_effort,
                    )
                )
            else:
                executor = ClaudeAgentExecutor(
                    config=AgentConfig(model=claude_agent_model)
                )

            # Load unified tools (search_jurisprudencia, search_rag, etc.)
            db_session = getattr(self, "db", None)
            tenant_id = context.user_id or "anonymous"
            if context.user_id and db_session:
                try:
                    from sqlalchemy import select
                    from app.models.user import User

                    res = await db_session.execute(
                        select(User.organization_id).where(User.id == context.user_id)
                    )
                    org_id = res.scalar_one_or_none()
                    if org_id:
                        tenant_id = str(org_id)
                except Exception as e:
                    logger.debug(f"[{job_id}] tenant_id resolve failed: {e}")

            tool_context = ToolExecutionContext(
                user_id=context.user_id or "anonymous",
                tenant_id=tenant_id,
                case_id=(
                    context.case_bundle.processo_id
                    if context.case_bundle and hasattr(context.case_bundle, "processo_id")
                    else None
                ),
                chat_id=context.chat_id,
                job_id=job_id,
                db_session=db_session,
                services={
                    # Used by tool handlers for policy/guards (e.g., block writes in graph UI mode).
                    "extra_instructions": context.extra_instructions or "",
                },
            )
            tool_names = build_tool_allowlist(
                user_prompt=context.prompt,
                extra_instructions=context.extra_instructions,
            )
            executor.load_unified_tools(
                include_mcp=True,
                execution_context=tool_context,
                tool_names=tool_names,
            )
            try:
                agent_session_registry.register(job_id, executor)
                registered = True
            except Exception as e:
                logger.debug(f"[{job_id}] agent_session_registry.register failed: {e}")

            # Build system prompt jurídico
            system_prompt = self._build_legal_system_prompt(context)

            # Build context string for the agent
            context_parts = []
            if context.rag_context:
                context_parts.append(f"## Contexto RAG\n{context.rag_context}")
            if context.template_structure:
                context_parts.append(f"## Estrutura de Template\n{context.template_structure}")
            if context.extra_instructions:
                context_parts.append(f"## Instruções Adicionais\n{context.extra_instructions}")
            context_str = "\n\n".join(context_parts) if context_parts else None

            # Executar agent (method is 'run', not 'execute')
            async for event in executor.run(
                prompt=context.prompt,
                system_prompt=system_prompt,
                job_id=job_id,
                context=context_str,
                initial_messages=(
                    [{"role": m["role"], "content": m["content"]}
                     for m in (context.conversation_history or [])
                     if isinstance(m, dict) and "role" in m and "content" in m]
                    or None
                ),
                user_id=context.user_id,
                case_id=(
                    context.case_bundle.processo_id
                    if context.case_bundle and hasattr(context.case_bundle, "processo_id")
                    else None
                ),
                session_id=context.chat_id,
                db=getattr(self, 'db', None),
                security_profile="server",
            ):
                yield event

            # If the agent finished, cleanup the registered session. If it paused
            # waiting for approval, keep it registered so /tool-approval can resume.
            if registered and executor is not None:
                try:
                    state = getattr(executor, "_state", None)
                    status = getattr(state, "status", None) if state is not None else None
                    status_val = getattr(status, "value", status)
                    if str(status_val) != "waiting_approval":
                        agent_session_registry.unregister(job_id)
                        registered = False
                except Exception:
                    try:
                        agent_session_registry.unregister(job_id)
                    except Exception:
                        pass

        except ImportError:
            logger.warning("ClaudeAgentExecutor não disponível. Usando fallback.")
            get_observability_metrics().record_fallback("sdk_to_raw", used_fallback=True)
            # Fallback para execução simples via agent_clients
            async for event in self._execute_claude_fallback(context):
                yield event

        except Exception as e:
            logger.exception(f"Erro no Claude Agent: {e}")
            if registered:
                try:
                    agent_session_registry.unregister(job_id)
                except Exception:
                    pass
            yield error_event(
                job_id=job_id,
                error=str(e),
                error_type="claude_agent_error",
                recoverable=True,
            )
        else:
            get_observability_metrics().record_fallback("sdk_to_raw", used_fallback=False)

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
                model=get_api_model_name(self.CLAUDE_AGENT_MODEL),
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
            from app.services.ai.model_registry import get_api_model_name
            from app.services.ai.shared import ToolExecutionContext

            if not OPENAI_AVAILABLE:
                raise ImportError("OpenAI SDK not available")

            # Criar contexto de execução para tools
            db_session = getattr(self, "db", None)
            tenant_id = context.user_id or "anonymous"
            if context.user_id and db_session:
                try:
                    from sqlalchemy import select
                    from app.models.user import User

                    res = await db_session.execute(
                        select(User.organization_id).where(User.id == context.user_id)
                    )
                    org_id = res.scalar_one_or_none()
                    if org_id:
                        tenant_id = str(org_id)
                except Exception as e:
                    logger.debug(f"[{job_id}] tenant_id resolve failed: {e}")

            tool_context = ToolExecutionContext(
                user_id=context.user_id or "anonymous",
                tenant_id=tenant_id,
                case_id=context.case_bundle.processo_id if context.case_bundle and hasattr(context.case_bundle, "processo_id") else None,
                chat_id=context.chat_id,
                job_id=job_id,
                db_session=db_session,
                services={
                    "extra_instructions": context.extra_instructions or "",
                },
            )

            # Configurar executor
            max_iterations = self._quick_max_iterations() if self._is_quick_profile(context) else 30
            config = OpenAIAgentConfig(
                model=get_api_model_name(self.OPENAI_AGENT_MODEL),
                temperature=context.temperature,
                max_tokens=context.max_tokens,
                max_iterations=max_iterations,
                enable_code_interpreter=True,
            )
            executor = OpenAIAgentExecutor(config=config)

            # Carregar tools unificadas
            tool_names = build_tool_allowlist(
                user_prompt=context.prompt,
                extra_instructions=context.extra_instructions,
            )
            executor.load_unified_tools(
                execution_context=tool_context,
                include_mcp=True,
                tool_names=tool_names,
            )

            # Build system prompt jurídico
            system_prompt = self._build_legal_system_prompt(context)
            full_prompt = self._build_full_prompt(context)

            # Executar agent
            async for event in executor.run(
                prompt=full_prompt,
                system_prompt=system_prompt,
                job_id=job_id,
                user_id=context.user_id,
                session_id=context.chat_id,
                project_id=(
                    context.case_bundle.processo_id
                    if context.case_bundle and hasattr(context.case_bundle, "processo_id")
                    else None
                ),
                db_session=getattr(self, "db", None),
                security_profile="server",
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
            get_observability_metrics().record_fallback("sdk_to_raw", used_fallback=True)
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
        else:
            get_observability_metrics().record_fallback("sdk_to_raw", used_fallback=False)

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
            from app.services.ai.model_registry import get_api_model_name

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
                model=get_api_model_name(self.OPENAI_AGENT_MODEL),
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
            from app.services.ai.model_registry import get_api_model_name
            from app.services.ai.shared import ToolExecutionContext

            if not GENAI_AVAILABLE and not VERTEX_AVAILABLE:
                raise ImportError("Google GenAI/Vertex SDK not available")

            # Criar contexto de execução para tools
            db_session = getattr(self, "db", None)
            tenant_id = context.user_id or "anonymous"
            if context.user_id and db_session:
                try:
                    from sqlalchemy import select
                    from app.models.user import User

                    res = await db_session.execute(
                        select(User.organization_id).where(User.id == context.user_id)
                    )
                    org_id = res.scalar_one_or_none()
                    if org_id:
                        tenant_id = str(org_id)
                except Exception as e:
                    logger.debug(f"[{job_id}] tenant_id resolve failed: {e}")

            tool_context = ToolExecutionContext(
                user_id=context.user_id or "anonymous",
                tenant_id=tenant_id,
                case_id=context.case_bundle.processo_id if context.case_bundle and hasattr(context.case_bundle, "processo_id") else None,
                chat_id=context.chat_id,
                job_id=job_id,
                db_session=db_session,
                services={
                    "extra_instructions": context.extra_instructions or "",
                },
            )

            # Configurar executor
            max_iterations = self._quick_max_iterations() if self._is_quick_profile(context) else 30
            config = GoogleAgentConfig(
                model=get_api_model_name(self.GOOGLE_AGENT_MODEL),
                temperature=context.temperature,
                max_tokens=context.max_tokens,
                max_iterations=max_iterations,
                use_vertex=VERTEX_AVAILABLE,
                use_adk=True,  # Preferir ADK se disponível
                enable_code_execution=True,
            )
            executor = GoogleAgentExecutor(config=config)

            # Carregar tools unificadas
            tool_names = build_tool_allowlist(
                user_prompt=context.prompt,
                extra_instructions=context.extra_instructions,
            )
            executor.load_unified_tools(
                execution_context=tool_context,
                include_mcp=True,
                tool_names=tool_names,
            )

            # Build system prompt jurídico
            system_prompt = self._build_legal_system_prompt(context)
            full_prompt = self._build_full_prompt(context)

            # Executar agent
            async for event in executor.run(
                prompt=full_prompt,
                system_prompt=system_prompt,
                job_id=job_id,
                user_id=context.user_id,
                session_id=context.chat_id,
                project_id=(
                    context.case_bundle.processo_id
                    if context.case_bundle and hasattr(context.case_bundle, "processo_id")
                    else None
                ),
                db_session=getattr(self, "db", None),
                security_profile="server",
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
            get_observability_metrics().record_fallback("sdk_to_raw", used_fallback=True)
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
        else:
            get_observability_metrics().record_fallback("sdk_to_raw", used_fallback=False)

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
            from app.services.ai.model_registry import get_api_model_name

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
                model=get_api_model_name(self.GOOGLE_AGENT_MODEL),
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
                "target_pages": int(context.target_pages or 0),
                "min_pages": int(context.min_pages or 0),
                "max_pages": int(context.max_pages or 0),
                "estimated_pages": int(context.estimated_pages or 0),
                "document_route": str(context.document_route or "default"),
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

        interaction_rules = """
REGRA DE INTERAÇÃO:
- Para mensagens casuais (oi, olá, bom dia, obrigado, tudo bem), responda brevemente e de forma natural
- NÃO gere templates, minutas ou peças jurídicas a menos que explicitamente solicitado
- Adapte a extensão da resposta à complexidade da pergunta
- Se a mensagem for uma saudação simples, cumprimente de volta e pergunte como pode ajudar
"""

        if personality == "geral":
            base_prompt = f"""Você é um assistente inteligente e versátil.
{interaction_rules}
ESTILO:
- Use linguagem clara e acessível
- Seja direto e objetivo
- Explique conceitos quando necessário
- Adapte o tom ao contexto da pergunta"""
        else:
            base_prompt = f"""Você é um especialista jurídico brasileiro altamente qualificado.
{interaction_rules}
FORMAÇÃO:
- Especialista em Direito Brasileiro
- Conhecimento profundo de legislação, jurisprudência e doutrina
- Experiência em redação de peças processuais

ESTILO:
- Use linguagem técnica e formal quando o assunto exigir
- Estruture argumentos de forma clara e lógica
- Cite fontes quando disponíveis
- Siga as normas da ABNT para referências

REGRAS DE CITAÇÃO:
- Cite leis no formato: Lei nº X.XXX/AAAA, art. XX
- Cite jurisprudência: Tribunal, Recurso nº, Relator, Data
- Use [n] para referenciar fontes da pesquisa web
- Marque afirmações sem fonte com [VERIFICAR]"""

            base_prompt += """

GRAFO JURÍDICO (ask_graph):
- Para consultar o grafo, use a tool ask_graph com operações tipadas (sem Cypher arbitrário).
- Para CRIAR arestas, use ask_graph(operation="link_entities") e NUNCA gere Cypher de escrita.
- Antes de linkar, resolva IDs com ask_graph(operation="search"). Não invente entity_id.
- Se search retornar múltiplos candidatos plausíveis, peça confirmação ao usuário antes de criar a aresta."""
            base_prompt += """

Seleção de operação (intenção -> operation):
- "vizinhos", "relacionados", "o que conecta a X": neighbors (ou related_entities se pedir relações reais do grafo)
- "caminho", "como conecta", "cadeia entre X e Y": path (ou audit_graph_chain se pedir auditoria/evidências)
- "comunidades", "clusters", "grupos": leiden (preferir) / community_detection
- "centralidade", "artigos mais centrais": degree_centrality (barato) ou eigenvector/pagerank; se pedir "ponte" use betweenness/bridges/articulation_points
- "similaridade", "parecidos com X": node_similarity (lista) ou knn; "score entre X e Y": adamic_adar

Guardrails de custo:
- Prefira operações básicas (search/neighbors/path/count) antes de GDS quando possível.
- Evite rodar mais de 1 algoritmo GDS pesado por turno sem o usuário pedir explicitamente.
- Se faltarem IDs, sempre comece com ask_graph(search) e confirme ambiguidades."""

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
