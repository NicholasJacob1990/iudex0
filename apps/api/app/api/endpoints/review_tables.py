"""
Review Tables — Extracao estruturada de dados de documentos em tabelas.

Templates:
GET    /review-tables/templates              — Listar templates disponiveis
GET    /review-tables/templates/system       — Listar templates pre-construidos
POST   /review-tables/templates              — Criar template customizado
GET    /review-tables/templates/{id}         — Obter template com colunas
POST   /review-tables/templates/seed         — Seed de templates pre-construidos

Review Tables:
POST   /review-tables/from-template          — Criar review a partir de template (one-click)
POST   /review-tables                        — Criar review (template + documentos)
GET    /review-tables                        — Listar reviews do usuario
GET    /review-tables/{id}                   — Obter review com resultados
POST   /review-tables/{id}/process           — Processar review (extrair dados)
POST   /review-tables/{id}/fill              — Preencher tabela via IA

Export:
GET    /review-tables/{id}/export            — Exportar como CSV/XLSX
POST   /review-tables/{id}/export/xlsx       — Exportar para Excel
POST   /review-tables/{id}/export/csv        — Exportar para CSV

Column Builder (generate columns from template description):
POST   /review-tables/{id}/columns/generate  — Column Builder (IA gera colunas)

Dynamic Columns (Harvey AI-style - create columns via natural language prompts):
POST   /review-tables/{id}/dynamic-columns              — Criar coluna via prompt
GET    /review-tables/{id}/dynamic-columns              — Listar colunas dinamicas
GET    /review-tables/{id}/dynamic-columns/{col_id}     — Obter coluna com extracoes
DELETE /review-tables/{id}/dynamic-columns/{col_id}     — Deletar coluna
POST   /review-tables/{id}/dynamic-columns/{col_id}/reprocess — Reprocessar extracoes

Cell Verification:
PATCH  /review-tables/{id}/cells/{cell_id}/verify       — Verificar/corrigir celula

Ask Table (Chat):
POST   /review-tables/{id}/chat              — Fazer pergunta sobre os dados
GET    /review-tables/{id}/chat/history      — Historico de perguntas
DELETE /review-tables/{id}/chat/history      — Limpar historico
GET    /review-tables/{id}/chat/statistics   — Estatisticas da tabela
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.time_utils import utcnow
from app.models.review_table import ReviewTable, ReviewTableTemplate
from app.models.dynamic_column import DynamicColumn, CellExtraction, ExtractionType, VerificationStatus
from app.models.table_chat import TableChatMessage, MessageRole
from app.models.user import User
from app.services.review_table_service import review_table_service
from app.services.column_builder_service import column_builder_service
from app.services.table_chat_service import table_chat_service
from app.services.cell_verification_service import cell_verification_service

logger = logging.getLogger("ReviewTableEndpoints")

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas (inline — seguindo padrao de endpoints simples)
# ---------------------------------------------------------------------------


class ColumnDefSchema(BaseModel):
    name: str
    type: str = "text"  # text, date, currency, number, verbatim, boolean, summary, date_extraction, yes_no_classification, verbatim_extraction, risk_rating, compliance_check, custom
    extraction_prompt: str


class TemplateCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None
    area: Optional[str] = None
    columns: List[ColumnDefSchema]


class TemplateResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    area: Optional[str] = None
    columns: List[Dict[str, Any]]
    is_system: bool
    created_by: Optional[str] = None
    organization_id: Optional[str] = None
    is_active: bool
    created_at: str
    updated_at: str


class TemplateListResponse(BaseModel):
    items: List[TemplateResponse]
    total: int


class CellEditRequest(BaseModel):
    document_id: str
    column_name: str
    new_value: str
    verified: bool = False


class CellEditResponse(BaseModel):
    success: bool
    document_id: str
    column_name: str
    new_value: str
    verified: bool
    edited_by: str
    edited_at: str


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=2000)


class QuerySourceRef(BaseModel):
    document_id: str
    document_name: str
    column_name: Optional[str] = None


class QueryResponse(BaseModel):
    answer: str
    sources: List[QuerySourceRef]


class ReviewFromTemplateRequest(BaseModel):
    """Criar review diretamente a partir de um template do sistema."""
    template_id: str
    document_ids: List[str]
    name: Optional[str] = None


class ReviewCreateRequest(BaseModel):
    template_id: str
    document_ids: List[str]
    name: str


class ReviewResponse(BaseModel):
    id: str
    template_id: str
    template_name: Optional[str] = None
    name: str
    user_id: str
    organization_id: Optional[str] = None
    status: str
    document_ids: List[str]
    results: List[Dict[str, Any]]
    total_documents: int
    processed_documents: int
    accuracy_score: Optional[float] = None
    error_message: Optional[str] = None
    cell_history: List[Dict[str, Any]] = Field(default_factory=list)
    created_at: str
    updated_at: str


class ReviewListResponse(BaseModel):
    items: List[ReviewResponse]
    total: int


# ---------------------------------------------------------------------------
# Column Builder Schemas
# ---------------------------------------------------------------------------


class ColumnGenerateRequest(BaseModel):
    """Gerar colunas via IA a partir de descricao em linguagem natural."""
    description: str = Field(
        ...,
        min_length=10,
        max_length=5000,
        description="Descricao do que deseja analisar nos documentos",
    )
    area: Optional[str] = Field(
        None,
        description="Area juridica: trabalhista, civil, societario, imobiliario, ti, empresarial, tributario, ambiental, regulatorio",
    )


class GeneratedColumnDef(BaseModel):
    name: str
    type: str
    extraction_prompt: str


class ColumnGenerateResponse(BaseModel):
    columns: List[GeneratedColumnDef]
    suggested_name: str
    suggested_area: str


# ---------------------------------------------------------------------------
# Fill Table Schemas
# ---------------------------------------------------------------------------


class FillTableRequest(BaseModel):
    """Preencher review table automaticamente via IA."""
    document_ids: Optional[List[str]] = Field(
        None,
        description="IDs dos documentos para processar. Se nao fornecido, processa todos.",
    )


class FillTableResponse(BaseModel):
    success: bool
    review_id: str
    status: str
    message: str


# ---------------------------------------------------------------------------
# Cell Verification Schemas
# ---------------------------------------------------------------------------


class VerifyCellRequest(BaseModel):
    """Request para verificar/rejeitar/corrigir uma celula."""
    verified: bool = Field(..., description="True para verificar, False para rejeitar")
    correction: Optional[str] = Field(None, description="Valor corrigido (se houver)")
    note: Optional[str] = Field(None, description="Nota explicativa")


class BulkVerifyRequest(BaseModel):
    """Request para verificar multiplas celulas."""
    cell_ids: List[str] = Field(..., min_length=1, max_length=100)
    verified: bool


class BulkVerifyResponse(BaseModel):
    success: bool
    updated_count: int


class CellExtractionResponse(BaseModel):
    id: str
    document_id: str
    column_id: Optional[str] = None  # dynamic_column_id
    column_name: Optional[str] = None
    value: str
    display_value: str
    confidence: float
    verification_status: str
    is_verified: bool
    source_snippet: Optional[str] = None
    source_page: Optional[int] = None
    verified_by: Optional[str] = None
    verified_at: Optional[str] = None
    corrected_value: Optional[str] = None
    correction_note: Optional[str] = None


class VerificationStatsResponse(BaseModel):
    total_cells: int
    verified: int
    rejected: int
    corrected: int
    pending: int
    average_confidence: float
    low_confidence_count: int


class CellSourceResponse(BaseModel):
    """Resposta com informacoes detalhadas da fonte de uma celula."""
    cell_id: str
    document_id: str
    document_name: str
    column_name: str
    extracted_value: str
    source_snippet: Optional[str] = None
    source_page: Optional[int] = None
    source_char_start: Optional[int] = None
    source_char_end: Optional[int] = None
    confidence: float
    extraction_reasoning: Optional[str] = None


# ---------------------------------------------------------------------------
# Ask Table (Chat) Schemas
# ---------------------------------------------------------------------------


class AskTableRequest(BaseModel):
    """Pergunta em linguagem natural sobre os dados da tabela."""
    question: str = Field(
        ...,
        min_length=3,
        max_length=2000,
        description="Pergunta em linguagem natural sobre os dados extraidos",
    )
    include_history: bool = Field(
        True,
        description="Se deve incluir historico da conversa no contexto",
    )


class DocumentReference(BaseModel):
    """Referencia a um documento citado na resposta."""
    id: str
    name: str
    relevance: Optional[str] = None


class AskTableResponse(BaseModel):
    """Resposta da consulta Ask Table."""
    answer: str = Field(..., description="Resposta em linguagem natural")
    query_type: str = Field(..., description="Tipo de query: filter, aggregation, comparison, summary, specific, general")
    documents: List[DocumentReference] = Field(default_factory=list, description="Documentos citados na resposta")
    data: Optional[dict] = Field(None, description="Dados estruturados (agregacoes, listas, etc.)")
    visualization_hint: Optional[str] = Field(None, description="Sugestao de visualizacao: bar_chart, pie_chart, table, list")
    message_id: str = Field(..., description="ID da mensagem salva no historico")


class ChatMessageResponse(BaseModel):
    """Mensagem do historico de chat."""
    id: str
    role: str
    content: str
    query_type: Optional[str] = None
    query_result: Optional[dict] = None
    documents_referenced: List[str] = Field(default_factory=list)
    visualization_hint: Optional[str] = None
    created_at: str


class ChatHistoryResponse(BaseModel):
    """Historico de chat de uma review table."""
    messages: List[ChatMessageResponse]
    total: int


class TableStatisticsResponse(BaseModel):
    """Estatisticas da tabela."""
    total_documents: int
    columns: int
    column_stats: Dict[str, Any]


# ---------------------------------------------------------------------------
# Dynamic Column Schemas
# ---------------------------------------------------------------------------


class CreateDynamicColumnRequest(BaseModel):
    """Criar coluna dinamica via prompt em linguagem natural."""
    prompt: str = Field(
        ...,
        min_length=5,
        max_length=2000,
        description="Pergunta em linguagem natural que define a extracao",
    )
    name: Optional[str] = Field(
        None,
        max_length=255,
        description="Nome da coluna (opcional, sera inferido do prompt)",
    )
    extraction_type: Optional[str] = Field(
        None,
        description="Tipo de extracao: text, boolean, number, date, currency, enum, list, verbatim, risk_rating, compliance_check",
    )
    enum_options: Optional[List[str]] = Field(
        None,
        description="Opcoes para tipo enum",
    )
    extraction_instructions: Optional[str] = Field(
        None,
        max_length=2000,
        description="Instrucoes adicionais para extracao",
    )


class DynamicColumnResponse(BaseModel):
    """Resposta de coluna dinamica."""
    id: str
    review_table_id: str
    name: str
    prompt: str
    extraction_type: str
    enum_options: Optional[List[str]] = None
    extraction_instructions: Optional[str] = None
    order: int
    is_active: bool
    created_by: Optional[str] = None
    created_at: str
    updated_at: str
    extraction_count: int = 0
    pending_count: int = 0
    verified_count: int = 0


class DynamicColumnListResponse(BaseModel):
    """Lista de colunas dinamicas."""
    items: List[DynamicColumnResponse]
    total: int


class CellExtractionResponse(BaseModel):
    """Resposta de extracao de celula."""
    id: str
    dynamic_column_id: str
    document_id: str
    document_name: Optional[str] = None
    extracted_value: str
    display_value: str
    confidence: float
    source_snippet: Optional[str] = None
    source_page: Optional[int] = None
    verification_status: str
    verified_by: Optional[str] = None
    verified_at: Optional[str] = None
    verification_note: Optional[str] = None
    corrected_value: Optional[str] = None
    extracted_at: str


class VerifyCellRequest(BaseModel):
    """Verificar ou corrigir uma celula extraida."""
    status: str = Field(
        ...,
        description="Status: verified, rejected, corrected",
    )
    corrected_value: Optional[str] = Field(
        None,
        description="Valor corrigido (obrigatorio se status=corrected)",
    )
    note: Optional[str] = Field(
        None,
        max_length=1000,
        description="Nota do revisor",
    )


class ReprocessColumnRequest(BaseModel):
    """Reprocessar extracoes de uma coluna."""
    document_ids: Optional[List[str]] = Field(
        None,
        description="IDs de documentos especificos para reprocessar. Se nulo, reprocessa todos.",
    )


class ColumnExtractionsResponse(BaseModel):
    """Lista de extracoes de uma coluna."""
    column: DynamicColumnResponse
    extractions: List[CellExtractionResponse]
    total: int
    stats: Dict[str, Any]


# ---------------------------------------------------------------------------
# Templates CRUD
# ---------------------------------------------------------------------------


@router.get("/templates", response_model=TemplateListResponse)
async def list_templates(
    area: Optional[str] = None,
    search: Optional[str] = None,
    is_system: Optional[bool] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Listar templates de review table disponiveis."""
    user_id = str(current_user.id)
    org_id = getattr(current_user, "organization_id", None)

    # System templates + user's own + org's
    conditions = [ReviewTableTemplate.is_system == True]  # noqa: E712
    conditions.append(ReviewTableTemplate.created_by == user_id)
    if org_id:
        conditions.append(ReviewTableTemplate.organization_id == org_id)

    stmt = select(ReviewTableTemplate).where(
        ReviewTableTemplate.is_active == True,  # noqa: E712
        or_(*conditions),
    )

    if area:
        stmt = stmt.where(ReviewTableTemplate.area == area)
    if is_system is not None:
        stmt = stmt.where(ReviewTableTemplate.is_system == is_system)
    if search:
        stmt = stmt.where(
            ReviewTableTemplate.name.ilike(f"%{search}%")
            | ReviewTableTemplate.description.ilike(f"%{search}%")
        )

    stmt = stmt.order_by(ReviewTableTemplate.is_system.desc(), ReviewTableTemplate.name)

    result = await db.execute(stmt)
    templates = result.scalars().all()

    items = [_template_to_response(t) for t in templates]
    return TemplateListResponse(items=items, total=len(items))


