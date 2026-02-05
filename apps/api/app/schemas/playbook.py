"""
Schemas Pydantic para Playbook — regras de revisão de contratos.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


# ---------------------------------------------------------------------------
# PlaybookRule schemas
# ---------------------------------------------------------------------------


class PlaybookRuleBase(BaseModel):
    """Schema base de regra do playbook."""
    clause_type: str = Field(..., min_length=1, max_length=100, description="Tipo de cláusula: foro, multa, sla, confidencialidade, etc.")
    rule_name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    preferred_position: str = Field(..., min_length=1, description="Linguagem ideal da cláusula")
    fallback_positions: List[str] = Field(default_factory=list, description="Alternativas aceitáveis")
    rejected_positions: List[str] = Field(default_factory=list, description="Termos inaceitáveis")
    action_on_reject: str = Field(default="flag", pattern="^(redline|flag|block|suggest)$")
    severity: str = Field(default="medium", pattern="^(low|medium|high|critical)$")
    guidance_notes: Optional[str] = None
    order: int = Field(default=0, ge=0)
    is_active: bool = True
    metadata: Optional[Dict[str, Any]] = None


class PlaybookRuleCreate(PlaybookRuleBase):
    """Schema para criação de regra."""
    pass


class PlaybookRuleUpdate(BaseModel):
    """Schema para atualização de regra."""
    clause_type: Optional[str] = Field(None, max_length=100)
    rule_name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    preferred_position: Optional[str] = None
    fallback_positions: Optional[List[str]] = None
    rejected_positions: Optional[List[str]] = None
    action_on_reject: Optional[str] = Field(None, pattern="^(redline|flag|block|suggest)$")
    severity: Optional[str] = Field(None, pattern="^(low|medium|high|critical)$")
    guidance_notes: Optional[str] = None
    order: Optional[int] = Field(None, ge=0)
    is_active: Optional[bool] = None
    metadata: Optional[Dict[str, Any]] = None


class PlaybookRuleResponse(PlaybookRuleBase):
    """Schema de resposta de regra."""
    id: str
    playbook_id: str
    created_at: str
    updated_at: str

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# PlaybookShare schemas
# ---------------------------------------------------------------------------


class PlaybookShareCreate(BaseModel):
    """Schema para compartilhar playbook."""
    shared_with_user_id: Optional[str] = None
    shared_with_org_id: Optional[str] = None
    user_email: Optional[str] = Field(None, description="E-mail do usuário para compartilhar")
    organization_wide: bool = Field(default=False, description="Compartilhar com toda a organização")
    permission: str = Field(default="view", pattern="^(view|edit|admin)$")


class PlaybookShareResponse(BaseModel):
    """Schema de resposta de compartilhamento."""
    id: str
    playbook_id: str
    shared_with_user_id: Optional[str] = None
    shared_with_org_id: Optional[str] = None
    shared_with_email: Optional[str] = None
    permission: str
    created_at: str

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Playbook schemas
# ---------------------------------------------------------------------------


class PlaybookBase(BaseModel):
    """Schema base de playbook."""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    area: Optional[str] = Field(None, max_length=100, description="Área jurídica: trabalhista, ti, m&a, imobiliario, etc.")
    scope: str = Field(default="personal", pattern="^(personal|organization|public)$")
    party_perspective: str = Field(
        default="neutro",
        pattern="^(contratante|contratado|neutro)$",
        description="Perspectiva da parte: contratante, contratado, neutro"
    )
    is_template: bool = False
    metadata: Optional[Dict[str, Any]] = None


class PlaybookCreate(PlaybookBase):
    """Schema para criação de playbook."""
    rules: Optional[List[PlaybookRuleCreate]] = Field(default_factory=list, description="Regras iniciais (opcional)")


class PlaybookUpdate(BaseModel):
    """Schema para atualização de playbook."""
    name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    area: Optional[str] = Field(None, max_length=100)
    scope: Optional[str] = Field(None, pattern="^(personal|organization|public)$")
    party_perspective: Optional[str] = Field(
        None, pattern="^(contratante|contratado|neutro)$",
        description="Perspectiva da parte: contratante, contratado, neutro"
    )
    is_active: Optional[bool] = None
    is_template: Optional[bool] = None
    metadata: Optional[Dict[str, Any]] = None


class PlaybookResponse(PlaybookBase):
    """Schema de resposta de playbook (sem regras detalhadas)."""
    id: str
    user_id: str
    organization_id: Optional[str] = None
    is_active: bool
    version: int
    parent_id: Optional[str] = None
    rules_count: int = 0
    created_at: str
    updated_at: str

    model_config = ConfigDict(from_attributes=True)


class PlaybookWithRulesResponse(PlaybookResponse):
    """Schema de resposta de playbook com regras completas."""
    rules_items: List[PlaybookRuleResponse] = Field(default_factory=list)
    shares: List[PlaybookShareResponse] = Field(default_factory=list)


class PlaybookListResponse(BaseModel):
    """Schema de resposta paginada de playbooks."""
    items: List[PlaybookResponse]
    total: int
    skip: int
    limit: int


class ReorderRulesRequest(BaseModel):
    """Schema para reordenar regras."""
    rule_ids: List[str] = Field(..., description="Lista de IDs de regras na nova ordem")


class PlaybookDuplicateRequest(BaseModel):
    """Schema para duplicar um playbook."""
    name: Optional[str] = Field(None, max_length=255, description="Nome do novo playbook (opcional)")
    scope: str = Field(default="personal", pattern="^(personal|organization|public)$")


# ---------------------------------------------------------------------------
# PlaybookVersion schemas
# ---------------------------------------------------------------------------


class PlaybookVersionResponse(BaseModel):
    """Schema de resposta de versão do playbook."""
    id: str
    playbook_id: str
    version_number: int
    changed_by: str
    changed_by_email: Optional[str] = None
    changes_summary: str
    previous_rules: List[Dict[str, Any]] = Field(default_factory=list)
    created_at: str

    model_config = ConfigDict(from_attributes=True)


class PlaybookVersionListResponse(BaseModel):
    """Schema de resposta paginada de versões."""
    items: List[PlaybookVersionResponse]
    total: int


