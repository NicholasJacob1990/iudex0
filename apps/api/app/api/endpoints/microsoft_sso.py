"""Microsoft SSO endpoints for Outlook Add-in and Teams."""

import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.microsoft_auth import (
    validate_microsoft_token,
    acquire_obo_token,
    find_or_create_microsoft_user,
)
from app.core.security import create_access_token, create_refresh_token
from app.schemas.microsoft_auth import MicrosoftSSORequest, TeamsSSORequest, MicrosoftSSOResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/microsoft-sso", response_model=MicrosoftSSOResponse)
async def microsoft_sso_login(
    request: MicrosoftSSORequest,
    db: AsyncSession = Depends(get_db),
) -> MicrosoftSSOResponse:
    """Authenticate user via Microsoft NAA/SSO token."""
    try:
        claims = await validate_microsoft_token(request.microsoft_token)
    except Exception as e:
        logger.error(f"Microsoft token validation failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid Microsoft token")

    try:
        user = await find_or_create_microsoft_user(
            db=db,
            email=claims.get("preferred_username", claims.get("email", "")),
            name=claims.get("name", ""),
            oid=claims["oid"],
            tid=claims["tid"],
        )
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))

    access_token = create_access_token(data={"sub": user.id})
    refresh_token = create_refresh_token(data={"sub": user.id})

    return MicrosoftSSOResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user={
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "role": user.role.value if hasattr(user.role, 'value') else str(user.role),
            "plan": user.plan.value if hasattr(user.plan, 'value') else str(user.plan),
            "account_type": user.account_type.value if hasattr(user.account_type, 'value') else str(user.account_type),
            "organization_id": user.organization_id,
            "created_at": user.created_at.isoformat() if user.created_at else "",
        },
    )


@router.post("/teams-sso", response_model=MicrosoftSSOResponse)
async def teams_sso_login(
    request: TeamsSSORequest,
    db: AsyncSession = Depends(get_db),
) -> MicrosoftSSOResponse:
    """Authenticate user via Teams SSO token with OBO flow."""
    try:
        claims = await validate_microsoft_token(request.teams_token)
    except Exception as e:
        logger.error(f"Teams token validation failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid Teams token")

    # OBO flow for Graph access
    try:
        graph_token = await acquire_obo_token(
            assertion=request.teams_token,
            scopes=["User.Read", "Mail.Read"],
        )
        # Cache graph token in Redis
        from app.core.redis import redis_client
        if redis_client:
            await redis_client.setex(
                f"graph_token:{claims['oid']}",
                3600,  # 1 hour
                graph_token,
            )
    except Exception as e:
        logger.warning(f"OBO token failed (non-critical): {e}")

    try:
        user = await find_or_create_microsoft_user(
            db=db,
            email=claims.get("preferred_username", claims.get("email", "")),
            name=claims.get("name", ""),
            oid=claims["oid"],
            tid=claims["tid"],
        )
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))

    access_token = create_access_token(data={"sub": user.id})
    refresh_token = create_refresh_token(data={"sub": user.id})

    return MicrosoftSSOResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user={
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "role": user.role.value if hasattr(user.role, 'value') else str(user.role),
            "plan": user.plan.value if hasattr(user.plan, 'value') else str(user.plan),
            "account_type": user.account_type.value if hasattr(user.account_type, 'value') else str(user.account_type),
            "organization_id": user.organization_id,
            "created_at": user.created_at.isoformat() if user.created_at else "",
        },
    )
