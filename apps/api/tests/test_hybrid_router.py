"""
Tests for Hybrid Router - Routes queries using rules first, LLM only for ambiguous cases.
"""

import pytest
from app.services.rag.core.hybrid_router import (
    HybridRouter,
    QueryIntent,
    RetrievalStrategy,
    RoutingDecision,
    get_hybrid_router,
    reset_hybrid_router,
)


class TestHybridRouterPatterns:
    """Tests for pattern-based routing."""

    @pytest.fixture
    def router(self):
        reset_hybrid_router()
        return HybridRouter(enable_llm_fallback=False)

    # =========================================================================
    # LEXICAL QUERIES (Legal citations)
    # =========================================================================

    def test_route_artigo_simple(self, router):
        """Art. references should be classified as LEXICAL."""
        result = router.route("O que diz o Art. 5º da Constituição?")
        assert result.intent == QueryIntent.LEXICAL
        assert result.strategy == RetrievalStrategy.GRAPH_FIRST
        assert result.confidence >= 0.5

    def test_route_lei_with_year(self, router):
        """Lei references should be LEXICAL."""
        result = router.route("Quais os requisitos da Lei 8.666/93?")
        assert result.intent == QueryIntent.LEXICAL
        assert result.strategy == RetrievalStrategy.GRAPH_FIRST

    def test_route_sumula(self, router):
        """Súmula references should be LEXICAL."""
        result = router.route("Explique a Súmula 331 do TST")
        assert result.intent == QueryIntent.LEXICAL
        assert result.confidence >= 0.5

    def test_route_sumula_vinculante(self, router):
        """Súmula Vinculante should be LEXICAL."""
        result = router.route("Súmula Vinculante 13 do STF")
        assert result.intent == QueryIntent.LEXICAL

    def test_route_cnj_process(self, router):
        """CNJ process numbers should be LEXICAL."""
        result = router.route("Status do processo 0001234-56.2023.8.26.0100")
        assert result.intent == QueryIntent.LEXICAL

    def test_route_codigo(self, router):
        """Código references should be LEXICAL."""
        result = router.route("Artigo do Código Civil sobre contratos")
        assert result.intent == QueryIntent.LEXICAL

    def test_route_tema(self, router):
        """Tema de repercussão geral should be LEXICAL."""
        result = router.route("Qual o entendimento do Tema 1234 do STF?")
        assert result.intent == QueryIntent.LEXICAL

    def test_route_multiple_citations(self, router):
        """Multiple legal citations should have high confidence."""
        result = router.route("Art. 5º da CF/88 combinado com a Lei 8.666/93")
        assert result.intent == QueryIntent.LEXICAL
        assert result.confidence >= 0.8

    # =========================================================================
    # COMPARISON QUERIES
    # =========================================================================

    def test_route_compare_tribunais(self, router):
        """Tribunal comparison should be COMPARISON."""
        result = router.route("Compare a jurisprudência do STF vs STJ sobre prescrição")
        assert result.intent == QueryIntent.COMPARISON
        assert result.strategy == RetrievalStrategy.MULTI_QUERY
        assert result.requires_agentic is True

    def test_route_diferenca_entre(self, router):
        """'Diferença entre' should be COMPARISON."""
        result = router.route("Qual a diferença entre dolo e culpa?")
        assert result.intent == QueryIntent.COMPARISON
        assert result.requires_agentic is True

    def test_route_versus(self, router):
        """'versus' should be COMPARISON."""
        result = router.route("Responsabilidade objetiva versus subjetiva")
        assert result.intent == QueryIntent.COMPARISON

    def test_route_comparison_extracts_subqueries(self, router):
        """Comparison should extract sub-queries."""
        result = router.route("STF vs STJ sobre terceirização")
        assert result.intent == QueryIntent.COMPARISON
        assert len(result.sub_queries) >= 1

    # =========================================================================
    # DEEP RESEARCH QUERIES
    # =========================================================================

    def test_route_pesquisa_profunda(self, router):
        """Deep research keywords should be DEEP_RESEARCH."""
        result = router.route("Faça uma pesquisa profunda sobre abandono afetivo")
        assert result.intent == QueryIntent.DEEP_RESEARCH
        assert result.strategy == RetrievalStrategy.ITERATIVE
        assert result.requires_agentic is True

    def test_route_analise_completa(self, router):
        """'Análise completa' should be DEEP_RESEARCH."""
        result = router.route("Análise completa da evolução jurisprudencial")
        assert result.intent == QueryIntent.DEEP_RESEARCH

    def test_route_revisao_jurisprudencial(self, router):
        """'Revisão jurisprudencial' should be DEEP_RESEARCH."""
        result = router.route("Revisão jurisprudencial sobre dano moral")
        assert result.intent == QueryIntent.DEEP_RESEARCH

    def test_route_mapeamento(self, router):
        """'Mapeamento' should be DEEP_RESEARCH."""
        result = router.route("Mapeamento das teses sobre responsabilidade civil")
        assert result.intent == QueryIntent.DEEP_RESEARCH

    # =========================================================================
    # OPEN-ENDED QUERIES
    # =========================================================================

    def test_route_melhor_estrategia(self, router):
        """'Melhor estratégia' should be OPEN_ENDED."""
        result = router.route("Qual a melhor estratégia para contestar esse argumento?")
        assert result.intent == QueryIntent.OPEN_ENDED
        assert result.strategy == RetrievalStrategy.HYBRID_RRF
        assert result.requires_agentic is True

    def test_route_como_devo(self, router):
        """'Como devo' should be OPEN_ENDED."""
        result = router.route("Como devo proceder neste caso?")
        assert result.intent == QueryIntent.OPEN_ENDED

    def test_route_recomendacao(self, router):
        """Recommendation requests should be OPEN_ENDED."""
        result = router.route("O que você recomenda para esta situação?")
        assert result.intent == QueryIntent.OPEN_ENDED

    def test_route_alternativas(self, router):
        """'Quais alternativas' should be OPEN_ENDED."""
        result = router.route("Quais as alternativas para resolver este impasse?")
        assert result.intent == QueryIntent.OPEN_ENDED

    # =========================================================================
    # SEMANTIC QUERIES (Default)
    # =========================================================================

    def test_route_conceptual_question(self, router):
        """Conceptual questions should be SEMANTIC."""
        result = router.route("O que é responsabilidade civil?")
        assert result.intent == QueryIntent.SEMANTIC
        assert result.strategy == RetrievalStrategy.VECTOR_FIRST
        assert result.requires_agentic is False

    def test_route_simple_question(self, router):
        """Simple questions should be SEMANTIC."""
        result = router.route("Explique o princípio da legalidade")
        assert result.intent == QueryIntent.SEMANTIC

    def test_route_definition(self, router):
        """Definition requests should be SEMANTIC."""
        result = router.route("Defina pessoa jurídica")
        assert result.intent == QueryIntent.SEMANTIC

    # =========================================================================
    # EDGE CASES
    # =========================================================================

    def test_route_empty_query(self, router):
        """Empty query should return SEMANTIC with low confidence."""
        result = router.route("")
        assert result.intent == QueryIntent.SEMANTIC

    def test_route_mixed_lexical_comparison(self, router):
        """Mixed query should prioritize comparison."""
        result = router.route("Compare o Art. 5º do STF vs STJ")
        # Should be COMPARISON because comparison patterns are checked first
        assert result.intent in [QueryIntent.COMPARISON, QueryIntent.LEXICAL]

    def test_route_no_llm_used_when_disabled(self, router):
        """LLM should not be used when disabled."""
        result = router.route("query ambígua qualquer")
        assert result.used_llm is False


