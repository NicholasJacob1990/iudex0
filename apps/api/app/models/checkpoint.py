"""
Checkpoint - Modelo para snapshots de estado do workflow para rewind.

Este modelo estende a funcionalidade de WorkflowState para permitir:
- Snapshots automáticos em pontos-chave do workflow
- Snapshots manuais solicitados pelo usuário
- Snapshots em paradas HIL (human-in-the-loop)
- Restauração (rewind) para estados anteriores
"""

from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Boolean, Enum as SQLEnum, Index, JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
import uuid
import enum
from app.core.time_utils import utcnow
from app.core.database import Base


class SnapshotType(str, enum.Enum):
    """Tipo de snapshot que gerou o checkpoint."""
    AUTO = "auto"      # Automático em pontos-chave (após research, após debate, etc.)
    MANUAL = "manual"  # Solicitado pelo usuário
    HIL = "hil"        # Criado em parada human-in-the-loop


class Checkpoint(Base):
    """
    Armazena snapshots de estado do workflow para permitir rewind.

    Cada checkpoint captura:
    - Estado completo do LangGraph serializado
    - Referência a arquivos/documentos gerados até o momento
    - Metadados sobre o ponto no workflow

    Exemplos de uso:
    - Checkpoint após outline -> permite voltar e refazer outline
    - Checkpoint após research -> permite reprocessar sem refazer pesquisa
    - Checkpoint antes de edição humana -> permite desfazer edição
    """
    __tablename__ = "checkpoints"

    # SQLite (dev) não suporta JSONB; usar JSON genérico fora do Postgres.
    _JSON_COMPAT = JSON().with_variant(JSONB, "postgresql")

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))

    # Referência ao workflow/job
    job_id = Column(String, ForeignKey("workflow_states.id", ondelete="CASCADE"), nullable=False, index=True)

    # Referência opcional à mensagem que gerou o checkpoint
    turn_id = Column(String, ForeignKey("chat_messages.id", ondelete="SET NULL"), nullable=True)

    # Tipo de snapshot
    snapshot_type = Column(SQLEnum(SnapshotType), nullable=False, default=SnapshotType.AUTO)

    # Descrição/label do checkpoint
    description = Column(String(500), nullable=True)

    # Estado completo serializado
    state_snapshot = Column(_JSON_COMPAT, nullable=False, default=dict)
    # Estrutura esperada: DocumentState completo do LangGraph
    # {
    #   "outline": [...],
    #   "research_sources": [...],
    #   "processed_sections": [...],
    #   "current_node": "research",
    #   ...
    # }

    # URI para arquivos/documentos no storage (S3, local, etc.)
    files_snapshot_uri = Column(String(1000), nullable=True)

    # Metadados adicionais
    checkpoint_metadata = Column(_JSON_COMPAT, default=dict)
    # {
    #   "node_name": "research",
    #   "iteration": 3,
    #   "tokens_used": 15000,
    #   "models_active": ["claude-4-sonnet", "gpt-5"]
    # }

    # Se este checkpoint pode ser restaurado
    # (pode ser False se arquivos foram deletados ou estado é inválido)
    is_restorable = Column(Boolean, nullable=False, default=True)

    # Motivo se não restaurável
    non_restorable_reason = Column(Text, nullable=True)

    # Quem criou (user_id ou "system")
    created_by = Column(String, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=utcnow, nullable=False)

    # Relacionamentos
    workflow = relationship("WorkflowState", backref="checkpoints")
    turn = relationship("ChatMessage", backref="checkpoints")

    # Índices
    __table_args__ = (
        Index('idx_checkpoints_job', 'job_id'),
        Index('idx_checkpoints_created', 'created_at'),
        Index('idx_checkpoints_type', 'snapshot_type'),
    )

    def __repr__(self) -> str:
        return (
            f"<Checkpoint(id={self.id}, job_id={self.job_id}, "
            f"type={self.snapshot_type}, restorable={self.is_restorable})>"
        )

    def to_dict(self) -> dict:
        """Converte para dicionário."""
        return {
            "id": self.id,
            "job_id": self.job_id,
            "turn_id": self.turn_id,
            "snapshot_type": self.snapshot_type.value if self.snapshot_type else None,
            "description": self.description,
            "files_snapshot_uri": self.files_snapshot_uri,
            "checkpoint_metadata": self.checkpoint_metadata,
            "is_restorable": self.is_restorable,
            "non_restorable_reason": self.non_restorable_reason,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def to_full_dict(self) -> dict:
        """Converte para dicionário incluindo state_snapshot."""
        result = self.to_dict()
        result["state_snapshot"] = self.state_snapshot
        return result

    @classmethod
    def create_auto_checkpoint(
        cls,
        job_id: str,
        state_snapshot: dict,
        node_name: str,
        description: str = None,
        files_uri: str = None,
        metadata: dict = None,
    ) -> "Checkpoint":
        """
        Factory method para criar checkpoint automático.

        Args:
            job_id: ID do workflow/job
            state_snapshot: Estado completo do LangGraph
            node_name: Nome do node atual
            description: Descrição opcional
            files_uri: URI dos arquivos no storage
            metadata: Metadados adicionais

        Returns:
            Nova instância de Checkpoint
        """
        base_metadata = {"node_name": node_name}
        if metadata:
            base_metadata.update(metadata)

        return cls(
            job_id=job_id,
            snapshot_type=SnapshotType.AUTO,
            description=description or f"Checkpoint automático após {node_name}",
            state_snapshot=state_snapshot,
            files_snapshot_uri=files_uri,
            checkpoint_metadata=base_metadata,
            is_restorable=True,
            created_by="system",
        )

    @classmethod
    def create_manual_checkpoint(
        cls,
        job_id: str,
        state_snapshot: dict,
        user_id: str,
        description: str,
        turn_id: str = None,
        files_uri: str = None,
        metadata: dict = None,
    ) -> "Checkpoint":
        """
        Factory method para criar checkpoint manual.

        Args:
            job_id: ID do workflow/job
            state_snapshot: Estado completo do LangGraph
            user_id: ID do usuário que solicitou
            description: Descrição do checkpoint
            turn_id: ID da mensagem relacionada
            files_uri: URI dos arquivos no storage
            metadata: Metadados adicionais

        Returns:
            Nova instância de Checkpoint
        """
        return cls(
            job_id=job_id,
            turn_id=turn_id,
            snapshot_type=SnapshotType.MANUAL,
            description=description,
            state_snapshot=state_snapshot,
            files_snapshot_uri=files_uri,
            checkpoint_metadata=metadata or {},
            is_restorable=True,
            created_by=user_id,
        )

    @classmethod
    def create_hil_checkpoint(
        cls,
        job_id: str,
        state_snapshot: dict,
        turn_id: str,
        hil_reason: str,
        files_uri: str = None,
        metadata: dict = None,
    ) -> "Checkpoint":
        """
        Factory method para criar checkpoint em parada HIL.

        Args:
            job_id: ID do workflow/job
            state_snapshot: Estado completo do LangGraph
            turn_id: ID da mensagem HIL
            hil_reason: Motivo da parada HIL
            files_uri: URI dos arquivos no storage
            metadata: Metadados adicionais

        Returns:
            Nova instância de Checkpoint
        """
        base_metadata = {"hil_reason": hil_reason}
        if metadata:
            base_metadata.update(metadata)

        return cls(
            job_id=job_id,
            turn_id=turn_id,
            snapshot_type=SnapshotType.HIL,
            description=f"Checkpoint HIL: {hil_reason}",
            state_snapshot=state_snapshot,
            files_snapshot_uri=files_uri,
            checkpoint_metadata=base_metadata,
            is_restorable=True,
            created_by="system",
        )

    def mark_non_restorable(self, reason: str) -> None:
        """
        Marca checkpoint como não restaurável.

        Args:
            reason: Motivo pelo qual não pode ser restaurado
        """
        self.is_restorable = False
        self.non_restorable_reason = reason

    def get_node_name(self) -> str:
        """Retorna nome do node do checkpoint."""
        return self.checkpoint_metadata.get("node_name", "unknown")
