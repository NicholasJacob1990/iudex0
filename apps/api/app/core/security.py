"""
Utilitários de segurança e autenticação
"""

from dataclasses import dataclass, field
from datetime import timedelta
from typing import List, Optional, Dict, Any

from jose import JWTError, jwt
from passlib.context import CryptContext
import bcrypt
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.core.database import get_db
from app.core.time_utils import utcnow
from app.models.user import User
from app.models.guest_session import GuestSession

# Contexto para hashing de senhas
#
# Observação:
# - `passlib` 1.7.x + `bcrypt` >= 5.0 pode falhar ao inicializar o backend do bcrypt
#   por causa da verificação interna de "wrap bug" (usa senha >72 bytes, e a lib
#   `bcrypt` agora levanta ValueError).
# - Para manter testes/ambiente estáveis, usamos `pbkdf2_sha256` como padrão para
#   novos hashes, mas preservamos verificação de hashes bcrypt existentes via
#   `bcrypt.checkpw()` quando o hash começa com "$2".
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

# Bearer token
security = HTTPBearer(auto_error=False)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica se a senha está correta"""
    if not hashed_password:
        return False

    # Backward-compat: hashes bcrypt existentes ($2a/$2b/$2y)
    if hashed_password.startswith("$2"):
        try:
            password_bytes = plain_password.encode("utf-8")
            if len(password_bytes) > 72:
                password_bytes = password_bytes[:72]
            return bcrypt.checkpw(password_bytes, hashed_password.encode("utf-8"))
        except Exception:
            return False

    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Gera hash da senha"""
    return pwd_context.hash(password)


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """
    Cria token de acesso JWT
    """
    to_encode = data.copy()
    
    if expires_delta:
        expire = utcnow() + expires_delta
    else:
        expire = utcnow() + timedelta(
            minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
        )
    
    to_encode.update({"exp": expire, "type": "access"})
    
    encoded_jwt = jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    
    return encoded_jwt


def create_refresh_token(data: Dict[str, Any]) -> str:
    """
    Cria token de refresh JWT
    """
    to_encode = data.copy()
    expire = utcnow() + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    
    encoded_jwt = jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    
    return encoded_jwt


def decode_token(token: str) -> Dict[str, Any]:
    """
    Decodifica e valida token JWT
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido ou expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    Dependency para obter usuário atual a partir do token
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authenticated",
        )

    token = credentials.credentials
    payload = decode_token(token)
    
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tipo de token inválido",
        )
    
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido",
        )
    
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário não encontrado",
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Usuário inativo",
        )
        
    return user


async def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """
    Dependency que retorna o usuário atual se autenticado, ou None caso contrário.
    Usado em endpoints que aceitam acesso público opcionalmente.
    """
    if credentials is None:
        return None
    try:
        token = credentials.credentials
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        if payload.get("type") != "access":
            return None
        user_id = payload.get("sub")
        if not user_id:
            return None
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user or not user.is_active:
            return None
        return user
    except JWTError:
        return None


def create_guest_token(guest_session: GuestSession) -> str:
    """
    Cria token JWT para sessao guest com claims especificos.
    """
    expire = guest_session.expires_at
    to_encode = {
        "sub": guest_session.id,
        "type": "access",
        "is_guest": True,
        "space_id": guest_session.space_id,
        "permissions": guest_session.permissions.get("permissions", ["read"]),
        "exp": expire,
    }
    encoded_jwt = jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    return encoded_jwt


@dataclass
class UserOrGuest:
    """Wrapper que pode conter um User autenticado ou uma GuestSession."""
    user: Optional[User] = None
    guest: Optional[GuestSession] = None

    @property
    def is_guest(self) -> bool:
        return self.guest is not None

    @property
    def is_authenticated(self) -> bool:
        return self.user is not None

    @property
    def display_name(self) -> str:
        if self.user:
            return self.user.name
        if self.guest:
            return self.guest.display_name
        return "Desconhecido"

    @property
    def subject_id(self) -> str:
        """ID do sujeito (user_id ou guest_session_id)."""
        if self.user:
            return self.user.id
        if self.guest:
            return self.guest.id
        return ""


async def get_current_user_or_guest(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> UserOrGuest:
    """
    Dependency que aceita tanto JWT de usuario regular quanto JWT de guest.
    Retorna UserOrGuest para que endpoints possam distinguir.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Autenticacao necessaria",
        )

    token = credentials.credentials
    payload = decode_token(token)

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tipo de token invalido",
        )

    subject_id = payload.get("sub")
    if not subject_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalido",
        )

    # Verificar se e token de guest
    if payload.get("is_guest"):
        result = await db.execute(
            select(GuestSession).where(
                GuestSession.id == subject_id,
                GuestSession.is_active == True,  # noqa: E712
            )
        )
        guest = result.scalar_one_or_none()
        if not guest:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Sessao de visitante nao encontrada",
            )
        if guest.is_expired:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Sessao de visitante expirada",
            )
        # Atualizar last_accessed_at
        guest.last_accessed_at = utcnow()
        return UserOrGuest(guest=guest)

    # Token de usuario regular
    result = await db.execute(select(User).where(User.id == subject_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario nao encontrado",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Usuario inativo",
        )
    return UserOrGuest(user=user)


async def require_authenticated_user(
    auth: UserOrGuest = Depends(get_current_user_or_guest),
) -> User:
    """
    Dependency que rejeita guests — somente usuarios autenticados.
    Use em endpoints de escrita ou operacoes que exigem conta real.
    """
    if auth.is_guest:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Esta operacao requer uma conta autenticada. Visitantes nao tem permissao.",
        )
    assert auth.user is not None
    return auth.user


