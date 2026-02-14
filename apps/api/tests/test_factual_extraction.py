"""
Tests for Factual Entity Extraction — CPF, CNPJ, dates, monetary values,
and factual schema/whitelist/prompt integration.

No external dependencies required (pure unit tests).
"""

import pytest


# =============================================================================
# CPF / CNPJ VALIDATION
# =============================================================================


class TestCPFValidation:
    """Tests for _validate_cpf check-digit algorithm."""

    def test_valid_cpf_accepted(self):
        from app.services.rag.core.neo4j_mvp import _validate_cpf
        # Known valid CPF: 529.982.247-25
        assert _validate_cpf("529.982.247-25") is True

    def test_invalid_cpf_rejected(self):
        from app.services.rag.core.neo4j_mvp import _validate_cpf
        # Wrong check digits
        assert _validate_cpf("529.982.247-99") is False

    def test_all_same_digits_rejected(self):
        from app.services.rag.core.neo4j_mvp import _validate_cpf
        assert _validate_cpf("111.111.111-11") is False
        assert _validate_cpf("000.000.000-00") is False

    def test_wrong_length_rejected(self):
        from app.services.rag.core.neo4j_mvp import _validate_cpf
        assert _validate_cpf("123.456.789") is False
        assert _validate_cpf("12345") is False

    def test_another_valid_cpf(self):
        from app.services.rag.core.neo4j_mvp import _validate_cpf
        assert _validate_cpf("111.444.777-35") is True


class TestCNPJValidation:
    """Tests for _validate_cnpj check-digit algorithm."""

    def test_valid_cnpj_accepted(self):
        from app.services.rag.core.neo4j_mvp import _validate_cnpj
        # Known valid CNPJ: 11.222.333/0001-81
        assert _validate_cnpj("11.222.333/0001-81") is True

    def test_invalid_cnpj_rejected(self):
        from app.services.rag.core.neo4j_mvp import _validate_cnpj
        assert _validate_cnpj("11.222.333/0001-99") is False

    def test_all_same_digits_rejected(self):
        from app.services.rag.core.neo4j_mvp import _validate_cnpj
        assert _validate_cnpj("11.111.111/1111-11") is False

    def test_wrong_length_rejected(self):
        from app.services.rag.core.neo4j_mvp import _validate_cnpj
        assert _validate_cnpj("12.345.678/9012") is False


# =============================================================================
# REGEX EXTRACTION
# =============================================================================


