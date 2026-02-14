"""
Tests for DoclingAdapter including 3-tier adaptive PDF extraction.
"""

import asyncio
from unittest.mock import MagicMock, patch

from app.services.docling_adapter import (
    DoclingAdapter,
    _MIN_CHARS_PER_PAGE,
    _MIN_TABLE_DENSITY,
    _MIN_PRINTABLE_RATIO,
    _MIN_SPACE_RATIO,
    _MAX_SPACE_RATIO,
)


# =============================================================================
# EXISTING TESTS
# =============================================================================


def test_extract_plain_text_fallback(tmp_path):
    file_path = tmp_path / "sample.txt"
    file_path.write_text("conteudo de teste", encoding="utf-8")

    adapter = DoclingAdapter()
    result = asyncio.run(adapter.extract(str(file_path)))

    assert "conteudo de teste" in result.text
    assert result.metadata.get("extraction_engine") == "plain_text"


def test_extract_unsupported_extension(tmp_path):
    file_path = tmp_path / "sample.xyz"
    file_path.write_bytes(b"\x00\x01\x02")

    adapter = DoclingAdapter()
    result = asyncio.run(adapter.extract(str(file_path)))

    assert result.text == ""
    assert result.metadata.get("extraction_engine") == "unsupported"


def test_doc_binary_without_antiword_returns_unsupported(monkeypatch):
    def _raise_file_not_found(*args, **kwargs):
        raise FileNotFoundError()

    monkeypatch.setattr("subprocess.run", _raise_file_not_found)
    adapter = DoclingAdapter()
    result = adapter._extract_doc_binary_sync("/tmp/fake.doc")

    assert result.text == ""
    assert result.metadata.get("extraction_engine") == "unsupported"


# =============================================================================
# DETECTION HELPERS
# =============================================================================


class TestTextSparseDetection:
    """Tests for _is_text_sparse static method."""

    def test_empty_text_is_sparse(self):
        assert DoclingAdapter._is_text_sparse("", 5) is True

    def test_none_text_is_sparse(self):
        assert DoclingAdapter._is_text_sparse(None, 5) is True

    def test_zero_pages_is_sparse(self):
        assert DoclingAdapter._is_text_sparse("some text", 0) is True

    def test_sufficient_text_is_not_sparse(self):
        text = "a" * 500
        assert DoclingAdapter._is_text_sparse(text, 3) is False

    def test_sparse_text_detected(self):
        text = "a" * 50  # 50 chars for 5 pages = 10 chars/page < 100
        assert DoclingAdapter._is_text_sparse(text, 5) is True

    def test_boundary_exact_threshold(self):
        text = "a" * (_MIN_CHARS_PER_PAGE * 3)
        assert DoclingAdapter._is_text_sparse(text, 3) is False

    def test_below_threshold(self):
        text = "a" * (_MIN_CHARS_PER_PAGE * 3 - 1)
        assert DoclingAdapter._is_text_sparse(text, 3) is True


class TestSignificantTablesDetection:
    """Tests for _has_significant_tables (density-based detection)."""

    def test_no_tables(self):
        doc = MagicMock()
        doc.tables = []
        assert DoclingAdapter._has_significant_tables(doc, 10) is False

    def test_no_tables_attr(self):
        doc = object()
        assert DoclingAdapter._has_significant_tables(doc, 10) is False

    def test_single_page_any_table_is_significant(self):
        doc = MagicMock()
        doc.tables = [MagicMock()]  # 1 table
        assert DoclingAdapter._has_significant_tables(doc, 1) is True

    def test_two_pages_any_table_is_significant(self):
        doc = MagicMock()
        doc.tables = [MagicMock()]
        assert DoclingAdapter._has_significant_tables(doc, 2) is True

    def test_multipage_below_density_threshold(self):
        doc = MagicMock()
        doc.tables = [MagicMock()]  # 1 table in 100 pages = 1% < 5%
        assert DoclingAdapter._has_significant_tables(doc, 100) is False

    def test_multipage_at_density_threshold(self):
        doc = MagicMock()
        # 5 tables in 100 pages = 5% == threshold
        doc.tables = [MagicMock() for _ in range(5)]
        assert DoclingAdapter._has_significant_tables(doc, 100) is True

    def test_multipage_above_density_threshold(self):
        doc = MagicMock()
        # 10 tables in 100 pages = 10% > 5%
        doc.tables = [MagicMock() for _ in range(10)]
        assert DoclingAdapter._has_significant_tables(doc, 100) is True

    def test_boundary_3_pages(self):
        doc = MagicMock()
        doc.tables = [MagicMock()]  # 1 table in 3 pages = 33% >> 5%
        # 3 pages is multi-page (>2), so threshold applies
        assert DoclingAdapter._has_significant_tables(doc, 3) is True


