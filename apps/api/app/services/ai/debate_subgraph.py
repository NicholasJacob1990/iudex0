"""
Granular Debate Sub-Graph - Production Version

This is the fully granular LangGraph implementation of the multi-agent committee
with 8 distinct nodes corresponding to the 4 rounds of debate, plus a conditional
reflection loop if the quality score is below threshold.

R1: Parallel Drafts (GPT, Claude, Judge Blind)
R2: Cross-Critique (GPT critiques Claude, Claude critiques GPT)
R3: Revision (GPT and Claude revise based on critique)
R4: Judge Merge (model escolhido consolida todas as versões)
Conditional: check logic -> Retry R1 if score < 8

Each node can emit SSE events for real-time observability.
"""

from typing import TypedDict, Literal, Optional, List, Dict, Any, Tuple
from langgraph.graph import StateGraph, END
from loguru import logger
from jinja2 import Template
import asyncio
import os
import time
import json
import re

from app.services.ai.prompts.debate_prompts import (
    PROMPT_JUIZ,
    PROMPT_CRITICA,
    PROMPT_REVISAO,
    PROMPT_GPT_SYSTEM,
    PROMPT_CLAUDE_SYSTEM,
    PROMPT_GEMINI_BLIND_SYSTEM,
    PROMPT_GEMINI_JUDGE_SYSTEM,
    get_document_instructions
)
from app.services.ai.model_registry import (
    DEFAULT_DEBATE_MODELS,
    DEFAULT_JUDGE_MODEL,
    get_model_config,
    get_api_model_name,
)
from app.services.api_call_tracker import billing_context
from app.services.job_manager import job_manager


# =============================================================================
# STATE DEFINITION
# =============================================================================

class DebateSectionState(TypedDict):
    # Input
    section_title: str
    section_index: int
    prompt_base: str
    rag_context: str
    thesis: str
    mode: str
    previous_sections: List[str]  # Titles of sections already processed (anticontradiction)
    previous_sections_excerpts: Optional[str]  # Optional: short excerpts to avoid contradictions

    # Optional formatting/meta
    formatting_options: Optional[Dict[str, Any]]
    template_structure: Optional[str]
    job_id: Optional[str]
    
    # API Clients (injected)
    gpt_client: Any
    claude_client: Any
    drafter: Any
    gpt_model: str
    claude_model: str
    judge_model: str
    temperature: float
    
    # Reflection Control
    retries: int 
    max_retries: int
    judge_feedback: Optional[str]
    
    # R1: Parallel Drafts
    draft_gpt_v1: Optional[str]
    draft_claude_v1: Optional[str]
    draft_gemini_v1: Optional[str]
    
    # R2: Cross-Critique
    critique_gpt_to_claude: Optional[str]
    critique_claude_to_gpt: Optional[str]
    
    # R3: Revisions
    draft_gpt_v2: Optional[str]
    draft_claude_v2: Optional[str]
    
    # R4: Final
    merged_content: str
    divergencias: str
    claims_requiring_citation: List[Dict[str, Any]]
    removed_claims: List[Dict[str, Any]]
    risk_flags: List[str]
    quality_score: int # 0-10
    retry_reason: Optional[str]
    
    # Metrics
    metrics: Dict[str, Any]
    
    # All drafts for observability
    drafts: Dict[str, str]


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

async def call_gpt_async(
    client,
    prompt: str,
    model: str,
    system: str = None,
    temperature: float = 0.3,
    *,
    billing_node: Optional[str] = None,
    billing_size: Optional[str] = None,
) -> str:
    """Call GPT with timeout and error handling"""
    from app.services.ai.agent_clients import call_openai_async
    
    if system:
        prompt = f"{system}\n\n{prompt}"
    
    try:
        with billing_context(node=billing_node, size=billing_size):
            result = await call_openai_async(client, prompt, model=model, temperature=temperature, timeout=90)
            return result or ""
    except Exception as e:
        logger.error(f"GPT call failed: {e}")
        return f"[GPT Error: {e}]"


