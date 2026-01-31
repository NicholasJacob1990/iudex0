"""
Tests for CogGRAG Phase 3 reasoning nodes.

Covers: reasoner_node, verifier_node, query_rewriter_node, integrator_node.
"""

import pytest
from unittest.mock import patch, AsyncMock

from app.services.rag.core.cograg.nodes.reasoner import (
    reasoner_node,
    _format_evidence_for_prompt,
    _compute_answer_confidence,
)
from app.services.rag.core.cograg.nodes.verifier import (
    verifier_node,
    query_rewriter_node,
    _parse_verification_result,
)
from app.services.rag.core.cograg.nodes.integrator import (
    integrator_node,
    _format_sub_answers,
    _collect_citations,
    _rule_based_integration,
)


# ═══════════════════════════════════════════════════════════════════════════
# Reasoner Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestReasonerHelpers:
    def test_format_evidence_for_prompt(self):
        evidence = {
            "local_results": [
                {"text": "Evidence 1", "score": 0.9, "source": "lei"},
                {"text": "Evidence 2", "score": 0.8},
            ],
            "global_results": [
                {"text": "Evidence 3", "score": 0.7},
            ],
            "chunk_results": [],
        }
        formatted = _format_evidence_for_prompt(evidence, max_chunks=3)

        assert "Evidence 1" in formatted
        assert "Evidence 2" in formatted
        assert "Evidence 3" in formatted
        assert "[fonte: lei]" in formatted

    def test_format_evidence_empty(self):
        evidence = {}
        formatted = _format_evidence_for_prompt(evidence)
        assert "Nenhuma evidência" in formatted

    def test_compute_confidence_base(self):
        confidence = _compute_answer_confidence(
            answer="Resposta básica",
            evidence={"local_results": []},
            has_conflicts=False,
        )
        assert 0.0 <= confidence <= 1.0

    def test_compute_confidence_with_evidence(self):
        confidence = _compute_answer_confidence(
            answer="Resposta com evidências relevantes " * 20,
            evidence={
                "local_results": [{"text": "e1"}, {"text": "e2"}, {"text": "e3"}, {"text": "e4"}, {"text": "e5"}],
                "quality_score": 0.8,
            },
            has_conflicts=False,
        )
        # Should have higher confidence with more evidence
        assert confidence >= 0.7

    def test_compute_confidence_with_conflicts(self):
        conf_no_conflict = _compute_answer_confidence(
            answer="Resposta média " * 10,
            evidence={"local_results": [{"text": "e1"}]},
            has_conflicts=False,
        )
        conf_with_conflict = _compute_answer_confidence(
            answer="Resposta média " * 10,
            evidence={"local_results": [{"text": "e1"}]},
            has_conflicts=True,
        )
        # Conflicts should reduce confidence
        assert conf_with_conflict < conf_no_conflict


class TestReasonerNode:
    @pytest.mark.asyncio
    async def test_no_sub_questions(self):
        state = {"sub_questions": [], "metrics": {}}
        result = await reasoner_node(state)

        assert result["sub_answers"] == []
        assert result["verification_status"] == "approved"
        assert result["metrics"]["reasoner_answers_generated"] == 0

    @pytest.mark.asyncio
    async def test_generates_answers(self):
        state = {
            "sub_questions": [
                {"node_id": "n1", "question": "Qual o prazo?"},
                {"node_id": "n2", "question": "Quais os requisitos?"},
            ],
            "evidence_map": {
                "n1": {
                    "local_results": [{"text": "O prazo é de 5 anos conforme Art. 206", "score": 0.9}],
                    "global_results": [],
                    "chunk_results": [],
                },
                "n2": {
                    "local_results": [{"text": "Os requisitos são: capacidade, objeto lícito", "score": 0.85}],
                    "global_results": [],
                    "chunk_results": [],
                },
            },
            "refined_evidence": {},
            "conflicts": [],
            "metrics": {},
        }

        # Mock LLM call
        with patch("app.services.rag.core.cograg.nodes.reasoner._call_llm") as mock_llm:
            mock_llm.return_value = "Resposta mockada com Art. 206 e Lei 10406"
            result = await reasoner_node(state)

        assert len(result["sub_answers"]) == 2
        assert result["sub_answers"][0]["node_id"] == "n1"
        assert result["sub_answers"][0]["answer"] == "Resposta mockada com Art. 206 e Lei 10406"
        assert result["metrics"]["reasoner_answers_generated"] == 2

    @pytest.mark.asyncio
    async def test_extracts_citations(self):
        state = {
            "sub_questions": [{"node_id": "n1", "question": "Test?"}],
            "evidence_map": {"n1": {"local_results": [{"text": "Test", "score": 0.9}], "global_results": [], "chunk_results": []}},
            "refined_evidence": {},
            "conflicts": [],
            "metrics": {},
        }

        with patch("app.services.rag.core.cograg.nodes.reasoner._call_llm") as mock_llm:
            mock_llm.return_value = "Conforme Art. 5 da CF e Súmula 331 do TST, a Lei 8112/90 estabelece..."
            result = await reasoner_node(state)

        citations = result["sub_answers"][0]["citations"]
        assert len(citations) > 0
        # Should extract legal references
        assert any("Art" in c for c in citations)


