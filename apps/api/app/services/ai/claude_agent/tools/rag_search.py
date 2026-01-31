"""
RAG Search Tools for Claude Agent SDK

Tools para busca no sistema RAG (Retrieval Augmented Generation) do Iudex.
Permite busca em conhecimento interno e templates de peças jurídicas.

v1.0 - 2026-01-26
"""

import asyncio
from typing import Any, Dict, List, Optional, Literal
from datetime import datetime
from loguru import logger


# =============================================================================
# TOOL SCHEMAS (Anthropic Tool Use Format)
# =============================================================================

SEARCH_RAG_SCHEMA = {
    "name": "search_rag",
    "description": """Busca no sistema RAG interno do Iudex.

    O RAG contém 4 coleções:
    - lei: Legislação consolidada (artigos, leis, decretos)
    - juris: Jurisprudência (ementas, votos, súmulas)
    - sei: Documentos internos (pareceres, notas técnicas)
    - pecas_modelo: Modelos de peças jurídicas aprovadas

    Use para:
    - Buscar conhecimento interno indexado
    - Encontrar documentos relevantes para o caso
    - Recuperar precedentes e modelos anteriores

    Suporta busca híbrida (BM25 + semântica) com reranking.""",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Texto da busca"
            },
            "scope": {
                "type": "string",
                "enum": ["all", "lei", "juris", "sei", "pecas_modelo"],
                "description": "Escopo da busca: todas as coleções ou uma específica",
                "default": "all"
            },
            "top_k": {
                "type": "integer",
                "description": "Número máximo de resultados",
                "default": 10,
                "minimum": 1,
                "maximum": 50
            },
            "filters": {
                "type": "object",
                "description": "Filtros de metadados (tribunal, tipo, área, etc.)",
                "additionalProperties": True
            },
            "use_graph": {
                "type": "boolean",
                "description": "Se True, usa GraphRAG para expandir resultados com entidades relacionadas",
                "default": False
            },
            "use_hyde": {
                "type": "boolean",
                "description": "Se True, usa HyDE (Hypothetical Document Embeddings) para melhor recall",
                "default": False
            },
            "include_global": {
                "type": "boolean",
                "description": "Se True, inclui documentos do escopo global além do tenant",
                "default": True
            }
        },
        "required": ["query"]
    }
}

SEARCH_TEMPLATES_SCHEMA = {
    "name": "search_templates",
    "description": """Busca templates de peças jurídicas aprovadas.

    Templates são modelos de peças que foram utilizadas com sucesso,
    organizadas por tipo e área do direito.

    Use para:
    - Encontrar modelos de petições iniciais
    - Buscar templates de contestações
    - Localizar modelos de recursos
    - Encontrar padrões de cláusulas contratuais

    Retorna blocos reutilizáveis com metadados de aprovação.""",
    "input_schema": {
        "type": "object",
        "properties": {
            "tipo_peca": {
                "type": "string",
                "enum": [
                    "peticao_inicial",
                    "contestacao",
                    "recurso_ordinario",
                    "recurso_especial",
                    "recurso_extraordinario",
                    "agravo",
                    "embargos",
                    "parecer",
                    "contrato",
                    "todos"
                ],
                "description": "Tipo de peça a buscar",
                "default": "todos"
            },
            "area": {
                "type": "string",
                "enum": [
                    "civil",
                    "tributario",
                    "trabalhista",
                    "administrativo",
                    "consumidor",
                    "empresarial",
                    "penal",
                    "todos"
                ],
                "description": "Área do direito",
                "default": "todos"
            },
            "query": {
                "type": "string",
                "description": "Termo de busca adicional para filtrar templates"
            },
            "top_k": {
                "type": "integer",
                "description": "Número máximo de templates",
                "default": 5,
                "minimum": 1,
                "maximum": 20
            },
            "only_approved": {
                "type": "boolean",
                "description": "Se True, retorna apenas templates aprovados",
                "default": True
            },
            "include_clauses": {
                "type": "boolean",
                "description": "Se True, inclui blocos de cláusulas além de peças completas",
                "default": True
            }
        }
    }
}


# =============================================================================
# TOOL IMPLEMENTATIONS
# =============================================================================

