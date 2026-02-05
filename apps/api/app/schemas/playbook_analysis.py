"""
Schemas Pydantic para análise de contratos via Playbook.

Define os modelos de entrada/saída para o PlaybookService,
incluindo resultados de análise por cláusula e resultado consolidado.
"""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict
from enum import Enum


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ClauseClassification(str, Enum):
    """Classificação de uma cláusula em relação a uma regra do playbook."""
    COMPLIANT = "compliant"
    NEEDS_REVIEW = "needs_review"
    NON_COMPLIANT = "non_compliant"
    NOT_FOUND = "not_found"


class AnalysisSeverity(str, Enum):
    """Severidade herdada da regra do playbook."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# ---------------------------------------------------------------------------
# Clause-level result
# ---------------------------------------------------------------------------


class ClauseAnalysisResult(BaseModel):
    """Resultado da análise de uma única cláusula contra uma regra do playbook."""

    rule_id: str = Field(..., description="ID da regra do playbook")
    rule_name: str = Field(..., description="Nome da regra")
    clause_type: str = Field(..., description="Tipo da cláusula (foro, multa, SLA, etc.)")

    found_in_contract: bool = Field(
        ..., description="Se a cláusula foi encontrada no contrato"
    )
    original_text: Optional[str] = Field(
        None, description="Texto da cláusula encontrada no contrato"
    )
    location: Optional[str] = Field(
        None, description="Referência de localização (seção, parágrafo)"
    )

    classification: ClauseClassification = Field(
        ..., description="Classificação: compliant, needs_review, non_compliant, not_found"
    )
    severity: AnalysisSeverity = Field(
        ..., description="Severidade da regra"
    )
    explanation: str = Field(
        ..., description="Explicação da IA sobre a classificação"
    )
    suggested_redline: Optional[str] = Field(
        None, description="Texto sugerido para substituição (se não-conforme)"
    )
    comment: Optional[str] = Field(
        None,
        description=(
            "Comentário auto-gerado explicando POR QUE a cláusula foi sinalizada "
            "e o que a alteração sugerida alcança. Exibido como tooltip/popover na UI."
        ),
    )
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Confiança da análise (0-1)"
    )

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Consolidated playbook analysis result
# ---------------------------------------------------------------------------


class PlaybookAnalysisResult(BaseModel):
    """Resultado consolidado da análise de um contrato contra um playbook."""

    playbook_id: str
    playbook_name: str
    document_id: str

    total_rules: int = Field(..., description="Total de regras analisadas")
    compliant: int = Field(0, description="Cláusulas conformes")
    needs_review: int = Field(0, description="Cláusulas que precisam revisão")
    non_compliant: int = Field(0, description="Cláusulas não-conformes")
    not_found: int = Field(0, description="Cláusulas não encontradas")

    risk_score: float = Field(
        ..., ge=0.0, le=100.0,
        description="Pontuação de risco (0=sem risco, 100=risco máximo)"
    )
    clauses: List[ClauseAnalysisResult] = Field(
        default_factory=list, description="Análises individuais por cláusula"
    )
    summary: str = Field(..., description="Resumo executivo gerado pela IA")

    analyzed_at: datetime = Field(..., description="Data/hora da análise")

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class PlaybookAnalyzeRequest(BaseModel):
    """Request para análise de contrato com playbook."""
    contract_text_override: Optional[str] = Field(
        None,
        description="Texto do contrato (se não informado, usa o texto extraído do documento)"
    )


class PlaybookGenerateRequest(BaseModel):
    """Request para gerar playbook a partir de contratos."""
    document_ids: List[str] = Field(
        ..., min_length=1, max_length=10,
        description="IDs dos documentos de contrato (1-10)"
    )
    name: str = Field(..., min_length=1, max_length=255, description="Nome do playbook")
    area: str = Field(
        ..., min_length=1, max_length=100,
        description="Área jurídica (trabalhista, ti, m&a, imobiliario, etc.)"
    )
    description: Optional[str] = Field(None, description="Descrição do playbook")


# ---------------------------------------------------------------------------
# Response wrappers
# ---------------------------------------------------------------------------


class PlaybookAnalysisResponse(BaseModel):
    """Wrapper de resposta para análise de playbook."""
    success: bool = True
    data: PlaybookAnalysisResult


class PlaybookGenerateResponse(BaseModel):
    """Wrapper de resposta para geração de playbook."""
    success: bool = True
    playbook_id: str
    name: str
    rules_count: int
    message: str = "Playbook gerado com sucesso"


class PlaybookImportRequest(BaseModel):
    """Request para importar playbook de um documento existente."""
    document_id: str = Field(
        ..., description="ID do documento fonte (PDF/DOCX) com o playbook"
    )
    name: str = Field(
        ..., min_length=1, max_length=255,
        description="Nome do playbook a ser criado"
    )
    area: str = Field(
        ..., min_length=1, max_length=100,
        description="Area juridica (trabalhista, ti, m&a, imobiliario, etc.)"
    )
    description: Optional[str] = Field(None, description="Descricao do playbook")


class PlaybookImportResponse(BaseModel):
    """Wrapper de resposta para importacao de playbook."""
    success: bool = True
    playbook_id: str
    name: str
    rules_count: int
    message: str = "Playbook importado com sucesso"


class WinningLanguageExtractRequest(BaseModel):
    """Request para extrair winning language de contratos já negociados."""
    document_ids: List[str] = Field(
        ..., min_length=1, max_length=10,
        description="IDs dos contratos já negociados (1-10)"
    )
    name: str = Field(
        ..., min_length=1, max_length=255,
        description="Nome do playbook a ser criado"
    )
    area: str = Field(
        ..., min_length=1, max_length=100,
        description="Área jurídica (trabalhista, ti, m&a, imobiliário, etc.)"
    )
    description: Optional[str] = Field(
        None, description="Descrição do playbook"
    )


class WinningLanguageExtractResponse(BaseModel):
    """Wrapper de resposta para extração de winning language."""
    success: bool = True
    playbook_id: str
    name: str
    rules_count: int
    documents_processed: int = Field(
        ..., description="Número de documentos efetivamente processados"
    )
    message: str = "Winning language extraída com sucesso"


# ---------------------------------------------------------------------------
# Persisted analysis schemas
# ---------------------------------------------------------------------------


class PlaybookAnalysisSavedResponse(BaseModel):
    """Resposta de análise persistida com metadados."""
    id: str
    playbook_id: str
    playbook_name: str
    document_id: str
    user_id: str
    organization_id: Optional[str] = None

    total_rules: int
    compliant: int = 0
    needs_review: int = 0
    non_compliant: int = 0
    not_found: int = 0
    risk_score: float = Field(..., ge=0.0, le=100.0)
    summary: str

    clauses: List[ClauseAnalysisResult] = Field(default_factory=list)
    reviewed_clauses: Optional[dict] = None

    model_used: Optional[str] = None
    analysis_duration_ms: Optional[int] = None

    created_at: str
    updated_at: str

    model_config = ConfigDict(from_attributes=True)


class PlaybookAnalysisSavedWrapper(BaseModel):
    """Wrapper de resposta para análise persistida."""
    success: bool = True
    data: PlaybookAnalysisSavedResponse


class PlaybookAnalysisListResponse(BaseModel):
    """Lista paginada de análises."""
    items: List[PlaybookAnalysisSavedResponse]
    total: int
    skip: int = 0
    limit: int = 50


class ClauseReviewRequest(BaseModel):
    """Request para marcar cláusulas como revisadas."""
    reviews: dict = Field(
        ...,
        description=(
            "Mapa de revisões: {rule_id: {status: 'approved'|'rejected'|'modified', notes: str}}"
        ),
    )


# ---------------------------------------------------------------------------
# Import from uploaded document (direct file upload)
# ---------------------------------------------------------------------------


class ImportDocumentExtractedRule(BaseModel):
    """Regra extraida de um documento para preview."""
    clause_type: str = "geral"
    rule_name: str = ""
    description: Optional[str] = None
    preferred_position: str = ""
    fallback_positions: List[str] = Field(default_factory=list)
    rejected_positions: List[str] = Field(default_factory=list)
    action_on_reject: str = "flag"
    severity: str = "medium"
    guidance_notes: Optional[str] = None
    order: int = 0


class ImportDocumentPreviewResponse(BaseModel):
    """Resposta com regras extraidas para preview antes de salvar."""
    success: bool = True
    rules: List[ImportDocumentExtractedRule]
    rules_count: int
    message: str = "Regras extraidas com sucesso"


class ImportDocumentConfirmRequest(BaseModel):
    """Request para confirmar e criar playbook a partir de regras previamente extraidas."""
    name: str = Field(..., min_length=1, max_length=255, description="Nome do playbook")
    area: str = Field(..., min_length=1, max_length=100, description="Area juridica")
    description: Optional[str] = Field(None, description="Descricao do playbook")
    rules: List[ImportDocumentExtractedRule] = Field(
        ..., min_length=1, description="Regras confirmadas (editadas pelo usuario)"
    )
