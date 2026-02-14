"""
Graph Risk Cleanup Task — Remove expired graph risk reports.

Designed to be executed periodically (cron / Celery beat / BackgroundTasks).
Default retention is handled by expires_at (usually 30 days).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import delete, select

from app.core.database import AsyncSessionLocal
from app.models.graph_risk_report import GraphRiskReport

logger = logging.getLogger(__name__)


async def cleanup_expired_graph_risk_reports() -> dict:
    stats = {"checked": 0, "removed": 0, "errors": 0}

    async with AsyncSessionLocal() as db:
        try:
            now = datetime.now(timezone.utc)
            # Count candidates
            res = await db.execute(
                select(GraphRiskReport.id).where(GraphRiskReport.expires_at < now)
            )
            ids = [str(x) for x in res.scalars().all()]
            stats["checked"] = len(ids)

            if ids:
                await db.execute(delete(GraphRiskReport).where(GraphRiskReport.id.in_(ids)))
                stats["removed"] = len(ids)
                await db.commit()
        except Exception as e:
            stats["errors"] += 1
            logger.error("Erro no cleanup de graph risk reports: %s", e)
            await db.rollback()

    logger.info(
        "GraphRisk cleanup concluido: checked=%d, removed=%d, errors=%d",
        stats["checked"],
        stats["removed"],
        stats["errors"],
    )
    return stats

