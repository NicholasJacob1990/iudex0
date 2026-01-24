from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.chat import Chat, ChatMessage
from app.models.user import User
from app.schemas.chat import MessageCreate
from app.services.ai.agent_clients import build_system_instruction
from app.services.billing_quote_service import estimate_chat_turn_points, FixedPointsEstimator
from app.services.billing_service import (
    get_points_summary,
    get_usd_per_point,
    resolve_chat_max_points_per_message,
    resolve_deep_research_billing,
    resolve_plan_key,
    get_plan_cap,
)
from app.services.poe_like_billing import quote_message as poe_quote_message
from app.services.token_budget_service import TokenBudgetService

router = APIRouter()
token_service = TokenBudgetService()


class QuoteMessageRequest(BaseModel):
    chat_id: str = Field(..., min_length=1)
    message: MessageCreate


@router.get("/summary")
async def get_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    plan_key = resolve_plan_key(getattr(current_user, "plan", None))
    return await get_points_summary(db, user_id=str(current_user.id), plan_key=plan_key)


@router.post("/quote_message")
async def quote_message(
    payload: QuoteMessageRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    chat_result = await db.execute(
        select(Chat).where(Chat.id == payload.chat_id, Chat.user_id == current_user.id)
    )
    chat = chat_result.scalars().first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat não encontrado")

    message_in = payload.message
    plan_key = resolve_plan_key(getattr(current_user, "plan", None))
    deep_effort, deep_multiplier = resolve_deep_research_billing(plan_key, message_in.deep_research_effort)

    max_web_search_requests = get_plan_cap(plan_key, "max_web_search_requests", default=5)
    web_search_flag = bool(message_in.web_search)
    if max_web_search_requests is not None and max_web_search_requests <= 0:
        web_search_flag = False

    base_instruction = build_system_instruction(message_in.chat_personality)
    history_rows = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.chat_id == payload.chat_id)
        .order_by(desc(ChatMessage.created_at))
        .limit(12)
    )
    history = history_rows.scalars().all()
    history_text = "\n".join([str(m.content or "") for m in reversed(history or []) if m and m.content])
    context_tokens_est = token_service.estimate_tokens(
        "\n\n".join([base_instruction or "", history_text, str(message_in.content or "")]).strip()
    )

    requested_model = (message_in.model or chat.context.get("model") or "gpt-5.2").strip()
    points_base, breakdown = estimate_chat_turn_points(
        model_id=requested_model,
        context_tokens=context_tokens_est,
        web_search=bool(web_search_flag),
        max_web_search_requests=max_web_search_requests,
        multi_query=bool(message_in.multi_query),
        dense_research=bool(message_in.dense_research) and bool(deep_effort),
        deep_research_effort=deep_effort,
        deep_research_points_multiplier=float(deep_multiplier),
        perplexity_search_type=message_in.perplexity_search_type,
        perplexity_search_context_size=message_in.perplexity_search_context_size,
        perplexity_disable_search=bool(message_in.perplexity_disable_search),
    )

    points_summary = await get_points_summary(db, user_id=str(current_user.id), plan_key=plan_key)
    points_available = points_summary.get("available_points")
    wallet_points_balance = int(points_available) if isinstance(points_available, int) else 10**12

    budget_override = message_in.budget_override_points
    message_budget = budget_override or resolve_chat_max_points_per_message(chat.context)

    usd_per_point = get_usd_per_point()
    quote = poe_quote_message(
        estimator=FixedPointsEstimator(usd_per_point=usd_per_point, breakdown=breakdown),
        req={"points_estimate": int(points_base)},
        wallet_points_balance=int(wallet_points_balance),
        chat_max_points_per_message=int(message_budget),
        usd_per_point=usd_per_point,
    )
    out = asdict(quote)
    out["wallet"] = points_summary
    out["message_budget"] = int(message_budget)
    return out


@router.get("/pricing_sheet")
async def pricing_sheet(
    model_id: str = Query("gpt-5.2"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    plan_key = resolve_plan_key(getattr(current_user, "plan", None))
    points_summary = await get_points_summary(db, user_id=str(current_user.id), plan_key=plan_key)
    usd_per_point = float(points_summary.get("usd_per_point") or get_usd_per_point())
    cfg = model_id.strip() or "gpt-5.2"

    billing_cfg = points_summary  # keep response small; frontend already fetches /config/billing

    return {
        "points_available": points_summary.get("available_points"),
        "subscription_label": str(getattr(current_user, "plan", "")),
        "bot": {"id": cfg, "name": cfg},
        "pricing_model": "variable",
        "notes": [
            "Preços exibidos em pontos (âncora USD/point).",
            "O custo real é calculado por eventos de uso (api_call_usage).",
        ],
        "usd_per_point": usd_per_point,
        "billing_summary": billing_cfg,
    }

