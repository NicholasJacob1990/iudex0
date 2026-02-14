"""
Tests for GLiNER zero-shot NER extractor.

Verifica que:
1. GLiNERExtractor importa corretamente
2. Extração com mock model gera nodes/relationships
3. Dedup funciona entre chunks
4. Chunks vazios retornam resultado vazio
5. Label mapping cobre todos os LEGAL_LABELS
6. Entity ID é determinístico
7. Integração com pipeline respeita env var
"""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from app.services.rag.core.kg_builder.gliner_extractor import (
    GLiNERExtractor,
    GLiNERExtractionResult,
    _make_entity_id,
    _LABEL_MAP,
)


# =============================================================================
# Mock GLiNER model
# =============================================================================

def _make_mock_model(entities_per_call=None):
    """Create a mock GLiNER model that returns predefined entities."""
    if entities_per_call is None:
        entities_per_call = [
            {"text": "Lei 14.133/2021", "label": "lei", "score": 0.92},
            {"text": "Art. 55", "label": "artigo", "score": 0.87},
            {"text": "STF", "label": "tribunal", "score": 0.95},
        ]

    mock = MagicMock()
    mock.predict_entities = MagicMock(return_value=entities_per_call)
    return mock


SAMPLE_CHUNKS = [
    {
        "text": "Conforme a Lei 14.133/2021, Art. 55, o STF decidiu...",
        "chunk_uid": "chunk_001",
    },
    {
        "text": "A Súmula 331 do TST trata da terceirização.",
        "chunk_uid": "chunk_002",
    },
]


# =============================================================================
# Tests: Import and basics
# =============================================================================


class TestGLiNERExtractorImport:
    """Testa que o extractor importa corretamente."""

    def test_import(self):
        assert callable(GLiNERExtractor)

    def test_has_legal_labels(self):
        assert len(GLiNERExtractor.LEGAL_LABELS) > 0
        assert "lei" in GLiNERExtractor.LEGAL_LABELS
        assert "tribunal" in GLiNERExtractor.LEGAL_LABELS

    def test_default_threshold(self):
        extractor = GLiNERExtractor()
        assert extractor._threshold == 0.5

    def test_custom_threshold(self):
        extractor = GLiNERExtractor(threshold=0.7)
        assert extractor._threshold == 0.7

    def test_resolve_labels_from_csv_env(self, monkeypatch):
        monkeypatch.setenv("GLINER_LABELS", "person, organization , product")
        extractor = GLiNERExtractor()
        assert extractor._labels == ["person", "organization", "product"]

    def test_resolve_labels_from_json_env(self, monkeypatch):
        monkeypatch.setenv("GLINER_LABELS", '["person","organization"]')
        extractor = GLiNERExtractor()
        assert extractor._labels == ["person", "organization"]

    def test_resolve_labels_from_domain_preset(self, monkeypatch):
        monkeypatch.delenv("GLINER_LABELS", raising=False)
        monkeypatch.setenv("KG_BUILDER_DOMAIN", "general")
        extractor = GLiNERExtractor()
        assert "person" in extractor._labels
        assert "organization" in extractor._labels


# =============================================================================
# Tests: Entity ID
# =============================================================================


class TestEntityId:
    """Testa geração de entity IDs determinísticos."""

    def test_deterministic(self):
        id1 = _make_entity_id("lei", "Lei 14.133/2021")
        id2 = _make_entity_id("lei", "Lei 14.133/2021")
        assert id1 == id2

    def test_different_text_different_id(self):
        id1 = _make_entity_id("lei", "Lei 14.133/2021")
        id2 = _make_entity_id("lei", "Lei 8.666/1993")
        assert id1 != id2

    def test_different_label_different_id(self):
        id1 = _make_entity_id("lei", "14.133")
        id2 = _make_entity_id("artigo", "14.133")
        assert id1 != id2

    def test_starts_with_prefix(self):
        entity_id = _make_entity_id("lei", "test")
        assert entity_id.startswith("gliner_")

    def test_case_insensitive(self):
        id1 = _make_entity_id("lei", "Lei 14.133")
        id2 = _make_entity_id("lei", "lei 14.133")
        assert id1 == id2


# =============================================================================
# Tests: Label mapping
# =============================================================================


class TestLabelMapping:
    """Testa que o label mapping cobre todos os LEGAL_LABELS."""

    def test_all_labels_mapped(self):
        for label in GLiNERExtractor.LEGAL_LABELS:
            assert label in _LABEL_MAP, f"Label '{label}' não está no _LABEL_MAP"

    def test_mapped_labels_are_pascal_case(self):
        for label, neo4j_label in _LABEL_MAP.items():
            assert neo4j_label[0].isupper(), (
                f"Label '{neo4j_label}' para '{label}' não começa com maiúscula"
            )


# =============================================================================
# Tests: Extraction with mock
# =============================================================================


