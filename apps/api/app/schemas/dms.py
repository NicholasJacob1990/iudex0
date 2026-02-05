"""
Schemas Pydantic para DMS (Document Management System) integrations.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Provider info
# ---------------------------------------------------------------------------

class DMSProviderInfo(BaseModel):
    id: str
    name: str
    description: str
    icon: str  # lucide icon name
    supports_sync: bool = True


class DMSProviderListResponse(BaseModel):
    providers: list[DMSProviderInfo]


# ---------------------------------------------------------------------------
# Connect (OAuth)
# ---------------------------------------------------------------------------

class DMSConnectRequest(BaseModel):
    provider: str = Field(..., description="google_drive | sharepoint | onedrive | imanage")
    display_name: str = Field(default="", max_length=255)
    redirect_url: Optional[str] = Field(
        default=None, description="URL para redirecionar após OAuth (override)"
    )
    # Campos opcionais para iManage
    server_url: Optional[str] = Field(
        default=None, description="URL do servidor iManage (ex: https://imanage.example.com)"
    )
    library: Optional[str] = Field(
        default=None, description="Nome da library iManage"
    )


class DMSConnectResponse(BaseModel):
    auth_url: str
    state: str  # CSRF state param


# ---------------------------------------------------------------------------
# Integration CRUD
# ---------------------------------------------------------------------------

class DMSIntegrationResponse(BaseModel):
    id: str
    provider: str
    display_name: str
    root_folder_id: Optional[str] = None
    sync_enabled: bool
    last_sync_at: Optional[datetime] = None
    connection_status: Optional[str] = "connected"
    provider_metadata: Optional[dict] = None
    created_at: datetime

    class Config:
        from_attributes = True


class DMSIntegrationListResponse(BaseModel):
    integrations: list[DMSIntegrationResponse]


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------

class DMSFileItem(BaseModel):
    id: str
    name: str
    mime_type: str
    size: Optional[int] = None
    is_folder: bool = False
    modified_at: Optional[datetime] = None
    parent_id: Optional[str] = None
    web_url: Optional[str] = None


class DMSFileListResponse(BaseModel):
    files: list[DMSFileItem]
    folder_id: Optional[str] = None
    breadcrumb: list[DMSFileItem] = []
    next_page_token: Optional[str] = None


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------

class DMSImportRequest(BaseModel):
    file_ids: list[str] = Field(..., min_length=1)
    target_corpus_project_id: Optional[str] = None


class DMSImportResponse(BaseModel):
    imported_count: int
    errors: list[str] = []
    document_ids: list[str] = []


# ---------------------------------------------------------------------------
# Sync
# ---------------------------------------------------------------------------

class DMSSyncRequest(BaseModel):
    folder_ids: Optional[list[str]] = None  # None = sync tudo


class DMSSyncResponse(BaseModel):
    status: str  # "started", "completed"
    synced_count: int = 0
    message: str = ""
