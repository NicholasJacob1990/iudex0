import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "apps", "api"))


@pytest.mark.asyncio
async def test_new_pipeline_uses_legacy_env_defaults_when_callers_do_not_override(monkeypatch):
    import app.core.config as core_config
    import app.services.rag.config as rag_config
    import app.services.rag.pipeline.rag_pipeline as rag_pipeline
    import app.services.rag.pipeline_adapter as pipeline_adapter

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

    # Force non-prod and disable unlock_all so legacy defaults are conservative unless env overrides.
    core_config.settings.ENVIRONMENT = "development"
    monkeypatch.setenv("RAG_UNLOCK_ALL", "false")

    # Ensure "new pipeline" env vars do not take precedence in this test.
    for key in (
        "RAG_ENABLE_MULTIQUERY",
        "RAG_MULTIQUERY_MAX",
        "RAG_ENABLE_COMPRESSION",
        "RAG_COMPRESSION_MAX_CHARS",
        "RAG_ENABLE_CHUNK_EXPANSION",
        "RAG_CHUNK_EXPANSION_WINDOW",
        "RAG_CHUNK_EXPANSION_MAX_EXTRA",
    ):
        monkeypatch.delenv(key, raising=False)

    # Legacy env vars should be applied as defaults when caller passes None.
    monkeypatch.setenv("RAG_MULTI_QUERY_ENABLED", "true")
    monkeypatch.setenv("RAG_MULTI_QUERY_MAX", "4")
    monkeypatch.setenv("RAG_CONTEXT_COMPRESSION_ENABLED", "true")
    monkeypatch.setenv("RAG_CONTEXT_COMPRESSION_MAX_CHARS", "123")
    monkeypatch.setenv("RAG_PARENT_CHILD_ENABLED", "true")
    monkeypatch.setenv("RAG_PARENT_CHILD_WINDOW", "2")
    monkeypatch.setenv("RAG_PARENT_CHILD_MAX_EXTRA", "7")
    monkeypatch.setenv("RAG_CORRECTIVE_ENABLED", "true")
    monkeypatch.setenv("RAG_CORRECTIVE_USE_HYDE", "false")
    monkeypatch.setenv("RAG_CORRECTIVE_MIN_BEST_SCORE", "0.22")
    monkeypatch.setenv("RAG_CORRECTIVE_MIN_AVG_SCORE", "0.11")

    called = {}

    async def fake_search(self, **kwargs):
        called.update(kwargs)

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
        multi_query=None,
        multi_query_max=None,
        compression_enabled=None,
        compression_max_chars=None,
        parent_child_enabled=None,
        parent_child_window=None,
        parent_child_max_extra=None,
        corrective_rag=None,
        corrective_use_hyde=None,
        corrective_min_best_score=None,
        corrective_min_avg_score=None,
        graph_rag_enabled=False,
        graph_hops=1,
        argument_graph_enabled=False,
        dense_research=False,
        tenant_id="default",
        user_id=None,
        rewrite_query=False,
    )

    assert called.get("multi_query") is True
    assert called.get("multi_query_max") == 4
    assert called.get("compression_enabled") is True
    assert called.get("compression_max_chars") == 123
    assert called.get("parent_child_enabled") is True
    assert called.get("parent_child_window") == 2
    assert called.get("parent_child_max_extra") == 7
    assert called.get("corrective_rag") is True
    assert called.get("corrective_use_hyde") is False
    assert called.get("corrective_min_best_score") == 0.22
    assert called.get("corrective_min_avg_score") == 0.11