async def call_claude_async(
    client,
    prompt: str,
    model: str,
    system: str = None,
    temperature: float = 0.3,
    *,
    billing_node: Optional[str] = None,
    billing_size: Optional[str] = None,
) -> str:
    """Call Claude with timeout and error handling"""
    from app.services.ai.agent_clients import call_anthropic_async
    
    if system:
        prompt = f"{system}\n\n{prompt}"
    
    try:
        with billing_context(node=billing_node, size=billing_size):
            result = await call_anthropic_async(client, prompt, model=model, temperature=temperature, timeout=90)
            return result or ""
    except Exception as e:
        logger.error(f"Claude call failed: {e}")
        return f"[Claude Error: {e}]"


async def _call_model_any_async(
    model_id: str,
    prompt: str,
    *,
    system_instruction: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: int = 2000,
    billing_node: Optional[str] = None,
    billing_size: Optional[str] = None,
) -> str:
    if not model_id:
        return ""

    cfg = get_model_config(model_id)
    if not cfg:
        return ""

    from app.services.ai.agent_clients import (
        init_openai_client,
        init_anthropic_client,
        init_xai_client,
        init_openrouter_client,
        get_gemini_client,
        call_openai_async,
        call_anthropic_async,
        call_vertex_gemini_async,
    )

    api_model = get_api_model_name(model_id)

    if cfg.provider == "openai":
        client = init_openai_client()
        if not client:
            return ""
        with billing_context(node=billing_node, size=billing_size):
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
        with billing_context(node=billing_node, size=billing_size):
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
        with billing_context(node=billing_node, size=billing_size):
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
        with billing_context(node=billing_node, size=billing_size):
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
        with billing_context(node=billing_node, size=billing_size):
            return await call_openai_async(
                client,
                prompt,
                model=api_model,
                max_tokens=max_tokens,
                temperature=temperature,
                system_instruction=system_instruction
            ) or ""
    return ""

def _resolve_temperatures(state: DebateSectionState) -> Tuple[float, float]:
    try:
        base = float(state.get("temperature", 0.3))
    except (TypeError, ValueError):
        base = 0.3
    base = max(0.0, min(1.0, base))
    return base, min(base, 0.3)


# =============================================================================
# R1: PARALLEL DRAFTS
# =============================================================================

async def gpt_draft_v1_node(state: DebateSectionState) -> DebateSectionState:
    """R1: GPT generates initial draft (Critic perspective)"""
    logger.info(f"🤖 [R1-GPT] Drafting: {state['section_title']} (Retry: {state['retries']})")
    if state.get("job_id"):
        job_manager.emit_event(
            state.get("job_id"),
            "section_stage",
            {"stage": "draft"},
            phase="debate",
            section=state.get("section_title"),
            agent="gpt",
        )
    start = time.time()
    draft_temperature, review_temperature = _resolve_temperatures(state)
    
    # Get document type specific instructions
    instrucoes = get_document_instructions(state['mode'])
    
    # Inject document type into system prompt
    t_sys = Template(PROMPT_GPT_SYSTEM)
    system = t_sys.render(tipo_documento=state['mode'], instrucoes=instrucoes)
    
    prompt = f"{state['prompt_base']}"
    
    # Inject Judge Feedback if retrying
    if state.get("judge_feedback") and state['retries'] > 0:
        prompt += f"\n\n## FEEDBACK DA TENTATIVA ANTERIOR (IMPORTANTE):\n{state['judge_feedback']}\nCorrija os pontos acima prioritariamente."
        
    draft = await call_gpt_async(
        state['gpt_client'], 
        prompt, 
        state.get('gpt_model', 'gpt-4o'),
        system=system,
        temperature=draft_temperature,
        billing_node="section_draft",
        billing_size="M",
    )
    
    latency = int((time.time() - start) * 1000)
    logger.info(f"✅ [R1-GPT] Done in {latency}ms")
    
    return {
        **state,
        "draft_gpt_v1": draft,
        "metrics": {**state.get("metrics", {}), "r1_gpt_latency": latency}
    }