class TestFactualRegexExtraction:
    """Tests for LegalEntityExtractor factual extraction."""

    def test_factual_disabled_by_default(self):
        from app.services.rag.core.neo4j_mvp import LegalEntityExtractor
        text = "CPF 529.982.247-25 e R$ 10.000,00 em 15/03/2024"
        entities = LegalEntityExtractor.extract(text)
        types = {e["entity_type"] for e in entities}
        assert "cpf" not in types
        assert "valor_monetario" not in types
        assert "data_juridica" not in types

    def test_factual_enabled_extracts_cpf(self):
        from app.services.rag.core.neo4j_mvp import LegalEntityExtractor
        text = "O autor, CPF 529.982.247-25, ajuizou ação"
        entities = LegalEntityExtractor.extract(text, include_factual=True)
        cpfs = [e for e in entities if e["entity_type"] == "cpf"]
        assert len(cpfs) == 1
        assert cpfs[0]["name"] == "529.982.247-25"
        assert cpfs[0]["entity_id"] == "cpf_52998224725"
        assert cpfs[0]["normalized"] == "cpf:52998224725"

    def test_factual_enabled_extracts_cnpj(self):
        from app.services.rag.core.neo4j_mvp import LegalEntityExtractor
        text = "Empresa CNPJ 11.222.333/0001-81 foi citada"
        entities = LegalEntityExtractor.extract(text, include_factual=True)
        cnpjs = [e for e in entities if e["entity_type"] == "cnpj"]
        assert len(cnpjs) == 1
        assert cnpjs[0]["name"] == "11.222.333/0001-81"
        assert cnpjs[0]["entity_id"] == "cnpj_11222333000181"

    def test_invalid_cpf_not_extracted(self):
        from app.services.rag.core.neo4j_mvp import LegalEntityExtractor
        text = "CPF 111.111.111-11 inválido"
        entities = LegalEntityExtractor.extract(text, include_factual=True)
        cpfs = [e for e in entities if e["entity_type"] == "cpf"]
        assert len(cpfs) == 0

    def test_factual_enabled_extracts_date(self):
        from app.services.rag.core.neo4j_mvp import LegalEntityExtractor
        text = "Audiência designada para 15/03/2024"
        entities = LegalEntityExtractor.extract(text, include_factual=True)
        dates = [e for e in entities if e["entity_type"] == "data_juridica"]
        assert len(dates) == 1
        assert dates[0]["name"] == "15/03/2024"
        assert dates[0]["normalized"] == "data:2024-03-15"

    def test_invalid_date_not_extracted(self):
        from app.services.rag.core.neo4j_mvp import LegalEntityExtractor
        text = "Data 32/13/2024 inválida"
        entities = LegalEntityExtractor.extract(text, include_factual=True)
        dates = [e for e in entities if e["entity_type"] == "data_juridica"]
        assert len(dates) == 0

    def test_factual_enabled_extracts_monetary_value(self):
        from app.services.rag.core.neo4j_mvp import LegalEntityExtractor
        text = "Condenação no valor de R$ 10.500,00"
        entities = LegalEntityExtractor.extract(text, include_factual=True)
        values = [e for e in entities if e["entity_type"] == "valor_monetario"]
        assert len(values) == 1
        assert values[0]["name"] == "R$ 10.500,00"
        assert "10500.00" in values[0]["normalized"]

    def test_extract_all_passes_factual(self):
        from app.services.rag.core.neo4j_mvp import LegalEntityExtractor
        text = "CPF 529.982.247-25 citado na Lei 8.666/93"
        result = LegalEntityExtractor.extract_all(text, include_factual=True)
        types = {e["entity_type"] for e in result["entities"]}
        assert "cpf" in types
        assert "lei" in types


# =============================================================================
# SCHEMA & WHITELIST
# =============================================================================


class TestFactualSchemaPatterns:
    """Tests for factual node types, rel types, and patterns in schema."""

    def test_pessoa_node_type_in_schema(self):
        from app.services.rag.core.kg_builder.legal_schema import LEGAL_NODE_TYPES
        labels = {nt["label"] for nt in LEGAL_NODE_TYPES}
        assert "Pessoa" in labels

    def test_empresa_node_type_in_schema(self):
        from app.services.rag.core.kg_builder.legal_schema import LEGAL_NODE_TYPES
        labels = {nt["label"] for nt in LEGAL_NODE_TYPES}
        assert "Empresa" in labels

    def test_evento_node_type_in_schema(self):
        from app.services.rag.core.kg_builder.legal_schema import LEGAL_NODE_TYPES
        labels = {nt["label"] for nt in LEGAL_NODE_TYPES}
        assert "Evento" in labels

    def test_factual_relationship_types(self):
        from app.services.rag.core.kg_builder.legal_schema import LEGAL_RELATIONSHIP_TYPES
        labels = {rt["label"] for rt in LEGAL_RELATIONSHIP_TYPES}
        assert "PARTICIPA_DE" in labels
        assert "PARTE_DE" in labels
        assert "OCORRE_EM" in labels
        assert "REPRESENTA" in labels

    def test_factual_patterns_in_schema(self):
        from app.services.rag.core.kg_builder.legal_schema import LEGAL_PATTERNS
        patterns_set = set(LEGAL_PATTERNS)
        assert ("Pessoa", "PARTICIPA_DE", "Processo") in patterns_set
        assert ("Empresa", "PARTE_DE", "Processo") in patterns_set
        assert ("Actor", "REPRESENTA", "Pessoa") in patterns_set
        assert ("Evento", "OCORRE_EM", "Local") in patterns_set


