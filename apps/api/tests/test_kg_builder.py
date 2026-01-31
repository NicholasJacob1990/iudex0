"""
Tests for KG Builder — Phase 2 of GraphRAG maturity plan.

Tests legal schema, regex extractor component, fuzzy resolver normalization,
and pipeline configuration.
"""

import asyncio
import pytest
from typing import Dict, Any, List


class TestLegalSchema:
    """Tests for legal_schema.py — schema definition for Brazilian legal domain."""

    def test_schema_importable(self):
        from app.services.rag.core.kg_builder.legal_schema import (
            LEGAL_NODE_TYPES,
            LEGAL_RELATIONSHIP_TYPES,
            LEGAL_PATTERNS,
            build_legal_schema,
        )
        assert LEGAL_NODE_TYPES is not None
        assert LEGAL_RELATIONSHIP_TYPES is not None
        assert LEGAL_PATTERNS is not None

    def test_node_types_cover_legal_entities(self):
        from app.services.rag.core.kg_builder.legal_schema import LEGAL_NODE_TYPES

        labels = {n["label"] for n in LEGAL_NODE_TYPES}
        required = {"Lei", "Artigo", "Sumula", "Tribunal", "Processo", "Tema"}
        assert required.issubset(labels), f"Missing node types: {required - labels}"

    def test_node_types_cover_argument_entities(self):
        from app.services.rag.core.kg_builder.legal_schema import LEGAL_NODE_TYPES

        labels = {n["label"] for n in LEGAL_NODE_TYPES}
        required = {"Claim", "Evidence", "Actor", "Issue"}
        assert required.issubset(labels), f"Missing argument node types: {required - labels}"

    def test_relationship_types_cover_core_and_argument(self):
        from app.services.rag.core.kg_builder.legal_schema import LEGAL_RELATIONSHIP_TYPES

        labels = {r["label"] for r in LEGAL_RELATIONSHIP_TYPES}
        core = {"MENTIONS", "RELATED_TO", "CITA", "FUNDAMENTA"}
        argument = {"SUPPORTS", "OPPOSES", "EVIDENCES", "ARGUES", "RAISES"}
        assert core.issubset(labels), f"Missing core relationship types: {core - labels}"
        assert argument.issubset(labels), f"Missing argument types: {argument - labels}"

    def test_patterns_are_valid_triplets(self):
        from app.services.rag.core.kg_builder.legal_schema import (
            LEGAL_NODE_TYPES,
            LEGAL_RELATIONSHIP_TYPES,
            LEGAL_PATTERNS,
        )

        node_labels = {n["label"] for n in LEGAL_NODE_TYPES}
        rel_labels = {r["label"] for r in LEGAL_RELATIONSHIP_TYPES}

        for src, rel, tgt in LEGAL_PATTERNS:
            assert src in node_labels, f"Pattern source {src} not in node types"
            assert rel in rel_labels, f"Pattern relationship {rel} not in relationship types"
            assert tgt in node_labels, f"Pattern target {tgt} not in node types"

    def test_build_legal_schema_returns_valid_dict(self):
        from app.services.rag.core.kg_builder.legal_schema import build_legal_schema

        schema = build_legal_schema()
        assert "node_types" in schema
        assert "relationship_types" in schema
        assert "patterns" in schema
        assert schema.get("additional_node_types") is False


class TestLegalRegexExtractor:
    """Tests for legal_extractor.py — Component wrapping LegalEntityExtractor."""

    def test_extractor_importable(self):
        from app.services.rag.core.kg_builder.legal_extractor import LegalRegexExtractor
        assert LegalRegexExtractor is not None

    @pytest.mark.asyncio
    async def test_extract_from_chunks(self):
        from app.services.rag.core.kg_builder.legal_extractor import LegalRegexExtractor

        extractor = LegalRegexExtractor(create_relationships=True)
        chunks = [
            {
                "chunk_uid": "test_001",
                "text": "Art. 5º da CF/88 e Lei 8.666/93 são fundamentais. Súmula 331 do TST.",
            },
        ]
        result = await extractor.run(chunks)
        assert len(result.nodes) >= 3, "Should extract at least Art, Lei, Sumula"
        labels = {n["label"] for n in result.nodes}
        assert "Artigo" in labels
        assert "Lei" in labels
        assert "Sumula" in labels

    @pytest.mark.asyncio
    async def test_extract_creates_relationships(self):
        from app.services.rag.core.kg_builder.legal_extractor import LegalRegexExtractor

        extractor = LegalRegexExtractor(create_relationships=True)
        chunks = [
            {
                "chunk_uid": "test_002",
                "text": "Art. 37 da Lei 8.666/93 e Súmula 473 do STF",
            },
        ]
        result = await extractor.run(chunks)
        # Should have MENTIONS relationships
        mention_rels = [r for r in result.relationships if r["type"] == "MENTIONS"]
        assert len(mention_rels) >= 1, "Should create MENTIONS relationships"
        # Should have RELATED_TO co-occurrence relationships
        related_rels = [r for r in result.relationships if r["type"] == "RELATED_TO"]
        assert len(related_rels) >= 1, "Should create co-occurrence RELATED_TO relationships"

    @pytest.mark.asyncio
    async def test_extract_empty_chunks(self):
        from app.services.rag.core.kg_builder.legal_extractor import LegalRegexExtractor

        extractor = LegalRegexExtractor()
        result = await extractor.run([])
        assert len(result.nodes) == 0
        assert len(result.relationships) == 0

    @pytest.mark.asyncio
    async def test_extract_deduplicates_nodes(self):
        from app.services.rag.core.kg_builder.legal_extractor import LegalRegexExtractor

        extractor = LegalRegexExtractor(create_relationships=False)
        chunks = [
            {"chunk_uid": "c1", "text": "Lei 8.666/93 é importante"},
            {"chunk_uid": "c2", "text": "A Lei 8.666/93 estabelece normas"},
        ]
        result = await extractor.run(chunks)
        ids = [n["id"] for n in result.nodes]
        assert len(ids) == len(set(ids)), "Nodes should be deduplicated"

    def test_entity_type_to_label_mapping(self):
        from app.services.rag.core.kg_builder.legal_extractor import _entity_type_to_label

        assert _entity_type_to_label("lei") == "Lei"
        assert _entity_type_to_label("artigo") == "Artigo"
        assert _entity_type_to_label("sumula") == "Sumula"
        assert _entity_type_to_label("tribunal") == "Tribunal"
        assert _entity_type_to_label("unknown") == "Entity"


