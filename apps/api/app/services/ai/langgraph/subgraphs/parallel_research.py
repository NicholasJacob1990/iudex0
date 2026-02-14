"""
Parallel Research Subgraph - Phase 3 Implementation

Este subgraph executa múltiplas buscas em paralelo para coletar contexto:
  - RAG local (documentos do caso/processo)
  - RAG global (templates, biblioteca de peças)
  - Web search (Perplexity)
  - Jurisprudência (base específica)

Flow:
  distribute → [rag_local, rag_global, web_search, jurisprudencia] → merge_results

Features:
  - Fan-out/Fan-in pattern para execução paralela
  - Reranking de resultados por relevância
  - Deduplicação de conteúdo
  - Formatação de contexto final
"""

from typing import TypedDict, List, Dict, Any, Optional, Tuple
from langgraph.graph import StateGraph, END
from loguru import logger
import asyncio
import hashlib
import time
import os
import re

from app.services.api_call_tracker import billing_context


# =============================================================================
# STATE DEFINITION
# =============================================================================

class ResearchState(TypedDict):
    """State for the parallel research subgraph."""

    # Input
    query: str                          # Main query for research
    section_title: Optional[str]        # Optional section title for context
    thesis: Optional[str]               # Optional thesis/argument
    input_text: Optional[str]           # Original input text/case description

    # Configuration
    job_id: Optional[str]               # Job ID for SSE events
    tenant_id: Optional[str]            # Tenant ID for RAG scoping
    processo_id: Optional[str]          # Process ID for case-specific RAG
    top_k: int                          # Number of results per source (default: 5)
    max_context_chars: int              # Max chars in final context (default: 12000)

    # Source-specific queries (can be customized)
    query_rag_local: Optional[str]
    query_rag_global: Optional[str]
    query_web: Optional[str]
    query_juris: Optional[str]

    # Intermediate results
    results_rag_local: List[Dict[str, Any]]
    results_rag_global: List[Dict[str, Any]]
    results_web: List[Dict[str, Any]]
    results_juris: List[Dict[str, Any]]
    results_agent_parallel: List[Dict[str, Any]]

    # Output
    merged_context: str                 # Final formatted context
    citations_map: Dict[str, Dict[str, Any]]  # Map of citations for reference
    sources_used: List[str]             # List of sources that returned results

    # Metrics
    metrics: Dict[str, Any]


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _get_rag_manager():
    """Get or create RAG manager instance."""
    try:
        from app.services.rag_module_old import create_rag_manager
        return create_rag_manager()
    except Exception as e:
        logger.warning(f"RAGManager unavailable: {e}")
        return None


def _get_web_search_service():
    """Get web search service instance."""
    try:
        from app.services.web_search_service import web_search_service
        return web_search_service
    except Exception as e:
        logger.warning(f"WebSearchService unavailable: {e}")
        return None


def _get_jurisprudence_service():
    """Get jurisprudence service instance."""
    try:
        from app.services.jurisprudence_service import JurisprudenceService
        return JurisprudenceService()
    except Exception as e:
        logger.warning(f"JurisprudenceService unavailable: {e}")
        return None


def _get_deep_research_service():
    """Get deep research service for advanced web search."""
    try:
        from app.services.ai.deep_research_service import deep_research_service
        return deep_research_service
    except Exception as e:
        logger.debug(f"DeepResearchService unavailable: {e}")
        return None


def _emit_event(job_id: Optional[str], event_type: str, data: Dict[str, Any]) -> None:
    """Emit SSE event if job_id is provided."""
    if not job_id:
        return
    try:
        from app.services.job_manager import job_manager
        job_manager.emit_event(
            job_id,
            event_type,
            data,
            phase="research",
        )
    except Exception as e:
        logger.debug(f"Failed to emit event: {e}")


def _hash_content(text: str) -> str:
    """Generate hash for content deduplication."""
    return hashlib.md5(text.encode("utf-8")).hexdigest()[:12]


