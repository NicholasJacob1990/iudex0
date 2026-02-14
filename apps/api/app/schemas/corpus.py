"""
Schemas Pydantic para o Corpus — interface unificada de gestão RAG.

O Corpus agrega dados de OpenSearch (lexical), Qdrant (vector) e Neo4j (graph),
fornecendo uma visão única e gerenciável de toda a base de conhecimento.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# =============================================================================
# Enums como literais para validação
# =============================================================================

VALID_SCOPES = ("global", "private", "group", "local")
VALID_COLLECTIONS = ("lei", "juris", "pecas_modelo", "doutrina", "sei", "local")
VALID_STATUSES = ("ingested", "pending", "processing", "failed")
VALID_SOURCES = ("lexical", "vector", "graph")


# =============================================================================
# Stats
# =============================================================================


class CorpusStats(BaseModel):
    """Estatísticas agregadas do Corpus."""

    total_documents: int = Field(..., description="Total de documentos no Corpus")
    by_scope: Dict[str, int] = Field(
        default_factory=dict,
        description="Contagem por escopo (global, private, local)",
    )
    by_collection: Dict[str, int] = Field(
        default_factory=dict,
        description="Contagem por coleção (lei, juris, pecas_modelo, ...)",
    )
    pending_ingestion: int = Field(0, description="Documentos aguardando ingestão")
    failed_ingestion: int = Field(0, description="Documentos com falha na ingestão")
    last_indexed_at: Optional[datetime] = Field(
        None, description="Timestamp da última indexação"
    )
    storage_size_mb: Optional[float] = Field(
        None, description="Tamanho estimado de armazenamento em MB"
    )

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# Document
# =============================================================================


class CorpusDocument(BaseModel):
    """Representação de um documento no Corpus."""

    id: str = Field(..., description="ID do documento")
    name: str = Field(..., description="Nome do documento")
    collection: Optional[str] = Field(
        None, description="Coleção (lei, juris, pecas_modelo, doutrina, sei, local)"
    )
    scope: Optional[str] = Field(
        None, description="Escopo (global, private, local)"
    )
    status: str = Field(
        "pending", description="Status (ingested, pending, processing, failed)"
    )
    ingested_at: Optional[datetime] = Field(
        None, description="Data da ingestão RAG"
    )
    expires_at: Optional[datetime] = Field(
        None, description="Expiração (apenas para escopo local)"
    )
    chunk_count: Optional[int] = Field(
        None, description="Quantidade de chunks indexados"
    )
    file_type: Optional[str] = Field(None, description="Tipo do arquivo")
    size_bytes: Optional[int] = Field(None, description="Tamanho em bytes")
    jurisdiction: Optional[str] = Field(
        None,
        description="Jurisdição (ISO-3166 alpha-2, ex.: BR, US, UK) ou INT. Normalmente presente apenas para scope=global.",
    )
    source_id: Optional[str] = Field(
        None,
        description="Sub-fonte regional (ex.: br_stf, br_planalto). Normalmente presente apenas para scope=global.",
    )

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# Regional Sources (Global Corpus)
# =============================================================================


class CorpusRegionalSource(BaseModel):
    """Fonte regional do Corpus Global (catálogo declarativo)."""

    id: str = Field(..., description="ID estável da fonte (ex.: br_stf)")
    label: str = Field(..., description="Nome exibido (ex.: STF)")
    jurisdiction: str = Field(
        ..., description="Jurisdição (ISO-3166 alpha-2, EU, INT)"
    )
    collections: List[str] = Field(
        default_factory=list,
        description="Coleções sugeridas (lei, juris, doutrina, pecas_modelo, sei).",
    )
    domains: List[str] = Field(
        default_factory=list,
        description="Domínios associados (informativo; útil para web-search allowlist no futuro).",
    )
    description: Optional[str] = Field(None, description="Descrição curta (opcional).")
    status: Optional[str] = Field(None, description="EA/GA (informativo).")
    sync: Optional[str] = Field(None, description="Live/Weekly/manual (informativo).")


class CorpusRegionalSourcesCatalogResponse(BaseModel):
    """Catálogo de fontes regionais (para UI/seleção no chat)."""

    sources: List[CorpusRegionalSource] = Field(default_factory=list)
    jurisdictions: List[str] = Field(default_factory=list, description="Códigos presentes no catálogo.")
    updated_at: Optional[datetime] = None


class CorpusDocumentList(BaseModel):
    """Lista paginada de documentos do Corpus."""

    items: List[CorpusDocument] = Field(default_factory=list)
    total: int = Field(0, description="Total de documentos")
    page: int = Field(1, description="Página atual")
    per_page: int = Field(20, description="Itens por página")

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# Ingest
# =============================================================================


class CorpusIngestRequest(BaseModel):
    """Requisição para ingestão de documentos no Corpus."""

    document_ids: List[str] = Field(
        ..., min_length=1, max_length=100, description="IDs dos documentos"
    )
    collection: str = Field(..., description="Coleção alvo")
    scope: str = Field("private", description="Escopo (global, private, group, local)")
    jurisdiction: Optional[str] = Field(
        default=None,
        description="Jurisdição do documento (ISO-3166 alpha-2, ex.: BR, US, UK) ou INT. Recomendado para scope=global.",
    )
    source_id: Optional[str] = Field(
        default=None,
        description="ID opcional da sub-fonte regional (ex.: br_stf, br_planalto). Recomendado para scope=global quando aplicável.",
    )
    group_ids: Optional[List[str]] = Field(
        default=None,
        description="IDs de equipes/departamentos (obrigatório quando scope='group')",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "document_ids": ["doc-123", "doc-456"],
                "collection": "lei",
                "scope": "global",
            }
        }
    )


class CorpusBackfillJurisdictionRequest(BaseModel):
    """Requisição para backfill de jurisdição nos índices RAG (admin)."""

    jurisdiction: str = Field(
        default="BR",
        description="Código de jurisdição (ISO-3166 alpha-2, ex.: BR, US, UK) ou INT.",
    )
    collections: Optional[List[str]] = Field(
        default=None,
        description="Restringir a coleções específicas (lei, juris, pecas_modelo, doutrina, sei). Default: todas exceto local.",
    )
    dry_run: bool = Field(
        default=True,
        description="Se True, apenas calcula quantos registros seriam afetados (não altera).",
    )
    limit: int = Field(
        default=0,
        ge=0,
        description="Limite máximo de itens por backend (0 = sem limite). Útil para testes.",
    )


class CorpusBackfillJurisdictionResponse(BaseModel):
    """Resposta do backfill de jurisdição (admin)."""

    jurisdiction: str
    dry_run: bool
    collections: List[str]
    opensearch_updated: int = 0
    qdrant_updated: int = 0
    opensearch_details: Dict[str, Any] = Field(default_factory=dict)
    qdrant_details: Dict[str, Any] = Field(default_factory=dict)


class CorpusBackfillSourceIdRequest(BaseModel):
    """Requisição para backfill de `source_id` nos índices RAG (admin)."""

    source_id: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="ID da sub-fonte regional a aplicar (ex.: br_stf, br_planalto).",
    )
    collections: Optional[List[str]] = Field(
        default=None,
        description="Restringir a coleções específicas (lei, juris, pecas_modelo, doutrina, sei). Default: todas exceto local.",
    )
    dry_run: bool = Field(
        default=True,
        description="Se True, apenas calcula quantos registros seriam afetados (não altera).",
    )
    limit: int = Field(
        default=0,
        ge=0,
        description="Limite máximo de itens por backend (0 = sem limite). Útil para testes.",
    )


class CorpusBackfillSourceIdResponse(BaseModel):
    """Resposta do backfill de `source_id` (admin)."""

    source_id: str
    dry_run: bool
    collections: List[str]
    opensearch_updated: int = 0
    qdrant_updated: int = 0
    opensearch_details: Dict[str, Any] = Field(default_factory=dict)
    qdrant_details: Dict[str, Any] = Field(default_factory=dict)


class CorpusIngestResponse(BaseModel):
    """Resposta da ingestão no Corpus."""

    queued: int = Field(0, description="Documentos enfileirados para ingestão")
    skipped: int = Field(0, description="Documentos ignorados (já ingeridos)")
    errors: List[Dict[str, str]] = Field(
        default_factory=list, description="Erros encontrados"
    )


# =============================================================================
# Search
# =============================================================================


class CorpusSearchRequest(BaseModel):
    """Requisição de busca unificada no Corpus."""

    query: str = Field(
        ..., min_length=1, max_length=10000, description="Consulta de busca"
    )
    collections: Optional[List[str]] = Field(
        None, description="Filtrar por coleções (None = todas)"
    )
    scope: Optional[str] = Field(
        None, description="Filtrar por escopo (None = todos acessíveis)"
    )
    limit: int = Field(10, ge=1, le=100, description="Número máximo de resultados")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "query": "responsabilidade civil do Estado art. 37 CF",
                "collections": ["lei", "juris"],
                "limit": 10,
            }
        }
    )


class CorpusSearchResult(BaseModel):
    """Resultado individual de busca no Corpus."""

    document_id: Optional[str] = Field(None, description="ID do documento de origem")
    chunk_text: str = Field(..., description="Texto do chunk")
    collection: Optional[str] = Field(None, description="Coleção de origem")
    score: float = Field(..., description="Score de relevância")
    source: str = Field(
        ..., description="Fonte do resultado (lexical, vector, graph)"
    )
    source_url: Optional[str] = Field(
        None,
        description="URL para visualizar o documento original (quando disponível).",
    )
    source_page: Optional[int] = Field(
        None,
        description="Página de origem do trecho (quando disponível).",
    )
    highlight_text: Optional[str] = Field(
        None,
        description="Trecho destacado para navegação no documento de origem.",
    )
    metadata: Optional[Dict[str, Any]] = Field(
        None, description="Metadados adicionais"
    )

    model_config = ConfigDict(from_attributes=True)


class CorpusSearchResponse(BaseModel):
    """Resposta da busca no Corpus."""

    results: List[CorpusSearchResult] = Field(default_factory=list)
    total: int = Field(0, description="Total de resultados encontrados")
    query: str = Field(..., description="Consulta original")


class CorpusDocumentSource(BaseModel):
    """Metadados para abrir o documento original associado ao Corpus."""

    document_id: str = Field(..., description="ID do documento")
    name: str = Field(..., description="Nome amigável do documento")
    original_name: str = Field(..., description="Nome original do arquivo")
    file_type: Optional[str] = Field(None, description="Tipo do arquivo")
    size_bytes: Optional[int] = Field(None, description="Tamanho em bytes")
    available: bool = Field(
        ...,
        description="Indica se o arquivo original está disponível para visualização/download.",
    )
    source_url: Optional[str] = Field(
        None,
        description="URL da fonte original (pode ser local via API ou URL externa).",
    )
    viewer_url: Optional[str] = Field(
        None,
        description="URL recomendada para visualização inline.",
    )
    download_url: Optional[str] = Field(
        None,
        description="URL recomendada para download direto.",
    )
    viewer_kind: Optional[str] = Field(
        None,
        description="Tipo de viewer: pdf_native | office_html | external | unavailable.",
    )
    preview_status: Optional[str] = Field(
        None,
        description="Status do preview: ready | processing | failed | not_supported.",
    )
    page_count: Optional[int] = Field(
        None,
        description="Total de páginas quando disponível.",
    )
    metadata: Optional[Dict[str, Any]] = Field(
        None, description="Metadados do documento úteis para viewer/RAG."
    )


class CorpusDocumentViewerManifest(BaseModel):
    """Manifesto de viewer para abrir evidências com precisão."""

    document_id: str
    viewer_kind: str = Field(
        ...,
        description="Tipo do viewer: pdf_native | office_html | external | unavailable",
    )
    viewer_url: Optional[str] = Field(
        None,
        description="URL principal de visualização.",
    )
    download_url: Optional[str] = Field(
        None,
        description="URL para download direto.",
    )
    source_url: Optional[str] = Field(
        None,
        description="URL de origem do arquivo.",
    )
    page_count: Optional[int] = Field(
        None,
        description="Quantidade de páginas quando disponível.",
    )
    supports_highlight: bool = Field(
        False,
        description="Indica se o viewer suporta highlight por trecho.",
    )
    supports_page_jump: bool = Field(
        False,
        description="Indica se o viewer suporta navegação por página.",
    )
    preview_status: str = Field(
        "not_supported",
        description="Status do preview: ready | processing | failed | not_supported",
    )
    metadata: Optional[Dict[str, Any]] = Field(
        None,
        description="Metadados extras do viewer/documento.",
    )


# =============================================================================
# Collections
# =============================================================================


class CorpusCollectionInfo(BaseModel):
    """Informações sobre uma coleção do Corpus."""

    name: str = Field(..., description="Nome da coleção")
    display_name: str = Field(..., description="Nome de exibição")
    description: str = Field("", description="Descrição da coleção")
    document_count: int = Field(0, description="Quantidade de documentos")
    chunk_count: int = Field(0, description="Quantidade de chunks indexados")
    scope: str = Field("global", description="Escopo padrão")
    vector_count: Optional[int] = Field(None, description="Vetores no Qdrant")
    status: str = Field("active", description="Status da coleção")

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# Retention Policy
# =============================================================================


class CorpusRetentionPolicy(BaseModel):
    """Política de retenção para dados do Corpus."""

    scope: str = Field(..., description="Escopo afetado")
    collection: Optional[str] = Field(
        None, description="Coleção específica (None = todas)"
    )
    retention_days: Optional[int] = Field(
        None, description="Dias de retenção (None = indefinido)"
    )
    auto_delete: bool = Field(False, description="Excluir automaticamente ao expirar")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "scope": "local",
                "collection": None,
                "retention_days": 7,
                "auto_delete": True,
            }
        }
    )


class CorpusRetentionPolicyList(BaseModel):
    """Lista de políticas de retenção."""

    policies: List[CorpusRetentionPolicy] = Field(default_factory=list)


# =============================================================================
# Promote / Extend TTL
# =============================================================================


class CorpusPromoteResponse(BaseModel):
    """Resposta da promoção de documento local para privado."""

    document_id: str
    old_scope: str
    new_scope: str
    success: bool
    message: str


class CorpusExtendTTLRequest(BaseModel):
    """Requisição para estender TTL de documento local."""

    days: int = Field(..., ge=1, le=365, description="Dias adicionais de TTL")


class CorpusExtendTTLResponse(BaseModel):
    """Resposta da extensão de TTL."""

    document_id: str
    new_expires_at: Optional[datetime] = None
    success: bool
    message: str


# =============================================================================
# Admin — Dashboard administrativo do Corpus
# =============================================================================


class CorpusAdminUserStats(BaseModel):
    """Estatísticas de um usuário no Corpus (visão admin)."""

    user_id: str = Field(..., description="ID do usuário")
    user_name: str = Field(..., description="Nome do usuário")
    user_email: str = Field(..., description="E-mail do usuário")
    doc_count: int = Field(0, description="Total de documentos ingeridos")
    storage_bytes: int = Field(0, description="Armazenamento total em bytes")
    last_activity: Optional[datetime] = Field(None, description="Última atividade no Corpus")
    collections_used: List[str] = Field(default_factory=list, description="Coleções utilizadas")

    model_config = ConfigDict(from_attributes=True)


class CorpusAdminUserList(BaseModel):
    """Lista paginada de usuários com stats do Corpus."""

    items: List[CorpusAdminUserStats] = Field(default_factory=list)
    total: int = Field(0, description="Total de usuários")
    skip: int = Field(0)
    limit: int = Field(20)


class CorpusAdminOverview(BaseModel):
    """Visão geral administrativa do Corpus para toda a organização."""

    total_documents: int = Field(0, description="Total de documentos em toda a org")
    total_storage_bytes: int = Field(0, description="Armazenamento total em bytes")
    active_users: int = Field(0, description="Usuários com pelo menos 1 doc no Corpus")
    pending_ingestion: int = Field(0, description="Documentos pendentes de ingestão")
    processing_ingestion: int = Field(0, description="Documentos em processamento")
    failed_ingestion: int = Field(0, description="Documentos com falha na ingestão")
    by_collection: Dict[str, int] = Field(default_factory=dict, description="Docs por coleção")
    by_scope: Dict[str, int] = Field(default_factory=dict, description="Docs por escopo")
    top_contributors: List[CorpusAdminUserStats] = Field(
        default_factory=list, description="Top 5 contribuidores"
    )
    recent_activity: List[Dict[str, Any]] = Field(
        default_factory=list, description="Últimas 50 operações"
    )

    model_config = ConfigDict(from_attributes=True)


class CorpusAdminActivity(BaseModel):
    """Entrada do log de atividade do Corpus."""

    document_id: str = Field(..., description="ID do documento")
    document_name: str = Field("", description="Nome do documento")
    user_id: str = Field(..., description="ID do usuário")
    user_name: str = Field("", description="Nome do usuário")
    action: str = Field(..., description="Ação realizada (ingest, delete, promote, extend_ttl)")
    timestamp: Optional[datetime] = Field(None, description="Data/hora da ação")
    details: Optional[Dict[str, Any]] = Field(None, description="Detalhes adicionais")

    model_config = ConfigDict(from_attributes=True)


class CorpusAdminActivityList(BaseModel):
    """Lista paginada de atividades do Corpus."""

    items: List[CorpusAdminActivity] = Field(default_factory=list)
    total: int = Field(0)
    skip: int = Field(0)
    limit: int = Field(50)


class CorpusViewerBackfillRequest(BaseModel):
    """Requisição para enfileirar backfill de previews de viewer."""

    limit: int = Field(200, ge=1, le=5000, description="Máximo de documentos avaliados")
    dry_run: bool = Field(False, description="Somente simular sem enfileirar tasks")


class CorpusViewerBackfillResponse(BaseModel):
    """Resposta do backfill de previews de viewer."""

    total_candidates: int = Field(0)
    queued: int = Field(0)
    skipped: int = Field(0)
    errors: List[Dict[str, str]] = Field(default_factory=list)


class CorpusTransferRequest(BaseModel):
    """Requisição para transferir propriedade de documento."""

    new_owner_id: str = Field(..., description="ID do novo proprietário")


class CorpusTransferResponse(BaseModel):
    """Resposta da transferência de propriedade."""

    document_id: str
    old_owner_id: str
    new_owner_id: str
    success: bool
    message: str


# =============================================================================
# Verbatim — Extração literal com proveniência
# =============================================================================


class VerbatimExcerpt(BaseModel):
    """Trecho literal extraído do corpus com proveniência."""

    text: str = Field(..., description="Texto literal do chunk")
    page_number: Optional[int] = Field(None, description="Número da página no documento")
    line_start: Optional[int] = Field(None, description="Linha inicial")
    line_end: Optional[int] = Field(None, description="Linha final")
    source_file: Optional[str] = Field(None, description="Arquivo de origem")
    doc_id: Optional[str] = Field(None, description="ID do documento de origem")
    score: float = Field(0.0, description="Score de relevância")
    collection: Optional[str] = Field(None, description="Coleção de origem")
    chunk_index: Optional[int] = Field(None, description="Índice do chunk")

    model_config = ConfigDict(from_attributes=True)


class VerbatimRequest(BaseModel):
    """Requisição de extração verbatim."""

    document_id: Optional[str] = Field(None, description="ID do documento (filtrar por doc)")
    query: str = Field(
        ..., min_length=1, max_length=5000,
        description="Consulta para buscar trechos relevantes",
    )
    limit: int = Field(5, ge=1, le=50, description="Número máximo de trechos")
    collections: Optional[List[str]] = Field(
        None, description="Filtrar por coleções",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "document_id": "doc-123",
                "query": "responsabilidade civil do Estado",
                "limit": 5,
            }
        }
    )


class VerbatimResponse(BaseModel):
    """Resposta da extração verbatim."""

    excerpts: List[VerbatimExcerpt] = Field(default_factory=list)
    total: int = Field(0, description="Total de trechos encontrados")
    query: str = Field(..., description="Consulta original")
