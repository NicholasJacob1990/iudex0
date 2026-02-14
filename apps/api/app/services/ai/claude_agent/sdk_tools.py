"""
SDK Tools — In-process MCP server for Claude Agent SDK.

Exposes pre-configured Iudex tools (jurisprudence, legislation, web search,
RAG, citation verification, workflow execution) as MCP tools that the
Claude Agent SDK can call natively.
"""

from __future__ import annotations

import json
import contextvars
from dataclasses import asdict, is_dataclass
from typing import Any

from loguru import logger

try:
    from claude_agent_sdk import tool, create_sdk_mcp_server

    CLAUDE_SDK_TOOLS_AVAILABLE = True
except ImportError:
    CLAUDE_SDK_TOOLS_AVAILABLE = False

    # Stubs so module can be imported without the SDK installed
    def tool(*args, **kwargs):  # type: ignore[misc]
        def _decorator(fn):
            return fn

        return _decorator

    def create_sdk_mcp_server(**kwargs):  # type: ignore[misc]
        return None


# ---------------------------------------------------------------------------
# Helper — serialise service results to MCP content
# ---------------------------------------------------------------------------

def _text_content(data: Any) -> dict[str, Any]:
    """Wrap data as MCP text content block."""
    if isinstance(data, str):
        text = data
    else:
        text = json.dumps(data, ensure_ascii=False, default=str)
    return {"content": [{"type": "text", "text": text}]}


def _normalize_result(data: Any) -> Any:
    """Convert dataclasses and nested values into JSON-serializable structures."""
    if is_dataclass(data):
        return asdict(data)
    if isinstance(data, list):
        return [_normalize_result(item) for item in data]
    if isinstance(data, tuple):
        return [_normalize_result(item) for item in data]
    if isinstance(data, dict):
        return {str(k): _normalize_result(v) for k, v in data.items()}
    return data


def _coerce_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    """Parse integer args with bounds and safe fallback."""
    try:
        parsed = int(value)
    except Exception:
        parsed = default
    return max(minimum, min(maximum, parsed))


def _coerce_bool(value: Any, default: bool = False) -> bool:
    """Parse boolean args from bool/int/string values."""
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on", "y"}:
            return True
        if normalized in {"0", "false", "no", "off", "n"}:
            return False
    return default


def _parse_tool_names(raw: Any) -> list[str] | None:
    """Normalize tool_names from comma-separated string or array."""
    if raw is None:
        return None

    if isinstance(raw, str):
        values = [part.strip() for part in raw.split(",")]
    elif isinstance(raw, list):
        values = [str(part).strip() for part in raw]
    else:
        return None

    dedup: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value or value in seen:
            continue
        dedup.append(value)
        seen.add(value)
    return dedup or None


# ---------------------------------------------------------------------------
# Execution context (per run) — injected by ClaudeAgentExecutor SDK mode
# ---------------------------------------------------------------------------

_IUDEX_TOOL_CONTEXT: contextvars.ContextVar[dict[str, Any]] = contextvars.ContextVar(
    "iudex_tool_context",
    default={},
)


def set_iudex_tool_context(ctx: dict[str, Any]) -> None:
    """
    Set default tool context for SDK tools.

    This avoids forcing the model to pass tenant/user identifiers explicitly
    on every tool call.
    """
    _IUDEX_TOOL_CONTEXT.set(dict(ctx or {}))


def _ctx_get(key: str, default: Any = None) -> Any:
    try:
        ctx = _IUDEX_TOOL_CONTEXT.get()
        return ctx.get(key, default)
    except Exception:
        return default


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

@tool(
    "search_jurisprudencia",
    "Pesquisa jurisprudência em base local (STF, STJ, TRFs, TJs). "
    "Retorna precedentes, ementas e decisões relevantes.",
    {"query": str, "court": str, "limit": int},
)
async def search_jurisprudencia(args: dict[str, Any]) -> dict[str, Any]:
    try:
        from app.services.jurisprudence_service import jurisprudence_service

        result = await jurisprudence_service.search(
            query=args["query"],
            court=args.get("court") or None,
            limit=int(args.get("limit", 10)),
        )
        return _text_content(result)
    except Exception as e:
        logger.warning(f"search_jurisprudencia failed: {e}")
        return _text_content({"error": str(e)})


