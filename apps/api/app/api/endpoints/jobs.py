"""
Jobs API Endpoints - Phase 1 LangGraph Integration

Handles SSE streaming and HIL resume for the legal document workflow.
"""

from fastapi import APIRouter, Depends, HTTPException, Body
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from loguru import logger
import json
import asyncio
import uuid
import os
from typing import Dict, Any

from app.core.database import get_db
from app.models.document import Document
from app.services.job_manager import job_manager
from app.services.ai.langgraph_legal_workflow import legal_workflow_app, DocumentState
from app.services.ai.model_registry import (
    DEFAULT_JUDGE_MODEL,
    DEFAULT_DEBATE_MODELS,
    validate_model_id,
    validate_model_list,
)
try:
    from langgraph.types import Command
except ImportError:
    # Fallback for older LangGraph versions: create a stub Command
    # In older versions, resume is done by passing state updates directly
    class Command:
        """Compatibility stub for Command when not available."""
        def __init__(self, resume: Any = None, **kwargs):
            self.resume = resume
            self.kwargs = kwargs

router = APIRouter()

# --- SSE HELPER ---
def sse_event(data: dict, event: str = "message") -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"

def resolve_page_range(payload: dict) -> Dict[str, int]:
    min_pages = int(payload.get("min_pages") or 0)
    max_pages = int(payload.get("max_pages") or 0)

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
        target_pages = (min_pages + max_pages) // 2
    else:
        effort_level = int(payload.get("effort_level") or 0)
        target_pages = effort_level * 3 if effort_level else 0

    return {"min_pages": min_pages, "max_pages": max_pages, "target_pages": target_pages}

def _filter_local_rag_files(docs: list[Document]) -> list[str]:
    allowed_exts = {".pdf", ".txt", ".md"}
    paths: list[str] = []
    for doc in docs:
        path = getattr(doc, "url", None)
        if not path or not os.path.exists(path):
            continue
        _, ext = os.path.splitext(path)
        if ext.lower() in allowed_exts:
            paths.append(path)
    return paths

def _build_attachment_prompt_context(
    docs: list[Document],
    max_chars: int = 12000,
    per_doc_chars: int = 3000
) -> str:
    if not docs:
        return ""
    remaining = max_chars
    blocks: list[str] = []
    for doc in docs:
        text = (getattr(doc, "extracted_text", "") or "").strip()
        if not text:
            continue
        chunk = text[: min(per_doc_chars, remaining)]
        if not chunk:
            break
        blocks.append(f"[{doc.name}]\n{chunk}")
        remaining -= len(chunk)
        if remaining <= 0:
            break
    if not blocks:
        return ""
    return (
        "## CONTEXTO DOS ANEXOS (INJEÇÃO DIRETA)\n"
        "Use apenas fatos explícitos nos trechos abaixo. Não invente informações.\n\n"
        + "\n\n".join(blocks)
        + "\n\n## FIM DO CONTEXTO DOS ANEXOS"
    )

def _build_local_rag_context(
    docs: list[Document],
    query: str,
    tenant_id: str = "default",
    top_k: int = 5
) -> str:
    try:
        from rag_local import LocalProcessIndex
    except Exception as e:
        logger.warning(f"RAG Local indisponível: {e}")
        return ""

    file_paths = _filter_local_rag_files(docs)
    if not file_paths:
        return ""

    try:
        index = LocalProcessIndex(
            processo_id=f"upload-{uuid.uuid4()}",
            sistema="UPLOAD",
            tenant_id=tenant_id
        )
        for path in file_paths[:10]:
            index.index_documento(path)
        results = index.search(query, top_k=top_k)
    except Exception as e:
        logger.warning(f"Falha ao indexar anexos no RAG Local: {e}")
        return ""

    if not results:
        return ""

    lines = ["### 📁 FATOS DO PROCESSO (ANEXOS)"]
    for r in results:
        snippet = (r.get("text") or "")[:300].strip()
        citation = r.get("citacao") or "Documento"
        if snippet:
            lines.append(f"- {citation}: \"{snippet}...\"")
    return "\n".join(lines)