class TestFuzzyResolverNormalization:
    """Tests for fuzzy_resolver.py — legal text normalization."""

    def test_normalize_lei_variations(self):
        from app.services.rag.core.kg_builder.fuzzy_resolver import _normalize_legal

        # "Lei 8.666/93" and "Lei nº 8.666, de 21 de junho de 1993" should be similar
        n1 = _normalize_legal("Lei 8.666/93")
        n2 = _normalize_legal("Lei nº 8.666/93")
        # Both should have numbers "8666" and "93"
        assert "8666" in n1
        assert "8666" in n2

    def test_normalize_artigo_variations(self):
        from app.services.rag.core.kg_builder.fuzzy_resolver import _normalize_legal

        n1 = _normalize_legal("Art. 5º")
        n2 = _normalize_legal("Artigo 5")
        # Both should normalize to something with "art" and "5"
        assert "art" in n1
        assert "art" in n2
        assert "5" in n1
        assert "5" in n2

    def test_normalize_removes_accents(self):
        from app.services.rag.core.kg_builder.fuzzy_resolver import _normalize_legal

        assert "sumula" in _normalize_legal("Súmula")

    def test_extract_numbers(self):
        from app.services.rag.core.kg_builder.fuzzy_resolver import _extract_numbers

        assert _extract_numbers("Lei 8.666/93") == "866693"
        assert _extract_numbers("Art. 5º, § 2º") == "52"
        assert _extract_numbers("STF") == ""

    def test_resolver_importable(self):
        from app.services.rag.core.kg_builder.fuzzy_resolver import (
            LegalFuzzyResolver,
            resolve_entities,
        )
        assert LegalFuzzyResolver is not None


class TestKGPipeline:
    """Tests for pipeline.py — composed KG construction pipeline."""

    def test_pipeline_importable(self):
        from app.services.rag.core.kg_builder.pipeline import run_kg_builder
        assert run_kg_builder is not None

    @pytest.mark.asyncio
    async def test_regex_extraction_standalone(self):
        from app.services.rag.core.kg_builder.pipeline import _run_regex_extraction

        chunks = [
            {
                "chunk_uid": "pipe_001",
                "text": "Art. 5º, Lei 8.666/93, Súmula 331 TST",
            },
        ]
        stats = await _run_regex_extraction(
            chunks, "doc_test", "tenant1",
            case_id=None, scope="global",
        )
        assert stats["chunks_processed"] == 1
        assert stats["regex_nodes"] >= 3

    def test_rag_endpoint_has_kg_builder_integration(self):
        """Verify rag.py endpoint includes KG Builder integration."""
        import inspect
        from app.api.endpoints.rag import _ingest_document_to_graph

        source = inspect.getsource(_ingest_document_to_graph)
        assert "KG_BUILDER_ENABLED" in source, (
            "rag.py must check KG_BUILDER_ENABLED env var"
        )
        assert "run_kg_builder" in source, (
            "rag.py must call run_kg_builder from kg_builder pipeline"
        )

    def test_requirements_has_dependencies(self):
        """Verify requirements.txt includes neo4j-graphrag and rapidfuzz."""
        import os

        req_path = os.path.join(os.path.dirname(__file__), "..", "requirements.txt")
        with open(req_path) as f:
            content = f.read()
        assert "neo4j-graphrag" in content, "neo4j-graphrag must be in requirements.txt"
        assert "rapidfuzz" in content, "rapidfuzz must be in requirements.txt"


# =============================================================================
# PHASE 3 TESTS: ArgumentLLM Extractor + Evidence Scorer
# =============================================================================


