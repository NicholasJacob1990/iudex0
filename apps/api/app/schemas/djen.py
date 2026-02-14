"""
Schemas Pydantic para integração DJEN
"""

from datetime import date, datetime
from typing import List, Optional
import re
from pydantic import BaseModel, Field, field_validator, model_validator


# =============================================================================
# Parâmetros de Busca (Comunica API)
# =============================================================================

class DjenSearchParams(BaseModel):
    """
    Parâmetros de busca na API Comunica.
    Pelo menos um filtro obrigatório: siglaTribunal, nomeParte, nomeAdvogado, numeroOab, numeroProcesso
    """
    siglaTribunal: Optional[str] = Field(None, description="Sigla do tribunal (ex: TJMG, TRF1)")
    numeroOab: Optional[str] = Field(None, description="Número OAB (apenas dígitos)")
    ufOab: Optional[str] = Field(None, description="UF da OAB (ex: MG, SP)")
    nomeAdvogado: Optional[str] = Field(None, description="Nome do advogado (busca parcial)")
    nomeParte: Optional[str] = Field(None, description="Nome da parte (busca parcial)")
    texto: Optional[str] = Field(None, description="Busca textual livre")
    numeroProcesso: Optional[str] = Field(None, description="Número do processo (apenas dígitos)")
    dataDisponibilizacaoInicio: Optional[str] = Field(None, description="Data início (YYYY-MM-DD)")
    dataDisponibilizacaoFim: Optional[str] = Field(None, description="Data fim (YYYY-MM-DD)")
    meio: str = Field("D", description="D=Diário, E=Edital")
    itensPorPagina: Optional[int] = Field(None, description="Itens por página (5 ou 100)")
    maxPages: Optional[int] = Field(None, description="Máximo de páginas a buscar")

    @field_validator("itensPorPagina")
    @classmethod
    def validate_itens_por_pagina(cls, value: Optional[int]) -> Optional[int]:
        if value is None:
            return value
        if value not in (5, 100):
            raise ValueError("itensPorPagina must be 5 or 100")
        return value

    @field_validator("maxPages")
    @classmethod
    def validate_max_pages(cls, value: Optional[int]) -> Optional[int]:
        if value is None:
            return value
        if value < 1:
            raise ValueError("maxPages must be >= 1")
        return value

    @field_validator("dataDisponibilizacaoInicio", "dataDisponibilizacaoFim")
    @classmethod
    def validate_date_format(cls, value: Optional[str]) -> Optional[str]:
        if not value:
            return value
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", value):
            raise ValueError("date must be in YYYY-MM-DD format")
        return value

    @model_validator(mode="after")
    def validate_filters(self):
        has_filter = any([
            self.siglaTribunal,
            self.nomeParte,
            self.nomeAdvogado,
            self.numeroOab,
            self.numeroProcesso,
            self.texto,
        ])
        if not has_filter:
            raise ValueError("At least one filter is required")
        if self.numeroOab and not self.ufOab:
            raise ValueError("ufOab is required when numeroOab is provided")
        return self


# =============================================================================
# DataJud (Metadados CNJ)
# =============================================================================

class DatajudSearchParams(BaseModel):
    """Busca de metadados no DataJud"""
    npu: str = Field(..., description="Número do processo (com ou sem formatação)")
    tribunal_sigla: Optional[str] = Field(None, description="Sigla do tribunal (ex: TJMG)")

    @field_validator("npu")
    @classmethod
    def validate_npu_digits(cls, value: str) -> str:
        digits = re.sub(r"\D", "", value or "")
        if not digits:
            raise ValueError("npu is required")
        return digits


class DatajudMovement(BaseModel):
    """Movimento do processo retornado pelo DataJud"""
    nome: Optional[str]
    data_hora: Optional[str]
    codigo: Optional[str]

    class Config:
        from_attributes = True


class DatajudProcessResponse(BaseModel):
    """Resposta resumida de metadados do processo"""
    numero_processo: str
    tribunal_sigla: str
    classe: Optional[str]
    orgao_julgador: Optional[str]
    sistema: Optional[str]
    formato: Optional[str]
    grau: Optional[str]
    nivel_sigilo: Optional[str]
    data_ajuizamento: Optional[str]
    data_ultima_atualizacao: Optional[str]
    assuntos: List[str] = Field(default_factory=list)
    ultimo_movimento: Optional[DatajudMovement]
    movimentos: List[DatajudMovement] = Field(default_factory=list)

    class Config:
        from_attributes = True


# =============================================================================
# Watchlist (Processos Monitorados)
# =============================================================================

class ProcessWatchlistCreate(BaseModel):
    """Criar novo item na watchlist"""
    npu: str = Field(..., description="Número do processo")
    tribunal_sigla: str = Field(..., description="Sigla do tribunal (ex: TJMG)")
    case_id: Optional[str] = Field(None, description="ID do caso para vincular")
    sync_frequency: str = Field("daily", description="Frequência: daily, twice_daily, weekly, custom")
    sync_time: str = Field("06:00", description="Horário do sync (HH:MM)")
    sync_cron: Optional[str] = Field(None, description="Cron customizado (quando frequency=custom)")
    sync_timezone: str = Field("America/Sao_Paulo", description="Timezone do usuário")

    @field_validator("sync_frequency")
    @classmethod
    def validate_frequency(cls, value: str) -> str:
        allowed = ("daily", "twice_daily", "weekly", "custom")
        if value not in allowed:
            raise ValueError(f"sync_frequency must be one of {allowed}")
        return value

    @field_validator("sync_time")
    @classmethod
    def validate_time(cls, value: str) -> str:
        if not re.match(r"^\d{2}:\d{2}$", value):
            raise ValueError("sync_time must be in HH:MM format")
        return value


