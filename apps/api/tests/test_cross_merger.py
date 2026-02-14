"""
Tests for Cross-Extractor Entity Merger — deduplication between extraction pipelines.

Mocks Neo4j and rapidfuzz to test without external dependencies.
"""

import pytest
from unittest.mock import MagicMock, patch


class TestPickKeeper:
    """Tests for _pick_keeper — choosing which entity to keep."""

    def test_predefined_type_wins(self):
        from app.services.rag.core.kg_builder.cross_merger import _pick_keeper
        entities = [
            {"entity_id": "gliner_very_long_hash_123", "name": "Lei 8.666", "entity_type": "norma"},
            {"entity_id": "lei_8666_1993", "name": "Lei 8.666/1993", "entity_type": "lei"},
        ]
        keeper, to_merge = _pick_keeper(entities)
        # "lei" is in the whitelist, "norma" is not
        assert keeper["entity_id"] == "lei_8666_1993"
        assert len(to_merge) == 1
        assert to_merge[0]["entity_id"] == "gliner_very_long_hash_123"

    def test_shorter_entity_id_tiebreaker(self):
        from app.services.rag.core.kg_builder.cross_merger import _pick_keeper
        entities = [
            {"entity_id": "lei_very_long_id_abc", "name": "Lei 14.133", "entity_type": "lei"},
            {"entity_id": "lei_14133", "name": "Lei 14.133", "entity_type": "lei"},
        ]
        keeper, to_merge = _pick_keeper(entities)
        # Both are known types, shorter entity_id wins
        assert keeper["entity_id"] == "lei_14133"

    def test_multiple_entities(self):
        from app.services.rag.core.kg_builder.cross_merger import _pick_keeper
        entities = [
            {"entity_id": "gliner_abc", "name": "STF", "entity_type": "corte"},
            {"entity_id": "tribunal_stf", "name": "STF", "entity_type": "tribunal"},
            {"entity_id": "llm_xyz_long", "name": "STF", "entity_type": "unknown"},
        ]
        keeper, to_merge = _pick_keeper(entities)
        assert keeper["entity_id"] == "tribunal_stf"
        assert len(to_merge) == 2


class TestTypesAreMergeable:
    """Tests for _types_are_mergeable — cross-type conflict resolution."""

    def test_same_type_always_mergeable(self):
        from app.services.rag.core.kg_builder.cross_merger import _types_are_mergeable
        assert _types_are_mergeable("lei", "lei") is True

    def test_equivalent_types_mergeable(self):
        from app.services.rag.core.kg_builder.cross_merger import _types_are_mergeable
        assert _types_are_mergeable("norma", "lei") is True
        assert _types_are_mergeable("codigo", "lei") is True
        assert _types_are_mergeable("acordao", "decisao") is True

    def test_non_equivalent_not_mergeable(self):
        from app.services.rag.core.kg_builder.cross_merger import _types_are_mergeable
        assert _types_are_mergeable("lei", "tribunal") is False
        assert _types_are_mergeable("artigo", "sumula") is False

    def test_empty_types_mergeable(self):
        from app.services.rag.core.kg_builder.cross_merger import _types_are_mergeable
        assert _types_are_mergeable("", "") is True


class TestGetCanonicalType:
    """Tests for _get_canonical_type."""

    def test_known_mapping(self):
        from app.services.rag.core.kg_builder.cross_merger import _get_canonical_type
        assert _get_canonical_type("norma") == "lei"
        assert _get_canonical_type("acordao") == "decisao"
        assert _get_canonical_type("enunciado") == "sumula"

    def test_unknown_passthrough(self):
        from app.services.rag.core.kg_builder.cross_merger import _get_canonical_type
        assert _get_canonical_type("lei") == "lei"
        assert _get_canonical_type("custom") == "custom"


class TestEquivalenceMapConsistency:
    """Tests that TYPE_EQUIVALENCE_MAP canonical types exist in the whitelist."""

    def test_all_canonical_types_in_whitelist(self):
        from app.services.rag.core.graph_hybrid import HYBRID_LABELS_BY_ENTITY_TYPE
        from app.services.rag.core.kg_builder.cross_merger import TYPE_EQUIVALENCE_MAP

        known = set(HYBRID_LABELS_BY_ENTITY_TYPE.keys())
        canonical_types = set(TYPE_EQUIVALENCE_MAP.values())

        for canonical in canonical_types:
            assert canonical in known, (
                f"Canonical type '{canonical}' from TYPE_EQUIVALENCE_MAP "
                f"not found in HYBRID_LABELS_BY_ENTITY_TYPE"
            )


class TestCrossMergeResult:
    """Tests for CrossMergeResult dataclass."""

    def test_default_values(self):
        from app.services.rag.core.kg_builder.cross_merger import CrossMergeResult
        r = CrossMergeResult()
        assert r.candidates == 0
        assert r.merged == 0
        assert r.conflicts == 0
        assert r.errors == []


class TestTenantSafety:
    """Tests tenant-scoped safeguards in cross-merger."""

    def test_requires_tenant_id(self):
        from app.services.rag.core.kg_builder.cross_merger import CrossExtractorMerger

        merger = CrossExtractorMerger(driver=MagicMock(), tenant_id=None)
        result = merger.run()

        assert result.merged == 0
        assert "tenant_id_required" in result.errors

    def test_fetch_candidates_uses_tenant_filter(self):
        from app.services.rag.core.kg_builder.cross_merger import CrossExtractorMerger

        mock_session = MagicMock()
        mock_session.run.return_value = []
        mock_driver = MagicMock()
        mock_driver.session.return_value.__enter__.return_value = mock_session

        merger = CrossExtractorMerger(driver=mock_driver, tenant_id="tenant_42")
        merger._fetch_candidates(mock_driver)

        called_query = mock_session.run.call_args.args[0]
        called_params = mock_session.run.call_args.kwargs
        assert "d_seed:Document {tenant_id: $tenant_id}" in called_query
        assert called_params["tenant_id"] == "tenant_42"
