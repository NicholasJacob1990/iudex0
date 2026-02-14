"""Celery tasks for proactive Teams Bot notifications."""

import asyncio
import logging

import httpx

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

NOTIFY_URL_BASE = "http://localhost:8000/api/teams-bot/notify"


@celery_app.task(
    name="notify_workflow_hil",
    bind=True,
    max_retries=3,
    default_retry_delay=10,
)
def notify_workflow_hil(
    self,
    user_id: str,
    workflow_name: str,
    run_id: str,
    node_name: str,
    summary: str,
) -> dict:
    """Send HIL (Human-in-the-Loop) approval request via Teams."""
    return asyncio.run(
        _send_notification(
            user_id=user_id,
            notification={
                "type": "hil",
                "workflow_name": workflow_name,
                "run_id": run_id,
                "node_name": node_name,
                "summary": summary,
            },
        )
    )


@celery_app.task(
    name="notify_workflow_completed",
    bind=True,
    max_retries=3,
    default_retry_delay=10,
)
def notify_workflow_completed(
    self,
    user_id: str,
    workflow_name: str,
    run_id: str,
    summary: str,
) -> dict:
    """Send workflow completion notification via Teams."""
    return asyncio.run(
        _send_notification(
            user_id=user_id,
            notification={
                "type": "completion",
                "workflow_name": workflow_name,
                "run_id": run_id,
                "summary": summary,
            },
        )
    )


async def _send_notification(user_id: str, notification: dict) -> dict:
    """Internal: POST notification to the Teams Bot notify endpoint."""
    url = f"{NOTIFY_URL_BASE}/{user_id}"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(url, json=notification)
            if response.status_code == 200:
                result = response.json()
                logger.info(
                    "Notification sent to user %s: %s",
                    user_id,
                    result.get("status"),
                )
                return result
            else:
                logger.error(
                    "Failed to send notification to user %s: HTTP %d",
                    user_id,
                    response.status_code,
                )
                return {"status": "error", "code": response.status_code}
    except Exception as exc:
        logger.error(
            "Error sending notification to user %s: %s",
            user_id,
            exc,
        )
        return {"status": "error", "message": str(exc)}
