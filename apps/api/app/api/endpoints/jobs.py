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
from pathlib import Path
from typing import Dict, Any, Optional, List

from app.core.database import get_db, AsyncSessionLocal
from app.core.time_utils import utcnow
from app.core.security import get_current_user
from app.models.document import Document, DocumentType
from app.models.user import User
from app.models.workflow_state import WorkflowState
from app.services.rag_policy import resolve_rag_scope
from app.services.job_manager import job_manager
from app.services.api_call_tracker import job_context
from app.services.billing_service import (
    resolve_plan_key,
    resolve_deep_research_billing,
    get_plan_cap,
    get_points_summary,
    get_usd_per_point,
    DEFAULT_MAX_POINTS_PER_MESSAGE,
)
from app.services.billing_quote_service import estimate_langgraph_job_points, FixedPointsEstimator
from app.services.poe_like_billing import quote_message as poe_quote_message
from dataclasses import asdict
from app.services.ai.langgraph_legal_workflow import legal_workflow_app, DocumentState, append_sources_section
from app.services.ai.document_store import resolve_full_document
from app.services.ai.citations.base import append_autos_references_section
from app.services.ai.model_registry import (
    DEFAULT_JUDGE_MODEL,
    DEFAULT_DEBATE_MODELS,
    get_model_config,
    validate_model_id,
    validate_model_list,
    is_agent_model,
)
from app.services.ai.orchestration.router import get_orchestration_router
from app.services.ai.quality_profiles import resolve_quality_profile
from app.services.ai.checklist_parser import (
    parse_document_checklist_from_prompt,
    merge_document_checklist_hints,
)
from app.services.context_strategy import summarize_documents
from app.services.document_processor import (
    extract_text_from_pdf,
    extract_text_from_pdf_with_ocr,
    extract_text_from_docx,
    extract_text_from_odt,
    extract_text_from_image,
    extract_text_from_zip,
)
from app.services.model_registry import get_model_config as get_budget_model_config
from app.services.token_budget_service import TokenBudgetService
from app.core.config import settings
from app.utils.validators import InputValidator
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
token_service = TokenBudgetService()

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

def _pick_smallest_context_model(model_ids: list[str]) -> str:
    if not model_ids:
        return "gpt-5.2"
    selected = model_ids[0]
    min_ctx = get_budget_model_config(selected).get("context_window", 0)
    for model_id in model_ids[1:]:
        ctx = get_budget_model_config(model_id).get("context_window", 0)
        if min_ctx <= 0 or (ctx > 0 and ctx < min_ctx):
            selected = model_id
            min_ctx = ctx
    return selected

def _should_use_precise_budget(model_id: str) -> bool:
    provider = (get_budget_model_config(model_id) or {}).get("provider") or ""
    return provider in ("vertex", "google")

def _estimate_attachment_stats(docs: list[Document]) -> tuple[int, int]:
    total_tokens = 0
    total_chars = 0
    for doc in docs:
        text = (getattr(doc, "extracted_text", "") or "").strip()
        if not text:
            continue
        total_chars += len(text)
        total_tokens += token_service.estimate_tokens(text)
    return total_tokens, total_chars

def _estimate_available_tokens(model_id: str, prompt: str, base_context: str) -> int:
    config = get_budget_model_config(model_id) or {}
    limit = config.get("context_window", 0)
    max_output = config.get("max_output", 4096)
    if limit <= 0:
        return 0
    buffer = 1000
    base_tokens = token_service.estimate_tokens(base_context or "")
    prompt_tokens = token_service.estimate_tokens(prompt or "")
    return limit - base_tokens - prompt_tokens - max_output - buffer

def _join_context_parts(*parts: Optional[str]) -> str:
    filtered = [part for part in parts if part]
    return "\n\n".join(filtered).strip()

def _detect_agent_models(
    judge_model: str,
    gpt_model: str,
    claude_model: str,
    strategist_model: Optional[str] = None,
    drafter_models: Optional[List[str]] = None,
    reviewer_models: Optional[List[str]] = None,
) -> List[str]:
    """
    Detecta se algum dos modelos selecionados é um agent model (claude-agent, openai-agent, google-agent).
    Retorna a lista de agent model IDs encontrados (pode ser vazia).
    """
    all_models = [judge_model, gpt_model, claude_model]
    if strategist_model:
        all_models.append(strategist_model)
    if drafter_models:
        all_models.extend(drafter_models)
    if reviewer_models:
        all_models.extend(reviewer_models)
    return [m for m in all_models if m and is_agent_model(m)]


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
    max_chars: Optional[int] = None,
    per_doc_chars: Optional[int] = None
) -> str:
    if not docs:
        return ""
    if max_chars is None:
        max_chars = settings.ATTACHMENT_INJECTION_MAX_CHARS
    if per_doc_chars is None:
        per_doc_chars = settings.ATTACHMENT_INJECTION_MAX_CHARS_PER_DOC
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
    top_k: Optional[int] = None,
    max_files: Optional[int] = None
) -> str:
    try:
        from rag_local import LocalProcessIndex
    except Exception as e:
        logger.warning(f"RAG Local indisponível: {e}")
        return ""

    if top_k is None:
        top_k = settings.ATTACHMENT_RAG_LOCAL_TOP_K
    if max_files is None:
        max_files = settings.ATTACHMENT_RAG_LOCAL_MAX_FILES
    max_files = max(1, int(max_files))
    allowed_exts = {".pdf", ".txt", ".md"}
    file_paths: list[str] = []
    inline_docs: list[tuple[Document, str]] = []
    for doc in docs:
        path = getattr(doc, "url", None)
        text = (getattr(doc, "extracted_text", None) or getattr(doc, "content", None) or "").strip()
        meta = getattr(doc, "doc_metadata", {}) or {}
        ocr_applied = bool(meta.get("ocr_applied")) or meta.get("ocr_status") == "completed"
        ext = os.path.splitext(path)[1].lower() if path else ""

        prefer_inline = False
        if text:
            if not path or not os.path.exists(path):
                prefer_inline = True
            elif ext not in allowed_exts:
                prefer_inline = True
            elif doc.type == DocumentType.PDF and ocr_applied:
                prefer_inline = True

        if prefer_inline:
            inline_docs.append((doc, text))
        elif path and os.path.exists(path) and ext in allowed_exts:
            file_paths.append(path)

    if not file_paths and not inline_docs:
        return ""

    try:
        index = LocalProcessIndex(
            processo_id=f"upload-{uuid.uuid4()}",
            sistema="UPLOAD",
            tenant_id=tenant_id
        )
        remaining = max_files
        for path in file_paths:
            if remaining <= 0:
                break
            index.index_documento(path)
            remaining -= 1
        for doc, text in inline_docs:
            if remaining <= 0:
                break
            filename = doc.name or doc.original_name or doc.id or "documento"
            index.index_text(
                text,
                filename=filename,
                doc_id=doc.id,
                source_path=getattr(doc, "url", None) or filename,
            )
            remaining -= 1
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


_CONTEXT_FILE_EXTS = {
    ".pdf",
    ".txt",
    ".md",
    ".docx",
    ".odt",
    ".rtf",
    ".html",
    ".htm",
    ".zip",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".bmp",
    ".tiff",
    ".tif",
}


def _expand_context_file_paths(paths: list[str], max_files: int) -> list[str]:
    expanded: list[str] = []
    seen: set[str] = set()
    for raw_path in paths:
        if len(expanded) >= max_files:
            break
        path = Path(str(raw_path or "").strip())
        if not path.exists():
            continue
        if path.is_dir():
            for candidate in path.rglob("*"):
                if len(expanded) >= max_files:
                    break
                if not candidate.is_file():
                    continue
                if candidate.suffix.lower() not in _CONTEXT_FILE_EXTS:
                    continue
                candidate_str = str(candidate)
                if candidate_str in seen:
                    continue
                seen.add(candidate_str)
                expanded.append(candidate_str)
        else:
            if path.suffix.lower() not in _CONTEXT_FILE_EXTS:
                continue
            path_str = str(path)
            if path_str in seen:
                continue
            seen.add(path_str)
            expanded.append(path_str)
    return expanded


async def _extract_text_for_context_file(path: str) -> str:
    ext = Path(path).suffix.lower()
    if ext == ".pdf":
        text = await extract_text_from_pdf(path)
        if text and len(text.strip()) >= 50:
            return text
        if settings.ENABLE_OCR:
            return await extract_text_from_pdf_with_ocr(path)
        return text
    if ext == ".docx":
        return await extract_text_from_docx(path)
    if ext == ".odt":
        return await extract_text_from_odt(path)
    if ext in {".txt", ".md", ".rtf"}:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
        except OSError:
            return ""
    if ext in {".html", ".htm"}:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                return InputValidator.sanitize_html(f.read())
        except OSError:
            return ""
    if ext == ".zip":
        zip_result = await extract_text_from_zip(path)
        return (zip_result or {}).get("extracted_text", "")
    if ext in {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".tif"}:
        if settings.ENABLE_OCR:
            return await extract_text_from_image(path)
        return ""
    return ""


