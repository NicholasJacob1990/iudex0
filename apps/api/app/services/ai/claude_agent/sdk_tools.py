"""
SDK Tools — In-process MCP server for Claude Agent SDK.

Exposes pre-configured Iudex tools (jurisprudence, legislation, web search,
RAG, citation verification, workflow execution) as MCP tools that the
Claude Agent SDK can call natively.
"""

from __future__ import annotations

import json
import contextvars
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


# ---------------------------------------------------------------------------
# MCP Server factory
# ---------------------------------------------------------------------------

_ALL_TOOLS = [
    search_jurisprudencia,
    search_legislacao,
    web_search,
    search_rag,
    verify_citation,
    run_workflow,
    ask_graph,
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
