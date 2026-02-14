"""
Tests for Schema Discovery — post-processing for LLM-discovered entity types.

Mocks Neo4j to test without external dependencies.
"""

import pytest
from unittest.mock import MagicMock, patch


class TestToPascalCase:
    """Tests for the _to_pascal_case helper."""

    def test_simple_word(self):
        from app.services.rag.core.kg_builder.schema_discovery import _to_pascal_case
        assert _to_pascal_case("norma") == "Norma"

    def test_underscore_separated(self):
        from app.services.rag.core.kg_builder.schema_discovery import _to_pascal_case
        assert _to_pascal_case("orgao_publico") == "OrgaoPublico"

    def test_space_separated(self):
        from app.services.rag.core.kg_builder.schema_discovery import _to_pascal_case
        assert _to_pascal_case("orgao publico") == "OrgaoPublico"

    def test_accent_removal(self):
        from app.services.rag.core.kg_builder.schema_discovery import _to_pascal_case
        result = _to_pascal_case("órgão público")
        assert result == "OrgaoPublico"

    def test_hyphen_separated(self):
        from app.services.rag.core.kg_builder.schema_discovery import _to_pascal_case
        assert _to_pascal_case("auto-de-infração") == "AutoDeInfracao"


class TestValidateType:
    """Tests for type validation heuristics."""

    @pytest.fixture
    def processor(self):
        from app.services.rag.core.kg_builder.schema_discovery import SchemaDiscoveryProcessor
        return SchemaDiscoveryProcessor(driver=MagicMock(), min_instances=2)

    @pytest.fixture
    def known_types(self):
        from app.services.rag.core.graph_hybrid import HYBRID_LABELS_BY_ENTITY_TYPE
        return set(HYBRID_LABELS_BY_ENTITY_TYPE.keys())

    def test_stopword_rejected(self, processor, known_types):
        raw = {"type": "entity", "count": 10, "samples": ["Entity A", "Entity B"]}
        result = processor._validate_type(raw, known_types)
        assert not result.is_valid
        assert result.rejection_reason == "stopword"

    def test_too_short_rejected(self, processor, known_types):
        raw = {"type": "ab", "count": 5, "samples": ["Foo", "Bar"]}
        result = processor._validate_type(raw, known_types)
        assert not result.is_valid
        assert result.rejection_reason == "too_short"

    def test_forbidden_label_rejected(self, processor, known_types):
        raw = {"type": "document", "count": 5, "samples": ["Doc A", "Doc B"]}
        # "document" -> PascalCase "Document" which is forbidden
        result = processor._validate_type(raw, known_types)
        assert not result.is_valid
        assert result.rejection_reason == "forbidden_label"

    def test_low_count_rejected(self, processor, known_types):
        raw = {"type": "contrato_social", "count": 1, "samples": ["X"]}
        result = processor._validate_type(raw, known_types)
        assert not result.is_valid
        assert result.rejection_reason == "low_count"

    def test_low_quality_names_rejected(self, processor, known_types):
        raw = {"type": "contrato_social", "count": 5, "samples": ["", "x", "a"]}
        result = processor._validate_type(raw, known_types)
        assert not result.is_valid
        assert result.rejection_reason == "low_quality_names"

    def test_valid_type_accepted(self, processor, known_types):
        raw = {
            "type": "contrato_social",
            "count": 5,
            "samples": ["Contrato Social LTDA", "Contrato Social SA"],
        }
        result = processor._validate_type(raw, known_types)
        assert result.is_valid
        assert result.proposed_label == "ContratoSocial"
        assert result.rejection_reason == ""

    def test_already_known_rejected(self, processor, known_types):
        raw = {"type": "lei", "count": 10, "samples": ["Lei 8.666", "Lei 14.133"]}
        result = processor._validate_type(raw, known_types)
        assert not result.is_valid
        assert result.rejection_reason == "already_known"


class TestRegisterDynamicLabel:
    """Tests for dynamic label registration via graph_hybrid."""

    def test_register_new_label(self):
        from app.services.rag.core.graph_hybrid import (
            HYBRID_LABELS_BY_ENTITY_TYPE,
            register_dynamic_label,
        )
        # Register a test label
        try:
            result = register_dynamic_label("contrato_teste", "ContratoTeste")
            assert result is True
            assert HYBRID_LABELS_BY_ENTITY_TYPE["contrato_teste"] == "ContratoTeste"
        finally:
            HYBRID_LABELS_BY_ENTITY_TYPE.pop("contrato_teste", None)

    def test_register_idempotent(self):
        from app.services.rag.core.graph_hybrid import (
            HYBRID_LABELS_BY_ENTITY_TYPE,
            register_dynamic_label,
        )
        try:
            register_dynamic_label("idem_teste", "IdemTeste")
            result = register_dynamic_label("idem_teste", "IdemTeste")
            assert result is True  # idempotent
        finally:
            HYBRID_LABELS_BY_ENTITY_TYPE.pop("idem_teste", None)

    def test_reject_forbidden(self):
        from app.services.rag.core.graph_hybrid import register_dynamic_label
        assert register_dynamic_label("entity", "Entity") is False

    def test_reject_unsafe(self):
        from app.services.rag.core.graph_hybrid import register_dynamic_label
        assert register_dynamic_label("foo bar", "Foo Bar") is False

    def test_reject_too_short(self):
        from app.services.rag.core.graph_hybrid import register_dynamic_label
        assert register_dynamic_label("ab", "Ab") is False