class TestEvidenceScorer:
    """Tests for evidence_scorer.py — scoring by authority, type, and stance."""

    def test_scorer_importable(self):
        from app.services.rag.core.kg_builder.evidence_scorer import (
            score_evidence,
            score_by_tribunal,
            TRIBUNAL_AUTHORITY,
            EVIDENCE_TYPE_SCORE,
        )
        assert score_evidence is not None
        assert score_by_tribunal is not None

    def test_score_jurisprudencia_stf(self):
        """STF jurisprudencia should score highest."""
        from app.services.rag.core.kg_builder.evidence_scorer import score_evidence

        evidence = {
            "text": "Decisão do STF no RE 123456",
            "evidence_type": "jurisprudencia",
            "stance": "pro",
        }
        score = score_evidence(evidence)
        # Base 0.9 + authority_bonus (1.0*0.15=0.15) + stance 0.05 = 1.0 (capped)
        assert score >= 0.95, f"STF jurisprudencia pro should score >= 0.95, got {score}"

    def test_score_doutrina_neutro(self):
        """Doutrina with neutral stance should score lower."""
        from app.services.rag.core.kg_builder.evidence_scorer import score_evidence

        evidence = {
            "text": "Conforme doutrina majoritária",
            "evidence_type": "doutrina",
            "stance": "neutro",
        }
        score = score_evidence(evidence)
        # Base 0.7, no authority bonus (no tribunal mentioned), no stance bonus
        assert score == 0.7, f"Doutrina neutro should score 0.7, got {score}"

    def test_score_fato_contra(self):
        """Fato with contra stance should get stance bonus."""
        from app.services.rag.core.kg_builder.evidence_scorer import score_evidence

        evidence = {
            "text": "O fato ocorreu em 2020",
            "evidence_type": "fato",
            "stance": "contra",
        }
        score = score_evidence(evidence)
        # Base 0.65 + stance 0.05 = 0.7
        assert score == 0.7, f"Fato contra should score 0.7, got {score}"

    def test_score_with_tribunal_stj(self):
        """Text mentioning STJ should get authority bonus."""
        from app.services.rag.core.kg_builder.evidence_scorer import score_evidence

        evidence = {
            "text": "Conforme entendimento do STJ no REsp 12345",
            "evidence_type": "jurisprudencia",
            "stance": "pro",
        }
        score = score_evidence(evidence)
        # Base 0.9 + STJ authority (0.95*0.15) + stance 0.05 = ~1.09 -> capped at 1.0
        assert score == 1.0, f"STJ jurisprudencia pro should cap at 1.0, got {score}"

    def test_score_unknown_type(self):
        """Unknown evidence type should use default base score."""
        from app.services.rag.core.kg_builder.evidence_scorer import score_evidence

        evidence = {
            "text": "Algo desconhecido",
            "evidence_type": "desconhecido",
            "stance": "neutro",
        }
        score = score_evidence(evidence)
        assert score == 0.5, f"Unknown type should score 0.5, got {score}"

    def test_score_by_tribunal_function(self):
        """Test standalone tribunal authority lookup."""
        from app.services.rag.core.kg_builder.evidence_scorer import score_by_tribunal

        assert score_by_tribunal("STF") == 1.0
        assert score_by_tribunal("stj") == 0.95
        assert score_by_tribunal("TRF1") == 0.75
        assert score_by_tribunal("TRF5") == 0.75
        assert score_by_tribunal("TJSP") == 0.6
        assert score_by_tribunal("UNKNOWN") == 0.5

    def test_score_multiple_tribunals_picks_highest(self):
        """When multiple tribunals are mentioned, use the highest authority."""
        from app.services.rag.core.kg_builder.evidence_scorer import score_evidence

        evidence = {
            "text": "O TJ decidiu X, mas o STF reformou a decisão",
            "evidence_type": "jurisprudencia",
            "stance": "pro",
        }
        score = score_evidence(evidence)
        # Should use STF authority (1.0), not TJ (0.6)
        # Base 0.9 + STF (1.0*0.15) + stance 0.05 = 1.1 -> capped at 1.0
        assert score == 1.0

    def test_score_capped_at_one(self):
        """Score should never exceed 1.0."""
        from app.services.rag.core.kg_builder.evidence_scorer import score_evidence

        evidence = {
            "text": "Decisão do STF",
            "evidence_type": "jurisprudencia",
            "stance": "pro",
        }
        score = score_evidence(evidence)
        assert score <= 1.0

    def test_tribunal_authority_completeness(self):
        """Tribunal authority dict should cover major courts."""
        from app.services.rag.core.kg_builder.evidence_scorer import TRIBUNAL_AUTHORITY

        required = {"stf", "stj", "tst", "tse", "trf", "trt", "tj"}
        assert required.issubset(set(TRIBUNAL_AUTHORITY.keys()))


