"""
Model Routing Endpoints

Exposes:
- POST /models/route: Roteamento inteligente de modelo por tipo de tarefa
- GET /models/routes: Tabela de roteamento completa (admin/debug)
- GET /models/metrics: Métricas de performance por rota
- GET /models/available: Lista de modelos disponíveis
"""

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User, UserRole
from app.services.audit_logger import log_audit
from app.services.ai.model_router import (
    RouteRequest,
    RouteResult,
    model_router,
)
from app.services.ai.model_registry import list_available_models
from app.services.ai.shared.feature_flags import FeatureFlagManager

router = APIRouter()


class FeatureFlagsUpdateRequest(BaseModel):
    overrides: Dict[str, Any] = Field(default_factory=dict)


def _require_admin(user: User) -> None:
    if user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito a administradores.",
        )


@router.post("/route", response_model=RouteResult)
async def route_model(
    request: RouteRequest,
    current_user: User = Depends(get_current_user),
) -> RouteResult:
    """Roteia uma tarefa para o modelo mais adequado.

    Recebe o tipo de tarefa e preferências opcionais, retornando
    o modelo recomendado com fallbacks e justificativa.

    O usuário pode forçar um modelo específico via `override_model`.
    """
    result = await model_router.route(request)
    logger.info(
        "Model route: user=%s task=%s → %s (override=%s)",
        current_user.id if current_user else "anon",
        request.task.value,
        result.model_id,
        result.is_override,
    )
    return result


@router.get("/routes")
async def get_route_table(
    current_user: User = Depends(get_current_user),
):
    """Retorna a tabela de roteamento completa (task -> modelos)."""
    return model_router.get_route_table()


@router.get("/metrics")
async def get_route_metrics(
    current_user: User = Depends(get_current_user),
):
    """Retorna métricas de performance por rota (task:model)."""
    return model_router.get_metrics()


@router.get("/available")
async def get_available_models(
    for_juridico: bool = False,
    for_agents: bool = False,
):
    """Lista modelos disponíveis no registry, com filtros opcionais."""
    return list_available_models(for_juridico=for_juridico, for_agents=for_agents)


@router.get("/agentic-flags")
async def get_agentic_feature_flags(
    current_user: User = Depends(get_current_user),
):
    """
    Snapshot de feature flags agentic + overrides runtime.
    Endpoint administrativo para governança de rollout.
    """
    _require_admin(current_user)
    manager = FeatureFlagManager()
    snapshot = manager.snapshot()
    return {
        "snapshot": {
            "global_enabled": snapshot.global_enabled,
            "auto_detect_sdk": snapshot.auto_detect_sdk,
            "sdk_available": snapshot.sdk_available,
            "canary_percent": snapshot.canary_percent,
            "analytics_sample_rate": snapshot.analytics_sample_rate,
            "executor_enabled": snapshot.executor_enabled,
            "limits": {
                "max_tool_calls_per_request": snapshot.limits.max_tool_calls_per_request,
                "max_delegated_tokens_per_request": snapshot.limits.max_delegated_tokens_per_request,
            },
        },
        "runtime_overrides": FeatureFlagManager.runtime_overrides(),
    }


@router.put("/agentic-flags")
async def update_agentic_feature_flags(
    payload: FeatureFlagsUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Atualiza overrides runtime para feature flags agentic.
    As mudanças são auditadas em `audit_logs`.
    """
    _require_admin(current_user)
    before = FeatureFlagManager.runtime_overrides()
    changed: Dict[str, Dict[str, Any]] = {}
    for key, value in (payload.overrides or {}).items():
        normalized_key = str(key or "").strip().upper()
        old_value = before.get(normalized_key)
        try:
            FeatureFlagManager.set_runtime_override(normalized_key, value)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        new_value = FeatureFlagManager.runtime_overrides().get(normalized_key)
        if old_value != new_value:
            changed[normalized_key] = {"old": old_value, "new": new_value}

    try:
        await log_audit(
            db=db,
            user_id=current_user.id,
            action="update",
            resource_type="agentic_feature_flags",
            resource_id=None,
            details={
                "changed": changed,
                "overrides_count": len(FeatureFlagManager.runtime_overrides()),
            },
        )
        await db.commit()
    except Exception as exc:
        logger.warning(f"Falha ao auditar alteração de feature flags: {exc}")

    manager = FeatureFlagManager()
    snapshot = manager.snapshot()
    return {
        "changed": changed,
        "runtime_overrides": FeatureFlagManager.runtime_overrides(),
        "snapshot": {
            "global_enabled": snapshot.global_enabled,
            "auto_detect_sdk": snapshot.auto_detect_sdk,
            "sdk_available": snapshot.sdk_available,
            "canary_percent": snapshot.canary_percent,
            "analytics_sample_rate": snapshot.analytics_sample_rate,
            "executor_enabled": snapshot.executor_enabled,
            "limits": {
                "max_tool_calls_per_request": snapshot.limits.max_tool_calls_per_request,
                "max_delegated_tokens_per_request": snapshot.limits.max_delegated_tokens_per_request,
            },
        },
    }


@router.delete("/agentic-flags/{flag_key}")
async def delete_agentic_feature_flag_override(
    flag_key: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Remove override runtime de uma feature flag agentic.
    """
    _require_admin(current_user)
    normalized_key = str(flag_key or "").strip().upper()
    before = FeatureFlagManager.runtime_overrides().get(normalized_key)
    removed = FeatureFlagManager.remove_runtime_override(normalized_key)
    after = FeatureFlagManager.runtime_overrides().get(normalized_key)

    try:
        await log_audit(
            db=db,
            user_id=current_user.id,
            action="delete",
            resource_type="agentic_feature_flags",
            resource_id=normalized_key,
            details={"old": before, "new": after, "removed": removed},
        )
        await db.commit()
    except Exception as exc:
        logger.warning(f"Falha ao auditar remoção de feature flag: {exc}")

    return {
        "flag_key": normalized_key,
        "removed": removed,
        "runtime_overrides": FeatureFlagManager.runtime_overrides(),
    }
