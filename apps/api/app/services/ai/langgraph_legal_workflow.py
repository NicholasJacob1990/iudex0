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

from app.services.web_search_service import web_search_service
from app.services.ai.deep_research_service import deep_research_service
from app.services.job_manager import job_manager
from app.services.ai.audit_service import AuditService
from app.services.ai.hil_decision_engine import HILDecisionEngine, HILChecklist, hil_engine
from app.services.ai.model_registry import get_api_model_name, DEFAULT_JUDGE_MODEL, DEFAULT_DEBATE_MODELS

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
    use_multi_agent: bool
    thinking_level: str
    chat_personality: str
    target_pages: int
    min_pages: int
    max_pages: int
    
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
    # Deep Research UX (para SSE/UI)
    deep_research_thinking_steps: Optional[List[Dict[str, Any]]]
    deep_research_from_cache: Optional[bool]
    
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
    
    # Final
    final_markdown: str


# --- NODES ---

async def outline_node(state: DocumentState) -> DocumentState:
    """Generate document outline"""
    logger.info("📑 [Phase2] Generating Outline...")
    
    mode = state.get("mode", "PETICAO")
    
    # v5.0: Dynamic Outline Generation (Unification with CLI)
    try:
        from app.services.ai.gemini_drafter import GeminiDrafterWrapper
        # Initialize basic drafter for outline
        strategist_model = state.get("strategist_model") or state.get("judge_model") or "gemini-1.5-pro"
        drafter = GeminiDrafterWrapper(model_name=get_api_model_name(strategist_model))
        
        # Use the robust generate_outline from juridico_gemini logic
        outline = drafter.generate_outline(
            tipo_peca=mode,
            resumo_caso=state.get("input_text", "")[:4000],
            tese_usuario=state.get("tese", "")
        )
        
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


