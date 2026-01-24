# Compatibility shim - re-exports from rag_module_old
# This file was recreated to fix missing module imports

from app.services.rag_module_old import (
    RAGManager,
    PecaModeloMetadata,
    create_rag_manager,
    get_scoped_knowledge_graph,
)

__all__ = [
    "RAGManager",
    "PecaModeloMetadata",
    "create_rag_manager",
    "get_scoped_knowledge_graph",
]
