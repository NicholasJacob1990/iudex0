"""
Integration tests for CogGRAG in the RAG pipeline.

Tests the integration between:
- RAGPipeline._cograg_pipeline()
- CogGRAG StateGraph (cognitive_rag.py)
- PipelineStage enum
- RAGConfig cograg_* settings
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from app.services.rag.config import RAGConfig
from app.services.rag.pipeline.rag_pipeline import PipelineStage


class TestPipelineStageEnum:
    """Test that CogGRAG stages are in the enum."""

    def test_cograg_stages_exist(self):
        assert hasattr(PipelineStage, "COGRAG_DECOMPOSE")
        assert hasattr(PipelineStage, "COGRAG_RETRIEVAL")
        assert hasattr(PipelineStage, "COGRAG_REFINE")
        assert hasattr(PipelineStage, "COGRAG_VERIFY")

    def test_cograg_stage_values(self):
        assert PipelineStage.COGRAG_DECOMPOSE.value == "cograg_decompose"
        assert PipelineStage.COGRAG_RETRIEVAL.value == "cograg_retrieval"
        assert PipelineStage.COGRAG_REFINE.value == "cograg_refine"
        assert PipelineStage.COGRAG_VERIFY.value == "cograg_verify"


class TestRAGConfigCogGRAG:
    """Test RAGConfig CogGRAG settings."""

    def test_default_cograg_disabled(self):
        config = RAGConfig()
        assert config.enable_cograg is False

    def test_cograg_settings_defaults(self):
        config = RAGConfig()
        assert config.cograg_max_depth == 3
        assert config.cograg_max_children == 4
        assert config.cograg_decomposer_model == "gemini-2.0-flash"
        assert config.cograg_similarity_threshold == 0.7
        assert config.cograg_complexity_threshold == 0.5

    def test_cograg_phase25_defaults(self):
        config = RAGConfig()
        assert config.cograg_theme_retrieval_enabled is False
        assert config.cograg_evidence_refinement_enabled is False
        assert config.cograg_memory_enabled is False
        assert config.cograg_abstain_mode is True

    def test_cograg_phase3_defaults(self):
        config = RAGConfig()
        assert config.cograg_verification_enabled is False
        assert config.cograg_verification_model == "gemini-2.0-flash"
        assert config.cograg_max_rethink_attempts == 2
        assert config.cograg_hallucination_loop is False


class TestCogGRAGImport:
    """Test CogGRAG module imports work correctly."""

    def test_import_run_cognitive_rag(self):
        from app.services.ai.langgraph.subgraphs.cognitive_rag import run_cognitive_rag
        assert run_cognitive_rag is not None
        assert callable(run_cognitive_rag)

    def test_import_cognitive_rag_state(self):
        from app.services.ai.langgraph.subgraphs.cognitive_rag import CognitiveRAGState
        assert CognitiveRAGState is not None

    def test_import_is_complex_query(self):
        from app.services.rag.core.cograg.nodes.planner import is_complex_query
        assert is_complex_query is not None
        assert callable(is_complex_query)

    def test_import_in_pipeline(self):
        """Test that the pipeline imports CogGRAG correctly."""
        from app.services.rag.pipeline import rag_pipeline
        # These should be available (not None) if imports succeeded
        assert hasattr(rag_pipeline, "run_cognitive_rag")
        assert hasattr(rag_pipeline, "cograg_is_complex")


class TestCogGRAGComplexityDetection:
    """Test complexity detection for CogGRAG routing."""

    def test_simple_query_not_routed(self):
        from app.services.rag.core.cograg.nodes.planner import is_complex_query

        simple_queries = [
            "Art. 5 CF",
            "sumula 331 TST",
            "o que é usucapião?",
            "qual é o prazo?",
        ]
        for q in simple_queries:
            assert is_complex_query(q) is False, f"Expected simple: {q}"

    def test_complex_query_routed(self):
        from app.services.rag.core.cograg.nodes.planner import is_complex_query

        complex_queries = [
            # Multiple conjunctions or > 12 words
            "Quais os requisitos para rescisão indireta e quais as verbas rescisórias devidas ao trabalhador?",  # > 12 words
            "Compare responsabilidade objetiva e subjetiva no CDC",  # has "compare"
            "Nulidade de contrato de trabalho com ente público sem concurso e direito ao FGTS conforme jurisprudência",  # > 12 words
        ]
        for q in complex_queries:
            assert is_complex_query(q) is True, f"Expected complex: {q}"


class TestCogGRAGPipelineMethod:
    """Test _cograg_pipeline method behavior."""

    @pytest.mark.asyncio
    async def test_cograg_pipeline_fallback_when_disabled(self):
        """When run_cognitive_rag is None, should return fallback=True."""
        from app.services.rag.pipeline.rag_pipeline import RAGPipeline, PipelineTrace

        pipeline = RAGPipeline()
        trace = PipelineTrace(original_query="test query")

        # Mock run_cognitive_rag as None (import failed)
        with patch("app.services.rag.pipeline.rag_pipeline.run_cognitive_rag", None):
            result = await pipeline._cograg_pipeline(
                query="test query",
                trace=trace,
                tenant_id="default",
                scope="global",
                case_id=None,
                indices=["test-index"],
                collections=["test-collection"],
                filters=None,
                top_k=10,
            )

        assert result["fallback"] is True
        assert result["results"] == []

    @pytest.mark.asyncio
    async def test_cograg_pipeline_simple_query_fallback(self):
        """Simple query (≤1 sub-question) should fallback to normal pipeline."""
        from app.services.rag.pipeline.rag_pipeline import RAGPipeline, PipelineTrace

        pipeline = RAGPipeline()
        trace = PipelineTrace(original_query="Art. 5 CF")

        # Mock run_cognitive_rag to return simple result
        mock_result = {
            "sub_questions": [{"node_id": "1", "question": "Art. 5 CF", "level": 0}],
            "evidence_map": {},
            "text_chunks": [],
            "mind_map": {},
            "metrics": {},
        }

        with patch(
            "app.services.rag.pipeline.rag_pipeline.run_cognitive_rag",
            new=AsyncMock(return_value=mock_result),
        ):
            result = await pipeline._cograg_pipeline(
                query="Art. 5 CF",
                trace=trace,
                tenant_id="default",
                scope="global",
                case_id=None,
                indices=["test"],
                collections=["test"],
                filters=None,
                top_k=10,
            )

        assert result["fallback"] is True

    @pytest.mark.asyncio
    async def test_cograg_pipeline_complex_query_processes(self):
        """Complex query with multiple sub-questions should be processed."""
        from app.services.rag.pipeline.rag_pipeline import RAGPipeline, PipelineTrace

        pipeline = RAGPipeline()
        trace = PipelineTrace(original_query="Complex query")

        # Mock run_cognitive_rag to return complex result
        mock_result = {
            "sub_questions": [
                {"node_id": "1", "question": "Sub Q1?", "level": 1},
                {"node_id": "2", "question": "Sub Q2?", "level": 1},
                {"node_id": "3", "question": "Sub Q3?", "level": 1},
            ],
            "evidence_map": {
                "1": {"local_results": [{"text": "Evidence 1", "score": 0.9}]},
                "2": {"local_results": [{"text": "Evidence 2", "score": 0.8}]},
            },
            "text_chunks": [
                {"text": "Chunk 1", "score": 0.9, "_content_hash": "h1"},
                {"text": "Chunk 2", "score": 0.8, "_content_hash": "h2"},
            ],
            "mind_map": {"root_question": "Complex query"},
            "metrics": {"cograg_total_latency_ms": 150},
        }

        with patch(
            "app.services.rag.pipeline.rag_pipeline.run_cognitive_rag",
            new=AsyncMock(return_value=mock_result),
        ):
            result = await pipeline._cograg_pipeline(
                query="Complex query",
                trace=trace,
                tenant_id="default",
                scope="global",
                case_id=None,
                indices=["test"],
                collections=["test"],
                filters=None,
                top_k=10,
            )

        assert result["fallback"] is False
        assert len(result["results"]) == 2
        assert result["sub_questions"] == mock_result["sub_questions"]
        assert result["mind_map"] == mock_result["mind_map"]
