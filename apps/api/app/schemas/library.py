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


class LibraryItemCreate(LibraryItemBase):
    """Schema para criação de item"""
    pass


class LibraryItemResponse(LibraryItemBase):
    """Schema de resposta de item"""
    id: str
    user_id: str
    is_shared: bool
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

