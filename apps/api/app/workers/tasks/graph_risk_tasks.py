"""
Graph Risk Celery Tasks.
"""

import asyncio

from loguru import logger

from app.workers.celery_app import celery_app


@celery_app.task(name="graph_risk_cleanup")
def graph_risk_cleanup_task() -> dict:
    """
    Remove expired graph risk reports.

    Safe to run periodically (tenant-scoped via persisted rows).
    """
    try:
        from app.tasks.graph_risk_cleanup import cleanup_expired_graph_risk_reports
        return asyncio.run(cleanup_expired_graph_risk_reports())
    except Exception as e:
        logger.error("graph_risk_cleanup failed: %s", e)
        return {"checked": 0, "removed": 0, "errors": 1, "error": str(e)}