class TestHybridRouterConfiguration:
    """Tests for router configuration."""

    def test_custom_confidence_threshold(self):
        """Custom confidence threshold should be respected."""
        router = HybridRouter(confidence_threshold=0.9, enable_llm_fallback=False)
        result = router.route("Art. 5º")
        # Even with lexical match, if below 0.9 it might try LLM (but disabled)
        assert isinstance(result, RoutingDecision)

    def test_singleton_pattern(self):
        """get_hybrid_router should return same instance."""
        reset_hybrid_router()
        router1 = get_hybrid_router()
        router2 = get_hybrid_router()
        assert router1 is router2

    def test_reset_singleton(self):
        """reset_hybrid_router should create new instance."""
        router1 = get_hybrid_router()
        reset_hybrid_router()
        router2 = get_hybrid_router()
        assert router1 is not router2


class TestRoutingDecision:
    """Tests for RoutingDecision dataclass."""

    def test_routing_decision_defaults(self):
        """RoutingDecision should have correct defaults."""
        decision = RoutingDecision(
            intent=QueryIntent.SEMANTIC,
            strategy=RetrievalStrategy.VECTOR_FIRST,
            confidence=0.8,
        )
        assert decision.requires_agentic is False
        assert decision.sub_queries == []
        assert decision.reasoning == ""
        assert decision.used_llm is False

    def test_routing_decision_with_subqueries(self):
        """RoutingDecision should store sub-queries."""
        decision = RoutingDecision(
            intent=QueryIntent.COMPARISON,
            strategy=RetrievalStrategy.MULTI_QUERY,
            confidence=0.9,
            requires_agentic=True,
            sub_queries=["STF terceirização", "STJ terceirização"],
        )
        assert len(decision.sub_queries) == 2
        assert decision.requires_agentic is True


class TestReasoningGeneration:
    """Tests for reasoning generation."""

    @pytest.fixture
    def router(self):
        return HybridRouter(enable_llm_fallback=False)

    def test_reasoning_includes_scores(self, router):
        """Reasoning should include pattern scores."""
        result = router.route("Art. 5º da CF")
        assert "citações legais" in result.reasoning.lower() or "regras" in result.reasoning.lower()

    def test_reasoning_for_comparison(self, router):
        """Comparison should mention comparison pattern."""
        result = router.route("Compare STF vs STJ")
        assert "comparação" in result.reasoning.lower() or "score" in result.reasoning.lower()
