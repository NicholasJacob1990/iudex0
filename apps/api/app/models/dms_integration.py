"""
Modelo de Integração com Sistemas de Gestão Documental (DMS)

Suporta Google Drive, SharePoint, OneDrive e iManage via OAuth2.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, JSON, String, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.time_utils import utcnow


class DMSIntegration(Base):
    __tablename__ = "dms_integrations"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    org_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("organizations.id"), nullable=True, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # "google_drive", "sharepoint", "onedrive", "imanage"
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    credentials_encrypted: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # JSON criptografado com tokens OAuth
    root_folder_id: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    sync_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # Status da conexão: connected, expired, error, disconnected
    connection_status: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True, server_default="connected"
    )
    # Metadados específicos do provider (ex: iManage server URL, library name)
    provider_metadata: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )
