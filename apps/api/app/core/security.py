"""
Utilitários de segurança e autenticação
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.core.database import get_db
from app.models.user import User

# Contexto para hashing de senhas
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Bearer token
security = HTTPBearer()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica se a senha está correta"""
    # Bcrypt tem limitação de 72 bytes - truncar se necessário
    password_bytes = plain_password.encode('utf-8')
    if len(password_bytes) > 72:
        plain_password = password_bytes[:72].decode('utf-8', errors='ignore')
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Gera hash da senha"""
    # Bcrypt tem limitação de 72 bytes - truncar se necessário
    password_bytes = password.encode('utf-8')
    if len(password_bytes) > 72:
        password = password_bytes[:72].decode('utf-8', errors='ignore')
    return pwd_context.hash(password)


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """
    Cria token de acesso JWT
    """
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(
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
    expire = datetime.utcnow() + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
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
