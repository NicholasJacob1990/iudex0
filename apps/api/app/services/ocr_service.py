"""
Serviço de OCR Híbrido

Estratégia:
1. PDFs com texto selecionável → PyMuPDF (fitz) (rápido)
2. Volume baixo (<threshold) → Tesseract local (gratuito)
3. Volume alto ou fallback → Cloud OCR (Azure/Google/Gemini)
"""

from typing import Optional, Literal
from dataclasses import dataclass
from enum import Enum
import os
from datetime import date

from loguru import logger
from PIL import Image

from app.core.config import settings


class OCRProvider(str, Enum):
    """Provedores de OCR disponíveis"""
    PYMUPDF = "pymupdf"        # Texto selecionável (não é OCR)
    TESSERACT = "tesseract"    # Local, gratuito
    AZURE = "azure"            # Azure Document Intelligence
    GOOGLE = "google"          # Google Cloud Vision
    GEMINI = "gemini"          # Gemini Vision (mais barato)


@dataclass
class OCRResult:
    """Resultado do OCR"""
    text: str
    provider: OCRProvider
    pages_processed: int
    confidence: Optional[float] = None
    error: Optional[str] = None


class OCRUsageTracker:
    """
    Rastreia uso diário de OCR para decisão de fallback
    Em produção, usar Redis para persistência entre workers
    """

    def __init__(self):
        self._daily_count: dict[str, int] = {}

    def _today_key(self) -> str:
        return date.today().isoformat()

    def increment(self, pages: int = 1) -> int:
        key = self._today_key()
        self._daily_count[key] = self._daily_count.get(key, 0) + pages
        return self._daily_count[key]

    def get_daily_count(self) -> int:
        return self._daily_count.get(self._today_key(), 0)

    def should_use_cloud(self) -> bool:
        """Retorna True se volume diário excedeu threshold"""
        return self.get_daily_count() >= settings.OCR_CLOUD_THRESHOLD_DAILY


# Singleton do tracker
_usage_tracker = OCRUsageTracker()


