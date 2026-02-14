"""
Tests for Factual Relationship Pattern-Based Extraction (Opção B).

Tests the deterministic regex patterns that create PARTICIPA_DE, REPRESENTA
relationships in the KG Builder pipeline.

No external dependencies required (pure unit tests).
"""

import re

import pytest


# =============================================================================
# TRIGGER LISTS
# =============================================================================


class TestFactualTriggerLists:
    """Tests for PARTICIPA and REPRESENTA trigger completeness."""

    def test_participa_triggers_include_core_roles(self):
        from app.services.rag.core.kg_builder.pipeline import _PARTICIPA_TRIGGERS
        core = {"autor", "autora", "réu", "ré", "reu", "reclamante", "reclamado"}
        for role in core:
            assert role in _PARTICIPA_TRIGGERS, f"Missing core role: {role}"

    def test_participa_triggers_include_appeal_roles(self):
        from app.services.rag.core.kg_builder.pipeline import _PARTICIPA_TRIGGERS
        appeal = {"apelante", "apelado", "agravante", "agravado"}
        for role in appeal:
            assert role in _PARTICIPA_TRIGGERS, f"Missing appeal role: {role}"

    def test_participa_triggers_include_execution_roles(self):
        from app.services.rag.core.kg_builder.pipeline import _PARTICIPA_TRIGGERS
        execution = {"exequente", "executado", "embargante", "embargado"}
        for role in execution:
            assert role in _PARTICIPA_TRIGGERS, f"Missing execution role: {role}"

    def test_participa_triggers_minimum_count(self):
        from app.services.rag.core.kg_builder.pipeline import _PARTICIPA_TRIGGERS
        assert len(_PARTICIPA_TRIGGERS) >= 20

    def test_representa_triggers_include_core(self):
        from app.services.rag.core.kg_builder.pipeline import _REPRESENTA_TRIGGERS
        core = {"advogado", "advogada", "procurador", "defensor"}
        for role in core:
            assert role in _REPRESENTA_TRIGGERS, f"Missing core: {role}"

    def test_representa_triggers_include_representante_legal(self):
        from app.services.rag.core.kg_builder.pipeline import _REPRESENTA_TRIGGERS
        assert "representante legal" in _REPRESENTA_TRIGGERS


# =============================================================================
# PESSOA_ROLE REGEX
# =============================================================================


class TestPessoaRoleRegex:
    """Tests for the _PESSOA_ROLE_RE name+role regex."""

    def test_captures_nome_comma_autor(self):
        from app.services.rag.core.kg_builder.pipeline import _PESSOA_ROLE_RE
        text = "João da Silva, autor neste processo"
        match = _PESSOA_ROLE_RE.search(text)
        assert match is not None
        assert match.group(1).strip() == "João da Silva"
        assert match.group(2).strip().lower() == "autor"

    def test_captures_nome_comma_reu(self):
        from app.services.rag.core.kg_builder.pipeline import _PESSOA_ROLE_RE
        text = "Maria José Santos, réu"
        match = _PESSOA_ROLE_RE.search(text)
        assert match is not None
        assert match.group(1).strip() == "Maria José Santos"
        assert match.group(2).strip() == "réu"

    def test_captures_nome_parenthesis_role(self):
        from app.services.rag.core.kg_builder.pipeline import _PESSOA_ROLE_RE
        text = "Carlos Eduardo Pereira (reclamante)"
        match = _PESSOA_ROLE_RE.search(text)
        assert match is not None
        assert match.group(1).strip() == "Carlos Eduardo Pereira"
        assert match.group(2).strip() == "reclamante"

    def test_captures_nome_with_preposition(self):
        from app.services.rag.core.kg_builder.pipeline import _PESSOA_ROLE_RE
        text = "Ana de Souza, autora da ação"
        match = _PESSOA_ROLE_RE.search(text)
        assert match is not None
        assert "Ana de Souza" in match.group(1)

    def test_ignores_lowercase_names(self):
        from app.services.rag.core.kg_builder.pipeline import _PESSOA_ROLE_RE
        text = "o autor mencionou que"
        match = _PESSOA_ROLE_RE.search(text)
        assert match is None

    def test_ignores_single_word_names(self):
        from app.services.rag.core.kg_builder.pipeline import _PESSOA_ROLE_RE
        text = "João, autor"
        match = _PESSOA_ROLE_RE.search(text)
        # Single word "João" doesn't match (requires at least 2 capitalized words)
        assert match is None

    def test_captures_testemunha(self):
        from app.services.rag.core.kg_builder.pipeline import _PESSOA_ROLE_RE
        text = "Pedro Henrique Oliveira, testemunha ouvida"
        match = _PESSOA_ROLE_RE.search(text)
        assert match is not None
        assert match.group(2).strip().lower() == "testemunha"

    def test_captures_perito(self):
        from app.services.rag.core.kg_builder.pipeline import _PESSOA_ROLE_RE
        text = "Luís Fernando Costa - perito nomeado"
        match = _PESSOA_ROLE_RE.search(text)
        assert match is not None
        assert match.group(1).strip() == "Luís Fernando Costa"
        assert match.group(2).strip() == "perito"

    def test_captures_re_feminine(self):
        from app.services.rag.core.kg_builder.pipeline import _PESSOA_ROLE_RE
        text = "Fernanda Moreira, ré na lide"
        match = _PESSOA_ROLE_RE.search(text)
        assert match is not None
        assert match.group(1).strip() == "Fernanda Moreira"
        assert match.group(2).strip() == "ré"

    def test_captures_multi_preposition_name(self):
        from app.services.rag.core.kg_builder.pipeline import _PESSOA_ROLE_RE
        text = "Maria José da Silva Santos, apelante no recurso"
        match = _PESSOA_ROLE_RE.search(text)
        assert match is not None
        assert match.group(1).strip() == "Maria José da Silva Santos"
        assert match.group(2).strip() == "apelante"


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


