"""
Proactive messaging — send Adaptive Cards to users outside of a turn.

Uses stored ConversationReferences from conversation_store.py
to reach users who previously interacted with the bot.
"""

import logging

from botbuilder.core import BotFrameworkAdapter, BotFrameworkAdapterSettings, TurnContext
from botbuilder.schema import Activity, Attachment

from app.core.config import settings
from app.services.teams_bot.conversation_store import get_conversation_reference

logger = logging.getLogger(__name__)

_adapter: BotFrameworkAdapter | None = None


def _get_adapter() -> BotFrameworkAdapter:
    """Get or create Bot Framework adapter for proactive messaging."""
    global _adapter
    if _adapter is None:
        adapter_settings = BotFrameworkAdapterSettings(
            app_id=settings.TEAMS_BOT_APP_ID or "",
            app_password=settings.TEAMS_BOT_APP_PASSWORD or "",
        )
        _adapter = BotFrameworkAdapter(adapter_settings)
    return _adapter


async def send_proactive_card(conversation_id: str, card: dict) -> bool:
    """Send an Adaptive Card to a user via proactive messaging.

    Args:
        conversation_id: The user's AAD Object ID or conversation reference key.
        card: Adaptive Card dict to send.

    Returns:
        True if sent successfully, False otherwise.
    """
    ref = await get_conversation_reference(conversation_id)
    if not ref:
        logger.warning("No conversation reference found for %s", conversation_id)
        return False

    adapter = _get_adapter()

    attachment = Attachment(
        content_type="application/vnd.microsoft.card.adaptive",
        content=card,
    )

    async def _send(turn_context: TurnContext):
        activity = Activity(
            type="message",
            attachments=[attachment],
        )
        await turn_context.send_activity(activity)

    try:
        await adapter.continue_conversation(ref, _send, settings.TEAMS_BOT_APP_ID or "")
        logger.info("Proactive card sent to %s", conversation_id)
        return True
    except Exception as e:
        logger.error("Failed to send proactive card to %s: %s", conversation_id, e)
        return False


async def send_proactive_text(conversation_id: str, text: str) -> bool:
    """Send a plain text message to a user via proactive messaging."""
    ref = await get_conversation_reference(conversation_id)
    if not ref:
        logger.warning("No conversation reference found for %s", conversation_id)
        return False

    adapter = _get_adapter()

    async def _send(turn_context: TurnContext):
        await turn_context.send_activity(text)

    try:
        await adapter.continue_conversation(ref, _send, settings.TEAMS_BOT_APP_ID or "")
        logger.info("Proactive text sent to %s", conversation_id)
        return True
    except Exception as e:
        logger.error("Failed to send proactive text to %s: %s", conversation_id, e)
        return False
