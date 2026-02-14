"""
Graph Enrichment Schemas — Pipeline L1→L2→L3→L3b.

Request/Response models for the /graph/enrich endpoint.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class EnrichLayer(str, Enum):
    structural = "structural"       # L1
    embedding = "embedding"         # L2
    llm = "llm"                     # L3
    exploratory = "exploratory"     # L3b
    all = "all"


class EnrichRequest(BaseModel):
    """Configuração do pipeline de enriquecimento."""
    layers: List[EnrichLayer] = Field(
        default=[EnrichLayer.all],
        description="Camadas a executar (all = L1+L2+L3+L3b)"
    )
    pass_l2_to_l3: bool = Field(
        default=True,
        description="Passar candidatos L2 para validação L3"
    )

    # L2 — embedding
    use_adaptive_threshold: bool = True
    total_budget: int = Field(10000, ge=100, le=100000)
    enable_artigo: bool = True
    enable_cross_type: bool = True

    # L3 — LLM
    llm_provider: str = "openai"
    llm_model: str = "gpt-4o-mini"
    max_llm_pairs: int = Field(50, ge=1, le=200)
    min_confidence: float = Field(0.75, ge=0.0, le=1.0)

    # L3b — exploratório
    explore_node_types: Optional[List[str]] = None
    max_isolated_nodes: int = Field(50, ge=1, le=500)
    max_degree_isolated: int = Field(1, ge=0, le=5)
    min_confidence_exploratory: float = Field(0.80, ge=0.0, le=1.0)


class LayerResult(BaseModel):
    """Resultado de uma camada de enriquecimento."""
    layer: str
    candidates_created: int = 0
    details: Dict[str, Any] = Field(default_factory=dict)
    duration_ms: int = 0
    warnings: List[str] = Field(default_factory=list)


class EnrichResponse(BaseModel):
    """Resposta completa do pipeline de enriquecimento."""
    success: bool
    layers_executed: List[str]
    total_candidates_created: int
    total_structural_created: int = 0
    layer_results: List[LayerResult]
    warnings: List[str] = Field(default_factory=list)
    duration_ms: int = 0