# ═══════════════════════════════════════════════════════════════════════════
# Verifier Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestVerifierHelpers:
    def test_parse_verification_json(self):
        response = """
        Analisando a resposta...
        ```json
        {
            "is_consistent": true,
            "confidence": 0.85,
            "issues": [],
            "requires_new_search": false,
            "suggestion": ""
        }
        ```
        """
        result = _parse_verification_result(response)
        assert result["is_consistent"] is True
        assert result["confidence"] == 0.85
        assert result["issues"] == []

    def test_parse_verification_rejection(self):
        response = """
        ```json
        {
            "is_consistent": false,
            "confidence": 0.3,
            "issues": ["Citação incorreta", "Afirmação sem suporte"],
            "requires_new_search": true,
            "suggestion": "Corrigir a citação do artigo"
        }
        ```
        """
        result = _parse_verification_result(response)
        assert result["is_consistent"] is False
        assert len(result["issues"]) == 2
        assert result["requires_new_search"] is True

    def test_parse_verification_fallback(self):
        # No JSON in response
        response = "A resposta parece consistente com as evidências."
        result = _parse_verification_result(response)
        # Should default to approved
        assert result["is_consistent"] is True

    def test_parse_verification_no_json_defaults_to_approved(self):
        # No JSON in response - defaults to approved (safer fallback)
        response = "A resposta parece estar correta."
        result = _parse_verification_result(response)
        # When no JSON is found, defaults to approved
        assert result["is_consistent"] is True
        assert result["confidence"] == 0.7


class TestVerifierNode:
    @pytest.mark.asyncio
    async def test_disabled_auto_approves(self):
        state = {
            "sub_answers": [{"node_id": "n1", "question": "Q?", "answer": "A"}],
            "cograg_verification_enabled": False,
            "metrics": {},
        }
        result = await verifier_node(state)

        assert result["verification_status"] == "approved"
        assert result["metrics"]["verifier_enabled"] is False

    @pytest.mark.asyncio
    async def test_no_answers_skip(self):
        state = {
            "sub_answers": [],
            "cograg_verification_enabled": True,
            "metrics": {},
        }
        result = await verifier_node(state)

        assert result["verification_status"] == "approved"

    @pytest.mark.asyncio
    async def test_verifies_and_approves(self):
        state = {
            "sub_answers": [
                {"node_id": "n1", "question": "Q?", "answer": "Answer"},
            ],
            "evidence_map": {
                "n1": {"local_results": [{"text": "Evidence"}], "global_results": [], "chunk_results": []},
            },
            "refined_evidence": {},
            "rethink_count": 0,
            "max_rethink": 2,
            "cograg_verification_enabled": True,
            "metrics": {},
        }

        with patch("app.services.rag.core.cograg.nodes.verifier._call_llm") as mock_llm:
            mock_llm.return_value = '{"is_consistent": true, "confidence": 0.9, "issues": [], "requires_new_search": false}'
            result = await verifier_node(state)

        assert result["verification_status"] == "approved"
        assert result["verification_issues"] == []

    @pytest.mark.asyncio
    async def test_verifies_and_rejects(self):
        state = {
            "sub_answers": [
                {"node_id": "n1", "question": "Q?", "answer": "Bad answer"},
            ],
            "evidence_map": {
                "n1": {"local_results": [{"text": "Evidence"}], "global_results": [], "chunk_results": []},
            },
            "refined_evidence": {},
            "rethink_count": 0,
            "max_rethink": 2,
            "cograg_verification_enabled": True,
            "metrics": {},
        }

        with patch("app.services.rag.core.cograg.nodes.verifier._call_llm") as mock_llm:
            mock_llm.return_value = '{"is_consistent": false, "confidence": 0.2, "issues": ["Problema encontrado"], "requires_new_search": false}'
            result = await verifier_node(state)

        assert result["verification_status"] == "rejected"
        assert len(result["verification_issues"]) > 0


class TestQueryRewriterNode:
    @pytest.mark.asyncio
    async def test_increments_rethink_count(self):
        state = {
            "query": "Original query",
            "verification_issues": ["Issue 1"],
            "rethink_count": 0,
            "metrics": {},
        }
        result = await query_rewriter_node(state)

        assert result["rethink_count"] == 1
        assert "rewriter_attempts" in result["metrics"]


