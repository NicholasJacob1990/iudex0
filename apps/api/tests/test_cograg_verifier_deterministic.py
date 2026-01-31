"""
Tests for deterministic CogRAG verifier gate.

Focus: ensure refs/citations are validated against evidence context without LLM.
"""

from __future__ import annotations

from app.services.rag.core.cograg.nodes.verifier import _deterministic_verify_answer


def _evidence_with(text: str, *, ref: str = "abc"):
    return {
        "chunk_results": [
            {"chunk_uid": ref, "text": text, "score": 0.9, "metadata": {}},
        ]
    }


def test_deterministic_accepts_valid_ref():
    evidence = _evidence_with("Texto qualquer Art. 37 Lei 8.112/90 Súmula 331")
    answer_data = {
        "answer": "Conforme a evidência. [ref:abc]",
        "evidence_refs": ["abc"],
    }
    res = _deterministic_verify_answer(answer_data, evidence)
    assert res["is_consistent"] is True


def test_deterministic_rejects_invalid_ref():
    evidence = _evidence_with("Texto qualquer")
    answer_data = {"answer": "Algo. [ref:xyz]"}
    res = _deterministic_verify_answer(answer_data, evidence)
    assert res["is_consistent"] is False
    assert res["requires_new_search"] is True


def test_deterministic_rejects_missing_citation():
    evidence = _evidence_with("Texto sem referências")
    answer_data = {"answer": "Aplica-se o Art. 37."}
    res = _deterministic_verify_answer(answer_data, evidence)
    assert res["is_consistent"] is False


def test_deterministic_accepts_citation_present_in_evidence():
    evidence = _evidence_with("Baseado no Art. 37 da CF e Súmula 331.")
    answer_data = {"answer": "Nos termos do Art. 37 e Súmula 331."}
    res = _deterministic_verify_answer(answer_data, evidence)
    assert res["is_consistent"] is True


def test_deterministic_accepts_law_format_variation():
    # Evidence uses "Lei nº 8112, de 1990", answer cites "Lei 8.112/90"
    evidence = _evidence_with("Conforme a Lei nº 8112, de 1990, aplica-se ...")
    answer_data = {"answer": "Nos termos da Lei 8.112/90."}
    res = _deterministic_verify_answer(answer_data, evidence)
    assert res["is_consistent"] is True


def test_deterministic_accepts_article_written_as_artigo():
    evidence = _evidence_with("O artigo 37 da Constituição estabelece ...")
    answer_data = {"answer": "Conforme Art. 37."}
    res = _deterministic_verify_answer(answer_data, evidence)
    assert res["is_consistent"] is True


def test_deterministic_allows_abstain_without_citations():
    evidence = _evidence_with("Texto sem referências")
    answer_data = {"answer": "Não encontrei evidência suficiente para responder."}
    res = _deterministic_verify_answer(answer_data, evidence)
    assert res["is_consistent"] is True
