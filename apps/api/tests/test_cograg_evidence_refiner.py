"""
Tests for CogGRAG evidence refiner node.

Covers: conflict detection, quality scoring, evidence refinement.
"""

import pytest
from unittest.mock import patch

from app.services.rag.core.cograg.nodes.evidence_refiner import (
    _extract_legal_numbers,
    _detect_contradiction_signals,
    _compute_evidence_quality_score,
    evidence_refiner_node,
)


# ═══════════════════════════════════════════════════════════════════════════
# Legal Number Extraction
# ═══════════════════════════════════════════════════════════════════════════

class TestExtractLegalNumbers:
    def test_extract_artigo(self):
        text = "Conforme Art. 5 da CF e Artigo 123 do CC"
        nums = _extract_legal_numbers(text)
        assert "5" in nums
        assert "123" in nums

    def test_extract_lei(self):
        text = "Lei 8.112/90 e Lei nº 13.467/2017"
        nums = _extract_legal_numbers(text)
        assert "8.112/90" in nums or "8112" in nums
        assert "13.467/2017" in nums or "13467" in nums

    def test_extract_sumula(self):
        text = "Súmula 331 do TST e Súmula n° 473"
        nums = _extract_legal_numbers(text)
        assert "331" in nums
        assert "473" in nums

    def test_empty_text(self):
        nums = _extract_legal_numbers("")
        assert len(nums) == 0

    def test_no_legal_refs(self):
        text = "Este texto não possui referências legais específicas."
        nums = _extract_legal_numbers(text)
        assert len(nums) == 0


# ═══════════════════════════════════════════════════════════════════════════
# Contradiction Detection
# ═══════════════════════════════════════════════════════════════════════════

class TestDetectContradictionSignals:
    def test_negation_mismatch(self):
        text1 = "A cláusula se aplica normalmente"
        text2 = "A cláusula não se aplica neste caso"
        signals = _detect_contradiction_signals(text1, text2)
        assert len(signals) > 0
        assert "negação de aplicabilidade" in signals

    def test_prohibition_mismatch(self):
        text1 = "É permitido o uso da ferramenta"
        text2 = "É vedado o uso da ferramenta nestas condições"
        signals = _detect_contradiction_signals(text1, text2)
        assert len(signals) > 0
        assert "proibição explícita" in signals

    def test_opposite_conclusions(self):
        text1 = "O Art. 5 permite a conduta descrita"
        text2 = "O Art. 5 veda tal procedimento"
        signals = _detect_contradiction_signals(text1, text2)
        assert len(signals) > 0

    def test_no_contradiction(self):
        text1 = "O prazo é de 5 anos para prescrição"
        text2 = "A prescrição ocorre em 5 anos conforme a lei"
        signals = _detect_contradiction_signals(text1, text2)
        assert len(signals) == 0

    def test_both_have_negation(self):
        text1 = "Não se aplica a regra geral"
        text2 = "Não incide a exceção prevista"
        signals = _detect_contradiction_signals(text1, text2)
        # Both have negation, so no mismatch
        assert "negação de aplicabilidade" not in signals


# ═══════════════════════════════════════════════════════════════════════════
# Quality Scoring
# ═══════════════════════════════════════════════════════════════════════════

class TestComputeEvidenceQualityScore:
    def test_high_quality_jurisprudencia(self):
        chunk = {
            "score": 0.95,
            "source": "jurisprudencia_tst",
            "doc_type": "acordao",
            "text": "RECURSO DE REVISTA. " + "x" * 600,  # Long text
        }
        score = _compute_evidence_quality_score(chunk)
        assert score >= 0.7

    def test_medium_quality_doutrina(self):
        chunk = {
            "score": 0.7,
            "source": "doutrina",
            "text": "Conforme Art. 5 da CF, " + "y" * 300,
        }
        score = _compute_evidence_quality_score(chunk)
        assert 0.4 <= score <= 0.8

    def test_low_quality_short_text(self):
        chunk = {
            "score": 0.3,
            "text": "Texto curto",
        }
        score = _compute_evidence_quality_score(chunk)
        assert score <= 0.3

    def test_legal_refs_boost(self):
        chunk_no_refs = {
            "score": 0.5,
            "text": "Texto sem referências específicas " * 20,
        }
        chunk_with_refs = {
            "score": 0.5,
            "text": "Art. 5, Art. 7 e Art. 8 da CF " * 20,
        }
        score_no_refs = _compute_evidence_quality_score(chunk_no_refs)
        score_with_refs = _compute_evidence_quality_score(chunk_with_refs)
        assert score_with_refs > score_no_refs

    def test_score_capped_at_one(self):
        chunk = {
            "score": 2.0,  # Impossibly high
            "source": "jurisprudencia",
            "doc_type": "acordao",
            "text": "Art. 1, Art. 2, Art. 3, Art. 4 " * 50,
        }
        score = _compute_evidence_quality_score(chunk)
        assert score <= 1.0


