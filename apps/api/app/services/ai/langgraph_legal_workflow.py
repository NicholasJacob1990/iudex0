"""
LangGraph Legal Workflow - Phase 4 (Audit Feedback Loop + HIL)

Fluxo:
  outline → [research] → debate → divergence_hil → audit → 
  → [if issues] → propose_corrections → correction_hil →
  → finalize_hil → END

Feature Flag:
  USE_GRANULAR_DEBATE=true  → Uses 8-node sub-graph (R1-R4)
  USE_GRANULAR_DEBATE=false → Uses hybrid node
"""

from typing import TypedDict, Literal, Optional, List, Dict, Any
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
from loguru import logger
import asyncio
import sqlite3
import os
import re
import json

from app.services.web_search_service import web_search_service, build_web_context, is_breadth_first, plan_queries
from app.services.ai.deep_research_service import deep_research_service
from app.services.job_manager import job_manager
from app.services.ai.audit_service import AuditService
from app.services.ai.hil_decision_engine import HILDecisionEngine, HILChecklist, hil_engine
from app.services.ai.model_registry import get_api_model_name, get_model_config, DEFAULT_JUDGE_MODEL, DEFAULT_DEBATE_MODELS

# Quality Pipeline (v2.25)
from app.services.ai.quality_gate import quality_gate_node
from app.services.ai.structural_fix import structural_fix_node
from app.services.ai.targeted_patch import targeted_patch_node
from app.services.ai.quality_report import quality_report_node

# Audit service instance
audit_service = AuditService()

# Feature Flag
USE_GRANULAR_DEBATE = os.getenv("USE_GRANULAR_DEBATE", "false").lower() == "true"

if USE_GRANULAR_DEBATE:
    from app.services.ai.debate_subgraph import run_debate_for_section
    logger.info("🔬 Granular Debate Mode ENABLED (8-node sub-graph)")
else:
    logger.info("🤝 Hybrid Debate Mode ENABLED (calls generate_section_agent_mode_async)")

# Graph RAG Integration (v5.1)
from app.services.rag_module import get_knowledge_graph

# =============================================================================
# RAG ROUTING STRATEGIES (ported from CLI)
# =============================================================================

STRATEGY_LOCAL_ONLY = "LOCAL_ONLY"       # Search only in local process documents
STRATEGY_GLOBAL_SINGLE = "GLOBAL_SINGLE" # Search only in global bases (lei, juris, etc.)
STRATEGY_HYBRID = "HYBRID"               # Search both local and global
STRATEGY_NO_RETRIEVAL = "NO_RETRIEVAL"   # Skip RAG entirely (simple/template sections)
STRATEGY_GRAPH = "GRAPH"                 # Use GraphRAG for multi-hop reasoning


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
        call_vertex_gemini,
        call_vertex_gemini_async,
    )

    if cfg.provider == "openai":
        client = init_openai_client()
        if not client:
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
            return ""
        return await call_openai_async(
            client,
            prompt,
            model=api_model,
            max_tokens=max_tokens,
            temperature=temperature,
            system_instruction=system_instruction
        ) or ""

    logger.warning(f"⚠️ Provider não suportado para judge/strategist: {cfg.provider}")
    return ""

def default_route_for_section(section_title: str, tipo_peca: str = "") -> Dict[str, Any]:
    """
    Heuristic-based router that decides RAG strategy based on section title.
    
    Returns a dict with:
        - strategy: one of STRATEGY_* constants
        - sources: list of RAG sources to query
        - top_k: number of results to fetch
        - graph_hops: (for STRATEGY_GRAPH) depth of relationship traversal
        - reason: explanation for routing decision
    """
    title_lower = section_title.lower()
    
    # Default config
    config = {
        "strategy": STRATEGY_HYBRID,
        "sources": ["lei", "juris", "pecas_modelo"],
        "top_k": 8,
        "graph_hops": 0,
        "reason": "default hybrid"
    }
    
    # 1. GRAPH: Jurisprudência, súmulas, precedentes (multi-hop reasoning)
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
                "graph_hops": 2,
                "reason": f"matched Graph pattern: {pattern}"
            }
    
    # 2. LOCAL_ONLY: Factual sections that require process-specific info
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
                "sources": [],
                "top_k": 5,
                "graph_hops": 0,
                "reason": f"matched local pattern: {pattern}"
            }
    
    # 3. GLOBAL_SINGLE: Simple legal doctrine sections
    global_patterns = [
        r"(do\s+)?direito",
        r"legislação",
        r"mérito",
        r"fundament(o|ação)",
    ]
    for pattern in global_patterns:
        if re.search(pattern, title_lower):
            return {
                "strategy": STRATEGY_GLOBAL_SINGLE,
                "sources": ["lei", "juris"],
                "top_k": 10,
                "graph_hops": 0,
                "reason": f"matched global pattern: {pattern}"
            }
    
    # 4. NO_RETRIEVAL: Procedural/template sections
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
                "graph_hops": 0,
                "reason": f"matched no-rag pattern: {pattern}"
            }
    
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
    if not results:
        return {
            "gate_passed": True,  # Pass-through if no results
            "safe_mode": False,
            "best_score": 0.0,
            "avg_top3": 0.0,
            "reason": "No RAG results, skipping gate"
        }
    
    scores = [r.get('score', r.get('final_score', 0)) for r in results]
    best = max(scores) if scores else 0.0
    top3 = scores[:3]
    avg_top3 = sum(top3) / len(top3) if top3 else 0.0
    
    gate_passed = best >= min_best_score and avg_top3 >= min_avg_top3_score
    
    return {
        "gate_passed": gate_passed,
        "safe_mode": not gate_passed,
        "best_score": best,
        "avg_top3": avg_top3,
        "reason": f"best={best:.2f}, avg_top3={avg_top3:.2f}, thresholds=({min_best_score}, {min_avg_top3_score})"
    }




# --- DOCUMENT STATE ---

class DocumentState(TypedDict):
    # Input
    input_text: str
    mode: str
    tese: str
    job_id: str
    
    # Config
    deep_research_enabled: bool
    web_search_enabled: bool
    search_mode: str
    research_mode: str
    need_juris: bool
    research_policy: str
    planning_reasoning: Optional[str]
    planned_queries: Optional[List[str]]  # Queries auto-generated by planner
    multi_query: bool
    breadth_first: bool
    use_multi_agent: bool
    thinking_level: str
    chat_personality: str
    target_pages: int
    min_pages: int
    max_pages: int
    audit_mode: str
    quality_profile: str
    target_section_score: float
    target_final_score: float
    max_rounds: int
    recursion_limit: int
    refinement_round: int
    strict_document_gate: bool
    hil_section_policy: str
    force_final_hil: bool
    
    # v4.1: CRAG Gate & Adaptive Routing (unified with CLI)
    crag_gate_enabled: bool
    adaptive_routing_enabled: bool
    crag_min_best_score: float  # default 0.45
    crag_min_avg_score: float   # default 0.35
    
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

    # Research Verification
    verifier_attempts: int
    verification_retry: bool
    
    # Sections (processed)
    processed_sections: List[Dict[str, Any]]
    full_document: str
    
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
    document_gate_status: Optional[str]
    document_gate_missing: List[Dict[str, Any]]

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

    report = state.get("committee_review_report") or {}
    score = report.get("score")
    if score is None:
        try:
            score = float(report.get("nota_consolidada"))
        except Exception:
            score = None
    target = state.get("target_final_score")
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


# --- NODES ---

