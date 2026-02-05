"""
Schemas para o modulo Word Add-in.

Inclui schemas para:
- Analise inline com playbook
- Edicao de conteudo com IA (SSE)
- Traducao (SSE)
- Anonimizacao (LGPD)
- Run Playbook com redlines OOXML (Fase 2)
- Aplicacao/rejeicao de redlines
"""

from typing import Optional, Literal, List
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Schemas existentes
# ---------------------------------------------------------------------------


class InlineAnalyzeRequest(BaseModel):
    """Requisicao para analise inline de conteudo com playbook."""
    playbook_id: str
    document_content: str = Field(..., min_length=1)
    document_format: Literal["text", "ooxml"] = "text"


class ClauseAnalysisResult(BaseModel):
    """Resultado da analise de uma clausula."""
    id: str
    text: str
    classification: Literal["conforme", "nao_conforme", "ausente", "parcial"]
    severity: Literal["critical", "warning", "info"]
    rule_id: str
    rule_name: str
    explanation: str
    suggested_redline: Optional[str] = None


class InlineAnalyzeResponse(BaseModel):
    """Resposta da analise inline."""
    playbook_id: str
    clauses: list[ClauseAnalysisResult]
    summary: str
    total_rules: int
    compliant: int
    non_compliant: int


class EditContentRequest(BaseModel):
    """Requisicao para edicao de conteudo com IA."""
    content: str = Field(..., min_length=1)
    instruction: str = Field(..., min_length=1)
    model: Optional[str] = None
    context: Optional[str] = None


class TranslateRequest(BaseModel):
    """Requisicao para traducao de conteudo."""
    content: str = Field(..., min_length=1)
    source_lang: str = "pt"
    target_lang: str = "en"


class AnonymizeRequest(BaseModel):
    """Requisicao para anonimizacao de conteudo."""
    content: str = Field(..., min_length=1)
    entities_to_anonymize: list[str] = [
        "CPF", "nome", "endereco", "telefone", "email", "RG", "OAB"
    ]


class AnonymizeResponse(BaseModel):
    """Resposta da anonimizacao."""
    anonymized_content: str
    entities_found: list[dict]
    mapping: dict[str, str]


# ---------------------------------------------------------------------------
# Fase 2 — Run Playbook + Redlines OOXML
# ---------------------------------------------------------------------------


class RedlineData(BaseModel):
    """Dados de um redline individual retornado pela analise."""
    redline_id: str
    rule_id: str
    rule_name: str
    clause_type: str
    classification: str
    severity: str
    original_text: str
    suggested_text: str
    explanation: str
    comment: Optional[str] = None
    confidence: float = 0.0
    applied: bool = False
    rejected: bool = False
    reviewed: bool = False
    created_at: str = ""
    ooxml: Optional[str] = None


class ClauseData(BaseModel):
    """Dados de uma clausula analisada."""
    rule_id: str
    rule_name: str
    clause_type: str
    found_in_contract: bool = False
    original_text: Optional[str] = None
    classification: str
    severity: str
    explanation: str
    suggested_redline: Optional[str] = None
    comment: Optional[str] = None
    confidence: float = 0.0
    redline_id: Optional[str] = None


class PlaybookRunStats(BaseModel):
    """Estatisticas de execucao do playbook."""
    total_rules: int = 0
    compliant: int = 0
    needs_review: int = 0
    non_compliant: int = 0
    not_found: int = 0
    risk_score: float = 0.0
    total_redlines: int = 0


class RunPlaybookRequest(BaseModel):
    """Request para executar playbook no documento Word."""
    playbook_id: str = Field(..., description="ID do playbook a executar")
    document_content: str = Field(..., min_length=1, description="Texto do documento Word")
    document_format: Literal["text", "ooxml"] = "text"
    include_ooxml: bool = Field(
        True,
        description="Se deve incluir OOXML de tracked changes na resposta"
    )
    cache_results: bool = Field(
        True,
        description="Se deve salvar resultados no cache para apply posterior"
    )


class RunPlaybookResponse(BaseModel):
    """Resposta completa da execucao de playbook no Word."""
    success: bool = True
    playbook_id: str
    playbook_name: str
    playbook_run_id: Optional[str] = Field(
        None,
        description="ID do cache para recuperar redlines posteriormente"
    )
    redlines: List[RedlineData] = Field(default_factory=list)
    clauses: List[ClauseData] = Field(default_factory=list)
    stats: PlaybookRunStats = Field(default_factory=PlaybookRunStats)
    summary: str = ""
    ooxml_package: Optional[str] = Field(
        None,
        description="OOXML pkg:package com todos os tracked changes"
    )
    error: Optional[str] = None


class ApplyRedlineRequest(BaseModel):
    """Request para aplicar redline(s) especifico(s)."""
    playbook_run_id: str = Field(
        ...,
        description="ID da execucao de playbook (retornado por /playbook/run)"
    )
    redline_ids: List[str] = Field(
        ..., min_length=1,
        description="IDs dos redlines a aplicar"
    )
    strategy: Literal["ooxml", "comment", "replace"] = Field(
        "ooxml",
        description="Estrategia de aplicacao: ooxml (tracked change), comment, replace"
    )