async def claude_draft_v1_node(state: DebateSectionState) -> DebateSectionState:
    """R1: Claude generates initial draft (Defense perspective)"""
    logger.info(f"🤖 [R1-Claude] Drafting: {state['section_title']} (Retry: {state['retries']})")
    if state.get("job_id"):
        job_manager.emit_event(
            state.get("job_id"),
            "section_stage",
            {"stage": "draft"},
            phase="debate",
            section=state.get("section_title"),
            agent="claude",
        )
    start = time.time()
    draft_temperature, review_temperature = _resolve_temperatures(state)
    
    instrucoes = get_document_instructions(state['mode'])
    t_sys = Template(PROMPT_CLAUDE_SYSTEM)
    system = t_sys.render(tipo_documento=state['mode'], instrucoes=instrucoes)
    
    prompt = f"{state['prompt_base']}"
    
    # Inject Judge Feedback if retrying
    if state.get("judge_feedback") and state['retries'] > 0:
        prompt += f"\n\n## FEEDBACK DA TENTATIVA ANTERIOR (IMPORTANTE):\n{state['judge_feedback']}\nCorrija os pontos acima prioritariamente."
    
    draft = await call_claude_async(
        state['claude_client'], 
        prompt, 
        state.get('claude_model', 'claude-4.5-sonnet'),
        system=system,
        temperature=draft_temperature,
        billing_node="section_draft",
        billing_size="M",
    )
    
    latency = int((time.time() - start) * 1000)
    logger.info(f"✅ [R1-Claude] Done in {latency}ms")
    
    return {
        **state,
        "draft_claude_v1": draft,
        "metrics": {**state.get("metrics", {}), "r1_claude_latency": latency}
    }


async def gemini_blind_node(state: DebateSectionState) -> DebateSectionState:
    """R1: Judge generates independent draft (Blind Judge - doesn't see others)"""
    logger.info(f"🤖 [R1-Judge] Blind Draft: {state['section_title']}")
    if state.get("job_id"):
        job_manager.emit_event(
            state.get("job_id"),
            "section_stage",
            {"stage": "draft"},
            phase="debate",
            section=state.get("section_title"),
            agent="judge",
        )
    start = time.time()
    draft_temperature, review_temperature = _resolve_temperatures(state)
    
    # Judge (Blind) usually runs once; we re-run with feedback to align with retries.
    
    instrucoes = get_document_instructions(state['mode'])
    t_sys = Template(PROMPT_GEMINI_BLIND_SYSTEM)
    system = t_sys.render(tipo_documento=state['mode'], instrucoes=instrucoes)
    
    prompt_content = state['prompt_base']
    if state.get("judge_feedback") and state['retries'] > 0:
         prompt_content += f"\n\n## FEEDBACK DA TENTATIVA ANTERIOR (IMPORTANTE):\n{state['judge_feedback']}\nCorrija os pontos acima prioritariamente."

    judge_model = state.get("judge_model") or DEFAULT_JUDGE_MODEL
    draft = await _call_model_any_async(
        judge_model,
        prompt_content,
        system_instruction=system,
        temperature=draft_temperature,
        max_tokens=2000,
        billing_node="section_draft",
        billing_size="M",
    )
    
    latency = int((time.time() - start) * 1000)
    logger.info(f"✅ [R1-Judge] Done in {latency}ms")
    
    return {
        **state,
        "draft_gemini_v1": draft,
        "metrics": {**state.get("metrics", {}), "r1_gemini_latency": latency}
    }


# =============================================================================
# R2: CROSS-CRITIQUE
# =============================================================================

