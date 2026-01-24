"""
Schemas Pydantic para documentos
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


class DocumentBase(BaseModel):
    """Schema base de documento"""
    name: str = Field(..., min_length=1, max_length=255)
    category: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


class DocumentCreate(DocumentBase):
    """Schema para criação de documento"""
    folder_id: Optional[str] = None


class DocumentUpload(BaseModel):
    """Schema para upload de documento"""
    apply_ocr: bool = False
    extract_metadata: bool = True
    category: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


class DocumentUpdate(BaseModel):
    """Schema para atualização de documento"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    folder_id: Optional[str] = None
    is_archived: Optional[bool] = None


class DocumentResponse(DocumentBase):
    """Schema de resposta de documento"""
    id: str
    user_id: str
    type: str
    status: str
    size: int
    url: str
    thumbnail_url: Optional[str] = None
    doc_metadata: Dict[str, Any] = Field(
        default_factory=dict,
        validation_alias="doc_metadata",
        serialization_alias="metadata",
    )
    folder_id: Optional[str] = None
    is_shared: bool
    is_archived: bool
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
    
    @classmethod
    def from_document(cls, doc: Any) -> "DocumentResponse":
        """Converte um objeto Document ORM para DocumentResponse de forma segura."""
        raw_meta = getattr(doc, 'doc_metadata', None)
        # Garantir que metadata seja sempre um dict
        if raw_meta is None:
            safe_meta = {}
        elif isinstance(raw_meta, dict):
            safe_meta = raw_meta
        else:
            # Fallback para objetos não-dict (ex: MetaData do SQLAlchemy)
            safe_meta = {}
        
        return cls(
            id=doc.id,
            user_id=doc.user_id,
            name=doc.name,
            category=doc.category.value if doc.category else None,
            tags=list(doc.tags) if doc.tags else [],
            type=doc.type.value if hasattr(doc.type, 'value') else str(doc.type),
            status=doc.status.value if hasattr(doc.status, 'value') else str(doc.status),
            size=doc.size,
            url=doc.url or "",
            thumbnail_url=doc.thumbnail_url,
            doc_metadata=safe_meta,
            folder_id=doc.folder_id,
            is_shared=doc.is_shared,
            is_archived=doc.is_archived,
            created_at=doc.created_at,
            updated_at=doc.updated_at,
        )


class DocumentSummaryRequest(BaseModel):
    """Schema para requisição de resumo"""
    type: str = Field(..., pattern="^(quick|detailed|audio|podcast)$")
    language: str = "pt-BR"


class DocumentOCRRequest(BaseModel):
    """Schema para requisição de OCR"""
    language: str = "por"
    dpi: int = Field(default=300, ge=72, le=600)


class DocumentTranscriptionRequest(BaseModel):
    """Schema para requisição de transcrição"""
    identify_speakers: bool = False
    language: str = "pt"


