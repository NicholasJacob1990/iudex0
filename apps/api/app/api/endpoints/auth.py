"""
Endpoints de autenticação
"""

from datetime import timedelta
from typing import Any
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.database import get_db
from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    get_password_hash,
    verify_password,
    get_current_user,
)
from app.models.user import User, UserRole, UserPlan, AccountType
from app.schemas.user import UserCreate, UserLogin, TokenResponse, UserResponse

router = APIRouter()


@router.post("/register", response_model=TokenResponse)
async def register(
    user_in: UserCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    Registrar novo usuário
    """
    # Verificar se email já existe
    result = await db.execute(select(User).where(User.email == user_in.email))
    existing_user = result.scalars().first()
    
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email já cadastrado no sistema"
        )
    
    # Preparar dados do usuário
    user_data = {
        "id": str(uuid.uuid4()),
        "email": user_in.email,
        "hashed_password": get_password_hash(user_in.password),
        "name": user_in.name,
        "role": UserRole.USER,
        "plan": UserPlan.FREE,
        "account_type": AccountType(user_in.account_type),
        "is_active": True,
        "is_verified": False,  # Requer confirmação de email futuramente
        "preferences": {
            "theme": "system",
            "language": "pt-BR",
            "notifications_enabled": True
        }
    }
    
    # Adicionar campos específicos do perfil
    if user_in.account_type == "INDIVIDUAL":
        if user_in.oab:
            user_data["oab"] = user_in.oab
        if user_in.cpf:
            user_data["cpf"] = user_in.cpf
            
    elif user_in.account_type == "INSTITUTIONAL":
        if user_in.institution_name:
            user_data["institution_name"] = user_in.institution_name
        if user_in.cnpj:
            user_data["cnpj"] = user_in.cnpj
        # team_size é salvo nas preferências por enquanto, pois não tem campo no model
        if user_in.team_size:
            user_data["preferences"]["team_size"] = user_in.team_size
            
    # Criar usuário
    db_user = User(**user_data)
    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)
    
    # Gerar tokens
    access_token_expires = timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": db_user.id, "type": "access", "role": db_user.role.value, "plan": db_user.plan.value},
        expires_delta=access_token_expires
    )
    
    refresh_token = create_refresh_token(
        data={"sub": db_user.id, "type": "refresh"}
    )
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "user": db_user
    }


@router.post("/login", response_model=TokenResponse)
async def login(
    login_data: UserLogin,
    db: AsyncSession = Depends(get_db)
):
    """
    Login de usuário
    """
    # Buscar usuário
    result = await db.execute(select(User).where(User.email == login_data.email))
    user = result.scalars().first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou senha incorretos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Verificar senha
    if not verify_password(login_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou senha incorretos",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Usuário inativo"
        )
    
    # Gerar tokens
    access_token_expires = timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.id, "type": "access", "role": user.role.value, "plan": user.plan.value},
        expires_delta=access_token_expires
    )
    
    refresh_token = create_refresh_token(
        data={"sub": user.id, "type": "refresh"}
    )
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "user": user
    }


@router.post("/logout")
async def logout(
    current_user: dict = Depends(get_current_user)
):
    """
    Logout de usuário
    """
    # Em JWT stateless, logout é feito no frontend removendo o token.
    # Futuramente pode-se implementar blacklist de tokens no Redis.
    return {"message": "Logout realizado com sucesso"}


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token_endpoint(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Renovar token de acesso
    """
    # current_user já vem do dependency que valida o token (mesmo que seja refresh se configurado)
    # Mas aqui assumimos que o endpoint /refresh recebe um token de refresh no header Authorization
    
    user_id = current_user["id"]
    
    # Buscar usuário atualizado
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
        
    access_token_expires = timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.id, "type": "access", "role": user.role.value, "plan": user.plan.value},
        expires_delta=access_token_expires
    )
    
    # Opcional: Rotacionar refresh token também
    refresh_token = create_refresh_token(
        data={"sub": user.id, "type": "refresh"}
    )
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "user": user
    }


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Obter informações do usuário atual
    """
    user_id = current_user["id"]
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
        
    return user
