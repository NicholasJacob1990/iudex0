"""
Endpoints da API para integração DJEN (Diário de Justiça Eletrônico Nacional)
"""

from datetime import datetime, date
import math
from typing import List, Optional, Any
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.djen import ProcessWatchlist, DjenIntimation, DjenOabWatchlist
from app.schemas.djen import (
    DjenSearchParams,
    DatajudSearchParams,
    DatajudProcessResponse,
    ProcessWatchlistCreate,
    ProcessWatchlistUpdate,
    ProcessWatchlistResponse,
    OabWatchlistCreate,
    OabWatchlistResponse,
    DjenIntimationResponse,
    DjenIntimationSearchResponse,
    DestinatarioResponse,
    AdvogadoResponse,
    SyncResult,
)
from app.services.djen_scheduler import compute_next_sync
from app.core.config import settings
from app.services.djen_service import (
    DjenService,
    get_djen_service,
    normalize_npu,
    get_datajud_alias,
    extract_tribunal_from_npu
)
from app.services.djen_sync import sync_process_watchlists, sync_oab_watchlists

router = APIRouter()


def parse_disponibilizacao(value: Optional[str]) -> Optional[date]:
    """Parse da data de disponibilização para Date."""
    if not value:
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


async def _comunica_search(
    params: DjenSearchParams,
    response: Optional[Response] = None
) -> List[DjenIntimationSearchResponse]:
    djen_service = get_djen_service()
    if response is not None:
        results, total_count, items_per_page = await djen_service.comunica.search(
            sigla_tribunal=params.siglaTribunal,
            numero_oab=params.numeroOab,
            uf_oab=params.ufOab,
            nome_advogado=params.nomeAdvogado,
            nome_parte=params.nomeParte,
            texto=params.texto,
            numero_processo=params.numeroProcesso,
            data_inicio=params.dataDisponibilizacaoInicio,
            data_fim=params.dataDisponibilizacaoFim,
            meio=params.meio,
            itens_por_pagina=params.itensPorPagina,
            max_pages=params.maxPages or 100,
            include_meta=True
        )
        if total_count is not None:
            total_pages = math.ceil(total_count / items_per_page) if items_per_page else 0
            response.headers["X-Total-Count"] = str(total_count)
            response.headers["X-Items-Per-Page"] = str(items_per_page)
            response.headers["X-Total-Pages"] = str(total_pages)
    else:
        results = await djen_service.comunica.search(
            sigla_tribunal=params.siglaTribunal,
            numero_oab=params.numeroOab,
            uf_oab=params.ufOab,
            nome_advogado=params.nomeAdvogado,
            nome_parte=params.nomeParte,
            texto=params.texto,
            numero_processo=params.numeroProcesso,
            data_inicio=params.dataDisponibilizacaoInicio,
            data_fim=params.dataDisponibilizacaoFim,
            meio=params.meio,
            itens_por_pagina=params.itensPorPagina,
            max_pages=params.maxPages or 100
        )

    response: List[DjenIntimationSearchResponse] = []
    for item in results:
        response.append(DjenIntimationSearchResponse(
            id=str(item.id),
            hash=item.hash,
            numero_processo=item.numero_processo or item.numero_processo_mascara,
            numero_processo_mascara=item.numero_processo_mascara,
            tribunal_sigla=item.tribunal_sigla,
            tipo_comunicacao=item.tipo_comunicacao,
            nome_orgao=item.nome_orgao,
            texto=item.texto,
            texto_resumo=item.texto[:200] if item.texto else None,
            data_disponibilizacao=parse_disponibilizacao(item.data_disponibilizacao),
            meio=item.meio,
            link=item.link,
            tipo_documento=item.tipo_documento,
            nome_classe=item.nome_classe,
            numero_comunicacao=item.numero_comunicacao,
            destinatarios=_normalize_destinatarios(item.destinatarios),
            advogados=_normalize_advogados(item.advogados),
        ))

    return response