class DocumentGenerationRequest(BaseModel):
    """Schema para requisição de geração de documento"""
    prompt: str = Field(..., min_length=10, max_length=10000)
    document_type: str = Field(..., description="Tipo de documento (petition, contract, opinion, etc.)")
    doc_kind: Optional[str] = Field(default=None, description="Genero do documento (doc_kind)")
    doc_subtype: Optional[str] = Field(default=None, description="Subtipo do documento (doc_subtype)")
    context_documents: List[str] = Field(default_factory=list, description="IDs de documentos para contexto")
    chat_id: Optional[str] = Field(None, description="ID do chat para usar historico da sessao")
    effort_level: int = Field(default=3, ge=1, le=5, description="Nível de esforço (1-5)")
    min_pages: Optional[int] = Field(default=None, ge=0, description="Mínimo de páginas desejado (0 = auto)")
    max_pages: Optional[int] = Field(default=None, ge=0, description="Máximo de páginas desejado (0 = auto)")
    attachment_mode: str = Field(default="auto", pattern="^(auto|rag_local|prompt_injection)$", description="Como usar anexos (auto|rag_local|prompt_injection)")
    include_signature: bool = Field(default=True, description="Incluir assinatura no documento")
    template_id: Optional[str] = Field(None, description="ID do template a ser usado")
    template_document_id: Optional[str] = Field(None, description="ID do documento base para modelo/estrutura")
    variables: Dict[str, Any] = Field(default_factory=dict, description="Variáveis do template")
    language: str = "pt-BR"
    tone: str = Field(default="formal", description="Tom do documento (formal, informal, técnico)")
    max_length: Optional[int] = Field(None, description="Comprimento máximo em palavras")
    use_multi_agent: bool = Field(default=True, description="Ativar modo multi-agente (debate)")
    # IDs canônicos (ver apps/api/app/services/ai/model_registry.py e apps/web/src/config/models.ts)
    model_selection: Optional[str] = Field(default="gemini-3-flash", description="Modelo preferencial (ex.: gemini-3-flash, gemini-3-pro, gpt-5.2, claude-4.5-sonnet)")
    model_gpt: Optional[str] = Field(default="gpt-5.2", description="Modelo GPT específico (id canônico)")
    model_claude: Optional[str] = Field(default="claude-4.5-sonnet", description="Modelo Claude específico (id canônico)")
    strategist_model: Optional[str] = Field(default=None, description="Modelo para planejamento/outline (id canônico)")
    drafter_models: List[str] = Field(default_factory=list, description="Lista de modelos para redação (ids canônicos)")
    reviewer_models: List[str] = Field(default_factory=list, description="Lista de modelos para revisão/critica (ids canônicos)")
    chat_personality: str = Field(default="juridico", pattern="^(juridico|geral)$", description="Personalidade do chat (juridico|geral)")
    reasoning_level: str = Field(default="medium", pattern="^(none|minimal|low|medium|high|xhigh)$", description="Nível de raciocínio")
    temperature: Optional[float] = Field(default=None, ge=0, le=1, description="Temperatura (criatividade)")
    web_search: bool = Field(default=False, description="Ativar pesquisa na web")
    search_mode: str = Field(default="hybrid", pattern="^(shared|native|hybrid|perplexity)$", description="Modo de busca (shared|native|hybrid|perplexity)")
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
    multi_query: bool = Field(default=True, description="Ativar multi-query para busca web")
    breadth_first: bool = Field(default=False, description="Ativar breadth-first para perguntas amplas")
    research_policy: str = Field(default="auto", pattern="^(auto|force)$", description="Política de pesquisa (auto|force)")
    thesis: Optional[str] = Field(None, description="Tese jurídica ou instruções livres")
    formatting_options: Dict[str, bool] = Field(default_factory=dict, description="Opções de formatação (include_toc, include_summaries, include_summary_table)")
    citation_style: str = Field(default="forense", pattern="^(forense|abnt|hibrido)$", description="Estilo de citação (forense|abnt|hibrido)")
    use_templates: bool = Field(default=False, description="Ativar uso de modelos de peça (RAG)")
    template_filters: Dict[str, Any] = Field(default_factory=dict, description="Filtros para busca de modelos (tipo_peca, area, rito, apenas_clause_bank)")
    rag_sources: Optional[List[str]] = Field(default=None, description="Fontes RAG (lei, juris, pecas_modelo)")
    rag_top_k: Optional[int] = Field(default=None, ge=1, le=50, description="Top K resultados do RAG")
    prompt_extra: Optional[str] = Field(None, description="Instruções adicionais para a redação")
    audit: bool = Field(default=True, description="Executar auditoria jurídica ao final")
    use_langgraph: bool = Field(default=True, description="Usar workflow LangGraph para geração")
    dense_research: bool = Field(default=False, description="Ativar deep research (LangGraph)")
    deep_research_effort: Optional[str] = Field(default=None, pattern="^(low|medium|high|1|2|3)$", description="Esforco do deep research (low|medium|high)")
    deep_research_search_focus: Optional[str] = Field(default=None, pattern="^(web|academic|sec)$")
    deep_research_domain_filter: Optional[str] = None
    deep_research_search_after_date: Optional[str] = None
    deep_research_search_before_date: Optional[str] = None
    deep_research_last_updated_after: Optional[str] = None
    deep_research_last_updated_before: Optional[str] = None
    deep_research_country: Optional[str] = None
    deep_research_latitude: Optional[str] = None
    deep_research_longitude: Optional[str] = None
    adaptive_routing: bool = Field(default=False, description="Ativar roteamento adaptativo (LangGraph)")
    crag_gate: bool = Field(default=False, description="Ativar CRAG gate (LangGraph)")
    crag_min_best_score: float = Field(default=0.45, ge=0, le=1, description="CRAG min best score")
    crag_min_avg_score: float = Field(default=0.35, ge=0, le=1, description="CRAG min avg score")
    hyde_enabled: bool = Field(default=False, description="Ativar HyDE (LangGraph)")
    graph_rag_enabled: bool = Field(default=False, description="Ativar GraphRAG (LangGraph)")
    graph_hops: int = Field(default=1, ge=1, le=5, description="Profundidade do GraphRAG")
    destino: str = Field(default="uso_interno", pattern="^(uso_interno|cliente|contraparte|autoridade|regulador)$")
    risco: str = Field(default="baixo", pattern="^(baixo|medio|alto)$")
    hil_outline_enabled: bool = Field(default=False, description="Habilitar revisão humana do outline (LangGraph)")
    hil_target_sections: List[str] = Field(default_factory=list, description="Seções alvo para HIL (LangGraph)")
    outline_override: List[str] = Field(
        default_factory=list,
        description="Override do outline (1 seção por item). Se vazio, o workflow gera automaticamente.",
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
    document_checklist_hint: List[Dict[str, Any]] = Field(default_factory=list, description="Checklist complementar do usuário")


class DocumentGenerationResponse(BaseModel):
    """Schema de resposta de geração de documento"""
    document_id: str
    content: str
    content_html: str
    metadata: Dict[str, Any]
    statistics: Dict[str, Any]
    cost_info: Dict[str, Any]
    signature_data: Optional[Dict[str, Any]] = None
    
    model_config = ConfigDict(from_attributes=True)


class TemplateVariable(BaseModel):
    """Variável de template"""
    name: str
    type: str = Field(..., pattern="^(text|number|date|boolean|select|user_field)$")
    label: str
    description: Optional[str] = None
    required: bool = True
    default_value: Optional[Any] = None
    options: Optional[List[str]] = None
    user_field_mapping: Optional[str] = Field(None, description="Campo do usuário a mapear (ex: name, oab, cnpj)")


class DocumentTemplate(BaseModel):
    """Template de documento"""
    id: Optional[str] = None
    name: str
    description: Optional[str] = None
    document_type: str
    content_template: str = Field(..., description="Template com variáveis {{variable_name}}")
    variables: List[TemplateVariable] = Field(default_factory=list)
    require_signature: bool = True
    is_public: bool = False
    user_id: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)


class SignatureRequest(BaseModel):
    """Schema para adicionar/atualizar assinatura"""
    signature_image: Optional[str] = Field(None, description="Imagem da assinatura em base64")
    signature_text: Optional[str] = Field(None, description="Texto da assinatura")


class SignatureResponse(BaseModel):
    """Schema de resposta de assinatura"""
    user_id: str
    signature_data: Dict[str, Any]
    created_at: datetime
    updated_at: datetime
