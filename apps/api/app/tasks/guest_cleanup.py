"""
Tarefa de limpeza de sessoes guest expiradas.

Pode ser executada como background task periodica (via Celery, APScheduler,
ou chamada manual em /admin).
"""

import logging

from sqlalchemy import delete, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.time_utils import utcnow
from app.models.guest_session import GuestSession

logger = logging.getLogger(__name__)


async def cleanup_expired_guest_sessions() -> int:
    """
    Remove sessoes guest expiradas ou inativas.
    Retorna o numero de sessoes removidas.
    """
    async with AsyncSessionLocal() as db:
        try:
            now = utcnow()

            # Contar antes de deletar (para log)
            count_result = await db.execute(
                select(func.count()).select_from(GuestSession).where(
                    (GuestSession.expires_at < now) | (GuestSession.is_active == False)  # noqa: E712
                )
            )
            expired_count = count_result.scalar() or 0

            if expired_count == 0:
                logger.info("Nenhuma sessao guest expirada para limpar")
                return 0

            # Deletar sessoes expiradas
            await db.execute(
                delete(GuestSession).where(
                    (GuestSession.expires_at < now) | (GuestSession.is_active == False)  # noqa: E712
                )
            )
            await db.commit()

            logger.info(f"Limpeza de guests: {expired_count} sessoes removidas")
            return expired_count

        except Exception as e:
            logger.error(f"Erro na limpeza de guest sessions: {e}")
            await db.rollback()
            raise
