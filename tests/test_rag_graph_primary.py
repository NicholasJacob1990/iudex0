"""
Coverage for GraphRAG primary + vector fallback and RRF ranking.
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "apps", "api"))


@pytest.mark.asyncio
async def test_graphrag_primary_skips_vector(monkeypatch):
    import app.services.rag_context as rag_context
    from app.services.rag.config import reset_rag_config

    monkeypatch.setenv("RAG_NEO4J_ONLY", "false")
    reset_rag_config()

    class DummyGraph:
        def query_context_from_text(self, text, hops=2):
            return ("GRAPH_CTX", ["lei:123"])

        def enrich_context(self, chunks, hops=1):
            raise AssertionError("enrich_context should not run on primary hit")

    monkeypatch.setattr(rag_context, "get_scoped_knowledge_graph", lambda scope, scope_id=None: DummyGraph())
    monkeypatch.setattr(rag_context, "get_rag_manager", lambda: None)

    rag_ctx, graph_ctx, results = await rag_context.build_rag_context(
        query="Lei 8.666/1993",
        rag_sources=[],
        rag_top_k=5,
        attachment_mode="prompt_injection",
        adaptive_routing=False,
        crag_gate=False,
        crag_min_best_score=0.45,
        crag_min_avg_score=0.35,
        hyde_enabled=False,
        graph_rag_enabled=True,
        graph_hops=2,
        argument_graph_enabled=False,
        dense_research=False,
        tenant_id="default",
        user_id=None,
        history=None,
        summary_text=None,
        conversation_id=None,
        rewrite_query=False,
    )

    assert rag_ctx == ""
    assert "GRAPH_CTX" in graph_ctx
    assert "Use apenas como evidencia" in graph_ctx
    assert results == []


@pytest.mark.asyncio
async def test_graphrag_fallback_to_vector(monkeypatch):
    import app.services.rag_context as rag_context
    from app.services.rag.config import reset_rag_config

    monkeypatch.setenv("RAG_NEO4J_ONLY", "false")
    reset_rag_config()

    class DummyGraph:
        def query_context_from_text(self, text, hops=2):
            return ("", [])

        def enrich_context(self, chunks, hops=1):
            return "GRAPH_ENRICH"

    class DummyRag:
        def __init__(self):
            self.called = False

        def hybrid_search(self, *args, **kwargs):
            self.called = True
            return [
                {
                    "text": "docA",
                    "metadata": {"tipo": "lei", "numero": "8666", "ano": 1993},
                    "final_score": 0.9,
                    "source": "lei",
                }
            ]

        def format_sources_for_prompt(self, results, max_chars=8000):
            return "RAG_CTX"

    dummy_rag = DummyRag()
    monkeypatch.setattr(rag_context, "get_scoped_knowledge_graph", lambda scope, scope_id=None: DummyGraph())
    monkeypatch.setattr(rag_context, "get_rag_manager", lambda: dummy_rag)

    rag_ctx, graph_ctx, results = await rag_context.build_rag_context(
        query="Qual a lei aplicavel?",
        rag_sources=["lei"],
        rag_top_k=5,
        attachment_mode="prompt_injection",
        adaptive_routing=False,
        crag_gate=False,
        crag_min_best_score=0.45,
        crag_min_avg_score=0.35,
        hyde_enabled=False,
        graph_rag_enabled=True,
        graph_hops=2,
        argument_graph_enabled=False,
        dense_research=False,
        tenant_id="default",
        user_id=None,
        history=None,
        summary_text=None,
        conversation_id=None,
        rewrite_query=False,
    )

    assert dummy_rag.called is True
    assert "docA" in rag_ctx
    assert "GRAPH_ENRICH" in graph_ctx
    assert results and results[0]["text"] == "docA"


def test_rrf_ranking_prefers_bm25_weight(monkeypatch):
    from app.services.rag_module import RAGManager

    manager = RAGManager.__new__(RAGManager)
    manager.COLLECTIONS = ["lei"]
    manager._collection_prefix_global = "global"
    manager._collection_prefix_group = "group"
    manager._collection_prefix_tenant = "tenant"
    manager._use_tenant_collections = False
    manager._cache_enabled = False
    manager._trace_enabled = False
    manager._result_cache = {}
    manager._audit_log_path = "rag_audit_log.jsonl"
    manager._trace_event = lambda *args, **kwargs: None
    manager._audit_retrieval = lambda *args, **kwargs: None

    def fake_bm25(self, query, source, top_k=20):
        return [("docA", 10.0), ("docB", 5.0)]

    def fake_semantic(self, query, source, top_k=20, where_filter=None):
        return [
            {"text": "docB", "metadata": {"m": 1}, "score": 0.9},
            {"text": "docA", "metadata": {"m": 2}, "score": 0.8},
        ]

    manager._bm25_search = fake_bm25.__get__(manager, RAGManager)
    manager._semantic_search = fake_semantic.__get__(manager, RAGManager)

    results = RAGManager.hybrid_search(
        manager,
        query="q",
        sources=["lei"],
        top_k=2,
        bm25_weight=0.7,
        semantic_weight=0.3,
        rrf_k=60,
        use_rerank=False,
    )

    assert results[0]["text"] == "docA"
