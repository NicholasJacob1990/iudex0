"""
Granular Debate Sub-Graph - Production Version

This is the fully granular LangGraph implementation of the multi-agent committee
with 8 distinct nodes corresponding to the 4 rounds of debate:

R1: Parallel Drafts (GPT, Claude, Gemini Blind)
R2: Cross-Critique (GPT critiques Claude, Claude critiques GPT)
R3: Revision (GPT and Claude revise based on critique)
R4: Judge Merge (Gemini consolidates all versions)

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
    
    # API Clients (injected)
    gpt_client: Any
    claude_client: Any
    drafter: Any
    gpt_model: str
    claude_model: str
    
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
    
    # Metrics
    metrics: Dict[str, Any]
    
    # All drafts for observability
    drafts: Dict[str, str]


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

async def call_gpt_async(client, prompt: str, model: str, system: str = None) -> str:
    """Call GPT with timeout and error handling"""
    from app.services.ai.agent_clients import call_openai_async
    
    if system:
        prompt = f"{system}\n\n{prompt}"
    
    try:
        result = await call_openai_async(client, prompt, model=model, timeout=60)
        return result or ""
    except Exception as e:
        logger.error(f"GPT call failed: {e}")
        return f"[GPT Error: {e}]"


async def call_claude_async(client, prompt: str, model: str, system: str = None) -> str:
    """Call Claude with timeout and error handling"""
    from app.services.ai.agent_clients import call_anthropic_async
    
    if system:
        prompt = f"{system}\n\n{prompt}"
    
    try:
        result = await call_anthropic_async(client, prompt, model=model, timeout=60)
        return result or ""
    except Exception as e:
        logger.error(f"Claude call failed: {e}")
        return f"[Claude Error: {e}]"


def call_gemini_sync(drafter, prompt: str) -> str:
    """Call Gemini via drafter wrapper"""
    try:
        if drafter is None:
            return "[Gemini não disponível - drafter=None]"
        resp = drafter._generate_with_retry(prompt)
        return resp.text if resp else ""
    except Exception as e:
        logger.error(f"Gemini call failed: {e}")
        return f"[Gemini Error: {e}]"


# =============================================================================
# R1: PARALLEL DRAFTS
# =============================================================================

async def gpt_draft_v1_node(state: DebateSectionState) -> DebateSectionState:
    """R1: GPT generates initial draft (Critic perspective)"""
    logger.info(f"🤖 [R1-GPT] Drafting: {state['section_title']}")
    start = time.time()
    
    # Get document type specific instructions
    instrucoes = get_document_instructions(state['mode'])
    
    # Inject document type into system prompt
    t_sys = Template(PROMPT_GPT_SYSTEM)
    system = t_sys.render(tipo_documento=state['mode'], instrucoes=instrucoes)
    
    prompt = f"{state['prompt_base']}"
    draft = await call_gpt_async(
        state['gpt_client'], 
        prompt, 
        state.get('gpt_model', 'gpt-4o'),
        system=system
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
    logger.info(f"🤖 [R1-Claude] Drafting: {state['section_title']}")
    start = time.time()
    
    instrucoes = get_document_instructions(state['mode'])
    t_sys = Template(PROMPT_CLAUDE_SYSTEM)
    system = t_sys.render(tipo_documento=state['mode'], instrucoes=instrucoes)
    
    prompt = f"{state['prompt_base']}"
    draft = await call_claude_async(
        state['claude_client'], 
        prompt, 
        state.get('claude_model', 'claude-sonnet-4-20250514'),
        system=system
    )
    
    latency = int((time.time() - start) * 1000)
    logger.info(f"✅ [R1-Claude] Done in {latency}ms")
    
    return {
        **state,
        "draft_claude_v1": draft,
        "metrics": {**state.get("metrics", {}), "r1_claude_latency": latency}
    }


async def gemini_blind_node(state: DebateSectionState) -> DebateSectionState:
    """R1: Gemini generates independent draft (Blind Judge - doesn't see others)"""
    logger.info(f"🤖 [R1-Gemini] Blind Draft: {state['section_title']}")
    start = time.time()
    
    instrucoes = get_document_instructions(state['mode'])
    t_sys = Template(PROMPT_GEMINI_BLIND_SYSTEM)
    system = t_sys.render(tipo_documento=state['mode'], instrucoes=instrucoes)
    
    prompt = f"{system}\n\n{state['prompt_base']}"
    draft = call_gemini_sync(state['drafter'], prompt)
    
    latency = int((time.time() - start) * 1000)
    logger.info(f"✅ [R1-Gemini] Done in {latency}ms")
    
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
    start = time.time()
    
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
        state.get('gpt_model', 'gpt-4o')
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
    start = time.time()
    
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
        state.get('claude_model', 'claude-sonnet-4-20250514')
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
    start = time.time()
    
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
        state.get('gpt_model', 'gpt-4o')
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
    start = time.time()
    
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
        state.get('claude_model', 'claude-sonnet-4-20250514')
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
    """R4: Gemini Judge consolidates all versions"""
    logger.info(f"⚖️ [R4-Judge] Consolidating: {state['section_title']}")
    start = time.time()
    
    instrucoes = get_document_instructions(state['mode'])
    
    # Build previous sections context (prefer excerpts, fallback to titles)
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
        # Human-readable directives to reduce variability
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
    t_sys = Template(PROMPT_GEMINI_JUDGE_SYSTEM)
    system = t_sys.render(tipo_documento=state['mode'], instrucoes=instrucoes)
    
    full_prompt = f"{system}\n\n{prompt}"
    merged = call_gemini_sync(state['drafter'], full_prompt)
    
    # Parse JSON (v2) with robust fallback
    final_content = ""
    divergencias = ""
    claims_requiring_citation: List[Dict[str, Any]] = []
    removed_claims: List[Dict[str, Any]] = []
    risk_flags: List[str] = []

    def _extract_json(text: str) -> Optional[dict]:
        if not text:
            return None
        s = text.strip()
        # Remove code fences if any
        if s.startswith("```"):
            s = re.sub(r"^```(json)?", "", s, flags=re.IGNORECASE).strip()
            s = re.sub(r"```$", "", s).strip()
        # Try direct JSON
        try:
            return json.loads(s)
        except Exception:
            pass
        # Try to extract first JSON object
        m = re.search(r"\{[\s\S]*\}", s)
        if not m:
            return None
        try:
            return json.loads(m.group(0))
        except Exception:
            return None

    parsed = _extract_json(merged)
    if isinstance(parsed, dict) and parsed.get("final_text"):
        final_content = parsed.get("final_text", "") or ""
        # Keep divergences as compact markdown text (for UI), but preserve structured lists in state too
        divs = parsed.get("divergences") or []
        if isinstance(divs, list) and divs:
            divergencias = json.dumps(divs, ensure_ascii=False, indent=2)
        claims_requiring_citation = parsed.get("claims_requiring_citation") or []
        removed_claims = parsed.get("removed_claims") or []
        risk_flags = parsed.get("risk_flags") or []
    else:
        # Legacy fallback: treat as markdown with headers
        final_content = merged
        if "### VERSÃO FINAL" in merged:
            parts = merged.split("### VERSÃO FINAL")
            if len(parts) > 1:
                final_content = parts[1].split("###")[0].strip()
            if "### LOG DE DIVERGÊNCIAS" in merged:
                parts = merged.split("### LOG DE DIVERGÊNCIAS")
                if len(parts) > 1:
                    divergencias = parts[1].split("###")[0].strip()
    
    latency = int((time.time() - start) * 1000)
    logger.info(f"✅ [R4-Judge] Done in {latency}ms")
    
    # Collect all drafts for observability
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
        "metrics": {**state.get("metrics", {}), "r4_judge_latency": latency}
    }