class TestFactualWhitelist:
    """Tests for factual types in HYBRID_LABELS_BY_ENTITY_TYPE whitelist."""

    def test_factual_types_in_whitelist(self):
        from app.services.rag.core.graph_hybrid import HYBRID_LABELS_BY_ENTITY_TYPE
        assert HYBRID_LABELS_BY_ENTITY_TYPE.get("pessoa") == "Pessoa"
        assert HYBRID_LABELS_BY_ENTITY_TYPE.get("empresa") == "Empresa"
        assert HYBRID_LABELS_BY_ENTITY_TYPE.get("evento") == "Evento"

    def test_orgao_publico_in_whitelist(self):
        """Bug fix: OrgaoPublico was in schema but missing from whitelist."""
        from app.services.rag.core.graph_hybrid import HYBRID_LABELS_BY_ENTITY_TYPE
        assert HYBRID_LABELS_BY_ENTITY_TYPE.get("orgao_publico") == "OrgaoPublico"

    def test_valor_monetario_in_whitelist(self):
        from app.services.rag.core.graph_hybrid import HYBRID_LABELS_BY_ENTITY_TYPE
        assert HYBRID_LABELS_BY_ENTITY_TYPE.get("valor_monetario") == "ValorMonetario"

    def test_data_juridica_in_whitelist(self):
        from app.services.rag.core.graph_hybrid import HYBRID_LABELS_BY_ENTITY_TYPE
        assert HYBRID_LABELS_BY_ENTITY_TYPE.get("data_juridica") == "DataJuridica"

    def test_local_in_whitelist(self):
        from app.services.rag.core.graph_hybrid import HYBRID_LABELS_BY_ENTITY_TYPE
        assert HYBRID_LABELS_BY_ENTITY_TYPE.get("local") == "Local"


# =============================================================================
# CROSS-MERGER EQUIVALENCES
# =============================================================================


class TestFactualEquivalences:
    """Tests for factual type equivalences in cross_merger."""

    def test_factual_canonical_types_in_whitelist(self):
        """All factual canonical types must exist in the whitelist."""
        from app.services.rag.core.graph_hybrid import HYBRID_LABELS_BY_ENTITY_TYPE
        from app.services.rag.core.kg_builder.cross_merger import TYPE_EQUIVALENCE_MAP

        factual_canonicals = {"pessoa", "empresa", "evento"}
        known = set(HYBRID_LABELS_BY_ENTITY_TYPE.keys())
        for canonical in factual_canonicals:
            assert canonical in known, f"Factual canonical '{canonical}' not in whitelist"

    def test_factual_equivalences_exist(self):
        from app.services.rag.core.kg_builder.cross_merger import TYPE_EQUIVALENCE_MAP
        assert TYPE_EQUIVALENCE_MAP.get("reclamante") == "pessoa"
        assert TYPE_EQUIVALENCE_MAP.get("empregador") == "empresa"
        assert TYPE_EQUIVALENCE_MAP.get("audiencia") == "evento"

    def test_factual_types_are_mergeable(self):
        from app.services.rag.core.kg_builder.cross_merger import _types_are_mergeable
        assert _types_are_mergeable("reclamante", "pessoa") is True
        assert _types_are_mergeable("empregador", "empresa") is True
        assert _types_are_mergeable("audiencia", "evento") is True


# =============================================================================
# PROMPT LAYER
# =============================================================================


