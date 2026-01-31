"""
Citation Verifier Tools for Claude Agent SDK

Tools para verificação e busca de citações jurídicas.
Garante que afirmações no documento tenham fontes válidas.

v1.0 - 2026-01-26
"""

import asyncio
import re
from typing import Any, Dict, List, Optional, Literal
from datetime import datetime
from loguru import logger


# =============================================================================
# TOOL SCHEMAS (Anthropic Tool Use Format)
# =============================================================================

VERIFY_CITATION_SCHEMA = {
    "name": "verify_citation",
    "description": """Verifica se uma citação jurídica é válida e existente.

    Use para:
    - Verificar se uma jurisprudência citada existe
    - Confirmar se uma lei/artigo está correto
    - Validar referências doutrinárias
    - Checar se súmulas e teses estão atualizadas

    A verificação busca a fonte original e retorna se está correta,
    com sugestões de correção quando necessário.""",
    "input_schema": {
        "type": "object",
        "properties": {
            "citation_text": {
                "type": "string",
                "description": "Texto da citação a verificar. Ex: 'STJ, REsp 1.234.567/SP, Rel. Min. Fulano'"
            },
            "source_type": {
                "type": "string",
                "enum": ["jurisprudencia", "legislacao", "doutrina", "sumula", "auto"],
                "description": "Tipo da fonte citada. Use 'auto' para detecção automática.",
                "default": "auto"
            },
            "context": {
                "type": "string",
                "description": "Contexto onde a citação aparece (trecho do documento)"
            },
            "strict_mode": {
                "type": "boolean",
                "description": "Se True, exige correspondência exata. Se False, aceita variações.",
                "default": False
            }
        },
        "required": ["citation_text"]
    }
}

FIND_CITATION_SOURCE_SCHEMA = {
    "name": "find_citation_source",
    "description": """Encontra a fonte adequada para uma afirmação jurídica.

    Use para:
    - Encontrar jurisprudência que suporte um argumento
    - Localizar a lei que fundamenta uma afirmação
    - Buscar doutrina sobre um tema
    - Identificar precedentes relevantes

    A busca analisa a afirmação e retorna fontes adequadas com
    nível de confiança e relevância.""",
    "input_schema": {
        "type": "object",
        "properties": {
            "claim": {
                "type": "string",
                "description": "Afirmação jurídica que precisa de fonte. Ex: 'O prazo prescricional é de 5 anos'"
            },
            "preferred_source": {
                "type": "string",
                "enum": ["jurisprudencia", "legislacao", "doutrina", "any"],
                "description": "Tipo preferido de fonte",
                "default": "any"
            },
            "area_direito": {
                "type": "string",
                "enum": [
                    "civil",
                    "penal",
                    "trabalhista",
                    "tributario",
                    "administrativo",
                    "constitucional",
                    "consumidor",
                    "empresarial",
                    "ambiental",
                    "auto"
                ],
                "description": "Área do direito para filtrar resultados",
                "default": "auto"
            },
            "top_k": {
                "type": "integer",
                "description": "Número máximo de fontes a retornar",
                "default": 5,
                "minimum": 1,
                "maximum": 20
            },
            "min_confidence": {
                "type": "number",
                "description": "Confiança mínima para incluir resultado (0-1)",
                "default": 0.5,
                "minimum": 0,
                "maximum": 1
            }
        },
        "required": ["claim"]
    }
}


# =============================================================================
# CITATION PATTERNS
# =============================================================================

# Padrões de citação jurídica
JURISPRUDENCIA_PATTERNS = [
    # STF/STJ com número de processo
    r"(?P<tribunal>STF|STJ|TST|TSE|STM),?\s*(?P<tipo>RE|AI|ARE|ADI|ADPF|HC|MS|RMS|REsp|RHC|AgRg|EDcl|AREsp|Rcl|RCL|AP|Inq)[\s.]*(?P<numero>[\d./-]+)",
    # Súmulas
    r"S[úu]mula\s*(?:n[º°]?\s*)?(?P<numero>\d+)\s*(?:do\s*)?(?P<tribunal>STF|STJ|TST|TSE|TRF|TJ\w*)?",
    # Temas de Repercussão Geral
    r"(?:Tema|RG)\s*(?:n[º°]?\s*)?(?P<numero>\d+)\s*(?:do\s*)?(?P<tribunal>STF|STJ)?",
    # Formato CNJ
    r"(?P<numero>\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4})",
    # TRFs e TJs
    r"(?P<tribunal>TRF[\s-]?\d|TJ[A-Z]{2}),?\s*(?P<tipo>AC|AI|AgRg|MS|REO)?[\s.]*(?P<numero>[\d./-]+)",
]