@tool(
    "search_jusbrasil",
    "Pesquisa conteudo juridico no JusBrasil, incluindo jurisprudencia, "
    "publicacoes e materiais indexados.",
    {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Termos de busca"},
            "tribunal": {"type": "string", "description": "Sigla opcional do tribunal (ex: STJ, TJSP)"},
            "tipo": {"type": "string", "description": "Tipo de conteudo (jurisprudencia, noticia, doutrina)"},
            "data_inicio": {"type": "string", "format": "date", "description": "Data inicial (YYYY-MM-DD)"},
            "data_fim": {"type": "string", "format": "date", "description": "Data final (YYYY-MM-DD)"},
            "max_results": {"type": "integer", "description": "Numero maximo de resultados (1-30)"},
            "use_cache": {"type": "boolean", "description": "Permite usar cache no fallback web"},
        },
        "required": ["query"],
    },
)
async def search_jusbrasil(args: dict[str, Any]) -> dict[str, Any]:
    try:
        from app.services.jusbrasil_service import jusbrasil_service

        result = await jusbrasil_service.search(
            query=str(args.get("query") or ""),
            tribunal=(str(args.get("tribunal")) if args.get("tribunal") else None),
            tipo=(str(args.get("tipo")) if args.get("tipo") else None),
            data_inicio=(str(args.get("data_inicio")) if args.get("data_inicio") else None),
            data_fim=(str(args.get("data_fim")) if args.get("data_fim") else None),
            max_results=_coerce_int(args.get("max_results"), default=10, minimum=1, maximum=30),
            use_cache=_coerce_bool(args.get("use_cache"), default=True),
        )
        return _text_content(result)
    except Exception as e:
        logger.warning(f"search_jusbrasil failed: {e}")
        return _text_content({"error": str(e)})


@tool(
    "search_legislacao",
    "Pesquisa legislação (leis, decretos, portarias). "
    "Retorna textos legais vigentes e informações normativas.",
    {"query": str, "tipo": str, "limit": int},
)
async def search_legislacao(args: dict[str, Any]) -> dict[str, Any]:
    try:
        from app.services.legislation_service import legislation_service

        result = await legislation_service.search(
            query=args["query"],
            tipo=args.get("tipo") or None,
            limit=int(args.get("limit", 10)),
        )
        return _text_content(result)
    except Exception as e:
        logger.warning(f"search_legislacao failed: {e}")
        return _text_content({"error": str(e)})


@tool(
    "web_search",
    "Pesquisa na web. Use para buscar informações atuais, jurisprudência, "
    "notícias, doutrina ou qualquer tema que precise de dados atualizados.",
    {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Query de busca"},
            "search_type": {
                "type": "string",
                "enum": ["general", "legal"],
                "description": "Tipo: general ou legal (fontes jurídicas)",
            },
            "max_results": {
                "type": "integer",
                "description": "Número máximo de resultados",
            },
        },
        "required": ["query"],
    },
)
async def web_search(args: dict[str, Any]) -> dict[str, Any]:
    try:
        from app.services.web_search_service import web_search_service

        query_text = str(args["query"])
        search_type = str(args.get("search_type", "general"))
        max_results = int(args.get("max_results", 8))

        if search_type == "legal":
            result = await web_search_service.search_legal(
                query_text, num_results=max_results
            )
        else:
            result = await web_search_service.search(
                query_text, num_results=max_results
            )
        return _text_content(result)
    except Exception as e:
        logger.warning(f"web_search failed: {e}")
        return _text_content({"error": str(e)})