@router.get("/{jobid}/stream")
async def stream_job(jobid: str, db: AsyncSession = Depends(get_db)):
    """
    Endpoint SSE para streaming de eventos do LangGraph
    """
    logger.info(f"📡 Iniciando stream para Job {jobid}")
    
    async def event_generator():
        config = {"configurable": {"thread_id": jobid}}
        
        try:
            # Check if job exists
            current_state = legal_workflow_app.get_state(config)
            
            if not current_state.values:
                yield sse_event({"type": "info", "message": "Aguardando início do job..."}, event="status")
                return

            # Initial UX hints (helps frontend show "running" states deterministically)
            if bool(current_state.values.get("deep_research_enabled")):
                yield sse_event({"type": "deep_research_start"}, event="research")

            # Stream events
            async for event in legal_workflow_app.astream(None, config, stream_mode="updates"):
                logger.debug(f"Event: {event}")
                
                for node_name, node_output in event.items():
                    
                    if node_name == "outline":
                        yield sse_event({
                            "type": "outline_done", 
                            "outline": node_output.get("outline", [])
                        }, event="outline")
                    
                    elif node_name == "deep_research":
                        # Replay thinking steps (batch) if available
                        thinking_steps = node_output.get("deep_research_thinking_steps") or []
                        if isinstance(thinking_steps, list) and thinking_steps:
                            if bool(node_output.get("deep_research_from_cache")):
                                yield sse_event({"type": "cache_hit", "from_cache": True}, event="research")
                            for step in thinking_steps[:50]:
                                text = (step or {}).get("text") if isinstance(step, dict) else None
                                if text:
                                    yield sse_event({"type": "thinking", "text": text, "from_cache": bool(node_output.get("deep_research_from_cache"))}, event="research")

                        yield sse_event({
                            "type": "deep_research_done",
                            "sources_count": len(node_output.get("research_sources", [])),
                            "from_cache": bool(node_output.get("deep_research_from_cache", False)),
                        }, event="research")
                    
                    elif node_name == "web_search":
                        yield sse_event({
                            "type": "web_search_done",
                            "sources_count": len(node_output.get("research_sources", []))
                        }, event="research")
                    
                    elif node_name in ["debate_all", "debate"]:
                        sections = node_output.get("processed_sections", [])
                        
                        # Emit per-section events for granular visibility
                        for sec in sections:
                            pending = sec.get("claims_requiring_citation", []) or []
                            removed = sec.get("removed_claims", []) or []
                            risk_flags = sec.get("risk_flags", []) or []
                            divergencias = sec.get("divergence_details") or sec.get("divergencias") or ""

                            # Truncamento para SSE (evita payload gigante)
                            pending_list = pending if isinstance(pending, list) else []
                            removed_list = removed if isinstance(removed, list) else []
                            pending_list = pending_list[:25]
                            removed_list = removed_list[:25]
                            yield sse_event({
                                "type": "section_processed",
                                "section": sec.get("section_title"),
                                "has_divergence": sec.get("has_significant_divergence", False),
                                "drafts": sec.get("drafts", {}),  # Expose internal drafts
                                "pending_citations_count": len(pending) if isinstance(pending, list) else 0,
                                "removed_claims_count": len(removed) if isinstance(removed, list) else 0,
                                "risk_flags": risk_flags if isinstance(risk_flags, list) else [],
                                "claims_requiring_citation": pending_list,
                                "removed_claims": removed_list,
                                "divergence_details": divergencias
                            }, event="section")
                        
                        yield sse_event({
                            "type": "debate_done",
                            "sections_count": len(sections),
                            "has_divergence": node_output.get("has_any_divergence", False),
                            "divergence_summary": node_output.get("divergence_summary", ""),
                            "document_preview": node_output.get("full_document", "")[:1000]
                        }, event="debate")
                    
                    # Granular Node Handlers (Phase 4.3)
                    elif node_name == "gpt_v1":
                        yield sse_event({"type": "thinking", "agent": "GPT", "round": 1}, event="granular")
                    elif node_name == "claude_v1":
                        yield sse_event({"type": "thinking", "agent": "Claude", "round": 1}, event="granular")
                    elif node_name == "gemini_v1":
                        yield sse_event({"type": "thinking", "agent": "Gemini", "round": 1}, event="granular")
                    elif "critique" in node_name:
                        yield sse_event({"type": "critique", "agent": node_name}, event="granular")
                    elif "revise" in node_name:
                        yield sse_event({"type": "revision", "agent": node_name}, event="granular")
                    elif node_name == "judge":
                        yield sse_event({"type": "judging", "agent": "Gemini Judge"}, event="granular")

                    elif node_name == "audit":
                        yield sse_event({
                            "type": "audit_done",
                            "status": node_output.get("audit_status"),
                            "issues_count": len(node_output.get("audit_issues", [])),
                            "report": node_output.get("audit_report")
                        }, event="audit")

                    # Quality Pipeline (v2.25)
                    elif node_name == "quality_gate":
                        results = node_output.get("quality_gate_results", []) or []
                        yield sse_event({
                            "type": "quality_gate_done",
                            "passed": bool(node_output.get("quality_gate_passed", True)),
                            "force_hil": bool(node_output.get("quality_gate_force_hil", False)),
                            "results_count": len(results) if isinstance(results, list) else 0,
                            "results": results[:10] if isinstance(results, list) else [],
                        }, event="quality")

                    elif node_name == "structural_fix":
                        yield sse_event({
                            "type": "structural_fix_done",
                            "result": node_output.get("structural_fix_result", {}) or {},
                        }, event="quality")

                    elif node_name == "targeted_patch":
                        pr = node_output.get("patch_result", {}) or {}
                        details = node_output.get("patches_applied", []) or []
                        yield sse_event({
                            "type": "targeted_patch_done",
                            "used": bool(node_output.get("targeted_patch_used", False)),
                            "patch_result": pr,
                            "patches_applied": details[:15] if isinstance(details, list) else [],
                        }, event="quality")

                    elif node_name == "quality_report":
                        report = node_output.get("quality_report", {}) or {}
                        md = (node_output.get("quality_report_markdown") or "")
                        yield sse_event({
                            "type": "quality_report_done",
                            "report": report,
                            "markdown_preview": md[:4000] if isinstance(md, str) else "",
                        }, event="quality")
                    
                    elif node_name == "evaluate_hil":
                        hil_checklist = node_output.get("hil_checklist", {})
                        yield sse_event({
                            "type": "hil_evaluated",
                            "requires_hil": hil_checklist.get("requires_hil", False),
                            "hil_level": hil_checklist.get("hil_level", "none"),
                            "triggered_factors": hil_checklist.get("triggered_factors", []),
                            "score_confianca": hil_checklist.get("score_confianca", 1.0)
                        }, event="hil_decision")
                    
                    elif node_name == "propose_corrections":
                        yield sse_event({
                            "type": "corrections_proposed",
                            "has_corrections": bool(node_output.get("proposed_corrections")),
                            "diff_summary": node_output.get("corrections_diff", "")
                        }, event="corrections")

            # Check for interrupts (HIL checkpoints)
            final_snapshot = legal_workflow_app.get_state(config)
            
            if final_snapshot.tasks:
                # There's an interrupt waiting
                next_nodes = final_snapshot.next or []
                
                if "outline_hil" in str(next_nodes):
                    payload = final_snapshot.values.get("hil_outline_payload") or {}
                    outline = payload.get("outline") or final_snapshot.values.get("outline") or []
                    if not isinstance(outline, list):
                        outline = []
                    outline = [str(x) for x in outline if str(x).strip()]
                    hil_targets = final_snapshot.values.get("hil_target_sections") or []
                    yield sse_event({
                        "type": "human_review_required",
                        "checkpoint": "outline",
                        "job_id": jobid,
                        "review_data": {
                            "outline": outline,
                            "hil_target_sections": hil_targets
                        }
                    }, event="review")
                    return

                elif "section_hil" in str(next_nodes):
                    payload = final_snapshot.values.get("hil_section_payload") or {}
                    yield sse_event({
                        "type": "human_review_required",
                        "checkpoint": "section",
                        "job_id": jobid,
                        "review_data": {
                            "section_title": payload.get("section_title"),
                            "merged_content": payload.get("merged_content", "")[:8000],
                            "divergence_details": payload.get("divergence_details", ""),
                            "drafts": payload.get("drafts", {}) or {},
                            "document_preview": (payload.get("document_preview") or final_snapshot.values.get("full_document", "") or "")[:2000],
                        }
                    }, event="review")
                    return

                elif "divergence_check_hil" in str(next_nodes) or "divergence_hil" in str(next_nodes):
                    processed = final_snapshot.values.get("processed_sections", []) or []
                    divergencias_por_secao = []
                    if isinstance(processed, list):
                        for sec in processed:
                            if not isinstance(sec, dict):
                                continue
                            div_txt = sec.get("divergence_details") or ""
                            if div_txt:
                                divergencias_por_secao.append({
                                    "secao": sec.get("section_title", "Seção"),
                                    "divergencias": div_txt,
                                    "drafts": sec.get("drafts", {}) or {}
                                })
                    yield sse_event({
                        "type": "human_review_required",
                        "checkpoint": "divergence",
                        "job_id": jobid,
                        "review_data": {
                            "divergencias": divergencias_por_secao,
                            "document_preview": final_snapshot.values.get("full_document", "")[:2000]
                        }
                    }, event="review")
                    return
                
                elif "correction_hil" in str(next_nodes):
                    yield sse_event({
                        "type": "human_review_required",
                        "checkpoint": "correction",
                        "job_id": jobid,
                        "review_data": {
                            "original_document": final_snapshot.values.get("full_document", "")[:2000],
                            "proposed_corrections": final_snapshot.values.get("proposed_corrections", "")[:2000],
                            "corrections_diff": final_snapshot.values.get("corrections_diff", ""),
                            "audit_issues": final_snapshot.values.get("audit_issues", []),
                            "audit_status": final_snapshot.values.get("audit_status")
                        }
                    }, event="review")
                    return
                
                elif "finalize_hil" in str(next_nodes):
                    yield sse_event({
                        "type": "human_review_required",
                        "checkpoint": "final",
                        "job_id": jobid,
                        "review_data": {
                            "document": final_snapshot.values.get("full_document"),
                            "audit_status": final_snapshot.values.get("audit_status"),
                            "audit_report": final_snapshot.values.get("audit_report")
                        }
                    }, event="review")
                    return

            # Check if finished
            if not final_snapshot.next:
                yield sse_event({
                    "type": "done",
                    "markdown": final_snapshot.values.get("final_markdown")
                }, event="done")

        except Exception as e:
            logger.error(f"Stream error: {e}")
            yield sse_event({"type": "error", "message": str(e)}, event="error")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive"
        }
    )