async def outline_node(state: DocumentState) -> DocumentState:
    """Generate document outline"""
    logger.info("📑 [Phase2] Generating Outline...")
    
    mode = state.get("mode", "PETICAO")
    
    # v5.0: Dynamic Outline Generation (Unification with CLI)
    try:
        strategist_model = state.get("strategist_model") or state.get("judge_model") or DEFAULT_JUDGE_MODEL
        min_pages = int(state.get("min_pages") or 0)
        max_pages = int(state.get("max_pages") or 0)
        size_guidance = _outline_size_guidance(min_pages, max_pages)
        prompt = f"""
Você é um estrategista jurídico. Gere o sumário (outline) para um documento do tipo {mode}.

REGRAS:
- Retorne apenas os tópicos do sumário, um por linha.
- Use numeração romana quando fizer sentido (ex.: I, II, III).
- Não inclua explicações, notas ou comentários.

{size_guidance}

RESUMO DO CASO:
{state.get("input_text", "")[:4000]}

TESE/INSTRUÇÕES:
{state.get("tese", "")}
""".strip()

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
        if mode == "PARECER":
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
    state["hil_outline_payload"] = payload  # type: ignore[typeddict-item]

    decision = interrupt({
        "type": "outline_review",
        "checkpoint": "outline",
        "message": "Revise o esqueleto (sumário) antes de iniciar a geração.",
        "outline": outline
    })

    # Keep interrupting until approved
    while not decision.get("approved", False):
        instr = (decision.get("instructions") or "").strip()
        if instr:
            payload["instructions"] = instr
            state["hil_outline_payload"] = payload  # type: ignore[typeddict-item]

        decision = interrupt({
            "type": "outline_review",
            "checkpoint": "outline",
            "message": "Outline rejeitada. Edite/aprove para continuar.",
            "outline": outline,
            **({"instructions": instr} if instr else {})
        })

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


def _contains_keywords(text: str, keywords: List[str]) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in keywords)


async def deep_research_node(state: DocumentState) -> DocumentState:
    """Deep Research based on outline"""
    if not state.get("deep_research_enabled"):
        return state
        
    logger.info("🧠 [Phase2] Deep Research...")
    
    sections_summary = "\n".join([f"- {s}" for s in state.get("outline", [])])
    planned_queries = _normalize_queries(state.get("planned_queries"))
    base_query = f"""
Pesquisa jurídica para {state['mode']}.
TESE: {state['tese']}
CONTEXTO: {state['input_text'][:1500]}
SEÇÕES: {sections_summary}
"""
    query = base_query
    if planned_queries:
        query += "\n\nFOCO DA PESQUISA (Queries Planejadas):\n"
        query += "\n".join([f"- {q}" for q in planned_queries[:6]])
    
    res = await deep_research_service.run_research_task(query)
    
    return {
        **state,
        "research_context": res.text,
        "research_sources": res.sources or [],
        "deep_research_thinking_steps": res.thinking_steps or [],
        "deep_research_from_cache": bool(getattr(res, "from_cache", False)),
    }


async def web_search_node(state: DocumentState) -> DocumentState:
    """Simple web search"""
    if not state.get("web_search_enabled"):
        return state

    search_mode = (state.get("search_mode") or "hybrid").lower()
    if search_mode not in ("shared", "native", "hybrid"):
        search_mode = "hybrid"

    logger.info("🌐 [Phase2] Web Search...")

    base_query = f"{state.get('tese', '')} jurisprudência {state.get('mode', '')}".strip()
    planned_queries = _normalize_queries(state.get("planned_queries"))
    query = planned_queries[0] if planned_queries else base_query
    breadth_first = bool(state.get("breadth_first")) or is_breadth_first(query)
    multi_query = bool(state.get("multi_query", True)) or breadth_first

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
            from app.services.ai.citations import to_perplexity
            from app.services.ai.model_registry import get_api_model_name, get_model_config

            judge_model = state.get("judge_model") or DEFAULT_JUDGE_MODEL
            api_model = get_api_model_name(judge_model) or judge_model
            cfg = get_model_config(judge_model)
            provider = cfg.provider if cfg else ""
            system_instruction = build_system_instruction(state.get("chat_personality"))
            prompt_query = "; ".join(planned_queries[:4]) if planned_queries else query
            prompt = f"Pesquise na web e resuma as fontes relevantes sobre: {prompt_query}. Cite as fontes."

            if provider == "openai":
                gpt_client = get_gpt_client()
                if gpt_client and hasattr(gpt_client, "responses"):
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
                    text = to_perplexity("openai", resp)
                    if text:
                        return {
                            **state,
                            "research_context": text,
                            "research_sources": [],
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
                    if _is_anthropic_vertex_client(claude_client):
                        kwargs["anthropic_version"] = os.getenv("ANTHROPIC_VERTEX_VERSION", "vertex-2023-10-16")
                    resp = claude_client.messages.create(**kwargs)
                    text = to_perplexity("claude", resp)
                    if text:
                        return {
                            **state,
                            "research_context": text,
                            "research_sources": [],
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
                    resp = gemini_client.models.generate_content(
                        model=api_model,
                        contents=prompt,
                        config=config,
                    )
                    text = to_perplexity("gemini", resp) or (resp.text or "").strip()
                    if text:
                        return {
                            **state,
                            "research_context": text,
                            "research_sources": [],
                        }
        except Exception as e:
            logger.error(f"❌ [Phase2] Web Search nativo falhou: {e}")

    if planned_queries:
        logger.info(f"🌐 [Phase2] Using {len(planned_queries)} planned queries")
        per_query = max(3, int(6 / max(1, len(planned_queries))))
        tasks = [
            web_search_service.search(q, num_results=per_query)
            for q in planned_queries[:6]
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
            "results": deduped[:12],
            "queries": planned_queries[:6],
            "query": query,
            "source": "multi-planned",
        }
    elif multi_query:
        payload = await web_search_service.search_multi(query, num_results=6)
    else:
        payload = await web_search_service.search(query, num_results=6)

    results = payload.get("results") or []
    web_context = build_web_context(payload, max_items=6)

    return {
        **state,
        "research_context": f"{web_context}\n",
        "research_sources": results
    }


async def research_notes_node(state: DocumentState) -> DocumentState:
    """
    Summarize research sources into concise notes and build a citations map.
    """
    research_context = (state.get("research_context") or "").strip()
    sources = state.get("research_sources") or []

    if not research_context and not sources:
        return {
            **state,
            "research_notes": None,
            "citations_map": {},
            "verification_retry": False,
        }

    citations_map: Dict[str, Any] = {}
    lines = ["## NOTAS DE PESQUISA (use citações [n])"]

    if sources:
        for idx, src in enumerate(sources[:8], start=1):
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
    else:
        lines.append(research_context[:4000])

    notes_text = "\n".join(lines).strip()
    combined_context = notes_text
    if research_context and sources:
        combined_context = f"{notes_text}\n\n## CONTEXTO ORIGINAL\n{research_context[:4000]}"

    return {
        **state,
        "research_notes": notes_text,
        "citations_map": citations_map,
        "research_context": combined_context or research_context,
        "verification_retry": False,
    }


async def research_verify_node(state: DocumentState) -> DocumentState:
    """
    Verify whether citations are present when jurisprudence is required.
    """
    if not state.get("need_juris"):
        return {**state, "verification_retry": False}

    if not (state.get("deep_research_enabled") or state.get("web_search_enabled")):
        return {**state, "verification_retry": False}

    attempts = int(state.get("verifier_attempts", 0) or 0)
    if attempts >= 1:
        return {**state, "verification_retry": False}

    full_document = state.get("full_document", "") or ""
    if not full_document:
        return {**state, "verification_retry": False}

    has_citations = bool(re.search(r"\[[0-9]{1,3}\]", full_document))
    if has_citations:
        return {**state, "verification_retry": False}

    planned_queries = _normalize_queries(state.get("planned_queries"))
    if not planned_queries:
        seed = f"{state.get('tese', '')} {state.get('mode', '')}".strip()
        planned_queries = plan_queries(seed, max_queries=4)

    return {
        **state,
        "verification_retry": True,
        "verifier_attempts": attempts + 1,
        "planned_queries": planned_queries,
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
            }
        }

    gpt_model = state.get("gpt_model") or "gpt-5.2"

    hint_block = "\n".join(
        f"- {item['label']} ({'critico' if item.get('critical') else 'nao_critico'})"
        for item in hint_items
    ) or "Nenhum checklist complementar informado."

    prompt = f"""
Você é um auditor jurídico. Valide fatos e documentos EXCLUSIVAMENTE com base no SEI abaixo.

TAREFA:
1) Liste fatos/IDs confirmados no SEI
2) Liste pontos não verificáveis (sem documento)
3) Liste inconsistências/alertas
4) Gere um CHECKLIST documental com criticidade

REGRAS:
- Use somente SEI/autos locais como prova de fato.
- Se faltar prova, marque como "missing" ou "uncertain".
- Marque como critical se a ausência impede a conclusão jurídica.
- Inclua os itens do checklist complementar do usuário, mesmo que não apareçam no SEI.

CHECKLIST COMPLEMENTAR DO USUÁRIO:
{hint_block}

SEI (trecho):
{sei_context[:12000]}

FORMATO DE RESPOSTA (JSON puro):
{{
  "confirmados": ["..."],
  "nao_verificaveis": ["..."],
  "inconsistencias": ["..."],
  "checklist": [
    {{
      "id": "ata_licitacao",
      "label": "Ata de licitação",
      "status": "present|missing|uncertain",
      "critical": true,
      "evidence": "SEI 12345, p. 3",
      "notes": "..."
    }}
  ],
  "summary": "..."
}}
""".strip()

    response_text = ""
    try:
        from app.services.ai.agent_clients import init_openai_client, call_openai_async
        from app.services.ai.model_registry import get_api_model_name
        gpt_client = init_openai_client()
        if gpt_client:
            response_text = await call_openai_async(
                gpt_client,
                prompt,
                model=get_api_model_name(gpt_model),
                timeout=90
            )
    except Exception as e:
        logger.warning(f"⚠️ Fact-check GPT falhou: {e}")

    if not response_text:
        try:
            from app.services.ai.gemini_drafter import GeminiDrafterWrapper
            drafter = GeminiDrafterWrapper()
            resp = await asyncio.to_thread(drafter._generate_with_retry, prompt)
            response_text = resp.text if resp else ""
        except Exception as e:
            logger.warning(f"⚠️ Fact-check Gemini falhou: {e}")

    def _extract_json_obj(text: str) -> Optional[Dict[str, Any]]:
        if not text:
            return None
        start = text.find("{")
        if start == -1:
            return None
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except Exception:
                        return None
        return None

    parsed = _extract_json_obj(response_text) or {}
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
        }
    }