def _normalize_text(text: str) -> str:
    """Normalize text for comparison."""
    text = re.sub(r"\s+", " ", text.lower().strip())
    return text[:500]  # Compare first 500 chars


def _is_duplicate(text: str, seen_hashes: set, seen_normalized: set) -> bool:
    """Check if content is duplicate."""
    content_hash = _hash_content(text)
    normalized = _normalize_text(text)

    if content_hash in seen_hashes:
        return True
    if normalized in seen_normalized:
        return True

    seen_hashes.add(content_hash)
    seen_normalized.add(normalized)
    return False


def _score_result(result: Dict[str, Any], query: str) -> float:
    """Calculate relevance score for a result."""
    base_score = float(result.get("score", 0.0))

    # Boost for exact query term matches
    text = (result.get("text", "") or result.get("snippet", "")).lower()
    query_terms = query.lower().split()

    term_matches = sum(1 for term in query_terms if term in text and len(term) > 3)
    term_boost = term_matches * 0.1

    # Boost for source type
    source = result.get("source_type", "")
    source_boosts = {
        "lei": 0.15,
        "juris": 0.12,
        "sei": 0.10,
        "web": 0.05,
        "pecas_modelo": 0.08,
    }
    source_boost = source_boosts.get(source, 0.0)

    # Boost for recent content
    recency_boost = 0.0
    if result.get("date"):
        try:
            from datetime import datetime
            date_str = str(result.get("date", ""))
            if "2024" in date_str or "2025" in date_str or "2026" in date_str:
                recency_boost = 0.05
        except Exception:
            pass

    return base_score + term_boost + source_boost + recency_boost


# =============================================================================
# DISTRIBUTE NODE
# =============================================================================

async def distribute_query(state: ResearchState) -> ResearchState:
    """
    Distribute the main query into source-specific queries.
    Optionally customizes queries based on source characteristics.
    """
    logger.info(f"[Research] Distributing query: '{state['query'][:100]}...'")
    start_time = time.time()

    _emit_event(state.get("job_id"), "research_stage", {"stage": "distribute"})

    main_query = state["query"]
    section = state.get("section_title", "")
    thesis = state.get("thesis", "")

    # Build context-aware queries
    base_query = main_query
    if section and section not in main_query:
        base_query = f"{section}: {main_query}"

    # RAG local: focus on case-specific terms
    query_local = base_query
    if state.get("processo_id"):
        query_local = f"Processo {state['processo_id']}: {base_query}"

    # RAG global: focus on legal templates and patterns
    query_global = base_query
    if thesis:
        query_global = f"{thesis}. {base_query}"

    # Web search: optimize for search engines
    query_web = main_query
    # Add legal context for better web results
    legal_context = ["jurisprudência", "Brasil", "lei", "STF", "STJ"]
    if not any(term in query_web.lower() for term in legal_context):
        query_web = f"{query_web} jurisprudência Brasil"

    # Jurisprudence: extract key legal terms
    query_juris = main_query

    latency = int((time.time() - start_time) * 1000)
    logger.info(f"[Research] Queries distributed in {latency}ms")

    return {
        **state,
        "query_rag_local": state.get("query_rag_local") or query_local,
        "query_rag_global": state.get("query_rag_global") or query_global,
        "query_web": state.get("query_web") or query_web,
        "query_juris": state.get("query_juris") or query_juris,
        "metrics": {
            **state.get("metrics", {}),
            "distribute_latency_ms": latency,
        }
    }


# =============================================================================
# SEARCH NODES
# =============================================================================

