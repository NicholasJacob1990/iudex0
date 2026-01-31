"""
ConversationSummary - Modelo para armazenar resumos compactados de conversas.

Este modelo é usado pelo sistema de compactação de contexto para:
- Armazenar resumos de conversas longas
- Rastrear ratio de compressão
- Permitir reconstrução do contexto quando necessário
"""

from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Integer, Float, Index, JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
import uuid
from app.core.time_utils import utcnow
from app.core.database import Base


class ConversationSummary(Base):
    """
    Armazena resumos compactados de conversas.

    Quando o contexto de uma conversa fica muito longo, o sistema gera
    um resumo que preserva as informações essenciais enquanto reduz
    o número de tokens.

    Exemplos de uso:
    - Chat com 50 mensagens -> resumo de 5000 tokens para 1000 tokens
    - Preserva decisões importantes, citações, e pontos-chave
    - Permite múltiplos resumos sequenciais conforme conversa cresce
    """
    __tablename__ = "conversation_summaries"

    # SQLite (dev) não suporta JSONB; usar JSON genérico fora do Postgres.
    _JSON_COMPAT = JSON().with_variant(JSONB, "postgresql")

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    chat_id = Column(String, ForeignKey("chats.id", ondelete="CASCADE"), nullable=False, index=True)

    # Range de mensagens cobertas pelo resumo
    from_message_id = Column(String, ForeignKey("chat_messages.id", ondelete="SET NULL"), nullable=True)
    to_message_id = Column(String, ForeignKey("chat_messages.id", ondelete="SET NULL"), nullable=True)

    # Índices numéricos das mensagens (backup caso messages sejam deletadas)
    from_message_index = Column(Integer, nullable=True)
    to_message_index = Column(Integer, nullable=True)

    # Conteúdo do resumo
    summary_text = Column(Text, nullable=False)

    # Métricas de compressão
    tokens_original = Column(Integer, nullable=False, default=0)
    tokens_compressed = Column(Integer, nullable=False, default=0)

    # Nota: compression_ratio calculado dinamicamente via property
    # PostgreSQL não suporta well computed columns em alguns casos

    # Metadados da compactação
    compaction_metadata = Column(_JSON_COMPAT, default=dict)
    # Estrutura esperada:
    # {
    #   "model_used": "claude-4-sonnet",
    #   "key_topics": ["citações", "decisões", "pedidos"],
    #   "preserved_citations": [...],
    #   "summary_version": 1
    # }

    # Qualidade do resumo (0-1, avaliado por LLM ou feedback)
    quality_score = Column(Float, nullable=True)

    # Se este resumo foi validado pelo usuário
    user_validated = Column(String, nullable=True)  # "approved", "rejected", None

    # Timestamps
    created_at = Column(DateTime, default=utcnow, nullable=False)

    # Relacionamentos
    chat = relationship("Chat", backref="summaries")

    # Índices
    __table_args__ = (
        Index('idx_summaries_chat', 'chat_id'),
        Index('idx_summaries_created', 'created_at'),
    )

    @property
    def compression_ratio(self) -> float:
        """Calcula ratio de compressão (tokens_compressed / tokens_original)."""
        if self.tokens_original and self.tokens_original > 0:
            return self.tokens_compressed / self.tokens_original
        return 0.0

    @property
    def tokens_saved(self) -> int:
        """Calcula tokens economizados."""
        return self.tokens_original - self.tokens_compressed

    @property
    def savings_percent(self) -> float:
        """Calcula percentual de economia."""
        if self.tokens_original and self.tokens_original > 0:
            return (1 - self.compression_ratio) * 100
        return 0.0

    def __repr__(self) -> str:
        return (
            f"<ConversationSummary(id={self.id}, chat_id={self.chat_id}, "
            f"ratio={self.compression_ratio:.2f})>"
        )

    def to_dict(self) -> dict:
        """Converte para dicionário."""
        return {
            "id": self.id,
            "chat_id": self.chat_id,
            "from_message_id": self.from_message_id,
            "to_message_id": self.to_message_id,
            "from_message_index": self.from_message_index,
            "to_message_index": self.to_message_index,
            "summary_text": self.summary_text,
            "tokens_original": self.tokens_original,
            "tokens_compressed": self.tokens_compressed,
            "compression_ratio": self.compression_ratio,
            "tokens_saved": self.tokens_saved,
            "savings_percent": self.savings_percent,
            "quality_score": self.quality_score,
            "user_validated": self.user_validated,
            "compaction_metadata": self.compaction_metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    @classmethod
    def create_summary(
        cls,
        chat_id: str,
        summary_text: str,
        tokens_original: int,
        tokens_compressed: int,
        from_message_id: str = None,
        to_message_id: str = None,
        from_message_index: int = None,
        to_message_index: int = None,
        metadata: dict = None,
    ) -> "ConversationSummary":
        """
        Factory method para criar um resumo de conversa.

        Args:
            chat_id: ID do chat
            summary_text: Texto do resumo
            tokens_original: Tokens antes da compactação
            tokens_compressed: Tokens após compactação
            from_message_id: ID da primeira mensagem coberta
            to_message_id: ID da última mensagem coberta
            from_message_index: Índice da primeira mensagem
            to_message_index: Índice da última mensagem
            metadata: Metadados adicionais

        Returns:
            Nova instância de ConversationSummary
        """
        return cls(
            chat_id=chat_id,
            summary_text=summary_text,
            tokens_original=tokens_original,
            tokens_compressed=tokens_compressed,
            from_message_id=from_message_id,
            to_message_id=to_message_id,
            from_message_index=from_message_index,
            to_message_index=to_message_index,
            compaction_metadata=metadata or {},
        )
