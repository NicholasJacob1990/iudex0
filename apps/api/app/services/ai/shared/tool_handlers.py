"""
Tool Handlers - Implementações das tools unificadas.

Este módulo contém os handlers que executam cada tool.
Integra com serviços existentes do Iudex.
"""

import asyncio
import fnmatch
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

# Serviços existentes do Iudex
from app.services.ai.shared.unified_tools import (
    UnifiedTool,
    ToolRiskLevel,
    TOOLS_BY_NAME,
    ALL_UNIFIED_TOOLS,
)


# =============================================================================
# CONTEXT FOR TOOL EXECUTION
# =============================================================================

class ToolExecutionContext:
    """
    Contexto para execução de tools.

    Contém informações necessárias para tools que requerem contexto:
    - IDs do usuário, caso, chat
    - Referências a serviços
    - Configurações
    """

    def __init__(
        self,
        user_id: str,
        tenant_id: Optional[str] = None,
        case_id: Optional[str] = None,
        chat_id: Optional[str] = None,
        job_id: Optional[str] = None,
        db_session: Optional[Any] = None,
        services: Optional[Dict[str, Any]] = None,
    ):
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.case_id = case_id
        self.chat_id = chat_id
        self.job_id = job_id
        self.db = db_session
        self.services = services or {}

    def get_service(self, name: str) -> Optional[Any]:
        """Obtém serviço pelo nome."""
        return self.services.get(name)


# =============================================================================
# HANDLER IMPLEMENTATIONS
# =============================================================================

