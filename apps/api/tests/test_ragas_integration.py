"""
Tests for RAGAs integration with legal metrics.

Verifica que:
1. evaluate_with_ragas() funciona com samples de exemplo
2. Métricas legais são sempre calculadas (mesmo sem RAGAs)
3. Score combinado é calculado corretamente
4. add_legal_metrics_to_ragas() funciona standalone
"""

import pytest
from app.services.ai.rag_evaluator import (
    evaluate_legal_answer,
    evaluate_legal_batch,
    add_legal_metrics_to_ragas,
)


# =============================================================================
# Fixtures
# =============================================================================

SAMPLE_LEGAL_QA = [
    {
        "question": "Qual o prazo para publicação de edital de licitação?",
        "answer": (
            "Conforme a Lei 14.133/2021, Art. 55, o prazo mínimo para publicação "
            "do edital é de 8 dias úteis para pregão eletrônico."
        ),
        "ground_truth": (
            "O prazo mínimo para publicação do edital de licitação varia conforme a "
            "modalidade. Para pregão eletrônico, é de 8 dias úteis (Art. 55, Lei 14.133/2021)."
        ),
        "contexts": [
            "Art. 55 da Lei 14.133/2021 estabelece prazos mínimos para publicação de editais.",
            "O pregão eletrônico tem prazo mínimo de 8 dias úteis para publicação.",
        ],
    },
    {
        "question": "O que diz a Súmula 331 do TST?",
        "answer": (
            "A Súmula 331 do TST trata da terceirização trabalhista. Estabelece que "
            "a contratação de trabalhadores por empresa interposta é ilegal, "
            "formando-se vínculo diretamente com o tomador de serviços."
        ),
        "ground_truth": (
            "A Súmula 331 do TST disciplina a terceirização, estabelecendo a "
            "responsabilidade subsidiária do tomador de serviços."
        ),
        "contexts": [
            "Súmula 331 TST - Contrato de Prestação de Serviços. Legalidade.",
        ],
    },
]


# =============================================================================
# Tests: evaluate_legal_answer
# =============================================================================


class TestEvaluateLegalAnswer:
    """Testa avaliação de resposta legal individual."""

    def test_basic_evaluation(self):
        result = evaluate_legal_answer(
            query="Qual o prazo do edital?",
            answer="Conforme a Lei 14.133/2021, Art. 55, o prazo é de 8 dias.",
            ground_truth="Art. 55 da Lei 14.133/2021 define 8 dias para pregão.",
        )
        assert 0.0 <= result.citation_coverage <= 1.0
        assert 0.0 <= result.temporal_validity <= 1.0
        assert isinstance(result.jurisdiction_match, bool)

    def test_evaluation_with_entities(self):
        # Note: evaluator normalizes "14.133" → "14133" (removes dots)
        result = evaluate_legal_answer(
            query="Qual lei de licitações?",
            answer="A Lei 14.133/2021 é a nova lei de licitações.",
            ground_truth="Lei 14.133/2021.",
            expected_entities=["Lei 14133/2021"],
        )
        assert result.entity_recall > 0.0

    def test_evaluation_with_jurisdiction(self):
        result = evaluate_legal_answer(
            query="Competência federal?",
            answer="O STF decidiu no RE 123456.",
            ground_truth="Competência da Justiça Federal.",
            expected_jurisdiction="federal",
        )
        assert isinstance(result.jurisdiction_match, bool)


# =============================================================================
# Tests: evaluate_legal_batch
# =============================================================================


class TestEvaluateLegalBatch:
    """Testa avaliação em lote."""

    def test_batch_returns_summary(self):
        result = evaluate_legal_batch(SAMPLE_LEGAL_QA)
        assert "summary" in result
        assert "legal_score" in result["summary"]

    def test_batch_summary_has_all_metrics(self):
        result = evaluate_legal_batch(SAMPLE_LEGAL_QA)
        summary = result["summary"]
        assert "legal_citation_coverage" in summary
        assert "legal_temporal_validity" in summary
        assert "legal_jurisdiction_match" in summary
        assert "legal_entity_precision" in summary
        assert "legal_entity_recall" in summary

    def test_batch_per_sample_metrics(self):
        result = evaluate_legal_batch(SAMPLE_LEGAL_QA)
        for sample in result["samples"]:
            assert "legal_metrics" in sample


# =============================================================================
# Tests: add_legal_metrics_to_ragas
# =============================================================================


class TestAddLegalMetricsToRagas:
    """Testa integração de métricas legais com formato RAGAS."""

    def test_adds_metrics_to_samples(self):
        results = {"samples": SAMPLE_LEGAL_QA.copy()}
        enriched = add_legal_metrics_to_ragas(results)
        for sample in enriched["samples"]:
            assert "legal_metrics" in sample

    def test_calculates_summary(self):
        results = {"samples": SAMPLE_LEGAL_QA.copy()}
        enriched = add_legal_metrics_to_ragas(results)
        assert "legal_score" in enriched["summary"]
        assert 0.0 <= enriched["summary"]["legal_score"] <= 1.0

    def test_empty_samples_returns_unchanged(self):
        results = {"samples": []}
        enriched = add_legal_metrics_to_ragas(results)
        assert enriched == results


# =============================================================================
# Tests: evaluate_with_ragas (async)
# =============================================================================


class TestEvaluateWithRagas:
    """Testa evaluate_with_ragas() — integração completa."""

    @pytest.mark.asyncio
    async def test_returns_legal_scores_always(self):
        """Métricas legais devem funcionar mesmo se RAGAs não está instalado."""
        from app.services.ai.rag_evaluator import evaluate_with_ragas
        result = await evaluate_with_ragas(SAMPLE_LEGAL_QA)
        assert "legal_scores" in result
        assert len(result["legal_scores"]) > 0

    @pytest.mark.asyncio
    async def test_returns_combined_score(self):
        from app.services.ai.rag_evaluator import evaluate_with_ragas
        result = await evaluate_with_ragas(SAMPLE_LEGAL_QA)
        assert "combined_score" in result
        assert 0.0 <= result["combined_score"] <= 1.0

    @pytest.mark.asyncio
    async def test_per_sample_results(self):
        from app.services.ai.rag_evaluator import evaluate_with_ragas
        result = await evaluate_with_ragas(SAMPLE_LEGAL_QA)
        assert len(result["per_sample"]) == len(SAMPLE_LEGAL_QA)

    @pytest.mark.asyncio
    async def test_ragas_available_flag(self):
        """O resultado deve indicar se RAGAs estava disponível."""
        from app.services.ai.rag_evaluator import evaluate_with_ragas
        result = await evaluate_with_ragas(SAMPLE_LEGAL_QA)
        assert "ragas_available" in result
        assert isinstance(result["ragas_available"], bool)
