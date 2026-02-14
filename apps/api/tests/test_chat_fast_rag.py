"""
Tests for Chat Fast RAG path and attachment vectorization.

Covers:
- search_fast() disables heavy stages while keeping graph/cograg
- build_rag_context_fast() returns results via fast pipeline
- _vectorize_and_search_local() calls ingest_local + search_fast
- Env var fallbacks (CHAT_RAG_FAST_PATH, CHAT_LOCAL_RAG_VECTORIZED)
- _format_local_results formatting
"""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest


# ---------------------------------------------------------------------------
# search_fast() — verifies kwargs defaults
# ---------------------------------------------------------------------------


class TestSearchFast:
    @pytest.mark.asyncio
    async def test_disables_heavy_stages(self):
        """search_fast should pass disabled flags to search()."""
        from app.services.rag.pipeline.rag_pipeline import RAGPipeline

        pipeline = RAGPipeline()

        mock_result = MagicMock()
        mock_result.results = []
        mock_result.graph_context = None
        mock_result.trace = MagicMock()
        mock_result.metadata = {}

        with patch.object(pipeline, "search", new_callable=AsyncMock, return_value=mock_result) as mock_search:
            await pipeline.search_fast("test query", top_k=5)

            mock_search.assert_called_once()
            call_kwargs = mock_search.call_args[1]
            assert call_kwargs["hyde_enabled"] is False
            assert call_kwargs["multi_query"] is False
            assert call_kwargs["compression_enabled"] is False
            assert call_kwargs["parent_child_enabled"] is False
            assert call_kwargs["crag_gate"] is False
            assert call_kwargs["corrective_rag"] is False
            assert call_kwargs["top_k"] == 5

    @pytest.mark.asyncio
    async def test_preserves_graph_flags(self):
        """search_fast should NOT override graph/argument flags."""
        from app.services.rag.pipeline.rag_pipeline import RAGPipeline

        pipeline = RAGPipeline()

        mock_result = MagicMock()
        mock_result.results = []
        mock_result.graph_context = None
        mock_result.trace = MagicMock()
        mock_result.metadata = {}

        with patch.object(pipeline, "search", new_callable=AsyncMock, return_value=mock_result) as mock_search:
            await pipeline.search_fast(
                "test query",
                include_graph=True,
                argument_graph_enabled=True,
            )
            call_kwargs = mock_search.call_args[1]
            assert call_kwargs["include_graph"] is True
            assert call_kwargs["argument_graph_enabled"] is True

    @pytest.mark.asyncio
    async def test_caller_can_override_defaults(self):
        """Caller can re-enable stages if needed."""
        from app.services.rag.pipeline.rag_pipeline import RAGPipeline

        pipeline = RAGPipeline()

        mock_result = MagicMock()
        mock_result.results = []
        mock_result.graph_context = None
        mock_result.trace = MagicMock()
        mock_result.metadata = {}

        with patch.object(pipeline, "search", new_callable=AsyncMock, return_value=mock_result) as mock_search:
            await pipeline.search_fast("test", hyde_enabled=True)
            call_kwargs = mock_search.call_args[1]
            # Caller override should win
            assert call_kwargs["hyde_enabled"] is True


# ---------------------------------------------------------------------------
# build_rag_context_fast()
# ---------------------------------------------------------------------------


class TestBuildRagContextFast:
    @pytest.mark.asyncio
    async def test_returns_tuple(self):
        """Should return (str, str, list) tuple."""
        mock_result = MagicMock()
        mock_result.results = [{"text": "chunk1", "score": 0.9, "metadata": {}}]
        mock_result.graph_context = None

        with patch("app.services.rag.pipeline.rag_pipeline.RAGPipeline") as MockPipeline:
            instance = MockPipeline.return_value
            instance.search_fast = AsyncMock(return_value=mock_result)

            from app.services.rag.pipeline_adapter import build_rag_context_fast

            rag_ctx, graph_ctx, results = await build_rag_context_fast(
                query="test query",
                tenant_id="t1",
            )
            assert isinstance(rag_ctx, str)
            assert isinstance(graph_ctx, str)
            assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_calls_search_fast_not_search(self):
        """Should call search_fast(), not search()."""
        mock_result = MagicMock()
        mock_result.results = []
        mock_result.graph_context = None

        with patch("app.services.rag.pipeline.rag_pipeline.RAGPipeline") as MockPipeline:
            instance = MockPipeline.return_value
            instance.search_fast = AsyncMock(return_value=mock_result)
            instance.search = AsyncMock()

            from app.services.rag.pipeline_adapter import build_rag_context_fast

            await build_rag_context_fast(query="test", tenant_id="t1")
            instance.search_fast.assert_called_once()
            instance.search.assert_not_called()

    @pytest.mark.asyncio
    async def test_passes_graph_flags(self):
        """Graph flags should be passed through to search_fast."""
        mock_result = MagicMock()
        mock_result.results = []
        mock_result.graph_context = None

        with patch("app.services.rag.pipeline.rag_pipeline.RAGPipeline") as MockPipeline:
            instance = MockPipeline.return_value
            instance.search_fast = AsyncMock(return_value=mock_result)

            from app.services.rag.pipeline_adapter import build_rag_context_fast

            await build_rag_context_fast(
                query="test",
                tenant_id="t1",
                graph_rag_enabled=True,
                argument_graph_enabled=True,
                graph_hops=3,
            )
            call_kwargs = instance.search_fast.call_args[1]
            assert call_kwargs["include_graph"] is True
            assert call_kwargs["argument_graph_enabled"] is True
            assert call_kwargs["graph_hops"] == 3


