"""
ToolPermission - Modelo para permissões de ferramentas do Claude Agent.

Este modelo gerencia permissões granulares para tools do Agent SDK:
- allow: executa automaticamente
- deny: bloqueia execução
- ask: solicita aprovação do usuário

Hierarquia de precedência: session > project > global > system
"""

from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Enum as SQLEnum, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
import uuid
import enum
from app.core.time_utils import utcnow
from app.core.database import Base


class PermissionMode(str, enum.Enum):
    """Modo de permissão para uma ferramenta."""
    ALLOW = "allow"  # Executa automaticamente
    DENY = "deny"    # Bloqueia execução
    ASK = "ask"      # Solicita aprovação


class PermissionScope(str, enum.Enum):
    """Escopo de aplicação da permissão."""
    SESSION = "session"  # Apenas para a sessão atual
    PROJECT = "project"  # Para um projeto/caso específico
    GLOBAL = "global"    # Para todas as sessões do usuário


class ToolPermission(Base):
    """
    Armazena regras de permissão para ferramentas do Claude Agent.

    Exemplos de uso:
    - user_id=X, tool_name="edit_document", mode="allow", scope="global"
      -> Usuário X sempre permite edição de documentos

    - user_id=X, tool_name="search_*", pattern="*STF*", mode="allow", scope="session"
      -> Permite pesquisas que contenham "STF" apenas nesta sessão

    - user_id=X, tool_name="bash", mode="deny", scope="global"
      -> Bloqueia comandos bash para o usuário
    """
    __tablename__ = "tool_permissions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # Identificação da ferramenta (pode usar wildcards como "search_*")
    tool_name = Column(String(100), nullable=False)

    # Padrão glob para matching do input (ex: "*sensivel*", "*/admin/*")
    # None significa que se aplica a qualquer input
    pattern = Column(String(500), nullable=True)

    # Modo de permissão
    mode = Column(SQLEnum(PermissionMode), nullable=False)

    # Escopo da permissão
    scope = Column(SQLEnum(PermissionScope), nullable=False)

    # Referências opcionais para escopos específicos
    session_id = Column(String, ForeignKey("workflow_states.id", ondelete="CASCADE"), nullable=True, index=True)
    project_id = Column(String, nullable=True, index=True)  # Pode ser case_id ou outro identificador

    # Metadados
    description = Column(Text, nullable=True)  # Descrição opcional da regra
    created_by = Column(String, nullable=True)  # "user" ou "system"

    # Timestamps
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    # Relacionamentos
    user = relationship("User", backref="tool_permissions")
    session = relationship("WorkflowState", backref="tool_permissions")

    # Índice composto para queries de permissão
    __table_args__ = (
        Index('idx_tool_permissions_lookup', 'user_id', 'tool_name', 'scope'),
        Index('idx_tool_permissions_session', 'session_id'),
        Index('idx_tool_permissions_project', 'project_id'),
    )

    def __repr__(self) -> str:
        return (
            f"<ToolPermission(id={self.id}, user_id={self.user_id}, "
            f"tool={self.tool_name}, mode={self.mode}, scope={self.scope})>"
        )

    def to_dict(self) -> dict:
        """Converte para dicionário."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "tool_name": self.tool_name,
            "pattern": self.pattern,
            "mode": self.mode.value if self.mode else None,
            "scope": self.scope.value if self.scope else None,
            "session_id": self.session_id,
            "project_id": self.project_id,
            "description": self.description,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def create_allow_rule(
        cls,
        user_id: str,
        tool_name: str,
        scope: PermissionScope = PermissionScope.GLOBAL,
        pattern: str = None,
        session_id: str = None,
        project_id: str = None,
        description: str = None,
    ) -> "ToolPermission":
        """Factory method para criar regra de permissão."""
        return cls(
            user_id=user_id,
            tool_name=tool_name,
            pattern=pattern,
            mode=PermissionMode.ALLOW,
            scope=scope,
            session_id=session_id,
            project_id=project_id,
            description=description,
            created_by="user",
        )

    @classmethod
    def create_deny_rule(
        cls,
        user_id: str,
        tool_name: str,
        scope: PermissionScope = PermissionScope.GLOBAL,
        pattern: str = None,
        session_id: str = None,
        project_id: str = None,
        description: str = None,
    ) -> "ToolPermission":
        """Factory method para criar regra de bloqueio."""
        return cls(
            user_id=user_id,
            tool_name=tool_name,
            pattern=pattern,
            mode=PermissionMode.DENY,
            scope=scope,
            session_id=session_id,
            project_id=project_id,
            description=description,
            created_by="user",
        )
