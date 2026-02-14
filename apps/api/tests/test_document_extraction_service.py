from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import app.services.document_extraction_service as extraction_service


class _FakeAdapter:
    def __init__(self, text: str = "", metadata: dict | None = None, exc: Exception | None = None):
        self._text = text
        self._metadata = metadata or {}
        self._exc = exc

    async def extract(self, _file_path: str):
        if self._exc is not None:
            raise self._exc
        return SimpleNamespace(text=self._text, metadata=self._metadata)


def _enable_ocr(monkeypatch: pytest.MonkeyPatch, *, enabled: bool = True, docling_ocr_enabled: bool = True) -> None:
    monkeypatch.setattr(extraction_service.settings, "ENABLE_OCR", enabled, raising=False)
    monkeypatch.setattr(extraction_service.settings, "DOCLING_OCR_ENABLED", docling_ocr_enabled, raising=False)


def test_should_run_pdf_ocr_respects_explicit_false(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_ocr(monkeypatch, enabled=True, docling_ocr_enabled=True)
    assert extraction_service.should_run_pdf_ocr("texto longo suficiente", ocr_requested=False) is False


def test_should_run_pdf_ocr_respects_explicit_true_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_ocr(monkeypatch, enabled=True, docling_ocr_enabled=True)
    assert extraction_service.should_run_pdf_ocr("texto longo suficiente", ocr_requested=True) is True


def test_should_run_pdf_ocr_returns_false_when_globally_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_ocr(monkeypatch, enabled=False, docling_ocr_enabled=True)
    assert extraction_service.should_run_pdf_ocr("x", ocr_requested=True) is False


def test_should_run_pdf_ocr_uses_threshold_when_not_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_ocr(monkeypatch, enabled=True, docling_ocr_enabled=True)
    assert extraction_service.should_run_pdf_ocr("abc", min_pdf_chars=10) is True
    assert extraction_service.should_run_pdf_ocr("texto grande o suficiente", min_pdf_chars=10) is False


@pytest.mark.asyncio
async def test_extract_text_from_path_non_pdf_uses_adapter_only(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_adapter = _FakeAdapter(text="conteudo docx", metadata={"extraction_engine": "docling"})
    ocr_mock = AsyncMock(return_value="ocr texto")

    monkeypatch.setattr(extraction_service, "get_docling_adapter", lambda: fake_adapter)
    monkeypatch.setattr(extraction_service, "extract_text_from_pdf_with_ocr", ocr_mock)

    result = await extraction_service.extract_text_from_path("/tmp/arquivo.docx")

    assert result.text == "conteudo docx"
    assert result.metadata.get("unified_route") == "adapter_only"
    ocr_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_extract_text_from_path_pdf_skips_ocr_when_docling_text_is_good(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_ocr(monkeypatch, enabled=True, docling_ocr_enabled=True)
    fake_adapter = _FakeAdapter(text="x" * 80, metadata={"extraction_engine": "docling"})
    ocr_mock = AsyncMock(return_value="ocr texto")

    monkeypatch.setattr(extraction_service, "get_docling_adapter", lambda: fake_adapter)
    monkeypatch.setattr(extraction_service, "extract_text_from_pdf_with_ocr", ocr_mock)

    result = await extraction_service.extract_text_from_path("/tmp/arquivo.pdf", min_pdf_chars=50)

    assert result.text == "x" * 80
    assert result.metadata.get("unified_route") == "pdf_adapter"
    assert result.metadata.get("unified_ocr_attempted") is False
    ocr_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_extract_text_from_path_pdf_uses_ocr_when_better(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_ocr(monkeypatch, enabled=True, docling_ocr_enabled=True)
    fake_adapter = _FakeAdapter(text="curto", metadata={"extraction_engine": "docling"})
    ocr_mock = AsyncMock(return_value="texto OCR bem maior que o docling")

    monkeypatch.setattr(extraction_service, "get_docling_adapter", lambda: fake_adapter)
    monkeypatch.setattr(extraction_service, "extract_text_from_pdf_with_ocr", ocr_mock)

    result = await extraction_service.extract_text_from_path("/tmp/arquivo.pdf", min_pdf_chars=50)

    assert result.text == "texto OCR bem maior que o docling"
    assert result.metadata.get("unified_route") == "pdf_adapter_plus_ocr"
    assert result.metadata.get("unified_ocr_attempted") is True
    assert result.metadata.get("unified_ocr_selected") is True
    assert result.metadata.get("extraction_engine") == "ocr_hybrid"
    ocr_mock.assert_awaited_once_with("/tmp/arquivo.pdf", force_ocr=False)


@pytest.mark.asyncio
async def test_extract_text_from_path_pdf_keeps_docling_when_ocr_worse(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_ocr(monkeypatch, enabled=True, docling_ocr_enabled=True)
    fake_adapter = _FakeAdapter(text="texto do docling mais completo", metadata={"extraction_engine": "docling"})
    ocr_mock = AsyncMock(return_value="ocr")

    monkeypatch.setattr(extraction_service, "get_docling_adapter", lambda: fake_adapter)
    monkeypatch.setattr(extraction_service, "extract_text_from_pdf_with_ocr", ocr_mock)

    result = await extraction_service.extract_text_from_path("/tmp/arquivo.pdf", min_pdf_chars=50, force_pdf_ocr=True)

    assert result.text == "texto do docling mais completo"
    assert result.metadata.get("unified_route") == "pdf_adapter_plus_ocr"
    assert result.metadata.get("unified_ocr_attempted") is True
    assert result.metadata.get("unified_ocr_selected") is False
    ocr_mock.assert_awaited_once_with("/tmp/arquivo.pdf", force_ocr=True)


@pytest.mark.asyncio
async def test_extract_text_from_path_pdf_adapter_error_falls_back_to_ocr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_ocr(monkeypatch, enabled=True, docling_ocr_enabled=True)
    fake_adapter = _FakeAdapter(exc=RuntimeError("adapter down"))
    ocr_mock = AsyncMock(return_value="texto vindo apenas do OCR")

    monkeypatch.setattr(extraction_service, "get_docling_adapter", lambda: fake_adapter)
    monkeypatch.setattr(extraction_service, "extract_text_from_pdf_with_ocr", ocr_mock)

    result = await extraction_service.extract_text_from_path("/tmp/arquivo.pdf", min_pdf_chars=50)

    assert result.text == "texto vindo apenas do OCR"
    assert result.metadata.get("unified_route") == "pdf_adapter_plus_ocr"
    assert result.metadata.get("unified_ocr_selected") is True
    assert result.metadata.get("adapter_error") == "adapter down"
