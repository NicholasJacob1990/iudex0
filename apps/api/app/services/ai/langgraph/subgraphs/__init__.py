"""
LangGraph Subgraphs Module

This module contains reusable subgraphs for the legal workflow:
- parallel_research: Parallel research across multiple sources
"""

from .parallel_research import (
    # State
    ResearchState,
    # Subgraph
    create_parallel_research_subgraph,
    parallel_research_subgraph,
    # Nodes (for testing/customization)
    distribute_query,
    search_rag_local,
    search_rag_global,
    search_web,
    search_jurisprudencia,
    run_parallel_claude_agents,
    merge_research_results,
    parallel_search_node,
    # Convenience function
    run_parallel_research,
)

__all__ = [
    # State
    "ResearchState",
    # Subgraph
    "create_parallel_research_subgraph",
    "parallel_research_subgraph",
    # Nodes
    "distribute_query",
    "search_rag_local",
    "search_rag_global",
    "search_web",
    "search_jurisprudencia",
    "run_parallel_claude_agents",
    "merge_research_results",
    "parallel_search_node",
    # Convenience function
    "run_parallel_research",
]