async def gpt_critique_node(state: DebateSectionState) -> DebateSectionState:
    """R2: GPT critiques Claude's draft"""
    logger.info(f"💬 [R2-GPT] Critiquing Claude's draft")
    if state.get("job_id"):
        job_manager.emit_event(
            state.get("job_id"),
            "section_stage",
            {"stage": "critique"},
            phase="debate",
            section=state.get("section_title"),
            agent="gpt",
        )
    start = time.time()
    draft_temperature, review_temperature = _resolve_temperatures(state)
    
    instrucoes = get_document_instructions(state['mode'])
    t = Template(PROMPT_CRITICA)
    prompt = t.render(
        texto_colega=state.get("draft_claude_v1", ""),
        rag_context=state.get("rag_context", ""),
        tipo_documento=state['mode'],
        tese=state.get('thesis', ''),
        instrucoes=instrucoes
    )
    
    critique = await call_gpt_async(
        state['gpt_client'], 
        prompt, 
        state.get('gpt_model', 'gpt-4o'),
        temperature=review_temperature,
        billing_node="section_critique",
        billing_size="M",
    )
    
    latency = int((time.time() - start) * 1000)
    logger.info(f"✅ [R2-GPT] Critique done in {latency}ms")
    
    return {
        **state,
        "critique_gpt_to_claude": critique,
        "metrics": {**state.get("metrics", {}), "r2_gpt_latency": latency}
    }


async def claude_critique_node(state: DebateSectionState) -> DebateSectionState:
    """R2: Claude critiques GPT's draft"""
    logger.info(f"💬 [R2-Claude] Critiquing GPT's draft")
    if state.get("job_id"):
        job_manager.emit_event(
            state.get("job_id"),
            "section_stage",
            {"stage": "critique"},
            phase="debate",
            section=state.get("section_title"),
            agent="claude",
        )
    start = time.time()
    draft_temperature, review_temperature = _resolve_temperatures(state)
    
    instrucoes = get_document_instructions(state['mode'])
    t = Template(PROMPT_CRITICA)
    prompt = t.render(
        texto_colega=state.get("draft_gpt_v1", ""),
        rag_context=state.get("rag_context", ""),
        tipo_documento=state['mode'],
        tese=state.get('thesis', ''),
        instrucoes=instrucoes
    )
    
    critique = await call_claude_async(
        state['claude_client'], 
        prompt, 
        state.get('claude_model', 'claude-4.5-sonnet'),
        temperature=review_temperature,
        billing_node="section_critique",
        billing_size="M",
    )
    
    latency = int((time.time() - start) * 1000)
    logger.info(f"✅ [R2-Claude] Critique done in {latency}ms")
    
    return {
        **state,
        "critique_claude_to_gpt": critique,
        "metrics": {**state.get("metrics", {}), "r2_claude_latency": latency}
    }


# =============================================================================
# R3: REVISION
# =============================================================================

async def gpt_revise_node(state: DebateSectionState) -> DebateSectionState:
    """R3: GPT revises its draft based on Claude's critique"""
    logger.info(f"✏️ [R3-GPT] Revising based on Claude's critique")
    if state.get("job_id"):
        job_manager.emit_event(
            state.get("job_id"),
            "section_stage",
            {"stage": "revise"},
            phase="debate",
            section=state.get("section_title"),
            agent="gpt",
        )
    start = time.time()
    draft_temperature, review_temperature = _resolve_temperatures(state)
    
    instrucoes = get_document_instructions(state['mode'])
    t = Template(PROMPT_REVISAO)
    prompt = t.render(
        texto_original=state.get("draft_gpt_v1", ""),
        critica_recebida=state.get("critique_claude_to_gpt", ""),
        rag_context=state.get("rag_context", ""),
        tipo_documento=state['mode'],
        tese=state.get('thesis', ''),
        instrucoes=instrucoes
    )
    
    revised = await call_gpt_async(
        state['gpt_client'], 
        prompt, 
        state.get('gpt_model', 'gpt-4o'),
        temperature=draft_temperature,
        billing_node="section_revision",
        billing_size="M",
    )
    
    latency = int((time.time() - start) * 1000)
    logger.info(f"✅ [R3-GPT] Revision done in {latency}ms")
    
    return {
        **state,
        "draft_gpt_v2": revised,
        "metrics": {**state.get("metrics", {}), "r3_gpt_latency": latency}
    }


