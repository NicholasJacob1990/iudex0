"""
Testes para o serviço de OCR híbrido
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import date

from app.services.ocr_service import (
    OCRProvider,
    OCRResult,
    OCRUsageTracker,
    HybridOCRService,
    get_ocr_service,
)


class TestOCRProvider:
    """Testes para o enum OCRProvider"""

    def test_provider_values(self):
        """Verifica valores dos providers"""
        assert OCRProvider.PYMUPDF.value == "pymupdf"
        assert OCRProvider.TESSERACT.value == "tesseract"
        assert OCRProvider.AZURE.value == "azure"
        assert OCRProvider.GOOGLE.value == "google"
        assert OCRProvider.GEMINI.value == "gemini"

    def test_provider_from_string(self):
        """Cria provider a partir de string"""
        assert OCRProvider("tesseract") == OCRProvider.TESSERACT
        assert OCRProvider("azure") == OCRProvider.AZURE


class TestOCRResult:
    """Testes para OCRResult"""

    def test_result_creation(self):
        """Cria resultado básico"""
        result = OCRResult(
            text="Texto extraído",
            provider=OCRProvider.TESSERACT,
            pages_processed=5,
        )
        assert result.text == "Texto extraído"
        assert result.provider == OCRProvider.TESSERACT
        assert result.pages_processed == 5
        assert result.error is None
        assert result.confidence is None

    def test_result_with_error(self):
        """Cria resultado com erro"""
        result = OCRResult(
            text="",
            provider=OCRProvider.AZURE,
            pages_processed=0,
            error="API indisponível",
        )
        assert result.error == "API indisponível"


class TestOCRUsageTracker:
    """Testes para rastreamento de uso"""

    def test_increment_count(self):
        """Incrementa contador"""
        tracker = OCRUsageTracker()
        tracker.increment(10)
        assert tracker.get_daily_count() == 10

        tracker.increment(5)
        assert tracker.get_daily_count() == 15

    def test_should_use_cloud_below_threshold(self):
        """Não usar cloud abaixo do threshold"""
        tracker = OCRUsageTracker()
        tracker.increment(100)
        # Threshold padrão é 1000
        assert tracker.should_use_cloud() is False

    @patch("app.services.ocr_service.settings")
    def test_should_use_cloud_above_threshold(self, mock_settings):
        """Usar cloud acima do threshold"""
        mock_settings.OCR_CLOUD_THRESHOLD_DAILY = 500
        tracker = OCRUsageTracker()
        tracker.increment(600)
        assert tracker.should_use_cloud() is True


class TestHybridOCRService:
    """Testes para o serviço OCR híbrido"""

    @pytest.fixture
    def service(self):
        """Cria instância do serviço para testes"""
        # Reset tracker para isolamento de testes
        import app.services.ocr_service as module
        module._usage_tracker = OCRUsageTracker()

        with patch("app.services.ocr_service.settings") as mock_settings:
            mock_settings.OCR_PROVIDER = "tesseract"
            mock_settings.OCR_CLOUD_THRESHOLD_DAILY = 1000
            mock_settings.OCR_DPI = 300
            mock_settings.TESSERACT_LANG = "por"
            mock_settings.AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT = None
            mock_settings.AZURE_DOCUMENT_INTELLIGENCE_KEY = None
            mock_settings.GEMINI_OCR_ENABLED = False
            mock_settings.GOOGLE_VISION_ENABLED = False
            mock_settings.GOOGLE_API_KEY = None
            svc = HybridOCRService()
            # Use fresh tracker instance
            svc.tracker = module._usage_tracker
            return svc

    def test_service_initialization(self, service):
        """Inicialização do serviço"""
        assert service.default_provider == OCRProvider.TESSERACT
        assert service.tracker is not None

    def test_select_provider_default(self, service):
        """Seleciona provider padrão"""
        provider = service._select_provider()
        assert provider == OCRProvider.TESSERACT

    @patch("app.services.ocr_service.settings")
    def test_select_provider_cloud_when_high_volume(self, mock_settings):
        """Seleciona cloud quando volume alto"""
        mock_settings.OCR_PROVIDER = "tesseract"
        mock_settings.OCR_CLOUD_THRESHOLD_DAILY = 100
        mock_settings.AZURE_DOCUMENT_INTELLIGENCE_KEY = "fake-key"
        mock_settings.AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT = "https://fake.azure.com"
        mock_settings.GEMINI_OCR_ENABLED = False
        mock_settings.GOOGLE_VISION_ENABLED = False

        service = HybridOCRService()
        service.tracker.increment(150)  # Acima do threshold

        provider = service._select_provider()
        assert provider == OCRProvider.AZURE

    @pytest.mark.asyncio
    async def test_try_pymupdf_text_with_text(self, service):
        """PyMuPDF extrai texto selecionável"""
        mock_page = MagicMock()
        mock_page.get_text.return_value = "Texto do PDF " * 50

        with patch("fitz.open") as mock_open:
            mock_open.return_value.__enter__.return_value = [mock_page]
            result = await service._try_pymupdf_text("/fake/path.pdf")

        assert result is not None
        assert "Texto do PDF" in result

    @pytest.mark.asyncio
    async def test_try_pymupdf_text_no_text(self, service):
        """PyMuPDF retorna vazio quando sem texto"""
        mock_page = MagicMock()
        mock_page.get_text.return_value = ""

        with patch("fitz.open") as mock_open:
            mock_open.return_value.__enter__.return_value = [mock_page]
            result = await service._try_pymupdf_text("/fake/path.pdf")

        # Texto vazio não é considerado válido
        assert result == ""

    def test_count_pdf_pages(self, service):
        """Conta páginas do PDF"""
        mock_pages = [MagicMock(), MagicMock(), MagicMock()]

        with patch("fitz.open") as mock_open:
            mock_open.return_value.__enter__.return_value = mock_pages
            count = service._count_pdf_pages("/fake/path.pdf")

        assert count == 3

    def test_get_usage_stats(self, service):
        """Retorna estatísticas de uso"""
        service.tracker.increment(50)
        stats = service.get_usage_stats()

        assert stats["daily_pages"] == 50
        assert stats["threshold"] == 1000
        assert stats["should_use_cloud"] is False
        assert stats["default_provider"] == "tesseract"

    @pytest.mark.asyncio
    async def test_extract_text_from_pdf_uses_pymupdf_first(self, service):
        """Tenta PyMuPDF antes de OCR"""
        with patch.object(
            service, "_try_pymupdf_text", return_value="Texto selecionável " * 50
        ) as mock_native:
            with patch.object(service, "_count_pdf_pages", return_value=1):
                result = await service.extract_text_from_pdf("/fake/path.pdf")

        mock_native.assert_called_once()
        assert result.provider == OCRProvider.PYMUPDF
        assert "Texto selecionável" in result.text

    @pytest.mark.asyncio
    async def test_extract_text_from_pdf_force_ocr(self, service):
        """Force OCR ignora extração nativa"""
        with patch.object(service, "_try_pymupdf_text") as mock_native:
            with patch.object(
                service,
                "_execute_ocr",
                return_value=OCRResult(
                    text="Texto OCR",
                    provider=OCRProvider.TESSERACT,
                    pages_processed=1,
                ),
            ):
                result = await service.extract_text_from_pdf(
                    "/fake/path.pdf", force_ocr=True
                )

        mock_native.assert_not_called()
        assert result.provider == OCRProvider.TESSERACT


class TestGetOCRService:
    """Testes para singleton do serviço"""

    def test_singleton(self):
        """Retorna mesma instância"""
        # Reset singleton
        import app.services.ocr_service as module

        module._ocr_service = None

        with patch("app.services.ocr_service.settings") as mock_settings:
            mock_settings.OCR_PROVIDER = "tesseract"
            mock_settings.OCR_CLOUD_THRESHOLD_DAILY = 1000

            service1 = get_ocr_service()
            service2 = get_ocr_service()

            assert service1 is service2
