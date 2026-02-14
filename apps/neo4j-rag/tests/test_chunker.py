"""Tests for the legal-aware chunker."""

from neo4j_rag.ingest.chunker import (
    chunk_document,
    _infer_document_type,
    _split_by_separators,
    SEPARATORS_DEFAULT,
)
from neo4j_rag.models import DocumentType


def test_infer_legislacao():
    text = "Art. 1º Esta lei dispõe sobre...\nArt. 2º Para os efeitos desta lei..."
    assert _infer_document_type(text, "lei_8112.pdf") == DocumentType.LEGISLACAO


def test_infer_jurisprudencia():
    text = "EMENTA: Recurso extraordinário...\nACÓRDÃO\nRELATÓRIO"
    assert _infer_document_type(text, "re_574706.pdf") == DocumentType.JURISPRUDENCIA


def test_infer_transcricao():
    assert _infer_document_type("bla bla", "transcricao_aula_01.docx") == DocumentType.TRANSCRICAO


def test_infer_questao():
    assert _infer_document_type("bla", "questoes_tributario.pdf") == DocumentType.QUESTAO


def test_chunk_legislacao(sample_legislacao_text):
    chunks = chunk_document(
        sample_legislacao_text,
        "doc1",
        DocumentType.LEGISLACAO,
        chunk_size=500,
    )
    assert len(chunks) >= 1
    assert all(c.doc_id == "doc1" for c in chunks)
    assert chunks[0].position == 0


def test_questao_single_chunk():
    text = "1. Qual o princípio da legalidade? a) X b) Y c) Z d) W Gabarito: A"
    chunks = chunk_document(text, "q1", DocumentType.QUESTAO, chunk_size=500)
    assert len(chunks) == 1
    assert chunks[0].hierarchy == ["questao_completa"]


def test_split_preserves_content():
    text = "Primeiro parágrafo.\n\nSegundo parágrafo.\n\nTerceiro parágrafo."
    parts = _split_by_separators(text, SEPARATORS_DEFAULT, chunk_size=30, overlap=0)
    combined = " ".join(parts)
    assert "Primeiro" in combined
    assert "Terceiro" in combined


def test_chunk_ids_are_unique(sample_legislacao_text):
    chunks = chunk_document(sample_legislacao_text, "doc1", DocumentType.LEGISLACAO)
    ids = [c.id for c in chunks]
    assert len(ids) == len(set(ids))
