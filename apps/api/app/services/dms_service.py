"""
Serviço DMS — Integração com Google Drive, SharePoint/OneDrive.

Implementa padrão Strategy com providers abstratos e um facade
que despacha para o provider correto.
"""

from __future__ import annotations

import json
import secrets
import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Optional

import httpx
from loguru import logger
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.time_utils import utcnow
from app.models.dms_integration import DMSIntegration
from app.schemas.dms import (
    DMSConnectResponse,
    DMSFileItem,
    DMSFileListResponse,
    DMSImportResponse,
    DMSIntegrationResponse,
    DMSProviderInfo,
    DMSSyncResponse,
)


# =============================================================================
# Encryption helpers (Fernet, com fallback para base64 em dev)
# =============================================================================

def _get_fernet():
    """Retorna instância Fernet usando SECRET_KEY (32 bytes, url-safe base64)."""
    try:
        from cryptography.fernet import Fernet
        import base64, hashlib
        # Derivar chave Fernet a partir do SECRET_KEY
        key = base64.urlsafe_b64encode(
            hashlib.sha256(settings.SECRET_KEY.encode()).digest()
        )
        return Fernet(key)
    except ImportError:
        return None


def encrypt_credentials(data: dict) -> str:
    """Encripta dicionário de credenciais para armazenamento."""
    raw = json.dumps(data)
    f = _get_fernet()
    if f:
        return f.encrypt(raw.encode()).decode()
    # Fallback dev: base64
    import base64
    return base64.b64encode(raw.encode()).decode()


def decrypt_credentials(encrypted: str) -> dict:
    """Decripta credenciais armazenadas."""
    f = _get_fernet()
    if f:
        raw = f.decrypt(encrypted.encode()).decode()
        return json.loads(raw)
    import base64
    raw = base64.b64decode(encrypted.encode()).decode()
    return json.loads(raw)


# =============================================================================
# Abstract DMS Provider
# =============================================================================

class DMSProvider(ABC):
    """Interface base para providers DMS."""

    provider_id: str
    provider_name: str

    @abstractmethod
    def get_auth_url(self, state: str, redirect_uri: str) -> str:
        """Retorna URL de autorização OAuth2."""
        ...

    @abstractmethod
    async def exchange_code(self, code: str, redirect_uri: str) -> dict:
        """Troca authorization code por tokens. Retorna dict com tokens."""
        ...

    @abstractmethod
    async def refresh_token(self, credentials: dict) -> dict:
        """Renova access_token usando refresh_token. Retorna credentials atualizados."""
        ...

    @abstractmethod
    async def list_files(
        self,
        credentials: dict,
        folder_id: Optional[str] = None,
        page_token: Optional[str] = None,
        query: Optional[str] = None,
    ) -> DMSFileListResponse:
        """Lista arquivos em uma pasta."""
        ...

    @abstractmethod
    async def download_file(self, credentials: dict, file_id: str) -> tuple[bytes, str, str]:
        """Baixa arquivo. Retorna (conteúdo, nome, mime_type)."""
        ...

    @abstractmethod
    async def get_file_metadata(self, credentials: dict, file_id: str) -> DMSFileItem:
        """Retorna metadados de um arquivo."""
        ...

    async def search_files(
        self, credentials: dict, query: str, page_token: Optional[str] = None
    ) -> DMSFileListResponse:
        """Busca arquivos por query. Default implementa via list_files."""
        return await self.list_files(credentials, query=query, page_token=page_token)


# =============================================================================
# Google Drive Provider
# =============================================================================