async def deep_research_node(state: DocumentState) -> DocumentState:
    """Deep Research based on outline"""
    if not state.get("deep_research_enabled"):
        return state
        
    logger.info("🧠 [Phase2] Deep Research...")
    
    sections_summary = "\n".join([f"- {s}" for s in state.get("outline", [])])
    query = f"""
Pesquisa jurídica para {state['mode']}.
TESE: {state['tese']}
CONTEXTO: {state['input_text'][:1500]}
SEÇÕES: {sections_summary}
"""
    
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
        
    logger.info("🌐 [Phase2] Web Search...")
    
    query = f"{state['tese']} jurisprudência {state['mode']}"
    results = await web_search_service.search(query, num_results=5)
    
    report = "\n".join([f"- {r.get('title')}: {r.get('body', '')[:200]}" for r in results])
    
    return {
        **state,
        "research_context": f"--- WEB SEARCH ---\n{report}\n",
        "research_sources": results
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

    # Initialize Drafter (Gemini Judge)
    drafter = None
    try:
        from app.services.ai.gemini_drafter import GeminiDrafterWrapper
        drafter = GeminiDrafterWrapper(model_name=get_api_model_name(judge_model))
        logger.info("✅ GeminiDrafterWrapper initialized")
    except ImportError as e:
        logger.warning(f"⚠️ GeminiDrafterWrapper not available: {e}. Will use internal fallback.")
    
    # State extraction
    outline = state.get("outline", [])
    research_context = state.get("research_context", "") or ""
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
        
        prompt_base = f"""
## SEÇÃO: {title}
## TIPO DE DOCUMENTO: {mode}
## TESE PRINCIPAL: {thesis}

{citation_instr}
{personality_instr}
{length_guidance}

### CONTEXTO FACTUAL (Extraído dos Autos):
{input_text[:2000]}

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
                    mode=mode,  # Unifica com prompts v2 (tipo de documento)
                    extra_agent_instructions="\n".join(
                        [part for part in [citation_instr, personality_instr] if part]
                    ).strip() or None,
                    system_instruction=system_instruction,
                    previous_sections=[
                        f"### {p.get('section_title','Seção')}\n{(p.get('merged_content','') or '')[:800]}"
                        for p in processed_sections[-6:]
                    ]  # Anticontradiction com trecho
                )
                
                # Store result with full observability
                processed_sections.append({
                    "section_title": title,
                    "merged_content": section_text,
                    "has_significant_divergence": bool(divergencias),
                    "divergence_details": divergencias or "",
                    "drafts": drafts or {},
                    "claims_requiring_citation": (drafts or {}).get("claims_requiring_citation", []) if isinstance(drafts, dict) else [],
                    "removed_claims": (drafts or {}).get("removed_claims", []) if isinstance(drafts, dict) else [],
                    "risk_flags": (drafts or {}).get("risk_flags", []) if isinstance(drafts, dict) else []
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
                    "drafts": {}
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
                        tese_usuario=thesis
                    )
                except Exception as e:
                    logger.warning(f"⚠️ Single-model robust generation failed: {e}. Falling back to simple.")
                    try:
                        simple_prompt = f"Redija a seção '{title}' para um documento do tipo {mode}.\n\nTese: {thesis}\n\nContexto: {input_text[:1500]}"
                        resp = drafter._generate_with_retry(simple_prompt)
                        if resp and resp.text:
                            fallback_content = resp.text
                    except:
                        pass
            
            processed_sections.append({
                "section_title": title,
                "merged_content": fallback_content,
                "has_significant_divergence": False,
                "divergence_details": "",
                "drafts": {}
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
        "divergence_summary": divergence_summary
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
    research_context = state.get("research_context", "") or ""
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
        
        prompt_base = f"""
## SEÇÃO: {title}
## TIPO DE DOCUMENTO: {mode}
## TESE PRINCIPAL: {thesis}

{citation_instr}
{length_guidance}

### CONTEXTO FACTUAL:
{input_text[:2000]}

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
                "risk_flags": result.get("risk_flags", []) or []
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
                "drafts": {}
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

    targets = state.get("hil_target_sections") or []
    if not targets:
        return {**state, "hil_section_payload": None}

    targets_set = set([t for t in targets if isinstance(t, str) and t.strip()])
    if not targets_set:
        return {**state, "hil_section_payload": None}

    processed = state.get("processed_sections", []) or []
    if not isinstance(processed, list) or not processed:
        return {**state, "hil_section_payload": None}

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
    
    GPT, Claude and Gemini review the entire document for:
    - Global coherence (contradictions between sections)
    - Logical flow (smooth transitions)
    - Thesis strength (persuasive narrative)
    
    The Judge (Gemini) synthesizes all reviews and produces final report.
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
    from app.services.ai.gemini_drafter import GeminiDrafterWrapper
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
    drafter = None
    
    try:
        gpt_client = init_openai_client()
        claude_client = init_anthropic_client()
        drafter = GeminiDrafterWrapper(model_name=get_api_model_name(judge_model))
    except Exception as e:
        logger.warning(f"⚠️ Could not initialize all clients for committee review: {e}")
    
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
    
    async def get_gemini_review():
        if not drafter:
            return None
        try:
            prompt = review_prompt_template.format(mode=mode, thesis=thesis, document=doc_excerpt)
            response = await asyncio.to_thread(drafter._generate_with_retry, prompt)
            if response and response.text:
                return {"agent": "Gemini", "response": response.text}
            return None
        except Exception as e:
            logger.warning(f"⚠️ Gemini review failed: {e}")
            return None
    
    # Run reviews in parallel
    try:
        results = await asyncio.gather(
            get_gpt_review(),
            get_claude_review(),
            get_gemini_review(),
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
        "markdown": f"""## Relatório do Comitê Final

**Agentes Participantes**: {", ".join(reviews.keys())}
**Nota Média**: {avg_score:.1f}/10
**Divergência entre agentes**: {"Sim" if score_disagreement else "Não"} (Δ {score_spread:.1f})
**Revisão Humana Obrigatória**: {"Sim" if requires_hil else "Não"}

### Problemas Identificados
{chr(10).join(f"- {p}" for p in all_problems[:5]) if all_problems else "Nenhum problema crítico identificado."}
"""
    }
    
    logger.info(f"✅ Committee Review Score: {avg_score:.1f}/10 (HIL: {requires_hil})")
    
    return {
        **state,
        "committee_review_report": committee_report,
        "quality_gate_force_hil": (
            requires_hil
            or score_disagreement
            or state.get("quality_gate_force_hil", False)
        )
    }



async def finalize_hil_node(state: DocumentState) -> DocumentState:
    """HIL Checkpoint: Final approval"""
    logger.info("🛑 [Phase2] HIL: Final Approval")

    force_hil = state.get("quality_gate_force_hil", False)

    if state.get("auto_approve_hil", False) and not force_hil:
        return {
            **state,
            "human_approved_final": True,
            "final_markdown": state.get("full_document", "")
        }
    
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
        return {**state, "human_approved_final": True, "final_markdown": final_md}
    
    return {**state, "human_approved_final": False, "human_edits": decision.get("instructions")}


# --- GRAPH DEFINITION ---

workflow = StateGraph(DocumentState)

# Nodes (renamed to avoid conflict with state keys)
workflow.add_node("gen_outline", outline_node)
workflow.add_node("outline_hil", outline_hil_node)
workflow.add_node("deep_research", deep_research_node)
workflow.add_node("web_search", web_search_node)

# Register debate node based on feature flag
if USE_GRANULAR_DEBATE:
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
workflow.add_node("finalize_hil", finalize_hil_node)

# Entry
workflow.set_entry_point("gen_outline")

# Routing after outline approval
def research_router(state: DocumentState) -> Literal["deep_research", "web_search", "debate"]:
    if state.get("deep_research_enabled"):
        return "deep_research"
    if state.get("web_search_enabled"):
        return "web_search"
    return "debate"

# Always go through outline_hil (no-op if not enabled)
workflow.add_edge("gen_outline", "outline_hil")
workflow.add_conditional_edges("outline_hil", research_router)
workflow.add_edge("deep_research", "debate")
workflow.add_edge("web_search", "debate")

# Main flow with Quality Pipeline (v2.25)
# debate → quality_gate → structural_fix → section_hil → divergence_hil → audit → targeted_patch → quality_report → evaluate_hil
workflow.add_edge("debate", "quality_gate")
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
workflow.add_edge("final_committee_review", "finalize_hil")  # v5.2: Committee review before final
workflow.add_edge("finalize_hil", END)

# Checkpointer
if SqliteSaver is not None:
    conn = sqlite3.connect(job_manager.db_path, check_same_thread=False)
    checkpointer = SqliteSaver(conn)
    logger.info("✅ LangGraph checkpointer: SqliteSaver")
else:
    checkpointer = MemorySaver()
    logger.warning("⚠️ LangGraph checkpointer: MemorySaver (SqliteSaver indisponível no ambiente)")

legal_workflow_app = workflow.compile(checkpointer=checkpointer)
