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
        source={
            "title": "Roe v. Wade",
            "reporter": "410 U.S. 113",
            "pin_cite": 120,
            "court": "U.S. Supreme Court",
            "year": 1973,
            "url": "https://example.com/case",
        },
        number=2,
        accessed_at=datetime(2026, 2, 7),
    )
    assert "410 U.S. 113, 120" in text
    assert "(U.S. Supreme Court 1973)." in text
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


def test_format_reference_alwd_case_uses_at_pin():
    text = format_reference(
        style="alwd",
        title="People v. Doe",
        url="https://example.com/judgment",
        source={
            "title": "People v. Doe",
            "reporter": "500 F.3d 100",
            "pin_cite": 105,
            "court": "9th Cir.",
            "year": 2024,
            "url": "https://example.com/judgment",
        },
        number=3,
    )
    assert "500 F.3d 100 at 105" in text
    assert "(9th Cir. 2024)." in text


def test_format_reference_oscola_web():
    text = format_reference(
        style="oscola",
        title="Guide to Evidence",
        url="https://example.com/evidence",
        source={
            "title": "Guide to Evidence",
            "author": "Oxford Faculty",
            "publisher": "Oxford Press",
            "year": 2025,
            "url": "https://example.com/evidence",
        },
        accessed_at=datetime(2026, 2, 7),
    )
    assert "'Guide to Evidence'" in text
    assert "<https://example.com/evidence>" in text
    assert "accessed 7 February 2026." in text


def test_format_reference_apa_author_initials():
    text = format_reference(
        style="apa",
        title="Direito administrativo",
        url="https://example.com/admin",
        source={
            "title": "Direito administrativo",
            "authors": ["Maria Silva", "Joao Souza"],
            "year": 2024,
            "site_name": "Revista Juridica",
            "url": "https://example.com/admin",
        },
    )
    assert "Silva, M." in text
    assert "& Souza, J." in text
    assert "(2024)." in text


def test_format_reference_chicago_prefers_published_date():
    text = format_reference(
        style="chicago",
        title="CNJ Report",
        url="https://example.com/cnj",
        source={
            "title": "CNJ Report",
            "author": "CNJ",
            "site_name": "Portal CNJ",
            "date": "2025-11-10",
            "url": "https://example.com/cnj",
        },
        accessed_at=datetime(2026, 2, 7),
    )
    assert "November 10, 2025." in text
    assert "Accessed" not in text


def test_format_reference_harvard_available_at_clause():
    text = format_reference(
        style="harvard",
        title="Compliance Memo",
        url="https://example.com/memo",
        source={
            "author": "DataJud",
            "title": "Compliance Memo",
            "year": 2023,
            "site_name": "Portal",
            "url": "https://example.com/memo",
        },
        accessed_at=datetime(2026, 2, 7),
    )
    assert "DataJud (2023) 'Compliance Memo'" in text
    assert "Available at: https://example.com/memo" in text


def test_format_reference_vancouver_internet_pattern():
    text = format_reference(
        style="vancouver",
        title="Medical-Legal Study",
        url="https://example.com/study",
        source={
            "authors": ["Ana Pereira", "Bruno Lima"],
            "title": "Medical-Legal Study",
            "publisher": "Forensic Journal",
            "year": 2022,
            "volume": 12,
            "issue": 3,
            "pages": "15-20",
            "url": "https://example.com/study",
        },
        accessed_at=datetime(2026, 2, 7),
    )
    assert "Pereira A, Lima B." in text
    assert "[Internet]." in text
    assert "[cited 2026 Feb 07]." in text


def test_format_reference_ecli_uses_identifier():
    text = format_reference(
        style="ecli",
        title="Decision",
        url="https://example.com/ecli",
        source={
            "ecli": "ECLI:EU:C:2024:123",
            "title": "Decision",
            "court": "CJEU",
            "year": 2024,
            "url": "https://example.com/ecli",
        },
    )
    assert "ECLI:EU:C:2024:123" in text
    assert "<https://example.com/ecli>" in text


def test_format_reference_numeric_and_inline_include_page():
    numeric = format_reference(
        style="numeric",
        title="Fonte A",
        url="https://example.com/a",
        source={"title": "Fonte A", "url": "https://example.com/a", "source_page": 13, "tribunal": "STJ"},
        number=1,
    )
    inline = format_reference(
        style="inline",
        title="Fonte A",
        url="https://example.com/a",
        source={"title": "Fonte A", "url": "https://example.com/a", "source_page": 13},
        number=1,
    )
    assert "p. 13" in numeric
    assert "(https://example.com/a)" in inline
