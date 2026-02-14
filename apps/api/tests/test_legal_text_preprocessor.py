import pytest


def test_clean_legal_text_removes_toc_and_page_numbers():
    from app.services.rag.core.kg_builder.legal_text_preprocessor import clean_legal_text

    raw = (
        "SUMARIO.................................... 1\n"
        "1\n"
        "Curso Intensivo: Direito\n"
        "Art. 135 do CTN nos termos do art. 10.\n"
        "2\n"
    )
    cleaned = clean_legal_text(raw)
    assert "SUMARIO" not in cleaned.upper()
    assert "Curso Intensivo" not in cleaned
    # keep substantive line
    assert "Art. 135" in cleaned


def test_is_quality_segment_filters_short_and_low_alnum():
    from app.services.rag.core.kg_builder.legal_text_preprocessor import is_quality_segment

    assert is_quality_segment("x" * 50) is False
    assert is_quality_segment("----\n----\n----\n" * 30) is False
    assert is_quality_segment("Art. 135 do CTN nos termos do art. 10 do CTN." * 10) is True


def test_prepare_segments_quality_filter_counts_skipped():
    from app.services.rag.core.kg_builder.legal_text_preprocessor import prepare_segments

    raw = (
        "SUMARIO.................................... 1\n\n"
        + ("Art. 135 do CTN nos termos do art. 10 do CTN.\n" * 15) + "\n"
        "2\n"
    )
    # segment_size should be >= min_chars for quality filter to keep segments
    segments, skipped = prepare_segments(raw, segment_size=1200, overlap=0, quality_filter=True)
    assert len(segments) >= 1
    assert skipped >= 0
    assert any("Art. 135" in s for s in segments)
