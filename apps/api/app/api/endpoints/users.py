"""
Endpoints de usuários
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
from typing import Any, Dict

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User

router = APIRouter()


class PreferencesUpdate(BaseModel):
    preferences: Dict[str, Any] = Field(default_factory=dict)
    replace: bool = False


def _merge_dicts(base: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base)
    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_dicts(merged[key], value)
        else:
            merged[key] = value
    return merged


@router.get("/profile")
async def get_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Obter perfil do usuário
    """
    # TODO: Buscar perfil completo do banco
    return {"message": "Profile endpoint"}


@router.put("/profile")
async def update_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Atualizar perfil do usuário
    """
    # TODO: Atualizar perfil
    return {"message": "Profile updated"}


@router.get("/preferences")
async def get_preferences(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Obter preferências do usuário
    """
    return {"preferences": current_user.preferences or {}}


@router.put("/preferences")
async def update_preferences(
    payload: PreferencesUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Atualizar preferências do usuário
    """
    incoming = payload.preferences or {}
    if payload.replace:
        current_user.preferences = incoming
    else:
        current_user.preferences = _merge_dicts(current_user.preferences or {}, incoming)

    db.add(current_user)
    await db.commit()
    await db.refresh(current_user)

    return {"message": "Preferences updated", "preferences": current_user.preferences or {}}