class TestArgumentLLMExtractor:
    """Tests for argument_llm_extractor.py — LLM extraction schemas and structure."""

    def test_extractor_importable(self):
        from app.services.rag.core.kg_builder.argument_llm_extractor import (
            ArgumentLLMExtractor,
            ARGUMENT_EXTRACTION_SCHEMA,
            EXTRACTION_PROMPT,
        )
        assert ArgumentLLMExtractor is not None
        assert ARGUMENT_EXTRACTION_SCHEMA is not None
        assert EXTRACTION_PROMPT is not None

    def test_schema_has_required_fields(self):
        from app.services.rag.core.kg_builder.argument_llm_extractor import (
            ARGUMENT_EXTRACTION_SCHEMA,
        )

        props = ARGUMENT_EXTRACTION_SCHEMA["properties"]
        assert "claims" in props, "Schema must define claims"
        assert "evidence" in props, "Schema must define evidence"
        assert "actors" in props, "Schema must define actors"
        assert "issues" in props, "Schema must define issues"

    def test_schema_claims_structure(self):
        from app.services.rag.core.kg_builder.argument_llm_extractor import (
            ARGUMENT_EXTRACTION_SCHEMA,
        )

        claims_schema = ARGUMENT_EXTRACTION_SCHEMA["properties"]["claims"]["items"]["properties"]
        assert "text" in claims_schema
        assert "claim_type" in claims_schema
        assert "polarity" in claims_schema
        assert "confidence" in claims_schema
        assert "supports" in claims_schema
        assert "opposes" in claims_schema
        assert "cited_entities" in claims_schema

    def test_schema_evidence_structure(self):
        from app.services.rag.core.kg_builder.argument_llm_extractor import (
            ARGUMENT_EXTRACTION_SCHEMA,
        )

        ev_schema = ARGUMENT_EXTRACTION_SCHEMA["properties"]["evidence"]["items"]["properties"]
        assert "text" in ev_schema
        assert "evidence_type" in ev_schema
        assert "stance" in ev_schema
        assert "supports_claims" in ev_schema

    def test_prompt_has_placeholders(self):
        from app.services.rag.core.kg_builder.argument_llm_extractor import EXTRACTION_PROMPT

        assert "{text}" in EXTRACTION_PROMPT, "Prompt must have {text} placeholder"

    @pytest.mark.asyncio
    async def test_extract_empty_text_returns_empty(self):
        from app.services.rag.core.kg_builder.argument_llm_extractor import (
            ArgumentLLMExtractor,
        )

        extractor = ArgumentLLMExtractor()
        result = await extractor.extract("", chunk_uid="test")
        assert result == {"claims": [], "evidence": [], "actors": [], "issues": []}

    def test_extractor_default_model(self):
        from app.services.rag.core.kg_builder.argument_llm_extractor import (
            ArgumentLLMExtractor,
        )

        extractor = ArgumentLLMExtractor()
        assert "gemini" in extractor._model.lower() or "flash" in extractor._model.lower()


class TestPipelineLLMIntegration:
    """Tests for pipeline.py Phase 3 — LLM extraction integration."""

    def test_pipeline_run_argument_extraction_importable(self):
        from app.services.rag.core.kg_builder.pipeline import _run_argument_extraction
        assert _run_argument_extraction is not None

    def test_pipeline_imports_llm_extractor(self):
        """Verify pipeline.py imports ArgumentLLMExtractor."""
        import inspect
        from app.services.rag.core.kg_builder.pipeline import _run_argument_extraction

        source = inspect.getsource(_run_argument_extraction)
        assert "ArgumentLLMExtractor" in source, (
            "pipeline must import ArgumentLLMExtractor"
        )
        assert "extract_and_ingest" in source, (
            "pipeline must call extract_and_ingest"
        )

    def test_pipeline_has_heuristic_fallback(self):
        """Verify pipeline falls back to heuristic when LLM unavailable."""
        import inspect
        from app.services.rag.core.kg_builder.pipeline import _run_argument_extraction

        source = inspect.getsource(_run_argument_extraction)
        assert "get_argument_neo4j" in source, (
            "pipeline must have heuristic fallback via ArgumentNeo4jService"
        )

    def test_graph_endpoint_argument_graph_exists(self):
        """Verify graph.py has /argument-graph/{case_id} endpoint."""
        import inspect
        from app.api.endpoints import graph

        source = inspect.getsource(graph)
        assert "argument-graph" in source, (
            "graph.py must have /argument-graph/{case_id} endpoint"
        )
        assert "ArgumentGraphData" in source, (
            "graph.py must define ArgumentGraphData response model"
        )

    def test_graph_endpoint_argument_stats_exists(self):
        """Verify graph.py has /argument-stats endpoint."""
        import inspect
        from app.api.endpoints import graph

        source = inspect.getsource(graph)
        assert "argument-stats" in source, (
            "graph.py must have /argument-stats endpoint"
        )


# =============================================================================
# Phase 3.7: Tests for FIND_PATHS separation, intent detection, security trimming
# =============================================================================

class TestFindPathsSeparation:
    """Tests that FIND_PATHS is properly separated into entity-only and argument-aware."""

    def test_entity_only_query_excludes_argument_relationships(self):
        """FIND_PATHS (entity-only) must NOT traverse argument edges."""
        from app.services.rag.core.neo4j_mvp import CypherQueries

        query = CypherQueries.FIND_PATHS
        # Must NOT contain argument relationship types
        for rel in ["SUPPORTS", "OPPOSES", "EVIDENCES", "ARGUES", "RAISES", "CITES", "CONTAINS_CLAIM"]:
            assert rel not in query, (
                f"Entity-only FIND_PATHS must not contain '{rel}' relationship"
            )

    def test_entity_only_query_excludes_argument_targets(self):
        """FIND_PATHS (entity-only) must NOT target Claim/Evidence nodes."""
        from app.services.rag.core.neo4j_mvp import CypherQueries

        query = CypherQueries.FIND_PATHS
        # Should exclude argument node labels from target matching
        assert "NOT (target:Claim" in query or "Claim" not in query.split("WHERE")[1].split("RETURN")[0], (
            "Entity-only FIND_PATHS must exclude Claim targets"
        )

    def test_entity_only_query_has_entity_relationships(self):
        """FIND_PATHS (entity-only) must traverse entity edges."""
        from app.services.rag.core.neo4j_mvp import CypherQueries

        query = CypherQueries.FIND_PATHS
        for rel in ["RELATED_TO", "MENTIONS"]:
            assert rel in query, f"Entity-only FIND_PATHS must contain '{rel}'"

    def test_argument_aware_query_has_all_relationships(self):
        """FIND_PATHS_WITH_ARGUMENTS must traverse all relationship types."""
        from app.services.rag.core.neo4j_mvp import CypherQueries

        query = CypherQueries.FIND_PATHS_WITH_ARGUMENTS
        for rel in ["RELATED_TO", "MENTIONS", "SUPPORTS", "OPPOSES", "EVIDENCES",
                     "ARGUES", "RAISES", "CITES", "CONTAINS_CLAIM"]:
            assert rel in query, (
                f"Argument-aware FIND_PATHS must contain '{rel}' relationship"
            )

    def test_argument_aware_query_targets_claim_evidence(self):
        """FIND_PATHS_WITH_ARGUMENTS must include Claim and Evidence in targets."""
        from app.services.rag.core.neo4j_mvp import CypherQueries

        query = CypherQueries.FIND_PATHS_WITH_ARGUMENTS
        assert "target:Claim" in query, "Must target Claim nodes"
        assert "target:Evidence" in query, "Must target Evidence nodes"

    def test_find_paths_method_has_include_arguments_param(self):
        """find_paths() method must accept include_arguments parameter."""
        import inspect
        from app.services.rag.core.neo4j_mvp import Neo4jMVPService

        sig = inspect.signature(Neo4jMVPService.find_paths)
        assert "include_arguments" in sig.parameters, (
            "find_paths() must have 'include_arguments' parameter"
        )
        # Default should be False (entity-only)
        param = sig.parameters["include_arguments"]
        assert param.default is False, (
            "include_arguments default must be False (entity-only by default)"
        )


