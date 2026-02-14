"""
Tests for Legal Query Classifier (dynamic sparse/dense weights).

Covers:
- Fast-path regex (CNJ, Art./§)
- LLM classification (mocked)
- Weight correctness for each category
- Fallback on LLM failure
- Cache behavior
- Edge cases
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.rag.core.query_classifier import (
    CATEGORY_WEIGHTS,
    ClassificationResult,
    QueryCategory,
    _fast_path,
    _llm_cache,
    classify_query,
    classify_query_sync,
    clear_classification_cache,
)


# ---------------------------------------------------------------------------
# Fast-path regex tests
# ---------------------------------------------------------------------------


class TestFastPath:
    def test_cnj_number(self):
        assert _fast_path("0001234-56.2024.8.26.0100") == QueryCategory.IDENTIFICADOR

    def test_cnj_in_context(self):
        assert _fast_path("processo 0001234-56.2024.8.26.0100 réu") == QueryCategory.IDENTIFICADOR

    def test_artigo(self):
        assert _fast_path("Art. 927 do CC") == QueryCategory.DISPOSITIVO

    def test_artigo_lowercase(self):
        assert _fast_path("art 5 da CF") == QueryCategory.DISPOSITIVO

    def test_paragrafo(self):
        assert _fast_path("§ 5º da CF") == QueryCategory.DISPOSITIVO

    def test_inciso(self):
        assert _fast_path("inciso III do art. 5") == QueryCategory.DISPOSITIVO

    def test_sumula(self):
        assert _fast_path("Súmula 385 do STJ") == QueryCategory.DISPOSITIVO

    def test_sumula_vinculante(self):
        assert _fast_path("Súmula Vinculante 11") == QueryCategory.DISPOSITIVO

    def test_alinea(self):
        assert _fast_path("alínea b do inciso I") == QueryCategory.DISPOSITIVO

    def test_no_match(self):
        assert _fast_path("teoria do risco integral") is None

    def test_empty_string(self):
        assert _fast_path("") is None

    def test_general_question(self):
        assert _fast_path("o que fazer neste caso?") is None


# ---------------------------------------------------------------------------
# Weights correctness
# ---------------------------------------------------------------------------


class TestCategoryWeights:
    def test_all_categories_have_weights(self):
        for cat in QueryCategory:
            assert cat in CATEGORY_WEIGHTS, f"Missing weights for {cat}"

    def test_weights_sum_to_one(self):
        for cat, (w_s, w_d) in CATEGORY_WEIGHTS.items():
            assert abs(w_s + w_d - 1.0) < 0.001, f"{cat}: {w_s}+{w_d} != 1.0"

    def test_sparse_dominant_order(self):
        """Sparse-dominant categories should have w_sparse > w_dense."""
        for cat in [QueryCategory.IDENTIFICADOR, QueryCategory.DISPOSITIVO, QueryCategory.NORMA, QueryCategory.FACTUAL]:
            w_s, w_d = CATEGORY_WEIGHTS[cat]
            assert w_s > w_d, f"{cat}: expected sparse > dense"

    def test_dense_dominant_order(self):
        """Dense-dominant categories should have w_dense > w_sparse."""
        for cat in [QueryCategory.ARGUMENTATIVO, QueryCategory.CONCEITUAL]:
            w_s, w_d = CATEGORY_WEIGHTS[cat]
            assert w_d > w_s, f"{cat}: expected dense > sparse"

    def test_general_is_balanced(self):
        w_s, w_d = CATEGORY_WEIGHTS[QueryCategory.GENERAL]
        assert w_s == w_d == 0.50

    def test_identificador_is_most_sparse(self):
        w_s, _ = CATEGORY_WEIGHTS[QueryCategory.IDENTIFICADOR]
        for cat, (other_s, _) in CATEGORY_WEIGHTS.items():
            if cat != QueryCategory.IDENTIFICADOR:
                assert w_s >= other_s, f"IDENTIFICADOR should be >= {cat}"

    def test_conceitual_is_most_dense(self):
        _, w_d = CATEGORY_WEIGHTS[QueryCategory.CONCEITUAL]
        for cat, (_, other_d) in CATEGORY_WEIGHTS.items():
            if cat != QueryCategory.CONCEITUAL:
                assert w_d >= other_d, f"CONCEITUAL should be >= {cat}"


# ---------------------------------------------------------------------------
# Sync classify
# ---------------------------------------------------------------------------


class TestClassifyQuerySync:
    def test_cnj_returns_identificador(self):
        result = classify_query_sync("0001234-56.2024.8.26.0100")
        assert result.category == QueryCategory.IDENTIFICADOR
        assert result.w_sparse == 0.90
        assert result.w_dense == 0.10
        assert result.used_llm is False

    def test_artigo_returns_dispositivo(self):
        result = classify_query_sync("Art. 927 do CC")
        assert result.category == QueryCategory.DISPOSITIVO
        assert result.w_sparse == 0.75
        assert result.used_llm is False

    def test_unknown_returns_general(self):
        result = classify_query_sync("teoria do risco integral")
        assert result.category == QueryCategory.GENERAL
        assert result.w_sparse == 0.50
        assert result.w_dense == 0.50

    def test_empty_returns_general(self):
        result = classify_query_sync("")
        assert result.category == QueryCategory.GENERAL

    def test_none_returns_general(self):
        result = classify_query_sync(None)
        assert result.category == QueryCategory.GENERAL


# ---------------------------------------------------------------------------
# Async classify (LLM mocked)
# ---------------------------------------------------------------------------


def _mock_genai_response(text: str):
    """Create a mock google genai response."""
    resp = MagicMock()
    resp.text = text
    return resp


class TestClassifyQueryAsync:
    @pytest.fixture(autouse=True)
    def _clear_cache(self):
        clear_classification_cache()
        yield
        clear_classification_cache()

    @pytest.mark.asyncio
    async def test_fast_path_skips_llm(self):
        """Fast-path regex should not call LLM."""
        result = await classify_query("0001234-56.2024.8.26.0100", use_llm=True)
        assert result.category == QueryCategory.IDENTIFICADOR
        assert result.used_llm is False

    @pytest.mark.asyncio
    async def test_llm_classifies_doutrina(self):
        with patch("app.services.rag.core.query_classifier.asyncio") as mock_aio:
            mock_aio.to_thread = AsyncMock(
                return_value=_mock_genai_response("CATEGORY: conceitual")
            )
            with patch("app.services.rag.core.query_classifier.genai", create=True):
                # Patch the actual import inside the function
                with patch(
                    "app.services.rag.core.query_classifier._classify_with_llm",
                    new_callable=AsyncMock,
                    return_value=QueryCategory.CONCEITUAL,
                ):
                    result = await classify_query("teoria do risco integral")
                    assert result.category == QueryCategory.CONCEITUAL
                    assert result.w_sparse == 0.25
                    assert result.w_dense == 0.75
                    assert result.used_llm is True

    @pytest.mark.asyncio
    async def test_llm_classifies_jurisprudencia(self):
        with patch(
            "app.services.rag.core.query_classifier._classify_with_llm",
            new_callable=AsyncMock,
            return_value=QueryCategory.JURISPRUDENCIA,
        ):
            result = await classify_query("precedentes sobre dano moral")
            assert result.category == QueryCategory.JURISPRUDENCIA
            assert result.w_sparse == 0.40
            assert result.w_dense == 0.60

    @pytest.mark.asyncio
    async def test_llm_classifies_argumentativo(self):
        with patch(
            "app.services.rag.core.query_classifier._classify_with_llm",
            new_callable=AsyncMock,
            return_value=QueryCategory.ARGUMENTATIVO,
        ):
            result = await classify_query("tese de responsabilidade objetiva")
            assert result.category == QueryCategory.ARGUMENTATIVO
            assert result.w_sparse == 0.35
            assert result.w_dense == 0.65

    @pytest.mark.asyncio
    async def test_llm_classifies_norma(self):
        with patch(
            "app.services.rag.core.query_classifier._classify_with_llm",
            new_callable=AsyncMock,
            return_value=QueryCategory.NORMA,
        ):
            result = await classify_query("Lei 14.133/2021")
            assert result.category == QueryCategory.NORMA
            assert result.w_sparse == 0.65

    @pytest.mark.asyncio
    async def test_llm_classifies_factual(self):
        with patch(
            "app.services.rag.core.query_classifier._classify_with_llm",
            new_callable=AsyncMock,
            return_value=QueryCategory.FACTUAL,
        ):
            result = await classify_query("provas documentais do dano")
            assert result.category == QueryCategory.FACTUAL
            assert result.w_sparse == 0.60

    @pytest.mark.asyncio
    async def test_llm_classifies_procedimento(self):
        with patch(
            "app.services.rag.core.query_classifier._classify_with_llm",
            new_callable=AsyncMock,
            return_value=QueryCategory.PROCEDIMENTO,
        ):
            result = await classify_query("prazo para recurso de apelação")
            assert result.category == QueryCategory.PROCEDIMENTO
            assert result.w_sparse == 0.55

    @pytest.mark.asyncio
    async def test_llm_failure_fallback(self):
        """When LLM fails, should fallback to GENERAL."""
        with patch(
            "app.services.rag.core.query_classifier._classify_with_llm",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await classify_query("algo vago e incerto")
            assert result.category == QueryCategory.GENERAL
            assert result.w_sparse == 0.50
            assert result.used_llm is False

    @pytest.mark.asyncio
    async def test_llm_disabled(self):
        """When use_llm=False, should only use regex and fallback."""
        result = await classify_query("teoria do risco", use_llm=False)
        assert result.category == QueryCategory.GENERAL
        assert result.used_llm is False

    @pytest.mark.asyncio
    async def test_custom_defaults(self):
        """Custom default weights should be used for GENERAL fallback."""
        result = await classify_query(
            "pergunta genérica",
            use_llm=False,
            default_sparse=0.60,
            default_dense=0.40,
        )
        assert result.w_sparse == 0.60
        assert result.w_dense == 0.40


# ---------------------------------------------------------------------------
# Cache behavior
# ---------------------------------------------------------------------------


class TestClassificationCache:
    def test_clear_cache(self):
        _llm_cache["test_key"] = QueryCategory.NORMA
        count = clear_classification_cache()
        assert count == 1
        assert len(_llm_cache) == 0

    def test_clear_empty_cache(self):
        clear_classification_cache()
        count = clear_classification_cache()
        assert count == 0


# ---------------------------------------------------------------------------
# ClassificationResult
# ---------------------------------------------------------------------------


class TestClassificationResult:
    def test_repr(self):
        r = ClassificationResult(QueryCategory.NORMA, 0.65, 0.35, True)
        assert "norma" in repr(r)
        assert "0.65" in repr(r)
        assert "llm=True" in repr(r)

    def test_slots(self):
        r = ClassificationResult(QueryCategory.GENERAL, 0.5, 0.5, False)
        assert r.category == QueryCategory.GENERAL
        assert r.w_sparse == 0.5
        assert r.w_dense == 0.5
        assert r.used_llm is False
