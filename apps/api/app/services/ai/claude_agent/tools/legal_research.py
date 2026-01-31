"""
Legal Research Tools for Claude Agent SDK

Tools para pesquisa jurídica: jurisprudência, legislação e doutrina.
Integra com WebSearchService para buscas externas e RAG para bases internas.

v1.0 - 2026-01-26
"""

import asyncio
from typing import Any, Dict, List, Optional
from datetime import datetime
from loguru import logger


# =============================================================================
# TOOL SCHEMAS (Anthropic Tool Use Format)
# =============================================================================

SEARCH_JURISPRUDENCIA_SCHEMA = {
    "name": "search_jurisprudencia",
    "description": """Busca jurisprudência em tribunais brasileiros.

    Use para encontrar:
    - Decisões de tribunais (STF, STJ, TRFs, TJs)
    - Súmulas e teses de repercussão geral
    - Precedentes sobre temas específicos
    - Entendimentos consolidados

    A busca retorna ementas, votos e decisões relevantes com metadados
    como tribunal, relator, data de julgamento e tema.""",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Termo de busca. Ex: 'dano moral relação de consumo CDC'"
            },
            "tribunais": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Lista de tribunais para filtrar. Ex: ['STF', 'STJ', 'TJSP']. Se vazio, busca em todos.",
                "default": []
            },
            "periodo": {
                "type": "object",
                "properties": {
                    "inicio": {
                        "type": "string",
                        "description": "Data inicial no formato YYYY-MM-DD"
                    },
                    "fim": {
                        "type": "string",
                        "description": "Data final no formato YYYY-MM-DD"
                    }
                },
                "description": "Período para filtrar resultados"
            },
            "tipo_decisao": {
                "type": "string",
                "enum": ["acordao", "sumula", "decisao_monocratica", "todos"],
                "description": "Tipo de decisão a buscar",
                "default": "todos"
            },
            "top_k": {
                "type": "integer",
                "description": "Número máximo de resultados",
                "default": 10,
                "minimum": 1,
                "maximum": 50
            }
        },
        "required": ["query"]
    }
}

SEARCH_LEGISLACAO_SCHEMA = {
    "name": "search_legislacao",
    "description": """Busca legislação brasileira consolidada.

    Use para encontrar:
    - Leis federais, estaduais e municipais
    - Constituição Federal e estaduais
    - Decretos e regulamentos
    - Portarias, resoluções e normativas
    - Artigos específicos de leis

    A busca retorna o texto legal com referências a artigos, parágrafos,
    incisos e alíneas, além de metadados como vigência e última atualização.""",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Termo de busca. Ex: 'direito do consumidor arrependimento art 49'"
            },
            "tipo": {
                "type": "string",
                "enum": ["lei", "decreto", "constituicao", "portaria", "resolucao", "todos"],
                "description": "Tipo de legislação",
                "default": "todos"
            },
            "esfera": {
                "type": "string",
                "enum": ["federal", "estadual", "municipal", "todos"],
                "description": "Esfera federativa",
                "default": "federal"
            },
            "vigente": {
                "type": "boolean",
                "description": "Se True, busca apenas legislação vigente",
                "default": True
            },
            "numero": {
                "type": "string",
                "description": "Número da lei específica. Ex: '8.078' para CDC"
            },
            "ano": {
                "type": "integer",
                "description": "Ano da legislação"
            },
            "top_k": {
                "type": "integer",
                "description": "Número máximo de resultados",
                "default": 10,
                "minimum": 1,
                "maximum": 50
            }
        },
        "required": ["query"]
    }
}


# =============================================================================
# TOOL IMPLEMENTATIONS
# =============================================================================