@tool(
    "search_rag",
    "Pesquisa na base de conhecimento RAG (local por caso e global). "
    "Retorna trechos relevantes de documentos, legislação e jurisprudência indexados.",
    {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Termos de busca"},
            "sources": {
                "type": "string",
                "description": "Fontes: lei, juris, sei, pecas_modelo. Separar com vírgula. Vazio = todas.",
            },
            "limit": {"type": "integer", "description": "Número máximo de resultados"},
            "user_id": {"type": "string", "description": "ID do usuário (para escopo de dados)"},
        },
        "required": ["query"],
    },
)
async def search_rag(args: dict[str, Any]) -> dict[str, Any]:
    try:
        from app.services.rag_module import get_scoped_knowledge_graph

        rag = get_scoped_knowledge_graph()
        sources_raw = args.get("sources", "")
        sources = [s.strip() for s in sources_raw.split(",") if s.strip()] if sources_raw else None
        user_id = args.get("user_id") or None

        results = rag.hybrid_search(
            query=args["query"],
            sources=sources,
            top_k=int(args.get("limit", 10)),
            user_id=user_id,
            include_global=True,
        )
        return _text_content({"results": results, "total": len(results)})
    except Exception as e:
        logger.warning(f"search_rag failed: {e}")
        return _text_content({"error": str(e)})


@tool(
    "verify_citation",
    "Verifica se uma citação jurídica (lei, artigo, jurisprudência) existe e é precisa. "
    "Retorna resultado da validação.",
    {"citation": str, "context": str},
)
async def verify_citation(args: dict[str, Any]) -> dict[str, Any]:
    try:
        from app.services.ai.citer_verifier import CiterVerifier

        verifier = CiterVerifier()
        result = await verifier.verify(
            citation=args["citation"],
            context=args.get("context", ""),
        )
        return _text_content(result)
    except Exception as e:
        logger.warning(f"verify_citation failed: {e}")
        return _text_content({"error": str(e)})


@tool(
    "run_workflow",
    "Executa um workflow LangGraph pré-configurado (ex: geração de minuta com plano, "
    "rascunho, revisão e finalização).",
    {
        "type": "object",
        "properties": {
            "prompt": {"type": "string", "description": "Instrução para o workflow"},
            "model": {
                "type": "string",
                "description": "Modelo a usar (padrão: gpt-4o)",
            },
        },
        "required": ["prompt"],
    },
)
async def run_workflow(args: dict[str, Any]) -> dict[str, Any]:
    try:
        from app.services.ai.langgraph_workflow import MinutaWorkflow

        model = args.get("model", "gpt-4o")
        workflow = MinutaWorkflow(model=model)
        result = await workflow.run(
            prompt=args["prompt"],
            context={},
        )
        return _text_content(result)
    except Exception as e:
        logger.warning(f"run_workflow failed: {e}")
        return _text_content({"error": str(e)})


@tool(
    "ask_graph",
    "Consulta o grafo de conhecimento jurídico via operações tipadas (sem Cypher arbitrário). "
    "Use para caminhos entre entidades, vizinhos semânticos, co-ocorrência e busca.",
    {"operation": str, "params": dict, "scope": str, "include_global": bool, "case_id": str},
)
async def ask_graph(args: dict[str, Any]) -> dict[str, Any]:
    """
    Graph ask tool for Claude Agent SDK mode.

    Uses the same safe typed operations as the REST endpoints and unified tool.
    """
    try:
        from app.services.graph_ask_service import get_graph_ask_service

        service = get_graph_ask_service()

        scope = (args.get("scope") or None)
        include_global = bool(args.get("include_global", True))

        # Segurança: tenant_id/case_id devem vir do contexto do servidor (não do LLM).
        tenant_id = _ctx_get("tenant_id")
        if not tenant_id:
            return _text_content({"error": "Contexto sem tenant_id (bloqueado por segurança)."})
        case_id = _ctx_get("case_id")

        result = await service.ask(
            operation=str(args.get("operation") or ""),
            params=args.get("params") or {},
            tenant_id=str(tenant_id),
            scope=str(scope) if scope else None,
            case_id=str(case_id) if case_id else None,
            include_global=include_global,
        )
        return _text_content(result.to_dict())
    except Exception as e:
        logger.warning(f"ask_graph failed: {e}")
        return _text_content({"error": str(e)})


