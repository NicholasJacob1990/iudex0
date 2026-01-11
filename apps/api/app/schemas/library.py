"""
Schemas Pydantic para biblioteca
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


class LibraryItemBase(BaseModel):
    """Schema base de item da biblioteca"""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    type: str
    tags: List[str] = Field(default_factory=list)
    folder_id: Optional[str] = None
    resource_id: str
    token_count: int = Field(default=0, ge=0)


class LibraryItemCreate(LibraryItemBase):
    """Schema para criação de item"""
    pass


class LibraryItemResponse(LibraryItemBase):
    """Schema de resposta de item"""
    id: str
    user_id: str
    is_shared: bool
    token_count: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class FolderBase(BaseModel):
    """Schema base de pasta"""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    parent_id: Optional[str] = None
    type: str = "DOCUMENT"
    color: Optional[str] = None
    icon: Optional[str] = None


class FolderCreate(FolderBase):
    """Schema para criação de pasta"""
    pass


class FolderResponse(FolderBase):
    """Schema de resposta de pasta"""
    id: str
    user_id: str
    is_shared: bool
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class LibrarianBase(BaseModel):
    """Schema base de bibliotecário"""
    name: str = Field(..., min_length=1, max_length=255)
    description: str
    icon: Optional[str] = None
    resources: List[str] = Field(default_factory=list)


class LibrarianCreate(LibrarianBase):
    """Schema para criação de bibliotecário"""
    pass


class LibrarianResponse(LibrarianBase):
    """Schema de resposta de bibliotecário"""
    id: str
    user_id: str
    is_shared: bool
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


# Schemas de Compartilhamento

class SharePermission(BaseModel):
    """Permissão de compartilhamento"""
    email: str = Field(..., pattern=r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
    permission: str = Field(..., pattern='^(view|edit)$')  # view ou edit


class ShareRequest(BaseModel):
    """Request para compartilhar recurso"""
    resource_id: str
    resource_type: str = Field(..., pattern='^(document|model|precedent|prompt|librarian|folder)$')
    users: List[SharePermission] = Field(default_factory=list)
    groups: List[str] = Field(default_factory=list)  # IDs de grupos
    message: Optional[str] = None


class ShareResponse(BaseModel):
    """Response de compartilhamento"""
    resource_id: str
    resource_type: str
    shared_with_users: List[Dict[str, Any]]
    shared_with_groups: List[str]
    success: bool
    message: str


class RevokeShareRequest(BaseModel):
    """Request para revogar compartilhamento"""
    resource_id: str
    resource_type: str
    user_emails: List[str] = Field(default_factory=list)
    group_ids: List[str] = Field(default_factory=list)


class SharedResourcesResponse(BaseModel):
    """Lista de recursos compartilhados"""
    shared_by_me: List[Dict[str, Any]]
    shared_with_me: List[Dict[str, Any]]
    pending: List[Dict[str, Any]]


class ShareRecordResponse(BaseModel):
    """Resposta detalhada de um compartilhamento"""
    id: str
    resource_type: str
    resource_id: str
    resource_name: str
    owner_id: str
    owner_email: str
    shared_with_user_id: Optional[str]
    shared_with_email: Optional[str]
    permission: str
    status: str
    created_at: datetime
    accepted_at: Optional[datetime]
    
    class Config:
        from_attributes = True


class AcceptShareRequest(BaseModel):
    """Request para aceitar compartilhamento"""
    share_id: str


class RejectShareRequest(BaseModel):
    """Request para rejeitar compartilhamento"""
    share_id: str
    reason: Optional[str] = None


class UpdatePermissionRequest(BaseModel):
    """Request para atualizar permissão"""
    share_id: str
    permission: str = Field(..., pattern='^(view|edit)$')