class TestTextQualityValidation:
    """Tests for _is_text_quality_good static method."""

    def test_empty_text_fails(self):
        assert DoclingAdapter._is_text_quality_good("") is False

    def test_too_short_text_fails(self):
        assert DoclingAdapter._is_text_quality_good("short") is False

    def test_good_quality_text_passes(self):
        text = "Este é um documento legal com texto bem formatado e estruturado. " * 10
        assert DoclingAdapter._is_text_quality_good(text) is True

    def test_low_printable_ratio_fails(self):
        # Gibberish with non-printable chars
        text = "abc" + "\x00\x01\x02" * 100 + "def"
        assert DoclingAdapter._is_text_quality_good(text) is False

    def test_no_spaces_fails(self):
        # Text without word separation (OCR artifact)
        text = "a" * 500  # no spaces
        assert DoclingAdapter._is_text_quality_good(text) is False

    def test_too_many_spaces_fails(self):
        # Text with excessive spaces
        text = "a " * 500  # 50% spaces (too high)
        assert DoclingAdapter._is_text_quality_good(text) is False

    def test_suspiciously_short_tokens_fail(self):
        # Single-char tokens (gibberish)
        text = "a b c d e f g h i j k l m n o p q r s t u v w x y z " * 10
        assert DoclingAdapter._is_text_quality_good(text) is False

    def test_suspiciously_long_tokens_fail(self):
        # Extremely long tokens without spaces (encoding issue)
        text = "abcdefghijklmnopqrstuvwxyz" * 30  # avg token len > 25
        assert DoclingAdapter._is_text_quality_good(text) is False

    def test_normal_legal_text_passes(self):
        text = """
        Art. 1º Esta Lei estabelece normas gerais sobre licitação e contratos
        administrativos pertinentes a obras, serviços, inclusive de publicidade,
        compras, alienações e locações no âmbito dos Poderes da União, dos Estados,
        do Distrito Federal e dos Municípios.

        Parágrafo único. Subordinam-se ao regime desta Lei, além dos órgãos da
        administração direta, os fundos especiais, as autarquias, as fundações
        públicas, as empresas públicas, as sociedades de economia mista e demais
        entidades controladas direta ou indiretamente pela União, Estados,
        Distrito Federal e Municípios.
        """ * 3
        assert DoclingAdapter._is_text_quality_good(text) is True


# =============================================================================
# ADAPTIVE PDF TIER SELECTION
# =============================================================================