LEGISLACAO_PATTERNS = [
    # Lei com número e ano
    r"Lei\s*(?:n[º°]?\s*)?(?P<numero>[\d.]+)(?:\s*/\s*|\s*,?\s*de\s*)(?P<ano>\d{4})",
    # Código Civil, Penal, etc.
    r"(?P<codigo>C[óo]digo\s+(?:Civil|Penal|Processo\s+Civil|Processo\s+Penal|Trabalho|Tribut[áa]rio|Defesa\s+do\s+Consumidor|Tr[âa]nsito))",
    # Constituição
    r"(?P<norma>Constitui[çc][ãa]o\s+Federal|CF(?:/\d{4})?)",
    # Artigo específico
    r"[Aa]rt(?:igo)?\.?\s*(?P<artigo>\d+)\s*(?:,\s*§\s*(?P<paragrafo>\d+))?(?:,\s*(?:inciso\s+)?(?P<inciso>[IVXLCDM]+))?",
    # Decreto
    r"Decreto(?:-Lei)?\s*(?:n[º°]?\s*)?(?P<numero>[\d.]+)(?:\s*/\s*|\s*,?\s*de\s*)(?P<ano>\d{4})",
    # CDC (referência comum)
    r"CDC\s*(?:,?\s*[Aa]rt\.?\s*(?P<artigo>\d+))?",
    # CLT
    r"CLT\s*(?:,?\s*[Aa]rt\.?\s*(?P<artigo>\d+))?",
]

DOUTRINA_PATTERNS = [
    # Autor e obra
    r"(?P<autor>[A-Z][a-záàâãéèêíïóôõöúç]+(?:\s+[A-Z][a-záàâãéèêíïóôõöúç]+)+),\s*(?P<obra>[^,]+),\s*(?P<ano>\d{4})",
    # In: Referência de coletânea
    r"[Ii]n:\s*(?P<obra>[^.]+)\.\s*(?P<editora>[^,]+),\s*(?P<ano>\d{4})",
]


# =============================================================================
# TOOL IMPLEMENTATIONS
# =============================================================================