@tool(
    "consultar_processo_datajud",
    "Consulta metadados de processo no DataJud (CNJ), incluindo classe, assuntos "
    "e movimentações mais recentes.",
    {
        "type": "object",
        "properties": {
            "numero_processo": {
                "type": "string",
                "description": "Número CNJ do processo (com ou sem máscara).",
            },
            "tribunal": {
                "type": "string",
                "description": "Sigla do tribunal (ex: TJSP). Opcional se inferível pelo NPU.",
            },
        },
        "required": ["numero_processo"],
    },
)
async def consultar_processo_datajud(args: dict[str, Any]) -> dict[str, Any]:
    try:
        from app.services.djen_service import extract_tribunal_from_npu, get_djen_service

        numero_processo = str(args.get("numero_processo") or "").strip()
        if not numero_processo:
            return _text_content({"error": "numero_processo é obrigatório"})

        tribunal = (args.get("tribunal") or "").strip().upper() or extract_tribunal_from_npu(numero_processo)
        if not tribunal:
            return _text_content(
                {
                    "error": (
                        "Tribunal nao identificado pelo NPU. "
                        "Informe o parametro 'tribunal' (ex: TJSP)."
                    )
                }
            )

        djen_service = get_djen_service()
        if not djen_service.datajud.api_key:
            return _text_content({"error": "CNJ_API_KEY not configured"})

        results = await djen_service.fetch_metadata(numero_processo, tribunal)
        payload = {
            "results": _normalize_result(results),
            "total": len(results),
            "tribunal": tribunal,
        }
        return _text_content(payload)
    except Exception as e:
        logger.warning(f"consultar_processo_datajud failed: {e}")
        return _text_content({"error": str(e)})


@tool(
    "buscar_publicacoes_djen",
    "Busca publicacoes no Diario de Justica Eletronico Nacional (DJEN) por "
    "processo, periodo e/ou tribunal.",
    {
        "type": "object",
        "properties": {
            "numero_processo": {
                "type": "string",
                "description": "Numero do processo para filtrar.",
            },
            "data_inicio": {
                "type": "string",
                "description": "Data inicial no formato YYYY-MM-DD.",
            },
            "data_fim": {
                "type": "string",
                "description": "Data final no formato YYYY-MM-DD.",
            },
            "tribunal": {
                "type": "string",
                "description": "Sigla do tribunal (ex: TJMG).",
            },
            "meio": {
                "type": "string",
                "enum": ["D", "E"],
                "description": "D=Diario, E=Edital.",
            },
            "max_pages": {
                "type": "integer",
                "description": "Numero maximo de paginas na busca DJEN.",
            },
        },
    },
)
async def buscar_publicacoes_djen(args: dict[str, Any]) -> dict[str, Any]:
    try:
        from app.services.djen_service import get_djen_service

        djen_service = get_djen_service()
        results = await djen_service.search_by_process(
            numero_processo=str(args.get("numero_processo") or ""),
            tribunal_sigla=(args.get("tribunal") or None),
            data_inicio=(args.get("data_inicio") or None),
            data_fim=(args.get("data_fim") or None),
            meio=str(args.get("meio", "D")),
            max_pages=int(args.get("max_pages", 10)),
        )
        payload = {
            "results": _normalize_result(results),
            "total": len(results),
        }
        return _text_content(payload)
    except Exception as e:
        logger.warning(f"buscar_publicacoes_djen failed: {e}")
        return _text_content({"error": str(e)})


