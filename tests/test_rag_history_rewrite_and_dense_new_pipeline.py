import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "apps", "api"))


@pytest.mark.asyncio
async def test_history_rewrite_applies_to_new_pipeline(monkeypatch):
    import app.services.rag.pipeline_adapter as pipeline_adapter
    import app.services.rag.config as rag_config
    import app.services.rag.pipeline.rag_pipeline as rag_pipeline
    import app.services.ai.rag_helpers as rag_helpers

    monkeypatch.setattr(pipeline_adapter, "_USE_NEW_PIPELINE", True)

    async def fail_legacy(*args, **kwargs):
        raise AssertionError("legacy pipeline should not be used")

    monkeypatch.setattr(pipeline_adapter, "_call_legacy_pipeline", fail_legacy)

    class DummyCfg:
        opensearch_index_lei = "idx_lei"
        opensearch_index_juris = "idx_juris"
        opensearch_index_pecas = "idx_pecas"
        opensearch_index_doutrina = "idx_doutrina"
        opensearch_index_sei = "idx_sei"
        opensearch_index_local = "idx_local"
        qdrant_collection_lei = "col_lei"
        qdrant_collection_juris = "col_juris"
        qdrant_collection_pecas = "col_pecas"
        qdrant_collection_doutrina = "col_doutrina"
        qdrant_collection_sei = "col_sei"
        qdrant_collection_local = "col_local"

    monkeypatch.setattr(rag_config, "get_rag_config", lambda: DummyCfg())

    async def fake_rewrite_query_with_history(*, query, history, summary_text=None):
        assert history
        return "consulta_reescrita"

    monkeypatch.setattr(rag_helpers, "rewrite_query_with_history", fake_rewrite_query_with_history)

    called = {}

    async def fake_search(self, *, query, indices, collections, top_k=None, **kwargs):
        called["query"] = query
        called["top_k"] = top_k
        called["indices"] = indices
        called["collections"] = collections

        class Result:
            results = [{"text": "doc", "source_type": "lei", "final_score": 0.9}]
            graph_context = None

        return Result()

    monkeypatch.setattr(rag_pipeline.RAGPipeline, "search", fake_search)

    rag_ctx, graph_ctx, results = await pipeline_adapter.build_rag_context_unified(
        query="original",
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
        parent_child_enabled=False,
        graph_rag_enabled=False,
        graph_hops=2,
        argument_graph_enabled=False,
        dense_research=False,
        tenant_id="default",
        user_id=None,
        history=[{"role": "user", "content": "oi"}],
        summary_text=None,
        conversation_id=None,
        rewrite_query=True,
    )

    assert called["query"] == "consulta_reescrita"
    assert called["indices"] == ["idx_lei"]
    assert called["collections"] == ["col_lei"]
    assert rag_ctx
    assert graph_ctx == ""
    assert results and results[0]["text"] == "doc"


@pytest.mark.asyncio
async def test_dense_research_increases_top_k_in_new_pipeline(monkeypatch):
    import app.services.rag.pipeline_adapter as pipeline_adapter
    import app.services.rag.config as rag_config
    import app.services.rag.pipeline.rag_pipeline as rag_pipeline

    monkeypatch.setattr(pipeline_adapter, "_USE_NEW_PIPELINE", True)

    class DummyCfg:
        opensearch_index_lei = "idx_lei"
        opensearch_index_juris = "idx_juris"
        opensearch_index_pecas = "idx_pecas"
        opensearch_index_doutrina = "idx_doutrina"
        opensearch_index_sei = "idx_sei"
        opensearch_index_local = "idx_local"
        qdrant_collection_lei = "col_lei"
        qdrant_collection_juris = "col_juris"
        qdrant_collection_pecas = "col_pecas"
        qdrant_collection_doutrina = "col_doutrina"
        qdrant_collection_sei = "col_sei"
        qdrant_collection_local = "col_local"

    monkeypatch.setattr(rag_config, "get_rag_config", lambda: DummyCfg())

    called = {}

    async def fake_search(self, *, top_k=None, **kwargs):
        called["top_k"] = top_k

        class Result:
            results = [{"text": "doc", "source_type": "lei", "final_score": 0.9}]
            graph_context = None

        return Result()

    monkeypatch.setattr(rag_pipeline.RAGPipeline, "search", fake_search)

    await pipeline_adapter.build_rag_context_unified(
        query="q",
        rag_sources=["lei"],
        rag_top_k=5,
        adaptive_routing=False,
        crag_gate=False,
        crag_min_best_score=0.45,
        crag_min_avg_score=0.35,
        hyde_enabled=False,
        multi_query=False,
        compression_enabled=False,
        parent_child_enabled=False,
        graph_rag_enabled=False,
        graph_hops=1,
        argument_graph_enabled=False,
        dense_research=True,
        tenant_id="default",
        user_id=None,
        rewrite_query=False,
    )

    assert called["top_k"] >= 12