async def claude_revise_node(state: DebateSectionState) -> DebateSectionState:
    """R3: Claude revises its draft based on GPT's critique"""
    logger.info(f"✏️ [R3-Claude] Revising based on GPT's critique")
    if state.get("job_id"):
        job_manager.emit_event(
            state.get("job_id"),
            "section_stage",
            {"stage": "revise"},
            phase="debate",
            section=state.get("section_title"),
            agent="claude",
        )
    start = time.time()
    draft_temperature, review_temperature = _resolve_temperatures(state)
    
    instrucoes = get_document_instructions(state['mode'])
    t = Template(PROMPT_REVISAO)
    prompt = t.render(
        texto_original=state.get("draft_claude_v1", ""),
        critica_recebida=state.get("critique_gpt_to_claude", ""),
        rag_context=state.get("rag_context", ""),
        tipo_documento=state['mode'],
        tese=state.get('thesis', ''),
        instrucoes=instrucoes
    )
    
    revised = await call_claude_async(
        state['claude_client'], 
        prompt, 
        state.get('claude_model', 'claude-4.5-sonnet'),
        temperature=draft_temperature,
        billing_node="section_revision",
        billing_size="M",
    )
    
    latency = int((time.time() - start) * 1000)
    logger.info(f"✅ [R3-Claude] Revision done in {latency}ms")
    
    return {
        **state,
        "draft_claude_v2": revised,
        "metrics": {**state.get("metrics", {}), "r3_claude_latency": latency}
    }


# =============================================================================
# R4: JUDGE MERGE
# =============================================================================

