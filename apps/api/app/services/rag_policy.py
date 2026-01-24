"""
Serviços para resolver políticas de acesso ao RAG por escopo.
"""

from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rag_policy import RAGAccessPolicy
from app.models.user import UserRole


async def fetch_rag_policy(
    db: AsyncSession,
    *,
    tenant_id: str,
    user_id: Optional[str] = None,
) -> Optional[RAGAccessPolicy]:
    if user_id:
        result = await db.execute(
            select(RAGAccessPolicy).where(
                RAGAccessPolicy.tenant_id == tenant_id,
                RAGAccessPolicy.user_id == user_id,
            )
        )
        policy = result.scalars().first()
        if policy:
            return policy
    result = await db.execute(
        select(RAGAccessPolicy).where(
            RAGAccessPolicy.tenant_id == tenant_id,
            RAGAccessPolicy.user_id.is_(None),
        )
    )
    return result.scalars().first()


async def resolve_rag_scope(
    db: AsyncSession,
    *,
    tenant_id: str,
    user_id: Optional[str],
    user_role: UserRole,
    chat_context: Optional[Dict[str, Any]] = None,
) -> Tuple[List[str], bool, bool]:
    chat_context = chat_context or {}
    scope_groups = chat_context.get("rag_groups")
    if isinstance(scope_groups, str):
        scope_groups = [g.strip() for g in scope_groups.split(",") if g.strip()]
    if not isinstance(scope_groups, list):
        scope_groups = []

    allow_global_scope = chat_context.get("rag_allow_global")
    allow_group_scope = chat_context.get("rag_allow_groups")


    policy = await fetch_rag_policy(db, tenant_id=tenant_id, user_id=user_id)
    if policy:
        scope_groups = list(policy.group_ids or [])
        allow_global_scope = bool(policy.allow_global)
        allow_group_scope = bool(policy.allow_groups)
    else:
        if allow_global_scope is None:
            allow_global_scope = user_role == UserRole.ADMIN
        if allow_group_scope is None:
            allow_group_scope = bool(scope_groups)

    return scope_groups, bool(allow_global_scope), bool(allow_group_scope)


async def upsert_rag_policy(
    db: AsyncSession,
    *,
    tenant_id: str,
    user_id: Optional[str],
    allow_global: bool,
    allow_groups: bool,
    group_ids: List[str],
) -> RAGAccessPolicy:
    result = await db.execute(
        select(RAGAccessPolicy).where(
            RAGAccessPolicy.tenant_id == tenant_id,
            RAGAccessPolicy.user_id == user_id,
        )
    )
    policy = result.scalars().first()
    if policy is None:
        policy = RAGAccessPolicy(
            tenant_id=tenant_id,
            user_id=user_id,
            allow_global=allow_global,
            allow_groups=allow_groups,
            group_ids=group_ids,
        )
        db.add(policy)
    else:
        policy.allow_global = allow_global
        policy.allow_groups = allow_groups
        policy.group_ids = group_ids
    await db.flush()
    return policy