class TestDiscoveryResult:
    """Tests for DiscoveryResult dataclass."""

    def test_default_values(self):
        from app.services.rag.core.kg_builder.schema_discovery import DiscoveryResult
        r = DiscoveryResult()
        assert r.total_unknown_entities == 0
        assert r.discovered_types == []
        assert r.rehydrated_types == []
        assert r.registered_types == []
        assert r.skipped_types == []


class TestDiscoverFlow:
    """Tests for discover() orchestration and safety behavior."""

    def test_register_failure_not_counted(self):
        from app.services.rag.core.kg_builder.schema_discovery import SchemaDiscoveryProcessor

        p = SchemaDiscoveryProcessor(driver=MagicMock(), min_instances=2, auto_register=True)
        valid_raw = [{"type": "contrato_social", "count": 3, "samples": ["Contrato Social LTDA"]}]

        p._query_unknown_types = MagicMock(return_value=valid_raw)
        p.rehydrate = MagicMock(return_value=[])
        p._register_type = MagicMock(return_value=False)
        p._persist_discovered_schema = MagicMock()

        result = p.discover("tenant_1")

        assert result.registered_types == []
        assert any("register_failed" in item for item in result.skipped_types)
        p._persist_discovered_schema.assert_not_called()

    def test_query_uses_tenant_filter(self):
        from app.services.rag.core.kg_builder.schema_discovery import SchemaDiscoveryProcessor

        mock_session = MagicMock()
        mock_session.run.return_value = []
        mock_driver = MagicMock()
        mock_driver.session.return_value.__enter__.return_value = mock_session

        p = SchemaDiscoveryProcessor(driver=mock_driver, min_instances=2)
        p._query_unknown_types("tenant_x", {"lei"})

        called_query = mock_session.run.call_args.args[0]
        called_params = mock_session.run.call_args.kwargs
        assert "Document {tenant_id: $tenant_id}" in called_query
        assert called_params["tenant_id"] == "tenant_x"


class TestRehydrate:
    """Tests persisted schema rehydration."""

    def test_rehydrate_registers_types(self):
        from app.services.rag.core.kg_builder.schema_discovery import SchemaDiscoveryProcessor

        payload = '[{"key":"contrato_social","label":"ContratoSocial"},{"key":"norma_x","label":"NormaX"}]'
        mock_record = {"types_json": payload}
        mock_session = MagicMock()
        mock_session.run.return_value.single.return_value = mock_record
        mock_driver = MagicMock()
        mock_driver.session.return_value.__enter__.return_value = mock_session

        with patch(
            "app.services.rag.core.graph_hybrid.register_dynamic_label",
            return_value=True,
        ) as mock_register:
            p = SchemaDiscoveryProcessor(driver=mock_driver)
            restored = p.rehydrate("tenant_abc")

        assert restored == ["contrato_social", "norma_x"]
        assert mock_register.call_count == 2


class TestGetAllNodeTypes:
    """Tests for get_all_node_types in legal_schema."""

    def test_includes_base_types(self):
        from app.services.rag.core.kg_builder.legal_schema import get_all_node_types
        types = get_all_node_types(include_discovered=False)
        labels = {t["label"] for t in types}
        assert "Lei" in labels
        assert "Artigo" in labels
        assert "Claim" in labels

    def test_includes_discovered_types(self):
        from app.services.rag.core.graph_hybrid import HYBRID_LABELS_BY_ENTITY_TYPE
        from app.services.rag.core.kg_builder.legal_schema import get_all_node_types

        try:
            HYBRID_LABELS_BY_ENTITY_TYPE["teste_discovery"] = "TesteDiscovery"
            types = get_all_node_types(include_discovered=True)
            labels = {t["label"] for t in types}
            assert "TesteDiscovery" in labels
        finally:
            HYBRID_LABELS_BY_ENTITY_TYPE.pop("teste_discovery", None)
