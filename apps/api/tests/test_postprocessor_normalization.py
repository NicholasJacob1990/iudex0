"""
Tests for legal_postprocessor normalization functions (Gaps 1-7).

Tests the Python-side normalization ported from fix_normalization.py
and fix_gender.py. Pure unit tests — no Neo4j required.
"""

import pytest


# =============================================================================
# GAP 1: ACCENT NORMALIZATION (§, º, ª)
# =============================================================================


class TestArticleAccentNormalization:
    """Tests for accent char replacement in Artigo names."""

    def test_section_symbol_to_par(self):
        from app.services.rag.core.kg_builder.legal_postprocessor import _normalize_artigo_name
        assert "par." in _normalize_artigo_name("Art. 5§3 do CF")

    def test_ordinal_masculine(self):
        from app.services.rag.core.kg_builder.legal_postprocessor import _normalize_artigo_name
        result = _normalize_artigo_name("Art. 5º do CF")
        assert "º" not in result
        assert "5o" in result

    def test_ordinal_feminine(self):
        from app.services.rag.core.kg_builder.legal_postprocessor import _normalize_artigo_name
        result = _normalize_artigo_name("Art. 1ª do CF")
        assert "ª" not in result
        assert "1a" in result

    def test_combined_accents(self):
        from app.services.rag.core.kg_builder.legal_postprocessor import _normalize_artigo_name
        result = _normalize_artigo_name("Art. 5º §1º do CF")
        assert "º" not in result
        assert "§" not in result


# =============================================================================
# GAP 2: GENDER PREPOSITION NORMALIZATION
# =============================================================================


class TestGenderPrepositionNormalization:
    """Tests for gender preposition fixes (do Lei → da Lei)."""

    def test_do_lei_to_da_lei(self):
        from app.services.rag.core.kg_builder.legal_postprocessor import _normalize_artigo_name
        result = _normalize_artigo_name("Art. 5 do Lei 8666")
        assert "da Lei" in result
        assert "do Lei" not in result

    def test_do_lc_to_da_lc(self):
        from app.services.rag.core.kg_builder.legal_postprocessor import _normalize_artigo_name
        result = _normalize_artigo_name("Art. 10 do LC 123")
        assert "da LC" in result

    def test_do_ec_to_da_ec(self):
        from app.services.rag.core.kg_builder.legal_postprocessor import _normalize_artigo_name
        result = _normalize_artigo_name("Art. 1 do EC 45")
        assert "da EC" in result

    def test_do_lindb_to_da_lindb(self):
        from app.services.rag.core.kg_builder.legal_postprocessor import _normalize_artigo_name
        result = _normalize_artigo_name("Art. 4 do LINDB")
        assert "da LINDB" in result

    def test_do_lrf_to_da_lrf(self):
        from app.services.rag.core.kg_builder.legal_postprocessor import _normalize_artigo_name
        result = _normalize_artigo_name("Art. 17 do LRF")
        assert "da LRF" in result

    def test_masculine_siglas_stay_do(self):
        from app.services.rag.core.kg_builder.legal_postprocessor import _normalize_artigo_name
        result = _normalize_artigo_name("Art. 5 da CF")
        assert "do CF" in result

    def test_cc_stays_masculine(self):
        from app.services.rag.core.kg_builder.legal_postprocessor import _normalize_artigo_name
        result = _normalize_artigo_name("Art. 421 da CC")
        assert "do CC" in result

    def test_na_sigla_to_do(self):
        from app.services.rag.core.kg_builder.legal_postprocessor import _normalize_artigo_name
        result = _normalize_artigo_name("Art. 5 na CPC")
        assert "do CPC" in result


# =============================================================================
# GAP 3: PARAGRAPH / INCISO FORMATTING
# =============================================================================


class TestParagraphIncisoFormatting:
    """Tests for paragraph and inciso normalization."""

    def test_comma_par_to_space_par(self):
        from app.services.rag.core.kg_builder.legal_postprocessor import _normalize_artigo_name
        result = _normalize_artigo_name("Art. 5, par.3o do CF")
        assert ", par." not in result
        assert " par." in result

    def test_par_dot_space_collapsed(self):
        from app.services.rag.core.kg_builder.legal_postprocessor import _normalize_artigo_name
        result = _normalize_artigo_name("Art. 5 par. 3o do CF")
        assert "par.3o" in result

    def test_comma_inc_to_space_inc(self):
        from app.services.rag.core.kg_builder.legal_postprocessor import _normalize_artigo_name
        result = _normalize_artigo_name("Art. 5, inc. X do CF")
        assert ", inc." not in result
        assert " inc." in result

    def test_inciso_word_to_inc(self):
        from app.services.rag.core.kg_builder.legal_postprocessor import _normalize_artigo_name
        result = _normalize_artigo_name("Art. 5 inciso X do CF")
        assert "inciso" not in result
        assert "inc." in result


