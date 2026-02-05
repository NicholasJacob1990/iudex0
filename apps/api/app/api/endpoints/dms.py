"""
DMS (Document Management System) Endpoints

Integrações com Google Drive, SharePoint e OneDrive para
importação e sincronização de documentos.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.dms import (
    DMSConnectRequest,
    DMSConnectResponse,
    DMSFileListResponse,
    DMSImportRequest,
    DMSImportResponse,
    DMSIntegrationListResponse,
    DMSIntegrationResponse,
    DMSProviderListResponse,
    DMSSyncRequest,
    DMSSyncResponse,
)
from app.services.dms_service import DMSService

router = APIRouter(tags=["dms"])


# =============================================================================
# Dependencies
# =============================================================================


def get_dms_service(db: AsyncSession = Depends(get_db)) -> DMSService:
    """Dependency para obter o serviço DMS."""
    return DMSService(db=db)


# =============================================================================
# Providers
# =============================================================================


@router.get("/providers", response_model=DMSProviderListResponse)
async def list_providers(
    current_user: User = Depends(get_current_user),
) -> DMSProviderListResponse:
    """Lista providers DMS disponíveis."""
    providers = DMSService.list_providers()
    return DMSProviderListResponse(providers=providers)


# =============================================================================
# OAuth Connect
# =============================================================================


@router.post("/connect", response_model=DMSConnectResponse)
async def start_connect(
    request: DMSConnectRequest,
    current_user: User = Depends(get_current_user),
    service: DMSService = Depends(get_dms_service),
) -> DMSConnectResponse:
    """
    Inicia fluxo OAuth para conectar um provider DMS.
    Retorna a URL de autorização para redirecionar o usuário.
    """
    valid_providers = {"google_drive", "sharepoint", "onedrive", "imanage"}
    if request.provider not in valid_providers:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Provider inválido. Use: {', '.join(valid_providers)}",
        )

    redirect_uri = request.redirect_url or getattr(
        settings, "DMS_OAUTH_REDIRECT_URL", ""
    )
    if not redirect_uri:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="DMS_OAUTH_REDIRECT_URL não configurado",
        )

    try:
        return service.start_oauth(
            provider_id=request.provider,
            redirect_uri=redirect_uri,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/callback")
async def oauth_callback(
    code: str = Query(...),
    state: str = Query(...),
    provider: str = Query(...),
    display_name: str = Query(default=""),
    current_user: User = Depends(get_current_user),
    service: DMSService = Depends(get_dms_service),
) -> DMSIntegrationResponse:
    """
    Callback OAuth — processa o código de autorização e cria a integração.

    Nota: Em produção, o state deve ser validado contra o valor
    armazenado em sessão/cache para prevenir CSRF.
    """
    redirect_uri = getattr(settings, "DMS_OAUTH_REDIRECT_URL", "")
    if not redirect_uri:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="DMS_OAUTH_REDIRECT_URL não configurado",
        )

    try:
        integration = await service.handle_callback(
            provider_id=provider,
            code=code,
            user_id=current_user.id,
            org_id=current_user.organization_id,
            display_name=display_name,
            redirect_uri=redirect_uri,
        )
        return integration
    except Exception as e:
        logger.error(f"Erro no callback OAuth DMS: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erro ao conectar provider: {str(e)}",
        )


# =============================================================================
# Provider-specific OAuth Connect (URL param)
# =============================================================================


@router.post("/connect/{provider}", response_model=DMSConnectResponse)
async def start_connect_by_provider(
    provider: str,
    request: DMSConnectRequest = DMSConnectRequest(provider="google_drive"),
    current_user: User = Depends(get_current_user),
    service: DMSService = Depends(get_dms_service),
) -> DMSConnectResponse:
    """
    Inicia fluxo OAuth para um provider específico via URL path.
    Alternativa ao POST /connect com provider no body.
    """
    valid_providers = {"google_drive", "sharepoint", "onedrive", "imanage"}
    if provider not in valid_providers:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Provider inválido. Use: {', '.join(valid_providers)}",
        )

    redirect_uri = request.redirect_url or getattr(
        settings, "DMS_OAUTH_REDIRECT_URL", ""
    )
    if not redirect_uri:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="DMS_OAUTH_REDIRECT_URL não configurado",
        )

    try:
        return service.start_oauth(
            provider_id=provider,
            redirect_uri=redirect_uri,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/callback/{provider}")
async def oauth_callback_by_provider(
    provider: str,
    code: str = Query(...),
    state: str = Query(...),
    display_name: str = Query(default=""),
    current_user: User = Depends(get_current_user),
    service: DMSService = Depends(get_dms_service),
) -> DMSIntegrationResponse:
    """
    Callback OAuth para provider específico via URL path.
    """
    redirect_uri = getattr(settings, "DMS_OAUTH_REDIRECT_URL", "")
    if not redirect_uri:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="DMS_OAUTH_REDIRECT_URL não configurado",
        )

    try:
        integration = await service.handle_callback(
            provider_id=provider,
            code=code,
            user_id=current_user.id,
            org_id=current_user.organization_id,
            display_name=display_name,
            redirect_uri=redirect_uri,
        )
        return integration
    except Exception as e:
        logger.error(f"Erro no callback OAuth DMS ({provider}): {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erro ao conectar provider: {str(e)}",
        )


# =============================================================================
# Integrations CRUD
# =============================================================================


@router.get("/integrations", response_model=DMSIntegrationListResponse)
async def list_integrations(
    current_user: User = Depends(get_current_user),
    service: DMSService = Depends(get_dms_service),
) -> DMSIntegrationListResponse:
    """Lista integrações DMS do usuário."""
    integrations = await service.list_integrations(user_id=current_user.id)
    return DMSIntegrationListResponse(integrations=integrations)


@router.delete(
    "/integrations/{integration_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def disconnect_integration(
    integration_id: str,
    current_user: User = Depends(get_current_user),
    service: DMSService = Depends(get_dms_service),
) -> None:
    """Desconecta uma integração DMS."""
    try:
        await service.disconnect(
            integration_id=integration_id,
            user_id=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


# =============================================================================
# File Operations
# =============================================================================


@router.get("/integrations/{integration_id}/files", response_model=DMSFileListResponse)
async def list_files(
    integration_id: str,
    folder_id: Optional[str] = Query(default=None),
    page_token: Optional[str] = Query(default=None),
    query: Optional[str] = Query(default=None),
    current_user: User = Depends(get_current_user),
    service: DMSService = Depends(get_dms_service),
) -> DMSFileListResponse:
    """Navega arquivos de uma integração DMS."""
    try:
        return await service.list_files(
            integration_id=integration_id,
            user_id=current_user.id,
            folder_id=folder_id,
            page_token=page_token,
            query=query,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Erro ao listar arquivos DMS: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Erro ao acessar o provider DMS. Tente reconectar.",
        )


@router.post(
    "/integrations/{integration_id}/import", response_model=DMSImportResponse
)
async def import_files(
    integration_id: str,
    request: DMSImportRequest,
    current_user: User = Depends(get_current_user),
    service: DMSService = Depends(get_dms_service),
) -> DMSImportResponse:
    """Importa arquivo(s) do DMS para o Corpus."""
    try:
        return await service.import_files(
            integration_id=integration_id,
            user_id=current_user.id,
            file_ids=request.file_ids,
            target_corpus_project_id=request.target_corpus_project_id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Erro ao importar arquivos DMS: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao importar arquivos do DMS",
        )


# =============================================================================
# Provider-level file listing (convenience)
# =============================================================================


@router.get("/{provider}/files", response_model=DMSFileListResponse)
async def list_files_by_provider(
    provider: str,
    path: Optional[str] = Query(default=None, description="Folder path or ID"),
    page_token: Optional[str] = Query(default=None),
    query: Optional[str] = Query(default=None),
    current_user: User = Depends(get_current_user),
    service: DMSService = Depends(get_dms_service),
) -> DMSFileListResponse:
    """
    Lista arquivos de um provider DMS.
    Encontra automaticamente a integração ativa do usuário para o provider.
    """
    integration = await service.find_integration_by_provider(
        user_id=current_user.id,
        provider=provider,
    )
    if not integration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Nenhuma integração ativa para o provider '{provider}'. Conecte primeiro.",
        )

    try:
        return await service.list_files(
            integration_id=integration.id,
            user_id=current_user.id,
            folder_id=path,
            page_token=page_token,
            query=query,
        )
    except Exception as e:
        logger.error(f"Erro ao listar arquivos DMS ({provider}): {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Erro ao acessar o provider DMS. Tente reconectar.",
        )


@router.post("/{provider}/import", response_model=DMSImportResponse)
async def import_files_by_provider(
    provider: str,
    request: DMSImportRequest,
    current_user: User = Depends(get_current_user),
    service: DMSService = Depends(get_dms_service),
) -> DMSImportResponse:
    """
    Importa arquivos de um provider DMS para o corpus.
    Encontra automaticamente a integração ativa do usuário.
    """
    integration = await service.find_integration_by_provider(
        user_id=current_user.id,
        provider=provider,
    )
    if not integration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Nenhuma integração ativa para o provider '{provider}'.",
        )

    try:
        return await service.import_files(
            integration_id=integration.id,
            user_id=current_user.id,
            file_ids=request.file_ids,
            target_corpus_project_id=request.target_corpus_project_id,
        )
    except Exception as e:
        logger.error(f"Erro ao importar arquivos DMS ({provider}): {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao importar arquivos do DMS",
        )


# =============================================================================
# Sync
# =============================================================================


@router.post(
    "/integrations/{integration_id}/sync", response_model=DMSSyncResponse
)
async def trigger_sync(
    integration_id: str,
    request: DMSSyncRequest = DMSSyncRequest(),
    current_user: User = Depends(get_current_user),
    service: DMSService = Depends(get_dms_service),
) -> DMSSyncResponse:
    """Dispara sincronização de arquivos do DMS."""
    try:
        return await service.trigger_sync(
            integration_id=integration_id,
            user_id=current_user.id,
            folder_ids=request.folder_ids,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