class TestClaimEvidenceSecurityTrimming:
    """Tests that Claim/Evidence nodes have security trimming in argument-aware traversal."""

    def test_argument_query_checks_claim_tenant_id(self):
        """FIND_PATHS_WITH_ARGUMENTS must check tenant_id on Claim/Evidence nodes."""
        from app.services.rag.core.neo4j_mvp import CypherQueries

        query = CypherQueries.FIND_PATHS_WITH_ARGUMENTS
        # Must have a security check for Claim/Evidence tenant_id
        assert "n:Claim OR n:Evidence" in query, (
            "Must have security clause checking Claim/Evidence nodes"
        )
        assert "n.tenant_id = $tenant_id" in query, (
            "Must check tenant_id on Claim/Evidence nodes"
        )

    def test_argument_query_checks_case_id(self):
        """FIND_PATHS_WITH_ARGUMENTS must check case_id on Claim/Evidence nodes."""
        from app.services.rag.core.neo4j_mvp import CypherQueries

        query = CypherQueries.FIND_PATHS_WITH_ARGUMENTS
        assert "n.case_id = $case_id" in query, (
            "Must check case_id on Claim/Evidence nodes"
        )

    def test_entity_only_query_has_no_claim_security(self):
        """FIND_PATHS (entity-only) should not need Claim/Evidence security checks."""
        from app.services.rag.core.neo4j_mvp import CypherQueries

        query = CypherQueries.FIND_PATHS
        # Entity-only query doesn't traverse argument nodes, so no need for their security
        assert "n:Claim OR n:Evidence" not in query, (
            "Entity-only query should not reference Claim/Evidence security"
        )

    def test_chunk_security_preserved_in_both_queries(self):
        """Both FIND_PATHS variants must preserve Chunk document-level security."""
        from app.services.rag.core.neo4j_mvp import CypherQueries

        for name, query in [("entity-only", CypherQueries.FIND_PATHS),
                            ("argument-aware", CypherQueries.FIND_PATHS_WITH_ARGUMENTS)]:
            assert "d.scope IN $allowed_scopes" in query, (
                f"{name} must check document scope"
            )
            assert "d.tenant_id = $tenant_id" in query, (
                f"{name} must check document tenant_id"
            )
            assert "d.sigilo" in query, (
                f"{name} must check document sigilo"
            )


