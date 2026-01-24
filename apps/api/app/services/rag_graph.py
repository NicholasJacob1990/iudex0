"""
GraphRAG adapter for the API package.

The project already has a canonical GraphRAG implementation at repo root: `rag_graph.py`.
The API code (and its tests) import it as `app.services.rag_graph`, so this module bridges
the two worlds by loading the root implementation and re-exporting its public symbols.

This avoids copying ~900 lines of graph logic into the API tree while still enabling:
- GraphRAG ingestion/enrichment in `apps/api/app/services/rag_module.py`
- GraphRAG context expansion in `apps/api/app/services/rag_context.py`
- ArgumentRAG integration via `apps/api/app/services/argument_pack.py`
"""

from __future__ import annotations

import importlib.util
import os
import pathlib
from functools import lru_cache
from types import ModuleType
from typing import Optional


def _root_rag_graph_path() -> pathlib.Path:
    this_file = pathlib.Path(__file__).resolve()
    for parent in this_file.parents:
        candidate = (parent / "rag_graph.py").resolve()
        if candidate.is_file() and candidate != this_file:
            return candidate
    raise FileNotFoundError("Could not locate repo-root `rag_graph.py` to load GraphRAG.")


@lru_cache(maxsize=1)
def _load_root_module() -> ModuleType:
    module_path = _root_rag_graph_path()
    spec = importlib.util.spec_from_file_location("_iudex_root_rag_graph", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load GraphRAG module spec from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_root = _load_root_module()

# Re-export enums and helpers
EntityType = _root.EntityType
RelationType = _root.RelationType
GraphSchema = _root.GraphSchema
BaseGraphPack = _root.BaseGraphPack
GenericPack = _root.GenericPack

# Re-export core graph classes
Entity = _root.Entity
Relation = _root.Relation
LegalEntity = getattr(_root, "LegalEntity", _root.Entity)
LegalRelation = getattr(_root, "LegalRelation", _root.Relation)


class KnowledgeGraph(_root.KnowledgeGraph):
    """API-scoped alias that keeps default persistence under `app/services/graph_db/`."""

    DEFAULT_PERSIST_PATH = os.path.join(
        os.path.dirname(__file__),
        "graph_db",
        "knowledge_graph.json",
    )


class LegalKnowledgeGraph(_root.LegalKnowledgeGraph):
    """API-scoped alias that keeps default persistence under `app/services/graph_db/`."""

    DEFAULT_PERSIST_PATH = os.path.join(
        os.path.dirname(__file__),
        "graph_db",
        "legal_knowledge_graph.json",
    )


LegalEntityExtractor = _root.LegalEntityExtractor


def create_knowledge_graph(
    persist_path: Optional[str] = None,
    pack: Optional[BaseGraphPack] = None,
) -> "KnowledgeGraph | LegalKnowledgeGraph":
    if pack is not None:
        return KnowledgeGraph(persist_path=persist_path, pack=pack)
    return LegalKnowledgeGraph(persist_path=persist_path)


@lru_cache(maxsize=1)
def get_knowledge_graph() -> LegalKnowledgeGraph:
    return LegalKnowledgeGraph()


__all__ = [
    "BaseGraphPack",
    "Entity",
    "EntityType",
    "GenericPack",
    "GraphSchema",
    "KnowledgeGraph",
    "LegalEntity",
    "LegalEntityExtractor",
    "LegalKnowledgeGraph",
    "LegalRelation",
    "Relation",
    "RelationType",
    "create_knowledge_graph",
    "get_knowledge_graph",
]