async def planner_node(state: DocumentState) -> DocumentState:
    """
    🧠 Planner Node (Auto-Decision)
    
    Decides research strategy (Deep Search vs Web Search vs None) based on:
    - Complexity of the thesis/facts
    - Completeness of the outline
    - User intent
    """
    logger.info("🧠 [Phase2] Planner: Analyzing research strategy...")
    
    # If user explicitly forced a mode via UI flags that we want to respect strictly,
    # we could skip this. But here we want the Planner to be authoritative or at least augment.
    # Let's check if we should skip if user ALREADY enabled deep_research manually?
    # For now, we will RE-EVALUATE. If the user turned it on, the planner likely agrees. 
    # If the user turned it off, the planner might turn it ON if needed.
    
    input_text = state.get("input_text", "")
    thesis = state.get("tese", "")
    mode = state.get("mode", "PETICAO")
    outline = state.get("outline", [])
    ui_deep = bool(state.get("deep_research_enabled"))
    ui_web = bool(state.get("web_search_enabled"))
    combined_text = f"{thesis}\n{input_text}"
    
    prompt = f"""## PLANEJADOR DE PESQUISA JURÍDICA

Você é o estrategista sênior do escritório. Sua função é decidir a estratégia de pesquisa necessária.

### CASO:
Tipo: {mode}
Tese: {thesis}
Fatos (resumo): {input_text[:1000]}...

### ESTRUTURA PROPÓSTA:
{chr(10).join(f"- {s}" for s in outline)}

### DECISÃO NECESSÁRIA:
Precisamos de "Deep Research" (pesquisa profunda, lenta, múltiplos passos) ou apenas "Web Search" (busca rápida) ou nenhuma?

Critérios:
- **Deep Research**: Teses complexas, divergência jurisprudencial, temas inéditos, necessidade de encontrar precedentes específicos difíceis.
- **Web Search**: Dúvidas pontuais, verificar lei atualizada, buscar fatos recentes.
- **Nenhuma**: Matéria puramente de fato (narrada pelo cliente) ou questão jurídica óbvia/pacificada.

### RESPONDA EM JSON:
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
        
        # We use a fast but smart model for planning (GPT-4o or similiar)
        client = init_openai_client()
        if not client:
             # Fallback if no OpenAI
            return state
            
        response = await call_openai_async(
            client, 
            prompt, 
            model=get_api_model_name("gpt-5.2"),
            temperature=0.2,
            max_tokens=500
        )
        
        import json
        decision = {}
        
        # Extract JSON
        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            decision = json.loads(json_match.group())
            
        raciocinio = decision.get("raciocinio", "Sem raciocínio")
        needs_deep = bool(decision.get("precisa_deep_research", False))
        needs_web = bool(decision.get("precisa_web_search", False))
        needs_juris = bool(decision.get("precisa_jurisprudencia", False))

        logger.info(
            f"🧠 Planner Decision: Deep={needs_deep}, Web={needs_web}, Juris={needs_juris}. Reason: {raciocinio}"
        )

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
            planned_queries = plan_queries(seed, max_queries=4)

        updates = {
            "planning_reasoning": raciocinio,
            "planned_queries": planned_queries,
            "deep_research_enabled": deep_enabled,
            "web_search_enabled": web_enabled,
            "need_juris": needs_juris or deep_enabled or web_enabled,
            "research_mode": "deep" if deep_enabled else "light" if web_enabled else "none",
        }

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

        planned_queries = _normalize_queries(state.get("planned_queries"))
        if not planned_queries and (deep_enabled or web_enabled):
            seed = f"{thesis} {mode}".strip() or input_text[:200]
            planned_queries = plan_queries(seed, max_queries=4)

        return {
            **state,
            "planning_reasoning": "Heurística (fallback)",
            "planned_queries": planned_queries,
            "deep_research_enabled": deep_enabled,
            "web_search_enabled": web_enabled,
            "need_juris": needs_juris or deep_enabled or web_enabled,
            "research_mode": "deep" if deep_enabled else "light" if web_enabled else "none",
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
    logger.info("⚔️ [6-Star Hybrid] Multi-Agent Committee Starting...")
    
    # Lazy imports to avoid circular dependencies
    from app.services.ai.agent_clients import (
        generate_section_agent_mode_async, 
        CaseBundle, 
        init_openai_client, 
        init_anthropic_client,
        build_system_instruction
    )
    
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
3) **Fontes acadêmicas/doutrina** (quando houver no RAG): use citação no texto (AUTOR, ano) e inclua ao final uma seção **REFERÊNCIAS (ABNT NBR 6023)** com as entradas completas baseadas nas fontes do RAG.
4) Se faltar metadado (autor/ano/local), não invente: use [[PENDENTE: completar referência ABNT da fonte X]].
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
    length_guidance = build_length_guidance(state, len(outline))
    reasoning_level = state.get("thinking_level", "medium")
    length_guidance = build_length_guidance(state, len(outline))
    
    processed_sections = []
    has_divergence = False
    divergence_parts = []
    
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
    
    # Process each section
    for i, title in enumerate(outline):
        section_start = f"[{i+1}/{len(outline)}] {title}"
        logger.info(f"📝 {section_start}")
        
        # Emit real-time event (if job_manager supports it)
        try:
            from app.services.job_manager import job_manager
            # job_manager.emit_event() # Would need implementation
        except:
            pass
        
        # v5.1: Graph RAG routing for this section
        route_config = default_route_for_section(title, mode)
        section_context = research_context
        
        # Enrich with graph context if STRATEGY_GRAPH
        if route_config.get("strategy") == STRATEGY_GRAPH:
            graph = get_knowledge_graph()
            if graph:
                # Get any existing RAG chunks for enrichment
                rag_chunks = []
                # Try to parse existing research as chunks (simple fallback)
                if research_context:
                    rag_chunks = [{"text": research_context[:2000], "metadata": {}}]
                
                graph_context = graph.enrich_context(rag_chunks, hops=route_config.get("graph_hops", 2))
                if graph_context:
                    section_context = graph_context + "\n\n" + (research_context or "")
                    logger.info(f"   📊 GraphRAG: Enriched context for '{title}'")
        
        evidence_policy = build_evidence_policy(state.get("audit_mode", "sei_only"))
        fact_check_summary = (state.get("fact_check_summary") or "").strip()
        fact_check_block = f"### FACT-CHECK SEI:\n{fact_check_summary}\n" if fact_check_summary else ""

        prompt_base = f"""