async def verify_citation(
    citation_text: str,
    source_type: str = "auto",
    context: Optional[str] = None,
    strict_mode: bool = False,
    # Contexto do caso (injetado pelo executor)
    case_id: Optional[str] = None,
    tenant_id: str = "default",
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Verifica se uma citação jurídica é válida e existente.

    Estratégia:
    1. Detectar tipo de citação (se auto)
    2. Extrair componentes da citação (tribunal, número, etc.)
    3. Buscar no RAG local
    4. Buscar na web para confirmação
    5. Comparar e retornar resultado

    Args:
        citation_text: Texto da citação a verificar
        source_type: Tipo da fonte (jurisprudencia, legislacao, etc.)
        context: Contexto onde a citação aparece
        strict_mode: Se True, exige correspondência exata
        case_id: ID do caso
        tenant_id: Tenant para multi-tenancy
        user_id: ID do usuário

    Returns:
        Dict com resultado da verificação
    """
    logger.info(f"[verify_citation] Verificando: '{citation_text[:100]}...'")

    # 1. Detectar tipo se auto
    if source_type == "auto":
        source_type = _detect_source_type(citation_text)
        logger.info(f"[verify_citation] Tipo detectado: {source_type}")

    # 2. Extrair componentes
    components = _extract_citation_components(citation_text, source_type)

    if not components:
        return {
            "success": False,
            "valid": False,
            "citation_text": citation_text,
            "source_type": source_type,
            "error": "Não foi possível identificar os componentes da citação",
            "suggestions": _suggest_citation_format(source_type),
        }

    # 3. Buscar no RAG local
    rag_result = await _search_rag_for_citation(components, source_type, tenant_id, user_id)

    # 4. Buscar na web para confirmação
    web_result = await _search_web_for_citation(components, source_type)

    # 5. Analisar resultados
    verification = _analyze_verification_results(
        citation_text=citation_text,
        components=components,
        rag_result=rag_result,
        web_result=web_result,
        strict_mode=strict_mode,
    )

    return {
        "success": True,
        "valid": verification["valid"],
        "confidence": verification["confidence"],
        "citation_text": citation_text,
        "source_type": source_type,
        "components": components,
        "verification": verification,
        "sources_found": {
            "rag": rag_result.get("found", False),
            "web": web_result.get("found", False),
        },
        "suggestions": verification.get("suggestions", []),
        "correct_citation": verification.get("correct_citation"),
        "timestamp": datetime.now().isoformat(),
    }


async def find_citation_source(
    claim: str,
    preferred_source: str = "any",
    area_direito: str = "auto",
    top_k: int = 5,
    min_confidence: float = 0.5,
    # Contexto do caso (injetado pelo executor)
    case_id: Optional[str] = None,
    tenant_id: str = "default",
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Encontra a fonte adequada para uma afirmação jurídica.

    Estratégia:
    1. Analisar a afirmação para identificar conceitos-chave
    2. Detectar área do direito (se auto)
    3. Buscar em múltiplas fontes (RAG + web)
    4. Ranquear por relevância e confiança
    5. Retornar fontes formatadas

    Args:
        claim: Afirmação jurídica que precisa de fonte
        preferred_source: Tipo preferido de fonte
        area_direito: Área do direito para filtrar
        top_k: Número máximo de fontes
        min_confidence: Confiança mínima
        case_id: ID do caso
        tenant_id: Tenant para multi-tenancy
        user_id: ID do usuário

    Returns:
        Dict com fontes encontradas
    """
    logger.info(f"[find_citation_source] Buscando fonte para: '{claim[:100]}...'")

    # 1. Analisar afirmação
    keywords = _extract_legal_keywords(claim)

    # 2. Detectar área do direito
    if area_direito == "auto":
        area_direito = _detect_area_direito(claim, keywords)
        logger.info(f"[find_citation_source] Área detectada: {area_direito}")

    sources: List[Dict[str, Any]] = []

    # 3. Buscar jurisprudência
    if preferred_source in ("any", "jurisprudencia"):
        juris_results = await _search_jurisprudencia_for_claim(
            claim=claim,
            keywords=keywords,
            area=area_direito,
            tenant_id=tenant_id,
            user_id=user_id,
            top_k=top_k,
        )
        sources.extend(juris_results)

    # 4. Buscar legislação
    if preferred_source in ("any", "legislacao"):
        leg_results = await _search_legislacao_for_claim(
            claim=claim,
            keywords=keywords,
            area=area_direito,
            tenant_id=tenant_id,
            user_id=user_id,
            top_k=top_k,
        )
        sources.extend(leg_results)

    # 5. Buscar doutrina (se disponível)
    if preferred_source in ("any", "doutrina"):
        doutrina_results = await _search_doutrina_for_claim(
            claim=claim,
            keywords=keywords,
            area=area_direito,
            top_k=top_k,
        )
        sources.extend(doutrina_results)

    # 6. Filtrar por confiança mínima e ordenar
    sources = [s for s in sources if s.get("confidence", 0) >= min_confidence]
    sources.sort(key=lambda x: x.get("confidence", 0), reverse=True)
    sources = sources[:top_k]

    # 7. Formatar citações
    for source in sources:
        source["formatted_citation"] = _format_citation(source)

    return {
        "success": len(sources) > 0,
        "claim": claim,
        "area_direito": area_direito,
        "keywords_extracted": keywords,
        "total_found": len(sources),
        "sources": sources,
        "best_match": sources[0] if sources else None,
        "timestamp": datetime.now().isoformat(),
    }


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _detect_source_type(text: str) -> str:
    """Detecta o tipo de fonte a partir do texto da citação."""
    text_upper = text.upper()

    # Verificar jurisprudência
    for pattern in JURISPRUDENCIA_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return "jurisprudencia"

    # Verificar súmula
    if re.search(r"S[ÚU]MULA", text_upper):
        return "sumula"

    # Verificar legislação
    for pattern in LEGISLACAO_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return "legislacao"

    # Verificar doutrina
    for pattern in DOUTRINA_PATTERNS:
        if re.search(pattern, text):
            return "doutrina"

    return "jurisprudencia"  # Default


def _extract_citation_components(text: str, source_type: str) -> Dict[str, Any]:
    """Extrai componentes da citação."""
    components: Dict[str, Any] = {"raw": text}

    if source_type in ("jurisprudencia", "sumula"):
        for pattern in JURISPRUDENCIA_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                components.update(match.groupdict())
                break

    elif source_type == "legislacao":
        for pattern in LEGISLACAO_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                components.update(match.groupdict())
                break

    elif source_type == "doutrina":
        for pattern in DOUTRINA_PATTERNS:
            match = re.search(pattern, text)
            if match:
                components.update(match.groupdict())
                break

    # Limpar valores None
    components = {k: v for k, v in components.items() if v is not None}

    return components if len(components) > 1 else {}


async def _search_rag_for_citation(
    components: Dict[str, Any],
    source_type: str,
    tenant_id: str,
    user_id: Optional[str],
) -> Dict[str, Any]:
    """Busca citação no RAG local."""
    try:
        from app.services.rag_module import create_rag_manager

        rag = create_rag_manager()
        if rag.client is None:
            return {"found": False, "error": "RAG não disponível"}

        # Construir query baseada nos componentes
        query_parts = []
        if components.get("tribunal"):
            query_parts.append(components["tribunal"])
        if components.get("numero"):
            query_parts.append(components["numero"])
        if components.get("tipo"):
            query_parts.append(components["tipo"])
        if components.get("codigo"):
            query_parts.append(components["codigo"])
        if components.get("artigo"):
            query_parts.append(f"art. {components['artigo']}")

        if not query_parts:
            query_parts.append(components.get("raw", ""))

        query = " ".join(query_parts)

        # Determinar fonte
        source_map = {
            "jurisprudencia": ["juris"],
            "sumula": ["juris"],
            "legislacao": ["lei"],
            "doutrina": ["doutrina"] if "doutrina" in rag.COLLECTIONS else ["pecas_modelo"],
        }
        sources = source_map.get(source_type, ["lei", "juris"])

        results = rag.hybrid_search(
            query=query,
            sources=sources,
            top_k=5,
            tenant_id=tenant_id,
            user_id=user_id,
        )

        if results:
            best = results[0]
            return {
                "found": True,
                "score": best.get("final_score", 0),
                "text": best.get("text", "")[:500],
                "metadata": best.get("metadata", {}),
            }

        return {"found": False}

    except Exception as e:
        logger.warning(f"[_search_rag_for_citation] Erro: {e}")
        return {"found": False, "error": str(e)}


async def _search_web_for_citation(
    components: Dict[str, Any],
    source_type: str,
) -> Dict[str, Any]:
    """Busca citação na web para confirmação."""
    try:
        from app.services.web_search_service import web_search_service

        # Construir query
        query_parts = []
        if components.get("tribunal"):
            query_parts.append(components["tribunal"])
        if components.get("tipo"):
            query_parts.append(components["tipo"])
        if components.get("numero"):
            query_parts.append(components["numero"])
        if components.get("codigo"):
            query_parts.append(components["codigo"])

        if not query_parts:
            query_parts.append(components.get("raw", "")[:100])

        query = " ".join(query_parts)

        # Usar busca jurídica
        results = await web_search_service.search_legal(
            query=query,
            num_results=5,
        )

        if results.get("results"):
            best = results["results"][0]
            return {
                "found": True,
                "title": best.get("title", ""),
                "url": best.get("url", ""),
                "snippet": best.get("snippet", ""),
            }

        return {"found": False}

    except Exception as e:
        logger.warning(f"[_search_web_for_citation] Erro: {e}")
        return {"found": False, "error": str(e)}


def _analyze_verification_results(
    citation_text: str,
    components: Dict[str, Any],
    rag_result: Dict[str, Any],
    web_result: Dict[str, Any],
    strict_mode: bool,
) -> Dict[str, Any]:
    """Analisa resultados de verificação e determina validade."""
    valid = False
    confidence = 0.0
    suggestions: List[str] = []
    correct_citation = None

    rag_found = rag_result.get("found", False)
    web_found = web_result.get("found", False)

    if rag_found and web_found:
        valid = True
        confidence = 0.95
    elif rag_found:
        valid = True
        confidence = 0.75
        suggestions.append("Citação encontrada no banco local, confirme com fonte oficial")
    elif web_found:
        valid = not strict_mode
        confidence = 0.6
        if strict_mode:
            suggestions.append("Citação não encontrada no banco local, apenas na web")
        else:
            suggestions.append("Verifique a citação na fonte oficial")
    else:
        valid = False
        confidence = 0.1
        suggestions.append("Citação não encontrada - verifique os dados")

    # Sugerir correção se possível
    if not valid and components:
        correct_citation = _suggest_correction(components, rag_result, web_result)

    return {
        "valid": valid,
        "confidence": confidence,
        "rag_score": rag_result.get("score", 0),
        "suggestions": suggestions,
        "correct_citation": correct_citation,
    }


def _suggest_citation_format(source_type: str) -> List[str]:
    """Sugere formatos de citação corretos."""
    formats = {
        "jurisprudencia": [
            "STJ, REsp 1.234.567/SP, Rel. Min. Fulano, DJe 01/01/2024",
            "STF, RE 123456, Rel. Min. Ciclano, j. 01/01/2024",
        ],
        "legislacao": [
            "Lei n. 8.078/1990, art. 6o",
            "Código Civil, art. 186",
            "Constituição Federal, art. 5o, II",
        ],
        "sumula": [
            "Súmula 123 do STJ",
            "Súmula Vinculante 13",
        ],
        "doutrina": [
            "AUTOR, Nome. Título da Obra. Editora, 2024, p. 100.",
        ],
    }
    return formats.get(source_type, formats["jurisprudencia"])


def _suggest_correction(
    components: Dict[str, Any],
    rag_result: Dict[str, Any],
    web_result: Dict[str, Any],
) -> Optional[str]:
    """Sugere correção para a citação."""
    # Usar resultado do RAG se disponível
    if rag_result.get("found") and rag_result.get("metadata"):
        meta = rag_result["metadata"]
        if meta.get("tribunal") and meta.get("numero"):
            return f"{meta['tribunal']}, {meta.get('tipo', '')} {meta['numero']}"

    # Usar resultado da web se disponível
    if web_result.get("found") and web_result.get("title"):
        return web_result["title"][:200]

    return None


def _extract_legal_keywords(text: str) -> List[str]:
    """Extrai palavras-chave jurídicas do texto."""
    # Remover stopwords e extrair termos relevantes
    stopwords = {
        "o", "a", "os", "as", "de", "do", "da", "dos", "das", "em", "no", "na",
        "nos", "nas", "um", "uma", "uns", "umas", "por", "para", "com", "sem",
        "que", "se", "é", "são", "foi", "foram", "ser", "ter", "há", "ou", "e",
    }

    words = re.findall(r"\b[a-záàâãéèêíïóôõöúç]+\b", text.lower())
    keywords = [w for w in words if w not in stopwords and len(w) > 3]

    # Priorizar termos jurídicos
    legal_terms = {
        "prazo", "prescrição", "decadência", "responsabilidade", "dano",
        "moral", "material", "contrato", "obrigação", "indenização",
        "ação", "recurso", "sentença", "decisão", "tutela", "liminar",
        "consumidor", "fornecedor", "trabalhista", "tributário",
    }

    prioritized = [w for w in keywords if w in legal_terms]
    others = [w for w in keywords if w not in legal_terms]

    return prioritized[:10] + others[:5]


def _detect_area_direito(text: str, keywords: List[str]) -> str:
    """Detecta área do direito."""
    text_lower = text.lower()

    areas = {
        "consumidor": ["consumidor", "fornecedor", "cdc", "produto", "serviço"],
        "civil": ["contrato", "obrigação", "responsabilidade", "dano", "indenização"],
        "trabalhista": ["trabalhista", "empregado", "empregador", "clt", "rescisão"],
        "tributario": ["tributo", "imposto", "contribuição", "icms", "ipi", "irpf"],
        "penal": ["crime", "penal", "pena", "delito", "réu", "acusado"],
        "administrativo": ["administrativo", "licitação", "servidor", "público"],
        "constitucional": ["constitucional", "direito fundamental", "cf/88"],
    }

    scores: Dict[str, int] = {}
    for area, terms in areas.items():
        score = sum(1 for term in terms if term in text_lower or term in keywords)
        if score > 0:
            scores[area] = score

    if scores:
        return max(scores, key=scores.get)

    return "civil"  # Default


async def _search_jurisprudencia_for_claim(
    claim: str,
    keywords: List[str],
    area: str,
    tenant_id: str,
    user_id: Optional[str],
    top_k: int,
) -> List[Dict[str, Any]]:
    """Busca jurisprudência para a afirmação."""
    from .legal_research import search_jurisprudencia

    result = await search_jurisprudencia(
        query=claim,
        top_k=top_k,
        tenant_id=tenant_id,
        user_id=user_id,
    )

    sources = []
    for r in result.get("results", []):
        sources.append({
            "type": "jurisprudencia",
            "tribunal": r.get("tribunal", ""),
            "numero": r.get("numero", ""),
            "ementa": r.get("ementa", "")[:500],
            "url": r.get("url", ""),
            "confidence": r.get("score", 0),
            "raw_result": r,
        })

    return sources


async def _search_legislacao_for_claim(
    claim: str,
    keywords: List[str],
    area: str,
    tenant_id: str,
    user_id: Optional[str],
    top_k: int,
) -> List[Dict[str, Any]]:
    """Busca legislação para a afirmação."""
    from .legal_research import search_legislacao

    result = await search_legislacao(
        query=claim,
        top_k=top_k,
        tenant_id=tenant_id,
        user_id=user_id,
    )

    sources = []
    for r in result.get("results", []):
        sources.append({
            "type": "legislacao",
            "tipo_lei": r.get("tipo_lei", ""),
            "numero": r.get("numero", ""),
            "artigo": r.get("artigo", ""),
            "texto": r.get("texto", "")[:500],
            "url": r.get("url", ""),
            "confidence": r.get("score", 0),
            "raw_result": r,
        })

    return sources


async def _search_doutrina_for_claim(
    claim: str,
    keywords: List[str],
    area: str,
    top_k: int,
) -> List[Dict[str, Any]]:
    """Busca doutrina para a afirmação (via web)."""
    try:
        from app.services.web_search_service import web_search_service

        query = f"{claim} doutrina jurídica {area}"

        result = await web_search_service.search(
            query=query,
            num_results=top_k,
            country="BR",
            language_filter=["pt"],
        )

        sources = []
        for r in result.get("results", []):
            sources.append({
                "type": "doutrina",
                "title": r.get("title", ""),
                "snippet": r.get("snippet", "")[:500],
                "url": r.get("url", ""),
                "confidence": r.get("score", 0.4),
                "raw_result": r,
            })

        return sources

    except Exception as e:
        logger.warning(f"[_search_doutrina_for_claim] Erro: {e}")
        return []


def _format_citation(source: Dict[str, Any]) -> str:
    """Formata uma fonte como citação."""
    source_type = source.get("type", "")

    if source_type == "jurisprudencia":
        tribunal = source.get("tribunal", "")
        numero = source.get("numero", "")
        return f"{tribunal}, {numero}".strip(", ")

    elif source_type == "legislacao":
        tipo = source.get("tipo_lei", "Lei")
        numero = source.get("numero", "")
        artigo = source.get("artigo", "")
        citation = f"{tipo} n. {numero}"
        if artigo:
            citation += f", {artigo}"
        return citation

    elif source_type == "doutrina":
        title = source.get("title", "")
        return title[:100]

    return source.get("title", "") or source.get("numero", "")


# =============================================================================
# TOOL REGISTRY
# =============================================================================

CITATION_VERIFIER_TOOLS = {
    "verify_citation": {
        "function": verify_citation,
        "schema": VERIFY_CITATION_SCHEMA,
        "permission_default": "allow",  # Leitura, pode executar automaticamente
    },
    "find_citation_source": {
        "function": find_citation_source,
        "schema": FIND_CITATION_SOURCE_SCHEMA,
        "permission_default": "allow",  # Leitura, pode executar automaticamente
    },
}