@router.post("/start")
async def start_job(
    request: dict = Body(...),
    db: AsyncSession = Depends(get_db)
):
    """
    Inicia um novo Job LangGraph
    """
    jobid = str(uuid.uuid4())
    config = {"configurable": {"thread_id": jobid}}
    
    # Validate model ids early (clear 400 instead of silent fallback)
    try:
        judge_model = validate_model_id(request.get("judge_model", DEFAULT_JUDGE_MODEL), for_juridico=True, field_name="judge_model")
        gpt_model = validate_model_id(request.get("gpt_model", DEFAULT_DEBATE_MODELS[0] if DEFAULT_DEBATE_MODELS else "gpt-5.2"), for_agents=True, field_name="gpt_model")
        claude_model = validate_model_id(request.get("claude_model", DEFAULT_DEBATE_MODELS[1] if len(DEFAULT_DEBATE_MODELS) > 1 else "claude-4.5-sonnet"), for_agents=True, field_name="claude_model")
        strategist_model = request.get("strategist_model")
        if strategist_model:
            strategist_model = validate_model_id(strategist_model, for_agents=True, field_name="strategist_model")
        drafter_models = validate_model_list(request.get("drafter_models"), for_agents=True, field_name="drafter_models")
        reviewer_models = validate_model_list(request.get("reviewer_models"), for_agents=True, field_name="reviewer_models")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    page_range = resolve_page_range(request)

    prompt_text = request.get("prompt", "")
    attachment_mode = (request.get("attachment_mode") or "rag_local").lower()
    if attachment_mode not in ["rag_local", "prompt_injection"]:
        attachment_mode = "rag_local"

    attachment_prompt_context = ""
    attachment_rag_context = ""
    context_document_ids = request.get("context_documents") or []
    if context_document_ids:
        try:
            result = await db.execute(
                select(Document).where(Document.id.in_(context_document_ids))
            )
            docs = result.scalars().all()
        except Exception as e:
            logger.warning(f"Erro ao buscar documentos de contexto: {e}")
            docs = []

        if docs:
            if attachment_mode == "prompt_injection":
                attachment_prompt_context = _build_attachment_prompt_context(docs)
            else:
                attachment_rag_context = _build_local_rag_context(
                    docs=docs,
                    query=f"{request.get('document_type', '')}: {prompt_text[:800]}",
                    tenant_id="default"
                )

    if attachment_prompt_context:
        prompt_text = f"{prompt_text}\n\n{attachment_prompt_context}"

    # Initial State
    initial_state = {
        "input_text": prompt_text,
        "mode": request.get("document_type", "PETICAO"),
        "tese": request.get("thesis", ""),
        "job_id": jobid,
        "deep_research_enabled": bool(request.get("dense_research", False)),
        "web_search_enabled": bool(request.get("web_search", False)),
        "use_multi_agent": request.get("use_multi_agent", False),
        "thinking_level": request.get("reasoning_level", "medium"),
        "auto_approve_hil": False,
        "chat_personality": request.get("chat_personality", "juridico"),

        # Contexto para decisão HIL
        "destino": request.get("destino", "uso_interno"),
        "risco": request.get("risco", "baixo"),

        # Formatting/meta
        "formatting_options": request.get("formatting_options"),
        "template_structure": request.get("template_structure"),
        "citation_style": request.get("citation_style", "forense"),
        "target_pages": page_range["target_pages"],
        "min_pages": page_range["min_pages"],
        "max_pages": page_range["max_pages"],

        # v4.1: CRAG Gate & Adaptive Routing (keys used by langgraph_legal_workflow.py)
        "crag_gate_enabled": bool(request.get("crag_gate", False)),
        "adaptive_routing_enabled": bool(request.get("adaptive_routing", False)),
        "crag_min_best_score": float(request.get("crag_min_best_score", 0.45)),
        "crag_min_avg_score": float(request.get("crag_min_avg_score", 0.35)),
        # Extra flags (kept for forward-compat/UI)
        "hyde_enabled": bool(request.get("hyde_enabled", False)),
        "graph_rag_enabled": bool(request.get("graph_rag_enabled", False)),
        "graph_hops": int(request.get("graph_hops", 1) or 1),
        
        # Initialize empty collections
        "outline": [],
        "processed_sections": [],
        "full_document": "",
        "research_context": attachment_rag_context or None,
        "research_sources": [],
        "deep_research_thinking_steps": [],
        "deep_research_from_cache": False,
        "has_any_divergence": False,
        "divergence_summary": "",
        "audit_status": "aprovado",
        "audit_report": None,
        "audit_issues": [],
        "hil_checklist": None,

        # Correções / HIL
        "proposed_corrections": None,
        "corrections_diff": None,
        "human_approved_corrections": False,

        # Quality Pipeline (v2.25)
        "quality_gate_passed": True,
        "quality_gate_results": [],
        "quality_gate_force_hil": False,
        "structural_fix_result": None,
        "patch_result": None,
        "patches_applied": [],
        "targeted_patch_used": False,
        "quality_report": None,
        "quality_report_markdown": None,
        "human_approved_divergence": False,
        "human_approved_final": False,
        "human_edits": None,
        "final_markdown": ""
        ,
        # Section-level HIL
        "hil_target_sections": request.get("hil_target_sections", []) or [],
        "hil_section_payload": None,

        # Outline-level HIL
        "hil_outline_enabled": bool(request.get("hil_outline_enabled", False)),
        "hil_outline_payload": None
        ,
        # Model selection (canonical ids)
        "judge_model": judge_model,
        "gpt_model": gpt_model,
        "claude_model": claude_model,
        "strategist_model": strategist_model,
        "drafter_models": drafter_models,
        "reviewer_models": reviewer_models,
    }
    
    # Save initial state
    await legal_workflow_app.aupdate_state(config, initial_state)
    
    logger.info(f"🚀 Job {jobid} started with mode={initial_state['mode']}, multi_agent={initial_state['use_multi_agent']}")
    
    return {"job_id": jobid, "status": "started"}