async def search_rag_local(state: ResearchState) -> ResearchState:
    """
    Search local RAG (case documents, SEI, process-specific content).
    """
    logger.info("[Research] Starting RAG local search")
    start_time = time.time()

    _emit_event(state.get("job_id"), "research_stage", {
        "stage": "search",
        "source": "rag_local",
    })

    results = []
    error = None

    try:
        rag_manager = _get_rag_manager()
        if rag_manager:
            query = state.get("query_rag_local") or state["query"]
            top_k = state.get("top_k", 5)
            tenant_id = state.get("tenant_id", "default")

            # Search in local collections (sei, case documents)
            with billing_context(node="research_rag_local", size="S"):
                raw_results = rag_manager.hybrid_search(
                    query=query,
                    sources=["sei"],  # Local case documents
                    top_k=top_k,
                    tenant_id=tenant_id,
                    include_global=False,
                )

            for r in raw_results:
                results.append({
                    "text": r.get("text", ""),
                    "score": r.get("score", 0.0),
                    "source_type": "sei",
                    "metadata": r.get("metadata", {}),
                    "source": "rag_local",
                })

            logger.info(f"[Research] RAG local returned {len(results)} results")
        else:
            logger.warning("[Research] RAG manager unavailable for local search")

    except Exception as e:
        error = str(e)
        logger.error(f"[Research] RAG local search failed: {e}")

    latency = int((time.time() - start_time) * 1000)

    return {
        **state,
        "results_rag_local": results,
        "metrics": {
            **state.get("metrics", {}),
            "rag_local_latency_ms": latency,
            "rag_local_count": len(results),
            "rag_local_error": error,
        }
    }


async def search_rag_global(state: ResearchState) -> ResearchState:
    """
    Search global RAG (templates, jurisprudence, legislation library).
    """
    logger.info("[Research] Starting RAG global search")
    start_time = time.time()

    _emit_event(state.get("job_id"), "research_stage", {
        "stage": "search",
        "source": "rag_global",
    })

    results = []
    error = None

    try:
        rag_manager = _get_rag_manager()
        if rag_manager:
            query = state.get("query_rag_global") or state["query"]
            top_k = state.get("top_k", 5)
            tenant_id = state.get("tenant_id", "default")

            # Search in global collections (lei, juris, pecas_modelo)
            with billing_context(node="research_rag_global", size="S"):
                raw_results = rag_manager.hybrid_search(
                    query=query,
                    sources=["lei", "juris", "pecas_modelo"],
                    top_k=top_k,
                    tenant_id=tenant_id,
                    include_global=True,  # Include global scope
                )

            for r in raw_results:
                source_type = r.get("metadata", {}).get("source_type", "global")
                results.append({
                    "text": r.get("text", ""),
                    "score": r.get("score", 0.0),
                    "source_type": source_type,
                    "metadata": r.get("metadata", {}),
                    "source": "rag_global",
                })

            logger.info(f"[Research] RAG global returned {len(results)} results")
        else:
            logger.warning("[Research] RAG manager unavailable for global search")

    except Exception as e:
        error = str(e)
        logger.error(f"[Research] RAG global search failed: {e}")

    latency = int((time.time() - start_time) * 1000)

    return {
        **state,
        "results_rag_global": results,
        "metrics": {
            **state.get("metrics", {}),
            "rag_global_latency_ms": latency,
            "rag_global_count": len(results),
            "rag_global_error": error,
        }
    }