class ProcessWatchlistUpdate(BaseModel):
    """Atualizar agendamento de watchlist"""
    sync_frequency: Optional[str] = None
    sync_time: Optional[str] = None
    sync_cron: Optional[str] = None
    sync_timezone: Optional[str] = None

    @field_validator("sync_frequency")
    @classmethod
    def validate_frequency(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        allowed = ("daily", "twice_daily", "weekly", "custom")
        if value not in allowed:
            raise ValueError(f"sync_frequency must be one of {allowed}")
        return value

    @field_validator("sync_time")
    @classmethod
    def validate_time(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        if not re.match(r"^\d{2}:\d{2}$", value):
            raise ValueError("sync_time must be in HH:MM format")
        return value


class ProcessWatchlistResponse(BaseModel):
    """Resposta de item da watchlist"""
    id: str
    npu: str
    npu_formatted: Optional[str]
    tribunal_sigla: str
    tribunal_alias: str
    is_active: bool
    last_datajud_check: Optional[datetime]
    last_mov_datetime: Optional[str]
    case_id: Optional[str]
    sync_frequency: str = "daily"
    sync_time: str = "06:00"
    sync_cron: Optional[str] = None
    sync_timezone: str = "America/Sao_Paulo"
    next_sync_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class OabWatchlistCreate(BaseModel):
    """Criar novo item de rastreamento por OAB"""
    numero_oab: str = Field(..., description="Número da OAB (apenas dígitos)")
    uf_oab: str = Field(..., description="UF da OAB (ex: MG)")
    sigla_tribunal: Optional[str] = Field(None, description="Sigla do tribunal (opcional)")
    meio: Optional[str] = Field("D", description="D=Diário, E=Edital")
    max_pages: Optional[int] = Field(3, description="Máximo de páginas por sync")
    sync_frequency: str = Field("daily", description="Frequência: daily, twice_daily, weekly, custom")
    sync_time: str = Field("06:00", description="Horário do sync (HH:MM)")
    sync_cron: Optional[str] = Field(None, description="Cron customizado")
    sync_timezone: str = Field("America/Sao_Paulo", description="Timezone")

    @field_validator("numero_oab")
    @classmethod
    def validate_oab_digits(cls, value: str) -> str:
        if not value or not value.isdigit():
            raise ValueError("numero_oab must contain only digits")
        return value

    @field_validator("uf_oab")
    @classmethod
    def validate_uf(cls, value: str) -> str:
        if not value or len(value.strip()) != 2:
            raise ValueError("uf_oab must be a 2-letter UF")
        return value.upper()

    @field_validator("max_pages")
    @classmethod
    def validate_max_pages(cls, value: Optional[int]) -> Optional[int]:
        if value is None:
            return value
        if value < 1:
            raise ValueError("max_pages must be >= 1")
        return value


class OabWatchlistResponse(BaseModel):
    """Resposta de item de rastreamento por OAB"""
    id: str
    numero_oab: str
    uf_oab: str
    sigla_tribunal: Optional[str]
    meio: Optional[str]
    max_pages: Optional[int]
    last_sync_date: Optional[date]
    is_active: bool
    sync_frequency: str = "daily"
    sync_time: str = "06:00"
    sync_cron: Optional[str] = None
    sync_timezone: str = "America/Sao_Paulo"
    next_sync_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# =============================================================================
# Destinatários
# =============================================================================

class DestinatarioResponse(BaseModel):
    """Destinatário de uma intimação"""
    nome: str
    polo: Optional[str]


class AdvogadoResponse(BaseModel):
    """Advogado destinatário de uma intimação"""
    nome: str
    numero_oab: Optional[str]
    uf_oab: Optional[str]


# =============================================================================
# Intimações
# =============================================================================

class DjenIntimationResponse(BaseModel):
    """Resposta de intimação capturada"""
    id: str
    hash: str
    numero_processo: str
    numero_processo_mascara: Optional[str]
    tribunal_sigla: str
    tipo_comunicacao: Optional[str]
    nome_orgao: Optional[str]
    texto: Optional[str]
    data_disponibilizacao: Optional[date]
    meio: Optional[str]
    link: Optional[str]
    tipo_documento: Optional[str]
    nome_classe: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class DjenIntimationBrief(BaseModel):
    """Versão resumida para listagens"""
    id: str
    hash: str
    numero_processo: str
    tribunal_sigla: str
    data_disponibilizacao: Optional[date]
    texto_resumo: Optional[str] = Field(None, description="Primeiros 200 caracteres do texto")

    class Config:
        from_attributes = True


class DjenIntimationSearchResponse(BaseModel):
    """Resposta detalhada para busca na API Comunica"""
    id: str
    hash: str
    numero_processo: str
    numero_processo_mascara: Optional[str]
    tribunal_sigla: str
    tipo_comunicacao: Optional[str]
    nome_orgao: Optional[str]
    texto: Optional[str]
    texto_resumo: Optional[str]
    data_disponibilizacao: Optional[date]
    meio: Optional[str]
    link: Optional[str]
    tipo_documento: Optional[str]
    nome_classe: Optional[str]
    numero_comunicacao: Optional[int]
    destinatarios: List[DestinatarioResponse] = Field(default_factory=list)
    advogados: List[AdvogadoResponse] = Field(default_factory=list)


# =============================================================================
# Resultados de Sincronização
# =============================================================================

class SyncResult(BaseModel):
    """Resultado de sincronização manual ou automática"""
    total_checked: int = Field(0, description="Processos verificados")
    new_intimations: int = Field(0, description="Novas intimações encontradas")
    updated_watchlist: int = Field(0, description="Itens da watchlist atualizados")
    errors: List[str] = Field(default_factory=list, description="Erros encontrados")
