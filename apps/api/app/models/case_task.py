"""
CaseTask - Tarefas derivadas vinculadas a casos.

Representa tarefas como:
- "Prazo de contestação em 15 dias"
- "Analisar decisão interlocutória"
- "Preparar recurso de apelação"
"""

from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Boolean, Integer, JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
import uuid
from app.core.time_utils import utcnow
from app.core.database import Base
import enum


class TaskPriority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"


class TaskType(str, enum.Enum):
    DEADLINE = "deadline"        # Prazo processual
    ANALYSIS = "analysis"        # Análise de documento/decisão
    DRAFT = "draft"              # Elaborar peça
    REVIEW = "review"            # Revisar documento
    HEARING = "hearing"          # Audiência
    MEETING = "meeting"          # Reunião com cliente
    RESEARCH = "research"        # Pesquisa jurídica
    FILING = "filing"            # Protocolar documento
    OTHER = "other"


class CaseTask(Base):
    """
    Tarefa derivada vinculada a um caso.
    Pode ser criada automaticamente (ex: prazo detectado) ou manualmente.
    """
    __tablename__ = "case_tasks"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    case_id = Column(String, ForeignKey("cases.id"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)

    # Identificação
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    task_type = Column(String, default=TaskType.OTHER)

    # Prioridade e Status
    priority = Column(String, default=TaskPriority.MEDIUM)
    status = Column(String, default=TaskStatus.PENDING)

    # Prazos
    deadline = Column(DateTime, nullable=True, index=True)  # Data limite
    reminder_at = Column(DateTime, nullable=True)           # Lembrete antes do prazo
    started_at = Column(DateTime, nullable=True)            # Quando iniciou
    completed_at = Column(DateTime, nullable=True)          # Quando concluiu

    # Origem da tarefa
    source = Column(String, default="manual")  # manual, djen, workflow, ai_suggested
    source_ref = Column(String, nullable=True)  # ID da movimentação/evento que originou

    # Documento relacionado (se houver)
    document_ref = Column(String, nullable=True)  # Referência ao documento no storage
    workflow_state_id = Column(String, ForeignKey("workflow_states.id"), nullable=True)

    # Metadados extras
    _JSON_COMPAT = JSON().with_variant(JSONB, "postgresql")
    extra_data = Column(_JSON_COMPAT, default=dict)  # Dados adicionais específicos do tipo

    # Recorrência (para tarefas periódicas)
    is_recurring = Column(Boolean, default=False)
    recurrence_rule = Column(String, nullable=True)  # RRULE format

    # Ordenação
    order_index = Column(Integer, default=0)

    # Timestamps
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    # Relacionamentos
    case = relationship("Case", backref="tasks")
    user = relationship("User", backref="tasks")
    workflow_state = relationship("WorkflowState", backref="tasks")

    def to_dict(self) -> dict:
        """Serializa para API."""
        return {
            "id": self.id,
            "case_id": self.case_id,
            "title": self.title,
            "description": self.description,
            "task_type": self.task_type,
            "priority": self.priority,
            "status": self.status,
            "deadline": self.deadline.isoformat() if self.deadline else None,
            "reminder_at": self.reminder_at.isoformat() if self.reminder_at else None,
            "source": self.source,
            "source_ref": self.source_ref,
            "document_ref": self.document_ref,
            "is_recurring": self.is_recurring,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @property
    def is_overdue(self) -> bool:
        """Verifica se a tarefa está atrasada."""
        if not self.deadline or self.status == TaskStatus.COMPLETED:
            return False
        return utcnow() > self.deadline

    @property
    def days_until_deadline(self) -> int | None:
        """Dias até o prazo (negativo se atrasado)."""
        if not self.deadline:
            return None
        delta = self.deadline - utcnow()
        return delta.days

    @classmethod
    def from_djen_intimation(cls, intimation, case_id: str, user_id: str):
        """
        Cria tarefa a partir de intimação do DJEN.

        Args:
            intimation: DjenIntimation model
            case_id: ID do caso
            user_id: ID do usuário
        """
        from datetime import timedelta

        # Calcula prazo padrão (15 dias úteis = ~21 dias corridos)
        deadline = intimation.data_disponibilizacao + timedelta(days=21)

        return cls(
            case_id=case_id,
            user_id=user_id,
            title=f"Prazo: {intimation.tipo_comunicacao}",
            description=intimation.texto[:500] if intimation.texto else None,
            task_type=TaskType.DEADLINE,
            priority=TaskPriority.HIGH,
            deadline=deadline,
            source="djen",
            source_ref=str(intimation.id) if hasattr(intimation, 'id') else None,
            extra_data={
                "tribunal": intimation.tribunal_sigla,
                "processo": intimation.numero_processo,
                "tipo_comunicacao": intimation.tipo_comunicacao,
                "link": intimation.link,
            },
        )

    @classmethod
    def from_workflow_suggestion(cls, suggestion: dict, case_id: str, user_id: str, workflow_state_id: str = None):
        """
        Cria tarefa a partir de sugestão do workflow AI.

        Args:
            suggestion: Dict com title, description, deadline, priority
            case_id: ID do caso
            user_id: ID do usuário
            workflow_state_id: ID do WorkflowState que gerou a sugestão
        """
        return cls(
            case_id=case_id,
            user_id=user_id,
            title=suggestion.get("title", "Tarefa sugerida"),
            description=suggestion.get("description"),
            task_type=suggestion.get("task_type", TaskType.OTHER),
            priority=suggestion.get("priority", TaskPriority.MEDIUM),
            deadline=suggestion.get("deadline"),
            source="ai_suggested",
            workflow_state_id=workflow_state_id,
            extra_data=suggestion.get("extra_data", suggestion.get("metadata", {})),
        )