async def search_web(state: ResearchState) -> ResearchState:
    """
    Search web using Perplexity or similar service.
    """
    logger.info("[Research] Starting web search")
    start_time = time.time()

    _emit_event(state.get("job_id"), "research_stage", {
        "stage": "search",
        "source": "web",
    })

    results = []
    error = None

    try:
        web_service = _get_web_search_service()
        if web_service:
            query = state.get("query_web") or state["query"]
            top_k = state.get("top_k", 5)

            with billing_context(node="research_web", size="M"):
                # Use legal-focused search if available
                try:
                    raw_results = await web_service.search_legal(
                        query=query,
                        num_results=top_k,
                    )
                except AttributeError:
                    # Fallback to regular search
                    raw_results = await web_service.search(
                        query=query,
                        num_results=top_k,
                    )

            for item in raw_results.get("results", []):
                snippet = item.get("snippet", "") or item.get("description", "")
                title = item.get("title", "")
                url = item.get("url", "")

                results.append({
                    "text": f"{title}\n{snippet}",
                    "score": item.get("relevance_score", 0.5),
                    "source_type": "web",
                    "metadata": {
                        "title": title,
                        "url": url,
                        "domain": item.get("domain", ""),
                    },
                    "source": "web",
                    "url": url,
                    "title": title,
                })

            logger.info(f"[Research] Web search returned {len(results)} results")
        else:
            logger.warning("[Research] Web search service unavailable")

    except Exception as e:
        error = str(e)
        logger.error(f"[Research] Web search failed: {e}")

    latency = int((time.time() - start_time) * 1000)

    return {
        **state,
        "results_web": results,
        "metrics": {
            **state.get("metrics", {}),
            "web_latency_ms": latency,
            "web_count": len(results),
            "web_error": error,
        }
    }


async def search_jurisprudencia(state: ResearchState) -> ResearchState:
    """
    Search jurisprudence database for relevant precedents.
    """
    logger.info("[Research] Starting jurisprudence search")
    start_time = time.time()

    _emit_event(state.get("job_id"), "research_stage", {
        "stage": "search",
        "source": "jurisprudencia",
    })

    results = []
    error = None

    try:
        juris_service = _get_jurisprudence_service()
        if juris_service:
            query = state.get("query_juris") or state["query"]
            top_k = state.get("top_k", 5)

            with billing_context(node="research_juris", size="S"):
                raw_results = await juris_service.search(
                    query=query,
                    limit=top_k,
                )

            for item in raw_results.get("items", []):
                title = item.get("title", "")
                summary = item.get("summary", "")
                court = item.get("court", "")

                results.append({
                    "text": f"[{court}] {title}\n{summary}",
                    "score": item.get("relevance_score", 0.5),
                    "source_type": "juris",
                    "metadata": {
                        "court": court,
                        "title": title,
                        "process_number": item.get("processNumber", ""),
                        "date": item.get("date", ""),
                        "relator": item.get("relator", ""),
                        "tema": item.get("tema", ""),
                        "url": item.get("url", ""),
                    },
                    "source": "jurisprudencia",
                })

            logger.info(f"[Research] Jurisprudence search returned {len(results)} results")
        else:
            logger.warning("[Research] Jurisprudence service unavailable")

    except Exception as e:
        error = str(e)
        logger.error(f"[Research] Jurisprudence search failed: {e}")

    latency = int((time.time() - start_time) * 1000)

    return {
        **state,
        "results_juris": results,
        "metrics": {
            **state.get("metrics", {}),
            "juris_latency_ms": latency,
            "juris_count": len(results),
            "juris_error": error,
        }
    }


# =============================================================================
# MERGE NODE
# =============================================================================

