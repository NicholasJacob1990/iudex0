"""
Endpoints para o modulo Word Add-in.

Fornece funcionalidades especificas para o Office Add-in do Word:
- Analise inline com playbooks
- Edicao de conteudo com IA (SSE)
- Traducao (SSE)
- Anonimizacao (LGPD)
- Run Playbook com redlines OOXML (Fase 2)
- Aplicacao/rejeicao de redlines individuais e batch
- Listagem de playbooks para o Add-in
- Cache de redlines para recuperacao posterior
- Persistencia de estado de redlines (Gap 4)
- Historico de analises anteriores (Gap 11)
- Recomendacao de playbooks (Gap 12)
"""

import hashlib
import json
import logging
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.time_utils import utcnow
from app.models.playbook import Playbook, PlaybookRule, PlaybookShare
from app.models.playbook_run_cache import PlaybookRunCache
from app.models.redline_state import RedlineState, RedlineStatus
from app.models.user import User
from app.schemas.word_addin import (
    InlineAnalyzeRequest,
    InlineAnalyzeResponse,
    EditContentRequest,
    TranslateRequest,
    AnonymizeRequest,
    AnonymizeResponse,
    RunPlaybookRequest,
    RunPlaybookResponse,
    RedlineData,
    ClauseData,
    PlaybookRunStats,
    ApplyRedlineRequest,
    ApplyRedlineResponse,
    RejectRedlineRequest,
    RejectRedlineResponse,
    ApplyAllRedlinesRequest,
    ApplyAllRedlinesResponse,
    RestorePlaybookRunResponse,
    PlaybookListItem,
    PlaybookListResponse,
    RedlineStateData,
    RedlineStateResponse,
    GetRedlineStatesResponse,
    AuditReportSummary,
    AuditReportRedline,
    AuditReportResponse,
)
from app.services.word_addin_service import word_addin_service

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Endpoints existentes
# ---------------------------------------------------------------------------


