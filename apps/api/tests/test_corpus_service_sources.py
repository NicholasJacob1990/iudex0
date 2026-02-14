from types import SimpleNamespace

from app.services.corpus_service import CorpusService


def _service() -> CorpusService:
    return CorpusService(db=None)  # type: ignore[arg-type]


def test_extract_source_page_reads_common_keys() -> None:
    service = _service()

    assert service._extract_source_page({"page": 4}) == 4
    assert service._extract_source_page({"page_number": "7"}) == 7
    assert service._extract_source_page({"pagina": "9"}) == 9
    assert service._extract_source_page({"page": "abc"}) is None


def test_build_source_url_prefers_document_endpoint() -> None:
    service = _service()

    url = service._build_source_url("doc-123", {"source_url": "https://example.com/file.pdf"})
    assert url == "/api/corpus/documents/doc-123/content"


def test_extract_highlight_text_prefers_highlight_list() -> None:
    service = _service()

    highlight = service._extract_highlight_text(
        {"highlights": ["trecho importante", "outro"]},
        "fallback",
    )
    assert highlight == "trecho importante"


def test_resolve_local_path_from_document_uses_metadata(tmp_path) -> None:
    service = _service()
    file_path = tmp_path / "sample.pdf"
    file_path.write_text("dummy", encoding="utf-8")

    doc = SimpleNamespace(url="", doc_metadata={"local_path": str(file_path)})
    resolved = service._resolve_local_path_from_document(doc)

    assert resolved == str(file_path)