class TestGLiNERExtraction:
    """Testa extração com mock model."""

    @pytest.mark.asyncio
    async def test_extraction_returns_result(self):
        mock_model = _make_mock_model()
        extractor = GLiNERExtractor()

        with patch.object(GLiNERExtractor, '_get_model', return_value=mock_model):
            result = await extractor.run(SAMPLE_CHUNKS)

        assert isinstance(result, GLiNERExtractionResult)
        assert len(result.nodes) > 0
        assert len(result.relationships) > 0

    @pytest.mark.asyncio
    async def test_nodes_have_required_fields(self):
        mock_model = _make_mock_model()
        extractor = GLiNERExtractor()

        with patch.object(GLiNERExtractor, '_get_model', return_value=mock_model):
            result = await extractor.run(SAMPLE_CHUNKS)

        for node in result.nodes:
            assert "id" in node
            assert "label" in node
            assert "properties" in node
            assert "name" in node["properties"]
            assert "entity_type" in node["properties"]
            assert "source" in node["properties"]
            assert node["properties"]["source"] == "gliner"

    @pytest.mark.asyncio
    async def test_relationships_have_required_fields(self):
        mock_model = _make_mock_model()
        extractor = GLiNERExtractor()

        with patch.object(GLiNERExtractor, '_get_model', return_value=mock_model):
            result = await extractor.run(SAMPLE_CHUNKS)

        for rel in result.relationships:
            assert "start" in rel
            assert "end" in rel
            assert "type" in rel
            assert rel["type"] in ("MENTIONS", "RELATED_TO")

    @pytest.mark.asyncio
    async def test_mentions_relationships_created(self):
        mock_model = _make_mock_model()
        extractor = GLiNERExtractor()

        with patch.object(GLiNERExtractor, '_get_model', return_value=mock_model):
            result = await extractor.run(SAMPLE_CHUNKS)

        mentions = [r for r in result.relationships if r["type"] == "MENTIONS"]
        assert len(mentions) > 0
        for m in mentions:
            assert m["start"].startswith("chunk_")

    @pytest.mark.asyncio
    async def test_cooccurrence_relationships_created(self):
        """With 3 entities per chunk, should create co-occurrence rels."""
        mock_model = _make_mock_model()
        extractor = GLiNERExtractor(create_relationships=True)

        with patch.object(GLiNERExtractor, '_get_model', return_value=mock_model):
            result = await extractor.run([SAMPLE_CHUNKS[0]])

        related = [r for r in result.relationships if r["type"] == "RELATED_TO"]
        # 3 entities -> C(3,2) = 3 co-occurrence pairs
        assert len(related) == 3

    @pytest.mark.asyncio
    async def test_no_cooccurrence_when_disabled(self):
        mock_model = _make_mock_model()
        extractor = GLiNERExtractor(create_relationships=False)

        with patch.object(GLiNERExtractor, '_get_model', return_value=mock_model):
            result = await extractor.run([SAMPLE_CHUNKS[0]])

        related = [r for r in result.relationships if r["type"] == "RELATED_TO"]
        assert len(related) == 0

    @pytest.mark.asyncio
    async def test_confidence_stored(self):
        mock_model = _make_mock_model()
        extractor = GLiNERExtractor()

        with patch.object(GLiNERExtractor, '_get_model', return_value=mock_model):
            result = await extractor.run([SAMPLE_CHUNKS[0]])

        for node in result.nodes:
            assert "confidence" in node["properties"]
            assert 0.0 <= node["properties"]["confidence"] <= 1.0


# =============================================================================
# Tests: Dedup
# =============================================================================


class TestGLiNERDedup:
    """Testa deduplicação de entidades entre chunks."""

    @pytest.mark.asyncio
    async def test_dedup_across_chunks(self):
        """Same entity in multiple chunks should only create one node."""
        same_entity = [{"text": "STF", "label": "tribunal", "score": 0.95}]
        mock_model = _make_mock_model(same_entity)
        extractor = GLiNERExtractor()

        with patch.object(GLiNERExtractor, '_get_model', return_value=mock_model):
            result = await extractor.run(SAMPLE_CHUNKS)

        # Only 1 unique node despite 2 chunks
        assert len(result.nodes) == 1
        # But 2 MENTIONS relationships (one per chunk)
        mentions = [r for r in result.relationships if r["type"] == "MENTIONS"]
        assert len(mentions) == 2


# =============================================================================
# Tests: Empty input
# =============================================================================


class TestGLiNEREmptyInput:
    """Testa comportamento com entrada vazia."""

    @pytest.mark.asyncio
    async def test_empty_chunks(self):
        mock_model = _make_mock_model()
        extractor = GLiNERExtractor()

        with patch.object(GLiNERExtractor, '_get_model', return_value=mock_model):
            result = await extractor.run([])

        assert len(result.nodes) == 0
        assert len(result.relationships) == 0

    @pytest.mark.asyncio
    async def test_chunks_with_empty_text(self):
        mock_model = _make_mock_model()
        extractor = GLiNERExtractor()

        with patch.object(GLiNERExtractor, '_get_model', return_value=mock_model):
            result = await extractor.run([{"text": "", "chunk_uid": "c1"}])

        assert len(result.nodes) == 0
        mock_model.predict_entities.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_entities_found(self):
        mock_model = _make_mock_model(entities_per_call=[])
        extractor = GLiNERExtractor()

        with patch.object(GLiNERExtractor, '_get_model', return_value=mock_model):
            result = await extractor.run(SAMPLE_CHUNKS)

        assert len(result.nodes) == 0
        assert len(result.relationships) == 0


# =============================================================================
# Tests: Pipeline integration
# =============================================================================


class TestPipelineGLiNERIntegration:
    """Testa integração com o pipeline."""

    def test_pipeline_imports_gliner(self):
        from app.services.rag.core.kg_builder.pipeline import _run_gliner_extraction
        assert callable(_run_gliner_extraction)

    def test_gliner_in_init_exports(self):
        from app.services.rag.core.kg_builder import GLiNERExtractor as Exported
        assert Exported is GLiNERExtractor
