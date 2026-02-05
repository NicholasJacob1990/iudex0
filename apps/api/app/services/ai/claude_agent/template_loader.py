"""
Template Loader — Loads user's .md agent templates as system instructions.

Agent templates are stored as LibraryItem entries with type=PROMPT and
tag "agent_template". The template content is stored in the description field.
"""

from __future__ import annotations

from typing import Optional

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.library import LibraryItem, LibraryItemType


async def load_agent_templates(user_id: str, db: AsyncSession) -> str:
    """Load all active agent templates for a user and concatenate as system instructions.

    Args:
        user_id: The user whose templates to load.
        db: Async database session.

    Returns:
        Concatenated markdown string of all matching templates, or empty string.
    """
    try:
        stmt = (
            select(LibraryItem)
            .where(
                LibraryItem.user_id == user_id,
                LibraryItem.type == LibraryItemType.PROMPT,
            )
            .order_by(LibraryItem.created_at)
        )
        result = await db.execute(stmt)
        items = result.scalars().all()

        # Filter to items tagged as agent templates
        templates = [
            item
            for item in items
            if "agent_template" in (item.tags or []) and item.description
        ]

        if not templates:
            return ""

        parts = []
        for t in templates:
            parts.append(f"## {t.name}\n\n{t.description}")

        combined = "\n\n---\n\n".join(parts)
        logger.debug(f"Loaded {len(templates)} agent template(s) for user {user_id}")
        return combined

    except Exception as e:
        logger.warning(f"Failed to load agent templates for user {user_id}: {e}")
        return ""
