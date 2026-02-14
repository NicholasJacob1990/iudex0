"""
CRUD endpoints for email trigger configurations.

Allows users to manage rules that map incoming emails to workflow executions.
"""

import logging
from datetime import timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.config import settings
from app.core.time_utils import utcnow
from app.core.webhook_validation import generate_client_state
from app.models.user import User
from app.models.email_trigger_config import EmailTriggerConfig
from app.models.graph_subscription import GraphSubscription

logger = logging.getLogger(__name__)

router = APIRouter()

def _to_graph_datetime(dt) -> str:
    return (
        dt.astimezone(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


# --- Schemas ---

class EmailTriggerConfigCreate(BaseModel):
    name: str = Field(..., max_length=255)
    command_prefix: Optional[str] = "/iudex"
    command: Optional[str] = None
    sender_filter: Optional[str] = None
    subject_contains: Optional[str] = None
    require_attachment: bool = False
    authorized_senders: list[str] = Field(default_factory=list)
    workflow_id: str
    workflow_parameters: dict = Field(default_factory=dict)


class EmailTriggerConfigUpdate(BaseModel):
    name: Optional[str] = None
    is_active: Optional[bool] = None
    command_prefix: Optional[str] = None
    command: Optional[str] = None
    sender_filter: Optional[str] = None
    subject_contains: Optional[str] = None
    require_attachment: Optional[bool] = None
    authorized_senders: Optional[list[str]] = None
    workflow_id: Optional[str] = None
    workflow_parameters: Optional[dict] = None


class EmailTriggerConfigResponse(BaseModel):
    id: str
    name: str
    is_active: bool
    command_prefix: Optional[str]
    command: Optional[str]
    sender_filter: Optional[str]
    subject_contains: Optional[str]
    require_attachment: bool
    authorized_senders: list
    workflow_id: str
    workflow_parameters: dict
    created_at: str
    updated_at: str


def _to_response(config: EmailTriggerConfig) -> EmailTriggerConfigResponse:
    return EmailTriggerConfigResponse(
        id=config.id,
        name=config.name,
        is_active=config.is_active,
        command_prefix=config.command_prefix,
        command=config.command,
        sender_filter=config.sender_filter,
        subject_contains=config.subject_contains,
        require_attachment=config.require_attachment,
        authorized_senders=config.authorized_senders or [],
        workflow_id=config.workflow_id,
        workflow_parameters=config.workflow_parameters or {},
        created_at=config.created_at.isoformat() if config.created_at else "",
        updated_at=config.updated_at.isoformat() if config.updated_at else "",
    )


# --- Endpoints ---


@router.get("", response_model=list[EmailTriggerConfigResponse])
async def list_email_triggers(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all email trigger configs for the current user."""
    stmt = select(EmailTriggerConfig).where(
        EmailTriggerConfig.user_id == current_user.id
    ).order_by(EmailTriggerConfig.created_at.desc())
    result = await db.execute(stmt)
    configs = result.scalars().all()
    return [_to_response(c) for c in configs]


@router.post("", response_model=EmailTriggerConfigResponse, status_code=201)
async def create_email_trigger(
    request: EmailTriggerConfigCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new email trigger config."""
    config = EmailTriggerConfig(
        user_id=current_user.id,
        name=request.name,
        command_prefix=request.command_prefix,
        command=request.command,
        sender_filter=request.sender_filter,
        subject_contains=request.subject_contains,
        require_attachment=request.require_attachment,
        authorized_senders=request.authorized_senders,
        workflow_id=request.workflow_id,
        workflow_parameters=request.workflow_parameters,
    )
    db.add(config)
    await db.commit()
    await db.refresh(config)
    return _to_response(config)


@router.put("/{config_id}", response_model=EmailTriggerConfigResponse)
async def update_email_trigger(
    config_id: str,
    request: EmailTriggerConfigUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update an existing email trigger config."""
    config = await db.get(EmailTriggerConfig, config_id)
    if not config or config.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Trigger config not found")

    update_data = request.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(config, field, value)

    await db.commit()
    await db.refresh(config)
    return _to_response(config)


@router.delete("/{config_id}")
async def delete_email_trigger(
    config_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete an email trigger config."""
    config = await db.get(EmailTriggerConfig, config_id)
    if not config or config.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Trigger config not found")

    await db.delete(config)
    await db.commit()
    return {"status": "deleted"}


@router.post("/subscribe")
async def subscribe_to_mail(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Create a Graph subscription for me/messages to receive email notifications.
    If a subscription already exists for this user/resource, renews it instead.
    """
    from app.models.microsoft_user import MicrosoftUser
    from app.core.redis import redis_client
    from app.services.graph_client import GraphClient

    # Check for existing subscription
    existing_stmt = select(GraphSubscription).where(
        GraphSubscription.user_id == current_user.id,
        GraphSubscription.resource == "me/messages",
    )
    existing_result = await db.execute(existing_stmt)
    existing_sub = existing_result.scalar_one_or_none()

    # Get Graph token
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

    expiration = utcnow() + timedelta(minutes=4230)

    if existing_sub:
        # Renew existing subscription
        async with GraphClient(graph_token) as client:
            await client.patch(
                f"/subscriptions/{existing_sub.subscription_id}",
                json_data={"expirationDateTime": _to_graph_datetime(expiration)},
            )
        existing_sub.expiration_datetime = expiration
        existing_sub.renewed_at = utcnow()
        await db.commit()
        return {
            "status": "renewed",
            "subscription_id": existing_sub.subscription_id,
            "expiration": expiration.isoformat(),
        }

    # Create new subscription
    if not settings.GRAPH_WEBHOOK_SECRET:
        raise HTTPException(status_code=500, detail="GRAPH_WEBHOOK_SECRET not configured")
    client_state = generate_client_state(settings.GRAPH_WEBHOOK_SECRET)
    notification_url = settings.GRAPH_NOTIFICATION_URL or "https://api.vorbium.com.br/api/graph-webhooks/notification"
    lifecycle_url = notification_url.replace("/notification", "/lifecycle")

    subscription_data = {
        "changeType": "created",
        "notificationUrl": notification_url,
        "lifecycleNotificationUrl": lifecycle_url,
        "resource": "me/messages",
        "expirationDateTime": _to_graph_datetime(expiration),
        "clientState": client_state,
    }

    async with GraphClient(graph_token) as client:
        result = await client.post("/subscriptions", json_data=subscription_data)

    sub = GraphSubscription(
        user_id=current_user.id,
        subscription_id=result["id"],
        resource="me/messages",
        change_types="created",
        expiration_datetime=expiration,
        client_state=client_state,
        notification_url=notification_url,
    )
    db.add(sub)
    await db.commit()

    return {
        "status": "created",
        "subscription_id": result["id"],
        "expiration": expiration.isoformat(),
    }