async def judge_merge_node(state: DebateSectionState) -> DebateSectionState:
    """R4: Judge model consolidates all versions"""
    judge_model = state.get("judge_model", "claude-4.5-opus")
    logger.info(f"⚖️ [R4-Judge] Consolidating: {state['section_title']} using {judge_model}")
    if state.get("job_id"):
        job_manager.emit_event(
            state.get("job_id"),
            "section_stage",
            {"stage": "merge"},
            phase="debate",
            section=state.get("section_title"),
            agent="judge",
        )
    start = time.time()
    draft_temperature, review_temperature = _resolve_temperatures(state)
    
    instrucoes = get_document_instructions(state['mode'])
    
    # Build previous sections context
    excerpts = state.get("previous_sections_excerpts")
    if excerpts:
        secoes_anteriores = excerpts
    else:
        prev_sections = state.get('previous_sections', [])
        secoes_anteriores = "\n".join([f"- {s}" for s in prev_sections]) if prev_sections else "(Esta é a primeira seção)"

    # Formatting directives
    formatting_options = state.get("formatting_options") or {}
    diretrizes_formatacao = ""
    if formatting_options:
        if formatting_options.get("include_toc"):
            diretrizes_formatacao += "- Incluir sumário (TOC) quando aplicável.\n"
        if formatting_options.get("include_summaries"):
            diretrizes_formatacao += "- Incluir resumos curtos no início de seções principais.\n"
        if formatting_options.get("include_summary_table"):
            diretrizes_formatacao += "- Incluir tabela de síntese ao final.\n"
    if not diretrizes_formatacao:
        diretrizes_formatacao = "(sem diretrizes adicionais)"
    modelo_estrutura = state.get("template_structure") or "(sem modelo de estrutura)"
    
    t = Template(PROMPT_JUIZ)
    prompt = t.render(
        titulo_secao=state['section_title'],
        tese=state.get('thesis', ''),
        secoes_anteriores=secoes_anteriores,
        versao_a=state.get("draft_gpt_v2", state.get("draft_gpt_v1", "")),
        versao_b=state.get("draft_claude_v2", state.get("draft_claude_v1", "")),
        versao_c=state.get("draft_gemini_v1", ""),
        rag_context=state.get("rag_context", ""),
        tipo_documento=state['mode'],
        instrucoes=instrucoes,
        diretrizes_formatacao=diretrizes_formatacao,
        modelo_estrutura=modelo_estrutura
    )
    
    # Use Judge system prompt
    t_sys = Template(PROMPT_GEMINI_JUDGE_SYSTEM)  # Reusing judge system prompt base
    system = t_sys.render(tipo_documento=state['mode'], instrucoes=instrucoes)
    
    merged = await _call_model_any_async(
        judge_model,
        prompt,
        system_instruction=system,
        temperature=review_temperature,
        max_tokens=2000,
        billing_node="section_judge",
        billing_size="S",
    )
    
    # Parse JSON
    final_content = ""
    divergencias = ""
    claims_requiring_citation: List[Dict[str, Any]] = []
    removed_claims: List[Dict[str, Any]] = []
    risk_flags: List[str] = []
    quality_score = 10 # Default optimistic
    quality_score_source = "heuristic"
    judge_feedback_text = ""
    retry_reason = ""

    def _extract_json(text: str) -> Optional[dict]:
        if not text: return None
        s = text.strip()
        if s.startswith("```"):
            s = re.sub(r"^```(json)?", "", s, flags=re.IGNORECASE).strip()
            s = re.sub(r"```$", "", s).strip()
        try:
            return json.loads(s)
        except Exception:
            # Try regex
            m = re.search(r"\{[\s\S]*\}", s)
            if m:
                try: 
                    return json.loads(m.group(0))
                except: 
                    pass
            return None

    parsed = _extract_json(merged)
    
    if isinstance(parsed, dict) and parsed.get("final_text"):
        final_content = parsed.get("final_text", "") or ""
        divs = parsed.get("divergences") or []
        if isinstance(divs, list) and divs:
            divergencias = json.dumps(divs, ensure_ascii=False, indent=2)
            
        claims_requiring_citation = parsed.get("claims_requiring_citation") or []
        removed_claims = parsed.get("removed_claims") or []
        risk_flags = parsed.get("risk_flags") or []
        
        parsed_score = parsed.get("quality_score")
        if isinstance(parsed_score, (int, float)):
            quality_score = max(0, min(10, int(round(parsed_score))))
            quality_score_source = "judge"
        else:
            quality_score = 5
            quality_score_source = "missing"
            judge_feedback_text = "Quality score ausente no JSON do juiz."
            retry_reason = "missing_quality_score"

            # Infer quality from risk flags and missing citations
            penalty = 0
            if claims_requiring_citation:
                penalty += 1
            if removed_claims:
                penalty += 1
            if risk_flags:
                penalty += len(risk_flags)
            quality_score = min(quality_score, max(0, 10 - penalty))

        if risk_flags or claims_requiring_citation:
            retry_reason = (
                f"risk_flags={len(risk_flags)}, missing_citations={len(claims_requiring_citation)}"
            )
            if risk_flags or claims_requiring_citation:
                judge_feedback_text = (
                    f"Riscos identificados: {', '.join(risk_flags)}. "
                    f"Citações faltantes: {len(claims_requiring_citation)}."
                )
            
    else:
        # Legacy fallback
        final_content = merged
        quality_score = 5 # Penalize format failure
        quality_score_source = "format_error"
        judge_feedback_text = "Falha na formatação JSON do output final."
        retry_reason = "invalid_json"
        if "### VERSÃO FINAL" in merged:
            parts = merged.split("### VERSÃO FINAL")
            if len(parts) > 1:
                final_content = parts[1].split("###")[0].strip()
            if "### LOG DE DIVERGÊNCIAS" in merged:
                parts = merged.split("### LOG DE DIVERGÊNCIAS")
                if len(parts) > 1:
                    divergencias = parts[1].split("###")[0].strip()
    
    latency = int((time.time() - start) * 1000)
    logger.info(f"✅ [R4-Judge] Done in {latency}ms (Score: {quality_score}/10)")
    
    # Collect all drafts
    all_drafts = {
        "gpt_v1": state.get("draft_gpt_v1", ""),
        "claude_v1": state.get("draft_claude_v1", ""),
        "gemini_v1": state.get("draft_gemini_v1", ""),
        "gpt_v2": state.get("draft_gpt_v2", ""),
        "claude_v2": state.get("draft_claude_v2", ""),
        "critique_gpt": state.get("critique_gpt_to_claude", ""),
        "critique_claude": state.get("critique_claude_to_gpt", "")
    }
    
    return {
        **state,
        "merged_content": final_content,
        "divergencias": divergencias,
        "claims_requiring_citation": claims_requiring_citation if isinstance(claims_requiring_citation, list) else [],
        "removed_claims": removed_claims if isinstance(removed_claims, list) else [],
        "risk_flags": risk_flags if isinstance(risk_flags, list) else [],
        "drafts": all_drafts,
        "quality_score": quality_score,
        "retry_reason": retry_reason or None,
        "judge_feedback": judge_feedback_text,
        "metrics": {
            **state.get("metrics", {}),
            "r4_judge_latency": latency,
            "quality_score": quality_score,
            "quality_score_source": quality_score_source,
            "retry_reason": retry_reason or None,
        }
    }