async def merge_research_results(state: ResearchState) -> ResearchState:
    """
    Merge results from all sources:
    - Rerank by relevance
    - Deduplicate
    - Format final context
    """
    logger.info("[Research] Merging research results")
    start_time = time.time()

    _emit_event(state.get("job_id"), "research_stage", {"stage": "merge"})

    # Collect all results
    all_results = []
    sources_used = []

    for source_name, results_key in [
        ("rag_local", "results_rag_local"),
        ("rag_global", "results_rag_global"),
        ("web", "results_web"),
        ("jurisprudencia", "results_juris"),
        ("agent_parallel", "results_agent_parallel"),
    ]:
        results = state.get(results_key, [])
        if results:
            sources_used.append(source_name)
            all_results.extend(results)

    logger.info(f"[Research] Total results before dedup: {len(all_results)}")

    # Deduplicate
    seen_hashes = set()
    seen_normalized = set()
    unique_results = []

    for result in all_results:
        text = result.get("text", "")
        if text and not _is_duplicate(text, seen_hashes, seen_normalized):
            unique_results.append(result)

    logger.info(f"[Research] Results after dedup: {len(unique_results)}")

    # Score and rank
    query = state["query"]
    for result in unique_results:
        result["final_score"] = _score_result(result, query)

    # Sort by final score
    ranked_results = sorted(
        unique_results,
        key=lambda x: x.get("final_score", 0),
        reverse=True
    )

    # Build formatted context
    max_chars = state.get("max_context_chars", 12000)
    context_lines = ["## CONTEXTO DA PESQUISA\n"]
    citations_map = {}
    total_chars = len(context_lines[0])
    citation_number = 1

    # Group by source type for better organization
    source_order = ["lei", "juris", "sei", "pecas_modelo", "agent_parallel", "web"]
    source_labels = {
        "lei": "LEGISLACAO",
        "juris": "JURISPRUDENCIA",
        "sei": "DOCUMENTOS DO CASO",
        "pecas_modelo": "MODELOS E TEMPLATES",
        "web": "FONTES WEB",
        "agent_parallel": "ANALISE PARALELA DE AGENTS",
    }

    # Process results by source type
    results_by_source = {}
    for result in ranked_results:
        source_type = result.get("source_type", "other")
        if source_type not in results_by_source:
            results_by_source[source_type] = []
        results_by_source[source_type].append(result)

    for source_type in source_order:
        results = results_by_source.get(source_type, [])
        if not results:
            continue

        label = source_labels.get(source_type, source_type.upper())
        section_header = f"\n### {label}\n"

        if total_chars + len(section_header) > max_chars:
            break

        context_lines.append(section_header)
        total_chars += len(section_header)

        for result in results[:5]:  # Max 5 per source type
            text = result.get("text", "").strip()
            if not text:
                continue

            # Truncate long texts
            if len(text) > 800:
                text = text[:800] + "..."

            metadata = result.get("metadata", {})

            # Build citation entry
            citation_key = str(citation_number)
            citations_map[citation_key] = {
                "title": metadata.get("title", "") or result.get("title", f"Fonte {citation_number}"),
                "url": metadata.get("url", "") or result.get("url", ""),
                "source_type": source_type,
                "court": metadata.get("court", ""),
                "date": metadata.get("date", ""),
            }

            # Format entry
            entry = f"[{citation_number}] {text}\n"

            if total_chars + len(entry) > max_chars:
                break

            context_lines.append(entry)
            total_chars += len(entry)
            citation_number += 1

    merged_context = "".join(context_lines).strip()

    # Handle case with no results
    if not ranked_results:
        merged_context = "## CONTEXTO DA PESQUISA\n\n(Nenhum resultado relevante encontrado nas buscas realizadas.)"

    latency = int((time.time() - start_time) * 1000)
    total_latency = sum([
        state.get("metrics", {}).get("distribute_latency_ms", 0),
        state.get("metrics", {}).get("rag_local_latency_ms", 0),
        state.get("metrics", {}).get("rag_global_latency_ms", 0),
        state.get("metrics", {}).get("web_latency_ms", 0),
        state.get("metrics", {}).get("juris_latency_ms", 0),
        state.get("metrics", {}).get("agent_parallel_latency_ms", 0),
        latency,
    ])

    logger.info(f"[Research] Merge complete in {latency}ms (total: {total_latency}ms)")
    logger.info(f"[Research] Final context: {len(merged_context)} chars, {len(citations_map)} citations")

    _emit_event(state.get("job_id"), "research_complete", {
        "sources_used": sources_used,
        "total_results": len(ranked_results),
        "citations_count": len(citations_map),
        "context_chars": len(merged_context),
    })

    return {
        **state,
        "merged_context": merged_context,
        "citations_map": citations_map,
        "sources_used": sources_used,
        "metrics": {
            **state.get("metrics", {}),
            "merge_latency_ms": latency,
            "total_latency_ms": total_latency,
            "total_results": len(all_results),
            "unique_results": len(unique_results),
            "final_citations": len(citations_map),
        }
    }


