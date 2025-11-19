"""
Schemas Pydantic para chat e minutas
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


class ChatBase(BaseModel):
    """Schema base de chat"""
    title: str = Field(..., min_length=1, max_length=255)
    mode: str = Field(..., regex="^(CHAT|MINUTA)$")


class ChatCreate(ChatBase):
    """Schema para criação de chat"""
    context: Dict[str, Any] = Field(default_factory=dict)


class ChatUpdate(BaseModel):
    """Schema para atualização de chat"""
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    mode: Optional[str] = Field(None, regex="^(CHAT|MINUTA)$")
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
    prompt: str = Field(..., min_length=10)
    effort_level: int = Field(default=3, ge=1, le=5)
    context: Dict[str, Any] = Field(default_factory=dict)
    verbosity: str = Field(default="balanced", regex="^(concise|balanced|detailed)$")
    use_profile: Optional[str] = None


class GenerateDocumentResponse(BaseModel):
    """Schema de resposta de geração"""
    content: str
    reviews: List[Dict[str, Any]] = Field(default_factory=list)
    consensus: bool
    conflicts: List[str] = Field(default_factory=list)
    total_tokens: int
    total_cost: float
    processing_time: float
    metadata: Dict[str, Any]

