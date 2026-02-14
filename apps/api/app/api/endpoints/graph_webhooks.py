"""
Graph API webhook endpoints for change notifications.

Handles:
- Subscription validation (token echo)
- Change notification processing
- Subscription CRUD (create, renew, delete)
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete as sa_delete

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.config import settings
from app.core.webhook_validation import validate_client_state, generate_client_state
from app.core.time_utils import utcnow
from app.models.user import User
from app.models.graph_subscription import GraphSubscription

logger = logging.getLogger(__name__)

router = APIRouter()

def _to_graph_datetime(dt: datetime) -> str:
    """Microsoft Graph expects RFC3339 UTC timestamps like 2026-02-10T12:34:56Z."""
    return (
        dt.astimezone(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


# --- Schemas ---

class CreateSubscriptionRequest(BaseModel):
    resource: str = Field(..., description="Graph resource path, e.g. 'me/messages'")
    change_types: str = Field(default="created,updated")
    expiration_minutes: int = Field(default=4230, le=4230)


class SubscriptionResponse(BaseModel):
    id: str
    subscription_id: str
    resource: str
    expiration_datetime: str
    status: str = "active"


# --- Notification Endpoint ---

@router.post("/notification")
async def handle_graph_notification(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Receive change notifications from Microsoft Graph.
    Validates clientState and dispatches to handlers.
    """
    # Validation token (subscription setup handshake)
    validation_token = request.query_params.get("validationToken")
    if validation_token:
        return PlainTextResponse(validation_token)

    body = await request.json()

    for notification in body.get("value", []):
        # Validate clientState (HMAC)
        client_state = notification.get("clientState", "")
        if not validate_client_state(client_state):
            logger.warning("Invalid clientState in Graph notification")
            continue

        # Dispatch to appropriate handler
        resource = notification.get("resource", "")
        change_type = notification.get("changeType", "")
        resource_data = notification.get("resourceData", {})

        logger.info(
            "graph.webhook.notification",
            extra={
                "resource": resource,
                "change_type": change_type,
                "resource_id": resource_data.get("id", ""),
            },
        )

        try:
            if "messages" in resource:
                await _handle_mail_notification(notification, db)
            elif "events" in resource:
                await _handle_calendar_notification(notification, db)
        except Exception as e:
            logger.error(f"Notification handler error: {e}")

    return {"status": "ok"}


@router.post("/lifecycle")
async def handle_lifecycle_notification(request: Request):
    """Handle lifecycle notifications (subscriptionRemoved, reauthorizationRequired, missed)."""
    body = await request.json()

    for notification in body.get("value", []):
        lifecycle_event = notification.get("lifecycleEvent", "")
        subscription_id = notification.get("subscriptionId", "")

        logger.info(f"Graph lifecycle event: {lifecycle_event} for subscription {subscription_id}")

        if lifecycle_event == "reauthorizationRequired":
            from app.workers.tasks.workflow_tasks import renew_graph_subscriptions
            renew_graph_subscriptions.delay()
            logger.info(f"Queued subscription renewal for {subscription_id}")
        elif lifecycle_event == "subscriptionRemoved":
            # Mark subscription as removed in DB
            from app.core.database import AsyncSessionLocal
            async with AsyncSessionLocal() as session:
                sub_stmt = select(GraphSubscription).where(
                    GraphSubscription.subscription_id == subscription_id
                )
                sub_result = await session.execute(sub_stmt)
                sub = sub_result.scalar_one_or_none()
                if sub:
                    await session.execute(
                        sa_delete(GraphSubscription).where(GraphSubscription.id == sub.id)
                    )
                    await session.commit()
            logger.warning(f"Subscription {subscription_id} removed by Graph, deleted from DB")
        elif lifecycle_event == "missed":
            logger.warning(
                f"Missed notifications for subscription {subscription_id}. "
                "Consider delta query to catch up."
            )

    return {"status": "ok"}


# --- Subscription CRUD ---

