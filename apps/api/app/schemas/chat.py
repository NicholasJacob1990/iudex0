"""
Schemas Pydantic para chat e minutas
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


class ChatBase(BaseModel):
    """Schema base de chat"""
    title: str = Field(..., min_length=1, max_length=255)
    mode: str = Field(..., pattern="^(CHAT|MINUTA)$")


class ChatCreate(ChatBase):
    """Schema para criação de chat"""
    context: Dict[str, Any] = Field(default_factory=dict)


class ChatUpdate(BaseModel):
    """Schema para atualização de chat"""
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    mode: Optional[str] = Field(None, pattern="^(CHAT|MINUTA)$")
    is_active: Optional[bool] = None


class ChatResponse(ChatBase):
    """Schema de resposta de chat"""
    id: str
    user_id: str
    context: Dict[str, Any]
    is_active: bool
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class MessageBase(BaseModel):
    """Schema base de mensagem"""
    content: str = Field(..., min_length=1)


class MessageCreate(MessageBase):
    """Schema para criação de mensagem"""
    attachments: List[Dict[str, Any]] = Field(default_factory=list)
    chat_personality: str = Field(default="juridico", pattern="^(juridico|geral)$")


class MessageResponse(MessageBase):
    """Schema de resposta de mensagem"""
    id: str
    chat_id: str
    role: str
    attachments: List[Dict[str, Any]]
    thinking: Optional[str] = None
    metadata: Dict[str, Any]
    created_at: datetime
    
    class Config:
        from_attributes = True


class GenerateDocumentRequest(BaseModel):
    """Schema para geração de documento com IA multi-agente"""
    prompt: str
    context: Dict[str, Any] = {}
    effort_level: int = 3
    use_profile: str = "basic"  # full, basic, none
    document_type: str = "generic"
    # IDs canônicos (ver apps/api/app/services/ai/model_registry.py)
    model: Optional[str] = "gemini-3-pro"
    model_gpt: Optional[str] = "gpt-5.2"
    model_claude: Optional[str] = "claude-4.5-sonnet"
    strategist_model: Optional[str] = None
    drafter_models: List[str] = Field(default_factory=list)
    reviewer_models: List[str] = Field(default_factory=list)
    chat_personality: str = Field(default="juridico", pattern="^(juridico|geral)$")
    citation_style: Optional[str] = Field(default="forense", pattern="^(forense|abnt|hibrido)$")
    use_multi_agent: bool = False
    context_documents: List[str] = Field(default_factory=list)
    attachment_mode: str = Field(default="rag_local", pattern="^(rag_local|prompt_injection)$")
    min_pages: Optional[int] = Field(default=None, ge=0)
    max_pages: Optional[int] = Field(default=None, ge=0)
    web_search: bool = False
    dense_research: bool = False
    thinking_level: str = "medium" # low, medium, high
    thesis: Optional[str] = None
    formatting_options: Dict[str, bool] = Field(default_factory=dict)
    use_templates: bool = False
    template_filters: Dict[str, Any] = Field(default_factory=dict)
    prompt_extra: Optional[str] = None
    template_id: Optional[str] = None
    variables: Dict[str, Any] = Field(default_factory=dict)
    rag_config: Optional[Dict[str, Any]] = None
    use_langgraph: bool = True
    adaptive_routing: bool = False
    crag_gate: bool = False
    crag_min_best_score: float = 0.45
    crag_min_avg_score: float = 0.35
    hyde_enabled: bool = False
    graph_rag_enabled: bool = False
    graph_hops: int = 1
    destino: str = "uso_interno"
    risco: str = "baixo"
    hil_outline_enabled: bool = False
    hil_target_sections: List[str] = Field(default_factory=list)


class GenerateDocumentResponse(BaseModel):
    """Schema de resposta de geração"""
    content: str
    docx_path: Optional[str] = None
    audit_report_path: Optional[str] = None
    metrics: Dict[str, Any] = Field(default_factory=dict)


class ChatWithDocsRequest(BaseModel):
    """Schema para chat com documentos (stateless/híbrido)"""
    case_id: Optional[str] = None
    message: str
    conversation_history: List[Dict[str, str]] = []  # [{"role": "user", "content": "..."}]
    document_ids: List[str] = []
    context_files: List[str] = [] # Caminhos de arquivos para context caching
    cache_ttl: int = 60
    custom_prompt: Optional[str] = None
    rag_config: Optional[Dict[str, Any]] = None # {"path": "/path/to/docs"}
    
class ChatWithDocsResponse(BaseModel):
    """Resposta do chat com documentos"""
    reply: str
    sources_used: List[Dict[str, Any]] = []
    conversation_id: Optional[str] = None