class TestDebateIntentDetection:
    """Tests for automatic debate vs factual intent detection."""

    def test_import_detect_debate_intent(self):
        """detect_debate_intent must be importable from pipeline."""
        from app.services.rag.pipeline.rag_pipeline import detect_debate_intent
        assert callable(detect_debate_intent)

    def test_debate_query_argumentos(self):
        from app.services.rag.pipeline.rag_pipeline import detect_debate_intent
        assert detect_debate_intent("Quais os argumentos a favor da tese?") is True

    def test_debate_query_tese(self):
        from app.services.rag.pipeline.rag_pipeline import detect_debate_intent
        assert detect_debate_intent("Qual a tese principal da defesa?") is True

    def test_debate_query_contratese(self):
        from app.services.rag.pipeline.rag_pipeline import detect_debate_intent
        assert detect_debate_intent("Existe contratese para isso?") is True

    def test_debate_query_pros_e_contras(self):
        from app.services.rag.pipeline.rag_pipeline import detect_debate_intent
        assert detect_debate_intent("Prós e contras da interpretação") is True

    def test_debate_query_defesa(self):
        from app.services.rag.pipeline.rag_pipeline import detect_debate_intent
        assert detect_debate_intent("Estratégia de defesa no caso") is True

    def test_debate_query_contraditorio(self):
        from app.services.rag.pipeline.rag_pipeline import detect_debate_intent
        assert detect_debate_intent("Princípio do contraditório") is True

    def test_debate_query_fundamentacao(self):
        from app.services.rag.pipeline.rag_pipeline import detect_debate_intent
        assert detect_debate_intent("Fundamentação da sentença") is True

    def test_debate_query_impugnacao(self):
        from app.services.rag.pipeline.rag_pipeline import detect_debate_intent
        assert detect_debate_intent("A impugnação do réu sobre o prazo") is True

    def test_debate_query_compare_argumentos(self):
        from app.services.rag.pipeline.rag_pipeline import detect_debate_intent
        assert detect_debate_intent("Compare os argumentos das partes") is True

    def test_factual_query_artigo(self):
        """Factual queries about articles should NOT trigger debate mode."""
        from app.services.rag.pipeline.rag_pipeline import detect_debate_intent
        assert detect_debate_intent("O que diz o Art. 5º da CF?") is False

    def test_factual_query_lei(self):
        from app.services.rag.pipeline.rag_pipeline import detect_debate_intent
        assert detect_debate_intent("Texto da Lei 8.666/93") is False

    def test_factual_query_sumula(self):
        from app.services.rag.pipeline.rag_pipeline import detect_debate_intent
        assert detect_debate_intent("Súmula 331 do TST") is False

    def test_factual_query_prazo(self):
        from app.services.rag.pipeline.rag_pipeline import detect_debate_intent
        assert detect_debate_intent("Qual o prazo para recurso?") is False

    def test_factual_query_conceito(self):
        from app.services.rag.pipeline.rag_pipeline import detect_debate_intent
        assert detect_debate_intent("O que é responsabilidade civil?") is False

    def test_empty_query(self):
        from app.services.rag.pipeline.rag_pipeline import detect_debate_intent
        assert detect_debate_intent("") is False
        assert detect_debate_intent(None) is False

    def test_debate_phrase_linha_argumentativa(self):
        from app.services.rag.pipeline.rag_pipeline import detect_debate_intent
        assert detect_debate_intent("A linha argumentativa do autor é fraca") is True

    def test_debate_phrase_pontos_fortes_fracos(self):
        from app.services.rag.pipeline.rag_pipeline import detect_debate_intent
        assert detect_debate_intent("Pontos fortes e fracos da petição") is True

    def test_pipeline_uses_intent_detection(self):
        """Verify that _stage_graph_enrich references detect_debate_intent."""
        import inspect
        from app.services.rag.pipeline import rag_pipeline

        source = inspect.getsource(rag_pipeline)
        assert "detect_debate_intent" in source, (
            "Pipeline must use detect_debate_intent function"
        )
        assert "include_arguments" in source, (
            "Pipeline must pass include_arguments to find_paths"
        )


# =============================================================================
# GRAPH-AUGMENTED RETRIEVAL: Neo4j as 3rd RRF Source
# =============================================================================


class TestGraphRetrievalConfig:
    """Tests for graph retrieval configuration fields."""

    def test_graph_retrieval_defaults(self):
        """Default config has graph retrieval enabled with weight 0.3."""
        from app.services.rag.config import RAGConfig

        config = RAGConfig()
        assert config.enable_graph_retrieval is True
        assert config.graph_weight == 0.3
        assert config.graph_retrieval_limit == 20

    def test_graph_retrieval_from_env(self):
        """Environment variables are read correctly for graph retrieval."""
        import os
        from app.services.rag.config import RAGConfig

        old_vals = {}
        envs = {
            "RAG_ENABLE_GRAPH_RETRIEVAL": "true",
            "RAG_GRAPH_WEIGHT": "0.5",
            "RAG_GRAPH_RETRIEVAL_LIMIT": "30",
        }
        for k, v in envs.items():
            old_vals[k] = os.environ.get(k)
            os.environ[k] = v

        try:
            config = RAGConfig.from_env()
            assert config.enable_graph_retrieval is True
            assert config.graph_weight == 0.5
            assert config.graph_retrieval_limit == 30
        finally:
            for k, v in old_vals.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


