"""
Playbook Models — Conjunto de regras para revisão de contratos.

Playbook stores a structured set of rules/guidelines for contract review.
PlaybookRule defines preferred positions, fallbacks, and rejected positions per clause type.
PlaybookShare manages sharing with users and organizations.
"""

import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum as SQLEnum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.time_utils import utcnow


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class PlaybookScope(str, enum.Enum):
    PERSONAL = "personal"
    ORGANIZATION = "organization"
    PUBLIC = "public"


class RuleActionOnReject(str, enum.Enum):
    REDLINE = "redline"
    FLAG = "flag"
    BLOCK = "block"
    SUGGEST = "suggest"


class RuleSeverity(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class PlaybookSharePermission(str, enum.Enum):
    VIEW = "view"
    EDIT = "edit"
    ADMIN = "admin"


# ---------------------------------------------------------------------------
# Playbook (rule set definition)
# ---------------------------------------------------------------------------


class Playbook(Base):
    """Conjunto de regras para revisão de contratos."""
    __tablename__ = "playbooks"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    organization_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("organizations.id"), nullable=True, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id"), nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    area: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, index=True,
        doc="Área jurídica: trabalhista, ti, m&a, imobiliario, etc."
    )

    # Inline rules as JSON (for quick access / export)
    rules: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_template: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    scope: Mapped[str] = mapped_column(
        SQLEnum(PlaybookScope), default=PlaybookScope.PERSONAL, nullable=False,
        doc="Escopo: personal, organization, public"
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    parent_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("playbooks.id"), nullable=True,
        doc="Referência ao playbook original (para versionamento/duplicação)"
    )

    party_perspective: Mapped[str] = mapped_column(
        String(20), default="neutro", nullable=False,
        doc="Perspectiva da parte: contratante, contratado, neutro"
    )

    metadata_: Mapped[Optional[dict]] = mapped_column(
        "metadata", JSON, nullable=True,
        doc="Configurações extras"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    # Relationships
    user = relationship("User", backref="playbooks", foreign_keys=[user_id])
    organization = relationship("Organization", backref="playbooks")
    rules_items = relationship(
        "PlaybookRule", back_populates="playbook", cascade="all, delete-orphan",
        order_by="PlaybookRule.order"
    )
    shares = relationship(
        "PlaybookShare", back_populates="playbook", cascade="all, delete-orphan"
    )
    parent = relationship("Playbook", remote_side=[id], backref="children")

    __table_args__ = (
        Index("ix_playbooks_scope", "scope"),
        Index("ix_playbooks_user_active", "user_id", "is_active"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "organization_id": self.organization_id,
            "user_id": self.user_id,
            "name": self.name,
            "description": self.description,
            "area": self.area,
            "rules": self.rules,
            "is_active": self.is_active,
            "is_template": self.is_template,
            "scope": self.scope,
            "version": self.version,
            "parent_id": self.parent_id,
            "party_perspective": self.party_perspective or "neutro",
            "metadata": self.metadata_,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# ---------------------------------------------------------------------------
# PlaybookRule (individual rule within a playbook)
# ---------------------------------------------------------------------------


class PlaybookRule(Base):
    """Regra individual dentro de um playbook."""
    __tablename__ = "playbook_rules"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    playbook_id: Mapped[str] = mapped_column(
        String, ForeignKey("playbooks.id", ondelete="CASCADE"), nullable=False, index=True
    )

    clause_type: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True,
        doc="Tipo de cláusula: foro, multa, sla, confidencialidade, indenizacao, etc."
    )
    rule_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    preferred_position: Mapped[str] = mapped_column(
        Text, nullable=False,
        doc="Linguagem ideal da cláusula"
    )
    fallback_positions: Mapped[list] = mapped_column(
        JSON, default=list, nullable=False,
        doc="Alternativas aceitáveis"
    )
    rejected_positions: Mapped[list] = mapped_column(
        JSON, default=list, nullable=False,
        doc="Termos inaceitáveis"
    )

    action_on_reject: Mapped[str] = mapped_column(
        SQLEnum(RuleActionOnReject), default=RuleActionOnReject.FLAG, nullable=False,
        doc="Ação ao detectar posição rejeitada: redline, flag, block, suggest"
    )
    severity: Mapped[str] = mapped_column(
        SQLEnum(RuleSeverity), default=RuleSeverity.MEDIUM, nullable=False,
        doc="Severidade: low, medium, high, critical"
    )

    guidance_notes: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
        doc="Notas contextuais para o revisor"
    )
    order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    metadata_: Mapped[Optional[dict]] = mapped_column(
        "metadata", JSON, nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    # Relationships
    playbook = relationship("Playbook", back_populates="rules_items")

    __table_args__ = (
        Index("ix_playbook_rules_order", "playbook_id", "order"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "playbook_id": self.playbook_id,
            "clause_type": self.clause_type,
            "rule_name": self.rule_name,
            "description": self.description,
            "preferred_position": self.preferred_position,
            "fallback_positions": self.fallback_positions,
            "rejected_positions": self.rejected_positions,
            "action_on_reject": self.action_on_reject,
            "severity": self.severity,
            "guidance_notes": self.guidance_notes,
            "order": self.order,
            "is_active": self.is_active,
            "metadata": self.metadata_,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# ---------------------------------------------------------------------------
# PlaybookShare (sharing / access control)
# ---------------------------------------------------------------------------


class PlaybookShare(Base):
    """Compartilhamento de playbook com usuários ou organizações."""
    __tablename__ = "playbook_shares"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    playbook_id: Mapped[str] = mapped_column(
        String, ForeignKey("playbooks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    shared_with_user_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("users.id"), nullable=True, index=True
    )
    shared_with_org_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("organizations.id"), nullable=True, index=True
    )

    permission: Mapped[str] = mapped_column(
        SQLEnum(PlaybookSharePermission), default=PlaybookSharePermission.VIEW, nullable=False,
        doc="Permissão: view, edit, admin"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )

    # Relationships
    playbook = relationship("Playbook", back_populates="shares")
    shared_with_user = relationship("User", backref="playbook_shares_received", foreign_keys=[shared_with_user_id])
    shared_with_org = relationship("Organization", backref="playbook_shares_received")

    __table_args__ = (
        Index("ix_playbook_shares_lookup", "playbook_id", "shared_with_user_id"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "playbook_id": self.playbook_id,
            "shared_with_user_id": self.shared_with_user_id,
            "shared_with_org_id": self.shared_with_org_id,
            "permission": self.permission,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ---------------------------------------------------------------------------
# PlaybookAnalysis (persisted analysis results)
# ---------------------------------------------------------------------------


class PlaybookAnalysis(Base):
    """Resultado persistido de análise de contrato contra um playbook."""
    __tablename__ = "playbook_analyses"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    playbook_id: Mapped[str] = mapped_column(
        String, ForeignKey("playbooks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_id: Mapped[str] = mapped_column(
        String, ForeignKey("documents.id"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id"), nullable=False, index=True
    )
    organization_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("organizations.id"), nullable=True, index=True
    )

    # Results
    total_rules: Mapped[int] = mapped_column(Integer, nullable=False)
    compliant: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    needs_review: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    non_compliant: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    not_found: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    risk_score: Mapped[float] = mapped_column(
        Float, nullable=False,
        doc="Pontuação de risco (0=sem risco, 100=risco máximo)"
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)

    # Detailed results stored as JSON
    clause_results: Mapped[list] = mapped_column(
        JSON, default=list, nullable=False,
        doc="Lista de ClauseAnalysisResult dicts"
    )

    # Review tracking (Harvey feature #10)
    reviewed_clauses: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True, default=None,
        doc="Tracking de revisão: {rule_id: {reviewed_by, reviewed_at, status}}"
    )

    # Metadata
    model_used: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    analysis_duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    # Relationships
    playbook = relationship("Playbook", backref="analyses")
    document = relationship("Document", backref="playbook_analyses")
    user = relationship("User", backref="playbook_analyses", foreign_keys=[user_id])
    organization = relationship("Organization", backref="playbook_analyses")

    __table_args__ = (
        Index("ix_playbook_analyses_playbook_doc", "playbook_id", "document_id"),
        Index("ix_playbook_analyses_user_created", "user_id", "created_at"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "playbook_id": self.playbook_id,
            "document_id": self.document_id,
            "user_id": self.user_id,
            "organization_id": self.organization_id,
            "total_rules": self.total_rules,
            "compliant": self.compliant,
            "needs_review": self.needs_review,
            "non_compliant": self.non_compliant,
            "not_found": self.not_found,
            "risk_score": self.risk_score,
            "summary": self.summary,
            "clause_results": self.clause_results,
            "reviewed_clauses": self.reviewed_clauses,
            "model_used": self.model_used,
            "analysis_duration_ms": self.analysis_duration_ms,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# ---------------------------------------------------------------------------
# PlaybookVersion (version history tracking)
# ---------------------------------------------------------------------------


class PlaybookVersion(Base):
    """Registro de versão de um playbook — criado automaticamente a cada edição de regras."""
    __tablename__ = "playbook_versions"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    playbook_id: Mapped[str] = mapped_column(
        String, ForeignKey("playbooks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    changed_by: Mapped[str] = mapped_column(
        String, ForeignKey("users.id"), nullable=False, index=True,
        doc="ID do usuário que fez a alteração"
    )
    changes_summary: Mapped[str] = mapped_column(
        Text, nullable=False,
        doc="Resumo das alterações feitas nesta versão"
    )
    previous_rules: Mapped[list] = mapped_column(
        JSON, default=list, nullable=False,
        doc="Snapshot das regras ANTES desta alteração"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False,
        doc="Data/hora em que esta versão foi registrada"
    )

    # Relationships
    playbook = relationship("Playbook", backref="versions")
    user = relationship("User", backref="playbook_versions", foreign_keys=[changed_by])

    __table_args__ = (
        Index("ix_playbook_versions_playbook_version", "playbook_id", "version_number"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "playbook_id": self.playbook_id,
            "version_number": self.version_number,
            "changed_by": self.changed_by,
            "changes_summary": self.changes_summary,
            "previous_rules": self.previous_rules,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
