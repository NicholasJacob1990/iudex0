"""
Modelos de Biblioteca
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import String, DateTime, JSON, Boolean, Text, Integer, Enum as SQLEnum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
import enum

from app.core.database import Base


class LibraryItemType(str, enum.Enum):
    DOCUMENT = "DOCUMENT"
    MODEL = "MODEL"
    PROMPT = "PROMPT"
    JURISPRUDENCE = "JURISPRUDENCE"
    LEGISLATION = "LEGISLATION"
    LIBRARIAN = "LIBRARIAN"


class LibraryItem(Base):
    __tablename__ = "library_items"
    
    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False, index=True)
    
    type: Mapped[LibraryItemType] = mapped_column(SQLEnum(LibraryItemType), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    icon: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    tags: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    folder_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    resource_id: Mapped[str] = mapped_column(String, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    is_shared: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    shared_with: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )
    
    def __repr__(self) -> str:
        return f"<LibraryItem(id={self.id}, name={self.name}, type={self.type})>"


class Folder(Base):
    __tablename__ = "folders"
    
    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False, index=True)
    
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    parent_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    type: Mapped[LibraryItemType] = mapped_column(SQLEnum(LibraryItemType), nullable=False)
    icon: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    color: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    is_shared: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )
    
    def __repr__(self) -> str:
        return f"<Folder(id={self.id}, name={self.name})>"


class Librarian(Base):
    __tablename__ = "librarians"
    
    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False, index=True)
    
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    icon: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    resources: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    
    is_shared: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    shared_with: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )
    
    def __repr__(self) -> str:
        return f"<Librarian(id={self.id}, name={self.name})>"


class SharePermission(str, enum.Enum):
    VIEW = "VIEW"
    EDIT = "EDIT"


class ShareStatus(str, enum.Enum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class Share(Base):
    """Modelo para gerenciar compartilhamentos com ACL completo"""
    __tablename__ = "shares"
    
    id: Mapped[str] = mapped_column(String, primary_key=True)
    resource_type: Mapped[str] = mapped_column(String, nullable=False)  # library_item, librarian, folder
    resource_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    
    owner_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False, index=True)
    shared_with_user_id: Mapped[Optional[str]] = mapped_column(String, ForeignKey("users.id"), nullable=True, index=True)
    shared_with_email: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    permission: Mapped[SharePermission] = mapped_column(SQLEnum(SharePermission), nullable=False)
    status: Mapped[ShareStatus] = mapped_column(SQLEnum(ShareStatus), default=ShareStatus.PENDING, nullable=False)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )
    accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    def __repr__(self) -> str:
        return f"<Share(id={self.id}, resource={self.resource_type}:{self.resource_id}, permission={self.permission})>"

