"""
Endpoints de Organização, Membros e Equipes
"""

import logging
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import (
    OrgContext,
    get_current_user,
    get_org_context,
    require_org_role,
)
from app.models.organization import (
    Organization,
    OrganizationMember,
    OrgRole,
    Team,
    TeamMember,
)
from app.models.user import User
from app.schemas.organization import (
    InviteRequest,
    MemberResponse,
    OrgCreate,
    OrgResponse,
    OrgUpdate,
    RoleUpdate,
    TeamCreate,
    TeamMemberAdd,
    TeamResponse,
    TeamUpdate,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# =============================================================================
# Organization CRUD
# =============================================================================

@router.post("/", response_model=OrgResponse, status_code=status.HTTP_201_CREATED)
async def create_organization(
    data: OrgCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Cria organização e adiciona o usuário como admin."""
    # Verificar se user já tem org
    if current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Usuário já pertence a uma organização",
        )

    # Gerar slug único
    base_slug = Organization.generate_slug(data.name)
    slug = base_slug
    suffix = 1
    while True:
        result = await db.execute(
            select(Organization).where(Organization.slug == slug)
        )
        if result.scalar_one_or_none() is None:
            break
        slug = f"{base_slug}-{suffix}"
        suffix += 1

    org = Organization(
        id=str(uuid.uuid4()),
        name=data.name,
        slug=slug,
        cnpj=data.cnpj,
        oab_section=data.oab_section,
    )
    db.add(org)

    # Adicionar user como admin
    member = OrganizationMember(
        id=str(uuid.uuid4()),
        organization_id=org.id,
        user_id=current_user.id,
        role=OrgRole.ADMIN,
    )
    db.add(member)

    # Atualizar user.organization_id
    current_user.organization_id = org.id
    db.add(current_user)

    await db.commit()
    await db.refresh(org)

    return OrgResponse(
        id=org.id,
        name=org.name,
        slug=org.slug,
        cnpj=org.cnpj,
        oab_section=org.oab_section,
        plan=org.plan,
        max_members=org.max_members,
        member_count=1,
        is_active=org.is_active,
        created_at=org.created_at,
        updated_at=org.updated_at,
    )


@router.get("/current", response_model=OrgResponse)
async def get_current_org(
    ctx: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
):
    """Retorna detalhes da organização ativa do usuário."""
    if not ctx.is_org_member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuário não pertence a nenhuma organização",
        )

    result = await db.execute(
        select(Organization).where(Organization.id == ctx.organization_id)
    )
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organização não encontrada")

    # Contar membros ativos
    count_result = await db.execute(
        select(func.count()).select_from(OrganizationMember).where(
            OrganizationMember.organization_id == org.id,
            OrganizationMember.is_active == True,  # noqa: E712
        )
    )
    member_count = count_result.scalar() or 0

    return OrgResponse(
        id=org.id,
        name=org.name,
        slug=org.slug,
        cnpj=org.cnpj,
        oab_section=org.oab_section,
        plan=org.plan,
        max_members=org.max_members,
        member_count=member_count,
        is_active=org.is_active,
        created_at=org.created_at,
        updated_at=org.updated_at,
    )


@router.put("/current", response_model=OrgResponse)
async def update_org(
    data: OrgUpdate,
    ctx: OrgContext = Depends(require_org_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Atualiza dados da organização (admin only)."""
    result = await db.execute(
        select(Organization).where(Organization.id == ctx.organization_id)
    )
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organização não encontrada")

    update_data = data.model_dump(exclude_unset=True)
    for field_name, value in update_data.items():
        setattr(org, field_name, value)

    await db.commit()
    await db.refresh(org)

    count_result = await db.execute(
        select(func.count()).select_from(OrganizationMember).where(
            OrganizationMember.organization_id == org.id,
            OrganizationMember.is_active == True,  # noqa: E712
        )
    )
    member_count = count_result.scalar() or 0

    return OrgResponse(
        id=org.id,
        name=org.name,
        slug=org.slug,
        cnpj=org.cnpj,
        oab_section=org.oab_section,
        plan=org.plan,
        max_members=org.max_members,
        member_count=member_count,
        is_active=org.is_active,
        created_at=org.created_at,
        updated_at=org.updated_at,
    )


# =============================================================================
# Members
# =============================================================================

@router.get("/members", response_model=List[MemberResponse])
async def list_members(
    ctx: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
):
    """Lista membros da organização."""
    if not ctx.is_org_member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sem organização")

    result = await db.execute(
        select(OrganizationMember, User)
        .join(User, User.id == OrganizationMember.user_id)
        .where(OrganizationMember.organization_id == ctx.organization_id)
        .order_by(OrganizationMember.joined_at)
    )
    rows = result.all()

    return [
        MemberResponse(
            user_id=member.user_id,
            user_name=user.name,
            user_email=user.email,
            role=member.role.value,
            is_active=member.is_active,
            joined_at=member.joined_at,
        )
        for member, user in rows
    ]


@router.post("/members/invite", response_model=MemberResponse, status_code=status.HTTP_201_CREATED)
async def invite_member(
    data: InviteRequest,
    ctx: OrgContext = Depends(require_org_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Convida usuário por email (admin only). Cria conta se necessário."""
    # Verificar limite de membros
    result = await db.execute(
        select(Organization).where(Organization.id == ctx.organization_id)
    )
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organização não encontrada")

    count_result = await db.execute(
        select(func.count()).select_from(OrganizationMember).where(
            OrganizationMember.organization_id == ctx.organization_id,
            OrganizationMember.is_active == True,  # noqa: E712
        )
    )
    member_count = count_result.scalar() or 0
    if member_count >= org.max_members:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Limite de {org.max_members} membros atingido",
        )

    # Buscar ou criar usuário
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()

    if not user:
        # Criar conta placeholder (sem senha — convite pendente)
        from app.core.security import get_password_hash
        user = User(
            id=str(uuid.uuid4()),
            email=data.email,
            hashed_password=get_password_hash(str(uuid.uuid4())),  # senha temporária
            name=data.email.split("@")[0],
            is_active=True,
            is_verified=False,
        )
        db.add(user)
        await db.flush()

    # Verificar se já é membro
    existing = await db.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == ctx.organization_id,
            OrganizationMember.user_id == user.id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Usuário já é membro desta organização",
        )

    # Criar membership
    role = OrgRole(data.role)
    member = OrganizationMember(
        id=str(uuid.uuid4()),
        organization_id=ctx.organization_id,
        user_id=user.id,
        role=role,
    )
    db.add(member)

    # Atualizar user.organization_id
    user.organization_id = ctx.organization_id
    db.add(user)

    await db.commit()
    await db.refresh(member)
    await db.refresh(user)

    return MemberResponse(
        user_id=user.id,
        user_name=user.name,
        user_email=user.email,
        role=member.role.value,
        is_active=member.is_active,
        joined_at=member.joined_at,
    )


@router.put("/members/{user_id}/role", response_model=MemberResponse)
async def update_member_role(
    user_id: str,
    data: RoleUpdate,
    ctx: OrgContext = Depends(require_org_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Altera role de um membro (admin only)."""
    # Não pode alterar própria role
    if user_id == ctx.user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não é possível alterar sua própria role",
        )

    result = await db.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == ctx.organization_id,
            OrganizationMember.user_id == user_id,
        )
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Membro não encontrado")

    member.role = OrgRole(data.role)
    await db.commit()
    await db.refresh(member)

    # Buscar dados do user
    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one()

    return MemberResponse(
        user_id=user.id,
        user_name=user.name,
        user_email=user.email,
        role=member.role.value,
        is_active=member.is_active,
        joined_at=member.joined_at,
    )


@router.delete("/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    user_id: str,
    ctx: OrgContext = Depends(require_org_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Remove membro da organização (admin only)."""
    if user_id == ctx.user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não é possível remover a si mesmo. Use 'sair da organização'.",
        )

    result = await db.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == ctx.organization_id,
            OrganizationMember.user_id == user_id,
        )
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Membro não encontrado")

    # Remover de teams da org
    teams_result = await db.execute(
        select(TeamMember)
        .join(Team, Team.id == TeamMember.team_id)
        .where(
            Team.organization_id == ctx.organization_id,
            TeamMember.user_id == user_id,
        )
    )
    for tm in teams_result.scalars().all():
        await db.delete(tm)

    # Remover membership
    await db.delete(member)

    # Limpar user.organization_id
    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    if user:
        user.organization_id = None
        db.add(user)

    await db.commit()


# =============================================================================
# Teams
# =============================================================================

@router.post("/teams", response_model=TeamResponse, status_code=status.HTTP_201_CREATED)
async def create_team(
    data: TeamCreate,
    ctx: OrgContext = Depends(require_org_role("admin", "advogado")),
    db: AsyncSession = Depends(get_db),
):
    """Cria equipe na organização."""
    team = Team(
        id=str(uuid.uuid4()),
        organization_id=ctx.organization_id,
        name=data.name,
        description=data.description,
    )
    db.add(team)
    await db.commit()
    await db.refresh(team)

    return TeamResponse(
        id=team.id,
        name=team.name,
        description=team.description,
        member_count=0,
        created_at=team.created_at,
    )


@router.get("/teams", response_model=List[TeamResponse])
async def list_teams(
    ctx: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
):
    """Lista equipes da organização."""
    if not ctx.is_org_member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sem organização")

    result = await db.execute(
        select(Team).where(Team.organization_id == ctx.organization_id).order_by(Team.created_at)
    )
    teams = result.scalars().all()

    responses = []
    for team in teams:
        count_result = await db.execute(
            select(func.count()).select_from(TeamMember).where(TeamMember.team_id == team.id)
        )
        member_count = count_result.scalar() or 0
        responses.append(
            TeamResponse(
                id=team.id,
                name=team.name,
                description=team.description,
                member_count=member_count,
                created_at=team.created_at,
            )
        )

    return responses


@router.post("/teams/{team_id}/members", status_code=status.HTTP_201_CREATED)
async def add_team_member(
    team_id: str,
    data: TeamMemberAdd,
    ctx: OrgContext = Depends(require_org_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Adiciona membro a uma equipe (admin only)."""
    # Verificar que team pertence à org
    team_result = await db.execute(
        select(Team).where(Team.id == team_id, Team.organization_id == ctx.organization_id)
    )
    if not team_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Equipe não encontrada")

    # Verificar que user é membro da org
    member_result = await db.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == ctx.organization_id,
            OrganizationMember.user_id == data.user_id,
            OrganizationMember.is_active == True,  # noqa: E712
        )
    )
    if not member_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Usuário não é membro ativo da organização",
        )

    # Verificar duplicata
    existing = await db.execute(
        select(TeamMember).where(
            TeamMember.team_id == team_id,
            TeamMember.user_id == data.user_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Usuário já é membro desta equipe",
        )

    tm = TeamMember(
        id=str(uuid.uuid4()),
        team_id=team_id,
        user_id=data.user_id,
    )
    db.add(tm)
    await db.commit()

    return {"status": "ok", "team_id": team_id, "user_id": data.user_id}


@router.delete("/teams/{team_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_team_member(
    team_id: str,
    user_id: str,
    ctx: OrgContext = Depends(require_org_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Remove membro de uma equipe (admin only)."""
    # Verificar que team pertence à org
    team_result = await db.execute(
        select(Team).where(Team.id == team_id, Team.organization_id == ctx.organization_id)
    )
    if not team_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Equipe não encontrada")

    result = await db.execute(
        select(TeamMember).where(
            TeamMember.team_id == team_id,
            TeamMember.user_id == user_id,
        )
    )
    tm = result.scalar_one_or_none()
    if not tm:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Membro não encontrado na equipe")

    await db.delete(tm)
    await db.commit()