## SEÇÃO: {title}
## TIPO DE DOCUMENTO: {mode}
## TESE PRINCIPAL: {thesis}

{citation_instr}
{personality_instr}
{length_guidance}
{evidence_policy}

### CONTEXTO FACTUAL (Extraído dos Autos):
{input_text[:2000]}

{fact_check_block}
### PESQUISA JURÍDICA:
{section_context[:3000] if section_context else "Nenhuma pesquisa adicional disponível."}
"""
        
        if use_multi_agent:
            try:
                # FULL PARAMETER CALL - 6 STARS
                section_text, divergencias, drafts = await generate_section_agent_mode_async(
                    section_title=title,
                    prompt_base=prompt_base,
                    case_bundle=CaseBundle(processo_id=state.get("job_id") or "langgraph-job"),
                    rag_local_context=research_context,
                    drafter=drafter,  # ⭐ Now properly passed
                    gpt_client=gpt_client,
                    claude_client=claude_client,
                    gpt_model=gpt_model,
                    claude_model=claude_model,
                    drafter_models=drafter_models,
                    reviewer_models=reviewer_models,
                    judge_model=judge_model,
                    reasoning_level=reasoning_level,  # ⭐ Now passed
                    thesis=thesis,  # ⭐ Now passed
                    web_search=state.get("web_search_enabled", False),  # ⭐ Now passed
                    search_mode=state.get("search_mode", "hybrid"),
                    multi_query=state.get("multi_query", True),
                    breadth_first=state.get("breadth_first", False),
                    mode=mode,  # Unifica com prompts v2 (tipo de documento)
                    extra_agent_instructions="\n".join(
                        [part for part in [citation_instr, personality_instr] if part]
                    ).strip() or None,
                    system_instruction=system_instruction,
                    previous_sections=[
                        f"### {p.get('section_title','Seção')}\n{(p.get('merged_content','') or '')[:800]}"
                        for p in processed_sections[-6:]
                    ],  # Anticontradiction com trecho
                    cached_content=context_cache  # v5.3: Context Reuse
                )
                
                # Store result with full observability
                judge_structured = None
                if isinstance(drafts, dict):
                    judge_structured = drafts.get("judge_structured")
                quality_score = None
                if isinstance(judge_structured, dict):
                    quality_score = judge_structured.get("quality_score")

                processed_sections.append({
                    "section_title": title,
                    "merged_content": section_text,
                    "has_significant_divergence": bool(divergencias),
                    "divergence_details": divergencias or "",
                    "drafts": drafts or {},
                    "claims_requiring_citation": (drafts or {}).get("claims_requiring_citation", []) if isinstance(drafts, dict) else [],
                    "removed_claims": (drafts or {}).get("removed_claims", []) if isinstance(drafts, dict) else [],
                    "risk_flags": (drafts or {}).get("risk_flags", []) if isinstance(drafts, dict) else [],
                    "quality_score": quality_score
                })
                
                if divergencias:
                    has_divergence = True
                    divergence_parts.append(f"- **{title}**: {divergencias[:200]}...")
                    
                logger.info(f"✅ {section_start} - Completed")
                    
            except Exception as e:
                logger.error(f"❌ {section_start} - Error: {e}")
                processed_sections.append({
                    "section_title": title,
                    "merged_content": f"[Erro no comitê multi-agente: {str(e)}]",
                    "has_significant_divergence": True,
                    "divergence_details": str(e),
                    "drafts": {},
                    "quality_score": None
                })
                has_divergence = True
                divergence_parts.append(f"- **{title}**: ERRO - {str(e)[:100]}")
        else:
            # Single Model Fallback (when multi-agent not available)
            logger.info(f"⚡ {section_start} - Using single-model mode")
            
            fallback_content = f"[Texto para {title} - Modo Simples (Multi-Agent não disponível)]"
            
            # Try to use drafter directly if available
            if drafter:
                try:
                    # v5.0: Use robust generate_section even in single mode to get formatting/citations
                    # This ensures single-agent mode has parity with the specialized prompts
                    fallback_content = drafter.generate_section(
                        titulo=title,
                        contexto_rag=research_context[:5000],
                        tipo_peca=mode,
                        resumo_caso=input_text[:3000],
                        tese_usuario=thesis,
                        cached_content=context_cache
                    )
                except Exception as e:
                    logger.warning(f"⚠️ Single-model robust generation failed: {e}. Falling back to simple.")
                    try:
                        simple_prompt = f"Redija a seção '{title}' para um documento do tipo {mode}.\n\nTese: {thesis}\n\nContexto: {input_text[:1500] if not context_cache else '[CONTEXTO EM CACHE]'}"
                        resp = drafter._generate_with_retry(simple_prompt, cached_content=context_cache)
                        if resp and resp.text:
                            fallback_content = resp.text
                    except:
                        pass
            
            processed_sections.append({
                "section_title": title,
                "merged_content": fallback_content,
                "has_significant_divergence": False,
                "divergence_details": "",
                "drafts": {},
                "quality_score": None
            })

    # Assemble full document
    full_doc = f"# {mode}\n\n"
    for section in processed_sections:
        full_doc += f"## {section.get('section_title', 'Seção')}\n\n"
        full_doc += section.get("merged_content", "")
        full_doc += "\n\n---\n\n"
    
    divergence_summary = "\n".join(divergence_parts) if divergence_parts else "✅ Consenso entre todos os agentes."
    
    logger.info(f"📄 Document assembled: {len(processed_sections)} sections, Divergence: {has_divergence}")
    
    return {
        **state,
        "processed_sections": processed_sections,
        "full_document": full_doc,
        "has_any_divergence": has_divergence,
        "divergence_summary": divergence_summary,
        "context_cache_created": context_cache_created,
        "context_cache_name": getattr(context_cache, 'name', None) if context_cache else None
    }


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
3) Doutrina/Acadêmico: (AUTOR, ano) + seção final **REFERÊNCIAS (ABNT NBR 6023)**
4) Sem metadado: [[PENDENTE: completar referência ABNT]]
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
    
    # Process each section through the sub-graph
    for i, title in enumerate(outline):
        logger.info(f"🔬 [{i+1}/{len(outline)}] Running sub-graph for: {title}")
        
        evidence_policy = build_evidence_policy(state.get("audit_mode", "sei_only"))
        fact_check_summary = (state.get("fact_check_summary") or "").strip()
        fact_check_block = f"### FACT-CHECK SEI:\n{fact_check_summary}\n" if fact_check_summary else ""

        prompt_base = f"""
## SEÇÃO: {title}
## TIPO DE DOCUMENTO: {mode}
## TESE PRINCIPAL: {thesis}

{citation_instr}
{length_guidance}
{evidence_policy}

### CONTEXTO FACTUAL:
{input_text[:2000]}

