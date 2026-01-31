"""
Tests for CogGRAG Planner node — complexity detection and decomposition.

Tests complexity heuristics (no LLM needed) and the planner node
structure (with mocked LLM calls).
"""

import pytest

from app.services.rag.core.cograg.nodes.planner import is_complex_query


# ═══════════════════════════════════════════════════════════════════════════
# Complexity Detection (pure logic, no LLM)
# ═══════════════════════════════════════════════════════════════════════════

class TestIsComplexQuery:
    """Test the heuristic complexity detection."""

    # ── Simple queries (should NOT decompose) ─────────────────────────

    def test_short_query(self):
        assert is_complex_query("Art. 5 CF") is False

    def test_article_citation(self):
        assert is_complex_query("art. 468 CLT") is False

    def test_sumula_citation(self):
        assert is_complex_query("sumula 331 TST") is False

    def test_simple_definition(self):
        assert is_complex_query("o que é usucapião?") is False

    def test_simple_factual(self):
        assert is_complex_query("qual é o prazo prescricional?") is False

    def test_cnj_number(self):
        assert is_complex_query("0001234-56.2024.5.02.0000") is False

    def test_empty_query(self):
        assert is_complex_query("") is False

    def test_very_short(self):
        assert is_complex_query("prazo") is False

    # ── Complex queries (SHOULD decompose) ────────────────────────────

    def test_multiple_conjunctions(self):
        assert is_complex_query(
            "Quais os requisitos para rescisão indireta e quais as verbas devidas e como calcular?"
        ) is True

    def test_comparison_question(self):
        assert is_complex_query(
            "Quais as diferenças entre responsabilidade civil objetiva e subjetiva no direito do consumidor?"
        ) is True

    def test_multi_concept_legal(self):
        assert is_complex_query(
            "A prescrição intercorrente e a interrupção do prazo no processo trabalhista"
        ) is True

    def test_long_query(self):
        # > 12 words
        assert is_complex_query(
            "Como funciona o regime de compensação de horas extras no contrato intermitente segundo a reforma trabalhista?"
        ) is True

    def test_compound_legal_issue(self):
        assert is_complex_query(
            "Nulidade do contrato de trabalho firmado com ente público sem concurso e direito ao FGTS"
        ) is True


# ═══════════════════════════════════════════════════════════════════════════
# Planner Node (with mocked LLM)
# ═══════════════════════════════════════════════════════════════════════════

class TestPlannerNode:
    """Test planner_node output structure (mocked LLM)."""

    @pytest.mark.asyncio
    async def test_simple_query_no_decomposition(self):
        """Simple query should return a 1-leaf tree without LLM calls."""
        from app.services.rag.core.cograg.nodes.planner import planner_node

        state = {
            "query": "Art. 5 CF",
            "metrics": {},
        }
        result = await planner_node(state)

        assert "mind_map" in result
        assert "sub_questions" in result
        assert "temas" in result
        assert "metrics" in result

        # Simple query → no decomposition
        assert result["metrics"]["planner_decomposed"] is False
        assert result["metrics"]["planner_leaf_count"] == 1
        assert len(result["sub_questions"]) == 1
        assert result["sub_questions"][0]["question"] == "Art. 5 CF"

    @pytest.mark.asyncio
    async def test_simple_query_tree_structure(self):
        """Check that the mind_map dict has expected keys."""
        from app.services.rag.core.cograg.nodes.planner import planner_node
        from app.services.rag.core.cograg.mindmap import CognitiveTree

        state = {"query": "sumula 331", "metrics": {}}
        result = await planner_node(state)

        tree = CognitiveTree.from_dict(result["mind_map"])
        assert tree.node_count() == 1
        assert tree.root_question == "sumula 331"
