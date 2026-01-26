"""
Modelo de Documento
"""

from datetime import datetime
from app.core.time_utils import utcnow
from typing import Optional
from sqlalchemy import String, Integer, DateTime, JSON, Boolean, Text, Enum as SQLEnum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
import enum

from app.core.database import Base


class DocumentType(str, enum.Enum):
    PDF = "PDF"
    DOCX = "DOCX"
    DOC = "DOC"
    ODT = "ODT"
    TXT = "TXT"
    RTF = "RTF"
    HTML = "HTML"
    IMAGE = "IMAGE"
    AUDIO = "AUDIO"
    VIDEO = "VIDEO"
    ZIP = "ZIP"


class DocumentStatus(str, enum.Enum):
    UPLOADING = "UPLOADING"
    PROCESSING = "PROCESSING"
    READY = "READY"
    ERROR = "ERROR"


class DocumentCategory(str, enum.Enum):
    PROCESSO = "PROCESSO"
    PETICAO = "PETICAO"
    SENTENCA = "SENTENCA"
    ACORDAO = "ACORDAO"
    CONTRATO = "CONTRATO"
    PARECER = "PARECER"
    LEI = "LEI"
    OUTRO = "OUTRO"


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False, index=True)
    case_id: Mapped[Optional[str]] = mapped_column(String, ForeignKey("cases.id"), nullable=True, index=True)

    name: Mapped[str] = mapped_column(String, nullable=False)
    original_name: Mapped[str] = mapped_column(String, nullable=False)
    
    type: Mapped[DocumentType] = mapped_column(SQLEnum(DocumentType), nullable=False)
    category: Mapped[Optional[DocumentCategory]] = mapped_column(
        SQLEnum(DocumentCategory),
        nullable=True
    )
    status: Mapped[DocumentStatus] = mapped_column(
        SQLEnum(DocumentStatus),
        default=DocumentStatus.PROCESSING,
        nullable=False
    )
    
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    url: Mapped[str] = mapped_column(String, nullable=False)
    thumbnail_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    extracted_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    doc_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    tags: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    
    folder_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    is_shared: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    share_token: Mapped[Optional[str]] = mapped_column(String, unique=True, nullable=True, index=True)
    share_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    share_access_level: Mapped[str] = mapped_column(String, default="VIEW", nullable=False) # VIEW, EDIT
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # RAG ingestion tracking
    rag_ingested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    rag_ingested_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    rag_scope: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # global, private, local
    graph_ingested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    graph_ingested_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow,
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow,
        onupdate=utcnow,
        nullable=False
    )
    
    def __repr__(self) -> str:
        return f"<Document(id={self.id}, name={self.name}, status={self.status})>"
