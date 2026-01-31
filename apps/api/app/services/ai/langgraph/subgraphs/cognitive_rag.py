"""
Cognitive RAG StateGraph — LangGraph orchestrator for CogGRAG pipeline.

Unifies CogGRAG (2503.06567v2), Cog-RAG dual-hypergraph (2511.13201),
and Cognitive RAG patterns into a single StateGraph with:

  planner → theme_activator → dual_retriever → evidence_refiner →
  memory_check → reasoner → verifier → (query_rewriter ↺ | integrator) →
  memory_store → END

Phase 1 implements: planner, theme_activator, dual_retriever.
Phase 2.5 adds: evidence_refiner, memory_check, memory_store.
Phase 3 adds: reasoner, verifier, query_rewriter, integrator.

Feature-flagged: only active when enable_cograg=True in RAGConfig.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, TypedDict

from langgraph.graph import END, StateGraph

logger = logging.getLogger("rag.cograg.graph")


# ═══════════════════════════════════════════════════════════════════════════
# State Definition
# ═══════════════════════════════════════════════════════════════════════════

class CognitiveRAGState(TypedDict, total=False):
    """Centralised state for the Cognitive RAG pipeline."""

    # ── Input ──────────────────────────────────────────────────────────
    query: str
    tenant_id: str
    case_id: Optional[str]
    scope: str
    user_id: Optional[str]
    group_ids: Optional[List[str]]
    indices: Optional[List[str]]
    collections: Optional[List[str]]
    filters: Optional[Dict[str, Any]]

    # ── CogGRAG config (injected at invocation) ───────────────────────
    cograg_max_depth: int
    cograg_max_children: int
    cograg_similarity_threshold: float
    cograg_memory_enabled: bool
    cograg_memory_backend: str
    cograg_memory_similarity_threshold: float
    cograg_verification_enabled: bool
    cograg_abstain_mode: bool
    cograg_abstain_threshold: float
    cograg_hallucination_loop: bool
    cograg_llm_max_concurrency: int

    # ── Phase 1: Decomposition (Planner) ──────────────────────────────
    mind_map: Optional[Dict[str, Any]]
    temas: List[str]
    sub_questions: List[Dict[str, Any]]

    # ── Phase 1: Retrieval ────────────────────────────────────────────
    graph_nodes: List[Dict[str, Any]]
    graph_paths: List[Dict[str, Any]]
    graph_triples: List[Dict[str, Any]]
    text_chunks: List[Dict[str, Any]]
    evidence_map: Dict[str, Any]

    # ── Phase 2.5: Refinement ────────────────────────────────────────
    conflicts: List[Dict[str, Any]]
    refined_evidence: Dict[str, Any]
    similar_consultation: Optional[Dict[str, Any]]

    # ── Phase 3: Reasoning + Verification ────────────────────────────
    sub_answers: List[Dict[str, Any]]
    verification_status: str           # "pending" | "approved" | "rejected" | "abstain"
    verification_issues: List[str]
    rethink_count: int
    max_rethink: int
    requires_new_search: bool

    # ── Phase 3: Integration ─────────────────────────────────────────
    integrated_response: Optional[str]
    citations_used: List[str]
    abstain_info: Optional[Dict[str, Any]]

    # ── Phase 4: Explainability artifact (MindMap paper) ─────────────
    reasoning_graph: Optional[Dict[str, Any]]
    reasoning_graph_mermaid: Optional[str]

    # ── Metadata ──────────────────────────────────────────────────────
    job_id: Optional[str]
    metrics: Dict[str, Any]


# ═══════════════════════════════════════════════════════════════════════════
# Node Imports (lazy, graceful degradation)
# ═══════════════════════════════════════════════════════════════════════════

def _import_planner():
    from app.services.rag.core.cograg.nodes.planner import planner_node
    return planner_node


def _import_theme_activator():
    from app.services.rag.core.cograg.nodes.retriever import theme_activator_node
    return theme_activator_node


def _import_dual_retriever():
    from app.services.rag.core.cograg.nodes.retriever import dual_retriever_node
    return dual_retriever_node


# ── Phase 2.5 Node Imports (lazy, graceful degradation) ──────────────────

def _import_evidence_refiner():
    try:
        from app.services.rag.core.cograg.nodes.evidence_refiner import evidence_refiner_node
        return evidence_refiner_node
    except ImportError:
        return _evidence_refiner_stub


def _import_memory_check():
    try:
        from app.services.rag.core.cograg.nodes.memory import memory_check_node
        return memory_check_node
    except ImportError:
        return _memory_check_stub


def _import_memory_store():
    try:
        from app.services.rag.core.cograg.nodes.memory import memory_store_node
        return memory_store_node
    except ImportError:
        return _memory_store_stub


# ── Phase 3 Node Imports (lazy, graceful degradation) ────────────────────

def _import_reasoner():
    try:
        from app.services.rag.core.cograg.nodes.reasoner import reasoner_node
        return reasoner_node
    except ImportError:
        return _reasoner_stub


def _import_verifier():
    try:
        from app.services.rag.core.cograg.nodes.verifier import verifier_node
        return verifier_node
    except ImportError:
        return _verifier_stub


def _import_query_rewriter():
    try:
        from app.services.rag.core.cograg.nodes.verifier import query_rewriter_node
        return query_rewriter_node
    except ImportError:
        return _query_rewriter_stub


def _import_integrator():
    try:
        from app.services.rag.core.cograg.nodes.integrator import integrator_node
        return integrator_node
    except ImportError:
        return _integrator_stub


def _import_mindmap_explain():
    try:
        from app.services.rag.core.cograg.nodes.mindmap_explain import mindmap_explain_node
        return mindmap_explain_node
    except ImportError:
        return _mindmap_explain_stub


# Phase 2.5 / 3 stubs (fallbacks if imports fail)

async def _evidence_refiner_stub(state: Dict[str, Any]) -> Dict[str, Any]:
    """Stub fallback for evidence refiner."""
    return {
        "refined_evidence": state.get("evidence_map", {}),
        "conflicts": [],
    }


async def _memory_check_stub(state: Dict[str, Any]) -> Dict[str, Any]:
    """Stub fallback for memory check."""
    return {"similar_consultation": None}


async def _reasoner_stub(state: Dict[str, Any]) -> Dict[str, Any]:
    """Stub for Phase 3 reasoner."""
    return {
        "sub_answers": [],
        "verification_status": "approved",
    }


async def _verifier_stub(state: Dict[str, Any]) -> Dict[str, Any]:
    """Stub for Phase 3 verifier."""
    return {
        "verification_status": "approved",
        "verification_issues": [],
        "requires_new_search": False,
    }


async def _query_rewriter_stub(state: Dict[str, Any]) -> Dict[str, Any]:
    """Stub for Phase 3 query rewriter (hallucination loop)."""
    return {"rethink_count": state.get("rethink_count", 0) + 1}


async def _integrator_stub(state: Dict[str, Any]) -> Dict[str, Any]:
    """Stub for Phase 3 integrator."""
    # Build a basic integrated response from evidence
    evidence_map = state.get("evidence_map", {})
    chunk_count = sum(
        len(ev.get("local_results", [])) + len(ev.get("global_results", [])) + len(ev.get("chunk_results", []))
        for ev in evidence_map.values()
    )
    return {
        "integrated_response": None,  # Will be filled by Phase 3 implementation
        "citations_used": [],
        "metrics": {
            **state.get("metrics", {}),
            "integrator_evidence_chunks": chunk_count,
        },
    }


async def _memory_store_stub(state: Dict[str, Any]) -> Dict[str, Any]:
    """Stub fallback for memory store."""
    return {}


async def _mindmap_explain_stub(state: Dict[str, Any]) -> Dict[str, Any]:
    """Stub fallback for MindMap explain node."""
    return {
        "reasoning_graph": None,
        "reasoning_graph_mermaid": None,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Conditional Edge Logic
# ═══════════════════════════════════════════════════════════════════════════

def _verifier_router(state: Dict[str, Any]) -> str:
    """Route after verifier: retry, rewrite, or integrate."""
    status = state.get("verification_status", "approved")
    rethink = state.get("rethink_count", 0)
    max_rethink = state.get("max_rethink", 2)

    if status == "rejected" and rethink < max_rethink:
        if state.get("requires_new_search", False) and state.get("cograg_hallucination_loop", False):
            return "query_rewriter"
        return "reasoner"

    return "integrator"


# ═══════════════════════════════════════════════════════════════════════════
# Graph Builder
# ═══════════════════════════════════════════════════════════════════════════

def build_cognitive_rag_graph() -> StateGraph:
    """
    Build and return the CognitiveRAG StateGraph (not compiled).

    All phases implemented:
    - Phase 1: planner, theme_activator, dual_retriever
    - Phase 2.5: evidence_refiner, memory_check, memory_store
    - Phase 3: reasoner, verifier, query_rewriter, integrator
    """
    graph = StateGraph(CognitiveRAGState)

    # ── Phase 1: Core nodes ───────────────────────────────────────────
    graph.add_node("planner", _import_planner())
    graph.add_node("theme_activator", _import_theme_activator())
    graph.add_node("dual_retriever", _import_dual_retriever())

    # ── Phase 2.5: Refinement nodes ────────────────────────────────────
    graph.add_node("evidence_refiner", _import_evidence_refiner())
    graph.add_node("memory_check", _import_memory_check())
    graph.add_node("memory_store", _import_memory_store())

    # ── Phase 3: Reasoning nodes ─────────────────────────────────────
    graph.add_node("reasoner", _import_reasoner())
    graph.add_node("verifier", _import_verifier())
    graph.add_node("query_rewriter", _import_query_rewriter())
    graph.add_node("integrator", _import_integrator())
    graph.add_node("mindmap_explain", _import_mindmap_explain())

    # ── Edges ─────────────────────────────────────────────────────────
    graph.set_entry_point("planner")
    graph.add_edge("planner", "theme_activator")
    graph.add_edge("theme_activator", "dual_retriever")
    graph.add_edge("dual_retriever", "evidence_refiner")
    graph.add_edge("evidence_refiner", "memory_check")
    graph.add_edge("memory_check", "reasoner")
    graph.add_edge("reasoner", "verifier")

    # Conditional: verifier → reasoner (rethink) | query_rewriter | integrator
    graph.add_conditional_edges(
        "verifier",
        _verifier_router,
        {
            "reasoner": "reasoner",
            "query_rewriter": "query_rewriter",
            "integrator": "integrator",
        },
    )
    graph.add_edge("query_rewriter", "dual_retriever")  # Loop back for new evidence
    graph.add_edge("integrator", "mindmap_explain")
    graph.add_edge("mindmap_explain", "memory_store")
    graph.add_edge("memory_store", END)

    return graph


# Pre-compiled graph for convenience
cognitive_rag_graph = build_cognitive_rag_graph().compile()


# ═══════════════════════════════════════════════════════════════════════════
# Convenience Runner
# ═══════════════════════════════════════════════════════════════════════════

async def run_cognitive_rag(
    query: str,
    *,
    tenant_id: str = "default",
    case_id: Optional[str] = None,
    scope: str = "global",
    user_id: Optional[str] = None,
    group_ids: Optional[List[str]] = None,
    indices: Optional[List[str]] = None,
    collections: Optional[List[str]] = None,
    filters: Optional[Dict[str, Any]] = None,
    job_id: Optional[str] = None,
    max_depth: int = 3,
    max_children: int = 4,
    similarity_threshold: float = 0.7,
    max_rethink: int = 2,
    memory_enabled: bool = False,
    memory_backend: str = "auto",
    memory_similarity_threshold: float = 0.85,
    verification_enabled: bool = False,
    abstain_mode: bool = True,
    abstain_threshold: float = 0.3,
    hallucination_loop: bool = False,
    mindmap_explain_enabled: bool = False,
    audit_mode: bool = False,
    mindmap_explain_format: str = "json",  # json | mermaid | both
    graph_evidence_enabled: bool = True,
    graph_evidence_max_hops: int = 2,
    graph_evidence_limit: int = 10,
    llm_max_concurrency: int = 6,
) -> Dict[str, Any]:
    """
    Run the full CognitiveRAG pipeline.

    Returns dict with: mind_map, evidence_map, text_chunks,
    integrated_response, citations_used, metrics, etc.
    """
    initial_state: CognitiveRAGState = {
        "query": query,
        "tenant_id": tenant_id,
        "case_id": case_id,
        "scope": scope,
        "user_id": user_id,
        "group_ids": group_ids or [],
        "indices": indices,
        "collections": collections,
        "filters": filters,
        "cograg_max_depth": max_depth,
        "cograg_max_children": max_children,
        "cograg_similarity_threshold": similarity_threshold,
        "cograg_memory_enabled": memory_enabled,
        "cograg_memory_backend": memory_backend,
        "cograg_memory_similarity_threshold": memory_similarity_threshold,
        "cograg_verification_enabled": verification_enabled,
        "cograg_abstain_mode": abstain_mode,
        "cograg_abstain_threshold": abstain_threshold,
        "cograg_hallucination_loop": hallucination_loop,
        "cograg_mindmap_explain_enabled": mindmap_explain_enabled,
        "cograg_audit_mode": audit_mode,
        "cograg_mindmap_explain_format": mindmap_explain_format,
        "cograg_graph_evidence_enabled": graph_evidence_enabled,
        "cograg_graph_evidence_max_hops": graph_evidence_max_hops,
        "cograg_graph_evidence_limit": graph_evidence_limit,
        "cograg_llm_max_concurrency": int(llm_max_concurrency) if llm_max_concurrency else 0,
        "mind_map": None,
        "temas": [],
        "sub_questions": [],
        "graph_nodes": [],
        "graph_paths": [],
        "graph_triples": [],
        "text_chunks": [],
        "evidence_map": {},
        "conflicts": [],
        "refined_evidence": {},
        "similar_consultation": None,
        "sub_answers": [],
        "verification_status": "pending",
        "verification_issues": [],
        "rethink_count": 0,
        "max_rethink": max_rethink,
        "requires_new_search": False,
        "integrated_response": None,
        "citations_used": [],
        "abstain_info": None,
        "reasoning_graph": None,
        "reasoning_graph_mermaid": None,
        "job_id": job_id,
        "metrics": {},
    }

    start = time.time()
    result = await cognitive_rag_graph.ainvoke(initial_state)
    total_ms = int((time.time() - start) * 1000)

    result["metrics"] = {
        **result.get("metrics", {}),
        "cograg_total_latency_ms": total_ms,
    }

    try:
        from app.services.rag.core.metrics import get_latency_collector

        get_latency_collector().record("cograg.total", float(total_ms))
    except Exception:
        pass

    logger.info(f"[CogGRAG] Pipeline complete in {total_ms}ms")
    return dict(result)
