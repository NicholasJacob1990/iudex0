"""
Testes para extração de citações jurídicas compostas (CompoundCitation).

Cobre:
- Citações simples (backward compatibility)
- Citações compostas em diversos formatos
- Casos especiais: parágrafo único, caput, numerais romanos
- Padrão invertido (Art. X da Lei Y)
- Normalização de IDs
- Integração com grounding
"""

import pytest
import sys
import os

# Adiciona o diretório raiz da API ao path para imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.rag.core.neo4j_mvp import (
    CompoundCitation,
    LegalEntityExtractor,
)


# =============================================================================
# Testes de backward compatibility (extração simples)
# =============================================================================


class TestSimpleExtractionBackwardCompat:
    """Garante que a extração simples existente continua funcionando."""

    def test_extract_lei(self):
        text = "Conforme a Lei 8.666/1993, as licitações..."
        entities = LegalEntityExtractor.extract(text)
        lei = [e for e in entities if e["entity_type"] == "lei"]
        assert len(lei) >= 1
        assert lei[0]["entity_id"] == "lei_8666_1993"

    def test_extract_artigo_simples(self):
        text = "O Art. 5º da Constituição Federal garante..."
        entities = LegalEntityExtractor.extract(text)
        arts = [e for e in entities if e["entity_type"] == "artigo"]
        assert len(arts) >= 1
        assert arts[0]["entity_id"] == "art_5"

    def test_extract_sumula(self):
        text = "A Súmula 331 do TST estabelece..."
        entities = LegalEntityExtractor.extract(text)
        sumulas = [e for e in entities if e["entity_type"] == "sumula"]
        assert len(sumulas) >= 1
        assert sumulas[0]["entity_id"] == "sumula_TST_331"

    def test_extract_tribunal(self):
        text = "O STF decidiu que..."
        entities = LegalEntityExtractor.extract(text)
        tribunais = [e for e in entities if e["entity_type"] == "tribunal"]
        assert len(tribunais) >= 1
        assert tribunais[0]["entity_id"] == "tribunal_STF"

    def test_extract_tema(self):
        text = "O Tema 1234 do STF é relevante."
        entities = LegalEntityExtractor.extract(text)
        temas = [e for e in entities if e["entity_type"] == "tema"]
        assert len(temas) >= 1
        assert temas[0]["entity_id"] == "tema_STF_1234"

    def test_extract_empty_text(self):
        assert LegalEntityExtractor.extract("") == []
        assert LegalEntityExtractor.extract("   ") == []

    def test_extract_no_entities(self):
        text = "Este é um texto qualquer sem referências jurídicas."
        entities = LegalEntityExtractor.extract(text)
        assert entities == []


# =============================================================================
# Testes de extração composta
# =============================================================================


