"""
Endpoints de usuários
"""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
from typing import Any, Dict

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_PREFERENCES_SIZE = 100_000  # 100KB
MAX_PREFERENCES_DEPTH = 10


class PreferencesUpdate(BaseModel):
    preferences: Dict[str, Any] = Field(default_factory=dict)
    replace: bool = False


def _merge_dicts(base: Dict[str, Any], incoming: Dict[str, Any], depth: int = 0) -> Dict[str, Any]:
    if depth > MAX_PREFERENCES_DEPTH:
        raise ValueError("Preferences nested too deeply")
    merged = dict(base)
    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_dicts(merged[key], value, depth + 1)
        else:
            merged[key] = value
    return merged


def _redact_credentials(prefs: Dict[str, Any]) -> Dict[str, Any]:
    """Centralized redaction — never return passwords to the frontend."""
    redacted = dict(prefs)
    if "pje_credentials" in redacted and isinstance(redacted["pje_credentials"], dict):
        sanitized = dict(redacted["pje_credentials"])
        if "senha" in sanitized:
            sanitized["senha_set"] = True
            del sanitized["senha"]
        redacted["pje_credentials"] = sanitized
    return redacted


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
    Obter preferências do usuário.
    Sensitive fields (passwords) are redacted from the response.
    """
    prefs = dict(current_user.preferences or {})
    return {"preferences": _redact_credentials(prefs)}


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

    # Validate size to prevent JSON bombs
    try:
        serialized = json.dumps(incoming)
        if len(serialized) > MAX_PREFERENCES_SIZE:
            raise HTTPException(413, "Preferences payload too large (max 100KB)")
    except (TypeError, ValueError):
        raise HTTPException(422, "Invalid preferences format")

    # Encrypt and validate sensitive credentials before storing
    if "pje_credentials" in incoming and isinstance(incoming["pje_credentials"], dict):
        pje = incoming["pje_credentials"]
        if "senha" in pje:
            senha_value = pje["senha"]
            # Remove empty/None/whitespace — don't overwrite existing password
            if not senha_value or (isinstance(senha_value, str) and not senha_value.strip()):
                del pje["senha"]
            else:
                # Encrypt the password before storing
                from app.core.credential_encryption import encrypt_credential
                pje["senha"] = encrypt_credential(senha_value)

    if payload.replace:
        current_user.preferences = incoming
    else:
        try:
            current_user.preferences = _merge_dicts(current_user.preferences or {}, incoming)
        except ValueError as e:
            raise HTTPException(422, str(e))

    db.add(current_user)
    await db.commit()
    await db.refresh(current_user)

    prefs = dict(current_user.preferences or {})
    return {"message": "Preferences updated", "preferences": _redact_credentials(prefs)}
