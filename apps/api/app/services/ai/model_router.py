"""
Model Router - Roteamento inteligente de modelos por tipo de tarefa

Inspirado no Harvey AI: cada tipo de tarefa jurídica é roteada para o modelo
mais adequado em termos de qualidade, latência e custo.

Categorias de tarefa:
- contract_analysis: Análise e classificação de contratos
- drafting: Geração de minutas e documentos jurídicos
- research: Pesquisa jurídica e doutrinária
- citation_verification: Verificação factual de citações
- summarization: Resumo de documentos
- translation: Tradução jurídica
- redlining: Comparação e revisão de documentos
- deep_research: Pesquisa aprofundada com grounding
"""

import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.services.ai.model_registry import (
    MODEL_REGISTRY,
    ModelConfig,
    get_model_config,
)

logger = logging.getLogger("ModelRouter")


# ---------------------------------------------------------------------------
# Task Categories
# ---------------------------------------------------------------------------

class TaskCategory(str, Enum):
    """Categorias de tarefa suportadas pelo roteador."""

    CONTRACT_ANALYSIS = "contract_analysis"
    DRAFTING = "drafting"
    RESEARCH = "research"
    CITATION_VERIFICATION = "citation_verification"
    SUMMARIZATION = "summarization"
    TRANSLATION = "translation"
    REDLINING = "redlining"
    DEEP_RESEARCH = "deep_research"


# ---------------------------------------------------------------------------
# Pydantic schemas (request / response)
# ---------------------------------------------------------------------------

class RouteRequest(BaseModel):
    """Payload para solicitar roteamento de modelo."""

    task: TaskCategory = Field(..., description="Tipo de tarefa jurídica")
    override_model: Optional[str] = Field(
        default=None,
        description="Se informado, força o uso desse modelo (bypass do router)",
    )
    prefer_fast: bool = Field(
        default=False,
        description="Priorizar latência baixa sobre qualidade máxima",
    )
    prefer_cheap: bool = Field(
        default=False,
        description="Priorizar custo baixo sobre qualidade máxima",
    )
    context_tokens: Optional[int] = Field(
        default=None,
        ge=0,
        description="Estimativa de tokens do contexto (para filtrar modelos com janela insuficiente)",
    )


class RouteResult(BaseModel):
    """Resultado do roteamento de modelo."""

    model_id: str = Field(..., description="ID canônico do modelo selecionado")
    provider: str = Field(..., description="Provider do modelo (openai, anthropic, google, ...)")
    label: str = Field(..., description="Nome legível do modelo")
    task: str = Field(..., description="Categoria de tarefa solicitada")
    reason: str = Field(..., description="Justificativa da escolha")
    fallbacks: List[str] = Field(
        default_factory=list,
        description="IDs dos modelos de fallback, em ordem de prioridade",
    )
    is_override: bool = Field(
        default=False,
        description="True se o modelo foi forçado via override do usuário",
    )


# ---------------------------------------------------------------------------
# Performance metrics (in-memory)
# ---------------------------------------------------------------------------

@dataclass
class _RouteMetrics:
    """Métricas acumuladas por rota (task + model)."""

    total_calls: int = 0
    total_latency_ms: float = 0.0
    errors: int = 0
    last_called: float = 0.0

    @property
    def avg_latency_ms(self) -> float:
        if self.total_calls == 0:
            return 0.0
        return self.total_latency_ms / self.total_calls

    @property
    def error_rate(self) -> float:
        if self.total_calls == 0:
            return 0.0
        return self.errors / self.total_calls


# ---------------------------------------------------------------------------
# Route table: task -> (primary model, fallback models)
# ---------------------------------------------------------------------------

