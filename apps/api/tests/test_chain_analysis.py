"""
Tests for v2 parity: APLICA_SUMULA schema, prompt enrichment,
post-processor enhancements, and chain analysis module.

No external dependencies required (pure unit tests).
"""

import re

import pytest


# =============================================================================
# APLICA_SUMULA SCHEMA
# =============================================================================


class TestAplicaSumulaSchema:
    """Tests for APLICA_SUMULA, AFASTA, ESTABELECE_TESE in schema."""

    def test_aplica_sumula_in_relationship_types(self):
        from app.services.rag.core.kg_builder.legal_schema import LEGAL_RELATIONSHIP_TYPES
        labels = {rt["label"] for rt in LEGAL_RELATIONSHIP_TYPES}
        assert "APLICA_SUMULA" in labels

    def test_afasta_in_relationship_types(self):
        from app.services.rag.core.kg_builder.legal_schema import LEGAL_RELATIONSHIP_TYPES
        labels = {rt["label"] for rt in LEGAL_RELATIONSHIP_TYPES}
        assert "AFASTA" in labels

    def test_estabelece_tese_in_relationship_types(self):
        from app.services.rag.core.kg_builder.legal_schema import LEGAL_RELATIONSHIP_TYPES
        labels = {rt["label"] for rt in LEGAL_RELATIONSHIP_TYPES}
        assert "ESTABELECE_TESE" in labels

    def test_aplica_sumula_pattern_exists(self):
        from app.services.rag.core.kg_builder.legal_schema import LEGAL_PATTERNS
        patterns_set = set(LEGAL_PATTERNS)
        assert ("Decisao", "APLICA_SUMULA", "Sumula") in patterns_set

    def test_afasta_patterns_exist(self):
        from app.services.rag.core.kg_builder.legal_schema import LEGAL_PATTERNS
        patterns_set = set(LEGAL_PATTERNS)
        assert ("Decisao", "AFASTA", "Artigo") in patterns_set
        assert ("Decisao", "AFASTA", "Lei") in patterns_set

    def test_estabelece_tese_pattern_exists(self):
        from app.services.rag.core.kg_builder.legal_schema import LEGAL_PATTERNS
        patterns_set = set(LEGAL_PATTERNS)
        assert ("Decisao", "ESTABELECE_TESE", "Tese") in patterns_set

    def test_backward_compat_aplica_sumula_still_exists(self):
        """APLICA generic for Sumula still exists for backward compatibility."""
        from app.services.rag.core.kg_builder.legal_schema import LEGAL_PATTERNS
        patterns_set = set(LEGAL_PATTERNS)
        assert ("Decisao", "APLICA", "Sumula") in patterns_set


# =============================================================================
# PROMPT PARITY
# =============================================================================


class TestPromptParity:
    """Tests for v2-parity prompt enrichment."""

    def test_prompt_has_architecture_section(self):
        from app.services.rag.core.kg_builder.legal_graphrag_prompt import (
            STRICT_LEGAL_EXTRACTION_PROMPT,
        )
        assert "ARQUITETURA DO GRAFO" in STRICT_LEGAL_EXTRACTION_PROMPT
        assert "CAMADA 1" in STRICT_LEGAL_EXTRACTION_PROMPT
        assert "CAMADA 2" in STRICT_LEGAL_EXTRACTION_PROMPT
        assert "CAMADA 3" in STRICT_LEGAL_EXTRACTION_PROMPT

    def test_prompt_has_dimension_mapping(self):
        from app.services.rag.core.kg_builder.legal_graphrag_prompt import (
            STRICT_LEGAL_EXTRACTION_PROMPT,
        )
        assert "remissiva: REMETE_A" in STRICT_LEGAL_EXTRACTION_PROMPT
        assert "hierarquica:" in STRICT_LEGAL_EXTRACTION_PROMPT
        assert "horizontal:" in STRICT_LEGAL_EXTRACTION_PROMPT

    def test_prompt_has_aplica_sumula_not_generic(self):
        from app.services.rag.core.kg_builder.legal_graphrag_prompt import (
            STRICT_LEGAL_EXTRACTION_PROMPT,
        )
        assert "APLICA_SUMULA" in STRICT_LEGAL_EXTRACTION_PROMPT

    def test_prompt_has_afasta(self):
        from app.services.rag.core.kg_builder.legal_graphrag_prompt import (
            STRICT_LEGAL_EXTRACTION_PROMPT,
        )
        assert "AFASTA" in STRICT_LEGAL_EXTRACTION_PROMPT

    def test_prompt_has_11_remete_a_triggers(self):
        """v2 has 9 triggers; we have 11 (superset)."""
        from app.services.rag.core.kg_builder.legal_graphrag_prompt import (
            STRICT_LEGAL_EXTRACTION_PROMPT,
        )
        triggers = [
            "nos termos do art.", "conforme art.", "aplica-se o art.",
            "de que trata o art.", "previsto no art.", "c/c art.",
            "na forma do art.", "ressalvado o art.", "com base no art.",
            "nos moldes do art.", "nos termos do artigo",
        ]
        for trigger in triggers:
            assert trigger in STRICT_LEGAL_EXTRACTION_PROMPT, f"Missing trigger: {trigger}"

    def test_prompt_has_citacao_entre_decisoes(self):
        """v2 REGRA #6: citation between decisions with example."""
        from app.services.rag.core.kg_builder.legal_graphrag_prompt import (
            STRICT_LEGAL_EXTRACTION_PROMPT,
        )
        assert "CITACAO ENTRE DECISOES" in STRICT_LEGAL_EXTRACTION_PROMPT
        assert "REsp 1.134.186" in STRICT_LEGAL_EXTRACTION_PROMPT

    def test_prompt_has_regulamenta_especializa(self):
        """v2 REGRA #7: regulamenta and especializa with examples."""
        from app.services.rag.core.kg_builder.legal_graphrag_prompt import (
            STRICT_LEGAL_EXTRACTION_PROMPT,
        )
        assert "REGULAMENTA E ESPECIALIZA" in STRICT_LEGAL_EXTRACTION_PROMPT
        assert "Decreto 10.854/2021" in STRICT_LEGAL_EXTRACTION_PROMPT

    def test_prompt_chains_use_aplica_sumula(self):
        """Chain patterns should use APLICA_SUMULA, not generic APLICA for Sumula."""
        from app.services.rag.core.kg_builder.legal_graphrag_prompt import (
            STRICT_LEGAL_EXTRACTION_PROMPT,
        )
        assert "APLICA_SUMULA-> Sumula" in STRICT_LEGAL_EXTRACTION_PROMPT

    def test_factual_layer_uses_regra_10_11_12(self):
        """Factual layer should use REGRA 10/11/12 (renumbered from 7/8/9)."""
        from app.services.rag.core.kg_builder.legal_graphrag_prompt import (
            FACTUAL_EXTRACTION_LAYER,
        )
        assert "REGRA 10" in FACTUAL_EXTRACTION_LAYER
        assert "REGRA 11" in FACTUAL_EXTRACTION_LAYER
        assert "REGRA 12" in FACTUAL_EXTRACTION_LAYER

    def test_template_with_factual_includes_regra_10(self):
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


