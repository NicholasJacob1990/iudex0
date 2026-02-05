"""
TableChatMessage Model — Chat history for Review Table "Ask Table" feature.

Allows users to ask natural language questions about extracted data in Review Tables.
Inspired by Harvey AI's "Ask Harvey" feature for data interrogation.
"""

import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Enum as SQLEnum,
    JSON,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.time_utils import utcnow


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class MessageRole(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class QueryType(str, enum.Enum):
    """Tipo de query detectado pela IA."""
    FILTER = "filter"           # "Quais documentos tem X?"
    AGGREGATION = "aggregation"  # "Quantos documentos tem X?"
    COMPARISON = "comparison"    # "Compare X entre documentos"
    SUMMARY = "summary"          # "Resuma os achados"
    SPECIFIC = "specific"        # "O que documento Y diz sobre X?"
    GENERAL = "general"          # Perguntas gerais


# ---------------------------------------------------------------------------
# TableChatMessage
# ---------------------------------------------------------------------------


class TableChatMessage(Base):
    """Mensagem de chat para consultas em Review Tables."""
    __tablename__ = "table_chat_messages"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )

    review_table_id: Mapped[str] = mapped_column(
        String, ForeignKey("review_tables.id", ondelete="CASCADE"),
        nullable=False, index=True
    )

    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id"),
        nullable=False, index=True
    )

    role: Mapped[str] = mapped_column(
        SQLEnum(MessageRole), default=MessageRole.USER, nullable=False,
        doc="Role: user, assistant, system"
    )

    content: Mapped[str] = mapped_column(
        Text, nullable=False,
        doc="Conteudo da mensagem (pergunta ou resposta)"
    )

    # Resultado estruturado para queries que retornam dados
    query_result: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True,
        doc="Resultado estruturado da query (ex: lista de docs, agregacoes)"
    )

    # Tipo de query detectado
    query_type: Mapped[Optional[str]] = mapped_column(
        SQLEnum(QueryType), nullable=True,
        doc="Tipo de query: filter, aggregation, comparison, summary, specific"
    )

    # Documentos referenciados na resposta
    documents_referenced: Mapped[list] = mapped_column(
        JSON, default=list, nullable=False,
        doc="IDs dos documentos citados na resposta"
    )

    # Dica de visualizacao para o frontend
    visualization_hint: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True,
        doc="Sugestao de viz: bar_chart, pie_chart, table, list"
    )

    # Metadados adicionais (tokens usados, modelo, etc.)
    msg_metadata: Mapped[dict] = mapped_column(
        JSON, default=dict, nullable=False,
        doc="Metadados da mensagem: model, tokens, latency_ms"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )

    # Relationships
    review_table = relationship("ReviewTable", backref="chat_messages")
    user = relationship("User", backref="table_chat_messages")

    __table_args__ = (
        Index("ix_table_chat_messages_table_id", "review_table_id"),
        Index("ix_table_chat_messages_user_id", "user_id"),
        Index("ix_table_chat_messages_table_created", "review_table_id", "created_at"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "review_table_id": self.review_table_id,
            "user_id": self.user_id,
            "role": self.role,
            "content": self.content,
            "query_result": self.query_result,
            "query_type": self.query_type,
            "documents_referenced": self.documents_referenced,
            "visualization_hint": self.visualization_hint,
            "metadata": self.msg_metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