class TestHelperFunctions:
    """Tests for _slugify_name and _extract_evidence."""

    def test_slugify_basic_name(self):
        from app.services.rag.core.kg_builder.pipeline import _slugify_name
        assert _slugify_name("João da Silva") == "joao_da_silva"

    def test_slugify_accented_name(self):
        from app.services.rag.core.kg_builder.pipeline import _slugify_name
        assert _slugify_name("José Antônio Müller") == "jose_antonio_muller"

    def test_slugify_preserves_structure(self):
        from app.services.rag.core.kg_builder.pipeline import _slugify_name
        slug = _slugify_name("Maria de Fátima dos Santos")
        assert "maria" in slug
        assert "santos" in slug

    def test_extract_evidence_center(self):
        from app.services.rag.core.kg_builder.pipeline import _extract_evidence
        text = "a" * 200
        evidence = _extract_evidence(text, 100, max_len=40)
        assert len(evidence) <= 40

    def test_extract_evidence_start(self):
        from app.services.rag.core.kg_builder.pipeline import _extract_evidence
        text = "início do texto e mais conteúdo aqui"
        evidence = _extract_evidence(text, 0, max_len=20)
        assert evidence.startswith("início")

    def test_extract_evidence_end(self):
        from app.services.rag.core.kg_builder.pipeline import _extract_evidence
        text = "conteúdo relevante no final"
        evidence = _extract_evidence(text, len(text) - 5, max_len=20)
        assert "final" in evidence


# =============================================================================
# STATS FIELDS
# =============================================================================


class TestFactualStatsFields:
    """Tests that factual stats fields are initialized."""

    def test_stats_has_factual_participa_links(self):
        """Verify the pipeline stats dict includes factual fields."""
        # We can't easily run the full pipeline, but we can check
        # the stats dict is built with the right keys by importing
        # and checking the source.
        from app.services.rag.core.kg_builder import pipeline
        import inspect
        source = inspect.getsource(pipeline._run_regex_extraction)
        assert "factual_participa_links" in source
        assert "factual_representa_links" in source
        assert "factual_oab_processo_links" in source
        assert "factual_pessoa_by_name" in source


# =============================================================================
# DIMENSION AND SCHEMA INTEGRATION
# =============================================================================


class TestFactualSchemaIntegration:
    """Tests that factual relationship types are in the schema."""

    def test_participa_de_in_schema(self):
        from app.services.rag.core.kg_builder.legal_schema import LEGAL_RELATIONSHIP_TYPES
        labels = {rt["label"] for rt in LEGAL_RELATIONSHIP_TYPES}
        assert "PARTICIPA_DE" in labels

    def test_representa_in_schema(self):
        from app.services.rag.core.kg_builder.legal_schema import LEGAL_RELATIONSHIP_TYPES
        labels = {rt["label"] for rt in LEGAL_RELATIONSHIP_TYPES}
        assert "REPRESENTA" in labels

    def test_parte_de_in_schema(self):
        from app.services.rag.core.kg_builder.legal_schema import LEGAL_RELATIONSHIP_TYPES
        labels = {rt["label"] for rt in LEGAL_RELATIONSHIP_TYPES}
        assert "PARTE_DE" in labels

    def test_factual_patterns_exist(self):
        from app.services.rag.core.kg_builder.legal_schema import LEGAL_PATTERNS
        patterns = set(LEGAL_PATTERNS)
        assert ("Pessoa", "PARTICIPA_DE", "Processo") in patterns
        assert ("Actor", "REPRESENTA", "Pessoa") in patterns
        assert ("Actor", "REPRESENTA", "Empresa") in patterns
        assert ("Empresa", "PARTICIPA_DE", "Processo") in patterns
