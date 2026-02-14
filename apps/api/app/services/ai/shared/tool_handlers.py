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
            "search_jusbrasil": self.handle_search_jusbrasil,
            "search_legislacao": self.handle_search_legislacao,
            "verify_citation": self.handle_verify_citation,
            "validate_cpc_compliance": self.handle_validate_cpc_compliance,
            "search_rag": self.handle_search_rag,
            "create_section": self.handle_create_section,
            # Graph
            "ask_graph": self.handle_ask_graph,
            "scan_graph_risk": self.handle_scan_graph_risk,
            "audit_graph_edge": self.handle_audit_graph_edge,
            "audit_graph_chain": self.handle_audit_graph_chain,
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

    async def handle_search_jusbrasil(
        self,
        params: Dict[str, Any],
        ctx: Optional[ToolExecutionContext] = None,
    ) -> Dict[str, Any]:
        """Pesquisa conteudo juridico no JusBrasil."""
        query = str(params.get("query") or "").strip()
        tribunal = params.get("tribunal")
        tipo = params.get("tipo")
        data_inicio = params.get("data_inicio")
        data_fim = params.get("data_fim")
        max_results = params.get("max_results", 10)
        use_cache = params.get("use_cache", True)

        if not query:
            return {"success": False, "error": "query is required", "results": [], "total": 0}

        try:
            from app.services.jusbrasil_service import jusbrasil_service

            result = await jusbrasil_service.search(
                query=query,
                tribunal=str(tribunal).strip() if tribunal else None,
                tipo=str(tipo).strip() if tipo else None,
                data_inicio=str(data_inicio).strip() if data_inicio else None,
                data_fim=str(data_fim).strip() if data_fim else None,
                max_results=int(max_results),
                use_cache=bool(use_cache),
            )
            return result
        except ImportError:
            return {
                "success": False,
                "query": query,
                "results": [],
                "total": 0,
                "error": "jusbrasil_service not available",
            }
        except Exception as e:
            return {
                "success": False,
                "query": query,
                "results": [],
                "total": 0,
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

    async def handle_validate_cpc_compliance(
        self,
        params: Dict[str, Any],
        ctx: Optional[ToolExecutionContext] = None,
    ) -> Dict[str, Any]:
        """Valida conformidade basica com CPC para a peca enviada."""
        document_text = params.get("document_text") or params.get("text") or ""
        document_type = params.get("document_type", "auto")
        filing_date = params.get("filing_date")
        reference_date = params.get("reference_date")
        strict_raw = params.get("strict_mode", False)
        if isinstance(strict_raw, bool):
            strict_mode = strict_raw
        elif isinstance(strict_raw, str):
            strict_mode = strict_raw.strip().lower() in {"1", "true", "yes", "on", "y"}
        else:
            strict_mode = bool(strict_raw)

        if not str(document_text).strip():
            return {
                "success": False,
                "error": "document_text é obrigatório",
            }

        try:
            from app.services.ai.claude_agent.tools.cpc_validator import (
                validate_cpc_compliance,
            )

            result = await validate_cpc_compliance(
                document_text=str(document_text),
                document_type=str(document_type or "auto"),
                filing_date=str(filing_date) if filing_date else None,
                reference_date=str(reference_date) if reference_date else None,
                strict_mode=strict_mode,
            )
            return result
        except ImportError:
            return {
                "success": False,
                "error": "cpc_validator não disponível",
            }
        except Exception as e:
            return {
                "success": False,
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

        if isinstance(queries, dict):
            queries = [queries]
        if not isinstance(queries, list):
            queries = []
        if not queries and isinstance(params.get("query"), str):
            queries = [{"query": params.get("query"), "source": params.get("source")}]

        try:
            from app.services.ai.langgraph.subgraphs import run_parallel_research

            tasks = []
            normalized_queries: List[Dict[str, str]] = []
            for item in queries:
                if isinstance(item, dict):
                    source = str(item.get("source") or "").strip() or "mixed"
                    query_text = str(item.get("query") or "").strip()
                else:
                    source = "mixed"
                    query_text = str(item or "").strip()

                if not query_text:
                    continue

                normalized_queries.append({"source": source, "query": query_text})
                tasks.append(
                    run_parallel_research(
                        query=query_text,
                        tenant_id=ctx.tenant_id if ctx else None,
                        processo_id=ctx.case_id if ctx else None,
                        top_k=int(max_per_source),
                    )
                )

            raw_results = await asyncio.gather(*tasks, return_exceptions=True) if tasks else []
            results = []
            for query_info, item in zip(normalized_queries, raw_results):
                if isinstance(item, Exception):
                    results.append(
                        {
                            "source": query_info["source"],
                            "query": query_info["query"],
                            "error": str(item),
                        }
                    )
                else:
                    results.append(
                        {
                            "source": query_info["source"],
                            "query": query_info["query"],
                            "result": item,
                        }
                    )

            if consolidate:
                # TODO: Consolidar com LLM
                pass

            return {
                "queries": len(normalized_queries),
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

        # UI-mode guardrail: never allow writes from the LLM stream chat widget.
        # Writes must stay deterministic (/link or explicit non-LLM flows).
        extra = ""
        if ctx and isinstance(getattr(ctx, "services", None), dict):
            extra = str(ctx.services.get("extra_instructions") or "")
        ui_mode = "modo grafo (ui)" in extra.lower()
        if ui_mode and operation in ("link_entities", "recompute_co_menciona"):
            return {
                "operation": operation,
                "success": False,
                "results": [],
                "error": (
                    "Operacao bloqueada no MODO GRAFO (UI). "
                    "Para escrita no grafo, use /link fora do modo LLM."
                ),
            }

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
        if "relation_type" in params and "relation_type" not in operation_params:
            operation_params["relation_type"] = params["relation_type"]
        if "top_n" in params and "top_n" not in operation_params:
            operation_params["top_n"] = params["top_n"]
        if "question" in params and "question" not in operation_params:
            operation_params["question"] = params["question"]
        if "decision_id" in params and "decision_id" not in operation_params:
            operation_params["decision_id"] = params["decision_id"]
        if "relation_filter" in params and "relation_filter" not in operation_params:
            operation_params["relation_filter"] = params["relation_filter"]
        if "source_ids" in params and "source_ids" not in operation_params:
            operation_params["source_ids"] = params["source_ids"]
        if "weight_property" in params and "weight_property" not in operation_params:
            operation_params["weight_property"] = params["weight_property"]
        if "direction" in params and "direction" not in operation_params:
            operation_params["direction"] = params["direction"]
        if "top_k" in params and "top_k" not in operation_params:
            operation_params["top_k"] = params["top_k"]
        if "confirm" in params and "confirm" not in operation_params:
            operation_params["confirm"] = params["confirm"]
        if "preflight_token" in params and "preflight_token" not in operation_params:
            operation_params["preflight_token"] = params["preflight_token"]
        if "node1_id" in params and "node1_id" not in operation_params:
            operation_params["node1_id"] = params["node1_id"]
        if "node2_id" in params and "node2_id" not in operation_params:
            operation_params["node2_id"] = params["node2_id"]
        if "embedding_dimension" in params and "embedding_dimension" not in operation_params:
            operation_params["embedding_dimension"] = params["embedding_dimension"]
        if "iterations" in params and "iterations" not in operation_params:
            operation_params["iterations"] = params["iterations"]

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
                "metadata": result.metadata,
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

    async def handle_scan_graph_risk(
        self,
        params: Dict[str, Any],
        ctx: Optional[ToolExecutionContext] = None,
    ) -> Dict[str, Any]:
        """Executa scan determinístico de risco/fraude no grafo."""
        if not ctx or not ctx.tenant_id:
            return {"success": False, "error": "Contexto sem tenant_id (bloqueado por segurança)."}
        if not ctx.user_id:
            return {"success": False, "error": "Contexto sem user_id (bloqueado por segurança)."}
        if not ctx.db:
            return {"success": False, "error": "Contexto sem db_session (necessário para persistência/relatórios)."}

        try:
            from app.schemas.graph_risk import RiskScanRequest
            from app.services.graph_risk_service import get_graph_risk_service

            req = RiskScanRequest(**(params or {}))
            service = get_graph_risk_service()
            res = await service.scan(
                tenant_id=str(ctx.tenant_id),
                user_id=str(ctx.user_id),
                db=ctx.db,
                request=req,
            )
            return res.model_dump()
        except Exception as e:
            logger.error("scan_graph_risk handler failed: %s", e)
            return {"success": False, "error": str(e)}

    async def handle_audit_graph_edge(
        self,
        params: Dict[str, Any],
        ctx: Optional[ToolExecutionContext] = None,
    ) -> Dict[str, Any]:
        """Audita relação direta e evidências (co-menções) entre duas entidades."""
        if not ctx or not ctx.tenant_id:
            return {"success": False, "error": "Contexto sem tenant_id (bloqueado por segurança)."}
        try:
            from app.schemas.graph_risk import AuditEdgeRequest
            from app.services.graph_risk_service import get_graph_risk_service

            req = AuditEdgeRequest(**(params or {}))
            service = get_graph_risk_service()
            res = await service.audit_edge(tenant_id=str(ctx.tenant_id), request=req)
            return res.model_dump()
        except Exception as e:
            logger.error("audit_graph_edge handler failed: %s", e)
            return {"success": False, "error": str(e)}

    async def handle_audit_graph_chain(
        self,
        params: Dict[str, Any],
        ctx: Optional[ToolExecutionContext] = None,
    ) -> Dict[str, Any]:
        """Audita caminhos multi-hop entre duas entidades."""
        if not ctx or not ctx.tenant_id:
            return {"success": False, "error": "Contexto sem tenant_id (bloqueado por segurança)."}
        try:
            from app.schemas.graph_risk import AuditChainRequest
            from app.services.graph_risk_service import get_graph_risk_service

            req = AuditChainRequest(**(params or {}))
            service = get_graph_risk_service()
            res = await service.audit_chain(tenant_id=str(ctx.tenant_id), request=req)
            return res.model_dump()
        except Exception as e:
            logger.error("audit_graph_chain handler failed: %s", e)
            return {"success": False, "error": str(e)}

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

            payload = await mcp_hub.tool_search(
                query=query,
                server_labels=server_labels,
                limit=limit,
                tenant_id=(str(ctx.tenant_id) if ctx and ctx.tenant_id else None),
            )
            tools = payload.get("matches", []) if isinstance(payload, dict) else []
            return {
                "query": query,
                "tools": tools,
                "count": len(tools),
                "servers_considered": payload.get("servers_considered", []) if isinstance(payload, dict) else [],
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

            result = await mcp_hub.tool_call(
                server_label=server_label,
                tool_name=tool_name,
                arguments=arguments,
                tenant_id=(str(ctx.tenant_id) if ctx and ctx.tenant_id else None),
                user_id=(str(ctx.user_id) if ctx and ctx.user_id else None),
                session_id=(str(ctx.chat_id) if ctx and ctx.chat_id else None),
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
