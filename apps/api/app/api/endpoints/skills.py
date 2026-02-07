"""Skill Builder endpoints (generate, validate, publish)."""

from __future__ import annotations

import uuid
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.library import LibraryItem, LibraryItemType
from app.models.user import User
from app.schemas.skills import (
    GenerateSkillRequest,
    GenerateSkillResponse,
    ValidateSkillRequest,
    ValidateSkillResponse,
    PublishSkillRequest,
    PublishSkillResponse,
)
from app.services.ai.skills.loader import parse_skill_markdown
from app.services.ai.skills.skill_builder import build_skill_draft, validate_skill_markdown
from app.utils.token_counter import estimate_tokens


router = APIRouter()


def _user_id(current_user: Any) -> str:
    uid = getattr(current_user, "id", None)
    if uid:
        return str(uid)
    if isinstance(current_user, dict):
        raw = current_user.get("id")
        if raw:
            return str(raw)
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuário inválido")


def _parse_version(tags: Optional[List[str]]) -> int:
    for tag in tags or []:
        if isinstance(tag, str) and tag.startswith("skill_version:"):
            try:
                return int(tag.split(":", 1)[1])
            except Exception:
                return 1
    return 1


def _replace_tag_prefix(tags: List[str], prefix: str, new_tag: str) -> List[str]:
    clean = [t for t in tags if not (isinstance(t, str) and t.startswith(prefix))]
    clean.append(new_tag)
    return clean


async def _get_skill_draft(*, draft_id: str, user_id: str, db: AsyncSession) -> LibraryItem:
    result = await db.execute(
        select(LibraryItem).where(
            LibraryItem.id == draft_id,
            LibraryItem.user_id == user_id,
            LibraryItem.type == LibraryItemType.PROMPT,
        )
    )
    draft = result.scalar_one_or_none()
    if not draft:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft não encontrado")
    tags = draft.tags or []
    if "skill_draft" not in tags:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Item informado não é um draft de skill")
    return draft