class TestCompoundCitationExtraction:
    """Testes para extração de citações compostas."""

    def test_lei_artigo_paragrafo_inciso(self):
        """Teste principal: Lei + Art + § + inciso."""
        text = "Conforme a Lei 8.666/1993, Art. 23, § 1º, inciso II, as licitações..."
        citations = LegalEntityExtractor.extract_compound_citations(text)
        assert len(citations) >= 1
        c = citations[0]
        assert c.law == "Lei 8.666/1993"
        assert c.article == "Art. 23"
        assert c.paragraph is not None
        assert "1" in c.paragraph
        assert c.inciso == "inciso II"
        assert c.code is None
        assert "lei" in c.normalized_id
        assert "art_23" in c.normalized_id
        assert "inc_ii" in c.normalized_id

    def test_codigo_artigo(self):
        """Teste com código abreviado."""
        text = "O CPC, Art. 1015, parágrafo único, dispõe..."
        citations = LegalEntityExtractor.extract_compound_citations(text)
        assert len(citations) >= 1
        c = citations[0]
        assert c.code == "CPC"
        assert c.article == "Art. 1015"
        assert c.paragraph == "parágrafo único"
        assert c.law is None
        assert "cpc" in c.normalized_id
        assert "pu" in c.normalized_id

    def test_clt_artigo_paragrafo(self):
        """CLT com artigo e parágrafo."""
        text = "A CLT, Art. 477, § 8º, determina o pagamento..."
        citations = LegalEntityExtractor.extract_compound_citations(text)
        assert len(citations) >= 1
        c = citations[0]
        assert c.code == "CLT"
        assert c.article == "Art. 477"
        assert c.paragraph is not None
        assert "8" in c.paragraph
        assert "clt" in c.normalized_id
        assert "art_477" in c.normalized_id
        assert "p8" in c.normalized_id

    def test_artigo_caput_da_cf(self):
        """Padrão invertido: Art. X, caput, da CF."""
        text = "O Art. 5º, caput, da Constituição Federal garante..."
        citations = LegalEntityExtractor.extract_compound_citations(text)
        assert len(citations) >= 1
        c = citations[0]
        assert c.article == "Art. 5"
        assert c.paragraph == "caput"
        assert c.code == "CF"
        assert "caput" in c.normalized_id

    def test_artigo_da_lei(self):
        """Padrão invertido: Art. X da Lei Y."""
        text = "O Art. 186 da Lei 10406/2002 trata da responsabilidade..."
        citations = LegalEntityExtractor.extract_compound_citations(text)
        assert len(citations) >= 1
        c = citations[0]
        assert c.article == "Art. 186"
        assert c.law is not None
        assert "10406" in c.law

    def test_lei_com_ano_2_digitos(self):
        """Lei com ano de 2 dígitos deve normalizar."""
        text = "Lei 8666/93, Art. 23, dispõe sobre licitações."
        citations = LegalEntityExtractor.extract_compound_citations(text)
        assert len(citations) >= 1
        c = citations[0]
        assert c.law == "Lei 8666/1993"

    def test_inciso_romano(self):
        """Numerais romanos no inciso."""
        text = "Lei 8112/1990, Art. 116, inciso III, prevê os deveres."
        citations = LegalEntityExtractor.extract_compound_citations(text)
        assert len(citations) >= 1
        c = citations[0]
        assert c.inciso == "inciso III"
        assert "inc_iii" in c.normalized_id

    def test_alinea(self):
        """Citação com alínea."""
        text = "CPC, Art. 525, § 1º, inciso III, alínea 'a', trata da impugnação."
        citations = LegalEntityExtractor.extract_compound_citations(text)
        assert len(citations) >= 1
        c = citations[0]
        assert c.alinea is not None
        assert "a" in c.alinea.lower()
        assert "al_a" in c.normalized_id

    def test_paragrafo_unico(self):
        """Parágrafo único em diferentes grafias."""
        text = "CDC, Art. 18, parágrafo único, estabelece..."
        citations = LegalEntityExtractor.extract_compound_citations(text)
        assert len(citations) >= 1
        c = citations[0]
        assert c.paragraph == "parágrafo único"
        assert "pu" in c.normalized_id

    def test_empty_text(self):
        """Texto vazio retorna lista vazia."""
        assert LegalEntityExtractor.extract_compound_citations("") == []
        assert LegalEntityExtractor.extract_compound_citations("   ") == []

    def test_no_compound_citations(self):
        """Texto sem citações compostas."""
        text = "Este texto fala sobre direito civil de forma genérica."
        citations = LegalEntityExtractor.extract_compound_citations(text)
        assert citations == []

    def test_multiple_citations(self):
        """Múltiplas citações compostas no mesmo texto."""
        text = (
            "Conforme a Lei 8.666/1993, Art. 23, § 1º, e também "
            "o CPC, Art. 300, inciso I, é necessário..."
        )
        citations = LegalEntityExtractor.extract_compound_citations(text)
        assert len(citations) >= 2

    def test_deduplication(self):
        """Citações duplicadas devem ser deduplicadas."""
        text = (
            "A Lei 8.666/1993, Art. 23 e novamente a Lei 8.666/1993, Art. 23 reforçam..."
        )
        citations = LegalEntityExtractor.extract_compound_citations(text)
        ids = [c.normalized_id for c in citations]
        assert len(ids) == len(set(ids)), "Citações duplicadas não foram deduplicadas"


# =============================================================================
# Testes de normalização de IDs
# =============================================================================