def _normalize_destinatarios(raw_items: Optional[List[Any]]) -> List[DestinatarioResponse]:
    normalized: List[DestinatarioResponse] = []
    if not raw_items:
        return normalized
    for item in raw_items:
        if isinstance(item, str):
            name = item.strip()
            if name:
                normalized.append(DestinatarioResponse(nome=name, polo=None))
            continue
        if isinstance(item, dict):
            name = (
                item.get("nome")
                or item.get("nomeDestinatario")
                or item.get("destinatario")
                or item.get("nomeParte")
            )
            polo = item.get("polo") or item.get("tipoParte") or item.get("tipo") or item.get("poloParte")
            if isinstance(name, str):
                name = name.strip()
            if isinstance(polo, str):
                polo = polo.strip()
            if name:
                normalized.append(DestinatarioResponse(nome=name, polo=polo))
    return normalized


def _normalize_advogados(raw_items: Optional[List[Any]]) -> List[AdvogadoResponse]:
    normalized: List[AdvogadoResponse] = []
    if not raw_items:
        return normalized
    for item in raw_items:
        name = None
        numero_oab = None
        uf_oab = None
        if isinstance(item, dict):
            advogado = item.get("advogado") if isinstance(item.get("advogado"), dict) else None
            source = advogado or item
            name = source.get("nome") or source.get("nomeAdvogado") or source.get("nome_advogado")
            numero_oab = source.get("numero_oab") or source.get("numeroOab") or source.get("oab") or source.get("numero")
            uf_oab = source.get("uf_oab") or source.get("ufOab") or source.get("uf")
        else:
            name = str(item) if item is not None else ""
        if isinstance(name, str):
            name = name.strip()
        if isinstance(numero_oab, str):
            numero_oab = numero_oab.strip()
        if isinstance(uf_oab, str):
            uf_oab = uf_oab.strip().upper()
        if name:
            normalized.append(AdvogadoResponse(nome=name, numero_oab=numero_oab, uf_oab=uf_oab))
    return normalized


# =============================================================================
# Watchlist (Processos Monitorados)
# =============================================================================

