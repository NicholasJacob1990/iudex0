"""
Compatibility shim (DEPRECATED) - re-exports from rag_module_old.

PREFERRED IMPORT:
    from app.services.rag_module_old import RAGManager, create_rag_manager, get_scoped_knowledge_graph

This file was recreated to fix missing module imports and maintain backward compatibility.
New code should import directly from rag_module_old.
"""

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