@tool(
    "validate_cpc_compliance",
    "Valida conformidade processual basica com o CPC (requisitos formais, "
    "prazos e alertas normativos) para pecas juridicas.",
    {
        "type": "object",
        "properties": {
            "document_text": {
                "type": "string",
                "description": "Texto integral da peca a validar.",
            },
            "document_type": {
                "type": "string",
                "enum": [
                    "auto",
                    "peticao_inicial",
                    "contestacao",
                    "apelacao",
                    "agravo_instrumento",
                    "embargos_declaracao",
                    "generic",
                ],
                "description": "Tipo de documento para aplicar regras especificas.",
            },
            "reference_date": {
                "type": "string",
                "description": "Data inicial de contagem de prazo (YYYY-MM-DD ou DD/MM/YYYY).",
            },
            "filing_date": {
                "type": "string",
                "description": "Data de protocolo/apresentacao (YYYY-MM-DD ou DD/MM/YYYY).",
            },
            "strict_mode": {
                "type": "boolean",
                "description": "Se true, warnings viram falhas no resumo final.",
            },
        },
        "required": ["document_text"],
    },
)
async def validate_cpc_compliance(args: dict[str, Any]) -> dict[str, Any]:
    try:
        from app.services.ai.claude_agent.tools.cpc_validator import (
            validate_cpc_compliance as run_cpc_validator,
        )

        document_text = str(args.get("document_text") or "").strip()
        if not document_text:
            return _text_content({"error": "document_text e obrigatorio"})

        result = await run_cpc_validator(
            document_text=document_text,
            document_type=str(args.get("document_type") or "auto"),
            filing_date=(args.get("filing_date") or None),
            reference_date=(args.get("reference_date") or None),
            strict_mode=_coerce_bool(args.get("strict_mode"), default=False),
        )
        return _text_content(result)
    except Exception as e:
        logger.warning(f"validate_cpc_compliance failed: {e}")
        return _text_content({"error": str(e)})