async def search_jurisprudencia(
    query: str,
    tribunais: Optional[List[str]] = None,
    periodo: Optional[Dict[str, str]] = None,
    tipo_decisao: str = "todos",
    top_k: int = 10,
    # Contexto do caso (injetado pelo executor)
    case_id: Optional[str] = None,
    tenant_id: str = "default",
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Busca jurisprudência em tribunais brasileiros.

    Estratégia:
    1. Busca no RAG local (coleção juris) para decisões indexadas
    2. Busca web em portais de tribunais para resultados frescos
    3. Combina e ranqueia resultados por relevância

    Args:
        query: Termo de busca
        tribunais: Lista de tribunais para filtrar
        periodo: Dict com 'inicio' e 'fim' em formato YYYY-MM-DD
        tipo_decisao: Filtro por tipo de decisão
        top_k: Número máximo de resultados
        case_id: ID do caso (para contexto)
        tenant_id: Tenant para multi-tenancy
        user_id: ID do usuário para RBAC

    Returns:
        Dict com resultados formatados
    """
    logger.info(f"[search_jurisprudencia] Query: '{query}', tribunais={tribunais}, tipo={tipo_decisao}")

    results: List[Dict[str, Any]] = []
    errors: List[str] = []

    # 1. Busca no RAG local
    try:
        from app.services.rag_module import create_rag_manager

        rag = create_rag_manager()
        if rag.client is not None:
            # Build filters
            filters = {}
            if tipo_decisao and tipo_decisao != "todos":
                filters["tipo_decisao"] = tipo_decisao
            if tribunais and len(tribunais) > 0:
                # ChromaDB não suporta OR nativo, faremos múltiplas buscas
                pass

            rag_results = rag.hybrid_search(
                query=query,
                sources=["juris"],
                top_k=top_k,
                filters=filters if filters else None,
                tenant_id=tenant_id,
                user_id=user_id,
            )

            for r in rag_results:
                metadata = r.get("metadata", {})
                results.append({
                    "source": "rag_local",
                    "type": "jurisprudencia",
                    "tribunal": metadata.get("tribunal", ""),
                    "numero": metadata.get("numero", ""),
                    "tipo_decisao": metadata.get("tipo_decisao", ""),
                    "relator": metadata.get("relator", ""),
                    "data_julgamento": metadata.get("data_julgamento", ""),
                    "tema": metadata.get("tema", ""),
                    "ementa": r.get("text", "")[:2000],
                    "score": r.get("final_score", 0),
                    "url": metadata.get("url", ""),
                })

            logger.info(f"[search_jurisprudencia] RAG local: {len(rag_results)} resultados")
    except Exception as e:
        logger.warning(f"[search_jurisprudencia] RAG local falhou: {e}")
        errors.append(f"RAG local: {str(e)}")

    # 2. Busca web em portais jurídicos
    try:
        from app.services.web_search_service import web_search_service

        # Adicionar termos jurídicos à query
        search_query = f"{query} jurisprudência"
        if tribunais:
            search_query += f" {' '.join(tribunais)}"

        # Usar filtro de domínios jurídicos
        web_results = await web_search_service.search_legal(
            query=search_query,
            num_results=min(top_k, 15),
            recency_filter=_periodo_to_recency(periodo),
        )

        for r in web_results.get("results", []):
            # Verificar se já não temos este resultado
            url = r.get("url", "")
            if any(existing.get("url") == url for existing in results):
                continue

            # Detectar tribunal do título/URL
            tribunal_detectado = _detect_tribunal(r.get("title", "") + " " + url)

            # Filtrar por tribunal se especificado
            if tribunais and tribunal_detectado and tribunal_detectado not in tribunais:
                continue

            results.append({
                "source": "web_search",
                "type": "jurisprudencia",
                "tribunal": tribunal_detectado or "",
                "numero": _extract_processo_number(r.get("title", "")),
                "tipo_decisao": _detect_tipo_decisao(r.get("title", "") + " " + r.get("snippet", "")),
                "relator": "",
                "data_julgamento": "",
                "tema": "",
                "ementa": r.get("snippet", "")[:2000],
                "score": r.get("score", 0.5),
                "url": url,
                "title": r.get("title", ""),
            })

        logger.info(f"[search_jurisprudencia] Web search: {len(web_results.get('results', []))} resultados")
    except Exception as e:
        logger.warning(f"[search_jurisprudencia] Web search falhou: {e}")
        errors.append(f"Web search: {str(e)}")

    # 3. Ordenar por score e limitar
    results.sort(key=lambda x: x.get("score", 0), reverse=True)
    results = results[:top_k]

    return {
        "success": len(results) > 0 or len(errors) == 0,
        "query": query,
        "filters": {
            "tribunais": tribunais,
            "periodo": periodo,
            "tipo_decisao": tipo_decisao,
        },
        "total": len(results),
        "results": results,
        "errors": errors if errors else None,
        "timestamp": datetime.now().isoformat(),
    }


async def search_legislacao(
    query: str,
    tipo: str = "todos",
    esfera: str = "federal",
    vigente: bool = True,
    numero: Optional[str] = None,
    ano: Optional[int] = None,
    top_k: int = 10,
    # Contexto do caso (injetado pelo executor)
    case_id: Optional[str] = None,
    tenant_id: str = "default",
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Busca legislação brasileira consolidada.

    Estratégia:
    1. Busca no RAG local (coleção lei) para legislação indexada
    2. Busca web em planalto.gov.br e outros portais
    3. Combina e formata resultados

    Args:
        query: Termo de busca
        tipo: Tipo de legislação (lei, decreto, etc.)
        esfera: Esfera federativa
        vigente: Se True, apenas legislação vigente
        numero: Número específico da lei
        ano: Ano da legislação
        top_k: Número máximo de resultados
        case_id: ID do caso (para contexto)
        tenant_id: Tenant para multi-tenancy
        user_id: ID do usuário para RBAC

    Returns:
        Dict com resultados formatados
    """
    logger.info(f"[search_legislacao] Query: '{query}', tipo={tipo}, esfera={esfera}")

    results: List[Dict[str, Any]] = []
    errors: List[str] = []

    # 1. Busca no RAG local
    try:
        from app.services.rag_module import create_rag_manager

        rag = create_rag_manager()
        if rag.client is not None:
            filters = {}
            if tipo and tipo != "todos":
                filters["tipo"] = tipo
            if vigente:
                filters["vigencia"] = "vigente"
            if numero:
                filters["numero"] = numero
            if ano:
                filters["ano"] = ano

            rag_results = rag.hybrid_search(
                query=query,
                sources=["lei"],
                top_k=top_k,
                filters=filters if filters else None,
                tenant_id=tenant_id,
                user_id=user_id,
            )

            for r in rag_results:
                metadata = r.get("metadata", {})
                results.append({
                    "source": "rag_local",
                    "type": "legislacao",
                    "tipo_lei": metadata.get("tipo", ""),
                    "numero": metadata.get("numero", ""),
                    "ano": metadata.get("ano", ""),
                    "jurisdicao": metadata.get("jurisdicao", ""),
                    "artigo": metadata.get("artigo", ""),
                    "vigencia": metadata.get("vigencia", ""),
                    "texto": r.get("text", "")[:2000],
                    "score": r.get("final_score", 0),
                    "url": metadata.get("url", ""),
                })

            logger.info(f"[search_legislacao] RAG local: {len(rag_results)} resultados")
    except Exception as e:
        logger.warning(f"[search_legislacao] RAG local falhou: {e}")
        errors.append(f"RAG local: {str(e)}")

    # 2. Busca web em portais de legislação
    try:
        from app.services.web_search_service import web_search_service

        # Construir query otimizada
        search_query = query
        if numero:
            search_query = f"Lei {numero}"
            if ano:
                search_query += f"/{ano}"
            search_query += f" {query}"

        # Domínios de legislação
        legal_domains = [
            "planalto.gov.br",
            "senado.leg.br",
            "camara.leg.br",
        ]

        web_results = await web_search_service.search(
            query=search_query,
            num_results=min(top_k, 15),
            country="BR",
            domain_filter=legal_domains,
            language_filter=["pt"],
        )

        for r in web_results.get("results", []):
            url = r.get("url", "")
            if any(existing.get("url") == url for existing in results):
                continue

            # Extrair informações do título
            title = r.get("title", "")
            lei_info = _extract_lei_info(title)

            results.append({
                "source": "web_search",
                "type": "legislacao",
                "tipo_lei": lei_info.get("tipo", tipo if tipo != "todos" else ""),
                "numero": lei_info.get("numero", numero or ""),
                "ano": lei_info.get("ano", str(ano) if ano else ""),
                "jurisdicao": _esfera_to_jurisdicao(esfera),
                "artigo": lei_info.get("artigo", ""),
                "vigencia": "vigente" if vigente else "",
                "texto": r.get("snippet", "")[:2000],
                "score": r.get("score", 0.5),
                "url": url,
                "title": title,
            })

        logger.info(f"[search_legislacao] Web search: {len(web_results.get('results', []))} resultados")
    except Exception as e:
        logger.warning(f"[search_legislacao] Web search falhou: {e}")
        errors.append(f"Web search: {str(e)}")

    # 3. Ordenar e limitar
    results.sort(key=lambda x: x.get("score", 0), reverse=True)
    results = results[:top_k]

    return {
        "success": len(results) > 0 or len(errors) == 0,
        "query": query,
        "filters": {
            "tipo": tipo,
            "esfera": esfera,
            "vigente": vigente,
            "numero": numero,
            "ano": ano,
        },
        "total": len(results),
        "results": results,
        "errors": errors if errors else None,
        "timestamp": datetime.now().isoformat(),
    }


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _periodo_to_recency(periodo: Optional[Dict[str, str]]) -> Optional[str]:
    """Converte período para filtro de recência do Perplexity."""
    if not periodo:
        return None

    try:
        inicio = periodo.get("inicio")
        if not inicio:
            return None

        from datetime import datetime, timedelta
        inicio_date = datetime.strptime(inicio, "%Y-%m-%d")
        dias = (datetime.now() - inicio_date).days

        if dias <= 1:
            return "day"
        elif dias <= 7:
            return "week"
        elif dias <= 30:
            return "month"
        elif dias <= 365:
            return "year"
        return None
    except Exception:
        return None


def _detect_tribunal(text: str) -> Optional[str]:
    """Detecta tribunal a partir do texto."""
    import re

    text_upper = text.upper()

    tribunais = [
        ("STF", r"\bSTF\b|SUPREMO\s+TRIBUNAL\s+FEDERAL"),
        ("STJ", r"\bSTJ\b|SUPERIOR\s+TRIBUNAL\s+DE\s+JUSTI[CÇ]A"),
        ("TST", r"\bTST\b|TRIBUNAL\s+SUPERIOR\s+DO\s+TRABALHO"),
        ("TSE", r"\bTSE\b|TRIBUNAL\s+SUPERIOR\s+ELEITORAL"),
        ("STM", r"\bSTM\b|SUPERIOR\s+TRIBUNAL\s+MILITAR"),
        ("TRF1", r"\bTRF[\s-]?1\b|TRF\s+1[ªº]?\s+REGI[ÃA]O"),
        ("TRF2", r"\bTRF[\s-]?2\b|TRF\s+2[ªº]?\s+REGI[ÃA]O"),
        ("TRF3", r"\bTRF[\s-]?3\b|TRF\s+3[ªº]?\s+REGI[ÃA]O"),
        ("TRF4", r"\bTRF[\s-]?4\b|TRF\s+4[ªº]?\s+REGI[ÃA]O"),
        ("TRF5", r"\bTRF[\s-]?5\b|TRF\s+5[ªº]?\s+REGI[ÃA]O"),
        ("TRF6", r"\bTRF[\s-]?6\b|TRF\s+6[ªº]?\s+REGI[ÃA]O"),
        ("TJSP", r"\bTJSP\b|TRIBUNAL\s+DE\s+JUSTI[CÇ]A\s+DE\s+S[ÃA]O\s+PAULO"),
        ("TJRJ", r"\bTJRJ\b|TRIBUNAL\s+DE\s+JUSTI[CÇ]A\s+DO\s+RIO"),
        ("TJMG", r"\bTJMG\b|TRIBUNAL\s+DE\s+JUSTI[CÇ]A\s+DE\s+MINAS"),
        ("TJRS", r"\bTJRS\b|TRIBUNAL\s+DE\s+JUSTI[CÇ]A\s+DO\s+RIO\s+GRANDE\s+DO\s+SUL"),
        ("TJPR", r"\bTJPR\b|TRIBUNAL\s+DE\s+JUSTI[CÇ]A\s+DO\s+PARAN[ÁA]"),
        ("CNJ", r"\bCNJ\b|CONSELHO\s+NACIONAL\s+DE\s+JUSTI[CÇ]A"),
    ]

    for tribunal, pattern in tribunais:
        if re.search(pattern, text_upper):
            return tribunal

    return None


def _detect_tipo_decisao(text: str) -> str:
    """Detecta tipo de decisão a partir do texto."""
    import re

    text_upper = text.upper()

    if re.search(r"\bS[ÚU]MULA\b", text_upper):
        return "sumula"
    if re.search(r"\bAC[ÓO]RD[ÃA]O\b", text_upper):
        return "acordao"
    if re.search(r"\bDECIS[ÃA]O\s+MONOCR[ÁA]TICA\b", text_upper):
        return "decisao_monocratica"
    if re.search(r"\bSENTEN[CÇ]A\b", text_upper):
        return "sentenca"

    return ""


def _extract_processo_number(text: str) -> str:
    """Extrai número de processo do texto."""
    import re

    # Padrões comuns de numeração
    patterns = [
        r"(RE|AI|ARE|ADI|ADPF|HC|MS|RMS|REsp|RHC|AgRg|EDcl|AREsp)\s*[\d.-]+",
        r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}",  # CNJ
        r"Processo\s+n[º°]?\s*[\d.-/]+",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(0).strip()

    return ""


def _extract_lei_info(text: str) -> Dict[str, str]:
    """Extrai informações de lei do texto."""
    import re

    info: Dict[str, str] = {}

    # Tipo de lei
    tipos = [
        (r"\bLEI\s+COMPLEMENTAR\b", "lei_complementar"),
        (r"\bLEI\s+ORDIN[ÁA]RIA\b", "lei"),
        (r"\bLEI\b", "lei"),
        (r"\bDECRETO-LEI\b", "decreto_lei"),
        (r"\bDECRETO\b", "decreto"),
        (r"\bMEDIDA\s+PROVIS[ÓO]RIA\b", "medida_provisoria"),
        (r"\bPORTARIA\b", "portaria"),
        (r"\bRESOLU[ÇC][ÃA]O\b", "resolucao"),
        (r"\bCONSTITUI[ÇC][ÃA]O\b", "constituicao"),
    ]

    text_upper = text.upper()
    for pattern, tipo in tipos:
        if re.search(pattern, text_upper):
            info["tipo"] = tipo
            break

    # Número da lei
    numero_match = re.search(r"(?:Lei|Decreto|Portaria|Resolu[çc][ãa]o)\s*(?:n[º°]?)?\s*([\d.]+)", text, re.IGNORECASE)
    if numero_match:
        info["numero"] = numero_match.group(1)

    # Ano
    ano_match = re.search(r"[/\s](\d{4})\b", text)
    if ano_match:
        info["ano"] = ano_match.group(1)

    # Artigo
    artigo_match = re.search(r"[Aa]rt\.?\s*(\d+)", text)
    if artigo_match:
        info["artigo"] = f"art. {artigo_match.group(1)}"

    return info


def _esfera_to_jurisdicao(esfera: str) -> str:
    """Converte esfera para código de jurisdição."""
    mapping = {
        "federal": "BR",
        "estadual": "UF",
        "municipal": "MUN",
        "todos": "",
    }
    return mapping.get(esfera, "")


# =============================================================================
# TOOL REGISTRY
# =============================================================================

LEGAL_RESEARCH_TOOLS = {
    "search_jurisprudencia": {
        "function": search_jurisprudencia,
        "schema": SEARCH_JURISPRUDENCIA_SCHEMA,
        "permission_default": "allow",  # Leitura, pode executar automaticamente
    },
    "search_legislacao": {
        "function": search_legislacao,
        "schema": SEARCH_LEGISLACAO_SCHEMA,
        "permission_default": "allow",  # Leitura, pode executar automaticamente
    },
}
