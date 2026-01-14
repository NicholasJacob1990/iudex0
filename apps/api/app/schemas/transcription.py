from pydantic import BaseModel, Field
from typing import Optional

class TranscriptionRequest(BaseModel):
    """Schema para requisição de transcrição via MLX Vomo"""
    mode: str = Field(default="APOSTILA", description="Modo de formatação: APOSTILA, FIDELIDADE ou RAW")
    thinking_level: str = Field(default="medium", pattern="^(low|medium|high)$", description="Nível de pensamento (thinking budget)")
    custom_prompt: Optional[str] = Field(None, description="Prompt customizado para sobrescrever o padrão")
    model_selection: str = Field(default="gemini-3-flash-preview", description="Modelo LLM para formatação")


class HearingTranscriptionRequest(BaseModel):
    """Schema para transcrição de audiências/reuniões."""
    case_id: str = Field(..., description="Identificador do caso/processo")
    goal: str = Field(
        default="alegacoes_finais",
        description="Objetivo jurídico: peticao_inicial, contestacao, alegacoes_finais, sentenca"
    )
    model_selection: str = Field(default="gemini-3-flash-preview", description="Modelo LLM para análise")
    high_accuracy: bool = Field(default=False, description="Usa Beam Search (mais lento)")
    format_mode: str = Field(default="AUDIENCIA", description="Modo de formatação: AUDIENCIA ou DEPOIMENTO")
    custom_prompt: Optional[str] = Field(None, description="Prompt customizado de estilo/tabela")
    format_enabled: bool = Field(default=True, description="Gera texto formatado adicional")


class HearingSpeakerUpdate(BaseModel):
    speaker_id: str = Field(..., description="ID interno do falante")
    name: Optional[str] = Field(None, description="Nome editado do falante")
    role: Optional[str] = Field(None, description="Papel jurídico")
    source: Optional[str] = Field(default="manual", description="Origem da edição")


class HearingSpeakersUpdateRequest(BaseModel):
    case_id: str = Field(..., description="Identificador do caso/processo")
    speakers: list[HearingSpeakerUpdate] = Field(default_factory=list)
