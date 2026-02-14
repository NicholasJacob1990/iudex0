from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_run_kg_builder_computes_tenant_pagerank(monkeypatch):
    from app.services.rag.core.kg_builder.pipeline import run_kg_builder

    monkeypatch.setenv("KG_BUILDER_USE_GRAPHRAG", "false")
    monkeypatch.setenv("KG_BUILDER_USE_GLINER", "false")
    monkeypatch.setenv("KG_BUILDER_COMPUTE_PAGERANK", "true")

    mock_gds = MagicMock()
    mock_gds.compute_pagerank.return_value = SimpleNamespace(total_entities=7)

    with patch(
        "app.services.rag.core.kg_builder.pipeline._run_regex_extraction",
        new=AsyncMock(return_value={"chunks_processed": 1, "regex_nodes": 1, "regex_relationships": 0}),
    ), patch(
        "app.services.rag.core.gds_analytics.get_gds_client",
        return_value=mock_gds,
    ):
        stats = await run_kg_builder(
            chunks=[{"text": "art. 5", "chunk_uid": "c1"}],
            doc_hash="doc_1",
            tenant_id="tenant_abc",
            use_llm=False,
            use_resolver=False,
        )

    assert stats["pagerank_entities"] == 7
    mock_gds.compute_pagerank.assert_called_once_with("tenant_abc")
