"""
Redis-based ConversationReference storage for proactive messaging.
Stores references with a 30-day TTL so the bot can send proactive
messages to users who have previously interacted.
"""

import json
import logging

import redis.asyncio as aioredis
from botbuilder.core import TurnContext
from botbuilder.schema import ConversationReference

from app.core.config import settings

logger = logging.getLogger(__name__)

# 30-day TTL for conversation references
CONVERSATION_REF_TTL = 60 * 60 * 24 * 30  # 30 days in seconds

_redis: aioredis.Redis | None = None


async def _get_redis() -> aioredis.Redis:
    """Get or create async Redis connection."""
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
        )
    return _redis


def _key(user_id: str) -> str:
    """Build Redis key for a conversation reference."""
    return f"teams:conv_ref:{user_id}"


async def save_conversation_reference(turn_context: TurnContext) -> None:
    """
    Save ConversationReference from a TurnContext.
    Keyed by the user's AAD Object ID (or fallback to activity from_id).
    """
    activity = turn_context.activity
    aad_id = getattr(activity.from_property, "aad_object_id", None)
    user_id = aad_id or activity.from_property.id

    if not user_id:
        logger.warning("Cannot save conversation reference: no user_id")
        return

    ref = TurnContext.get_conversation_reference(activity)
    ref_dict = ref.serialize() if hasattr(ref, "serialize") else ref.__dict__

    r = await _get_redis()
    await r.set(
        _key(user_id),
        json.dumps(ref_dict, default=str),
        ex=CONVERSATION_REF_TTL,
    )
    logger.debug("Saved conversation reference for user %s", user_id)


async def get_conversation_reference(user_id: str) -> ConversationReference | None:
    """
    Retrieve a stored ConversationReference for proactive messaging.
    Returns None if no reference is stored or it has expired.
    """
    r = await _get_redis()
    data = await r.get(_key(user_id))

    if not data:
        return None

    try:
        ref_dict = json.loads(data)
        ref = ConversationReference().deserialize(ref_dict)
        return ref
    except Exception as e:
        logger.error("Error deserializing conversation reference for %s: %s", user_id, e)
        return None


async def delete_conversation_reference(user_id: str) -> None:
    """Remove a stored ConversationReference."""
    r = await _get_redis()
    await r.delete(_key(user_id))
    logger.debug("Deleted conversation reference for user %s", user_id)
