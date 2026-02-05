"""
Analytics API — Dashboard de métricas do Corpus, Workflows e Documentos.

Fornece estatísticas agregadas para a interface de Analytics,
inspirado no conceito de Vault Analytics da Harvey AI.
"""

from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, and_, case as sql_case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.database import get_db
from app.core.security import get_org_context, OrgContext
from app.models.document import Document, DocumentStatus, DocumentType
from app.models.workflow import Workflow, WorkflowRun, WorkflowRunStatus
from app.models.rag_trace import RAGTraceEvent
from app.models.chat import Chat, ChatMessage

logger = logging.getLogger(__name__)

router = APIRouter(tags=["analytics"])


# =============================================================================
# Helpers
# =============================================================================


def _build_user_filter(user_id: str, org_id: Optional[str], model):
    """Constrói filtro base por usuário/organização."""
    if org_id and hasattr(model, "organization_id"):
        return [model.organization_id == org_id]
    if hasattr(model, "user_id"):
        return [model.user_id == user_id]
    return []


# =============================================================================
# Corpus Overview
# =============================================================================


@router.get("/corpus/overview")
async def corpus_overview(
    ctx: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
):
    """
    Estatísticas gerais do Corpus: total de documentos, buscas e armazenamento.
    """
    user_id = ctx.user.id
    org_id = ctx.organization_id
    base_filter = _build_user_filter(user_id, org_id, Document)

    # Total de documentos
    total_q = select(func.count(Document.id)).where(and_(*base_filter))
    total_result = await db.execute(total_q)
    total_documents = total_result.scalar() or 0

    # Documentos por tipo (para "coleções" baseadas em category)
    from app.services.corpus_service import COLLECTION_DISPLAY

    collections = []
    for coll_name, coll_meta in COLLECTION_DISPLAY.items():
        collections.append({
            "name": coll_name,
            "label": coll_meta["display_name"],
            "count": 0,
        })

    # Contar documentos ingeridos por scope/category
    if base_filter:
        scope_q = (
            select(Document.rag_scope, func.count(Document.id))
            .where(and_(*base_filter, Document.rag_ingested == True))  # noqa: E712
            .group_by(Document.rag_scope)
        )
        scope_result = await db.execute(scope_q)
        scope_counts = dict(scope_result.all())
    else:
        scope_counts = {}

    # Tentar obter contagens reais dos backends RAG
    try:
        from app.services.corpus_service import CorpusService
        service = CorpusService(db=db)
        coll_counts = await service._get_collection_counts()
        for col in collections:
            col["count"] = coll_counts.get(col["name"], 0)
    except Exception:
        # Fallback: distribuir documentos estimados pelas coleções
        category_q = (
            select(Document.category, func.count(Document.id))
            .where(and_(*base_filter))
            .group_by(Document.category)
        )
        cat_result = await db.execute(category_q)
        cat_counts = dict(cat_result.all())

        category_to_collection = {
            "LEI": "lei",
            "SENTENCA": "juris",
            "ACORDAO": "juris",
            "PETICAO": "pecas_modelo",
            "PARECER": "sei",
        }
        for cat_val, count in cat_counts.items():
            if cat_val is not None:
                cat_str = cat_val.value if hasattr(cat_val, "value") else str(cat_val)
                coll_name = category_to_collection.get(cat_str)
                if coll_name:
                    for col in collections:
                        if col["name"] == coll_name:
                            col["count"] += count

    # Total de buscas (RAG trace events com event = "search" nos últimos 30 dias)
    total_searches = 0
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        search_q = select(func.count(RAGTraceEvent.id)).where(
            and_(
                RAGTraceEvent.user_id == str(user_id),
                RAGTraceEvent.event.in_(["search", "retrieve", "query", "corpus_search"]),
                RAGTraceEvent.created_at >= cutoff,
            )
        )
        search_result = await db.execute(search_q)
        total_searches = search_result.scalar() or 0
    except Exception as e:
        logger.debug(f"Não foi possível contar buscas do RAG trace: {e}")

    # Se não houver traces, estimar com base em chats recentes
    if total_searches == 0:
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(days=30)
            chat_msg_q = select(func.count(ChatMessage.id)).join(
                Chat, Chat.id == ChatMessage.chat_id
            ).where(
                and_(
                    Chat.user_id == str(user_id),
                    ChatMessage.role == "user",
                    ChatMessage.created_at >= cutoff,
                )
            )
            chat_result = await db.execute(chat_msg_q)
            total_searches = chat_result.scalar() or 0
        except Exception:
            pass

    # Armazenamento estimado (soma dos tamanhos dos documentos em MB)
    storage_q = select(func.coalesce(func.sum(Document.size), 0)).where(
        and_(*base_filter)
    )
    storage_result = await db.execute(storage_q)
    storage_bytes = storage_result.scalar() or 0
    storage_mb = round(storage_bytes / (1024 * 1024), 1)

    return {
        "total_documents": total_documents,
        "total_searches": total_searches,
        "collections": collections,
        "storage_mb": storage_mb,
    }