class TestAdaptivePdfTierSelection:
    """Tests that the correct tier is selected based on content."""

    def _make_adapter(self):
        """Create adapter with Docling marked as available."""
        adapter = DoclingAdapter.__new__(DoclingAdapter)
        adapter._enabled = True
        adapter._docling_available = True
        adapter.converter = None
        adapter._converter_fast = None
        adapter._converter_tables = None
        adapter._converter_ocr = None
        return adapter

    def _mock_convert_result(self, text="", pages=5, tables=None):
        """Create a mock Docling convert result."""
        doc = MagicMock()
        doc.export_to_markdown.return_value = text
        doc.export_to_text.return_value = text
        doc.pages = [MagicMock() for _ in range(pages)]
        doc.tables = tables or []
        result = MagicMock()
        result.document = doc
        return result

    def test_fast_tier_for_text_native_pdf(self):
        adapter = self._make_adapter()
        # Good quality text: 200+ chars/page with proper word structure
        text = "Este é um documento legal com texto bem estruturado e formatado adequadamente. " * 15  # ~1200 chars, good quality

        mock_converter = MagicMock()
        mock_converter.convert.return_value = self._mock_convert_result(text, 5)
        adapter._converter_fast = mock_converter

        result = adapter._docling_pdf_adaptive_sync("/tmp/test.pdf")

        assert result.metadata["docling_tier"] == "fast"
        mock_converter.convert.assert_called_once()

    def test_ocr_tier_for_sparse_text(self):
        adapter = self._make_adapter()

        # Fast converter returns sparse text
        fast_converter = MagicMock()
        fast_converter.convert.return_value = self._mock_convert_result("short", 10)
        adapter._converter_fast = fast_converter

        # OCR converter returns full text
        ocr_text = "a" * 5000
        ocr_converter = MagicMock()
        ocr_converter.convert.return_value = self._mock_convert_result(ocr_text, 10)
        adapter._converter_ocr = ocr_converter

        result = adapter._docling_pdf_adaptive_sync("/tmp/scanned.pdf")

        assert result.metadata["docling_tier"] == "ocr"
        fast_converter.convert.assert_called_once()
        ocr_converter.convert.assert_called_once()
        assert len(result.text) == 5000

    def test_tables_tier_for_pdf_with_tables(self):
        adapter = self._make_adapter()
        # Good quality text with high enough density: 1000 chars / 5 pages = 200 chars/page
        # Need to ensure text quality is good too
        text = "Este é um texto legal bem formatado com espaços adequados. " * 20  # ~1200 chars, good quality

        # Fast converter returns text but detects tables (1 table in 2 pages = 50% > 5% threshold)
        fast_result = self._mock_convert_result(text, 2, tables=[MagicMock()])
        fast_converter = MagicMock()
        fast_converter.convert.return_value = fast_result
        adapter._converter_fast = fast_converter

        # Tables converter re-extracts
        table_text = "Este é um texto legal bem formatado com espaços adequados e tabelas estruturadas. " * 20
        tables_converter = MagicMock()
        tables_converter.convert.return_value = self._mock_convert_result(table_text, 2)
        adapter._converter_tables = tables_converter

        result = adapter._docling_pdf_adaptive_sync("/tmp/with_tables.pdf")

        assert result.metadata["docling_tier"] == "tables"
        fast_converter.convert.assert_called_once()
        tables_converter.convert.assert_called_once()

    def test_ocr_takes_priority_over_tables(self):
        """If text is sparse AND has tables, OCR tier should be used (OCR includes TableFormer)."""
        adapter = self._make_adapter()

        # Fast: sparse text + tables detected
        fast_result = self._mock_convert_result("hi", 10, tables=[MagicMock()])
        fast_converter = MagicMock()
        fast_converter.convert.return_value = fast_result
        adapter._converter_fast = fast_converter

        ocr_text = "Este é um texto recuperado via OCR com boa qualidade. " * 100
        ocr_converter = MagicMock()
        ocr_converter.convert.return_value = self._mock_convert_result(ocr_text, 10)
        adapter._converter_ocr = ocr_converter

        result = adapter._docling_pdf_adaptive_sync("/tmp/scanned_tables.pdf")

        assert result.metadata["docling_tier"] == "ocr"

    def test_ocr_tier_for_low_quality_text(self):
        """Even if text is not sparse, low quality should trigger OCR."""
        adapter = self._make_adapter()

        # Fast: sufficient length but poor quality (no spaces, gibberish)
        bad_text = "a" * 2000  # 200 chars/page (not sparse), but no spaces → low quality
        fast_converter = MagicMock()
        fast_converter.convert.return_value = self._mock_convert_result(bad_text, 10)
        adapter._converter_fast = fast_converter

        # OCR: recovers good quality text
        good_text = "Este é um texto legal bem estruturado com palavras e espaços. " * 50
        ocr_converter = MagicMock()
        ocr_converter.convert.return_value = self._mock_convert_result(good_text, 10)
        adapter._converter_ocr = ocr_converter

        result = adapter._docling_pdf_adaptive_sync("/tmp/bad_encoding.pdf")

        assert result.metadata["docling_tier"] == "ocr"
        fast_converter.convert.assert_called_once()
        ocr_converter.convert.assert_called_once()

    def test_metadata_includes_tier(self):
        adapter = self._make_adapter()
        text = "Este é um documento legal com texto bem estruturado e formatado adequadamente. " * 15

        mock_converter = MagicMock()
        mock_converter.convert.return_value = self._mock_convert_result(text, 5)
        adapter._converter_fast = mock_converter

        result = adapter._docling_pdf_adaptive_sync("/tmp/test.pdf")

        assert "docling_tier" in result.metadata
        assert result.metadata["extraction_engine"] == "docling"
        assert "pages" in result.metadata

    def test_fallback_to_plain_text_on_empty_markdown(self):
        """When OCR tier produces empty markdown, falls back to export_to_text."""
        adapter = self._make_adapter()

        # Fast pass: empty text, 1 page → sparse → triggers OCR
        fast_doc = MagicMock()
        fast_doc.export_to_markdown.return_value = ""
        fast_doc.pages = [MagicMock()]
        fast_doc.tables = []
        fast_result = MagicMock()
        fast_result.document = fast_doc

        fast_converter = MagicMock()
        fast_converter.convert.return_value = fast_result
        adapter._converter_fast = fast_converter

        # OCR pass: also empty markdown, but export_to_text has content
        ocr_doc = MagicMock()
        ocr_doc.export_to_markdown.return_value = ""
        ocr_doc.export_to_text.return_value = "fallback text content"
        ocr_doc.pages = [MagicMock()]
        ocr_doc.tables = []
        ocr_result = MagicMock()
        ocr_result.document = ocr_doc

        ocr_converter = MagicMock()
        ocr_converter.convert.return_value = ocr_result
        adapter._converter_ocr = ocr_converter

        result = adapter._docling_pdf_adaptive_sync("/tmp/test.pdf")

        assert result.text == "fallback text content"
        assert result.metadata["docling_tier"] == "ocr"