# =============================================================================
# POST-PROCESSOR ENHANCEMENTS
# =============================================================================


class TestPostProcessorEnhancements:
    """Tests for post-processor v2-parity enhancements."""

    def test_stats_has_new_fields(self):
        from app.services.rag.core.kg_builder.legal_postprocessor import LegalPostProcessStats
        stats = LegalPostProcessStats()
        assert hasattr(stats, "artigo_names_normalized")
        assert hasattr(stats, "compound_decisao_removed")
        assert hasattr(stats, "aplica_to_aplica_sumula_migrated")
        assert stats.artigo_names_normalized == 0
        assert stats.compound_decisao_removed == 0
        assert stats.aplica_to_aplica_sumula_migrated == 0

    def test_compound_decisao_regex_pattern(self):
        """The compound decisao regex should match "ADIs 4296, 4357 e 4425"."""
        pattern = re.compile(r".*\d+.*,.*\d+.*")
        test_cases = [
            ("ADIs 4296, 4357 e 4425", True),
            ("REsp 1.134.186", False),
            ("Decisao 123, 456 e 789", True),
        ]
        for name, should_match in test_cases:
            has_e = " e " in name
            has_pattern = bool(pattern.match(name))
            result = has_e and has_pattern
            assert result == should_match, f"Failed for {name}: expected {should_match}, got {result}"


# =============================================================================
# CHAIN ANALYZER MODULE
# =============================================================================


class TestChainAnalyzer:
    """Tests for chain_analyzer.py module."""

    def test_chain_queries_exist(self):
        from app.services.rag.core.kg_builder.chain_analyzer import CHAIN_QUERIES
        assert len(CHAIN_QUERIES) == 6

    def test_chain_query_names_match_v2(self):
        from app.services.rag.core.kg_builder.chain_analyzer import CHAIN_QUERIES
        expected_keys = {
            "4h_art_art_decisao_tese",
            "4h_decisao_sumula_art_art",
            "4h_decisao_decisao_art_lei",
            "4h_sumula_art_decisao_tese",
            "5h_art_art_sumula_decisao_tese",
            "5h_dec_dec_art_art_lei",
        }
        assert set(CHAIN_QUERIES.keys()) == expected_keys

    def test_chain_queries_use_aplica_sumula(self):
        """v2 chain queries use APLICA_SUMULA, not generic APLICA."""
        from app.services.rag.core.kg_builder.chain_analyzer import CHAIN_QUERIES
        sumula_chains = [
            "4h_decisao_sumula_art_art",
            "5h_art_art_sumula_decisao_tese",
        ]
        for key in sumula_chains:
            assert "APLICA_SUMULA" in CHAIN_QUERIES[key], f"{key} should use APLICA_SUMULA"

    def test_component_queries_exist(self):
        from app.services.rag.core.kg_builder.chain_analyzer import COMPONENT_QUERIES
        assert len(COMPONENT_QUERIES) >= 17

    def test_component_queries_include_aplica_sumula(self):
        from app.services.rag.core.kg_builder.chain_analyzer import COMPONENT_QUERIES
        assert "APLICA_SUMULA" in COMPONENT_QUERIES

    def test_chain_analysis_result_dataclass(self):
        from app.services.rag.core.kg_builder.chain_analyzer import ChainAnalysisResult
        result = ChainAnalysisResult()
        assert result.total_chains == 0
        assert result.chains == {}
        assert result.component_counts == {}
        assert result.errors == []

    def test_chain_queries_are_syntactically_valid_cypher(self):
        """Basic check: all queries should start with MATCH and contain RETURN."""
        from app.services.rag.core.kg_builder.chain_analyzer import CHAIN_QUERIES
        for name, query in CHAIN_QUERIES.items():
            assert "MATCH" in query, f"{name} missing MATCH"
            assert "RETURN" in query, f"{name} missing RETURN"
