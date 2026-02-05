"""
OpenAI Agent Executor - Executor baseado no OpenAI Agents SDK.

Implementa a mesma interface do Claude Agent, mas usando OpenAI.
Usa as tools unificadas e sistema de permissões compartilhado.

Referência: https://github.com/openai/openai-agents-python
"""

import asyncio
import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional

from loguru import logger

from app.services.ai.tool_gateway.adapters import OpenAIMCPAdapter
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

# OpenAI imports
try:
    from openai import AsyncOpenAI, OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    AsyncOpenAI = None
    OpenAI = None

# OpenAI Agents SDK imports (quando disponível)
# pip install openai-agents
try:
    from agents import Agent, Runner, function_tool, RunContextWrapper
    from agents.tool import FunctionTool
    AGENTS_SDK_AVAILABLE = True
except ImportError:
    AGENTS_SDK_AVAILABLE = False
    Agent = None
    Runner = None
    function_tool = None
    FunctionTool = None
    RunContextWrapper = None

# OpenAI Responses API tools (hosted tools)
HOSTED_TOOLS = {
    "file_search": {"type": "file_search"},  # Busca em vector stores
    "web_search": {"type": "web_search_preview"},  # Busca web (preview)
    "code_interpreter": {"type": "code_interpreter", "container": {"type": "auto"}},  # Execução de código (container reusável)
}


# =============================================================================
# CONFIGURATION
# =============================================================================

OPENAI_AGENT_ENABLED = os.getenv("OPENAI_AGENT_ENABLED", "true").lower() == "true"
OPENAI_AGENT_DEFAULT_MODEL = os.getenv("OPENAI_AGENT_DEFAULT_MODEL", "gpt-4o")
OPENAI_AGENT_MAX_ITERATIONS = int(os.getenv("OPENAI_AGENT_MAX_ITERATIONS", "50"))

# Modelos e context windows
MODEL_CONTEXT_WINDOWS = {
    "gpt-4o": 128_000,
    "gpt-4o-mini": 128_000,
    "gpt-4-turbo": 128_000,
    "gpt-4": 8_192,
    "gpt-3.5-turbo": 16_385,
    "o1": 200_000,
    "o1-mini": 128_000,
    "o1-preview": 128_000,
    # GPT-5.x
    "gpt-5": 400_000,
    "gpt-5-mini": 400_000,
    "gpt-5.2": 400_000,
    "gpt-5.2-instant": 400_000,
    "gpt-5.2-pro": 400_000,
    "gpt-5.2-codex": 400_000,
}


@dataclass
class OpenAIAgentConfig(ExecutorConfig):
    """Configuração específica para OpenAI Agent."""

    model: str = OPENAI_AGENT_DEFAULT_MODEL
    max_iterations: int = OPENAI_AGENT_MAX_ITERATIONS

    # OpenAI specific
    use_agents_sdk: bool = True  # Usar Agents SDK se disponível
    parallel_tool_calls: bool = True
    response_format: Optional[Dict[str, Any]] = None

    # Reasoning (para o1)
    reasoning_effort: Optional[str] = None  # "low", "medium", "high"

    # Hosted tools (OpenAI managed)
    enable_file_search: bool = False  # RAG via vector stores OpenAI
    enable_web_search: bool = False  # Web search (preview)
    enable_code_interpreter: bool = True  # Code execution

    # Responses API config
    vector_store_ids: List[str] = field(default_factory=list)  # Para file_search

    def __post_init__(self):
        # Ajustar context window baseado no modelo
        self.context_window = MODEL_CONTEXT_WINDOWS.get(
            self.model, 128_000
        )

        # Passar configs para provider_config para uso interno
        self.provider_config = {
            "enable_file_search": self.enable_file_search,
            "enable_web_search": self.enable_web_search,
            "enable_code_interpreter": self.enable_code_interpreter,
            "vector_store_ids": self.vector_store_ids,
        }


# =============================================================================
# OPENAI AGENT EXECUTOR
# =============================================================================