@tool(
    "delegate_subtask",
    "Delega uma subtarefa para um subagente Claude com modelo especifico "
    "(default: claude-haiku-4-5) para reduzir custo em tarefas simples.",
    {
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "Subtarefa a ser executada pelo subagente.",
            },
            "model": {
                "type": "string",
                "description": "Modelo Claude do subagente (default: claude-haiku-4-5).",
            },
            "tool_names": {
                "description": "Lista de tools permitidas para o subagente (array ou CSV).",
                "oneOf": [
                    {"type": "array", "items": {"type": "string"}},
                    {"type": "string"},
                ],
            },
            "max_tokens": {
                "type": "integer",
                "description": "Maximo de tokens de saida do subagente.",
            },
            "max_iterations": {
                "type": "integer",
                "description": "Numero maximo de iteracoes do loop agentico.",
            },
            "system_prompt": {
                "type": "string",
                "description": "System prompt especifico para a subtarefa.",
            },
            "context": {
                "type": "string",
                "description": "Contexto adicional opcional para a subtarefa.",
            },
            "include_mcp": {
                "type": "boolean",
                "description": "Se true, inclui MCP tools no subagente (default: false).",
            },
        },
        "required": ["task"],
    },
)
async def delegate_subtask(args: dict[str, Any]) -> dict[str, Any]:
    """
    Spawn a lightweight Claude subagent for focused subtasks.

    Uses the same local tool stack through load_unified_tools, with SDK mode
    disabled to avoid nested SDK sessions.
    """
    try:
        from app.services.ai.claude_agent.executor import AgentConfig, ClaudeAgentExecutor
        from app.services.ai.shared import SSEEventType, ToolExecutionContext

        task = str(args.get("task") or "").strip()
        if not task:
            return _text_content({"error": "task é obrigatória"})

        model = str(args.get("model") or "claude-haiku-4-5").strip()
        if not model.startswith("claude-"):
            return _text_content({"error": "Somente modelos Claude são permitidos em delegate_subtask"})

        max_tokens = _coerce_int(args.get("max_tokens"), default=4096, minimum=256, maximum=16384)
        max_iterations = _coerce_int(args.get("max_iterations"), default=5, minimum=1, maximum=12)
        include_mcp = _coerce_bool(args.get("include_mcp"), default=False)
        tool_names = _parse_tool_names(args.get("tool_names"))

        system_prompt = str(
            args.get("system_prompt")
            or "Você é um assistente jurídico auxiliar. Resolva apenas a subtarefa solicitada."
        )
        context = args.get("context")
        context_text = str(context).strip() if context is not None else None
        if context_text == "":
            context_text = None

        user_id = str(_ctx_get("user_id") or "sdk-subagent")
        tenant_id = str(_ctx_get("tenant_id") or user_id)
        case_id = _ctx_get("case_id")
        chat_id = _ctx_get("chat_id")
        parent_job_id = _ctx_get("job_id")

        config = AgentConfig(
            model=model,
            max_tokens=max_tokens,
            max_iterations=max_iterations,
            enable_checkpoints=False,
            use_sdk=False,
            enable_code_execution=False,
            code_execution_effort="low",
        )
        subagent = ClaudeAgentExecutor(config=config)

        exec_ctx = ToolExecutionContext(
            user_id=user_id,
            tenant_id=tenant_id,
            case_id=str(case_id) if case_id else None,
            chat_id=str(chat_id) if chat_id else None,
            job_id=str(parent_job_id) if parent_job_id else None,
        )
        subagent.load_unified_tools(
            include_mcp=include_mcp,
            tool_names=tool_names,
            execution_context=exec_ctx,
        )

        token_parts: list[str] = []
        final_text = ""
        subagent_metadata: dict[str, Any] = {}

        async for event in subagent.run(
            prompt=task,
            system_prompt=system_prompt,
            context=context_text,
            user_id=user_id,
            case_id=str(case_id) if case_id else None,
            session_id=str(chat_id) if chat_id else None,
        ):
            event_type = getattr(event, "type", "")
            if hasattr(event_type, "value"):
                event_type = event_type.value
            data = getattr(event, "data", {}) or {}

            if event_type == SSEEventType.TOKEN.value:
                token = str(data.get("token") or "")
                if token:
                    token_parts.append(token)
            elif event_type == SSEEventType.DONE.value:
                final_text = str(data.get("final_text") or "").strip()
                if isinstance(data.get("metadata"), dict):
                    subagent_metadata = data["metadata"]
            elif event_type == SSEEventType.ERROR.value:
                return _text_content(
                    {
                        "error": str(data.get("error") or "Subagent execution failed"),
                        "model": model,
                    }
                )

        resolved_text = final_text or "".join(token_parts).strip()
        payload: dict[str, Any] = {
            "result": resolved_text,
            "model": model,
            "max_iterations": max_iterations,
            "max_tokens": max_tokens,
            "tool_names": tool_names or "all_unified",
            "include_mcp": include_mcp,
            "subagent_metadata": subagent_metadata,
        }
        if not resolved_text:
            payload["warning"] = "Subagent returned empty output"

        return _text_content(payload)
    except Exception as e:
        logger.warning(f"delegate_subtask failed: {e}")
        return _text_content({"error": str(e)})


# ---------------------------------------------------------------------------
# MCP Server factory
# ---------------------------------------------------------------------------

_ALL_TOOLS = [
    search_jurisprudencia,
    search_jusbrasil,
    search_legislacao,
    web_search,
    search_rag,
    verify_citation,
    run_workflow,
    ask_graph,
    delegate_subtask,
    consultar_processo_datajud,
    buscar_publicacoes_djen,
    validate_cpc_compliance,
]


def create_iudex_mcp_server():
    """Create an in-process MCP server with all pre-configured Iudex tools."""
    if not CLAUDE_SDK_TOOLS_AVAILABLE:
        logger.warning("claude-agent-sdk not installed — MCP server unavailable")
        return None

    return create_sdk_mcp_server(
        name="iudex-legal",
        version="1.0.0",
        tools=_ALL_TOOLS,
    )
