"""
Google Agent Executor - Executor baseado em Gemini/Vertex AI.

Implementa a mesma interface do Claude Agent, mas usando Google AI.
Usa as tools unificadas e sistema de permissões compartilhado.

Suporta:
- Gemini API (google.generativeai)
- Vertex AI (vertexai)
"""

import asyncio
import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional

from loguru import logger

from app.services.ai.tool_gateway.adapters import GeminiMCPAdapter
from app.services.ai.executors.base import (
    AgentProvider,
    BaseAgentExecutor,
    ExecutorConfig,
    ExecutorState,
    ExecutorStatus,
)
from app.services.ai.shared.sse_protocol import (
    SSEEvent,
    SSEEventType,
    ToolApprovalMode,
    create_sse_event,
    agent_iteration_event,
    tool_call_event,
    tool_result_event,
    tool_approval_required_event,
    context_warning_event,
    token_event,
    thinking_event,
    done_event,
    error_event,
    # Code Artifacts
    artifact_start_event,
    artifact_token_event,
    artifact_done_event,
)

# Google AI imports
try:
    import google.generativeai as genai
    from google.generativeai.types import (
        GenerationConfig,
        FunctionDeclaration,
        Tool,
    )
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False
    genai = None

# Vertex AI imports (para produção)
try:
    import vertexai
    from vertexai.generative_models import (
        GenerativeModel,
        Part,
        FunctionDeclaration as VertexFunctionDeclaration,
        Tool as VertexTool,
    )
    VERTEX_AVAILABLE = True
except ImportError:
    VERTEX_AVAILABLE = False
    vertexai = None

# Google ADK imports (Agent Development Kit)
# pip install google-adk
try:
    from google.adk import Agent as AdkAgent, Runner as AdkRunner
    from google.adk.tools import FunctionTool as AdkFunctionTool
    from google.adk.sessions import InMemorySessionService
    from google.adk.events import Event as AdkEvent
    ADK_AVAILABLE = True
except ImportError:
    ADK_AVAILABLE = False
    AdkAgent = None
    AdkRunner = None
    AdkFunctionTool = None
    InMemorySessionService = None
    AdkEvent = None


# =============================================================================
# CONFIGURATION
# =============================================================================

GOOGLE_AGENT_ENABLED = os.getenv("GOOGLE_AGENT_ENABLED", "true").lower() == "true"
GOOGLE_AGENT_DEFAULT_MODEL = os.getenv("GOOGLE_AGENT_DEFAULT_MODEL", "gemini-3-flash")
GOOGLE_AGENT_MAX_ITERATIONS = int(os.getenv("GOOGLE_AGENT_MAX_ITERATIONS", "50"))

# Use Vertex AI em produção
USE_VERTEX_AI = os.getenv("USE_VERTEX_AI", "false").lower() == "true"

# Modelos e context windows
MODEL_CONTEXT_WINDOWS = {
    # Gemini 3.x
    "gemini-3-pro": 2_000_000,
    "gemini-3-pro-preview": 2_000_000,
    "gemini-3-flash": 1_000_000,
    "gemini-3-flash-preview": 1_000_000,
    # Gemini 2.5
    "gemini-2.5-pro": 1_000_000,
    "gemini-2.5-flash": 1_000_000,
    # Gemini 2.x (legacy)
    "gemini-2.0-flash": 1_000_000,
    "gemini-2.0-flash-thinking": 1_000_000,
    "gemini-2.0-pro": 2_000_000,
    # Gemini 1.5 (legacy)
    "gemini-1.5-pro": 2_000_000,
    "gemini-1.5-flash": 1_000_000,
}