# =============================================================================
# PARALLEL EXECUTION WRAPPER
# =============================================================================

def _agent_fanout_enabled() -> bool:
    return os.getenv("IUDEX_PARALLEL_RESEARCH_AGENT_FANOUT", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


async def run_parallel_claude_agents(state: ResearchState) -> List[Dict[str, Any]]:
    """
    Optional sub fan-out using lightweight Claude agents.

    Returns normalized results compatible with merge_research_results.
    """
    try:
        from app.services.ai.langgraph.nodes import ParallelAgentsNode

        prompts = []
        for candidate in [
            state.get("query_rag_local"),
            state.get("query_juris"),
            state.get("query_web"),
            state.get("query"),
        ]:
            text = str(candidate or "").strip()
            if text and text not in prompts:
                prompts.append(text)
        prompts = prompts[:3]
        if not prompts:
            return []

        model = os.getenv("IUDEX_PARALLEL_RESEARCH_AGENT_MODEL", "claude-haiku-4-5")
        max_iterations = int(os.getenv("IUDEX_PARALLEL_RESEARCH_AGENT_MAX_ITERATIONS", "3"))
        max_tokens = int(os.getenv("IUDEX_PARALLEL_RESEARCH_AGENT_MAX_TOKENS", "1200"))
        max_parallel = int(os.getenv("IUDEX_PARALLEL_RESEARCH_AGENT_MAX_PARALLEL", "3"))

        node = ParallelAgentsNode(
            node_id="parallel_research_agents",
            prompt_templates=prompts,
            models=[model for _ in prompts],
            system_prompt=(
                "Voce e um assistente juridico de suporte. Responda de forma curta, "
                "factual e com foco na pergunta."
            ),
            max_iterations=max_iterations,
            max_tokens=max_tokens,
            include_mcp=False,
            tool_names=["search_rag", "search_jurisprudencia", "search_legislacao"],
            use_sdk=False,
            max_parallel=max_parallel,
            aggregation_strategy="json",
        )

        node_state: Dict[str, Any] = {
            "input": state.get("query", ""),
            "output": "",
            "llm_responses": {},
            "variables": {},
            "step_outputs": {},
            "logs": [],
            "user_id": state.get("tenant_id"),
            "case_id": state.get("processo_id"),
        }

        result_state = await node(node_state)
        branch_rows = (
            result_state.get("step_outputs", {})
            .get("parallel_research_agents", {})
            .get("branches", [])
        )
        normalized: List[Dict[str, Any]] = []
        for row in branch_rows:
            if not isinstance(row, dict):
                continue
            output_text = str(row.get("output") or "").strip()
            if not output_text:
                continue
            normalized.append(
                {
                    "text": output_text,
                    "score": 0.55,
                    "source_type": "agent_parallel",
                    "metadata": {
                        "title": row.get("branch_id"),
                        "model": row.get("model"),
                        "error": row.get("error"),
                    },
                }
            )
        return normalized
    except Exception as exc:
        logger.warning(f"[Research] parallel agent fan-out unavailable: {exc}")
        return []


async def parallel_search_node(state: ResearchState) -> ResearchState:
    """
    Execute all search nodes in parallel using asyncio.gather.
    This is used as a single node that internally parallelizes the searches.
    """
    logger.info("[Research] Starting parallel search execution")
    start_time = time.time()

    _emit_event(state.get("job_id"), "research_stage", {"stage": "parallel_search"})

    # Execute all searches in parallel
    tasks = [
        search_rag_local(state),
        search_rag_global(state),
        search_web(state),
        search_jurisprudencia(state),
    ]
    source_names = ["rag_local", "rag_global", "web", "juris"]
    if _agent_fanout_enabled():
        tasks.append(run_parallel_claude_agents(state))
        source_names.append("agent_parallel")

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Merge results from all parallel tasks
    merged_state = dict(state)
    merged_metrics = dict(state.get("metrics", {}))

    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"[Research] {source_names[i]} failed: {result}")
            continue

        if source_names[i] == "agent_parallel" and isinstance(result, list):
            merged_state["results_agent_parallel"] = result
            merged_metrics["agent_parallel_count"] = len(result)
            continue

        if isinstance(result, dict):
            # Merge results
            for key in [
                "results_rag_local",
                "results_rag_global",
                "results_web",
                "results_juris",
            ]:
                if key in result:
                    merged_state[key] = result[key]

            # Merge metrics
            if "metrics" in result:
                merged_metrics.update(result["metrics"])

    merged_state["metrics"] = merged_metrics

    latency = int((time.time() - start_time) * 1000)
    merged_state["metrics"]["parallel_search_latency_ms"] = latency

    logger.info(f"[Research] Parallel search completed in {latency}ms")

    return merged_state


