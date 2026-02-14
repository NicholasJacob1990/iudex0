from __future__ import annotations

from typing import List

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ai.skills.loader import load_builtin_skills, load_user_skills
from app.services.ai.skills.models import SkillDefinition


class SkillRegistry:
    """Unified registry for builtin + user-defined skills."""

    def __init__(self, skills: List[SkillDefinition]):
        dedup: dict[str, SkillDefinition] = {}
        for skill in skills:
            # User skill (library:*) should override builtin when names collide.
            if skill.name in dedup and dedup[skill.name].source.startswith("library:"):
                continue
            dedup[skill.name] = skill
        self._skills = list(dedup.values())

    @property
    def skills(self) -> List[SkillDefinition]:
        return list(self._skills)

    @classmethod
    async def build(
        cls,
        *,
        user_id: str,
        db: AsyncSession,
        include_builtin: bool = True,
    ) -> "SkillRegistry":
        builtin = load_builtin_skills() if include_builtin else []
        user = await load_user_skills(user_id, db)
        # Keep user skills first so they win on dedup in __init__
        return cls([*user, *builtin])
