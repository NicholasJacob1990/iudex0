"""
Playbooks — CRUD + sharing + rule management + AI analysis endpoints.

POST   /playbooks                              — Create playbook
GET    /playbooks                              — List user's playbooks
GET    /playbooks/{id}                         — Get playbook with rules
PUT    /playbooks/{id}                         — Update playbook
DELETE /playbooks/{id}                         — Delete playbook
POST   /playbooks/{id}/rules                  — Add rule
PUT    /playbooks/{id}/rules/{rule_id}         — Update rule
DELETE /playbooks/{id}/rules/{rule_id}         — Delete rule
POST   /playbooks/{id}/rules/reorder           — Reorder rules
POST   /playbooks/{id}/share                  — Share playbook
DELETE /playbooks/{id}/share/{share_id}        — Unshare
POST   /playbooks/{id}/duplicate               — Duplicate playbook
POST   /playbooks/generate                     — Generate from contracts (AI-powered)
POST   /playbooks/import                       — Import playbook from document (AI)
GET    /playbooks/{id}/export?format=          — Export playbook as JSON/PDF/DOCX
POST   /playbooks/{id}/analyze/{document_id}   — Analyze contract with playbook (AI)
GET    /playbooks/{id}/prompt                  — Get playbook prompt for agent

Integração com /minuta:
    Quando o usuário abre um contrato na página /minuta e seleciona um Playbook:
    1. Frontend chama GET /playbooks/{id}/prompt
    2. Recebe regras formatadas como prompt
    3. Injeta no system prompt do agente de chat
    4. Agente aplica regras durante revisão interativa
    Para análise batch, usa POST /playbooks/{id}/analyze/{document_id}.
"""

from __future__ import annotations

import logging
import os
import tempfile
import time
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.rate_limit import (
    playbook_analyze_limit,
    playbook_generate_limit,
    playbook_read_limit,
    playbook_write_limit,
)
from app.core.security import get_current_user
from app.core.time_utils import utcnow
from app.models.playbook import Playbook, PlaybookAnalysis, PlaybookRule, PlaybookShare, PlaybookVersion
from app.models.user import User
from app.schemas.playbook_analysis import (
    ClauseReviewRequest,
    ImportDocumentConfirmRequest,
    ImportDocumentExtractedRule,
    ImportDocumentPreviewResponse,
    PlaybookAnalyzeRequest,
    PlaybookAnalysisListResponse,
    PlaybookAnalysisResponse,
    PlaybookAnalysisSavedResponse,
    PlaybookAnalysisSavedWrapper,
    PlaybookGenerateRequest as PlaybookAIGenerateRequest,
    PlaybookGenerateResponse,
    PlaybookImportRequest,
    PlaybookImportResponse,
    WinningLanguageExtractRequest,
    WinningLanguageExtractResponse,
)
from app.services.playbook_service import playbook_service
from app.schemas.playbook import (
    PlaybookCreate,
    PlaybookDuplicateRequest,
    PlaybookListResponse,
    PlaybookResponse,
    PlaybookRuleCreate,
    PlaybookRuleResponse,
    PlaybookRuleUpdate,
    PlaybookShareCreate,
    PlaybookShareResponse,
    PlaybookUpdate,
    PlaybookVersionListResponse,
    PlaybookVersionResponse,
    PlaybookWithRulesResponse,
    ReorderRulesRequest,
)

logger = logging.getLogger("PlaybookEndpoints")

router = APIRouter()


# ---------------------------------------------------------------------------
# CRUD — Playbook
# ---------------------------------------------------------------------------


@router.post("", response_model=PlaybookResponse, status_code=201)
async def create_playbook(
    request: PlaybookCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _rl: None = Depends(playbook_write_limit),
):
    """Criar um novo playbook."""
    playbook = Playbook(
        id=str(uuid.uuid4()),
        user_id=str(current_user.id),
        organization_id=getattr(current_user, "organization_id", None),
        name=request.name,
        description=request.description,
        area=request.area,
        rules=[],
        is_template=request.is_template,
        scope=request.scope,
        party_perspective=getattr(request, "party_perspective", "neutro") or "neutro",
        metadata_=request.metadata,
    )
    db.add(playbook)

    # Create initial rules if provided
    if request.rules:
        for i, rule_data in enumerate(request.rules):
            rule = PlaybookRule(
                id=str(uuid.uuid4()),
                playbook_id=playbook.id,
                clause_type=rule_data.clause_type,
                rule_name=rule_data.rule_name,
                description=rule_data.description,
                preferred_position=rule_data.preferred_position,
                fallback_positions=rule_data.fallback_positions,
                rejected_positions=rule_data.rejected_positions,
                action_on_reject=rule_data.action_on_reject,
                severity=rule_data.severity,
                guidance_notes=rule_data.guidance_notes,
                order=rule_data.order if rule_data.order is not None else i,
                is_active=rule_data.is_active,
                metadata_=rule_data.metadata,
            )
            db.add(rule)

    await db.commit()
    await db.refresh(playbook)

    return _playbook_to_response(playbook, rules_count=len(request.rules or []))