_ROUTE_TABLE: Dict[TaskCategory, List[str]] = {
    TaskCategory.CONTRACT_ANALYSIS: [
        "gemini-3-flash",       # Rápido, bom em classificação
        "gemini-3-pro",         # Fallback com mais capacidade
        "claude-4.5-sonnet",    # Fallback cross-provider
    ],
    TaskCategory.DRAFTING: [
        "claude-4.5-opus",      # Melhor geração de texto jurídico
        "claude-4.5-sonnet",    # Bom custo-benefício
        "gpt-5.2",              # Fallback cross-provider
    ],
    TaskCategory.RESEARCH: [
        "gemini-3-pro",         # Melhor recall, grounding
        "sonar-pro",            # Web-grounded research
        "claude-4.5-sonnet",    # Fallback cross-provider
    ],
    TaskCategory.CITATION_VERIFICATION: [
        "gpt-5.2",              # Preciso em verificação factual
        "claude-4.5-sonnet",    # Fallback
        "gemini-3-pro",         # Fallback cross-provider
    ],
    TaskCategory.SUMMARIZATION: [
        "claude-4.5-sonnet",    # Bom custo-benefício para resumo
        "gemini-3-flash",       # Rápido e barato
        "gpt-5",                # Fallback cross-provider
    ],
    TaskCategory.TRANSLATION: [
        "claude-4.5-sonnet",    # Excelente em tradução jurídica
        "gpt-5.2",              # Boa qualidade de tradução
        "gemini-3-pro",         # Fallback cross-provider
    ],
    TaskCategory.REDLINING: [
        "gemini-3-flash",       # Rápido para comparação lado-a-lado
        "gemini-3-pro",         # Mais capacidade se necessário
        "claude-4.5-sonnet",    # Fallback cross-provider
    ],
    TaskCategory.DEEP_RESEARCH: [
        "gemini-3-pro",         # Grounding + janela de contexto grande
        "sonar-deep-research",  # Pesquisa profunda web-grounded
        "claude-4.5-opus",      # Raciocínio estendido como fallback
    ],
}

# Preferências para modo rápido (prefer_fast=True)
_FAST_OVERRIDES: Dict[TaskCategory, str] = {
    TaskCategory.CONTRACT_ANALYSIS: "gemini-3-flash",
    TaskCategory.DRAFTING: "claude-4.5-sonnet",
    TaskCategory.RESEARCH: "gemini-3-flash",
    TaskCategory.CITATION_VERIFICATION: "gemini-3-flash",
    TaskCategory.SUMMARIZATION: "gemini-3-flash",
    TaskCategory.TRANSLATION: "claude-4.5-haiku",
    TaskCategory.REDLINING: "gemini-3-flash",
    TaskCategory.DEEP_RESEARCH: "gemini-3-pro",
}

# Preferências para modo barato (prefer_cheap=True)
_CHEAP_OVERRIDES: Dict[TaskCategory, str] = {
    TaskCategory.CONTRACT_ANALYSIS: "gemini-3-flash",
    TaskCategory.DRAFTING: "gemini-3-flash",
    TaskCategory.RESEARCH: "gemini-2.5-flash",
    TaskCategory.CITATION_VERIFICATION: "gpt-5-mini",
    TaskCategory.SUMMARIZATION: "gemini-3-flash",
    TaskCategory.TRANSLATION: "gemini-3-flash",
    TaskCategory.REDLINING: "gemini-3-flash",
    TaskCategory.DEEP_RESEARCH: "gemini-2.5-pro",
}


# ---------------------------------------------------------------------------
# Reasons (human-readable justification)
# ---------------------------------------------------------------------------

_TASK_REASONS: Dict[TaskCategory, str] = {
    TaskCategory.CONTRACT_ANALYSIS: "Gemini 3 Flash selecionado por velocidade e precisão em classificação de cláusulas",
    TaskCategory.DRAFTING: "Claude 4.5 Opus selecionado por qualidade superior em geração de texto jurídico formal",
    TaskCategory.RESEARCH: "Gemini 3 Pro selecionado por melhor recall e capacidade de grounding",
    TaskCategory.CITATION_VERIFICATION: "GPT-5.2 selecionado por precisão em verificação factual e citações",
    TaskCategory.SUMMARIZATION: "Claude 4.5 Sonnet selecionado por melhor custo-benefício em resumos",
    TaskCategory.TRANSLATION: "Claude 4.5 Sonnet selecionado por qualidade de tradução jurídica",
    TaskCategory.REDLINING: "Gemini 3 Flash selecionado por velocidade em comparação de documentos",
    TaskCategory.DEEP_RESEARCH: "Gemini 3 Pro selecionado por grounding e janela de contexto de 1M tokens",
}


