"""
Teams Bot endpoint — receives activities from Azure Bot Service,
processes commands, and sends responses (including Adaptive Cards).
"""

import json
import logging

from botbuilder.core import (
    BotFrameworkAdapter,
    BotFrameworkAdapterSettings,
    TurnContext,
)
from botbuilder.schema import Activity, ActivityTypes
from fastapi import APIRouter, Request, Response

from app.core.config import settings
from app.services.teams_bot.bot import IudexBot
from app.services.teams_bot.conversation_store import save_conversation_reference

logger = logging.getLogger(__name__)

router = APIRouter()

# Bot Framework adapter
adapter_settings = BotFrameworkAdapterSettings(
    app_id=settings.TEAMS_BOT_APP_ID or "",
    app_password=settings.TEAMS_BOT_APP_PASSWORD or "",
)
adapter = BotFrameworkAdapter(adapter_settings)

# Bot instance
bot = IudexBot()


@router.post("/webhook")
async def teams_webhook(request: Request) -> Response:
    """Receives activities from Bot Framework (Teams)."""
    body = await request.json()
    activity = Activity().deserialize(body)
    auth_header = request.headers.get("Authorization", "")

    async def call_bot(turn_context: TurnContext):
        await save_conversation_reference(turn_context)
        await bot.on_turn(turn_context)

    try:
        await adapter.process_activity(activity, auth_header, call_bot)
        return Response(status_code=200)
    except Exception as e:
        logger.error(f"Bot webhook error: {e}")
        return Response(status_code=500)


@router.post("/notify/{user_id}")
async def send_proactive_notification(user_id: str, request: Request):
    """Send proactive notification to a user via Teams (called by Celery)."""
    from app.services.teams_bot.conversation_store import get_conversation_reference
    from app.services.teams_bot.cards import build_notification_card

    notification = await request.json()

    ref = await get_conversation_reference(user_id)
    if not ref:
        return {"status": "no_conversation_reference"}

    card = build_notification_card(notification)

    async def send_card(turn_context: TurnContext):
        await turn_context.send_activity(
            Activity(
                type=ActivityTypes.message,
                attachments=[card],
            )
        )

    await adapter.continue_conversation(
        ref,
        send_card,
        settings.TEAMS_BOT_APP_ID or "",
    )
    return {"status": "sent"}
