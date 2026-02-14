"""Pydantic schemas for Outlook Add-in endpoints."""

from typing import List, Optional
from pydantic import BaseModel, Field


class SummarizeEmailRequest(BaseModel):
    subject: str = Field(..., max_length=1000)
    from_address: str = Field(..., max_length=500)
    to_addresses: List[str] = Field(default_factory=list)
    body: str = Field(..., max_length=1_000_000)  # 1MB max
    body_type: str = Field(default="html")
    attachment_names: List[str] = Field(default_factory=list)
    internet_message_id: Optional[str] = Field(None, max_length=500)
    conversation_id: Optional[str] = Field(None, max_length=500)


class ClassifyEmailRequest(BaseModel):
    subject: str = Field(..., max_length=1000)
    from_address: str = Field(..., max_length=500)
    body: str = Field(..., max_length=500_000)
    body_type: str = Field(default="html")
    internet_message_id: Optional[str] = None


class ClassifyEmailResponse(BaseModel):
    tipo_juridico: str
    subtipo: Optional[str] = None
    confianca: float = Field(ge=0.0, le=1.0)
    tags: List[str] = Field(default_factory=list)


class DeadlineItem(BaseModel):
    data: str
    descricao: str
    urgencia: str = Field(default="media")  # alta, media, baixa
    tipo: Optional[str] = None  # prazo_fatal, prazo_ordinario, reuniao, etc.


class ExtractDeadlinesRequest(BaseModel):
    subject: str = Field(..., max_length=1000)
    body: str = Field(..., max_length=500_000)
    body_type: str = Field(default="html")
    internet_message_id: Optional[str] = None


class ExtractDeadlinesResponse(BaseModel):
    prazos: List[DeadlineItem]
    total: int


class SummaryResult(BaseModel):
    tipo_juridico: str
    confianca: float
    resumo: str
    partes: List[str] = Field(default_factory=list)
    prazos: List[DeadlineItem] = Field(default_factory=list)
    acoes_sugeridas: List[str] = Field(default_factory=list)
    workflows_recomendados: List[dict] = Field(default_factory=list)


class OutlookWorkflowTriggerRequest(BaseModel):
    workflow_id: str = Field(..., description="Slug builtin OU UUID de workflow real")
    email_data: dict = Field(..., description="{ subject, body, sender, recipients, date, attachments }")
    parameters: Optional[dict] = None


class OutlookWorkflowRunResponse(BaseModel):
    id: str
    workflow_id: str
    workflow_name: str
    status: str = Field(..., description="pending | running | completed | failed")
    result: Optional[dict] = None
    created_at: str
    updated_at: str
