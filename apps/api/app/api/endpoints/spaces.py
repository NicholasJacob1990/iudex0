"""
Endpoints de Shared Spaces — Espaços compartilhados com clientes externos

Permite criar workspaces branded, convidar guests e compartilhar
workflows, documentos e runs com acesso controlado.
"""

import logging
import secrets
import uuid
import re
import unicodedata
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import (
    OrgContext,
    UserOrGuest,
    get_current_user,
    get_current_user_or_guest,
    get_org_context,
    require_authenticated_user,
)
from app.core.time_utils import utcnow
from app.models.shared_space import (
    InviteStatus,
    SharedSpace,
    SpaceInvite,
    SpaceResource,
    SpaceRole,
)
from app.models.user import User
from app.schemas.shared_space import (
    AddResourceRequest,
    InviteToSpaceRequest,
    JoinSpaceResponse,
    SpaceCreate,
    SpaceInviteCreatedResponse,
    SpaceInviteResponse,
    SpaceMemberResponse,
    SpaceResourceResponse,
    SpaceResponse,
    SpaceUpdate,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slugify(text: str) -> str:
    """Gera slug URL-safe a partir de texto."""
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[-\s]+", "-", text)
    return text[:180].strip("-") or "space"


async def _get_space_or_404(
    space_id: str, db: AsyncSession
) -> SharedSpace:
    result = await db.execute(
        select(SharedSpace).where(SharedSpace.id == space_id, SharedSpace.is_active == True)  # noqa: E712
    )
    space = result.scalar_one_or_none()
    if not space:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Space não encontrado")
    return space


async def _ensure_space_access(
    space: SharedSpace,
    user: User,
    db: AsyncSession,
    require_role: Optional[List[str]] = None,
) -> Optional[SpaceInvite]:
    """Verifica se o usuário é dono da org ou tem convite aceito."""
    # Membro da org dona do space? Acesso total.
    if user.organization_id and user.organization_id == space.organization_id:
        return None

    # Convite aceito?
    result = await db.execute(
        select(SpaceInvite).where(
            SpaceInvite.space_id == space.id,
            SpaceInvite.user_id == user.id,
            SpaceInvite.status == InviteStatus.ACCEPTED,
        )
    )
    invite = result.scalar_one_or_none()
    if not invite:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sem acesso a este space")

    if require_role and invite.role.value not in require_role:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permissão insuficiente")

    return invite


async def _count_members(space_id: str, db: AsyncSession) -> int:
    result = await db.execute(
        select(func.count()).select_from(SpaceInvite).where(
            SpaceInvite.space_id == space_id,
            SpaceInvite.status == InviteStatus.ACCEPTED,
        )
    )
    return result.scalar() or 0


async def _count_resources(space_id: str, db: AsyncSession) -> int:
    result = await db.execute(
        select(func.count()).select_from(SpaceResource).where(
            SpaceResource.space_id == space_id,
        )
    )
    return result.scalar() or 0


def _space_to_response(space: SharedSpace, member_count: int, resource_count: int) -> SpaceResponse:
    return SpaceResponse(
        id=space.id,
        organization_id=space.organization_id,
        name=space.name,
        slug=space.slug,
        description=space.description,
        branding=space.branding,
        member_count=member_count,
        resource_count=resource_count,
        created_by=space.created_by,
        is_active=space.is_active,
        created_at=space.created_at,
        updated_at=space.updated_at,
    )


# =============================================================================
# Space CRUD
# =============================================================================

@router.post("/", response_model=SpaceResponse, status_code=status.HTTP_201_CREATED)
async def create_space(
    data: SpaceCreate,
    ctx: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
):
    """Cria um novo shared space para a organização."""
    if not ctx.is_org_member:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Necessário pertencer a uma organização para criar spaces",
        )

    # Gerar slug único dentro da org
    base_slug = _slugify(data.name)
    slug = base_slug
    suffix = 1
    while True:
        result = await db.execute(
            select(SharedSpace).where(
                SharedSpace.organization_id == ctx.organization_id,
                SharedSpace.slug == slug,
            )
        )
        if result.scalar_one_or_none() is None:
            break
        slug = f"{base_slug}-{suffix}"
        suffix += 1

    space = SharedSpace(
        id=str(uuid.uuid4()),
        organization_id=ctx.organization_id,
        name=data.name,
        slug=slug,
        description=data.description,
        branding=data.branding or {},
        created_by=ctx.user.id,
    )
    db.add(space)
    await db.flush()

    logger.info(f"Space criado: {space.id} ({space.name}) por user={ctx.user.id}")

    return _space_to_response(space, member_count=0, resource_count=0)