# ═══════════════════════════════════════════════════════════════════════════
# Evidence Refiner Node
# ═══════════════════════════════════════════════════════════════════════════

class TestEvidenceRefinerNode:
    @pytest.mark.asyncio
    async def test_empty_evidence(self):
        state = {"evidence_map": {}, "text_chunks": []}
        result = await evidence_refiner_node(state)

        assert result["refined_evidence"] == {}
        assert result["conflicts"] == []
        assert result["metrics"]["refiner_latency_ms"] >= 0

    @pytest.mark.asyncio
    async def test_single_node_no_conflict(self):
        state = {
            "evidence_map": {
                "node1": {
                    "node_id": "node1",
                    "question": "Qual o prazo?",
                    "local_results": [
                        {"text": "O prazo é de 5 anos", "score": 0.9, "_content_hash": "h1"},
                        {"text": "Prescrição em 5 anos conforme lei", "score": 0.85, "_content_hash": "h2"},
                    ],
                    "global_results": [],
                    "chunk_results": [],
                }
            },
            "text_chunks": [],
            "metrics": {},
        }
        result = await evidence_refiner_node(state)

        assert "node1" in result["refined_evidence"]
        assert result["refined_evidence"]["node1"]["quality_score"] > 0
        assert result["refined_evidence"]["node1"]["has_conflicts"] is False

    @pytest.mark.asyncio
    async def test_detect_intra_node_conflict(self):
        state = {
            "evidence_map": {
                "node1": {
                    "node_id": "node1",
                    "question": "A cláusula se aplica?",
                    "local_results": [
                        {"text": "A cláusula se aplica normalmente ao caso", "score": 0.9, "_content_hash": "h1"},
                        {"text": "A cláusula não se aplica neste contexto específico", "score": 0.85, "_content_hash": "h2"},
                    ],
                    "global_results": [],
                    "chunk_results": [],
                }
            },
            "text_chunks": [],
            "metrics": {},
        }
        result = await evidence_refiner_node(state)

        assert len(result["conflicts"]) > 0
        assert result["refined_evidence"]["node1"]["has_conflicts"] is True

    @pytest.mark.asyncio
    async def test_chunks_sorted_by_quality(self):
        state = {
            "evidence_map": {
                "node1": {
                    "node_id": "node1",
                    "question": "Test",
                    "local_results": [
                        {"text": "Low quality", "score": 0.3, "_content_hash": "h1"},
                        {"text": "High quality jurisprudencia acordao " * 50, "score": 0.95, "source": "jurisprudencia", "_content_hash": "h2"},
                    ],
                    "global_results": [],
                    "chunk_results": [],
                }
            },
            "text_chunks": [],
            "metrics": {},
        }
        result = await evidence_refiner_node(state)

        chunks = result["refined_evidence"]["node1"]["chunks"]
        assert len(chunks) == 2
        # Higher quality should be first
        assert chunks[0]["_quality_score"] >= chunks[1]["_quality_score"]

    @pytest.mark.asyncio
    async def test_cross_node_conflict_detection(self):
        state = {
            "evidence_map": {
                "node1": {
                    "node_id": "node1",
                    "question": "Q1?",
                    "local_results": [
                        {"text": "Conforme Art. 5 da CF, a conduta é autorizada e válida", "score": 0.9, "_content_hash": "h1"},
                    ],
                    "global_results": [],
                    "chunk_results": [],
                },
                "node2": {
                    "node_id": "node2",
                    "question": "Q2?",
                    "local_results": [
                        {"text": "O Art. 5 da CF veda expressamente tal procedimento como inválido", "score": 0.9, "_content_hash": "h2"},
                    ],
                    "global_results": [],
                    "chunk_results": [],
                },
            },
            "text_chunks": [],
            "metrics": {},
        }
        result = await evidence_refiner_node(state)

        # Should detect cross-node conflict (opposite conclusions on same Art. 5)
        cross_conflicts = [c for c in result["conflicts"] if c["type"] == "cross_node"]
        assert len(cross_conflicts) > 0

    @pytest.mark.asyncio
    async def test_metrics_populated(self):
        state = {
            "evidence_map": {
                "node1": {
                    "node_id": "node1",
                    "question": "Test",
                    "local_results": [{"text": "Test text", "score": 0.8, "_content_hash": "h1"}],
                    "global_results": [],
                    "chunk_results": [],
                }
            },
            "text_chunks": [],
            "metrics": {"existing_metric": 123},
        }
        result = await evidence_refiner_node(state)

        assert "refiner_latency_ms" in result["metrics"]
        assert "refiner_conflicts" in result["metrics"]
        assert "refiner_avg_quality" in result["metrics"]
        assert result["metrics"]["existing_metric"] == 123