# ---------------------------------------------------------------------------
# ModelRouter service
# ---------------------------------------------------------------------------

class ModelRouter:
    """Serviço singleton de roteamento inteligente de modelos.

    Responsável por:
    1. Selecionar o modelo ótimo para cada tipo de tarefa
    2. Gerenciar cadeia de fallbacks
    3. Respeitar overrides do usuário
    4. Coletar métricas de performance por rota
    """

    def __init__(self) -> None:
        self._metrics: Dict[str, _RouteMetrics] = defaultdict(_RouteMetrics)
        logger.info("ModelRouter inicializado com %d categorias de tarefa", len(TaskCategory))

    # ------------------------------------------------------------------
    # Core routing
    # ------------------------------------------------------------------

    async def route(self, request: RouteRequest) -> RouteResult:
        """Roteia uma tarefa para o modelo mais adequado.

        Args:
            request: Dados da solicitação incluindo tipo de tarefa e preferências.

        Returns:
            RouteResult com modelo selecionado, fallbacks e justificativa.
        """
        task = request.task

        # 1. Override do usuário tem prioridade absoluta
        if request.override_model:
            cfg = get_model_config(request.override_model)
            if cfg:
                logger.info(
                    "ModelRouter: override do usuário para task=%s → model=%s",
                    task.value,
                    request.override_model,
                )
                return RouteResult(
                    model_id=cfg.id,
                    provider=cfg.provider,
                    label=cfg.label,
                    task=task.value,
                    reason=f"Modelo {cfg.label} selecionado por override do usuário",
                    fallbacks=self._get_fallbacks(task, exclude=cfg.id),
                    is_override=True,
                )
            else:
                logger.warning(
                    "ModelRouter: override_model '%s' não encontrado no registry, usando rota padrão",
                    request.override_model,
                )

        # 2. Aplicar preferências de velocidade/custo
        primary_id = self._resolve_primary(task, request.prefer_fast, request.prefer_cheap)

        # 3. Filtrar por context_tokens se informado
        if request.context_tokens:
            primary_id = self._ensure_context_fits(primary_id, task, request.context_tokens)

        cfg = get_model_config(primary_id)
        if not cfg:
            # Fallback de segurança
            primary_id = "gemini-3-flash"
            cfg = get_model_config(primary_id)

        reason = self._build_reason(task, request.prefer_fast, request.prefer_cheap)
        fallbacks = self._get_fallbacks(task, exclude=primary_id)

        logger.info(
            "ModelRouter: task=%s → model=%s (provider=%s) | fallbacks=%s",
            task.value,
            primary_id,
            cfg.provider if cfg else "unknown",
            fallbacks,
        )

        return RouteResult(
            model_id=primary_id,
            provider=cfg.provider if cfg else "unknown",
            label=cfg.label if cfg else primary_id,
            task=task.value,
            reason=reason,
            fallbacks=fallbacks,
            is_override=False,
        )

    # ------------------------------------------------------------------
    # Convenience: route a task synchronously (thin wrapper)
    # ------------------------------------------------------------------

    def route_sync(self, task: TaskCategory, override_model: Optional[str] = None) -> RouteResult:
        """Versão síncrona para uso em contextos não-async.

        Args:
            task: Tipo de tarefa.
            override_model: Modelo forçado pelo usuário (opcional).

        Returns:
            RouteResult com modelo selecionado.
        """
        req = RouteRequest(task=task, override_model=override_model)
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Já estamos num event loop — criar future
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                result = pool.submit(asyncio.run, self.route(req)).result()
            return result
        return asyncio.run(self.route(req))

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    def record_call(
        self,
        task: TaskCategory,
        model_id: str,
        latency_ms: float,
        success: bool = True,
    ) -> None:
        """Registra métricas de uma chamada roteada.

        Args:
            task: Categoria da tarefa executada.
            model_id: Modelo que executou a tarefa.
            latency_ms: Latência da chamada em milissegundos.
            success: Se a chamada foi bem-sucedida.
        """
        key = f"{task.value}:{model_id}"
        m = self._metrics[key]
        m.total_calls += 1
        m.total_latency_ms += latency_ms
        m.last_called = time.time()
        if not success:
            m.errors += 1

    def get_metrics(self) -> Dict[str, Any]:
        """Retorna métricas agregadas de todas as rotas.

        Returns:
            Dicionário com métricas por rota (task:model).
        """
        result: Dict[str, Any] = {}
        for key, m in self._metrics.items():
            result[key] = {
                "total_calls": m.total_calls,
                "avg_latency_ms": round(m.avg_latency_ms, 2),
                "error_rate": round(m.error_rate, 4),
                "last_called": m.last_called,
            }
        return result

    def get_route_table(self) -> Dict[str, List[str]]:
        """Retorna a tabela de roteamento completa (para debugging/admin).

        Returns:
            Dicionário task -> lista de modelos [primary, ...fallbacks].
        """
        return {task.value: models for task, models in _ROUTE_TABLE.items()}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_primary(
        self,
        task: TaskCategory,
        prefer_fast: bool,
        prefer_cheap: bool,
    ) -> str:
        """Determina o modelo primário com base nas preferências."""
        if prefer_fast and task in _FAST_OVERRIDES:
            return _FAST_OVERRIDES[task]
        if prefer_cheap and task in _CHEAP_OVERRIDES:
            return _CHEAP_OVERRIDES[task]
        models = _ROUTE_TABLE.get(task, [])
        return models[0] if models else "gemini-3-flash"

    def _ensure_context_fits(
        self,
        model_id: str,
        task: TaskCategory,
        context_tokens: int,
    ) -> str:
        """Se o modelo primário não comporta o contexto, encontra um que comporte."""
        cfg = get_model_config(model_id)
        if cfg and cfg.context_window >= context_tokens:
            return model_id

        # Buscar fallbacks com janela suficiente
        for fallback_id in _ROUTE_TABLE.get(task, [])[1:]:
            fb_cfg = get_model_config(fallback_id)
            if fb_cfg and fb_cfg.context_window >= context_tokens:
                logger.info(
                    "ModelRouter: contexto de %d tokens excede janela de %s (%d), "
                    "promovendo fallback %s (%d)",
                    context_tokens,
                    model_id,
                    cfg.context_window if cfg else 0,
                    fallback_id,
                    fb_cfg.context_window,
                )
                return fallback_id

        # Último recurso: buscar qualquer modelo com janela suficiente
        for mid, mcfg in MODEL_REGISTRY.items():
            if mcfg.context_window >= context_tokens and mcfg.for_juridico:
                return mid

        return model_id  # Retorna o original se nenhum couber

    def _get_fallbacks(self, task: TaskCategory, exclude: str) -> List[str]:
        """Retorna fallbacks para a tarefa, excluindo o modelo primário."""
        models = _ROUTE_TABLE.get(task, [])
        return [m for m in models if m != exclude]

    def _build_reason(
        self,
        task: TaskCategory,
        prefer_fast: bool,
        prefer_cheap: bool,
    ) -> str:
        """Constrói a justificativa da escolha."""
        base = _TASK_REASONS.get(task, "Modelo selecionado pela rota padrão")
        if prefer_fast:
            base += " (modo rápido: priorizando latência)"
        if prefer_cheap:
            base += " (modo econômico: priorizando custo)"
        return base


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

model_router = ModelRouter()
