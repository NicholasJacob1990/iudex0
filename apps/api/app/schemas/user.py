"""
Schemas Pydantic para usuários
"""

from typing import Optional
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, ConfigDict
from enum import Enum


class AccountType(str, Enum):
    INDIVIDUAL = "INDIVIDUAL"
    INSTITUTIONAL = "INSTITUTIONAL"


class UserBase(BaseModel):
    """Schema base de usuário"""
    email: EmailStr
    name: str = Field(..., min_length=2, max_length=100)
    account_type: AccountType = AccountType.INDIVIDUAL


class UserCreate(UserBase):
    """Schema para criação de usuário"""
    password: str = Field(..., min_length=8, max_length=100)
    account_type: str = Field(default="INDIVIDUAL", pattern="^(INDIVIDUAL|INSTITUTIONAL)$")
    
    # Campos opcionais para conta Individual
    cpf: Optional[str] = None
    oab: Optional[str] = None
    oab_state: Optional[str] = None
    phone: Optional[str] = None
    
    # Campos opcionais para conta Institucional
    institution_name: Optional[str] = None
    cnpj: Optional[str] = None
    position: Optional[str] = None
    team_size: Optional[int] = None
    department: Optional[str] = None


class UserLogin(BaseModel):
    """Schema para login"""
    email: EmailStr
    password: str


class UserUpdate(BaseModel):
    """Schema para atualização de usuário"""
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    avatar: Optional[str] = None
    phone: Optional[str] = None
    
    # Individual
    oab: Optional[str] = None
    oab_state: Optional[str] = None
    signature_text: Optional[str] = None
    
    # Institucional
    institution_name: Optional[str] = None
    position: Optional[str] = None
    department: Optional[str] = None
    institution_address: Optional[str] = None
    institution_phone: Optional[str] = None


class UserResponse(UserBase):
    """Schema de resposta de usuário (sem dados sensíveis)"""
    id: str
    role: str
    plan: str
    is_active: bool
    is_verified: bool
    created_at: datetime
    updated_at: datetime

    # Campos de perfil
    avatar: Optional[str] = None
    oab: Optional[str] = None
    oab_state: Optional[str] = None
    phone: Optional[str] = None

    institution_name: Optional[str] = None
    position: Optional[str] = None
    department: Optional[str] = None

    # Multi-tenancy
    organization_id: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class UserDetailResponse(UserResponse):
    """Schema de resposta detalhada (admin) — inclui CPF/CNPJ"""
    cpf: Optional[str] = None
    cnpj: Optional[str] = None


class TokenResponse(BaseModel):
    """Schema de resposta de token"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse
