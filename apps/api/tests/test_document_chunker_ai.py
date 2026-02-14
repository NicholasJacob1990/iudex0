from app.services.ai.document_chunker import (
    estimate_pages,
    classify_document_route,
    split_text_for_multi_pass,
    merge_chunk_summaries,
)


def test_estimate_pages_uses_char_heuristic():
    text = "a" * 8100
    assert estimate_pages(text, chars_per_page=4000) == 3


def test_classify_document_route_thresholds():
    assert classify_document_route(80) == "direct"
    assert classify_document_route(320) == "rag_enhanced"
    assert classify_document_route(900) == "chunked_rag"
    assert classify_document_route(2500) == "multi_pass"


def test_split_text_for_multi_pass_creates_multiple_chunks():
    text = ("Paragrafo de teste. " * 2500).strip()
    chunks = split_text_for_multi_pass(
        text,
        max_chunk_chars=12000,
        overlap_chars=300,
        max_chunks=10,
    )

    assert len(chunks) >= 2
    assert chunks[0].start_char == 0
    assert chunks[-1].end_char <= len(text)
    assert all(c.text for c in chunks)


def test_merge_chunk_summaries_enforces_size_limit():
    summaries = ["Resumo A " * 4000, "Resumo B " * 4000]
    merged = merge_chunk_summaries(summaries, max_chars=5000)
    assert len(merged) <= 5000
    assert "[Chunk 1]" in merged