@dataclass
class GoogleAgentConfig(ExecutorConfig):
    """Configuração específica para Google Agent."""

    model: str = GOOGLE_AGENT_DEFAULT_MODEL
    max_iterations: int = GOOGLE_AGENT_MAX_ITERATIONS

    # Google specific
    use_vertex_ai: bool = USE_VERTEX_AI
    use_adk: bool = True  # Usar ADK se disponível
    project_id: Optional[str] = None
    location: str = "us-central1"

    # Thinking mode (para modelos que suportam)
    thinking_mode: Optional[str] = None  # "standard", "high"

    # Safety settings
    safety_settings: Optional[Dict[str, str]] = None

    # Hosted tools (Google managed)
    enable_code_execution: bool = True  # Gemini code execution sandbox

    # ADK specific
    agent_name: str = "iudex_legal_agent"

    def __post_init__(self):
        self.context_window = MODEL_CONTEXT_WINDOWS.get(
            self.model, 1_000_000
        )
        if self.use_vertex_ai and not self.project_id:
            self.project_id = os.getenv("GOOGLE_CLOUD_PROJECT")


# =============================================================================
# GOOGLE AGENT EXECUTOR
# =============================================================================

class GoogleAgentExecutor(BaseAgentExecutor):
    """
    Executor de agentes usando Google AI (Gemini).

    Suporta dois backends:
    1. Google AI (genai) - Para desenvolvimento
    2. Vertex AI - Para produção

    Ambos usam:
    - Tools unificadas
    - Sistema de permissões Ask/Allow/Deny
    - Checkpoints/rewind
    - Compactação de contexto
    """

    def __init__(
        self,
        config: Optional[GoogleAgentConfig] = None,
        tool_executor: Optional[Callable] = None,
        model: Optional[Any] = None,
    ):
        """
        Inicializa o Google Agent Executor.

        Args:
            config: Configuração do agente
            tool_executor: Executor customizado de tools
            model: Modelo pré-inicializado
        """
        super().__init__(config or GoogleAgentConfig(), tool_executor)

        self.config: GoogleAgentConfig = self.config
        self._model = model
        self._chat = None

        # Tool Gateway adapter
        self._mcp_adapter: Optional[GeminiMCPAdapter] = None
        self._execution_context: Optional[Dict[str, Any]] = None

        if not model:
            self._init_model()

    @property
    def provider(self) -> AgentProvider:
        return AgentProvider.GOOGLE

    def _init_model(self):
        """Inicializa o modelo Gemini."""
        if self.config.use_vertex_ai:
            self._init_vertex_model()
        else:
            self._init_genai_model()

    def _init_genai_model(self):
        """Inicializa usando Google AI (genai)."""
        if not GENAI_AVAILABLE:
            logger.warning("google-generativeai not installed. pip install google-generativeai")
            return

        api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if not api_key:
            logger.warning("GOOGLE_API_KEY/GEMINI_API_KEY not set. Google Agent disabled.")
            return

        try:
            genai.configure(api_key=api_key)

            generation_config = GenerationConfig(
                temperature=self.config.temperature,
                max_output_tokens=self.config.max_tokens,
            )

            self._model = genai.GenerativeModel(
                model_name=self.config.model,
                generation_config=generation_config,
                safety_settings=self.config.safety_settings,
            )

            logger.info(f"Initialized Gemini model: {self.config.model}")

        except Exception as e:
            logger.error(f"Failed to initialize Gemini model: {e}")

    def _init_vertex_model(self):
        """Inicializa usando Vertex AI."""
        if not VERTEX_AVAILABLE:
            logger.warning("vertexai not installed. pip install google-cloud-aiplatform")
            return

        try:
            vertexai.init(
                project=self.config.project_id,
                location=self.config.location,
            )

            self._model = GenerativeModel(
                model_name=self.config.model,
            )

            logger.info(f"Initialized Vertex AI model: {self.config.model}")

        except Exception as e:
            logger.error(f"Failed to initialize Vertex AI model: {e}")

    def _get_tools_for_provider(
        self,
        tool_names: Optional[List[str]] = None,
        include_mcp: bool = True,
    ) -> List[Dict[str, Any]]:
        """Retorna tools no formato Google/Gemini."""
        # Gemini usa um formato similar ao OpenAI
        from app.services.ai.shared import get_tools_for_openai
        openai_tools = get_tools_for_openai(
            tool_names=tool_names,
            include_mcp=include_mcp,
        )

        # Converter para formato Gemini
        gemini_tools = []
        for tool in openai_tools:
            func = tool.get("function", {})
            gemini_tools.append({
                "name": func.get("name", ""),
                "description": func.get("description", ""),
                "parameters": func.get("parameters", {}),
            })

        return gemini_tools

    def _extract_tool_name(self, tool_def: Dict[str, Any]) -> str:
        """Extrai nome da tool do formato Gemini."""
        return tool_def.get("name", "")

    # =========================================================================
    # TOOL GATEWAY INTEGRATION
    # =========================================================================

    def _get_context(self) -> Dict[str, Any]:
        """Get current execution context for Tool Gateway."""
        context = self._execution_context.copy() if self._execution_context else {}
        if self._state:
            context.update({
                "job_id": self._state.job_id,
                "iteration": self._state.iteration,
            })
        return context

    def _init_mcp_adapter(self, context: Optional[Dict[str, Any]] = None) -> None:
        """Initialize MCP adapter with context."""
        self._execution_context = context or {}
        self._mcp_adapter = GeminiMCPAdapter(context=self._execution_context)

    async def load_tools_from_gateway(
        self,
        context: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Load tools from Tool Gateway via MCP adapter.

        This is the recommended way to load tools as it goes through
        the centralized Tool Gateway with policy enforcement.

        Args:
            context: Execution context (user_id, tenant_id, case_id, etc.)

        Returns:
            List of tools in Gemini function declaration format
        """
        self._init_mcp_adapter(context)
        tools = await self._mcp_adapter.get_tools()

        # Register tools internally
        for tool_def in tools:
            self._tools.append(tool_def)
            name = self._extract_tool_name(tool_def)

            # Create executor that routes through MCP adapter
            def create_mcp_executor(tool_name: str, adapter: GeminiMCPAdapter):
                async def executor(**kwargs):
                    result = await adapter.execute_tool(
                        tool_name,
                        kwargs,
                        self._get_context()
                    )
                    return result
                return executor

            self._tool_registry[name] = create_mcp_executor(name, self._mcp_adapter)

        logger.info(f"[Google Agent] Loaded {len(tools)} tools from Tool Gateway")
        return tools

    def get_genai_tools_from_gateway(self) -> List[Any]:
        """
        Get tools as google.genai.types.Tool objects via Gateway.

        For direct use with Gemini SDK.
        """
        if not self._mcp_adapter:
            self._init_mcp_adapter()

        return self._mcp_adapter.get_genai_tools()

    async def execute_function_calls_via_gateway(
        self,
        function_calls: List[Any],
    ) -> List[Any]:
        """
        Execute function calls via the Tool Gateway.

        Args:
            function_calls: List of Gemini FunctionCall objects

        Returns:
            List of FunctionResponse Parts for Gemini
        """
        if not self._mcp_adapter:
            self._init_mcp_adapter()

        return await self._mcp_adapter.handle_function_calls(
            function_calls,
            self._get_context()
        )

    def _convert_tools_to_gemini_format(self) -> Optional[List[Any]]:
        """Converte tools para formato nativo do Gemini."""
        if not GENAI_AVAILABLE:
            return None

        tools_list = []

        # Function declarations (tools unificadas)
        if self._tools:
            try:
                function_declarations = []
                for tool_def in self._tools:
                    fd = FunctionDeclaration(
                        name=tool_def["name"],
                        description=tool_def.get("description", ""),
                        parameters=tool_def.get("parameters", {}),
                    )
                    function_declarations.append(fd)

                tools_list.append(Tool(function_declarations=function_declarations))

            except Exception as e:
                logger.warning(f"Could not convert tools to Gemini format: {e}")

        # Code execution (hosted tool do Gemini — not supported by flash-lite models)
        _ce_compatible = not any(
            self.config.model.startswith(p)
            for p in ("gemini-2.0-flash-lite", "gemini-2-flash-lite")
        )
        if self.config.enable_code_execution and _ce_compatible:
            try:
                # Try ToolCodeExecution class (new SDK), then dict fallback (old SDK)
                _tce = getattr(genai.types if hasattr(genai, 'types') else genai, 'ToolCodeExecution', None)
                if _tce is not None:
                    tools_list.append(Tool(code_execution=_tce))
                else:
                    tools_list.append(Tool(code_execution={}))
                logger.debug("Code execution tool enabled for Gemini")
            except Exception as e:
                logger.warning(f"Could not enable code_execution tool: {e}")

        return tools_list if tools_list else None

    async def run(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        context: Optional[str] = None,
        job_id: Optional[str] = None,
        **kwargs,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Executa o agente Google/Gemini.

        Args:
            prompt: Prompt do usuário
            system_prompt: System prompt
            context: Contexto adicional
            job_id: ID do job
            **kwargs: Argumentos adicionais

        Yields:
            Eventos SSE
        """
        if not self._model:
            yield error_event(
                job_id or "",
                "Gemini model not initialized",
                "initialization_error"
            ).to_sse_dict()
            return

        # Inicializar estado
        job_id = job_id or str(uuid.uuid4())
        self._state = ExecutorState(
            job_id=job_id,
            status=ExecutorStatus.RUNNING,
            start_time=datetime.now(timezone.utc),
        )
        self._cancel_requested = False
        await self._init_permission_manager(
            db_session=kwargs.get("db_session") or kwargs.get("db"),
            user_id=kwargs.get("user_id"),
            session_id=kwargs.get("session_id") or kwargs.get("chat_id"),
            project_id=kwargs.get("project_id") or kwargs.get("case_id"),
            security_profile=kwargs.get("security_profile"),
        )

        # Construir system prompt
        full_system = self._build_system_prompt(system_prompt, context)

        # Inicializar chat
        tools = self._convert_tools_to_gemini_format()

        try:
            # Decidir qual modo usar: ADK vs Chat
            if self.config.use_adk and ADK_AVAILABLE and self._tools:
                async for event in self._run_with_adk(prompt, full_system, job_id):
                    yield event
            else:
                if tools:
                    self._chat = self._model.start_chat(
                        history=[],
                    )
                else:
                    self._chat = self._model.start_chat(history=[])

                # Combinar system + user prompt
                full_prompt = f"{full_system}\n\n---\n\nUser: {prompt}"

                async for event in self._run_agent_loop(full_prompt, job_id, tools):
                    yield event

        except Exception as e:
            logger.exception(f"Google agent error: {e}")
            self._state.status = ExecutorStatus.ERROR
            self._state.error = str(e)
            yield error_event(job_id, str(e), "execution_error").to_sse_dict()

        finally:
            self._state.end_time = datetime.now(timezone.utc)
            if self._state.status == ExecutorStatus.RUNNING:
                self._state.status = ExecutorStatus.COMPLETED

    async def _run_with_adk(
        self,
        prompt: str,
        system_prompt: str,
        job_id: str,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Executa usando Google ADK (Agent Development Kit).

        O ADK oferece:
        - Orquestração nativa de agentes com Runner
        - Suporte a sessões e memória
        - Tools como funções Python decoradas
        - Streaming de eventos

        Ref: https://google.github.io/adk-docs/
        """
        if not ADK_AVAILABLE:
            logger.warning("ADK not available, falling back to chat")
            return

        logger.info(f"[Google Agent] Running with ADK for job {job_id}")

        # Criar funções Python para cada tool
        adk_tools = self._create_adk_tools()

        try:
            # Criar agente ADK
            # O Agent (LlmAgent) é o componente principal
            agent = AdkAgent(
                name=self.config.agent_name or "IudexLegalAgent",
                model=self.config.model,  # ex: "gemini-2.0-flash-exp"
                instruction=system_prompt,
                tools=adk_tools,
            )

            # Criar session service em memória
            session_service = InMemorySessionService()

            # Criar Runner para executar o agente
            runner = AdkRunner(
                agent=agent,
                session_service=session_service,
                app_name="iudex",
            )

            # User e session IDs
            user_id = self._state.metadata.get("user_id", "default_user")
            session_id = f"session_{job_id}"

            # Criar sessão
            session = await session_service.create_session(
                app_name="iudex",
                user_id=user_id,
                session_id=session_id,
            )

            iteration = 0

            # Executar agente e processar eventos via streaming
            async with runner:
                # O Runner.run_async retorna um async generator de eventos
                from google.genai import types as genai_types

                # Criar mensagem do usuário
                user_content = genai_types.Content(
                    parts=[genai_types.Part(text=prompt)],
                    role="user",
                )

                async for event in runner.run_async(
                    user_id=user_id,
                    session_id=session_id,
                    new_message=user_content,
                ):
                    if self._cancel_requested:
                        yield done_event(job_id, "cancelled", {}).to_sse_dict()
                        return

                    # Processar eventos do ADK
                    # Os eventos podem ser de diferentes tipos baseados na classe
                    event_author = getattr(event, 'author', None)
                    event_content = getattr(event, 'content', None)

                    # Verificar se é evento de tool
                    if hasattr(event, 'actions') and event.actions:
                        for action in event.actions:
                            if hasattr(action, 'function_calls'):
                                for fc in action.function_calls:
                                    iteration += 1
                                    self._state.iteration = iteration

                                    tool_name = fc.name if hasattr(fc, 'name') else str(fc)
                                    tool_input = fc.args if hasattr(fc, 'args') else {}

                                    yield tool_call_event(
                                        job_id,
                                        f"adk_{iteration}_{tool_name}",
                                        tool_name,
                                        tool_input
                                    ).to_sse_dict()

                                    # Verificar permissão
                                    permission = await self._check_permission(tool_name, tool_input)

                                    if permission == "ask":
                                        self._state.status = ExecutorStatus.WAITING_APPROVAL
                                        self._state.pending_approvals.append({
                                            "tool_call_id": f"adk_{iteration}_{tool_name}",
                                            "tool_name": tool_name,
                                            "tool_input": tool_input,
                                        })
                                        yield tool_approval_required_event(
                                            job_id,
                                            f"adk_{iteration}_{tool_name}",
                                            tool_name,
                                            tool_input,
                                            self._get_tool_risk_level(tool_name)
                                        ).to_sse_dict()
                                        yield done_event(job_id, "waiting_approval", {}).to_sse_dict()
                                        return

                    # Verificar resposta de tool
                    if hasattr(event, 'function_responses'):
                        for fr in event.function_responses:
                            tool_name = fr.name if hasattr(fr, 'name') else "unknown"
                            result = fr.response if hasattr(fr, 'response') else {}
                            success = 'error' not in str(result).lower()

                            self._state.tools_called.append({
                                "name": tool_name,
                                "result": result,
                                "success": success,
                            })

                            yield tool_result_event(
                                job_id,
                                f"adk_{iteration}_{tool_name}",
                                tool_name,
                                result,
                                success
                            ).to_sse_dict()

                    # Verificar conteúdo de texto e code execution
                    if event_content:
                        if hasattr(event_content, 'parts'):
                            for part in event_content.parts:
                                if hasattr(part, 'executable_code') and part.executable_code:
                                    code = part.executable_code
                                    lang = getattr(code, 'language', 'PYTHON')
                                    code_text = getattr(code, 'code', str(code))
                                    yield {
                                        "type": "code_execution",
                                        "data": {
                                            "language": str(lang),
                                            "code": code_text,
                                        }
                                    }
                                elif hasattr(part, 'code_execution_result') and part.code_execution_result:
                                    exec_result = part.code_execution_result
                                    outcome = getattr(exec_result, 'outcome', 'UNKNOWN')
                                    output = getattr(exec_result, 'output', '')
                                    yield {
                                        "type": "code_execution_result",
                                        "data": {
                                            "outcome": str(outcome),
                                            "output": output,
                                        }
                                    }
                                elif hasattr(part, 'text') and part.text:
                                    text = part.text
                                    yield {
                                        "type": "token",
                                        "data": {"token": text}
                                    }
                                    self._state.final_output += text

                    # Verificar se é evento final
                    if hasattr(event, 'is_final') and event.is_final:
                        self._state.status = ExecutorStatus.COMPLETED
                        yield done_event(
                            job_id,
                            "completed",
                            {
                                "output": self._state.final_output,
                                "iterations": iteration,
                                "tools_called": len(self._state.tools_called),
                                "mode": "adk",
                            }
                        ).to_sse_dict()
                        return

            # Se chegou aqui sem evento final, finalizar
            if self._state.status != ExecutorStatus.COMPLETED:
                self._state.status = ExecutorStatus.COMPLETED
                yield done_event(
                    job_id,
                    "completed",
                    {
                        "output": self._state.final_output,
                        "iterations": iteration,
                        "tools_called": len(self._state.tools_called),
                        "mode": "adk",
                    }
                ).to_sse_dict()

        except Exception as e:
            logger.exception(f"ADK execution error: {e}")
            # Fallback para modo chat se ADK falhar
            logger.info("Falling back to chat mode due to ADK error")
            tools = self._convert_tools_to_gemini_format()
            full_prompt = f"{system_prompt}\n\n---\n\nUser: {prompt}"
            async for event in self._run_agent_loop(full_prompt, job_id, tools):
                yield event

    def _create_adk_tools(self) -> List[Callable]:
        """
        Cria funções Python para uso com ADK.

        O ADK aceita funções Python (sync ou async) com docstrings
        bem definidas como tools. O ADK detecta automaticamente
        o schema a partir da assinatura e docstring.

        Ref: https://google.github.io/adk-docs/tools/
        """
        adk_tools = []

        for tool_name, handler in self._tool_registry.items():
            # Obter definição da tool
            tool_def = None
            for t in self._tools:
                if t.get("name") == tool_name:
                    tool_def = t
                    break

            if not tool_def:
                continue

            # Criar wrapper com docstring adequada
            description = tool_def.get("description", f"Tool: {tool_name}")

            # Criar closure para capturar variáveis corretamente
            def make_tool_wrapper(name: str, desc: str, h: Callable):
                """Cria wrapper para a tool."""
                async def tool_wrapper(**kwargs) -> dict:
                    """Wrapper que executa a tool com tratamento de erros."""
                    try:
                        # Verificar permissão antes de executar
                        permission = await self._check_permission(name, kwargs)

                        if permission == "deny":
                            return {"error": f"Tool '{name}' denied by policy"}

                        # Executar handler
                        if asyncio.iscoroutinefunction(h):
                            result = await h(**kwargs)
                        else:
                            result = h(**kwargs)

                        return result if isinstance(result, dict) else {"result": result}

                    except Exception as e:
                        logger.error(f"ADK tool error for {name}: {e}")
                        return {"error": str(e)}

                # Configurar metadata da função
                tool_wrapper.__doc__ = desc
                tool_wrapper.__name__ = name
                # Preservar qualname para debug
                tool_wrapper.__qualname__ = f"adk_tool_{name}"

                return tool_wrapper

            # Criar e adicionar wrapper
            wrapper = make_tool_wrapper(tool_name, description, handler)
            adk_tools.append(wrapper)

        logger.info(f"[ADK] Created {len(adk_tools)} tool wrappers")
        return adk_tools

    async def _run_agent_loop(
        self,
        prompt: str,
        job_id: str,
        tools: Optional[List[Any]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Loop principal do agente.

        Args:
            prompt: Prompt inicial
            job_id: ID do job
            tools: Tools no formato Gemini

        Yields:
            Eventos SSE
        """
        iteration = 0
        current_prompt = prompt

        while iteration < self.config.max_iterations:
            if self._cancel_requested:
                yield done_event(job_id, "cancelled", {"reason": "user_cancelled"}).to_sse_dict()
                return

            iteration += 1
            self._state.iteration = iteration

            yield agent_iteration_event(
                job_id,
                iteration,
                self.config.max_iterations
            ).to_sse_dict()

            # Verificar contexto
            if await self._check_context_usage():
                yield context_warning_event(
                    job_id,
                    self._state.get_context_usage(self.config.context_window),
                    self.config.context_window
                ).to_sse_dict()

            # Chamar Gemini
            try:
                if tools:
                    response = await asyncio.to_thread(
                        self._chat.send_message,
                        current_prompt,
                        tools=tools,
                    )
                else:
                    response = await asyncio.to_thread(
                        self._chat.send_message,
                        current_prompt,
                    )
            except Exception as e:
                yield error_event(job_id, str(e), "api_error").to_sse_dict()
                return

            # Atualizar tokens (estimativa)
            if hasattr(response, 'usage_metadata'):
                self._state.total_input_tokens += getattr(
                    response.usage_metadata, 'prompt_token_count', 0
                )
                self._state.total_output_tokens += getattr(
                    response.usage_metadata, 'candidates_token_count', 0
                )

            # Processar resposta
            candidate = response.candidates[0] if response.candidates else None
            if not candidate:
                yield error_event(job_id, "No response candidate", "empty_response").to_sse_dict()
                return

            # Verificar function calls e code execution
            function_calls = []
            text_parts = []

            for part in candidate.content.parts:
                if hasattr(part, 'function_call') and part.function_call:
                    function_calls.append(part.function_call)
                elif hasattr(part, 'executable_code') and part.executable_code:
                    # Gemini code_execution: modelo gerou código para executar
                    code = part.executable_code
                    lang = getattr(code, 'language', 'PYTHON')
                    code_text = getattr(code, 'code', str(code))
                    yield {
                        "type": "code_execution",
                        "data": {
                            "language": str(lang),
                            "code": code_text,
                        }
                    }
                elif hasattr(part, 'code_execution_result') and part.code_execution_result:
                    # Gemini code_execution: resultado da execução
                    exec_result = part.code_execution_result
                    outcome = getattr(exec_result, 'outcome', 'UNKNOWN')
                    output = getattr(exec_result, 'output', '')
                    yield {
                        "type": "code_execution_result",
                        "data": {
                            "outcome": str(outcome),
                            "output": output,
                        }
                    }
                elif hasattr(part, 'text') and part.text:
                    text_parts.append(part.text)

            if function_calls:
                # Processar function calls
                function_responses = []

                for fc in function_calls:
                    tool_name = fc.name
                    tool_input = dict(fc.args) if fc.args else {}

                    yield tool_call_event(
                        job_id,
                        f"fc_{iteration}_{tool_name}",
                        tool_name,
                        tool_input
                    ).to_sse_dict()

                    # Verificar permissão
                    permission = await self._check_permission(tool_name, tool_input)

                    if permission == "deny":
                        result = {"error": "Tool execution denied by policy"}
                        yield tool_result_event(
                            job_id, f"fc_{iteration}_{tool_name}",
                            tool_name, result, False
                        ).to_sse_dict()
                        function_responses.append({
                            "name": tool_name,
                            "response": result,
                        })

                    elif permission == "ask":
                        self._state.status = ExecutorStatus.WAITING_APPROVAL
                        self._state.pending_approvals.append({
                            "tool_call_id": f"fc_{iteration}_{tool_name}",
                            "tool_name": tool_name,
                            "tool_input": tool_input,
                        })
                        yield tool_approval_required_event(
                            job_id,
                            f"fc_{iteration}_{tool_name}",
                            tool_name,
                            tool_input,
                            self._get_tool_risk_level(tool_name)
                        ).to_sse_dict()
                        yield done_event(
                            job_id,
                            "waiting_approval",
                            {"pending_tools": [tool_name]}
                        ).to_sse_dict()
                        return

                    else:  # allow
                        result = await self._execute_tool(tool_name, tool_input)
                        success = "error" not in result

                        self._state.tools_called.append({
                            "id": f"fc_{iteration}_{tool_name}",
                            "name": tool_name,
                            "input": tool_input,
                            "result": result,
                            "success": success,
                        })

                        yield tool_result_event(
                            job_id, f"fc_{iteration}_{tool_name}",
                            tool_name, result, success
                        ).to_sse_dict()

                        function_responses.append({
                            "name": tool_name,
                            "response": result,
                        })

                # Enviar resultados de volta ao modelo
                current_prompt = json.dumps(function_responses)

                # Criar checkpoint
                await self._create_checkpoint(f"After tools in iteration {iteration}")

            else:
                # Sem function calls - resposta final
                content = "\n".join(text_parts)

                if content:
                    yield thinking_event(job_id, content).to_sse_dict()

                self._state.final_output = content
                self._state.status = ExecutorStatus.COMPLETED

                yield done_event(
                    job_id,
                    "completed",
                    {
                        "output": content,
                        "iterations": iteration,
                        "tools_called": len(self._state.tools_called),
                    }
                ).to_sse_dict()
                return

        # Limite de iterações
        self._state.status = ExecutorStatus.ERROR
        self._state.error = "Max iterations reached"
        yield error_event(
            job_id,
            "Maximum iterations reached",
            "iteration_limit"
        ).to_sse_dict()

    async def resume(
        self,
        job_id: str,
        tool_results: Optional[List[Dict[str, Any]]] = None,
        **kwargs,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Resume execução após aprovação de tools.

        Args:
            job_id: ID do job
            tool_results: Resultados das tools aprovadas

        Yields:
            Eventos SSE
        """
        if not self._state or self._state.job_id != job_id:
            yield error_event(
                job_id,
                "No state found for job",
                "state_not_found"
            ).to_sse_dict()
            return

        if self._state.status != ExecutorStatus.WAITING_APPROVAL:
            yield error_event(
                job_id,
                f"Cannot resume from status: {self._state.status}",
                "invalid_status"
            ).to_sse_dict()
            return

        # Processar resultados aprovados
        function_responses = []

        for pending in self._state.pending_approvals:
            tool_name = pending["tool_name"]
            tool_input = pending["tool_input"]

            approved = False
            if tool_results:
                for tr in tool_results:
                    if tr.get("tool_call_id") == pending["tool_call_id"]:
                        approved = tr.get("approved", False)
                        break

            if approved:
                result = await self._execute_tool(tool_name, tool_input)
                success = "error" not in result

                self._state.tools_called.append({
                    "id": pending["tool_call_id"],
                    "name": tool_name,
                    "input": tool_input,
                    "result": result,
                    "success": success,
                })

                yield tool_result_event(
                    job_id, pending["tool_call_id"],
                    tool_name, result, success
                ).to_sse_dict()

                function_responses.append({
                    "name": tool_name,
                    "response": result,
                })
            else:
                function_responses.append({
                    "name": tool_name,
                    "response": {"error": "Tool execution denied by user"},
                })

        # Limpar pendências
        self._state.pending_approvals = []
        self._state.status = ExecutorStatus.RUNNING

        # Continuar loop
        current_prompt = json.dumps(function_responses)
        tools = self._convert_tools_to_gemini_format()

        async for event in self._run_agent_loop(current_prompt, job_id, tools):
            yield event

    def _build_system_prompt(
        self,
        base_prompt: Optional[str],
        context: Optional[str],
    ) -> str:
        """Constrói system prompt completo."""
        parts = []

        if base_prompt:
            parts.append(base_prompt)
        else:
            parts.append(
                "Você é um assistente jurídico especializado brasileiro. "
                "Use as ferramentas disponíveis para pesquisar informações, "
                "analisar documentos e auxiliar na elaboração de peças jurídicas. "
                "Sempre cite fontes quando usar jurisprudência ou legislação."
            )

        if context:
            parts.append(f"\n\n## CONTEXTO DISPONÍVEL\n\n{context}")

        return "\n\n".join(parts)

    def _get_tool_risk_level(self, tool_name: str) -> str:
        """Retorna nível de risco da tool."""
        try:
            from app.services.ai.shared import get_tool_risk_level
            return get_tool_risk_level(tool_name).value
        except ImportError:
            return "medium"
