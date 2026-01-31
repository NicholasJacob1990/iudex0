"""
LangGraph Legal Workflow - Phase 4 (Audit Feedback Loop + HIL)

Fluxo:
  outline → [research] → fact_check → citer_verifier → debate →
  → divergence_hil → audit → [if issues] → propose_corrections →
  → correction_hil → finalize_hil → END

Nodes:
  - citer_verifier (B2): Gate pré-debate que verifica rastreabilidade
    de afirmações às fontes. Marca claims sem fonte como [VERIFICAR].
    Se coverage < 0.3, bloqueia debate e vai direto para HIL.

Feature Flag:
  USE_GRANULAR_DEBATE=true  → Uses 8-node sub-graph (R1-R4)
  USE_GRANULAR_DEBATE=false → Uses hybrid node
"""

from typing import TypedDict, Literal, Optional, List, Dict, Any, Tuple, Mapping
from langgraph.graph import StateGraph, END
try:
    # Newer versions
    from langgraph.checkpoint.sqlite import SqliteSaver  # type: ignore
except Exception:  # pragma: no cover
    SqliteSaver = None  # type: ignore
    from langgraph.checkpoint.memory import MemorySaver  # type: ignore
try:
    from langgraph.types import interrupt
except ImportError:
    # Fallback for older LangGraph versions without interrupt()
    from langgraph.types import Interrupt
    def interrupt(value: dict):
        """Compatibility shim: raises Interrupt to pause the graph for HIL."""
        raise Interrupt(value)
else:
    # Ensure Interrupt is available for observability wrappers.
    try:
        from langgraph.types import Interrupt  # type: ignore
    except Exception:  # pragma: no cover
        Interrupt = None  # type: ignore
from loguru import logger
import asyncio
import sqlite3
import os
import re
import json
import time

from app.services.web_search_service import web_search_service, build_web_context, is_breadth_first, plan_queries
from app.services.web_rag_service import web_rag_service
from app.services.ai.citations import extract_perplexity
from app.services.ai.rag_helpers import evaluate_crag_gate
from app.services.ai.citations.base import sources_to_citations, format_reference_abnt
from app.services.ai.deep_research_service import deep_research_service
from app.services.ai.perplexity_config import (
    build_perplexity_chat_kwargs,
    normalize_perplexity_search_mode,
    normalize_perplexity_recency,
    normalize_perplexity_date,
    parse_csv_list,
    normalize_float,
)
from app.services.rag.config import get_rag_config
from app.services.job_manager import job_manager
from app.services.api_call_tracker import record_api_call, billing_context
from app.services.ai.audit_service import AuditService
from app.services.ai.hil_decision_engine import HILDecisionEngine, HILChecklist, hil_engine
from app.services.ai.model_registry import get_api_model_name, get_model_config, DEFAULT_JUDGE_MODEL, DEFAULT_DEBATE_MODELS, ModelConfig
from app.services.ai.document_store import resolve_full_document, store_full_document_state

# Quality Pipeline (v2.25)
from app.services.ai.quality_gate import quality_gate_node
from app.services.ai.structural_fix import structural_fix_node
from app.services.ai.targeted_patch import targeted_patch_node
from app.services.ai.quality_report import quality_report_node

# B2 Citer/Verifier (Pre-Debate Gate)
from app.services.ai.citer_verifier import citer_verifier_node

# Audit service instance
audit_service = AuditService()

# Feature Flag
USE_GRANULAR_DEBATE = os.getenv("USE_GRANULAR_DEBATE", "false").lower() == "true"
logger.info("🔀 Mixed Debate Mode ENABLED (granular per section, default_granular=%s)", USE_GRANULAR_DEBATE)

# Graph RAG Integration (v5.1)
from app.services.rag_module_old import create_rag_manager, get_scoped_knowledge_graph

# =============================================================================
# RAG ROUTING STRATEGIES (ported from CLI)
# =============================================================================

STRATEGY_LOCAL_ONLY = "LOCAL_ONLY"       # Search only in local process documents
STRATEGY_GLOBAL_SINGLE = "GLOBAL_SINGLE" # Search only in global bases (lei, juris, etc.)
STRATEGY_HYBRID = "HYBRID"               # Search both local and global
STRATEGY_NO_RETRIEVAL = "NO_RETRIEVAL"   # Skip RAG entirely (simple/template sections)
STRATEGY_HYDE = "HYDE"                   # Use HyDE for complex/abstract queries
STRATEGY_GRAPH = "GRAPH"                 # Use GraphRAG for multi-hop reasoning

_rag_manager_instance = None


def _get_rag_manager():
    global _rag_manager_instance
    if _rag_manager_instance is None:
        try:
            _rag_manager_instance = create_rag_manager()
            logger.info("🧠 RAGManager inicializado para LangGraph")
        except Exception as e:
            logger.warning(f"⚠️ RAGManager indisponível no LangGraph: {e}")
            return None
    return _rag_manager_instance


def _validate_document_size(state: "DocumentState", model_id: str) -> Dict[str, Any]:
    """
    Validates if document size fits within model's context window.
    Returns validation result with warning if exceeded.
    
    v5.7: Added for 100+ page document support.
    """
    input_text = state.get("input_text", "") or ""
    research_context = state.get("research_context", "") or ""
    
    # Estimate total chars that will be used
    total_chars = len(input_text) + len(research_context)
    
    # Get model config
    cfg = get_model_config(model_id)
    if not cfg:
        return {"valid": True, "warning": None}
    
    # Calculate max safe chars (context_window * 3.5 chars/token - 20% overhead)
    max_safe_chars = int(cfg.context_window * 3.5 * 0.8)
    
    # Check if exceeded
    if total_chars > max_safe_chars:
        pages_estimate = total_chars // 4000  # ~4k chars per page
        max_pages = max_safe_chars // 4000
        
        warning = {
            "type": "DOCUMENT_SIZE_WARNING",
            "model": model_id,
            "model_label": cfg.label if cfg else model_id,
            "context_window_tokens": cfg.context_window,
            "document_chars": total_chars,
            "max_safe_chars": max_safe_chars,
            "estimated_pages": pages_estimate,
            "max_pages_for_model": max_pages,
            "message": (
                f"Documento (~{pages_estimate} páginas) excede capacidade do modelo "
                f"{cfg.label} (~{max_pages} páginas). Considere usar um modelo maior "
                f"(gemini-1.5-pro, claude-3-5-sonnet) ou dividir o documento."
            )
        }
        logger.warning(f"⚠️ {warning['message']}")
        return {"valid": False, "warning": warning}
    
    return {"valid": True, "warning": None}


def _build_case_bundle(state: "DocumentState", processo_id: Optional[str] = None) -> "CaseBundle":
    from app.services.ai.agent_clients import CaseBundle

    bundle_id = (
        processo_id
        or state.get("case_bundle_processo_id")
        or state.get("job_id")
        or "langgraph-job"
    )
    text_pack = (state.get("case_bundle_text_pack") or "").strip()
    pdf_paths = [
        str(p).strip()
        for p in (state.get("case_bundle_pdf_paths") or [])
        if str(p).strip()
    ]
    return CaseBundle(processo_id=bundle_id, text_pack=text_pack, pdf_paths=pdf_paths)


def _build_section_query(section_title: str, thesis: str, input_text: str) -> str:
    base = section_title.strip()
    parts = [base] if base else []
    if thesis:
        parts.append(f"Tese: {thesis}")
    if input_text:
        parts.append(f"Contexto: {input_text[:800]}")
    return ". ".join(parts).strip()


async def _build_hyde_query(
    model_id: str,
    section_title: str,
    thesis: str,
    input_text: str
) -> str:
    # v5.7: Improved prompt structure
    prompt = f"""
# ROLE
Você é um especialista em redação jurídica criando um documento hipotético para busca.

# TASK
Crie um texto hipotético curto (150-300 palavras) que RESPONDERIA à seção jurídica abaixo.
Este texto será usado como query de busca (HyDE - Hypothetical Document Embedding).

# CONTEXT
## Seção: {section_title}
## Tese: {thesis}
## Contexto: {input_text[:1200]}

# RULES
1. Use linguagem técnica jurídica
2. Cite fundamentos em alto nível (sem inventar números específicos)
3. NÃO use Markdown, apenas texto corrido
4. Foque em termos que apareceriam em documentos relevantes

# OUTPUT FORMAT
Texto corrido, 150-300 palavras, sem formatação.

TEXTO HIPOTÉTICO:"""
    with billing_context(node="hyde_query", size="S"):
        response = await _call_model_any_async(
            model_id,
            prompt,
            temperature=0.4,
            max_tokens=600
        )
    return (response or "").strip()


def build_personality_instructions(personality: str) -> str:
    if personality == "geral":
        return (
            "## ESTILO DE RESPOSTA (MODO LIVRE)\n"
            "- Use linguagem clara e acessível, sem jargões jurídicos.\n"
            "- Explique conceitos quando necessário, de forma objetiva.\n"
            "- Mantenha a precisão do conteúdo, mas com tom mais conversacional.\n"
        )
    if personality == "juridico":
        return (
            "## ESTILO DE RESPOSTA (MODO JURÍDICO)\n"
            "- Use linguagem técnica e formal, com termos jurídicos adequados.\n"
            "- Estruture o texto conforme práticas forenses e normas aplicáveis.\n"
        )
    return ""

def build_evidence_policy(audit_mode: str) -> str:
    if (audit_mode or "").lower() == "research":
        return (
            "## POLÍTICA DE EVIDÊNCIA (PESQUISA)\n"
            "- SEI/autos do caso (RAG local + anexos) são a fonte de verdade para fatos administrativos.\n"
            "- Fontes externas servem apenas para fundamentação normativa/jurisprudencial.\n"
            "- Nunca trate fonte externa como prova de fato do processo.\n"
            "- Separe claramente 'fato dos autos' vs 'fundamentação externa'.\n"
        )
    return (
        "## POLÍTICA DE EVIDÊNCIA (AUDITORIA - SOMENTE SEI)\n"
        "- Use exclusivamente o SEI/autos do caso (RAG local + anexos) para fatos e eventos administrativos.\n"
        "- Não cite nem invente fontes externas para comprovar fatos.\n"
        "- Se faltar prova no SEI, marque como [[PENDENTE: confirmar no SEI]].\n"
    )


def build_web_citation_policy(citations_map: Any) -> str:
    if not isinstance(citations_map, dict) or not citations_map:
        return ""
    keys = [k for k in citations_map.keys() if str(k).isdigit()]
    max_n = max((int(k) for k in keys), default=len(citations_map))
    max_n = max(1, min(20, max_n))
    return (
        "## POLÍTICA DE CITAÇÃO (FONTES WEB)\n"
        "- Ao usar qualquer informação das fontes numeradas da pesquisa, cite no texto com [n].\n"
        f"- Use apenas números disponíveis (1–{max_n}). Não invente citações.\n"
        "- Prefira citar junto à afirmação (fim da frase/parágrafo).\n"
    )


def append_sources_section(markdown_text: str, citations_map: Any, *, max_sources: int = 20) -> str:
    """
    Append a copy-friendly references section (ABNT-like) to the final markdown using citations_map.
    Only includes sources that were actually cited in the document ([n]).
    """
    text = (markdown_text or "").rstrip()
    if not text:
        return markdown_text
    if not isinstance(citations_map, dict) or not citations_map:
        return markdown_text

    # Avoid duplicating if the model already produced a sources/references section.
    if re.search(r"(?im)^\s{0,3}#{1,6}\s+(fontes|references|referências|referencias)\b", text):
        return markdown_text
    if re.search(r"(?im)^\s*(fontes|references|referências|referencias)\s*:\s*$", text):
        return markdown_text

    cited_numbers = {
        int(n)
        for n in re.findall(r"\[(\d{1,3})\]", text)
        if str(n).isdigit()
    }
    if not cited_numbers:
        return markdown_text

    ordered_keys: List[str] = []
    for n in sorted(cited_numbers):
        key = str(n)
        if key in citations_map:
            ordered_keys.append(key)
    if not ordered_keys:
        return markdown_text

    ordered_keys = ordered_keys[: max(1, min(20, int(max_sources or 20)))]

    lines = ["", "---", "", "## Referências"]
    for key in ordered_keys:
        item = citations_map.get(key) or {}
        title = (item.get("title") or f"Fonte {key}").strip()
        url = (item.get("url") or "").strip()
        if url:
            lines.append(f"[{key}] {format_reference_abnt(title=title, url=url)}".strip())
        else:
            lines.append(f"[{key}] {format_reference_abnt(title=title, url='')}".strip())

    return text + "\n" + "\n".join(lines).rstrip() + "\n"

def prepend_need_evidence_notice(state: "DocumentState", markdown_text: str) -> str:
    """
    Prepend a user-visible notice when we generated a draft but the workflow
    flagged missing/insufficient evidence. This is meant for HIL-off mode:
    keep the workflow running, but make the risk explicit in the document.
    """
    text = (markdown_text or "").lstrip()
    if not text:
        return markdown_text

    # Avoid duplicates if the banner is already present.
    if re.search(r"(?im)pendênci(as)?\s+de\s+evidênci(a|as)", text):
        return markdown_text
    if re.search(r"(?im)minuta\s+gerada\s+com\s+pendênci", text):
        return markdown_text

    citer = state.get("citer_verifier_result") or {}
    coverage = citer.get("coverage")
    try:
        coverage_pct = f"{float(coverage) * 100:.1f}%"
    except Exception:
        coverage_pct = None

    gaps = []
    if isinstance(citer, dict):
        gaps = citer.get("critical_gaps") or []
    gaps = [str(g).strip() for g in (gaps or []) if str(g).strip()]
    gaps = gaps[:5]

    lines = [
        "> ⚠️ **Minuta gerada com pendências de evidência** — revise antes de protocolar.",
    ]
    if coverage_pct:
        lines.append(f"> **Rastreabilidade (Citer/Verifier):** {coverage_pct}.")
    if gaps:
        lines.append("> **Lacunas principais:**")
        for gap in gaps:
            lines.append(f"> - {gap[:240]}")
    lines.append("")

    return "\n".join(lines) + "\n" + text


def _clean_outline_line(line: str) -> str:
    cleaned = re.sub(r"^[\s>*-]+", "", (line or "").strip())
    cleaned = re.sub(r"^\d+[\.)-]\s*", "", cleaned).strip()
    return cleaned


def _parse_outline_response(text: str) -> List[str]:
    if not text:
        return []

    # Try JSON array
    json_block = None
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1 and end > start:
        json_block = text[start:end + 1]
    if json_block:
        try:
            parsed = json.loads(json_block)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        except Exception:
            pass

    # Fallback: parse lines
    lines = []
    for raw in text.splitlines():
        line = _clean_outline_line(raw)
        if line:
            lines.append(line)
    return lines


def _sections_for_pages(pages: int) -> int:
    pages = int(pages or 0)
    if pages <= 0:
        return 0
    sections = round(pages * 0.5) + 2
    return max(3, min(sections, 14))


def _outline_section_range(min_pages: int, max_pages: int) -> tuple[int, int]:
    min_sections = _sections_for_pages(min_pages) if min_pages else 0
    max_sections = _sections_for_pages(max_pages) if max_pages else 0

    if min_sections and max_sections and max_sections < min_sections:
        max_sections = min_sections
    if min_sections and not max_sections:
        max_sections = min(14, min_sections + 2)
    if max_sections and not min_sections:
        min_sections = max(3, max_sections - 2)

    return min_sections, max_sections


def _outline_size_guidance(min_pages: int, max_pages: int) -> str:
    if not (min_pages or max_pages):
        return ""

    min_sections, max_sections = _outline_section_range(min_pages, max_pages)
    if min_sections and max_sections:
        sections_label = f"{min_sections}" if min_sections == max_sections else f"{min_sections}-{max_sections}"
    else:
        sections_label = None

    if min_pages and max_pages:
        pages_label = f"{min_pages}-{max_pages}"
    elif min_pages:
        pages_label = f"{min_pages}+"
    else:
        pages_label = f"até {max_pages}"

    lines = [
        "TAMANHO:",
        f"- Documento entre {pages_label} páginas.",
    ]
    if sections_label:
        lines.append(f"- Estruture o sumário com cerca de {sections_label} tópicos principais.")
    lines.append("- Se for curto, agrupe itens; se for longo, subdivida.")
    return "\n".join(lines)


def _merge_outline_pair(outline: List[str], idx: int) -> List[str]:
    left = _clean_outline_line(outline[idx]) if idx < len(outline) else ""
    right = _clean_outline_line(outline[idx + 1]) if idx + 1 < len(outline) else ""
    if left and right:
        merged = f"{left} / {right}"
    else:
        merged = left or right or outline[idx]
    return outline[:idx] + [merged] + outline[idx + 2:]


def _shrink_outline(outline: List[str], max_sections: int) -> List[str]:
    if max_sections <= 0:
        return outline
    current = list(outline)
    while len(current) > max_sections and len(current) >= 2:
        cleaned = [_clean_outline_line(item) for item in current]
        best_idx = 0
        best_score = None
        for i in range(len(cleaned) - 1):
            score = len(cleaned[i]) + len(cleaned[i + 1])
            if best_score is None or score < best_score:
                best_score = score
                best_idx = i
        current = _merge_outline_pair(current, best_idx)
    return current


def _expand_outline(outline: List[str], min_sections: int) -> List[str]:
    if min_sections <= 0:
        return outline

    rules = [
        (re.compile(r"\b(fatos|relat[oó]rio|s[ií]ntese)\b", re.I), "Contexto fático detalhado"),
        (re.compile(r"\b(direito|fundamenta)\b", re.I), "Jurisprudência e precedentes"),
        (re.compile(r"\bmérito\b", re.I), "Teses específicas do mérito"),
        (re.compile(r"\bpreliminar\b", re.I), "Preliminares processuais"),
        (re.compile(r"\bpedidos?|requerimentos?\b", re.I), "Pedidos subsidiários"),
        (re.compile(r"\bconclus[aã]o|opini[aã]o|fecho\b", re.I), "Providências finais"),
    ]

    current = list(outline)
    idx = 0
    while len(current) < min_sections and idx < len(current):
        title = current[idx]
        added = False
        for pattern, addition in rules:
            if pattern.search(title):
                if addition not in current:
                    current.insert(idx + 1, addition)
                    added = True
                break
        idx += 2 if added else 1

    fallback_additions = ["Pontos complementares", "Observações finais"]
    for addition in fallback_additions:
        if len(current) >= min_sections:
            break
        if addition not in current:
            current.append(addition)

    return current


def _adjust_outline_to_range(outline: List[str], min_pages: int, max_pages: int) -> List[str]:
    if not (min_pages or max_pages):
        return outline
    min_sections, max_sections = _outline_section_range(min_pages, max_pages)
    adjusted = list(outline)
    if max_sections and len(adjusted) > max_sections:
        adjusted = _shrink_outline(adjusted, max_sections)
    if min_sections and len(adjusted) < min_sections:
        adjusted = _expand_outline(adjusted, min_sections)
    return adjusted


async def _call_model_any_async(
    model_id: str,
    prompt: str,
    *,
    system_instruction: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: int = 1200,
    cached_content: Optional[Any] = None
) -> str:
    if not model_id:
        return ""

    cfg = get_model_config(model_id)
    if not cfg:
        logger.warning(f"⚠️ Model config não encontrado para model_id={model_id}. Retornando vazio.")
        return ""

    api_model = get_api_model_name(model_id)

    from app.services.ai.agent_clients import (
        init_openai_client,
        init_anthropic_client,
        init_xai_client,
        init_openrouter_client,
        get_gemini_client,
        call_openai_async,
        call_anthropic_async,
        call_perplexity_async,
        call_vertex_gemini,
        call_vertex_gemini_async,
    )

    if cfg.provider == "openai":
        client = init_openai_client()
        if not client:
            logger.warning("⚠️ OpenAI client não inicializado. Retornando vazio.")
            return ""
        return await call_openai_async(
            client,
            prompt,
            model=api_model,
            max_tokens=max_tokens,
            temperature=temperature,
            system_instruction=system_instruction
        ) or ""
    if cfg.provider == "anthropic":
        client = init_anthropic_client()
        if not client:
            logger.warning("⚠️ Anthropic client não inicializado. Retornando vazio.")
            return ""
        return await call_anthropic_async(
            client,
            prompt,
            model=api_model,
            max_tokens=max_tokens,
            temperature=temperature,
            system_instruction=system_instruction
        ) or ""
    if cfg.provider == "google":
        client = get_gemini_client()
        if not client:
            logger.warning("⚠️ Gemini client não inicializado. Retornando vazio.")
            return ""
        if cached_content:
            return await asyncio.to_thread(
                call_vertex_gemini,
                client,
                prompt,
                model=model_id,
                max_tokens=max_tokens,
                temperature=temperature,
                system_instruction=system_instruction,
                cached_content=cached_content
            ) or ""
        return await call_vertex_gemini_async(
            client,
            prompt,
            model=model_id,
            max_tokens=max_tokens,
            temperature=temperature,
            system_instruction=system_instruction
        ) or ""
    if cfg.provider == "xai":
        client = init_xai_client()
        if not client:
            logger.warning("⚠️ xAI client não inicializado. Retornando vazio.")
            return ""
        return await call_openai_async(
            client,
            prompt,
            model=api_model,
            max_tokens=max_tokens,
            temperature=temperature,
            system_instruction=system_instruction
        ) or ""
    if cfg.provider == "openrouter":
        client = init_openrouter_client()
        if not client:
            logger.warning("⚠️ OpenRouter client não inicializado. Retornando vazio.")
            return ""
        return await call_openai_async(
            client,
            prompt,
            model=api_model,
            max_tokens=max_tokens,
            temperature=temperature,
            system_instruction=system_instruction
        ) or ""
    if cfg.provider == "perplexity":
        text = await call_perplexity_async(
            prompt,
            model=api_model or model_id,
            max_tokens=max_tokens,
            temperature=temperature,
            system_instruction=system_instruction,
            web_search_enabled=False,
            disable_search=True,
        )
        if not text:
            logger.warning("⚠️ Perplexity client não inicializado. Retornando vazio.")
            return ""
        return text

    logger.warning(f"⚠️ Provider não suportado para judge/strategist: {cfg.provider}")
    return ""

def default_route_for_section(section_title: str, tipo_peca: str = "") -> Dict[str, Any]:
    """
    Heuristic-based router that decides RAG strategy based on section title.

    Returns a dict with:
        - strategy: one of STRATEGY_* constants
        - sources: list of RAG sources to query
        - top_k: number of results to fetch
        - bm25_weight / semantic_weight: weights for hybrid retrieval
        - graph_hops: (for STRATEGY_GRAPH) depth of relationship traversal
        - use_hyde: whether to use HyDE for this section (pipeline flag)
        - use_graph: whether to use GraphRAG for this section (pipeline flag)
        - reason: explanation for routing decision
    
    v5.8: Added use_hyde and use_graph flags to enable combined techniques.
    """
    title_lower = (section_title or "").lower()

    # Default config
    config = {
        "strategy": STRATEGY_HYBRID,
        "sources": ["lei", "juris", "pecas_modelo"],
        "top_k": 8,
        "bm25_weight": 0.4,
        "semantic_weight": 0.6,
        "graph_hops": 0,
        "use_hyde": False,
        "use_graph": False,
        "reason": "default hybrid",
    }

    # 1. LOCAL_ONLY: Factual sections that require process-specific info
    local_patterns = [
        r"(dos?\s+)?fatos?",
        r"(da\s+)?narrativa",
        r"síntese\s*(da|do)?\s*(inicial|proceso|fatos)?",
        r"relatório",
        r"qualificação\s*(das?\s+partes)?",
        r"histórico",
        r"(do\s+)?caso",
    ]
    for pattern in local_patterns:
        if re.search(pattern, title_lower):
            return {
                "strategy": STRATEGY_LOCAL_ONLY,
                "sources": ["sei"],
                "top_k": 5,
                "bm25_weight": 0.6,
                "semantic_weight": 0.4,
                "graph_hops": 0,
                "use_hyde": False,
                "use_graph": False,
                "reason": f"matched local pattern: {pattern}",
            }

    # 2. HYDE: complex fundamentação (abstract concepts)
    hyde_patterns = [
        r"fundament(o|ação)\s*(jurídica)?",
        r"tese(s)?\s+(central|principal|jurídica)",
        r"doutrina",
        r"teoria\s*(geral|do)?",
    ]
    for pattern in hyde_patterns:
        if re.search(pattern, title_lower):
            return {
                "strategy": STRATEGY_HYDE,
                "sources": ["lei", "juris", "pecas_modelo"],
                "top_k": 10,
                "bm25_weight": 0.3,
                "semantic_weight": 0.7,
                "graph_hops": 2,
                "use_hyde": True,
                "use_graph": True,  # v5.8: Complex thesis sections benefit from both
                "reason": f"matched HyDE pattern: {pattern}",
            }

    # 3. GRAPH: Jurisprudência, súmulas, precedentes (multi-hop reasoning)
    graph_patterns = [
        r"juris(prudência)?",
        r"súmula(s)?",
        r"precedent(e|es)",
        r"entendimento\s+(do|da)\s+(st[fj]|tst|tribunal)",
    ]
    for pattern in graph_patterns:
        if re.search(pattern, title_lower):
            return {
                "strategy": STRATEGY_GRAPH,
                "sources": ["juris"],
                "top_k": 8,
                "bm25_weight": 0.4,
                "semantic_weight": 0.6,
                "graph_hops": 2,
                "use_hyde": False,
                "use_graph": True,
                "reason": f"matched Graph pattern: {pattern}",
            }

    # 4. GLOBAL_SINGLE: Simple legal doctrine sections
    # v5.8: "Mérito" and "Direito" sections now support combined techniques
    global_patterns = [
        r"(do\s+)?direito",
        r"legislação",
        r"mérito",
    ]
    for pattern in global_patterns:
        if re.search(pattern, title_lower):
            return {
                "strategy": STRATEGY_GLOBAL_SINGLE,
                "sources": ["lei", "juris"],
                "top_k": 10,
                "bm25_weight": 0.5,
                "semantic_weight": 0.5,
                "graph_hops": 1,
                "use_hyde": True,  # v5.8: Direito/Mérito benefit from HyDE
                "use_graph": True,  # v5.8: Also benefit from GraphRAG connections
                "reason": f"matched global pattern: {pattern}",
            }

    # 5. NO_RETRIEVAL: Procedural/template sections
    no_rag_patterns = [
        r"(dos?\s+)?pedidos?",
        r"(do\s+)?valor\s*(da\s+causa)?",
        r"(opção\s*(por)?\s*)?(audiência|conciliação)",
        r"endereçamento",
        r"conclusão",
        r"fecho",
        r"requerimentos?\s*finais?",
        r"tempestividade",
        r"preparo",
    ]
    for pattern in no_rag_patterns:
        if re.search(pattern, title_lower):
            return {
                "strategy": STRATEGY_NO_RETRIEVAL,
                "sources": [],
                "top_k": 0,
                "bm25_weight": 0.0,
                "semantic_weight": 0.0,
                "graph_hops": 0,
                "use_hyde": False,
                "use_graph": False,
                "reason": f"matched no-rag pattern: {pattern}",
            }

    # 6. Return default for unmatched sections
    return config


# v4.1: SAFE MODE INSTRUCTION (unified with CLI)
SAFE_MODE_INSTRUCTION = """
⚠️ **ATENÇÃO: MODO SEGURO ATIVADO**

A qualidade das fontes RAG está abaixo do ideal. Para evitar alegações falsas:
1. LIMITE-SE aos fatos explicitamente presentes no contexto fornecido.
2. NÃO cite leis, súmulas ou jurisprudência específicas a menos que estejam LITERALMENTE no contexto.
3. Use linguagem genérica quando não houver fonte: "conforme entendimento jurisprudencial", "nos termos da legislação aplicável".
4. Prefira argumentos lógicos e principiológicos a citações específicas.
5. Marque com [VERIFICAR] qualquer afirmação que necessite confirmação posterior.
"""