class HybridOCRService:
    """
    Serviço de OCR com estratégia híbrida inteligente
    """

    def __init__(self):
        self.tracker = _usage_tracker
        self.default_provider = OCRProvider(settings.OCR_PROVIDER)
        logger.info(
            f"HybridOCRService inicializado - Provider padrão: {self.default_provider}, "
            f"Threshold cloud: {settings.OCR_CLOUD_THRESHOLD_DAILY} páginas/dia"
        )

    async def extract_text_from_pdf(
        self,
        file_path: str,
        force_ocr: bool = False,
        preferred_provider: Optional[OCRProvider] = None,
    ) -> OCRResult:
        """
        Extrai texto de PDF com estratégia inteligente

        Args:
            file_path: Caminho do PDF
            force_ocr: Força OCR mesmo se PDF tiver texto selecionável
            preferred_provider: Provider específico (ignora estratégia automática)
        """
        logger.info(f"Processando PDF: {file_path}")

        # 1. Tentar extrair texto selecionável (não é OCR)
        if not force_ocr:
            text = await self._try_pymupdf_text(file_path)
            if text and len(text.strip()) > 100:
                logger.info("Texto extraído via PyMuPDF (texto selecionável)")
                return OCRResult(
                    text=text,
                    provider=OCRProvider.PYMUPDF,
                    pages_processed=self._count_pdf_pages(file_path),
                )

        # 2. Precisa de OCR - determinar provider
        provider = preferred_provider or self._select_provider()
        logger.info(f"Usando OCR provider: {provider}")

        # 3. Executar OCR com fallback
        result = await self._execute_ocr(file_path, provider)

        # 4. Fallback se falhou
        if result.error and provider != OCRProvider.TESSERACT:
            logger.warning(f"Falha no {provider}, tentando Tesseract como fallback")
            result = await self._execute_ocr(file_path, OCRProvider.TESSERACT)

        # 5. Atualizar contador
        if not result.error:
            self.tracker.increment(result.pages_processed)

        return result

    async def extract_text_from_image(
        self,
        file_path: str,
        preferred_provider: Optional[OCRProvider] = None,
    ) -> OCRResult:
        """
        Extrai texto de imagem (sempre precisa de OCR)
        """
        provider = preferred_provider or self._select_provider()
        logger.info(f"OCR em imagem: {file_path} via {provider}")

        result = await self._execute_image_ocr(file_path, provider)

        # Fallback
        if result.error and provider != OCRProvider.TESSERACT:
            logger.warning(f"Falha no {provider}, tentando Tesseract")
            result = await self._execute_image_ocr(file_path, OCRProvider.TESSERACT)

        if not result.error:
            self.tracker.increment(1)

        return result

    def _select_provider(self) -> OCRProvider:
        """
        Seleciona provider baseado em:
        1. Volume diário
        2. Disponibilidade de credenciais
        3. Configuração padrão
        """
        # Se volume alto, preferir cloud (se configurado)
        if self.tracker.should_use_cloud():
            if settings.AZURE_DOCUMENT_INTELLIGENCE_KEY:
                return OCRProvider.AZURE
            if settings.GEMINI_OCR_ENABLED and settings.GOOGLE_API_KEY:
                return OCRProvider.GEMINI
            if settings.GOOGLE_VISION_ENABLED:
                return OCRProvider.GOOGLE

        # Caso contrário, usar configuração padrão
        return self.default_provider

    async def _try_pymupdf_text(self, file_path: str) -> Optional[str]:
        """Tenta extrair texto selecionável do PDF via PyMuPDF."""
        try:
            import fitz

            text_content = []
            with fitz.open(file_path) as pdf:
                for page in pdf:
                    text = page.get_text("text") or ""
                    text_content.append(text)

            return "\n\n".join(text_content)
        except Exception as e:
            logger.debug(f"PyMuPDF text extraction falhou: {e}")
            return None

    def _render_pdf_pages_to_images(self, file_path: str, dpi: Optional[int] = None) -> list[Image.Image]:
        """
        Renderiza páginas de PDF em imagens PIL usando PyMuPDF.
        Evita dependência de poppler/pdf2image no caminho principal.
        """
        import fitz

        dpi = int(dpi or settings.OCR_DPI or 300)
        zoom = dpi / 72.0
        matrix = fitz.Matrix(zoom, zoom)
        images: list[Image.Image] = []

        with fitz.open(file_path) as pdf:
            for page in pdf:
                pix = page.get_pixmap(matrix=matrix, alpha=False)
                mode = "RGB"
                image = Image.frombytes(mode, [pix.width, pix.height], pix.samples)
                images.append(image)

        return images

    async def _execute_ocr(self, file_path: str, provider: OCRProvider) -> OCRResult:
        """Executa OCR no PDF usando provider especificado"""
        try:
            if provider == OCRProvider.TESSERACT:
                return await self._ocr_tesseract_pdf(file_path)
            elif provider == OCRProvider.AZURE:
                return await self._ocr_azure_pdf(file_path)
            elif provider == OCRProvider.GOOGLE:
                return await self._ocr_google_pdf(file_path)
            elif provider == OCRProvider.GEMINI:
                return await self._ocr_gemini_pdf(file_path)
            else:
                return await self._ocr_tesseract_pdf(file_path)
        except Exception as e:
            logger.error(f"Erro no OCR ({provider}): {e}")
            return OCRResult(
                text="",
                provider=provider,
                pages_processed=0,
                error=str(e),
            )

    async def _execute_image_ocr(
        self, file_path: str, provider: OCRProvider
    ) -> OCRResult:
        """Executa OCR em imagem usando provider especificado"""
        try:
            if provider == OCRProvider.TESSERACT:
                return await self._ocr_tesseract_image(file_path)
            elif provider == OCRProvider.AZURE:
                return await self._ocr_azure_image(file_path)
            elif provider == OCRProvider.GOOGLE:
                return await self._ocr_google_image(file_path)
            elif provider == OCRProvider.GEMINI:
                return await self._ocr_gemini_image(file_path)
            else:
                return await self._ocr_tesseract_image(file_path)
        except Exception as e:
            logger.error(f"Erro no OCR de imagem ({provider}): {e}")
            return OCRResult(
                text="",
                provider=provider,
                pages_processed=0,
                error=str(e),
            )

    # ==================== TESSERACT ====================

    async def _ocr_tesseract_pdf(self, file_path: str) -> OCRResult:
        """OCR via Tesseract (local)"""
        import pytesseract

        logger.info(f"Tesseract OCR em PDF: {file_path}")

        images = self._render_pdf_pages_to_images(file_path, dpi=settings.OCR_DPI)
        ocr_texts = []

        for i, image in enumerate(images, 1):
            logger.debug(f"Tesseract: página {i}/{len(images)}")
            page_text = pytesseract.image_to_string(image, lang=settings.TESSERACT_LANG)
            if page_text.strip():
                ocr_texts.append(f"--- Página {i} ---\n{page_text}")
            else:
                ocr_texts.append(f"--- Página {i} ---\n[Sem texto detectado]")

        return OCRResult(
            text="\n\n".join(ocr_texts),
            provider=OCRProvider.TESSERACT,
            pages_processed=len(images),
        )

    async def _ocr_tesseract_image(self, file_path: str) -> OCRResult:
        """OCR via Tesseract em imagem única"""
        import pytesseract

        image = Image.open(file_path)
        text = pytesseract.image_to_string(image, lang=settings.TESSERACT_LANG)

        return OCRResult(
            text=text,
            provider=OCRProvider.TESSERACT,
            pages_processed=1,
        )

    # ==================== AZURE ====================

    async def _ocr_azure_pdf(self, file_path: str) -> OCRResult:
        """OCR via Azure Document Intelligence"""
        from azure.ai.documentintelligence import DocumentIntelligenceClient
        from azure.core.credentials import AzureKeyCredential

        endpoint = settings.AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT
        key = settings.AZURE_DOCUMENT_INTELLIGENCE_KEY

        if not endpoint or not key:
            raise ValueError("Azure Document Intelligence não configurado")

        logger.info(f"Azure OCR em PDF: {file_path}")

        client = DocumentIntelligenceClient(
            endpoint=endpoint,
            credential=AzureKeyCredential(key),
        )

        with open(file_path, "rb") as f:
            poller = client.begin_analyze_document(
                "prebuilt-read",
                body=f,
                content_type="application/pdf",
            )

        result = poller.result()

        # Extrair texto de todas as páginas
        text_content = []
        for page in result.pages:
            page_text = []
            for line in page.lines:
                page_text.append(line.content)
            text_content.append(
                f"--- Página {page.page_number} ---\n" + "\n".join(page_text)
            )

        return OCRResult(
            text="\n\n".join(text_content),
            provider=OCRProvider.AZURE,
            pages_processed=len(result.pages),
        )

    async def _ocr_azure_image(self, file_path: str) -> OCRResult:
        """OCR via Azure em imagem única"""
        from azure.ai.documentintelligence import DocumentIntelligenceClient
        from azure.core.credentials import AzureKeyCredential

        endpoint = settings.AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT
        key = settings.AZURE_DOCUMENT_INTELLIGENCE_KEY

        if not endpoint or not key:
            raise ValueError("Azure Document Intelligence não configurado")

        client = DocumentIntelligenceClient(
            endpoint=endpoint,
            credential=AzureKeyCredential(key),
        )

        with open(file_path, "rb") as f:
            poller = client.begin_analyze_document(
                "prebuilt-read",
                body=f,
            )

        result = poller.result()

        text_lines = []
        for page in result.pages:
            for line in page.lines:
                text_lines.append(line.content)

        return OCRResult(
            text="\n".join(text_lines),
            provider=OCRProvider.AZURE,
            pages_processed=1,
        )

    # ==================== GOOGLE CLOUD VISION ====================

    async def _ocr_google_pdf(self, file_path: str) -> OCRResult:
        """OCR via Google Cloud Vision"""
        from google.cloud import vision
        import io

        logger.info(f"Google Vision OCR em PDF: {file_path}")

        client = vision.ImageAnnotatorClient()
        images = self._render_pdf_pages_to_images(file_path, dpi=settings.OCR_DPI)
        text_content = []

        for i, pil_image in enumerate(images, 1):
            # Converter PIL para bytes
            img_byte_arr = io.BytesIO()
            pil_image.save(img_byte_arr, format="PNG")
            img_bytes = img_byte_arr.getvalue()

            image = vision.Image(content=img_bytes)
            response = client.text_detection(image=image)

            if response.text_annotations:
                page_text = response.text_annotations[0].description
                text_content.append(f"--- Página {i} ---\n{page_text}")
            else:
                text_content.append(f"--- Página {i} ---\n[Sem texto detectado]")

        return OCRResult(
            text="\n\n".join(text_content),
            provider=OCRProvider.GOOGLE,
            pages_processed=len(images),
        )

    async def _ocr_google_image(self, file_path: str) -> OCRResult:
        """OCR via Google Cloud Vision em imagem"""
        from google.cloud import vision

        client = vision.ImageAnnotatorClient()

        with open(file_path, "rb") as f:
            content = f.read()

        image = vision.Image(content=content)
        response = client.text_detection(image=image)

        text = ""
        if response.text_annotations:
            text = response.text_annotations[0].description

        return OCRResult(
            text=text,
            provider=OCRProvider.GOOGLE,
            pages_processed=1,
        )

    # ==================== GEMINI VISION ====================

    async def _ocr_gemini_pdf(self, file_path: str) -> OCRResult:
        """OCR via Gemini Vision (mais barato que Google Vision tradicional)"""
        import google.generativeai as genai
        import io

        logger.info(f"Gemini Vision OCR em PDF: {file_path}")

        genai.configure(api_key=settings.GOOGLE_API_KEY)
        model = genai.GenerativeModel(settings.GEMINI_OCR_MODEL)

        images = self._render_pdf_pages_to_images(file_path, dpi=settings.OCR_DPI)
        text_content = []

        prompt = """Extraia TODO o texto desta imagem de documento.
Mantenha a formatação original o máximo possível.
Retorne APENAS o texto extraído, sem comentários adicionais."""

        for i, pil_image in enumerate(images, 1):
            logger.debug(f"Gemini OCR: página {i}/{len(images)}")

            # Converter PIL para bytes
            img_byte_arr = io.BytesIO()
            pil_image.save(img_byte_arr, format="PNG")
            img_bytes = img_byte_arr.getvalue()

            response = model.generate_content(
                [prompt, {"mime_type": "image/png", "data": img_bytes}]
            )

            page_text = response.text if response.text else "[Sem texto detectado]"
            text_content.append(f"--- Página {i} ---\n{page_text}")

        return OCRResult(
            text="\n\n".join(text_content),
            provider=OCRProvider.GEMINI,
            pages_processed=len(images),
        )

    async def _ocr_gemini_image(self, file_path: str) -> OCRResult:
        """OCR via Gemini Vision em imagem única"""
        import google.generativeai as genai

        genai.configure(api_key=settings.GOOGLE_API_KEY)
        model = genai.GenerativeModel(settings.GEMINI_OCR_MODEL)

        with open(file_path, "rb") as f:
            image_bytes = f.read()

        # Detectar mime type
        ext = os.path.splitext(file_path)[1].lower()
        mime_map = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".bmp": "image/bmp",
            ".webp": "image/webp",
        }
        mime_type = mime_map.get(ext, "image/png")

        prompt = """Extraia TODO o texto desta imagem de documento.
Mantenha a formatação original o máximo possível.
Retorne APENAS o texto extraído, sem comentários adicionais."""

        response = model.generate_content(
            [prompt, {"mime_type": mime_type, "data": image_bytes}]
        )

        return OCRResult(
            text=response.text or "",
            provider=OCRProvider.GEMINI,
            pages_processed=1,
        )

    # ==================== UTILS ====================

    def _count_pdf_pages(self, file_path: str) -> int:
        """Conta páginas do PDF"""
        try:
            import fitz

            with fitz.open(file_path) as pdf:
                return len(pdf)
        except Exception:
            return 1

    def get_usage_stats(self) -> dict:
        """Retorna estatísticas de uso"""
        return {
            "daily_pages": self.tracker.get_daily_count(),
            "threshold": settings.OCR_CLOUD_THRESHOLD_DAILY,
            "should_use_cloud": self.tracker.should_use_cloud(),
            "default_provider": self.default_provider.value,
        }


# Singleton do serviço
_ocr_service: Optional[HybridOCRService] = None


def get_ocr_service() -> HybridOCRService:
    """Retorna instância singleton do serviço OCR"""
    global _ocr_service
    if _ocr_service is None:
        _ocr_service = HybridOCRService()
    return _ocr_service
