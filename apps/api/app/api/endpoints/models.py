"""
Model Routing Endpoints

Exposes:
- POST /models/route: Roteamento inteligente de modelo por tipo de tarefa
- GET /models/routes: Tabela de roteamento completa (admin/debug)
- GET /models/metrics: Métricas de performance por rota
- GET /models/available: Lista de modelos disponíveis
"""

from fastapi import APIRouter, Depends
from loguru import logger

from app.core.security import get_current_user
from app.models.user import User
from app.services.ai.model_router import (
    RouteRequest,
    RouteResult,
    model_router,
)
from app.services.ai.model_registry import list_available_models

router = APIRouter()


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