class ApplyRedlineResponse(BaseModel):
    """Resposta da aplicacao de redline(s)."""
    success: bool = True
    applied: List[str] = Field(default_factory=list, description="IDs aplicados com sucesso")
    failed: List[str] = Field(default_factory=list, description="IDs que falharam")
    ooxml_data: Optional[dict] = Field(
        None,
        description="Mapa redline_id -> OOXML para cada redline aplicado"
    )


class RejectRedlineRequest(BaseModel):
    """Request para rejeitar redline(s)."""
    playbook_run_id: str = Field(
        ...,
        description="ID da execucao de playbook (retornado por /playbook/run)"
    )
    redline_ids: List[str] = Field(
        ..., min_length=1,
        description="IDs dos redlines a rejeitar"
    )


class RejectRedlineResponse(BaseModel):
    """Resposta da rejeicao de redline(s)."""
    success: bool = True
    rejected: List[str] = Field(default_factory=list)
    failed: List[str] = Field(default_factory=list)


class ApplyAllRedlinesRequest(BaseModel):
    """Request para aplicar todos os redlines."""
    playbook_run_id: str = Field(
        ...,
        description="ID da execucao de playbook (retornado por /playbook/run)"
    )
    redline_ids: Optional[List[str]] = Field(
        None,
        description="IDs especificos (None = todos pendentes)"
    )
    strategy: Literal["ooxml", "comment", "replace"] = "ooxml"


class ApplyAllRedlinesResponse(BaseModel):
    """Resposta da aplicacao de todos os redlines."""
    success: bool = True
    total: int = 0
    applied: int = 0
    failed: int = 0
    ooxml_package: Optional[str] = Field(
        None,
        description="OOXML pkg:package com todos os tracked changes aplicados"
    )


class RestorePlaybookRunResponse(BaseModel):
    """Resposta da restauracao de uma execucao de playbook do cache."""
    success: bool = True
    playbook_run_id: str
    playbook_id: str
    playbook_name: str = ""
    redlines: List[RedlineData] = Field(default_factory=list)
    clauses: List[ClauseData] = Field(default_factory=list)
    stats: PlaybookRunStats = Field(default_factory=PlaybookRunStats)
    summary: str = ""
    expires_at: Optional[str] = Field(
        None,
        description="Data/hora de expiracao do cache (ISO format)"
    )
    error: Optional[str] = None


class PlaybookListItem(BaseModel):
    """Item da lista de playbooks disponiveis."""
    id: str
    name: str
    description: Optional[str] = None
    area: Optional[str] = None
    rules_count: int = 0
    scope: str = "personal"
    party_perspective: str = "neutro"


class PlaybookListResponse(BaseModel):
    """Resposta da listagem de playbooks."""
    items: List[PlaybookListItem] = Field(default_factory=list)
    total: int = 0


# ---------------------------------------------------------------------------
# Gap 4 — Persistencia de Estado de Redlines
# ---------------------------------------------------------------------------


class RedlineStateData(BaseModel):
    """Dados de estado de um redline persistido."""
    redline_id: str
    status: Literal["pending", "applied", "rejected"]
    applied_at: Optional[str] = None
    rejected_at: Optional[str] = None


class RedlineStateResponse(BaseModel):
    """Resposta de uma operacao de estado de redline."""
    success: bool = True
    redline_id: str
    status: str
    message: Optional[str] = None


class GetRedlineStatesResponse(BaseModel):
    """Resposta da busca de estados de redlines de um playbook run."""
    success: bool = True
    playbook_run_id: str
    states: List[RedlineStateData] = Field(default_factory=list)
    stats: Optional[dict] = Field(
        None,
        description="Estatisticas: total, pending, applied, rejected"
    )


# ---------------------------------------------------------------------------
# Gap 8 — Exportacao de Audit Log
# ---------------------------------------------------------------------------


class AuditReportSummary(BaseModel):
    """Resumo do relatorio de auditoria."""
    total_clauses: int = 0
    total_redlines: int = 0
    applied: int = 0
    rejected: int = 0
    pending: int = 0
    compliant: int = 0
    non_compliant: int = 0
    needs_review: int = 0
    not_found: int = 0
    risk_score: float = 0.0


class AuditReportRedline(BaseModel):
    """Detalhes de um redline no relatorio de auditoria."""
    redline_id: str
    rule_name: str
    clause_type: str
    classification: str
    severity: str
    status: Literal["applied", "rejected", "pending"]
    original_text: str
    suggested_text: str
    explanation: str
    confidence: float = 0.0
    applied_at: Optional[str] = None
    rejected_at: Optional[str] = None


class AuditReportResponse(BaseModel):
    """Resposta do relatorio de auditoria."""
    playbook_run_id: str
    playbook_name: str
    generated_at: str
    user_email: Optional[str] = None
    summary: AuditReportSummary
    analysis_summary: str = ""
    redlines: List[AuditReportRedline] = Field(default_factory=list)