{fact_check_block}
### PESQUISA JURÍDICA:
{research_context[:3000] if research_context else "Nenhuma pesquisa."}
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
                rag_context=research_context,
                thesis=thesis,
                mode=mode,
                gpt_client=gpt_client,
                claude_client=claude_client,
                drafter=drafter,
                gpt_model=gpt_model,
                claude_model=claude_model,
                previous_sections=previous_section_titles,  # Back-compat
                previous_sections_excerpts=previous_section_excerpts,
                formatting_options=state.get("formatting_options"),
                template_structure=state.get("template_structure")
                ,
                # Note: extra instructions are included inside prompt_base for sub-graph
            )
            
            processed_sections.append({
                "section_title": title,
                "merged_content": result.get("merged_content", ""),
                "has_significant_divergence": bool(result.get("divergencias")),
                "divergence_details": result.get("divergencias", ""),
                "drafts": result.get("drafts", {}),
                "metrics": result.get("metrics", {}),
                "claims_requiring_citation": result.get("claims_requiring_citation", []) or [],
                "removed_claims": result.get("removed_claims", []) or [],
                "risk_flags": result.get("risk_flags", []) or [],
                "quality_score": (result.get("metrics", {}) or {}).get("quality_score"),
            })
            
            if result.get("divergencias"):
                has_divergence = True
                divergence_parts.append(f"- **{title}**: {result['divergencias'][:200]}...")
                
            logger.info(f"✅ [{i+1}/{len(outline)}] {title} - Complete")
            
        except Exception as e:
            logger.error(f"❌ [{i+1}/{len(outline)}] {title} - Error: {e}")
            processed_sections.append({
                "section_title": title,
                "merged_content": f"[Erro no sub-grafo: {e}]",
                "has_significant_divergence": True,
                "divergence_details": str(e),
                "drafts": {},
                "quality_score": None
            })
            has_divergence = True
            divergence_parts.append(f"- **{title}**: ERRO")
    
    # Assemble document
    full_doc = f"# {mode}\n\n"
    for section in processed_sections:
        full_doc += f"## {section.get('section_title', 'Seção')}\n\n"
        full_doc += section.get("merged_content", "")
        full_doc += "\n\n---\n\n"
    
    divergence_summary = "\n".join(divergence_parts) if divergence_parts else "✅ Consenso (Granular Mode)"
    
    logger.info(f"📄 [Granular] Document: {len(processed_sections)} sections, Divergence: {has_divergence}")
    
    return {
        **state,
        "processed_sections": processed_sections,
        "full_document": full_doc,
        "has_any_divergence": has_divergence,
        "divergence_summary": divergence_summary
    }


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

        prompt = f"""
Você é um assistente jurídico. Reescreva APENAS a seção abaixo do documento.

TIPO: {mode_local}
SEÇÃO: {title}
TESE: {thesis_local}

INSTRUÇÕES DO REVISOR HUMANO:
{instructions}

CONTEXTO (autos):
{input_text_local[:2000]}

PESQUISA:
{research_local[:2500] if research_local else "(sem pesquisa)"}

TEXTO ATUAL DA SEÇÃO (para referência):
{current_text[:8000]}

Saída: entregue somente o texto final da seção (sem cabeçalhos '##', sem prefácio).
""".strip()

        if drafter:
            try:
                resp = drafter._generate_with_retry(prompt)
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
            case_bundle=CaseBundle(processo_id="langgraph-section-hil"),
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
            thesis=thesis_local,
            web_search=state.get("web_search_enabled", False),
            search_mode=state.get("search_mode", "hybrid"),
            multi_query=state.get("multi_query", True),
            breadth_first=state.get("breadth_first", False),
            mode=mode_local,
            previous_sections=prev_sections,
            system_instruction=system_instruction,
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
        # Only gate by score when policy is optional. If section-level HIL is required, do not skip low-scoring sections.
        if policy != "required" and target_score and (sec_score is None or float(sec_score) < target_score):
            continue

        # Keep interrupt payload also in state so the SSE layer can read it reliably.
        payload: Dict[str, Any] = {
            "section_title": title,
            "merged_content": sec.get("merged_content", "") or "",
            "divergence_details": sec.get("divergence_details", "") or "",
            "drafts": sec.get("drafts", {}) or {},
            "document_preview": state.get("full_document", "")[:2000],
        }

        # Mutate in-place so checkpointer snapshot includes this payload at interrupt time.
        state["hil_section_payload"] = payload  # type: ignore[typeddict-item]

        decision = interrupt({
            "type": "section_review",
            "checkpoint": "section",
            "message": f"Revise a seção '{title}' antes de prosseguir.",
            **payload
        })

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
                    state["full_document"] = full_doc  # type: ignore[typeddict-item]
                    payload["document_preview"] = full_doc[:2000]

                except Exception as e:
                    logger.error(f"❌ [Section HIL] IA rewrite failed for '{title}': {e}")

            # Keep last instructions visible in the next interrupt (so user can iterate).
            if instr:
                payload["instructions"] = instr

            state["hil_section_payload"] = payload  # type: ignore[typeddict-item]

            decision = interrupt({
                "type": "section_review",
                "checkpoint": "section",
                "message": f"Seção '{title}' precisa de aprovação. Edite manualmente ou aprove para continuar.",
                **payload
            })

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

    return {
        **state,
        "processed_sections": processed,
        "full_document": full_doc,
        "hil_section_payload": None
    }


async def divergence_hil_node(state: DocumentState) -> DocumentState:
    """HIL Checkpoint: Review divergences"""
    if state.get("auto_approve_hil", False):
        logger.info("✅ [Phase2] Auto-approve enabled, skipping divergence HIL")
        return {**state, "human_approved_divergence": True}

    if not state.get("has_any_divergence"):
        logger.info("✅ [Phase2] No divergence, skipping HIL")
        return {**state, "human_approved_divergence": True}
    
    logger.info("🛑 [Phase2] HIL: Divergence Review")
    
    decision = interrupt({
        "type": "divergence_review",
        "checkpoint": "divergence",
        "message": "Divergências detectadas no debate multi-agente.",
        "divergence_summary": state.get("divergence_summary", ""),
        "document_preview": state.get("full_document", "")[:3000]
    })
    
    return {
        **state,
        "human_approved_divergence": decision.get("approved", False),
        "human_edits": decision.get("edits")
    }