async def get_current_user_from_refresh_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    Dependency para obter usuário a partir de REFRESH token.
    Usado exclusivamente no endpoint /auth/refresh.
    """
    token = credentials.credentials
    payload = decode_token(token)
    
    # Validar que é um refresh token, não access token
    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de refresh esperado. Use o refresh_token, não o access_token.",
        )
    
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido",
        )
    
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário não encontrado",
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Usuário inativo",
        )
        
    return user


def require_role(*allowed_roles: str):
    """
    Dependency factory para verificar roles do usuário
    """
    async def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permissão negada",
            )
        return current_user
    
    return role_checker


def require_plan(*allowed_plans: str):
    """
    Dependency factory para verificar plano do usuário
    """
    async def plan_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.plan not in allowed_plans:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Plano insuficiente para esta funcionalidade",
            )
        return current_user

    return plan_checker


# ---------------------------------------------------------------------------
# Multi-tenancy: OrgContext
# ---------------------------------------------------------------------------

@dataclass
class OrgContext:
    """Contexto organizacional do usuário autenticado."""

    user: User
    organization_id: Optional[str] = None
    org_role: Optional[str] = None
    team_ids: List[str] = field(default_factory=list)

    @property
    def is_org_member(self) -> bool:
        return self.organization_id is not None

    @property
    def is_org_admin(self) -> bool:
        return self.org_role == "admin"

    @property
    def tenant_id(self) -> str:
        """Tenant ID para RAG/Neo4j: org_id se membro, senão user_id."""
        return self.organization_id or self.user.id


async def get_org_context(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OrgContext:
    """
    Dependency que carrega contexto organizacional completo.
    Se o usuário não tem organização, retorna OrgContext com org_id=None.
    """
    org_id = current_user.organization_id
    org_role: Optional[str] = None
    team_ids: List[str] = []

    if org_id:
        from app.models.organization import OrganizationMember, TeamMember, Team

        # Buscar role na org
        result = await db.execute(
            select(OrganizationMember.role).where(
                OrganizationMember.organization_id == org_id,
                OrganizationMember.user_id == current_user.id,
                OrganizationMember.is_active == True,  # noqa: E712
            )
        )
        role_value = result.scalar_one_or_none()
        if role_value is not None:
            org_role = role_value.value if hasattr(role_value, "value") else str(role_value)

        # Buscar teams do usuário nesta org
        result = await db.execute(
            select(TeamMember.team_id)
            .join(Team, Team.id == TeamMember.team_id)
            .where(
                Team.organization_id == org_id,
                TeamMember.user_id == current_user.id,
            )
        )
        team_ids = list(result.scalars().all())

    return OrgContext(
        user=current_user,
        organization_id=org_id,
        org_role=org_role,
        team_ids=team_ids,
    )


def require_org_role(*allowed_roles: str):
    """
    Dependency factory: verifica se usuário tem role específica na org.
    """
    async def checker(ctx: OrgContext = Depends(get_org_context)) -> OrgContext:
        if not ctx.is_org_member:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Requer membro de organização",
            )
        if ctx.org_role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permissão insuficiente na organização",
            )
        return ctx

    return checker


def build_tenant_filter(ctx: OrgContext, model_class):
    """
    Retorna cláusula WHERE apropriada para isolamento de dados.

    - Se o usuário é membro de uma org → filtra por organization_id
    - Senão (single-user mode) → filtra por user_id
    """
    if ctx.is_org_member:
        return model_class.organization_id == ctx.organization_id
    return model_class.user_id == ctx.user.id
