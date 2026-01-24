from typing import List, Dict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import ChatMessage


async def fetch_chat_history(db: AsyncSession, chat_id: str) -> List[Dict[str, str]]:
    if not chat_id:
        return []

    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.chat_id == chat_id)
        .order_by(ChatMessage.created_at.asc())
    )
    messages = result.scalars().all()

    history: List[Dict[str, str]] = []
    for msg in messages or []:
        role = str(msg.role or "").lower()
        if role not in ("user", "assistant"):
            continue
        content = str(msg.content or "").strip()
        if not content:
            continue
        history.append({"role": role, "content": content})

    return history