# =============================================================================
# GAP 4: DECISAO DOT NORMALIZATION
# =============================================================================


class TestDecisaoDotNormalization:
    """Tests for Decisao number dot removal."""

    def test_single_dot_removal(self):
        from app.services.rag.core.kg_builder.legal_postprocessor import _normalize_decisao_name
        assert _normalize_decisao_name("RE 4.650") == "RE 4650"

    def test_double_dot_removal(self):
        from app.services.rag.core.kg_builder.legal_postprocessor import _normalize_decisao_name
        assert _normalize_decisao_name("ADI 4.296.123") == "ADI 4296123"

    def test_repercussao_accent_removal(self):
        from app.services.rag.core.kg_builder.legal_postprocessor import _normalize_decisao_name
        result = _normalize_decisao_name("Repercussão Geral 860")
        assert "Repercussao" in result
        assert "Repercussão" not in result

    def test_numero_removal(self):
        from app.services.rag.core.kg_builder.legal_postprocessor import _normalize_decisao_name
        assert _normalize_decisao_name("ADI nº 5432") == "ADI 5432"

    def test_preserves_normal_name(self):
        from app.services.rag.core.kg_builder.legal_postprocessor import _normalize_decisao_name
        assert _normalize_decisao_name("ADI 2530") == "ADI 2530"


# =============================================================================
# GAP 7: SUMULA NORMALIZATION
# =============================================================================


class TestSumulaNormalization:
    """Tests for Sumula accent normalization."""

    def test_sumula_accent_removal(self):
        from app.services.rag.core.kg_builder.legal_postprocessor import _normalize_sumula_name
        result = _normalize_sumula_name("Súmula 473 do STF")
        assert "Sumula" in result
        assert "Súmula" not in result

    def test_sumula_lowercase_accent(self):
        from app.services.rag.core.kg_builder.legal_postprocessor import _normalize_sumula_name
        result = _normalize_sumula_name("súmula Vinculante 13")
        assert "sumula" in result


# =============================================================================
# GAP 7: LEI COMPLEMENTAR → LC
# =============================================================================


class TestLeiComplementarNormalization:
    """Tests for Lei Complementar → LC normalization."""

    def test_lei_complementar_to_lc(self):
        from app.services.rag.core.kg_builder.legal_postprocessor import _normalize_lei_name
        result = _normalize_lei_name("Lei Complementar 214")
        assert result == "LC 214"

    def test_lei_complementar_with_number(self):
        from app.services.rag.core.kg_builder.legal_postprocessor import _normalize_lei_name
        result = _normalize_lei_name("Lei Complementar 123")
        assert "LC 123" in result

    def test_preserves_lei_ordinaria(self):
        from app.services.rag.core.kg_builder.legal_postprocessor import _normalize_lei_name
        result = _normalize_lei_name("Lei 8666")
        assert result == "Lei 8666"

    def test_lei_name_expansion(self):
        from app.services.rag.core.kg_builder.legal_postprocessor import _normalize_lei_name
        result = _normalize_lei_name("Código Civil")
        assert result == "CC"


# =============================================================================
# TESE NORMALIZATION
# =============================================================================


class TestTeseNormalization:
    """Tests for Tese trailing period removal."""

    def test_trailing_period_removal(self):
        from app.services.rag.core.kg_builder.legal_postprocessor import _normalize_tese_name
        result = _normalize_tese_name("Inconstitucionalidade da norma.")
        assert not result.endswith(".")

    def test_preserves_content(self):
        from app.services.rag.core.kg_builder.legal_postprocessor import _normalize_tese_name
        result = _normalize_tese_name("Tese sem ponto")
        assert result == "Tese sem ponto"

    def test_collapses_spaces(self):
        from app.services.rag.core.kg_builder.legal_postprocessor import _normalize_tese_name
        result = _normalize_tese_name("  Tese   com   espaços  . ")
        assert "  " not in result


# =============================================================================
# NAME EXPANSION COVERAGE
# =============================================================================


