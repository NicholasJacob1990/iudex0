"""Celery tasks for scheduled workflow execution."""
import asyncio
import logging
from datetime import datetime, timezone

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="run_scheduled_workflow",
    bind=True,
    max_retries=2,
    soft_time_limit=1800,
    time_limit=1860,
)
def run_scheduled_workflow(self, workflow_id: str, user_id: str) -> dict:
    """Execute a workflow as a scheduled/triggered run."""
    return asyncio.run(
        _run_workflow(workflow_id, user_id, trigger_type="scheduled")
    )


@celery_app.task(
    name="run_webhook_workflow",
    bind=True,
    max_retries=1,
    soft_time_limit=1800,
    time_limit=1860,
)
def run_webhook_workflow(
    self,
    workflow_id: str,
    user_id: str,
    input_data: dict | None = None,
) -> dict:
    """Execute a workflow triggered by webhook."""
    return asyncio.run(
        _run_workflow(
            workflow_id,
            user_id,
            trigger_type="webhook",
            input_data=input_data,
        )
    )


@celery_app.task(name="sync_workflow_schedules")
def sync_workflow_schedules() -> dict:
    """Periodic task: scan DB for enabled schedules and enqueue due workflows."""
    return asyncio.run(_sync_schedules())


async def _run_workflow(
    workflow_id: str,
    user_id: str,
    trigger_type: str = "scheduled",
    input_data: dict | None = None,
) -> dict:
    """Internal: run a single workflow."""
    import uuid

    from app.core.database import AsyncSessionLocal
    from app.models.workflow import Workflow, WorkflowRun, WorkflowRunStatus
    from app.services.ai.workflow_runner import WorkflowRunner

    run_id = str(uuid.uuid4())
    async with AsyncSessionLocal() as db:
        wf = await db.get(Workflow, workflow_id)
        if not wf or not wf.is_active:
            return {
                "status": "error",
                "message": f"Workflow {workflow_id} not found or inactive",
            }

        run = WorkflowRun(
            id=run_id,
            workflow_id=workflow_id,
            user_id=user_id,
            status=WorkflowRunStatus.RUNNING,
            input_data=input_data or {},
            trigger_type=trigger_type,
            started_at=datetime.now(timezone.utc),
        )
        db.add(run)

        # Update last_scheduled_run
        if trigger_type == "scheduled":
            wf.last_scheduled_run = datetime.now(timezone.utc)

        await db.commit()

        try:
            runner = WorkflowRunner()
            final_output = {}
            async for event in runner.run_streaming(
                graph_json=wf.graph_json,
                input_data=input_data or {},
                job_id=run_id,
                run_id=run_id,
            ):
                # Collect output from events
                evt_data = (
                    event.get("data", {}) if isinstance(event, dict) else {}
                )
                if isinstance(evt_data, dict) and evt_data.get("output"):
                    final_output = evt_data["output"]

            run.status = WorkflowRunStatus.COMPLETED
            run.output_data = final_output
            run.completed_at = datetime.now(timezone.utc)
        except Exception as exc:
            logger.exception(
                f"Scheduled workflow {workflow_id} failed: {exc}"
            )
            run.status = WorkflowRunStatus.ERROR
            run.error_message = str(exc)
            run.completed_at = datetime.now(timezone.utc)

        await db.commit()

    return {"status": str(run.status.value), "run_id": run_id}


async def _sync_schedules() -> dict:
    """Scan for enabled schedules and dispatch due workflows."""
    from croniter import croniter
    from sqlalchemy import select

    from app.core.database import AsyncSessionLocal
    from app.models.workflow import Workflow

    dispatched = 0
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Workflow).where(
                Workflow.schedule_enabled == True,  # noqa: E712
                Workflow.schedule_cron.isnot(None),
                Workflow.is_active == True,  # noqa: E712
            )
        )
        workflows = result.scalars().all()

        now = datetime.now(timezone.utc)
        for wf in workflows:
            try:
                cron = croniter(
                    wf.schedule_cron,
                    wf.last_scheduled_run or wf.created_at,
                )
                next_run = cron.get_next(datetime)
                if next_run <= now:
                    run_scheduled_workflow.delay(wf.id, wf.user_id)
                    dispatched += 1
            except Exception as exc:
                logger.warning(
                    f"Invalid cron for workflow {wf.id}: {exc}"
                )

    return {"dispatched": dispatched, "checked": len(workflows)}
