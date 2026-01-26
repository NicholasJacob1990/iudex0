import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "apps", "api"))


@pytest.mark.asyncio
async def test_pipeline_adapter_maps_doutrina_to_indices_and_collections(monkeypatch):
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

    called = {}

    async def fake_search(self, **kwargs):
        called.update(kwargs)

        class Result:
            results = [{"text": "doc", "source_type": "doutrina", "final_score": 0.9}]
            graph_context = None

        return Result()

    monkeypatch.setattr(rag_pipeline.RAGPipeline, "search", fake_search)

    await pipeline_adapter.build_rag_context_unified(
        query="q",
        rag_sources=["doutrina"],
        rag_top_k=5,
        adaptive_routing=False,
        crag_gate=False,
        crag_min_best_score=0.45,
        crag_min_avg_score=0.35,
        hyde_enabled=False,
        multi_query=False,
        graph_rag_enabled=False,
        graph_hops=1,
        argument_graph_enabled=False,
        dense_research=False,
        tenant_id="default",
        user_id=None,
        rewrite_query=False,
    )

    assert called.get("indices") == ["idx_doutrina"]
    assert called.get("collections") == ["col_doutrina"]


def test_agentic_registry_includes_doutrina():
    from app.services.ai.agentic_rag import DatasetRegistry

    names = [d.name for d in DatasetRegistry().list()]
    assert "doutrina" in names


def test_heuristic_sources_can_select_doutrina():
    from app.services.ai.rag_helpers import _heuristic_sources

    sources = ["lei", "juris", "doutrina"]
    selected = _heuristic_sources("O que a doutrina diz sobre boa-fe?", sources)
    assert "doutrina" in selected