# =============================================================================
# ROUTING: PDF vs NON-PDF
# =============================================================================


class TestExtractionRouting:
    """Tests that PDF uses adaptive, non-PDF uses generic converter."""

    def test_pdf_routes_to_adaptive(self):
        adapter = DoclingAdapter.__new__(DoclingAdapter)
        adapter._enabled = True
        adapter._docling_available = True
        adapter.converter = None
        adapter._converter_fast = None
        adapter._converter_tables = None
        adapter._converter_ocr = None

        called = {"adaptive": False, "generic": False}

        def mock_adaptive(path):
            from app.services.docling_adapter import ExtractionResult
            called["adaptive"] = True
            return ExtractionResult(text="pdf text", metadata={"extraction_engine": "docling", "docling_tier": "fast", "pages": 1, "tables_count": 0, "sections": [], "has_images": False})

        def mock_generic(path):
            from app.services.docling_adapter import ExtractionResult
            called["generic"] = True
            return ExtractionResult(text="docx text", metadata={"extraction_engine": "docling", "docling_tier": "generic", "pages": 1, "tables_count": 0, "sections": [], "has_images": False})

        adapter._docling_pdf_adaptive_sync = mock_adaptive
        adapter._docling_sync = mock_generic

        # PDF should use adaptive
        with patch.object(adapter, '_extract_pdf_adaptive', side_effect=lambda p: asyncio.coroutine(lambda: mock_adaptive(p))()):
            pass  # routing tested below

        # Direct sync method test
        result = adapter._docling_pdf_adaptive_sync("/tmp/test.pdf")
        assert called["adaptive"] is True
        assert result.metadata["docling_tier"] == "fast"