@router.post("/subscriptions", response_model=SubscriptionResponse)
async def create_subscription(
    request: CreateSubscriptionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new Graph webhook subscription."""
    from app.services.graph_client import GraphClient
    from app.core.redis import redis_client

    # Get user's Graph token from Redis
    from app.models.microsoft_user import MicrosoftUser
    ms_stmt = select(MicrosoftUser).where(MicrosoftUser.user_id == current_user.id)
    ms_result = await db.execute(ms_stmt)
    ms_user = ms_result.scalar_one_or_none()

    if not ms_user:
        raise HTTPException(status_code=400, detail="No Microsoft account linked")

    if not redis_client:
        raise HTTPException(status_code=503, detail="Redis not available")

    graph_token = await redis_client.get(f"graph_token:{ms_user.microsoft_oid}")
    if not graph_token:
        raise HTTPException(status_code=401, detail="Graph token expired, re-authenticate")

    if not settings.GRAPH_WEBHOOK_SECRET:
        raise HTTPException(status_code=500, detail="GRAPH_WEBHOOK_SECRET not configured")

    client_state = generate_client_state(settings.GRAPH_WEBHOOK_SECRET)
    expiration = utcnow() + timedelta(minutes=request.expiration_minutes)

    notification_url = settings.GRAPH_NOTIFICATION_URL or "https://api.vorbium.com.br/api/graph-webhooks/notification"
    lifecycle_url = notification_url.replace("/notification", "/lifecycle")

    subscription_data = {
        "changeType": request.change_types,
        "notificationUrl": notification_url,
        "lifecycleNotificationUrl": lifecycle_url,
        "resource": request.resource,
        "expirationDateTime": _to_graph_datetime(expiration),
        "clientState": client_state,
    }

    async with GraphClient(graph_token) as client:
        result = await client.post("/subscriptions", json_data=subscription_data)

    # Save to DB
    sub = GraphSubscription(
        user_id=current_user.id,
        subscription_id=result["id"],
        resource=request.resource,
        change_types=request.change_types,
        expiration_datetime=expiration,
        client_state=client_state,
        notification_url=notification_url,
    )
    db.add(sub)
    await db.commit()
    await db.refresh(sub)

    return SubscriptionResponse(
        id=sub.id,
        subscription_id=sub.subscription_id,
        resource=sub.resource,
        expiration_datetime=expiration.isoformat(),
    )


@router.post("/subscriptions/{subscription_id}/renew")
async def renew_subscription(
    subscription_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Renew an existing subscription."""
    stmt = select(GraphSubscription).where(
        GraphSubscription.subscription_id == subscription_id,
        GraphSubscription.user_id == current_user.id,
    )
    result = await db.execute(stmt)
    sub = result.scalar_one_or_none()

    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")

    new_expiration = utcnow() + timedelta(minutes=4230)

    from app.models.microsoft_user import MicrosoftUser
    from app.core.redis import redis_client

    ms_stmt = select(MicrosoftUser).where(MicrosoftUser.user_id == current_user.id)
    ms_result = await db.execute(ms_stmt)
    ms_user = ms_result.scalar_one_or_none()

    graph_token = await redis_client.get(f"graph_token:{ms_user.microsoft_oid}") if ms_user and redis_client else None
    if not graph_token:
        raise HTTPException(status_code=401, detail="Graph token expired")

    from app.services.graph_client import GraphClient
    async with GraphClient(graph_token) as client:
        await client.patch(
            f"/subscriptions/{subscription_id}",
            json_data={"expirationDateTime": _to_graph_datetime(new_expiration)},
        )

    sub.expiration_datetime = new_expiration
    sub.renewed_at = utcnow()
    await db.commit()

    return {"status": "renewed", "new_expiration": new_expiration.isoformat()}


@router.delete("/subscriptions/{subscription_id}")
async def delete_subscription(
    subscription_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a subscription."""
    stmt = select(GraphSubscription).where(
        GraphSubscription.subscription_id == subscription_id,
        GraphSubscription.user_id == current_user.id,
    )
    result = await db.execute(stmt)
    sub = result.scalar_one_or_none()

    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")

    # Delete from Graph
    try:
        from app.models.microsoft_user import MicrosoftUser
        from app.core.redis import redis_client
        from app.services.graph_client import GraphClient

        ms_stmt = select(MicrosoftUser).where(MicrosoftUser.user_id == current_user.id)
        ms_result = await db.execute(ms_stmt)
        ms_user = ms_result.scalar_one_or_none()

        graph_token = await redis_client.get(f"graph_token:{ms_user.microsoft_oid}") if ms_user and redis_client else None
        if graph_token:
            async with GraphClient(graph_token) as client:
                await client.delete(f"/subscriptions/{subscription_id}")
    except Exception as e:
        logger.warning(f"Failed to delete Graph subscription: {e}")

    # Delete from DB
    await db.execute(
        sa_delete(GraphSubscription).where(GraphSubscription.id == sub.id)
    )
    await db.commit()

    return {"status": "deleted"}


# --- Internal Handlers ---

async def _handle_mail_notification(notification: dict, db: AsyncSession):
    """Process mail change notification — fetch email and dispatch to TriggerRegistry."""
    resource_data = notification.get("resourceData", {})
    message_id = resource_data.get("id", "")
    subscription_id = notification.get("subscriptionId", "")

    logger.info(f"Mail notification: message={message_id}, subscription={subscription_id}")

    # 1. Find the GraphSubscription → user_id
    stmt = select(GraphSubscription).where(
        GraphSubscription.subscription_id == subscription_id
    )
    result = await db.execute(stmt)
    sub = result.scalar_one_or_none()
    if not sub:
        logger.warning(f"No subscription found for {subscription_id}")
        return

    user_id = sub.user_id

    # 2. Fetch email details via Graph API
    try:
        from app.services.graph_email import get_attachments, get_email_details

        email = await get_email_details(user_id, message_id, db)
        if not email:
            logger.warning(f"Could not fetch email {message_id}")
            return

        # 3. Fetch attachments if present.
        # We include metadata only by default (no base64 blobs) and forward on-demand in Delivery.
        attachments: list[dict] = []
        if email.get("hasAttachments", False):
            attachments = await get_attachments(user_id, message_id, db, include_content_bytes_up_to_mb=0.0)

        # 4. Match EmailTriggerConfig rules (per-user) and dispatch configured workflows.
        # If no config matches, fallback to legacy TriggerRegistry matching against workflow graphs.
        from app.models.email_trigger_config import EmailTriggerConfig
        from app.services.workflow_triggers import trigger_registry, parse_email_command

        subject = email.get("subject", "") or ""
        subject_l = subject.lower()
        sender_email = (
            email.get("from", {}).get("emailAddress", {}).get("address", "") or ""
        ).lower()
        has_attachments = bool(email.get("hasAttachments", False))

        # Recipients (best-effort, used by builtin workflows)
        to_recipients = [
            r.get("emailAddress", {}).get("address", "")
            for r in (email.get("toRecipients", []) or [])
        ]
        cc_recipients = [
            r.get("emailAddress", {}).get("address", "")
            for r in (email.get("ccRecipients", []) or [])
        ]
        recipients = [r for r in (to_recipients + cc_recipients) if r]

        body_html = email.get("body", {}).get("content", "") or ""
        body_preview = email.get("bodyPreview", "") or ""

        # This structure is used for builtin workflows and is embedded into event_data for UUID workflows.
        email_data = {
            "message_id": message_id,
            "internet_message_id": email.get("internetMessageId", ""),
            "subject": subject,
            "body": body_html or body_preview,
            "body_preview": body_preview,
            "body_html": body_html,
            "sender": email.get("from", {}).get("emailAddress", {}).get("address", "") or "",
            "recipients": recipients,
            "date": email.get("receivedDateTime", ""),
            "has_attachment": has_attachments,
            "attachments": attachments,
        }

        cfg_stmt = select(EmailTriggerConfig).where(
            EmailTriggerConfig.user_id == user_id,
            EmailTriggerConfig.is_active == True,  # noqa: E712
        )
        cfg_res = await db.execute(cfg_stmt)
        configs = cfg_res.scalars().all()

        # Global allowlist behavior (security): if the user has any active configs with
        # authorized_senders, only those senders can trigger anything (including legacy fallback).
        union_allowed = {
            s.lower()
            for cfg in configs
            for s in (cfg.authorized_senders or [])
        }
        if union_allowed and sender_email and sender_email not in union_allowed:
            logger.info(
                f"Email from {sender_email} not in authorized_senders for user {user_id}, ignoring"
            )
            return

        matched: list[tuple[EmailTriggerConfig, dict]] = []
        for cfg in configs:
            # Per-config sender allowlist
            if cfg.authorized_senders:
                allowed = {s.lower() for s in (cfg.authorized_senders or [])}
                if sender_email and sender_email not in allowed:
                    continue

            if cfg.sender_filter and cfg.sender_filter.lower() not in sender_email:
                continue
            if cfg.subject_contains and cfg.subject_contains.lower() not in subject_l:
                continue
            if cfg.require_attachment and not has_attachments:
                continue

            parsed = {}
            if cfg.command_prefix:
                parsed = (
                    parse_email_command(subject, custom_prefix=cfg.command_prefix)
                    or {}
                )
                # If command_prefix is configured, require it to be present.
                if not parsed:
                    continue

            if cfg.command:
                if not parsed:
                    parsed = (
                        parse_email_command(subject, custom_prefix=cfg.command_prefix)
                        or {}
                    )
                if parsed.get("command", "").lower() != (cfg.command or "").lower():
                    continue

            matched.append((cfg, parsed))

        if matched:
            import uuid

            from app.models.workflow import Workflow, WorkflowRun, WorkflowRunStatus
            from app.models.organization import OrganizationMember
            from app.services.builtin_workflows import is_builtin
            from app.workers.tasks.workflow_tasks import (
                run_builtin_workflow,
                run_triggered_workflow,
            )

            now = utcnow()
            enqueues: list[tuple[str, str, dict]] = []

            for cfg, parsed in matched:
                # Merge parameters: defaults from config + derived args from parsed command
                params = dict(cfg.workflow_parameters or {})
                if parsed.get("command_args") and "command_args" not in params:
                    params["command_args"] = parsed.get("command_args")

                target_id = cfg.workflow_id

                # Builtin workflows (slug)
                if is_builtin(target_id):
                    run_id = str(uuid.uuid4())
                    run = WorkflowRun(
                        id=run_id,
                        workflow_id=target_id,
                        user_id=user_id,
                        status=WorkflowRunStatus.PENDING,
                        input_data={
                            "email_data": email_data,
                            "parameters": params,
                            "trigger_config_id": cfg.id,
                            "parsed_command": parsed,
                        },
                        trigger_type="outlook_email",
                        created_at=now,
                    )
                    db.add(run)
                    enqueues.append(
                        (
                            "builtin",
                            run_id,
                            {
                                "workflow_id": target_id,
                                "email_data": email_data,
                                "parameters": params,
                            },
                        )
                    )
                    continue

                # UUID workflows — validate access (owner or active org member)
                wf = await db.get(Workflow, target_id)
                if not wf or not wf.is_active:
                    logger.warning(
                        f"EmailTriggerConfig {cfg.id}: workflow {target_id} not found/inactive"
                    )
                    continue

                if wf.user_id != str(user_id):
                    if not wf.organization_id:
                        logger.warning(
                            f"EmailTriggerConfig {cfg.id}: not authorized for workflow {target_id}"
                        )
                        continue
                    mem_stmt = select(OrganizationMember).where(
                        OrganizationMember.organization_id == wf.organization_id,
                        OrganizationMember.user_id == user_id,
                        OrganizationMember.is_active == True,  # noqa: E712
                    )
                    mem_res = await db.execute(mem_stmt)
                    if not mem_res.scalar_one_or_none():
                        logger.warning(
                            f"EmailTriggerConfig {cfg.id}: not authorized for workflow {target_id}"
                        )
                        continue

                run_id = str(uuid.uuid4())
                run = WorkflowRun(
                    id=run_id,
                    workflow_id=target_id,
                    user_id=user_id,
                    status=WorkflowRunStatus.PENDING,
                    input_data={
                        "email_data": email_data,
                        "parameters": params,
                        "trigger_config_id": cfg.id,
                        "parsed_command": parsed,
                    },
                    trigger_type="outlook_email",
                    created_at=now,
                )
                db.add(run)

                # For UUID workflows, event_data must expose the email fields at top-level.
                event_data = {
                    **email_data,
                    "parameters": params,
                    "parsed_command": parsed,
                    "trigger_config_id": cfg.id,
                }
                enqueues.append(
                    (
                        "uuid",
                        run_id,
                        {
                            "workflow_id": target_id,
                            "event_data": event_data,
                        },
                    )
                )

            await db.commit()

            for kind, run_id, payload in enqueues:
                try:
                    if kind == "builtin":
                        run_builtin_workflow.delay(
                            run_id=run_id,
                            workflow_id=payload["workflow_id"],
                            email_data=payload["email_data"],
                            parameters=payload["parameters"],
                            user_id=user_id,
                        )
                    else:
                        run_triggered_workflow.delay(
                            workflow_id=payload["workflow_id"],
                            user_id=user_id,
                            trigger_type="outlook_email",
                            event_data=payload["event_data"],
                            run_id=run_id,
                        )
                except Exception as e:
                    logger.error(
                        f"Failed to enqueue email-trigger workflow run {run_id}: {e}"
                    )

            return

        # 5. Legacy fallback: dispatch via TriggerRegistry (workflow graph trigger nodes)
        parsed_command = parse_email_command(subject) or {}

        event_data = {
            "message_id": message_id,
            "internet_message_id": email.get("internetMessageId", ""),
            "subject": subject,
            "body": body_preview,
            "body_html": body_html,
            "sender": email.get("from", {}).get("emailAddress", {}).get("address", ""),
            "has_attachment": has_attachments,
            "received_at": email.get("receivedDateTime", ""),
            "attachments": attachments,
            "parsed_command": parsed_command,
        }

        if parsed_command:
            logger.info(
                f"Email command parsed: command={parsed_command.get('command')}, "
                f"args={parsed_command.get('command_args', '')[:80]}"
            )

        await trigger_registry.dispatch_event(
            trigger_type="outlook_email",
            event_data=event_data,
            user_id=user_id,
            db=db,
        )
    except Exception as e:
        logger.error(f"Mail trigger dispatch failed: {e}")


async def _handle_calendar_notification(notification: dict, db: AsyncSession):
    """Process calendar change notification."""
    resource_data = notification.get("resourceData", {})
    event_id = resource_data.get("id", "")

    logger.info(f"Calendar notification: event={event_id}")
    # Calendar notifications are informational — no trigger dispatch needed
