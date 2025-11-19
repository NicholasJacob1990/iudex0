"""
Modelos de Biblioteca
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import String, DateTime, JSON, Boolean, Text, Enum as SQLEnum, ForeignKey
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