class TestNormalizedId:
    """Testes para normalização dos IDs compostos."""

    def test_normalized_id_lei_completa(self):
        text = "Lei 8.666/1993, Art. 23, § 1º, inciso II"
        citations = LegalEntityExtractor.extract_compound_citations(text)
        assert len(citations) >= 1
        nid = citations[0].normalized_id
        # Deve conter todos os componentes normalizados
        assert "art_23" in nid
        assert "p1" in nid
        assert "inc_ii" in nid

    def test_normalized_id_codigo(self):
        text = "CLT, Art. 477, § 8º"
        citations = LegalEntityExtractor.extract_compound_citations(text)
        assert len(citations) >= 1
        nid = citations[0].normalized_id
        assert nid.startswith("clt_")
        assert "art_477" in nid
        assert "p8" in nid

    def test_normalized_id_caput(self):
        text = "CF, Art. 5, caput"
        citations = LegalEntityExtractor.extract_compound_citations(text)
        assert len(citations) >= 1
        assert "caput" in citations[0].normalized_id


# =============================================================================
# Testes de CompoundCitation dataclass
# =============================================================================


class TestCompoundCitationModel:
    """Testes do modelo CompoundCitation."""

    def test_to_dict(self):
        cc = CompoundCitation(
            full_text="Lei 8.666/1993, Art. 23, § 1º",
            law="Lei 8.666/1993",
            code=None,
            article="Art. 23",
            paragraph="§ 1º",
            inciso=None,
            alinea=None,
            normalized_id="lei_8666_1993_art_23_p1",
        )
        d = cc.to_dict()
        assert d["full_text"] == "Lei 8.666/1993, Art. 23, § 1º"
        assert d["law"] == "Lei 8.666/1993"
        assert d["code"] is None
        assert d["article"] == "Art. 23"
        assert d["paragraph"] == "§ 1º"
        assert d["normalized_id"] == "lei_8666_1993_art_23_p1"

    def test_fields_optional(self):
        cc = CompoundCitation(
            full_text="CF, Art. 5",
            law=None,
            code="CF",
            article="Art. 5",
            paragraph=None,
            inciso=None,
            alinea=None,
            normalized_id="cf_art_5",
        )
        assert cc.law is None
        assert cc.paragraph is None
        assert cc.inciso is None
        assert cc.alinea is None


# =============================================================================
# Testes de extract_all (método unificado)
# =============================================================================


class TestExtractAll:
    """Testes para o método unificado extract_all."""

    def test_extract_all_returns_all_keys(self):
        text = "A Lei 8.666/1993, Art. 23, c/c art. 24, dispõe sobre licitações."
        result = LegalEntityExtractor.extract_all(text)
        assert "entities" in result
        assert "compound_citations" in result
        assert "remissions" in result

    def test_extract_all_entities_present(self):
        text = "Lei 8.666/1993, Art. 23"
        result = LegalEntityExtractor.extract_all(text)
        # Deve ter entidades simples
        assert len(result["entities"]) > 0

    def test_extract_all_compound_present(self):
        text = "Lei 8.666/1993, Art. 23, § 1º"
        result = LegalEntityExtractor.extract_all(text)
        assert len(result["compound_citations"]) > 0


# =============================================================================
# Testes de code normalization
# =============================================================================


class TestCodeNormalization:
    """Testes para normalização de códigos jurídicos."""

    @pytest.mark.parametrize("code_input,expected", [
        ("CF", "CF"),
        ("CPC", "CPC"),
        ("CLT", "CLT"),
        ("CDC", "CDC"),
        ("CC", "CC"),
        ("CP", "CP"),
        ("CPP", "CPP"),
        ("CTB", "CTB"),
        ("CTN", "CTN"),
        ("ECA", "ECA"),
    ])
    def test_code_normalization(self, code_input, expected):
        assert LegalEntityExtractor._normalize_code(code_input) == expected

    def test_constituicao_federal_normalizes_to_cf(self):
        assert LegalEntityExtractor._normalize_code("Constituição Federal") == "CF"

    def test_consolidacao_leis_trabalho_normalizes_to_clt(self):
        assert LegalEntityExtractor._normalize_code("consolidação das leis do trabalho") == "CLT"


# =============================================================================
# Testes de edge cases com numerais romanos
# =============================================================================


class TestRomanNumerals:
    """Testes para tratamento de numerais romanos."""

    @pytest.mark.parametrize("roman,expected", [
        ("I", "i"),
        ("II", "ii"),
        ("III", "iii"),
        ("IV", "iv"),
        ("V", "v"),
        ("IX", "ix"),
        ("X", "x"),
        ("XLII", "xlii"),
    ])
    def test_roman_normalization(self, roman, expected):
        assert LegalEntityExtractor._normalize_roman(roman) == expected