async def _build_local_rag_context_from_paths(
    context_files: list[str],
    query: str,
    tenant_id: str = "default",
    top_k: Optional[int] = None,
    max_files: Optional[int] = None,
) -> str:
    try:
        from rag_local import LocalProcessIndex
    except Exception as e:
        logger.warning(f"RAG Local indisponível: {e}")
        return ""

    if top_k is None:
        top_k = settings.ATTACHMENT_RAG_LOCAL_TOP_K
    if max_files is None:
        max_files = settings.ATTACHMENT_RAG_LOCAL_MAX_FILES
    max_files = max(1, int(max_files))

    expanded_paths = _expand_context_file_paths(context_files, max_files)
    if not expanded_paths:
        return ""

    try:
        index = LocalProcessIndex(
            processo_id=f"context-{uuid.uuid4()}",
            sistema="UPLOAD",
            tenant_id=tenant_id,
        )
        remaining = max_files
        for path in expanded_paths:
            if remaining <= 0:
                break
            ext = Path(path).suffix.lower()
            if ext in {".pdf", ".txt", ".md"}:
                chunks = index.index_documento(path)
                remaining -= 1
                if chunks <= 0 and ext == ".pdf" and settings.ENABLE_OCR:
                    text = await extract_text_from_pdf_with_ocr(path)
                    if text and text.strip():
                        index.index_text(
                            text,
                            filename=Path(path).name,
                            source_path=path,
                        )
                continue
            text = await _extract_text_for_context_file(path)
            if text and text.strip():
                index.index_text(
                    text,
                    filename=Path(path).name,
                    source_path=path,
                )
                remaining -= 1
        results = index.search(query, top_k=top_k)
    except Exception as e:
        logger.warning(f"Falha ao indexar context_files no RAG Local: {e}")
        return ""

    if not results:
        return ""

    lines = ["### 📁 FATOS DO PROCESSO (CONTEXT_FILES)"]
    for r in results:
        snippet = (r.get("text") or "")[:300].strip()
        citation = r.get("citacao") or "Documento"
        if snippet:
            lines.append(f"- {citation}: \"{snippet}...\"")
    return "\n".join(lines)


async def persist_workflow_state(
    job_id: str,
    state: Dict[str, Any],
    user_id: str,
    case_id: Optional[str] = None,
    chat_id: Optional[str] = None,
) -> None:
    """
    Persiste o estado do workflow para auditabilidade.
    Executa em background para não bloquear o streaming.
    """
    try:
        async with AsyncSessionLocal() as db:
            workflow_state = WorkflowState.from_document_state(
                state=state,
                job_id=job_id,
                user_id=user_id,
                case_id=case_id,
                chat_id=chat_id,
            )
            workflow_state.completed_at = utcnow()
            db.add(workflow_state)
            await db.commit()
            logger.info(f"✅ WorkflowState persistido para job {job_id}")
    except Exception as e:
        logger.error(f"❌ Falha ao persistir WorkflowState para job {job_id}: {e}")