# ═══════════════════════════════════════════════════════════════════════════
# Integrator Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestIntegratorHelpers:
    def test_format_sub_answers(self):
        sub_answers = [
            {"question": "Q1?", "answer": "A1", "confidence": 0.9, "citations": ["Art. 5"]},
            {"question": "Q2?", "answer": "A2", "confidence": 0.8, "citations": []},
        ]
        formatted = _format_sub_answers(sub_answers)

        assert "Q1?" in formatted
        assert "A1" in formatted
        assert "90%" in formatted  # confidence
        assert "[Art. 5]" in formatted

    def test_format_sub_answers_empty(self):
        formatted = _format_sub_answers([])
        assert "Nenhuma resposta" in formatted

    def test_collect_citations(self):
        sub_answers = [
            {"citations": ["Art. 5", "Lei 8112"]},
            {"citations": ["art. 5", "Súmula 331"]},  # art. 5 duplicate (case insensitive)
            {"citations": []},
        ]
        citations = _collect_citations(sub_answers)

        assert len(citations) == 3  # Art. 5, Lei 8112, Súmula 331 (art. 5 deduped)
        assert "Lei 8112" in citations
        assert "Súmula 331" in citations

    def test_rule_based_integration_single(self):
        sub_answers = [{"answer": "Only answer"}]
        result = _rule_based_integration("Query", sub_answers)
        assert result == "Only answer"

    def test_rule_based_integration_multiple(self):
        sub_answers = [
            {"answer": "First answer about topic."},
            {"answer": "Second related point."},
        ]
        result = _rule_based_integration("Query", sub_answers)

        assert "First answer" in result
        assert "Além disso" in result  # Transition word
        assert "second" in result.lower()


class TestIntegratorNode:
    @pytest.mark.asyncio
    async def test_no_query_skip(self):
        state = {"query": "", "sub_answers": [], "metrics": {}}
        result = await integrator_node(state)

        assert result["integrated_response"] is None

    @pytest.mark.asyncio
    async def test_single_answer_no_synthesis(self):
        state = {
            "query": "Test query",
            "sub_answers": [
                {"question": "Q?", "answer": "Single answer", "confidence": 0.9, "citations": ["Art. 1"]},
            ],
            "verification_status": "approved",
            "verification_issues": [],
            "cograg_abstain_mode": True,
            "metrics": {},
        }
        result = await integrator_node(state)

        # Single answer should be returned directly
        assert result["integrated_response"] == "Single answer"
        assert "Art. 1" in result["citations_used"]

    @pytest.mark.asyncio
    async def test_multiple_answers_synthesis(self):
        state = {
            "query": "Complex query",
            "sub_answers": [
                {"question": "Q1?", "answer": "Answer 1", "confidence": 0.9, "citations": ["Art. 5"]},
                {"question": "Q2?", "answer": "Answer 2", "confidence": 0.8, "citations": ["Lei 8112"]},
            ],
            "verification_status": "approved",
            "verification_issues": [],
            "cograg_abstain_mode": True,
            "metrics": {},
        }

        with patch("app.services.rag.core.cograg.nodes.integrator._call_llm") as mock_llm:
            mock_llm.return_value = "Integrated response combining both answers"
            result = await integrator_node(state)

        assert result["integrated_response"] == "Integrated response combining both answers"
        assert len(result["citations_used"]) == 2

    @pytest.mark.asyncio
    async def test_abstain_mode(self):
        state = {
            "query": "Difficult query",
            "sub_answers": [
                {"question": "Q?", "answer": "Partial answer", "confidence": 0.3, "citations": []},
            ],
            "verification_status": "abstain",
            "verification_issues": ["Insufficient evidence"],
            "cograg_abstain_mode": True,
            "metrics": {},
        }

        with patch("app.services.rag.core.cograg.nodes.integrator._call_llm") as mock_llm:
            mock_llm.return_value = "Explanation of why we cannot answer"
            result = await integrator_node(state)

        assert "abstain_info" in result
        assert result["abstain_info"]["reason"] == "insufficient_evidence"
        assert result["metrics"]["integrator_abstained"] is True

    @pytest.mark.asyncio
    async def test_llm_failure_fallback(self):
        state = {
            "query": "Test query",
            "sub_answers": [
                {"question": "Q1?", "answer": "Answer 1", "confidence": 0.9, "citations": []},
                {"question": "Q2?", "answer": "Answer 2", "confidence": 0.8, "citations": []},
            ],
            "verification_status": "approved",
            "verification_issues": [],
            "cograg_abstain_mode": True,
            "metrics": {},
        }

        with patch("app.services.rag.core.cograg.nodes.integrator._call_llm") as mock_llm:
            mock_llm.return_value = ""  # LLM failed
            result = await integrator_node(state)

        # Should fallback to rule-based integration
        assert result["integrated_response"] is not None
        assert "Answer 1" in result["integrated_response"]
