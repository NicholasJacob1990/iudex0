from datetime import datetime

from app.services.ai.citations.base import (
    append_references_section,
    build_references_section,
    format_reference,
)
from app.services.ai.citations.style_registry import normalize_citation_style


def test_normalize_citation_style_aliases():
    assert normalize_citation_style("forense") == "forense_br"
    assert normalize_citation_style("hibrido") == "abnt"
    assert normalize_citation_style("bluebook") == "bluebook"


def test_format_reference_bluebook_uses_style_dispatch():
    text = format_reference(
        style="bluebook",
        title="Roe v. Wade",
        url="https://example.com/case",
        source={"title": "Roe v. Wade", "url": "https://example.com/case"},
        number=2,
        accessed_at=datetime(2026, 2, 7),
    )
    assert "last visited" in text
    assert "[2]" in text


def test_append_references_section_respects_numeric_style():
    body = "Conclusao com suporte [1]."
    citations = [{"number": 1, "title": "Fonte A", "url": "https://example.com/a"}]

    output = append_references_section(body, citations, style="numeric")

    assert "REFERÊNCIAS NUMERADAS" in output
    assert "[1] Fonte A." in output


def test_build_references_section_uses_style_heading():
    section = build_references_section(
        [{"number": 1, "title": "Source", "url": "https://example.com"}],
        style="oscola",
    )
    assert "TABLE OF AUTHORITIES (OSCOLA)" in section