# =============================================================================
# Trending Topics
# =============================================================================


@router.get("/corpus/trending")
async def corpus_trending_topics(
    days: int = Query(default=30, ge=1, le=365),
    ctx: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
):
    """
    Tópicos de busca em alta nos últimos N dias.

    Agrega queries do RAG trace para identificar temas recorrentes.
    """
    user_id = str(ctx.user.id)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    trending = []

    # Tentar obter de RAGTraceEvent
    try:
        # Buscar queries recentes do trace
        trace_q = (
            select(RAGTraceEvent.payload)
            .where(
                and_(
                    RAGTraceEvent.user_id == user_id,
                    RAGTraceEvent.event.in_(["search", "retrieve", "query", "corpus_search"]),
                    RAGTraceEvent.created_at >= cutoff,
                )
            )
            .order_by(RAGTraceEvent.created_at.desc())
            .limit(500)
        )
        trace_result = await db.execute(trace_q)
        payloads = trace_result.scalars().all()

        # Extrair queries dos payloads
        query_counts: dict[str, int] = {}
        for payload in payloads:
            if isinstance(payload, dict):
                q = payload.get("query") or payload.get("text") or payload.get("search_query", "")
                if q and len(q) > 3:
                    q_lower = q.strip().lower()[:100]
                    query_counts[q_lower] = query_counts.get(q_lower, 0) + 1

        # Ordenar por frequência
        sorted_queries = sorted(query_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        for query_text, count in sorted_queries:
            trending.append({
                "query": query_text.title(),
                "count": count,
                "trend": "up" if count > 2 else "stable",
            })
    except Exception as e:
        logger.debug(f"Não foi possível obter trending topics do trace: {e}")

    # Se não houver dados reais, gerar baseado em títulos de chats recentes
    if not trending:
        try:
            chat_q = (
                select(Chat.title)
                .where(
                    and_(
                        Chat.user_id == user_id,
                        Chat.created_at >= cutoff,
                    )
                )
                .order_by(Chat.updated_at.desc())
                .limit(50)
            )
            chat_result = await db.execute(chat_q)
            titles = chat_result.scalars().all()

            title_counts: dict[str, int] = {}
            for title in titles:
                if title and len(title) > 5:
                    key = title.strip()[:80]
                    title_counts[key] = title_counts.get(key, 0) + 1

            sorted_titles = sorted(title_counts.items(), key=lambda x: x[1], reverse=True)[:10]
            for title, count in sorted_titles:
                trending.append({
                    "query": title,
                    "count": count,
                    "trend": "stable",
                })
        except Exception as e:
            logger.debug(f"Não foi possível obter trending topics de chats: {e}")

    return trending


# =============================================================================
# Usage Over Time
# =============================================================================


@router.get("/corpus/usage-over-time")
async def corpus_usage_over_time(
    days: int = Query(default=30, ge=1, le=365),
    granularity: str = Query(default="day"),
    ctx: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
):
    """
    Métricas de uso ao longo do tempo (documentos adicionados e buscas por dia).
    """
    user_id = str(ctx.user.id)
    org_id = ctx.organization_id
    base_filter = _build_user_filter(user_id, org_id, Document)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    today = datetime.now(timezone.utc).date()

    # Documentos adicionados por dia
    docs_per_day: dict[str, int] = {}
    try:
        doc_q = (
            select(
                func.date(Document.created_at).label("day"),
                func.count(Document.id).label("cnt"),
            )
            .where(and_(*base_filter, Document.created_at >= cutoff))
            .group_by(func.date(Document.created_at))
            .order_by(func.date(Document.created_at))
        )
        doc_result = await db.execute(doc_q)
        for row in doc_result.all():
            day_str = str(row.day) if row.day else ""
            if day_str:
                docs_per_day[day_str] = row.cnt
    except Exception as e:
        logger.debug(f"Erro ao consultar docs por dia: {e}")

    # Buscas por dia (via RAG trace ou mensagens de chat)
    searches_per_day: dict[str, int] = {}
    try:
        trace_q = (
            select(
                func.date(RAGTraceEvent.created_at).label("day"),
                func.count(RAGTraceEvent.id).label("cnt"),
            )
            .where(
                and_(
                    RAGTraceEvent.user_id == user_id,
                    RAGTraceEvent.event.in_(["search", "retrieve", "query", "corpus_search"]),
                    RAGTraceEvent.created_at >= cutoff,
                )
            )
            .group_by(func.date(RAGTraceEvent.created_at))
        )
        trace_result = await db.execute(trace_q)
        for row in trace_result.all():
            day_str = str(row.day) if row.day else ""
            if day_str:
                searches_per_day[day_str] = row.cnt
    except Exception:
        pass

    # Fallback: mensagens de chat como proxy de buscas
    if not searches_per_day:
        try:
            msg_q = (
                select(
                    func.date(ChatMessage.created_at).label("day"),
                    func.count(ChatMessage.id).label("cnt"),
                )
                .join(Chat, Chat.id == ChatMessage.chat_id)
                .where(
                    and_(
                        Chat.user_id == user_id,
                        ChatMessage.role == "user",
                        ChatMessage.created_at >= cutoff,
                    )
                )
                .group_by(func.date(ChatMessage.created_at))
            )
            msg_result = await db.execute(msg_q)
            for row in msg_result.all():
                day_str = str(row.day) if row.day else ""
                if day_str:
                    searches_per_day[day_str] = row.cnt
        except Exception:
            pass

    # Montar série temporal completa
    usage = []
    for i in range(days):
        day = cutoff.date() + timedelta(days=i + 1)
        if day > today:
            break
        day_str = day.isoformat()
        usage.append({
            "date": day_str,
            "searches": searches_per_day.get(day_str, 0),
            "documents_added": docs_per_day.get(day_str, 0),
        })

    return usage


# =============================================================================
# Workflow Stats
# =============================================================================


@router.get("/workflows/stats")
async def workflow_stats(
    ctx: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
):
    """
    Estatísticas de uso dos Workflows.
    """
    user_id = str(ctx.user.id)
    org_id = ctx.organization_id
    wf_filter = _build_user_filter(user_id, org_id, Workflow)

    # Total de workflows
    total_q = select(func.count(Workflow.id)).where(and_(*wf_filter))
    total_result = await db.execute(total_q)
    total = total_result.scalar() or 0

    # Workflows ativos
    active_q = select(func.count(Workflow.id)).where(
        and_(*wf_filter, Workflow.is_active == True)  # noqa: E712
    )
    active_result = await db.execute(active_q)
    active = active_result.scalar() or 0

    # Total de execuções
    total_runs = 0
    try:
        runs_q = select(func.coalesce(func.sum(Workflow.run_count), 0)).where(
            and_(*wf_filter)
        )
        runs_result = await db.execute(runs_q)
        total_runs = runs_result.scalar() or 0
    except Exception:
        pass

    # Top workflows por run_count
    top_q = (
        select(Workflow.id, Workflow.name, Workflow.run_count)
        .where(and_(*wf_filter))
        .order_by(Workflow.run_count.desc())
        .limit(10)
    )
    top_result = await db.execute(top_q)
    top_workflows = [
        {"id": row.id, "name": row.name, "run_count": row.run_count or 0}
        for row in top_result.all()
    ]

    # Sucesso dos runs recentes
    success_rate = None
    try:
        # Buscar IDs dos workflows do usuário
        wf_ids_q = select(Workflow.id).where(and_(*wf_filter))
        wf_ids_result = await db.execute(wf_ids_q)
        wf_ids = [row[0] for row in wf_ids_result.all()]

        if wf_ids:
            completed_q = select(func.count(WorkflowRun.id)).where(
                and_(
                    WorkflowRun.workflow_id.in_(wf_ids),
                    WorkflowRun.status == WorkflowRunStatus.COMPLETED,
                )
            )
            completed_result = await db.execute(completed_q)
            completed = completed_result.scalar() or 0

            total_finished_q = select(func.count(WorkflowRun.id)).where(
                and_(
                    WorkflowRun.workflow_id.in_(wf_ids),
                    WorkflowRun.status.in_([
                        WorkflowRunStatus.COMPLETED,
                        WorkflowRunStatus.ERROR,
                    ]),
                )
            )
            total_finished_result = await db.execute(total_finished_q)
            total_finished = total_finished_result.scalar() or 0

            if total_finished > 0:
                success_rate = round((completed / total_finished) * 100, 1)
    except Exception as e:
        logger.debug(f"Erro ao calcular taxa de sucesso: {e}")

    return {
        "total": total,
        "active": active,
        "total_runs": total_runs,
        "top_workflows": top_workflows,
        "success_rate": success_rate,
    }


# =============================================================================
# Document Insights
# =============================================================================


@router.get("/documents/insights")
async def document_insights(
    ctx: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
):
    """
    Insights sobre a coleção de documentos.
    """
    user_id = str(ctx.user.id)
    org_id = ctx.organization_id
    base_filter = _build_user_filter(user_id, org_id, Document)

    # Documentos por tipo
    type_q = (
        select(Document.type, func.count(Document.id))
        .where(and_(*base_filter))
        .group_by(Document.type)
    )
    type_result = await db.execute(type_q)
    by_type = {
        (row[0].value if hasattr(row[0], "value") else str(row[0])): row[1]
        for row in type_result.all()
        if row[0] is not None
    }

    # Documentos por categoria
    cat_q = (
        select(Document.category, func.count(Document.id))
        .where(and_(*base_filter))
        .group_by(Document.category)
    )
    cat_result = await db.execute(cat_q)
    by_category = {
        (row[0].value if hasattr(row[0], "value") else str(row[0])): row[1]
        for row in cat_result.all()
        if row[0] is not None
    }

    # Recentemente acessados (últimos 10 por updated_at)
    recent_q = (
        select(Document.id, Document.name, Document.type, Document.updated_at)
        .where(and_(*base_filter))
        .order_by(Document.updated_at.desc())
        .limit(10)
    )
    recent_result = await db.execute(recent_q)
    recently_accessed = [
        {
            "id": row.id,
            "name": row.name,
            "type": row.type.value if hasattr(row.type, "value") else str(row.type),
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
        for row in recent_result.all()
    ]

    # Total por status
    status_q = (
        select(Document.status, func.count(Document.id))
        .where(and_(*base_filter))
        .group_by(Document.status)
    )
    status_result = await db.execute(status_q)
    by_status = {
        (row[0].value if hasattr(row[0], "value") else str(row[0])): row[1]
        for row in status_result.all()
        if row[0] is not None
    }

    return {
        "by_type": by_type,
        "by_category": by_category,
        "by_status": by_status,
        "recently_accessed": recently_accessed,
    }
