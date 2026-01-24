"""
Chat API Endpoints - Multi-Model Support

Exposes:
- POST /chat/threads: Create new conversation
- GET /chat/threads: List conversations
- POST /chat/threads/{id}/messages: Send message (SSE streaming)
- POST /chat/threads/{id}/consolidate: Consolidate multi-model candidates into a single answer
"""

from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Body, Depends
from fastapi.responses import StreamingResponse
from loguru import logger
import json
import uuid
from typing import List, Dict, Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.document import Document
from app.models.user import User
from app.services.chat_service import chat_service
from app.services.api_call_tracker import usage_context, billing_context
from app.services.token_budget_service import TokenBudgetService
from app.services.billing_service import (
    get_points_summary,
    get_usd_per_point,
    resolve_plan_key,
    resolve_chat_max_points_per_message,
    resolve_deep_research_billing,
    get_plan_cap,
    get_deep_research_monthly_status,
)
from app.services.billing_quote_service import estimate_chat_turn_points, FixedPointsEstimator
from app.services.poe_like_billing import quote_message as poe_quote_message
from app.services.ai.model_registry import validate_model_id, DEFAULT_JUDGE_MODEL
from app.services.ai.agent_clients import build_system_instruction
from app.services.ai.prompt_flags import (
    parse_prompt_flags,
    apply_verbosity_instruction,
    clamp_thinking_budget,
)

router = APIRouter()

token_service = TokenBudgetService()

