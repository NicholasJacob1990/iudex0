"""
Schemas Pydantic para chat e minutas
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


class ChatBase(BaseModel):
    """Schema base de chat"""
    title: str = Field(..., min_length=1, max_length=255)
    mode: str = Field(..., pattern="^(CHAT|MINUTA)$")


class ChatCreate(ChatBase):
    """Schema para criação de chat"""
    context: Dict[str, Any] = Field(default_factory=dict)


class ChatDuplicate(BaseModel):
    """Schema para duplicação de chat"""
    title: Optional[str] = None


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
    
    model_config = ConfigDict(from_attributes=True)


class MessageBase(BaseModel):
    """Schema base de mensagem"""
    content: str = Field(..., min_length=1)


class MessageCreate(MessageBase):
    """Schema para criação de mensagem"""
    attachments: List[Dict[str, Any]] = Field(default_factory=list)
    chat_personality: str = Field(default="juridico", pattern="^(juridico|geral)$")
    model: Optional[str] = None
    # RAG Scope Control - allows user to choose document sources
    rag_scope: str = Field(
        default="case_and_global",
        pattern="^(case_only|case_and_global|global_only)$",
        description="RAG scope: case_only (only case attachments), case_and_global (both), global_only (ignore case attachments)"
    )
    outline_pipeline: bool = False
    document_type: Optional[str] = None
    doc_kind: Optional[str] = None
    doc_subtype: Optional[str] = None
    thesis: Optional[str] = None
    min_pages: Optional[int] = Field(default=None, ge=0)
    max_pages: Optional[int] = Field(default=None, ge=0)
    web_search: bool = False
    multi_query: bool = True
    breadth_first: bool = False
    search_mode: str = Field(default="hybrid", pattern="^(shared|native|hybrid|perplexity)$")
    perplexity_search_mode: Optional[str] = Field(default=None, pattern="^(web|academic|sec)$")
    perplexity_search_type: Optional[str] = Field(default=None, pattern="^(fast|pro|auto)$")
    perplexity_search_context_size: Optional[str] = Field(default=None, pattern="^(low|medium|high)$")
    perplexity_search_classifier: bool = False
    perplexity_disable_search: bool = False
    perplexity_stream_mode: Optional[str] = Field(default=None, pattern="^(full|concise)$")
    perplexity_search_domain_filter: Optional[str] = None
    perplexity_search_language_filter: Optional[str] = None
    perplexity_search_recency_filter: Optional[str] = Field(default=None, pattern="^(day|week|month|year)$")
    perplexity_search_after_date: Optional[str] = None
    perplexity_search_before_date: Optional[str] = None
    perplexity_last_updated_after: Optional[str] = None
    perplexity_last_updated_before: Optional[str] = None
    perplexity_search_max_results: Optional[int] = Field(default=None, ge=1, le=20)
    perplexity_search_max_tokens: Optional[int] = Field(default=None, ge=1, le=1_000_000)
    perplexity_search_max_tokens_per_page: Optional[int] = Field(default=None, ge=1, le=1_000_000)
    perplexity_search_country: Optional[str] = None
    perplexity_search_region: Optional[str] = None
    perplexity_search_city: Optional[str] = None
    perplexity_search_latitude: Optional[str] = None
    perplexity_search_longitude: Optional[str] = None
    perplexity_return_images: bool = False
    perplexity_return_videos: bool = False
    research_policy: str = Field(default="auto", pattern="^(auto|force)$")
    rag_sources: Optional[List[str]] = None
    rag_top_k: Optional[int] = Field(default=None, ge=1, le=50)
    attachment_mode: str = Field(default="auto", pattern="^(auto|rag_local|prompt_injection)$")
    context_mode: str = Field(default="auto", pattern="^(auto|rag_local|upload_cache)$")
    context_files: List[str] = Field(default_factory=list)
    cache_ttl: int = 60
    adaptive_routing: bool = False
    rag_mode: str = Field(default="manual", pattern="^(auto|manual)$")
    crag_gate: bool = False
    crag_min_best_score: float = 0.45
    crag_min_avg_score: float = 0.35
    hyde_enabled: bool = False
    graph_rag_enabled: bool = False
    argument_graph_enabled: Optional[bool] = Field(default=None)
    graph_hops: int = Field(default=1, ge=1, le=5)
    dense_research: bool = False
    deep_research_effort: Optional[str] = Field(default=None, pattern="^(low|medium|high|1|2|3)$")
    deep_research_provider: Optional[str] = Field(default=None, pattern="^(auto|google|perplexity)$")
    deep_research_model: Optional[str] = None
    deep_research_search_focus: Optional[str] = Field(default=None, pattern="^(web|academic|sec)$")
    deep_research_domain_filter: Optional[str] = None
    deep_research_search_after_date: Optional[str] = None
    deep_research_search_before_date: Optional[str] = None
    deep_research_last_updated_after: Optional[str] = None
    deep_research_last_updated_before: Optional[str] = None
    deep_research_country: Optional[str] = None
    deep_research_latitude: Optional[str] = None
    deep_research_longitude: Optional[str] = None
    use_templates: bool = False
    template_filters: Dict[str, Any] = Field(default_factory=dict)
    template_id: Optional[str] = None
    template_document_id: Optional[str] = None
    variables: Dict[str, Any] = Field(default_factory=dict)
    outline: Optional[List[str]] = None
    reasoning_level: str = Field(default="medium", pattern="^(none|minimal|low|medium|high|xhigh)$")
    verbosity: Optional[str] = Field(default=None, pattern="^(low|medium|high)$")
    thinking_budget: Optional[int] = Field(default=None, ge=0, le=63999)
    temperature: Optional[float] = Field(default=None, ge=0, le=1, description="Temperatura (criatividade)")
    # Poe-like billing: optional per-message override (UI driven)
    budget_override_points: Optional[int] = Field(default=None, ge=1)


class MessageResponse(MessageBase):
    """Schema de resposta de mensagem"""
    id: str
    chat_id: str
    role: str
    attachments: List[Dict[str, Any]]
    thinking: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict, validation_alias="msg_metadata")
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class GenerateDocumentRequest(BaseModel):
    """Schema para geração de documento com IA multi-agente"""
    prompt: str
    context: Dict[str, Any] = {}
    effort_level: int = 3
    use_profile: str = "basic"  # full, basic, none
    document_type: str = "generic"
    doc_kind: Optional[str] = None
    doc_subtype: Optional[str] = None
    # RAG Scope Control - allows user to choose document sources
    rag_scope: str = Field(
        default="case_and_global",
        pattern="^(case_only|case_and_global|global_only)$",
        description="RAG scope: case_only (only case attachments), case_and_global (both), global_only (ignore case attachments)"
    )
    # IDs canônicos (ver apps/api/app/services/ai/model_registry.py)
    model: Optional[str] = "gemini-3-flash"
    model_gpt: Optional[str] = "gpt-5.2"
    model_claude: Optional[str] = "claude-4.5-sonnet"
    strategist_model: Optional[str] = None
    drafter_models: List[str] = Field(default_factory=list)
    reviewer_models: List[str] = Field(default_factory=list)
    chat_personality: str = Field(default="juridico", pattern="^(juridico|geral)$")
    citation_style: Optional[str] = Field(default="forense", pattern="^(forense|abnt|hibrido)$")
    temperature: Optional[float] = Field(default=None, ge=0, le=1, description="Temperatura (criatividade)")
    use_multi_agent: bool = False
    context_documents: List[str] = Field(default_factory=list)
    attachment_mode: str = Field(default="auto", pattern="^(auto|rag_local|prompt_injection)$")
    min_pages: Optional[int] = Field(default=None, ge=0)
    max_pages: Optional[int] = Field(default=None, ge=0)
    web_search: bool = False
    search_mode: str = Field(default="hybrid", pattern="^(shared|native|hybrid|perplexity)$")
    perplexity_search_mode: Optional[str] = Field(default=None, pattern="^(web|academic|sec)$")
    perplexity_search_type: Optional[str] = Field(default=None, pattern="^(fast|pro|auto)$")
    perplexity_search_context_size: Optional[str] = Field(default=None, pattern="^(low|medium|high)$")
    perplexity_search_classifier: bool = False
    perplexity_disable_search: bool = False
    perplexity_stream_mode: Optional[str] = Field(default=None, pattern="^(full|concise)$")
    perplexity_search_domain_filter: Optional[str] = None
    perplexity_search_language_filter: Optional[str] = None
    perplexity_search_recency_filter: Optional[str] = Field(default=None, pattern="^(day|week|month|year)$")
    perplexity_search_after_date: Optional[str] = None
    perplexity_search_before_date: Optional[str] = None
    perplexity_last_updated_after: Optional[str] = None
    perplexity_last_updated_before: Optional[str] = None
    perplexity_search_max_results: Optional[int] = Field(default=None, ge=1, le=20)
    perplexity_search_max_tokens: Optional[int] = Field(default=None, ge=1, le=1_000_000)
    perplexity_search_max_tokens_per_page: Optional[int] = Field(default=None, ge=1, le=1_000_000)
    perplexity_search_country: Optional[str] = None
    perplexity_search_region: Optional[str] = None
    perplexity_search_city: Optional[str] = None
    perplexity_search_latitude: Optional[str] = None
    perplexity_search_longitude: Optional[str] = None
    perplexity_return_images: bool = False
    perplexity_return_videos: bool = False
    multi_query: bool = True
    breadth_first: bool = False
    research_policy: str = Field(default="auto", pattern="^(auto|force)$")
    dense_research: bool = False
    deep_research_effort: Optional[str] = Field(default=None, pattern="^(low|medium|high|1|2|3)$")
    deep_research_search_focus: Optional[str] = Field(default=None, pattern="^(web|academic|sec)$")
    deep_research_domain_filter: Optional[str] = None
    deep_research_search_after_date: Optional[str] = None
    deep_research_search_before_date: Optional[str] = None
    deep_research_last_updated_after: Optional[str] = None
    deep_research_last_updated_before: Optional[str] = None
    deep_research_country: Optional[str] = None
    deep_research_latitude: Optional[str] = None
    deep_research_longitude: Optional[str] = None
    thinking_level: str = "medium" # none/minimal/low/medium/high/xhigh
    thesis: Optional[str] = None
    formatting_options: Dict[str, bool] = Field(default_factory=dict)
    use_templates: bool = False
    template_filters: Dict[str, Any] = Field(default_factory=dict)
    prompt_extra: Optional[str] = None
    template_id: Optional[str] = None
    template_document_id: Optional[str] = None
    variables: Dict[str, Any] = Field(default_factory=dict)
    rag_config: Optional[Dict[str, Any]] = None
    rag_sources: Optional[List[str]] = None
    rag_top_k: Optional[int] = Field(default=None, ge=1, le=50)
    use_langgraph: bool = True
    adaptive_routing: bool = False
    rag_mode: str = Field(default="manual", pattern="^(auto|manual)$")
    crag_gate: bool = False
    crag_min_best_score: float = 0.45
    crag_min_avg_score: float = 0.35
    hyde_enabled: bool = False
    graph_rag_enabled: bool = False
    argument_graph_enabled: Optional[bool] = Field(default=None)
    graph_hops: int = 1
    destino: str = "uso_interno"
    risco: str = "baixo"
    hil_outline_enabled: bool = False
    hil_target_sections: List[str] = Field(default_factory=list)
    outline_override: Optional[List[str]] = Field(
        default=None,
        description="Override do outline (1 seção por item). Se vazio/None, o workflow gera automaticamente.",
    )
    audit_mode: str = Field(default="sei_only", pattern="^(sei_only|research)$")
    quality_profile: str = Field(default="padrao", pattern="^(rapido|padrao|rigoroso|auditoria)$")
    target_section_score: Optional[float] = Field(default=None, ge=0, le=10)
    target_final_score: Optional[float] = Field(default=None, ge=0, le=10)
    max_rounds: Optional[int] = Field(default=None, ge=1, le=6)
    style_refine_max_rounds: Optional[int] = Field(default=None, ge=0, le=6)
    strict_document_gate: Optional[bool] = Field(default=None)
    hil_section_policy: Optional[str] = Field(default=None, pattern="^(none|optional|required)$")
    hil_final_required: Optional[bool] = Field(default=None)
    recursion_limit: Optional[int] = Field(default=None, ge=20, le=500)
    max_research_verifier_attempts: Optional[int] = Field(default=None, ge=0, le=5)
    max_rag_retries: Optional[int] = Field(default=None, ge=0, le=5)
    rag_retry_expand_scope: Optional[bool] = Field(default=None)
    document_checklist_hint: List[Dict[str, Any]] = Field(default_factory=list)
    # Poe-like billing: optional per-execution override (UI driven)
    budget_override_points: Optional[int] = Field(default=None, ge=1)


class GenerateDocumentResponse(BaseModel):
    """Schema de resposta de geração"""
    content: str
    docx_path: Optional[str] = None
    audit_report_path: Optional[str] = None
    metrics: Dict[str, Any] = Field(default_factory=dict)


class OutlineRequest(BaseModel):
    """Schema para geração leve de outline (modo chat)"""
    prompt: str = Field(..., min_length=1)
    document_type: str = Field(default="PETICAO")
    doc_kind: Optional[str] = None
    doc_subtype: Optional[str] = None
    thesis: Optional[str] = None
    model: Optional[str] = None
    min_pages: Optional[int] = Field(default=0, ge=0)
    max_pages: Optional[int] = Field(default=0, ge=0)


class OutlineResponse(BaseModel):
    """Schema de resposta de outline"""
    outline: List[str] = Field(default_factory=list)
    model: Optional[str] = None


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
