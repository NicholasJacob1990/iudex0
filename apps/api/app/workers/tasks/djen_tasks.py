"""
Tasks Celery para rastreamento diário do DJEN/DataJud.
"""

import asyncio
from loguru import logger

from app.core.database import AsyncSessionLocal
from app.schemas.djen import SyncResult
from app.services.djen_service import get_djen_service
from app.services.djen_sync import sync_process_watchlists, sync_oab_watchlists
from app.workers.celery_app import celery_app


@celery_app.task(name="djen_daily_sync")
def djen_daily_sync_task() -> dict:
    """
    Executa sincronização diária para todas as watchlists (processo + OAB).
    """
    return asyncio.run(_run_daily_sync())


async def _run_daily_sync() -> dict:
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
