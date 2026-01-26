"""
WorkflowState - Persistência do DocumentState do LangGraph para auditabilidade.

Este modelo captura o estado completo do workflow após conclusão, incluindo:
- sources[] (documentos recuperados, ids, links, trechos)
- drafts history (versões via hil_history)
- decisions_log (routing reasons, hil reasons, audit issues)
- retrieval_queries (research context)
"""

from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Float, Integer, Boolean, JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
import uuid
from app.core.time_utils import utcnow
from app.core.database import Base


class WorkflowState(Base):
    """
    Persiste o DocumentState do LangGraph após conclusão do workflow.
    Mantém auditabilidade completa de todo o processo de geração.
    """
    __tablename__ = "workflow_states"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    case_id = Column(String, ForeignKey("cases.id"), nullable=True, index=True)
    job_id = Column(String, nullable=False, unique=True, index=True)
    chat_id = Column(String, nullable=True, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)

    # Status do workflow
    status = Column(String, default="completed")  # completed, failed, cancelled

    # ===== RETRIEVAL & SOURCES =====
    # Queries executadas durante research
    _JSON_COMPAT = JSON().with_variant(JSONB, "postgresql")
    retrieval_queries = Column(_JSON_COMPAT, default=list)  # List[str] - queries RAG/web
    # Fontes recuperadas com metadados
    sources = Column(_JSON_COMPAT, default=list)  # List[Dict] com id, title, link, excerpt, score, source_type
    # Mapa de citações usadas
    citations_map = Column(_JSON_COMPAT, default=dict)  # Dict[key, citation_data]

    # ===== DRAFTS =====
    # Referência ao documento final
    final_document_ref = Column(String, nullable=True)  # blob storage ref
    final_document_chars = Column(Integer, nullable=True)
    # Histórico de versões (via HIL)
    drafts_history = Column(_JSON_COMPAT, default=list)  # List[Dict] com version, content_preview, timestamp

    # ===== DECISIONS LOG =====
    # Por que roteou cada seção
    routing_decisions = Column(_JSON_COMPAT, default=dict)  # Dict[section, {model, reason, scores}]
    # Por que alertou (HIL risk factors)
    alert_decisions = Column(_JSON_COMPAT, default=dict)  # {risk_score, risk_level, risk_reasons, hil_checklist}
    # Por que citou/não citou
    citation_decisions = Column(_JSON_COMPAT, default=dict)  # {used_keys, missing_keys, orphan_keys, validation_report}
    # Resultado de auditoria
    audit_decisions = Column(_JSON_COMPAT, default=dict)  # {status, issues, report}
    # Quality gate results
    quality_decisions = Column(_JSON_COMPAT, default=dict)  # {passed, compression_ratio, reference_coverage, missing_refs}

    # ===== HIL HISTORY =====
    # Histórico completo de interações humanas
    hil_history = Column(_JSON_COMPAT, default=list)  # List[HilEntry] com todas as interações

    # ===== PROCESSED SECTIONS =====
    # Seções processadas com divergências e debates
    processed_sections = Column(_JSON_COMPAT, default=list)  # List[ProcessedSection] com drafts_by_model, divergences

    # ===== METADATA =====
    # Config usada no workflow
    workflow_config = Column(_JSON_COMPAT, default=dict)  # quality_profile, models, temperature, etc.
    # Métricas de performance
    metrics = Column(_JSON_COMPAT, default=dict)  # tokens_used, duration_ms, nodes_executed

    # Timestamps
    created_at = Column(DateTime, default=utcnow)
    completed_at = Column(DateTime, nullable=True)

    # Relacionamentos
    case = relationship("Case", backref="workflow_states")
    user = relationship("User", backref="workflow_states")

    def to_audit_dict(self) -> dict:
        """Retorna dados formatados para auditoria."""
        return {
            "id": self.id,
            "job_id": self.job_id,
            "case_id": self.case_id,
            "status": self.status,
            "sources": self.sources,
            "decisions": {
                "routing": self.routing_decisions,
                "alerts": self.alert_decisions,
                "citations": self.citation_decisions,
                "audit": self.audit_decisions,
                "quality": self.quality_decisions,
            },
            "hil_history": self.hil_history,
            "processed_sections": self.processed_sections,
            "metrics": self.metrics,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }

    @classmethod
    def from_document_state(cls, state: dict, job_id: str, user_id: str, case_id: str = None, chat_id: str = None):
        """
        Cria WorkflowState a partir do DocumentState do LangGraph.

        Args:
            state: O DocumentState completo do workflow
            job_id: ID do job
            user_id: ID do usuário
            case_id: ID do caso (opcional)
            chat_id: ID do chat (opcional)
        """
        return cls(
            job_id=job_id,
            user_id=user_id,
            case_id=case_id,
            chat_id=chat_id,
            status="completed",

            # Retrieval & Sources
            retrieval_queries=state.get("research_queries", []),
            sources=state.get("research_sources", []),
            citations_map=state.get("citations_map", {}),

            # Drafts
            final_document_ref=state.get("full_document_ref"),
            final_document_chars=state.get("full_document_chars"),
            drafts_history=cls._extract_drafts_history(state),

            # Decisions
            routing_decisions=state.get("section_routing_reasons", {}),
            alert_decisions={
                "risk_score": state.get("hil_risk_score"),
                "risk_level": state.get("hil_risk_level"),
                "risk_reasons": state.get("hil_risk_reasons", []),
                "hil_checklist": state.get("hil_checklist", {}),
            },
            citation_decisions={
                "used_keys": state.get("citation_used_keys", []),
                "missing_keys": state.get("citation_missing_keys", []),
                "orphan_keys": state.get("citation_orphan_keys", []),
                "validation_report": state.get("citation_validation_report", {}),
            },
            audit_decisions={
                "status": state.get("audit_status"),
                "issues": state.get("audit_issues", []),
                "report": state.get("audit_report", {}),
            },
            quality_decisions=cls._extract_quality_decisions(state),

            # HIL & Sections
            hil_history=state.get("hil_history", []),
            processed_sections=state.get("processed_sections", []),

            # Config & Metrics
            workflow_config={
                "quality_profile": state.get("quality_profile"),
                "creativity_mode": state.get("creativity_mode"),
                "temperature": state.get("temperature"),
                "models": state.get("models", {}),
                "rag_sources": state.get("rag_sources", []),
            },
            metrics=state.get("metrics", {}),
        )

    @staticmethod
    def _extract_drafts_history(state: dict) -> list:
        """Extrai histórico de drafts do state."""
        history = []
        # Adiciona draft inicial se existir
        if state.get("draft_document_ref"):
            history.append({
                "version": 0,
                "ref": state.get("draft_document_ref"),
                "chars": state.get("draft_document_chars"),
                "preview": state.get("draft_document_preview", "")[:500],
            })
        # Adiciona versão final
        if state.get("full_document_ref"):
            history.append({
                "version": 1,
                "ref": state.get("full_document_ref"),
                "chars": state.get("full_document_chars"),
                "preview": state.get("full_document_preview", "")[:500],
            })
        return history

    @staticmethod
    def _extract_quality_decisions(state: dict) -> dict:
        """Extrai decisões de quality gate do state."""
        gate_results = state.get("quality_gate_results", [])
        if not gate_results:
            return {}

        # Pega o último resultado
        last = gate_results[-1] if isinstance(gate_results, list) else gate_results
        return {
            "passed": last.get("passed"),
            "compression_ratio": last.get("compression_ratio"),
            "reference_coverage": last.get("reference_coverage"),
            "missing_references": last.get("missing_references", []),
            "notes": last.get("notes", []),
        }
