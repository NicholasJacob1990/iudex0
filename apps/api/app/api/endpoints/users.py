"""
Endpoints de usuários
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user

router = APIRouter()


@router.get("/profile")
async def get_profile(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Obter perfil do usuário
    """
    # TODO: Buscar perfil completo do banco
    return {"message": "Profile endpoint"}


@router.put("/profile")
async def update_profile(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Atualizar perfil do usuário
    """
    # TODO: Atualizar perfil
    return {"message": "Profile updated"}


@router.get("/preferences")
async def get_preferences(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Obter preferências do usuário
    """
    # TODO: Buscar preferências
    return {"preferences": {}}


@router.put("/preferences")
async def update_preferences(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Atualizar preferências do usuário
    """
    # TODO: Atualizar preferências
    return {"message": "Preferences updated"}

