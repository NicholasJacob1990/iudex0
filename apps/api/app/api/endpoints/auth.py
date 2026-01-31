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
    get_current_user_from_refresh_token,
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
    # Normalizar account_type
    account_type_str = user_in.account_type.upper() if isinstance(user_in.account_type, str) else str(user_in.account_type).upper()
    
    # Validar account_type
    if account_type_str not in ["INDIVIDUAL", "INSTITUTIONAL"]:
        account_type_str = "INDIVIDUAL"
        
    # Converter para Enum
    account_type_enum = AccountType.INDIVIDUAL if account_type_str == "INDIVIDUAL" else AccountType.INSTITUTIONAL
    
    user_data = {
        "id": str(uuid.uuid4()),
        "email": user_in.email,
        "hashed_password": get_password_hash(user_in.password),
        "name": user_in.name,
        "role": UserRole.USER,
        "plan": UserPlan.FREE,
        "account_type": account_type_enum,
        "is_active": True,
        "is_verified": False,  # Requer confirmação de email futuramente
        "preferences": {
            "theme": "system",
            "language": "pt-BR",
            "notifications_enabled": True
        }
    }
    
    # Adicionar campos específicos do perfil
    if account_type_str == "INDIVIDUAL":
        if user_in.oab:
            user_data["oab"] = user_in.oab
        if user_in.oab_state:
            user_data["oab_state"] = user_in.oab_state
        if user_in.cpf:
            user_data["cpf"] = user_in.cpf
        if user_in.phone:
            user_data["phone"] = user_in.phone
            
    elif account_type_str == "INSTITUTIONAL":
        if user_in.institution_name:
            user_data["institution_name"] = user_in.institution_name
        if user_in.cnpj:
            user_data["cnpj"] = user_in.cnpj
        if user_in.position:
            user_data["position"] = user_in.position
        if user_in.department:
            user_data["department"] = user_in.department
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
        data={"sub": db_user.id, "type": "access", "role": db_user.role.value, "plan": db_user.plan.value, "org_id": db_user.organization_id},
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
        data={"sub": user.id, "type": "access", "role": user.role.value, "plan": user.plan.value, "org_id": user.organization_id},
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


@router.post("/login-test", response_model=TokenResponse)
async def login_test(
    db: AsyncSession = Depends(get_db)
):
    """
    Login especial para testes/demonstração (Cria usuário se não existir)
    """
    print("[Login Test] Iniciando endpoint login-test")
    test_email = "teste@iudex.ai"
    
    try:
        # Verificar se usuário teste existe
        print(f"[Login Test] Buscando usuário {test_email}")
        result = await db.execute(select(User).where(User.email == test_email))
        user = result.scalars().first()
        
        if not user:
            print("[Login Test] Usuário não encontrado. Criando novo usuário...")
            # Criar usuário de teste
            user = User(
                id=str(uuid.uuid4()),
                email=test_email,
                hashed_password=get_password_hash("teste123"),
                name="Usuário de Teste",
                role=UserRole.PREMIUM,
                plan=UserPlan.PROFESSIONAL,
                account_type=AccountType.INDIVIDUAL,
                is_active=True,
                is_verified=True,
                oab="999999",
                oab_state="SP",
                preferences={
                    "theme": "system",
                    "language": "pt-BR",
                    "notifications_enabled": True
                }
            )
            db.add(user)
            print("[Login Test] Usuário adicionado à sessão. Commitando...")
            await db.commit()
            print("[Login Test] Commit realizado. Refreshing...")
            await db.refresh(user)
            print(f"[Login Test] Usuário criado: {user.id}")
        else:
            print(f"[Login Test] Usuário encontrado: {user.id}. Verificando self-healing...")
            # Self-healing: Garantir que o usuário de teste esteja ativo e correto
            params_changed = False
            
            if not user.is_active:
                user.is_active = True
                params_changed = True
                
            if not user.is_verified:
                user.is_verified = True
                params_changed = True
                
            # Garantir roles corretas para teste
            if user.role != UserRole.PREMIUM:
                user.role = UserRole.PREMIUM
                params_changed = True
                
            if user.plan != UserPlan.PROFESSIONAL:
                user.plan = UserPlan.PROFESSIONAL
                params_changed = True
                
            if params_changed:
                print("[Login Test] Aplicando correções (self-healing)...")
                db.add(user)
                await db.commit()
                await db.refresh(user)
                print("[Login Test] Correções aplicadas com sucesso.")
        
        # Gerar tokens (mesma lógica do login)
        print("[Login Test] Gerando tokens...")
        access_token_expires = timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": user.id, "type": "access", "role": user.role.value, "plan": user.plan.value, "org_id": user.organization_id},
            expires_delta=access_token_expires
        )
        
        refresh_token = create_refresh_token(
            data={"sub": user.id, "type": "refresh"}
        )
        
        # Verificar se o usuário realmente existe no banco antes de retornar
        verify_result = await db.execute(select(User).where(User.id == user.id))
        verify_user = verify_result.scalars().first()
        if not verify_user:
            print(f"[Login Test] ERRO: Usuário {user.id} não encontrado após commit!")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erro ao persistir usuário de teste"
            )

        print(f"[Login Test] Tokens gerados. User ID: {user.id}, Email: {user.email}")
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            "user": user
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"[Login Test] ERRO CRÍTICO: {str(e)}")
        import traceback
        traceback.print_exc()
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao realizar login de teste: {str(e)}"
        )


@router.post("/logout")
async def logout(
    current_user: User = Depends(get_current_user)
):
    """
    Logout de usuário
    """
    # Em JWT stateless, logout é feito no frontend removendo o token.
    # Futuramente pode-se implementar blacklist de tokens no Redis.
    return {"message": "Logout realizado com sucesso"}


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token_endpoint(
    current_user: User = Depends(get_current_user_from_refresh_token)
):
    """
    Renovar token de acesso
    """
    # current_user já é um objeto User retornado por get_current_user
    
    access_token_expires = timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": current_user.id, "type": "access", "role": current_user.role.value, "plan": current_user.plan.value, "org_id": current_user.organization_id},
        expires_delta=access_token_expires
    )

    # Opcional: Rotacionar refresh token também
    refresh_token = create_refresh_token(
        data={"sub": current_user.id, "type": "refresh"}
    )
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "user": current_user
    }


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_user)
):
    """
    Obter informações do usuário atual
    """
    # current_user já é um objeto User retornado por get_current_user
    return current_user
