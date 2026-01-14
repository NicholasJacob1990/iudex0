"""
Modelos de Chat e Mensagens
"""

from datetime import datetime
from app.core.time_utils import utcnow
from typing import Optional
from sqlalchemy import String, DateTime, JSON, Boolean, Text, Enum as SQLEnum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
import enum

from app.core.database import Base


class ChatMode(str, enum.Enum):
    CHAT = "CHAT"
    MINUTA = "MINUTA"


class Chat(Base):
    __tablename__ = "chats"
    
    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False, index=True)
    
    title: Mapped[str] = mapped_column(String, nullable=False)
    mode: Mapped[ChatMode] = mapped_column(
        SQLEnum(ChatMode),
        default=ChatMode.CHAT,
        nullable=False
    )
    
    context: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
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
        return f"<Chat(id={self.id}, title={self.title}, mode={self.mode})>"


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    
    id: Mapped[str] = mapped_column(String, primary_key=True)
    chat_id: Mapped[str] = mapped_column(String, ForeignKey("chats.id"), nullable=False, index=True)
    
    role: Mapped[str] = mapped_column(String, nullable=False)  # user, assistant, system
    content: Mapped[str] = mapped_column(Text, nullable=False)
    
    attachments: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    thinking: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    msg_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow,
        nullable=False
    )
    
    def __repr__(self) -> str:
        return f"<ChatMessage(id={self.id}, chat_id={self.chat_id}, role={self.role})>"
