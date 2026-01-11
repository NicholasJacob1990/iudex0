"""
Schemas Pydantic para documentos
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


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
    metadata: Dict[str, Any] = Field(default_factory=dict)
    folder_id: Optional[str] = None
    is_shared: bool
    is_archived: bool
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


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
    context_documents: List[str] = Field(default_factory=list, description="IDs de documentos para contexto")
    effort_level: int = Field(default=3, ge=1, le=5, description="Nível de esforço (1-5)")
    min_pages: Optional[int] = Field(default=None, ge=0, description="Mínimo de páginas desejado (0 = auto)")
    max_pages: Optional[int] = Field(default=None, ge=0, description="Máximo de páginas desejado (0 = auto)")
    attachment_mode: str = Field(default="rag_local", pattern="^(rag_local|prompt_injection)$", description="Como usar anexos (rag_local|prompt_injection)")
    include_signature: bool = Field(default=True, description="Incluir assinatura no documento")
    template_id: Optional[str] = Field(None, description="ID do template a ser usado")
    variables: Dict[str, Any] = Field(default_factory=dict, description="Variáveis do template")
    language: str = "pt-BR"
    tone: str = Field(default="formal", description="Tom do documento (formal, informal, técnico)")
    max_length: Optional[int] = Field(None, description="Comprimento máximo em palavras")
    use_multi_agent: bool = Field(default=True, description="Ativar modo multi-agente (debate)")
    # IDs canônicos (ver apps/api/app/services/ai/model_registry.py e apps/web/src/config/models.ts)
    model_selection: Optional[str] = Field(default="gemini-3-pro", description="Modelo preferencial (ex.: gemini-3-pro, gemini-3-flash, gpt-5.2, claude-4.5-sonnet)")
    model_gpt: Optional[str] = Field(default="gpt-5.2", description="Modelo GPT específico (id canônico)")
    model_claude: Optional[str] = Field(default="claude-4.5-sonnet", description="Modelo Claude específico (id canônico)")
    strategist_model: Optional[str] = Field(default=None, description="Modelo para planejamento/outline (id canônico)")
    drafter_models: List[str] = Field(default_factory=list, description="Lista de modelos para redação (ids canônicos)")
    reviewer_models: List[str] = Field(default_factory=list, description="Lista de modelos para revisão/critica (ids canônicos)")
    chat_personality: str = Field(default="juridico", pattern="^(juridico|geral)$", description="Personalidade do chat (juridico|geral)")
    reasoning_level: str = Field(default="medium", pattern="^(low|medium|high)$", description="Nível de raciocínio")
    web_search: bool = Field(default=False, description="Ativar pesquisa na web")
    thesis: Optional[str] = Field(None, description="Tese jurídica ou instruções livres")
    formatting_options: Dict[str, bool] = Field(default_factory=dict, description="Opções de formatação (include_toc, include_summaries, include_summary_table)")
    citation_style: str = Field(default="forense", pattern="^(forense|abnt|hibrido)$", description="Estilo de citação (forense|abnt|hibrido)")
    use_templates: bool = Field(default=False, description="Ativar uso de modelos de peça (RAG)")
    template_filters: Dict[str, Any] = Field(default_factory=dict, description="Filtros para busca de modelos (tipo_peca, area, rito, apenas_clause_bank)")
    prompt_extra: Optional[str] = Field(None, description="Instruções adicionais para a redação")
    audit: bool = Field(default=True, description="Executar auditoria jurídica ao final")
    use_langgraph: bool = Field(default=True, description="Usar workflow LangGraph para geração")
    dense_research: bool = Field(default=False, description="Ativar deep research (LangGraph)")
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


class DocumentGenerationResponse(BaseModel):
    """Schema de resposta de geração de documento"""
    document_id: str
    content: str
    content_html: str
    metadata: Dict[str, Any]
    statistics: Dict[str, Any]
    cost_info: Dict[str, Any]
    signature_data: Optional[Dict[str, Any]] = None
    
    class Config:
        from_attributes = True


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
    
    class Config:
        from_attributes = True


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
