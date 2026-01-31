"""
Schemas Pydantic para Organização, Membros e Equipes
"""

from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ---------------------------------------------------------------------------
# Organization
# ---------------------------------------------------------------------------

class OrgCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=200)
    cnpj: Optional[str] = None
    oab_section: Optional[str] = None


class OrgUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=200)
    cnpj: Optional[str] = None
    oab_section: Optional[str] = None
    settings: Optional[dict] = None


class OrgResponse(BaseModel):
    id: str
    name: str
    slug: str
    cnpj: Optional[str] = None
    oab_section: Optional[str] = None
    plan: str
    max_members: int
    member_count: int = 0
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Members
# ---------------------------------------------------------------------------

class MemberResponse(BaseModel):
    user_id: str
    user_name: str
    user_email: str
    role: str
    is_active: bool
    joined_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InviteRequest(BaseModel):
    email: EmailStr
    role: str = Field(default="advogado", pattern=r"^(admin|advogado|estagiario)$")


class RoleUpdate(BaseModel):
    role: str = Field(..., pattern=r"^(admin|advogado|estagiario)$")


# ---------------------------------------------------------------------------
# Teams
# ---------------------------------------------------------------------------

class TeamCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    description: Optional[str] = None


class TeamUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    description: Optional[str] = None


class TeamResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    member_count: int = 0
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TeamMemberAdd(BaseModel):
    user_id: str
