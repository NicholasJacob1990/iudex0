"""
Graph Risk Schemas — Fraudes e Auditorias (GraphRAG).

These schemas back the /graph/risk endpoints and the optional chat tools.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class RiskProfile(str, Enum):
    precision = "precision"
    balanced = "balanced"
    recall = "recall"


class RiskEntity(BaseModel):
    entity_id: str
    name: Optional[str] = None
    entity_type: Optional[str] = None
    role: Optional[str] = None


class SupportingDocs(BaseModel):
    count: int = 0
    doc_ids_sample: List[str] = Field(default_factory=list)
    chunk_previews_sample: List[str] = Field(default_factory=list)


class RiskFocus(BaseModel):
    """Primary focus pair used by audit endpoints."""
    source_id: str
    target_id: str


class RiskSignal(BaseModel):
    scenario: str
    title: str
    score: float
    entities: List[RiskEntity] = Field(default_factory=list)
    supporting_docs: SupportingDocs = Field(default_factory=SupportingDocs)
    explain: str = ""
    focus: Optional[RiskFocus] = None
    raw: Optional[Dict[str, Any]] = None


class RiskScanRequest(BaseModel):
    profile: RiskProfile = Field(RiskProfile.balanced, description="precision | balanced | recall")
    scenarios: Optional[List[str]] = Field(None, description="Lista de cenários. Omitir = todos.")
    include_candidates: Optional[bool] = Field(None, description="Override do include_candidates (default depende do profile).")
    limit: int = Field(30, ge=1, le=200, description="Máximo de sinais retornados (por detector).")
    min_shared_docs: int = Field(2, ge=1, le=20, description="Threshold para co-mentions.")
    max_hops: int = Field(4, ge=1, le=6, description="Para auditoria/cadeias quando aplicável.")
    scope: Optional[str] = Field(None, description="global | private | local (group bloqueado)")
    include_global: bool = Field(True, description="Se true, inclui corpus global além do tenant.")
    case_id: Optional[str] = Field(None, description="Filtro por caso (quando scope=local).")
    persist: bool = Field(True, description="Se true, salva um relatório (retenção 30 dias).")


class RiskScanResponse(BaseModel):
    success: bool
    signals: List[RiskSignal] = Field(default_factory=list)
    report_id: Optional[str] = None
    execution_time_ms: int = 0
    error: Optional[str] = None


class GraphRiskReportListItem(BaseModel):
    id: str
    created_at: str
    expires_at: str
    status: str
    signal_count: int = 0
    params: Dict[str, Any] = Field(default_factory=dict)


class GraphRiskReportDetail(BaseModel):
    id: str
    created_at: str
    expires_at: str
    status: str
    params: Dict[str, Any] = Field(default_factory=dict)
    signals: List[RiskSignal] = Field(default_factory=list)
    error: Optional[str] = None


class AuditEdgeRequest(BaseModel):
    source_id: str
    target_id: str
    include_candidates: bool = False
    limit_docs: int = Field(5, ge=1, le=20)
    scope: Optional[str] = None
    include_global: bool = True
    case_id: Optional[str] = None


class AuditEdgeResponse(BaseModel):
    success: bool
    source_id: str
    target_id: str
    edge_matches: List[Dict[str, Any]] = Field(default_factory=list)
    co_mentions: List[Dict[str, Any]] = Field(default_factory=list)
    notes: Optional[str] = None
    execution_time_ms: int = 0
    error: Optional[str] = None


class AuditChainRequest(BaseModel):
    source_id: str
    target_id: str
    max_hops: int = Field(4, ge=1, le=6)
    include_candidates: bool = False
    limit: int = Field(5, ge=1, le=20)
    scope: Optional[str] = None
    include_global: bool = True
    case_id: Optional[str] = None


class AuditChainResponse(BaseModel):
    success: bool
    source_id: str
    target_id: str
    paths: List[Dict[str, Any]] = Field(default_factory=list)
    execution_time_ms: int = 0
    error: Optional[str] = None