# --- SSE HELPER ---
def sse_event(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


def _collect_attachment_ids(attachments: Optional[List[Any]]) -> List[str]:
    ids: List[str] = []
    for item in attachments or []:
        if isinstance(item, str):
            ids.append(item)
            continue
        if isinstance(item, dict):
            raw = item.get("id") or item.get("document_id") or item.get("doc_id")
            if raw:
                ids.append(str(raw))
    return list(dict.fromkeys(ids))


async def _load_attachment_docs(
    db: AsyncSession,
    user_id: str,
    attachments: Optional[List[Any]],
) -> List[Document]:
    ids = _collect_attachment_ids(attachments)
    if not ids:
        return []
    result = await db.execute(
        select(Document).where(
            Document.user_id == user_id,
            Document.id.in_(ids),
        )
    )
    docs = result.scalars().all()
    by_id = {doc.id: doc for doc in docs}
    return [by_id[doc_id] for doc_id in ids if doc_id in by_id]

@router.post("/threads")
async def create_thread(
    title: str = Body("Nova Conversa", embed=True)
):
    """Create a new chat thread"""
    try:
        thread = chat_service.thread_manager.create_thread(title)
        return thread
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/threads")
async def list_threads(limit: int = 20):
    """List recent threads"""
    return chat_service.thread_manager.list_threads(limit)

@router.get("/threads/{thread_id}")
async def get_thread(thread_id: str):
    """Get full thread history"""
    thread = chat_service.thread_manager.get_thread(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    return thread

@router.post("/threads/{thread_id}/messages")
async def send_message(
    thread_id: str,
    message: str = Body(...),
    models: List[str] = Body(...),
    budget_override_points: Optional[int] = Body(default=None, ge=1),
    attachments: Optional[List[Dict[str, Any]]] = Body(default_factory=list),
    attachment_mode: str = Body("auto"),
    chat_personality: str = Body("juridico"),
    reasoning_level: str = Body("medium"),
    verbosity: Optional[str] = Body(None),
    thinking_budget: Optional[int] = Body(None, ge=0),
    temperature: Optional[float] = Body(None),
    web_search: bool = Body(False),
    multi_query: bool = Body(True),
    breadth_first: bool = Body(False),
    search_mode: str = Body("hybrid"),
    perplexity_search_mode: Optional[str] = Body(None),
    perplexity_search_type: Optional[str] = Body(None),
    perplexity_search_context_size: Optional[str] = Body(None),
    perplexity_search_classifier: bool = Body(False),
    perplexity_disable_search: bool = Body(False),
    perplexity_stream_mode: Optional[str] = Body(None),
    perplexity_search_domain_filter: Optional[str] = Body(None),
    perplexity_search_language_filter: Optional[str] = Body(None),
    perplexity_search_recency_filter: Optional[str] = Body(None),
    perplexity_search_after_date: Optional[str] = Body(None),
    perplexity_search_before_date: Optional[str] = Body(None),
    perplexity_last_updated_after: Optional[str] = Body(None),
    perplexity_last_updated_before: Optional[str] = Body(None),
    perplexity_search_max_results: Optional[int] = Body(None, ge=1, le=20),
    perplexity_search_max_tokens: Optional[int] = Body(None, ge=1, le=1_000_000),
    perplexity_search_max_tokens_per_page: Optional[int] = Body(None, ge=1, le=1_000_000),
    perplexity_search_country: Optional[str] = Body(None),
    perplexity_search_region: Optional[str] = Body(None),
    perplexity_search_city: Optional[str] = Body(None),
    perplexity_search_latitude: Optional[str] = Body(None),
    perplexity_search_longitude: Optional[str] = Body(None),
    perplexity_return_images: bool = Body(False),
    perplexity_return_videos: bool = Body(False),
    rag_sources: Optional[List[str]] = Body(None),
    rag_top_k: int = Body(8),
    adaptive_routing: bool = Body(False),
    crag_gate: bool = Body(False),
    crag_min_best_score: float = Body(0.45),
    crag_min_avg_score: float = Body(0.35),
    hyde_enabled: bool = Body(False),
    graph_rag_enabled: bool = Body(False),
    argument_graph_enabled: Optional[bool] = Body(None),
    graph_hops: int = Body(1),
    dense_research: bool = Body(False),
    rag_scope: str = Body("case_and_global"),  # case_only, case_and_global, global_only
    deep_research_effort: Optional[str] = Body(None),
    deep_research_provider: Optional[str] = Body(None),
    deep_research_model: Optional[str] = Body(None),
    deep_research_search_focus: Optional[str] = Body(None),
    deep_research_domain_filter: Optional[str] = Body(None),
    deep_research_search_after_date: Optional[str] = Body(None),
    deep_research_search_before_date: Optional[str] = Body(None),
    deep_research_last_updated_after: Optional[str] = Body(None),
    deep_research_last_updated_before: Optional[str] = Body(None),
    deep_research_country: Optional[str] = Body(None),
    deep_research_latitude: Optional[str] = Body(None),
    deep_research_longitude: Optional[str] = Body(None),
    research_policy: str = Body("auto"),
    per_model_overrides: Optional[Dict[str, Dict[str, Any]]] = Body(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Send message to one or more models.
    Returns: SSE Stream
    """
    logger.info(
        "💬 Chat request in %s for models: %s (graph_rag=%s argument_graph=%s)",
        thread_id,
        models,
        graph_rag_enabled,
        argument_graph_enabled,
    )

    parsed_flags = parse_prompt_flags(message)
    if parsed_flags.clean_text != message:
        message = parsed_flags.clean_text
    if parsed_flags.web_search is not None:
        web_search = parsed_flags.web_search
    if parsed_flags.reasoning_level:
        reasoning_level = parsed_flags.reasoning_level
    verbosity_override = parsed_flags.verbosity
    thinking_budget_override = clamp_thinking_budget(parsed_flags.thinking_budget)
    if verbosity is not None:
        verbosity_override = str(verbosity).strip().lower()
    if thinking_budget is not None:
        thinking_budget_override = clamp_thinking_budget(thinking_budget)

    per_model_overrides_payload: Optional[Dict[str, Dict[str, Any]]] = None
    if isinstance(per_model_overrides, dict):
        normalized: Dict[str, Dict[str, Any]] = {}
        for raw_id, overrides in per_model_overrides.items():
            if not isinstance(overrides, dict):
                continue
            try:
                model_id = validate_model_id(str(raw_id), for_juridico=True, field_name="per_model_overrides")
            except ValueError:
                continue
            entry: Dict[str, Any] = {}
            verbosity_raw = overrides.get("verbosity")
            if isinstance(verbosity_raw, str):
                v = verbosity_raw.strip().lower()
                if v in ("low", "medium", "high"):
                    entry["verbosity"] = v
            reasoning_raw = overrides.get("reasoning_level")
            if isinstance(reasoning_raw, str):
                r = reasoning_raw.strip().lower()
                if r in ("none", "minimal", "low", "medium", "high", "xhigh"):
                    entry["reasoning_level"] = r
            if "thinking_budget" in overrides:
                budget = clamp_thinking_budget(overrides.get("thinking_budget"), model_id)
                if budget is not None:
                    entry["thinking_budget"] = budget
            if entry:
                normalized[model_id] = entry
        if normalized:
            per_model_overrides_payload = normalized
    
    attachment_docs = await _load_attachment_docs(db, current_user.id, attachments)
    turn_id = str(uuid.uuid4())
    plan_key = resolve_plan_key(getattr(current_user, "plan", None))
    effort, points_multiplier = resolve_deep_research_billing(plan_key, deep_research_effort)
    if not effort:
        dense_research = False
    if dense_research and effort:
        status = await get_deep_research_monthly_status(
            db,
            user_id=str(current_user.id),
            plan_key=plan_key,
        )
        if not status.get("allowed", True):
            dense_research = False
            effort = None
            points_multiplier = 1.0
    max_web_search_requests = get_plan_cap(plan_key, "max_web_search_requests", default=5)
    if max_web_search_requests is not None and max_web_search_requests <= 0:
        web_search = False

    # --- Poe-like billing: quote + gates (wallet + per-message budget) ---
    safe_models: List[str] = []
    for raw in models or []:
        mid = str(raw or "").strip()
        if not mid:
            continue
        try:
            safe_models.append(validate_model_id(mid, for_juridico=True, field_name="models"))
        except ValueError:
            continue
    if not safe_models:
        safe_models = [DEFAULT_JUDGE_MODEL]

    thread = chat_service.thread_manager.get_thread(thread_id)
    history_text = ""
    if thread and getattr(thread, "messages", None):
        tail = list(thread.messages)[-20:]
        history_text = "\n".join(str(m.content or "") for m in tail if getattr(m, "content", None))

    base_instruction = apply_verbosity_instruction(
        build_system_instruction(chat_personality),
        verbosity_override,
    )

    context_tokens_est = token_service.estimate_tokens(
        "\n\n".join([base_instruction or "", history_text, str(message or "")]).strip()
    )

    # LLM points: sum across models (tools are shared in ChatService.dispatch_turn)
    llm_components: List[Dict[str, Any]] = []
    llm_points_total = 0
    for model_id in safe_models:
        pts, br = estimate_chat_turn_points(
            model_id=model_id,
            context_tokens=context_tokens_est,
            web_search=False,
            max_web_search_requests=0,
            multi_query=False,
            dense_research=False,
            deep_research_effort=None,
            deep_research_points_multiplier=1.0,
            perplexity_search_type=perplexity_search_type,
            perplexity_search_context_size=perplexity_search_context_size,
            perplexity_disable_search=bool(perplexity_disable_search),
        )
        llm_points_total += int(pts)
        llm_components.append({"model": model_id, "points": int(pts), "breakdown": br})

    tool_components: List[Dict[str, Any]] = []
    tool_points_total = 0
    # Tool cost is shared once across the whole multi-model turn.
    if web_search and (max_web_search_requests is None or max_web_search_requests > 0):
        from app.services.billing_service import calculate_points

        per_request = calculate_points(kind="web_search", provider="tool", model=None, meta=None) or 0
        est_requests = 2 if multi_query else 1
        if isinstance(max_web_search_requests, int):
            est_requests = max(1, min(est_requests, int(max_web_search_requests)))
        ws_points = int(per_request) * int(est_requests)
        tool_points_total += ws_points
        tool_components.append(
            {
                "kind": "web_search",
                "n_requests_est": int(est_requests),
                "points_per_request": int(per_request),
                "points": int(ws_points),
            }
        )

    if dense_research and effort:
        from app.services.billing_service import calculate_points

        dr_points = (
            calculate_points(
                kind="deep_research",
                provider="tool",
                model=None,
                meta={"effort": effort, "points_multiplier": points_multiplier},
            )
            or 0
        )
        tool_points_total += int(dr_points)
        tool_components.append(
            {
                "kind": "deep_research",
                "effort": str(effort),
                "points_multiplier": float(points_multiplier),
                "points": int(dr_points),
            }
        )

    points_base = int(llm_points_total + tool_points_total)
    billing_breakdown = {
        "estimator": "multichat_turn_v1",
        "context_tokens_est": int(context_tokens_est),
        "models": safe_models,
        "components": {
            "llm": llm_components,
            "tools": tool_components,
        },
        "points_llm_total": int(llm_points_total),
        "points_tools_total": int(tool_points_total),
        "points_total_base": int(points_base),
    }

    points_summary = await get_points_summary(
        db,
        user_id=str(current_user.id),
        plan_key=plan_key,
    )
    points_available = points_summary.get("available_points")
    wallet_points_balance = int(points_available) if isinstance(points_available, int) else 10**12

    try:
        budget_override = int(budget_override_points) if budget_override_points is not None else None
    except (TypeError, ValueError):
        budget_override = None
    message_budget = budget_override or resolve_chat_max_points_per_message({})

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

    async def event_generator():
        try:
            with usage_context("thread", thread_id, user_id=current_user.id, turn_id=turn_id):
                with billing_context(
                    graph_rag_enabled=graph_rag_enabled,
                    argument_graph_enabled=argument_graph_enabled,
                ):
                    async for event in chat_service.dispatch_turn(
                        thread_id,
                        message,
                        models,
                        attachment_docs=attachment_docs,
                        attachment_mode=attachment_mode,
                        tenant_id=current_user.id,
                        chat_personality=chat_personality,
                        reasoning_level=reasoning_level,
                        temperature=temperature,
                        web_search=web_search,
                        multi_query=multi_query,
                        breadth_first=breadth_first,
                        search_mode=search_mode,
                        perplexity_search_mode=perplexity_search_mode,
                        perplexity_search_type=perplexity_search_type,
                        perplexity_search_context_size=perplexity_search_context_size,
                        perplexity_search_classifier=perplexity_search_classifier,
                        perplexity_disable_search=perplexity_disable_search,
                        perplexity_stream_mode=perplexity_stream_mode,
                        perplexity_search_domain_filter=perplexity_search_domain_filter,
                        perplexity_search_language_filter=perplexity_search_language_filter,
                        perplexity_search_recency_filter=perplexity_search_recency_filter,
                        perplexity_search_after_date=perplexity_search_after_date,
                        perplexity_search_before_date=perplexity_search_before_date,
                        perplexity_last_updated_after=perplexity_last_updated_after,
                        perplexity_last_updated_before=perplexity_last_updated_before,
                        perplexity_search_max_results=perplexity_search_max_results,
                        perplexity_search_max_tokens=perplexity_search_max_tokens,
                        perplexity_search_max_tokens_per_page=perplexity_search_max_tokens_per_page,
                        perplexity_search_country=perplexity_search_country,
                        perplexity_search_region=perplexity_search_region,
                        perplexity_search_city=perplexity_search_city,
                        perplexity_search_latitude=perplexity_search_latitude,
                        perplexity_search_longitude=perplexity_search_longitude,
                        perplexity_return_images=perplexity_return_images,
                        perplexity_return_videos=perplexity_return_videos,
                        rag_sources=rag_sources,
                        rag_top_k=rag_top_k,
                        adaptive_routing=adaptive_routing,
                        crag_gate=crag_gate,
                        crag_min_best_score=crag_min_best_score,
                        crag_min_avg_score=crag_min_avg_score,
                        hyde_enabled=hyde_enabled,
                        graph_rag_enabled=graph_rag_enabled,
                        graph_hops=graph_hops,
                        argument_graph_enabled=argument_graph_enabled,
                        dense_research=dense_research,
                        rag_scope=rag_scope,
                        deep_research_effort=effort,
                        verbosity=verbosity_override,
                        thinking_budget=thinking_budget_override,
                        deep_research_provider=deep_research_provider,
                        deep_research_model=deep_research_model,
                        deep_research_search_focus=deep_research_search_focus,
                        deep_research_domain_filter=deep_research_domain_filter,
                        deep_research_search_after_date=deep_research_search_after_date,
                        deep_research_search_before_date=deep_research_search_before_date,
                        deep_research_last_updated_after=deep_research_last_updated_after,
                        deep_research_last_updated_before=deep_research_last_updated_before,
                        deep_research_country=deep_research_country,
                        deep_research_latitude=deep_research_latitude,
                        deep_research_longitude=deep_research_longitude,
                        deep_research_points_multiplier=points_multiplier,
                        max_web_search_requests=max_web_search_requests,
                        research_policy=research_policy,
                        per_model_overrides=per_model_overrides_payload,
                    ):
                        yield sse_event(event)
        except Exception as e:
            logger.error(f"Stream error: {e}")
            yield sse_event({"type": "error", "error": str(e)})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive"
        }
    )


@router.post("/threads/{thread_id}/consolidate")
async def consolidate_turn(
    thread_id: str,
    message: str = Body(...),
    candidates: List[Dict[str, Any]] = Body(...),
    budget_override_points: Optional[int] = Body(default=None, ge=1),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Consolidate multiple model answers into a single "judge/merge" response.
    candidates: [{ "model": "gpt-4o", "text": "..." }, ...]
    """
    try:
        turn_id = str(uuid.uuid4())
        plan_key = resolve_plan_key(getattr(current_user, "plan", None))

        candidates_text = "\n\n".join(str(c.get("text") or "") for c in (candidates or []) if isinstance(c, dict))
        context_tokens_est = token_service.estimate_tokens(
            "\n\n".join([str(message or ""), candidates_text]).strip()
        )
        # Worst-case among typical judge models (ChatService tries multiple providers)
        judge_candidates = ["gpt-5.2", "claude-4.5-sonnet", "gemini-3-flash"]
        judge_points = 0
        judge_pick = DEFAULT_JUDGE_MODEL
        judge_breakdown = {}
        for mid in judge_candidates:
            try:
                model_id = validate_model_id(mid, for_juridico=True, field_name="judge_model")
            except ValueError:
                continue
            pts, br = estimate_chat_turn_points(
                model_id=model_id,
                context_tokens=context_tokens_est,
                web_search=False,
                max_web_search_requests=0,
                multi_query=False,
                dense_research=False,
                deep_research_effort=None,
            )
            if int(pts) > int(judge_points):
                judge_points = int(pts)
                judge_pick = model_id
                judge_breakdown = br

        billing_breakdown = {
            "estimator": "multichat_consolidate_v1",
            "context_tokens_est": int(context_tokens_est),
            "judge_model_est": judge_pick,
            "judge_points_est": int(judge_points),
            "components": [judge_breakdown] if judge_breakdown else [],
            "points_total_base": int(judge_points),
        }

        points_summary = await get_points_summary(
            db,
            user_id=str(current_user.id),
            plan_key=plan_key,
        )
        points_available = points_summary.get("available_points")
        wallet_points_balance = int(points_available) if isinstance(points_available, int) else 10**12
        try:
            budget_override = int(budget_override_points) if budget_override_points is not None else None
        except (TypeError, ValueError):
            budget_override = None
        message_budget = budget_override or resolve_chat_max_points_per_message({})
        usd_per_point = get_usd_per_point()
        quote = poe_quote_message(
            estimator=FixedPointsEstimator(usd_per_point=usd_per_point, breakdown=billing_breakdown),
            req={"points_estimate": int(judge_points)},
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

        with usage_context("thread", thread_id, user_id=current_user.id, turn_id=turn_id):
            merged = await chat_service.consolidate_turn(thread_id, message, candidates)
        return {"content": merged}
    except Exception as e:
        logger.error(f"Consolidate error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/threads/{thread_id}/edit")
async def edit_document(
    thread_id: str,
    message: str = Body(..., description="Edit command from user"),
    document: str = Body(..., description="Full document or section to edit"),
    selection: str = Body(None, description="Optional selected text to focus on"),
    selection_context_before: str = Body(None, description="Optional selection context before"),
    selection_context_after: str = Body(None, description="Optional selection context after"),
    models: List[str] = Body(None, description="Models to use. None=committee, ['model']=fast mode"),
    mode: str = Body("committee", description="Mode: committee, fast, debate, engineering")
):
    """
    v5.4: Edit document via agent committee or single model.
    
    Pass models=None for full committee (GPT + Claude + Gemini Judge).
    Pass models=["gemini-3-flash"] for single-model.
    Pass mode="engineering" for Agentic Engineering Pipeline.
    """
    effective_mode = mode
    if models and len(models) == 1:
        effective_mode = "fast"
    elif not mode or mode == "committee":
        if not models:
             effective_mode = "committee"
    
    mode_label = effective_mode
    logger.info(f"📝 Edit request [{mode_label}] in {thread_id}: {message[:50]}...")
    turn_id = str(uuid.uuid4())
    
    async def event_generator():
        try:
            with usage_context("thread", thread_id, turn_id=turn_id):
                async for event in chat_service.dispatch_document_edit(
                    thread_id,
                    message,
                    document,
                    selection,
                    models,
                    None,
                    None,
                    selection_context_before,
                    selection_context_after,
                    use_debate=(mode == "debate"),
                    mode=mode
                ):
                    yield sse_event(event)
        except Exception as e:
            logger.error(f"Edit stream error: {e}")
            yield sse_event({"type": "error", "error": str(e)})
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive"
        }
    )
