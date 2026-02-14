from __future__ import annotations

import re
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ai.skills.models import SkillDefinition, SkillMatch
from app.services.ai.skills.registry import SkillRegistry


def _normalize_text(text: str) -> str:
    normalized = (text or "").strip().lower()
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def match_skill(skills: List[SkillDefinition], user_input: str) -> Optional[SkillMatch]:
    """Simple trigger-based matcher. Highest trigger hits wins."""
    text = _normalize_text(user_input)
    if not text or not skills:
        return None

    best: Optional[SkillMatch] = None
    for skill in skills:
        matched = []
        for trigger in skill.triggers:
            trig = _normalize_text(trigger)
            if trig and trig in text:
                matched.append(trigger)
        if not matched:
            continue

        score = float(len(matched))
        if best is None or score > best.score:
            best = SkillMatch(skill=skill, score=score, matched_triggers=matched)
    return best


def render_skill_prompt(match: SkillMatch) -> str:
    """Render matched skill as deterministic prompt block."""
    skill = match.skill
    tools = ", ".join(skill.tools_required)
    triggers = ", ".join(match.matched_triggers)
    lines = [
        f"## SKILL ATIVA: {skill.name}",
        f"Descrição: {skill.description or 'N/A'}",
        f"Triggers acionadas: {triggers}",
        f"Tools requeridas: {tools}",
    ]
    if skill.subagent_model:
        lines.append(f"Subagent model sugerido: {skill.subagent_model}")
    lines.append("")
    lines.append(skill.instructions)
    return "\n".join(lines).strip()


async def match_user_skill(
    *,
    user_id: str,
    user_input: str,
    db: AsyncSession,
    include_builtin: bool = True,
) -> Optional[SkillMatch]:
    """Build registry and match a user prompt against available skills."""
    registry = await SkillRegistry.build(
        user_id=user_id,
        db=db,
        include_builtin=include_builtin,
    )
    return match_skill(registry.skills, user_input)
