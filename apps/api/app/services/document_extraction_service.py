"""
Serviço unificado de extração de texto.

Centraliza a decisão de extração para evitar divergência entre:
- DoclingAdapter (FAST/TABLES/OCR)
- fallbacks de OCR em endpoints
- workers assíncronos
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

from loguru import logger

from app.core.config import settings
from app.services.docling_adapter import get_docling_adapter
from app.services.document_processor import extract_text_from_pdf_with_ocr


DEFAULT_MIN_PDF_CHARS = 50


@dataclass
class UnifiedExtractionResult:
    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)


def _pdf_ocr_enabled() -> bool:
    return bool(getattr(settings, "DOCLING_OCR_ENABLED", True)) and bool(settings.ENABLE_OCR)


def should_run_pdf_ocr(
    extracted_text: str,
    *,
    ocr_requested: Optional[bool] = None,
    min_pdf_chars: int = DEFAULT_MIN_PDF_CHARS,
) -> bool:
    """
    Regra única para decidir OCR em PDF.

    Regras:
    - `ocr_requested=True`  -> sempre OCR (se habilitado em config)
    - `ocr_requested=False` -> nunca OCR
    - `ocr_requested=None`  -> OCR quando texto extraído é insuficiente
    """
    if ocr_requested is False:
        return False
    if not _pdf_ocr_enabled():
        return False
    if ocr_requested is True:
        return True
    return len((extracted_text or "").strip()) < int(min_pdf_chars or DEFAULT_MIN_PDF_CHARS)


async def extract_text_from_path(
    file_path: str,
    *,
    min_pdf_chars: int = DEFAULT_MIN_PDF_CHARS,
    allow_pdf_ocr_fallback: bool = True,
    ocr_requested: Optional[bool] = None,
    force_pdf_ocr: bool = False,
) -> UnifiedExtractionResult:
    """
    Entry-point único para extração de texto.

    - Para todos formatos: tenta DoclingAdapter (com fallback interno do adapter).
    - Para PDF: opcionalmente aplica OCR híbrido quando necessário e escolhe
      o melhor resultado entre texto nativo e OCR.
    """
    ext = Path(file_path).suffix.lower()
    adapter = get_docling_adapter()

    text = ""
    metadata: Dict[str, Any] = {}
    try:
        result = await adapter.extract(file_path)
        text = str(result.text or "")
        metadata = dict(result.metadata or {})
    except Exception as exc:
        logger.warning(f"Falha no adapter para {file_path}: {exc}")
        metadata = {
            "extraction_engine": "adapter_error",
            "adapter_error": str(exc),
        }

    if ext != ".pdf":
        metadata.update({
            "unified_extraction": True,
            "unified_route": "adapter_only",
        })
        return UnifiedExtractionResult(text=text, metadata=metadata)

    should_ocr = False
    if force_pdf_ocr:
        should_ocr = True
    elif allow_pdf_ocr_fallback:
        should_ocr = should_run_pdf_ocr(
            text,
            ocr_requested=ocr_requested,
            min_pdf_chars=min_pdf_chars,
        )

    if not should_ocr:
        metadata.update({
            "unified_extraction": True,
            "unified_route": "pdf_adapter",
            "unified_docling_chars": len(text.strip()),
            "unified_ocr_attempted": False,
        })
        return UnifiedExtractionResult(text=text, metadata=metadata)

    ocr_text = ""
    ocr_error: Optional[str] = None
    try:
        ocr_text = await extract_text_from_pdf_with_ocr(
            file_path,
            force_ocr=bool(force_pdf_ocr),
        )
    except Exception as exc:
        ocr_error = str(exc)
        logger.warning(f"OCR fallback falhou para {file_path}: {exc}")

    docling_chars = len((text or "").strip())
    ocr_chars = len((ocr_text or "").strip())
    use_ocr_text = ocr_chars > docling_chars
    final_text = ocr_text if use_ocr_text else text

    metadata.update({
        "unified_extraction": True,
        "unified_route": "pdf_adapter_plus_ocr",
        "unified_docling_chars": docling_chars,
        "unified_ocr_chars": ocr_chars,
        "unified_ocr_attempted": True,
        "unified_ocr_selected": use_ocr_text,
        "unified_ocr_force": bool(force_pdf_ocr),
        "unified_ocr_error": ocr_error,
    })

    if use_ocr_text:
        metadata["extraction_engine"] = "ocr_hybrid"

    return UnifiedExtractionResult(text=final_text, metadata=metadata)