# =============================================================================
# CONDITIONAL LOGIC
# =============================================================================

def should_retry(state: DebateSectionState) -> Literal["prepare_retry", END]:
    """
    Decides whether to retry the draft loop based on quality score.
    Target: Score >= 8/10
    Max Retries: 2 (3 runs total)
    """
    score = state.get("quality_score", 10)
    retries = state.get("retries", 0)
    max_retries = state.get("max_retries", 2) # Default 2 retries (3 runs total)
    try:
        min_quality = int(os.getenv("DEBATE_MIN_QUALITY", "8"))
    except ValueError:
        min_quality = 8
    min_quality = max(0, min(10, min_quality))
    
    if score < min_quality and retries < max_retries:
        reason = state.get("retry_reason") or "quality_below_threshold"
        logger.warning(
            f"🔄 Low quality score ({score}/10 < {min_quality}). Retrying... "
            f"(Attempt {retries + 2}/{max_retries+1}) reason={reason}"
        )
        # Increment retries in the state update (LangGraph usually handles this in the node return, 
        # but for conditional edge, we need to modify state in the next node or update it here if possible. 
        # Since conditional edges just return the route, we rely on the next node to see the count, 
        # BUT we need to increment it. 
        # HACK: We can't update state here. We will add a 'setup_retry' node or just rely on the next draft node to increment?
        # Better: We add a pass-through node 'prepare_retry' to increment counter.
        return "prepare_retry"
    
    return END

def prepare_retry_node(state: DebateSectionState) -> DebateSectionState:
    """Updates retry counter and clears previous drafts for clean run (optional)"""
    return {
        **state,
        "retries": state.get("retries", 0) + 1,
        # We keep drafts for history in 'drafts' dict, but might clear current slots?
        # Actually better to overwrite them in next nodes.
    }

# =============================================================================
# SUB-GRAPH DEFINITION
# =============================================================================