class TestNameExpansions:
    """Tests for code name expansions in Artigo normalization."""

    def test_constituicao_to_cf(self):
        from app.services.rag.core.kg_builder.legal_postprocessor import _normalize_artigo_name
        assert "CF" in _normalize_artigo_name("Art. 5 do Constituição Federal")

    def test_codigo_civil_to_cc(self):
        from app.services.rag.core.kg_builder.legal_postprocessor import _normalize_artigo_name
        assert "CC" in _normalize_artigo_name("Art. 421 do Código Civil")

    def test_cpc_expansion(self):
        from app.services.rag.core.kg_builder.legal_postprocessor import _normalize_artigo_name
        assert "CPC" in _normalize_artigo_name("Art. 300 do Código de Processo Civil")

    def test_clt_expansion(self):
        from app.services.rag.core.kg_builder.legal_postprocessor import _normalize_artigo_name
        assert "CLT" in _normalize_artigo_name("Art. 1 do Consolidação das Leis do Trabalho")

    def test_crfb_to_cf(self):
        from app.services.rag.core.kg_builder.legal_postprocessor import _normalize_artigo_name
        assert "CF" in _normalize_artigo_name("Art. 5 do CRFB")

    def test_numero_removal(self):
        from app.services.rag.core.kg_builder.legal_postprocessor import _normalize_artigo_name
        result = _normalize_artigo_name("Art. nº 5 do CF")
        assert "nº" not in result

    def test_trailing_period_removed(self):
        from app.services.rag.core.kg_builder.legal_postprocessor import _normalize_artigo_name
        result = _normalize_artigo_name("Art. 5 do CF.")
        assert not result.endswith(".")

    def test_trailing_period_preserved_for_par(self):
        from app.services.rag.core.kg_builder.legal_postprocessor import _normalize_artigo_name
        result = _normalize_artigo_name("Art. 5 par.")
        assert result.endswith("par.")


# =============================================================================
# INTEGRATION: FULL NORMALIZATION PIPELINE
# =============================================================================


class TestFullNormalizationPipeline:
    """Integration-style tests combining multiple normalizations."""

    def test_complex_artigo(self):
        from app.services.rag.core.kg_builder.legal_postprocessor import _normalize_artigo_name
        result = _normalize_artigo_name("Art. 5º, §1º, inciso X da Constituição Federal")
        assert "5o" in result
        assert "par.1o" in result
        assert "inc." in result
        assert "CF" in result
        assert "do CF" in result  # feminine→masculine for sigla

    def test_no_change_on_clean_name(self):
        from app.services.rag.core.kg_builder.legal_postprocessor import _normalize_artigo_name
        clean = "Art. 5 do CF"
        assert _normalize_artigo_name(clean) == clean

    def test_decisao_full_pipeline(self):
        from app.services.rag.core.kg_builder.legal_postprocessor import _normalize_decisao_name
        result = _normalize_decisao_name("RE nº 1.234.567 - Repercussão Geral")
        assert "nº" not in result
        assert "1234567" in result
        assert "Repercussao" in result


# =============================================================================
# CONSTANTS VALIDATION
# =============================================================================


class TestNormalizationConstants:
    """Tests that normalization constants are properly defined."""

    def test_siglas_all_has_minimum(self):
        from app.services.rag.core.kg_builder.legal_postprocessor import _SIGLAS_ALL
        assert len(_SIGLAS_ALL) >= 10
        assert "CF" in _SIGLAS_ALL
        assert "CC" in _SIGLAS_ALL
        assert "CPC" in _SIGLAS_ALL

    def test_name_expansions_has_core(self):
        from app.services.rag.core.kg_builder.legal_postprocessor import _NAME_EXPANSIONS
        shorts = {short for _, short in _NAME_EXPANSIONS}
        assert "CF" in shorts
        assert "CC" in shorts
        assert "CPC" in shorts
        assert "CLT" in shorts

    def test_gender_fixes_has_lei(self):
        from app.services.rag.core.kg_builder.legal_postprocessor import _GENDER_FIXES
        wrongs = {wrong for wrong, _ in _GENDER_FIXES}
        assert any("Lei" in w for w in wrongs)
        assert any("LC" in w for w in wrongs)
        assert any("EC" in w for w in wrongs)

    def test_infra_rel_types(self):
        from app.services.rag.core.kg_builder.legal_postprocessor import _INFRA_REL_TYPES
        assert "FROM_CHUNK" in _INFRA_REL_TYPES
        assert "FROM_DOCUMENT" in _INFRA_REL_TYPES
        assert "NEXT_CHUNK" in _INFRA_REL_TYPES


# =============================================================================
# STATS FIELDS
# =============================================================================


class TestNewStatsFields:
    """Tests that new stats fields exist in LegalPostProcessStats."""

    def test_stats_has_new_fields(self):
        from app.services.rag.core.kg_builder.legal_postprocessor import LegalPostProcessStats
        stats = LegalPostProcessStats()
        assert hasattr(stats, "decisao_python_normalized")
        assert hasattr(stats, "sumula_python_normalized")
        assert hasattr(stats, "lei_python_normalized")
        assert hasattr(stats, "tese_python_normalized")
        assert hasattr(stats, "relationships_deduped")
        assert hasattr(stats, "garbage_artigo_removed")

    def test_stats_defaults_to_zero(self):
        from app.services.rag.core.kg_builder.legal_postprocessor import LegalPostProcessStats
        stats = LegalPostProcessStats()
        assert stats.decisao_python_normalized == 0
        assert stats.relationships_deduped == 0
        assert stats.garbage_artigo_removed == 0