async def search_rag(
    query: str,
    scope: str = "all",
    top_k: int = 10,
    filters: Optional[Dict[str, Any]] = None,
    use_graph: bool = False,
    use_hyde: bool = False,
    include_global: bool = True,
    # Contexto do caso (injetado pelo executor)
    case_id: Optional[str] = None,
    tenant_id: str = "default",
    user_id: Optional[str] = None,
    group_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Busca no sistema RAG interno do Iudex.

    Estratégia:
    1. Se use_hyde=True, gera documento hipotético para melhor embedding
    2. Busca híbrida (BM25 + semântica) nas coleções selecionadas
    3. Se use_graph=True, expande resultados com GraphRAG
    4. Aplica reranking e retorna resultados formatados

    Args:
        query: Texto da busca
        scope: Escopo (all, lei, juris, sei, pecas_modelo)
        top_k: Número máximo de resultados
        filters: Filtros de metadados
        use_graph: Se True, usa GraphRAG
        use_hyde: Se True, usa HyDE
        include_global: Se True, inclui escopo global
        case_id: ID do caso
        tenant_id: Tenant para multi-tenancy
        user_id: ID do usuário para RBAC
        group_ids: IDs de grupos para escopo de grupo

    Returns:
        Dict com resultados formatados
    """
    logger.info(f"[search_rag] Query: '{query}', scope={scope}, graph={use_graph}")

    results: List[Dict[str, Any]] = []
    errors: List[str] = []
    hyde_doc = None

    # 1. Aplicar HyDE se solicitado
    if use_hyde:
        try:
            from app.services.ai.rag_helpers import generate_hypothetical_document

            hyde_doc = await generate_hypothetical_document(query)
            if hyde_doc:
                logger.info(f"[search_rag] HyDE gerado: {len(hyde_doc)} chars")
        except Exception as e:
            logger.warning(f"[search_rag] HyDE falhou: {e}")
            errors.append(f"HyDE: {str(e)}")

    # 2. Busca no RAG
    try:
        from app.services.rag_module import create_rag_manager

        rag = create_rag_manager()
        if rag.client is None:
            return {
                "success": False,
                "error": "RAG não disponível (dependências não instaladas)",
                "query": query,
            }

        # Determinar fontes
        if scope == "all":
            sources = rag.COLLECTIONS
        else:
            sources = [scope]

        # Query principal ou HyDE
        search_query = hyde_doc if hyde_doc else query

        # Busca híbrida
        if use_hyde and hyde_doc:
            # HyDE prioriza semântica
            rag_results = rag.hyde_search(
                query=search_query,
                sources=sources,
                top_k=top_k,
                filters=filters,
                user_id=user_id,
                tenant_id=tenant_id,
                group_ids=group_ids,
                include_global=include_global,
            )
        else:
            # Busca híbrida normal
            rag_results = rag.hybrid_search(
                query=search_query,
                sources=sources,
                top_k=top_k,
                filters=filters,
                user_id=user_id,
                tenant_id=tenant_id,
                group_ids=group_ids,
                include_global=include_global,
            )

        # Formatar resultados
        for r in rag_results:
            metadata = r.get("metadata", {})
            results.append({
                "source": r.get("source", "unknown"),
                "scope": r.get("scope", "private"),
                "text": r.get("text", "")[:1500],
                "score": r.get("final_score", 0),
                "rerank_score": r.get("rerank_score"),
                "metadata": _format_metadata(metadata, r.get("source")),
                "collection": r.get("collection", ""),
            })

        logger.info(f"[search_rag] Encontrados: {len(results)} resultados")

    except Exception as e:
        logger.error(f"[search_rag] Erro na busca RAG: {e}")
        errors.append(f"RAG search: {str(e)}")

    # 3. Expandir com GraphRAG se solicitado
    graph_expansions = []
    if use_graph and results:
        try:
            graph_expansions = await _expand_with_graph(
                results=results,
                query=query,
                tenant_id=tenant_id,
            )
            logger.info(f"[search_rag] GraphRAG: {len(graph_expansions)} expansões")
        except Exception as e:
            logger.warning(f"[search_rag] GraphRAG falhou: {e}")
            errors.append(f"GraphRAG: {str(e)}")

    return {
        "success": len(results) > 0 or len(errors) == 0,
        "query": query,
        "hyde_applied": bool(hyde_doc),
        "graph_applied": len(graph_expansions) > 0,
        "scope": scope,
        "total": len(results),
        "results": results,
        "graph_expansions": graph_expansions if graph_expansions else None,
        "errors": errors if errors else None,
        "timestamp": datetime.now().isoformat(),
    }


async def search_templates(
    tipo_peca: str = "todos",
    area: str = "todos",
    query: Optional[str] = None,
    top_k: int = 5,
    only_approved: bool = True,
    include_clauses: bool = True,
    # Contexto do caso (injetado pelo executor)
    case_id: Optional[str] = None,
    tenant_id: str = "default",
    user_id: Optional[str] = None,
    group_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Busca templates de peças jurídicas aprovadas.

    Estratégia:
    1. Busca na coleção pecas_modelo com filtros
    2. Opcionalmente inclui blocos de cláusulas (clause_bank)
    3. Ordena por relevância e aprovação
    4. Formata para uso pelo agente

    Args:
        tipo_peca: Tipo de peça (peticao_inicial, contestacao, etc.)
        area: Área do direito
        query: Termo de busca adicional
        top_k: Número máximo de templates
        only_approved: Se True, apenas aprovados
        include_clauses: Se True, inclui blocos de cláusulas
        case_id: ID do caso
        tenant_id: Tenant para multi-tenancy
        user_id: ID do usuário
        group_ids: IDs de grupos

    Returns:
        Dict com templates encontrados
    """
    logger.info(f"[search_templates] tipo={tipo_peca}, area={area}")

    results: List[Dict[str, Any]] = []
    errors: List[str] = []

    try:
        from app.services.rag_module import create_rag_manager

        rag = create_rag_manager()
        if rag.client is None:
            return {
                "success": False,
                "error": "RAG não disponível",
                "tipo_peca": tipo_peca,
                "area": area,
            }

        # Construir filtros
        filters: Dict[str, Any] = {}

        if tipo_peca and tipo_peca != "todos":
            filters["tipo_peca"] = tipo_peca

        if area and area != "todos":
            filters["area"] = area

        if only_approved:
            filters["aprovado"] = "True"

        # Construir query
        search_query = query if query else f"{tipo_peca} {area}".strip()
        if search_query == "todos todos":
            search_query = "modelo peça jurídica"

        # Busca principal em pecas_modelo
        rag_results = rag.hybrid_search(
            query=search_query,
            sources=["pecas_modelo"],
            top_k=top_k,
            filters=filters if filters else None,
            user_id=user_id,
            tenant_id=tenant_id,
            group_ids=group_ids,
            include_global=True,
            tipo_peca_filter=tipo_peca if tipo_peca != "todos" else None,
        )

        for r in rag_results:
            metadata = r.get("metadata", {})
            results.append({
                "type": "template",
                "source": r.get("source", "pecas_modelo"),
                "tipo_peca": metadata.get("tipo_peca", ""),
                "area": metadata.get("area", ""),
                "rito": metadata.get("rito", ""),
                "tribunal_destino": metadata.get("tribunal_destino", ""),
                "tese": metadata.get("tese", ""),
                "resultado": metadata.get("resultado", ""),
                "versao": metadata.get("versao", ""),
                "aprovado": metadata.get("aprovado") == "True",
                "content": r.get("text", "")[:2000],
                "score": r.get("final_score", 0),
            })

        # Buscar cláusulas se solicitado
        if include_clauses:
            clause_results = await _search_clauses(
                tipo_peca=tipo_peca,
                area=area,
                query=search_query,
                top_k=top_k,
                rag=rag,
                tenant_id=tenant_id,
                user_id=user_id,
            )
            for clause in clause_results:
                # Evitar duplicatas
                if not any(r.get("content", "")[:100] == clause.get("content", "")[:100] for r in results):
                    results.append(clause)

        # Ordenar por score
        results.sort(key=lambda x: x.get("score", 0), reverse=True)
        results = results[:top_k]

        logger.info(f"[search_templates] Encontrados: {len(results)} templates")

    except Exception as e:
        logger.error(f"[search_templates] Erro: {e}")
        errors.append(str(e))

    return {
        "success": len(results) > 0 or len(errors) == 0,
        "tipo_peca": tipo_peca,
        "area": area,
        "query": query,
        "total": len(results),
        "templates": results,
        "errors": errors if errors else None,
        "timestamp": datetime.now().isoformat(),
    }


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _format_metadata(metadata: Dict[str, Any], source: str) -> Dict[str, Any]:
    """Formata metadados de acordo com o tipo de fonte."""
    formatted: Dict[str, Any] = {}

    if source == "lei":
        formatted = {
            "tipo": metadata.get("tipo", ""),
            "numero": metadata.get("numero", ""),
            "ano": metadata.get("ano", ""),
            "jurisdicao": metadata.get("jurisdicao", ""),
            "artigo": metadata.get("artigo", ""),
            "vigencia": metadata.get("vigencia", ""),
        }
    elif source == "juris":
        formatted = {
            "tribunal": metadata.get("tribunal", ""),
            "numero": metadata.get("numero", ""),
            "tipo_decisao": metadata.get("tipo_decisao", ""),
            "relator": metadata.get("relator", ""),
            "data_julgamento": metadata.get("data_julgamento", ""),
            "tema": metadata.get("tema", ""),
        }
    elif source == "sei":
        formatted = {
            "processo_sei": metadata.get("processo_sei", ""),
            "tipo_documento": metadata.get("tipo_documento", ""),
            "orgao": metadata.get("orgao", ""),
            "unidade": metadata.get("unidade", ""),
            "data_criacao": metadata.get("data_criacao", ""),
        }
    elif source == "pecas_modelo":
        formatted = {
            "tipo_peca": metadata.get("tipo_peca", ""),
            "area": metadata.get("area", ""),
            "rito": metadata.get("rito", ""),
            "tribunal_destino": metadata.get("tribunal_destino", ""),
            "tese": metadata.get("tese", ""),
            "versao": metadata.get("versao", ""),
            "aprovado": metadata.get("aprovado", ""),
        }
    else:
        # Genérico
        formatted = {k: v for k, v in metadata.items() if v and k not in (
            "doc_hash", "source_hash", "chunk_index", "ingested_at"
        )}

    return formatted


async def _expand_with_graph(
    results: List[Dict[str, Any]],
    query: str,
    tenant_id: str,
) -> List[Dict[str, Any]]:
    """Expande resultados usando GraphRAG."""
    expansions: List[Dict[str, Any]] = []

    try:
        from app.services.rag_module import get_scoped_knowledge_graph

        graph = get_scoped_knowledge_graph(scope="private", scope_id=tenant_id)
        if graph is None:
            return []

        # Extrair entidades dos resultados
        entities_found = set()
        for r in results[:5]:  # Limitar para performance
            text = r.get("text", "")
            metadata = r.get("metadata", {})

            # Entidades de jurisprudência
            if metadata.get("tribunal"):
                entities_found.add(f"tribunal:{metadata['tribunal']}")
            if metadata.get("numero"):
                entities_found.add(f"processo:{metadata['numero']}")

            # Entidades de legislação
            if metadata.get("tipo") and metadata.get("numero"):
                entities_found.add(f"lei:{metadata['tipo']}_{metadata['numero']}")

        # Buscar relacionamentos no grafo
        for entity_id in list(entities_found)[:10]:
            try:
                neighbors = graph.get_neighbors(entity_id, max_hops=2)
                for neighbor in neighbors[:3]:
                    expansions.append({
                        "type": "graph_expansion",
                        "source_entity": entity_id,
                        "related_entity": neighbor.get("id"),
                        "relationship": neighbor.get("relationship"),
                        "label": neighbor.get("label"),
                        "confidence": neighbor.get("weight", 0.5),
                    })
            except Exception:
                continue

    except Exception as e:
        logger.warning(f"[_expand_with_graph] Erro: {e}")

    return expansions


async def _search_clauses(
    tipo_peca: str,
    area: str,
    query: str,
    top_k: int,
    rag,
    tenant_id: str,
    user_id: Optional[str],
) -> List[Dict[str, Any]]:
    """Busca blocos de cláusulas."""
    clauses: List[Dict[str, Any]] = []

    try:
        # Mapear tipo de peça para tipos de bloco
        bloco_map = {
            "peticao_inicial": ["preliminar", "merito", "pedido", "fundamentacao"],
            "contestacao": ["preliminar", "merito", "impugnacao"],
            "recurso_ordinario": ["razoes", "pedido", "fundamentacao"],
            "recurso_especial": ["razoes", "prequestionamento", "fundamentacao"],
            "recurso_extraordinario": ["razoes", "repercussao_geral", "fundamentacao"],
        }

        blocos = bloco_map.get(tipo_peca, ["merito", "fundamentacao"])

        # Buscar cada tipo de bloco
        for bloco in blocos[:2]:  # Limitar para performance
            filters = {
                "tipo_bloco": bloco,
                "status": "aprovado",
            }
            if area and area != "todos":
                filters["area"] = area

            results = rag.hybrid_search(
                query=f"{bloco} {query}",
                sources=["pecas_modelo"],
                top_k=top_k // 2,
                filters=filters,
                user_id=user_id,
                tenant_id=tenant_id,
                include_global=True,
            )

            for r in results:
                metadata = r.get("metadata", {})
                if metadata.get("source_type") == "clause_bank":
                    clauses.append({
                        "type": "clause",
                        "source": "clause_bank",
                        "tipo_bloco": metadata.get("tipo_bloco", ""),
                        "subtipo": metadata.get("subtipo", ""),
                        "tipo_peca": metadata.get("tipo_peca", ""),
                        "area": metadata.get("area", ""),
                        "tribunal": metadata.get("tribunal", ""),
                        "status": metadata.get("status", ""),
                        "sucesso": metadata.get("sucesso") == "True",
                        "content": r.get("text", "")[:1500],
                        "score": r.get("final_score", 0),
                    })

    except Exception as e:
        logger.warning(f"[_search_clauses] Erro: {e}")

    return clauses


# =============================================================================
# TOOL REGISTRY
# =============================================================================

RAG_SEARCH_TOOLS = {
    "search_rag": {
        "function": search_rag,
        "schema": SEARCH_RAG_SCHEMA,
        "permission_default": "allow",  # Leitura, pode executar automaticamente
    },
    "search_templates": {
        "function": search_templates,
        "schema": SEARCH_TEMPLATES_SCHEMA,
        "permission_default": "allow",  # Leitura, pode executar automaticamente
    },
}
