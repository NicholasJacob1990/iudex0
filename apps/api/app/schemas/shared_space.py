"""
Schemas Pydantic para Shared Spaces
"""

from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ---------------------------------------------------------------------------
# SharedSpace
# ---------------------------------------------------------------------------

class SpaceCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=200)
    description: Optional[str] = None
    branding: Optional[dict] = None  # {logo_url, primary_color, accent_color}


class SpaceUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=200)
    description: Optional[str] = None
    branding: Optional[dict] = None


class SpaceResponse(BaseModel):
    id: str
    organization_id: str
    name: str
    slug: str
    description: Optional[str] = None
    branding: Optional[dict] = None
    member_count: int = 0
    resource_count: int = 0
    created_by: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# SpaceInvite
# ---------------------------------------------------------------------------

class InviteToSpaceRequest(BaseModel):
    email: EmailStr
    role: str = Field(default="viewer", pattern=r"^(admin|contributor|viewer)$")
    message: Optional[str] = None


class SpaceInviteResponse(BaseModel):
    """Resposta padrao de convite (sem token)."""
    id: str
    space_id: str
    email: str
    role: str
    status: str
    message: Optional[str] = None
    invited_by: Optional[str] = None
    user_id: Optional[str] = None
    accepted_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SpaceInviteCreatedResponse(SpaceInviteResponse):
    """Resposta ao criar convite -- inclui token (retornado apenas na criacao)."""
    token: str


class SpaceMemberResponse(BaseModel):
    email: str
    role: str
    status: str
    user_id: Optional[str] = None
    user_name: Optional[str] = None
    accepted_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class JoinSpaceResponse(BaseModel):
    space_id: str
    space_name: str
    role: str
    message: str


# ---------------------------------------------------------------------------
# SpaceResource
# ---------------------------------------------------------------------------

class AddResourceRequest(BaseModel):
    resource_type: str = Field(..., pattern=r"^(workflow|document|run|folder)$")
    resource_id: str
    resource_name: Optional[str] = None


class SpaceResourceResponse(BaseModel):
    id: str
    space_id: str
    resource_type: str
    resource_id: str
    resource_name: Optional[str] = None
    added_by: Optional[str] = None
    added_at: datetime

    model_config = ConfigDict(from_attributes=True)