@router.post(
    "/analyze-content",
    response_model=InlineAnalyzeResponse,
    summary="Analisa conteudo inline com playbook",
)
async def analyze_inline_content(
    request: InlineAnalyzeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> InlineAnalyzeResponse:
    """
    Analisa conteudo de documento enviado inline contra um playbook.

    Diferente de /playbooks/{id}/analyze/{doc_id}, este endpoint aceita
    o texto diretamente no body -- ideal para o Office Add-in que extrai
    o conteudo via Office.js.
    """
    try:
        result = await word_addin_service.analyze_inline_content(
            playbook_id=request.playbook_id,
            document_content=request.document_content,
            document_format=request.document_format,
            user_id=str(current_user.id),
            db=db,
        )
        return result
    except Exception as e:
        logger.error(f"Erro na analise inline: {e}")
        raise HTTPException(status_code=500, detail="Erro interno")


@router.post(
    "/edit-content",
    summary="Edita conteudo com IA (SSE)",
)
async def edit_content(
    request: EditContentRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Edita conteudo usando IA via streaming SSE.

    Aceita texto selecionado no Word + instrucao em linguagem natural.
    Retorna o texto editado via SSE com eventos thinking/content/done.
    """
    return StreamingResponse(
        word_addin_service.edit_content_stream(
            content=request.content,
            instruction=request.instruction,
            model=request.model,
            context=request.context,
            user_id=str(current_user.id),
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/translate",
    summary="Traduz conteudo (SSE)",
)
async def translate_content(
    request: TranslateRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Traduz conteudo de documento via streaming SSE.
    Mantem terminologia juridica e formatacao.
    """
    return StreamingResponse(
        word_addin_service.translate_content_stream(
            content=request.content,
            source_lang=request.source_lang,
            target_lang=request.target_lang,
            user_id=str(current_user.id),
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/anonymize",
    response_model=AnonymizeResponse,
    summary="Anonimiza conteudo (LGPD)",
)
async def anonymize_content(
    request: AnonymizeRequest,
    current_user: User = Depends(get_current_user),
) -> AnonymizeResponse:
    """
    Identifica e substitui informacoes pessoais (PII) no texto.
    Util para preparar documentos conforme LGPD.
    """
    try:
        result = await word_addin_service.anonymize_content(
            content=request.content,
            entities_to_anonymize=request.entities_to_anonymize,
            user_id=str(current_user.id),
        )
        return AnonymizeResponse(**result)
    except Exception as e:
        logger.error(f"Erro na anonimizacao: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Fase 2 — Run Playbook + Redlines OOXML
# ---------------------------------------------------------------------------


async def _cleanup_expired_caches(db: AsyncSession) -> int:
    """Remove caches expirados. Retorna quantidade removida."""
    stmt = delete(PlaybookRunCache).where(
        PlaybookRunCache.expires_at < utcnow()
    )
    result = await db.execute(stmt)
    await db.commit()
    count = result.rowcount
    if count > 0:
        logger.info("Cleaned up %d expired playbook run caches", count)
    return count


async def _get_cached_run(
    db: AsyncSession,
    playbook_run_id: str,
    user_id: str,
) -> PlaybookRunCache | None:
    """
    Recupera um cache de execucao de playbook.
    Retorna None se nao encontrado ou expirado.
    """
    stmt = select(PlaybookRunCache).where(
        PlaybookRunCache.id == playbook_run_id,
        PlaybookRunCache.user_id == user_id,
    )
    result = await db.execute(stmt)
    cache = result.scalar_one_or_none()

    if cache and cache.is_expired:
        # Remove o cache expirado
        await db.delete(cache)
        await db.commit()
        return None

    return cache


@router.post(
    "/playbook/run",
    response_model=RunPlaybookResponse,
    summary="Executar playbook no documento Word com redlines OOXML",
)
async def run_playbook(
    request: RunPlaybookRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RunPlaybookResponse:
    """
    Executa um playbook completo no documento Word.

    Fluxo:
    1. Recebe texto do documento via Office.js
    2. Executa todas as regras do playbook contra o documento
    3. Gera redlines OOXML com tracked changes (w:ins/w:del)
    4. Gera comentarios para cada redline
    5. Salva resultados no cache (TTL 24h) para aplicacao posterior
    6. Retorna lista de redlines com OOXML individual e package completo

    O frontend pode:
    - Exibir a lista de clausulas com classificacao visual
    - Aplicar redlines individuais via insertOoxml()
    - Aplicar todos os redlines de uma vez
    - Rejeitar redlines individualmente
    - Restaurar redlines do cache via /playbook/run/{id}/restore
    """
    try:
        from app.services.redline_service import redline_service

        # Limpar caches expirados (cleanup periodico)
        await _cleanup_expired_caches(db)

        result = await redline_service.run_playbook_on_word_document(
            document_content=request.document_content,
            playbook_id=request.playbook_id,
            user_id=str(current_user.id),
            db=db,
        )

        if not result.get("success"):
            return RunPlaybookResponse(
                success=False,
                playbook_id=request.playbook_id,
                playbook_name=result.get("playbook_name", ""),
                error=result.get("error", "Erro desconhecido"),
            )

        # Convert raw dicts to schema objects
        redlines = [RedlineData(**r) for r in result.get("redlines", [])]
        clauses = [ClauseData(**c) for c in result.get("clauses", [])]
        stats_dict = result.get("stats", {})
        stats = PlaybookRunStats(**stats_dict)

        playbook_run_id = None

        # Salvar no cache se solicitado
        if request.cache_results:
            document_hash = hashlib.sha256(
                request.document_content.encode()
            ).hexdigest()

            cache_entry = PlaybookRunCache(
                user_id=str(current_user.id),
                playbook_id=request.playbook_id,
                document_hash=document_hash,
                redlines_json=json.dumps(result.get("redlines", [])),
                analysis_result_json=json.dumps({
                    "playbook_name": result.get("playbook_name", ""),
                    "clauses": result.get("clauses", []),
                    "stats": stats_dict,
                    "summary": result.get("summary", ""),
                }),
                expires_at=utcnow() + timedelta(hours=24),
            )
            db.add(cache_entry)
            await db.commit()
            await db.refresh(cache_entry)
            playbook_run_id = cache_entry.id
            logger.info(
                "Playbook run cached: %s (expires %s)",
                playbook_run_id,
                cache_entry.expires_at,
            )

        return RunPlaybookResponse(
            success=True,
            playbook_id=result["playbook_id"],
            playbook_name=result["playbook_name"],
            playbook_run_id=playbook_run_id,
            redlines=redlines,
            clauses=clauses,
            stats=stats,
            summary=result.get("summary", ""),
            ooxml_package=result.get("ooxml_package") if request.include_ooxml else None,
        )

    except ValueError as e:
        logger.warning("Erro de validacao no run playbook: %s", e)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Erro ao executar playbook no Word: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Erro interno ao executar o playbook.",
        )


@router.get(
    "/playbook/run/{playbook_run_id}/restore",
    response_model=RestorePlaybookRunResponse,
    summary="Restaurar redlines de uma execucao de playbook do cache",
)
async def restore_playbook_run(
    playbook_run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RestorePlaybookRunResponse:
    """
    Restaura redlines e resultados de uma execucao de playbook do cache.

    Util quando o usuario volta ao documento e quer continuar aplicando
    ou rejeitando redlines sem re-executar a analise.

    Cache tem TTL de 24 horas.
    """
    cache = await _get_cached_run(db, playbook_run_id, str(current_user.id))

    if not cache:
        raise HTTPException(
            status_code=404,
            detail="Execucao de playbook nao encontrada ou expirada",
        )

    try:
        redlines_raw = json.loads(cache.redlines_json)
        analysis_result = json.loads(cache.analysis_result_json)

        redlines = [RedlineData(**r) for r in redlines_raw]
        clauses = [ClauseData(**c) for c in analysis_result.get("clauses", [])]
        stats = PlaybookRunStats(**analysis_result.get("stats", {}))

        return RestorePlaybookRunResponse(
            success=True,
            playbook_run_id=cache.id,
            playbook_id=cache.playbook_id,
            playbook_name=analysis_result.get("playbook_name", ""),
            redlines=redlines,
            clauses=clauses,
            stats=stats,
            summary=analysis_result.get("summary", ""),
            expires_at=cache.expires_at.isoformat() if cache.expires_at else None,
        )

    except Exception as e:
        logger.error("Erro ao restaurar playbook run %s: %s", playbook_run_id, e)
        raise HTTPException(
            status_code=500,
            detail="Erro ao restaurar dados do cache",
        )


@router.post(
    "/redline/apply",
    response_model=ApplyRedlineResponse,
    summary="Aplicar redline(s) especifico(s)",
)
async def apply_redlines(
    request: ApplyRedlineRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApplyRedlineResponse:
    """
    Aplica redline(s) especifico(s) retornando o OOXML de cada um.

    Recupera os redlines do cache e gera OOXML individual para cada um.

    O frontend recebe o OOXML e o insere no documento via:
    - insertOoxml() para tracked changes OOXML
    - insertComment() como fallback
    - replaceText() para substituicao direta

    Cada OOXML contem:
    - w:del para texto removido (tachado vermelho)
    - w:ins para texto inserido (sublinhado azul)
    - w:comment com regra, classificacao e justificativa
    """
    from app.services.redline_service import redline_service, RedlineItem

    # Recuperar do cache
    cache = await _get_cached_run(db, request.playbook_run_id, str(current_user.id))

    if not cache:
        raise HTTPException(
            status_code=404,
            detail="Execucao de playbook nao encontrada ou expirada",
        )

    try:
        redlines_raw = json.loads(cache.redlines_json)
    except Exception as e:
        logger.error("Erro ao parsear cache de redlines: %s", e)
        raise HTTPException(
            status_code=500,
            detail="Erro ao ler dados do cache",
        )

    # Indexar redlines por ID
    redlines_by_id = {r["redline_id"]: r for r in redlines_raw}

    applied = []
    failed = []
    ooxml_data = {}

    for redline_id in request.redline_ids:
        try:
            redline_dict = redlines_by_id.get(redline_id)
            if not redline_dict:
                logger.warning("Redline %s nao encontrado no cache", redline_id)
                failed.append(redline_id)
                continue

            # Construir RedlineItem a partir do dict
            item = RedlineItem(
                redline_id=redline_dict["redline_id"],
                rule_id=redline_dict["rule_id"],
                rule_name=redline_dict["rule_name"],
                clause_type=redline_dict["clause_type"],
                classification=redline_dict["classification"],
                severity=redline_dict["severity"],
                original_text=redline_dict["original_text"],
                suggested_text=redline_dict["suggested_text"],
                explanation=redline_dict["explanation"],
                comment=redline_dict.get("comment"),
                confidence=redline_dict.get("confidence", 0.0),
            )

            # Gerar OOXML
            ooxml = redline_service.generate_single_redline_ooxml(item)
            ooxml_data[redline_id] = ooxml
            applied.append(redline_id)

            # Persistir estado como applied (se o modelo existir)
            now = utcnow()
            stmt = select(RedlineState).where(
                RedlineState.playbook_run_id == request.playbook_run_id,
                RedlineState.redline_id == redline_id,
            )
            result = await db.execute(stmt)
            state = result.scalar_one_or_none()

            if state:
                state.status = RedlineStatus.APPLIED
                state.applied_at = now
                state.rejected_at = None
            else:
                state = RedlineState(
                    user_id=str(current_user.id),
                    playbook_run_id=request.playbook_run_id,
                    redline_id=redline_id,
                    status=RedlineStatus.APPLIED,
                    applied_at=now,
                )
                db.add(state)

        except Exception as e:
            logger.warning("Falha ao aplicar redline %s: %s", redline_id, e)
            failed.append(redline_id)

    await db.commit()

    return ApplyRedlineResponse(
        success=len(failed) == 0,
        applied=applied,
        failed=failed,
        ooxml_data=ooxml_data,
    )


@router.post(
    "/redline/reject",
    response_model=RejectRedlineResponse,
    summary="Rejeitar redline(s)",
)
async def reject_redlines(
    request: RejectRedlineRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RejectRedlineResponse:
    """
    Rejeita redline(s), marcando-os como revisados e descartados.

    O texto original e mantido no documento. O estado e persistido
    para que possa ser recuperado ao reabrir o Add-in.
    """
    # Verificar se o cache existe
    cache = await _get_cached_run(db, request.playbook_run_id, str(current_user.id))

    if not cache:
        raise HTTPException(
            status_code=404,
            detail="Execucao de playbook nao encontrada ou expirada",
        )

    rejected = []
    failed = []
    now = utcnow()

    for redline_id in request.redline_ids:
        try:
            # Persistir estado como rejected
            stmt = select(RedlineState).where(
                RedlineState.playbook_run_id == request.playbook_run_id,
                RedlineState.redline_id == redline_id,
            )
            result = await db.execute(stmt)
            state = result.scalar_one_or_none()

            if state:
                state.status = RedlineStatus.REJECTED
                state.rejected_at = now
                state.applied_at = None
            else:
                state = RedlineState(
                    user_id=str(current_user.id),
                    playbook_run_id=request.playbook_run_id,
                    redline_id=redline_id,
                    status=RedlineStatus.REJECTED,
                    rejected_at=now,
                )
                db.add(state)

            rejected.append(redline_id)

        except Exception as e:
            logger.warning("Falha ao rejeitar redline %s: %s", redline_id, e)
            failed.append(redline_id)

    await db.commit()

    return RejectRedlineResponse(
        success=len(failed) == 0,
        rejected=rejected,
        failed=failed,
    )


@router.post(
    "/redline/apply-all",
    response_model=ApplyAllRedlinesResponse,
    summary="Aplicar todos os redlines",
)
async def apply_all_redlines(
    request: ApplyAllRedlinesRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApplyAllRedlinesResponse:
    """
    Aplica todos os redlines pendentes (ou um subset) de uma vez.

    Recupera os redlines do cache e gera um OOXML package completo
    com todos os tracked changes para insercao em batch.

    Se redline_ids for fornecido, aplica apenas os IDs especificados.
    Se None, aplica todos os redlines pendentes (nao aplicados/rejeitados).
    """
    from app.services.redline_service import redline_service, RedlineItem

    # Recuperar do cache
    cache = await _get_cached_run(db, request.playbook_run_id, str(current_user.id))

    if not cache:
        raise HTTPException(
            status_code=404,
            detail="Execucao de playbook nao encontrada ou expirada",
        )

    try:
        redlines_raw = json.loads(cache.redlines_json)
    except Exception as e:
        logger.error("Erro ao parsear cache de redlines: %s", e)
        raise HTTPException(
            status_code=500,
            detail="Erro ao ler dados do cache",
        )

    # Buscar estados existentes para filtrar pendentes
    stmt = select(RedlineState).where(
        RedlineState.playbook_run_id == request.playbook_run_id,
        RedlineState.user_id == str(current_user.id),
    )
    result = await db.execute(stmt)
    existing_states = {s.redline_id: s for s in result.scalars().all()}

    # Filtrar redlines a aplicar
    redlines_to_apply = []
    for r in redlines_raw:
        redline_id = r["redline_id"]

        # Se IDs especificos foram fornecidos, filtrar
        if request.redline_ids and redline_id not in request.redline_ids:
            continue

        # Verificar estado existente
        state = existing_states.get(redline_id)
        if state:
            status_val = state.status.value if isinstance(state.status, RedlineStatus) else state.status
            if status_val in ("applied", "rejected"):
                continue  # Ja processado

        redlines_to_apply.append(r)

    if not redlines_to_apply:
        return ApplyAllRedlinesResponse(
            success=True,
            total=0,
            applied=0,
            failed=0,
            ooxml_package=None,
        )

    # Construir RedlineItems
    items = []
    applied_ids = []
    failed_count = 0
    now = utcnow()

    for r in redlines_to_apply:
        try:
            item = RedlineItem(
                redline_id=r["redline_id"],
                rule_id=r["rule_id"],
                rule_name=r["rule_name"],
                clause_type=r["clause_type"],
                classification=r["classification"],
                severity=r["severity"],
                original_text=r["original_text"],
                suggested_text=r["suggested_text"],
                explanation=r["explanation"],
                comment=r.get("comment"),
                confidence=r.get("confidence", 0.0),
            )
            items.append(item)
            applied_ids.append(r["redline_id"])

            # Persistir estado
            state = existing_states.get(r["redline_id"])
            if state:
                state.status = RedlineStatus.APPLIED
                state.applied_at = now
                state.rejected_at = None
            else:
                new_state = RedlineState(
                    user_id=str(current_user.id),
                    playbook_run_id=request.playbook_run_id,
                    redline_id=r["redline_id"],
                    status=RedlineStatus.APPLIED,
                    applied_at=now,
                )
                db.add(new_state)

        except Exception as e:
            logger.warning("Falha ao processar redline %s: %s", r.get("redline_id"), e)
            failed_count += 1

    # Gerar OOXML package com todos os redlines
    ooxml_package = redline_service.generate_ooxml_redlines(items, include_comments=True)

    await db.commit()

    return ApplyAllRedlinesResponse(
        success=failed_count == 0,
        total=len(redlines_to_apply),
        applied=len(applied_ids),
        failed=failed_count,
        ooxml_package=ooxml_package,
    )


@router.get(
    "/playbook/list",
    response_model=PlaybookListResponse,
    summary="Listar playbooks disponiveis para o Add-in",
)
async def list_playbooks_for_addin(
    skip: int = 0,
    limit: int = 50,
    search: str = Query(None, description="Busca por nome ou descricao"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PlaybookListResponse:
    """
    Lista playbooks disponiveis para uso no Word Add-in.

    Retorna playbooks do usuario, compartilhados e publicos.
    Otimizado para exibicao no painel lateral do Add-in.
    """
    user_id = str(current_user.id)
    org_id = getattr(current_user, "organization_id", None)

    # Base conditions: own playbooks + shared + public
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
    conditions.append(Playbook.scope == "public")

    stmt = select(Playbook).where(
        Playbook.is_active == True,  # noqa: E712
        or_(*conditions),
    )

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

    items = []
    for pb in playbooks:
        # Get rules count
        count_result = await db.execute(
            select(func.count()).select_from(PlaybookRule).where(
                PlaybookRule.playbook_id == pb.id,
                PlaybookRule.is_active == True,  # noqa: E712
            )
        )
        rules_count = count_result.scalar() or 0

        items.append(PlaybookListItem(
            id=pb.id,
            name=pb.name,
            description=pb.description,
            area=pb.area,
            rules_count=rules_count,
            scope=pb.scope if isinstance(pb.scope, str) else pb.scope.value,
            party_perspective=getattr(pb, "party_perspective", "neutro") or "neutro",
        ))

    return PlaybookListResponse(items=items, total=total)


# ---------------------------------------------------------------------------
# Gap 4 — Persistencia de Estado de Redlines
# ---------------------------------------------------------------------------


@router.post(
    "/redline/state/{playbook_run_id}/{redline_id}/applied",
    response_model=RedlineStateResponse,
    summary="Persistir estado de redline como aplicado",
)
async def persist_redline_applied(
    playbook_run_id: str,
    redline_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RedlineStateResponse:
    """
    Persiste o estado de um redline como 'applied'.

    Upsert: cria novo registro ou atualiza existente.
    Permite recuperar o estado ao reabrir o Add-in.
    """
    user_id = str(current_user.id)
    now = utcnow()

    try:
        # Buscar estado existente
        stmt = select(RedlineState).where(
            RedlineState.playbook_run_id == playbook_run_id,
            RedlineState.redline_id == redline_id,
        )
        result = await db.execute(stmt)
        state = result.scalar_one_or_none()

        if state:
            # Update existing
            state.status = RedlineStatus.APPLIED
            state.applied_at = now
            state.rejected_at = None
            state.updated_at = now
        else:
            # Create new
            state = RedlineState(
                user_id=user_id,
                playbook_run_id=playbook_run_id,
                redline_id=redline_id,
                status=RedlineStatus.APPLIED,
                applied_at=now,
            )
            db.add(state)

        await db.flush()

        return RedlineStateResponse(
            success=True,
            redline_id=redline_id,
            status="applied",
            message="Estado persistido com sucesso",
        )

    except Exception as e:
        logger.error(
            "Erro ao persistir estado applied para redline %s: %s",
            redline_id, e, exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao persistir estado: {str(e)}",
        )


@router.post(
    "/redline/state/{playbook_run_id}/{redline_id}/rejected",
    response_model=RedlineStateResponse,
    summary="Persistir estado de redline como rejeitado",
)
async def persist_redline_rejected(
    playbook_run_id: str,
    redline_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RedlineStateResponse:
    """
    Persiste o estado de um redline como 'rejected'.

    Upsert: cria novo registro ou atualiza existente.
    Permite recuperar o estado ao reabrir o Add-in.
    """
    user_id = str(current_user.id)
    now = utcnow()

    try:
        # Buscar estado existente
        stmt = select(RedlineState).where(
            RedlineState.playbook_run_id == playbook_run_id,
            RedlineState.redline_id == redline_id,
        )
        result = await db.execute(stmt)
        state = result.scalar_one_or_none()

        if state:
            # Update existing
            state.status = RedlineStatus.REJECTED
            state.rejected_at = now
            state.applied_at = None
            state.updated_at = now
        else:
            # Create new
            state = RedlineState(
                user_id=user_id,
                playbook_run_id=playbook_run_id,
                redline_id=redline_id,
                status=RedlineStatus.REJECTED,
                rejected_at=now,
            )
            db.add(state)

        await db.flush()

        return RedlineStateResponse(
            success=True,
            redline_id=redline_id,
            status="rejected",
            message="Estado persistido com sucesso",
        )

    except Exception as e:
        logger.error(
            "Erro ao persistir estado rejected para redline %s: %s",
            redline_id, e, exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao persistir estado: {str(e)}",
        )


@router.get(
    "/redline/state/{playbook_run_id}",
    response_model=GetRedlineStatesResponse,
    summary="Obter estados de redlines de um playbook run",
)
async def get_redline_states(
    playbook_run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> GetRedlineStatesResponse:
    """
    Retorna todos os estados de redlines para um playbook run.

    Usado para restaurar o progresso da revisao ao reabrir o Add-in.
    Inclui estatisticas de pending/applied/rejected.
    """
    user_id = str(current_user.id)

    try:
        # Buscar todos os estados para este playbook run
        stmt = select(RedlineState).where(
            RedlineState.playbook_run_id == playbook_run_id,
            RedlineState.user_id == user_id,
        )
        result = await db.execute(stmt)
        states = result.scalars().all()

        # Converter para schema
        state_data = []
        stats = {"total": 0, "pending": 0, "applied": 0, "rejected": 0}

        for state in states:
            status_str = state.status.value if isinstance(state.status, RedlineStatus) else state.status
            state_data.append(RedlineStateData(
                redline_id=state.redline_id,
                status=status_str,
                applied_at=state.applied_at.isoformat() if state.applied_at else None,
                rejected_at=state.rejected_at.isoformat() if state.rejected_at else None,
            ))
            stats["total"] += 1
            if status_str in stats:
                stats[status_str] += 1

        return GetRedlineStatesResponse(
            success=True,
            playbook_run_id=playbook_run_id,
            states=state_data,
            stats=stats,
        )

    except Exception as e:
        logger.error(
            "Erro ao buscar estados de redlines para run %s: %s",
            playbook_run_id, e, exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao buscar estados: {str(e)}",
        )


# ---------------------------------------------------------------------------
# Gap 11 — Historico de Analises Anteriores
# ---------------------------------------------------------------------------


class PlaybookRunHistoryItem(BaseModel):
    """Item do historico de execucoes de playbook."""
    id: str
    playbook_id: str
    playbook_name: str
    document_name: Optional[str] = None
    created_at: str
    stats: dict


class PlaybookRunHistoryResponse(BaseModel):
    """Resposta do historico de execucoes."""
    items: List[PlaybookRunHistoryItem]
    total: int


@router.get(
    "/user/playbook-runs",
    response_model=PlaybookRunHistoryResponse,
    summary="Listar historico de execucoes de playbook do usuario",
)
async def list_user_playbook_runs(
    limit: int = Query(10, ge=1, le=50, description="Maximo de itens a retornar"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PlaybookRunHistoryResponse:
    """
    Gap 11: Lista as ultimas execucoes de playbook do usuario.

    Retorna historico de analises com estatisticas resumidas,
    permitindo ao usuario restaurar analises anteriores.

    Limitado aos ultimos N runs (default 10, max 50).
    Exclui caches expirados.
    """
    user_id = str(current_user.id)

    try:
        # Buscar execucoes recentes nao expiradas
        stmt = (
            select(PlaybookRunCache)
            .where(
                PlaybookRunCache.user_id == user_id,
                PlaybookRunCache.expires_at > utcnow(),
            )
            .order_by(PlaybookRunCache.created_at.desc())
            .limit(limit)
        )
        result = await db.execute(stmt)
        runs = result.scalars().all()

        # Buscar nomes dos playbooks
        playbook_ids = list(set(r.playbook_id for r in runs))
        if playbook_ids:
            pb_stmt = select(Playbook).where(Playbook.id.in_(playbook_ids))
            pb_result = await db.execute(pb_stmt)
            playbooks_by_id = {pb.id: pb for pb in pb_result.scalars().all()}
        else:
            playbooks_by_id = {}

        items = []
        for run in runs:
            # Parsear resultado da analise para obter stats
            try:
                analysis_result = json.loads(run.analysis_result_json)
                stats = analysis_result.get("stats", {})
                playbook_name = analysis_result.get("playbook_name", "")
            except Exception:
                stats = {}
                playbook_name = ""

            # Se nao tem nome no cache, buscar do playbook
            if not playbook_name and run.playbook_id in playbooks_by_id:
                playbook_name = playbooks_by_id[run.playbook_id].name

            items.append(PlaybookRunHistoryItem(
                id=run.id,
                playbook_id=run.playbook_id,
                playbook_name=playbook_name,
                document_name=None,  # Poderia ser extraido do document_hash se necessario
                created_at=run.created_at.isoformat(),
                stats=stats,
            ))

        return PlaybookRunHistoryResponse(items=items, total=len(items))

    except Exception as e:
        logger.error("Erro ao listar historico de playbook runs: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Erro ao buscar historico",
        )


# ---------------------------------------------------------------------------
# Gap 12 — Sugestao de Playbook Recomendado
# ---------------------------------------------------------------------------


class RecommendPlaybookRequest(BaseModel):
    """Request para recomendacao de playbook."""
    document_excerpt: str = Field(
        ...,
        min_length=100,
        max_length=5000,
        description="Trecho inicial do documento (primeiros 2000-5000 caracteres)"
    )


class RecommendedPlaybook(BaseModel):
    """Playbook recomendado."""
    id: str
    name: str
    description: Optional[str] = None
    area: Optional[str] = None
    relevance_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Score de relevancia (0-1)"
    )
    reason: str = Field(..., description="Motivo da recomendacao")


class RecommendPlaybookResponse(BaseModel):
    """Resposta da recomendacao de playbook."""
    document_type: str = Field(..., description="Tipo de documento detectado")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confianca na classificacao")
    recommended: List[RecommendedPlaybook] = Field(
        default_factory=list,
        description="Playbooks recomendados ordenados por relevancia"
    )


# Mapeamento de tipos de documento para areas de playbook
DOCUMENT_TYPE_TO_AREA = {
    "contrato_prestacao_servicos": ["contratos", "prestacao_servicos", "comercial"],
    "contrato_locacao": ["contratos", "locacao", "imobiliario"],
    "contrato_compra_venda": ["contratos", "compra_venda", "comercial"],
    "contrato_trabalho": ["contratos", "trabalhista", "recursos_humanos"],
    "contrato_sociedade": ["contratos", "societario", "comercial"],
    "procuracao": ["procuracoes", "mandato"],
    "peticao_inicial": ["processual", "litigio"],
    "contestacao": ["processual", "litigio"],
    "recurso": ["processual", "recurso", "litigio"],
    "acordo": ["contratos", "acordo", "transacao"],
    "nda": ["contratos", "confidencialidade", "comercial"],
    "termo_adesao": ["contratos", "adesao", "consumidor"],
    "parecer": ["parecer", "consultivo"],
    "memorando": ["interno", "corporativo"],
    "regulamento": ["regulamento", "compliance"],
    "politica": ["politica", "compliance", "corporativo"],
}


async def classify_document_type(excerpt: str) -> tuple[str, float]:
    """
    Classifica o tipo de documento baseado no excerpt.

    Usa heuristicas simples + keywords para classificacao rapida.
    Em producao, poderia usar LLM para classificacao mais precisa.

    Returns:
        Tuple de (tipo_documento, confianca)
    """
    excerpt_lower = excerpt.lower()

    # Heuristicas por keywords
    classifications = []

    # Contratos
    if "prestacao de servico" in excerpt_lower or "prestador" in excerpt_lower:
        classifications.append(("contrato_prestacao_servicos", 0.8))
    if "locacao" in excerpt_lower or "locador" in excerpt_lower or "locatario" in excerpt_lower:
        classifications.append(("contrato_locacao", 0.85))
    if "compra e venda" in excerpt_lower or "vendedor" in excerpt_lower and "comprador" in excerpt_lower:
        classifications.append(("contrato_compra_venda", 0.8))
    if "empregado" in excerpt_lower or "empregador" in excerpt_lower or "clt" in excerpt_lower:
        classifications.append(("contrato_trabalho", 0.85))
    if "socio" in excerpt_lower or "quotas" in excerpt_lower or "capital social" in excerpt_lower:
        classifications.append(("contrato_sociedade", 0.8))

    # Procuracao
    if "procuracao" in excerpt_lower or "outorgante" in excerpt_lower or "outorgado" in excerpt_lower:
        classifications.append(("procuracao", 0.9))

    # Processual
    if "excelentissimo" in excerpt_lower or "meritissimo" in excerpt_lower:
        if "autor" in excerpt_lower and "reu" in excerpt_lower:
            classifications.append(("peticao_inicial", 0.75))
        if "contestacao" in excerpt_lower:
            classifications.append(("contestacao", 0.85))
        if "recurso" in excerpt_lower or "apelacao" in excerpt_lower:
            classifications.append(("recurso", 0.8))

    # NDA / Confidencialidade
    if "confidencial" in excerpt_lower or "sigilo" in excerpt_lower or "nda" in excerpt_lower:
        classifications.append(("nda", 0.8))

    # Acordo
    if "acordo" in excerpt_lower and "transacao" in excerpt_lower:
        classifications.append(("acordo", 0.75))

    # Termo de adesao
    if "termo de adesao" in excerpt_lower or "adesao" in excerpt_lower:
        classifications.append(("termo_adesao", 0.7))

    # Parecer
    if "parecer" in excerpt_lower and ("juridico" in excerpt_lower or "consulta" in excerpt_lower):
        classifications.append(("parecer", 0.8))

    # Politica / Regulamento
    if "politica" in excerpt_lower and ("privacidade" in excerpt_lower or "dados" in excerpt_lower):
        classifications.append(("politica", 0.8))
    if "regulamento" in excerpt_lower:
        classifications.append(("regulamento", 0.75))

    # Se nenhuma classificacao especifica, tentar generica
    if not classifications:
        if "contrato" in excerpt_lower or "clausula" in excerpt_lower:
            classifications.append(("contrato_generico", 0.5))
        else:
            classifications.append(("documento_juridico", 0.3))

    # Retornar a classificacao com maior confianca
    classifications.sort(key=lambda x: x[1], reverse=True)
    return classifications[0]


def rank_playbooks_by_relevance(
    playbooks: list,
    document_type: str,
    confidence: float
) -> list[dict]:
    """
    Rankeia playbooks por relevancia ao tipo de documento.

    Args:
        playbooks: Lista de objetos Playbook
        document_type: Tipo de documento detectado
        confidence: Confianca da classificacao

    Returns:
        Lista de dicts com playbook + score + reason
    """
    relevant_areas = DOCUMENT_TYPE_TO_AREA.get(document_type, [])
    document_type_readable = document_type.replace("_", " ").title()

    ranked = []
    for pb in playbooks:
        pb_area = (pb.area or "").lower()
        pb_name = (pb.name or "").lower()
        pb_desc = (pb.description or "").lower()

        # Calcular score de relevancia
        score = 0.0
        reasons = []

        # Match por area
        for area in relevant_areas:
            if area in pb_area:
                score += 0.4
                reasons.append(f"Area '{area}' compativel")
                break

        # Match por nome
        for area in relevant_areas:
            if area in pb_name:
                score += 0.3
                reasons.append(f"Nome menciona '{area}'")
                break

        # Match por keywords no nome/descricao
        doc_keywords = document_type.split("_")
        for kw in doc_keywords:
            if len(kw) > 3 and kw in pb_name:
                score += 0.2
                reasons.append(f"Keyword '{kw}' no nome")
            if len(kw) > 3 and kw in pb_desc:
                score += 0.1
                reasons.append(f"Keyword '{kw}' na descricao")

        # Ajustar pela confianca da classificacao
        score = min(score * confidence, 1.0)

        if score > 0:
            ranked.append({
                "playbook": pb,
                "score": round(score, 2),
                "reason": "; ".join(reasons[:2]) if reasons else f"Potencialmente relevante para {document_type_readable}",
            })

    # Ordenar por score decrescente
    ranked.sort(key=lambda x: x["score"], reverse=True)
    return ranked


@router.post(
    "/playbook/recommend",
    response_model=RecommendPlaybookResponse,
    summary="Recomendar playbooks para o documento",
)
async def recommend_playbook(
    request: RecommendPlaybookRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RecommendPlaybookResponse:
    """
    Gap 12: Recomenda playbooks baseado no conteudo do documento.

    Analisa o excerpt do documento (primeiros ~2000 caracteres),
    classifica o tipo de documento e sugere playbooks relevantes.

    Processo:
    1. Classifica tipo de documento usando heuristicas + keywords
    2. Busca playbooks disponiveis (proprios + compartilhados + publicos)
    3. Rankeia por relevancia ao tipo de documento
    4. Retorna top 3 recomendacoes

    Em versoes futuras, pode usar LLM para classificacao mais precisa.
    """
    user_id = str(current_user.id)
    org_id = getattr(current_user, "organization_id", None)

    try:
        # 1. Classificar tipo de documento
        document_type, confidence = await classify_document_type(request.document_excerpt)
        document_type_readable = document_type.replace("_", " ").title()

        # 2. Buscar playbooks disponiveis
        conditions = [Playbook.user_id == user_id]

        # Playbooks compartilhados
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
        conditions.append(Playbook.scope == "public")

        stmt = select(Playbook).where(
            Playbook.is_active == True,  # noqa: E712
            or_(*conditions),
        )
        result = await db.execute(stmt)
        playbooks = result.scalars().all()

        # 3. Rankear por relevancia
        ranked = rank_playbooks_by_relevance(playbooks, document_type, confidence)

        # 4. Retornar top 3
        recommended = []
        for item in ranked[:3]:
            pb = item["playbook"]
            recommended.append(RecommendedPlaybook(
                id=pb.id,
                name=pb.name,
                description=pb.description,
                area=pb.area,
                relevance_score=item["score"],
                reason=item["reason"],
            ))

        return RecommendPlaybookResponse(
            document_type=document_type_readable,
            confidence=round(confidence, 2),
            recommended=recommended,
        )

    except Exception as e:
        logger.error("Erro ao recomendar playbook: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Erro ao processar recomendacao",
        )


# ---------------------------------------------------------------------------
# Gap 8 — Exportacao de Audit Log
# ---------------------------------------------------------------------------


@router.get(
    "/playbook/run/{playbook_run_id}/audit-report",
    response_model=AuditReportResponse,
    summary="Gerar relatorio de auditoria de redlines",
)
async def get_audit_report(
    playbook_run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AuditReportResponse:
    """
    Gera um relatorio de auditoria completo para uma execucao de playbook.

    Inclui:
    - Resumo com estatisticas (total, aplicados, rejeitados, pendentes)
    - Detalhes de cada redline com status atual
    - Timestamps de aplicacao/rejeicao

    Ideal para:
    - Documentar revisoes de contratos
    - Compliance e auditoria
    - Historico de decisoes
    """
    user_id = str(current_user.id)

    # Buscar cache do playbook run
    cache = await _get_cached_run(db, playbook_run_id, user_id)

    if not cache:
        raise HTTPException(
            status_code=404,
            detail="Execucao de playbook nao encontrada ou expirada",
        )

    try:
        # Parsear dados do cache
        redlines_raw = json.loads(cache.redlines_json)
        analysis_result = json.loads(cache.analysis_result_json)

        # Buscar estados dos redlines
        stmt = select(RedlineState).where(
            RedlineState.playbook_run_id == playbook_run_id,
            RedlineState.user_id == user_id,
        )
        result = await db.execute(stmt)
        states = {s.redline_id: s for s in result.scalars().all()}

        # Contar estatisticas
        applied_count = 0
        rejected_count = 0
        pending_count = 0

        # Montar lista de redlines com status
        report_redlines = []
        for r in redlines_raw:
            redline_id = r["redline_id"]
            state = states.get(redline_id)

            if state:
                status_val = state.status.value if isinstance(state.status, RedlineStatus) else state.status
                applied_at = state.applied_at.isoformat() if state.applied_at else None
                rejected_at = state.rejected_at.isoformat() if state.rejected_at else None

                if status_val == "applied":
                    applied_count += 1
                    status = "applied"
                elif status_val == "rejected":
                    rejected_count += 1
                    status = "rejected"
                else:
                    pending_count += 1
                    status = "pending"
            else:
                status = "pending"
                applied_at = None
                rejected_at = None
                pending_count += 1

            report_redlines.append(AuditReportRedline(
                redline_id=redline_id,
                rule_name=r.get("rule_name", ""),
                clause_type=r.get("clause_type", ""),
                classification=r.get("classification", ""),
                severity=r.get("severity", ""),
                status=status,
                original_text=r.get("original_text", ""),
                suggested_text=r.get("suggested_text", ""),
                explanation=r.get("explanation", ""),
                confidence=r.get("confidence", 0.0),
                applied_at=applied_at,
                rejected_at=rejected_at,
            ))

        # Extrair stats do resultado da analise
        stats_dict = analysis_result.get("stats", {})

        summary = AuditReportSummary(
            total_clauses=len(analysis_result.get("clauses", [])),
            total_redlines=len(redlines_raw),
            applied=applied_count,
            rejected=rejected_count,
            pending=pending_count,
            compliant=stats_dict.get("compliant", 0),
            non_compliant=stats_dict.get("non_compliant", 0),
            needs_review=stats_dict.get("needs_review", 0),
            not_found=stats_dict.get("not_found", 0),
            risk_score=stats_dict.get("risk_score", 0.0),
        )

        return AuditReportResponse(
            playbook_run_id=playbook_run_id,
            playbook_name=analysis_result.get("playbook_name", ""),
            generated_at=utcnow().isoformat(),
            user_email=current_user.email,
            summary=summary,
            analysis_summary=analysis_result.get("summary", ""),
            redlines=report_redlines,
        )

    except Exception as e:
        logger.error("Erro ao gerar audit report para run %s: %s", playbook_run_id, e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Erro ao gerar relatorio de auditoria",
        )