# =============================================================================
# SUBGRAPH DEFINITION
# =============================================================================

def create_parallel_research_subgraph() -> StateGraph:
    """
    Creates the parallel research subgraph.

    Flow:
        distribute → parallel_search → merge_results → END

    Note: LangGraph doesn't natively support fan-out/fan-in for async nodes,
    so we use a single parallel_search_node that internally uses asyncio.gather.
    """

    workflow = StateGraph(ResearchState)

    # Add nodes
    workflow.add_node("distribute", distribute_query)
    workflow.add_node("parallel_search", parallel_search_node)
    workflow.add_node("merge_results", merge_research_results)

    # Define edges
    workflow.set_entry_point("distribute")
    workflow.add_edge("distribute", "parallel_search")
    workflow.add_edge("parallel_search", "merge_results")
    workflow.add_edge("merge_results", END)

    return workflow


# Compiled subgraph
parallel_research_subgraph = create_parallel_research_subgraph().compile()


# =============================================================================
# CONVENIENCE FUNCTION
# =============================================================================

async def run_parallel_research(
    query: str,
    *,
    section_title: Optional[str] = None,
    thesis: Optional[str] = None,
    input_text: Optional[str] = None,
    job_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    processo_id: Optional[str] = None,
    top_k: int = 5,
    max_context_chars: int = 12000,
) -> Dict[str, Any]:
    """
    Convenience function to run the parallel research subgraph.

    Args:
        query: Main query for research
        section_title: Optional section title for context
        thesis: Optional thesis/argument
        input_text: Original input text/case description
        job_id: Job ID for SSE events
        tenant_id: Tenant ID for RAG scoping
        processo_id: Process ID for case-specific RAG
        top_k: Number of results per source (default: 5)
        max_context_chars: Max chars in final context (default: 12000)

    Returns:
        Dictionary with merged_context, citations_map, sources_used, and metrics
    """
    initial_state = ResearchState(
        query=query,
        section_title=section_title,
        thesis=thesis,
        input_text=input_text,
        job_id=job_id,
        tenant_id=tenant_id or "default",
        processo_id=processo_id,
        top_k=top_k,
        max_context_chars=max_context_chars,
        query_rag_local=None,
        query_rag_global=None,
        query_web=None,
        query_juris=None,
        results_rag_local=[],
        results_rag_global=[],
        results_web=[],
        results_juris=[],
        results_agent_parallel=[],
        merged_context="",
        citations_map={},
        sources_used=[],
        metrics={},
    )

    result = await parallel_research_subgraph.ainvoke(initial_state)

    return {
        "merged_context": result.get("merged_context", ""),
        "citations_map": result.get("citations_map", {}),
        "sources_used": result.get("sources_used", []),
        "metrics": result.get("metrics", {}),
    }
