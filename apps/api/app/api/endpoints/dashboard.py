"""
Dashboard — Endpoint de atividade recente para homepage personalizada.

GET /dashboard/recent-activity — Retorna atividade recente do usuário autenticado.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.chat import Chat
from app.models.corpus_project import CorpusProject
from app.models.playbook import Playbook, PlaybookRule
from app.models.review_table import ReviewTable
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class RecentPlaybook(BaseModel):
    id: str
    name: str
    updated_at: str
    rule_count: int


class RecentCorpusProject(BaseModel):
    id: str
    name: str
    document_count: int
    updated_at: str


class RecentChat(BaseModel):
    id: str
    title: str
    updated_at: str


class RecentReviewTable(BaseModel):
    id: str
    name: str
    status: str
    processed_documents: int
    total_documents: int


class DashboardStats(BaseModel):
    total_playbooks: int
    total_corpus_docs: int
    total_chats: int
    total_review_tables: int


class DashboardRecentActivityResponse(BaseModel):
    recent_playbooks: list[RecentPlaybook]
    recent_corpus_projects: list[RecentCorpusProject]
    recent_chats: list[RecentChat]
    recent_review_tables: list[RecentReviewTable]
    stats: DashboardStats


# ---------------------------------------------------------------------------
# GET /dashboard/recent-activity
# ---------------------------------------------------------------------------


@router.get("/recent-activity", response_model=DashboardRecentActivityResponse)
async def get_recent_activity(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DashboardRecentActivityResponse:
    """Retorna atividade recente e estatísticas do usuário autenticado."""
    user_id = current_user.id

    # --- Recent Playbooks (last 5, with rule count) ---
    playbooks_stmt = (
        select(
            Playbook.id,
            Playbook.name,
            Playbook.updated_at,
            func.count(PlaybookRule.id).label("rule_count"),
        )
        .outerjoin(PlaybookRule, PlaybookRule.playbook_id == Playbook.id)
        .where(Playbook.user_id == user_id, Playbook.is_active == True)
        .group_by(Playbook.id)
        .order_by(Playbook.updated_at.desc())
        .limit(5)
    )
    playbooks_result = await db.execute(playbooks_stmt)
    recent_playbooks = [
        RecentPlaybook(
            id=row.id,
            name=row.name,
            updated_at=row.updated_at.isoformat() if row.updated_at else "",
            rule_count=row.rule_count or 0,
        )
        for row in playbooks_result.all()
    ]

    # --- Recent Corpus Projects (last 5) ---
    corpus_stmt = (
        select(CorpusProject)
        .where(CorpusProject.owner_id == user_id, CorpusProject.is_active == True)
        .order_by(CorpusProject.updated_at.desc())
        .limit(5)
    )
    corpus_result = await db.execute(corpus_stmt)
    recent_corpus_projects = [
        RecentCorpusProject(
            id=row.id,
            name=row.name,
            document_count=row.document_count or 0,
            updated_at=row.updated_at.isoformat() if row.updated_at else "",
        )
        for row in corpus_result.scalars().all()
    ]

    # --- Recent Chats (last 5) ---
    chats_stmt = (
        select(Chat)
        .where(Chat.user_id == user_id, Chat.is_active == True)
        .order_by(Chat.updated_at.desc())
        .limit(5)
    )
    chats_result = await db.execute(chats_stmt)
    recent_chats = [
        RecentChat(
            id=row.id,
            title=row.title or "Sem título",
            updated_at=row.updated_at.isoformat() if row.updated_at else "",
        )
        for row in chats_result.scalars().all()
    ]

    # --- Recent Review Tables (last 5) ---
    reviews_stmt = (
        select(ReviewTable)
        .where(ReviewTable.user_id == user_id)
        .order_by(ReviewTable.updated_at.desc())
        .limit(5)
    )
    reviews_result = await db.execute(reviews_stmt)
    recent_review_tables = [
        RecentReviewTable(
            id=row.id,
            name=row.name,
            status=row.status if isinstance(row.status, str) else row.status.value,
            processed_documents=row.processed_documents or 0,
            total_documents=row.total_documents or 0,
        )
        for row in reviews_result.scalars().all()
    ]

    # --- Stats (counts) ---
    total_playbooks_q = await db.execute(
        select(func.count(Playbook.id)).where(
            Playbook.user_id == user_id, Playbook.is_active == True
        )
    )
    total_playbooks = total_playbooks_q.scalar() or 0

    total_corpus_docs_q = await db.execute(
        select(func.coalesce(func.sum(CorpusProject.document_count), 0)).where(
            CorpusProject.owner_id == user_id, CorpusProject.is_active == True
        )
    )
    total_corpus_docs = total_corpus_docs_q.scalar() or 0

    total_chats_q = await db.execute(
        select(func.count(Chat.id)).where(
            Chat.user_id == user_id, Chat.is_active == True
        )
    )
    total_chats = total_chats_q.scalar() or 0

    total_reviews_q = await db.execute(
        select(func.count(ReviewTable.id)).where(ReviewTable.user_id == user_id)
    )
    total_review_tables = total_reviews_q.scalar() or 0

    return DashboardRecentActivityResponse(
        recent_playbooks=recent_playbooks,
        recent_corpus_projects=recent_corpus_projects,
        recent_chats=recent_chats,
        recent_review_tables=recent_review_tables,
        stats=DashboardStats(
            total_playbooks=total_playbooks,
            total_corpus_docs=int(total_corpus_docs),
            total_chats=total_chats,
            total_review_tables=total_review_tables,
        ),
    )