async def audit_node(state: DocumentState) -> DocumentState:
    """
    ⚖️ Real Audit Node
    
    Calls AuditService to analyze the document for:
    - Citation hallucinations
    - Procedural errors
    - Legal validity issues
    """
    logger.info("⚖️ [Phase4] Real Audit Starting...")
    
    full_document = state.get("full_document", "")
    
    if not full_document:
        logger.warning("⚠️ No document to audit")
        return {**state, "audit_status": "aprovado", "audit_report": None, "audit_issues": []}
    
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
        
        # Determine status
        if "Reprovado" in audit_markdown:
            status = "reprovado"
        elif issues or "Ressalvas" in audit_markdown:
            status = "aprovado_ressalvas"
        else:
            status = "aprovado"
        
        logger.info(f"⚖️ Audit complete: {status}, {len(issues)} issues found")
        
        return {
            **state,
            "audit_status": status,
            "audit_report": {
                "markdown": audit_markdown,
                "citations": citations,
                "issue_count": len(issues)
            },
            "audit_issues": issues
        }
        
    except Exception as e:
        logger.error(f"❌ Audit failed: {e}")
        return {
            **state,
            "audit_status": "aprovado_ressalvas",
            "audit_report": {"error": str(e)},
            "audit_issues": [f"Falha na auditoria: {e}"]
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
    
    return {
        **state,
        "hil_checklist": checklist.to_dict()
    }


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
    
    full_document = state.get("full_document", "")
    mode = state.get("mode", "PETICAO")
    
    prompt = f"""
Você é um revisor jurídico sênior. O documento abaixo foi auditado e os seguintes problemas foram identificados:

## PROBLEMAS ENCONTRADOS:
{chr(10).join(['- ' + issue for issue in issues])}

## DOCUMENTO ORIGINAL ({mode}):
{full_document[:15000]}

## INSTRUÇÕES RIGOROSAS:
1. CORRIJA apenas os trechos problemáticos apontados acima.
2. NÃO invente citações, jurisprudências ou dados não fundamentados.
3. Se uma citação foi apontada como inexistente, REMOVA-A ou substitua por fonte verificável.
4. MANTENHA a estrutura geral e o tom do documento.
5. Produza o documento COMPLETO corrigido, não apenas os trechos alterados.

## DOCUMENTO CORRIGIDO:
"""
    
    try:
        resp = drafter._generate_with_retry(prompt)
        corrected = resp.text if resp else ""
        
        if not corrected:
            logger.warning("⚠️ Empty correction response")
            return {**state, "proposed_corrections": None}
        
        # Simple diff summary (just count changes)
        original_lines = set(full_document.split("\n"))
        corrected_lines = set(corrected.split("\n"))
        diff_count = len(original_lines.symmetric_difference(corrected_lines))
        diff_summary = f"~{diff_count} linhas modificadas"
        
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
            return {**state, "full_document": proposed, "human_approved_corrections": True}
        return {**state, "human_approved_corrections": True}

    if not proposed:
        logger.info("✅ No corrections to review, skipping HIL")
        return {**state, "human_approved_corrections": True}
    
    logger.info("🛑 [Phase4] HIL: Correction Review")
    
    decision = interrupt({
        "type": "correction_review",
        "checkpoint": "correction",
        "message": "Correções propostas com base na auditoria. Revise antes de aplicar.",
        "original_document": state.get("full_document", "")[:3000],
        "proposed_corrections": proposed[:3000],
        "corrections_diff": state.get("corrections_diff", ""),
        "audit_issues": state.get("audit_issues", []),
        "audit_status": state.get("audit_status")
    })
    
    if decision.get("approved"):
        # Apply corrections (use edited version if provided, else proposed)
        final_corrected = decision.get("edits") or proposed
        logger.info("✅ Corrections approved and applied")
        return {
            **state,
            "full_document": final_corrected,
            "human_approved_corrections": True
        }
    
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
    logger.info("🤝 [Final Committee Review] Starting holistic document review...")
    
    full_document = state.get("full_document", "")
    if not full_document:
        logger.warning("⚠️ No document for committee review")
        return {**state, "committee_review_report": None}
    
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
    doc_excerpt = full_document[:15000]
    
    # Base review prompt
    review_prompt_template = """
## REVISÃO HOLÍSTICA DO DOCUMENTO - COMITÊ FINAL

Você é um revisor sênior analisando o documento completo ANTES da entrega final.

**TIPO DE DOCUMENTO**: {mode}
**TESE PRINCIPAL**: {thesis}

### DOCUMENTO COMPLETO:
{document}

---

### TAREFA DE REVISÃO

Analise o documento e forneça um parecer CONCISO (máx 500 palavras):

1. **COERÊNCIA** (0-10): Contradições entre seções?
2. **FLUXO** (0-10): Transições suaves? Progressão lógica?
3. **TESE** (0-10): Argumentação persuasiva?
4. **PROBLEMAS CRÍTICOS**: Liste até 3 problemas (formato: [SEÇÃO] - Problema)
5. **NOTA FINAL** (0-10)

Responda em JSON:
{{"coerencia": N, "fluxo": N, "tese": N, "problemas": [...], "nota_final": N, "resumo": "..."}}
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
            if hasattr(getattr(gpt_client, "models", None), "generate_content"):
                response = await asyncio.to_thread(
                    gpt_client.models.generate_content,
                    model=get_api_model_name(gpt_model),
                    contents=prompt
                )
                return {"agent": "GPT", "response": response.text}
            response = await asyncio.to_thread(
                gpt_client.chat.completions.create,
                model=get_api_model_name(gpt_model),
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=1000
            )
            return {"agent": "GPT", "response": response.choices[0].message.content}
        except Exception as e:
            logger.warning(f"⚠️ GPT review failed: {e}")
            return None
    
    async def get_claude_review():
        if not claude_client:
            return None
        try:
            prompt = review_prompt_template.format(mode=mode, thesis=thesis, document=doc_excerpt)
            response = await asyncio.to_thread(
                claude_client.messages.create,
                model=get_api_model_name(claude_model),
                max_tokens=1000,
                messages=[{"role": "user", "content": prompt}]
            )
            return {"agent": "Claude", "response": response.content[0].text}
        except Exception as e:
            logger.warning(f"⚠️ Claude review failed: {e}")
            return None
    
    async def get_judge_review():
        try:
            prompt = review_prompt_template.format(mode=mode, thesis=thesis, document=doc_excerpt)
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
        return {**state, "committee_review_report": {"status": "skipped", "reason": "no reviews completed"}}
    
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
        
        judge_consolidation_prompt = f"""## TAREFA: CONSOLIDAÇÃO FINAL DO COMITÊ

Você é o Juiz Final do comitê de revisão. Três agentes (GPT, Claude e Juiz) revisaram independentemente o documento abaixo.

### DOCUMENTO ORIGINAL:
{doc_excerpt[:8000]}

### REVISÕES DOS AGENTES:
{reviews_text}

## INSTRUÇÕES:
1. **SINTETIZE** os pontos fortes e fracos identificados pelos 3 agentes.
2. **IDENTIFIQUE** consensos e divergências entre as revisões.
3. **PROPONHA** correções específicas para os problemas mais críticos.
4. **GERE** uma versão revisada do documento SE houver correções materiais a fazer.

## FORMATO DE RESPOSTA (JSON):
```json
{{
    "sintese_criticas": "string resumindo os principais pontos",
    "consensos": ["lista de pontos em que todos concordam"],
    "divergencias": ["lista de pontos em que os agentes discordam"],
    "correcoes_propostas": [
        {{"trecho_original": "...", "trecho_corrigido": "...", "justificativa": "..."}}
    ],
    "documento_revisado": "string com o documento completo revisado (ou null se não houver correções)",
    "nota_consolidada": 8.5,
    "recomendacao": "aprovar|revisar_humano|rejeitar"
}}
```
"""
        try:
            judge_response = await _call_model_any_async(
                judge_model,
                judge_consolidation_prompt,
                temperature=0.2,
                max_tokens=1500
            )
            if judge_response:
                judge_synthesis = judge_response
                logger.info("✅ Juiz concluiu consolidação")
                
                # Try to extract revised document
                try:
                    json_match = re.search(r'\{[\s\S]*\}', judge_response)
                    if json_match:
                        judge_data = json.loads(json_match.group())
                        if judge_data.get("documento_revisado"):
                            revised_document = judge_data["documento_revisado"]
                            logger.info("📝 Documento revisado pelo Juiz disponível")
                except (json.JSONDecodeError, AttributeError):
                    pass
                    
        except Exception as e:
            logger.warning(f"⚠️ Judge consolidation failed: {e}")

    
    # Parse scores and synthesize
    import json
    all_scores = []
    all_problems = []
    scores_by_agent: Dict[str, float] = {}

    def _extract_json_block(text: str) -> Optional[str]:
        if not text:
            return None
        start = text.find("{")
        if start == -1:
            return None
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
        return None

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
        try:
            # Try to extract JSON from response
            json_block = _extract_json_block(response)
            if json_block and "nota_final" in json_block:
                data = json.loads(json_block)
                score = _coerce_score(data.get("nota_final"))
                if score is not None:
                    all_scores.append(score)
                    scores_by_agent[agent] = score
                if "problemas" in data and isinstance(data["problemas"], list):
                    all_problems.extend(data["problemas"])
        except (json.JSONDecodeError, AttributeError):
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
    updated_full_document = revised_document or state.get("full_document", "")
    
    return {
        **state,
        "committee_review_report": committee_report,
        "full_document": updated_full_document,  # v5.4: May be revised by Judge
        "quality_gate_force_hil": (
            requires_hil
            or score_disagreement
            or state.get("quality_gate_force_hil", False)
        )
    }


async def refine_document_node(state: DocumentState) -> DocumentState:
    """
    ♻️ Refine document based on committee review feedback (full-auto).
    """
    logger.info("♻️ [Refine] Applying committee feedback...")

    report = state.get("committee_review_report") or {}
    full_document = state.get("full_document", "") or ""
    if not full_document:
        return {**state, "refinement_round": state.get("refinement_round", 0) + 1}

    issues = report.get("critical_problems") or []
    synthesis = report.get("judge_synthesis") or ""
    score = report.get("score")

    prompt = f"""
Você é um revisor jurídico sênior. Melhore o documento abaixo com base nas críticas.

NOTA ATUAL: {score}
PROBLEMAS CRÍTICOS:
{chr(10).join(f"- {p}" for p in issues) if issues else "- (não informado)"}

SÍNTESE DO JUIZ (se houver):
{synthesis or "(sem síntese)"}

REGRAS:
- Preserve fatos e citações com [TIPO - Doc. X, p. Y].
- Não invente documentos ou fatos.
- Se precisar de prova não presente no SEI, use [[PENDENTE: ...]].
- Retorne o documento completo revisado.

DOCUMENTO:
{full_document[:18000]}
""".strip()

    updated_document = full_document
    try:
        from app.services.ai.gemini_drafter import GeminiDrafterWrapper
        drafter = GeminiDrafterWrapper()
        resp = await asyncio.to_thread(drafter._generate_with_retry, prompt)
        if resp and resp.text:
            updated_document = resp.text
    except Exception as e:
        logger.warning(f"⚠️ Refine document failed: {e}")

    return {
        **state,
        "full_document": updated_document,
        "refinement_round": state.get("refinement_round", 0) + 1
    }


def _parse_style_report(raw: str) -> Dict[str, Any]:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        pass
    match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
    if not match:
        return {}
    try:
        return json.loads(match.group(0))
    except Exception:
        return {}


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
    logger.info("🎨 [Style Check] Avaliando estilo editorial...")
    full_document = state.get("full_document", "") or ""
    if not full_document:
        return {
            **state,
            "style_report": None,
            "style_score": None,
            "style_tone": None,
            "style_issues": [],
            "style_term_variations": [],
            "style_check_status": "skipped",
            "style_check_payload": None
        }

    excerpt = full_document[:12000]
    if len(full_document) > 14000:
        excerpt = f"{full_document[:10000]}\n...\n{full_document[-4000:]}"

    prompt = f"""
Você é um revisor de estilo jurídico. Avalie APENAS o estilo (clareza, formalidade, impessoalidade e consistência terminológica).
NÃO avalie mérito jurídico nem fatos. Responda exclusivamente em JSON válido, sem markdown.

Campos obrigatórios:
- score (0-10)
- tone (rótulo curto: ex. "formal/defensivo", "agressivo", "neutro")
- thermometer ("Muito brando" | "Equilibrado" | "Agressivo")
- issues (lista de até 5 problemas de estilo)
- term_variations (lista de objetos {{term, preferred, count, note}}; pode ser vazia)
- recommended_action (instrução curta para ajuste de tom)

DOCUMENTO (amostra):
{excerpt}
""".strip()

    raw = await _call_model_any_async(
        "claude-4.5-opus",
        prompt,
        temperature=0.1,
        max_tokens=800
    )
    report = _normalize_style_report(_parse_style_report(raw))
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
        "style_check_payload": style_payload
    }

    if state.get("auto_approve_hil", False):
        if score_val is not None and score_val < min_score:
            instruction = report.get("recommended_action") or "Ajuste o tom para ficar mais formal, impessoal e consistente."
            return {
                **base_state,
                "style_check_status": "needs_refine",
                "style_instruction": instruction,
                "style_check_payload": None
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
        "style_check_payload": None
    }


async def style_refine_node(state: DocumentState) -> DocumentState:
    """
    ✍️ Ajusta o tom/estilo do documento conforme instruções de Style Check.
    """
    instruction = (state.get("style_instruction") or "").strip()
    full_document = state.get("full_document", "") or ""
    if not full_document or not instruction:
        return {**state, "style_check_status": "approved", "style_instruction": None}

    logger.info("✍️ [Style Refine] Ajustando tom editorial...")
    issues = state.get("style_issues") or []
    tone = state.get("style_tone") or ""

    prompt = f"""
Você é um editor jurídico sênior. Ajuste APENAS o estilo e o tom do documento.

INSTRUÇÕES DE TOM:
{instruction}

ACHADOS DE ESTILO:
{chr(10).join(f"- {i}" for i in issues) if issues else "- (sem achados)"}

TOM DETECTADO:
{tone or "(não informado)"}

REGRAS:
- Preserve fatos, estrutura e citações [TIPO - Doc. X, p. Y].
- Não invente documentos nem fatos.
- Retorne o documento completo revisado.

DOCUMENTO:
{full_document[:18000]}
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
    return {
        **state,
        "full_document": updated_document,
        "style_instruction": None,
        "style_check_status": "refined",
        "style_refine_round": rounds + 1
    }


async def document_gate_node(state: DocumentState) -> DocumentState:
    """
    🛑 Gate documental: bloqueia sem documentos críticos, permite HIL em faltas não críticas.
    """
    checklist = state.get("document_checklist") or {}
    items = checklist.get("items") or []
    strict_gate = bool(state.get("strict_document_gate", False))

    missing_critical = [i for i in items if i.get("status") != "present" and i.get("critical")]
    missing_noncritical = [i for i in items if i.get("status") != "present" and not i.get("critical")]

    if strict_gate and (missing_critical or missing_noncritical):
        missing_all = missing_critical + missing_noncritical
        summary = checklist.get("summary") or "Documentos pendentes (modo auditoria)."
        missing_labels = ", ".join([i.get("label") or i.get("id") for i in missing_all if isinstance(i, dict)]) or "Documentos pendentes"
        return _with_final_decision({
            **state,
            "document_gate_status": "blocked",
            "document_gate_missing": missing_all,
            "final_markdown": f"⛔ Documento bloqueado.\n\n{summary}\n\nPendências: {missing_labels}"
        }, "NEED_EVIDENCE")

    if missing_critical:
        summary = checklist.get("summary") or "Documentos críticos pendentes."
        missing_labels = ", ".join([i.get("label") or i.get("id") for i in missing_critical if isinstance(i, dict)]) or "Documentos críticos pendentes"
        return _with_final_decision({
            **state,
            "document_gate_status": "blocked",
            "document_gate_missing": missing_critical,
            "final_markdown": f"⛔ Documento bloqueado.\n\n{summary}\n\nPendências: {missing_labels}"
        }, "NEED_EVIDENCE")

    if missing_noncritical:
        if state.get("auto_approve_hil", False):
            return _with_final_decision({
                **state,
                "document_gate_status": "override_auto",
                "document_gate_missing": missing_noncritical,
            }, "APPROVED", extra_reasons=["override_noncritical_docs"])

        decision = interrupt({
            "type": "document_gate",
            "checkpoint": "document_gate",
            "message": "Faltam documentos NÃO críticos. Deseja prosseguir com ressalva?",
            "missing_noncritical": missing_noncritical,
            "summary": checklist.get("summary"),
        })

        if decision.get("approved"):
            return _with_final_decision({
                **state,
                "document_gate_status": "override",
                "document_gate_missing": missing_noncritical,
            }, "APPROVED", extra_reasons=["override_noncritical_docs"])

        return _with_final_decision({
            **state,
            "document_gate_status": "blocked",
            "document_gate_missing": missing_noncritical,
            "final_markdown": "⛔ Documento bloqueado por decisão humana."
        }, "NEED_EVIDENCE", extra_reasons=["blocked_by_human"])

    return {
        **state,
        "document_gate_status": "ok",
        "document_gate_missing": [],
    }


async def human_proposal_debate_node(state: DocumentState) -> DocumentState:
    """
    v5.4: Debate node for evaluating human proposals.
    
    When user rejects with a proposal (section or final), the committee
    evaluates it and the Judge model decides whether to accept, merge, or reject.
    """
    logger.info("💬 [Phase3] Human Proposal Debate Starting...")
    
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
        current_content = state.get("full_document", "")[:8000]
    
    # Initialize clients
    from app.services.ai.agent_clients import (
        init_openai_client, init_anthropic_client,
        call_openai_async, call_anthropic_async
    )
    from app.services.ai.model_registry import DEFAULT_JUDGE_MODEL
    
    gpt_client = init_openai_client()
    claude_client = init_anthropic_client()
    judge_model = state.get("judge_model") or DEFAULT_JUDGE_MODEL
    
    evaluation_prompt = f"""## AVALIAÇÃO DE PROPOSTA HUMANA

O usuário rejeitou a versão atual e propôs uma alternativa.

### VERSÃO ATUAL DO {'SEÇÃO: ' + target_section if scope == 'section' else 'DOCUMENTO'}:
{current_content[:3000]}

### PROPOSTA DO USUÁRIO:
{proposal[:3000]}

## INSTRUÇÕES:
1. Compare a proposta com a versão atual.
2. Avalie se a proposta:
   - Resolve problemas existentes
   - Mantém a coerência jurídica
   - Está bem fundamentada
3. Dê uma nota de 0-10 para a proposta.

## RESPONDA EM JSON:
```json
{{
    "nota": 8.0,
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
    judge_prompt = f"""## DECISÃO FINAL SOBRE PROPOSTA HUMANA

### PROPOSTA DO USUÁRIO:
{proposal[:2000]}

### VERSÃO ATUAL:
{current_content[:2000]}

### AVALIAÇÕES DOS AGENTES:
{chr(10).join([f"**{a}**: {r[:1000]}" for a, r in evaluations.items()])}

## INSTRUÇÕES:
Você é o Juiz Final. Decida:
1. **ACEITAR**: A proposta do usuário substitui completamente a versão atual.
2. **MERGE**: Combine os melhores elementos de ambas as versões.
3. **REJEITAR**: Mantém a versão atual, explicando os problemas da proposta.

## RESPONDA EM JSON:
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
        try:
            json_match = re.search(r'\{[\s\S]*\}', judge_response)
            if json_match:
                judge_data = json.loads(json_match.group())
                decision = judge_data.get("decisao", "rejeitar")
                justification = judge_data.get("justificativa", "")
                if judge_data.get("texto_final"):
                    final_text = judge_data["texto_final"]
        except (json.JSONDecodeError, AttributeError):
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
            updated_state["full_document"] = final_text
            logger.info("✅ Full document updated with proposal")
    else:
        logger.info("❌ Proposal rejected, keeping original")
    
    return updated_state


async def finalize_hil_node(state: DocumentState) -> DocumentState:
    """HIL Checkpoint: Final approval"""
    logger.info("🛑 [Phase2] HIL: Final Approval")

    # v5.3: Cleanup context cache if it was created
    job_id = state.get("job_id", "")
    if state.get("context_cache_created") and job_id:
        from app.services.ai.agent_clients import cleanup_job_cache
        cleanup_job_cache(job_id)

    force_hil = bool(state.get("quality_gate_force_hil", False))
    force_final_hil = bool(state.get("force_final_hil", False))

    if not force_final_hil and not force_hil:
        return _with_final_decision({
            **state,
            "human_approved_final": True,
            "final_markdown": state.get("full_document", "")
        }, "APPROVED", extra_reasons=["final_hil_disabled"])

    if state.get("auto_approve_hil", False) and force_final_hil:
        logger.warning("⚠️ HIL final obrigatório, mas auto_approve_hil está ativo. Prosseguindo sem interrupção.")
        return _with_final_decision({
            **state,
            "human_approved_final": True,
            "final_markdown": state.get("full_document", "")
        }, "APPROVED", extra_reasons=["force_final_hil"])
    
    decision = interrupt({
        "type": "final_approval",
        "checkpoint": "final",
        "message": "Documento pronto. Aprove para gerar versão final.",
        "document": state.get("full_document", ""),
        "audit_status": state.get("audit_status"),
        "audit_report": state.get("audit_report"),
        "committee_review_report": state.get("committee_review_report")
    })
    
    if decision.get("approved"):
        final_md = decision.get("edits") or state.get("full_document", "")
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
workflow.add_node("gen_outline", outline_node)
workflow.add_node("outline_hil", outline_hil_node)
workflow.add_node("planner", planner_node)
workflow.add_node("deep_research", deep_research_node)
workflow.add_node("web_search", web_search_node)
workflow.add_node("research_notes_step", research_notes_node)
workflow.add_node("research_verify", research_verify_node)
workflow.add_node("fact_check", fact_check_sei_node)

# Register debate node based on feature flag
if USE_GRANULAR_DEBATE:
    # Assuming debate_granular_node is available or imported conditionally. 
    # If it was named differently in the original file, I might need to adjust.
    # Checking previous context, it seemed to use 'debate_granular_node' in the text I saw.
    # However, to be safe, I'll restrict it to what I saw in Step 55 view_file output.
    # It was: workflow.add_node("debate", debate_granular_node)
    workflow.add_node("debate", debate_granular_node)
    logger.info("📊 Graph: Using GRANULAR debate node (8-node sub-graph)")
else:
    workflow.add_node("debate", debate_all_sections_node)
    logger.info("📊 Graph: Using HYBRID debate node (calls generate_section_agent_mode_async)")

workflow.add_node("divergence_hil", divergence_hil_node)
workflow.add_node("section_hil", section_hil_node)

# Quality Pipeline nodes (v2.25)
workflow.add_node("quality_gate", quality_gate_node)
workflow.add_node("structural_fix", structural_fix_node)
workflow.add_node("targeted_patch", targeted_patch_node)
workflow.add_node("gen_quality_report", quality_report_node)

workflow.add_node("audit", audit_node)
workflow.add_node("evaluate_hil", evaluate_hil_node)  # Universal HIL Decision
workflow.add_node("propose_corrections", propose_corrections_node)
workflow.add_node("correction_hil", correction_hil_node)
workflow.add_node("final_committee_review", final_committee_review_node)  # v5.2: Holistic review
workflow.add_node("refine_document", refine_document_node)
workflow.add_node("style_check", style_check_node)
workflow.add_node("style_refine", style_refine_node)
workflow.add_node("document_gate", document_gate_node)
workflow.add_node("finalize_hil", finalize_hil_node)

# Entry
workflow.set_entry_point("gen_outline")

# Always go through outline_hil (no-op if not enabled)
workflow.add_edge("gen_outline", "outline_hil")

# Routing after outline approval
def research_router(state: DocumentState) -> Literal["deep_research", "web_search", "fact_check"]:
    if (state.get("audit_mode") or "").lower() == "sei_only":
        return "fact_check"
    if state.get("deep_research_enabled"):
        return "deep_research"
    if state.get("web_search_enabled"):
        return "web_search"
    return "fact_check"


def research_retry_router(state: DocumentState) -> Literal["deep_research", "web_search", "quality_gate"]:
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

# If Deep Research is done, do we still do Web Search?
# Current logic: deep_research -> debate
#                web_search -> debate
# They are mutually exclusive in the router's current 'if/elif' logic.
# If both are true, Deep Research wins (first if).
workflow.add_edge("deep_research", "research_notes_step")
workflow.add_edge("web_search", "research_notes_step")
workflow.add_edge("research_notes_step", "fact_check")
workflow.add_edge("fact_check", "debate")

# Main flow with Quality Pipeline (v2.25)
# debate → quality_gate → structural_fix → section_hil → divergence_hil → audit → targeted_patch → quality_report → evaluate_hil
workflow.add_edge("debate", "research_verify")
workflow.add_conditional_edges("research_verify", research_retry_router)
workflow.add_edge("quality_gate", "structural_fix")
workflow.add_edge("structural_fix", "section_hil")
workflow.add_edge("section_hil", "divergence_hil")
workflow.add_edge("divergence_hil", "audit")
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
    report = state.get("committee_review_report") or {}
    score = report.get("score")
    try:
        score_val = float(score) if score is not None else 0.0
    except Exception:
        score_val = 0.0
    target = float(state.get("target_final_score") or 0)
    rounds = int(state.get("refinement_round", 0) or 0)
    max_rounds = int(state.get("max_rounds", 0) or 0)

    if max_rounds and rounds >= max_rounds:
        return "style_check"
    if target and score_val >= target:
        return "style_check"
    if not target and not max_rounds:
        return "style_check"
    return "refine_document"

def document_gate_router(state: DocumentState) -> Literal["finalize_hil", "__end__"]:
    if state.get("document_gate_status") == "blocked":
        return "__end__"
    return "finalize_hil"

def style_check_router(state: DocumentState) -> Literal["style_refine", "document_gate"]:
    status = state.get("style_check_status")
    if status == "needs_refine":
        rounds = int(state.get("style_refine_round", 0) or 0)
        max_rounds = int(state.get("style_refine_max_rounds", 2) or 2)
        if max_rounds and rounds >= max_rounds:
            logger.warning("⚠️ Style refine max rounds reached; proceeding to document gate.")
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
workflow.add_node("proposal_debate", human_proposal_debate_node)

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