def build_length_guidance(state: "DocumentState", num_sections: int) -> str:
    WORDS_PER_PAGE = 350
    target_pages = int(state.get("target_pages") or 0)
    min_pages = int(state.get("min_pages") or 0)
    max_pages = int(state.get("max_pages") or 0)

    if min_pages < 0:
        min_pages = 0
    if max_pages < 0:
        max_pages = 0
    if min_pages and max_pages and max_pages < min_pages:
        max_pages = min_pages
    if max_pages and not min_pages:
        min_pages = 1
    if min_pages and not max_pages:
        max_pages = min_pages

    if min_pages or max_pages:
        total_words_min = min_pages * WORDS_PER_PAGE
        total_words_max = max_pages * WORDS_PER_PAGE
        if num_sections > 0:
            per_min = max(1, total_words_min // num_sections)
            per_max = max(1, total_words_max // num_sections)
            return (
                "\n### TAMANHO DESEJADO\n"
                f"Documento entre {min_pages}-{max_pages} páginas. "
                f"Para esta seção, mire em {per_min}-{per_max} palavras.\n"
            )
        return f"\n### TAMANHO DESEJADO\nDocumento entre {min_pages}-{max_pages} páginas.\n"

    if target_pages > 0 and num_sections > 0:
        total_words = target_pages * WORDS_PER_PAGE
        per_words = max(1, total_words // num_sections)
        return (
            "\n### TAMANHO DESEJADO\n"
            f"Documento com ~{target_pages} páginas. "
            f"Para esta seção, mire em ~{per_words} palavras.\n"
        )

    return ""


def _get_full_document_preview(state: Mapping[str, Any], max_chars: int = 3000) -> str:
    preview = state.get("full_document_preview") or ""
    if preview:
        return preview[:max_chars]
    full_document = resolve_full_document(state)
    return full_document[:max_chars] if full_document else ""


def _coalesce_str(*vals: Any) -> str:
    for val in vals:
        if isinstance(val, str):
            trimmed = val.strip()
            if trimmed:
                return trimmed
    return ""


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _extract_merge_rationale(judge_structured: Dict[str, Any]) -> str:
    return _coalesce_str(
        judge_structured.get("merge_rationale"),
        judge_structured.get("merge_reasoning"),
        judge_structured.get("rationale"),
        judge_structured.get("justificativa"),
        judge_structured.get("decision_rationale"),
    )

def _default_review_block() -> Dict[str, Any]:
    return {
        "critique": {"issues": [], "summary": "", "by_agent": {}},
        "revision": {"changelog": [], "resolved": [], "unresolved": []},
        "merge": {"rationale": "", "decisions": [], "judge_structured": {}},
    }

def _ensure_review_schema(sections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    for section in sections:
        if not isinstance(section, dict):
            continue
        review = section.get("review")
        if not isinstance(review, dict):
            section["review"] = _default_review_block()
            continue

        critique = review.get("critique")
        if not isinstance(critique, dict):
            critique = {}
            review["critique"] = critique
        revision = review.get("revision")
        if not isinstance(revision, dict):
            revision = {}
            review["revision"] = revision
        merge = review.get("merge")
        if not isinstance(merge, dict):
            merge = {}
            review["merge"] = merge

        if not isinstance(critique.get("issues"), list):
            critique["issues"] = []
        if not isinstance(critique.get("summary"), str):
            critique["summary"] = ""
        if not isinstance(critique.get("by_agent"), dict):
            critique["by_agent"] = {}

        if not isinstance(revision.get("changelog"), list):
            revision["changelog"] = []
        if not isinstance(revision.get("resolved"), list):
            revision["resolved"] = []
        if not isinstance(revision.get("unresolved"), list):
            revision["unresolved"] = []

        if not isinstance(merge.get("rationale"), str):
            merge["rationale"] = ""
        if not isinstance(merge.get("decisions"), list):
            merge["decisions"] = []
        if not isinstance(merge.get("judge_structured"), dict):
            merge["judge_structured"] = {}
    return sections

def _capture_draft_snapshot(state: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        **state,
        "draft_document_ref": state.get("full_document_ref"),
        "draft_document_preview": state.get("full_document_preview"),
        "draft_document_chars": state.get("full_document_chars"),
    }

def extract_json_strict(
    text: str,
    *,
    expect: Literal["object", "array", "any"] = "object",
) -> Optional[Any]:
    if not text:
        return None
    raw = text.strip()
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw, flags=re.IGNORECASE)
    if fence_match:
        raw = fence_match.group(1).strip()

    def _matches_expect(value: Any) -> bool:
        if expect == "object":
            return isinstance(value, dict)
        if expect == "array":
            return isinstance(value, list)
        return isinstance(value, (dict, list))

    try:
        parsed = json.loads(raw)
        if _matches_expect(parsed):
            return parsed
    except Exception:
        pass

    def _scan_block(start_char: str, end_char: str) -> Optional[str]:
        start = raw.find(start_char)
        if start == -1:
            return None
        depth = 0
        for i in range(start, len(raw)):
            ch = raw[i]
            if ch == start_char:
                depth += 1
            elif ch == end_char:
                depth -= 1
                if depth == 0:
                    return raw[start:i + 1]
        return None

    candidates: List[str] = []
    if expect in ("object", "any"):
        block = _scan_block("{", "}")
        if block:
            candidates.append(block)
    if expect in ("array", "any"):
        block = _scan_block("[", "]")
        if block:
            candidates.append(block)

    for block in candidates:
        try:
            parsed = json.loads(block)
        except Exception:
            continue
        if _matches_expect(parsed):
            return parsed

    return None

def validate_citations(text: str, citations_map: Any) -> Dict[str, Any]:
    used_keys: List[str] = []
    missing_keys: List[str] = []
    orphan_keys: List[str] = []
    if not text:
        return {
            "used_keys": used_keys,
            "missing_keys": missing_keys,
            "orphan_keys": orphan_keys,
            "total_used": 0,
            "total_missing": 0,
            "total_orphans": 0,
        }

    used = {
        str(n)
        for n in re.findall(r"\[(\d{1,3})\]", text)
        if str(n).isdigit()
    }
    used_keys = sorted(used, key=lambda k: int(k))

    citations_dict = citations_map if isinstance(citations_map, dict) else {}
    missing_keys = [k for k in used_keys if k not in citations_dict]

    citation_keys = [str(k) for k in citations_dict.keys() if str(k).isdigit()]
    orphan_keys = [k for k in sorted(citation_keys, key=lambda k: int(k)) if k not in used]

    return {
        "used_keys": used_keys,
        "missing_keys": missing_keys,
        "orphan_keys": orphan_keys,
        "total_used": len(used_keys),
        "total_missing": len(missing_keys),
        "total_orphans": len(orphan_keys),
    }

def build_section_record(
    *,
    section_title: str,
    merged_content: str,
    divergence_details: str = "",
    drafts: Optional[Dict[str, Any]] = None,
    metrics: Optional[Dict[str, Any]] = None,
    claims_requiring_citation: Optional[List[Any]] = None,
    removed_claims: Optional[List[Any]] = None,
    risk_flags: Optional[List[Any]] = None,
    quality_score: Optional[float] = None,
    review: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    record: Dict[str, Any] = {
        "section_title": section_title,
        "merged_content": merged_content or "",
        "has_significant_divergence": bool(divergence_details),
        "divergence_details": divergence_details or "",
        "drafts": _as_dict(drafts),
        "claims_requiring_citation": _as_list(claims_requiring_citation),
        "removed_claims": _as_list(removed_claims),
        "risk_flags": _as_list(risk_flags),
        "quality_score": quality_score,
        "review": review if isinstance(review, dict) else _default_review_block(),
    }
    if metrics is not None:
        record["metrics"] = _as_dict(metrics)
    _ensure_review_schema([record])
    return record

def _should_use_granular_for_section(
    state: Mapping[str, Any],
    section_title: str,
    route_config: Optional[Dict[str, Any]] = None,
    safe_mode: bool = False,
) -> bool:
    if state.get("force_granular_debate", False):
        return True
    if state.get("disable_granular_debate", False):
        return False

    requested = state.get("granular_target_sections") or state.get("granular_sections") or []
    if isinstance(requested, list) and section_title in requested:
        return True

    title = (section_title or "").lower()
    simple_patterns = [
        r"qualifica",
        r"enderec",
        r"tempestiv",
        r"preparo",
        r"fecho",
        r"conclus",
        r"requerimentos?\s*finais?",
    ]
    if any(re.search(p, title) for p in simple_patterns):
        return False

    complex_patterns = [
        r"fundament",
        r"mérito|merito",
        r"juris",
        r"tese",
        r"precedent",
        r"nulidade",
        r"responsabil",
        r"cabimento",
        r"prescri",
    ]
    if any(re.search(p, title) for p in complex_patterns):
        return True

    if safe_mode:
        return True

    if (state.get("risco") or "").lower() == "alto":
        return True
    if (state.get("destino") or "uso_interno") != "uso_interno":
        return True
    if state.get("need_juris"):
        return True

    strategy = (route_config or {}).get("strategy")
    if strategy in (STRATEGY_GRAPH, STRATEGY_HYDE):
        return True

    return bool(USE_GRANULAR_DEBATE)


def _fallback_structured_critique(drafts: Dict[str, Any], divergencias: str) -> Dict[str, Any]:
    native = drafts.get("critique_structured")
    if isinstance(native, dict):
        return native

    issues = []
    for rf in _as_list(drafts.get("risk_flags")):
        if isinstance(rf, dict):
            issues.append({
                "type": rf.get("type") or "risk_flag",
                "severity": rf.get("severity") or "major",
                "message": rf.get("message") or str(rf),
                "evidence_needed": rf.get("evidence_needed"),
                "span": rf.get("span"),
            })
        else:
            issues.append({
                "type": "risk_flag",
                "severity": "major",
                "message": str(rf),
            })

    summary = ""
    if isinstance(divergencias, str):
        summary = divergencias.strip()
        if summary:
            issues.append({
                "type": "divergence",
                "severity": "major",
                "message": summary[:800],
            })

    return {"issues": issues, "summary": summary[:400], "by_agent": {}}


def _calculate_context_limits(model_id: str) -> tuple[int, int]:
    """
    Calculates dynamic char limits for input_text (facts) and rag_context
    based on the model's context window.
    
    Returns: (limit_facts, limit_rag) in characters.
    """
    cfg = get_model_config(model_id)
    # Default to conservative 32k window if unknown (~128k chars total capacity)
    # But usually models have at least 4k tokens (~16k chars)
    # We'll map tokens -> likely chars (safe factor 3.5x)
    
    # Defaults for unknown/small models
    default_facts = 3000
    default_rag = 4000
    
    if not cfg:
        return default_facts, default_rag

    window_tokens = cfg.context_window
    
    # Simple logic:
    # Reserve 10k tokens for system prompt + output + overhead
    # Remaining capacity split: 40% facts, 60% RAG
    
    reserved_tokens = 4000
    available_tokens = max(0, window_tokens - reserved_tokens)
    
    if available_tokens < 2000:
        return default_facts, default_rag
        
    # Convert available tokens to safe char count (1 token approx 3.5-4 chars)
    total_chars = int(available_tokens * 3.5)
    
    # Cap total chars to avoid excessive payloads even if model supports it
    # (e.g. 1M context is huge, we might not want to dump 1M chars of facts)
    # v5.7: Increased cap for 100-page support (~400k chars = ~100k tokens)
    MAX_CAP = 600_000 # Cap at ~600k chars to support massive contexts
    total_chars = min(total_chars, MAX_CAP)
    
    limit_facts = int(total_chars * 0.40)
    limit_rag = int(total_chars * 0.60)
    
    # Ensure minimums
    limit_facts = max(limit_facts, default_facts)
    limit_rag = max(limit_rag, default_rag)
    
    return limit_facts, limit_rag

def crag_gate_retrieve(
    results: list,
    min_best_score: float = 0.45,
    min_avg_top3_score: float = 0.35,
) -> dict:
    """
    CRAG Gate: Validates RAG result quality for safe generation.
    
    Returns:
        {
            "gate_passed": bool,
            "safe_mode": bool,
            "best_score": float,
            "avg_top3": float,
            "reason": str
        }
    """
    return evaluate_crag_gate(results, min_best_score, min_avg_top3_score)


def _merge_context_blocks(blocks: List[str], max_chars: int = 6000) -> str:
    cleaned = [b.strip() for b in blocks if b and b.strip()]
    if not cleaned:
        return ""
    merged = "\n\n".join(cleaned)
    if len(merged) <= max_chars:
        return merged
    return merged[:max_chars].rstrip() + "\n\n...[conteúdo truncado]..."


async def _resolve_section_context(
    state: "DocumentState",
    section_title: str,
    input_text: str,
    thesis: str,
    base_context: str
) -> Tuple[str, Dict[str, Any], bool]:
    adaptive_enabled = bool(state.get("adaptive_routing_enabled"))
    rag_sources = [
        str(s).strip()
        for s in (state.get("rag_sources") or [])
        if str(s).strip()
    ]
    rag_top_k = int(state.get("rag_top_k") or 8)
    max_rag_retries = int(state.get("max_rag_retries", 1) or 1)
    audit_mode = (state.get("audit_mode") or "sei_only").lower()
    rag_retry_expand_scope = bool(state.get("rag_retry_expand_scope", False))

    if not rag_sources and audit_mode != "sei_only":
        rag_sources = ["lei", "juris", "pecas_modelo"]

    if adaptive_enabled:
        route_config = default_route_for_section(section_title, state.get("mode", ""))
    else:
        route_config = {
            "strategy": STRATEGY_HYBRID,
            "sources": rag_sources,
            "top_k": rag_top_k,
            "bm25_weight": 0.4,
            "semantic_weight": 0.6,
            "graph_hops": 0,
            "reason": "adaptive disabled",
        }

    # v5.6: Only disable retrieval if BOTH global and local sources are missing
    local_sources = route_config.get("sources") or []
    if not rag_sources and not local_sources and route_config["strategy"] not in (STRATEGY_NO_RETRIEVAL,):
        route_config = {**route_config, "strategy": STRATEGY_NO_RETRIEVAL, "sources": [], "top_k": 0}

    use_external_context = route_config["strategy"] not in (STRATEGY_NO_RETRIEVAL,)
    rag_manager = _get_rag_manager() if use_external_context else None
    effective_sources = route_config.get("sources") or rag_sources
    if audit_mode == "sei_only":
        effective_sources = [] if route_config["strategy"] == STRATEGY_NO_RETRIEVAL else ["sei"]
    effective_top_k = int(route_config.get("top_k") or rag_top_k)
    bm25_weight = float(route_config.get("bm25_weight", 0.4))
    semantic_weight = float(route_config.get("semantic_weight", 0.6))

    routing_reasons = state.get("section_routing_reasons")
    if not isinstance(routing_reasons, dict):
        routing_reasons = {}
        state["section_routing_reasons"] = routing_reasons
    routing_payload: Dict[str, Any] = {
        "strategy": route_config.get("strategy"),
        "sources": list(effective_sources or []),
        "top_k": effective_top_k,
        "bm25_weight": bm25_weight,
        "semantic_weight": semantic_weight,
        "graph_hops": route_config.get("graph_hops"),
        "reason": route_config.get("reason"),
        "audit_mode": audit_mode,
        "adaptive_enabled": adaptive_enabled,
        "use_external_context": use_external_context,
        "request_id": state.get("request_id"),
    }
    routing_reasons[section_title] = dict(routing_payload)
    _emit_event(
        state,
        "RAG_ROUTING_DECISION",
        dict(routing_payload),
        phase="rag",
        section=section_title,
    )

    section_rag_context = ""
    graph_context = ""
    safe_mode = False

    if use_external_context and rag_manager and effective_sources:
        section_query = _build_section_query(section_title, thesis, input_text)
        
        # RAG Memory (Conversational Query Rewriting)
        if state.get("messages"):
            try:
                from app.services.ai.rag_memory_helper import _rewrite_query_with_memory
                section_query = await _rewrite_query_with_memory(state, section_query, section_title)
            except Exception as e:
                logger.warning(f"⚠️ RAG Memory disabled (import error): {e}")
        rag_results = []
        graph_context = ""
        graph_primary_hit = False
        graph_used = None
        graph_used_scope = None
        argument_context = ""

        # v5.8: Pipeline-style search - use_hyde and use_graph flags allow combined techniques
        use_hyde = bool(state.get("hyde_enabled")) and bool(route_config.get("use_hyde", False))
        use_graph = bool(state.get("graph_rag_enabled")) and bool(route_config.get("use_graph", False))

        if adaptive_enabled and effective_sources:
            try:
                from app.services.ai.agentic_rag import AgenticRAGRouter, DatasetRegistry
                router = AgenticRAGRouter(DatasetRegistry())
                routed = await router.route(
                    query=section_query,
                    history=state.get("messages"),
                    summary_text=None,
                )
                datasets = routed.get("datasets") if isinstance(routed, dict) else None
                if datasets:
                    resolved = router.registry.get_sources(
                        [str(d).strip() for d in datasets if str(d).strip()]
                    )
                    if resolved:
                        effective_sources = resolved
                routed_query = routed.get("query") if isinstance(routed, dict) else None
                if routed_query:
                    section_query = str(routed_query).strip() or section_query
                route_config["sources"] = effective_sources
                routing_payload["sources"] = list(effective_sources or [])
                routing_payload["agentic_datasets"] = datasets
                routing_payload["agentic_query"] = section_query[:280]
                routing_reasons[section_title] = dict(routing_payload)
                _emit_event(
                    state,
                    "RAG_ROUTING_DECISION",
                    {"update": "agentic", **routing_payload},
                    phase="rag",
                    section=section_title,
                )
            except Exception as exc:
                logger.warning(f"⚠️ AgenticRAG routing failed: {exc}")

        request_id = state.get("request_id") if isinstance(state, dict) else None
        scope_groups = state.get("rag_scope_groups") or []
        allow_global_scope = bool(state.get("rag_allow_global", False))
        allow_group_scope = bool(state.get("rag_allow_groups", bool(scope_groups)))
        try:
            neo4j_only = bool(get_rag_config().neo4j_only)
        except Exception:
            neo4j_only = False

        if use_graph:
            use_tenant_graph = os.getenv("RAG_GRAPH_TENANT_SCOPED", "false").lower() in ("1", "true", "yes", "on")
            scope_groups = state.get("rag_scope_groups") or []
            allow_global_scope = bool(state.get("rag_allow_global", False))
            allow_group_scope = bool(state.get("rag_allow_groups", bool(scope_groups)))
            graphs = []
            hop_count = int(route_config.get("graph_hops") or state.get("graph_hops") or 2)
            if neo4j_only:
                try:
                    from app.services.rag.core.neo4j_mvp import (
                        get_neo4j_mvp,
                        build_graph_context,
                        LegalEntityExtractor,
                    )
                    neo4j = get_neo4j_mvp()
                    if neo4j.health_check():
                        query_entities = LegalEntityExtractor.extract(section_query)
                        entity_ids = [e.get("entity_id") for e in query_entities if e.get("entity_id")]
                        if entity_ids:
                            allowed_scopes: List[str] = []
                            if allow_global_scope:
                                allowed_scopes.append("global")
                            if state.get("tenant_id"):
                                allowed_scopes.append("private")
                            if allow_group_scope and scope_groups:
                                allowed_scopes.append("group")
                            if not allowed_scopes:
                                allowed_scopes = ["global"]
                            group_ids = [str(g) for g in (scope_groups or []) if g]
                            paths = neo4j.find_paths(
                                entity_ids=entity_ids[:10],
                                tenant_id=str(state.get("tenant_id") or "default"),
                                allowed_scopes=allowed_scopes,
                                group_ids=group_ids,
                                case_id=str(state.get("case_id")) if state.get("case_id") else None,
                                user_id=str(state.get("user_id")) if state.get("user_id") else None,
                                max_hops=hop_count,
                                limit=15,
                                include_arguments=False,
                            )
                            if paths and build_graph_context is not None:
                                graph_context = build_graph_context(paths, max_chars=4000)
                                graph_primary_hit = True
                except Exception as exc:
                    logger.warning(f"⚠️ Neo4j-only GraphRAG failed: {exc}")
            else:
                private_scope_id = state.get("tenant_id") if use_tenant_graph else None
                private_graph = get_scoped_knowledge_graph(scope="private", scope_id=private_scope_id)
                if private_graph:
                    graphs.append(("private", private_graph))
                if allow_global_scope:
                    global_graph = get_scoped_knowledge_graph(scope="global", scope_id=None)
                    if global_graph:
                        graphs.append(("global", global_graph))
                if allow_group_scope:
                    for gid in scope_groups:
                        if not gid:
                            continue
                        group_graph = get_scoped_knowledge_graph(scope="group", scope_id=str(gid))
                        if group_graph:
                            graphs.append((f"group:{gid}", group_graph))
                for scope, graph in graphs:
                    graph_context, _ = graph.query_context_from_text(
                        section_query,
                        hops=hop_count,
                    )
                    if graph_context:
                        graph_primary_hit = True
                        graph_used = graph
                        graph_used_scope = scope
                        break
                if not graph_used and private_graph:
                    graph_used = private_graph
                    graph_used_scope = "private"

        # Step 1: Primary search (HyDE if flagged, otherwise hybrid)
        if not graph_primary_hit:
            if use_hyde:
                model_id = state.get("strategist_model") or state.get("judge_model") or DEFAULT_JUDGE_MODEL
                hyde_query = await _build_hyde_query(model_id, section_title, thesis, input_text)
                search_query = hyde_query or section_query
                logger.info(f"🧪 [RAG Pipeline] HyDE ativado para seção '{section_title}'")
                rag_results = rag_manager.hyde_search(
                    query=search_query,
                    sources=effective_sources,
                    top_k=effective_top_k,
                    tenant_id="default",
                    group_ids=scope_groups,
                    include_global=allow_global_scope,
                    allow_group_scope=allow_group_scope,
                    request_id=request_id,
                )
            else:
                rag_results = rag_manager.hybrid_search(
                    query=section_query,
                    sources=effective_sources,
                    top_k=effective_top_k,
                    bm25_weight=bm25_weight,
                    semantic_weight=semantic_weight,
                    tenant_id="default",
                    group_ids=scope_groups,
                    include_global=allow_global_scope,
                    allow_group_scope=allow_group_scope,
                    request_id=request_id,
                )
        route_config["results_count"] = len(rag_results) if isinstance(rag_results, list) else 0

        if state.get("crag_gate_enabled") and rag_results:
            gate = crag_gate_retrieve(
                rag_results,
                min_best_score=float(state.get("crag_min_best_score", 0.45)),
                min_avg_top3_score=float(state.get("crag_min_avg_score", 0.35)),
            )
            route_config["crag_gate"] = gate
            safe_mode = not gate.get("gate_passed", True)
            retries = 0
            retry_sources = effective_sources
            if rag_retry_expand_scope and route_config["strategy"] == STRATEGY_LOCAL_ONLY and audit_mode != "sei_only":
                retry_sources = [s for s in rag_sources if s != "sei"] or ["lei", "juris", "pecas_modelo"]
                logger.info(f"🔄 [RAG Retry] Expandindo fontes LOCAL_ONLY → {retry_sources}")
            while safe_mode and retries < max_rag_retries:
                retries += 1
                logger.info(
                    f"🔄 [RAG Retry] Tentativa {retries}/{max_rag_retries} para seção '{section_title}' | "
                    f"Fontes: {retry_sources} | Razão: CRAG gate falhou (best={gate.get('best_score', 0):.2f})"
                )
                retry_results = rag_manager.hybrid_search(
                    query=section_query,
                    sources=retry_sources,
                    top_k=min(effective_top_k * 2, 20),
                    bm25_weight=0.6,
                    semantic_weight=0.4,
                    tenant_id="default",
                    group_ids=scope_groups,
                    include_global=allow_global_scope,
                    allow_group_scope=allow_group_scope,
                    request_id=request_id,
                )
                retry_gate = crag_gate_retrieve(
                    retry_results,
                    min_best_score=float(state.get("crag_min_best_score", 0.45)),
                    min_avg_top3_score=float(state.get("crag_min_avg_score", 0.35)),
                )
                if retry_gate.get("gate_passed", False):
                    logger.info(f"✅ [RAG Retry] Sucesso na tentativa {retries} para '{section_title}'")
                    rag_results = retry_results
                    safe_mode = False
                    break
                else:
                    logger.warning(
                        f"⚠️ [RAG Retry] Tentativa {retries} falhou para '{section_title}' | "
                        f"best={retry_gate.get('best_score', 0):.2f}, avg_top3={retry_gate.get('avg_top3', 0):.2f}"
                    )

        if rag_results:
            section_rag_context = rag_manager.format_sources_for_prompt(rag_results, max_chars=4000)

        # Step 2: GraphRAG enrichment (v5.8: now uses use_graph flag, not just strategy)
        if use_graph and not graph_context:
            if neo4j_only:
                try:
                    from app.services.rag.core.neo4j_mvp import (
                        get_neo4j_mvp,
                        build_graph_context,
                        LegalEntityExtractor,
                    )
                    neo4j = get_neo4j_mvp()
                    if neo4j.health_check():
                        query_entities = LegalEntityExtractor.extract(section_query)
                        entity_ids = [e.get("entity_id") for e in query_entities if e.get("entity_id")]
                        if entity_ids:
                            allowed_scopes: List[str] = []
                            if allow_global_scope:
                                allowed_scopes.append("global")
                            if state.get("tenant_id"):
                                allowed_scopes.append("private")
                            if allow_group_scope and scope_groups:
                                allowed_scopes.append("group")
                            if not allowed_scopes:
                                allowed_scopes = ["global"]
                            group_ids = [str(g) for g in (scope_groups or []) if g]
                            paths = neo4j.find_paths(
                                entity_ids=entity_ids[:10],
                                tenant_id=str(state.get("tenant_id") or "default"),
                                allowed_scopes=allowed_scopes,
                                group_ids=group_ids,
                                case_id=str(state.get("case_id")) if state.get("case_id") else None,
                                user_id=str(state.get("user_id")) if state.get("user_id") else None,
                                max_hops=int(route_config.get("graph_hops") or state.get("graph_hops") or 2),
                                limit=15,
                                include_arguments=False,
                            )
                            if paths and build_graph_context is not None:
                                graph_context = build_graph_context(paths, max_chars=4000)
                except Exception as exc:
                    logger.warning(f"⚠️ Neo4j-only GraphRAG enrichment failed: {exc}")
            elif graph_used:
                rag_chunks = rag_results or []
                if not rag_chunks and base_context:
                    rag_chunks = [{"text": base_context[:2000], "metadata": {}}]
                logger.info(f"🔗 [RAG Pipeline] GraphRAG ativado para seção '{section_title}' (hops={route_config.get('graph_hops', 2)})")
                graph_context = graph_used.enrich_context(
                    rag_chunks,
                    hops=int(route_config.get("graph_hops") or state.get("graph_hops") or 2)
                ) or ""

    if not use_external_context:
        return "", route_config, safe_mode

    if bool(state.get("argument_graph_enabled")):
        if neo4j_only:
            try:
                from app.services.rag.core.argument_neo4j import get_argument_neo4j
                arg_svc = get_argument_neo4j()
                arg_ctx, _arg_stats = arg_svc.get_debate_context(
                    results=rag_results or [],
                    tenant_id=str(state.get("tenant_id") or "default"),
                    case_id=str(state.get("case_id")) if state.get("case_id") else None,
                )
                argument_context = arg_ctx or ""
            except Exception as exc:
                logger.warning(f"⚠️ Neo4j ArgumentRAG failed for section '{section_title}': {exc}")
                argument_context = ""
        elif graph_used and (graph_used_scope or "").startswith("private"):
            try:
                from app.services.argument_pack import ARGUMENT_PACK
                argument_context = ARGUMENT_PACK.build_debate_context_from_query(
                    graph_used,
                    section_query,
                    hops=int(route_config.get("graph_hops") or state.get("graph_hops") or 2),
                ) or ""
            except Exception as exc:
                logger.warning(f"⚠️ ArgumentRAG failed for section '{section_title}': {exc}")
                argument_context = ""

    section_context = _merge_context_blocks(
        [argument_context, graph_context, section_rag_context, base_context],
        max_chars=6000,
    )
    return section_context, route_config, safe_mode




# --- DOCUMENT STATE ---

class DocumentState(TypedDict):
    # Input
    input_text: str
    mode: str
    doc_kind: Optional[str]
    doc_subtype: Optional[str]
    tese: str
    job_id: str
    messages: List[Dict[str, Any]] # Chat history for RAG Memory
    conversation_id: Optional[str]
    
    # Config
    deep_research_enabled: bool
    deep_research_provider: Optional[str]
    deep_research_model: Optional[str]
    deep_research_effort: Optional[str]
    deep_research_points_multiplier: Optional[float]
    deep_research_search_focus: Optional[str]
    deep_research_domain_filter: Optional[str]
    deep_research_search_after_date: Optional[str]
    deep_research_search_before_date: Optional[str]
    deep_research_last_updated_after: Optional[str]
    deep_research_last_updated_before: Optional[str]
    deep_research_country: Optional[str]
    deep_research_latitude: Optional[str]
    deep_research_longitude: Optional[str]
    web_search_enabled: bool
    web_search_model: Optional[str]
    search_mode: str
    perplexity_search_mode: Optional[str]
    perplexity_search_type: Optional[str]
    perplexity_search_context_size: Optional[str]
    perplexity_search_classifier: bool
    perplexity_disable_search: bool
    perplexity_stream_mode: Optional[str]
    perplexity_search_domain_filter: Optional[str]
    perplexity_search_language_filter: Optional[str]
    perplexity_search_recency_filter: Optional[str]
    perplexity_search_after_date: Optional[str]
    perplexity_search_before_date: Optional[str]
    perplexity_last_updated_after: Optional[str]
    perplexity_last_updated_before: Optional[str]
    perplexity_search_max_results: Optional[int]
    perplexity_search_max_tokens: Optional[int]
    perplexity_search_max_tokens_per_page: Optional[int]
    perplexity_search_country: Optional[str]
    perplexity_search_region: Optional[str]
    perplexity_search_city: Optional[str]
    perplexity_search_latitude: Optional[str]
    perplexity_search_longitude: Optional[str]
    perplexity_return_images: bool
    perplexity_return_videos: bool
    research_mode: str
    last_research_step: str
    web_search_insufficient: bool
    need_juris: bool
    research_policy: str
    planning_reasoning: Optional[str]
    planned_queries: Optional[List[str]]  # Queries auto-generated by planner
    multi_query: bool
    breadth_first: bool
    use_multi_agent: bool
    thinking_level: str
    chat_personality: str
    temperature: float
    target_pages: int
    min_pages: int
    max_pages: int
    audit_mode: str
    quality_profile: str
    target_section_score: float
    target_final_score: float
    max_rounds: int
    max_final_review_loops: Optional[int]
    recursion_limit: int
    stream_tokens: bool
    stream_token_chunk_chars: int
    max_research_verifier_attempts: int
    max_rag_retries: int
    refinement_round: int
    strict_document_gate: bool
    hil_section_policy: str
    force_final_hil: bool
    max_web_search_requests: Optional[int]
    max_granular_passes: Optional[int]
    hil_iterations_cap: Optional[int]
    hil_iterations_count: int
    hil_iterations_by_checkpoint: Dict[str, int]

    # Budget (approved at quote time; soft caps only, never hard-stop)
    budget_approved_points: Optional[int]
    budget_estimate_points: Optional[int]
    budget_stage: Optional[str]
    budget_spent_points: Optional[int]
    budget_remaining_points: Optional[int]
    
    # v4.1: CRAG Gate & Adaptive Routing (unified with CLI)
    crag_gate_enabled: bool
    adaptive_routing_enabled: bool
    crag_min_best_score: float  # default 0.45
    crag_min_avg_score: float   # default 0.35
    rag_sources: List[str]
    rag_top_k: int
    rag_retry_expand_scope: bool
    case_bundle_text_pack: str
    case_bundle_pdf_paths: List[str]
    case_bundle_processo_id: Optional[str]
    
    # Formatting/meta
    formatting_options: Optional[Dict[str, Any]]
    template_structure: Optional[str]
    citation_style: str
    
    # Context for HIL Decision (from user request)
    destino: str  # uso_interno, cliente, contraparte, autoridade, regulador
    risco: str    # baixo, medio, alto
    
    # Outline
    outline: List[str]

    # Section-level HIL (optional): review/approve specific sections before proceeding
    hil_target_sections: List[str]
    hil_section_payload: Optional[Dict[str, Any]]  # payload for current section under review

    # Outline-level HIL (optional): review/approve outline before proceeding to research/debate
    hil_outline_enabled: bool
    hil_outline_payload: Optional[Dict[str, Any]]  # payload for outline under review
    auto_approve_hil: bool

    # Model selection (canonical ids)
    judge_model: str
    gpt_model: str
    claude_model: str
    strategist_model: Optional[str]
    drafter_models: List[str]
    reviewer_models: List[str]
    
    # Research
    research_context: Optional[str]
    research_sources: List[Dict[str, Any]]
    research_notes: Optional[str]
    citations_map: Optional[Dict[str, Any]]
    # Deep Research UX (para SSE/UI)
    deep_research_thinking_steps: Optional[List[Dict[str, Any]]]
    deep_research_from_cache: Optional[bool]
    deep_research_streamed: Optional[bool]

    # Research Verification
    verifier_attempts: int
    verification_retry: bool
    verification_retry_reason: Optional[str]
    research_retry_progress: Optional[str]  # e.g. "2/3" for UI display
    
    # RAG Routing Observability (per-section route reasons)
    section_routing_reasons: Dict[str, Dict[str, Any]]  # {section_title: {strategy, reason, sources, ...}}
    
    # Sections (processed)
    processed_sections: List[Dict[str, Any]]
    full_document: str
    full_document_ref: Optional[str]
    full_document_preview: Optional[str]
    full_document_chars: Optional[int]
    draft_document_ref: Optional[str]
    draft_document_preview: Optional[str]
    draft_document_chars: Optional[int]
    
    # Divergence
    has_any_divergence: bool
    divergence_summary: str
    
    # Audit
    audit_status: Literal["aprovado", "aprovado_ressalvas", "reprovado"]
    audit_report: Optional[Dict[str, Any]]
    audit_issues: List[str]
    sei_context: Optional[str]
    fact_check_summary: Optional[str]
    document_checklist_hint: Optional[List[Dict[str, Any]]]
    document_checklist: Optional[Dict[str, Any]]
    document_gate_status: Optional[Literal["passed", "BLOCKED_CRITICAL", "BLOCKED_OPTIONAL_HIL"]]  # v5.5: Severity typing
    document_gate_missing: List[Dict[str, Any]]
    citation_validation_report: Optional[Dict[str, Any]]
    citation_used_keys: List[str]
    citation_missing_keys: List[str]
    citation_orphan_keys: List[str]

    # Citer/Verifier (B2 - Pre-Debate Gate)
    citer_verifier_result: Optional[Dict[str, Any]]
    verified_context: Optional[str]
    citer_verifier_force_hil: bool
    citer_verifier_coverage: Optional[float]
    citer_verifier_critical_gaps: List[str]
    citer_min_coverage: float  # Config: minimum coverage to pass (default 0.6)
    citer_block_debate_coverage: float  # Config: coverage threshold to block debate (default 0.3)
    citer_block_debate_min_unverified: int  # Config: min unverified claims to block (default 1)

    # Style Check (editorial gate)
    style_report: Optional[Dict[str, Any]]
    style_score: Optional[float]
    style_tone: Optional[str]
    style_issues: List[str]
    style_term_variations: List[Dict[str, Any]]
    style_check_status: Optional[str]
    style_check_payload: Optional[Dict[str, Any]]
    style_instruction: Optional[str]
    style_refine_round: int
    style_refine_max_rounds: int
    style_min_score: float
    
    # HIL Decision Engine
    hil_checklist: Optional[Dict[str, Any]]  # Serialized HILChecklist
    hil_risk_score: Optional[float]
    hil_risk_reasons: List[str]
    hil_risk_level: Optional[str]
    
    # Correction (Audit Feedback Loop)
    proposed_corrections: Optional[str]
    corrections_diff: Optional[str]
    human_approved_corrections: bool

    # Quality Pipeline (v2.25)
    quality_gate_passed: bool
    quality_gate_results: List[Dict[str, Any]]
    quality_gate_force_hil: bool
    structural_fix_result: Optional[Dict[str, Any]]
    patch_result: Optional[Dict[str, Any]]
    patches_applied: List[Dict[str, Any]]
    targeted_patch_used: bool
    quality_report: Optional[Dict[str, Any]]
    quality_report_markdown: Optional[str]
    
    # Human Decisions
    human_approved_divergence: bool
    human_approved_final: bool
    human_edits: Optional[str]
    divergence_hil_round: int
    max_divergence_hil_rounds: int
    divergence_hil_instructions: Optional[str]
    document_overridden_by_human: bool
    json_parse_failures: List[Dict[str, Any]]

    # HIL History (v5.6) - Audit trail of all human interactions
    hil_history: List[Dict[str, Any]]
    
    # Committee Review (v5.2)
    committee_review_report: Optional[Dict[str, Any]]
    
    # Context Caching (v5.3)
    context_cache_name: Optional[str]
    context_cache_created: bool
    
    # Human Proposal Debate (v5.4)
    human_proposal: Optional[str]
    proposal_scope: Optional[str]  # "section" or "final"
    proposal_target_section: Optional[str]
    proposal_evaluation: Optional[Dict[str, Any]]
    
    # Final
    final_markdown: str
    final_decision: Optional[str]
    final_decision_reasons: List[str]
    final_decision_score: Optional[float]
    final_decision_target: Optional[float]


# --- FINAL DECISION HELPERS ---

FINAL_DECISIONS = ("APPROVED", "NEED_EVIDENCE", "NEED_REWRITE", "NEED_HUMAN_REVIEW")

def _collect_final_decision_reasons(state: DocumentState) -> Dict[str, Any]:
    reasons: List[str] = []

    checklist = state.get("document_checklist") or {}
    missing_critical = checklist.get("missing_critical", []) or []
    missing_noncritical = checklist.get("missing_noncritical", []) or []
    if missing_critical:
        reasons.append("missing_critical_docs")
    if missing_noncritical:
        reasons.append("missing_noncritical_docs")

    audit_status = state.get("audit_status")
    if audit_status == "reprovado":
        reasons.append("audit_reprovado")
    elif audit_status == "aprovado_ressalvas":
        reasons.append("audit_ressalvas")

    if state.get("has_any_divergence"):
        reasons.append("divergence_detected")

    if state.get("quality_gate_force_hil"):
        reasons.append("quality_gate_force_hil")

    citer_result = state.get("citer_verifier_result") or {}
    if isinstance(citer_result, dict):
        if citer_result.get("force_hil"):
            reasons.append("citer_verifier_force_hil")
        if citer_result.get("block_debate"):
            reasons.append("citer_verifier_block_debate")

    report = state.get("committee_review_report") or {}
    score = report.get("score")
    if score is None:
        try:
            score = float(report.get("nota_consolidada"))
        except Exception:
            score = None
    target = state.get("target_final_score")
    catalog_spec = None
    try:
        target = float(target) if target is not None else None
    except Exception:
        target = None
    if score is not None and target is not None and score < target:
        reasons.append("score_below_target")
    if report.get("score_disagreement"):
        reasons.append("agent_disagreement")

    return {"reasons": reasons, "score": score, "target": target}


def _with_final_decision(
    state: DocumentState,
    decision: str,
    extra_reasons: Optional[List[str]] = None
) -> DocumentState:
    payload = _collect_final_decision_reasons(state)
    reasons = payload["reasons"]
    if extra_reasons:
        for item in extra_reasons:
            if item and item not in reasons:
                reasons.append(item)

    return {
        **state,
        "final_decision": decision,
        "final_decision_reasons": reasons,
        "final_decision_score": payload["score"],
        "final_decision_target": payload["target"],
    }

# --- RECURSION LIMIT VALIDATION ---


def _validate_recursion_limit(state: DocumentState) -> Dict[str, Any]:
    """
    Validates that the configured recursion_limit is sufficient for the current settings.
    Returns a dict with 'warning' (str or None), 'estimated_steps', 'current_limit', 
    and optionally 'suggested_limit'.
    """
    try:
        # Extract configuration
        num_sections = len(state.get("outline") or []) or 8  # Default estimate
        max_rounds = int(state.get("max_rounds") or 1)
        style_refine_rounds = int(state.get("style_refine_max_rounds") or 0)
        max_rag_retries = int(state.get("max_rag_retries") or 0)
        recursion_limit = int(state.get("recursion_limit") or 50)
        
        # Estimate steps:
        # - Per section: R1 (1) + R2-R3 loop (max_rounds * 2) + R4 (1) = 2 + max_rounds*2
        # - Plus: quality gates, HIL nodes, style refine, research, etc.
        base_workflow_steps = 15  # Research, outline, planning, audit, finalize, etc.
        steps_per_section = 2 + (max_rounds * 2)  # R1, (R2, R3)*N, R4
        section_steps = num_sections * steps_per_section
        quality_steps = num_sections * 3  # quality_gate, structural_fix, targeted_patch
        style_steps = num_sections * style_refine_rounds * 2  # style_check + style_refine per round
        rag_steps = max_rag_retries * 2  # Per retry: research + verify
        
        estimated_steps = base_workflow_steps + section_steps + quality_steps + style_steps + rag_steps
        
        # Add safety buffer (20%)
        estimated_with_buffer = int(estimated_steps * 1.2)
        
        result: Dict[str, Any] = {
            "estimated_steps": estimated_steps,
            "estimated_with_buffer": estimated_with_buffer,
            "current_limit": recursion_limit,
            "warning": None,
            "suggested_limit": None,
        }
        
        if estimated_with_buffer > recursion_limit:
            result["warning"] = (
                f"⚠️ Configurações agressivas: ~{estimated_steps} passos estimados "
                f"(limite atual: {recursion_limit}). "
                f"Considere aumentar o limite ou reduzir rodadas/seções."
            )
            result["suggested_limit"] = estimated_with_buffer + 10
            logger.warning(result["warning"])
        elif estimated_with_buffer > recursion_limit * 0.8:
            result["warning"] = (
                f"⚡ Configurações próximas do limite: ~{estimated_steps}/{recursion_limit} passos. "
                f"Fluxo pode ser interrompido se houver retries."
            )
            logger.info(result["warning"])
        else:
            logger.info(f"✅ Recursion limit OK: ~{estimated_steps}/{recursion_limit} passos estimados")
        
        return result
    except Exception as e:
        logger.warning(f"⚠️ Could not validate recursion limit: {e}")
        return {"warning": None, "estimated_steps": 0, "current_limit": 50}


# --- NODES ---


def _build_outline_fixed_context(
    state: "DocumentState",
    required_sections: Optional[List[str]] = None
) -> str:
    """Builds deterministic fixed preferences for outline generation."""
    items = []
    doc_subtype = state.get("doc_subtype") or state.get("mode")
    if doc_subtype:
        items.append(f"Tipo de documento: {doc_subtype}")

    min_pages = int(state.get("min_pages") or 0)
    max_pages = int(state.get("max_pages") or 0)
    if min_pages or max_pages:
        if min_pages and max_pages:
            size_label = f"{min_pages}–{max_pages}"
        elif min_pages:
            size_label = f"mínimo {min_pages}"
        else:
            size_label = f"máximo {max_pages}"
        items.append(f"Tamanho alvo (páginas): {size_label}")

    chat_personality = (state.get("chat_personality") or "").strip()
    if chat_personality:
        items.append(f"Tom/estilo: {chat_personality}")

    style_instruction = (state.get("style_instruction") or "").strip()
    if style_instruction:
        items.append(f"Preferência de estilo: {style_instruction}")

    destino = (state.get("destino") or "").strip()
    if destino:
        items.append(f"Destino: {destino}")

    risco = (state.get("risco") or "").strip()
    if risco:
        items.append(f"Risco: {risco}")

    if required_sections:
        items.append(f"Seções obrigatórias: {', '.join(required_sections)}")

    if not items:
        return ""

    return "## Preferências Fixas\n" + "\n".join([f"- {item}" for item in items])


def _build_chat_context(messages: List[Dict[str, Any]], max_user_msgs: int = 8) -> str:
    """Extracts recent user instructions from chat history."""
    if not messages:
        return ""

    user_msgs = [m for m in messages if m.get("role") == "user"]
    if not user_msgs:
        return ""

    recent = user_msgs[-max_user_msgs:]
    # Limit message length to avoid blowing up context
    block = "\n".join([f"- {str(m.get('content', '')).strip()[:500]}" for m in recent])

    return f"## Instruções do Usuário (Chat Recente)\n{block}"


async def outline_node(state: DocumentState) -> DocumentState:

    """Generate document outline"""
    logger.info("📑 [Phase2] Generating Outline...")
    
    mode = state.get("mode", "PETICAO")
    doc_kind = state.get("doc_kind")
    doc_subtype = state.get("doc_subtype") or mode

    raw_override = state.get("outline_override") or state.get("outlineOverride")
    if raw_override:
        min_pages = int(state.get("min_pages") or 0)
        max_pages = int(state.get("max_pages") or 0)
        if isinstance(raw_override, str):
            override_items = [s.strip() for s in raw_override.splitlines() if s.strip()]
        elif isinstance(raw_override, list):
            override_items = [str(s).strip() for s in raw_override if str(s).strip()]
        else:
            override_items = []
        override_items = list(dict.fromkeys(override_items))
        if override_items:
            outline = _adjust_outline_to_range(override_items, min_pages, max_pages)
            logger.info(f"✅ Outline override aplicado: {len(outline)} sections")
            _emit_event(
                state,
                "outline_generated",
                {"outline": outline, "outline_len": len(outline), "outline_source": "override"},
                phase="outline",
                node="gen_outline",
            )
            return {**state, "outline": outline}
    
    # v5.7: Validate document size against model capacity
    primary_model = state.get("strategist_model") or state.get("judge_model") or DEFAULT_JUDGE_MODEL
    size_validation = _validate_document_size(state, primary_model)
    if size_validation.get("warning"):
        # Emit warning event for UI
        job_id = state.get("job_id")
        if job_id:
            try:
                job_manager.emit_event(job_id, size_validation["warning"])
            except Exception as e:
                logger.warning(f"⚠️ Could not emit size warning: {e}")
        # Store warning in state for later reference
        state = {**state, "document_size_warning": size_validation["warning"]}
    
    # v6.0: Validate recursion limit against aggressive configurations
    recursion_validation = _validate_recursion_limit(state)
    if recursion_validation.get("warning"):
        job_id = state.get("job_id")
        if job_id:
            try:
                job_manager.emit_event(job_id, recursion_validation["warning"])
            except Exception:
                pass
        state = {**state, "recursion_limit_warning": recursion_validation["warning"]}
    
    # v5.0: Dynamic Outline Generation (Unification with CLI)
    try:
        strategist_model = state.get("strategist_model") or state.get("judge_model") or DEFAULT_JUDGE_MODEL
        min_pages = int(state.get("min_pages") or 0)
        max_pages = int(state.get("max_pages") or 0)
        size_guidance = _outline_size_guidance(min_pages, max_pages)
        
        # v5.7: Improved prompt structure with explicit ROLE, TASK, CONTEXT, RULES
        try:
            from app.services.ai.prompt_constants import (
                ROLE_STRATEGIST, OUTPUT_FORMAT_OUTLINE, 
                get_required_sections, get_outline_example
            )
        except ImportError:
            ROLE_STRATEGIST = "Você é um estrategista jurídico sênior."
            OUTPUT_FORMAT_OUTLINE = "Retorne apenas a lista de seções, uma por linha."
            get_required_sections = lambda m, doc_kind=None, doc_subtype=None: []
            get_outline_example = lambda m: ""

        numbering_hint = "Use numeração romana (I, II, III...) para seções principais"
        structure_hint = "Ordene logicamente: fatos → preliminares → mérito → pedidos/conclusão"
        catalog_spec = None
        try:
            from app.services.ai.nodes.catalogo_documentos import (
                get_template,
                get_numbering_instruction,
                get_structure_hint,
                infer_doc_kind_subtype,
            )
            if not doc_kind and doc_subtype:
                doc_kind, _ = infer_doc_kind_subtype(doc_subtype)
            if doc_kind and doc_subtype:
                catalog_spec = get_template(doc_kind, doc_subtype)
            if catalog_spec:
                numbering_hint = get_numbering_instruction(catalog_spec.numbering)
                structure_hint = get_structure_hint(doc_kind, doc_subtype) or structure_hint
        except Exception:
            catalog_spec = None

        required_sections = get_required_sections(mode, doc_kind=doc_kind, doc_subtype=doc_subtype)
        required_hint = f"Seções típicas para {doc_subtype}: {', '.join(required_sections)}" if required_sections else ""
        outline_example = get_outline_example(mode)

        rules = [
            numbering_hint,
            structure_hint,
            required_hint,
            size_guidance,
        ]
        rules = [r for r in rules if r]
        rules_block = "\n".join([f"{i + 1}. {r}" for i, r in enumerate(rules)]) or "1. Mantenha coerência estrutural."

        fixed_context = _build_outline_fixed_context(state, required_sections=required_sections)
        chat_context = _build_chat_context(state.get("messages", []))

        prompt = f"""
# ROLE
{ROLE_STRATEGIST}

# TASK
Crie o sumário (outline) para um documento do tipo {doc_subtype} baseado no caso abaixo.

# CONTEXT
## Resumo do Caso
{state.get("input_text", "")[:4000]}

## Tese/Objetivo
{state.get("tese", "")}

{fixed_context}

{chat_context}

# RULES
{rules_block}

# OUTPUT FORMAT
{OUTPUT_FORMAT_OUTLINE}

{outline_example}
""".strip()

        with billing_context(node="outline_node", size="S"):
            response = await _call_model_any_async(
                strategist_model,
                prompt,
                temperature=0.2,
                max_tokens=600
            )
        outline = _parse_outline_response(response)
        outline = _adjust_outline_to_range(outline, min_pages, max_pages)
        
        if not outline:
            logger.warning(f"⚠️ Dynamic outline failed for {mode}, using fallback.")
            raise ValueError("Empty outline")
            
        logger.info(f"✅ Dynamic Outline Generated: {len(outline)} sections")
        
    except Exception as e:
        logger.error(f"❌ Error generating dynamic outline: {e}. Using static fallback.")
        # Fallbacks for robustness
        if not catalog_spec:
            try:
                from app.services.ai.nodes.catalogo_documentos import (
                    get_template,
                    build_default_outline,
                    infer_doc_kind_subtype,
                )
                if not doc_kind and doc_subtype:
                    doc_kind, _ = infer_doc_kind_subtype(doc_subtype)
                if doc_kind and doc_subtype:
                    catalog_spec = get_template(doc_kind, doc_subtype)
                if catalog_spec:
                    outline = build_default_outline(catalog_spec)
            except Exception:
                catalog_spec = None
        if catalog_spec:
            try:
                from app.services.ai.nodes.catalogo_documentos import build_default_outline
                outline = outline or build_default_outline(catalog_spec)
            except Exception:
                outline = outline or []
        elif mode == "PARECER":
            outline = [
                "I - RELATÓRIO",
                "II - FUNDAMENTAÇÃO JURÍDICA",
                "III - CONCLUSÃO E OPINATIVO"
            ]
        elif mode == "CONTESTACAO":
            outline = [
                "I - SÍNTESE DOS FATOS",
                "II - PRELIMINARES",
                "III - DO MÉRITO",
                "IV - DOS PEDIDOS"
            ]
        elif mode in ["NOTA_TECNICA", "NOTA_JURIDICA"]:
            outline = [
                "1. IDENTIFICAÇÃO",
                "2. ANÁLISE DO PROBLEMA",
                "3. FUNDAMENTAÇÃO TÉCNICA",
                "4. CONCLUSÃO"
            ]
        elif mode in ["OFICIO", "CI"]:
            outline = [
                "1. CABEÇALHO",
                "2. ASSUNTO",
                "3. CORPO DO TEXTO",
                "4. ENCERRAMENTO"
            ]
        else:
            outline = [
                "I - DOS FATOS",
                "II - DO DIREITO",
                "III - DOS PEDIDOS"
            ]

        min_pages = int(state.get("min_pages") or 0)
        max_pages = int(state.get("max_pages") or 0)
        outline = _adjust_outline_to_range(outline, min_pages, max_pages)
    
    _emit_event(
        state,
        "outline_generated",
        {"outline": outline, "outline_len": len(outline)},
        phase="outline",
        node="gen_outline",
    )
    return {**state, "outline": outline}


async def outline_hil_node(state: DocumentState) -> DocumentState:
    """
    HIL Checkpoint: Outline approval/edit

    When enabled, pauses after outline generation so the user can approve or edit
    the outline (sumário/esqueleto) before research/debate begins.
    """
    if state.get("auto_approve_hil", False) or not state.get("hil_outline_enabled", False):
        return {**state, "hil_outline_payload": None}

    outline = state.get("outline", []) or []
    if not isinstance(outline, list):
        outline = []

    payload: Dict[str, Any] = {"outline": outline}
    state = {**state, "hil_outline_payload": payload}

    # v5.9: Emit observability event for frontend
    _emit_event(
        state,
        "hil_outline_waiting",
        {
            "checkpoint": "outline",
            "outline": outline,
            "message": "Aguardando aprovação do sumário/esqueleto."
        },
        phase="hil",
        node="outline_hil",
    )

    decision, state, skipped = _try_hil_interrupt(
        state,
        "outline",
        {
            "type": "outline_review",
            "checkpoint": "outline",
            "message": "Revise o esqueleto (sumário) antes de iniciar a geração.",
            "outline": outline,
        },
    )
    if skipped:
        return {**state, "hil_outline_payload": None}

    # Keep interrupting until approved
    while not decision.get("approved", False):
        instr = (decision.get("instructions") or "").strip()
        if instr:
            payload["instructions"] = instr
            state = {**state, "hil_outline_payload": payload}

        decision, state, skipped = _try_hil_interrupt(
            state,
            "outline",
            {
                "type": "outline_review",
                "checkpoint": "outline",
                "message": "Outline rejeitada. Edite/aprove para continuar.",
                "outline": outline,
                **({"instructions": instr} if instr else {}),
            },
        )
        if skipped:
            return {**state, "hil_outline_payload": None}

    edits = decision.get("edits")
    if isinstance(edits, str) and edits.strip():
        # Accept newline-separated list
        new_outline = [l.strip() for l in edits.split("\n") if l.strip()]
        if new_outline:
            outline = new_outline
    elif isinstance(edits, list):
        # Accept direct list of strings if frontend sends it
        new_outline = [str(l).strip() for l in edits if str(l).strip()]
        if new_outline:
            outline = new_outline

    hil_targets = decision.get("hil_target_sections")
    if isinstance(hil_targets, list):
        cleaned_targets = [str(t).strip() for t in hil_targets if str(t).strip()]
        return {
            **state,
            "outline": outline,
            "hil_outline_payload": None,
            "hil_target_sections": cleaned_targets
        }

    return {**state, "outline": outline, "hil_outline_payload": None}


def _normalize_queries(queries: Optional[List[str]]) -> List[str]:
    if not queries:
        return []
    cleaned = []
    seen = set()
    for item in queries:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        cleaned.append(text)
    return cleaned


def _resolve_cap_value(raw: Any, default: Optional[int] = None) -> Optional[int]:
    if raw is None:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    if value < 0:
        return default
    return value


def _cap_queries(queries: List[str], cap: Optional[int]) -> List[str]:
    if cap is None:
        return queries
    if cap <= 0:
        return []
    return queries[:cap]


def _contains_keywords(text: str, keywords: List[str]) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in keywords)

def _sanitize_thinking_text(text: str, max_len: int = 280) -> str:
    if not text:
        return ""
    cleaned = re.sub(r"\s+", " ", str(text)).strip()
    if len(cleaned) <= max_len:
        return cleaned
    trimmed = cleaned[:max_len].rsplit(" ", 1)[0].strip()
    return trimmed or cleaned[:max_len]


def _sanitize_thinking_steps(steps: List[Dict[str, Any]], max_items: int = 30) -> List[Dict[str, Any]]:
    safe_steps: List[Dict[str, Any]] = []
    for step in steps[:max_items]:
        if not isinstance(step, dict):
            continue
        text = _sanitize_thinking_text(step.get("text") or "")
        if not text:
            continue
        safe_steps.append({"text": text, "timestamp": step.get("timestamp")})
    return safe_steps


def _emit_event(
    state: Mapping[str, Any],
    event_type: str,
    data: Optional[Dict[str, Any]] = None,
    *,
    phase: Optional[str] = None,
    node: Optional[str] = None,
    section: Optional[str] = None,
    agent: Optional[str] = None,
) -> None:
    job_id = state.get("job_id")
    if not job_id:
        return
    job_manager.emit_event(
        job_id,
        event_type,
        data or {},
        phase=phase,
        node=node,
        section=section,
        agent=agent,
    )


LANGGRAPH_AUDIT_NODE_EVENTS = os.getenv("LANGGRAPH_AUDIT_NODE_EVENTS", "true").lower() == "true"


def _audit_channel_for_node(node_name: str) -> str:
    name = (node_name or "").strip()
    if name in ("gen_outline", "outline_hil", "planner"):
        return "outline"
    if name in ("deep_research", "web_search", "research_notes_step", "research_verify"):
        return "research"
    if name in ("fact_check",):
        return "fact_check"
    if name in ("debate",):
        return "debate"
    if name in ("audit",):
        return "audit"
    if name in ("quality_gate", "structural_fix", "targeted_patch", "gen_quality_report", "style_check", "style_refine", "refine_document"):
        return "quality"
    if name in ("document_gate",):
        return "document_gate"
    if name in ("evaluate_hil",):
        return "hil_decision"
    if name in ("divergence_hil", "section_hil", "correction_hil", "finalize_hil", "proposal_debate", "final_committee_review"):
        return "review"
    return "message"


def _summarize_value(value: Any, *, max_chars: int = 480) -> Any:
    if value is None:
        return None
    if isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        text = value.strip()
        if len(text) <= max_chars:
            return text
        return text[:max_chars].rsplit(" ", 1)[0].strip() or text[:max_chars]
    if isinstance(value, list):
        size = len(value)
        if not value:
            return {"type": "list", "len": 0}
        head = value[:5]
        if all(isinstance(x, (str, int, float, bool)) for x in head):
            return {"type": "list", "len": size, "head": head}
        return {"type": "list", "len": size}
    if isinstance(value, dict):
        keys = list(value.keys())
        sample = {}
        for k in keys[:12]:
            try:
                sample[str(k)] = _summarize_value(value.get(k), max_chars=160)
            except Exception:
                continue
        return {"type": "dict", "keys": keys[:25], "sample": sample}
    try:
        return str(value)[:max_chars]
    except Exception:
        return None


def _audit_state_summary(state: Mapping[str, Any]) -> Dict[str, Any]:
    input_text = state.get("input_text") or ""
    research_context = state.get("research_context") or ""
    processed = state.get("processed_sections") or []
    outline = state.get("outline") or []
    routing = state.get("section_routing_reasons") or {}
    routing_sample: Dict[str, Any] = {}
    if isinstance(routing, dict):
        for title in list(routing.keys())[:3]:
            try:
                item = routing.get(title) or {}
                if not isinstance(item, dict):
                    continue
                routing_sample[str(title)] = {
                    "strategy": item.get("strategy"),
                    "reason": _summarize_value(item.get("reason"), max_chars=180),
                    "sources": item.get("sources"),
                }
            except Exception:
                continue

    return {
        "job_id": state.get("job_id"),
        "request_id": state.get("request_id"),
        "mode": state.get("mode"),
        "audit_mode": state.get("audit_mode"),
        "web_search_enabled": state.get("web_search_enabled"),
        "deep_research_enabled": state.get("deep_research_enabled"),
        "thinking_level": state.get("thinking_level"),
        "input_text_chars": len(str(input_text)),
        "research_context_chars": len(str(research_context)),
        "full_document_ref": state.get("full_document_ref"),
        "full_document_chars": state.get("full_document_chars"),
        "outline_count": len(outline) if isinstance(outline, list) else None,
        "processed_sections_count": len(processed) if isinstance(processed, list) else None,
        "has_any_divergence": state.get("has_any_divergence"),
        "divergence_summary": _summarize_value(state.get("divergence_summary"), max_chars=220),
        "section_routing_reasons_count": len(routing) if isinstance(routing, dict) else None,
        "section_routing_reasons_sample": routing_sample,
        "final_decision": state.get("final_decision"),
        "final_decision_reasons": _summarize_value(state.get("final_decision_reasons"), max_chars=220),
    }


def _audit_updates_summary(updates: Any) -> Dict[str, Any]:
    if not isinstance(updates, dict):
        return {"type": type(updates).__name__}
    summary: Dict[str, Any] = {"keys": list(updates.keys())[:60]}
    previews: Dict[str, Any] = {}
    for k in list(updates.keys())[:25]:
        try:
            previews[str(k)] = _summarize_value(updates.get(k))
        except Exception:
            continue
    summary["previews"] = previews
    return summary


def _wrap_node(node_name: str, fn):
    async def wrapped(state: DocumentState):
        if LANGGRAPH_AUDIT_NODE_EVENTS:
            _emit_event(
                state,
                "node_start",
                {"node": node_name, "input": _audit_state_summary(state)},
                phase=_audit_channel_for_node(node_name),
                node=node_name,
            )
        started = time.time()
        try:
            result = await fn(state)
        except Exception as exc:
            duration_ms = round((time.time() - started) * 1000, 2)
            is_interrupt = bool(Interrupt) and isinstance(exc, Interrupt)  # type: ignore[arg-type]
            if LANGGRAPH_AUDIT_NODE_EVENTS:
                _emit_event(
                    state,
                    "node_interrupt" if is_interrupt else "node_error",
                    {
                        "node": node_name,
                        "duration_ms": duration_ms,
                        "error": _summarize_value(str(exc), max_chars=600),
                    },
                    phase=_audit_channel_for_node(node_name),
                    node=node_name,
                )
            raise
        duration_ms = round((time.time() - started) * 1000, 2)
        if LANGGRAPH_AUDIT_NODE_EVENTS:
            _emit_event(
                state,
                "node_end",
                {
                    "node": node_name,
                    "duration_ms": duration_ms,
                    "updates": _audit_updates_summary(result),
                },
                phase=_audit_channel_for_node(node_name),
                node=node_name,
            )
        return result
    return wrapped


def _iter_text_chunks(text: str, chunk_size: int):
    if not text:
        return
    size = max(1, int(chunk_size or 40))
    for i in range(0, len(text), size):
        yield text[i:i + size]


def _emit_section_stream(
    state: Mapping[str, Any],
    *,
    section_title: str,
    section_text: str,
    mode: str,
    reset: bool,
    chunk_size: int,
) -> None:
    section_text = section_text or ""
    header = f"# {mode}\n\n" if reset else ""
    if header:
        _emit_event(
            state,
            "token",
            {"delta": header, "reset": True},
            phase="debate",
            section=section_title,
        )
    _emit_event(
        state,
        "token",
        {"delta": f"## {section_title}\n\n"},
        phase="debate",
        section=section_title,
    )
    for chunk in _iter_text_chunks(section_text, chunk_size):
        _emit_event(
            state,
            "token",
            {"delta": chunk},
            phase="debate",
            section=section_title,
        )
    _emit_event(
        state,
        "token",
        {"delta": "\n\n---\n\n"},
        phase="debate",
        section=section_title,
    )


def _resolve_hil_cap(state: Mapping[str, Any]) -> Optional[int]:
    cap = state.get("hil_iterations_cap")
    if cap is None:
        return None
    try:
        cap_value = int(cap)
    except (TypeError, ValueError):
        return None
    if cap_value < 0:
        return None
    return cap_value


def _increment_hil_counters(state: DocumentState, checkpoint: str) -> DocumentState:
    total = int(state.get("hil_iterations_count") or 0) + 1
    per_checkpoint = dict(state.get("hil_iterations_by_checkpoint") or {})
    per_checkpoint[checkpoint] = int(per_checkpoint.get(checkpoint, 0)) + 1
    return {
        **state,
        "hil_iterations_count": total,
        "hil_iterations_by_checkpoint": per_checkpoint,
    }

def _apply_budget_soft_caps(state: "DocumentState", *, node: str) -> "DocumentState":
    """
    Soft budget supervisor.

    Goal: do NOT abort the workflow mid-run if the user has credits and approved a budget.
    Instead, progressively reduce optional/expensive loops/tools as we approach the approved budget.
    """
    job_id = state.get("job_id")
    if not job_id:
        return state

    approved_raw = state.get("budget_approved_points")
    if approved_raw is None:
        return state
    try:
        approved = int(approved_raw)
    except (TypeError, ValueError):
        return state
    if approved <= 0:
        return state

    counters = job_manager.get_api_counters(str(job_id))
    try:
        spent = int((counters or {}).get("points_total") or 0)
    except Exception:
        spent = 0
    remaining = approved - spent

    low_threshold = max(10, int(approved * 0.10))
    stage = "ok"
    if remaining <= 0:
        stage = "exhausted"
    elif remaining <= low_threshold:
        stage = "low"

    prev_stage = str(state.get("budget_stage") or "").strip() or None
    updated: Dict[str, Any] = {
        "budget_stage": stage,
        "budget_spent_points": spent,
        "budget_remaining_points": remaining,
    }

    if stage in ("low", "exhausted"):
        for key, cap_value in (
            ("max_web_search_requests", 1),
            ("max_final_review_loops", 1),
            ("style_refine_max_rounds", 1),
            ("max_granular_passes", 1),
        ):
            try:
                current = int(state.get(key) or 0)
            except Exception:
                current = 0
            if current > 0:
                updated[key] = min(current, cap_value)

        for key in ("max_research_verifier_attempts", "max_rag_retries"):
            try:
                current = int(state.get(key) or 0)
            except Exception:
                current = 0
            if current > 0:
                updated[key] = 0

    if stage == "exhausted":
        updated["deep_research_enabled"] = False
        updated["web_search_enabled"] = False

    if not prev_stage or prev_stage != stage:
        _emit_event(
            state,
            "billing_budget_stage",
            {
                "node": node,
                "stage": stage,
                "approved_points": approved,
                "spent_points": spent,
                "remaining_points": remaining,
                "low_threshold": low_threshold,
            },
            phase="billing",
            node=node,
        )

    return {**state, **updated}


def _try_hil_interrupt(
    state: DocumentState,
    checkpoint: str,
    payload: Dict[str, Any],
) -> Tuple[Optional[Dict[str, Any]], DocumentState, bool]:
    cap = _resolve_hil_cap(state)
    if cap is not None:
        used = int(state.get("hil_iterations_count") or 0)
        if used >= cap:
            _emit_event(
                state,
                "hil_budget_exhausted",
                {"checkpoint": checkpoint, "cap": cap, "used": used},
                phase="hil",
                node=checkpoint,
            )
            return None, state, True
    updated_state = _increment_hil_counters(state, checkpoint)
    decision = interrupt(payload)
    return decision, updated_state, False


async def deep_research_node(state: DocumentState) -> DocumentState:
    """Deep Research based on outline"""
    state = _apply_budget_soft_caps(state, node="deep_research")
    if not state.get("deep_research_enabled"):
        return state
        
    logger.info("🧠 [Phase2] Deep Research...")
    
    sections_summary = "\n".join([f"- {s}" for s in state.get("outline", [])])
    planned_queries = _normalize_queries(state.get("planned_queries"))
    mode = state.get("mode", "PETICAO")
    tese = state.get("tese", "")
    input_text = state.get("input_text", "") or ""
    base_query = f"""
Pesquisa jurídica para {mode}.
TESE: {tese}
CONTEXTO: {input_text[:1500]}
SEÇÕES: {sections_summary}
"""
    query = base_query
    if planned_queries:
        query += "\n\nFOCO DA PESQUISA (Queries Planejadas):\n"
        query += "\n".join([f"- {q}" for q in planned_queries[:6]])
    
    job_id = state.get("job_id")
    streamed_any = False
    from_cache = False
    thinking_steps: List[Dict[str, Any]] = []
    final_report = ""
    sources: List[Dict[str, Any]] = []

    if job_id:
        _emit_event(
            state,
            "research_start",
            {
                "researchmode": "deep",
                "plannedqueries": planned_queries,
                "query_preview": _sanitize_thinking_text(query, max_len=160),
            },
            phase="research",
            node="deep_research",
        )

    deep_provider = (state.get("deep_research_provider") or "auto").strip().lower()
    deep_model = state.get("deep_research_model")
    deep_search_focus = normalize_perplexity_search_mode(state.get("deep_research_search_focus"))
    deep_domain_filter = parse_csv_list(state.get("deep_research_domain_filter"), max_items=20)
    deep_search_after = normalize_perplexity_date(state.get("deep_research_search_after_date"))
    deep_search_before = normalize_perplexity_date(state.get("deep_research_search_before_date"))
    deep_updated_after = normalize_perplexity_date(state.get("deep_research_last_updated_after"))
    deep_updated_before = normalize_perplexity_date(state.get("deep_research_last_updated_before"))
    deep_country = (state.get("deep_research_country") or "").strip() or None
    deep_latitude = normalize_float(state.get("deep_research_latitude"))
    deep_longitude = normalize_float(state.get("deep_research_longitude"))
    deep_config = {"provider": deep_provider}
    if deep_model:
        deep_config["model"] = deep_model
    deep_effort = state.get("deep_research_effort")
    if deep_effort:
        deep_config["effort"] = deep_effort
    deep_multiplier = state.get("deep_research_points_multiplier")
    if deep_multiplier is not None:
        deep_config["points_multiplier"] = deep_multiplier
    if deep_search_focus:
        deep_config["search_focus"] = deep_search_focus
    if deep_domain_filter:
        deep_config["search_domain_filter"] = deep_domain_filter
    if deep_search_after:
        deep_config["search_after_date"] = deep_search_after
    if deep_search_before:
        deep_config["search_before_date"] = deep_search_before
    if deep_updated_after:
        deep_config["last_updated_after"] = deep_updated_after
    if deep_updated_before:
        deep_config["last_updated_before"] = deep_updated_before
    if deep_country:
        deep_config["search_country"] = deep_country
    if deep_latitude is not None:
        deep_config["search_latitude"] = deep_latitude
    if deep_longitude is not None:
        deep_config["search_longitude"] = deep_longitude

    with billing_context(node="deep_research_node", effort=deep_effort, points_multiplier=deep_multiplier):
        try:
            async for event in deep_research_service.stream_research_task(query, config=deep_config):
                etype = event.get("type")
                if etype == "cache_hit":
                    from_cache = True
                    streamed_any = True
                    _emit_event(
                        state,
                        "cache_hit",
                        {"from_cache": True},
                        phase="research",
                        node="deep_research",
                    )
                elif etype == "thinking":
                    text = _sanitize_thinking_text(event.get("text") or "")
                    if text:
                        streamed_any = True
                        thinking_steps.append({"text": text, "timestamp": time.time()})
                        _emit_event(
                            state,
                            "deepresearch_step",
                            {"step": text, "from_cache": bool(event.get("from_cache", False))},
                            phase="research",
                            node="deep_research",
                        )
                elif etype == "content":
                    final_report += event.get("text") or ""
                elif etype == "done":
                    sources = event.get("sources") or []
                    streamed_any = True
                    _emit_event(
                        state,
                        "research_done",
                        {
                            "researchmode": "deep",
                            "sources_count": len(sources),
                            "from_cache": from_cache,
                        },
                        phase="research",
                        node="deep_research",
                    )
                elif etype == "error":
                    streamed_any = True
                    _emit_event(
                        state,
                        "research_error",
                        {"message": str(event.get("message") or "Erro no Deep Research")},
                        phase="research",
                        node="deep_research",
                    )
        except Exception as exc:
            _emit_event(
                state,
                "research_error",
                {"message": str(exc)},
                phase="research",
                node="deep_research",
            )

        if not final_report:
            res = await deep_research_service.run_research_task(query, config=deep_config)
            final_report = res.text
            sources = res.sources or []
            from_cache = bool(getattr(res, "from_cache", False))
            thinking_steps = _sanitize_thinking_steps(res.thinking_steps or [])

    return {
        **state,
        "research_context": final_report,
        "research_sources": sources,
        "deep_research_thinking_steps": thinking_steps,
        "deep_research_from_cache": from_cache,
        "deep_research_streamed": streamed_any,
        "last_research_step": "deep_research",
        "web_search_insufficient": False,
    }


async def web_search_node(state: DocumentState) -> DocumentState:
    """Simple web search"""
    state = _apply_budget_soft_caps(state, node="web_search")
    if not state.get("web_search_enabled"):
        return state

    search_mode = (state.get("search_mode") or "hybrid").lower()
    if search_mode not in ("shared", "native", "hybrid", "perplexity"):
        search_mode = "hybrid"
    perplexity_search_mode = normalize_perplexity_search_mode(state.get("perplexity_search_mode"))
    search_domain_filter = parse_csv_list(state.get("perplexity_search_domain_filter"), max_items=20)
    search_language_filter = parse_csv_list(state.get("perplexity_search_language_filter"), max_items=10)
    search_recency_filter = normalize_perplexity_recency(state.get("perplexity_search_recency_filter"))
    search_after_date = normalize_perplexity_date(state.get("perplexity_search_after_date"))
    search_before_date = normalize_perplexity_date(state.get("perplexity_search_before_date"))
    last_updated_after = normalize_perplexity_date(state.get("perplexity_last_updated_after"))
    last_updated_before = normalize_perplexity_date(state.get("perplexity_last_updated_before"))
    try:
        search_max_results = int(state.get("perplexity_search_max_results"))
    except (TypeError, ValueError):
        search_max_results = None
    if search_max_results is not None and search_max_results <= 0:
        search_max_results = None
    if search_max_results is not None and search_max_results > 20:
        search_max_results = 20
    try:
        search_max_tokens = int(state.get("perplexity_search_max_tokens"))
    except (TypeError, ValueError):
        search_max_tokens = None
    if search_max_tokens is not None and search_max_tokens <= 0:
        search_max_tokens = None
    if search_max_tokens is not None and search_max_tokens > 1_000_000:
        search_max_tokens = 1_000_000
    try:
        search_max_tokens_per_page = int(state.get("perplexity_search_max_tokens_per_page"))
    except (TypeError, ValueError):
        search_max_tokens_per_page = None
    if search_max_tokens_per_page is not None and search_max_tokens_per_page <= 0:
        search_max_tokens_per_page = None
    if search_max_tokens_per_page is not None and search_max_tokens_per_page > 1_000_000:
        search_max_tokens_per_page = 1_000_000
    search_country = (state.get("perplexity_search_country") or "").strip() or None
    search_region = (state.get("perplexity_search_region") or "").strip() or None
    search_city = (state.get("perplexity_search_city") or "").strip() or None
    search_latitude = normalize_float(state.get("perplexity_search_latitude"))
    search_longitude = normalize_float(state.get("perplexity_search_longitude"))
    return_images = bool(state.get("perplexity_return_images"))
    return_videos = bool(state.get("perplexity_return_videos"))

    logger.info("🌐 [Phase2] Web Search...")

    def _citations_list_to_map(items: List[Dict[str, Any]]) -> Dict[str, Any]:
        citations: Dict[str, Any] = {}
        for idx, item in enumerate(items or [], start=1):
            if idx > 20:
                break
            number = item.get("number") if isinstance(item, dict) else None
            number = number if number is not None else idx
            key = str(number)
            if not key or key in citations:
                continue
            title = (item or {}).get("title") if isinstance(item, dict) else None
            url = (item or {}).get("url") if isinstance(item, dict) else None
            quote = (item or {}).get("quote") if isinstance(item, dict) else None
            snippet = (item or {}).get("snippet") if isinstance(item, dict) else None
            citations[key] = {
                "title": title or "Fonte",
                "url": url or "",
                "snippet": quote or snippet or "",
            }
        return citations

    def _results_to_citations_map(results: List[Dict[str, Any]], limit: int = 20) -> Dict[str, Any]:
        citations: Dict[str, Any] = {}
        for idx, item in enumerate(results[:limit], start=1):
            if not isinstance(item, dict):
                continue
            snippet = item.get("snippet") or item.get("content") or ""
            snippet = str(snippet) if snippet is not None else ""
            if len(snippet) > 1200:
                snippet = snippet[:1200]
            citations[str(idx)] = {
                "title": item.get("title") or "Fonte",
                "url": item.get("url") or "",
                "snippet": snippet,
                "query": item.get("query"),
                "source": item.get("source"),
            }
        return citations

    def _dedupe_results(results: List[Dict[str, Any]], limit: int = 20) -> List[Dict[str, Any]]:
        deduped: List[Dict[str, Any]] = []
        seen = set()
        for item in results or []:
            if not isinstance(item, dict):
                continue
            url = (item.get("url") or "").strip()
            if not url or url in seen:
                continue
            seen.add(url)
            deduped.append(item)
            if len(deduped) >= limit:
                break
        return deduped

    base_query = f"{state.get('tese', '')} jurisprudência {state.get('mode', '')}".strip()
    planned_queries = _normalize_queries(state.get("planned_queries"))
    max_requests = _resolve_cap_value(state.get("max_web_search_requests"), default=None)
    if max_requests is not None and max_requests <= 0:
        logger.info("🌐 [Phase2] Web Search capped to 0 requests; skipping.")
        return state
    planned_queries = _cap_queries(planned_queries, max_requests)
    query = planned_queries[0] if planned_queries else base_query
    breadth_first = bool(state.get("breadth_first")) or is_breadth_first(query)
    multi_query = bool(state.get("multi_query", True)) or breadth_first
    max_sources = search_max_results or 20

    _emit_event(
        state,
        "research_start",
        {"researchmode": "web", "plannedqueries": planned_queries},
        phase="research",
        node="web_search",
    )

    if search_mode == "native":
        try:
            from app.services.ai.agent_clients import (
                build_system_instruction,
                get_gpt_client,
                get_claude_client,
                get_gemini_client,
                _is_anthropic_vertex_client,
                call_openai_async,
                call_anthropic_async,
                call_vertex_gemini_async
            )
            from app.services.ai.model_registry import get_api_model_name, get_model_config

            preferred = str(state.get("web_search_model") or "").strip()
            if preferred.lower() == "auto":
                preferred = ""
            if preferred:
                preferred_cfg = get_model_config(preferred)
                if preferred_cfg and "deep_research" in (preferred_cfg.capabilities or []):
                    logger.warning(
                        f"⚠️ web_search_model='{preferred}' é Deep Research; ignorando e usando fallback."
                    )
                    preferred = ""
            judge_model = preferred or state.get("judge_model") or DEFAULT_JUDGE_MODEL
            api_model = get_api_model_name(judge_model) or judge_model
            cfg = get_model_config(judge_model)
            provider = cfg.provider if cfg else ""
            system_instruction = build_system_instruction(state.get("chat_personality"))
            prompt_query = "; ".join(planned_queries[:4]) if planned_queries else query
            prompt = f"Pesquise na web e resuma as fontes relevantes sobre: {prompt_query}. Cite as fontes."

            if provider == "openai":
                gpt_client = get_gpt_client()
                if gpt_client and hasattr(gpt_client, "responses"):
                    try:
                        resp = gpt_client.responses.create(
                            model=api_model,
                            input=[
                                {"role": "system", "content": system_instruction},
                                {"role": "user", "content": prompt},
                            ],
                            tools=[{"type": "web_search"}],
                            max_output_tokens=1200,
                            temperature=0.3,
                        )
                        record_api_call(
                            kind="llm",
                            provider="openai",
                            model=api_model,
                            success=True,
                            meta={"tool": "web_search"},
                        )
                    except Exception:
                        record_api_call(
                            kind="llm",
                            provider="openai",
                            model=api_model,
                            success=False,
                            meta={"tool": "web_search"},
                        )
                        raise
                    text, sources = extract_perplexity("openai", resp)
                    citations_map = _citations_list_to_map(sources_to_citations(sources))
                    if text:
                        _emit_event(
                            state,
                            "research_done",
                            {"researchmode": "web", "sources_count": len(sources)},
                            phase="research",
                            node="web_search",
                        )
                        return {
                            **state,
                            "research_context": text,
                            "research_sources": [],
                            "citations_map": citations_map,
                            "last_research_step": "web_search",
                        }

            if provider == "anthropic":
                claude_client = get_claude_client()
                if claude_client:
                    kwargs: Dict[str, Any] = {
                        "model": api_model,
                        "max_tokens": 1200,
                        "messages": [{"role": "user", "content": prompt}],
                        "system": system_instruction,
                        "tools": [{"type": "web_search_20250305", "name": "web_search"}],
                    }
                    beta_header = os.getenv("ANTHROPIC_WEB_SEARCH_BETA", "web-search-2025-03-05").strip()
                    if beta_header:
                        kwargs["extra_headers"] = {"anthropic-beta": beta_header}
                    provider_name = "anthropic"
                    if _is_anthropic_vertex_client(claude_client):
                        kwargs["anthropic_version"] = os.getenv("ANTHROPIC_VERTEX_VERSION", "vertex-2023-10-16")
                        provider_name = "vertex-anthropic"
                    try:
                        resp = claude_client.messages.create(**kwargs)
                        record_api_call(
                            kind="llm",
                            provider=provider_name,
                            model=api_model,
                            success=True,
                            meta={"tool": "web_search"},
                        )
                    except Exception:
                        record_api_call(
                            kind="llm",
                            provider=provider_name,
                            model=api_model,
                            success=False,
                            meta={"tool": "web_search"},
                        )
                        raise
                    text, sources = extract_perplexity("claude", resp)
                    citations_map = _citations_list_to_map(sources_to_citations(sources))
                    if text:
                        _emit_event(
                            state,
                            "research_done",
                            {"researchmode": "web", "sources_count": len(sources)},
                            phase="research",
                            node="web_search",
                        )
                        return {
                            **state,
                            "research_context": text,
                            "research_sources": [],
                            "citations_map": citations_map,
                            "last_research_step": "web_search",
                        }

            if provider == "google":
                gemini_client = get_gemini_client()
                if gemini_client:
                    from google.genai import types as genai_types

                    tool = genai_types.Tool(google_search=genai_types.GoogleSearch())
                    config = genai_types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        tools=[tool],
                        max_output_tokens=1200,
                        temperature=0.3,
                    )
                    try:
                        resp = gemini_client.models.generate_content(
                            model=api_model,
                            contents=prompt,
                            config=config,
                        )
                        record_api_call(
                            kind="llm",
                            provider="vertex-gemini",
                            model=api_model,
                            success=True,
                            meta={"tool": "web_search"},
                        )
                    except Exception:
                        record_api_call(
                            kind="llm",
                            provider="vertex-gemini",
                            model=api_model,
                            success=False,
                            meta={"tool": "web_search"},
                        )
                        raise
                    text, sources = extract_perplexity("gemini", resp)
                    if not text:
                        text = (resp.text or "").strip()
                    citations_map = _citations_list_to_map(sources_to_citations(sources))
                    if text:
                        _emit_event(
                            state,
                            "research_done",
                            {"researchmode": "web", "sources_count": len(sources)},
                            phase="research",
                            node="web_search",
                        )
                        return {
                            **state,
                            "research_context": text,
                            "research_sources": [],
                            "citations_map": citations_map,
                            "last_research_step": "web_search",
                        }

            if provider == "perplexity":
                perplexity_key = os.getenv("PERPLEXITY_API_KEY")
                if perplexity_key:
                    try:
                        from perplexity import AsyncPerplexity
                    except Exception as exc:
                        logger.error(f"Perplexity SDK import failed: {exc}")
                    else:
                        import inspect

                        def _to_result(item: Any) -> Dict[str, Any]:
                            if isinstance(item, dict):
                                return {
                                    "title": item.get("title") or item.get("name") or "",
                                    "url": item.get("url") or item.get("uri") or "",
                                    "snippet": item.get("snippet") or item.get("content") or "",
                                    "source": "perplexity",
                                }
                            return {
                                "title": getattr(item, "title", "") or getattr(item, "name", "") or "",
                                "url": getattr(item, "url", "") or getattr(item, "uri", "") or "",
                                "snippet": getattr(item, "snippet", "") or getattr(item, "content", "") or "",
                                "source": "perplexity",
                            }

                        client = AsyncPerplexity(api_key=perplexity_key)
                        messages = [
                            {"role": "system", "content": system_instruction},
                            {"role": "user", "content": prompt},
                        ]
                        pplx_meta = {
                            "size": "M",
                            "stream": False,
                            "search_type": state.get("perplexity_search_type"),
                            "search_context_size": state.get("perplexity_search_context_size"),
                            "disable_search": bool(state.get("perplexity_disable_search")),
                            "search_mode": perplexity_search_mode,
                            "search_domain_filter": search_domain_filter,
                            "search_language_filter": search_language_filter,
                            "search_recency_filter": search_recency_filter,
                            "search_after_date": search_after_date,
                            "search_before_date": search_before_date,
                            "last_updated_after": last_updated_after,
                            "last_updated_before": last_updated_before,
                            "search_country": search_country,
                            "search_region": search_region,
                            "search_city": search_city,
                            "search_latitude": search_latitude,
                            "search_longitude": search_longitude,
                            "return_images": return_images,
                            "return_videos": return_videos,
                        }
                        pplx_kwargs = build_perplexity_chat_kwargs(
                            api_model=api_model,
                            web_search_enabled=True,
                            search_mode=perplexity_search_mode,
                            search_type=state.get("perplexity_search_type"),
                            search_context_size=state.get("perplexity_search_context_size"),
                            search_domain_filter=search_domain_filter,
                            search_language_filter=search_language_filter,
                            search_recency_filter=search_recency_filter,
                            search_after_date=search_after_date,
                            search_before_date=search_before_date,
                            last_updated_after=last_updated_after,
                            last_updated_before=last_updated_before,
                            search_country=search_country,
                            search_region=search_region,
                            search_city=search_city,
                            search_latitude=search_latitude,
                            search_longitude=search_longitude,
                            return_images=return_images,
                            return_videos=return_videos,
                            enable_search_classifier=bool(state.get("perplexity_search_classifier")),
                            disable_search=bool(state.get("perplexity_disable_search")),
                            stream_mode=None,
                        )
                        try:
                            resp_obj = client.chat.completions.create(
                                model=api_model,
                                messages=messages,
                                temperature=0.3,
                                max_tokens=1200,
                                **pplx_kwargs,
                            )
                            if inspect.isawaitable(resp_obj):
                                resp_obj = await resp_obj
                            record_api_call(
                                kind="llm",
                                provider="perplexity",
                                model=api_model,
                                success=True,
                                meta=pplx_meta,
                            )
                        except Exception:
                            record_api_call(
                                kind="llm",
                                provider="perplexity",
                                model=api_model,
                                success=False,
                                meta=pplx_meta,
                            )
                            raise

                        choices = getattr(resp_obj, "choices", None) or []
                        msg = getattr(choices[0], "message", None) if choices else None
                        text = getattr(msg, "content", "") if msg else ""

                        search_results = (
                            getattr(resp_obj, "search_results", None)
                            or getattr(resp_obj, "searchResults", None)
                            or []
                        )
                        results = []
                        if isinstance(search_results, list):
                            results = [_to_result(item) for item in search_results]

                        citations_map = {}
                        if results:
                            citations_map = _results_to_citations_map(results, limit=max_sources)
                        else:
                            citations = getattr(resp_obj, "citations", None) or []
                            if isinstance(citations, list) and citations:
                                citation_items = []
                                for item in citations:
                                    if isinstance(item, dict):
                                        citation_items.append(item)
                                    else:
                                        citation_items.append({"url": str(item), "title": str(item)})
                                citations_map = _citations_list_to_map(citation_items)

                        if text:
                            _emit_event(
                                state,
                                "research_done",
                                {"researchmode": "web", "sources_count": len(citations_map)},
                                phase="research",
                                node="web_search",
                            )
                            return {
                                **state,
                                "research_context": text,
                                "research_sources": [],
                                "citations_map": citations_map,
                                "last_research_step": "web_search",
                            }
        except Exception as e:
            logger.error(f"❌ [Phase2] Web Search nativo falhou: {e}")

    if planned_queries:
        logger.info(f"🌐 [Phase2] Using {len(planned_queries)} planned queries")
        planned_slice = planned_queries
        per_query = max(2, int((max_sources + len(planned_slice) - 1) / max(1, len(planned_slice))))
        tasks = [
            web_search_service.search(
                q,
                num_results=per_query,
                search_mode=perplexity_search_mode,
                country=search_country,
                domain_filter=search_domain_filter,
                language_filter=search_language_filter,
                recency_filter=search_recency_filter,
                search_after_date=search_after_date,
                search_before_date=search_before_date,
                last_updated_after=last_updated_after,
                last_updated_before=last_updated_before,
                max_tokens=search_max_tokens,
                max_tokens_per_page=search_max_tokens_per_page,
                return_images=return_images,
                return_videos=return_videos,
            )
            for q in planned_slice
        ]
        results_list = await asyncio.gather(*tasks, return_exceptions=True)
        results = []
        for payload in results_list:
            if isinstance(payload, Exception):
                logger.error(f"Erro search planejada: {payload}")
                continue
            for item in payload.get("results", []) or []:
                results.append({**item, "query": payload.get("query")})
        deduped = []
        seen = set()
        for item in results:
            url = (item.get("url") or "").strip()
            if not url or url in seen:
                continue
            seen.add(url)
            deduped.append(item)
        payload = {
            "results": deduped[:max_sources],
            "queries": planned_slice,
            "query": query,
            "source": "multi-planned",
        }
    elif multi_query:
        if max_requests is not None:
            payload = await web_search_service.search_multi(
                query,
                num_results=max_sources,
                max_queries=max_requests,
                search_mode=perplexity_search_mode,
                country=search_country,
                domain_filter=search_domain_filter,
                language_filter=search_language_filter,
                recency_filter=search_recency_filter,
                search_after_date=search_after_date,
                search_before_date=search_before_date,
                last_updated_after=last_updated_after,
                last_updated_before=last_updated_before,
                max_tokens=search_max_tokens,
                max_tokens_per_page=search_max_tokens_per_page,
                return_images=return_images,
                return_videos=return_videos,
            )
        else:
            payload = await web_search_service.search_multi(
                query,
                num_results=max_sources,
                search_mode=perplexity_search_mode,
                country=search_country,
                domain_filter=search_domain_filter,
                language_filter=search_language_filter,
                recency_filter=search_recency_filter,
                search_after_date=search_after_date,
                search_before_date=search_before_date,
                last_updated_after=last_updated_after,
                last_updated_before=last_updated_before,
                max_tokens=search_max_tokens,
                max_tokens_per_page=search_max_tokens_per_page,
                return_images=return_images,
                return_videos=return_videos,
            )
    else:
        payload = await web_search_service.search(
            query,
            num_results=max_sources,
            search_mode=perplexity_search_mode,
            country=search_country,
            domain_filter=search_domain_filter,
            language_filter=search_language_filter,
            recency_filter=search_recency_filter,
            search_after_date=search_after_date,
            search_before_date=search_before_date,
            last_updated_after=last_updated_after,
            last_updated_before=last_updated_before,
            max_tokens=search_max_tokens,
            max_tokens_per_page=search_max_tokens_per_page,
            return_images=return_images,
            return_videos=return_videos,
        )

    results = _dedupe_results(payload.get("results") or [], limit=max_sources)
    payload = {**(payload or {}), "results": results}
    citations_map = _results_to_citations_map(results, limit=max_sources)
    web_context = build_web_context(payload, max_items=max_sources)
    url_to_number = {
        (item.get("url") or "").strip(): idx
        for idx, item in enumerate(results, start=1)
        if isinstance(item, dict) and (item.get("url") or "").strip()
    }
    try:
        web_rag_context, _ = await web_rag_service.build_web_rag_context(
            query,
            results,
            max_docs=3,
            max_chunks=6,
            max_chars=6000,
            url_to_number=url_to_number,
        )
    except TypeError:
        web_rag_context, _ = await web_rag_service.build_web_rag_context(
            query,
            results,
            max_docs=3,
            max_chunks=6,
            max_chars=6000,
        )
    merged_context = _merge_context_blocks([web_rag_context, web_context], max_chars=8000) or web_rag_context or web_context

    _emit_event(
        state,
        "research_done",
        {"researchmode": "web", "sources_count": len(results)},
        phase="research",
        node="web_search",
    )
    return {
        **state,
        "research_context": f"{merged_context}\n",
        "research_sources": results,
        "citations_map": citations_map,
        "last_research_step": "web_search",
    }


async def research_notes_node(state: DocumentState) -> DocumentState:
    """
    Summarize research sources into concise notes and build a citations map.
    """
    research_context = (state.get("research_context") or "").strip()
    sources = state.get("research_sources") or []
    existing_citations = state.get("citations_map") or {}
    web_search_insufficient = False
    if (
        state.get("last_research_step") == "web_search"
        and state.get("web_search_enabled")
        and state.get("deep_research_enabled")
    ):
        min_sources = 2
        min_chars = 400
        if len(sources) < min_sources and len(research_context) < min_chars:
            web_search_insufficient = True
            logger.info("⚠️ Web search insuficiente; habilitando deep research no retry.")

    if not research_context and not sources and not existing_citations:
        return {
            **state,
            "research_notes": None,
            "citations_map": {},
            "verification_retry": False,
            "web_search_insufficient": web_search_insufficient,
        }

    citations_map: Dict[str, Any] = {}
    if isinstance(existing_citations, dict):
        citations_map = {str(k): v for k, v in existing_citations.items() if k is not None}
    lines = ["## NOTAS DE PESQUISA (use citações [n])"]

    if citations_map:
        def _sort_key(item: str):
            return int(item) if str(item).isdigit() else item

        for key in sorted(citations_map.keys(), key=_sort_key)[:20]:
            item = citations_map.get(key) or {}
            title = item.get("title") or "Fonte"
            url = item.get("url") or ""
            snippet = item.get("snippet") or item.get("quote") or ""
            entry = f"[{key}] {title}"
            if url:
                entry += f" — {url}"
            lines.append(entry.strip())
            if snippet:
                lines.append(str(snippet).strip())
    elif sources:
        for idx, src in enumerate(sources[:20], start=1):
            title = src.get("title") or "Fonte"
            url = src.get("url") or ""
            snippet = src.get("snippet") or src.get("text") or ""
            citations_map[str(idx)] = {
                "title": title,
                "url": url,
                "snippet": snippet,
                "query": src.get("query"),
                "source": src.get("source"),
            }
            entry = f"[{idx}] {title}"
            if url:
                entry += f" — {url}"
            lines.append(entry.strip())
            if snippet:
                lines.append(snippet.strip())
    elif research_context:
        lines.append(research_context[:4000])

    notes_text = "\n".join(lines).strip()
    combined_context = notes_text
    if research_context and (sources or citations_map):
        combined_context = f"{notes_text}\n\n## CONTEXTO ORIGINAL\n{research_context[:4000]}"

    return {
        **state,
        "research_notes": notes_text,
        "citations_map": citations_map,
        "research_context": combined_context or research_context,
        "verification_retry": False,
        "web_search_insufficient": web_search_insufficient,
    }


async def research_verify_node(state: DocumentState) -> DocumentState:
    """
    Verify whether citations are present when jurisprudence is required.
    """
    if not state.get("need_juris"):
        return {**state, "verification_retry": False, "verification_retry_reason": None}

    if not (state.get("deep_research_enabled") or state.get("web_search_enabled")):
        return {**state, "verification_retry": False, "verification_retry_reason": None}

    attempts = int(state.get("verifier_attempts", 0) or 0)
    max_attempts = int(state.get("max_research_verifier_attempts", 1) or 1)
    if attempts >= max_attempts:
        return {**state, "verification_retry": False, "verification_retry_reason": None}

    full_document = resolve_full_document(state)
    if not full_document:
        return {**state, "verification_retry": False, "verification_retry_reason": None}

    citation_report = validate_citations(full_document, state.get("citations_map"))
    used_keys = citation_report.get("used_keys", [])
    missing_keys = citation_report.get("missing_keys", [])
    orphan_keys = citation_report.get("orphan_keys", [])
    has_citations = bool(used_keys)
    if missing_keys:
        return {
            **state,
            "verification_retry": False,
            "verification_retry_reason": "citation_keys_missing",
            "citation_validation_report": citation_report,
            "citation_used_keys": used_keys,
            "citation_missing_keys": missing_keys,
            "citation_orphan_keys": orphan_keys,
            "quality_gate_force_hil": True,
        }
    if has_citations:
        return {
            **state,
            "verification_retry": False,
            "verification_retry_reason": None,
            "citation_validation_report": citation_report,
            "citation_used_keys": used_keys,
            "citation_missing_keys": missing_keys,
            "citation_orphan_keys": orphan_keys,
        }

    retry_reason = "missing_citations_for_jurisprudence"
    planned_queries = _normalize_queries(state.get("planned_queries"))
    seed = f"{state.get('tese', '')} {state.get('mode', '')}".strip()
    focus_query = f"{seed} jurisprudência com citações"
    max_query_cap = _resolve_cap_value(state.get("max_web_search_requests"), default=4)
    if not planned_queries:
        planned_queries = plan_queries(focus_query.strip(), max_queries=max_query_cap or 4)
    else:
        planned_queries = _normalize_queries(planned_queries + [focus_query])
    planned_queries = _cap_queries(planned_queries, max_query_cap)

    next_attempt = attempts + 1
    logger.info(
        f"🔄 [Research Retry] Acionando tentativa {next_attempt}/{max_attempts} | "
        f"Razão: {retry_reason} | Queries: {len(planned_queries)} novas"
    )

    return {
        **state,
        "verification_retry": True,
        "verifier_attempts": next_attempt,
        "planned_queries": planned_queries,
        "verification_retry_reason": retry_reason,
        "research_retry_progress": f"{next_attempt}/{max_attempts}",
    }


async def fact_check_sei_node(state: DocumentState) -> DocumentState:
    """
    🔍 Fact-check SEI (RAG local como fonte de verdade)
    """
    logger.info("🔍 [Phase2] Fact-check SEI (RAG local)...")

    def _normalize_key(text: str) -> str:
        return re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_")

    def _normalize_hint_items(hints: Any) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        if not hints:
            return normalized
        for raw in hints:
            if isinstance(raw, str):
                label = raw.strip()
                if not label:
                    continue
                normalized.append({
                    "id": _normalize_key(label) or f"hint_{len(normalized)+1}",
                    "label": label,
                    "critical": False,
                })
                continue
            if not isinstance(raw, dict):
                continue
            label = str(raw.get("label") or raw.get("name") or "").strip()
            if not label:
                continue
            raw_id = str(raw.get("id") or "").strip()
            item_id = _normalize_key(raw_id or label) or f"hint_{len(normalized)+1}"
            normalized.append({
                "id": item_id,
                "label": label,
                "critical": bool(raw.get("critical", False)),
            })
        return normalized

    hint_items = _normalize_hint_items(state.get("document_checklist_hint") or [])

    sei_context = (state.get("sei_context") or "").strip()
    if not sei_context:
        hint_output = []
        for hint in hint_items:
            hint_output.append({
                "id": hint["id"],
                "label": hint["label"],
                "status": "uncertain",
                "critical": bool(hint.get("critical", False)),
                "evidence": "",
                "notes": "Checklist complementar (usuario)."
            })
        missing_critical = [i for i in hint_output if i["status"] != "present" and i.get("critical")]
        missing_noncritical = [i for i in hint_output if i["status"] != "present" and not i.get("critical")]
        summary = "Sem contexto SEI disponível para validação factual."
        if hint_output:
            summary += f" {len(missing_critical)} crítico(s) e {len(missing_noncritical)} não crítico(s) pendentes."
        return {
            **state,
            "fact_check_summary": summary,
            "document_checklist": {
                "items": hint_output,
                "missing_critical": missing_critical,
                "missing_noncritical": missing_noncritical,
                "summary": summary,
                "confirmados": [],
                "nao_verificaveis": [],
                "inconsistencias": [],
            },
            "json_parse_failures": parse_failures,
        }

    gpt_model = state.get("gpt_model") or "gpt-5.2"

    hint_block = "\n".join(
        f"- {item['label']} ({'critico' if item.get('critical') else 'nao_critico'})"
        for item in hint_items
    ) or "Nenhum checklist complementar informado."

    # v5.7: Improved prompt structure
    try:
        from app.services.ai.prompt_constants import (
            ROLE_AUDITOR, EVIDENCE_POLICY_AUDIT, OUTPUT_FORMAT_AUDIT, CHECKLIST_EXAMPLE
        )
    except ImportError:
        ROLE_AUDITOR = "Você é um auditor jurídico rigoroso."
        EVIDENCE_POLICY_AUDIT = "Use apenas provas do SEI."
        OUTPUT_FORMAT_AUDIT = "Retorne JSON válido."
        CHECKLIST_EXAMPLE = ""

    prompt = f"""
# ROLE
{ROLE_AUDITOR}

# TASK
Valide fatos e documentos EXCLUSIVAMENTE com base no SEI abaixo.
1. Liste fatos confirmados
2. Liste pontos sem prova ("missing" ou "uncertain")
3. Gere CHECKLIST com criticidade

# CONTEXT
## Checklist Complementar (Usuário)
{hint_block}

## SEI (Trecho Documental)
{sei_context[:300000]}

# RULES
{EVIDENCE_POLICY_AUDIT}
1. Se faltar prova, marque "status": "missing"
2. Marque "critical": true se a ausência impede a conclusão
3. Inclua itens do checklist complementar na análise

# OUTPUT FORMAT
{OUTPUT_FORMAT_AUDIT}

{CHECKLIST_EXAMPLE}
""".strip()

    response_text = ""
    parse_failures = list(state.get("json_parse_failures") or [])
    model_used = None
    gpt_client = None
    try:
        from app.services.ai.agent_clients import init_openai_client, call_openai_async
        gpt_client = init_openai_client()
        if gpt_client:
            with billing_context(node="fact_check_sei_node", size="M"):
                response_text = await call_openai_async(
                    gpt_client,
                    prompt,
                    model=get_api_model_name(gpt_model),
                    timeout=90
                )
            model_used = get_api_model_name(gpt_model)
    except Exception as e:
        logger.warning(f"⚠️ Fact-check GPT falhou: {e}")

    if not response_text:
        try:
            from app.services.ai.gemini_drafter import GeminiDrafterWrapper
            drafter = GeminiDrafterWrapper()
            with billing_context(node="fact_check_sei_node", size="M"):
                resp = await asyncio.to_thread(drafter._generate_with_retry, prompt)
            response_text = resp.text if resp else ""
            model_used = "gemini"
        except Exception as e:
            logger.warning(f"⚠️ Fact-check Gemini falhou: {e}")

    parsed = extract_json_strict(response_text, expect="object") or {}
    if not parsed and response_text:
        parse_failures.append({
            "node": "fact_check_sei",
            "model": model_used,
            "reason": "parse_failed",
            "sample": response_text[:800],
        })
        retry_prompt = f"{prompt}\n\nRESPONDA APENAS COM JSON VÁLIDO. NÃO INCLUA TEXTO EXTRA."
        try:
            if gpt_client:
                with billing_context(node="fact_check_sei_node_retry", size="M"):
                    response_text = await call_openai_async(
                        gpt_client,
                        retry_prompt,
                        model=get_api_model_name(gpt_model),
                        timeout=90
                    )
                    model_used = get_api_model_name(gpt_model)
            else:
                from app.services.ai.gemini_drafter import GeminiDrafterWrapper
                drafter = GeminiDrafterWrapper()
                with billing_context(node="fact_check_sei_node_retry", size="M"):
                    resp = await asyncio.to_thread(drafter._generate_with_retry, retry_prompt)
                response_text = resp.text if resp else ""
                model_used = "gemini"
        except Exception as e:
            logger.warning(f"⚠️ Fact-check retry falhou: {e}")
        parsed = extract_json_strict(response_text, expect="object") or {}
        if not parsed and response_text:
            parse_failures.append({
                "node": "fact_check_sei",
                "model": model_used,
                "reason": "parse_failed_retry",
                "sample": response_text[:800],
            })
    items = []
    for item in parsed.get("checklist", []) or []:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "").lower()
        if status not in ("present", "missing", "uncertain"):
            status = "uncertain"
        items.append({
            "id": str(item.get("id") or "").strip() or f"doc_{len(items)+1}",
            "label": str(item.get("label") or "Documento").strip(),
            "status": status,
            "critical": bool(item.get("critical", False)),
            "evidence": str(item.get("evidence") or "").strip(),
            "notes": str(item.get("notes") or "").strip()
        })

    if hint_items:
        existing_by_key = {}
        for existing in items:
            key = _normalize_key(existing.get("id") or existing.get("label") or "")
            if not key:
                continue
            existing_by_key[key] = existing
        for hint in hint_items:
            hint_key = _normalize_key(hint.get("id") or hint.get("label") or "")
            if hint_key in existing_by_key:
                if hint.get("critical") and not existing_by_key[hint_key].get("critical"):
                    existing_by_key[hint_key]["critical"] = True
                continue
            items.append({
                "id": hint.get("id") or f"doc_{len(items)+1}",
                "label": hint.get("label") or "Documento",
                "status": "uncertain",
                "critical": bool(hint.get("critical", False)),
                "evidence": "",
                "notes": "Checklist complementar (usuario)."
            })

    missing_critical = [i for i in items if i["status"] != "present" and i.get("critical")]
    missing_noncritical = [i for i in items if i["status"] != "present" and not i.get("critical")]

    summary = parsed.get("summary") or f"{len(missing_critical)} crítico(s) e {len(missing_noncritical)} não crítico(s) pendentes."

    return {
        **state,
        "fact_check_summary": summary,
        "document_checklist": {
            "items": items,
            "missing_critical": missing_critical,
            "missing_noncritical": missing_noncritical,
            "summary": summary,
            "confirmados": parsed.get("confirmados", []),
            "nao_verificaveis": parsed.get("nao_verificaveis", []),
            "inconsistencias": parsed.get("inconsistencias", []),
        },
        "json_parse_failures": parse_failures,
    }


async def planner_node(state: DocumentState) -> DocumentState:
    """
    🧠 Planner Node (Auto-Decision)
    
    Decides research strategy (Deep Search vs Web Search vs None) based on:
    - Complexity of the thesis/facts
    - Completeness of the outline
    - User intent
    """
    state = _apply_budget_soft_caps(state, node="planner")
    logger.info("🧠 [Phase2] Planner: Analyzing research strategy...")
    parse_failures = list(state.get("json_parse_failures") or [])
    
    # If user explicitly forced a mode via UI flags that we want to respect strictly,
    # we could skip this. But here we want the Planner to be authoritative or at least augment.
    # Let's check if we should skip if user ALREADY enabled deep_research manually?
    # For now, we will RE-EVALUATE. If the user turned it on, the planner likely agrees. 
    # If the user turned it off, the planner might turn it ON if needed.
    
    input_text = state.get("input_text", "")
    outline = state.get("outline", [])
    length_guidance = build_length_guidance(state, len(outline))
    thesis = state.get("tese", "")
    mode = state.get("mode", "PETICAO")
    ui_deep = bool(state.get("deep_research_enabled"))
    ui_web = bool(state.get("web_search_enabled"))
    combined_text = f"{thesis}\n{input_text}"
    
    prompt = f"""
# ROLE
Você é o estrategista sênior do escritório, responsável por decidir a estratégia de pesquisa.

# TASK
Decida qual tipo de pesquisa é necessário para este caso.

# CONTEXT
## Tipo de Documento: {mode}
## Tese: {thesis}
## Fatos (resumo): {input_text[:1000]}...

## Estrutura Proposta
{chr(10).join(f"- {s}" for s in outline)}

# RULES
Critérios de decisão:
- **Deep Research**: Teses complexas, divergência jurisprudencial, temas inéditos, precedentes específicos difíceis
- **Web Search**: Dúvidas pontuais, verificar lei atualizada, buscar fatos recentes
- **Nenhuma**: Matéria puramente de fato ou questão jurídica pacificada

# OUTPUT FORMAT
Responda APENAS em JSON válido:
```json
{{
    "raciocinio": "Explique brevemente por que...",
    "precisa_jurisprudencia": true/false,
    "precisa_deep_research": true/false,
    "precisa_web_search": true/false,
    "queries_sugeridas": ["query 1", "query 2"]
}}
```
"""

    try:
        from app.services.ai.agent_clients import init_openai_client, call_openai_async, get_api_model_name
        
        # Use configurable planner model (defaults to gpt_model or gpt-5.2)
        planner_model = state.get("planner_model") or state.get("gpt_model") or "gpt-5.2"
        client = init_openai_client()
        if not client:
             # Fallback if no OpenAI
            return state
            
        with billing_context(node="planner_node", size="S"):
            response = await call_openai_async(
                client, 
                prompt, 
                model=get_api_model_name(planner_model),
                temperature=0.2,
                max_tokens=500
            )
        
        import json
        decision = extract_json_strict(response, expect="object") or {}
        if not decision:
            parse_failures.append({
                "node": "planner",
                "model": planner_model,
                "reason": "parse_failed",
                "sample": (response or "")[:800],
            })
            raise ValueError("Planner JSON parse failed")
            
        raciocinio = decision.get("raciocinio", "Sem raciocínio")
        needs_deep = bool(decision.get("precisa_deep_research", False))
        needs_web = bool(decision.get("precisa_web_search", False))
        needs_juris = bool(decision.get("precisa_jurisprudencia", False))

        logger.info(
            f"🧠 Planner Decision: Deep={needs_deep}, Web={needs_web}, Juris={needs_juris}. Reason: {raciocinio}"
        )

        max_query_cap = _resolve_cap_value(state.get("max_web_search_requests"), default=4)
        planned_queries = _normalize_queries(state.get("planned_queries"))
        suggested_queries = _normalize_queries(decision.get("queries_sugeridas", []))
        planned_queries = _normalize_queries(planned_queries + suggested_queries)

        policy = (state.get("research_policy") or "auto").lower()
        if policy not in ("auto", "force"):
            policy = "auto"

        if policy == "force":
            deep_enabled = ui_deep
            web_enabled = ui_web
        else:
            deep_enabled = ui_deep or needs_deep
            web_enabled = ui_web or needs_web
            if not deep_enabled and not web_enabled and needs_juris:
                web_enabled = True

        if not planned_queries and (deep_enabled or web_enabled):
            seed = f"{thesis} {mode}".strip() or input_text[:200]
            planned_queries = plan_queries(seed, max_queries=max_query_cap or 4)
        planned_queries = _cap_queries(planned_queries, max_query_cap)

        updates = {
            "planning_reasoning": raciocinio,
            "planned_queries": planned_queries,
            "deep_research_enabled": deep_enabled,
            "web_search_enabled": web_enabled,
            "need_juris": needs_juris or deep_enabled or web_enabled,
            "research_mode": "deep" if deep_enabled else "light" if web_enabled else "none",
            "json_parse_failures": parse_failures,
        }

        _emit_event(
            state,
            "planner_decision",
            {
                "deepresearchenabled": deep_enabled,
                "websearchenabled": web_enabled,
                "needjuris": needs_juris or deep_enabled or web_enabled,
                "researchmode": updates["research_mode"],
                "plannedqueries": planned_queries,
                "planningreasoning": raciocinio,
            },
            phase="research",
            node="planner",
        )

        return {**state, **updates}
        
    except Exception as e:
        logger.error(f"❌ Planner failed: {e}. Falling back to heuristic planning.")

        juris_keywords = [
            "jurisprudência", "jurisprudencia", "precedente", "stj", "stf",
            "súmula", "sumula", "acórdão", "acordao", "tema repetitivo",
            "repercussão geral", "repercussao geral", "ementa", "tese"
        ]
        deep_keywords = [
            "fundamente", "fundamentar", "cite", "citação", "citacao",
            "divergência", "divergencia", "comparar", "panorama", "mapa",
            "contexto histórico", "contexto historico", "atualizado"
        ]
        needs_juris = _contains_keywords(combined_text, juris_keywords)
        needs_deep = needs_juris and _contains_keywords(combined_text, deep_keywords)
        needs_web = needs_juris and not needs_deep

        policy = (state.get("research_policy") or "auto").lower()
        if policy not in ("auto", "force"):
            policy = "auto"

        if policy == "force":
            deep_enabled = ui_deep
            web_enabled = ui_web
        else:
            deep_enabled = ui_deep or needs_deep
            web_enabled = ui_web or needs_web
            if not deep_enabled and not web_enabled and needs_juris:
                web_enabled = True

        max_query_cap = _resolve_cap_value(state.get("max_web_search_requests"), default=4)
        planned_queries = _normalize_queries(state.get("planned_queries"))
        if not planned_queries and (deep_enabled or web_enabled):
            seed = f"{thesis} {mode}".strip() or input_text[:200]
            planned_queries = plan_queries(seed, max_queries=max_query_cap or 4)
        planned_queries = _cap_queries(planned_queries, max_query_cap)

        research_mode = "deep" if deep_enabled else "light" if web_enabled else "none"
        _emit_event(
            state,
            "planner_decision",
            {
                "deepresearchenabled": deep_enabled,
                "websearchenabled": web_enabled,
                "needjuris": needs_juris or deep_enabled or web_enabled,
                "researchmode": research_mode,
                "plannedqueries": planned_queries,
                "planningreasoning": "Heurística (fallback)",
            },
            phase="research",
            node="planner",
        )
        return {
            **state,
            "planning_reasoning": "Heurística (fallback)",
            "planned_queries": planned_queries,
            "deep_research_enabled": deep_enabled,
            "web_search_enabled": web_enabled,
            "need_juris": needs_juris or deep_enabled or web_enabled,
            "research_mode": research_mode,
            "json_parse_failures": parse_failures,
        }


async def debate_all_sections_node(state: DocumentState) -> DocumentState:
    """
    ⭐⭐⭐⭐⭐⭐ 6-Star Hybrid Node
    
    Uses proven generate_section_agent_mode_async logic with:
    - Proper LegalDrafter initialization
    - All parameters passed (thesis, reasoning_level, etc.)
    - Real-time event emission via job_manager
    - Comprehensive error handling and fallback
    """
    state = _apply_budget_soft_caps(state, node="debate")
    logger.info("⚔️ [6-Star Hybrid] Multi-Agent Committee Starting...")
    
    # Lazy imports to avoid circular dependencies
    from app.services.ai.agent_clients import (
        generate_section_agent_mode_async, 
        CaseBundle, 
        init_openai_client, 
        init_anthropic_client,
        build_system_instruction
    )
    try:
        from app.services.ai.debate_subgraph import run_debate_for_section as run_granular_for_section
    except Exception:
        run_granular_for_section = None
    
    # Resolve model selection (canonical ids) with safe defaults
    judge_model = state.get("judge_model") or DEFAULT_JUDGE_MODEL
    gpt_model = state.get("gpt_model") or (DEFAULT_DEBATE_MODELS[0] if DEFAULT_DEBATE_MODELS else "gpt-5.2")
    claude_model = state.get("claude_model") or (DEFAULT_DEBATE_MODELS[1] if len(DEFAULT_DEBATE_MODELS) > 1 else "claude-4.5-sonnet")
    drafter_models = state.get("drafter_models") or []
    reviewer_models = state.get("reviewer_models") or []
    citation_style = (state.get("citation_style") or "forense").lower()

    citation_instr = ""
    if citation_style in ("abnt", "hibrido"):
        citation_instr = """
## ESTILO DE CITAÇÃO (ABNT/HÍBRIDO) — OBRIGATÓRIO
1) **Autos/peças do processo**: mantenha o padrão forense **[TIPO - Doc. X, p. Y]** quando citar fatos dos autos.
2) **Jurisprudência**: ao citar julgados, inclua tribunal + classe + número + UF quando houver no contexto (ex.: STJ, REsp n. 1.234.567/RS).
3) **Notas de rodapé**: use [n] no texto e inclua ao final **NOTAS DE RODAPÉ (ABNT NBR 6023)** com a referência completa de cada nota.
4) **Fontes acadêmicas/doutrina** (quando houver no RAG): use citação no texto (AUTOR, ano) e detalhe a referência completa nas notas ABNT.
5) Se faltar metadado (autor/ano/local), não invente: use [[PENDENTE: completar referência ABNT da fonte X]].
""".strip()

    chat_personality = (state.get("chat_personality") or "juridico").lower()
    personality_instr = build_personality_instructions(chat_personality)
    system_instruction = build_system_instruction(chat_personality)

    # Judge model (provider-agnostic)
    drafter = None
    judge_cfg = get_model_config(judge_model)
    if judge_cfg and judge_cfg.provider == "google":
        try:
            from app.services.ai.gemini_drafter import GeminiDrafterWrapper
            drafter = GeminiDrafterWrapper(model_name=get_api_model_name(judge_model))
            logger.info("✅ GeminiDrafterWrapper initialized (judge)")
        except ImportError as e:
            logger.warning(f"⚠️ GeminiDrafterWrapper not available: {e}.")
    
    # State extraction
    outline = state.get("outline", [])
    research_context = state.get("research_notes") or state.get("research_context", "") or ""
    thesis = state.get("tese", "")
    mode = state.get("mode", "PETICAO")
    input_text = state.get("input_text", "")
    try:
        temperature = float(state.get("temperature", 0.3))
    except (TypeError, ValueError):
        temperature = 0.3
    temperature = max(0.0, min(1.0, temperature))
    length_guidance = build_length_guidance(state, len(outline))
    reasoning_level = state.get("thinking_level", "medium")
    max_granular_passes = _resolve_cap_value(state.get("max_granular_passes"), default=None)
    max_granular_retries = None
    if max_granular_passes is not None:
        max_granular_retries = max(0, max_granular_passes - 1)
    
    processed_sections = []
    has_divergence = False
    divergence_parts = []
    stream_tokens = bool(state.get("stream_tokens", False))
    try:
        stream_chunk_chars = int(state.get("stream_token_chunk_chars") or 40)
    except (TypeError, ValueError):
        stream_chunk_chars = 40
    stream_chunk_chars = max(10, min(stream_chunk_chars, 400))
    stream_started = False
    
    # Initialize API Clients Once
    gpt_client = None
    claude_client = None
    
    try:
        gpt_client = init_openai_client()
        claude_client = init_anthropic_client()
        logger.info(f"✅ API Clients: GPT={bool(gpt_client)}, Claude={bool(claude_client)}")
    except Exception as e:
        logger.error(f"❌ Client init failed: {e}")
    
    requested_drafter_models = state.get("drafter_models") or []
    requested_reviewer_models = state.get("reviewer_models") or []
    has_custom_lists = bool(requested_drafter_models or requested_reviewer_models)
    if has_custom_lists:
        use_multi_agent = bool(state.get("use_multi_agent")) and (gpt_client or claude_client or drafter)
    else:
        use_multi_agent = state.get("use_multi_agent") and gpt_client and claude_client
    
    # v5.3: Context Caching for Gemini (reduces token usage by 40-60%)
    from app.services.ai.agent_clients import get_or_create_context_cache, get_gemini_client
    context_cache = None
    context_cache_created = False
    job_id = state.get("job_id", "")
    
    if judge_cfg and judge_cfg.provider == "google" and len(outline) >= 3 and job_id:
        # Build unified context that will be reused across all sections
        gemini_client = get_gemini_client()
        if gemini_client:
            unified_context = f"""## CONTEXTO FACTUAL DO CASO
            
{input_text[:20000]}

## PESQUISA E FONTES (RAG)

{research_context[:30000]}

## TESE PRINCIPAL

{thesis}
"""
            context_cache = get_or_create_context_cache(
                client=gemini_client,
                job_id=job_id,
                context_content=unified_context,
                model_name=get_api_model_name(judge_model),
                num_sections=len(outline)
            )
            context_cache_created = context_cache is not None
            if context_cache_created:
                logger.info(f"📦 Context cache ativo para {len(outline)} seções")
    
    # v6.1: Parallel Section Processing
    async def process_single_section(i, title, prev_sections_for_this_sec):
        section_start = f"[{i+1}/{len(outline)}] {title}"
        logger.info(f"📝 {section_start}")
        
        if job_id:
            _emit_event(
                state,
                "section_start",
                {"index": i + 1, "total": len(outline)},
                phase="debate",
                section=title,
            )
            _emit_event(
                state,
                "section_context_start",
                {"index": i + 1, "total": len(outline)},
                phase="research",
                section=title,
                node="resolve_section_context",
            )
        
        section_context, route_config, safe_mode = await _resolve_section_context(
            state,
            title,
            input_text,
            thesis,
            research_context
        )
        
        safe_mode_block = SAFE_MODE_INSTRUCTION if safe_mode else ""
        evidence_policy = build_evidence_policy(state.get("audit_mode", "sei_only"))
        web_citation_policy = build_web_citation_policy(state.get("citations_map"))
        fact_check_summary = (state.get("fact_check_summary") or "").strip()
        fact_check_block = f"### FACT-CHECK SEI:\n{fact_check_summary}\n" if fact_check_summary else ""

        limit_facts, limit_rag = _calculate_context_limits(judge_model)
        
        try:
            from app.services.ai.prompt_constants import (
                ROLE_WRITER, LEGAL_WRITING_RULES, OUTPUT_FORMAT_SECTION
            )
            role_text = ROLE_WRITER.format(mode=mode)
        except ImportError:
            role_text = f"Você é um especialista em redação jurídica para {mode}."
            LEGAL_WRITING_RULES = "Use linguagem formal e impessoal."
            OUTPUT_FORMAT_SECTION = "Retorne apenas o texto da seção."

        prompt_base = f"""
# ROLE
{role_text}

# TASK
Redija a seção "{title}" para um documento do tipo {mode}, defendendo a tese: "{thesis}".

# CONTEXT
## Fatos do Caso (Extraído dos Autos)
{input_text[:limit_facts]}

{fact_check_block}

## Pesquisa Jurídica Disponível
{section_context[:limit_rag] if section_context else "Nenhuma pesquisa adicional disponível."}

# RULES
{LEGAL_WRITING_RULES}
{citation_instr}
{personality_instr}
{length_guidance}
{evidence_policy}
{web_citation_policy}
{safe_mode_block}

# OUTPUT FORMAT
{OUTPUT_FORMAT_SECTION}
"""
        use_granular = _should_use_granular_for_section(state, title, route_config, safe_mode)
        
        try:
            if use_granular and run_granular_for_section and gpt_client and claude_client:
                result = await run_granular_for_section(
                    section_title=title,
                    section_index=i,
                    prompt_base=prompt_base,
                    rag_context=section_context or research_context,
                    thesis=thesis,
                    mode=mode,
                    gpt_client=gpt_client,
                    claude_client=claude_client,
                    drafter=drafter,
                    gpt_model=gpt_model,
                    claude_model=claude_model,
                    judge_model=judge_model,
                    temperature=temperature,
                    previous_sections=prev_sections_for_this_sec,
                    previous_sections_excerpts=None,
                    formatting_options=state.get("formatting_options"),
                    template_structure=state.get("template_structure"),
                    max_retries=max_granular_retries,
                    job_id=job_id,
                )

                drafts_local = _as_dict(result.get("drafts"))
                metrics_local = _as_dict(result.get("metrics"))
                judge_structured = _as_dict(
                    drafts_local.get("judge_structured") or metrics_local.get("judge_structured")
                )
                merge_rationale = _extract_merge_rationale(judge_structured)
                merge_decisions = _as_list(judge_structured.get("decisions") or judge_structured.get("merge_decisions"))
                revision_changelog = _as_list(judge_structured.get("changelog") or judge_structured.get("revision_changelog"))

                critique_structured = drafts_local.get("critique_structured")
                if not isinstance(critique_structured, dict):
                    critique_structured = metrics_local.get("critique_structured")
                if not isinstance(critique_structured, dict):
                    critique_structured = _fallback_structured_critique(
                        drafts_local,
                        result.get("divergencias", "") or "",
                    )

                review_block = {
                    "critique": {
                        "issues": _as_list(critique_structured.get("issues")),
                        "summary": _coalesce_str(critique_structured.get("summary")),
                        "by_agent": _as_dict(critique_structured.get("by_agent")),
                    },
                    "revision": {
                        "changelog": revision_changelog,
                        "resolved": _as_list(judge_structured.get("resolved_issues")),
                        "unresolved": _as_list(judge_structured.get("unresolved_issues")),
                    },
                    "merge": {
                        "rationale": merge_rationale,
                        "decisions": merge_decisions,
                        "judge_structured": judge_structured,
                    },
                }

                result_record = build_section_record(
                    section_title=title,
                    merged_content=result.get("merged_content", ""),
                    divergence_details=result.get("divergencias", ""),
                    drafts=drafts_local,
                    metrics=metrics_local,
                    claims_requiring_citation=result.get("claims_requiring_citation"),
                    removed_claims=result.get("removed_claims"),
                    risk_flags=result.get("risk_flags"),
                    quality_score=metrics_local.get("quality_score"),
                    review=review_block,
                )
                if job_id:
                    _emit_event(
                        state,
                        "section_completed",
                        {
                            "hassignificantdivergence": bool(result.get("divergencias")),
                            "qualityscore": metrics_local.get("quality_score"),
                            "riskflags_count": len(result.get("risk_flags", []) or []),
                            "merged_preview": (result.get("merged_content", "") or "")[:600],
                        },
                        phase="debate",
                        section=title,
                    )
                return result_record, result.get("divergencias", "")

            if job_id and use_multi_agent:
                agents_list = drafter_models or [gpt_model, claude_model, judge_model]
                for agent_id in agents_list[:6]:
                    _emit_event(
                        state,
                        "agent_start",
                        {"role": "draft"},
                        phase="debate",
                        section=title,
                        agent=str(agent_id),
                    )
            if job_id:
                _emit_event(
                    state,
                    "section_stage",
                    {"stage": "draft"},
                    phase="debate",
                    section=title,
                )

            section_text, divergencias, drafts = await generate_section_agent_mode_async(
                section_title=title,
                prompt_base=prompt_base,
                case_bundle=_build_case_bundle(state),
                rag_local_context=section_context or research_context,
                drafter=drafter,
                gpt_client=gpt_client,
                claude_client=claude_client,
                gpt_model=gpt_model,
                claude_model=claude_model,
                drafter_models=drafter_models,
                reviewer_models=reviewer_models,
                judge_model=judge_model,
                reasoning_level=reasoning_level,
                temperature=temperature,
                thesis=thesis,
                web_search=state.get("web_search_enabled", False),
                search_mode=state.get("search_mode", "hybrid"),
                perplexity_search_mode=state.get("perplexity_search_mode"),
                multi_query=state.get("multi_query", True),
                breadth_first=state.get("breadth_first", False),
                mode=mode,
                extra_agent_instructions="\n".join(
                    [part for part in [citation_instr, personality_instr] if part]
                ).strip() or None,
                system_instruction=system_instruction,
                previous_sections=prev_sections_for_this_sec,
                cached_content=context_cache,
                num_committee_rounds=int(state.get("max_rounds", 1) or 1)
            )
            
            drafts_dict = _as_dict(drafts)
            judge_structured = _as_dict(drafts_dict.get("judge_structured"))
            quality_score = judge_structured.get("quality_score")
            merge_rationale = _extract_merge_rationale(judge_structured)
            merge_decisions = _as_list(judge_structured.get("decisions") or judge_structured.get("merge_decisions"))
            revision_changelog = _as_list(judge_structured.get("changelog") or judge_structured.get("revision_changelog"))
            critique_structured = _fallback_structured_critique(drafts_dict, divergencias or "")

            review_block = {
                "critique": {
                    "issues": _as_list(critique_structured.get("issues")),
                    "summary": _coalesce_str(critique_structured.get("summary")),
                    "by_agent": _as_dict(critique_structured.get("by_agent")),
                },
                "revision": {
                    "changelog": revision_changelog,
                    "resolved": _as_list(judge_structured.get("resolved_issues")),
                    "unresolved": _as_list(judge_structured.get("unresolved_issues")),
                },
                "merge": {
                    "rationale": merge_rationale,
                    "decisions": merge_decisions,
                    "judge_structured": judge_structured,
                },
            }

            result = build_section_record(
                section_title=title,
                merged_content=section_text,
                divergence_details=divergencias or "",
                drafts=drafts_dict,
                claims_requiring_citation=drafts_dict.get("claims_requiring_citation"),
                removed_claims=drafts_dict.get("removed_claims"),
                risk_flags=drafts_dict.get("risk_flags"),
                quality_score=quality_score,
                review=review_block,
            )
            if job_id:
                _emit_event(
                    state,
                    "section_stage",
                    {"stage": "merge"},
                    phase="debate",
                    section=title,
                )

            if job_id:
                preview_limit = 600
                if isinstance(drafts, dict):
                    drafts_by_model = drafts.get("drafts_by_model")
                    if isinstance(drafts_by_model, dict):
                        for mid, text in list(drafts_by_model.items())[:6]:
                            _emit_event(state, "agent_output", {"preview": (text or "")[:preview_limit]}, phase="debate", section=title, agent=str(mid))
                            _emit_event(state, "agent_end", {"status": "completed"}, phase="debate", section=title, agent=str(mid))
                _emit_event(
                    state,
                    "section_completed",
                    {
                        "hassignificantdivergence": bool(divergencias),
                        "qualityscore": quality_score,
                        "riskflags_count": len((drafts or {}).get("risk_flags", [])) if isinstance(drafts, dict) else 0,
                    },
                    phase="debate",
                    section=title,
                )
            
            logger.info(f"✅ {section_start} - Completed")
            return result, divergencias

        except Exception as e:
            logger.error(f"❌ {section_start} - Error: {e}")
            return build_section_record(
                section_title=title,
                merged_content=f"[Erro no comitê multi-agente: {str(e)}]",
                divergence_details=str(e),
                drafts={},
                claims_requiring_citation=[],
                removed_claims=[],
                risk_flags=[],
                quality_score=None,
                review=_default_review_block(),
            ), str(e)

    # Process each section
    section_tasks = []
    # Note: For parallel execution, the "previous_sections" for each section 
    # will only contain the FACTUAL context of the outline, since concurrent 
    # drafts won't have the final text of their predecessors yet.
    # This is a trade-off for speed (latency).
    for i, title in enumerate(outline):
        prev_factual = []
        if i > 0:
            prev_factual = [f"### {outline[j]}\n(Ponto anterior no sumário)" for j in range(max(0, i-3), i)]
        
        section_tasks.append(process_single_section(i, title, prev_factual))

    # Parallel Execute
    logger.info(f"🚀 Iniciando processamento paralelo de {len(section_tasks)} seções...")
    all_results = await asyncio.gather(*section_tasks)
    
    for res_tuple, div_text in all_results:
        processed_sections.append(res_tuple)
        if res_tuple.get("has_significant_divergence"):
            has_divergence = True
            divergence_parts.append(f"- **{res_tuple['section_title']}**: {div_text[:200]}...")

    processed_sections = _ensure_review_schema(processed_sections)

    # Post-process streaming events in order for UI (optional, since UI usually handles async)
    if stream_tokens:
        for res_tuple in processed_sections:
            _emit_section_stream(
                state,
                section_title=res_tuple["section_title"],
                section_text=res_tuple["merged_content"] or "",
                mode=mode,
                reset=res_tuple == processed_sections[0],
                chunk_size=stream_chunk_chars,
            )

    # Assemble full document
    full_doc = f"# {mode}\n\n"
    for section in processed_sections:
        full_doc += f"## {section.get('section_title', 'Seção')}\n\n"
        full_doc += section.get("merged_content", "")
        full_doc += "\n\n---\n\n"
    
    divergence_summary = "\n".join(divergence_parts) if divergence_parts else "✅ Consenso entre todos os agentes."
    
    logger.info(f"📄 Document assembled: {len(processed_sections)} sections, Divergence: {has_divergence}")
    if has_divergence:
        _emit_event(
            state,
            "divergence_detected",
            {"divergencesummary": divergence_summary},
            phase="debate",
        )
    
    updated_state = {
        **state,
        "processed_sections": processed_sections,
        "has_any_divergence": has_divergence,
        "divergence_summary": divergence_summary,
        "context_cache_created": context_cache_created,
        "context_cache_name": getattr(context_cache, 'name', None) if context_cache else None
    }
    stored = store_full_document_state(updated_state, full_doc)
    return _capture_draft_snapshot(stored)


async def debate_granular_node(state: DocumentState) -> DocumentState:
    """
    🔬 Granular Debate Node (Phase 3)
    
    Uses the 8-node sub-graph for each section:
    R1: GPT Draft → Claude Draft → Gemini Blind
    R2: GPT Critique ↔ Claude Critique
    R3: GPT Revise → Claude Revise
    R4: Judge Merge
    
    Enable with: USE_GRANULAR_DEBATE=true
    """
    logger.info("🔬 [Granular] Starting 8-Node Debate Sub-Graph...")
    
    from app.services.ai.debate_subgraph import run_debate_for_section
    from app.services.ai.agent_clients import (
        init_openai_client, 
        init_anthropic_client
    )
    
    # Resolve model selection (canonical ids) with safe defaults
    judge_model = state.get("judge_model") or DEFAULT_JUDGE_MODEL
    gpt_model = state.get("gpt_model") or (DEFAULT_DEBATE_MODELS[0] if DEFAULT_DEBATE_MODELS else "gpt-5.2")
    claude_model = state.get("claude_model") or (DEFAULT_DEBATE_MODELS[1] if len(DEFAULT_DEBATE_MODELS) > 1 else "claude-4.5-sonnet")
    citation_style = (state.get("citation_style") or "forense").lower()
    citation_instr = ""
    if citation_style in ("abnt", "hibrido"):
        citation_instr = """
## ESTILO DE CITAÇÃO (ABNT/HÍBRIDO) — OBRIGATÓRIO
1) Autos: preserve **[TIPO - Doc. X, p. Y]**
2) Juris: inclua tribunal/classe/número/UF quando houver
3) Notas: use [n] no texto e inclua ao final **NOTAS DE RODAPÉ (ABNT NBR 6023)**
4) Doutrina/Acadêmico: (AUTOR, ano) + notas ABNT completas
5) Sem metadado: [[PENDENTE: completar referência ABNT]]
""".strip()

    # Initialize Drafter
    drafter = None
    try:
        from app.services.ai.gemini_drafter import GeminiDrafterWrapper
        drafter = GeminiDrafterWrapper(model_name=get_api_model_name(judge_model))
    except ImportError as e:
        logger.warning(f"⚠️ GeminiDrafterWrapper not available: {e}")
    
    # State extraction
    outline = state.get("outline", [])
    research_context = state.get("research_notes") or state.get("research_context", "") or ""
    thesis = state.get("tese", "")
    mode = state.get("mode", "PETICAO")
    input_text = state.get("input_text", "")
    
    processed_sections = []
    has_divergence = False
    divergence_parts = []
    
    # Initialize clients
    gpt_client = init_openai_client()
    claude_client = init_anthropic_client()
    
    if not gpt_client or not claude_client:
        logger.error("❌ Cannot run granular mode without GPT and Claude clients")
        return {**state, "has_any_divergence": True, "divergence_summary": "API clients not available"}
    
    # v5.7: Missing variable definitions (bug fix)
    try:
        temperature = float(state.get("temperature", 0.3))
    except (TypeError, ValueError):
        temperature = 0.3
    temperature = max(0.0, min(1.0, temperature))

    max_passes = _resolve_cap_value(state.get("max_granular_passes"), default=None)
    max_retries = None
    if max_passes is not None:
        max_retries = max(0, max_passes - 1)
    
    length_guidance = build_length_guidance(state, len(outline))
    safe_mode_block = ""  # Will be set per-section if needed
    
    # Process each section through the sub-graph
    for i, title in enumerate(outline):
        logger.info(f"🔬 [{i+1}/{len(outline)}] Running sub-graph for: {title}")
        _emit_event(
            state,
            "section_start",
            {"index": i + 1, "total": len(outline)},
            phase="debate",
            section=title,
        )
        _emit_event(
            state,
            "progress",
            {"current": i + 1, "total": len(outline), "label": "debate"},
            phase="debate",
            section=title,
        )
        
        evidence_policy = build_evidence_policy(state.get("audit_mode", "sei_only"))
        web_citation_policy = build_web_citation_policy(state.get("citations_map"))
        fact_check_summary = (state.get("fact_check_summary") or "").strip()
        fact_check_block = f"### FACT-CHECK SEI:\n{fact_check_summary}\n" if fact_check_summary else ""

        # v5.7: Resolve section-specific context (bug fix - was missing)
        section_context, route_config, safe_mode = await _resolve_section_context(
            state,
            title,
            input_text,
            thesis,
            research_context
        )
        safe_mode_block = SAFE_MODE_INSTRUCTION if safe_mode else ""

        # v5.6: Dynamic Context Limits (Granular)
        limit_facts, limit_rag = _calculate_context_limits(judge_model)

        prompt_base = f"""
## SEÇÃO: {title}
## TIPO DE DOCUMENTO: {mode}
## TESE PRINCIPAL: {thesis}

{citation_instr}
{length_guidance}
{evidence_policy}
{web_citation_policy}
{safe_mode_block}

### CONTEXTO FACTUAL:
{input_text[:limit_facts]}

{fact_check_block}
### PESQUISA JURÍDICA:
{section_context[:limit_rag] if section_context else "Nenhuma pesquisa."}
"""
        
        try:
            # Track previous sections for anticontradiction
            previous_section_titles = [p["section_title"] for p in processed_sections]
            previous_section_excerpts = "\n\n".join([
                f"### {p.get('section_title','Seção')}\n{(p.get('merged_content','') or '')[:800]}"
                for p in processed_sections[-6:]
            ]) if processed_sections else "(Esta é a primeira seção)"
            
            result = await run_debate_for_section(
                section_title=title,
                section_index=i,
                prompt_base=prompt_base,
                rag_context=section_context or research_context,
                thesis=thesis,
                mode=mode,
                gpt_client=gpt_client,
                claude_client=claude_client,
                drafter=drafter,
                gpt_model=gpt_model,
                claude_model=claude_model,
                temperature=temperature,
                previous_sections=previous_section_titles,  # Back-compat
                previous_sections_excerpts=previous_section_excerpts,
                formatting_options=state.get("formatting_options"),
                template_structure=state.get("template_structure"),
                max_retries=max_retries,
                job_id=state.get("job_id"),
                # Note: extra instructions are included inside prompt_base for sub-graph
            )
            
            drafts_local = _as_dict(result.get("drafts"))
            metrics_local = _as_dict(result.get("metrics"))
            judge_structured = _as_dict(
                drafts_local.get("judge_structured") or metrics_local.get("judge_structured")
            )
            merge_rationale = _extract_merge_rationale(judge_structured)
            merge_decisions = _as_list(judge_structured.get("decisions") or judge_structured.get("merge_decisions"))
            revision_changelog = _as_list(judge_structured.get("changelog") or judge_structured.get("revision_changelog"))

            critique_structured = drafts_local.get("critique_structured")
            if not isinstance(critique_structured, dict):
                critique_structured = metrics_local.get("critique_structured")
            if not isinstance(critique_structured, dict):
                critique_structured = _fallback_structured_critique(
                    drafts_local,
                    result.get("divergencias", "") or "",
                )

            review_block = {
                "critique": {
                    "issues": _as_list(critique_structured.get("issues")),
                    "summary": _coalesce_str(critique_structured.get("summary")),
                    "by_agent": _as_dict(critique_structured.get("by_agent")),
                },
                "revision": {
                    "changelog": revision_changelog,
                    "resolved": _as_list(judge_structured.get("resolved_issues")),
                    "unresolved": _as_list(judge_structured.get("unresolved_issues")),
                },
                "merge": {
                    "rationale": merge_rationale,
                    "decisions": merge_decisions,
                    "judge_structured": judge_structured,
                },
            }

            processed_sections.append(build_section_record(
                section_title=title,
                merged_content=result.get("merged_content", ""),
                divergence_details=result.get("divergencias", ""),
                drafts=drafts_local,
                metrics=metrics_local,
                claims_requiring_citation=result.get("claims_requiring_citation"),
                removed_claims=result.get("removed_claims"),
                risk_flags=result.get("risk_flags"),
                quality_score=metrics_local.get("quality_score"),
                review=review_block,
            ))
            if stream_tokens:
                _emit_section_stream(
                    state,
                    section_title=title,
                    section_text=result.get("merged_content", "") or "",
                    mode=mode,
                    reset=not stream_started,
                    chunk_size=stream_chunk_chars,
                )
                stream_started = True
            _emit_event(
                state,
                "section_completed",
                {
                    "hassignificantdivergence": bool(result.get("divergencias")),
                    "qualityscore": (result.get("metrics", {}) or {}).get("quality_score"),
                    "riskflags_count": len(result.get("risk_flags", []) or []),
                    "merged_preview": (result.get("merged_content", "") or "")[:600],
                },
                phase="debate",
                section=title,
            )
            
            if result.get("divergencias"):
                has_divergence = True
                divergence_parts.append(f"- **{title}**: {result['divergencias'][:200]}...")
                
            logger.info(f"✅ [{i+1}/{len(outline)}] {title} - Complete")
            
        except Exception as e:
            logger.error(f"❌ [{i+1}/{len(outline)}] {title} - Error: {e}")
            _emit_event(
                state,
                "section_error",
                {"message": str(e)},
                phase="debate",
                section=title,
            )
            processed_sections.append(build_section_record(
                section_title=title,
                merged_content=f"[Erro no sub-grafo: {e}]",
                divergence_details=str(e),
                drafts={},
                metrics={},
                claims_requiring_citation=[],
                removed_claims=[],
                risk_flags=[],
                quality_score=None,
                review=_default_review_block(),
            ))
            if stream_tokens:
                _emit_section_stream(
                    state,
                    section_title=title,
                    section_text=f"[Erro no sub-grafo: {e}]",
                    mode=mode,
                    reset=not stream_started,
                    chunk_size=stream_chunk_chars,
                )
                stream_started = True
            has_divergence = True
            divergence_parts.append(f"- **{title}**: ERRO")

    processed_sections = _ensure_review_schema(processed_sections)

    # Assemble document
    full_doc = f"# {mode}\n\n"
    for section in processed_sections:
        full_doc += f"## {section.get('section_title', 'Seção')}\n\n"
        full_doc += section.get("merged_content", "")
        full_doc += "\n\n---\n\n"
    
    divergence_summary = "\n".join(divergence_parts) if divergence_parts else "✅ Consenso (Granular Mode)"
    
    logger.info(f"📄 [Granular] Document: {len(processed_sections)} sections, Divergence: {has_divergence}")
    if has_divergence:
        _emit_event(
            state,
            "divergence_detected",
            {"divergencesummary": divergence_summary},
            phase="debate",
        )
    
    updated_state = {
        **state,
        "processed_sections": processed_sections,
        "has_any_divergence": has_divergence,
        "divergence_summary": divergence_summary
    }
    stored = store_full_document_state(updated_state, full_doc)
    return _capture_draft_snapshot(stored)


async def section_hil_node(state: DocumentState) -> DocumentState:
    """
    HIL Checkpoint: Section-level review

    If `hil_target_sections` is provided, the workflow will interrupt for each
    matching section (by `section_title`) before proceeding to divergence/audit.
    """
    if state.get("auto_approve_hil", False):
        return {**state, "hil_section_payload": None}

    policy = (state.get("hil_section_policy") or "optional").lower()
    if policy == "none":
        return {**state, "hil_section_payload": None}

    targets = state.get("hil_target_sections") or []

    requested_targets = {t.strip() for t in targets if isinstance(t, str) and t.strip()}

    processed = state.get("processed_sections", []) or []
    if not isinstance(processed, list) or not processed:
        return {**state, "hil_section_payload": None}

    processed_titles = {
        p.get("section_title")
        for p in processed
        if isinstance(p, dict) and isinstance(p.get("section_title"), str) and p.get("section_title")
    }

    if policy == "required":
        # If caller didn't provide targets (or provided only invalid titles), require review for all sections.
        targets_set = requested_targets & processed_titles
        if not targets_set:
            targets_set = set(processed_titles)
    else:
        # Optional: only review explicitly targeted sections.
        targets_set = requested_targets & processed_titles

    if not targets_set:
        return {**state, "hil_section_payload": None}

    target_score = float(state.get("target_section_score") or 0)

    mode = state.get("mode", "PETICAO")
    try:
        temperature = float(state.get("temperature", 0.3))
    except (TypeError, ValueError):
        temperature = 0.3
    temperature = max(0.0, min(1.0, temperature))

    # Helpers for re-generation
    async def regenerate_section_single_model(title: str, current_text: str, instructions: str) -> str:
        """Fast rewrite using single-model (Gemini drafter wrapper if available)."""
        drafter = None
        try:
            from app.services.ai.gemini_drafter import GeminiDrafterWrapper
            drafter = GeminiDrafterWrapper()
        except Exception as e:
            logger.warning(f"⚠️ GeminiDrafterWrapper not available for section rewrite: {e}")

        mode_local = state.get("mode", "PETICAO")
        thesis_local = state.get("tese", "")
        input_text_local = state.get("input_text", "")
        research_local = state.get("research_context", "") or ""
        # v5.7: Improved prompt structure
        try:
            from app.services.ai.prompt_constants import ROLE_WRITER, OUTPUT_FORMAT_SECTION
        except ImportError:
            ROLE_WRITER = "Você é um especialista em redação jurídica para {mode}."
            OUTPUT_FORMAT_SECTION = "Retorne apenas o texto da seção."

        prompt = f"""
# ROLE
{ROLE_WRITER.format(mode=mode_local)}

# TASK
Reescreva APENAS a seção abaixo do documento, seguindo as instruções do revisor humano.

# CONTEXT
## Tipo de Documento: {mode_local}
## Seção: {title}
## Tese: {thesis_local}

## Instruções do Revisor Humano (OBRIGATÓRIAS)
{instructions}

## Contexto (Autos)
{input_text_local[:2000]}

## Pesquisa Jurídica
{research_local[:2500] if research_local else "(sem pesquisa)"}

## Texto Atual da Seção (referência)
{current_text[:8000]}

# RULES
1. Siga FIELMENTE as instruções do revisor
2. Mantenha o tom e estilo do restante do documento
3. Preserve citações e referências válidas
4. NÃO invente fatos ou documentos

# OUTPUT FORMAT
{OUTPUT_FORMAT_SECTION}
Entregue somente o texto final da seção, sem cabeçalhos '##', sem prefácio.
""".strip()

        if drafter:
            try:
                resp = drafter._generate_with_retry(prompt, temperature=temperature)
                if resp and getattr(resp, "text", None):
                    return resp.text
            except Exception as e:
                logger.warning(f"⚠️ Single-model rewrite failed: {e}")

        # Fallback: keep current text if rewrite fails
        return current_text

    async def regenerate_section_multi_agent(title: str, current_text: str, instructions: str) -> Dict[str, Any]:
        """
        Multi-agent rewrite using the same committee pipeline, but scoped to a single section.
        Returns {text, divergencias, drafts}.
        """
        from app.services.ai.agent_clients import (
            generate_section_agent_mode_async,
            init_openai_client,
            init_anthropic_client,
            CaseBundle,
            build_system_instruction,
        )

        drafter = None
        try:
            from app.services.ai.gemini_drafter import GeminiDrafterWrapper
            drafter = GeminiDrafterWrapper()
        except Exception as e:
            logger.warning(f"⚠️ GeminiDrafterWrapper not available for multi-agent rewrite: {e}")

        gpt_client = None
        claude_client = None
        try:
            gpt_client = init_openai_client()
            claude_client = init_anthropic_client()
        except Exception as e:
            logger.error(f"❌ Multi-agent clients not available for section rewrite: {e}")

        if not gpt_client or not claude_client:
            return {"text": current_text, "divergencias": "", "drafts": {}}

        mode_local = state.get("mode", "PETICAO")
        thesis_local = state.get("tese", "")
        input_text_local = state.get("input_text", "")
        research_local = state.get("research_context", "") or ""
        reasoning_level = state.get("thinking_level", "medium")
        chat_personality = (state.get("chat_personality") or "juridico").lower()
        system_instruction = build_system_instruction(chat_personality)
        judge_model_local = state.get("judge_model") or DEFAULT_JUDGE_MODEL
        gpt_model_local = state.get("gpt_model") or (DEFAULT_DEBATE_MODELS[0] if DEFAULT_DEBATE_MODELS else "gpt-5.2")
        claude_model_local = state.get("claude_model") or (DEFAULT_DEBATE_MODELS[1] if len(DEFAULT_DEBATE_MODELS) > 1 else "claude-4.5-sonnet")
        drafter_models_local = state.get("drafter_models") or []
        reviewer_models_local = state.get("reviewer_models") or []

        prev_sections = []
        processed_local = state.get("processed_sections", []) or []
        if isinstance(processed_local, list):
            prev_sections = [
                f"### {p.get('section_title','Seção')}\n{(p.get('merged_content','') or '')[:800]}"
                for p in processed_local[-6:]
                if isinstance(p, dict)
            ]

        prompt_base = f"""
## SEÇÃO: {title}
## TIPO DE DOCUMENTO: {mode_local}
## TESE PRINCIPAL: {thesis_local}

### INSTRUÇÕES DO REVISOR HUMANO (OBRIGATÓRIAS):
{instructions}

### CONTEXTO FACTUAL (Extraído dos Autos):
{input_text_local[:2000]}

### PESQUISA JURÍDICA:
{research_local[:3000] if research_local else "Nenhuma pesquisa adicional disponível."}

### TEXTO ATUAL (para referência e melhoria):
{current_text[:8000]}
""".strip()

        section_text, divergencias, drafts = await generate_section_agent_mode_async(
            section_title=title,
            prompt_base=prompt_base,
            case_bundle=_build_case_bundle(state, processo_id="langgraph-section-hil"),
            rag_local_context=research_local,
            drafter=drafter,
            gpt_client=gpt_client,
            claude_client=claude_client,
            gpt_model=gpt_model_local,
            claude_model=claude_model_local,
            drafter_models=drafter_models_local,
            reviewer_models=reviewer_models_local,
            judge_model=judge_model_local,
            reasoning_level=reasoning_level,
            temperature=temperature,
            thesis=thesis_local,
            web_search=state.get("web_search_enabled", False),
            search_mode=state.get("search_mode", "hybrid"),
            perplexity_search_mode=state.get("perplexity_search_mode"),
            multi_query=state.get("multi_query", True),
            breadth_first=state.get("breadth_first", False),
            mode=mode_local,
            previous_sections=prev_sections,
            system_instruction=system_instruction,
            num_committee_rounds=int(state.get("max_rounds", 1) or 1)  # v6.0: Recursive Committee Loop
        )

        return {"text": section_text, "divergencias": divergencias or "", "drafts": drafts or {}}

    # Iterate and require approval for each target section.
    for idx, sec in enumerate(processed):
        if not isinstance(sec, dict):
            continue
        title = sec.get("section_title") or ""
        if title not in targets_set:
            continue
        sec_score = sec.get("quality_score")
        if sec_score is None and isinstance(sec.get("metrics"), dict):
            sec_score = sec["metrics"].get("quality_score")
        # Only gate by score when policy is optional. Skip if score meets target; review when score is low or missing.
        if policy != "required" and target_score:
            try:
                score_val = float(sec_score) if sec_score is not None else None
            except Exception:
                score_val = None
            if score_val is not None and score_val >= target_score:
                continue

        # Keep interrupt payload also in state so the SSE layer can read it reliably.
        payload: Dict[str, Any] = {
            "section_title": title,
            "merged_content": sec.get("merged_content", "") or "",
            "divergence_details": sec.get("divergence_details", "") or "",
            "drafts": sec.get("drafts", {}) or {},
            "document_preview": _get_full_document_preview(state, 2000),
        }
        divergence_instructions = (state.get("divergence_hil_instructions") or "").strip()
        if divergence_instructions:
            payload["instructions"] = divergence_instructions

        # Mutate in-place so checkpointer snapshot includes this payload at interrupt time.
        state["hil_section_payload"] = payload  # type: ignore[typeddict-item]

        decision, state, skipped = _try_hil_interrupt(
            state,
            "section",
            {
                "type": "section_review",
                "checkpoint": "section",
                "message": f"Revise a seção '{title}' antes de prosseguir.",
                **payload,
            },
        )
        if skipped:
            processed[idx]["human_review"] = "auto_approved"
            continue

        # Guarantee review: do not proceed until approved (job will keep pausing).
        while not decision.get("approved", False):
            instr = (decision.get("instructions") or "").strip()

            # If instructions were provided, regenerate via IA respecting current mode (single vs multi-agent).
            if instr:
                try:
                    use_multi = bool(state.get("use_multi_agent", False))
                    logger.info(f"🛠️ [Section HIL] Rewriting section via IA: title='{title}', multi_agent={use_multi}")

                    if use_multi:
                        res = await regenerate_section_multi_agent(title, payload.get("merged_content", "") or "", instr)
                        payload["merged_content"] = res.get("text", payload.get("merged_content", ""))
                        payload["divergence_details"] = res.get("divergencias", payload.get("divergence_details", ""))
                        payload["drafts"] = res.get("drafts", payload.get("drafts", {}))
                    else:
                        payload["merged_content"] = await regenerate_section_single_model(
                            title,
                            payload.get("merged_content", "") or "",
                            instr
                        )

                    # Apply candidate text into state so subsequent nodes see the updated section (even before approval).
                    processed[idx]["merged_content"] = payload.get("merged_content", "")
                    processed[idx]["human_review"] = "ai_rewrite_pending"

                    # Re-assemble document for preview consistency
                    mode_local = state.get("mode", "PETICAO")
                    full_doc = f"# {mode_local}\n\n"
                    for s in processed:
                        if not isinstance(s, dict):
                            continue
                        full_doc += f"## {s.get('section_title', 'Seção')}\n\n"
                        full_doc += s.get("merged_content", "") or ""
                        full_doc += "\n\n---\n\n"
                    updated_state = store_full_document_state(state, full_doc)
                    state = {**updated_state, "hil_section_payload": payload}
                    payload["document_preview"] = updated_state.get("full_document_preview") or full_doc[:2000]

                except Exception as e:
                    logger.error(f"❌ [Section HIL] IA rewrite failed for '{title}': {e}")

            # Keep last instructions visible in the next interrupt (so user can iterate).
            if instr:
                payload["instructions"] = instr

            state["hil_section_payload"] = payload  # type: ignore[typeddict-item]

            decision, state, skipped = _try_hil_interrupt(
                state,
                "section",
                {
                    "type": "section_review",
                    "checkpoint": "section",
                    "message": f"Seção '{title}' precisa de aprovação. Edite manualmente ou aprove para continuar.",
                    **payload,
                },
            )
            if skipped:
                processed[idx]["human_review"] = "auto_approved"
                break

        if not skipped:
            edits = decision.get("edits")
            if edits:
                processed[idx]["merged_content"] = edits
                processed[idx]["human_review"] = "edited"
            else:
                processed[idx]["human_review"] = "approved"

    # Re-assemble full document after potential edits
    full_doc = f"# {mode}\n\n"
    for section in processed:
        if not isinstance(section, dict):
            continue
        full_doc += f"## {section.get('section_title', 'Seção')}\n\n"
        full_doc += section.get("merged_content", "") or ""
        full_doc += "\n\n---\n\n"

    updated_state = {
        **state,
        "processed_sections": processed,
        "hil_section_payload": None,
        "divergence_hil_instructions": None,
    }
    return store_full_document_state(updated_state, full_doc)


async def divergence_hil_node(state: DocumentState) -> DocumentState:
    """HIL Checkpoint: Review divergences"""
    if state.get("auto_approve_hil", False):
        logger.info("✅ [Phase2] Auto-approve enabled, skipping divergence HIL")
        return {**state, "human_approved_divergence": True}

    if not state.get("has_any_divergence"):
        logger.info("✅ [Phase2] No divergence, skipping HIL")
        return {**state, "human_approved_divergence": True}
    
    logger.info("🛑 [Phase2] HIL: Divergence Review")

    rounds = int(state.get("divergence_hil_round", 0) or 0)
    max_rounds = int(state.get("max_divergence_hil_rounds", 2) or 2)

    divergent_sections = [
        sec.get("section_title")
        for sec in state.get("processed_sections", []) or []
        if isinstance(sec, dict) and sec.get("section_title") and sec.get("has_significant_divergence")
    ]
    
    decision, state, skipped = _try_hil_interrupt(
        state,
        "divergence",
        {
            "type": "divergence_review",
            "checkpoint": "divergence",
            "message": "Divergências detectadas no debate multi-agente.",
            "divergence_summary": state.get("divergence_summary", ""),
            "document_preview": _get_full_document_preview(state, 3000),
        },
    )
    if skipped:
        return {**state, "human_approved_divergence": True}

    edits = (decision.get("edits") or "").strip()
    if edits:
        updated = {
            **state,
            "human_approved_divergence": True,
            "human_edits": edits,
            "document_overridden_by_human": True,
            "divergence_hil_instructions": None,
            "divergence_hil_round": rounds,
            "hil_target_sections": [],
        }
        return store_full_document_state(updated, edits)

    approved = bool(decision.get("approved", False))
    if approved:
        return {
            **state,
            "human_approved_divergence": True,
            "human_edits": None,
            "divergence_hil_instructions": None,
            "divergence_hil_round": rounds,
        }

    rounds += 1
    updated = {
        **state,
        "human_approved_divergence": False,
        "human_edits": None,
        "divergence_hil_round": rounds,
        "max_divergence_hil_rounds": max_rounds,
        "divergence_hil_instructions": (decision.get("instructions") or "").strip() or None,
    }
    if divergent_sections:
        updated["hil_target_sections"] = divergent_sections
        updated["hil_section_policy"] = "required"
    if rounds >= max_rounds:
        return _with_final_decision(updated, "NEED_HUMAN_REVIEW", extra_reasons=["divergence_rejected"])
    return updated


async def audit_node(state: DocumentState) -> DocumentState:
    """
    ⚖️ Real Audit Node
    
    Calls AuditService to analyze the document for:
    - Citation hallucinations
    - Procedural errors
    - Legal validity issues
    """
    logger.info("⚖️ [Phase4] Real Audit Starting...")
    
    full_document = resolve_full_document(state)
    citations_map = state.get("citations_map")
    citation_report = validate_citations(full_document, citations_map)
    used_keys = citation_report.get("used_keys", [])
    missing_keys = citation_report.get("missing_keys", [])
    orphan_keys = citation_report.get("orphan_keys", [])
    
    if not full_document:
        logger.warning("⚠️ No document to audit")
        return {**state, "audit_status": "aprovado", "audit_report": None, "audit_issues": []}

    base_state = {
        **state,
        "citation_validation_report": citation_report,
        "citation_used_keys": used_keys,
        "citation_missing_keys": missing_keys,
        "citation_orphan_keys": orphan_keys,
    }
    citation_issues = [
        f"Citação [{key}] sem fonte em citations_map"
        for key in missing_keys
    ]
    
    try:
        # Call real audit service
        result = audit_service.audit_document(full_document)
        
        audit_markdown = result.get("audit_report_markdown", "")
        citations = result.get("citations", [])
        
        # Parse issues from markdown (look for 🔴 markers)
        issues = []
        if "🔴" in audit_markdown:
            # Extract lines with red markers
            for line in audit_markdown.split("\n"):
                if "🔴" in line:
                    issues.append(line.strip())
        if citation_issues:
            issues = citation_issues + issues
        
        # Determine status
        if "Reprovado" in audit_markdown:
            status = "reprovado"
        elif issues or "Ressalvas" in audit_markdown:
            status = "aprovado_ressalvas"
        else:
            status = "aprovado"
        if citation_issues:
            status = "reprovado"
        
        logger.info(f"⚖️ Audit complete: {status}, {len(issues)} issues found")
        
        return {
            **base_state,
            "audit_status": status,
            "audit_report": {
                "markdown": audit_markdown,
                "citations": citations,
                "issue_count": len(issues),
                "citation_validation": citation_report,
            },
            "audit_issues": issues
        }
        
    except Exception as e:
        logger.error(f"❌ Audit failed: {e}")
        audit_mode = (state.get("audit_mode") or "").lower()
        risco = (state.get("risco") or "").lower()
        safe_mode = bool(state.get("safe_mode", False))
        fail_closed = audit_mode == "sei_only" or safe_mode or risco == "alto"
        status = "reprovado" if fail_closed or citation_issues else "aprovado_ressalvas"
        issues = citation_issues + [f"Falha na auditoria: {e}"]
        updated_state = {
            **base_state,
            "audit_status": status,
            "audit_report": {"error": str(e), "citation_validation": citation_report},
            "audit_issues": issues,
        }
        if fail_closed:
            updated_state["force_final_hil"] = True
        return {
            **updated_state,
        }


async def evaluate_hil_node(state: DocumentState) -> DocumentState:
    """
    📋 Evaluate HIL Checklist Node
    
    Runs the Universal HIL Decision Engine to evaluate all 10 risk factors
    and determine if human review is mandatory.
    
    Uses data from:
    - User context (destino, risco)
    - Audit results (citations, issues)
    - Debate results (divergences)
    """
    logger.info("📋 [Phase4] Evaluating HIL Checklist...")
    
    # Get context from state
    destino = state.get("destino", "uso_interno")
    risco = state.get("risco", "baixo")
    
    # Get audit data
    audit_report = state.get("audit_report", {})
    audit_status = state.get("audit_status", "aprovado")
    
    # Get debate data
    has_divergence = state.get("has_any_divergence", False)
    divergence_summary = state.get("divergence_summary", "")
    
    # Run full evaluation
    checklist = hil_engine.evaluate(
        destino=destino,
        risco=risco,
        audit_report=audit_report,
        audit_status=audit_status,
        has_divergence=has_divergence,
        divergence_summary=divergence_summary
    )
    
    # Pending citations from debate (claims requiring citation)
    pending_count = 0
    for sec in state.get("processed_sections", []) or []:
        pending = sec.get("claims_requiring_citation") or []
        if isinstance(pending, list):
            pending_count += len(pending)
    if pending_count:
        # Force HIL via explicit pending citations factor
        try:
            checklist.num_citacoes_pendentes = pending_count  # type: ignore[attr-defined]
        except Exception:
            pass
        checklist.evaluation_notes.append(f"{pending_count} item(ns) com citação/validação pendente (debate)")
    
    # Update checklist with audit issues (for fato_inventado detection)
    audit_issues = state.get("audit_issues", [])
    if any("inexistente" in issue.lower() or "alucinação" in issue.lower() for issue in audit_issues):
        checklist.fato_inventado = True
        checklist.evaluation_notes.append("Citação/fato inexistente detectado na auditoria")
    
    # Log result
    triggered = checklist.get_triggered_factors()
    if triggered:
        logger.info(f"🛑 HIL REQUIRED - Factors: {triggered}")
    else:
        logger.info("✅ HIL NOT REQUIRED - All checks passed")

    risk_score = None
    try:
        risk_score = max(0.0, min(1.0, 1.0 - float(checklist.score_confianca)))
    except Exception:
        risk_score = None

    risk_level = "LOW"
    if checklist.get_hil_level() == "critical":
        risk_level = "HIGH"
    elif checklist.requires_hil():
        risk_level = "MED"
    if risk_score is not None:
        if risk_score >= 0.6:
            risk_level = "HIGH"
        elif risk_score >= 0.3 and risk_level == "LOW":
            risk_level = "MED"
    
    updated_state = {
        **state,
        "hil_checklist": checklist.to_dict(),
        "hil_risk_score": risk_score,
        "hil_risk_reasons": triggered,
        "hil_risk_level": risk_level,
    }
    if checklist.requires_hil():
        updated_state["force_final_hil"] = True
    return updated_state


async def propose_corrections_node(state: DocumentState) -> DocumentState:
    """
    📝 Propose Corrections Node
    
    If audit found issues, generate a corrected version of the document.
    Uses LLM to rewrite problematic sections based on audit feedback.
    """
    issues = state.get("audit_issues", [])

    patch_result = state.get("patch_result", {}) or {}
    if isinstance(patch_result, dict) and patch_result.get("patches_applied", 0) > 0:
        logger.info("✅ Targeted Patch aplicado; pulando geração de correções completas")
        return {**state, "proposed_corrections": state.get("proposed_corrections"), "corrections_diff": state.get("corrections_diff")}
    
    if not issues:
        logger.info("✅ No audit issues, skipping corrections")
        return {**state, "proposed_corrections": None, "corrections_diff": None}
    
    logger.info(f"📝 [Phase4] Proposing corrections for {len(issues)} issues...")
    
    # Initialize drafter for corrections
    try:
        from app.services.ai.gemini_drafter import GeminiDrafterWrapper
        drafter = GeminiDrafterWrapper()
    except ImportError:
        logger.error("❌ GeminiDrafterWrapper not available for corrections")
        return {**state, "proposed_corrections": None}
    
    full_document = resolve_full_document(state)
    mode = state.get("mode", "PETICAO")
    
    # v5.7: Improved prompt structure
    try:
        from app.services.ai.prompt_constants import ROLE_REVIEWER, OUTPUT_FORMAT_SECTION
    except ImportError:
        ROLE_REVIEWER = "Você é um revisor jurídico sênior."
        OUTPUT_FORMAT_SECTION = "Retorne o documento corrigido."
    
    prompt = f"""
# ROLE
{ROLE_REVIEWER}

# TASK
Corrija o documento abaixo com base nos problemas identificados pela auditoria.

# CONTEXT
## Problemas Encontrados
{chr(10).join(['- ' + issue for issue in issues])}

## Documento Original ({mode})
{full_document[:300000]}

# RULES
1. CORRIJA apenas os trechos problemáticos apontados acima
2. NÃO invente citações, jurisprudências ou dados não fundamentados
3. Se uma citação foi apontada como inexistente, REMOVA-A ou substitua por fonte verificável
4. MANTENHA a estrutura geral e o tom do documento
5. Produza o documento COMPLETO corrigido

# OUTPUT FORMAT
Retorne o documento COMPLETO corrigido, não apenas os trechos alterados.

## DOCUMENTO CORRIGIDO:
"""
    
    try:
        resp = drafter._generate_with_retry(prompt)
        corrected = resp.text if resp else ""
        
        if not corrected:
            logger.warning("⚠️ Empty correction response")
            return {**state, "proposed_corrections": None}
        
        # Diff summary with ordering preserved
        import difflib
        original_lines = full_document.splitlines()
        corrected_lines = corrected.splitlines()
        diff = list(difflib.unified_diff(original_lines, corrected_lines, lineterm=""))
        diff_count = sum(
            1
            for line in diff
            if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
        )
        diff_summary = f"{diff_count} linhas alteradas"
        
        logger.info(f"📝 Corrections proposed: {diff_summary}")
        
        return {
            **state,
            "proposed_corrections": corrected,
            "corrections_diff": diff_summary
        }
        
    except Exception as e:
        logger.error(f"❌ Correction generation failed: {e}")
        return {**state, "proposed_corrections": None, "corrections_diff": f"Erro: {e}"}


async def correction_hil_node(state: DocumentState) -> DocumentState:
    """
    🛑 Correction HIL Checkpoint
    
    Human reviews proposed corrections before they're applied.
    Can approve, edit, or reject the corrections.
    """
    proposed = state.get("proposed_corrections")

    if state.get("auto_approve_hil", False):
        if proposed:
            logger.info("✅ Auto-approve enabled, applying corrections automatically")
            updated_state = {**state, "human_approved_corrections": True}
            return store_full_document_state(updated_state, proposed)
        return {**state, "human_approved_corrections": True}

    if not proposed:
        logger.info("✅ No corrections to review, skipping HIL")
        return {**state, "human_approved_corrections": True}
    
    logger.info("🛑 [Phase4] HIL: Correction Review")
    
    decision, state, skipped = _try_hil_interrupt(
        state,
        "correction",
        {
            "type": "correction_review",
            "checkpoint": "correction",
            "message": "Correções propostas com base na auditoria. Revise antes de aplicar.",
            "original_document": _get_full_document_preview(state, 3000),
            "proposed_corrections": proposed[:3000],
            "corrections_diff": state.get("corrections_diff", ""),
            "audit_issues": state.get("audit_issues", []),
            "audit_status": state.get("audit_status"),
        },
    )
    if skipped:
        if proposed:
            logger.info("⚠️ HIL cap reached, applying corrections automatically")
            updated_state = {**state, "human_approved_corrections": True}
            return store_full_document_state(updated_state, proposed)
        return {**state, "human_approved_corrections": True}
    
    if decision.get("approved"):
        # Apply corrections (use edited version if provided, else proposed)
        final_corrected = decision.get("edits") or proposed
        logger.info("✅ Corrections approved and applied")
        updated_state = {
            **state,
            "human_approved_corrections": True
        }
        return store_full_document_state(updated_state, final_corrected)
    
    logger.info("❌ Corrections rejected by human")
    return {
        **state,
        "human_approved_corrections": False,
        "human_edits": decision.get("instructions")
    }


async def final_committee_review_node(state: DocumentState) -> DocumentState:
    """
    🤝 Final Committee Review Node
    
    Holistic multi-agent review of the complete document before final approval.
    
    GPT, Claude and the Judge model review the entire document for:
    - Global coherence (contradictions between sections)
    - Logical flow (smooth transitions)
    - Thesis strength (persuasive narrative)
    
    The Judge synthesizes all reviews and produces final report.
    """
    state = _apply_budget_soft_caps(state, node="final_committee_review")
    logger.info("🤝 [Final Committee Review] Starting holistic document review...")
    parse_failures = list(state.get("json_parse_failures") or [])
    
    full_document = resolve_full_document(state)
    if not full_document:
        logger.warning("⚠️ No document for committee review")
        return {**state, "committee_review_report": None, "json_parse_failures": parse_failures}
    
    # Lazy imports to avoid circular dependencies
    from app.services.ai.agent_clients import (
        init_openai_client,
        init_anthropic_client
    )
    from app.services.ai.model_registry import get_api_model_name
    
    # Get model configs
    judge_model = state.get("judge_model") or DEFAULT_JUDGE_MODEL
    gpt_model = state.get("gpt_model") or (DEFAULT_DEBATE_MODELS[0] if DEFAULT_DEBATE_MODELS else "gpt-5.2")
    claude_model = state.get("claude_model") or (DEFAULT_DEBATE_MODELS[1] if len(DEFAULT_DEBATE_MODELS) > 1 else "claude-4.5-sonnet")
    thesis = state.get("tese", "")
    mode = state.get("mode", "PETICAO")
    
    # Truncate document for review
    doc_excerpt = full_document[:300000]
    
    # v5.7: Improved prompt structure
    try:
        from app.services.ai.prompt_constants import ROLE_REVIEWER, OUTPUT_FORMAT_JSON
    except ImportError:
        ROLE_REVIEWER = "Você é um revisor jurídico sênior."
        OUTPUT_FORMAT_JSON = "Retorne JSON válido."
    
    review_prompt_template = """
# ROLE
Você é um revisor sênior do comitê final, responsável pela aprovação de documentos jurídicos.

# TASK
Faça uma revisão holística do documento completo ANTES da entrega final.

# CONTEXT
## Tipo de Documento: {mode}
## Tese Principal: {thesis}

## Documento Completo
{document}

# RULES
1. Avalie coerência global (contradições entre seções)
2. Avalie fluxo lógico (transições, progressão)
3. Avalie força da tese (persuasão, fundamentação)
4. Identifique até 3 problemas críticos
5. Seja CONCISO (máx 500 palavras)

# OUTPUT FORMAT
Responda APENAS em JSON válido:
{{
  "coerencia": 0-10,
  "fluxo": 0-10,
  "tese": 0-10,
  "problemas": ["[SEÇÃO] - Problema"],
  "nota_final": 0-10,
  "resumo": "..."
}}
"""

    # Initialize clients
    gpt_client = None
    claude_client = None
    try:
        gpt_client = init_openai_client()
        claude_client = init_anthropic_client()
    except Exception as e:
        logger.warning(f"⚠️ Could not initialize all clients for committee review: {e}")

    judge_cfg = get_model_config(judge_model)
    judge_label = judge_cfg.label if judge_cfg else judge_model
    
    reviews = {}
    
    # Async review functions
    async def get_gpt_review():
        if not gpt_client:
            return None
        try:
            prompt = review_prompt_template.format(mode=mode, thesis=thesis, document=doc_excerpt)
            provider_name = "vertex-openai" if hasattr(getattr(gpt_client, "models", None), "generate_content") else "openai"
            with billing_context(node="final_committee_review_parallel", size="M"):
                if provider_name == "vertex-openai":
                    response = await asyncio.to_thread(
                        gpt_client.models.generate_content,
                        model=get_api_model_name(gpt_model),
                        contents=prompt
                    )
                    record_api_call(
                        kind="llm",
                        provider=provider_name,
                        model=get_api_model_name(gpt_model),
                        success=True,
                    )
                    return {"agent": "GPT", "response": response.text}
                response = await asyncio.to_thread(
                    gpt_client.chat.completions.create,
                    model=get_api_model_name(gpt_model),
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2,
                    max_tokens=1000
                )
                record_api_call(
                    kind="llm",
                    provider=provider_name,
                    model=get_api_model_name(gpt_model),
                    success=True,
                )
                return {"agent": "GPT", "response": response.choices[0].message.content}
        except Exception as e:
            record_api_call(
                kind="llm",
                provider="vertex-openai" if hasattr(getattr(gpt_client, "models", None), "generate_content") else "openai",
                model=get_api_model_name(gpt_model),
                success=False,
            )
            logger.warning(f"⚠️ GPT review failed: {e}")
            return None
    
    async def get_claude_review():
        if not claude_client:
            return None
        try:
            prompt = review_prompt_template.format(mode=mode, thesis=thesis, document=doc_excerpt)
            from app.services.ai.agent_clients import _is_anthropic_vertex_client
            provider_name = "vertex-anthropic" if _is_anthropic_vertex_client(claude_client) else "anthropic"
            with billing_context(node="final_committee_review_parallel", size="M"):
                response = await asyncio.to_thread(
                    claude_client.messages.create,
                    model=get_api_model_name(claude_model),
                    max_tokens=1000,
                    messages=[{"role": "user", "content": prompt}]
                )
                record_api_call(
                    kind="llm",
                    provider=provider_name,
                    model=get_api_model_name(claude_model),
                    success=True,
                )
                return {"agent": "Claude", "response": response.content[0].text}
        except Exception as e:
            record_api_call(
                kind="llm",
                provider="vertex-anthropic" if "_is_anthropic_vertex_client" in locals() and _is_anthropic_vertex_client(claude_client) else "anthropic",
                model=get_api_model_name(claude_model),
                success=False,
            )
            logger.warning(f"⚠️ Claude review failed: {e}")
            return None
    
    async def get_judge_review():
        try:
            prompt = review_prompt_template.format(mode=mode, thesis=thesis, document=doc_excerpt)
            with billing_context(node="final_committee_review_parallel", size="M"):
                response = await _call_model_any_async(
                    judge_model,
                    prompt,
                    temperature=0.2,
                    max_tokens=1000
                )
            if response:
                return {"agent": judge_label, "response": response}
            return None
        except Exception as e:
            logger.warning(f"⚠️ Judge review failed: {e}")
            return None
    
    # Run reviews in parallel
    try:
        results = await asyncio.gather(
            get_gpt_review(),
            get_claude_review(),
            get_judge_review(),
            return_exceptions=True
        )
        
        for result in results:
            if result and not isinstance(result, Exception) and result.get("response"):
                reviews[result["agent"]] = result["response"]
                
    except Exception as e:
        logger.error(f"❌ Parallel review failed: {e}")
    
    # If no reviews succeeded, skip
    if not reviews:
        logger.warning("⚠️ No reviews completed, skipping committee review")
        return {
            **state,
            "committee_review_report": {"status": "skipped", "reason": "no reviews completed"},
            "json_parse_failures": parse_failures,
        }
    
    logger.info(f"📊 Reviews collected from: {list(reviews.keys())}")
    
    # v5.4: Judge consolidates all reviews and proposes final corrections
    judge_synthesis = None
    revised_document = None
    
    if len(reviews) >= 2:
        logger.info("⚖️ Juiz consolidando revisões do comitê...")
        
        reviews_text = "\n\n".join([
            f"### Revisão do {agent}:\n{response[:2000]}"
            for agent, response in reviews.items()
        ])
        
        judge_consolidation_prompt = f"""
# ROLE
Você é o Juiz Final do comitê de revisão, responsável pela decisão consolidada.

# TASK
Sintetize as revisões de GPT, Claude e outros agentes e proponha correções finais.

# CONTEXT
## Documento Original
{doc_excerpt[:300000]}

## Revisões dos Agentes
{reviews_text}

# RULES
1. SINTETIZE pontos fortes e fracos identificados
2. IDENTIFIQUE consensos e divergências entre revisões
3. PROPONHA correções específicas para problemas críticos
4. GERE versão revisada SE houver correções materiais

# OUTPUT FORMAT
Responda APENAS em JSON válido:
```json
{{
    "sintese_criticas": "resumo dos principais pontos",
    "consensos": ["pontos em que todos concordam"],
    "divergencias": ["pontos de discordância"],
    "correcoes_propostas": [
        {{"trecho_original": "...", "trecho_corrigido": "...", "justificativa": "..."}}
    ],
    "documento_revisado": "documento completo revisado (ou null)",
    "nota_consolidada": 8.5,
    "recomendacao": "aprovar|revisar_humano|rejeitar"
}}
```
"""
        try:
            with billing_context(node="final_committee_consolidation", size="S"):
                judge_response = await _call_model_any_async(
                    judge_model,
                    judge_consolidation_prompt,
                    temperature=0.2,
                    max_tokens=1500
                )
            if judge_response:
                judge_synthesis = judge_response
                logger.info("✅ Juiz concluiu consolidação")
                
                judge_data = extract_json_strict(judge_response, expect="object")
                if isinstance(judge_data, dict):
                    if judge_data.get("documento_revisado"):
                        revised_document = judge_data["documento_revisado"]
                        logger.info("📝 Documento revisado pelo Juiz disponível")
                else:
                    parse_failures.append({
                        "node": "final_committee_judge_consolidation",
                        "model": judge_model,
                        "reason": "parse_failed",
                        "sample": judge_response[:800],
                    })
                    
        except Exception as e:
            logger.warning(f"⚠️ Judge consolidation failed: {e}")

    
    # Parse scores and synthesize
    import json
    all_scores = []
    all_problems = []
    scores_by_agent: Dict[str, float] = {}

    def _coerce_score(value: Any) -> Optional[float]:
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            match = re.search(r"\d+(?:[.,]\d+)?", value)
            if match:
                try:
                    return float(match.group(0).replace(",", "."))
                except ValueError:
                    return None
        return None
    
    for agent, response in reviews.items():
        data = extract_json_strict(response, expect="object")
        if isinstance(data, dict):
            score = _coerce_score(data.get("nota_final"))
            if score is not None:
                all_scores.append(score)
                scores_by_agent[agent] = score
            if "problemas" in data and isinstance(data["problemas"], list):
                all_problems.extend(data["problemas"])
        else:
            parse_failures.append({
                "node": "final_committee_review_parse",
                "model": agent,
                "reason": "parse_failed",
                "sample": response[:800],
            })
            # Try regex fallback for score
            score_match = re.search(r"nota[_\s]?final[:\s]*(\d+(?:[.,]\d+)?)", response, re.IGNORECASE)
            if score_match:
                score = _coerce_score(score_match.group(1))
                if score is not None:
                    all_scores.append(score)
                    scores_by_agent[agent] = score
    
    # Calculate average score
    avg_score = sum(all_scores) / len(all_scores) if all_scores else 5.0
    requires_hil = avg_score < 7.0
    score_spread = 0.0
    if len(scores_by_agent) >= 2:
        score_spread = max(scores_by_agent.values()) - min(scores_by_agent.values())
    score_disagreement = score_spread > 3.0
    
    # Build committee report
    committee_report = {
        "status": "completed",
        "agents_participated": list(reviews.keys()),
        "individual_reviews": reviews,
        "score": round(avg_score, 1),
        "score_by_agent": scores_by_agent,
        "score_spread": round(score_spread, 1),
        "score_disagreement": score_disagreement,
        "requires_hil": requires_hil,
        "critical_problems": list(set(all_problems))[:5],
        "judge_synthesis": judge_synthesis,  # v5.4: Consolidated by Judge
        "revised_document": revised_document,  # v5.4: Document revised by Judge (if any)
        "markdown": f"""## Relatório do Comitê Final

**Agentes Participantes**: {", ".join(reviews.keys())}
**Nota Média**: {avg_score:.1f}/10
**Divergência entre agentes**: {"Sim" if score_disagreement else "Não"} (Δ {score_spread:.1f})
**Revisão Humana Obrigatória**: {"Sim" if requires_hil else "Não"}
**Consolidação pelo Juiz**: {"Sim" if judge_synthesis else "Não"}
**Documento Revisado Disponível**: {"Sim" if revised_document else "Não"}

### Problemas Identificados
{chr(10).join(f"- {p}" for p in all_problems[:5]) if all_problems else "Nenhum problema crítico identificado."}
"""
    }
    
    logger.info(f"✅ Committee Review Score: {avg_score:.1f}/10 (HIL: {requires_hil}, Judge: {bool(judge_synthesis)})")
    
    # If judge produced a revised document, update full_document for finalize node
    base_document = resolve_full_document(state)
    updated_full_document = revised_document or base_document

    updated_state = {
        **state,
        "committee_review_report": committee_report,
        "quality_gate_force_hil": (
            requires_hil
            or score_disagreement
            or state.get("quality_gate_force_hil", False)
        ),
        "json_parse_failures": parse_failures,
    }
    return store_full_document_state(updated_state, updated_full_document)


async def refine_document_node(state: DocumentState) -> DocumentState:
    """
    ♻️ Refine document based on committee review feedback (full-auto).
    """
    logger.info("♻️ [Refine] Applying committee feedback...")

    report = state.get("committee_review_report") or {}
    full_document = resolve_full_document(state)
    if not full_document:
        return {**state, "refinement_round": state.get("refinement_round", 0) + 1}

    issues = report.get("critical_problems") or []
    synthesis = report.get("judge_synthesis") or ""
    score = report.get("score")

    # v5.7: Improved prompt structure
    try:
        from app.services.ai.prompt_constants import ROLE_REVIEWER, LEGAL_WRITING_RULES
    except ImportError:
        ROLE_REVIEWER = "Você é um revisor jurídico sênior."
        LEGAL_WRITING_RULES = "Use linguagem formal."

    prompt = f"""
# ROLE
{ROLE_REVIEWER}

# TASK
Melhore o documento abaixo com base nas críticas do comitê de revisão.

# CONTEXT
## Nota Atual: {score}/10

## Problemas Críticos
{chr(10).join(f"- {p}" for p in issues) if issues else "- (não informado)"}

## Síntese do Juiz
{synthesis or "(sem síntese)"}

## Documento Atual
{full_document[:300000]}

# RULES
{LEGAL_WRITING_RULES}
1. Preserve fatos e citações com [TIPO - Doc. X, p. Y]
2. NÃO invente documentos ou fatos
3. Se precisar de prova não presente no SEI, use [[PENDENTE: ...]]
4. Retorne o documento COMPLETO revisado

# OUTPUT FORMAT
Retorne o documento completo revisado, mantendo toda a estrutura original.
""".strip()

    updated_document = full_document
    try:
        from app.services.ai.gemini_drafter import GeminiDrafterWrapper
        drafter = GeminiDrafterWrapper()
        with billing_context(node="style_refine_node", size="L"):
            resp = await asyncio.to_thread(drafter._generate_with_retry, prompt)
        if resp and resp.text:
            updated_document = resp.text
    except Exception as e:
        logger.warning(f"⚠️ Refine document failed: {e}")

    updated_state = {
        **state,
        "refinement_round": state.get("refinement_round", 0) + 1
    }
    return store_full_document_state(updated_state, updated_document)


def _parse_style_report(raw: str) -> Dict[str, Any]:
    return extract_json_strict(raw or "", expect="object") or {}


def _normalize_style_report(report: Dict[str, Any]) -> Dict[str, Any]:
    score = report.get("score")
    try:
        score_val = float(score) if score is not None else None
    except Exception:
        score_val = None
    tone = str(report.get("tone") or report.get("tone_detected") or "indefinido").strip()
    thermometer = str(report.get("thermometer") or "").strip()
    issues_raw = report.get("issues") or []
    if isinstance(issues_raw, str):
        issues = [issues_raw.strip()] if issues_raw.strip() else []
    elif isinstance(issues_raw, list):
        issues = [str(i).strip() for i in issues_raw if str(i).strip()]
    else:
        issues = []
    term_variations_raw = report.get("term_variations") or report.get("terms_out_of_standard") or []
    term_variations: List[Dict[str, Any]] = []
    if isinstance(term_variations_raw, list):
        for item in term_variations_raw:
            if isinstance(item, dict):
                term_variations.append({
                    "term": str(item.get("term") or item.get("variant") or "").strip(),
                    "preferred": str(item.get("preferred") or item.get("canonical") or "").strip(),
                    "count": item.get("count"),
                    "note": str(item.get("note") or "").strip()
                })
            elif isinstance(item, str) and item.strip():
                term_variations.append({"term": item.strip()})
    recommended_action = str(report.get("recommended_action") or report.get("action") or "").strip()
    return {
        "score": score_val,
        "tone": tone,
        "thermometer": thermometer,
        "issues": issues,
        "term_variations": term_variations,
        "recommended_action": recommended_action
    }


async def style_check_node(state: DocumentState) -> DocumentState:
    """
    🎨 Style Check: avalia tom e consistência editorial antes do gate documental.
    """
    state = _apply_budget_soft_caps(state, node="style_check")
    logger.info("🎨 [Style Check] Avaliando estilo editorial...")
    parse_failures = list(state.get("json_parse_failures") or [])
    full_document = resolve_full_document(state)
    if not full_document:
        return {
            **state,
            "style_report": None,
            "style_score": None,
            "style_tone": None,
            "style_issues": [],
            "style_term_variations": [],
            "style_check_status": "skipped",
            "style_check_payload": None,
            "json_parse_failures": parse_failures,
        }

    excerpt = full_document[:300000]
    if len(full_document) > 350000:
        excerpt = f"{full_document[:200000]}\n...\n{full_document[-100000:]}"

    # v5.7: Improved prompt structure
    try:
        from app.services.ai.prompt_constants import ROLE_STYLE_EDITOR, OUTPUT_FORMAT_JSON
    except ImportError:
        ROLE_STYLE_EDITOR = "Você é um revisor de estilo jurídico."
        OUTPUT_FORMAT_JSON = "Retorne JSON válido."

    prompt = f"""
# ROLE
{ROLE_STYLE_EDITOR}

# TASK
Avalie APENAS o estilo do documento (clareza, formalidade, impessoalidade e consistência terminológica).
NÃO avalie mérito jurídico nem fatos.

# CONTEXT
## Documento (amostra)
{excerpt}

# RULES
1. Avalie clareza e objetividade
2. Verifique formalidade e impessoalidade
3. Identifique inconsistências terminológicas
4. Liste até 5 problemas de estilo
5. NÃO avalie conteúdo jurídico

# OUTPUT FORMAT
Responda APENAS em JSON válido (sem markdown):
{{
  "score": 0-10,
  "tone": "formal/defensivo|agressivo|neutro|...",
  "thermometer": "Muito brando|Equilibrado|Agressivo",
  "issues": ["problema 1", "problema 2"],
  "term_variations": [{{"term": "...", "preferred": "...", "count": N, "note": "..."}}],
  "recommended_action": "instrução curta para ajuste"
}}
""".strip()

    # Use configurable style_check_model (defaults to claude_model or claude-4.5-opus)
    style_check_model = state.get("style_check_model") or state.get("claude_model") or "claude-4.5-opus"
    with billing_context(node="style_check_node", size="L"):
        raw = await _call_model_any_async(
            style_check_model,
            prompt,
            temperature=0.1,
            max_tokens=800
        )
    report = _normalize_style_report(_parse_style_report(raw))
    if not report and raw:
        parse_failures.append({
            "node": "style_check",
            "model": style_check_model,
            "reason": "parse_failed",
            "sample": raw[:800],
        })
        retry_prompt = f"{prompt}\n\nRESPONDA APENAS COM JSON VÁLIDO. NÃO INCLUA TEXTO EXTRA."
        with billing_context(node="style_check_node_retry", size="L"):
            raw_retry = await _call_model_any_async(
                style_check_model,
                retry_prompt,
                temperature=0.1,
                max_tokens=800
            )
        report = _normalize_style_report(_parse_style_report(raw_retry))
        if not report and raw_retry:
            parse_failures.append({
                "node": "style_check",
                "model": style_check_model,
                "reason": "parse_failed_retry",
                "sample": raw_retry[:800],
            })
    score_val = report.get("score")
    min_score = float(state.get("style_min_score") or 8.0)

    style_payload = {
        "type": "style_review",
        "checkpoint": "style_check",
        "message": "Revise o tom editorial antes do gate documental.",
        "tone_detected": report.get("tone"),
        "thermometer": report.get("thermometer"),
        "score": score_val,
        "issues": report.get("issues"),
        "term_variations": report.get("term_variations"),
        "draft_snippet": excerpt[:1200],
    }

    base_state = {
        **state,
        "style_report": report,
        "style_score": score_val,
        "style_tone": report.get("tone"),
        "style_issues": report.get("issues", []),
        "style_term_variations": report.get("term_variations", []),
        "style_check_payload": style_payload,
        "json_parse_failures": parse_failures,
    }

    if state.get("auto_approve_hil", False):
        if score_val is not None and score_val < min_score:
            instruction = report.get("recommended_action") or "Ajuste o tom para ficar mais formal, impessoal e consistente."
            return {
                **base_state,
                "style_check_status": "needs_refine",
                "style_instruction": instruction,
                "style_check_payload": None,
            }
        return {**base_state, "style_check_status": "approved", "style_check_payload": None}

    state["style_check_payload"] = style_payload  # type: ignore[typeddict-item]
    decision = interrupt(style_payload)

    if decision.get("approved"):
        return {**base_state, "style_check_status": "approved", "style_check_payload": None}

    instruction = (decision.get("instructions") or "").strip()
    if not instruction:
        instruction = report.get("recommended_action") or "Ajuste o tom para ficar mais formal, impessoal e consistente."

    return {
        **base_state,
        "style_check_status": "needs_refine",
        "style_instruction": instruction,
        "style_check_payload": None,
        "json_parse_failures": parse_failures,
    }


async def style_refine_node(state: DocumentState) -> DocumentState:
    """
    ✍️ Ajusta o tom/estilo do documento conforme instruções de Style Check.
    """
    state = _apply_budget_soft_caps(state, node="style_refine")
    instruction = (state.get("style_instruction") or "").strip()
    full_document = resolve_full_document(state)
    if not full_document or not instruction:
        return {**state, "style_check_status": "approved", "style_instruction": None}

    logger.info("✍️ [Style Refine] Ajustando tom editorial...")
    issues = state.get("style_issues") or []
    tone = state.get("style_tone") or ""

    # v5.7: Improved prompt structure
    try:
        from app.services.ai.prompt_constants import ROLE_STYLE_EDITOR, LEGAL_WRITING_RULES
    except ImportError:
        ROLE_STYLE_EDITOR = "Você é um editor de estilo jurídico."
        LEGAL_WRITING_RULES = "Use linguagem formal."

    prompt = f"""
# ROLE
{ROLE_STYLE_EDITOR}

# TASK
Ajuste APENAS o estilo e o tom do documento, sem alterar o conteúdo jurídico.

# CONTEXT
## Instruções de Tom
{instruction}

## Achados de Estilo
{chr(10).join(f"- {i}" for i in issues) if issues else "- (sem achados)"}

## Tom Detectado
{tone or "(não informado)"}

## Documento Atual
{full_document[:300000]}

# RULES
{LEGAL_WRITING_RULES}
1. Preserve fatos, estrutura e citações [TIPO - Doc. X, p. Y]
2. NÃO invente documentos nem fatos
3. Ajuste apenas estilo, tom e clareza

# OUTPUT FORMAT
Retorne o documento COMPLETO com estilo ajustado.
""".strip()

    updated_document = full_document
    try:
        from app.services.ai.gemini_drafter import GeminiDrafterWrapper
        drafter = GeminiDrafterWrapper()
        resp = await asyncio.to_thread(drafter._generate_with_retry, prompt)
        if resp and resp.text:
            updated_document = resp.text
    except Exception as e:
        logger.warning(f"⚠️ Style refine failed: {e}")

    rounds = int(state.get("style_refine_round", 0) or 0)
    updated_state = {
        **state,
        "style_instruction": None,
        "style_check_status": "refined",
        "style_refine_round": rounds + 1
    }
    return store_full_document_state(updated_state, updated_document)


async def document_gate_node(state: DocumentState) -> DocumentState:
    """
    🛑 Gate documental: bloqueia sem documentos críticos, permite HIL em faltas não críticas.
    
    v5.5: Uses severity typing:
    - BLOCKED_CRITICAL: Cannot proceed even with HIL
    - BLOCKED_OPTIONAL_HIL: Can proceed with explicit human approval
    - passed: All checks passed
    """
    checklist = state.get("document_checklist") or {}
    full_document = state.get("full_document") or ""
    doc_kind = state.get("doc_kind")
    doc_subtype = state.get("doc_subtype") or state.get("mode")

    # Merge structured checklist (catalog) into document_checklist
    try:
        from app.services.ai.nodes.catalogo_documentos import (
            infer_doc_kind_subtype,
            get_template,
            evaluate_structured_checklist,
        )
        if not doc_kind and doc_subtype:
            doc_kind, _ = infer_doc_kind_subtype(doc_subtype)
        spec = get_template(doc_kind, doc_subtype) if doc_kind and doc_subtype else None
        if spec and spec.checklist_base:
            structured = evaluate_structured_checklist(full_document, spec.checklist_base)
            existing_items = checklist.get("items") or []
            index = {}
            merged_items = []

            def _norm_key(raw: str) -> str:
                return re.sub(r"[^a-z0-9]+", "_", (raw or "").lower()).strip("_")

            for item in existing_items:
                if not isinstance(item, dict):
                    continue
                key = _norm_key(str(item.get("id") or item.get("label") or ""))
                if not key:
                    continue
                index[key] = item
                merged_items.append(item)

            for item in structured.get("items", []):
                key = _norm_key(str(item.get("id") or item.get("label") or ""))
                if not key or key in index:
                    continue
                merged_items.append(item)

            checklist = {
                **checklist,
                "items": merged_items,
                "missing_critical": (checklist.get("missing_critical") or []) + structured.get("missing_critical", []),
                "missing_noncritical": (checklist.get("missing_noncritical") or []) + structured.get("missing_noncritical", []),
                "summary": checklist.get("summary") or "Checklist estruturado aplicado.",
            }
    except Exception:
        pass
    items = checklist.get("items") or []
    strict_gate = bool(state.get("strict_document_gate", False))

    missing_critical = [i for i in items if i.get("status") != "present" and i.get("critical")]
    missing_noncritical = [i for i in items if i.get("status") != "present" and not i.get("critical")]

    # Strict audit mode: all missing docs block
    if strict_gate and (missing_critical or missing_noncritical):
        missing_all = missing_critical + missing_noncritical
        summary = checklist.get("summary") or "Documentos pendentes (modo auditoria)."
        missing_labels = ", ".join([i.get("label") or i.get("id") for i in missing_all if isinstance(i, dict)]) or "Documentos pendentes"
        
        # Emit blocking event
        job_manager.emit_event(state.get("job_id"), "DOCUMENT_GATE_BLOCKED", {
            "severity": "BLOCKED_CRITICAL",
            "missing": missing_labels,
            "reason": "strict_audit_mode"
        })
        
        return _with_final_decision({
            **state,
            "document_gate_status": "BLOCKED_CRITICAL",
            "document_gate_missing": missing_all,
            "final_markdown": f"⛔ Documento bloqueado.\\n\\n{summary}\\n\\nPendências: {missing_labels}"
        }, "NEED_EVIDENCE")

    # Critical docs missing: hard block
    if missing_critical:
        summary = checklist.get("summary") or "Documentos críticos pendentes."
        missing_labels = ", ".join([i.get("label") or i.get("id") for i in missing_critical if isinstance(i, dict)]) or "Documentos críticos pendentes"
        
        job_manager.emit_event(state.get("job_id"), "DOCUMENT_GATE_BLOCKED", {
            "severity": "BLOCKED_CRITICAL",
            "missing": missing_labels,
            "reason": "critical_docs_missing"
        })
        
        return _with_final_decision({
            **state,
            "document_gate_status": "BLOCKED_CRITICAL",
            "document_gate_missing": missing_critical,
            "final_markdown": f"⛔ Documento bloqueado.\\n\\n{summary}\\n\\nPendências: {missing_labels}"
        }, "NEED_EVIDENCE")

    # Non-critical docs missing: can proceed with HIL
    if missing_noncritical:
        if state.get("auto_approve_hil", False):
            job_manager.emit_event(state.get("job_id"), "DOCUMENT_GATE_OVERRIDE", {
                "severity": "BLOCKED_OPTIONAL_HIL",
                "missing": [i.get("label") for i in missing_noncritical],
                "auto_approved": True
            })
            return _with_final_decision({
                **state,
                "document_gate_status": "passed",  # Auto-approved
                "document_gate_missing": missing_noncritical,
            }, "APPROVED", extra_reasons=["override_noncritical_docs"])

        decision = interrupt({
            "type": "document_gate",
            "checkpoint": "document_gate",
            "message": "Faltam documentos NÃO críticos. Deseja prosseguir com ressalva?",
            "missing_noncritical": missing_noncritical,
            "summary": checklist.get("summary"),
            "severity": "BLOCKED_OPTIONAL_HIL",
        })

        if decision.get("approved"):
            job_manager.emit_event(state.get("job_id"), "DOCUMENT_GATE_OVERRIDE", {
                "severity": "BLOCKED_OPTIONAL_HIL",
                "missing": [i.get("label") for i in missing_noncritical],
                "human_approved": True
            })
            return _with_final_decision({
                **state,
                "document_gate_status": "passed",  # Human approved
                "document_gate_missing": missing_noncritical,
            }, "APPROVED", extra_reasons=["override_noncritical_docs"])

        return _with_final_decision({
            **state,
            "document_gate_status": "BLOCKED_OPTIONAL_HIL",
            "document_gate_missing": missing_noncritical,
            "final_markdown": "⛔ Documento bloqueado por decisão humana."
        }, "NEED_EVIDENCE", extra_reasons=["blocked_by_human"])

    citations_map = state.get("citations_map") or {}
    full_document = resolve_full_document(state)
    updated_state = {
        **state,
        "document_gate_status": "passed",
        "document_gate_missing": [],
    }
    final_doc = append_sources_section(full_document, citations_map)
    if final_doc != full_document:
        return store_full_document_state(updated_state, final_doc)
    return updated_state


async def human_proposal_debate_node(state: DocumentState) -> DocumentState:
    """
    v5.4: Debate node for evaluating human proposals.
    
    When user rejects with a proposal (section or final), the committee
    evaluates it and the Judge model decides whether to accept, merge, or reject.
    """
    logger.info("💬 [Phase3] Human Proposal Debate Starting...")
    parse_failures = list(state.get("json_parse_failures") or [])
    
    proposal = state.get("human_proposal", "")
    scope = state.get("proposal_scope", "final")
    target_section = state.get("proposal_target_section")
    
    if not proposal:
        logger.warning("⚠️ No proposal found, skipping debate")
        return {**state, "proposal_evaluation": {"status": "skipped", "reason": "no_proposal"}}
    
    # Get current document or section
    if scope == "section" and target_section:
        # Find the target section content
        sections = state.get("processed_sections", [])
        current_content = ""
        section_idx = -1
        for i, sec in enumerate(sections):
            if sec.get("section_title") == target_section:
                current_content = sec.get("merged_content", "")
                section_idx = i
                break
        if not current_content:
            current_content = f"[Seção '{target_section}' não encontrada]"
    else:
        current_content = resolve_full_document(state)[:8000]
    
    # Initialize clients
    from app.services.ai.agent_clients import (
        init_openai_client, init_anthropic_client,
        call_openai_async, call_anthropic_async
    )
    from app.services.ai.model_registry import DEFAULT_JUDGE_MODEL
    
    gpt_client = init_openai_client()
    claude_client = init_anthropic_client()
    judge_model = state.get("judge_model") or DEFAULT_JUDGE_MODEL
    
    evaluation_prompt = f"""
# ROLE
Você é um avaliador do comitê, responsável por analisar propostas do usuário.

# TASK
Avalie a proposta do usuário comparando com a versão atual.

# CONTEXT
## Versão Atual {'(Seção: ' + target_section + ')' if scope == 'section' else '(Documento)'}
{current_content[:3000]}

## Proposta do Usuário
{proposal[:3000]}

# RULES
1. Compare a proposta com a versão atual
2. Avalie se a proposta:
   - Resolve problemas existentes
   - Mantém coerência jurídica
   - Está bem fundamentada
3. Seja objetivo e imparcial

# OUTPUT FORMAT
Responda APENAS em JSON válido:
```json
{{
    "nota": 0-10,
    "analise": "A proposta do usuário...",
    "pontos_fortes": ["..."],
    "pontos_fracos": ["..."],
    "recomendacao": "aceitar|merge|rejeitar"
}}
```
"""
    
    evaluations = {}
    
    # Parallel evaluation by GPT and Claude
    async def eval_gpt():
        try:
            resp = await call_openai_async(gpt_client, evaluation_prompt)
            return {"agent": "GPT", "response": resp}
        except Exception as e:
            return {"agent": "GPT", "response": None, "error": str(e)}
    
    async def eval_claude():
        try:
            resp = await call_anthropic_async(claude_client, evaluation_prompt)
            return {"agent": "Claude", "response": resp}
        except Exception as e:
            return {"agent": "Claude", "response": None, "error": str(e)}
    
    results = await asyncio.gather(eval_gpt(), eval_claude(), return_exceptions=True)
    
    for r in results:
        if r and not isinstance(r, Exception) and r.get("response"):
            evaluations[r["agent"]] = r["response"]
    
    logger.info(f"📊 Proposal evaluations from: {list(evaluations.keys())}")
    
    # Judge consolidates and decides
    judge_prompt = f"""
# ROLE
Você é o Juiz Final, responsável pela decisão definitiva sobre propostas do usuário.

# TASK
Decida o destino da proposta do usuário com base nas avaliações dos agentes.

# CONTEXT
## Proposta do Usuário
{proposal[:2000]}

## Versão Atual
{current_content[:2000]}

## Avaliações dos Agentes
{chr(10).join([f"**{a}**: {r[:1000]}" for a, r in evaluations.items()])}

# RULES
Opções de decisão:
1. **ACEITAR**: A proposta substitui completamente a versão atual
2. **MERGE**: Combine os melhores elementos de ambas
3. **REJEITAR**: Mantém a versão atual, explicando os problemas

# OUTPUT FORMAT
Responda APENAS em JSON válido:
```json
{{
    "decisao": "aceitar|merge|rejeitar",
    "justificativa": "...",
    "texto_final": "..." // O texto resultante (proposta, merge, ou original)
}}
```
"""
    
    judge_response = await _call_model_any_async(
        judge_model,
        judge_prompt,
        temperature=0.2,
        max_tokens=1200
    )
    
    # Parse judge decision
    decision = "rejeitar"
    final_text = current_content
    justification = ""
    
    if judge_response:
        judge_data = extract_json_strict(judge_response, expect="object")
        if isinstance(judge_data, dict):
            decision = judge_data.get("decisao", "rejeitar")
            justification = judge_data.get("justificativa", "")
            if judge_data.get("texto_final"):
                final_text = judge_data["texto_final"]
        else:
            parse_failures.append({
                "node": "proposal_debate_judge",
                "model": judge_model,
                "reason": "parse_failed",
                "sample": judge_response[:800],
            })
            logger.warning("⚠️ Failed to parse judge decision, defaulting to reject")
    
    logger.info(f"⚖️ Judge decision: {decision}")
    
    # Build evaluation report
    evaluation_report = {
        "status": "completed",
        "scope": scope,
        "target_section": target_section,
        "agent_evaluations": evaluations,
        "judge_decision": decision,
        "judge_justification": justification,
        "accepted": decision in ["aceitar", "merge"]
    }
    
    # Update document or section based on decision
    updated_state = {
        **state,
        "proposal_evaluation": evaluation_report,
        "human_proposal": None,  # Clear proposal after processing
        "json_parse_failures": parse_failures,
    }
    
    if decision in ["aceitar", "merge"]:
        if scope == "section" and target_section and section_idx >= 0:
            # Update specific section
            sections = list(state.get("processed_sections", []))
            if 0 <= section_idx < len(sections):
                sections[section_idx]["merged_content"] = final_text
                sections[section_idx]["human_revised"] = True
            updated_state["processed_sections"] = sections
            logger.info(f"✅ Section '{target_section}' updated with proposal")
        else:
            # Update full document
            logger.info("✅ Full document updated with proposal")
            return store_full_document_state(updated_state, final_text)
    else:
        logger.info("❌ Proposal rejected, keeping original")
    
    return updated_state


async def finalize_hil_node(state: DocumentState) -> DocumentState:
    """HIL Checkpoint: Final approval"""
    logger.info("🛑 [Phase2] HIL: Final Approval")
    full_document = resolve_full_document(state)
    citations_map = state.get("citations_map") or {}

    # v5.3: Cleanup context cache if it was created
    job_id = state.get("job_id", "")
    if state.get("context_cache_created") and job_id:
        from app.services.ai.agent_clients import cleanup_job_cache
        cleanup_job_cache(job_id)

    force_hil = bool(state.get("quality_gate_force_hil", False))
    force_final_hil = bool(state.get("force_final_hil", False))

    if not force_final_hil and not force_hil:
        final_md = append_sources_section(full_document, citations_map)
        return _with_final_decision({
            **state,
            "human_approved_final": True,
            "final_markdown": final_md
        }, "APPROVED", extra_reasons=["final_hil_disabled"])

    if state.get("auto_approve_hil", False) and (force_final_hil or force_hil):
        logger.warning(
            "⚠️ HIL final solicitado (force_final_hil=%s, force_hil=%s), mas auto_approve_hil está ativo. Prosseguindo sem interrupção.",
            force_final_hil,
            force_hil,
        )
        decision = "NEED_EVIDENCE" if force_hil else "APPROVED"
        final_doc = full_document
        if decision == "NEED_EVIDENCE":
            final_doc = prepend_need_evidence_notice(state, final_doc)
        final_md = append_sources_section(final_doc, citations_map)
        return _with_final_decision(
            {
                **state,
                "human_approved_final": True,
                "final_markdown": final_md,
            },
            decision,
            extra_reasons=["auto_approve_hil"],
        )
    
    decision, state, skipped = _try_hil_interrupt(
        state,
        "final",
        {
            "type": "final_approval",
            "checkpoint": "final",
            "message": "Documento pronto. Aprove para gerar versão final.",
            "document": full_document,
            "audit_status": state.get("audit_status"),
            "audit_report": state.get("audit_report"),
            "committee_review_report": state.get("committee_review_report"),
        },
    )
    if skipped:
        final_md = append_sources_section(full_document, citations_map)
        return _with_final_decision(
            {**state, "human_approved_final": True, "final_markdown": final_md},
            "APPROVED",
            extra_reasons=["hil_budget_exhausted"],
        )
    
    if decision.get("approved"):
        final_md = append_sources_section(decision.get("edits") or full_document, citations_map)
        return _with_final_decision(
            {**state, "human_approved_final": True, "final_markdown": final_md},
            "APPROVED"
        )
    
    # v5.4: Check if user provided a proposal for committee debate
    user_proposal = decision.get("proposal")
    if user_proposal:
        logger.info("📝 User provided proposal, routing to committee debate")
        return _with_final_decision({
            **state, 
            "human_approved_final": False, 
            "human_edits": decision.get("instructions"),
            "human_proposal": user_proposal,
            "proposal_scope": "final",
            "proposal_target_section": None
        }, "NEED_HUMAN_REVIEW", extra_reasons=["proposal_submitted"])

    return _with_final_decision(
        {**state, "human_approved_final": False, "human_edits": decision.get("instructions")},
        "NEED_HUMAN_REVIEW",
        extra_reasons=["final_rejected"]
    )


# --- GRAPH DEFINITION ---

workflow = StateGraph(DocumentState)

# Nodes (renamed to avoid conflict with state keys)
workflow.add_node("gen_outline", _wrap_node("gen_outline", outline_node))
workflow.add_node("outline_hil", _wrap_node("outline_hil", outline_hil_node))
workflow.add_node("planner", _wrap_node("planner", planner_node))
workflow.add_node("deep_research", _wrap_node("deep_research", deep_research_node))
workflow.add_node("web_search", _wrap_node("web_search", web_search_node))
workflow.add_node("research_notes_step", _wrap_node("research_notes_step", research_notes_node))
workflow.add_node("research_verify", _wrap_node("research_verify", research_verify_node))
workflow.add_node("fact_check", _wrap_node("fact_check", fact_check_sei_node))

# B2 Citer/Verifier (Pre-Debate Gate)
workflow.add_node("citer_verifier", _wrap_node("citer_verifier", citer_verifier_node))
logger.info("🔍 Graph: Citer/Verifier node registered (pre-debate gate)")

# Register debate node (mixed granular per section)
workflow.add_node("debate", _wrap_node("debate", debate_all_sections_node))
logger.info("📊 Graph: Using MIXED debate node (granular per section)")

workflow.add_node("divergence_hil", _wrap_node("divergence_hil", divergence_hil_node))
workflow.add_node("section_hil", _wrap_node("section_hil", section_hil_node))

# Quality Pipeline nodes (v2.25)
workflow.add_node("quality_gate", _wrap_node("quality_gate", quality_gate_node))
workflow.add_node("structural_fix", _wrap_node("structural_fix", structural_fix_node))
workflow.add_node("targeted_patch", _wrap_node("targeted_patch", targeted_patch_node))
workflow.add_node("gen_quality_report", _wrap_node("gen_quality_report", quality_report_node))

workflow.add_node("audit", _wrap_node("audit", audit_node))
workflow.add_node("evaluate_hil", _wrap_node("evaluate_hil", evaluate_hil_node))  # Universal HIL Decision
workflow.add_node("propose_corrections", _wrap_node("propose_corrections", propose_corrections_node))
workflow.add_node("correction_hil", _wrap_node("correction_hil", correction_hil_node))
workflow.add_node("final_committee_review", _wrap_node("final_committee_review", final_committee_review_node))  # v5.2: Holistic review
workflow.add_node("refine_document", _wrap_node("refine_document", refine_document_node))
workflow.add_node("style_check", _wrap_node("style_check", style_check_node))
workflow.add_node("style_refine", _wrap_node("style_refine", style_refine_node))
workflow.add_node("document_gate", _wrap_node("document_gate", document_gate_node))
workflow.add_node("finalize_hil", _wrap_node("finalize_hil", finalize_hil_node))

# Entry
workflow.set_entry_point("gen_outline")

# Always go through outline_hil (no-op if not enabled)
workflow.add_edge("gen_outline", "outline_hil")

# Routing after outline approval
def research_router(state: DocumentState) -> Literal["deep_research", "web_search", "fact_check"]:
    if (state.get("audit_mode") or "").lower() == "sei_only":
        return "fact_check"
    # Prefer web search first for lower latency; deep research only on retry if needed.
    if state.get("web_search_enabled"):
        return "web_search"
    if state.get("deep_research_enabled"):
        return "deep_research"
    return "fact_check"


def research_retry_router(state: DocumentState) -> Literal["deep_research", "web_search", "quality_gate"]:
    if state.get("web_search_insufficient") and state.get("deep_research_enabled"):
        return "deep_research"
    if not state.get("verification_retry"):
        return "quality_gate"
    if state.get("deep_research_enabled"):
        return "deep_research"
    if state.get("web_search_enabled"):
        return "web_search"
    return "quality_gate"

# Planner Flow: outline_hil -> planner -> router
workflow.add_edge("outline_hil", "planner")
workflow.add_conditional_edges("planner", research_router)

# If both are enabled, Web Search runs first. Deep Research is only invoked
# on verification retry when web results are insufficient.
workflow.add_edge("deep_research", "research_notes_step")
workflow.add_edge("web_search", "research_notes_step")
workflow.add_edge("research_notes_step", "fact_check")

# B2 Citer/Verifier: fact_check → citer_verifier → debate
workflow.add_edge("fact_check", "citer_verifier")


def citer_verifier_router(state: DocumentState) -> Literal["debate", "__end__"]:
    """
    Route based on citer_verifier result.
    If block_debate=True:
    - auto_approve_hil=True: proceed (no pauses) but keep NEED_EVIDENCE flags in state.
    - otherwise: end early with a diagnostic report (avoid spending on low-signal draft).
    """
    result = state.get("citer_verifier_result") or {}
    if result.get("block_debate") and not state.get("auto_approve_hil", False):
        logger.warning("⚠️ Citer/Verifier: Bloqueando debate (rastreabilidade insuficiente)")
        return "__end__"
    return "debate"


workflow.add_conditional_edges("citer_verifier", citer_verifier_router, {
    "debate": "debate",
    "__end__": END,
})

# Main flow with Quality Pipeline (v2.25)
# debate → quality_gate → structural_fix → divergence_hil → section_hil → audit → targeted_patch → quality_report → evaluate_hil
workflow.add_edge("debate", "research_verify")
workflow.add_conditional_edges("research_verify", research_retry_router)
workflow.add_edge("quality_gate", "structural_fix")
workflow.add_edge("structural_fix", "divergence_hil")

def divergence_router(state: DocumentState) -> Literal["section_hil", "__end__"]:
    if state.get("human_approved_divergence"):
        return "section_hil"
    rounds = int(state.get("divergence_hil_round", 0) or 0)
    max_rounds = int(state.get("max_divergence_hil_rounds", 2) or 2)
    if rounds < max_rounds:
        return "section_hil"
    return "__end__"

workflow.add_conditional_edges("divergence_hil", divergence_router, {
    "section_hil": "section_hil",
    "__end__": END,
})
workflow.add_edge("section_hil", "audit")
workflow.add_edge("audit", "targeted_patch")
workflow.add_edge("targeted_patch", "gen_quality_report")
workflow.add_edge("gen_quality_report", "evaluate_hil")  # Evaluate HIL checklist after quality pipeline

# Universal HIL Router: Uses hil_checklist to decide flow
def hil_router(state: DocumentState) -> Literal["propose_corrections", "final_committee_review"]:
    """
    Universal HIL Router based on 10-factor checklist.
    
    Routes to:
    - propose_corrections: If audit found issues that need correction
    - final_committee_review: If no issues (goes to committee before final)
    """
    hil_checklist = state.get("hil_checklist", {})
    audit_issues = state.get("audit_issues", [])
    
    # If audit found correctable issues, go to correction flow
    if audit_issues or state.get("audit_status") == "reprovado":
        return "propose_corrections"
    
    # Otherwise go to committee review before final
    return "final_committee_review"

workflow.add_conditional_edges("evaluate_hil", hil_router)
workflow.add_edge("propose_corrections", "correction_hil")
workflow.add_edge("correction_hil", "final_committee_review")  # v5.2: Committee review after corrections

def final_refine_router(state: DocumentState) -> Literal["refine_document", "style_check"]:
    rounds = int(state.get("refinement_round", 0) or 0)
    max_rounds = _resolve_cap_value(state.get("max_final_review_loops"), default=None)
    if max_rounds is None:
        max_rounds = int(state.get("max_rounds", 0) or 0)

    if max_rounds and rounds < max_rounds:
        return "refine_document"
    return "style_check"

def document_gate_router(state: DocumentState) -> Literal["finalize_hil", "__end__"]:
    status = state.get("document_gate_status")
    # v5.5: BLOCKED_CRITICAL always ends, BLOCKED_OPTIONAL_HIL also ends (user rejected)
    if status in ("BLOCKED_CRITICAL", "BLOCKED_OPTIONAL_HIL"):
        return "__end__"
    return "finalize_hil"

def style_check_router(state: DocumentState) -> Literal["style_refine", "document_gate"]:
    status = state.get("style_check_status")
    if status == "needs_refine":
        score = state.get("style_score")
        try:
            min_score = float(state.get("style_min_score") or 8.0)
        except Exception:
            min_score = 8.0
        if isinstance(score, (int, float)) and score >= min_score:
            return "document_gate"
        rounds = int(state.get("style_refine_round", 0) or 0)
        max_rounds = int(state.get("style_refine_max_rounds", 2) or 2)
        if max_rounds and rounds >= max_rounds:
            logger.warning("⚠️ Style refine max rounds reached; proceeding to document gate.")
            
            # v5.5: Emit degradation event for observability
            job_manager.emit_event(state.get("job_id"), "STYLE_DEGRADED_DUE_TO_BUDGET", {
                "style_score": state.get("style_score"),
                "target_score": state.get("style_min_score"),
                "rounds_used": rounds,
                "max_rounds": max_rounds,
                "style_issues": state.get("style_issues", [])[:5],  # First 5 issues
                "reason": "max_rounds_exhausted"
            })
            
            return "document_gate"
        return "style_refine"
    return "document_gate"

workflow.add_conditional_edges("final_committee_review", final_refine_router, {
    "refine_document": "refine_document",
    "style_check": "style_check",
})
workflow.add_edge("refine_document", "final_committee_review")
workflow.add_conditional_edges("style_check", style_check_router, {
    "style_refine": "style_refine",
    "document_gate": "document_gate",
})
workflow.add_edge("style_refine", "style_check")
workflow.add_conditional_edges("document_gate", document_gate_router, {
    "__end__": END,
    "finalize_hil": "finalize_hil",
})

# v5.4: Human Proposal Debate node and routing
workflow.add_node("proposal_debate", _wrap_node("proposal_debate", human_proposal_debate_node))

def finalize_hil_router(state: DocumentState) -> Literal["proposal_debate", "__end__"]:
    """Route based on whether user provided a proposal."""
    if state.get("human_proposal"):
        return "proposal_debate"
    if state.get("human_approved_final"):
        return "__end__"
    # If rejected without proposal, still end (user can restart)
    return "__end__"

workflow.add_conditional_edges("finalize_hil", finalize_hil_router)
workflow.add_edge("proposal_debate", "finalize_hil")  # Loop back to HIL after proposal debate

# Checkpointer
if SqliteSaver is not None:
    conn = sqlite3.connect(job_manager.db_path, check_same_thread=False)
    checkpointer = SqliteSaver(conn)
    logger.info("✅ LangGraph checkpointer: SqliteSaver")
else:
    checkpointer = MemorySaver()
    logger.warning("⚠️ LangGraph checkpointer: MemorySaver (SqliteSaver indisponível no ambiente)")

legal_workflow_app = workflow.compile(checkpointer=checkpointer)