class GoogleDriveProvider(DMSProvider):
    """Provider para Google Drive usando google-api-python-client."""

    provider_id = "google_drive"
    provider_name = "Google Drive"

    SCOPES = [
        "https://www.googleapis.com/auth/drive.readonly",
        "https://www.googleapis.com/auth/drive.metadata.readonly",
    ]
    AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    TOKEN_URL = "https://oauth2.googleapis.com/token"

    @property
    def client_id(self) -> str:
        return getattr(settings, "GOOGLE_DRIVE_CLIENT_ID", "") or ""

    @property
    def client_secret(self) -> str:
        return getattr(settings, "GOOGLE_DRIVE_CLIENT_SECRET", "") or ""

    def get_auth_url(self, state: str, redirect_uri: str) -> str:
        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(self.SCOPES),
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
        qs = "&".join(f"{k}={httpx.URL('', params={k: v}).params}" for k, v in params.items())
        # Construir URL manualmente para evitar encoding duplo
        from urllib.parse import urlencode
        return f"{self.AUTH_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str, redirect_uri: str) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self.TOKEN_URL,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": redirect_uri,
                },
            )
            resp.raise_for_status()
            tokens = resp.json()
            return {
                "access_token": tokens["access_token"],
                "refresh_token": tokens.get("refresh_token", ""),
                "expires_at": utcnow().timestamp() + tokens.get("expires_in", 3600),
                "token_type": tokens.get("token_type", "Bearer"),
            }

    async def refresh_token(self, credentials: dict) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self.TOKEN_URL,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "refresh_token": credentials["refresh_token"],
                    "grant_type": "refresh_token",
                },
            )
            resp.raise_for_status()
            tokens = resp.json()
            credentials["access_token"] = tokens["access_token"]
            credentials["expires_at"] = utcnow().timestamp() + tokens.get("expires_in", 3600)
            return credentials

    def _headers(self, credentials: dict) -> dict:
        return {"Authorization": f"Bearer {credentials['access_token']}"}

    async def _ensure_valid_token(self, credentials: dict) -> dict:
        """Renova token se expirado."""
        expires_at = credentials.get("expires_at", 0)
        if utcnow().timestamp() > expires_at - 60:
            credentials = await self.refresh_token(credentials)
        return credentials

    async def list_files(
        self,
        credentials: dict,
        folder_id: Optional[str] = None,
        page_token: Optional[str] = None,
        query: Optional[str] = None,
    ) -> DMSFileListResponse:
        credentials = await self._ensure_valid_token(credentials)
        q_parts = ["trashed = false"]
        if folder_id:
            q_parts.append(f"'{folder_id}' in parents")
        if query:
            q_parts.append(f"name contains '{query}'")

        params: dict[str, Any] = {
            "q": " and ".join(q_parts),
            "fields": "nextPageToken,files(id,name,mimeType,size,modifiedTime,parents,webViewLink)",
            "pageSize": "50",
            "orderBy": "folder,name",
        }
        if page_token:
            params["pageToken"] = page_token

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://www.googleapis.com/drive/v3/files",
                headers=self._headers(credentials),
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()

        files = []
        for f in data.get("files", []):
            files.append(
                DMSFileItem(
                    id=f["id"],
                    name=f["name"],
                    mime_type=f.get("mimeType", ""),
                    size=int(f["size"]) if f.get("size") else None,
                    is_folder=f.get("mimeType") == "application/vnd.google-apps.folder",
                    modified_at=f.get("modifiedTime"),
                    parent_id=f.get("parents", [None])[0] if f.get("parents") else None,
                    web_url=f.get("webViewLink"),
                )
            )

        return DMSFileListResponse(
            files=files,
            folder_id=folder_id,
            next_page_token=data.get("nextPageToken"),
        )

    async def download_file(self, credentials: dict, file_id: str) -> tuple[bytes, str, str]:
        credentials = await self._ensure_valid_token(credentials)
        # Obter metadados primeiro
        meta = await self.get_file_metadata(credentials, file_id)

        # Google Docs nativos precisam ser exportados
        export_mimes = {
            "application/vnd.google-apps.document": "application/pdf",
            "application/vnd.google-apps.spreadsheet": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/vnd.google-apps.presentation": "application/pdf",
        }

        async with httpx.AsyncClient() as client:
            if meta.mime_type in export_mimes:
                export_mime = export_mimes[meta.mime_type]
                resp = await client.get(
                    f"https://www.googleapis.com/drive/v3/files/{file_id}/export",
                    headers=self._headers(credentials),
                    params={"mimeType": export_mime},
                )
            else:
                resp = await client.get(
                    f"https://www.googleapis.com/drive/v3/files/{file_id}",
                    headers=self._headers(credentials),
                    params={"alt": "media"},
                )
            resp.raise_for_status()

        return resp.content, meta.name, meta.mime_type

    async def get_file_metadata(self, credentials: dict, file_id: str) -> DMSFileItem:
        credentials = await self._ensure_valid_token(credentials)
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"https://www.googleapis.com/drive/v3/files/{file_id}",
                headers=self._headers(credentials),
                params={
                    "fields": "id,name,mimeType,size,modifiedTime,parents,webViewLink"
                },
            )
            resp.raise_for_status()
            f = resp.json()

        return DMSFileItem(
            id=f["id"],
            name=f["name"],
            mime_type=f.get("mimeType", ""),
            size=int(f["size"]) if f.get("size") else None,
            is_folder=f.get("mimeType") == "application/vnd.google-apps.folder",
            modified_at=f.get("modifiedTime"),
            parent_id=f.get("parents", [None])[0] if f.get("parents") else None,
            web_url=f.get("webViewLink"),
        )