class TestRRFGraphRank:
    """Tests for _compute_rrf_score and _merge_results_rrf with graph rank."""

    def _make_pipeline(self, graph_weight=0.3):
        """Create a minimal pipeline instance for testing RRF."""
        from unittest.mock import MagicMock
        from app.services.rag.config import RAGConfig

        config = RAGConfig(
            lexical_weight=0.5,
            vector_weight=0.5,
            graph_weight=graph_weight,
            rrf_k=60,
        )

        pipeline = MagicMock()
        pipeline._base_config = config
        pipeline._compute_rrf_score = (
            lambda lex, vec, graph=None, k=60: self._rrf(config, lex, vec, graph, k)
        )
        return pipeline, config

    @staticmethod
    def _rrf(config, lex, vec, graph, k):
        score = 0.0
        if lex is not None:
            score += config.lexical_weight * (1.0 / (k + lex))
        if vec is not None:
            score += config.vector_weight * (1.0 / (k + vec))
        if graph is not None:
            score += config.graph_weight * (1.0 / (k + graph))
        return score

    def test_compute_rrf_score_with_graph_rank(self):
        """Graph rank contributes to RRF score with graph_weight."""
        from app.services.rag.config import RAGConfig

        config = RAGConfig(lexical_weight=0.5, vector_weight=0.5, graph_weight=0.3, rrf_k=60)
        # score = 0.3 * 1/(60+1) ≈ 0.00492
        score = config.graph_weight * (1.0 / (60 + 1))
        assert 0.004 < score < 0.006

    def test_compute_rrf_score_graph_none_backward_compatible(self):
        """When graph_rank=None, score equals original 2-source formula."""
        _, config = self._make_pipeline()

        # With graph=None, should equal lex+vec only
        score_no_graph = self._rrf(config, 1, 1, None, 60)
        expected = 0.5 * (1.0 / 61) + 0.5 * (1.0 / 61)
        assert abs(score_no_graph - expected) < 1e-10

    def test_compute_rrf_score_all_three_sources(self):
        """Chunk in all 3 sources gets highest score."""
        _, config = self._make_pipeline()

        score_all = self._rrf(config, 1, 1, 1, 60)
        score_two = self._rrf(config, 1, 1, None, 60)
        assert score_all > score_two

    def test_graph_weight_zero_disables(self):
        """Setting graph_weight=0 effectively disables graph contribution."""
        _, config = self._make_pipeline(graph_weight=0.0)

        score_with_graph = self._rrf(config, 1, 1, 1, 60)
        score_without = self._rrf(config, 1, 1, None, 60)
        assert abs(score_with_graph - score_without) < 1e-10

    def test_graph_only_chunk_lower_score(self):
        """Chunk appearing only in graph gets lower score than multi-source."""
        _, config = self._make_pipeline()

        score_graph_only = self._rrf(config, None, None, 1, 60)
        score_lex_vec = self._rrf(config, 1, 1, None, 60)
        assert score_graph_only < score_lex_vec

    def test_overlap_boost(self):
        """Chunk in all 3 sources scores higher than any pair."""
        _, config = self._make_pipeline()

        score_all = self._rrf(config, 1, 1, 1, 60)
        score_lex_vec = self._rrf(config, 1, 1, None, 60)
        score_lex_graph = self._rrf(config, 1, None, 1, 60)
        score_vec_graph = self._rrf(config, None, 1, 1, 60)
        assert score_all > score_lex_vec
        assert score_all > score_lex_graph
        assert score_all > score_vec_graph


class TestMergeResultsRRFGraph:
    """Tests for _merge_results_rrf with graph_results parameter."""

    def test_merge_three_sources(self):
        """Three sources merge correctly with dedup by chunk_uid."""
        from app.services.rag.pipeline.rag_pipeline import RAGPipeline
        from app.services.rag.config import RAGConfig

        config = RAGConfig(
            lexical_weight=0.5, vector_weight=0.5, graph_weight=0.3, rrf_k=60,
        )
        pipeline = RAGPipeline.__new__(RAGPipeline)
        pipeline._base_config = config

        lex = [{"chunk_uid": "a", "text": "a", "score": 0.9}]
        vec = [{"chunk_uid": "a", "text": "a", "score": 0.8}]
        graph = [{"chunk_uid": "a", "text": "a", "score": 0.5}]

        merged = pipeline._merge_results_rrf(lex, vec, graph)
        assert len(merged) == 1
        # Should have contributions from all 3 sources
        expected = 0.5 * (1/61) + 0.5 * (1/61) + 0.3 * (1/61)
        assert abs(merged[0]["final_score"] - expected) < 1e-10

    def test_merge_empty_graph_backward_compatible(self):
        """Empty graph_results does not affect existing merge."""
        from app.services.rag.pipeline.rag_pipeline import RAGPipeline
        from app.services.rag.config import RAGConfig

        config = RAGConfig(lexical_weight=0.5, vector_weight=0.5, graph_weight=0.3, rrf_k=60)
        pipeline = RAGPipeline.__new__(RAGPipeline)
        pipeline._base_config = config

        lex = [{"chunk_uid": "a", "text": "a", "score": 0.9}]
        vec = [{"chunk_uid": "a", "text": "a", "score": 0.8}]

        merged_no_graph = pipeline._merge_results_rrf(lex, vec, None)
        merged_empty = pipeline._merge_results_rrf(lex, vec, [])
        assert abs(merged_no_graph[0]["final_score"] - merged_empty[0]["final_score"]) < 1e-10

    def test_merge_graph_only_chunk_included(self):
        """Chunk appearing only in graph is included in merged results."""
        from app.services.rag.pipeline.rag_pipeline import RAGPipeline
        from app.services.rag.config import RAGConfig

        config = RAGConfig(lexical_weight=0.5, vector_weight=0.5, graph_weight=0.3, rrf_k=60)
        pipeline = RAGPipeline.__new__(RAGPipeline)
        pipeline._base_config = config

        lex = [{"chunk_uid": "a", "text": "a", "score": 0.9}]
        vec = []
        graph = [{"chunk_uid": "b", "text": "b", "score": 0.5}]

        merged = pipeline._merge_results_rrf(lex, vec, graph)
        uids = {r["chunk_uid"] for r in merged}
        assert "a" in uids
        assert "b" in uids
        # "a" should rank higher than "b" (lex weight > graph weight)
        assert merged[0]["chunk_uid"] == "a"

    def test_merge_no_internal_fields_leaked(self):
        """Internal _graph_rank fields are cleaned up."""
        from app.services.rag.pipeline.rag_pipeline import RAGPipeline
        from app.services.rag.config import RAGConfig

        config = RAGConfig(lexical_weight=0.5, vector_weight=0.5, graph_weight=0.3, rrf_k=60)
        pipeline = RAGPipeline.__new__(RAGPipeline)
        pipeline._base_config = config

        graph = [{"chunk_uid": "a", "text": "a", "score": 0.5}]
        merged = pipeline._merge_results_rrf([], [], graph)
        assert "_graph_rank" not in merged[0]
        assert "_lexical_rank" not in merged[0]
        assert "_vector_rank" not in merged[0]


