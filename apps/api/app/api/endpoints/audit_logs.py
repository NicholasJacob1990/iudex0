"""
Endpoints de Audit Logs — Rastreamento de ações no sistema.

Acesso restrito a administradores.
Permite listagem paginada, filtragem e exportação CSV.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from loguru import logger
from sqlalchemy import func, select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.audit_log import AuditLog
from app.models.user import User, UserRole
from app.schemas.audit_log import AuditLogListResponse, AuditLogResponse

router = APIRouter(tags=["audit-logs"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_admin(user: User) -> None:
    """Levanta 403 se o usuário não for admin."""
    if user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito a administradores.",
        )


def _build_query(
    user_id: Optional[str],
    action: Optional[str],
    resource_type: Optional[str],
    resource_id: Optional[str],
    date_from: Optional[datetime],
    date_to: Optional[datetime],
    search: Optional[str],
):
    """Constrói query base com filtros opcionais."""
    query = select(AuditLog)

    if user_id:
        query = query.where(AuditLog.user_id == user_id)
    if action:
        query = query.where(AuditLog.action == action)
    if resource_type:
        query = query.where(AuditLog.resource_type == resource_type)
    if resource_id:
        query = query.where(AuditLog.resource_id == resource_id)
    if date_from:
        query = query.where(AuditLog.created_at >= date_from)
    if date_to:
        query = query.where(AuditLog.created_at <= date_to)

    return query


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=AuditLogListResponse)
async def list_audit_logs(
    user_id: Optional[str] = Query(default=None, description="Filtrar por ID do usuário"),
    action: Optional[str] = Query(default=None, description="Filtrar por ação"),
    resource_type: Optional[str] = Query(default=None, description="Filtrar por tipo de recurso"),
    resource_id: Optional[str] = Query(default=None, description="Filtrar por ID do recurso"),
    date_from: Optional[datetime] = Query(default=None, description="Data início (ISO 8601)"),
    date_to: Optional[datetime] = Query(default=None, description="Data fim (ISO 8601)"),
    search: Optional[str] = Query(default=None, description="Busca livre"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AuditLogListResponse:
    """
    Lista audit logs com paginação e filtros.
    Acesso restrito a administradores.
    """
    _require_admin(current_user)

    base_query = _build_query(user_id, action, resource_type, resource_id, date_from, date_to, search)

    # Total count
    count_query = select(func.count()).select_from(base_query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Paginated results with user join
    data_query = (
        base_query
        .order_by(desc(AuditLog.created_at))
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(data_query)
    logs = result.scalars().all()

    # Buscar nomes dos usuários em batch
    user_ids = list({log.user_id for log in logs})
    user_map: dict[str, User] = {}
    if user_ids:
        users_result = await db.execute(
            select(User).where(User.id.in_(user_ids))
        )
        for u in users_result.scalars().all():
            user_map[u.id] = u

    items = []
    for log in logs:
        u = user_map.get(log.user_id)
        items.append(
            AuditLogResponse(
                id=log.id,
                user_id=log.user_id,
                user_name=u.name if u else None,
                user_email=u.email if u else None,
                action=log.action,
                resource_type=log.resource_type,
                resource_id=log.resource_id,
                details=log.details,
                ip_address=log.ip_address,
                created_at=log.created_at,
            )
        )

    return AuditLogListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/export")
async def export_audit_logs_csv(
    user_id: Optional[str] = Query(default=None),
    action: Optional[str] = Query(default=None),
    resource_type: Optional[str] = Query(default=None),
    resource_id: Optional[str] = Query(default=None),
    date_from: Optional[datetime] = Query(default=None),
    date_to: Optional[datetime] = Query(default=None),
    search: Optional[str] = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Exporta audit logs em formato CSV.
    Acesso restrito a administradores.
    Limite de 10.000 registros por exportação.
    """
    _require_admin(current_user)

    base_query = _build_query(user_id, action, resource_type, resource_id, date_from, date_to, search)
    data_query = base_query.order_by(desc(AuditLog.created_at)).limit(10_000)

    result = await db.execute(data_query)
    logs = result.scalars().all()

    # Buscar nomes
    user_ids = list({log.user_id for log in logs})
    user_map: dict[str, User] = {}
    if user_ids:
        users_result = await db.execute(
            select(User).where(User.id.in_(user_ids))
        )
        for u in users_result.scalars().all():
            user_map[u.id] = u

    # Gerar CSV
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Data", "Usuário", "Email", "Ação", "Tipo Recurso", "ID Recurso", "IP", "Detalhes"])

    for log in logs:
        u = user_map.get(log.user_id)
        writer.writerow([
            log.created_at.isoformat() if log.created_at else "",
            u.name if u else log.user_id,
            u.email if u else "",
            log.action,
            log.resource_type,
            log.resource_id or "",
            log.ip_address or "",
            str(log.details) if log.details else "",
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="audit_logs.csv"',
        },
    )


@router.get("/stats")
async def audit_log_stats(
    days: int = Query(default=30, ge=1, le=365, description="Período em dias"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Estatísticas resumidas dos audit logs.
    """
    _require_admin(current_user)

    from app.core.time_utils import utcnow
    from datetime import timedelta

    since = utcnow() - timedelta(days=days)

    # Contagem por ação
    action_query = (
        select(AuditLog.action, func.count(AuditLog.id))
        .where(AuditLog.created_at >= since)
        .group_by(AuditLog.action)
    )
    action_result = await db.execute(action_query)
    actions = dict(action_result.all())

    # Contagem por tipo de recurso
    resource_query = (
        select(AuditLog.resource_type, func.count(AuditLog.id))
        .where(AuditLog.created_at >= since)
        .group_by(AuditLog.resource_type)
    )
    resource_result = await db.execute(resource_query)
    resources = dict(resource_result.all())

    # Total
    total_query = (
        select(func.count(AuditLog.id))
        .where(AuditLog.created_at >= since)
    )
    total_result = await db.execute(total_query)
    total = total_result.scalar() or 0

    # Usuários mais ativos
    top_users_query = (
        select(AuditLog.user_id, func.count(AuditLog.id).label("count"))
        .where(AuditLog.created_at >= since)
        .group_by(AuditLog.user_id)
        .order_by(func.count(AuditLog.id).desc())
        .limit(10)
    )
    top_users_result = await db.execute(top_users_query)
    top_users_raw = top_users_result.all()

    # Buscar nomes dos top users
    top_user_ids = [r[0] for r in top_users_raw]
    user_map: dict[str, User] = {}
    if top_user_ids:
        users_result = await db.execute(
            select(User).where(User.id.in_(top_user_ids))
        )
        for u in users_result.scalars().all():
            user_map[u.id] = u

    top_users = [
        {
            "user_id": uid,
            "name": user_map[uid].name if uid in user_map else uid,
            "count": count,
        }
        for uid, count in top_users_raw
    ]

    return {
        "period_days": days,
        "total": total,
        "by_action": actions,
        "by_resource_type": resources,
        "top_users": top_users,
    }
