from pydantic import BaseModel, Field
from typing import Optional

class TranscriptionRequest(BaseModel):
    """Schema para requisição de transcrição via MLX Vomo"""
    mode: str = Field(default="APOSTILA", description="Modo de formatação: APOSTILA, FIDELIDADE ou RAW")
    thinking_level: str = Field(default="medium", pattern="^(low|medium|high)$", description="Nível de pensamento (thinking budget)")
    custom_prompt: Optional[str] = Field(None, description="Prompt customizado para sobrescrever o padrão")
    model_selection: str = Field(default="gemini-3-flash-preview", description="Modelo LLM para formatação")
