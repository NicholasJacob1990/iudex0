"""
Microsoft token validation and OBO flow for SSO.
"""

import logging
from typing import Optional

import jwt as pyjwt
from jwt import PyJWKClient
import msal

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.models.microsoft_user import MicrosoftUser
from app.models.user import User

logger = logging.getLogger(__name__)

MICROSOFT_JWKS_URI = "https://login.microsoftonline.com/common/discovery/v2.0/keys"

_jwks_client: Optional[PyJWKClient] = None


def get_jwks_client() -> PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = PyJWKClient(MICROSOFT_JWKS_URI)
    return _jwks_client


async def validate_microsoft_token(token: str) -> dict:
    """Validate JWT from Microsoft (NAA or Teams SSO)."""
    jwks_client = get_jwks_client()
    signing_key = jwks_client.get_signing_key_from_jwt(token)

    claims = pyjwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        audience=settings.AZURE_CLIENT_ID,
        options={
            "verify_exp": True,
            "verify_nbf": True,
            "verify_iss": False,  # Multi-tenant: issuer varies
            "verify_aud": True,
        },
    )
    return claims


async def acquire_obo_token(assertion: str, scopes: list[str]) -> str:
    """OBO flow: exchange Teams/Outlook token for Graph token."""
    app = msal.ConfidentialClientApplication(
        settings.AZURE_CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{settings.AZURE_TENANT_ID}",
        client_credential=settings.AZURE_CLIENT_SECRET,
    )
    result = app.acquire_token_on_behalf_of(
        user_assertion=assertion,
        scopes=scopes,
    )
    if "access_token" not in result:
        raise ValueError(f"OBO token acquisition failed: {result.get('error_description', 'Unknown error')}")
    return result["access_token"]


async def find_or_create_microsoft_user(
    db: AsyncSession,
    email: str,
    name: str,
    oid: str,
    tid: str,
) -> User:
    """Find existing user by Microsoft OID or create new one."""
    # Check if Microsoft account already linked
    stmt = select(MicrosoftUser).where(
        MicrosoftUser.microsoft_oid == oid,
        MicrosoftUser.microsoft_tid == tid,
    )
    result = await db.execute(stmt)
    ms_user = result.scalar_one_or_none()

    if ms_user:
        # Update display info
        ms_user.microsoft_email = email
        ms_user.display_name = name
        await db.commit()

        # Load linked user
        user_stmt = select(User).where(User.id == ms_user.user_id)
        user_result = await db.execute(user_stmt)
        return user_result.scalar_one()

    # Check if user with same email exists
    user_stmt = select(User).where(User.email == email)
    user_result = await db.execute(user_stmt)
    user = user_result.scalar_one_or_none()

    if not user:
        raise ValueError(
            "Nenhuma conta Iudex encontrada para este email Microsoft. "
            "Use as mesmas credenciais do Iudex ou peça ao administrador para criar sua conta."
        )

    # Link Microsoft account
    ms_user = MicrosoftUser(
        user_id=user.id,
        microsoft_oid=oid,
        microsoft_tid=tid,
        microsoft_email=email,
        display_name=name,
    )
    db.add(ms_user)
    await db.commit()
    await db.refresh(user)

    return user
