"""
Microsoft Graph API — Calendar operations.

Create, list and manage calendar events using the user's Graph OBO token.
"""

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.graph_client import GraphClient

logger = logging.getLogger(__name__)


async def _get_graph_token(user_id: str, db: AsyncSession) -> Optional[str]:
    """Resolve user_id → microsoft_oid → Redis graph_token."""
    from app.core.redis import redis_client
    from app.models.microsoft_user import MicrosoftUser
    from sqlalchemy import select

    if not redis_client:
        return None

    stmt = select(MicrosoftUser).where(MicrosoftUser.user_id == user_id)
    result = await db.execute(stmt)
    ms_user = result.scalar_one_or_none()
    if not ms_user:
        return None

    return await redis_client.get(f"graph_token:{ms_user.microsoft_oid}")


async def create_event(
    user_id: str,
    subject: str,
    body_html: str,
    start: datetime,
    end: datetime,
    db: AsyncSession,
    attendees: list[str] | None = None,
    location: str | None = None,
    reminder_minutes: int = 15,
    timezone: str = "America/Sao_Paulo",
) -> dict:
    """Create a calendar event via Microsoft Graph API.

    Returns the created event dict from Graph.
    Raises RuntimeError if token not available.
    """
    token = await _get_graph_token(user_id, db)
    if not token:
        raise RuntimeError(f"Graph token unavailable for user {user_id}")

    event_payload: dict = {
        "subject": subject,
        "body": {
            "contentType": "HTML",
            "content": body_html,
        },
        "start": {
            "dateTime": start.strftime("%Y-%m-%dT%H:%M:%S"),
            "timeZone": timezone,
        },
        "end": {
            "dateTime": end.strftime("%Y-%m-%dT%H:%M:%S"),
            "timeZone": timezone,
        },
        "isReminderOn": True,
        "reminderMinutesBeforeStart": reminder_minutes,
    }

    if attendees:
        event_payload["attendees"] = [
            {
                "emailAddress": {"address": addr},
                "type": "required",
            }
            for addr in attendees
        ]

    if location:
        event_payload["location"] = {"displayName": location}

    async with GraphClient(token) as client:
        result = await client.post("/me/events", json_data=event_payload)

    logger.info(f"Calendar event created: {subject} ({start} - {end})")
    return result


async def list_events(
    user_id: str,
    start: datetime,
    end: datetime,
    db: AsyncSession,
    timezone: str = "America/Sao_Paulo",
) -> list[dict]:
    """List calendar events in a date range via Microsoft Graph API."""
    token = await _get_graph_token(user_id, db)
    if not token:
        raise RuntimeError(f"Graph token unavailable for user {user_id}")

    params = {
        "startdatetime": start.isoformat(),
        "enddatetime": end.isoformat(),
        "$select": "id,subject,start,end,location,attendees,bodyPreview",
        "$orderby": "start/dateTime",
        "$top": "50",
    }

    async with GraphClient(token) as client:
        data = await client.get("/me/calendarview", params=params)
        return data.get("value", [])
