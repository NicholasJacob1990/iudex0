"""
Rotinas de sincronização diária do DJEN/DataJud.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.djen import ProcessWatchlist, DjenIntimation, DjenOabWatchlist
from app.schemas.djen import SyncResult
from app.services.djen_service import DjenService, normalize_npu, get_datajud_alias, extract_tribunal_from_npu
from app.core.time_utils import utcnow


def _default_oab_start_date(last_sync_date: Optional[date]) -> str:
    if last_sync_date:
        return last_sync_date.strftime("%Y-%m-%d")
    start = date.today() - timedelta(days=7)
    return start.strftime("%Y-%m-%d")


def _parse_disponibilizacao(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


async def sync_process_watchlists(
    db: AsyncSession,
    djen_service: DjenService,
    result: SyncResult,
    user_id: Optional[str] = None,
    npu: Optional[str] = None,
) -> SyncResult:
    query = select(ProcessWatchlist).where(ProcessWatchlist.is_active == True)
    if user_id:
        query = query.where(ProcessWatchlist.user_id == user_id)
    if npu:
        npu_clean = normalize_npu(npu)
        query = query.where(ProcessWatchlist.npu == npu_clean)

    watchlist_result = await db.execute(query)
    watchlist_items = watchlist_result.scalars().all()

    for item in watchlist_items:
        result.total_checked += 1

        try:
            # Publicações/Comunicacões (independente de movimentação)
            data_inicio = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
            data_fim = date.today().strftime("%Y-%m-%d")
            comunications = await djen_service.search_by_process(
                numero_processo=item.npu,
                tribunal_sigla=item.tribunal_sigla,
                data_inicio=data_inicio,
                data_fim=data_fim,
                meio="D",
                max_pages=3
            )

            for intimation_data in comunications:
                existing = await db.execute(
                    select(DjenIntimation).where(
                        DjenIntimation.user_id == item.user_id,
                        DjenIntimation.hash == intimation_data.hash
                    )
                )
                if existing.scalar_one_or_none():
                    continue

                new_intimation = DjenIntimation(
                    user_id=item.user_id,
                    watchlist_id=item.id,
                    hash=intimation_data.hash,
                    comunicacao_id=intimation_data.id,
                    numero_processo=intimation_data.numero_processo,
                    numero_processo_mascara=intimation_data.numero_processo_mascara,
                    tribunal_sigla=intimation_data.tribunal_sigla,
                    tipo_comunicacao=intimation_data.tipo_comunicacao,
                    nome_orgao=intimation_data.nome_orgao,
                    texto=intimation_data.texto,
                    data_disponibilizacao=_parse_disponibilizacao(
                        intimation_data.data_disponibilizacao
                    ),
                    meio=intimation_data.meio,
                    link=intimation_data.link,
                    tipo_documento=intimation_data.tipo_documento,
                    nome_classe=intimation_data.nome_classe,
                    numero_comunicacao=intimation_data.numero_comunicacao,
                    ativo=intimation_data.ativo
                )
                db.add(new_intimation)
                result.new_intimations += 1

            data_mov, intimations = await djen_service.check_and_fetch(
                npu=item.npu,
                tribunal_sigla=item.tribunal_sigla,
                last_seen=item.last_mov_datetime
            )

            for intimation_data in intimations:
                existing = await db.execute(
                    select(DjenIntimation).where(
                        DjenIntimation.user_id == item.user_id,
                        DjenIntimation.hash == intimation_data.hash
                    )
                )
                if existing.scalar_one_or_none():
                    continue

                new_intimation = DjenIntimation(
                    user_id=item.user_id,
                    watchlist_id=item.id,
                    hash=intimation_data.hash,
                    comunicacao_id=intimation_data.id,
                    numero_processo=intimation_data.numero_processo,
                    numero_processo_mascara=intimation_data.numero_processo_mascara,
                    tribunal_sigla=intimation_data.tribunal_sigla,
                    tipo_comunicacao=intimation_data.tipo_comunicacao,
                    nome_orgao=intimation_data.nome_orgao,
                    texto=intimation_data.texto,
                    data_disponibilizacao=_parse_disponibilizacao(
                        intimation_data.data_disponibilizacao
                    ),
                    meio=intimation_data.meio,
                    link=intimation_data.link,
                    tipo_documento=intimation_data.tipo_documento,
                    nome_classe=intimation_data.nome_classe,
                    numero_comunicacao=intimation_data.numero_comunicacao,
                    ativo=intimation_data.ativo
                )
                db.add(new_intimation)
                result.new_intimations += 1

            item.last_datajud_check = datetime.utcnow()
            if data_mov:
                item.last_mov_datetime = data_mov
            result.updated_watchlist += 1

        except Exception as e:
            logger.error(f"Erro sync processo {item.npu}: {e}")
            result.errors.append(f"Erro em {item.npu}: {str(e)}")

    return result


async def sync_oab_watchlists(
    db: AsyncSession,
    djen_service: DjenService,
    result: SyncResult,
    user_id: Optional[str] = None,
    watchlist_id: Optional[str] = None,
) -> SyncResult:
    query = select(DjenOabWatchlist).where(DjenOabWatchlist.is_active == True)
    if user_id:
        query = query.where(DjenOabWatchlist.user_id == user_id)
    if watchlist_id:
        query = query.where(DjenOabWatchlist.id == watchlist_id)

    watchlist_result = await db.execute(query)
    watchlist_items = watchlist_result.scalars().all()

    discovered_cache: set[tuple[str, str]] = set()

    for item in watchlist_items:
        result.total_checked += 1
        try:
            data_inicio = _default_oab_start_date(item.last_sync_date)
            data_fim = date.today().strftime("%Y-%m-%d")
            max_pages = item.max_pages or 3

            results = await djen_service.search_by_oab(
                numero_oab=item.numero_oab,
                uf_oab=item.uf_oab,
                tribunal_sigla=item.sigla_tribunal,
                data_inicio=data_inicio,
                data_fim=data_fim,
                meio=item.meio or "D",
                max_pages=max_pages
            )

            for intimation_data in results:
                existing = await db.execute(
                    select(DjenIntimation).where(
                        DjenIntimation.user_id == item.user_id,
                        DjenIntimation.hash == intimation_data.hash
                    )
                )
                if existing.scalar_one_or_none():
                    continue

                new_intimation = DjenIntimation(
                    user_id=item.user_id,
                    oab_watchlist_id=item.id,
                    hash=intimation_data.hash,
                    comunicacao_id=intimation_data.id,
                    numero_processo=intimation_data.numero_processo,
                    numero_processo_mascara=intimation_data.numero_processo_mascara,
                    tribunal_sigla=intimation_data.tribunal_sigla,
                    tipo_comunicacao=intimation_data.tipo_comunicacao,
                    nome_orgao=intimation_data.nome_orgao,
                    texto=intimation_data.texto,
                    data_disponibilizacao=_parse_disponibilizacao(
                        intimation_data.data_disponibilizacao
                    ),
                    meio=intimation_data.meio,
                    link=intimation_data.link,
                    tipo_documento=intimation_data.tipo_documento,
                    nome_classe=intimation_data.nome_classe,
                    numero_comunicacao=intimation_data.numero_comunicacao,
                    ativo=intimation_data.ativo
                )
                db.add(new_intimation)
                result.new_intimations += 1

                # Auto-descoberta: vincular processo à watchlist por processo
                npu_raw = intimation_data.numero_processo or intimation_data.numero_processo_mascara
                npu_clean = normalize_npu(npu_raw)
                if npu_clean:
                    cache_key = (item.user_id, npu_clean)
                    if cache_key not in discovered_cache:
                        discovered_cache.add(cache_key)
                        existing_watch = await db.execute(
                            select(ProcessWatchlist).where(
                                ProcessWatchlist.user_id == item.user_id,
                                ProcessWatchlist.npu == npu_clean
                            )
                        )
                        watch_item = existing_watch.scalar_one_or_none()
                        if watch_item:
                            if not watch_item.is_active:
                                watch_item.is_active = True
                                watch_item.updated_at = utcnow()
                        else:
                            tribunal_sigla = intimation_data.tribunal_sigla or extract_tribunal_from_npu(npu_raw or "")
                            if tribunal_sigla:
                                watch_item = ProcessWatchlist(
                                    user_id=item.user_id,
                                    case_id=None,
                                    npu=npu_clean,
                                    npu_formatted=intimation_data.numero_processo_mascara or npu_raw,
                                    tribunal_sigla=tribunal_sigla,
                                    tribunal_alias=get_datajud_alias(tribunal_sigla),
                                    is_active=True
                                )
                                db.add(watch_item)

            item.last_sync_date = date.today()
            result.updated_watchlist += 1

        except Exception as e:
            logger.error(f"Erro sync OAB {item.numero_oab}/{item.uf_oab}: {e}")
            result.errors.append(f"Erro em OAB {item.numero_oab}/{item.uf_oab}: {str(e)}")

    return result