@router.get("/templates/system", response_model=TemplateListResponse)
async def list_system_templates(
    area: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Listar templates pre-construidos do sistema (is_system=True).

    Endpoint publico para o frontend exibir workflows pre-construidos.
    Nao requer autenticacao para facilitar a descoberta de templates.
    """
    stmt = select(ReviewTableTemplate).where(
        ReviewTableTemplate.is_system == True,  # noqa: E712
        ReviewTableTemplate.is_active == True,  # noqa: E712
    )

    if area:
        stmt = stmt.where(ReviewTableTemplate.area == area)

    stmt = stmt.order_by(ReviewTableTemplate.name)

    result = await db.execute(stmt)
    templates = result.scalars().all()

    items = [_template_to_response(t) for t in templates]
    return TemplateListResponse(items=items, total=len(items))


@router.get("/templates/{template_id}", response_model=TemplateResponse)
async def get_template(
    template_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Obter template com detalhes das colunas."""
    template = await db.get(ReviewTableTemplate, template_id)
    if not template or not template.is_active:
        raise HTTPException(status_code=404, detail="Template nao encontrado")
    return _template_to_response(template)


@router.post("/templates", response_model=TemplateResponse, status_code=201)
async def create_template(
    request: TemplateCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Criar template customizado de review table."""
    if not request.columns:
        raise HTTPException(
            status_code=400,
            detail="O template deve ter ao menos uma coluna."
        )

    if len(request.columns) > 30:
        raise HTTPException(
            status_code=400,
            detail="Maximo de 30 colunas por template."
        )

    template = ReviewTableTemplate(
        id=str(uuid.uuid4()),
        name=request.name,
        description=request.description,
        area=request.area,
        columns=[col.model_dump() for col in request.columns],
        is_system=False,
        created_by=str(current_user.id),
        organization_id=getattr(current_user, "organization_id", None),
        is_active=True,
    )
    db.add(template)
    await db.commit()
    await db.refresh(template)

    return _template_to_response(template)


@router.post("/templates/seed")
async def seed_templates(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Carregar templates pre-construidos do sistema (idempotente)."""
    try:
        created = await review_table_service.seed_system_templates(db)
        return {
            "success": True,
            "message": f"{created} templates criados.",
        }
    except Exception as e:
        logger.error("Erro ao fazer seed de templates: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Erro interno ao carregar templates."
        )


# ---------------------------------------------------------------------------
# Column Builder — Gerar colunas via IA
# ---------------------------------------------------------------------------


@router.post(
    "/columns/generate",
    response_model=ColumnGenerateResponse,
    status_code=200,
)
async def generate_columns_standalone(
    request: ColumnGenerateRequest,
    current_user: User = Depends(get_current_user),
):
    """Column Builder: gera definicoes de colunas a partir de descricao em linguagem natural.

    Endpoint standalone que nao requer uma review table existente.
    Util para o fluxo de criacao de novos templates via IA.

    Exemplo de uso:
      POST /review-tables/columns/generate
      {"description": "Quero analisar contratos de compra e venda de imoveis para due diligence"}

    Retorna colunas sugeridas com tipos e prompts de extracao.
    """
    try:
        result = await review_table_service.generate_columns(
            description=request.description,
            area=request.area,
        )
        return ColumnGenerateResponse(
            columns=[
                GeneratedColumnDef(**col)
                for col in result["columns"]
            ],
            suggested_name=result["suggested_name"],
            suggested_area=result["suggested_area"],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        logger.error("Erro no Column Builder: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Erro interno ao gerar colunas."
        )


@router.post(
    "/{review_id}/columns/generate",
    response_model=ColumnGenerateResponse,
    status_code=200,
)
async def generate_columns_for_review(
    review_id: str,
    request: ColumnGenerateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Column Builder para uma review table existente.

    Gera sugestoes de colunas baseadas na descricao do usuario.
    As colunas sugeridas podem ser usadas para criar um novo template
    ou atualizar o template existente da review table.
    """
    review = await db.get(ReviewTable, review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review table nao encontrada")

    user_id = str(current_user.id)
    org_id = getattr(current_user, "organization_id", None)
    if review.user_id != user_id and review.organization_id != org_id:
        raise HTTPException(status_code=403, detail="Sem permissao")

    try:
        result = await review_table_service.generate_columns(
            description=request.description,
            area=request.area,
        )
        return ColumnGenerateResponse(
            columns=[
                GeneratedColumnDef(**col)
                for col in result["columns"]
            ],
            suggested_name=result["suggested_name"],
            suggested_area=result["suggested_area"],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        logger.error("Erro no Column Builder para review %s: %s", review_id, e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Erro interno ao gerar colunas."
        )


# ---------------------------------------------------------------------------
# Review Tables CRUD
# ---------------------------------------------------------------------------


@router.post("/from-template", response_model=ReviewResponse, status_code=201)
async def create_review_from_template(
    request: ReviewFromTemplateRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Criar review table a partir de um template do sistema + document_ids.

    Gera automaticamente um nome baseado no template se nao fornecido.
    Ideal para o workflow de one-click extraction.
    """
    # Validar template
    template = await db.get(ReviewTableTemplate, request.template_id)
    if not template or not template.is_active:
        raise HTTPException(status_code=404, detail="Template nao encontrado")

    if not request.document_ids:
        raise HTTPException(status_code=400, detail="Selecione ao menos um documento.")

    # Gerar nome automatico se nao fornecido
    review_name = request.name
    if not review_name:
        from datetime import datetime
        now = datetime.now()
        review_name = f"{template.name} — {now.strftime('%d/%m/%Y %H:%M')}"

    try:
        review = await review_table_service.create_review(
            template_id=request.template_id,
            document_ids=request.document_ids,
            user_id=str(current_user.id),
            org_id=getattr(current_user, "organization_id", None),
            name=review_name,
            db=db,
        )

        # Processar em background
        background_tasks.add_task(
            _process_review_background,
            review_id=review.id,
        )

        return _review_to_response(review, template_name=template.name)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Erro ao criar review from template: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno ao criar review table.")


@router.post("", response_model=ReviewResponse, status_code=201)
async def create_review(
    request: ReviewCreateRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Criar review table e iniciar processamento em background."""
    try:
        review = await review_table_service.create_review(
            template_id=request.template_id,
            document_ids=request.document_ids,
            user_id=str(current_user.id),
            org_id=getattr(current_user, "organization_id", None),
            name=request.name,
            db=db,
        )

        # Processar em background
        background_tasks.add_task(
            _process_review_background,
            review_id=review.id,
        )

        template = await db.get(ReviewTableTemplate, review.template_id)
        return _review_to_response(review, template_name=template.name if template else None)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Erro ao criar review table: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno ao criar review table.")


@router.get("", response_model=ReviewListResponse)
async def list_reviews(
    skip: int = 0,
    limit: int = 50,
    status_filter: Optional[str] = Query(None, alias="status"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Listar review tables do usuario."""
    user_id = str(current_user.id)

    stmt = select(ReviewTable).where(ReviewTable.user_id == user_id)

    if status_filter:
        stmt = stmt.where(ReviewTable.status == status_filter)

    # Count
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = stmt.order_by(ReviewTable.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    reviews = result.scalars().all()

    # Load template names
    items = []
    for r in reviews:
        template = await db.get(ReviewTableTemplate, r.template_id)
        items.append(_review_to_response(r, template_name=template.name if template else None))

    return ReviewListResponse(items=items, total=total)


@router.get("/{review_id}", response_model=ReviewResponse)
async def get_review(
    review_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Obter review table com resultados."""
    review = await db.get(ReviewTable, review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review table nao encontrada")

    # Verificar acesso
    user_id = str(current_user.id)
    org_id = getattr(current_user, "organization_id", None)
    if review.user_id != user_id and review.organization_id != org_id:
        raise HTTPException(status_code=403, detail="Sem permissao")

    template = await db.get(ReviewTableTemplate, review.template_id)
    return _review_to_response(review, template_name=template.name if template else None)


@router.post("/{review_id}/process")
async def process_review(
    review_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Reprocessar review table (para re-execucao manual)."""
    review = await db.get(ReviewTable, review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review table nao encontrada")

    if review.user_id != str(current_user.id):
        raise HTTPException(status_code=403, detail="Sem permissao")

    if review.status == "processing":
        raise HTTPException(status_code=409, detail="Review table ja esta sendo processada")

    # Reset para reprocessar
    review.status = "created"
    review.results = []
    review.processed_documents = 0
    review.accuracy_score = None
    review.error_message = None
    review.updated_at = utcnow()
    await db.commit()

    background_tasks.add_task(
        _process_review_background,
        review_id=review.id,
    )

    return {"success": True, "message": "Processamento reiniciado."}


# ---------------------------------------------------------------------------
# Fill Table — Preenchimento automatico via IA
# ---------------------------------------------------------------------------


@router.post("/{review_id}/fill", response_model=FillTableResponse)
async def fill_review_table(
    review_id: str,
    request: FillTableRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Preencher review table automaticamente via IA.

    Processa documentos e preenche todas as colunas do template.
    Pode ser usado incrementalmente para adicionar novos documentos.

    Se document_ids nao for fornecido, reprocessa todos os documentos
    da review table.
    """
    review = await db.get(ReviewTable, review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review table nao encontrada")

    user_id = str(current_user.id)
    org_id = getattr(current_user, "organization_id", None)
    if review.user_id != user_id and review.organization_id != org_id:
        raise HTTPException(status_code=403, detail="Sem permissao")

    if review.status == "processing":
        raise HTTPException(
            status_code=409,
            detail="Review table ja esta sendo processada. Aguarde a conclusao."
        )

    # Processar em background
    background_tasks.add_task(
        _fill_table_background,
        table_id=review.id,
        document_ids=request.document_ids,
    )

    doc_count = len(request.document_ids) if request.document_ids else len(review.document_ids or [])

    return FillTableResponse(
        success=True,
        review_id=review.id,
        status="processing",
        message=f"Preenchimento iniciado para {doc_count} documento(s). Acompanhe o status via GET /review-tables/{review.id}",
    )


# ---------------------------------------------------------------------------
# Export endpoints dedicados
# ---------------------------------------------------------------------------


@router.get("/{review_id}/export")
async def export_review(
    review_id: str,
    format: str = Query("csv", pattern="^(csv|xlsx)$"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Exportar review table como CSV ou XLSX (via query param)."""
    return await _do_export(review_id, format, current_user, db)


@router.post("/{review_id}/export/xlsx")
async def export_review_xlsx(
    review_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Exportar review table como Excel (.xlsx).

    Gera arquivo Excel com:
    - Aba de dados com color coding por tipo de coluna e conteudo
    - Aba de resumo com estatisticas
    - Aba de metadados com definicoes das colunas
    - Headers com cores diferenciadas por tipo (risco, conformidade, etc.)
    - Freeze panes e auto-width
    """
    return await _do_export(review_id, "xlsx", current_user, db)


@router.post("/{review_id}/export/csv")
async def export_review_csv(
    review_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Exportar review table como CSV.

    Gera arquivo CSV UTF-8 com BOM para compatibilidade com Excel.
    """
    return await _do_export(review_id, "csv", current_user, db)


async def _do_export(
    review_id: str,
    format: str,
    current_user: User,
    db: AsyncSession,
) -> Response:
    """Logica compartilhada de exportacao."""
    review = await db.get(ReviewTable, review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review table nao encontrada")

    user_id = str(current_user.id)
    org_id = getattr(current_user, "organization_id", None)
    if review.user_id != user_id and review.organization_id != org_id:
        raise HTTPException(status_code=403, detail="Sem permissao")

    if review.status != "completed":
        raise HTTPException(
            status_code=400,
            detail="A review table precisa estar completa para exportacao."
        )

    try:
        content, filename, content_type = await review_table_service.export_review(
            review_id=review_id,
            format=format,
            db=db,
        )

        return Response(
            content=content,
            media_type=content_type,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Erro na exportacao: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno na exportacao.")


# ---------------------------------------------------------------------------
# Inline Cell Editing
# ---------------------------------------------------------------------------


@router.patch("/{review_id}/cell", response_model=CellEditResponse)
async def edit_cell(
    review_id: str,
    request: CellEditRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Editar uma celula especifica da review table."""
    review = await db.get(ReviewTable, review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review table nao encontrada")

    user_id = str(current_user.id)
    org_id = getattr(current_user, "organization_id", None)
    if review.user_id != user_id and review.organization_id != org_id:
        raise HTTPException(status_code=403, detail="Sem permissao")

    # Encontrar a linha do documento nos resultados
    results = list(review.results or [])
    row_idx = None
    for idx, row in enumerate(results):
        if row.get("document_id") == request.document_id:
            row_idx = idx
            break

    if row_idx is None:
        raise HTTPException(
            status_code=404,
            detail=f"Documento {request.document_id} nao encontrado nos resultados"
        )

    # Atualizar valor da celula
    row = results[row_idx]
    columns = row.get("columns", {})
    old_value = columns.get(request.column_name, "")
    columns[request.column_name] = request.new_value

    # Rastrear edicoes manuais em metadata por celula
    edits = row.get("_edits", {})
    now = utcnow()
    edits[request.column_name] = {
        "edited_by": user_id,
        "edited_at": now.isoformat(),
        "verified": request.verified,
    }
    row["columns"] = columns
    row["_edits"] = edits
    results[row_idx] = row

    # Append to cell_history for change tracking
    history = list(review.cell_history or [])
    history.append({
        "document_id": request.document_id,
        "column_name": request.column_name,
        "old_value": str(old_value) if old_value else "",
        "new_value": request.new_value,
        "changed_by": user_id,
        "changed_at": now.isoformat(),
    })

    # Salvar — SQLAlchemy precisa de reatribuicao para detectar mudanca em JSON
    review.results = results
    review.cell_history = history
    review.updated_at = now
    await db.commit()
    await db.refresh(review)

    return CellEditResponse(
        success=True,
        document_id=request.document_id,
        column_name=request.column_name,
        new_value=request.new_value,
        verified=request.verified,
        edited_by=user_id,
        edited_at=now.isoformat(),
    )


# ---------------------------------------------------------------------------
# Cell History
# ---------------------------------------------------------------------------


class CellHistoryEntry(BaseModel):
    document_id: str
    column_name: str
    old_value: str
    new_value: str
    changed_by: str
    changed_at: str


class CellHistoryResponse(BaseModel):
    entries: List[CellHistoryEntry]
    total: int


@router.get("/{review_id}/cell-history", response_model=CellHistoryResponse)
async def get_cell_history(
    review_id: str,
    document_id: Optional[str] = Query(None, description="Filtrar por documento"),
    column_name: Optional[str] = Query(None, description="Filtrar por coluna"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Obter historico de edicoes de celulas de uma review table."""
    review = await db.get(ReviewTable, review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review table nao encontrada")

    user_id = str(current_user.id)
    org_id = getattr(current_user, "organization_id", None)
    if review.user_id != user_id and review.organization_id != org_id:
        raise HTTPException(status_code=403, detail="Sem permissao")

    history = review.cell_history or []

    # Apply filters
    if document_id:
        history = [h for h in history if h.get("document_id") == document_id]
    if column_name:
        history = [h for h in history if h.get("column_name") == column_name]

    # Sort by changed_at descending
    history.sort(key=lambda h: h.get("changed_at", ""), reverse=True)

    entries = [
        CellHistoryEntry(
            document_id=h.get("document_id", ""),
            column_name=h.get("column_name", ""),
            old_value=h.get("old_value", ""),
            new_value=h.get("new_value", ""),
            changed_by=h.get("changed_by", ""),
            changed_at=h.get("changed_at", ""),
        )
        for h in history
    ]

    return CellHistoryResponse(entries=entries, total=len(entries))


# ---------------------------------------------------------------------------
# Cell Verification Endpoints
# ---------------------------------------------------------------------------


@router.patch("/{table_id}/cells/{cell_id}/verify", response_model=CellExtractionResponse)
async def verify_cell(
    table_id: str,
    cell_id: str,
    request: VerifyCellRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Verificar, rejeitar ou corrigir uma celula especifica.

    - verified=True: Marca como verificada (correta)
    - verified=False: Marca como rejeitada (incorreta)
    - correction: Se fornecido, marca como corrigida com o novo valor
    """
    # Verificar acesso a review table
    review = await db.get(ReviewTable, table_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review table nao encontrada")

    user_id = str(current_user.id)
    org_id = getattr(current_user, "organization_id", None)
    if review.user_id != user_id and review.organization_id != org_id:
        raise HTTPException(status_code=403, detail="Sem permissao")

    try:
        cell = await cell_verification_service.verify_cell(
            cell_id=cell_id,
            user_id=user_id,
            verified=request.verified,
            correction=request.correction,
            note=request.note,
            db=db,
        )

        return _cell_to_response(cell)

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Erro ao verificar celula %s: %s", cell_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao verificar celula")


@router.post("/{table_id}/cells/bulk-verify", response_model=BulkVerifyResponse)
async def bulk_verify_cells(
    table_id: str,
    request: BulkVerifyRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Verificar ou rejeitar multiplas celulas de uma vez."""
    # Verificar acesso
    review = await db.get(ReviewTable, table_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review table nao encontrada")

    user_id = str(current_user.id)
    org_id = getattr(current_user, "organization_id", None)
    if review.user_id != user_id and review.organization_id != org_id:
        raise HTTPException(status_code=403, detail="Sem permissao")

    try:
        count = await cell_verification_service.bulk_verify(
            cell_ids=request.cell_ids,
            user_id=user_id,
            verified=request.verified,
            db=db,
        )

        return BulkVerifyResponse(success=True, updated_count=count)

    except Exception as e:
        logger.error("Erro no bulk verify: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao verificar celulas")


@router.get("/{table_id}/verification-stats", response_model=VerificationStatsResponse)
async def get_verification_stats(
    table_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Obter estatisticas de verificacao de uma review table.

    Retorna totais de celulas verificadas, rejeitadas, corrigidas, pendentes,
    media de confianca e quantidade de celulas de baixa confianca.
    """
    review = await db.get(ReviewTable, table_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review table nao encontrada")

    user_id = str(current_user.id)
    org_id = getattr(current_user, "organization_id", None)
    if review.user_id != user_id and review.organization_id != org_id:
        raise HTTPException(status_code=403, detail="Sem permissao")

    try:
        stats = await cell_verification_service.get_verification_stats(
            review_table_id=table_id,
            db=db,
        )

        return VerificationStatsResponse(**stats.to_dict())

    except Exception as e:
        logger.error("Erro ao obter stats de verificacao: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao obter estatisticas")


@router.get("/{table_id}/cells/low-confidence", response_model=List[CellExtractionResponse])
async def get_low_confidence_cells(
    table_id: str,
    threshold: float = Query(0.7, ge=0.0, le=1.0, description="Limite de confianca"),
    limit: int = Query(50, ge=1, le=200, description="Maximo de celulas"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Listar celulas com confianca abaixo do threshold para revisao.

    Util para identificar rapidamente quais celulas precisam de atencao humana.
    """
    review = await db.get(ReviewTable, table_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review table nao encontrada")

    user_id = str(current_user.id)
    org_id = getattr(current_user, "organization_id", None)
    if review.user_id != user_id and review.organization_id != org_id:
        raise HTTPException(status_code=403, detail="Sem permissao")

    try:
        cells = await cell_verification_service.get_low_confidence_cells(
            review_table_id=table_id,
            threshold=threshold,
            limit=limit,
            db=db,
        )

        return [_cell_to_response(cell) for cell in cells]

    except Exception as e:
        logger.error("Erro ao obter celulas de baixa confianca: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao buscar celulas")


@router.get("/{table_id}/cells/{cell_id}/source", response_model=CellSourceResponse)
async def get_cell_source(
    table_id: str,
    cell_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Obter informacoes detalhadas da fonte de uma celula.

    Retorna o trecho do documento de onde a informacao foi extraida,
    posicao no texto, pagina e raciocinio do modelo.
    """
    from app.models.document import Document

    review = await db.get(ReviewTable, table_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review table nao encontrada")

    user_id = str(current_user.id)
    org_id = getattr(current_user, "organization_id", None)
    if review.user_id != user_id and review.organization_id != org_id:
        raise HTTPException(status_code=403, detail="Sem permissao")

    cell = await db.get(CellExtraction, cell_id)
    if not cell or cell.review_table_id != table_id:
        raise HTTPException(status_code=404, detail="Celula nao encontrada")

    # Buscar nome do documento
    doc = await db.get(Document, cell.document_id)
    doc_name = getattr(doc, "name", cell.document_id) if doc else cell.document_id

    # Determinar nome da coluna
    column_name = cell.column_name
    if not column_name and cell.dynamic_column_id:
        from app.models.dynamic_column import DynamicColumn
        dynamic_col = await db.get(DynamicColumn, cell.dynamic_column_id)
        if dynamic_col:
            column_name = dynamic_col.name

    return CellSourceResponse(
        cell_id=cell.id,
        document_id=cell.document_id,
        document_name=doc_name,
        column_name=column_name or "",
        extracted_value=cell.extracted_value,
        source_snippet=cell.source_snippet,
        source_page=cell.source_page,
        source_char_start=cell.source_char_start,
        source_char_end=cell.source_char_end,
        confidence=cell.confidence,
        extraction_reasoning=cell.extraction_reasoning,
    )


@router.get("/{table_id}/cells", response_model=List[CellExtractionResponse])
async def list_cells(
    table_id: str,
    document_id: Optional[str] = Query(None, description="Filtrar por documento"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filtrar por status: pending, verified, rejected, corrected"),
    min_confidence: Optional[float] = Query(None, ge=0.0, le=1.0, description="Confianca minima"),
    max_confidence: Optional[float] = Query(None, ge=0.0, le=1.0, description="Confianca maxima"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Listar todas as celulas extraidas de uma review table com filtros."""
    review = await db.get(ReviewTable, table_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review table nao encontrada")

    user_id = str(current_user.id)
    org_id = getattr(current_user, "organization_id", None)
    if review.user_id != user_id and review.organization_id != org_id:
        raise HTTPException(status_code=403, detail="Sem permissao")

    try:
        if document_id:
            cells = await cell_verification_service.get_cells_for_document(
                review_table_id=table_id,
                document_id=document_id,
                db=db,
            )
            # Aplicar filtros adicionais em memoria
            if status_filter:
                cells = [c for c in cells if c.verification_status == status_filter]
            if min_confidence is not None:
                cells = [c for c in cells if c.confidence >= min_confidence]
            if max_confidence is not None:
                cells = [c for c in cells if c.confidence <= max_confidence]
        else:
            cells = await cell_verification_service.get_cells_for_review_table(
                review_table_id=table_id,
                status_filter=status_filter,
                min_confidence=min_confidence,
                max_confidence=max_confidence,
                db=db,
            )

        return [_cell_to_response(cell) for cell in cells]

    except Exception as e:
        logger.error("Erro ao listar celulas: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao listar celulas")


def _cell_to_response(cell: CellExtraction) -> CellExtractionResponse:
    """Converte CellExtraction para response schema."""
    return CellExtractionResponse(
        id=cell.id,
        document_id=cell.document_id,
        column_id=cell.dynamic_column_id,
        column_name=cell.column_name,
        value=cell.extracted_value,
        display_value=cell.display_value,
        confidence=cell.confidence,
        verification_status=cell.verification_status,
        is_verified=cell.is_verified,
        source_snippet=cell.source_snippet,
        source_page=cell.source_page,
        verified_by=cell.verified_by,
        verified_at=cell.verified_at.isoformat() if cell.verified_at else None,
        corrected_value=cell.corrected_value,
        correction_note=cell.correction_note,
    )


# ---------------------------------------------------------------------------
# Natural Language Query
# ---------------------------------------------------------------------------


@router.post("/{review_id}/query", response_model=QueryResponse)
async def query_review_table(
    review_id: str,
    request: QueryRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Consultar a review table usando linguagem natural.

    DEPRECATED: Use POST /{table_id}/chat para o novo Ask Table com historico.
    """
    review = await db.get(ReviewTable, review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review table nao encontrada")

    user_id = str(current_user.id)
    org_id = getattr(current_user, "organization_id", None)
    if review.user_id != user_id and review.organization_id != org_id:
        raise HTTPException(status_code=403, detail="Sem permissao")

    if not review.results:
        raise HTTPException(
            status_code=400,
            detail="A review table ainda nao possui resultados."
        )

    try:
        answer, sources = await review_table_service.query_review_table(
            review=review,
            question=request.question,
            db=db,
        )
        return QueryResponse(answer=answer, sources=sources)
    except Exception as e:
        logger.error("Erro na consulta da review table %s: %s", review_id, e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Erro ao processar a consulta. Tente novamente."
        )


# ---------------------------------------------------------------------------
# Ask Table (Chat) Endpoints
# ---------------------------------------------------------------------------


@router.post("/{table_id}/chat", response_model=AskTableResponse)
async def ask_table(
    table_id: str,
    request: AskTableRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Ask Table: faca perguntas em linguagem natural sobre os dados extraidos.

    Suporta varios tipos de queries:
    - FILTER: "Quais documentos tem Demand Rights?"
    - AGGREGATION: "Quantos documentos tem blackout provisions?"
    - COMPARISON: "Compare as estruturas de prioridade entre documentos"
    - SUMMARY: "Resuma os principais achados"
    - SPECIFIC: "O que o documento X diz sobre Y?"

    A resposta inclui:
    - answer: Resposta em linguagem natural
    - documents: Documentos citados
    - data: Dados estruturados (agregacoes, listas)
    - visualization_hint: Sugestao de visualizacao
    - message_id: ID da mensagem salva no historico
    """
    review = await db.get(ReviewTable, table_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review table nao encontrada")

    user_id = str(current_user.id)
    org_id = getattr(current_user, "organization_id", None)
    if review.user_id != user_id and review.organization_id != org_id:
        raise HTTPException(status_code=403, detail="Sem permissao")

    if not review.results:
        raise HTTPException(
            status_code=400,
            detail="A review table ainda nao possui resultados extraidos."
        )

    try:
        result = await table_chat_service.ask_table(
            review_table_id=table_id,
            question=request.question,
            user_id=user_id,
            db=db,
            include_history=request.include_history,
        )

        # Converter documents para schema
        docs = [
            DocumentReference(
                id=d.get("id", ""),
                name=d.get("name", ""),
                relevance=d.get("relevance"),
            )
            for d in result.get("documents", [])
            if isinstance(d, dict)
        ]

        return AskTableResponse(
            answer=result.get("answer", ""),
            query_type=result.get("query_type", "general"),
            documents=docs,
            data=result.get("data"),
            visualization_hint=result.get("visualization_hint"),
            message_id=result.get("message_id", ""),
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Erro no Ask Table %s: %s", table_id, e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Erro ao processar a pergunta. Tente novamente."
        )


@router.get("/{table_id}/chat/history", response_model=ChatHistoryResponse)
async def get_table_chat_history(
    table_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Obter historico de chat de uma review table.

    Retorna as mensagens em ordem cronologica (mais antigas primeiro).
    Use offset e limit para paginacao.
    """
    review = await db.get(ReviewTable, table_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review table nao encontrada")

    user_id = str(current_user.id)
    org_id = getattr(current_user, "organization_id", None)
    if review.user_id != user_id and review.organization_id != org_id:
        raise HTTPException(status_code=403, detail="Sem permissao")

    messages = await table_chat_service.get_chat_history(
        review_table_id=table_id,
        db=db,
        limit=limit,
        offset=offset,
    )

    # Contar total
    count_stmt = select(func.count()).where(
        TableChatMessage.review_table_id == table_id
    )
    total = (await db.execute(count_stmt)).scalar() or 0

    items = [
        ChatMessageResponse(
            id=msg.id,
            role=msg.role,
            content=msg.content,
            query_type=msg.query_type,
            query_result=msg.query_result,
            documents_referenced=msg.documents_referenced or [],
            visualization_hint=msg.visualization_hint,
            created_at=msg.created_at.isoformat() if msg.created_at else "",
        )
        for msg in messages
    ]

    return ChatHistoryResponse(messages=items, total=total)


@router.delete("/{table_id}/chat/history")
async def clear_table_chat_history(
    table_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Limpar historico de chat de uma review table.

    Remove todas as mensagens do historico. Esta acao e irreversivel.
    """
    review = await db.get(ReviewTable, table_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review table nao encontrada")

    user_id = str(current_user.id)
    org_id = getattr(current_user, "organization_id", None)
    if review.user_id != user_id and review.organization_id != org_id:
        raise HTTPException(status_code=403, detail="Sem permissao")

    deleted_count = await table_chat_service.clear_chat_history(
        review_table_id=table_id,
        db=db,
    )

    return {
        "success": True,
        "deleted_count": deleted_count,
        "message": f"{deleted_count} mensagem(ns) removida(s) do historico.",
    }


@router.get("/{table_id}/chat/statistics", response_model=TableStatisticsResponse)
async def get_table_chat_statistics(
    table_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Obter estatisticas resumidas da tabela.

    Util para exibir resumo antes de iniciar perguntas.
    Inclui:
    - Total de documentos
    - Numero de colunas
    - Estatisticas por coluna (preenchidos, nao encontrados, taxa de preenchimento)
    """
    review = await db.get(ReviewTable, table_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review table nao encontrada")

    user_id = str(current_user.id)
    org_id = getattr(current_user, "organization_id", None)
    if review.user_id != user_id and review.organization_id != org_id:
        raise HTTPException(status_code=403, detail="Sem permissao")

    template = await db.get(ReviewTableTemplate, review.template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template nao encontrado")

    stats = await table_chat_service.get_table_statistics(
        review=review,
        template=template,
    )

    return TableStatisticsResponse(
        total_documents=stats.get("total_documents", 0),
        columns=stats.get("columns", 0),
        column_stats=stats.get("column_stats", {}),
    )


# ---------------------------------------------------------------------------
# Dynamic Columns — Create via Natural Language Prompt
# ---------------------------------------------------------------------------


@router.post("/{table_id}/dynamic-columns", response_model=DynamicColumnResponse, status_code=201)
async def create_dynamic_column(
    table_id: str,
    request: CreateDynamicColumnRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Criar coluna dinamica via prompt em linguagem natural.

    O sistema analisa o prompt para inferir:
    - Tipo de extracao (text, boolean, number, date, etc.)
    - Nome sugestivo para a coluna
    - Opcoes de enum se aplicavel

    Apos criar a coluna, inicia extracao automatica em background
    para todos os documentos da review table.

    Exemplo:
        POST /review-tables/{id}/dynamic-columns
        {"prompt": "What type of registration rights are granted?"}

    Retorna a coluna criada com metadados inferidos.
    """
    # Validar acesso
    review = await db.get(ReviewTable, table_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review table nao encontrada")

    user_id = str(current_user.id)
    org_id = getattr(current_user, "organization_id", None)
    if review.user_id != user_id and review.organization_id != org_id:
        raise HTTPException(status_code=403, detail="Sem permissao")

    try:
        column = await column_builder_service.create_column_from_prompt(
            review_table_id=table_id,
            prompt=request.prompt,
            user_id=user_id,
            db=db,
            name=request.name,
            extraction_type=request.extraction_type,
            enum_options=request.enum_options,
            extraction_instructions=request.extraction_instructions,
        )

        # Iniciar extracao em background
        background_tasks.add_task(
            _extract_column_background,
            column_id=column.id,
        )

        return await _dynamic_column_to_response(column, db=db)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Erro ao criar coluna dinamica: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Erro interno ao criar coluna."
        )


@router.get("/{table_id}/dynamic-columns", response_model=DynamicColumnListResponse)
async def list_dynamic_columns(
    table_id: str,
    include_inactive: bool = Query(False, description="Incluir colunas desativadas"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Listar colunas dinamicas de uma review table."""
    review = await db.get(ReviewTable, table_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review table nao encontrada")

    user_id = str(current_user.id)
    org_id = getattr(current_user, "organization_id", None)
    if review.user_id != user_id and review.organization_id != org_id:
        raise HTTPException(status_code=403, detail="Sem permissao")

    stmt = select(DynamicColumn).where(DynamicColumn.review_table_id == table_id)

    if not include_inactive:
        stmt = stmt.where(DynamicColumn.is_active == True)  # noqa: E712

    stmt = stmt.order_by(DynamicColumn.order)

    result = await db.execute(stmt)
    columns = result.scalars().all()

    items = [await _dynamic_column_to_response(col, db=db) for col in columns]
    return DynamicColumnListResponse(items=items, total=len(items))


@router.get("/{table_id}/dynamic-columns/{column_id}", response_model=ColumnExtractionsResponse)
async def get_dynamic_column_with_extractions(
    table_id: str,
    column_id: str,
    verification_status: Optional[str] = Query(None, description="Filtrar por status: pending, verified, rejected, corrected"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Obter coluna dinamica com suas extracoes."""
    review = await db.get(ReviewTable, table_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review table nao encontrada")

    user_id = str(current_user.id)
    org_id = getattr(current_user, "organization_id", None)
    if review.user_id != user_id and review.organization_id != org_id:
        raise HTTPException(status_code=403, detail="Sem permissao")

    column = await db.get(DynamicColumn, column_id)
    if not column or column.review_table_id != table_id:
        raise HTTPException(status_code=404, detail="Coluna nao encontrada")

    # Obter extracoes
    ver_status = None
    if verification_status:
        try:
            ver_status = VerificationStatus(verification_status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Status invalido: {verification_status}")

    extractions = await column_builder_service.get_column_extractions(
        column_id=column_id,
        db=db,
        verification_status=ver_status,
    )

    # Carregar nomes dos documentos
    from app.models.document import Document
    extraction_responses = []
    for ext in extractions:
        doc = await db.get(Document, ext.document_id)
        doc_name = doc.name if doc else "Documento nao encontrado"
        extraction_responses.append(
            CellExtractionResponse(
                id=ext.id,
                document_id=ext.document_id,
                column_id=ext.dynamic_column_id,
                column_name=ext.column_name or column.name,
                value=ext.extracted_value,
                display_value=ext.display_value,
                confidence=ext.confidence,
                verification_status=ext.verification_status,
                is_verified=ext.is_verified,
                source_snippet=ext.source_snippet,
                source_page=ext.source_page,
                verified_by=ext.verified_by,
                verified_at=ext.verified_at.isoformat() if ext.verified_at else None,
                corrected_value=ext.corrected_value,
                correction_note=getattr(ext, 'correction_note', None),
            )
        )

    # Calcular estatisticas
    stats = {
        "total": len(extractions),
        "verified": sum(1 for e in extractions if e.verification_status == VerificationStatus.VERIFIED),
        "rejected": sum(1 for e in extractions if e.verification_status == VerificationStatus.REJECTED),
        "corrected": sum(1 for e in extractions if e.verification_status == VerificationStatus.CORRECTED),
        "pending": sum(1 for e in extractions if e.verification_status == VerificationStatus.PENDING),
        "avg_confidence": sum(e.confidence for e in extractions) / len(extractions) if extractions else 0,
        "low_confidence_count": sum(1 for e in extractions if e.confidence < 0.5),
    }

    return ColumnExtractionsResponse(
        column=await _dynamic_column_to_response(column, db=db),
        extractions=extraction_responses,
        total=len(extractions),
        stats=stats,
    )


@router.delete("/{table_id}/dynamic-columns/{column_id}", status_code=204)
async def delete_dynamic_column(
    table_id: str,
    column_id: str,
    hard_delete: bool = Query(False, description="Deletar permanentemente (default: apenas desativar)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Deletar coluna dinamica (soft delete por padrao)."""
    review = await db.get(ReviewTable, table_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review table nao encontrada")

    user_id = str(current_user.id)
    org_id = getattr(current_user, "organization_id", None)
    if review.user_id != user_id and review.organization_id != org_id:
        raise HTTPException(status_code=403, detail="Sem permissao")

    column = await db.get(DynamicColumn, column_id)
    if not column or column.review_table_id != table_id:
        raise HTTPException(status_code=404, detail="Coluna nao encontrada")

    if hard_delete:
        await db.delete(column)
    else:
        column.is_active = False
        column.updated_at = utcnow()

    await db.commit()
    return Response(status_code=204)


@router.post("/{table_id}/dynamic-columns/{column_id}/reprocess")
async def reprocess_dynamic_column(
    table_id: str,
    column_id: str,
    request: ReprocessColumnRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Reprocessar extracoes de uma coluna.

    Pode reprocessar todos os documentos ou apenas documentos especificos.
    Util quando:
    - A extracao inicial teve erros
    - O prompt da coluna foi atualizado
    - Novos documentos foram adicionados
    """
    review = await db.get(ReviewTable, table_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review table nao encontrada")

    user_id = str(current_user.id)
    org_id = getattr(current_user, "organization_id", None)
    if review.user_id != user_id and review.organization_id != org_id:
        raise HTTPException(status_code=403, detail="Sem permissao")

    column = await db.get(DynamicColumn, column_id)
    if not column or column.review_table_id != table_id:
        raise HTTPException(status_code=404, detail="Coluna nao encontrada")

    # Reprocessar em background
    background_tasks.add_task(
        _reprocess_column_background,
        column_id=column_id,
        document_ids=request.document_ids,
    )

    doc_count = len(request.document_ids) if request.document_ids else len(review.document_ids or [])

    return {
        "success": True,
        "message": f"Reprocessamento iniciado para {doc_count} documento(s).",
        "column_id": column_id,
    }


# ---------------------------------------------------------------------------
# Background tasks
# ---------------------------------------------------------------------------


async def _extract_column_background(column_id: str) -> None:
    """Extrai valores de uma coluna para todos os documentos em background."""
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        try:
            column = await db.get(DynamicColumn, column_id)
            if column:
                await column_builder_service.extract_column_for_all_documents(
                    column=column,
                    db=db,
                )
        except Exception as e:
            logger.error(
                "Erro na extracao background da coluna %s: %s",
                column_id, e, exc_info=True,
            )


async def _reprocess_column_background(
    column_id: str,
    document_ids: Optional[List[str]] = None,
) -> None:
    """Reprocessa extracoes de uma coluna em background."""
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        try:
            await column_builder_service.reprocess_column(
                column_id=column_id,
                db=db,
                document_ids=document_ids,
            )
        except Exception as e:
            logger.error(
                "Erro no reprocessamento background da coluna %s: %s",
                column_id, e, exc_info=True,
            )


async def _process_review_background(review_id: str) -> None:
    """Processa review table em background."""
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        try:
            await review_table_service.process_review(review_id=review_id, db=db)
        except Exception as e:
            logger.error(
                "Erro no processamento background da review %s: %s",
                review_id, e, exc_info=True,
            )


async def _fill_table_background(
    table_id: str,
    document_ids: Optional[List[str]] = None,
) -> None:
    """Preenche review table em background."""
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        try:
            await review_table_service.fill_table(
                table_id=table_id,
                document_ids=document_ids,
                db=db,
            )
        except Exception as e:
            logger.error(
                "Erro no preenchimento background da review %s: %s",
                table_id, e, exc_info=True,
            )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _template_to_response(t: ReviewTableTemplate) -> TemplateResponse:
    return TemplateResponse(
        id=t.id,
        name=t.name,
        description=t.description,
        area=t.area,
        columns=t.columns or [],
        is_system=t.is_system,
        created_by=t.created_by,
        organization_id=t.organization_id,
        is_active=t.is_active,
        created_at=t.created_at.isoformat() if t.created_at else "",
        updated_at=t.updated_at.isoformat() if t.updated_at else "",
    )


def _review_to_response(
    r: ReviewTable,
    template_name: Optional[str] = None,
) -> ReviewResponse:
    return ReviewResponse(
        id=r.id,
        template_id=r.template_id,
        template_name=template_name,
        name=r.name,
        user_id=r.user_id,
        organization_id=r.organization_id,
        status=r.status,
        document_ids=r.document_ids or [],
        results=r.results or [],
        total_documents=r.total_documents,
        processed_documents=r.processed_documents,
        accuracy_score=r.accuracy_score,
        error_message=r.error_message,
        cell_history=r.cell_history or [],
        created_at=r.created_at.isoformat() if r.created_at else "",
        updated_at=r.updated_at.isoformat() if r.updated_at else "",
    )


async def _dynamic_column_to_response(
    column: DynamicColumn,
    db: AsyncSession,
) -> DynamicColumnResponse:
    """Converte DynamicColumn para response schema com contagens."""
    # Contar extracoes por status
    stmt = select(func.count()).where(
        CellExtraction.dynamic_column_id == column.id
    )
    total_extractions = (await db.execute(stmt)).scalar() or 0

    pending_stmt = select(func.count()).where(
        CellExtraction.dynamic_column_id == column.id,
        CellExtraction.verification_status == VerificationStatus.PENDING,
    )
    pending_count = (await db.execute(pending_stmt)).scalar() or 0

    verified_stmt = select(func.count()).where(
        CellExtraction.dynamic_column_id == column.id,
        CellExtraction.verification_status.in_([
            VerificationStatus.VERIFIED,
            VerificationStatus.CORRECTED,
        ]),
    )
    verified_count = (await db.execute(verified_stmt)).scalar() or 0

    return DynamicColumnResponse(
        id=column.id,
        review_table_id=column.review_table_id,
        name=column.name,
        prompt=column.prompt,
        extraction_type=column.extraction_type,
        enum_options=column.enum_options,
        extraction_instructions=column.extraction_instructions,
        order=column.order,
        is_active=column.is_active,
        created_by=column.created_by,
        created_at=column.created_at.isoformat() if column.created_at else "",
        updated_at=column.updated_at.isoformat() if column.updated_at else "",
        extraction_count=total_extractions,
        pending_count=pending_count,
        verified_count=verified_count,
    )