# =============================================================================
# SharePoint / OneDrive Provider (Microsoft Graph API)
# =============================================================================

class SharePointProvider(DMSProvider):
    """Provider para SharePoint e OneDrive via Microsoft Graph API."""

    provider_id = "sharepoint"
    provider_name = "SharePoint / OneDrive"

    SCOPES = ["Files.Read.All", "Sites.Read.All", "offline_access"]
    AUTH_URL_TEMPLATE = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize"
    TOKEN_URL_TEMPLATE = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
    GRAPH_BASE = "https://graph.microsoft.com/v1.0"

    @property
    def client_id(self) -> str:
        return getattr(settings, "MICROSOFT_CLIENT_ID", "") or ""

    @property
    def client_secret(self) -> str:
        return getattr(settings, "MICROSOFT_CLIENT_SECRET", "") or ""

    @property
    def tenant_id(self) -> str:
        return getattr(settings, "MICROSOFT_TENANT_ID", "") or "common"

    @property
    def auth_url(self) -> str:
        return self.AUTH_URL_TEMPLATE.format(tenant=self.tenant_id)

    @property
    def token_url(self) -> str:
        return self.TOKEN_URL_TEMPLATE.format(tenant=self.tenant_id)

    def get_auth_url(self, state: str, redirect_uri: str) -> str:
        from urllib.parse import urlencode
        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(self.SCOPES),
            "state": state,
            "response_mode": "query",
        }
        return f"{self.auth_url}?{urlencode(params)}"

    async def exchange_code(self, code: str, redirect_uri: str) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self.token_url,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": redirect_uri,
                    "scope": " ".join(self.SCOPES),
                },
            )
            resp.raise_for_status()
            tokens = resp.json()
            return {
                "access_token": tokens["access_token"],
                "refresh_token": tokens.get("refresh_token", ""),
                "expires_at": utcnow().timestamp() + tokens.get("expires_in", 3600),
                "token_type": tokens.get("token_type", "Bearer"),
            }

    async def refresh_token(self, credentials: dict) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self.token_url,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "refresh_token": credentials["refresh_token"],
                    "grant_type": "refresh_token",
                    "scope": " ".join(self.SCOPES),
                },
            )
            resp.raise_for_status()
            tokens = resp.json()
            credentials["access_token"] = tokens["access_token"]
            credentials["expires_at"] = utcnow().timestamp() + tokens.get("expires_in", 3600)
            if tokens.get("refresh_token"):
                credentials["refresh_token"] = tokens["refresh_token"]
            return credentials

    def _headers(self, credentials: dict) -> dict:
        return {"Authorization": f"Bearer {credentials['access_token']}"}

    async def _ensure_valid_token(self, credentials: dict) -> dict:
        expires_at = credentials.get("expires_at", 0)
        if utcnow().timestamp() > expires_at - 60:
            credentials = await self.refresh_token(credentials)
        return credentials

    async def list_files(
        self,
        credentials: dict,
        folder_id: Optional[str] = None,
        page_token: Optional[str] = None,
        query: Optional[str] = None,
    ) -> DMSFileListResponse:
        credentials = await self._ensure_valid_token(credentials)

        if query:
            url = f"{self.GRAPH_BASE}/me/drive/root/search(q='{query}')"
        elif folder_id:
            url = f"{self.GRAPH_BASE}/me/drive/items/{folder_id}/children"
        else:
            url = f"{self.GRAPH_BASE}/me/drive/root/children"

        params: dict[str, str] = {"$top": "50"}
        if page_token:
            # Microsoft usa @odata.nextLink como URL completa
            url = page_token
            params = {}

        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=self._headers(credentials), params=params)
            resp.raise_for_status()
            data = resp.json()

        files = []
        for item in data.get("value", []):
            is_folder = "folder" in item
            files.append(
                DMSFileItem(
                    id=item["id"],
                    name=item["name"],
                    mime_type=item.get("file", {}).get("mimeType", "application/octet-stream")
                    if not is_folder
                    else "application/vnd.ms-folder",
                    size=item.get("size"),
                    is_folder=is_folder,
                    modified_at=item.get("lastModifiedDateTime"),
                    parent_id=item.get("parentReference", {}).get("id"),
                    web_url=item.get("webUrl"),
                )
            )

        return DMSFileListResponse(
            files=files,
            folder_id=folder_id,
            next_page_token=data.get("@odata.nextLink"),
        )

    async def download_file(self, credentials: dict, file_id: str) -> tuple[bytes, str, str]:
        credentials = await self._ensure_valid_token(credentials)
        meta = await self.get_file_metadata(credentials, file_id)

        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.get(
                f"{self.GRAPH_BASE}/me/drive/items/{file_id}/content",
                headers=self._headers(credentials),
            )
            resp.raise_for_status()

        return resp.content, meta.name, meta.mime_type

    async def get_file_metadata(self, credentials: dict, file_id: str) -> DMSFileItem:
        credentials = await self._ensure_valid_token(credentials)
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.GRAPH_BASE}/me/drive/items/{file_id}",
                headers=self._headers(credentials),
            )
            resp.raise_for_status()
            item = resp.json()

        is_folder = "folder" in item
        return DMSFileItem(
            id=item["id"],
            name=item["name"],
            mime_type=item.get("file", {}).get("mimeType", "application/octet-stream")
            if not is_folder
            else "application/vnd.ms-folder",
            size=item.get("size"),
            is_folder=is_folder,
            modified_at=item.get("lastModifiedDateTime"),
            parent_id=item.get("parentReference", {}).get("id"),
            web_url=item.get("webUrl"),
        )