# =============================================================================
# SUB-GRAPH DEFINITION
# =============================================================================

def create_debate_subgraph() -> StateGraph:
    """
    Creates the full 4-round debate sub-graph.
    
    Flow:
    R1: [gpt_v1, claude_v1, gemini_v1] (sequential for simplicity)
    R2: [gpt_critique, claude_critique] (sequential)
    R3: [gpt_v2, claude_v2] (sequential)
    R4: [judge]
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
    
    # Sequential edges (for reliability; parallel would use Send API)
    workflow.set_entry_point("gpt_v1")
    workflow.add_edge("gpt_v1", "claude_v1")
    workflow.add_edge("claude_v1", "gemini_v1")
    workflow.add_edge("gemini_v1", "gpt_critique")
    workflow.add_edge("gpt_critique", "claude_critique")
    workflow.add_edge("claude_critique", "gpt_v2")
    workflow.add_edge("gpt_v2", "claude_v2")
    workflow.add_edge("claude_v2", "judge")
    workflow.add_edge("judge", END)
    
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
    claude_model: str = "claude-sonnet-4-20250514",
    previous_sections: List[str] = None,  # Titles of already processed sections
    previous_sections_excerpts: Optional[str] = None,
    formatting_options: Optional[Dict[str, Any]] = None,
    template_structure: Optional[str] = None
) -> Dict[str, Any]:
    """
    Convenience function to run the full debate for one section.
    Returns the final state with merged_content, divergencias, and drafts.
    
    Args:
        previous_sections: List of section titles already processed (for anticontradiction)
    """
    
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
        gpt_client=gpt_client,
        claude_client=claude_client,
        drafter=drafter,
        gpt_model=gpt_model,
        claude_model=claude_model,
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
