import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "apps", "api"))


@pytest.mark.asyncio
async def test_context_compression_applies(monkeypatch):
    import app.services.rag_context as rag_context

    class DummyRag:
        def __init__(self):
            self.last_results = None

        def hybrid_search(self, *args, **kwargs):
            text = (
                "O contrato foi firmado em 2020. "
                "A clausula terceira define a responsabilidade objetiva. "
                "Houve inadimplemento em 2022 com multa aplicada."
            )
            return [
                {
                    "text": text,
                    "metadata": {"doc_hash": "doc1", "chunk_index": 0},
                    "final_score": 0.9,
                    "source": "lei",
                }
            ]

        def format_sources_for_prompt(self, results, max_chars=8000):
            self.last_results = results
            return "CTX"

    dummy = DummyRag()
    monkeypatch.setattr(rag_context, "get_rag_manager", lambda: dummy)
    monkeypatch.setattr(rag_context, "get_scoped_knowledge_graph", lambda scope, scope_id=None: None)

    rag_ctx, graph_ctx, _ = await rag_context.build_rag_context(
        query="responsabilidade objetiva",
        rag_sources=["lei"],
        rag_top_k=5,
        attachment_mode="prompt_injection",
        adaptive_routing=False,
        crag_gate=False,
        crag_min_best_score=0.45,
        crag_min_avg_score=0.35,
        hyde_enabled=False,
        multi_query=False,
        compression_enabled=True,
        compression_max_chars=60,
        parent_child_enabled=False,
        corrective_rag=False,
        graph_rag_enabled=False,
        graph_hops=2,
        argument_graph_enabled=False,
        dense_research=False,
        tenant_id="default",
        user_id=None,
        history=None,
        summary_text=None,
        conversation_id=None,
        request_id=None,
        rewrite_query=False,
    )

    assert "responsabilidade objetiva" in rag_ctx
    assert graph_ctx == ""
    assert dummy.last_results
    assert len(dummy.last_results[0]["text"]) <= 60
    assert "full_text" in dummy.last_results[0]


@pytest.mark.asyncio
async def test_parent_child_expands_results(monkeypatch):
    import app.services.rag_context as rag_context

    class DummyRag:
        def __init__(self):
            self.expand_called = False
            self.last_results = None

        def hybrid_search(self, *args, **kwargs):
            return [
                {
                    "text": "Chunk base",
                    "metadata": {"doc_hash": "doc1", "chunk_index": 1},
                    "final_score": 0.9,
                    "source": "lei",
                }
            ]

        def expand_parent_chunks(self, results, window=1, max_extra=20):
            self.expand_called = True
            extra = dict(results[0])
            extra["text"] = "Chunk vizinho"
            extra_meta = dict(extra["metadata"])
            extra_meta["chunk_index"] = 0
            extra["metadata"] = extra_meta
            return results + [extra]

        def format_sources_for_prompt(self, results, max_chars=8000):
            self.last_results = results
            return "CTX"

    dummy = DummyRag()
    monkeypatch.setattr(rag_context, "get_rag_manager", lambda: dummy)
    monkeypatch.setattr(rag_context, "get_scoped_knowledge_graph", lambda scope, scope_id=None: None)

    rag_ctx, graph_ctx, _ = await rag_context.build_rag_context(
        query="contrato",
        rag_sources=["lei"],
        rag_top_k=5,
        attachment_mode="prompt_injection",
        adaptive_routing=False,
        crag_gate=False,
        crag_min_best_score=0.45,
        crag_min_avg_score=0.35,
        hyde_enabled=False,
        multi_query=False,
        compression_enabled=False,
        parent_child_enabled=True,
        parent_child_window=1,
        parent_child_max_extra=2,
        corrective_rag=False,
        graph_rag_enabled=False,
        graph_hops=2,
        argument_graph_enabled=False,
        dense_research=False,
        tenant_id="default",
        user_id=None,
        history=None,
        summary_text=None,
        conversation_id=None,
        request_id=None,
        rewrite_query=False,
    )

    assert "Chunk base" in rag_ctx
    assert "Chunk vizinho" in rag_ctx
    assert graph_ctx == ""
    assert dummy.expand_called is True
    assert dummy.last_results is not None
    assert len(dummy.last_results) == 2
