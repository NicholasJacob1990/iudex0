"""
Schemas Pydantic para integração com serviço de tribunais
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ConfigDict


# =============================================================================
# Enums
# =============================================================================


class TribunalType(str, Enum):
    """Tipos de tribunal suportados"""
    PJE = "pje"
    EPROC = "eproc"
    ESAJ = "esaj"


class AuthType(str, Enum):
    """Tipos de autenticação"""
    PASSWORD = "password"
    CERTIFICATE_A1 = "certificate_a1"
    CERTIFICATE_A3_PHYSICAL = "certificate_a3_physical"
    CERTIFICATE_A3_CLOUD = "certificate_a3_cloud"


class OperationType(str, Enum):
    """Tipos de operação"""
    CONSULTAR_PROCESSO = "consultar_processo"
    LISTAR_DOCUMENTOS = "listar_documentos"
    LISTAR_MOVIMENTACOES = "listar_movimentacoes"
    BAIXAR_DOCUMENTO = "baixar_documento"
    BAIXAR_PROCESSO = "baixar_processo"
    PETICIONAR = "peticionar"
    ACOMPANHAR = "acompanhar"


class JobStatus(str, Enum):
    """Status de jobs na fila"""
    PENDING = "pending"
    PROCESSING = "processing"
    WAITING_SIGN = "waiting_sign"
    COMPLETED = "completed"
    FAILED = "failed"


class PeticaoTipo(str, Enum):
    """Tipos de petição"""
    PETICAO_INICIAL = "peticao_inicial"
    PETICAO_INTERMEDIARIA = "peticao_intermediaria"
    RECURSO = "recurso"
    OUTROS = "outros"


class CloudProvider(str, Enum):
    """Provedores de certificado A3 na nuvem"""
    CERTISIGN = "certisign"
    SERASA = "serasa"
    SAFEWEB = "safeweb"


# =============================================================================
# Request Schemas - Credenciais
# =============================================================================


class PasswordCredentialCreate(BaseModel):
    """Schema para criar credencial com senha"""
    user_id: str = Field(..., alias="userId")
    tribunal: TribunalType
    tribunal_url: str = Field(..., alias="tribunalUrl")
    name: str = Field(..., min_length=1, max_length=100)
    cpf: str = Field(..., pattern=r"^\d{11}$")
    password: str = Field(..., min_length=1)

    model_config = ConfigDict(populate_by_name=True)


class CertificateA1Create(BaseModel):
    """Schema para criar credencial com certificado A1"""
    user_id: str = Field(..., alias="userId")
    tribunal: TribunalType
    tribunal_url: str = Field(..., alias="tribunalUrl")
    name: str = Field(..., min_length=1, max_length=100)
    pfx_base64: str = Field(..., alias="pfxBase64")
    pfx_password: str = Field(..., alias="pfxPassword")
    expires_at: Optional[datetime] = Field(None, alias="expiresAt")

    model_config = ConfigDict(populate_by_name=True)


class CertificateA3CloudCreate(BaseModel):
    """Schema para criar credencial com certificado A3 na nuvem"""
    user_id: str = Field(..., alias="userId")
    tribunal: TribunalType
    tribunal_url: str = Field(..., alias="tribunalUrl")
    name: str = Field(..., min_length=1, max_length=100)
    provider: CloudProvider

    model_config = ConfigDict(populate_by_name=True)


class CertificateA3PhysicalCreate(BaseModel):
    """Schema para criar credencial com certificado A3 físico"""
    user_id: str = Field(..., alias="userId")
    tribunal: TribunalType
    tribunal_url: str = Field(..., alias="tribunalUrl")
    name: str = Field(..., min_length=1, max_length=100)

    model_config = ConfigDict(populate_by_name=True)


class CredentialDelete(BaseModel):
    """Schema para deletar credencial"""
    user_id: str = Field(..., alias="userId")

    model_config = ConfigDict(populate_by_name=True)


# =============================================================================
# Response Schemas - Credenciais
# =============================================================================


class CredentialResponse(BaseModel):
    """Schema de resposta para credencial"""
    id: str
    user_id: str = Field(..., alias="userId")
    tribunal: TribunalType
    tribunal_url: str = Field(..., alias="tribunalUrl")
    auth_type: AuthType = Field(..., alias="authType")
    name: str
    cloud_provider: Optional[CloudProvider] = Field(None, alias="cloudProvider")
    expires_at: Optional[datetime] = Field(None, alias="expiresAt")
    last_used_at: Optional[datetime] = Field(None, alias="lastUsedAt")
    created_at: datetime = Field(..., alias="createdAt")
    updated_at: datetime = Field(..., alias="updatedAt")

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


class CredentialListResponse(BaseModel):
    """Schema de resposta para lista de credenciais"""
    credentials: List[CredentialResponse]
    total: int


# =============================================================================
# Request Schemas - Operações
# =============================================================================


class OperationSyncRequest(BaseModel):
    """Schema para operação síncrona"""
    credential_id: str = Field(..., alias="credentialId")
    operation: OperationType
    params: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(populate_by_name=True)


class OperationAsyncRequest(BaseModel):
    """Schema para operação assíncrona"""
    user_id: str = Field(..., alias="userId")
    credential_id: str = Field(..., alias="credentialId")
    operation: OperationType
    params: Dict[str, Any] = Field(default_factory=dict)
    webhook_url: Optional[str] = Field(None, alias="webhookUrl")

    model_config = ConfigDict(populate_by_name=True)


class PeticionarArquivo(BaseModel):
    """Schema para arquivo de petição"""
    name: str
    path: Optional[str] = None
    base64: Optional[str] = None
    mime_type: str = Field(..., alias="mimeType")
    tipo_documento: Optional[str] = Field(None, alias="tipoDocumento")

    model_config = ConfigDict(populate_by_name=True)


class PeticionarRequest(BaseModel):
    """Schema para peticionamento"""
    user_id: str = Field(..., alias="userId")
    credential_id: str = Field(..., alias="credentialId")
    processo: str
    tipo: PeticaoTipo
    arquivos: List[PeticionarArquivo]
    webhook_url: Optional[str] = Field(None, alias="webhookUrl")

    model_config = ConfigDict(populate_by_name=True)


# =============================================================================
# Response Schemas - Operações
# =============================================================================


class OperationSyncResponse(BaseModel):
    """Schema de resposta para operação síncrona"""
    success: bool
    operation: OperationType
    data: Optional[Any] = None
    error: Optional[str] = None
    executed_at: datetime = Field(..., alias="executedAt")

    model_config = ConfigDict(populate_by_name=True)


class OperationAsyncResponse(BaseModel):
    """Schema de resposta para operação assíncrona"""
    job_id: str = Field(..., alias="jobId")
    queue_id: Optional[str] = Field(None, alias="queueId")
    status: JobStatus
    message: str
    requires_interaction: bool = Field(False, alias="requiresInteraction")

    model_config = ConfigDict(populate_by_name=True)


class JobStatusResponse(BaseModel):
    """Schema de resposta para status de job"""
    job_id: str = Field(..., alias="jobId")
    status: str
    progress: Optional[Any] = None
    data: Optional[Dict[str, Any]] = None
    result: Optional[Any] = None
    failed_reason: Optional[str] = Field(None, alias="failedReason")
    created_at: Optional[datetime] = Field(None, alias="createdAt")
    processed_at: Optional[datetime] = Field(None, alias="processedAt")
    finished_at: Optional[datetime] = Field(None, alias="finishedAt")

    model_config = ConfigDict(populate_by_name=True)


# =============================================================================
# Response Schemas - Processo
# =============================================================================


class ParteProcesso(BaseModel):
    """Schema para parte do processo"""
    polo: str
    nome: str
    documento: Optional[str] = None
    advogados: Optional[List[str]] = None


class ProcessoInfo(BaseModel):
    """Schema para informações do processo"""
    numero: str
    classe: Optional[str] = None
    assunto: Optional[str] = None
    vara: Optional[str] = None
    comarca: Optional[str] = None
    data_distribuicao: Optional[datetime] = Field(None, alias="dataDistribuicao")
    valor_causa: Optional[float] = Field(None, alias="valorCausa")
    partes: Optional[List[ParteProcesso]] = None
    situacao: Optional[str] = None
    ultima_movimentacao: Optional[datetime] = Field(None, alias="ultimaMovimentacao")

    model_config = ConfigDict(populate_by_name=True)


class DocumentoInfo(BaseModel):
    """Schema para documento do processo"""
    id: str
    numero: Optional[str] = None
    tipo: str
    descricao: Optional[str] = None
    data_juntada: datetime = Field(..., alias="dataJuntada")
    tamanho: Optional[int] = None
    assinado: Optional[bool] = None
    signatarios: Optional[List[str]] = None

    model_config = ConfigDict(populate_by_name=True)


class MovimentacaoInfo(BaseModel):
    """Schema para movimentação do processo"""
    id: str
    data: datetime
    tipo: str
    descricao: str
    responsavel: Optional[str] = None
    documentos: Optional[List[str]] = None


# =============================================================================
# Webhook Schemas
# =============================================================================


class WebhookEvent(BaseModel):
    """Schema para evento de webhook do serviço de tribunais"""
    event_type: str = Field(..., alias="eventType")
    job_id: str = Field(..., alias="jobId")
    user_id: str = Field(..., alias="userId")
    status: JobStatus
    operation: OperationType
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    timestamp: datetime

    model_config = ConfigDict(populate_by_name=True)


class WebhookResponse(BaseModel):
    """Schema de resposta para webhook"""
    received: bool
    message: str


# =============================================================================
# Error Schemas
# =============================================================================


class TribunaisError(BaseModel):
    """Schema para erro do serviço de tribunais"""
    error: str
    detail: Optional[str] = None
    requires_interaction: bool = Field(False, alias="requiresInteraction")
    auth_type: Optional[AuthType] = Field(None, alias="authType")

    model_config = ConfigDict(populate_by_name=True)