# =============================================================================
# Provider Registry
# =============================================================================

PROVIDERS: dict[str, DMSProvider] = {
    "google_drive": GoogleDriveProvider(),
    "sharepoint": SharePointProvider(),
    "onedrive": SharePointProvider(),  # OneDrive usa mesma Graph API
}


def get_provider(provider_id: str) -> DMSProvider:
    provider = PROVIDERS.get(provider_id)
    if not provider:
        raise ValueError(f"Provider DMS desconhecido: {provider_id}")
    return provider


# =============================================================================
# DMS Service (Facade)
# =============================================================================

class DMSService:
    """Facade que gerencia integrações DMS e despacha para providers."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # -------------------------------------------------------------------------
    # Providers
    # -------------------------------------------------------------------------

    @staticmethod
    def list_providers() -> list[DMSProviderInfo]:
        return [
            DMSProviderInfo(
                id="google_drive",
                name="Google Drive",
                description="Acesse e importe documentos do Google Drive",
                icon="cloud",
                supports_sync=True,
            ),
            DMSProviderInfo(
                id="sharepoint",
                name="SharePoint",
                description="Acesse documentos do SharePoint da sua organização",
                icon="building-2",
                supports_sync=True,
            ),
            DMSProviderInfo(
                id="onedrive",
                name="OneDrive",
                description="Acesse e importe documentos do OneDrive",
                icon="hard-drive",
                supports_sync=True,
            ),
            DMSProviderInfo(
                id="imanage",
                name="iManage",
                description="Conecte ao iManage Work para acessar documentos do escritório",
                icon="briefcase",
                supports_sync=True,
            ),
        ]

    async def find_integration_by_provider(
        self, user_id: str, provider: str
    ) -> Optional[DMSIntegration]:
        """Encontra integração ativa do usuário para um provider."""
        result = await self.db.execute(
            select(DMSIntegration)
            .where(
                DMSIntegration.user_id == user_id,
                DMSIntegration.provider == provider,
            )
            .order_by(DMSIntegration.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    # -------------------------------------------------------------------------
    # OAuth Connect
    # -------------------------------------------------------------------------

    def start_oauth(self, provider_id: str, redirect_uri: str) -> DMSConnectResponse:
        provider = get_provider(provider_id)
        state = secrets.token_urlsafe(32)
        auth_url = provider.get_auth_url(state=state, redirect_uri=redirect_uri)
        return DMSConnectResponse(auth_url=auth_url, state=state)

    async def handle_callback(
        self,
        provider_id: str,
        code: str,
        user_id: str,
        org_id: Optional[str],
        display_name: str,
        redirect_uri: str,
    ) -> DMSIntegrationResponse:
        """Processa callback OAuth e cria integração."""
        provider = get_provider(provider_id)
        tokens = await provider.exchange_code(code=code, redirect_uri=redirect_uri)

        integration = DMSIntegration(
            id=str(uuid.uuid4()),
            org_id=org_id,
            user_id=user_id,
            provider=provider_id,
            display_name=display_name or provider.provider_name,
            credentials_encrypted=encrypt_credentials(tokens),
            sync_enabled=False,
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        self.db.add(integration)
        await self.db.commit()
        await self.db.refresh(integration)

        logger.info(f"DMS integration criada: {integration.id} ({provider_id}) para user {user_id}")
        return DMSIntegrationResponse.model_validate(integration)

    # -------------------------------------------------------------------------
    # CRUD
    # -------------------------------------------------------------------------

    async def list_integrations(self, user_id: str) -> list[DMSIntegrationResponse]:
        result = await self.db.execute(
            select(DMSIntegration)
            .where(DMSIntegration.user_id == user_id)
            .order_by(DMSIntegration.created_at.desc())
        )
        integrations = result.scalars().all()
        return [DMSIntegrationResponse.model_validate(i) for i in integrations]

    async def get_integration(self, integration_id: str, user_id: str) -> DMSIntegration:
        result = await self.db.execute(
            select(DMSIntegration).where(
                DMSIntegration.id == integration_id,
                DMSIntegration.user_id == user_id,
            )
        )
        integration = result.scalar_one_or_none()
        if not integration:
            raise ValueError("Integração DMS não encontrada")
        return integration

    async def disconnect(self, integration_id: str, user_id: str) -> None:
        await self.db.execute(
            delete(DMSIntegration).where(
                DMSIntegration.id == integration_id,
                DMSIntegration.user_id == user_id,
            )
        )
        await self.db.commit()
        logger.info(f"DMS integration removida: {integration_id}")

    # -------------------------------------------------------------------------
    # File operations
    # -------------------------------------------------------------------------

    async def _get_credentials(self, integration: DMSIntegration) -> dict:
        """Decripta e retorna credenciais, renovando se necessário."""
        creds = decrypt_credentials(integration.credentials_encrypted)
        provider = get_provider(integration.provider)

        # Verificar se precisa renovar
        expires_at = creds.get("expires_at", 0)
        if utcnow().timestamp() > expires_at - 60:
            creds = await provider.refresh_token(creds)
            integration.credentials_encrypted = encrypt_credentials(creds)
            integration.updated_at = utcnow()
            await self.db.commit()

        return creds

    async def list_files(
        self,
        integration_id: str,
        user_id: str,
        folder_id: Optional[str] = None,
        page_token: Optional[str] = None,
        query: Optional[str] = None,
    ) -> DMSFileListResponse:
        integration = await self.get_integration(integration_id, user_id)
        creds = await self._get_credentials(integration)
        provider = get_provider(integration.provider)
        return await provider.list_files(
            creds,
            folder_id=folder_id or integration.root_folder_id,
            page_token=page_token,
            query=query,
        )

    async def import_files(
        self,
        integration_id: str,
        user_id: str,
        file_ids: list[str],
        target_corpus_project_id: Optional[str] = None,
    ) -> DMSImportResponse:
        """Importa arquivos do DMS para o Corpus local."""
        integration = await self.get_integration(integration_id, user_id)
        creds = await self._get_credentials(integration)
        provider = get_provider(integration.provider)

        imported_ids: list[str] = []
        errors: list[str] = []

        for file_id in file_ids:
            try:
                content, name, mime_type = await provider.download_file(creds, file_id)
                # Salvar como documento no storage local
                doc_id = str(uuid.uuid4())
                storage_path = f"{settings.LOCAL_STORAGE_PATH}/dms_imports/{user_id}/{doc_id}"

                import os
                os.makedirs(os.path.dirname(storage_path), exist_ok=True)

                # Determinar extensão
                ext_map = {
                    "application/pdf": ".pdf",
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
                    "text/plain": ".txt",
                    "text/html": ".html",
                }
                ext = ext_map.get(mime_type, "")
                file_path = f"{storage_path}{ext}"

                with open(file_path, "wb") as f:
                    f.write(content)

                imported_ids.append(doc_id)
                logger.info(f"DMS import: {name} -> {doc_id}")

            except Exception as e:
                logger.error(f"Erro ao importar arquivo {file_id}: {e}")
                errors.append(f"{file_id}: {str(e)}")

        return DMSImportResponse(
            imported_count=len(imported_ids),
            errors=errors,
            document_ids=imported_ids,
        )

    async def trigger_sync(
        self,
        integration_id: str,
        user_id: str,
        folder_ids: Optional[list[str]] = None,
    ) -> DMSSyncResponse:
        """Trigger sync de arquivos do DMS."""
        integration = await self.get_integration(integration_id, user_id)

        if not integration.sync_enabled:
            return DMSSyncResponse(
                status="error",
                message="Sincronização não está habilitada para esta integração",
            )

        # Em produção, isso seria despachado para uma task Celery
        integration.last_sync_at = utcnow()
        integration.updated_at = utcnow()
        await self.db.commit()

        logger.info(f"DMS sync triggered: {integration_id}")
        return DMSSyncResponse(
            status="started",
            message="Sincronização iniciada. Você será notificado quando concluir.",
        )
