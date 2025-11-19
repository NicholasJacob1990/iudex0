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
    type: str = Field(..., regex="^(quick|detailed|audio|podcast)$")
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
    include_signature: bool = Field(default=True, description="Incluir assinatura no documento")
    template_id: Optional[str] = Field(None, description="ID do template a ser usado")
    variables: Dict[str, Any] = Field(default_factory=dict, description="Variáveis do template")
    language: str = "pt-BR"
    tone: str = Field(default="formal", description="Tom do documento (formal, informal, técnico)")
    max_length: Optional[int] = Field(None, description="Comprimento máximo em palavras")


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
    type: str = Field(..., regex="^(text|number|date|boolean|select|user_field)$")
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