@router.post("/generate", response_model=GenerateSkillResponse, status_code=status.HTTP_201_CREATED)
async def generate_skill(
    payload: GenerateSkillRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = _user_id(current_user)

    skill_markdown = build_skill_draft(
        directive=payload.directive,
        name=payload.name,
        description=payload.description,
        version=payload.version,
        audience=payload.audience,
        triggers=payload.triggers,
        tools_required=payload.tools_required,
        tools_denied=payload.tools_denied,
        subagent_model=payload.subagent_model,
        citation_style=payload.citation_style,
        output_format=payload.output_format,
        prefer_workflow=payload.prefer_workflow,
        prefer_agent=payload.prefer_agent,
        guardrails=payload.guardrails,
        examples=payload.examples,
    )

    validation = validate_skill_markdown(skill_markdown)
    quality_score = float(validation.get("quality_score") or 0.0)

    draft_id = str(uuid.uuid4())
    draft = LibraryItem(
        id=draft_id,
        user_id=user_id,
        type=LibraryItemType.PROMPT,
        name=f"skill-draft:{draft_id[:8]}",
        description=skill_markdown,
        tags=["skill_draft", "schema:skill.v1", "draft_version:1"],
        folder_id=None,
        resource_id=draft_id,
        token_count=estimate_tokens(skill_markdown),
        is_shared=False,
        shared_with=[],
    )

    db.add(draft)
    await db.commit()

    parsed = validation.get("parsed") or {}
    suggested_tests = []
    for trigger in list(parsed.get("triggers") or [])[:5]:
        suggested_tests.append(f"Quando o usuário pedir '{trigger}', a skill deve ser ativada.")

    return GenerateSkillResponse(
        draft_id=draft_id,
        status="draft_created",
        version=1,
        schema_version="skill.v1",
        quality_score=quality_score,
        warnings=validation.get("warnings", []),
        suggested_tests=suggested_tests,
        skill_markdown=skill_markdown,
    )


@router.post("/validate", response_model=ValidateSkillResponse)
async def validate_skill(
    payload: ValidateSkillRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = _user_id(current_user)

    markdown = (payload.skill_markdown or "").strip()
    if payload.draft_id:
        draft = await _get_skill_draft(draft_id=payload.draft_id, user_id=user_id, db=db)
        if not markdown:
            markdown = (draft.description or "").strip()

    if not markdown:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Forneça draft_id ou skill_markdown",
        )

    report = validate_skill_markdown(markdown)
    return ValidateSkillResponse(
        valid=bool(report.get("valid")),
        errors=list(report.get("errors") or []),
        warnings=list(report.get("warnings") or []),
        quality_score=float(report.get("quality_score") or 0.0),
        tpr=float(report.get("tpr") or 0.0),
        fpr=float(report.get("fpr") or 0.0),
        security_violations=list(report.get("security_violations") or []),
        improvements=list(report.get("improvements") or []),
        routing=dict(report.get("routing") or {}),
        parsed=report.get("parsed"),
    )


@router.post("/publish", response_model=PublishSkillResponse)
async def publish_skill(
    payload: PublishSkillRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = _user_id(current_user)
    draft: Optional[LibraryItem] = None
    markdown = (payload.skill_markdown or "").strip()

    if payload.draft_id:
        draft = await _get_skill_draft(draft_id=payload.draft_id, user_id=user_id, db=db)
        if not markdown:
            markdown = (draft.description or "").strip()

    if not markdown:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Forneça draft_id ou skill_markdown",
        )

    report = validate_skill_markdown(markdown)
    if not report.get("valid"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "Skill draft inválido para publicação",
                "errors": report.get("errors") or [],
            },
        )

    source_ref = f"draft:{draft.id}" if draft else "inline"
    parsed = parse_skill_markdown(markdown, source=source_ref)
    if not parsed:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Não foi possível parsear o draft")

    # Check existing published skill with same name
    result = await db.execute(
        select(LibraryItem).where(
            LibraryItem.user_id == user_id,
            LibraryItem.type == LibraryItemType.PROMPT,
        )
    )
    existing_items = result.scalars().all()

    existing: Optional[LibraryItem] = None
    for item in existing_items:
        tags = item.tags or []
        if "skill" in tags and item.name == parsed.name:
            existing = item
            break

    status_label = "published"
    if existing:
        current_version = _parse_version(existing.tags)
        if payload.if_match_version and payload.if_match_version != current_version:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Versão conflitante. Atual={current_version}, if_match={payload.if_match_version}",
            )
        new_version = current_version + 1
        tags = list(existing.tags or [])
        tags = _replace_tag_prefix(tags, "skill_version:", f"skill_version:{new_version}")
        tags = _replace_tag_prefix(tags, "visibility:", f"visibility:{payload.visibility}")
        tags = _replace_tag_prefix(tags, "state:", f"state:{'active' if payload.activate else 'inactive'}")
        if "skill" not in tags:
            tags.append("skill")

        existing.description = markdown
        existing.tags = tags
        existing.token_count = estimate_tokens(markdown)
        skill_item = existing
        status_label = "updated"
    else:
        new_version = 1
        skill_item = LibraryItem(
            id=str(uuid.uuid4()),
            user_id=user_id,
            type=LibraryItemType.PROMPT,
            name=parsed.name,
            description=markdown,
            tags=[
                "skill",
                f"skill_version:{new_version}",
                f"visibility:{payload.visibility}",
                f"state:{'active' if payload.activate else 'inactive'}",
            ],
            folder_id=draft.folder_id if draft else None,
            resource_id=f"skill:{parsed.name}:{uuid.uuid4()}",
            token_count=estimate_tokens(markdown),
            is_shared=False,
            shared_with=[],
        )
        db.add(skill_item)

    await db.commit()
    await db.refresh(skill_item)

    return PublishSkillResponse(
        skill_id=skill_item.id,
        status=status_label,
        version=new_version,
        indexed_triggers=len(parsed.triggers),
    )