@router.post("/watchlist", response_model=ProcessWatchlistResponse)
async def add_to_watchlist(
    data: ProcessWatchlistCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Adicionar processo à watchlist para monitoramento automático.
    O sistema verificará diariamente por novas publicações no DJEN.
    """
    npu_clean = normalize_npu(data.npu)
    tribunal_alias = get_datajud_alias(data.tribunal_sigla)
    
    # Verificar se já existe
    existing = await db.execute(
        select(ProcessWatchlist).where(
            ProcessWatchlist.user_id == current_user.id,
            ProcessWatchlist.npu == npu_clean,
            ProcessWatchlist.is_active == True
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Processo já está na watchlist")
    
    # Calcular próximo sync
    next_sync = compute_next_sync(
        frequency=data.sync_frequency,
        sync_time=data.sync_time,
        timezone=data.sync_timezone,
        cron=data.sync_cron,
    )

    # Criar novo item
    watchlist_item = ProcessWatchlist(
        user_id=current_user.id,
        case_id=data.case_id,
        npu=npu_clean,
        npu_formatted=data.npu,
        tribunal_sigla=data.tribunal_sigla.upper(),
        tribunal_alias=tribunal_alias,
        sync_frequency=data.sync_frequency,
        sync_time=data.sync_time,
        sync_cron=data.sync_cron,
        sync_timezone=data.sync_timezone,
        next_sync_at=next_sync,
        is_active=True
    )

    db.add(watchlist_item)
    await db.commit()
    await db.refresh(watchlist_item)

    return watchlist_item


@router.get("/watchlist", response_model=List[ProcessWatchlistResponse])
async def get_watchlist(
    active_only: bool = Query(True, description="Apenas processos ativos"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Listar processos monitorados do usuário."""
    query = select(ProcessWatchlist).where(
        ProcessWatchlist.user_id == current_user.id
    )
    
    if active_only:
        query = query.where(ProcessWatchlist.is_active == True)
    
    query = query.order_by(desc(ProcessWatchlist.created_at))
    
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/watchlist/oab", response_model=OabWatchlistResponse)
async def add_oab_watchlist(
    data: OabWatchlistCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Adicionar OAB à watchlist para rastreamento diário."""
    existing = await db.execute(
        select(DjenOabWatchlist).where(
            DjenOabWatchlist.user_id == current_user.id,
            DjenOabWatchlist.numero_oab == data.numero_oab,
            DjenOabWatchlist.uf_oab == data.uf_oab,
            DjenOabWatchlist.sigla_tribunal == (data.sigla_tribunal.upper() if data.sigla_tribunal else None),
            DjenOabWatchlist.is_active == True
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="OAB já está na watchlist")

    next_sync = compute_next_sync(
        frequency=data.sync_frequency,
        sync_time=data.sync_time,
        timezone=data.sync_timezone,
        cron=data.sync_cron,
    )

    watchlist_item = DjenOabWatchlist(
        user_id=current_user.id,
        numero_oab=data.numero_oab,
        uf_oab=data.uf_oab.upper(),
        sigla_tribunal=data.sigla_tribunal.upper() if data.sigla_tribunal else None,
        meio=data.meio or "D",
        max_pages=data.max_pages or 3,
        sync_frequency=data.sync_frequency,
        sync_time=data.sync_time,
        sync_cron=data.sync_cron,
        sync_timezone=data.sync_timezone,
        next_sync_at=next_sync,
        is_active=True
    )
    db.add(watchlist_item)
    await db.commit()
    await db.refresh(watchlist_item)
    return watchlist_item


@router.get("/watchlist/oab", response_model=List[OabWatchlistResponse])
async def get_oab_watchlist(
    active_only: bool = Query(True, description="Apenas itens ativos"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Listar OABs monitoradas do usuário."""
    query = select(DjenOabWatchlist).where(
        DjenOabWatchlist.user_id == current_user.id
    )
    if active_only:
        query = query.where(DjenOabWatchlist.is_active == True)
    query = query.order_by(desc(DjenOabWatchlist.created_at))
    result = await db.execute(query)
    return result.scalars().all()


@router.delete("/watchlist/oab/{watchlist_id}")
async def remove_oab_watchlist(
    watchlist_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Remover OAB da watchlist (desativa, não deleta)."""
    result = await db.execute(
        select(DjenOabWatchlist).where(
            DjenOabWatchlist.id == watchlist_id,
            DjenOabWatchlist.user_id == current_user.id
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item não encontrado")

    item.is_active = False
    item.updated_at = datetime.utcnow()
    await db.commit()
    return {"ok": True, "message": "OAB removida da watchlist"}


@router.patch("/watchlist/{watchlist_id}", response_model=ProcessWatchlistResponse)
async def update_watchlist_schedule(
    watchlist_id: str,
    data: ProcessWatchlistUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Atualizar agendamento de sincronização de um item da watchlist."""
    result = await db.execute(
        select(ProcessWatchlist).where(
            ProcessWatchlist.id == watchlist_id,
            ProcessWatchlist.user_id == current_user.id
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item não encontrado")

    if data.sync_frequency is not None:
        item.sync_frequency = data.sync_frequency
    if data.sync_time is not None:
        item.sync_time = data.sync_time
    if data.sync_cron is not None:
        item.sync_cron = data.sync_cron
    if data.sync_timezone is not None:
        item.sync_timezone = data.sync_timezone

    item.next_sync_at = compute_next_sync(
        frequency=item.sync_frequency,
        sync_time=item.sync_time,
        timezone=item.sync_timezone,
        cron=item.sync_cron,
    )
    item.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(item)
    return item


@router.patch("/watchlist/oab/{watchlist_id}", response_model=OabWatchlistResponse)
async def update_oab_watchlist_schedule(
    watchlist_id: str,
    data: ProcessWatchlistUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Atualizar agendamento de sincronização de uma OAB na watchlist."""
    result = await db.execute(
        select(DjenOabWatchlist).where(
            DjenOabWatchlist.id == watchlist_id,
            DjenOabWatchlist.user_id == current_user.id
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item não encontrado")

    if data.sync_frequency is not None:
        item.sync_frequency = data.sync_frequency
    if data.sync_time is not None:
        item.sync_time = data.sync_time
    if data.sync_cron is not None:
        item.sync_cron = data.sync_cron
    if data.sync_timezone is not None:
        item.sync_timezone = data.sync_timezone

    item.next_sync_at = compute_next_sync(
        frequency=item.sync_frequency,
        sync_time=item.sync_time,
        timezone=item.sync_timezone,
        cron=item.sync_cron,
    )
    item.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(item)
    return item


@router.delete("/watchlist/{watchlist_id}")
async def remove_from_watchlist(
    watchlist_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Remover processo da watchlist (desativa, não deleta)."""
    result = await db.execute(
        select(ProcessWatchlist).where(
            ProcessWatchlist.id == watchlist_id,
            ProcessWatchlist.user_id == current_user.id
        )
    )
    item = result.scalar_one_or_none()
    
    if not item:
        raise HTTPException(status_code=404, detail="Item não encontrado")
    
    item.is_active = False
    item.updated_at = datetime.utcnow()
    await db.commit()
    
    return {"ok": True, "message": "Processo removido da watchlist"}


# =============================================================================
# Busca (Comunica API)
# =============================================================================

@router.post("/datajud/search", response_model=List[DatajudProcessResponse])
async def search_datajud(
    params: DatajudSearchParams,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Buscar metadados CNJ (DataJud) por NPU e tribunal.
    """
    djen_service = get_djen_service()
    if not djen_service.datajud.api_key:
        raise HTTPException(status_code=400, detail="CNJ_API_KEY not configured")

    tribunal_sigla = params.tribunal_sigla.strip().upper() if params.tribunal_sigla else None
    if not tribunal_sigla:
        tribunal_sigla = extract_tribunal_from_npu(params.npu)
    if not tribunal_sigla:
        raise HTTPException(status_code=400, detail="Tribunal nao identificado pelo NPU. Informe a sigla do tribunal.")

    results = await djen_service.fetch_metadata(params.npu, tribunal_sigla)
    return results


@router.post("/comunica/search", response_model=List[DjenIntimationSearchResponse])
async def search_comunica(
    params: DjenSearchParams,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Buscar publicações no DJEN (Comunica) por OAB, nome, processo ou tribunal.
    """
    return await _comunica_search(params, response)


@router.post("/search", response_model=List[DjenIntimationSearchResponse])
async def search_djen(
    params: DjenSearchParams,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Buscar publicações no DJEN por OAB, nome, processo ou tribunal.
    Alias para /comunica/search.
    """
    return await _comunica_search(params, response)


# =============================================================================
# Intimações Capturadas
# =============================================================================

@router.get("/intimations", response_model=List[DjenIntimationResponse])
async def get_intimations(
    case_id: Optional[str] = Query(None, description="Filtrar por caso"),
    npu: Optional[str] = Query(None, description="Filtrar por número do processo"),
    limit: int = Query(50, le=200, description="Limite de resultados"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Listar intimações capturadas do DJEN."""
    query = select(DjenIntimation).where(
        DjenIntimation.user_id == current_user.id
    )
    
    if npu:
        npu_clean = normalize_npu(npu)
        query = query.where(DjenIntimation.numero_processo == npu_clean)
    
    if case_id:
        # Buscar via watchlist associada ao case
        query = query.join(ProcessWatchlist).where(
            ProcessWatchlist.case_id == case_id
        )
    
    query = query.order_by(desc(DjenIntimation.created_at)).limit(limit)
    
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/intimations/{intimation_id}", response_model=DjenIntimationResponse)
async def get_intimation(
    intimation_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Obter detalhes de uma intimação específica."""
    result = await db.execute(
        select(DjenIntimation).where(
            DjenIntimation.id == intimation_id,
            DjenIntimation.user_id == current_user.id
        )
    )
    item = result.scalar_one_or_none()
    
    if not item:
        raise HTTPException(status_code=404, detail="Intimação não encontrada")
    
    return item


# =============================================================================
# Sincronização Manual
# =============================================================================

@router.post("/sync", response_model=SyncResult)
async def trigger_sync(
    npu: Optional[str] = Query(None, description="Sincronizar processo específico"),
    include_process: bool = Query(True, description="Incluir rastreamento por processo"),
    include_oab: bool = Query(True, description="Incluir rastreamento por OAB"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Sincronização manual do DJEN.
    Verifica DataJud por novidades e busca publicações no Comunica.
    """
    djen_service = get_djen_service()
    result = SyncResult()

    if include_process:
        if djen_service.datajud.api_key:
            result = await sync_process_watchlists(
                db=db,
                djen_service=djen_service,
                result=result,
                user_id=current_user.id,
                npu=npu
            )
        else:
            result.errors.append("CNJ_API_KEY not configured")

    if include_oab:
        result = await sync_oab_watchlists(
            db=db,
            djen_service=djen_service,
            result=result,
            user_id=current_user.id
        )

    await db.commit()
    return result
