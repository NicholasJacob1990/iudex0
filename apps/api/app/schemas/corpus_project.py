"""
Schemas Pydantic para Corpus Projects — projetos dinâmicos de corpus.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


# =============================================================================
# Create / Update
# =============================================================================


class CorpusProjectCreate(BaseModel):
    """Payload para criar um projeto de corpus."""

    name: str = Field(
        ..., min_length=1, max_length=255, description="Nome do projeto"
    )
    description: Optional[str] = Field(
        None, max_length=5000, description="Descrição do projeto"
    )
    is_knowledge_base: bool = Field(
        False, description="Se True, disponível para consulta workspace-wide"
    )
    scope: str = Field(
        "personal", description="Escopo: personal ou organization"
    )
    max_documents: int = Field(
        10000, ge=1, le=100000, description="Limite máximo de documentos"
    )
    retention_days: Optional[int] = Field(
        None, ge=1, le=3650, description="Dias de retenção (None = indefinido)"
    )
    metadata: Optional[Dict[str, Any]] = Field(
        None, description="Metadados adicionais"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Contratos de TI 2026",
                "description": "Base de contratos de tecnologia para análise",
                "is_knowledge_base": True,
                "scope": "organization",
            }
        }
    )


class CorpusProjectUpdate(BaseModel):
    """Payload para atualizar um projeto de corpus."""

    name: Optional[str] = Field(
        None, min_length=1, max_length=255, description="Nome do projeto"
    )
    description: Optional[str] = Field(
        None, max_length=5000, description="Descrição do projeto"
    )
    is_knowledge_base: Optional[bool] = Field(
        None, description="Se True, disponível para consulta workspace-wide"
    )
    max_documents: Optional[int] = Field(
        None, ge=1, le=100000, description="Limite máximo de documentos"
    )
    retention_days: Optional[int] = Field(
        None, ge=1, le=3650, description="Dias de retenção"
    )
    metadata: Optional[Dict[str, Any]] = Field(
        None, description="Metadados adicionais"
    )


# =============================================================================
# Response
# =============================================================================


class CorpusProjectResponse(BaseModel):
    """Representação completa de um projeto de corpus."""

    id: str = Field(..., description="ID do projeto")
    name: str = Field(..., description="Nome do projeto")
    description: Optional[str] = Field(None, description="Descrição")
    owner_id: str = Field(..., description="ID do proprietário")
    organization_id: Optional[str] = Field(None, description="ID da organização")

    is_knowledge_base: bool = Field(False, description="Se é Knowledge Base")
    scope: str = Field("personal", description="Escopo do projeto")

    collection_name: str = Field(..., description="Nome da coleção nos backends")
    max_documents: int = Field(10000, description="Limite de documentos")
    retention_days: Optional[int] = Field(None, description="Dias de retenção")

    document_count: int = Field(0, description="Total de documentos")
    chunk_count: int = Field(0, description="Total de chunks indexados")
    storage_size_bytes: int = Field(0, description="Tamanho em bytes")
    last_indexed_at: Optional[datetime] = Field(None, description="Última indexação")

    metadata: Optional[Dict[str, Any]] = Field(None, description="Metadados")
    is_active: bool = Field(True, description="Se está ativo")

    created_at: datetime = Field(..., description="Data de criação")
    updated_at: datetime = Field(..., description="Data de atualização")

    model_config = ConfigDict(from_attributes=True)


class CorpusProjectListResponse(BaseModel):
    """Lista paginada de projetos de corpus."""

    items: List[CorpusProjectResponse] = Field(default_factory=list)
    total: int = Field(0, description="Total de projetos")
    page: int = Field(1, description="Página atual")
    per_page: int = Field(20, description="Itens por página")

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# Documents
# =============================================================================


class CorpusProjectDocumentAdd(BaseModel):
    """Payload para adicionar documentos a um projeto."""

    document_ids: List[str] = Field(
        ..., min_length=1, max_length=100,
        description="IDs dos documentos a adicionar"
    )
    folder_path: Optional[str] = Field(
        None, max_length=1024,
        description="Caminho da pasta virtual (ex: 'Contratos/2026')"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "document_ids": ["doc-123", "doc-456"],
                "folder_path": "Contratos/2026"
            }
        }
    )


class CorpusProjectDocumentResponse(BaseModel):
    """Resposta de um documento no projeto."""

    id: str = Field(..., description="ID da associação")
    project_id: str = Field(..., description="ID do projeto")
    document_id: str = Field(..., description="ID do documento")
    document_name: Optional[str] = Field(None, description="Nome do documento")
    folder_path: Optional[str] = Field(None, description="Caminho da pasta virtual")
    status: str = Field("pending", description="Status da ingestão")
    ingested_at: Optional[datetime] = Field(None, description="Data da ingestão")
    error_message: Optional[str] = Field(None, description="Mensagem de erro")
    created_at: datetime = Field(..., description="Data de adição")

    model_config = ConfigDict(from_attributes=True)


class CorpusProjectDocumentAddResponse(BaseModel):
    """Resposta da adição de documentos ao projeto."""

    added: int = Field(0, description="Documentos adicionados")
    skipped: int = Field(0, description="Documentos ignorados (já existem)")
    errors: List[Dict[str, str]] = Field(
        default_factory=list, description="Erros encontrados"
    )


# =============================================================================
# Share
# =============================================================================


class CorpusProjectShareCreate(BaseModel):
    """Payload para compartilhar um projeto."""

    shared_with_user_id: Optional[str] = Field(
        None, description="ID do usuário para compartilhar"
    )
    shared_with_org_id: Optional[str] = Field(
        None, description="ID da organização para compartilhar"
    )
    permission: str = Field(
        "view", description="Permissão: view, edit, admin"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "shared_with_user_id": "user-123",
                "permission": "edit"
            }
        }
    )


class CorpusProjectShareResponse(BaseModel):
    """Representação de um compartilhamento."""

    id: str = Field(..., description="ID do compartilhamento")
    project_id: str = Field(..., description="ID do projeto")
    shared_with_user_id: Optional[str] = Field(None)
    shared_with_org_id: Optional[str] = Field(None)
    permission: str = Field("view")
    created_at: datetime = Field(..., description="Data do compartilhamento")

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# Transfer
# =============================================================================


class CorpusProjectTransferRequest(BaseModel):
    """Payload para transferir propriedade de um projeto."""

    new_owner_id: str = Field(
        ..., description="ID do novo proprietário"
    )


# =============================================================================
# Folders
# =============================================================================


class FolderNode(BaseModel):
    """Nó da árvore de pastas."""

    name: str = Field(..., description="Nome da pasta")
    path: str = Field(..., description="Caminho completo da pasta")
    document_count: int = Field(0, description="Quantidade de documentos nesta pasta")
    children: List["FolderNode"] = Field(default_factory=list, description="Sub-pastas")

    model_config = ConfigDict(from_attributes=True)


class FolderTreeResponse(BaseModel):
    """Árvore de pastas de um projeto."""

    project_id: str = Field(..., description="ID do projeto")
    folders: List[FolderNode] = Field(default_factory=list, description="Pastas raiz")
    total_folders: int = Field(0, description="Total de pastas")

    model_config = ConfigDict(from_attributes=True)


class MoveDocumentRequest(BaseModel):
    """Payload para mover documento entre pastas."""

    folder_path: Optional[str] = Field(
        None, max_length=1024,
        description="Novo caminho de pasta (None = raiz)"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "folder_path": "Contratos/2026/Janeiro"
            }
        }
    )


class CreateFolderRequest(BaseModel):
    """Payload para criar uma pasta."""

    folder_path: str = Field(
        ..., min_length=1, max_length=1024,
        description="Caminho da pasta a criar (ex: 'Contratos/2026')"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "folder_path": "Contratos/2026/Janeiro"
            }
        }
    )