@router.get("/", response_model=List[SpaceResponse])
async def list_spaces(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Lista todos os spaces que o usuário tem acesso (da org + convidado)."""
    spaces: list[SharedSpace] = []

    # Spaces da organização do usuário
    if current_user.organization_id:
        result = await db.execute(
            select(SharedSpace).where(
                SharedSpace.organization_id == current_user.organization_id,
                SharedSpace.is_active == True,  # noqa: E712
            ).order_by(SharedSpace.created_at.desc())
        )
        spaces.extend(result.scalars().all())

    # Spaces onde foi convidado
    result = await db.execute(
        select(SharedSpace)
        .join(SpaceInvite, SpaceInvite.space_id == SharedSpace.id)
        .where(
            SpaceInvite.user_id == current_user.id,
            SpaceInvite.status == InviteStatus.ACCEPTED,
            SharedSpace.is_active == True,  # noqa: E712
        )
        .order_by(SharedSpace.created_at.desc())
    )
    invited_spaces = result.scalars().all()

    # Mesclar sem duplicatas
    seen_ids = {s.id for s in spaces}
    for s in invited_spaces:
        if s.id not in seen_ids:
            spaces.append(s)
            seen_ids.add(s.id)

    # Montar respostas com contagens
    responses = []
    for space in spaces:
        mc = await _count_members(space.id, db)
        rc = await _count_resources(space.id, db)
        responses.append(_space_to_response(space, mc, rc))

    return responses


@router.get("/{space_id}", response_model=SpaceResponse)
async def get_space(
    space_id: str,
    auth: UserOrGuest = Depends(get_current_user_or_guest),
    db: AsyncSession = Depends(get_db),
):
    """Detalhes de um space. Aceita usuarios autenticados e visitantes."""
    space = await _get_space_or_404(space_id, db)

    if auth.is_guest:
        # Guest so pode ver spaces vinculados a sua sessao
        guest = auth.guest
        if guest.space_id != space.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Sem acesso a este space",
            )
    else:
        await _ensure_space_access(space, auth.user, db)

    mc = await _count_members(space.id, db)
    rc = await _count_resources(space.id, db)
    return _space_to_response(space, mc, rc)


@router.put("/{space_id}", response_model=SpaceResponse)
async def update_space(
    space_id: str,
    data: SpaceUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Atualiza nome, descrição ou branding do space."""
    space = await _get_space_or_404(space_id, db)
    await _ensure_space_access(space, current_user, db, require_role=["admin"])

    # Membros da org podem editar se são donos
    update_data = data.model_dump(exclude_unset=True)
    for field_name, value in update_data.items():
        setattr(space, field_name, value)

    await db.flush()

    mc = await _count_members(space.id, db)
    rc = await _count_resources(space.id, db)
    return _space_to_response(space, mc, rc)


@router.delete("/{space_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_space(
    space_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Desativa um shared space (soft delete)."""
    space = await _get_space_or_404(space_id, db)

    # Somente membros da org dona podem deletar
    if not current_user.organization_id or current_user.organization_id != space.organization_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Somente membros da organização podem desativar o space")

    space.is_active = False
    await db.flush()

    logger.info(f"Space desativado: {space.id} por user={current_user.id}")


# =============================================================================
# Members / Invites
# =============================================================================

@router.post("/{space_id}/invite", response_model=SpaceInviteCreatedResponse, status_code=status.HTTP_201_CREATED)
async def invite_to_space(
    space_id: str,
    data: InviteToSpaceRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Convida alguém (interno ou externo) para o space."""
    space = await _get_space_or_404(space_id, db)
    await _ensure_space_access(space, current_user, db, require_role=["admin"])

    # Verificar convite duplicado pendente
    existing = await db.execute(
        select(SpaceInvite).where(
            SpaceInvite.space_id == space_id,
            SpaceInvite.email == data.email,
            SpaceInvite.status.in_([InviteStatus.PENDING, InviteStatus.ACCEPTED]),
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Já existe um convite ativo para este email",
        )

    token = secrets.token_urlsafe(48)
    invite = SpaceInvite(
        id=str(uuid.uuid4()),
        space_id=space_id,
        email=data.email,
        role=SpaceRole(data.role),
        token=token,
        message=data.message,
        invited_by=current_user.id,
    )
    db.add(invite)
    await db.flush()

    logger.info(f"Convite criado: space={space_id}, email={data.email}, role={data.role}")

    return SpaceInviteCreatedResponse(
        id=invite.id,
        space_id=invite.space_id,
        email=invite.email,
        role=invite.role.value,
        status=invite.status.value,
        token=invite.token,
        message=invite.message,
        invited_by=invite.invited_by,
        user_id=invite.user_id,
        accepted_at=invite.accepted_at,
        created_at=invite.created_at,
    )


@router.get("/{space_id}/members", response_model=List[SpaceMemberResponse])
async def list_space_members(
    space_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Lista todos os membros e convites pendentes do space."""
    space = await _get_space_or_404(space_id, db)
    await _ensure_space_access(space, current_user, db)

    result = await db.execute(
        select(SpaceInvite).where(
            SpaceInvite.space_id == space_id,
            SpaceInvite.status.in_([InviteStatus.PENDING, InviteStatus.ACCEPTED]),
        ).order_by(SpaceInvite.created_at)
    )
    invites = result.scalars().all()

    members = []
    for inv in invites:
        user_name = None
        if inv.user_id:
            user_result = await db.execute(select(User.name).where(User.id == inv.user_id))
            user_name = user_result.scalar_one_or_none()

        members.append(SpaceMemberResponse(
            email=inv.email,
            role=inv.role.value,
            status=inv.status.value,
            user_id=inv.user_id,
            user_name=user_name,
            accepted_at=inv.accepted_at,
            created_at=inv.created_at,
        ))

    return members


@router.delete("/{space_id}/members/{member_email}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    space_id: str,
    member_email: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove ou revoga acesso de um membro."""
    space = await _get_space_or_404(space_id, db)
    await _ensure_space_access(space, current_user, db, require_role=["admin"])

    result = await db.execute(
        select(SpaceInvite).where(
            SpaceInvite.space_id == space_id,
            SpaceInvite.email == member_email,
            SpaceInvite.status.in_([InviteStatus.PENDING, InviteStatus.ACCEPTED]),
        )
    )
    invite = result.scalar_one_or_none()
    if not invite:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Membro não encontrado")

    invite.status = InviteStatus.REVOKED
    await db.flush()

    logger.info(f"Membro removido: space={space_id}, email={member_email}")


@router.post("/join/{token}", response_model=JoinSpaceResponse)
async def join_space(
    token: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Aceita um convite para entrar em um space."""
    result = await db.execute(
        select(SpaceInvite).where(
            SpaceInvite.token == token,
            SpaceInvite.status == InviteStatus.PENDING,
        )
    )
    invite = result.scalar_one_or_none()
    if not invite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Convite não encontrado ou já utilizado",
        )

    # Verificar que o email corresponde (ou permitir qualquer usuário autenticado)
    if invite.email.lower() != current_user.email.lower():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Este convite foi enviado para outro email",
        )

    invite.status = InviteStatus.ACCEPTED
    invite.user_id = current_user.id
    invite.accepted_at = utcnow()
    await db.flush()

    # Buscar nome do space
    space_result = await db.execute(
        select(SharedSpace).where(SharedSpace.id == invite.space_id)
    )
    space = space_result.scalar_one()

    logger.info(f"Convite aceito: space={invite.space_id}, user={current_user.id}")

    return JoinSpaceResponse(
        space_id=space.id,
        space_name=space.name,
        role=invite.role.value,
        message=f"Bem-vindo ao space '{space.name}'!",
    )


# =============================================================================
# Resources
# =============================================================================

@router.post("/{space_id}/resources", response_model=SpaceResourceResponse, status_code=status.HTTP_201_CREATED)
async def add_resource(
    space_id: str,
    data: AddResourceRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Adiciona um workflow, documento ou run ao space."""
    space = await _get_space_or_404(space_id, db)
    await _ensure_space_access(space, current_user, db, require_role=["admin", "contributor"])

    # Verificar duplicata
    existing = await db.execute(
        select(SpaceResource).where(
            SpaceResource.space_id == space_id,
            SpaceResource.resource_type == data.resource_type,
            SpaceResource.resource_id == data.resource_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Recurso já adicionado a este space",
        )

    resource = SpaceResource(
        id=str(uuid.uuid4()),
        space_id=space_id,
        resource_type=data.resource_type,
        resource_id=data.resource_id,
        resource_name=data.resource_name,
        added_by=current_user.id,
    )
    db.add(resource)
    await db.flush()

    logger.info(f"Recurso adicionado: space={space_id}, type={data.resource_type}, id={data.resource_id}")

    return SpaceResourceResponse(
        id=resource.id,
        space_id=resource.space_id,
        resource_type=resource.resource_type,
        resource_id=resource.resource_id,
        resource_name=resource.resource_name,
        added_by=resource.added_by,
        added_at=resource.added_at,
    )


@router.get("/{space_id}/resources", response_model=List[SpaceResourceResponse])
async def list_resources(
    space_id: str,
    resource_type: Optional[str] = Query(None, pattern=r"^(workflow|document|run|folder)$"),
    auth: UserOrGuest = Depends(get_current_user_or_guest),
    db: AsyncSession = Depends(get_db),
):
    """Lista todos os recursos no space. Aceita visitantes (somente leitura)."""
    space = await _get_space_or_404(space_id, db)

    if auth.is_guest:
        guest = auth.guest
        if guest.space_id != space.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Sem acesso a este space",
            )
    else:
        await _ensure_space_access(space, auth.user, db)

    query = select(SpaceResource).where(SpaceResource.space_id == space_id)
    if resource_type:
        query = query.where(SpaceResource.resource_type == resource_type)
    query = query.order_by(SpaceResource.added_at.desc())

    result = await db.execute(query)
    resources = result.scalars().all()

    return [
        SpaceResourceResponse(
            id=r.id,
            space_id=r.space_id,
            resource_type=r.resource_type,
            resource_id=r.resource_id,
            resource_name=r.resource_name,
            added_by=r.added_by,
            added_at=r.added_at,
        )
        for r in resources
    ]


@router.delete("/{space_id}/resources/{resource_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_resource(
    space_id: str,
    resource_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove um recurso do space."""
    space = await _get_space_or_404(space_id, db)
    await _ensure_space_access(space, current_user, db, require_role=["admin", "contributor"])

    result = await db.execute(
        select(SpaceResource).where(
            SpaceResource.id == resource_id,
            SpaceResource.space_id == space_id,
        )
    )
    resource = result.scalar_one_or_none()
    if not resource:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recurso não encontrado")

    await db.delete(resource)
    await db.flush()

    logger.info(f"Recurso removido: space={space_id}, resource={resource_id}")
