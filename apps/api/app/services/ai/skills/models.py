from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass(frozen=True)
class SkillDefinition:
    """Canonical skill object loaded from builtin markdown or LibraryItem."""

    name: str
    description: str
    triggers: List[str]
    tools_required: List[str]
    instructions: str
    source: str
    subagent_model: Optional[str] = None
    prefer_workflow: bool = False
    prefer_agent: bool = True


@dataclass(frozen=True)
class SkillMatch:
    """Result of matching a user prompt against available skills."""

    skill: SkillDefinition
    score: float
    matched_triggers: List[str] = field(default_factory=list)