def create_debate_subgraph() -> StateGraph:
    """
    Creates the full granular debate sub-graph with reflection loop.
    """
    
    workflow = StateGraph(DebateSectionState)
    
    # R1: Drafts
    workflow.add_node("gpt_v1", gpt_draft_v1_node)
    workflow.add_node("claude_v1", claude_draft_v1_node)
    workflow.add_node("gemini_v1", gemini_blind_node)
    
    # R2: Critiques
    workflow.add_node("gpt_critique", gpt_critique_node)
    workflow.add_node("claude_critique", claude_critique_node)
    
    # R3: Revisions
    workflow.add_node("gpt_v2", gpt_revise_node)
    workflow.add_node("claude_v2", claude_revise_node)
    
    # R4: Judge
    workflow.add_node("judge", judge_merge_node)
    
    # Retry Setup
    workflow.add_node("prepare_retry", prepare_retry_node)
    
    # Edges
    workflow.set_entry_point("gpt_v1")
    
    # Parallel simulation (sequential execution)
    workflow.add_edge("gpt_v1", "claude_v1")
    workflow.add_edge("claude_v1", "gemini_v1")
    workflow.add_edge("gemini_v1", "gpt_critique")
    
    workflow.add_edge("gpt_critique", "claude_critique")
    workflow.add_edge("claude_critique", "gpt_v2")
    workflow.add_edge("gpt_v2", "claude_v2")
    workflow.add_edge("claude_v2", "judge")
    
    # Conditional Edge from Judge
    workflow.add_conditional_edges(
        "judge",
        should_retry,
        {
            "prepare_retry": "prepare_retry",
            END: END
        }
    )
    
    workflow.add_edge("prepare_retry", "gpt_v1")
    
    return workflow


# Compiled sub-graph
debate_section_subgraph = create_debate_subgraph().compile()


# =============================================================================
# CONVENIENCE FUNCTION
# =============================================================================

async def run_debate_for_section(
    section_title: str,
    section_index: int,
    prompt_base: str,
    rag_context: str,
    thesis: str,
    mode: str,
    gpt_client,
    claude_client,
    drafter,
    gpt_model: str = "gpt-4o",
    claude_model: str = "claude-4.5-sonnet", # Updated default
    judge_model: str = "claude-4.5-opus",    # Updated default
    temperature: float = 0.3,
    previous_sections: List[str] = None,  
    previous_sections_excerpts: Optional[str] = None,
    formatting_options: Optional[Dict[str, Any]] = None,
    template_structure: Optional[str] = None,
    max_retries: Optional[int] = None,
    job_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Convenience function to run the full debate for one section.
    Returns the final state with merged_content, divergencias, and drafts.
    """

    max_retries_value = 2
    if max_retries is not None:
        try:
            max_retries_value = max(0, int(max_retries))
        except (TypeError, ValueError):
            max_retries_value = 2
    
    initial_state = DebateSectionState(
        section_title=section_title,
        section_index=section_index,
        prompt_base=prompt_base,
        rag_context=rag_context,
        thesis=thesis,
        mode=mode,
        previous_sections=previous_sections or [],
        previous_sections_excerpts=previous_sections_excerpts,
        formatting_options=formatting_options,
        template_structure=template_structure,
        job_id=job_id,
        gpt_client=gpt_client,
        claude_client=claude_client,
        drafter=drafter,
        gpt_model=gpt_model,
        claude_model=claude_model,
        judge_model=judge_model,
        temperature=temperature,
        retries=0,
        max_retries=max_retries_value, # Allow N retries (total N+1 attempts)
        judge_feedback=None,
        retry_reason=None,
        draft_gpt_v1=None,
        draft_claude_v1=None,
        draft_gemini_v1=None,
        critique_gpt_to_claude=None,
        critique_claude_to_gpt=None,
        draft_gpt_v2=None,
        draft_claude_v2=None,
        merged_content="",
        divergencias="",
        claims_requiring_citation=[],
        removed_claims=[],
        risk_flags=[],
        quality_score=0,
        metrics={},
        drafts={}
    )
    
    result = await debate_section_subgraph.ainvoke(initial_state)
    
    return {
        "section_title": section_title,
        "merged_content": result.get("merged_content", ""),
        "divergencias": result.get("divergencias", ""),
        "claims_requiring_citation": result.get("claims_requiring_citation", []) or [],
        "removed_claims": result.get("removed_claims", []) or [],
        "risk_flags": result.get("risk_flags", []) or [],
        "drafts": result.get("drafts", {}),
        "metrics": result.get("metrics", {})
    }
