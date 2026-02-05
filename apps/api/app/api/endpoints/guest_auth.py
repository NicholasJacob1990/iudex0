"""
Endpoints de autenticacao para visitantes (guest sessions)

Permite acesso anonimo/temporario com permissoes limitadas (somente leitura).
"""

import logging
import secrets
import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import (
    UserOrGuest,
    create_guest_token,
    get_current_user_or_guest,
)
from app.core.time_utils import utcnow
from app.models.guest_session import GuestSession
from app.models.shared_space import InviteStatus, SharedSpace, SpaceInvite
from app.schemas.guest import (
    GuestCreateRequest,
    GuestFromShareRequest,
    GuestInfoResponse,
    GuestSessionResponse,
    GuestTokenResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# Duracao padrao da sessao guest: 24 horas
GUEST_SESSION_HOURS = 24


@router.post("/guest", response_model=GuestTokenResponse)
async def create_guest_session(
    data: GuestCreateRequest = None,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Cria uma sessao anonima de visitante com permissoes minimas (somente leitura).

    Nao requer autenticacao. O token retornado expira em 24h.
    """
    body = data or GuestCreateRequest()
    display_name = body.display_name or "Visitante"

    guest = GuestSession(
        id=str(uuid.uuid4()),
        guest_token=secrets.token_urlsafe(48),
        display_name=display_name,
        expires_at=utcnow() + timedelta(hours=GUEST_SESSION_HOURS),
        permissions={"permissions": ["read"]},
        ip_address=request.client.host if request and request.client else None,
        user_agent=request.headers.get("user-agent") if request else None,
    )
    db.add(guest)
    await db.flush()

    access_token = create_guest_token(guest)

    logger.info(f"Guest session criada: {guest.id}, name={display_name}")

    return GuestTokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=GUEST_SESSION_HOURS * 3600,
        guest=GuestSessionResponse(
            id=guest.id,
            display_name=guest.display_name,
            is_guest=True,
            expires_at=guest.expires_at,
            space_id=guest.space_id,
            permissions=guest.permissions,
            created_at=guest.created_at,
        ),
    )


@router.post("/guest/from-share/{token}", response_model=GuestTokenResponse)
async def create_guest_from_share(
    token: str,
    data: GuestFromShareRequest = None,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Cria uma sessao de visitante a partir de um link de compartilhamento (SpaceInvite).

    O guest tera acesso somente leitura ao space vinculado ao convite.
    Nao requer autenticacao previa.
    """
    body = data or GuestFromShareRequest()

    # Buscar o convite pelo token
    result = await db.execute(
        select(SpaceInvite).where(
            SpaceInvite.token == token,
            SpaceInvite.status.in_([InviteStatus.PENDING, InviteStatus.ACCEPTED]),
        )
    )
    invite = result.scalar_one_or_none()
    if not invite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Link de compartilhamento nao encontrado ou expirado",
        )

    # Verificar que o space esta ativo
    space_result = await db.execute(
        select(SharedSpace).where(
            SharedSpace.id == invite.space_id,
            SharedSpace.is_active == True,  # noqa: E712
        )
    )
    space = space_result.scalar_one_or_none()
    if not space:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Espaco compartilhado nao disponivel",
        )

    display_name = body.display_name or "Visitante"

    guest = GuestSession(
        id=str(uuid.uuid4()),
        guest_token=secrets.token_urlsafe(48),
        display_name=display_name,
        expires_at=utcnow() + timedelta(hours=GUEST_SESSION_HOURS),
        permissions={
            "permissions": ["read"],
            "spaces": [space.id],
        },
        created_from_share_token=token,
        space_id=space.id,
        ip_address=request.client.host if request and request.client else None,
        user_agent=request.headers.get("user-agent") if request else None,
    )
    db.add(guest)
    await db.flush()

    access_token = create_guest_token(guest)

    logger.info(
        f"Guest session via share: {guest.id}, space={space.id}, "
        f"invite={invite.id}, name={display_name}"
    )

    return GuestTokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=GUEST_SESSION_HOURS * 3600,
        guest=GuestSessionResponse(
            id=guest.id,
            display_name=guest.display_name,
            is_guest=True,
            expires_at=guest.expires_at,
            space_id=guest.space_id,
            permissions=guest.permissions,
            created_at=guest.created_at,
        ),
    )


@router.get("/guest/me", response_model=GuestInfoResponse)
async def get_guest_info(
    auth: UserOrGuest = Depends(get_current_user_or_guest),
):
    """
    Retorna informacoes da sessao guest atual.
    Funciona tanto para guests quanto para usuarios autenticados
    (neste caso retorna is_guest=false).
    """
    if auth.is_guest:
        guest = auth.guest
        return GuestInfoResponse(
            id=guest.id,
            display_name=guest.display_name,
            is_guest=True,
            expires_at=guest.expires_at,
            space_id=guest.space_id,
            permissions=guest.permissions,
        )

    # Usuario autenticado acessando este endpoint
    user = auth.user
    return GuestInfoResponse(
        id=user.id,
        display_name=user.name,
        is_guest=False,
        expires_at=utcnow() + timedelta(days=365),  # placeholder
        space_id=None,
        permissions={"permissions": ["read", "write", "admin"]},
    )


@router.post("/guest/invalidate")
async def invalidate_guest_session(
    auth: UserOrGuest = Depends(get_current_user_or_guest),
    db: AsyncSession = Depends(get_db),
):
    """
    Invalida (encerra) a sessao guest atual.
    """
    if not auth.is_guest:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Esta operacao e apenas para sessoes de visitante",
        )

    guest = auth.guest
    guest.is_active = False
    await db.flush()

    logger.info(f"Guest session invalidada: {guest.id}")

    return {"message": "Sessao de visitante encerrada com sucesso"}
