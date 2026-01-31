"""
LangGraph - Módulo de orquestração de workflows jurídicos

Este módulo contém:
- workflow.py: Workflow principal de geração de documentos
- nodes/: Nodes individuais do workflow
- subgraphs/: Sub-grafos (debate, research paralelo)
- improvements/: Melhorias (context manager, checkpoint, parallel nodes)
"""

from .improvements.context_manager import ContextManager, ContextWindow

# Subgraphs
from .subgraphs import (
    ResearchState,
    create_parallel_research_subgraph,
    parallel_research_subgraph,
    run_parallel_research,
)

__all__ = [
    # Improvements
    "ContextManager",
    "ContextWindow",
    # Subgraphs - Parallel Research
    "ResearchState",
    "create_parallel_research_subgraph",
    "parallel_research_subgraph",
    "run_parallel_research",
]
