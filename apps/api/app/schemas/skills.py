"""Schemas for Skill Builder endpoints (generate / validate / publish)."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
import re

from pydantic import BaseModel, Field, model_validator


_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
_ALLOWED_CITATION_STYLES = {
    "abnt",
    "forense_br",
    "bluebook",
    "harvard",
    "apa",
    "chicago",
    "oscola",
    "ecli",
    "vancouver",
    "inline",
    "numeric",
    "alwd",
}


class SkillExamplePayload(BaseModel):
    prompt: str = Field(..., min_length=3, max_length=500)
    expected_behavior: str = Field(..., min_length=3, max_length=1000)


class SkillTestPromptsPayload(BaseModel):
    positive: List[str] = Field(default_factory=list)
    negative: List[str] = Field(default_factory=list)


class GenerateSkillRequest(BaseModel):
    directive: str = Field(..., min_length=5, max_length=8000)
    name: Optional[str] = Field(default=None, max_length=120)
    description: Optional[str] = Field(default=None, max_length=500)
    version: str = Field(default="1.0.0")
    audience: Literal["beginner", "advanced", "both"] = "both"
    triggers: Optional[List[str]] = Field(default=None)
    tools_required: Optional[List[str]] = Field(default=None)
    tools_denied: Optional[List[str]] = Field(default=None)
    subagent_model: str = Field(default="claude-haiku-4-5", max_length=100)
    citation_style: str = Field(default="abnt", max_length=50)
    output_format: Literal["chat", "document", "checklist", "json"] = "document"
    prefer_workflow: bool = False
    prefer_agent: bool = True
    guardrails: Optional[List[str]] = Field(default=None)
    examples: Optional[List[str | SkillExamplePayload]] = Field(default=None)
    negative_examples: Optional[List[str]] = Field(default=None)
    tools_allowed: Optional[List[str]] = Field(default=None)

    @model_validator(mode="after")
    def _validate_skill_request(self):
        if not _SEMVER_RE.match(self.version):
            raise ValueError("version deve seguir semver (ex: 1.0.0)")

        if self.citation_style not in _ALLOWED_CITATION_STYLES:
            raise ValueError("citation_style inválido para SkillV1")

        if self.prefer_workflow and self.prefer_agent:
            raise ValueError("prefer_workflow e prefer_agent não podem ser true ao mesmo tempo")

        triggers = self.triggers or []
        if triggers and not (3 <= len(triggers) <= 12):
            raise ValueError("triggers deve conter entre 3 e 12 itens")

        examples = self.examples or []
        if examples and not (2 <= len(examples) <= 10):
            raise ValueError("examples deve conter entre 2 e 10 itens")

        required = set(self.tools_required or [])
        denied = set(self.tools_denied or [])
        overlap = required.intersection(denied)
        if overlap:
            raise ValueError(f"tools_required e tools_denied não podem sobrepor: {', '.join(sorted(overlap))}")
        return self


class GenerateSkillResponse(BaseModel):
    draft_id: str
    status: str
    version: int
    schema_version: str
    quality_score: float
    warnings: List[str]
    suggested_tests: List[str] = Field(default_factory=list)
    skill_markdown: str


class ValidateSkillRequest(BaseModel):
    draft_id: Optional[str] = None
    skill_markdown: Optional[str] = None
    test_prompts: Optional[SkillTestPromptsPayload] = None
    strict: bool = False


class ValidateSkillResponse(BaseModel):
    valid: bool
    errors: List[str]
    warnings: List[str]
    quality_score: float = 0.0
    tpr: float = 0.0
    fpr: float = 0.0
    security_violations: List[str] = Field(default_factory=list)
    improvements: List[str] = Field(default_factory=list)
    routing: Dict[str, float]
    parsed: Optional[Dict[str, Any]] = None


class PublishSkillRequest(BaseModel):
    draft_id: Optional[str] = None
    skill_markdown: Optional[str] = None
    activate: bool = True
    visibility: str = Field(default="personal", pattern="^(personal|organization|public)$")
    if_match_version: Optional[int] = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _validate_source(self):
        if self.draft_id:
            return self
        if self.skill_markdown and self.skill_markdown.strip():
            return self
        raise ValueError("Forneça draft_id ou skill_markdown")


class PublishSkillResponse(BaseModel):
    skill_id: str
    status: str
    version: int
    indexed_triggers: int