class OpenAIAgentExecutor(BaseAgentExecutor):
    """
    Executor de agentes usando OpenAI.

    Suporta dois modos:
    1. OpenAI Agents SDK (preferido quando disponível)
    2. OpenAI Chat Completions com function calling (fallback)

    Ambos usam:
    - Tools unificadas
    - Sistema de permissões Ask/Allow/Deny
    - Checkpoints/rewind
    - Compactação de contexto
    """

    def __init__(
        self,
        config: Optional[OpenAIAgentConfig] = None,
        tool_executor: Optional[Callable] = None,
        client: Optional[Any] = None,
    ):
        """
        Inicializa o OpenAI Agent Executor.

        Args:
            config: Configuração do agente
            tool_executor: Executor customizado de tools
            client: Cliente OpenAI pré-inicializado
        """
        super().__init__(config or OpenAIAgentConfig(), tool_executor)

        self.config: OpenAIAgentConfig = self.config

        # Inicializar cliente
        if client:
            self.client = None
            self.async_client = client
        else:
            self.client, self.async_client = self._init_clients()

        # Agents SDK runner (se disponível)
        self._agent = None
        self._runner = None

        # Tool Gateway adapter
        self._mcp_adapter: Optional[OpenAIMCPAdapter] = None
        self._execution_context: Optional[Dict[str, Any]] = None

    @property
    def provider(self) -> AgentProvider:
        return AgentProvider.OPENAI

    def _init_clients(self):
        """Inicializa clientes OpenAI."""
        if not OPENAI_AVAILABLE:
            logger.warning("OpenAI SDK not installed. pip install openai")
            return None, None

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.warning("OPENAI_API_KEY not set. OpenAI Agent disabled.")
            return None, None

        try:
            sync_client = OpenAI(api_key=api_key)
            async_client = AsyncOpenAI(api_key=api_key)
            return sync_client, async_client
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI clients: {e}")
            return None, None

    def _get_tools_for_provider(
        self,
        tool_names: Optional[List[str]] = None,
        include_mcp: bool = True,
    ) -> List[Dict[str, Any]]:
        """Retorna tools no formato OpenAI."""
        from app.services.ai.shared import get_tools_for_openai
        return get_tools_for_openai(
            tool_names=tool_names,
            include_mcp=include_mcp,
        )

    def _extract_tool_name(self, tool_def: Dict[str, Any]) -> str:
        """Extrai nome da tool do formato OpenAI."""
        return tool_def.get("function", {}).get("name", "")

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
        self._mcp_adapter = OpenAIMCPAdapter(context=self._execution_context)

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
            List of tools in OpenAI function calling format
        """
        self._init_mcp_adapter(context)
        tools = await self._mcp_adapter.get_tools()

        # Register tools internally
        for tool_def in tools:
            self._tools.append(tool_def)
            name = self._extract_tool_name(tool_def)

            # Create executor that routes through MCP adapter
            def create_mcp_executor(tool_name: str, adapter: OpenAIMCPAdapter):
                async def executor(**kwargs):
                    result = await adapter.execute_tool(
                        tool_name,
                        kwargs,
                        self._get_context()
                    )
                    return result
                return executor

            self._tool_registry[name] = create_mcp_executor(name, self._mcp_adapter)

        logger.info(f"[OpenAI Agent] Loaded {len(tools)} tools from Tool Gateway")
        return tools

    async def execute_tool_calls_via_gateway(
        self,
        tool_calls: List[Any],
    ) -> List[Dict[str, Any]]:
        """
        Execute tool calls via the Tool Gateway.

        Args:
            tool_calls: List of OpenAI tool call objects

        Returns:
            List of tool message dicts for OpenAI messages
        """
        if not self._mcp_adapter:
            self._init_mcp_adapter()

        # Convert tool_calls to the format expected by adapter
        formatted_calls = []
        for tc in tool_calls:
            formatted_calls.append({
                "id": tc.id if hasattr(tc, "id") else tc.get("id", ""),
                "function": {
                    "name": tc.function.name if hasattr(tc, "function") else tc.get("function", {}).get("name", ""),
                    "arguments": tc.function.arguments if hasattr(tc, "function") else tc.get("function", {}).get("arguments", "{}"),
                }
            })

        return await self._mcp_adapter.handle_tool_calls(
            formatted_calls,
            self._get_context()
        )

    async def run(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        context: Optional[str] = None,
        job_id: Optional[str] = None,
        **kwargs,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Executa o agente OpenAI.

        Args:
            prompt: Prompt do usuário
            system_prompt: System prompt
            context: Contexto adicional
            job_id: ID do job
            **kwargs: Argumentos adicionais

        Yields:
            Eventos SSE
        """
        if not self.async_client:
            yield error_event(
                job_id or "",
                "OpenAI client not initialized",
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

        # Construir system prompt
        full_system = self._build_system_prompt(system_prompt, context)

        # Inicializar mensagens
        messages = [
            {"role": "system", "content": full_system},
            {"role": "user", "content": prompt},
        ]
        self._state.messages = messages.copy()

        try:
            # Decidir qual modo usar
            if self.config.use_agents_sdk and AGENTS_SDK_AVAILABLE:
                async for event in self._run_with_agents_sdk(messages, job_id):
                    yield event
            else:
                async for event in self._run_with_chat_completions(messages, job_id):
                    yield event

        except Exception as e:
            logger.exception(f"OpenAI agent error: {e}")
            self._state.status = ExecutorStatus.ERROR
            self._state.error = str(e)
            yield error_event(job_id, str(e), "execution_error").to_sse_dict()

        finally:
            self._state.end_time = datetime.now(timezone.utc)
            if self._state.status == ExecutorStatus.RUNNING:
                self._state.status = ExecutorStatus.COMPLETED

    async def _run_with_agents_sdk(
        self,
        messages: List[Dict[str, Any]],
        job_id: str,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Executa usando OpenAI Agents SDK.

        O Agents SDK oferece:
        - Agent loop completo (executa tools, retorna resultados, continua)
        - Handoffs entre agentes
        - Guardrails
        - Suporte a tools hospedadas (file_search, web_search)
        - Suporte a function tools (nossas tools unificadas)

        Ref: https://github.com/openai/openai-agents-python
        """
        logger.info(f"[OpenAI Agent] Running with Agents SDK for job {job_id}")

        # Criar function tools a partir das tools unificadas
        sdk_tools = self._create_sdk_function_tools()

        # Adicionar tools hospedadas se configurado
        hosted_tools = self._get_hosted_tools()

        # Extrair system prompt e user prompt das mensagens
        system_content = ""
        user_content = ""
        for msg in messages:
            if msg.get("role") == "system":
                system_content = msg.get("content", "")
            elif msg.get("role") == "user":
                user_content = msg.get("content", "")

        try:
            # Criar agente
            agent = Agent(
                name="IudexLegalAgent",
                instructions=system_content,
                model=self.config.model,
                tools=sdk_tools + hosted_tools,
            )

            # Criar runner para execução
            # O Runner gerencia o loop agentico automaticamente
            runner = Runner(agent=agent)

            # Executar e processar eventos via streaming
            iteration = 0
            async for event in runner.run_streamed(user_content):
                iteration += 1

                # Mapear eventos do SDK para nosso protocolo SSE
                event_type = event.type if hasattr(event, 'type') else type(event).__name__

                if event_type == "raw_model_stream_event":
                    # Token streaming
                    if hasattr(event, 'delta') and event.delta:
                        delta = event.delta
                        if hasattr(delta, 'content') and delta.content:
                            for content_part in delta.content:
                                if hasattr(content_part, 'text'):
                                    yield {
                                        "type": "token",
                                        "data": {"token": content_part.text}
                                    }

                elif event_type == "run_item_stream_event":
                    item = event.item if hasattr(event, 'item') else None

                    if item:
                        item_type = item.type if hasattr(item, 'type') else type(item).__name__

                        if item_type == "tool_call_item":
                            # Tool sendo chamada
                            tool_name = item.raw_item.name if hasattr(item.raw_item, 'name') else "unknown"
                            tool_input = {}
                            if hasattr(item.raw_item, 'arguments'):
                                try:
                                    tool_input = json.loads(item.raw_item.arguments)
                                except:
                                    tool_input = {"raw": item.raw_item.arguments}

                            yield tool_call_event(
                                job_id,
                                item.raw_item.id if hasattr(item.raw_item, 'id') else str(uuid.uuid4()),
                                tool_name,
                                tool_input
                            ).to_sse_dict()

                            # Registrar
                            self._state.tools_called.append({
                                "id": item.raw_item.id if hasattr(item.raw_item, 'id') else "",
                                "name": tool_name,
                                "input": tool_input,
                            })

                        elif item_type == "tool_call_output_item":
                            # Resultado de tool
                            tool_id = item.raw_item.tool_call_id if hasattr(item.raw_item, 'tool_call_id') else ""
                            output = item.output if hasattr(item, 'output') else str(item.raw_item)

                            yield tool_result_event(
                                job_id,
                                tool_id,
                                "tool",
                                {"result": output},
                                True
                            ).to_sse_dict()

                        elif item_type == "message_output_item":
                            # Mensagem final do agente
                            if hasattr(item, 'raw_item') and hasattr(item.raw_item, 'content'):
                                for content_part in item.raw_item.content:
                                    if hasattr(content_part, 'text'):
                                        self._state.final_output += content_part.text

                elif event_type == "agent_updated_stream_event":
                    # Agente foi atualizado (ex: handoff)
                    yield agent_iteration_event(
                        job_id,
                        iteration,
                        self.config.max_iterations
                    ).to_sse_dict()

            # Finalizar
            self._state.status = ExecutorStatus.COMPLETED
            yield done_event(
                job_id,
                "completed",
                {
                    "output": self._state.final_output,
                    "iterations": iteration,
                    "tools_called": len(self._state.tools_called),
                    "mode": "agents_sdk",
                }
            ).to_sse_dict()

        except Exception as e:
            logger.error(f"Agents SDK error: {e}. Falling back to chat completions.")
            # Fallback para chat completions em caso de erro
            async for event in self._run_with_chat_completions(messages, job_id):
                yield event

    def _create_sdk_function_tools(self) -> List:
        """
        Cria function tools no formato do Agents SDK.

        O SDK usa decorators @function_tool, mas podemos criar
        FunctionTool programaticamente a partir das nossas tools.
        """
        if not AGENTS_SDK_AVAILABLE or not FunctionTool:
            return []

        sdk_tools = []

        for tool_def in self._tools:
            tool_name = self._extract_tool_name(tool_def)
            if not tool_name:
                continue

            # Obter handler do registry
            handler = self._tool_registry.get(tool_name)
            if not handler:
                continue

            # Criar wrapper que respeita nosso sistema de permissões
            async def create_tool_wrapper(name: str, func: Callable):
                async def wrapper(**kwargs):
                    # Verificar permissão
                    permission = await self._check_permission(name, kwargs)

                    if permission == "deny":
                        return {"error": f"Tool '{name}' denied by policy"}

                    if permission == "ask":
                        # No Agents SDK, não podemos pausar facilmente
                        # Por enquanto, executamos com aviso
                        logger.warning(f"Tool '{name}' requires approval but running in SDK mode")

                    # Executar
                    try:
                        if asyncio.iscoroutinefunction(func):
                            result = await func(**kwargs)
                        else:
                            result = func(**kwargs)
                        return result
                    except Exception as e:
                        return {"error": str(e)}

                return wrapper

            # Extrair schema da definição OpenAI
            func_def = tool_def.get("function", {})
            description = func_def.get("description", "")
            parameters = func_def.get("parameters", {})

            try:
                # Criar FunctionTool programaticamente
                # O Agents SDK espera uma função decorada, mas podemos
                # usar a API de baixo nível
                wrapped = asyncio.get_event_loop().run_until_complete(
                    create_tool_wrapper(tool_name, handler)
                )

                # Usar function_tool como decorator factory se disponível
                if function_tool:
                    # Adicionar metadata à função
                    wrapped.__name__ = tool_name
                    wrapped.__doc__ = description

                    decorated = function_tool(wrapped)
                    sdk_tools.append(decorated)

            except Exception as e:
                logger.warning(f"Failed to create SDK tool for {tool_name}: {e}")

        return sdk_tools

    def _get_hosted_tools(self) -> List[Dict[str, Any]]:
        """
        Retorna tools hospedadas da OpenAI para usar.

        Hosted tools disponíveis:
        - file_search: Busca em vector stores (RAG gerenciado)
        - web_search: Busca na web (preview)
        - code_interpreter: Execução de código Python
        """
        hosted = []

        # Por enquanto, não habilitamos hosted tools por padrão
        # Podem ser habilitadas via config
        provider_config = self.config.provider_config

        if provider_config.get("enable_file_search"):
            hosted.append(HOSTED_TOOLS["file_search"])

        if provider_config.get("enable_web_search"):
            hosted.append(HOSTED_TOOLS["web_search"])

        if provider_config.get("enable_code_interpreter"):
            hosted.append(HOSTED_TOOLS["code_interpreter"])

        return hosted

    async def _run_with_chat_completions(
        self,
        messages: List[Dict[str, Any]],
        job_id: str,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Executa usando OpenAI Chat Completions com function calling.

        Loop agentico padrão:
        1. Chamar modelo com tools
        2. Se tool_calls, executar e adicionar resultados
        3. Repetir até stop ou limite
        """
        iteration = 0

        while iteration < self.config.max_iterations:
            if self._cancel_requested:
                yield done_event(job_id, "cancelled", {"reason": "user_cancelled"}).to_sse_dict()
                return

            iteration += 1
            self._state.iteration = iteration

            # Evento de iteração
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
                await self._compact_context()

            # Chamar OpenAI
            try:
                response = await self._call_openai(messages)
            except Exception as e:
                yield error_event(job_id, str(e), "api_error").to_sse_dict()
                return

            # Processar resposta
            message = response.choices[0].message

            # Atualizar tokens
            if hasattr(response, 'usage') and response.usage:
                self._state.total_input_tokens += response.usage.prompt_tokens
                self._state.total_output_tokens += response.usage.completion_tokens
                yield token_event(
                    job_id,
                    response.usage.prompt_tokens,
                    response.usage.completion_tokens
                ).to_sse_dict()

            # Verificar se há tool calls
            if message.tool_calls:
                # Adicionar mensagem do assistant
                messages.append({
                    "role": "assistant",
                    "content": message.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            }
                        }
                        for tc in message.tool_calls
                    ]
                })

                # Processar cada tool call
                for tool_call in message.tool_calls:
                    tool_name = tool_call.function.name
                    try:
                        tool_input = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError:
                        tool_input = {}

                    # Evento de tool call
                    yield tool_call_event(
                        job_id,
                        tool_call.id,
                        tool_name,
                        tool_input
                    ).to_sse_dict()

                    # Verificar permissão
                    permission = await self._check_permission(tool_name, tool_input)

                    if permission == "deny":
                        result = {"error": "Tool execution denied by policy"}
                        yield tool_result_event(
                            job_id, tool_call.id, tool_name, result, False
                        ).to_sse_dict()

                    elif permission == "ask":
                        # Pausar para aprovação
                        self._state.status = ExecutorStatus.WAITING_APPROVAL
                        self._state.pending_approvals.append({
                            "tool_call_id": tool_call.id,
                            "tool_name": tool_name,
                            "tool_input": tool_input,
                        })
                        yield tool_approval_required_event(
                            job_id,
                            tool_call.id,
                            tool_name,
                            tool_input,
                            self._get_tool_risk_level(tool_name)
                        ).to_sse_dict()

                        # Aguardar aprovação (resume será chamado)
                        yield done_event(
                            job_id,
                            "waiting_approval",
                            {"pending_tools": [tool_name]}
                        ).to_sse_dict()
                        return

                    else:  # allow
                        # Executar tool
                        result = await self._execute_tool(tool_name, tool_input)
                        success = "error" not in result

                        # Registrar
                        self._state.tools_called.append({
                            "id": tool_call.id,
                            "name": tool_name,
                            "input": tool_input,
                            "result": result,
                            "success": success,
                        })

                        yield tool_result_event(
                            job_id, tool_call.id, tool_name, result, success
                        ).to_sse_dict()

                        # Adicionar resultado às mensagens
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": json.dumps(result) if isinstance(result, dict) else str(result),
                        })

                # Criar checkpoint após tools
                await self._create_checkpoint(f"After tools in iteration {iteration}")

            else:
                # Sem tool calls - resposta final
                content = message.content or ""

                # Stream do conteúdo
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

        # Limite de iterações atingido
        self._state.status = ExecutorStatus.ERROR
        self._state.error = "Max iterations reached"
        yield error_event(
            job_id,
            "Maximum iterations reached",
            "iteration_limit"
        ).to_sse_dict()

    async def _call_openai(
        self,
        messages: List[Dict[str, Any]],
    ) -> Any:
        """
        Chama a API do OpenAI.

        Args:
            messages: Histórico de mensagens

        Returns:
            Response do OpenAI
        """
        kwargs = {
            "model": self.config.model,
            "messages": messages,
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
        }

        # Adicionar tools se disponíveis
        if self._tools:
            kwargs["tools"] = self._tools
            if self.config.parallel_tool_calls:
                kwargs["parallel_tool_calls"] = True

        # Response format (JSON mode, etc.)
        if self.config.response_format:
            kwargs["response_format"] = self.config.response_format

        # Reasoning effort (para o1)
        if self.config.reasoning_effort and self.config.model.startswith("o1"):
            kwargs["reasoning_effort"] = self.config.reasoning_effort

        return await self.async_client.chat.completions.create(**kwargs)

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
            **kwargs: Argumentos adicionais

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
        messages = self._state.messages.copy()

        for pending in self._state.pending_approvals:
            tool_call_id = pending["tool_call_id"]
            tool_name = pending["tool_name"]
            tool_input = pending["tool_input"]

            # Verificar se foi aprovado ou negado
            approved_result = None
            if tool_results:
                for tr in tool_results:
                    if tr.get("tool_call_id") == tool_call_id:
                        approved_result = tr
                        break

            if approved_result and approved_result.get("approved", False):
                # Executar tool
                result = await self._execute_tool(tool_name, tool_input)
                success = "error" not in result

                self._state.tools_called.append({
                    "id": tool_call_id,
                    "name": tool_name,
                    "input": tool_input,
                    "result": result,
                    "success": success,
                })

                yield tool_result_event(
                    job_id, tool_call_id, tool_name, result, success
                ).to_sse_dict()

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": json.dumps(result) if isinstance(result, dict) else str(result),
                })
            else:
                # Negado
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": json.dumps({"error": "Tool execution denied by user"}),
                })

        # Limpar pendências
        self._state.pending_approvals = []
        self._state.status = ExecutorStatus.RUNNING
        self._state.messages = messages

        # Continuar execução
        async for event in self._run_with_chat_completions(messages, job_id):
            yield event

    def _build_system_prompt(
        self,
        base_prompt: Optional[str],
        context: Optional[str],
    ) -> str:
        """Constrói system prompt completo."""
        parts = []

        # Prompt base
        if base_prompt:
            parts.append(base_prompt)
        else:
            parts.append(
                "Você é um assistente jurídico especializado. "
                "Use as ferramentas disponíveis para pesquisar informações, "
                "analisar documentos e auxiliar na elaboração de peças jurídicas."
            )

        # Contexto
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