@router.post("/{jobid}/resume")
async def resume_job(
    jobid: str,
    decision: dict = Body(...),
    db: AsyncSession = Depends(get_db)
):
    """
    Retoma job após revisão humana (HIL checkpoint)
    """
    logger.info(f"▶️ Resuming job {jobid} with decision: {decision}")
    config = {"configurable": {"thread_id": jobid}}
    
    checkpoint = decision.get("checkpoint", "unknown")
    approved = decision.get("approved", False)
    edits = decision.get("edits")
    instructions = decision.get("instructions")
    
    # Resume execution properly by feeding the interrupt() decision back via Command(resume=...)
    resume_payload = {
        "checkpoint": checkpoint,
        "approved": approved,
        "edits": edits,
        "instructions": instructions,
        "hil_target_sections": decision.get("hil_target_sections")
    }
    await legal_workflow_app.ainvoke(Command(resume=resume_payload), config)
    
    return {"status": "resumed", "checkpoint": checkpoint, "approved": approved}


@router.get("/{jobid}/status")
async def get_job_status(jobid: str, db: AsyncSession = Depends(get_db)):
    """
    Retorna status atual do job
    """
    config = {"configurable": {"thread_id": jobid}}
    
    try:
        state = legal_workflow_app.get_state(config)
        
        if not state.values:
            return {"status": "not_found", "job_id": jobid}
        
        return {
            "status": "active" if state.next else "completed",
            "job_id": jobid,
            "current_node": str(state.next) if state.next else "END",
            "has_interrupt": bool(state.tasks),
            "values": {
                "mode": state.values.get("mode"),
                "outline": state.values.get("outline"),
                "has_divergence": state.values.get("has_any_divergence"),
                "audit_status": state.values.get("audit_status")
            }
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}
