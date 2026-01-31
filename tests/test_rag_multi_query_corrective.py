import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "apps", "api"))


@pytest.mark.asyncio
async def test_multi_query_kb_path(monkeypatch):
    import app.services.rag_context as rag_context

    class DummyRag:
        def __init__(self):
            self.multi_called = False
            self.queries = []
            self.parent_called = False

        def multi_query_search(self, queries, **kwargs):
            self.multi_called = True
            self.queries = queries
            return [{"text": "docA", "metadata": {}, "final_score": 0.9, "source": "lei"}]

        def expand_parent_chunks(self, results, window=1, max_extra=20):
            self.parent_called = True
            return results

        def hybrid_search(self, *args, **kwargs):
            raise AssertionError("hybrid_search should not be called on multi-query path")

        def format_sources_for_prompt(self, results, max_chars=8000):
            return "RAG_CTX"

    dummy = DummyRag()
    monkeypatch.setattr(rag_context, "get_rag_manager", lambda: dummy)
    monkeypatch.setattr(rag_context, "get_scoped_knowledge_graph", lambda scope, scope_id=None: None)

    async def fake_generate_multi_queries(*args, **kwargs):
        return ["q1", "q2"]

    monkeypatch.setattr(rag_context, "generate_multi_queries", fake_generate_multi_queries)

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
        multi_query=True,
        multi_query_max=2,
        parent_child_enabled=True,
        graph_rag_enabled=False,
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

    assert dummy.multi_called is True
    assert dummy.queries == ["q1", "q2"]
    assert dummy.parent_called is True
    assert "docA" in rag_ctx
    assert graph_ctx == ""
    assert results and results[0]["text"] == "docA"


@pytest.mark.asyncio
async def test_corrective_fallback_uses_multi_query(monkeypatch):
    import app.services.rag_context as rag_context

    class DummyRag:
        def __init__(self):
            self.hybrid_calls = 0
            self.multi_calls = 0
            self.parent_called = False

        def hybrid_search(self, *args, **kwargs):
            self.hybrid_calls += 1
            return [{"text": "low", "metadata": {}, "final_score": 0.05, "source": "lei"}]

        def multi_query_search(self, queries, **kwargs):
            self.multi_calls += 1
            if self.multi_calls == 1:
                return [{"text": "low", "metadata": {}, "final_score": 0.05, "source": "lei"}]
            return [{"text": "good", "metadata": {}, "final_score": 0.9, "source": "lei"}]

        def expand_parent_chunks(self, results, window=1, max_extra=20):
            self.parent_called = True
            return results

        def format_sources_for_prompt(self, results, max_chars=8000):
            return "RAG_CTX"

    dummy = DummyRag()
    monkeypatch.setattr(rag_context, "get_rag_manager", lambda: dummy)
    monkeypatch.setattr(rag_context, "get_scoped_knowledge_graph", lambda scope, scope_id=None: None)

    async def fake_generate_multi_queries(*args, **kwargs):
        return ["q1", "q2"]

    monkeypatch.setattr(rag_context, "generate_multi_queries", fake_generate_multi_queries)

    rag_ctx, graph_ctx, results = await rag_context.build_rag_context(
        query="Tema controverso",
        rag_sources=["lei"],
        rag_top_k=5,
        attachment_mode="prompt_injection",
        adaptive_routing=False,
        crag_gate=True,
        crag_min_best_score=0.8,
        crag_min_avg_score=0.8,
        hyde_enabled=False,
        multi_query=True,
        multi_query_max=2,
        corrective_rag=True,
        corrective_use_hyde=False,
        corrective_min_best_score=0.2,
        corrective_min_avg_score=0.2,
        parent_child_enabled=True,
        graph_rag_enabled=False,
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

    assert dummy.hybrid_calls >= 1
    assert dummy.multi_calls == 2
    assert dummy.parent_called is True
    assert "good" in rag_ctx
    assert graph_ctx == ""
    assert results and results[0]["text"] == "good"
