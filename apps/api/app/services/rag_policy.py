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
    membership_groups = chat_context.get("rag_groups")
    scope_groups = membership_groups
    if isinstance(scope_groups, str):
        scope_groups = [g.strip() for g in scope_groups.split(",") if g.strip()]
    if not isinstance(scope_groups, list):
        scope_groups = []
    membership_groups_list = [str(g).strip() for g in scope_groups if str(g).strip()]
    membership_groups_set = set(membership_groups_list)

    selected_groups = chat_context.get("rag_selected_groups")
    selected_list: List[str] = []
    if isinstance(selected_groups, str):
        selected_list = [g.strip() for g in selected_groups.split(",") if g.strip()]
    elif isinstance(selected_groups, list):
        selected_list = [str(g).strip() for g in selected_groups if str(g).strip()]
    selected_set = set(selected_list)
    if membership_groups_set and selected_set:
        selected_set = selected_set.intersection(membership_groups_set)

    allow_global_scope = chat_context.get("rag_allow_global")
    allow_group_scope = chat_context.get("rag_allow_groups")


    policy = await fetch_rag_policy(db, tenant_id=tenant_id, user_id=user_id)
    if policy:
        policy_groups = [str(g).strip() for g in (policy.group_ids or []) if str(g).strip()]
        # Security: never grant group access outside user's actual org membership.
        # If membership is unknown/empty, we keep policy groups (backwards-compat),
        # but call-sites should always pass membership groups from OrgContext.
        effective_membership_set = membership_groups_set or set(policy_groups)
        if selected_set:
            effective_membership_set = effective_membership_set.intersection(selected_set)
        if effective_membership_set:
            scope_groups = [g for g in policy_groups if g in effective_membership_set]
        else:
            scope_groups = policy_groups
        # Policy acts as the ceiling; UI/client flags can further restrict scope.
        policy_allow_global = bool(policy.allow_global)
        policy_allow_groups = bool(policy.allow_groups) and bool(scope_groups)

        if allow_global_scope is None:
            allow_global_scope = policy_allow_global
        else:
            allow_global_scope = bool(allow_global_scope) and policy_allow_global

        if allow_group_scope is None:
            allow_group_scope = policy_allow_groups
        else:
            allow_group_scope = bool(allow_group_scope) and policy_allow_groups
    else:
        if selected_set:
            scope_groups = [g for g in membership_groups_list if g in selected_set] if membership_groups_list else list(selected_set)
        if allow_global_scope is None:
            allow_global_scope = user_role == UserRole.ADMIN
        if allow_group_scope is None:
            allow_group_scope = bool(scope_groups)

    # Normalize and de-dup
    scope_groups = list(dict.fromkeys([str(g).strip() for g in (scope_groups or []) if str(g).strip()]))

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