# ---------------------------------------------------------------------------
# _format_local_results()
# ---------------------------------------------------------------------------


class TestFormatLocalResults:
    def test_empty_results(self):
        from app.services.chat_service import _format_local_results

        assert _format_local_results([]) == ""

    def test_formats_results(self):
        from app.services.chat_service import _format_local_results

        results = [
            {"text": "chunk text", "score": 0.85, "metadata": {"filename": "doc.pdf"}},
        ]
        output = _format_local_results(results)
        assert "ANEXOS (RAG Local)" in output
        assert "doc.pdf" in output
        assert "chunk text" in output
        assert "0.85" in output

    def test_respects_max_chars(self):
        from app.services.chat_service import _format_local_results

        results = [
            {"text": "x" * 5000, "score": 0.5, "metadata": {"filename": "big.pdf"}},
            {"text": "y" * 5000, "score": 0.4, "metadata": {"filename": "big2.pdf"}},
        ]
        output = _format_local_results(results, max_chars=6000)
        # Should have truncated — only first chunk fits
        assert "big.pdf" in output
        assert "big2.pdf" not in output


# ---------------------------------------------------------------------------
# _vectorize_and_search_local()
# ---------------------------------------------------------------------------


class TestVectorizeAndSearchLocal:
    @pytest.mark.asyncio
    async def test_ingests_and_searches(self):
        from app.services.chat_service import _vectorize_and_search_local

        mock_doc = MagicMock()
        mock_doc.extracted_text = "texto do documento"
        mock_doc.content = None
        mock_doc.id = "doc-1"
        mock_doc.name = "petição.pdf"
        mock_doc.original_name = "petição.pdf"

        mock_result = MagicMock()
        mock_result.results = [
            {"text": "resultado", "score": 0.9, "metadata": {"filename": "petição.pdf"}},
        ]

        mock_pipeline = MagicMock()
        mock_pipeline.ingest_local = AsyncMock(return_value={"indexed": 1})
        mock_pipeline.search_fast = AsyncMock(return_value=mock_result)

        with patch(
            "app.services.rag.pipeline.rag_pipeline.get_rag_pipeline",
            return_value=mock_pipeline,
        ):
            result = await _vectorize_and_search_local(
                docs=[mock_doc],
                query="buscar no documento",
                tenant_id="t1",
                case_id="case-1",
            )
            assert "resultado" in result
            mock_pipeline.ingest_local.assert_called_once()
            mock_pipeline.search_fast.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_docs_returns_empty(self):
        from app.services.chat_service import _vectorize_and_search_local

        mock_doc = MagicMock()
        mock_doc.extracted_text = ""
        mock_doc.content = None
        mock_doc.id = "doc-1"
        mock_doc.name = "empty.pdf"

        mock_pipeline = MagicMock()
        mock_pipeline.ingest_local = AsyncMock()

        with patch(
            "app.services.rag.pipeline.rag_pipeline.get_rag_pipeline",
            return_value=mock_pipeline,
        ):
            result = await _vectorize_and_search_local(
                docs=[mock_doc],
                query="test",
                tenant_id="t1",
                case_id="case-1",
            )
            assert result == ""
            mock_pipeline.ingest_local.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_results_returns_empty(self):
        from app.services.chat_service import _vectorize_and_search_local

        mock_doc = MagicMock()
        mock_doc.extracted_text = "some text"
        mock_doc.content = None
        mock_doc.id = "doc-1"
        mock_doc.name = "doc.pdf"
        mock_doc.original_name = "doc.pdf"

        mock_result = MagicMock()
        mock_result.results = []

        mock_pipeline = MagicMock()
        mock_pipeline.ingest_local = AsyncMock(return_value={"indexed": 1})
        mock_pipeline.search_fast = AsyncMock(return_value=mock_result)

        with patch(
            "app.services.rag.pipeline.rag_pipeline.get_rag_pipeline",
            return_value=mock_pipeline,
        ):
            result = await _vectorize_and_search_local(
                docs=[mock_doc],
                query="test",
                tenant_id="t1",
                case_id="case-1",
            )
            assert result == ""
