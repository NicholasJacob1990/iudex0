from __future__ import annotations

from pathlib import Path
import re
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.library import LibraryItem, LibraryItemType
from app.services.ai.skills.models import SkillDefinition

try:
    import yaml
except Exception:  # pragma: no cover - optional import safety
    yaml = None  # type: ignore


_SKILLS_DIR = Path(__file__).resolve().parent
_BUILTIN_DIR = _SKILLS_DIR / "builtin"
_REQUIRED_KEYS = {"name", "triggers", "tools_required"}
_NAME_RE = re.compile(r"^[a-z0-9-]{3,64}$")


def _normalize_list(value: Any) -> List[str]:
    if isinstance(value, str):
        raw_items = value.split(",")
    elif isinstance(value, (list, tuple, set)):
        raw_items = list(value)
    else:
        raw_items = []
    cleaned: List[str] = []
    for item in raw_items:
        text = str(item).strip()
        if text:
            cleaned.append(text)
    return cleaned


def _dedupe_keep_order(items: List[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for item in items:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _validate_skill_frontmatter(frontmatter: Dict[str, Any], *, source: str) -> bool:
    name = str(frontmatter.get("name") or "").strip()
    if not _NAME_RE.match(name):
        logger.warning(f"Skill ignored ({source}): invalid name '{name}'")
        return False

    triggers = _dedupe_keep_order(_normalize_list(frontmatter.get("triggers")))
    if len(triggers) < 3 or len(triggers) > 12:
        logger.warning(
            f"Skill ignored ({source}): triggers must contain between 3 and 12 items"
        )
        return False

    tools_required = _dedupe_keep_order(_normalize_list(frontmatter.get("tools_required")))
    if not tools_required:
        logger.warning(f"Skill ignored ({source}): tools_required cannot be empty")
        return False

    tools_denied = _dedupe_keep_order(_normalize_list(frontmatter.get("tools_denied")))
    overlap = sorted({t.lower() for t in tools_required}.intersection({t.lower() for t in tools_denied}))
    if overlap:
        logger.warning(
            f"Skill ignored ({source}): tools_required/tools_denied conflict ({', '.join(overlap)})"
        )
        return False

    prefer_workflow = bool(frontmatter.get("prefer_workflow", False))
    prefer_agent = bool(frontmatter.get("prefer_agent", True))
    if prefer_workflow and prefer_agent:
        logger.warning(
            f"Skill ignored ({source}): prefer_workflow and prefer_agent cannot both be true"
        )
        return False

    return True


def _parse_frontmatter(markdown: str) -> tuple[Optional[Dict[str, Any]], str]:
    text = (markdown or "").lstrip()
    if not text.startswith("---\n"):
        return None, markdown or ""

    _, _, remainder = text.partition("---\n")
    frontmatter_raw, sep, body = remainder.partition("\n---\n")
    if not sep:
        return None, markdown or ""

    if not yaml:
        logger.warning("PyYAML unavailable; skipping skill frontmatter parsing")
        return None, body

    try:
        parsed = yaml.safe_load(frontmatter_raw) or {}
    except Exception as e:
        logger.warning(f"Invalid skill frontmatter YAML: {e}")
        return None, body

    if not isinstance(parsed, dict):
        return None, body

    return parsed, body


def parse_skill_markdown(markdown: str, *, source: str) -> Optional[SkillDefinition]:
    """
    Parse markdown with YAML frontmatter into SkillDefinition.

    Required frontmatter keys:
    - name
    - triggers
    - tools_required
    """
    frontmatter, body = _parse_frontmatter(markdown or "")
    if not frontmatter:
        return None

    if not _REQUIRED_KEYS.issubset(set(frontmatter.keys())):
        missing = sorted(_REQUIRED_KEYS.difference(set(frontmatter.keys())))
        logger.warning(f"Skill ignored ({source}): missing frontmatter keys {missing}")
        return None

    if not _validate_skill_frontmatter(frontmatter, source=source):
        return None

    name = str(frontmatter.get("name") or "").strip()
    description = str(frontmatter.get("description") or "").strip()
    triggers_raw = _normalize_list(frontmatter.get("triggers") or [])
    tools_raw = _normalize_list(frontmatter.get("tools_required") or [])
    subagent_model = frontmatter.get("subagent_model")
    prefer_workflow = bool(frontmatter.get("prefer_workflow", False))
    prefer_agent = bool(frontmatter.get("prefer_agent", True))

    triggers = _dedupe_keep_order(triggers_raw)
    tools_required = _dedupe_keep_order(tools_raw)

    instructions = str(body or "").strip()
    if not name or not triggers or not tools_required or not instructions:
        logger.warning(f"Skill ignored ({source}): invalid empty fields")
        return None

    return SkillDefinition(
        name=name,
        description=description,
        triggers=triggers,
        tools_required=tools_required,
        instructions=instructions,
        source=source,
        subagent_model=str(subagent_model).strip() if subagent_model else None,
        prefer_workflow=prefer_workflow,
        prefer_agent=prefer_agent,
    )


def load_builtin_skills() -> List[SkillDefinition]:
    """Load versioned builtin skills from markdown files."""
    skills: List[SkillDefinition] = []
    if not _BUILTIN_DIR.exists():
        return skills

    for path in sorted(_BUILTIN_DIR.glob("*.md")):
        try:
            parsed = parse_skill_markdown(
                path.read_text(encoding="utf-8"),
                source=f"builtin:{path.name}",
            )
            if parsed:
                skills.append(parsed)
        except Exception as e:
            logger.warning(f"Failed to load builtin skill {path.name}: {e}")
    return skills


async def load_user_skills(user_id: str, db: AsyncSession) -> List[SkillDefinition]:
    """Load user skills from LibraryItem(tag='skill')."""
    if not user_id or not db:
        return []

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

    skills: List[SkillDefinition] = []
    for item in items:
        tags = item.tags or []
        if "skill" not in tags:
            continue
        if not item.description:
            continue
        parsed = parse_skill_markdown(
            item.description,
            source=f"library:{item.id}",
        )
        if parsed:
            skills.append(parsed)
    return skills