@router.get("", response_model=PlaybookListResponse)
async def list_playbooks(
    skip: int = 0,
    limit: int = 50,
    scope: Optional[str] = None,
    area: Optional[str] = None,
    is_template: Optional[bool] = None,
    search: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _rl: None = Depends(playbook_read_limit),
):
    """Listar playbooks do usuário com filtros."""
    user_id = str(current_user.id)
    org_id = getattr(current_user, "organization_id", None)

    # Base: own playbooks + shared with user + shared with org + public
    conditions = [Playbook.user_id == user_id]

    # Include shared playbooks
    shared_subq = (
        select(PlaybookShare.playbook_id)
        .where(
            or_(
                PlaybookShare.shared_with_user_id == user_id,
                PlaybookShare.shared_with_org_id == org_id if org_id else False,
            )
        )
    )
    conditions.append(Playbook.id.in_(shared_subq))

    # Include public playbooks
    conditions.append(Playbook.scope == "public")

    stmt = select(Playbook).where(
        Playbook.is_active == True,  # noqa: E712
        or_(*conditions),
    )

    if scope:
        stmt = stmt.where(Playbook.scope == scope)
    if area:
        stmt = stmt.where(Playbook.area == area)
    if is_template is not None:
        stmt = stmt.where(Playbook.is_template == is_template)
    if search:
        stmt = stmt.where(
            Playbook.name.ilike(f"%{search}%") | Playbook.description.ilike(f"%{search}%")
        )

    # Count
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0

    # Fetch with pagination
    stmt = stmt.order_by(Playbook.updated_at.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    playbooks = result.scalars().all()

    # Get rule counts
    items = []
    for pb in playbooks:
        count_result = await db.execute(
            select(func.count()).select_from(PlaybookRule).where(
                PlaybookRule.playbook_id == pb.id
            )
        )
        rules_count = count_result.scalar() or 0
        items.append(_playbook_to_response(pb, rules_count=rules_count))

    return PlaybookListResponse(items=items, total=total, skip=skip, limit=limit)


@router.get("/{playbook_id}", response_model=PlaybookWithRulesResponse)
async def get_playbook(
    playbook_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _rl: None = Depends(playbook_read_limit),
):
    """Obter playbook com regras completas."""
    playbook = await _get_accessible_playbook(playbook_id, current_user, db)

    # Load rules
    rules_result = await db.execute(
        select(PlaybookRule)
        .where(PlaybookRule.playbook_id == playbook_id)
        .order_by(PlaybookRule.order)
    )
    rules = rules_result.scalars().all()

    # Load shares
    shares_result = await db.execute(
        select(PlaybookShare).where(PlaybookShare.playbook_id == playbook_id)
    )
    shares = shares_result.scalars().all()

    resp = _playbook_to_response(playbook, rules_count=len(rules))

    # Resolve share responses (async to include user emails)
    share_responses = []
    for s in shares:
        share_responses.append(await _share_to_response(s, db))

    return PlaybookWithRulesResponse(
        **resp.model_dump(),
        rules_items=[_rule_to_response(r) for r in rules],
        shares=share_responses,
    )


@router.put("/{playbook_id}", response_model=PlaybookResponse)
async def update_playbook(
    playbook_id: str,
    request: PlaybookUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _rl: None = Depends(playbook_write_limit),
):
    """Atualizar playbook."""
    playbook = await _get_writable_playbook(playbook_id, current_user, db)

    if request.name is not None:
        playbook.name = request.name
    if request.description is not None:
        playbook.description = request.description
    if request.area is not None:
        playbook.area = request.area
    if request.scope is not None:
        playbook.scope = request.scope
    if request.is_active is not None:
        playbook.is_active = request.is_active
    if request.is_template is not None:
        playbook.is_template = request.is_template
    if request.party_perspective is not None:
        playbook.party_perspective = request.party_perspective
    if request.metadata is not None:
        playbook.metadata_ = request.metadata

    await db.commit()
    await db.refresh(playbook)

    count_result = await db.execute(
        select(func.count()).select_from(PlaybookRule).where(
            PlaybookRule.playbook_id == playbook_id
        )
    )
    rules_count = count_result.scalar() or 0

    return _playbook_to_response(playbook, rules_count=rules_count)


@router.delete("/{playbook_id}", status_code=204)
async def delete_playbook(
    playbook_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _rl: None = Depends(playbook_write_limit),
):
    """Deletar playbook."""
    playbook = await _get_owned_playbook(playbook_id, current_user, db)
    await db.delete(playbook)
    await db.commit()


# ---------------------------------------------------------------------------
# Rules Management
# ---------------------------------------------------------------------------


@router.post("/{playbook_id}/rules", response_model=PlaybookRuleResponse, status_code=201)
async def create_rule(
    playbook_id: str,
    request: PlaybookRuleCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Adicionar regra ao playbook."""
    playbook = await _get_writable_playbook(playbook_id, current_user, db)

    # Auto-version before change
    await _create_version_snapshot(
        playbook_id=playbook_id,
        user_id=str(current_user.id),
        changes_summary=f"Regra adicionada: {request.rule_name} ({request.clause_type})",
        db=db,
    )

    # Get max order
    max_order_result = await db.execute(
        select(func.max(PlaybookRule.order)).where(
            PlaybookRule.playbook_id == playbook_id
        )
    )
    max_order = max_order_result.scalar() or 0

    rule = PlaybookRule(
        id=str(uuid.uuid4()),
        playbook_id=playbook_id,
        clause_type=request.clause_type,
        rule_name=request.rule_name,
        description=request.description,
        preferred_position=request.preferred_position,
        fallback_positions=request.fallback_positions,
        rejected_positions=request.rejected_positions,
        action_on_reject=request.action_on_reject,
        severity=request.severity,
        guidance_notes=request.guidance_notes,
        order=request.order if request.order is not None else max_order + 1,
        is_active=request.is_active,
        metadata_=request.metadata,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)

    return _rule_to_response(rule)


@router.put("/{playbook_id}/rules/{rule_id}", response_model=PlaybookRuleResponse)
async def update_rule(
    playbook_id: str,
    rule_id: str,
    request: PlaybookRuleUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Atualizar regra do playbook."""
    await _get_writable_playbook(playbook_id, current_user, db)
    rule = await _get_rule(playbook_id, rule_id, db)

    # Auto-version before change
    await _create_version_snapshot(
        playbook_id=playbook_id,
        user_id=str(current_user.id),
        changes_summary=f"Regra atualizada: {rule.rule_name} ({rule.clause_type})",
        db=db,
    )

    if request.clause_type is not None:
        rule.clause_type = request.clause_type
    if request.rule_name is not None:
        rule.rule_name = request.rule_name
    if request.description is not None:
        rule.description = request.description
    if request.preferred_position is not None:
        rule.preferred_position = request.preferred_position
    if request.fallback_positions is not None:
        rule.fallback_positions = request.fallback_positions
    if request.rejected_positions is not None:
        rule.rejected_positions = request.rejected_positions
    if request.action_on_reject is not None:
        rule.action_on_reject = request.action_on_reject
    if request.severity is not None:
        rule.severity = request.severity
    if request.guidance_notes is not None:
        rule.guidance_notes = request.guidance_notes
    if request.order is not None:
        rule.order = request.order
    if request.is_active is not None:
        rule.is_active = request.is_active
    if request.metadata is not None:
        rule.metadata_ = request.metadata

    await db.commit()
    await db.refresh(rule)

    return _rule_to_response(rule)


@router.delete("/{playbook_id}/rules/{rule_id}", status_code=204)
async def delete_rule(
    playbook_id: str,
    rule_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Deletar regra do playbook."""
    await _get_writable_playbook(playbook_id, current_user, db)
    rule = await _get_rule(playbook_id, rule_id, db)

    # Auto-version before change
    await _create_version_snapshot(
        playbook_id=playbook_id,
        user_id=str(current_user.id),
        changes_summary=f"Regra removida: {rule.rule_name} ({rule.clause_type})",
        db=db,
    )

    await db.delete(rule)
    await db.commit()


@router.post("/{playbook_id}/rules/reorder")
async def reorder_rules(
    playbook_id: str,
    request: ReorderRulesRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Reordenar regras do playbook."""
    await _get_writable_playbook(playbook_id, current_user, db)

    for i, rule_id in enumerate(request.rule_ids):
        result = await db.execute(
            select(PlaybookRule).where(
                PlaybookRule.id == rule_id,
                PlaybookRule.playbook_id == playbook_id,
            )
        )
        rule = result.scalar_one_or_none()
        if rule:
            rule.order = i

    await db.commit()
    return {"status": "ok", "order": request.rule_ids}


# ---------------------------------------------------------------------------
# Sharing
# ---------------------------------------------------------------------------


@router.post("/{playbook_id}/share", response_model=PlaybookShareResponse, status_code=201)
async def share_playbook(
    playbook_id: str,
    request: PlaybookShareCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Compartilhar playbook com usuário (por ID ou e-mail) ou organização."""
    await _get_owned_playbook(playbook_id, current_user, db)

    shared_with_user_id = request.shared_with_user_id
    shared_with_org_id = request.shared_with_org_id

    # Resolve user_email to user_id
    if request.user_email and not shared_with_user_id:
        user_result = await db.execute(
            select(User).where(User.email == request.user_email.strip().lower())
        )
        target_user = user_result.scalar_one_or_none()
        if not target_user:
            raise HTTPException(
                status_code=404,
                detail=f"Usuário com e-mail '{request.user_email}' não encontrado"
            )
        shared_with_user_id = str(target_user.id)

    # Share with entire org
    if request.organization_wide and not shared_with_org_id:
        org_id = getattr(current_user, "organization_id", None)
        if not org_id:
            raise HTTPException(
                status_code=400,
                detail="Você não pertence a uma organização"
            )
        shared_with_org_id = org_id

    if not shared_with_user_id and not shared_with_org_id:
        raise HTTPException(
            status_code=400,
            detail="É necessário informar user_email, shared_with_user_id ou shared_with_org_id"
        )

    # Prevent sharing with yourself
    if shared_with_user_id == str(current_user.id):
        raise HTTPException(
            status_code=400,
            detail="Não é possível compartilhar consigo mesmo"
        )

    # Check if already shared
    existing_stmt = select(PlaybookShare).where(
        PlaybookShare.playbook_id == playbook_id
    )
    if shared_with_user_id:
        existing_stmt = existing_stmt.where(
            PlaybookShare.shared_with_user_id == shared_with_user_id
        )
    elif shared_with_org_id:
        existing_stmt = existing_stmt.where(
            PlaybookShare.shared_with_org_id == shared_with_org_id
        )

    existing = (await db.execute(existing_stmt)).scalar_one_or_none()
    if existing:
        # Update permission
        existing.permission = request.permission
        await db.commit()
        await db.refresh(existing)
        return await _share_to_response(existing, db)

    share = PlaybookShare(
        id=str(uuid.uuid4()),
        playbook_id=playbook_id,
        shared_with_user_id=shared_with_user_id,
        shared_with_org_id=shared_with_org_id,
        permission=request.permission,
    )
    db.add(share)
    await db.commit()
    await db.refresh(share)

    return await _share_to_response(share, db)


@router.delete("/{playbook_id}/share/{share_id}", status_code=204)
async def unshare_playbook(
    playbook_id: str,
    share_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remover compartilhamento de playbook."""
    await _get_owned_playbook(playbook_id, current_user, db)

    result = await db.execute(
        select(PlaybookShare).where(
            PlaybookShare.id == share_id,
            PlaybookShare.playbook_id == playbook_id,
        )
    )
    share = result.scalar_one_or_none()
    if not share:
        raise HTTPException(status_code=404, detail="Compartilhamento não encontrado")

    await db.delete(share)
    await db.commit()


# ---------------------------------------------------------------------------
# Duplicate & Generate
# ---------------------------------------------------------------------------


@router.post("/{playbook_id}/duplicate", response_model=PlaybookResponse, status_code=201)
async def duplicate_playbook(
    playbook_id: str,
    request: PlaybookDuplicateRequest = PlaybookDuplicateRequest(),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Duplicar playbook (para uso como template ou cópia pessoal)."""
    source = await _get_accessible_playbook(playbook_id, current_user, db)

    # Load source rules
    rules_result = await db.execute(
        select(PlaybookRule)
        .where(PlaybookRule.playbook_id == playbook_id)
        .order_by(PlaybookRule.order)
    )
    source_rules = rules_result.scalars().all()

    new_id = str(uuid.uuid4())
    new_playbook = Playbook(
        id=new_id,
        user_id=str(current_user.id),
        organization_id=getattr(current_user, "organization_id", None),
        name=request.name or f"{source.name} (cópia)",
        description=source.description,
        area=source.area,
        rules=[],
        is_template=False,
        scope=request.scope,
        version=1,
        parent_id=source.id,
        metadata_=source.metadata_,
    )
    db.add(new_playbook)

    # Duplicate rules
    for rule in source_rules:
        new_rule = PlaybookRule(
            id=str(uuid.uuid4()),
            playbook_id=new_id,
            clause_type=rule.clause_type,
            rule_name=rule.rule_name,
            description=rule.description,
            preferred_position=rule.preferred_position,
            fallback_positions=rule.fallback_positions,
            rejected_positions=rule.rejected_positions,
            action_on_reject=rule.action_on_reject,
            severity=rule.severity,
            guidance_notes=rule.guidance_notes,
            order=rule.order,
            is_active=rule.is_active,
            metadata_=rule.metadata_,
        )
        db.add(new_rule)

    await db.commit()
    await db.refresh(new_playbook)

    return _playbook_to_response(new_playbook, rules_count=len(source_rules))


@router.post("/generate", response_model=PlaybookGenerateResponse, status_code=201)
async def generate_playbook(
    request: PlaybookAIGenerateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _rl: None = Depends(playbook_generate_limit),
):
    """Gerar playbook a partir de contratos existentes usando IA.

    Inspirado no Harvey AI Playbook Generation:
    1. Carrega textos de 1-10 contratos
    2. IA identifica tipos de cláusula em todos os contratos
    3. Para cada tipo, determina posição preferida, alternativas e rejeições
    4. Gera PlaybookRules e persiste no banco
    """
    try:
        playbook = await playbook_service.generate_playbook_from_contracts(
            document_ids=request.document_ids,
            name=request.name,
            area=request.area,
            user_id=str(current_user.id),
            db=db,
            description=request.description,
        )

        rules_count = len(playbook.rules) if playbook.rules else 0

        return PlaybookGenerateResponse(
            success=True,
            playbook_id=playbook.id,
            name=playbook.name,
            rules_count=rules_count,
            message=f"Playbook '{playbook.name}' gerado com {rules_count} regras.",
        )
    except ValueError as e:
        logger.warning("Erro de validação na geração de playbook: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error("Erro inesperado na geração de playbook: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao gerar o playbook.",
        )


# ---------------------------------------------------------------------------
# Import — Extract playbook rules from an existing document
# ---------------------------------------------------------------------------


@router.post("/import", response_model=PlaybookImportResponse, status_code=201)
async def import_playbook(
    request: PlaybookImportRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _rl: None = Depends(playbook_generate_limit),
):
    """Importar playbook extraindo regras de um documento existente (PDF/DOCX).

    Fluxo:
    1. Carrega o texto do documento (ja processado)
    2. IA analisa e extrai regras de revisao
    3. Cria Playbook com as regras extraidas
    """
    try:
        playbook = await playbook_service.import_playbook_from_document(
            document_id=request.document_id,
            name=request.name,
            area=request.area,
            user_id=str(current_user.id),
            db=db,
            description=request.description,
        )

        rules_count = len(playbook.rules) if playbook.rules else 0

        return PlaybookImportResponse(
            success=True,
            playbook_id=playbook.id,
            name=playbook.name,
            rules_count=rules_count,
            message=f"Playbook '{playbook.name}' importado com {rules_count} regras.",
        )
    except ValueError as e:
        logger.warning("Erro de validacao na importacao de playbook: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error("Erro inesperado na importacao de playbook: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao importar o playbook.",
        )


# ---------------------------------------------------------------------------
# Extract Winning Language — Extract playbook from negotiated contracts
# ---------------------------------------------------------------------------


@router.post(
    "/extract-from-contracts",
    response_model=WinningLanguageExtractResponse,
    status_code=201,
    summary="Extrair winning language de contratos",
    description=(
        "Extrai 'linguagem vencedora' (winning language) de contratos já negociados "
        "e assinados. Analisa cláusulas aceitas por ambas as partes para criar um "
        "playbook com posições padrão, alternativas e rejeições inferidas."
    ),
)
async def extract_winning_language(
    request: WinningLanguageExtractRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _rl: None = Depends(playbook_generate_limit),
):
    """Extrai winning language de contratos já negociados usando IA.

    Fluxo:
    1. Carrega textos de 1-10 contratos já assinados
    2. IA identifica cláusulas vencedoras (aceitas por ambas as partes)
    3. Para cada cláusula: extrai posição padrão, variações e rejeições
    4. Classifica importância baseada em recorrência entre contratos
    5. Gera PlaybookRules e persiste no banco
    """
    try:
        playbook = await playbook_service.extract_winning_language(
            document_ids=request.document_ids,
            name=request.name,
            area=request.area,
            user_id=str(current_user.id),
            db=db,
            description=request.description,
        )

        rules_count = len(playbook.rules) if playbook.rules else 0
        docs_processed = (
            playbook.metadata_.get("source_documents_loaded", len(request.document_ids))
            if playbook.metadata_
            else len(request.document_ids)
        )

        return WinningLanguageExtractResponse(
            success=True,
            playbook_id=playbook.id,
            name=playbook.name,
            rules_count=rules_count,
            documents_processed=docs_processed,
            message=(
                f"Winning language extraída: playbook '{playbook.name}' "
                f"criado com {rules_count} regras a partir de {docs_processed} contrato(s)."
            ),
        )
    except ValueError as e:
        logger.warning("Erro de validação na extração de winning language: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(
            "Erro inesperado na extração de winning language: %s", e, exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao extrair winning language dos contratos.",
        )


# ---------------------------------------------------------------------------
# Import from uploaded file — Direct file upload (PDF/DOCX)
# ---------------------------------------------------------------------------


@router.post(
    "/import-document",
    response_model=ImportDocumentPreviewResponse,
    summary="Extrair regras de arquivo enviado (preview)",
    description=(
        "Faz upload de um arquivo PDF ou DOCX de playbook e extrai regras via IA. "
        "Retorna as regras para preview/edicao antes da confirmacao."
    ),
)
async def import_document_preview(
    file: UploadFile = File(..., description="Arquivo PDF ou DOCX"),
    area: str = Form("outro", description="Area juridica"),
    current_user: User = Depends(get_current_user),
    _rl: None = Depends(playbook_generate_limit),
):
    """Extrai regras de um documento enviado por upload para preview.

    Fluxo:
    1. Recebe arquivo PDF ou DOCX via upload
    2. Extrai texto do arquivo
    3. Envia texto para IA extrair regras
    4. Retorna regras para preview/edicao no frontend
    5. Frontend chama POST /import-document/confirm para criar o playbook
    """
    # Validar tipo de arquivo
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nome do arquivo nao informado.",
        )

    filename_lower = file.filename.lower()
    if not (filename_lower.endswith(".pdf") or filename_lower.endswith(".docx")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Formato nao suportado. Envie um arquivo PDF ou DOCX.",
        )

    # Salvar arquivo temporario e extrair texto
    tmp_path = None
    try:
        suffix = ".pdf" if filename_lower.endswith(".pdf") else ".docx"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name

        # Extrair texto via entrypoint unificado
        from app.services.document_extraction_service import extract_text_from_path

        extraction = await extract_text_from_path(
            tmp_path,
            min_pdf_chars=50,
            allow_pdf_ocr_fallback=True,
        )
        document_text = extraction.text or ""

        if not document_text or not document_text.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Nao foi possivel extrair texto do arquivo. Verifique se o documento nao esta vazio ou protegido.",
            )

        # Extrair regras via IA (sem persistir)
        rules_data = await playbook_service.extract_rules_from_text(
            document_text=document_text,
            area=area,
        )

        rules = [
            ImportDocumentExtractedRule(**rd)
            for rd in rules_data
        ]

        return ImportDocumentPreviewResponse(
            success=True,
            rules=rules,
            rules_count=len(rules),
            message=f"{len(rules)} regra(s) extraida(s) do documento.",
        )

    except ValueError as e:
        logger.warning("Erro de validacao na extracao de regras: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Erro inesperado na extracao de regras do documento: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao processar o documento.",
        )
    finally:
        # Limpar arquivo temporario
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


@router.post(
    "/import-document/confirm",
    response_model=PlaybookImportResponse,
    status_code=201,
    summary="Confirmar e criar playbook a partir de regras extraidas",
    description=(
        "Cria o playbook com as regras previamente extraidas e editadas pelo usuario. "
        "Chamado apos o preview de POST /import-document."
    ),
)
async def import_document_confirm(
    request: ImportDocumentConfirmRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _rl: None = Depends(playbook_write_limit),
):
    """Cria playbook a partir das regras confirmadas pelo usuario."""
    try:
        rules_data = [rule.model_dump() for rule in request.rules]

        playbook = await playbook_service.create_playbook_with_rules(
            name=request.name,
            area=request.area,
            user_id=str(current_user.id),
            rules_data=rules_data,
            db=db,
            description=request.description,
        )

        rules_count = len(playbook.rules) if playbook.rules else 0

        return PlaybookImportResponse(
            success=True,
            playbook_id=playbook.id,
            name=playbook.name,
            rules_count=rules_count,
            message=f"Playbook '{playbook.name}' criado com {rules_count} regras.",
        )

    except ValueError as e:
        logger.warning("Erro de validacao na criacao de playbook: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error("Erro inesperado na criacao de playbook: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao criar o playbook.",
        )


# ---------------------------------------------------------------------------
# Export — Download playbook as JSON, PDF, or DOCX
# ---------------------------------------------------------------------------


@router.get(
    "/{playbook_id}/export",
    summary="Exportar playbook",
    description="Exporta o playbook no formato especificado (json, pdf, docx).",
)
async def export_playbook(
    playbook_id: str,
    format: str = Query(
        "json",
        pattern="^(json|pdf|docx)$",
        description="Formato de exportacao: json, pdf, docx",
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Exporta um playbook como arquivo para download."""
    # Verify access
    await _get_accessible_playbook(playbook_id, current_user, db)

    try:
        content, filename, content_type = await playbook_service.export_playbook(
            playbook_id=playbook_id,
            format=format,
            user_id=str(current_user.id),
            db=db,
        )

        return Response(
            content=content,
            media_type=content_type,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
        )
    except ValueError as e:
        logger.warning("Erro na exportacao de playbook: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error("Erro inesperado na exportacao de playbook: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao exportar o playbook.",
        )


# ---------------------------------------------------------------------------
# AI Analysis — Contract review with Playbook rules
# ---------------------------------------------------------------------------


@router.post(
    "/{playbook_id}/analyze/{document_id}",
    response_model=PlaybookAnalysisResponse,
    summary="Analisar contrato com playbook",
    description=(
        "Executa a análise completa de um contrato contra as regras de um playbook. "
        "Para cada regra, identifica a cláusula correspondente, classifica como "
        "conforme/não-conforme/ausente, e gera sugestões de redline."
    ),
)
async def analyze_contract_with_playbook(
    playbook_id: str,
    document_id: str,
    request: PlaybookAnalyzeRequest = PlaybookAnalyzeRequest(),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _rl: None = Depends(playbook_analyze_limit),
) -> PlaybookAnalysisSavedWrapper:
    """Analisa um contrato contra as regras do playbook usando IA e persiste os resultados."""
    try:
        start_time = time.monotonic()

        result = await playbook_service.analyze_contract_with_playbook(
            document_id=document_id,
            playbook_id=playbook_id,
            user_id=str(current_user.id),
            db=db,
            contract_text_override=request.contract_text_override,
        )

        duration_ms = int((time.monotonic() - start_time) * 1000)

        # Persist analysis to database
        analysis = PlaybookAnalysis(
            id=str(uuid.uuid4()),
            playbook_id=playbook_id,
            document_id=document_id,
            user_id=str(current_user.id),
            organization_id=getattr(current_user, "organization_id", None),
            total_rules=result.total_rules,
            compliant=result.compliant,
            needs_review=result.needs_review,
            non_compliant=result.non_compliant,
            not_found=result.not_found,
            risk_score=result.risk_score,
            summary=result.summary,
            clause_results=[c.model_dump(mode="json") for c in result.clauses],
            reviewed_clauses=None,
            model_used=None,
            analysis_duration_ms=duration_ms,
        )
        db.add(analysis)
        await db.commit()
        await db.refresh(analysis)

        logger.info(
            "Análise persistida: id=%s, playbook=%s, documento=%s, duration=%dms",
            analysis.id, playbook_id, document_id, duration_ms,
        )

        return PlaybookAnalysisSavedWrapper(
            success=True,
            data=_analysis_to_response(analysis, result.playbook_name, result.clauses),
        )

    except ValueError as e:
        logger.warning("Erro de validação na análise de playbook: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error("Erro inesperado na análise de playbook: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao processar a análise do playbook.",
        )


# ---------------------------------------------------------------------------
# Analysis History — List, Get, Review
# ---------------------------------------------------------------------------


@router.get(
    "/{playbook_id}/analyses",
    response_model=PlaybookAnalysisListResponse,
    summary="Listar análises de um playbook",
    description="Retorna lista paginada de análises executadas para um playbook.",
)
async def list_playbook_analyses(
    playbook_id: str,
    skip: int = 0,
    limit: int = 50,
    document_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PlaybookAnalysisListResponse:
    """Listar análises de um playbook com paginação."""
    await _get_accessible_playbook(playbook_id, current_user, db)

    stmt = select(PlaybookAnalysis).where(
        PlaybookAnalysis.playbook_id == playbook_id,
        PlaybookAnalysis.user_id == str(current_user.id),
    )

    if document_id:
        stmt = stmt.where(PlaybookAnalysis.document_id == document_id)

    # Count
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0

    # Fetch with pagination
    stmt = stmt.order_by(PlaybookAnalysis.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    analyses = result.scalars().all()

    # Load playbook name once
    playbook = await db.get(Playbook, playbook_id)
    playbook_name = playbook.name if playbook else ""

    items = [
        _analysis_to_response(a, playbook_name)
        for a in analyses
    ]

    return PlaybookAnalysisListResponse(
        items=items, total=total, skip=skip, limit=limit,
    )


@router.get(
    "/{playbook_id}/analyses/{analysis_id}",
    response_model=PlaybookAnalysisSavedWrapper,
    summary="Obter análise específica",
    description="Retorna os detalhes de uma análise específica.",
)
async def get_playbook_analysis(
    playbook_id: str,
    analysis_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PlaybookAnalysisSavedWrapper:
    """Obter uma análise específica pelo ID."""
    await _get_accessible_playbook(playbook_id, current_user, db)

    result = await db.execute(
        select(PlaybookAnalysis).where(
            PlaybookAnalysis.id == analysis_id,
            PlaybookAnalysis.playbook_id == playbook_id,
        )
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(status_code=404, detail="Análise não encontrada")

    # Check access: owner or same org
    user_id = str(current_user.id)
    org_id = getattr(current_user, "organization_id", None)
    if analysis.user_id != user_id and analysis.organization_id != org_id:
        raise HTTPException(status_code=403, detail="Sem permissão")

    playbook = await db.get(Playbook, playbook_id)
    playbook_name = playbook.name if playbook else ""

    return PlaybookAnalysisSavedWrapper(
        success=True,
        data=_analysis_to_response(analysis, playbook_name),
    )


@router.patch(
    "/{playbook_id}/analyses/{analysis_id}/review",
    response_model=PlaybookAnalysisSavedWrapper,
    summary="Marcar cláusulas como revisadas",
    description=(
        "Atualiza o status de revisão de cláusulas individuais em uma análise. "
        "Permite rastrear quais cláusulas foram revisadas por humanos."
    ),
)
async def review_analysis_clauses(
    playbook_id: str,
    analysis_id: str,
    request: ClauseReviewRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PlaybookAnalysisSavedWrapper:
    """Marcar cláusulas de uma análise como revisadas."""
    await _get_accessible_playbook(playbook_id, current_user, db)

    result = await db.execute(
        select(PlaybookAnalysis).where(
            PlaybookAnalysis.id == analysis_id,
            PlaybookAnalysis.playbook_id == playbook_id,
        )
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(status_code=404, detail="Análise não encontrada")

    # Check access: owner or same org
    user_id = str(current_user.id)
    org_id = getattr(current_user, "organization_id", None)
    if analysis.user_id != user_id and analysis.organization_id != org_id:
        raise HTTPException(status_code=403, detail="Sem permissão")

    # Merge new reviews into existing
    existing_reviews = analysis.reviewed_clauses or {}
    now_iso = datetime.now(timezone.utc).isoformat()

    for rule_id, review_data in request.reviews.items():
        if not isinstance(review_data, dict):
            continue
        existing_reviews[rule_id] = {
            "reviewed_by": user_id,
            "reviewed_at": now_iso,
            "status": review_data.get("status", "approved"),
            "notes": review_data.get("notes", ""),
        }

    analysis.reviewed_clauses = existing_reviews
    analysis.updated_at = utcnow()

    await db.commit()
    await db.refresh(analysis)

    playbook = await db.get(Playbook, playbook_id)
    playbook_name = playbook.name if playbook else ""

    return PlaybookAnalysisSavedWrapper(
        success=True,
        data=_analysis_to_response(analysis, playbook_name),
    )


# ---------------------------------------------------------------------------
# Playbook Prompt for Agent
# ---------------------------------------------------------------------------


@router.get(
    "/{playbook_id}/prompt",
    summary="Obter prompt do playbook para agente",
    description=(
        "Retorna as regras do playbook formatadas como prompt para injeção "
        "no system prompt do agente de revisão contratual na página /minuta."
    ),
)
async def get_playbook_prompt(
    playbook_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Retorna as regras do playbook serializadas para injeção no prompt do agente.

    Fluxo na página /minuta:
    1. Usuário abre contrato e seleciona playbook no dropdown
    2. Frontend chama GET /playbooks/{id}/prompt
    3. Recebe prompt formatado com as regras
    4. Injeta no system prompt do agente de chat
    5. Agente aplica regras durante revisão interativa do contrato
    """
    try:
        prompt_text = await playbook_service.get_playbook_for_prompt(
            playbook_id=playbook_id,
            db=db,
        )
        return {
            "success": True,
            "playbook_id": playbook_id,
            "prompt": prompt_text,
        }
    except ValueError as e:
        logger.warning("Playbook não encontrado para prompt: %s", e)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.error("Erro ao gerar prompt do playbook: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao gerar prompt do playbook.",
        )


# ---------------------------------------------------------------------------
# Version History
# ---------------------------------------------------------------------------


@router.get(
    "/{playbook_id}/versions",
    response_model=PlaybookVersionListResponse,
    summary="Listar histórico de versões do playbook",
    description="Retorna a timeline de alterações feitas nas regras do playbook.",
)
async def list_playbook_versions(
    playbook_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _rl: None = Depends(playbook_read_limit),
) -> PlaybookVersionListResponse:
    """Listar versões de um playbook."""
    await _get_accessible_playbook(playbook_id, current_user, db)

    stmt = (
        select(PlaybookVersion)
        .where(PlaybookVersion.playbook_id == playbook_id)
        .order_by(PlaybookVersion.version_number.desc())
    )
    result = await db.execute(stmt)
    versions = result.scalars().all()

    items = []
    for v in versions:
        user = await db.get(User, v.changed_by)
        email = user.email if user else None
        items.append(PlaybookVersionResponse(
            id=v.id,
            playbook_id=v.playbook_id,
            version_number=v.version_number,
            changed_by=v.changed_by,
            changed_by_email=email,
            changes_summary=v.changes_summary,
            previous_rules=v.previous_rules or [],
            created_at=v.created_at.isoformat() if v.created_at else "",
        ))

    return PlaybookVersionListResponse(items=items, total=len(items))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_version_snapshot(
    playbook_id: str,
    user_id: str,
    changes_summary: str,
    db: AsyncSession,
) -> None:
    """Cria um snapshot de versão ANTES de uma alteração nas regras."""
    playbook = await db.get(Playbook, playbook_id)
    if not playbook:
        return

    rules_result = await db.execute(
        select(PlaybookRule)
        .where(PlaybookRule.playbook_id == playbook_id)
        .order_by(PlaybookRule.order)
    )
    current_rules = rules_result.scalars().all()
    rules_snapshot = [r.to_dict() for r in current_rules]

    max_ver_result = await db.execute(
        select(func.max(PlaybookVersion.version_number)).where(
            PlaybookVersion.playbook_id == playbook_id
        )
    )
    max_version = max_ver_result.scalar() or 0
    new_version = max_version + 1

    version = PlaybookVersion(
        id=str(uuid.uuid4()),
        playbook_id=playbook_id,
        version_number=new_version,
        changed_by=user_id,
        changes_summary=changes_summary,
        previous_rules=rules_snapshot,
    )
    db.add(version)

    playbook.version = new_version


async def _get_owned_playbook(
    playbook_id: str, user: User, db: AsyncSession
) -> Playbook:
    """Get playbook owned by the current user (owner-only operations like delete)."""
    playbook = await db.get(Playbook, playbook_id)
    if not playbook:
        raise HTTPException(status_code=404, detail="Playbook não encontrado")
    if playbook.user_id != str(user.id):
        raise HTTPException(status_code=403, detail="Sem permissão")
    return playbook


async def _get_writable_playbook(
    playbook_id: str, user: User, db: AsyncSession
) -> Playbook:
    """Get playbook that user can write to (owner OR has EDIT/ADMIN share permission)."""
    playbook = await db.get(Playbook, playbook_id)
    if not playbook:
        raise HTTPException(status_code=404, detail="Playbook não encontrado")

    user_id = str(user.id)

    # Owner can always write
    if playbook.user_id == user_id:
        return playbook

    # Check share permissions
    share_result = await db.execute(
        select(PlaybookShare).where(
            PlaybookShare.playbook_id == playbook_id,
            PlaybookShare.shared_with_user_id == user_id,
            PlaybookShare.permission.in_(["edit", "admin"]),
        )
    )
    if share_result.scalar_one_or_none():
        return playbook

    # Check org-level share permissions
    org_id = getattr(user, "organization_id", None)
    if org_id:
        org_share_result = await db.execute(
            select(PlaybookShare).where(
                PlaybookShare.playbook_id == playbook_id,
                PlaybookShare.shared_with_org_id == org_id,
                PlaybookShare.permission.in_(["edit", "admin"]),
            )
        )
        if org_share_result.scalar_one_or_none():
            return playbook

    raise HTTPException(status_code=403, detail="Sem permissão para editar este playbook")


async def _get_accessible_playbook(
    playbook_id: str, user: User, db: AsyncSession
) -> Playbook:
    """Get playbook if user has access (own, shared, or public)."""
    playbook = await db.get(Playbook, playbook_id)
    if not playbook:
        raise HTTPException(status_code=404, detail="Playbook não encontrado")

    user_id = str(user.id)
    org_id = getattr(user, "organization_id", None)

    # Owner
    if playbook.user_id == user_id:
        return playbook

    # Public
    if playbook.scope == "public":
        return playbook

    # Shared with user or org
    share_stmt = select(PlaybookShare).where(
        PlaybookShare.playbook_id == playbook_id,
        or_(
            PlaybookShare.shared_with_user_id == user_id,
            PlaybookShare.shared_with_org_id == org_id if org_id else False,
        ),
    )
    share_result = await db.execute(share_stmt)
    if share_result.scalar_one_or_none():
        return playbook

    raise HTTPException(status_code=403, detail="Sem permissão")


async def _get_rule(
    playbook_id: str, rule_id: str, db: AsyncSession
) -> PlaybookRule:
    """Get a rule belonging to a playbook."""
    result = await db.execute(
        select(PlaybookRule).where(
            PlaybookRule.id == rule_id,
            PlaybookRule.playbook_id == playbook_id,
        )
    )
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Regra não encontrada")
    return rule


def _playbook_to_response(pb: Playbook, rules_count: int = 0) -> PlaybookResponse:
    return PlaybookResponse(
        id=pb.id,
        user_id=pb.user_id,
        organization_id=pb.organization_id,
        name=pb.name,
        description=pb.description,
        area=pb.area,
        scope=pb.scope,
        party_perspective=getattr(pb, "party_perspective", "neutro") or "neutro",
        is_template=pb.is_template,
        is_active=pb.is_active,
        version=pb.version,
        parent_id=pb.parent_id,
        metadata=pb.metadata_,
        rules_count=rules_count,
        created_at=pb.created_at.isoformat() if pb.created_at else "",
        updated_at=pb.updated_at.isoformat() if pb.updated_at else "",
    )


def _rule_to_response(r: PlaybookRule) -> PlaybookRuleResponse:
    return PlaybookRuleResponse(
        id=r.id,
        playbook_id=r.playbook_id,
        clause_type=r.clause_type,
        rule_name=r.rule_name,
        description=r.description,
        preferred_position=r.preferred_position,
        fallback_positions=r.fallback_positions or [],
        rejected_positions=r.rejected_positions or [],
        action_on_reject=r.action_on_reject,
        severity=r.severity,
        guidance_notes=r.guidance_notes,
        order=r.order,
        is_active=r.is_active,
        metadata=r.metadata_,
        created_at=r.created_at.isoformat() if r.created_at else "",
        updated_at=r.updated_at.isoformat() if r.updated_at else "",
    )


async def _share_to_response(s: PlaybookShare, db: AsyncSession) -> PlaybookShareResponse:
    shared_with_email = None
    if s.shared_with_user_id:
        user = await db.get(User, s.shared_with_user_id)
        if user:
            shared_with_email = user.email
    return PlaybookShareResponse(
        id=s.id,
        playbook_id=s.playbook_id,
        shared_with_user_id=s.shared_with_user_id,
        shared_with_org_id=s.shared_with_org_id,
        shared_with_email=shared_with_email,
        permission=s.permission,
        created_at=s.created_at.isoformat() if s.created_at else "",
    )


def _analysis_to_response(
    a: PlaybookAnalysis,
    playbook_name: str,
    clauses: Optional[list] = None,
) -> PlaybookAnalysisSavedResponse:
    """Convert PlaybookAnalysis model to response schema.

    Args:
        a: PlaybookAnalysis ORM instance
        playbook_name: Name of the playbook (loaded separately)
        clauses: Optional pre-parsed ClauseAnalysisResult list.
            If None, clause_results JSON from the model is used directly.
    """
    from app.schemas.playbook_analysis import ClauseAnalysisResult as ClauseSchema

    if clauses is not None:
        clause_data = [c.model_dump(mode="json") if hasattr(c, "model_dump") else c for c in clauses]
    else:
        clause_data = a.clause_results or []

    # Parse clause_data back to ClauseAnalysisResult for validation
    parsed_clauses = []
    for c in clause_data:
        if isinstance(c, dict):
            try:
                parsed_clauses.append(ClauseSchema(**c))
            except Exception:
                parsed_clauses.append(ClauseSchema(
                    rule_id=c.get("rule_id", ""),
                    rule_name=c.get("rule_name", ""),
                    clause_type=c.get("clause_type", ""),
                    found_in_contract=c.get("found_in_contract", False),
                    classification=c.get("classification", "needs_review"),
                    severity=c.get("severity", "medium"),
                    explanation=c.get("explanation", ""),
                    comment=c.get("comment"),
                    confidence=c.get("confidence", 0.0),
                ))
        elif hasattr(c, "model_dump"):
            parsed_clauses.append(c)

    return PlaybookAnalysisSavedResponse(
        id=a.id,
        playbook_id=a.playbook_id,
        playbook_name=playbook_name,
        document_id=a.document_id,
        user_id=a.user_id,
        organization_id=a.organization_id,
        total_rules=a.total_rules,
        compliant=a.compliant,
        needs_review=a.needs_review,
        non_compliant=a.non_compliant,
        not_found=a.not_found,
        risk_score=a.risk_score,
        summary=a.summary,
        clauses=parsed_clauses,
        reviewed_clauses=a.reviewed_clauses,
        model_used=a.model_used,
        analysis_duration_ms=a.analysis_duration_ms,
        created_at=a.created_at.isoformat() if a.created_at else "",
        updated_at=a.updated_at.isoformat() if a.updated_at else "",
    )
