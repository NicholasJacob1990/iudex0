"""Tests for entity extraction and contextual prefixes."""

from neo4j_rag.ingest.graph_builder import _extract_entities_from_chunk, _normalize_lei_name
from neo4j_rag.ingest.contextual import build_context_prefix_regex
from neo4j_rag.models import EntityType


class TestEntityExtraction:
    def test_extracts_artigo_with_lei(self, sample_jurisprudencia_text):
        entities = _extract_entities_from_chunk(sample_jurisprudencia_text)
        artigos = [e for e in entities if e.entity_type == EntityType.ARTIGO]
        assert len(artigos) >= 1
        # Should find Art. 150 do CTN
        names = [a.name for a in artigos]
        assert any("150" in n and "CTN" in n for n in names)

    def test_extracts_sumula(self, sample_jurisprudencia_text):
        entities = _extract_entities_from_chunk(sample_jurisprudencia_text)
        sumulas = [e for e in entities if e.entity_type == EntityType.SUMULA]
        assert len(sumulas) >= 1
        assert any("435" in s.name for s in sumulas)

    def test_extracts_decisao(self, sample_jurisprudencia_text):
        entities = _extract_entities_from_chunk(sample_jurisprudencia_text)
        decisoes = [e for e in entities if e.entity_type == EntityType.DECISAO]
        assert len(decisoes) >= 1
        assert any("574706" in d.name for d in decisoes)

    def test_extracts_tema(self, sample_jurisprudencia_text):
        entities = _extract_entities_from_chunk(sample_jurisprudencia_text)
        temas = [e for e in entities if e.entity_type == EntityType.TEMA]
        assert len(temas) >= 1
        assert any("69" in t.name for t in temas)

    def test_creates_lei_for_artigo(self, sample_legislacao_text):
        entities = _extract_entities_from_chunk(
            "nos termos do Art. 150 do CTN"
        )
        leis = [e for e in entities if e.entity_type == EntityType.LEI]
        assert any("CTN" in l.name for l in leis)

    def test_no_orphan_artigos(self):
        """Art without Lei reference should still have lei_pai from context."""
        text = "Art. 37 da CF estabelece os princípios da administração pública."
        entities = _extract_entities_from_chunk(text)
        artigos = [e for e in entities if e.entity_type == EntityType.ARTIGO]
        assert len(artigos) == 1
        assert "CF" in artigos[0].name


class TestNormalization:
    def test_normalize_cf(self):
        assert _normalize_lei_name("Constituição Federal") == "CF"
        assert _normalize_lei_name("constituicao federal") == "CF"
        assert _normalize_lei_name("CRFB") == "CF"

    def test_normalize_ctn(self):
        assert _normalize_lei_name("Código Tributário Nacional") == "CTN"

    def test_passthrough_unknown(self):
        assert _normalize_lei_name("Lei 8.112/1990") == "Lei 8.112/1990"


class TestContextualPrefix:
    def test_extracts_artigo_reference(self):
        text = "O Art. 150 do CTN prevê a obrigatoriedade..."
        prefix = build_context_prefix_regex(text)
        assert "Art. 150" in prefix
        assert "CTN" in prefix

    def test_extracts_multiple_refs(self):
        text = (
            "Conforme Art. 150 do CTN e Art. 5 da CF, os princípios..."
        )
        prefix = build_context_prefix_regex(text)
        assert "150" in prefix
        assert "CTN" in prefix

    def test_empty_for_no_refs(self):
        text = "Este é um texto sem referências normativas específicas."
        prefix = build_context_prefix_regex(text)
        assert prefix == ""
