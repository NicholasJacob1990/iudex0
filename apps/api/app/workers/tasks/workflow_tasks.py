"""Celery tasks for scheduled and triggered workflow execution."""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

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


@celery_app.task(
    name="run_triggered_workflow",
    bind=True,
    max_retries=2,
    soft_time_limit=1800,
    time_limit=1860,
)
def run_triggered_workflow(
    self,
    workflow_id: str,
    user_id: str,
    trigger_type: str,
    event_data: dict | None = None,
    run_id: str | None = None,
) -> dict:
    """Execute a workflow triggered by an external event and dispatch deliveries."""
    return asyncio.run(
        _run_triggered(
            workflow_id,
            user_id,
            trigger_type,
            event_data or {},
            run_id=run_id,
        )
    )


@celery_app.task(
    name="run_builtin_workflow",
    bind=True,
    max_retries=2,
    soft_time_limit=300,
    time_limit=360,
)
def run_builtin_workflow(
    self,
    run_id: str,
    workflow_id: str,
    email_data: dict,
    parameters: dict | None,
    user_id: str,
) -> dict:
    """Execute a builtin workflow (no LangGraph, direct AI calls)."""
    return asyncio.run(
        _run_builtin(run_id, workflow_id, email_data, parameters, user_id)
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
    run_id: str | None = None,
) -> dict:
    """Internal: run a single workflow."""
    from app.core.database import AsyncSessionLocal
    from app.models.workflow import Workflow, WorkflowRun, WorkflowRunStatus
    from app.services.ai.workflow_runner import WorkflowRunner

    # If a run_id is provided (e.g. Outlook add-in / email-trigger config), we update that
    # WorkflowRun instead of creating a new one, so the caller can poll status by run_id.
    if not run_id:
        import uuid
        run_id = str(uuid.uuid4())
    async with AsyncSessionLocal() as db:
        wf = await db.get(Workflow, workflow_id)
        if not wf or not wf.is_active:
            return {
                "status": "error",
                "message": f"Workflow {workflow_id} not found or inactive",
            }

        # Normalize and enrich input_data for the runner:
        # - user_id is required for credential resolution (Graph, tribunais, etc.)
        # - tenant_id enables graph tools and scoped retrieval
        # - trigger_event preserves the original event payload for the `trigger` node
        normalized_input = dict(input_data or {})
        if "trigger_event" not in normalized_input:
            normalized_input["trigger_event"] = dict(input_data or {})
        normalized_input["user_id"] = str(user_id)
        if wf.organization_id and "tenant_id" not in normalized_input:
            normalized_input["tenant_id"] = str(wf.organization_id)

        run = await db.get(WorkflowRun, run_id)
        if run:
            # Guardrail: do not allow a user to mutate someone else's run id.
            if run.user_id != str(user_id):
                return {"status": "error", "message": "Not authorized for this WorkflowRun"}

            # Idempotency: if we already reached a terminal status, don't flip it back.
            if run.status in (
                WorkflowRunStatus.COMPLETED,
                WorkflowRunStatus.ERROR,
                WorkflowRunStatus.CANCELLED,
            ):
                return {"status": run.status.value, "run_id": run_id}

            run.workflow_id = workflow_id
            run.status = WorkflowRunStatus.RUNNING
            run.input_data = normalized_input
            run.trigger_type = trigger_type
            run.started_at = datetime.now(timezone.utc)
        else:
            run = WorkflowRun(
                id=run_id,
                workflow_id=workflow_id,
                user_id=user_id,
                status=WorkflowRunStatus.RUNNING,
                input_data=normalized_input,
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
                input_data=normalized_input,
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


async def _run_triggered(
    workflow_id: str,
    user_id: str,
    trigger_type: str,
    event_data: dict,
    run_id: str | None = None,
) -> dict:
    """Run a triggered workflow and dispatch delivery nodes afterward."""
    from app.core.database import AsyncSessionLocal
    from app.models.workflow import Workflow
    from app.services.workflow_delivery import delivery_service

    # 1. Execute the workflow
    result = await _run_workflow(
        workflow_id,
        user_id,
        trigger_type=trigger_type,
        input_data=event_data,
        run_id=run_id,
    )

    if result.get("status") == "error":
        return result

    run_id = result.get("run_id", "")

    # 2. Extract delivery nodes from graph_json and dispatch each
    async with AsyncSessionLocal() as db:
        wf = await db.get(Workflow, workflow_id)
        if not wf:
            return result

        graph_json = wf.graph_json or {}
        delivery_nodes = [
            n.get("data", {})
            for n in graph_json.get("nodes", [])
            if n.get("type") == "delivery"
            or n.get("data", {}).get("type") == "delivery"
        ]

        if not delivery_nodes:
            logger.info(f"No delivery nodes in workflow {workflow_id}")
            return result

        # Get the output from the completed run
        from app.models.workflow import WorkflowRun
        run = await db.get(WorkflowRun, run_id)
        output = (run.output_data if run else {}) or {}

        delivery_results = []
        for node_data in delivery_nodes:
            delivery_type = node_data.get("delivery_type", "")
            delivery_config = node_data.get("delivery_config", {})
            delivery_config["workflow_name"] = wf.name
            delivery_config["run_id"] = run_id

            try:
                dr = await delivery_service.dispatch(
                    delivery_type=delivery_type,
                    config=delivery_config,
                    output=output,
                    user_id=user_id,
                    db=db,
                    trigger_event=event_data,
                )
                delivery_results.append(dr)
            except Exception as exc:
                logger.exception(f"Delivery {delivery_type} failed: {exc}")
                delivery_results.append(
                    {"status": "error", "delivery_type": delivery_type, "message": str(exc)}
                )

        # 3. Update run with delivery results
        if run:
            run.output_data = {
                **(run.output_data or {}),
                "delivery_results": delivery_results,
            }
            await db.commit()

    result["delivery_results"] = delivery_results
    return result


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


async def _run_builtin(
    run_id: str,
    workflow_id: str,
    email_data: dict,
    parameters: dict | None,
    user_id: str,
) -> dict:
    """Internal: execute a builtin workflow and update the WorkflowRun record."""
    from app.core.database import AsyncSessionLocal
    from app.models.workflow import WorkflowRun, WorkflowRunStatus
    from app.services.builtin_workflows import execute as execute_builtin

    async with AsyncSessionLocal() as db:
        run = await db.get(WorkflowRun, run_id)
        if not run:
            return {"status": "error", "message": f"WorkflowRun {run_id} not found"}

        run.status = WorkflowRunStatus.RUNNING
        run.started_at = datetime.now(timezone.utc)
        await db.commit()

        try:
            output = await execute_builtin(
                workflow_id=workflow_id,
                email_data=email_data,
                parameters=parameters,
                user_id=user_id,
                db=db,
            )
            run.status = WorkflowRunStatus.COMPLETED
            run.output_data = output
            run.completed_at = datetime.now(timezone.utc)
        except Exception as exc:
            logger.exception(f"Builtin workflow {workflow_id} failed: {exc}")
            run.status = WorkflowRunStatus.ERROR
            run.error_message = str(exc)
            run.completed_at = datetime.now(timezone.utc)

        await db.commit()

    return {"status": str(run.status.value), "run_id": run_id}


# ---------------------------------------------------------------------------
# Graph subscription renewal
# ---------------------------------------------------------------------------


@celery_app.task(name="renew_graph_subscriptions")
def renew_graph_subscriptions() -> dict:
    """Periodic task: renew Graph subscriptions expiring within 24h."""
    return asyncio.run(_renew_subscriptions())


async def _renew_subscriptions() -> dict:
    """Scan for expiring Graph subscriptions and renew them."""
    from sqlalchemy import select
    from app.core.database import AsyncSessionLocal
    from app.core.redis import redis_client
    from app.models.graph_subscription import GraphSubscription
    from app.models.microsoft_user import MicrosoftUser
    from app.services.graph_client import GraphClient
    from app.core.time_utils import utcnow

    if not redis_client:
        return {"status": "skipped", "reason": "redis not available"}

    threshold = utcnow() + timedelta(hours=24)
    renewed = 0
    errors = 0

    async with AsyncSessionLocal() as db:
        stmt = select(GraphSubscription).where(
            GraphSubscription.expiration_datetime < threshold
        )
        result = await db.execute(stmt)
        subs = result.scalars().all()

        for sub in subs:
            try:
                # Resolve Graph token for this user
                ms_stmt = select(MicrosoftUser).where(MicrosoftUser.user_id == sub.user_id)
                ms_result = await db.execute(ms_stmt)
                ms_user = ms_result.scalar_one_or_none()
                if not ms_user:
                    logger.warning(f"No Microsoft user for subscription {sub.subscription_id}")
                    continue

                token = await redis_client.get(f"graph_token:{ms_user.microsoft_oid}")
                if not token:
                    logger.warning(f"No Graph token for {ms_user.microsoft_oid}, skipping renewal")
                    continue

                new_expiration = utcnow() + timedelta(minutes=4230)

                async with GraphClient(token) as client:
                    await client.patch(
                        f"/subscriptions/{sub.subscription_id}",
                        json_data={
                            "expirationDateTime": new_expiration.astimezone(timezone.utc)
                            .replace(microsecond=0)
                            .isoformat()
                            .replace("+00:00", "Z")
                        },
                    )

                sub.expiration_datetime = new_expiration
                sub.renewed_at = utcnow()
                renewed += 1
            except Exception as exc:
                logger.error(f"Failed to renew subscription {sub.subscription_id}: {exc}")
                errors += 1

        await db.commit()

    return {"renewed": renewed, "errors": errors, "checked": len(subs)}