@router.get("/{jobid}/stream")
async def stream_job(jobid: str, db: AsyncSession = Depends(get_db)):
    """
    Endpoint SSE para streaming de eventos do LangGraph
    """
    logger.info(f"📡 Iniciando stream para Job {jobid}")
    
    async def event_generator():
        config = {"configurable": {"thread_id": jobid}}
        def _build_citations(values: Dict[str, Any]) -> List[Dict[str, Any]]:
            citations: List[Dict[str, Any]] = []
            citations_map = values.get("citations_map") or {}
            if isinstance(citations_map, dict) and citations_map:
                def _sort_key(item: str):
                    return int(item) if str(item).isdigit() else item
                for key in sorted(citations_map.keys(), key=_sort_key):
                    if len(citations) >= 20:
                        break
                    item = citations_map.get(key) or {}
                    citations.append({
                        "number": int(key) if str(key).isdigit() else key,
                        "title": item.get("title"),
                        "url": item.get("url"),
                        "quote": item.get("snippet") or item.get("quote"),
                    })
                return citations

            sources = values.get("research_sources") or []
            if isinstance(sources, list):
                for idx, src in enumerate(sources[:20], start=1):
                    if not isinstance(src, dict):
                        continue
                    citations.append({
                        "number": idx,
                        "title": src.get("title"),
                        "url": src.get("url"),
                        "quote": src.get("snippet") or src.get("text"),
                    })
            return citations

        def _hil_event(checkpoint: str, interrupt_type: str, message: str, payload: Dict[str, Any], node: str) -> str:
            return sse_event(
                job_manager.build_event(
                    jobid,
                    "hil_required",
                    {
                        "checkpoint": checkpoint,
                        "interrupt_type": interrupt_type,
                        "message": message,
                        "payload": payload,
                    },
                    phase="hil",
                    node=node,
                ),
                event="message",
            )
        
        try:
            # Check if job exists
            current_state = legal_workflow_app.get_state(config)
            recursion_limit = int(current_state.values.get("recursion_limit") or 200) if current_state.values else 200
            config["recursion_limit"] = recursion_limit
            
            if not current_state.values:
                yield sse_event({"type": "info", "message": "Aguardando início do job..."}, event="status")
                return

            # ── Agent Model Branch ─────────────────────────────────────────
            # If any selected model is an agent model, route through OrchestrationRouter
            # instead of the LangGraph workflow. This is a separate streaming path.
            _state_vals = current_state.values or {}
            _agent_model_ids = _detect_agent_models(
                judge_model=_state_vals.get("judge_model", ""),
                gpt_model=_state_vals.get("gpt_model", ""),
                claude_model=_state_vals.get("claude_model", ""),
                strategist_model=_state_vals.get("strategist_model"),
                drafter_models=_state_vals.get("drafter_models"),
                reviewer_models=_state_vals.get("reviewer_models"),
            )
            if _agent_model_ids:
                logger.info(
                    f"🤖 Job {jobid}: Agent models detected ({_agent_model_ids}). "
                    f"Routing to OrchestrationRouter."
                )
                orchestration_router = get_orchestration_router()

                # Collect all selected model IDs for the router
                _all_models = list(dict.fromkeys(filter(None, [
                    _state_vals.get("judge_model"),
                    _state_vals.get("gpt_model"),
                    _state_vals.get("claude_model"),
                    _state_vals.get("strategist_model"),
                    *(_state_vals.get("drafter_models") or []),
                    *(_state_vals.get("reviewer_models") or []),
                ])))

                # Build context for OrchestrationRouter from the persisted state
                _orch_context = {
                    "user_id": job_manager.get_job_user(jobid) or "",
                    "chat_id": _state_vals.get("conversation_id"),
                    "rag_context": _state_vals.get("research_context") or _state_vals.get("sei_context") or "",
                    "template_structure": _state_vals.get("template_structure") or "",
                    "extra_instructions": _state_vals.get("tese") or "",
                    "conversation_history": _state_vals.get("messages"),
                    "chat_personality": _state_vals.get("chat_personality", "juridico"),
                    "reasoning_level": _state_vals.get("thinking_level", "medium"),
                    "temperature": float(_state_vals.get("temperature", 0.3)),
                    "web_search": bool(_state_vals.get("web_search_enabled", False)),
                }

                _mode = _state_vals.get("mode", "PETICAO")

                # Emit workflow_start for consistency
                yield sse_event(
                    job_manager.build_event(
                        jobid,
                        "orchestration_start",
                        {
                            "executor": "agent",
                            "agent_models": _agent_model_ids,
                            "all_models": _all_models,
                        },
                        phase="orchestration",
                        node="router",
                    ),
                    event="message",
                )

                # Stream SSE events from OrchestrationRouter
                _accumulated_text = ""
                _had_agent_error = False
                with job_context(jobid, user_id=job_manager.get_job_user(jobid)):
                    async for sse_ev in orchestration_router.execute(
                        prompt=_state_vals.get("input_text", ""),
                        selected_models=_all_models,
                        context=_orch_context,
                        mode=_mode,
                        job_id=jobid,
                    ):
                        # Convert SSEEvent from orchestration to our SSE format
                        ev_dict = sse_ev.to_dict() if hasattr(sse_ev, "to_dict") else (
                            sse_ev if isinstance(sse_ev, dict) else {"type": "unknown"}
                        )
                        ev_type = ev_dict.get("type", "")

                        # Map orchestration events to existing frontend events
                        if ev_type == "token":
                            token_text = (ev_dict.get("data") or {}).get("token", "")
                            if token_text:
                                _accumulated_text += token_text
                                yield sse_event({
                                    "type": "token",
                                    "token": token_text,
                                    "phase": "generation",
                                }, event="message")
                        elif ev_type == "thinking":
                            yield sse_event({
                                "type": "thinking",
                                "content": (ev_dict.get("data") or {}).get("content", ""),
                                "agent": (ev_dict.get("agent") or "agent"),
                            }, event="granular")
                        elif ev_type == "agent_start":
                            yield sse_event({
                                "type": "agent_start",
                                "agent": (ev_dict.get("data") or {}).get("agent", ""),
                                "message": (ev_dict.get("data") or {}).get("message", ""),
                            }, event="granular")
                        elif ev_type == "tool_call":
                            yield sse_event({
                                "type": "tool_call",
                                "data": ev_dict.get("data", {}),
                            }, event="granular")
                        elif ev_type == "tool_result":
                            yield sse_event({
                                "type": "tool_result",
                                "data": ev_dict.get("data", {}),
                            }, event="granular")
                        elif ev_type == "done":
                            final_text = (ev_dict.get("data") or {}).get("final_text", "")
                            if final_text:
                                _accumulated_text = final_text
                        elif ev_type == "error":
                            _had_agent_error = True
                            err_msg = (ev_dict.get("data") or {}).get("error", "Unknown agent error")
                            yield sse_event({"type": "error", "message": err_msg}, event="error")
                        else:
                            # Forward any other events as-is
                            yield sse_event(ev_dict, event="message")

                if not _had_agent_error:
                    # Persist workflow state for auditability
                    asyncio.create_task(persist_workflow_state(
                        job_id=jobid,
                        state=_state_vals,
                        user_id=job_manager.get_job_user(jobid) or "",
                        case_id=_state_vals.get("case_id"),
                        chat_id=_state_vals.get("conversation_id"),
                    ))

                    # Emit final done event
                    yield sse_event({
                        "type": "done",
                        "markdown": _accumulated_text,
                        "final_decision": None,
                        "final_decision_reasons": [],
                        "final_decision_score": None,
                        "final_decision_target": None,
                        "citations": [],
                        "api_counters": job_manager.get_api_counters(jobid),
                        "processed_sections": [],
                        "hil_history": [],
                        "has_any_divergence": False,
                        "divergence_summary": "",
                        "executor": "agent",
                        "agent_models": _agent_model_ids,
                    }, event="done")
                    job_manager.clear_events(jobid)

                return  # End stream for agent models
            # ── End Agent Model Branch ─────────────────────────────────────

            # Initial UX hints (helps frontend show "running" states deterministically)
            if bool(current_state.values.get("deep_research_enabled")):
                planned_queries = current_state.values.get("planned_queries") or []
                yield sse_event(
                    job_manager.build_event(
                        jobid,
                        "research_start",
                        {"researchmode": "deep", "plannedqueries": planned_queries},
                        phase="research",
                        node="deep_research",
                    ),
                    event="message",
                )

            research_streamed = False
            combined_queue: asyncio.Queue = asyncio.Queue()
            stop_event = asyncio.Event()

            async def pump_job_events():
                last_id = 0
                last_billing_emit = 0.0
                last_points_total = None
                loop = asyncio.get_running_loop()
                try:
                    while not stop_event.is_set():
                        now = loop.time()
                        if now - last_billing_emit >= 1.0:
                            counters = job_manager.get_api_counters(jobid)
                            points_total = counters.get("points_total") if isinstance(counters, dict) else None
                            if points_total != last_points_total:
                                last_points_total = points_total
                                await combined_queue.put((
                                    "job",
                                    job_manager.build_event(
                                        jobid,
                                        "billing_update",
                                        {"api_counters": counters},
                                        phase="billing",
                                        node="billing",
                                    ),
                                ))
                            last_billing_emit = now

                        events = job_manager.list_events(jobid, after_id=last_id)
                        for ev in events:
                            last_id = max(last_id, int(ev.get("id", 0)))
                            await combined_queue.put(("job", ev))
                        await asyncio.sleep(0.2)
                finally:
                    events = job_manager.list_events(jobid, after_id=last_id)
                    for ev in events:
                        await combined_queue.put(("job", ev))
                    await combined_queue.put(("job_done", None))

            async def pump_langgraph():
                with job_context(jobid, user_id=job_manager.get_job_user(jobid)):
                    try:
                        async for event in legal_workflow_app.astream(None, config, stream_mode="updates"):
                            await combined_queue.put(("langgraph", event))
                    except Exception as exc:
                        await combined_queue.put(("langgraph_error", exc))
                    finally:
                        await combined_queue.put(("langgraph_done", None))

            tasks = [
                asyncio.create_task(pump_job_events()),
                asyncio.create_task(pump_langgraph()),
            ]
            job_done = False
            graph_done = False
            had_error = False

            while True:
                kind, payload = await combined_queue.get()

                if kind == "job":
                    event_type = payload.get("type")
                    if event_type in (
                        "deep_research_start",
                        "cache_hit",
                        "thinking",
                        "deep_research_done",
                        "research_start",
                        "deepresearch_step",
                        "research_done",
                    ):
                        research_streamed = True
                    event_name = payload.get("event") or payload.get("channel") or "message"
                    yield sse_event(payload, event=event_name)
                    continue

                if kind == "langgraph_error":
                    yield sse_event({"type": "error", "message": str(payload)}, event="error")
                    had_error = True
                    break

                if kind == "langgraph_done":
                    graph_done = True
                    stop_event.set()
                    if job_done:
                        break
                    continue

                if kind == "job_done":
                    job_done = True
                    if graph_done:
                        break
                    continue

                if kind != "langgraph":
                    continue

                event = payload
                logger.debug(f"Event: {event}")

                for node_name, node_output in event.items():

                    # NOTE: workflow node was renamed to "gen_outline" to avoid conflict with the state key "outline".
                    # Keep backward-compatible handling for older graphs still emitting "outline".
                    if node_name in ("outline", "gen_outline"):
                        yield sse_event({
                            "type": "outline_done",
                            "outline": node_output.get("outline", [])
                        }, event="outline")

                    elif node_name == "deep_research":
                        if not (research_streamed or bool(node_output.get("deep_research_streamed"))):
                            # Replay thinking steps (batch) if available
                            thinking_steps = node_output.get("deep_research_thinking_steps") or []
                            if isinstance(thinking_steps, list) and thinking_steps:
                                if bool(node_output.get("deep_research_from_cache")):
                                    yield sse_event(
                                        job_manager.build_event(
                                            jobid,
                                            "cache_hit",
                                            {"from_cache": True},
                                            phase="research",
                                            node="deep_research",
                                        ),
                                        event="message",
                                    )
                                for step in thinking_steps[:50]:
                                    text = (step or {}).get("text") if isinstance(step, dict) else None
                                    if text:
                                        yield sse_event(
                                            job_manager.build_event(
                                                jobid,
                                                "deepresearch_step",
                                                {"step": text, "from_cache": bool(node_output.get("deep_research_from_cache"))},
                                                phase="research",
                                                node="deep_research",
                                            ),
                                            event="message",
                                        )

                            yield sse_event(
                                job_manager.build_event(
                                    jobid,
                                    "research_done",
                                    {
                                        "researchmode": "deep",
                                        "sources_count": len(node_output.get("research_sources", [])),
                                        "from_cache": bool(node_output.get("deep_research_from_cache", False)),
                                    },
                                    phase="research",
                                    node="deep_research",
                                ),
                                event="message",
                            )

                    elif node_name == "web_search":
                        yield sse_event({
                            "type": "web_search_done",
                            "sources_count": len(node_output.get("research_sources", []))
                        }, event="research")

                    elif node_name in ["debate_all", "debate"]:
                        sections = node_output.get("processed_sections", [])
                        document_preview = node_output.get("full_document_preview") or node_output.get("full_document") or ""
                        if not isinstance(document_preview, str):
                            document_preview = ""
                        document_preview = document_preview[:2000]

                        # Emit per-section events for granular visibility
                        for sec in sections:
                            pending = sec.get("claims_requiring_citation", []) or []
                            removed = sec.get("removed_claims", []) or []
                            risk_flags = sec.get("risk_flags", []) or []
                            divergencias = sec.get("divergence_details") or sec.get("divergencias") or ""
                            review = sec.get("review", {})
                            if not isinstance(review, dict):
                                review = {}

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
                                "divergence_details": divergencias,
                                "review": review,
                                "document_preview": document_preview,
                            }, event="section")

                        yield sse_event({
                            "type": "debate_done",
                            "sections_count": len(sections),
                            "has_divergence": node_output.get("has_any_divergence", False),
                            "divergence_summary": node_output.get("divergence_summary", ""),
                            "document_preview": document_preview,
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
                        yield sse_event({
                            "type": "judging",
                            "agent": node_output.get("judge_model", "Judge"),
                            "quality_score": node_output.get("quality_score"),
                            "retry_reason": node_output.get("retry_reason"),
                            "retries": node_output.get("retries"),
                            "max_retries": node_output.get("max_retries"),
                        }, event="granular")
                    elif node_name == "prepare_retry":
                        yield sse_event({
                            "type": "retry",
                            "retries": node_output.get("retries"),
                            "max_retries": node_output.get("max_retries"),
                            "retry_reason": node_output.get("retry_reason"),
                            "quality_score": node_output.get("quality_score"),
                        }, event="granular")

                    elif node_name == "research_verify":
                        retry_progress = node_output.get("research_retry_progress")
                        retry_reason = node_output.get("verification_retry_reason")
                        is_retrying = bool(node_output.get("verification_retry", False))
                        yield sse_event({
                            "type": "research_retry_progress",
                            "progress": retry_progress,
                            "reason": retry_reason,
                            "is_retrying": is_retrying,
                            "attempts": node_output.get("verifier_attempts", 0),
                        }, event="research")

                    elif node_name == "audit":
                        yield sse_event({
                            "type": "audit_done",
                            "status": node_output.get("audit_status"),
                            "issues_count": len(node_output.get("audit_issues", [])),
                            "report": node_output.get("audit_report")
                        }, event="audit")
                        yield sse_event(
                            job_manager.build_event(
                                jobid,
                                "audit_result",
                                {
                                    "auditstatus": node_output.get("audit_status"),
                                    "issues_count": len(node_output.get("audit_issues", [])),
                                },
                                phase="audit",
                                node="audit",
                            ),
                            event="message",
                        )
                    elif node_name == "fact_check":
                        checklist = node_output.get("document_checklist", {}) or {}
                        yield sse_event({
                            "type": "fact_check_done",
                            "summary": checklist.get("summary"),
                            "missing_critical": checklist.get("missing_critical", []),
                            "missing_noncritical": checklist.get("missing_noncritical", []),
                        }, event="fact_check")
                    elif node_name == "document_gate":
                        yield sse_event({
                            "type": "document_gate_done",
                            "status": node_output.get("document_gate_status"),
                            "missing": node_output.get("document_gate_missing", []),
                        }, event="document_gate")
                        missing = node_output.get("document_gate_missing", []) or []
                        missing_critical = [m for m in missing if isinstance(m, dict) and m.get("critical")]
                        missing_noncritical = [m for m in missing if isinstance(m, dict) and not m.get("critical")]
                        yield sse_event(
                            job_manager.build_event(
                                jobid,
                                "documentgate_result",
                                {
                                    "status": node_output.get("document_gate_status"),
                                    "missingcritical_count": len(missing_critical),
                                    "missingnoncritical_count": len(missing_noncritical),
                                },
                                phase="quality",
                                node="document_gate",
                            ),
                            event="message",
                        )

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

                    elif node_name == "style_check":
                        yield sse_event(
                            job_manager.build_event(
                                jobid,
                                "stylecheck_result",
                                {
                                    "score": node_output.get("style_score"),
                                    "tone": node_output.get("style_tone"),
                                    "issues": node_output.get("style_issues", []),
                                },
                                phase="quality",
                                node="style_check",
                            ),
                            event="message",
                        )

                    # NOTE: workflow node was renamed to "gen_quality_report" to avoid conflict with the state key.
                    elif node_name in ("quality_report", "gen_quality_report"):
                        report = node_output.get("quality_report", {}) or {}
                        md = (node_output.get("quality_report_markdown") or "")
                        yield sse_event({
                            "type": "quality_report_done",
                            "report": report,
                            "markdown_preview": md[:4000] if isinstance(md, str) else "",
                        }, event="quality")

                    elif node_name == "evaluate_hil":
                        hil_checklist = node_output.get("hil_checklist", {}) or {}
                        if not isinstance(hil_checklist, dict):
                            hil_checklist = {}
                        hil_risk_score = node_output.get("hil_risk_score")
                        hil_risk_level = node_output.get("hil_risk_level")
                        yield sse_event({
                            "type": "hil_evaluated",
                            "requires_hil": hil_checklist.get("requires_hil", False),
                            "hil_level": hil_checklist.get("hil_level", "none"),
                            "triggered_factors": hil_checklist.get("triggered_factors", []),
                            "score_confianca": hil_checklist.get("score_confianca", 1.0),
                            "evaluation_notes": hil_checklist.get("evaluation_notes", []),
                            "hil_checklist": hil_checklist,
                            "hil_risk_score": hil_risk_score,
                            "hil_risk_level": hil_risk_level,
                        }, event="hil_decision")

                    elif node_name == "propose_corrections":
                        yield sse_event({
                            "type": "corrections_proposed",
                            "has_corrections": bool(node_output.get("proposed_corrections")),
                            "diff_summary": node_output.get("corrections_diff", "")
                        }, event="corrections")

            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if had_error:
                return

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
                    yield _hil_event(
                        "outline",
                        "outlinereview",
                        "Revisão do outline requerida.",
                        {"outline": outline, "hil_target_sections": hil_targets},
                        node="outline_hil",
                    )
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
                    yield _hil_event(
                        "section",
                        "sectionreview",
                        "Revisão de seção requerida.",
                        {
                            "section_title": payload.get("section_title"),
                            "merged_content": payload.get("merged_content", "")[:8000],
                            "divergence_details": payload.get("divergence_details", ""),
                            "drafts": payload.get("drafts", {}) or {},
                            "document_preview": (payload.get("document_preview") or final_snapshot.values.get("full_document", "") or "")[:2000],
                        },
                        node="section_hil",
                    )
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
                    yield _hil_event(
                        "divergence",
                        "divergencereview",
                        "Revisão de divergências requerida.",
                        {
                            "divergencias": divergencias_por_secao,
                            "document_preview": final_snapshot.values.get("full_document", "")[:2000],
                        },
                        node="divergence_hil",
                    )
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
                    yield _hil_event(
                        "correction",
                        "correctionreview",
                        "Revisão de correções requerida.",
                        {
                            "original_document": final_snapshot.values.get("full_document", "")[:2000],
                            "proposed_corrections": final_snapshot.values.get("proposed_corrections", "")[:2000],
                            "corrections_diff": final_snapshot.values.get("corrections_diff", ""),
                            "audit_issues": final_snapshot.values.get("audit_issues", []),
                            "audit_status": final_snapshot.values.get("audit_status"),
                        },
                        node="correction_hil",
                    )
                    return
                
                elif "finalize_hil" in str(next_nodes):
                    yield sse_event({
                        "type": "human_review_required",
                        "checkpoint": "final",
                        "job_id": jobid,
                        "review_data": {
                            "document": final_snapshot.values.get("full_document"),
                            "audit_status": final_snapshot.values.get("audit_status"),
                            "audit_report": final_snapshot.values.get("audit_report"),
                            "committee_review_report": final_snapshot.values.get("committee_review_report")
                        }
                    }, event="review")
                    yield _hil_event(
                        "final",
                        "finalreview",
                        "Revisão final requerida.",
                        {
                            "document": final_snapshot.values.get("full_document"),
                            "audit_status": final_snapshot.values.get("audit_status"),
                            "audit_report": final_snapshot.values.get("audit_report"),
                            "committee_review_report": final_snapshot.values.get("committee_review_report"),
                        },
                        node="finalize_hil",
                    )
                    return
                elif "style_check" in str(next_nodes):
                    payload = final_snapshot.values.get("style_check_payload") or {}
                    report = final_snapshot.values.get("style_report") or {}
                    issues = payload.get("issues") or report.get("issues") or []
                    term_variations = payload.get("term_variations") or report.get("term_variations") or []
                    yield sse_event({
                        "type": "human_review_required",
                        "checkpoint": "style_check",
                        "job_id": jobid,
                        "review_data": {
                            "tone_detected": payload.get("tone_detected") or report.get("tone"),
                            "thermometer": payload.get("thermometer") or report.get("thermometer"),
                            "score": payload.get("score") or report.get("score"),
                            "issues": issues,
                            "term_variations": term_variations,
                            "draft_snippet": payload.get("draft_snippet") or (final_snapshot.values.get("full_document", "") or "")[:1200],
                        }
                    }, event="review")
                    yield _hil_event(
                        "style_check",
                        "stylereview",
                        "Revisão de estilo requerida.",
                        {
                            "tone_detected": payload.get("tone_detected") or report.get("tone"),
                            "thermometer": payload.get("thermometer") or report.get("thermometer"),
                            "score": payload.get("score") or report.get("score"),
                            "issues": issues,
                            "term_variations": term_variations,
                            "draft_snippet": payload.get("draft_snippet") or (final_snapshot.values.get("full_document", "") or "")[:1200],
                        },
                        node="style_check",
                    )
                    return
                elif "document_gate" in str(next_nodes):
                    checklist = final_snapshot.values.get("document_checklist", {}) or {}
                    yield sse_event({
                        "type": "human_review_required",
                        "checkpoint": "document_gate",
                        "job_id": jobid,
                        "review_data": {
                            "summary": checklist.get("summary"),
                            "missing_critical": checklist.get("missing_critical", []),
                            "missing_noncritical": checklist.get("missing_noncritical", []),
                        }
                    }, event="review")
                    yield _hil_event(
                        "document_gate",
                        "documentgate",
                        "Revisão do document gate requerida.",
                        {
                            "summary": checklist.get("summary"),
                            "missing_critical": checklist.get("missing_critical", []),
                            "missing_noncritical": checklist.get("missing_noncritical", []),
                        },
                        node="document_gate",
                    )
                    return

            # Check if finished
            if not final_snapshot.next:
                citations_payload = _build_citations(final_snapshot.values or {})
                yield sse_event(
                    job_manager.build_event(
                        jobid,
                        "workflow_end",
                        {
                            "finaldecision": final_snapshot.values.get("final_decision"),
                            "finaldecisionscore": final_snapshot.values.get("final_decision_score"),
                            "finaldecisionreasons": final_snapshot.values.get("final_decision_reasons", []),
                        },
                        phase="final",
                        node="finalize",
                    ),
                    event="message",
                )
                final_markdown = final_snapshot.values.get("final_markdown")
                if not isinstance(final_markdown, str) or not final_markdown.strip():
                    final_markdown = resolve_full_document(final_snapshot.values or {})
                final_markdown = append_sources_section(final_markdown or "", final_snapshot.values.get("citations_map"))
                final_markdown = append_autos_references_section(final_markdown, attachment_docs=None)

                # v5.7: Persist WorkflowState for auditability
                asyncio.create_task(persist_workflow_state(
                    job_id=jobid,
                    state=final_snapshot.values or {},
                    user_id=job_manager.get_job_user(jobid) or "",
                    case_id=final_snapshot.values.get("case_id"),
                    chat_id=final_snapshot.values.get("chat_id") or final_snapshot.values.get("conversation_id"),
                ))

                yield sse_event({
                    "type": "done",
                    "markdown": final_markdown,
                    "final_decision": final_snapshot.values.get("final_decision"),
                    "final_decision_reasons": final_snapshot.values.get("final_decision_reasons", []),
                    "final_decision_score": final_snapshot.values.get("final_decision_score"),
                    "final_decision_target": final_snapshot.values.get("final_decision_target"),
                    "citations": citations_payload,
                    "api_counters": job_manager.get_api_counters(jobid),
                    # v5.6: Include audit data
                    "processed_sections": final_snapshot.values.get("processed_sections", []),
                    "hil_history": final_snapshot.values.get("hil_history", []),
                    "has_any_divergence": final_snapshot.values.get("has_any_divergence", False),
                    "divergence_summary": final_snapshot.values.get("divergence_summary", ""),
                }, event="done")
                job_manager.clear_events(jobid)

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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Inicia um novo Job LangGraph
    """
    jobid = str(uuid.uuid4())
    job_manager.set_job_user(jobid, str(getattr(current_user, "id", "") or ""))
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

    web_search_model = request.get("web_search_model")
    if web_search_model is not None:
        web_search_model = str(web_search_model).strip()
    if web_search_model and web_search_model.lower() != "auto":
        try:
            web_search_model = validate_model_id(
                web_search_model,
                for_agents=True,
                field_name="web_search_model",
            )
            cfg = get_model_config(web_search_model)
            if cfg and "deep_research" in (cfg.capabilities or []):
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Campo 'web_search_model' não pode ser um modelo de Deep Research "
                        f"('{web_search_model}'). Use os campos 'deep_research_*' para isso "
                        "ou selecione um modelo de web search comum (ex.: 'sonar', 'sonar-pro', "
                        "'sonar-reasoning-pro')."
                    ),
                )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    else:
        web_search_model = None

    deep_research_provider = str(
        request.get("deep_research_provider")
        or request.get("deep_research_backend")
        or ""
    ).strip().lower()
    if deep_research_provider in ("pplx", "perplexity", "sonar"):
        deep_research_provider = "perplexity"
    elif deep_research_provider in ("google", "gemini"):
        deep_research_provider = "google"
    elif deep_research_provider in ("", "auto"):
        deep_research_provider = "auto"
    else:
        deep_research_provider = "auto"

    deep_research_model = request.get("deep_research_model")
    if deep_research_model:
        try:
            deep_research_model = validate_model_id(
                deep_research_model,
                for_juridico=True,
                field_name="deep_research_model",
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    judge_cfg = get_model_config(judge_model)
    judge_provider = judge_cfg.provider if judge_cfg else ""
    if deep_research_provider == "auto" and judge_provider == "perplexity":
        deep_research_provider = "perplexity"
    if deep_research_provider == "perplexity":
        # In this app, Perplexity Deep Research is restricted to Sonar Deep Research.
        deep_research_model = "sonar-deep-research"

    plan_key = resolve_plan_key(
        request.get("plan")
        or request.get("plan_key")
        or request.get("user_plan")
        or getattr(current_user, "plan", None)
    )
    deep_research_effort, deep_research_multiplier = resolve_deep_research_billing(
        plan_key,
        request.get("deep_research_effort"),
    )

    page_range = resolve_page_range(request)

    # --- Poe-like billing: quote + gates (wallet + per-job budget) ---
    budget_override = request.get("budget_override_points")
    try:
        budget_override = int(budget_override) if budget_override is not None else None
    except (TypeError, ValueError):
        budget_override = None
    max_points_per_message = request.get("max_points_per_message")
    try:
        max_points_per_message = int(max_points_per_message) if max_points_per_message is not None else None
    except (TypeError, ValueError):
        max_points_per_message = None
    message_budget = budget_override or (max_points_per_message or DEFAULT_MAX_POINTS_PER_MESSAGE)

    max_web_search_requests_cap = get_plan_cap(plan_key, "max_web_search_requests", default=5)
    max_final_review_loops_cap = get_plan_cap(plan_key, "max_final_review_loops", default=2)
    max_style_loops_cap = get_plan_cap(plan_key, "max_style_loops", default=2)
    max_granular_passes_cap = get_plan_cap(plan_key, "max_granular_passes", default=2)

    model_ids_for_estimate = [
        judge_model,
        gpt_model,
        claude_model,
        strategist_model or "",
        web_search_model or "",
        *(drafter_models or []),
        *(reviewer_models or []),
    ]
    points_base, billing_breakdown = estimate_langgraph_job_points(
        prompt=str(request.get("prompt") or ""),
        model_ids=[m for m in model_ids_for_estimate if str(m).strip()],
        use_multi_agent=bool(request.get("use_multi_agent", False)),
        drafter_models=drafter_models or [],
        reviewer_models=reviewer_models or [],
        hyde_enabled=bool(request.get("hyde_enabled", False)),
        web_search=bool(request.get("web_search", False)),
        multi_query=bool(request.get("multi_query", True)),
        max_web_search_requests=max_web_search_requests_cap,
        dense_research=bool(request.get("dense_research", False)),
        deep_research_effort=deep_research_effort,
        deep_research_points_multiplier=float(deep_research_multiplier),
        target_pages=int(page_range.get("target_pages") or 0),
        max_style_loops=int(max_style_loops_cap or 0),
        max_final_review_loops=int(max_final_review_loops_cap or 0),
        max_granular_passes=int(max_granular_passes_cap or 0),
    )

    points_summary = await get_points_summary(db, user_id=str(current_user.id), plan_key=plan_key)
    points_available = points_summary.get("available_points")
    wallet_points_balance = int(points_available) if isinstance(points_available, int) else 10**12
    usd_per_point = get_usd_per_point()
    quote = poe_quote_message(
        estimator=FixedPointsEstimator(usd_per_point=usd_per_point, breakdown=billing_breakdown),
        req={"points_estimate": int(points_base)},
        wallet_points_balance=int(wallet_points_balance),
        chat_max_points_per_message=int(message_budget),
        usd_per_point=usd_per_point,
    )
    if not quote.ok:
        status_code = 400
        if quote.error == "insufficient_balance":
            status_code = 402
        elif quote.error == "message_budget_exceeded":
            status_code = 409
        raise HTTPException(status_code=status_code, detail=asdict(quote))

    approved_budget_points = int(message_budget)
    estimated_budget_points = int(quote.estimated_points)

    prompt_text = request.get("prompt", "")
    doc_kind = request.get("doc_kind") or request.get("docKind")
    doc_subtype = request.get("doc_subtype") or request.get("docSubtype")
    if not doc_kind and doc_subtype:
        try:
            from app.services.ai.nodes.catalogo_documentos import infer_doc_kind_subtype
            doc_kind, _ = infer_doc_kind_subtype(doc_subtype)
        except Exception:
            doc_kind = None
    attachment_mode = (request.get("attachment_mode") or "auto").lower()

    attachment_prompt_context = ""
    attachment_rag_context = ""
    context_document_ids = request.get("context_documents") or []
    docs = []
    if context_document_ids:
        try:
            result = await db.execute(
                select(Document).where(Document.id.in_(context_document_ids))
            )
            docs = result.scalars().all()
        except Exception as e:
            logger.warning(f"Erro ao buscar documentos de contexto: {e}")
            docs = []
    context_files = request.get("context_files") or request.get("contextFiles") or []
    if isinstance(context_files, str):
        context_files = [context_files]
    if not isinstance(context_files, list):
        context_files = []
    context_files = [str(path).strip() for path in context_files if str(path).strip()]
    context_files = list(dict.fromkeys(context_files))

    budget_models = [judge_model, gpt_model, claude_model, strategist_model]
    budget_models.extend(drafter_models or [])
    budget_models.extend(reviewer_models or [])
    budget_model_id = _pick_smallest_context_model([m for m in budget_models if m])

    if attachment_mode == "auto" and docs:
        base_context = ""
        attachment_tokens, attachment_chars = _estimate_attachment_stats(docs)
        if attachment_tokens > 0:
            available_tokens = _estimate_available_tokens(budget_model_id, prompt_text, base_context)
            available_chars = max(0, int(available_tokens * 3.5))
            if available_tokens > 0 and attachment_chars > 0 and attachment_chars <= available_chars:
                max_chars = min(attachment_chars, available_chars)
                attachment_prompt_context = _build_attachment_prompt_context(
                    docs,
                    max_chars=max_chars,
                    per_doc_chars=max_chars,
                )
        if not attachment_prompt_context:
            attachment_mode = "rag_local"
        else:
            budget_context = _join_context_parts(base_context, attachment_prompt_context)
            if _should_use_precise_budget(budget_model_id):
                budget = await token_service.check_budget_precise(
                    prompt_text,
                    {"system": budget_context},
                    budget_model_id,
                )
            else:
                budget = token_service.check_budget(
                    prompt_text,
                    {"system": budget_context},
                    budget_model_id,
                )
            if budget["status"] == "error":
                attachment_mode = "rag_local"
                attachment_prompt_context = ""
            else:
                attachment_mode = "prompt_injection"

        stats = summarize_documents(docs)
        logger.info(
            "Auto attachment_mode=%s (files=%s, text_chars=%s, bytes=%s, budget_model=%s)",
            attachment_mode,
            stats.file_count,
            stats.text_chars,
            stats.total_bytes,
            budget_model_id,
        )
    elif attachment_mode == "auto":
        attachment_mode = "rag_local"
    if attachment_mode not in ["rag_local", "prompt_injection"]:
        attachment_mode = "rag_local"

    if attachment_mode == "prompt_injection" and docs and not attachment_prompt_context:
        attachment_prompt_context = _build_attachment_prompt_context(docs)
    if attachment_mode == "prompt_injection" and not attachment_prompt_context:
        attachment_mode = "rag_local"

    if docs and attachment_mode == "rag_local":
        attachment_rag_context = _build_local_rag_context(
            docs=docs,
            query=f"{request.get('document_type', '')}: {prompt_text[:800]}",
            tenant_id="default"
        )
    if context_files:
        context_files_rag_context = await _build_local_rag_context_from_paths(
            context_files=context_files,
            query=f"{request.get('document_type', '')}: {prompt_text[:800]}",
            tenant_id="default",
        )
        attachment_rag_context = _join_context_parts(
            attachment_rag_context,
            context_files_rag_context,
        )

    if attachment_prompt_context:
        prompt_text = f"{prompt_text}\n\n{attachment_prompt_context}"

    audit_mode = request.get("audit_mode", "sei_only")
    strict_document_gate_override = request.get("strict_document_gate")
    if not isinstance(strict_document_gate_override, bool):
        strict_document_gate_override = None
    hil_section_policy = request.get("hil_section_policy")
    if hil_section_policy not in ("none", "optional", "required"):
        hil_section_policy = None
    hil_final_required_override = request.get("hil_final_required")
    if not isinstance(hil_final_required_override, bool):
        hil_final_required_override = None
    auto_approve_hil = request.get("auto_approve_hil")
    if not isinstance(auto_approve_hil, bool):
        auto_approve_hil = False
    recursion_limit_override = request.get("recursion_limit")
    try:
        recursion_limit_override = int(recursion_limit_override) if recursion_limit_override is not None else None
    except (TypeError, ValueError):
        recursion_limit_override = None
    stream_tokens = request.get("stream_tokens")
    if not isinstance(stream_tokens, bool):
        stream_tokens = os.getenv("LANGGRAPH_STREAM_TOKENS", "true").lower() == "true"
    stream_chunk_raw = request.get("stream_token_chunk_chars")
    if stream_chunk_raw is None:
        stream_chunk_raw = os.getenv("LANGGRAPH_STREAM_CHUNK_CHARS", "40")
    try:
        stream_token_chunk_chars = int(stream_chunk_raw)
    except (TypeError, ValueError):
        stream_token_chunk_chars = 40
    stream_token_chunk_chars = max(10, min(stream_token_chunk_chars, 400))

    # Optional overrides (advanced UI)
    thinking_level = request.get("thinking_level")
    if thinking_level is None:
        thinking_level = request.get("reasoning_level", "medium")
    thinking_level = str(thinking_level or "medium").strip().lower() or "medium"

    force_granular_debate = request.get("force_granular_debate")
    if not isinstance(force_granular_debate, bool):
        force_granular_debate = False

    raw_max_divergence_hil_rounds = request.get("max_divergence_hil_rounds")
    try:
        max_divergence_hil_rounds = (
            int(raw_max_divergence_hil_rounds) if raw_max_divergence_hil_rounds is not None else None
        )
    except (TypeError, ValueError):
        max_divergence_hil_rounds = None
    if max_divergence_hil_rounds is not None:
        max_divergence_hil_rounds = max(1, min(max_divergence_hil_rounds, 10))

    # HIL Outline flag - extract for override, will use profile_config fallback later
    hil_outline_override = request.get("hil_outline_enabled")
    if not isinstance(hil_outline_override, bool):
        hil_outline_override = request.get("hil_outline")
    if not isinstance(hil_outline_override, bool):
        hil_outline_override = None  # Will use profile_config default
    profile_config = resolve_quality_profile(
        request.get("quality_profile", "padrao"),
        {
            "target_section_score": request.get("target_section_score"),
            "target_final_score": request.get("target_final_score"),
            "max_rounds": request.get("max_rounds"),
            "strict_document_gate": strict_document_gate_override,
            "hil_section_policy": hil_section_policy,
            "hil_final_required": hil_final_required_override,
            "hil_outline_enabled": hil_outline_override,
            "recursion_limit": recursion_limit_override,
            "style_refine_max_rounds": request.get("style_refine_max_rounds"),
            "max_research_verifier_attempts": request.get("max_research_verifier_attempts"),
            "max_rag_retries": request.get("max_rag_retries"),
            "rag_retry_expand_scope": request.get("rag_retry_expand_scope"),
            "crag_min_best_score": request.get("crag_min_best_score"),
            "crag_min_avg_score": request.get("crag_min_avg_score"),
        }
    )
    max_web_search_requests = get_plan_cap(plan_key, "max_web_search_requests", default=5)
    max_hil_iterations = get_plan_cap(plan_key, "max_hil_iterations", default=0)
    max_final_review_loops_cap = get_plan_cap(
        plan_key,
        "max_final_review_loops",
        default=profile_config.get("max_rounds", 0),
    )
    max_style_loops = get_plan_cap(
        plan_key,
        "max_style_loops",
        default=profile_config.get("style_refine_max_rounds", 2),
    )
    max_granular_passes = get_plan_cap(plan_key, "max_granular_passes", default=2)
    style_refine_max_rounds = int(profile_config.get("style_refine_max_rounds", 2))
    if max_style_loops is not None:
        style_refine_max_rounds = min(style_refine_max_rounds, max_style_loops)
    raw_requested_final_review_loops = request.get("max_final_review_loops")
    try:
        requested_final_review_loops = (
            int(raw_requested_final_review_loops) if raw_requested_final_review_loops is not None else None
        )
    except (TypeError, ValueError):
        requested_final_review_loops = None
    if requested_final_review_loops is not None:
        requested_final_review_loops = max(0, min(requested_final_review_loops, 6))

    final_review_loops = (
        int(requested_final_review_loops)
        if requested_final_review_loops is not None
        else int(profile_config.get("max_rounds", 0))
    )
    if max_final_review_loops_cap is not None:
        final_review_loops = min(final_review_loops, max_final_review_loops_cap)
    final_review_loops = max(0, int(final_review_loops))
    config["recursion_limit"] = int(profile_config.get("recursion_limit", 200))
    sei_context = attachment_prompt_context or attachment_rag_context or None
    prompt_checklist_hint = parse_document_checklist_from_prompt(request.get("prompt", ""))
    merged_checklist_hint = merge_document_checklist_hints(
        request.get("document_checklist_hint", []) or [],
        prompt_checklist_hint,
    )

    rag_sources = [
        str(src).strip()
        for src in (request.get("rag_sources") or [])
        if str(src).strip()
    ]
    rag_top_k_raw = request.get("rag_top_k", 8)
    try:
        rag_top_k_value = int(rag_top_k_raw)
    except (TypeError, ValueError):
        rag_top_k_value = 8
    rag_top_k_value = max(1, min(rag_top_k_value, 50))

    raw_temperature = request.get("temperature")
    try:
        temperature = float(raw_temperature) if raw_temperature is not None else 0.3
    except (TypeError, ValueError):
        temperature = 0.3
    temperature = max(0.0, min(1.0, temperature))

    chat_history = []
    chat_id = request.get("chat_id") or request.get("chatId")
    if chat_id:
        try:
            from app.services.chat_history import fetch_chat_history
            chat_history = await fetch_chat_history(db, chat_id)
        except Exception as e:
            logger.warning(f"⚠️ Falha ao carregar historico do chat {chat_id}: {e}")

    rag_messages = request.get("messages") or chat_history
    conversation_id = request.get("conversation_id") or chat_id or jobid

    citation_style = "abnt"
    deep_enabled = bool(request.get("dense_research", False)) and bool(deep_research_effort)
    web_enabled = bool(request.get("web_search", False)) and audit_mode != "sei_only"
    if max_web_search_requests is not None and max_web_search_requests <= 0:
        web_enabled = False

    context = request.get("context") if isinstance(request, dict) else None
    if not isinstance(context, dict):
        context = {}
    client_request_id = context.get("request_id")
    request_id = str(client_request_id).strip() if client_request_id else ""
    if not request_id:
        request_id = f"{jobid}:{uuid.uuid4().hex}"
    from app.core.security import get_org_context

    org_ctx = await get_org_context(current_user=current_user, db=db)
    # Segurança: derive grupos por membership + policy (não por request.context).
    scope_groups, allow_global_scope, allow_group_scope = await resolve_rag_scope(
        db,
        tenant_id=str(org_ctx.tenant_id),
        user_id=str(org_ctx.user.id),
        user_role=current_user.role,
        chat_context={
            "rag_groups": list(org_ctx.team_ids or []),
            "rag_selected_groups": request.get("rag_selected_groups"),
            "rag_allow_global": None,
            "rag_allow_private": request.get("rag_allow_private"),
            "rag_allow_groups": request.get("rag_allow_groups"),
        },
    )

    # Initial State
    effective_mode = doc_subtype or request.get("document_type", "PETICAO")
    initial_state = {
        "input_text": prompt_text,
        "mode": effective_mode,
        "doc_kind": doc_kind,
        "doc_subtype": doc_subtype or effective_mode,
        "tese": request.get("thesis", ""),
        "job_id": jobid,
        "request_id": request_id,
        "tenant_id": str(org_ctx.tenant_id),
        "rag_scope_groups": scope_groups,
        "rag_allow_global": allow_global_scope,
        "rag_allow_private": request.get("rag_allow_private"),
        "rag_allow_groups": allow_group_scope,
        "messages": rag_messages,
        "conversation_id": conversation_id,
        "deep_research_enabled": deep_enabled,
        "deep_research_effort": deep_research_effort,
        "deep_research_points_multiplier": deep_research_multiplier,
        "deep_research_provider": deep_research_provider,
        "deep_research_model": deep_research_model,
        "web_search_enabled": web_enabled,
        "web_search_model": web_search_model,
        "search_mode": request.get("search_mode", "hybrid"),
        "perplexity_search_mode": request.get("perplexity_search_mode"),
        "perplexity_search_type": request.get("perplexity_search_type"),
        "perplexity_search_context_size": request.get("perplexity_search_context_size"),
        "perplexity_search_classifier": bool(request.get("perplexity_search_classifier", False)),
        "perplexity_disable_search": bool(request.get("perplexity_disable_search", False)),
        "perplexity_stream_mode": request.get("perplexity_stream_mode"),
        "perplexity_search_domain_filter": request.get("perplexity_search_domain_filter"),
        "perplexity_search_language_filter": request.get("perplexity_search_language_filter"),
        "perplexity_search_recency_filter": request.get("perplexity_search_recency_filter"),
        "perplexity_search_after_date": request.get("perplexity_search_after_date"),
        "perplexity_search_before_date": request.get("perplexity_search_before_date"),
        "perplexity_last_updated_after": request.get("perplexity_last_updated_after"),
        "perplexity_last_updated_before": request.get("perplexity_last_updated_before"),
        "perplexity_search_max_results": request.get("perplexity_search_max_results"),
        "perplexity_search_max_tokens": request.get("perplexity_search_max_tokens"),
        "perplexity_search_max_tokens_per_page": request.get("perplexity_search_max_tokens_per_page"),
        "perplexity_search_country": request.get("perplexity_search_country"),
        "perplexity_search_region": request.get("perplexity_search_region"),
        "perplexity_search_city": request.get("perplexity_search_city"),
        "perplexity_search_latitude": request.get("perplexity_search_latitude"),
        "perplexity_search_longitude": request.get("perplexity_search_longitude"),
        "perplexity_return_images": bool(request.get("perplexity_return_images", False)),
        "perplexity_return_videos": bool(request.get("perplexity_return_videos", False)),
        "research_policy": request.get("research_policy", "auto"),
        "research_mode": "none",
        "last_research_step": "none",
        "web_search_insufficient": False,
        "need_juris": False,
        "planning_reasoning": None,
        "planned_queries": [],
        "multi_query": bool(request.get("multi_query", True)),
        "breadth_first": bool(request.get("breadth_first", False)),
        "use_multi_agent": request.get("use_multi_agent", False),
        "thinking_level": thinking_level,
        "auto_approve_hil": bool(auto_approve_hil),
        "chat_personality": request.get("chat_personality", "juridico"),
        "playbook_prompt": request.get("playbook_prompt") or None,
        "temperature": temperature,
        "deep_research_search_focus": request.get("deep_research_search_focus"),
        "deep_research_domain_filter": request.get("deep_research_domain_filter"),
        "deep_research_search_after_date": request.get("deep_research_search_after_date"),
        "deep_research_search_before_date": request.get("deep_research_search_before_date"),
        "deep_research_last_updated_after": request.get("deep_research_last_updated_after"),
        "deep_research_last_updated_before": request.get("deep_research_last_updated_before"),
        "deep_research_country": request.get("deep_research_country"),
        "deep_research_latitude": request.get("deep_research_latitude"),
        "deep_research_longitude": request.get("deep_research_longitude"),

        # Contexto para decisão HIL
        "destino": request.get("destino", "uso_interno"),
        "risco": request.get("risco", "baixo"),

        # Formatting/meta
        "formatting_options": request.get("formatting_options"),
        "template_structure": request.get("template_structure"),
        "citation_style": citation_style,
        "target_pages": page_range["target_pages"],
        "min_pages": page_range["min_pages"],
        "max_pages": page_range["max_pages"],

        # v4.1: CRAG Gate & Adaptive Routing (keys used by langgraph_legal_workflow.py)
        "crag_gate_enabled": bool(request.get("crag_gate", False)),
        "adaptive_routing_enabled": bool(request.get("adaptive_routing", False)),
        "crag_min_best_score": float(profile_config.get("crag_min_best_score", 0.45)),
        "crag_min_avg_score": float(profile_config.get("crag_min_avg_score", 0.35)),
        "rag_sources": rag_sources,
        "rag_top_k": rag_top_k_value,
        "rag_jurisdictions": request.get("rag_jurisdictions"),
        "max_web_search_requests": max_web_search_requests,
        "max_granular_passes": max_granular_passes,
        "max_final_review_loops": final_review_loops,
        "max_divergence_hil_rounds": max_divergence_hil_rounds,
        "force_granular_debate": bool(force_granular_debate),
        "hil_iterations_cap": max_hil_iterations,
        "hil_iterations_count": 0,
        "hil_iterations_by_checkpoint": {},
        "max_research_verifier_attempts": int(profile_config.get("max_research_verifier_attempts", 1)),
        "max_rag_retries": int(profile_config.get("max_rag_retries", 1)),
        "rag_retry_expand_scope": bool(profile_config.get("rag_retry_expand_scope", False)),
        "case_bundle_text_pack": sei_context or "",
        "case_bundle_pdf_paths": [],
        "case_bundle_processo_id": jobid,
        # Extra flags (kept for forward-compat/UI)
        "hyde_enabled": bool(request.get("hyde_enabled", False)),
        "graph_rag_enabled": bool(request.get("graph_rag_enabled", False)),
        "graph_hops": int(request.get("graph_hops", 1) or 1),
        
        # RAG Memory (message history for query rewriting)
        # RAG Routing Observability
        "section_routing_reasons": {},
        
        # Initialize empty collections
        "outline": [],
        "processed_sections": [],
        "full_document": "",
        "research_context": attachment_rag_context or None,
        "research_sources": [],
        "research_notes": None,
        "citations_map": {},
        "deep_research_thinking_steps": [],
        "deep_research_from_cache": False,
        "deep_research_streamed": False,
        "verifier_attempts": 0,
        "verification_retry": False,
        "verification_retry_reason": None,
        "has_any_divergence": False,
        "divergence_summary": "",
        "audit_status": "aprovado",
        "audit_report": None,
        "audit_issues": [],
        "hil_checklist": None,
        "audit_mode": audit_mode,
        "sei_context": sei_context,
        "document_checklist_hint": merged_checklist_hint,
        "document_checklist": None,
        "document_gate_status": None,
        "document_gate_missing": [],
        "style_report": None,
        "style_score": None,
        "style_tone": None,
        "style_issues": [],
        "style_term_variations": [],
        "style_check_status": None,
        "style_check_payload": None,
        "style_instruction": None,
        "style_refine_round": 0,
        "style_refine_max_rounds": style_refine_max_rounds,
        "style_min_score": 8.0,
        "quality_profile": request.get("quality_profile", "padrao"),
        "target_section_score": float(profile_config["target_section_score"]),
        "target_final_score": float(profile_config["target_final_score"]),
        "max_rounds": int(profile_config["max_rounds"]),
        "recursion_limit": int(profile_config.get("recursion_limit", 200)),
        "stream_tokens": bool(stream_tokens),
        "stream_token_chunk_chars": stream_token_chunk_chars,
        "refinement_round": 0,
        "strict_document_gate": bool(profile_config.get("strict_document_gate", False)),
        "hil_section_policy": profile_config.get("hil_section_policy", "optional"),
        "force_final_hil": bool(profile_config.get("hil_final_required", True)),
        "hil_outline_enabled": bool(profile_config.get("hil_outline_enabled", True)),

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
        "final_markdown": "",
        "final_decision": None,
        "final_decision_reasons": [],
        "final_decision_score": None,
        "final_decision_target": None
        ,
	        # Section-level HIL
	        "hil_target_sections": request.get("hil_target_sections", []) or [],
	        "outline_override": request.get("outline_override") or request.get("outlineOverride") or [],
	        "hil_section_payload": None,

        # Outline-level HIL
        "hil_outline_payload": None
        ,
        # Model selection (canonical ids)
        "judge_model": judge_model,
        "gpt_model": gpt_model,
        "claude_model": claude_model,
        "strategist_model": strategist_model,
        "drafter_models": drafter_models,
        "reviewer_models": reviewer_models,

        # Billing / Budget (soft caps, do not abort mid-workflow)
        "budget_approved_points": approved_budget_points,
        "budget_estimate_points": estimated_budget_points,
    }

    if rag_messages and conversation_id:
        try:
            from app.services.ai.rag_memory_store import RAGMemoryStore
            await RAGMemoryStore().set_history(str(conversation_id), rag_messages)
        except Exception as e:
            logger.warning(f"⚠️ Falha ao persistir memoria RAG: {e}")
    
    # Save initial state
    await legal_workflow_app.aupdate_state(config, initial_state)

    job_manager.emit_event(
        jobid,
        "workflow_start",
        {
            "mode": initial_state.get("mode"),
            "auditmode": initial_state.get("audit_mode"),
            "usemultiagent": bool(initial_state.get("use_multi_agent")),
            "outline_len": len(initial_state.get("outline") or []),
        },
        phase="outline",
    )
    
    logger.info(f"🚀 Job {jobid} started with mode={initial_state['mode']}, multi_agent={initial_state['use_multi_agent']}")
    
    return {
        "job_id": jobid,
        "status": "started",
        "request_id": request_id,
        "billing_quote": {
            "estimated_points": int(quote.estimated_points),
            "estimated_usd": float(quote.estimated_usd),
            "approved_points": int(approved_budget_points),
            "usd_per_point": float(usd_per_point),
        },
    }


@router.post("/{jobid}/resume")
async def resume_job(
    jobid: str,
    decision: dict = Body(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Retoma job após revisão humana (HIL checkpoint)
    """
    import uuid
    from datetime import datetime, timezone

    logger.info(f"▶️ Resuming job {jobid} with decision: {decision}")
    config = {"configurable": {"thread_id": jobid}}

    # Get current state to capture original content and hil_history
    original_content = ""
    section_title = None
    hil_history = []
    hil_iteration = 1

    try:
        current_state = legal_workflow_app.get_state(config)
        recursion_limit = int(current_state.values.get("recursion_limit") or 200) if current_state.values else 200
        config["recursion_limit"] = recursion_limit

        if current_state.values:
            # Get existing hil_history
            hil_history = list(current_state.values.get("hil_history") or [])
            hil_iteration = len(hil_history) + 1

            # Capture original content based on checkpoint type
            checkpoint_type = decision.get("checkpoint", "unknown")
            if checkpoint_type == "section":
                payload = current_state.values.get("hil_section_payload") or {}
                original_content = payload.get("merged_content", "")
                section_title = payload.get("section_title")
            elif checkpoint_type == "outline":
                original_content = "\n".join(current_state.values.get("outline") or [])
            elif checkpoint_type == "divergence":
                original_content = current_state.values.get("divergence_summary", "")
            elif checkpoint_type in ("final", "finalize"):
                original_content = current_state.values.get("full_document", "")[:5000]
            elif checkpoint_type == "correction":
                original_content = current_state.values.get("proposed_corrections", "")
    except Exception:
        config["recursion_limit"] = 200

    checkpoint = decision.get("checkpoint", "unknown")
    approved = decision.get("approved", False)
    edits = decision.get("edits")
    instructions = decision.get("instructions")
    proposal = decision.get("proposal")

    # Build HIL history entry
    user_id = str(getattr(current_user, "id", "") or "anonymous")
    user_email = str(getattr(current_user, "email", "") or "")

    hil_entry = {
        "id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checkpoint": checkpoint,
        "section_title": section_title,
        "user_id": user_id,
        "user_email": user_email,
        "decision": "edited" if edits else ("approved" if approved else "rejected"),
        "approved": approved,
        "original_content": original_content[:3000] if original_content else None,
        "edited_content": edits[:3000] if edits else None,
        "instructions": instructions[:1000] if instructions else None,
        "proposal": proposal[:1000] if proposal else None,
        "iteration": hil_iteration,
    }

    # Append to history
    hil_history.append(hil_entry)

    # Resume execution properly by feeding the interrupt() decision back via Command(resume=...)
    resume_payload = {
        "checkpoint": checkpoint,
        "approved": approved,
        "edits": edits,
        "instructions": instructions,
        "hil_target_sections": decision.get("hil_target_sections"),
        # v5.4: allow committee proposal debate when user rejects with a proposal
        "proposal": proposal,
        # v5.6: include updated hil_history
        "hil_history": hil_history,
    }
    job_manager.set_job_user(jobid, str(getattr(current_user, "id", "") or ""))
    with job_context(jobid, user_id=job_manager.get_job_user(jobid)):
        await legal_workflow_app.ainvoke(Command(resume=resume_payload), config)

    # Emit detailed hil_response event for frontend
    job_manager.emit_event(
        jobid,
        "hil_response",
        {
            "checkpoint": checkpoint,
            "approved": approved,
            "has_edits": bool(edits),
            "has_instructions": bool(instructions),
            "has_proposal": bool(proposal),
            "iteration": hil_iteration,
            "user_id": user_id,
            "section_title": section_title,
            "hil_entry": hil_entry,
        },
        phase="hil",
    )

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
            "api_calls": job_manager.get_api_counters(jobid),
            "values": {
                "mode": state.values.get("mode"),
                "outline": state.values.get("outline"),
                "has_divergence": state.values.get("has_any_divergence"),
                "audit_status": state.values.get("audit_status")
            }
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}