class TestStageGraphSearch:
    """Tests for _stage_graph_search method."""

    @pytest.mark.asyncio
    async def test_graph_search_neo4j_none_returns_empty(self):
        """When _neo4j is None, returns empty list."""
        from unittest.mock import MagicMock, AsyncMock
        from app.services.rag.pipeline.rag_pipeline import RAGPipeline, PipelineTrace

        pipeline = RAGPipeline.__new__(RAGPipeline)
        pipeline._neo4j = None

        trace = MagicMock(spec=PipelineTrace)
        stage_mock = MagicMock()
        trace.start_stage.return_value = stage_mock
        trace.trace_id = "test"

        result = await pipeline._stage_graph_search(
            "Art. 5 CF", "tenant1", "global", None, trace
        )
        assert result == []
        stage_mock.skip.assert_called_once()

    @pytest.mark.asyncio
    async def test_graph_search_no_entities_returns_empty(self):
        """When no entities are extracted, returns empty list."""
        from unittest.mock import MagicMock, patch
        from app.services.rag.pipeline.rag_pipeline import RAGPipeline, PipelineTrace

        pipeline = RAGPipeline.__new__(RAGPipeline)
        pipeline._neo4j = MagicMock()

        trace = MagicMock(spec=PipelineTrace)
        stage_mock = MagicMock()
        trace.start_stage.return_value = stage_mock
        trace.trace_id = "test"

        # Patch entity extractor to return no entities
        with patch(
            "app.services.rag.pipeline.rag_pipeline.Neo4jEntityExtractor"
        ) as mock_ext:
            mock_ext.extract.return_value = []

            result = await pipeline._stage_graph_search(
                "bom dia", "tenant1", "global", None, trace
            )
            assert result == []
            stage_mock.skip.assert_called_once()

    @pytest.mark.asyncio
    async def test_graph_search_fail_open(self):
        """When Neo4j raises, returns empty list (fail-open)."""
        from unittest.mock import MagicMock, patch
        from app.services.rag.pipeline.rag_pipeline import RAGPipeline, PipelineTrace

        pipeline = RAGPipeline.__new__(RAGPipeline)
        pipeline._neo4j = MagicMock()
        pipeline._neo4j.query_chunks_by_entities.side_effect = ConnectionError("Neo4j down")

        trace = MagicMock(spec=PipelineTrace)
        stage_mock = MagicMock()
        trace.start_stage.return_value = stage_mock
        trace.trace_id = "test"

        with patch(
            "app.services.rag.pipeline.rag_pipeline.Neo4jEntityExtractor"
        ) as mock_ext:
            mock_ext.extract.return_value = [{"entity_id": "art_5"}]

            result = await pipeline._stage_graph_search(
                "Art. 5 CF", "tenant1", "global", None, trace
            )
            assert result == []
            stage_mock.fail.assert_called_once()

    @pytest.mark.asyncio
    async def test_graph_search_returns_normalized_chunks(self):
        """Graph search returns chunks with pipeline-expected fields."""
        from unittest.mock import MagicMock, patch
        from app.services.rag.pipeline.rag_pipeline import RAGPipeline, PipelineTrace

        pipeline = RAGPipeline.__new__(RAGPipeline)
        pipeline._neo4j = MagicMock()
        pipeline._neo4j.query_chunks_by_entities.return_value = [
            {
                "chunk_uid": "c1",
                "text_preview": "Art. 5 garante...",
                "doc_hash": "d1",
                "doc_title": "CF88",
                "source_type": "lei",
                "matched_entities": ["art_5"],
            }
        ]

        trace = MagicMock(spec=PipelineTrace)
        stage_mock = MagicMock()
        trace.start_stage.return_value = stage_mock
        trace.trace_id = "test"

        with patch(
            "app.services.rag.pipeline.rag_pipeline.Neo4jEntityExtractor"
        ) as mock_ext:
            mock_ext.extract.return_value = [{"entity_id": "art_5"}]

            result = await pipeline._stage_graph_search(
                "Art. 5 CF", "tenant1", "global", None, trace
            )
            assert len(result) == 1
            assert result[0]["chunk_uid"] == "c1"
            assert result[0]["_source_type"] == "neo4j_graph"
            assert result[0]["text"] == "Art. 5 garante..."
            stage_mock.complete.assert_called_once()


class TestPipelineEnums:
    """Tests for new pipeline enums."""

    def test_pipeline_stage_graph_search_exists(self):
        """PipelineStage.GRAPH_SEARCH enum exists."""
        from app.services.rag.pipeline.rag_pipeline import PipelineStage
        assert PipelineStage.GRAPH_SEARCH.value == "graph_search"

    def test_search_mode_hybrid_lex_vec_graph(self):
        """SearchMode.HYBRID_LEX_VEC_GRAPH enum exists."""
        from app.services.rag.pipeline.rag_pipeline import SearchMode
        assert SearchMode.HYBRID_LEX_VEC_GRAPH.value == "hybrid_lex+vec+graph"

    def test_search_mode_hybrid_lex_graph(self):
        """SearchMode.HYBRID_LEX_GRAPH enum exists."""
        from app.services.rag.pipeline.rag_pipeline import SearchMode
        assert SearchMode.HYBRID_LEX_GRAPH.value == "hybrid_lex+graph"
