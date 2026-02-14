"""
Tasks Celery para rastreamento do DJEN/DataJud.

A task principal `djen_scheduled_sync` roda a cada 5 minutos e sincroniza
apenas as watchlists cujo `next_sync_at` já passou, respeitando o
agendamento configurado individualmente pelo usuário.

A task legada `djen_daily_sync` continua existindo como fallback.
"""

import asyncio
from datetime import datetime

from loguru import logger
from sqlalchemy import select, or_

from app.core.database import AsyncSessionLocal
from app.models.djen import ProcessWatchlist, DjenOabWatchlist
from app.schemas.djen import SyncResult
from app.services.djen_service import get_djen_service
from app.services.djen_sync import sync_process_watchlists, sync_oab_watchlists
from app.services.djen_scheduler import compute_next_sync
from app.workers.celery_app import celery_app


@celery_app.task(name="djen_scheduled_sync")
def djen_scheduled_sync_task() -> dict:
    """
    Verifica watchlists com next_sync_at vencido e sincroniza.
    Roda a cada 5 minutos via Celery Beat.
    """
    return asyncio.run(_run_scheduled_sync())


@celery_app.task(name="djen_daily_sync")
def djen_daily_sync_task() -> dict:
    """
    Fallback: sincronização diária para watchlists sem next_sync_at.
    """
    return asyncio.run(_run_daily_sync())


async def _run_scheduled_sync() -> dict:
    """Sync only watchlists whose next_sync_at has passed."""
    now = datetime.utcnow()
    djen_service = get_djen_service()
    total_synced = 0
    total_new = 0
    errors = []

    async with AsyncSessionLocal() as db:
        try:
            # Find process watchlists due for sync
            stmt = select(ProcessWatchlist).where(
                ProcessWatchlist.is_active == True,  # noqa: E712
                ProcessWatchlist.next_sync_at != None,  # noqa: E711
                ProcessWatchlist.next_sync_at <= now,
            )
            result = await db.execute(stmt)
            due_process = result.scalars().all()

            if due_process and djen_service.datajud.api_key:
                for item in due_process:
                    try:
                        sync_result = SyncResult()
                        sync_result = await sync_process_watchlists(
                            db=db,
                            djen_service=djen_service,
                            result=sync_result,
                            user_id=item.user_id,
                            npu=item.npu,
                        )
                        total_synced += 1
                        total_new += sync_result.new_intimations

                        # Recalculate next sync
                        item.next_sync_at = compute_next_sync(
                            frequency=item.sync_frequency,
                            sync_time=item.sync_time,
                            timezone=item.sync_timezone,
                            cron=item.sync_cron,
                        )
                    except Exception as e:
                        logger.error(f"[DJEN] Process sync error for {item.npu}: {e}")
                        errors.append(f"{item.npu}: {e}")
                        # Still reschedule even on error
                        item.next_sync_at = compute_next_sync(
                            frequency=item.sync_frequency,
                            sync_time=item.sync_time,
                            timezone=item.sync_timezone,
                            cron=item.sync_cron,
                        )

            # Find OAB watchlists due for sync
            stmt_oab = select(DjenOabWatchlist).where(
                DjenOabWatchlist.is_active == True,  # noqa: E712
                DjenOabWatchlist.next_sync_at != None,  # noqa: E711
                DjenOabWatchlist.next_sync_at <= now,
            )
            result_oab = await db.execute(stmt_oab)
            due_oab = result_oab.scalars().all()

            if due_oab:
                for item in due_oab:
                    try:
                        sync_result = SyncResult()
                        sync_result = await sync_oab_watchlists(
                            db=db,
                            djen_service=djen_service,
                            result=sync_result,
                            user_id=item.user_id,
                        )
                        total_synced += 1
                        total_new += sync_result.new_intimations

                        item.next_sync_at = compute_next_sync(
                            frequency=item.sync_frequency,
                            sync_time=item.sync_time,
                            timezone=item.sync_timezone,
                            cron=item.sync_cron,
                        )
                    except Exception as e:
                        logger.error(f"[DJEN] OAB sync error for {item.numero_oab}: {e}")
                        errors.append(f"OAB {item.numero_oab}: {e}")
                        item.next_sync_at = compute_next_sync(
                            frequency=item.sync_frequency,
                            sync_time=item.sync_time,
                            timezone=item.sync_timezone,
                            cron=item.sync_cron,
                        )

            await db.commit()

            if total_synced > 0:
                logger.info(
                    f"[DJEN] Scheduled sync: {total_synced} watchlists synced, "
                    f"{total_new} new intimations"
                )

            return {
                "synced": total_synced,
                "new_intimations": total_new,
                "errors": errors,
            }

        except Exception as exc:
            await db.rollback()
            logger.error(f"[DJEN] Scheduled sync error: {exc}")
            return {"success": False, "error": str(exc)}


async def _run_daily_sync() -> dict:
    """Legacy daily sync for watchlists without next_sync_at (backward compat)."""
    result = SyncResult()
    djen_service = get_djen_service()

    async with AsyncSessionLocal() as db:
        try:
            if djen_service.datajud.api_key:
                result = await sync_process_watchlists(
                    db=db,
                    djen_service=djen_service,
                    result=result
                )
            else:
                result.errors.append("CNJ_API_KEY not configured")

            result = await sync_oab_watchlists(
                db=db,
                djen_service=djen_service,
                result=result
            )

            await db.commit()
            logger.info(f"[TASK] DJEN daily sync ok: {result.model_dump()}")
            return result.model_dump()
        except Exception as exc:
            await db.rollback()
            logger.error(f"[TASK] DJEN daily sync error: {exc}")
            return {
                "success": False,
                "error": str(exc)
            }