class ToolHandlers:
    """
    Implementações dos handlers de tools.

    Cada método corresponde a uma tool e implementa sua lógica.
    """

    def __init__(self, context: Optional[ToolExecutionContext] = None):
        """
        Inicializa handlers com contexto.

        Args:
            context: Contexto de execução (user_id, case_id, etc.)
        """
        self.context = context
        self._handlers: Dict[str, callable] = self._register_handlers()

    def _register_handlers(self) -> Dict[str, callable]:
        """Registra todos os handlers."""
        return {
            # SDK Adapted
            "read_document": self.handle_read_document,
            "write_document": self.handle_write_document,
            "edit_document": self.handle_edit_document,
            "find_documents": self.handle_find_documents,
            "search_in_documents": self.handle_search_in_documents,
            "web_search": self.handle_web_search,
            "web_fetch": self.handle_web_fetch,
            "delegate_research": self.handle_delegate_research,
            # Legal Domain
            "search_jurisprudencia": self.handle_search_jurisprudencia,
            "search_legislacao": self.handle_search_legislacao,
            "verify_citation": self.handle_verify_citation,
            "search_rag": self.handle_search_rag,
            "create_section": self.handle_create_section,
            # Graph
            "ask_graph": self.handle_ask_graph,
            # MCP
            "mcp_tool_search": self.handle_mcp_tool_search,
            "mcp_tool_call": self.handle_mcp_tool_call,
        }

    async def execute(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        context: Optional[ToolExecutionContext] = None,
    ) -> Dict[str, Any]:
        """
        Executa uma tool pelo nome.

        Args:
            tool_name: Nome da tool
            parameters: Parâmetros da tool
            context: Contexto de execução (sobrescreve self.context)

        Returns:
            Resultado da execução
        """
        handler = self._handlers.get(tool_name)
        if not handler:
            return {
                "success": False,
                "error": f"Tool não encontrada: {tool_name}",
            }

        ctx = context or self.context

        try:
            result = await handler(parameters, ctx)
            return {
                "success": True,
                "result": result,
                "tool_name": tool_name,
                "executed_at": datetime.utcnow().isoformat(),
            }
        except Exception as e:
            logger.error(f"Erro executando tool {tool_name}: {e}")
            return {
                "success": False,
                "error": str(e),
                "tool_name": tool_name,
            }

    # =========================================================================
    # DOCUMENT HANDLERS
    # =========================================================================

    async def handle_read_document(
        self,
        params: Dict[str, Any],
        ctx: Optional[ToolExecutionContext] = None,
    ) -> Dict[str, Any]:
        """Lê documento do caso."""
        document_id = params.get("document_id")
        section = params.get("section")
        format_type = params.get("format", "markdown")

        # Importar serviço de documentos
        try:
            from app.services.document_processor import DocumentProcessor

            if ctx and ctx.db:
                processor = DocumentProcessor(ctx.db)
                content = await processor.get_document_content(
                    document_id=document_id,
                    section=section,
                    format=format_type,
                )
                return {
                    "document_id": document_id,
                    "content": content,
                    "format": format_type,
                    "section": section,
                }
            else:
                # Fallback sem DB
                return {
                    "document_id": document_id,
                    "content": f"[Documento {document_id} - seção {section or 'completo'}]",
                    "format": format_type,
                    "note": "DB session não disponível - retorno simulado",
                }
        except ImportError:
            return {
                "document_id": document_id,
                "content": f"[Documento {document_id}]",
                "note": "DocumentProcessor não disponível",
            }

    async def handle_write_document(
        self,
        params: Dict[str, Any],
        ctx: Optional[ToolExecutionContext] = None,
    ) -> Dict[str, Any]:
        """Cria/sobrescreve documento."""
        content = params.get("content", "")
        title = params.get("title", "Sem título")
        doc_type = params.get("document_type", "outro")
        format_type = params.get("format", "markdown")
        document_id = params.get("document_id")

        try:
            from app.services.document_processor import DocumentProcessor

            if ctx and ctx.db:
                processor = DocumentProcessor(ctx.db)
                result = await processor.save_document(
                    content=content,
                    title=title,
                    document_type=doc_type,
                    case_id=ctx.case_id,
                    user_id=ctx.user_id,
                    document_id=document_id,
                )
                return {
                    "document_id": result.get("id"),
                    "title": title,
                    "saved": True,
                }
            else:
                import uuid
                return {
                    "document_id": document_id or str(uuid.uuid4()),
                    "title": title,
                    "saved": True,
                    "note": "Simulado - DB não disponível",
                }
        except ImportError:
            import uuid
            return {
                "document_id": document_id or str(uuid.uuid4()),
                "title": title,
                "note": "DocumentProcessor não disponível",
            }

    async def handle_edit_document(
        self,
        params: Dict[str, Any],
        ctx: Optional[ToolExecutionContext] = None,
    ) -> Dict[str, Any]:
        """Edita seção de documento."""
        document_id = params.get("document_id")
        old_text = params.get("old_text", "")
        new_text = params.get("new_text", "")
        section = params.get("section")
        replace_all = params.get("replace_all", False)

        try:
            from app.services.document_processor import DocumentProcessor

            if ctx and ctx.db:
                processor = DocumentProcessor(ctx.db)
                result = await processor.edit_document(
                    document_id=document_id,
                    old_text=old_text,
                    new_text=new_text,
                    section=section,
                    replace_all=replace_all,
                )
                return {
                    "document_id": document_id,
                    "edited": True,
                    "replacements": result.get("count", 1),
                }
            else:
                return {
                    "document_id": document_id,
                    "edited": True,
                    "replacements": 1,
                    "note": "Simulado - DB não disponível",
                }
        except ImportError:
            return {
                "document_id": document_id,
                "edited": True,
                "note": "DocumentProcessor não disponível",
            }

    async def handle_find_documents(
        self,
        params: Dict[str, Any],
        ctx: Optional[ToolExecutionContext] = None,
    ) -> Dict[str, Any]:
        """Busca documentos por padrão."""
        pattern = params.get("pattern", "*")
        doc_type = params.get("document_type", "all")
        limit = params.get("limit", 20)

        try:
            from app.services.case_service import CaseService

            if ctx and ctx.db and ctx.case_id:
                case_service = CaseService(ctx.db)
                documents = await case_service.list_documents(
                    case_id=ctx.case_id,
                    pattern=pattern,
                    doc_type=doc_type if doc_type != "all" else None,
                    limit=limit,
                )
                return {
                    "pattern": pattern,
                    "documents": documents,
                    "count": len(documents),
                }
            else:
                return {
                    "pattern": pattern,
                    "documents": [],
                    "count": 0,
                    "note": "Case ID ou DB não disponível",
                }
        except ImportError:
            return {
                "pattern": pattern,
                "documents": [],
                "note": "CaseService não disponível",
            }

    async def handle_search_in_documents(
        self,
        params: Dict[str, Any],
        ctx: Optional[ToolExecutionContext] = None,
    ) -> Dict[str, Any]:
        """Busca texto em documentos."""
        pattern = params.get("pattern", "")
        document_ids = params.get("document_ids", [])
        case_sensitive = params.get("case_sensitive", False)
        use_regex = params.get("regex", False)
        context_lines = params.get("context_lines", 2)

        try:
            from app.services.rag_ingestion import search_documents

            if ctx and ctx.case_id:
                results = await search_documents(
                    query=pattern,
                    case_id=ctx.case_id,
                    document_ids=document_ids or None,
                    context_lines=context_lines,
                )
                return {
                    "pattern": pattern,
                    "matches": results,
                    "count": len(results),
                }
            else:
                return {
                    "pattern": pattern,
                    "matches": [],
                    "note": "Case ID não disponível",
                }
        except ImportError:
            return {
                "pattern": pattern,
                "matches": [],
                "note": "search_documents não disponível",
            }

    async def handle_create_section(
        self,
        params: Dict[str, Any],
        ctx: Optional[ToolExecutionContext] = None,
    ) -> Dict[str, Any]:
        """Cria nova seção em documento."""
        document_id = params.get("document_id")
        section_title = params.get("section_title", "")
        content = params.get("content", "")
        position = params.get("position", "end")
        reference = params.get("reference_section")

        try:
            from app.services.document_processor import DocumentProcessor

            if ctx and ctx.db:
                processor = DocumentProcessor(ctx.db)
                result = await processor.add_section(
                    document_id=document_id,
                    title=section_title,
                    content=content,
                    position=position,
                    reference=reference,
                )
                return {
                    "document_id": document_id,
                    "section_title": section_title,
                    "created": True,
                }
            else:
                return {
                    "document_id": document_id,
                    "section_title": section_title,
                    "created": True,
                    "note": "Simulado - DB não disponível",
                }
        except ImportError:
            return {
                "document_id": document_id,
                "section_title": section_title,
                "note": "DocumentProcessor não disponível",
            }

    # =========================================================================
    # WEB HANDLERS
    # =========================================================================

    async def handle_web_search(
        self,
        params: Dict[str, Any],
        ctx: Optional[ToolExecutionContext] = None,
    ) -> Dict[str, Any]:
        """Pesquisa na web."""
        query = params.get("query", "")
        search_type = params.get("search_type", "general")
        recency = params.get("recency", "any")
        max_results = params.get("max_results", 10)

        try:
            from app.services.web_search_service import WebSearchService

            service = WebSearchService()
            results = await service.search(
                query=query,
                search_type=search_type,
                recency=recency,
                max_results=max_results,
            )
            return {
                "query": query,
                "results": results,
                "count": len(results),
            }
        except ImportError:
            return {
                "query": query,
                "results": [],
                "note": "WebSearchService não disponível",
            }
        except Exception as e:
            return {
                "query": query,
                "results": [],
                "error": str(e),
            }

    async def handle_web_fetch(
        self,
        params: Dict[str, Any],
        ctx: Optional[ToolExecutionContext] = None,
    ) -> Dict[str, Any]:
        """Busca conteúdo de URL."""
        url = params.get("url", "")
        extract_mode = params.get("extract_mode", "main_content")
        timeout = params.get("timeout", 30)

        try:
            from app.services.url_scraper_service import URLScraperService

            scraper = URLScraperService()
            content = await scraper.fetch(
                url=url,
                extract_mode=extract_mode,
                timeout=timeout,
            )
            return {
                "url": url,
                "content": content,
                "extracted": True,
            }
        except ImportError:
            return {
                "url": url,
                "content": "",
                "note": "URLScraperService não disponível",
            }
        except Exception as e:
            return {
                "url": url,
                "error": str(e),
            }

    # =========================================================================
    # LEGAL DOMAIN HANDLERS
    # =========================================================================

    async def handle_search_jurisprudencia(
        self,
        params: Dict[str, Any],
        ctx: Optional[ToolExecutionContext] = None,
    ) -> Dict[str, Any]:
        """Pesquisa jurisprudência."""
        query = params.get("query", "")
        tribunais = params.get("tribunais", ["todos"])
        data_inicio = params.get("data_inicio")
        data_fim = params.get("data_fim")
        tipo_decisao = params.get("tipo_decisao", "todos")
        max_results = params.get("max_results", 10)

        try:
            from app.services.legislation_service import LegislationService

            service = LegislationService()
            results = await service.search_jurisprudencia(
                query=query,
                tribunais=tribunais,
                data_inicio=data_inicio,
                data_fim=data_fim,
                tipo=tipo_decisao,
                limit=max_results,
            )
            return {
                "query": query,
                "results": results,
                "count": len(results),
                "tribunais": tribunais,
            }
        except ImportError:
            return {
                "query": query,
                "results": [],
                "note": "LegislationService não disponível",
            }
        except Exception as e:
            return {
                "query": query,
                "error": str(e),
            }

    async def handle_search_legislacao(
        self,
        params: Dict[str, Any],
        ctx: Optional[ToolExecutionContext] = None,
    ) -> Dict[str, Any]:
        """Pesquisa legislação."""
        query = params.get("query", "")
        tipo = params.get("tipo", "todos")
        esfera = params.get("esfera", "federal")
        vigente = params.get("vigente", True)

        try:
            from app.services.legislation_service import LegislationService

            service = LegislationService()
            results = await service.search_legislation(
                query=query,
                tipo=tipo,
                esfera=esfera,
                vigente_only=vigente,
            )
            return {
                "query": query,
                "results": results,
                "count": len(results),
            }
        except ImportError:
            return {
                "query": query,
                "results": [],
                "note": "LegislationService não disponível",
            }
        except Exception as e:
            return {
                "query": query,
                "error": str(e),
            }

    async def handle_verify_citation(
        self,
        params: Dict[str, Any],
        ctx: Optional[ToolExecutionContext] = None,
    ) -> Dict[str, Any]:
        """Verifica citação jurisprudencial."""
        citation_text = params.get("citation_text", "")
        expected_source = params.get("expected_source")
        strict_mode = params.get("strict_mode", False)

        try:
            from app.services.ai.citer_verifier import CitationVerifier

            verifier = CitationVerifier()
            result = await verifier.verify(
                citation=citation_text,
                expected_source=expected_source,
                strict=strict_mode,
            )
            return {
                "citation": citation_text[:100] + "..." if len(citation_text) > 100 else citation_text,
                "verified": result.get("verified", False),
                "confidence": result.get("confidence", 0.0),
                "source_found": result.get("source"),
                "issues": result.get("issues", []),
            }
        except ImportError:
            return {
                "citation": citation_text[:100],
                "verified": None,
                "note": "CitationVerifier não disponível",
            }
        except Exception as e:
            return {
                "citation": citation_text[:100],
                "error": str(e),
            }

    async def handle_search_rag(
        self,
        params: Dict[str, Any],
        ctx: Optional[ToolExecutionContext] = None,
    ) -> Dict[str, Any]:
        """Busca no RAG."""
        query = params.get("query", "")
        scope = params.get("scope", "case")
        doc_types = params.get("document_types")
        max_results = params.get("max_results", 10)
        min_score = params.get("min_score", 0.7)

        try:
            from app.services.rag_ingestion import RAGIngestion

            rag = RAGIngestion()

            # Determinar IDs baseado no escopo
            case_id = ctx.case_id if ctx and scope in ["case", "both"] else None
            include_global = scope in ["global", "both"]

            results = await rag.search(
                query=query,
                case_id=case_id,
                include_global=include_global,
                doc_types=doc_types,
                limit=max_results,
                min_score=min_score,
            )
            return {
                "query": query,
                "scope": scope,
                "results": results,
                "count": len(results),
            }
        except ImportError:
            return {
                "query": query,
                "results": [],
                "note": "RAGIngestion não disponível",
            }
        except Exception as e:
            return {
                "query": query,
                "error": str(e),
            }

    async def handle_delegate_research(
        self,
        params: Dict[str, Any],
        ctx: Optional[ToolExecutionContext] = None,
    ) -> Dict[str, Any]:
        """Delega pesquisa paralela."""
        queries = params.get("research_queries", [])
        consolidate = params.get("consolidate", True)
        max_per_source = params.get("max_results_per_source", 5)

        try:
            from app.services.ai.langgraph.subgraphs import run_parallel_research

            results = await run_parallel_research(
                queries=queries,
                case_id=ctx.case_id if ctx else None,
                max_per_source=max_per_source,
            )

            if consolidate:
                # TODO: Consolidar com LLM
                pass

            return {
                "queries": len(queries),
                "results": results,
                "consolidated": consolidate,
            }
        except ImportError:
            # Fallback: executar sequencialmente
            all_results = []
            for q in queries:
                source = q.get("source")
                query = q.get("query")

                if source == "rag":
                    r = await self.handle_search_rag({"query": query}, ctx)
                elif source == "jurisprudencia":
                    r = await self.handle_search_jurisprudencia({"query": query}, ctx)
                elif source == "legislacao":
                    r = await self.handle_search_legislacao({"query": query}, ctx)
                elif source == "web":
                    r = await self.handle_web_search({"query": query}, ctx)
                else:
                    r = {"source": source, "note": "Fonte não suportada"}

                all_results.append({"source": source, "query": query, "result": r})

            return {
                "queries": len(queries),
                "results": all_results,
                "consolidated": False,
                "note": "Executado sequencialmente (subgraph não disponível)",
            }

    # =========================================================================
    # GRAPH ASK HANDLERS
    # =========================================================================

    async def handle_ask_graph(
        self,
        params: Dict[str, Any],
        ctx: Optional[ToolExecutionContext] = None,
    ) -> Dict[str, Any]:
        """
        Executa consulta tipada ao grafo de conhecimento.

        Operações suportadas:
        - path: Caminho entre entidades
        - neighbors: Vizinhos semânticos
        - cooccurrence: Co-ocorrência em documentos
        - search: Busca de entidades
        - count: Contagem com filtros
        """
        operation = params.get("operation", "search")
        operation_params = params.get("params", {})

        # Extrair parâmetros comuns do nível superior se não estiverem em params
        if "source_id" in params and "source_id" not in operation_params:
            operation_params["source_id"] = params["source_id"]
        if "target_id" in params and "target_id" not in operation_params:
            operation_params["target_id"] = params["target_id"]
        if "entity_id" in params and "entity_id" not in operation_params:
            operation_params["entity_id"] = params["entity_id"]
        if "entity1_id" in params and "entity1_id" not in operation_params:
            operation_params["entity1_id"] = params["entity1_id"]
        if "entity2_id" in params and "entity2_id" not in operation_params:
            operation_params["entity2_id"] = params["entity2_id"]
        if "query" in params and "query" not in operation_params:
            operation_params["query"] = params["query"]
        if "limit" in params and "limit" not in operation_params:
            operation_params["limit"] = params["limit"]
        if "max_hops" in params and "max_hops" not in operation_params:
            operation_params["max_hops"] = params["max_hops"]
        if "entity_type" in params and "entity_type" not in operation_params:
            operation_params["entity_type"] = params["entity_type"]

        try:
            from app.services.graph_ask_service import get_graph_ask_service

            service = get_graph_ask_service()

            # Extrair contexto de segurança
            if not ctx or not ctx.tenant_id:
                return {
                    "operation": operation,
                    "success": False,
                    "results": [],
                    "error": "Contexto de execução sem tenant_id (bloqueado por segurança).",
                }

            tenant_id = str(ctx.tenant_id)
            case_id = ctx.case_id
            scope = params.get("scope")
            include_global = bool(params.get("include_global", True))

            result = await service.ask(
                operation=operation,
                params=operation_params,
                tenant_id=tenant_id,
                scope=scope,
                case_id=case_id,
                include_global=include_global,
            )

            return {
                "operation": result.operation,
                "success": result.success,
                "results": result.results[:20],  # Limitar para contexto do agente
                "result_count": result.result_count,
                "execution_time_ms": result.execution_time_ms,
                "error": result.error,
            }

        except ImportError:
            return {
                "operation": operation,
                "success": False,
                "results": [],
                "error": "GraphAskService não disponível",
            }
        except Exception as e:
            logger.error(f"ask_graph handler failed: {e}")
            return {
                "operation": operation,
                "success": False,
                "results": [],
                "error": str(e),
            }

    # =========================================================================
    # MCP HANDLERS
    # =========================================================================

    async def handle_mcp_tool_search(
        self,
        params: Dict[str, Any],
        ctx: Optional[ToolExecutionContext] = None,
    ) -> Dict[str, Any]:
        """Pesquisa tools MCP."""
        query = params.get("query", "")
        server_labels = params.get("server_labels")
        limit = params.get("limit", 20)

        try:
            from app.services.mcp_hub import mcp_hub

            tools = await mcp_hub.search_tools(
                query=query,
                server_labels=server_labels,
                limit=limit,
            )
            return {
                "query": query,
                "tools": tools,
                "count": len(tools),
            }
        except ImportError:
            return {
                "query": query,
                "tools": [],
                "note": "mcp_hub não disponível",
            }
        except Exception as e:
            return {
                "query": query,
                "error": str(e),
            }

    async def handle_mcp_tool_call(
        self,
        params: Dict[str, Any],
        ctx: Optional[ToolExecutionContext] = None,
    ) -> Dict[str, Any]:
        """Executa tool MCP."""
        server_label = params.get("server_label", "")
        tool_name = params.get("tool_name", "")
        arguments = params.get("arguments", {})

        try:
            from app.services.mcp_hub import mcp_hub

            result = await mcp_hub.call_tool(
                server_label=server_label,
                tool_name=tool_name,
                arguments=arguments,
            )
            return {
                "server": server_label,
                "tool": tool_name,
                "result": result,
                "success": True,
            }
        except ImportError:
            return {
                "server": server_label,
                "tool": tool_name,
                "note": "mcp_hub não disponível",
            }
        except Exception as e:
            return {
                "server": server_label,
                "tool": tool_name,
                "error": str(e),
            }


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

# Singleton global
_global_handlers: Optional[ToolHandlers] = None


def get_tool_handlers(context: Optional[ToolExecutionContext] = None) -> ToolHandlers:
    """
    Obtém handlers globais ou cria com contexto.

    Args:
        context: Contexto de execução

    Returns:
        ToolHandlers instance
    """
    global _global_handlers

    if context:
        return ToolHandlers(context)

    if _global_handlers is None:
        _global_handlers = ToolHandlers()

    return _global_handlers


async def execute_tool(
    tool_name: str,
    parameters: Dict[str, Any],
    context: Optional[ToolExecutionContext] = None,
) -> Dict[str, Any]:
    """
    Função de conveniência para executar tool.

    Args:
        tool_name: Nome da tool
        parameters: Parâmetros
        context: Contexto de execução

    Returns:
        Resultado da execução
    """
    handlers = get_tool_handlers(context)
    return await handlers.execute(tool_name, parameters, context)