class TestFactualPromptLayer:
    """Tests for factual extraction layer in LLM prompt."""

    def test_prompt_without_factual_has_no_regra_10(self):
        """Base prompt should not contain REGRA 10 (factual layer starts at 10)."""
        from app.services.rag.core.kg_builder.legal_graphrag_prompt import (
            STRICT_LEGAL_EXTRACTION_PROMPT,
        )
        assert "REGRA 10" not in STRICT_LEGAL_EXTRACTION_PROMPT

    def test_factual_layer_contains_regra_10_11_12(self):
        """Factual layer uses REGRA 10/11/12 (renumbered from 7/8/9 for v2 parity)."""
        from app.services.rag.core.kg_builder.legal_graphrag_prompt import (
            FACTUAL_EXTRACTION_LAYER,
        )
        assert "REGRA 10" in FACTUAL_EXTRACTION_LAYER
        assert "REGRA 11" in FACTUAL_EXTRACTION_LAYER
        assert "REGRA 12" in FACTUAL_EXTRACTION_LAYER

    def test_factual_layer_mentions_key_entities(self):
        from app.services.rag.core.kg_builder.legal_graphrag_prompt import (
            FACTUAL_EXTRACTION_LAYER,
        )
        assert "Pessoa" in FACTUAL_EXTRACTION_LAYER
        assert "Empresa" in FACTUAL_EXTRACTION_LAYER
        assert "Evento" in FACTUAL_EXTRACTION_LAYER

    def test_template_without_factual(self):
        """Default template should NOT include factual layer."""
        try:
            from app.services.rag.core.kg_builder.legal_graphrag_prompt import (
                StrictLegalExtractionTemplate,
            )
            tmpl = StrictLegalExtractionTemplate(include_factual=False)
            if hasattr(tmpl, "template"):
                assert "REGRA 10" not in tmpl.template
        except Exception:
            pytest.skip("neo4j-graphrag not installed")

    def test_template_with_factual(self):
        """Template with include_factual=True should include factual layer."""
        try:
            from app.services.rag.core.kg_builder.legal_graphrag_prompt import (
                StrictLegalExtractionTemplate,
            )
            tmpl = StrictLegalExtractionTemplate(include_factual=True)
            if hasattr(tmpl, "template"):
                assert "REGRA 10" in tmpl.template
                assert "REGRA 12" in tmpl.template
        except Exception:
            pytest.skip("neo4j-graphrag not installed")

    def test_regra_11_requires_evidence(self):
        """REGRA 11 must require evidence for factual relationships (strict parity)."""
        from app.services.rag.core.kg_builder.legal_graphrag_prompt import (
            FACTUAL_EXTRACTION_LAYER,
        )
        assert "properties.evidence" in FACTUAL_EXTRACTION_LAYER
        assert "properties.dimension" in FACTUAL_EXTRACTION_LAYER

    def test_regra_11_dimension_fatica(self):
        """REGRA 11 must use dimension 'fatica' for factual relationships."""
        from app.services.rag.core.kg_builder.legal_graphrag_prompt import (
            FACTUAL_EXTRACTION_LAYER,
        )
        assert '"fatica"' in FACTUAL_EXTRACTION_LAYER

    def test_regra_11_has_triggers(self):
        """REGRA 11 must have trigger phrases for PARTICIPA_DE and REPRESENTA."""
        from app.services.rag.core.kg_builder.legal_graphrag_prompt import (
            FACTUAL_EXTRACTION_LAYER,
        )
        assert "autor" in FACTUAL_EXTRACTION_LAYER
        assert "reu" in FACTUAL_EXTRACTION_LAYER
        assert "advogado" in FACTUAL_EXTRACTION_LAYER

    def test_dimension_fatica_in_base_prompt(self):
        """Base prompt REGRA 0.1 must include 'fatica' as valid dimension."""
        from app.services.rag.core.kg_builder.legal_graphrag_prompt import (
            STRICT_LEGAL_EXTRACTION_PROMPT,
        )
        assert "fatica" in STRICT_LEGAL_EXTRACTION_PROMPT
        assert "PARTICIPA_DE" in STRICT_LEGAL_EXTRACTION_PROMPT
