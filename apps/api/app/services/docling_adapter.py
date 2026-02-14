"""
DoclingAdapter - ponto unico de extracao de texto.

Todos os fluxos de upload devem usar este servico para manter
consistencia entre ingestao RAG e consumo por IA.

Estrategia 3-tier adaptativa para PDFs:
  1. FAST  — layout only (sem OCR, sem TableFormer)
  2. TABLES — layout + TableFormer (densidade de tabelas >= 5% OU documento pequeno)
  3. OCR    — layout + OCR + TableFormer (texto esparso <150 chars/pág OU baixa qualidade)

Critérios de qualidade de texto:
  - Printable ratio >= 85% (evita encoding corrupto)
  - Space ratio 8-35% (palavras separadas, não gibberish)
  - Avg token length 2-25 chars (estrutura de palavras razoável)
"""

from __future__ import annotations

import asyncio
import os
import re
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Dict, List, Optional

from loguru import logger

from app.core.config import settings

# Adaptive extraction thresholds (configurable via env vars)
_MIN_CHARS_PER_PAGE = int(os.getenv("DOCLING_MIN_CHARS_PER_PAGE", "150"))  # chars/page
_MIN_TABLE_DENSITY = float(os.getenv("DOCLING_MIN_TABLE_DENSITY", "0.05"))  # tables/pages
_MIN_PRINTABLE_RATIO = float(os.getenv("DOCLING_MIN_PRINTABLE_RATIO", "0.85"))  # ASCII printable
_MIN_SPACE_RATIO = float(os.getenv("DOCLING_MIN_SPACE_RATIO", "0.08"))  # word separation
_MAX_SPACE_RATIO = float(os.getenv("DOCLING_MAX_SPACE_RATIO", "0.35"))  # too sparse


@dataclass
class ExtractionResult:
    text: str
    metadata: Dict[str, Any]

    @property
    def engine(self) -> str:
        return str(self.metadata.get("extraction_engine") or "unknown")


class DoclingAdapter:
    """
    Adaptador unificado de extracao.

    Estrategia 3-tier adaptativa:
    1. Docling FAST (sem OCR, sem TableFormer) — maioria dos PDFs
    2. Docling TABLES (com TableFormer) — densidade de tabelas >= 5% (config.)
    3. Docling OCR (OCR + TableFormer) — texto esparso <150 chars/pág OU baixa qualidade
    4. Fallback para extratores legacy

    Validação de qualidade de texto FAST:
    - Printable ratio >= 85%, space ratio 8-35%, avg token len 2-25 chars
    - Se qualidade baixa → re-extrai com OCR
    """

    def __init__(self) -> None:
        self._enabled = bool(getattr(settings, "DOCLING_ENABLED", True))
        self._docling_available = self._check_docling() if self._enabled else False
        # Legacy single converter (kept for non-PDF formats)
        self.converter = None
        # 3-tier PDF converters (lazy-initialized)
        self._converter_fast: Any = None
        self._converter_tables: Any = None
        self._converter_ocr: Any = None

        if self._docling_available:
            try:
                from docling.document_converter import DocumentConverter  # noqa: F401

                logger.info("DoclingAdapter inicializado (3-tier adaptativo)")
            except Exception as exc:
                self._docling_available = False
                logger.warning(f"Docling indisponivel, usando fallback: {exc}")
        else:
            logger.info("Docling desabilitado/indisponivel, usando fallback")

    def is_available(self) -> bool:
        return self._docling_available

    def _check_docling(self) -> bool:
        try:
            from docling.document_converter import DocumentConverter  # noqa: F401

            return True
        except Exception:
            return False

    # -----------------------------------------------------------------
    # Lazy-initialized 3-tier converters
    # -----------------------------------------------------------------

    def _get_converter(self, mode: str = "fast") -> Any:
        """Lazy-init Docling converter by tier.

        fast   = no OCR, no TableFormer (text-native PDFs)
        tables = no OCR, with TableFormer (PDFs with tables)
        ocr    = OCR + TableFormer (scanned PDFs)
        """
        if mode == "fast":
            if self._converter_fast is None:
                from docling.document_converter import DocumentConverter, PdfFormatOption
                from docling.datamodel.base_models import InputFormat
                from docling.datamodel.pipeline_options import PdfPipelineOptions

                po = PdfPipelineOptions()
                po.do_ocr = False
                po.do_table_structure = False
                self._converter_fast = DocumentConverter(
                    allowed_formats=[InputFormat.PDF],
                    format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=po)},
                )
                logger.info("Docling FAST inicializado (sem OCR, sem TableFormer)")
            return self._converter_fast

        if mode == "tables":
            if self._converter_tables is None:
                from docling.document_converter import DocumentConverter, PdfFormatOption
                from docling.datamodel.base_models import InputFormat
                from docling.datamodel.pipeline_options import PdfPipelineOptions

                po = PdfPipelineOptions()
                po.do_ocr = False
                po.do_table_structure = True
                self._converter_tables = DocumentConverter(
                    allowed_formats=[InputFormat.PDF],
                    format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=po)},
                )
                logger.info("Docling TABLES inicializado (sem OCR, com TableFormer)")
            return self._converter_tables

        # mode == "ocr"
        if self._converter_ocr is None:
            from docling.document_converter import DocumentConverter, PdfFormatOption
            from docling.datamodel.base_models import InputFormat
            from docling.datamodel.pipeline_options import PdfPipelineOptions

            po = PdfPipelineOptions()
            po.do_ocr = True
            po.do_table_structure = True
            self._converter_ocr = DocumentConverter(
                allowed_formats=[InputFormat.PDF],
                format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=po)},
            )
            logger.info("Docling OCR inicializado (OCR + TableFormer)")
        return self._converter_ocr

    def _get_generic_converter(self) -> Any:
        """Lazy-init a generic converter for non-PDF formats (DOCX, PPTX, etc.)."""
        if self.converter is None:
            from docling.document_converter import DocumentConverter

            self.converter = DocumentConverter()
            logger.info("Docling generico inicializado (non-PDF formats)")
        return self.converter

    # -----------------------------------------------------------------
    # Detection helpers
    # -----------------------------------------------------------------

    @staticmethod
    def _is_text_sparse(text: str, npages: int) -> bool:
        """Detect scanned/image PDFs by checking chars per page."""
        if not text or npages == 0:
            return True
        return len(text.strip()) / max(npages, 1) < _MIN_CHARS_PER_PAGE

    @staticmethod
    def _has_significant_tables(doc: Any, npages: int) -> bool:
        """Detect if DoclingDocument has significant table density.

        Returns True if:
        - Has tables AND (tables/pages >= threshold OR only 1-2 pages)
        """
        if not hasattr(doc, "tables") or len(doc.tables) == 0:
            return False

        ntables = len(doc.tables)

        # Single/few page documents: any table is significant
        if npages <= 2:
            return True

        # Multi-page: check density threshold
        density = ntables / max(npages, 1)
        return density >= _MIN_TABLE_DENSITY

    @staticmethod
    def _is_text_quality_good(text: str) -> bool:
        """Validate text quality from FAST tier extraction.

        Checks:
        1. Printable ASCII ratio (gibberish/encoding issues)
        2. Space ratio (word separation - OCR artifacts often lack spaces)
        3. Basic word structure (avg token length)

        Returns False if text looks corrupted/OCR-garbled.
        """
        if not text or len(text.strip()) < 50:
            return False

        # 1. Printable ASCII ratio
        printable_count = sum(1 for c in text if c.isprintable() or c in '\n\r\t')
        printable_ratio = printable_count / len(text)
        if printable_ratio < _MIN_PRINTABLE_RATIO:
            return False

        # 2. Space ratio (word separation)
        space_count = text.count(' ')
        space_ratio = space_count / len(text)
        if space_ratio < _MIN_SPACE_RATIO or space_ratio > _MAX_SPACE_RATIO:
            return False

        # 3. Word structure (avg token length should be reasonable 3-15 chars)
        tokens = text.split()
        if len(tokens) < 10:  # too few words
            return False

        avg_token_len = sum(len(t) for t in tokens[:100]) / min(len(tokens), 100)
        if avg_token_len < 2 or avg_token_len > 25:  # suspiciously short/long
            return False

        return True

    # -----------------------------------------------------------------
    # Main extraction
    # -----------------------------------------------------------------

    async def extract(self, file_path: str) -> ExtractionResult:
        ext = os.path.splitext(file_path)[1].lower()

        if self._docling_available and ext in self._docling_supported_formats():
            try:
                if ext == ".pdf":
                    return await self._extract_pdf_adaptive(file_path)
                return await self._extract_with_docling(file_path)
            except Exception as exc:
                logger.warning(f"Docling falhou para {file_path}, fallback: {exc}")

        return await self._extract_with_fallback(file_path, ext)

    def _docling_supported_formats(self) -> set[str]:
        return {
            ".pdf",
            ".docx",
            ".pptx",
            ".xlsx",
            ".html",
            ".png",
            ".jpg",
            ".jpeg",
            ".gif",
            ".bmp",
            ".tiff",
            ".tif",
        }

    # -----------------------------------------------------------------
    # PDF adaptive extraction (3-tier)
    # -----------------------------------------------------------------

    async def _extract_pdf_adaptive(self, file_path: str) -> ExtractionResult:
        return await asyncio.to_thread(self._docling_pdf_adaptive_sync, file_path)

    def _docling_pdf_adaptive_sync(self, file_path: str) -> ExtractionResult:
        """3-tier adaptive PDF extraction.

        Phase 1: FAST (layout only, no OCR, no TableFormer)
        Phase 2: Quality checks + adaptive re-extraction:
                 - Text sparse OR low quality → OCR + TableFormer
                 - Significant table density → TableFormer only
        """
        # Phase 1: fast extraction
        tier = "fast"
        converter = self._get_converter("fast")
        result = converter.convert(file_path)
        doc = result.document
        markdown = doc.export_to_markdown() if doc else ""
        npages = self._extract_pages_count(doc)

        # Phase 2: quality checks + adaptive re-extraction
        is_sparse = self._is_text_sparse(markdown, npages)
        quality_good = self._is_text_quality_good(markdown) if not is_sparse else False
        has_significant_tbl = self._has_significant_tables(doc, npages)

        # Decision tree: OCR > TABLES > FAST
        needs_ocr = is_sparse or (not quality_good and npages > 0)

        if needs_ocr:
            tier = "ocr"
            reason = "texto esparso" if is_sparse else "baixa qualidade de texto"
            logger.info(
                f"{reason} ({len(markdown or '')} chars, {npages} pgs) "
                f"-> reprocessando com OCR: {os.path.basename(file_path)}"
            )
            converter2 = self._get_converter("ocr")
            result = converter2.convert(file_path)
            doc = result.document
            markdown = doc.export_to_markdown() if doc else ""
            npages = self._extract_pages_count(doc)
            logger.info(f"OCR: {npages} paginas, {len(markdown)} chars")

        elif has_significant_tbl:
            tier = "tables"
            ntables = len(doc.tables) if hasattr(doc, "tables") else 0
            density = ntables / max(npages, 1)
            logger.info(
                f"{ntables} tabelas ({density:.2%} densidade) "
                f"-> reprocessando com TableFormer: {os.path.basename(file_path)}"
            )
            converter2 = self._get_converter("tables")
            result = converter2.convert(file_path)
            doc = result.document
            markdown = doc.export_to_markdown() if doc else ""
            npages = self._extract_pages_count(doc)
            logger.info(f"TableFormer: {npages} paginas, {len(markdown)} chars")

        # Fallback to plain text if markdown is empty
        if not markdown or not markdown.strip():
            markdown = doc.export_to_text() if doc else ""

        sections = self._extract_sections_from_markdown(markdown)
        tables_count = self._extract_tables_from_markdown(markdown)
        has_images = "![ " in markdown or "![" in markdown

        return ExtractionResult(
            text=markdown or "",
            metadata={
                "extraction_engine": "docling",
                "docling_tier": tier,
                "pages": npages,
                "tables_count": tables_count,
                "sections": sections,
                "has_images": has_images,
            },
        )

    # -----------------------------------------------------------------
    # Non-PDF Docling extraction
    # -----------------------------------------------------------------

    async def _extract_with_docling(self, file_path: str) -> ExtractionResult:
        return await asyncio.to_thread(self._docling_sync, file_path)

    def _docling_sync(self, file_path: str) -> ExtractionResult:
        converter = self._get_generic_converter()
        result = converter.convert(file_path)
        doc = result.document
        markdown = doc.export_to_markdown() if doc else ""
        pages = self._extract_pages_count(doc)
        sections = self._extract_sections_from_markdown(markdown)
        tables_count = self._extract_tables_from_markdown(markdown)
        has_images = "![ " in markdown or "![" in markdown

        return ExtractionResult(
            text=markdown or "",
            metadata={
                "extraction_engine": "docling",
                "docling_tier": "generic",
                "pages": pages,
                "tables_count": tables_count,
                "sections": sections,
                "has_images": has_images,
            },
        )

    def _extract_pages_count(self, doc: Any) -> int:
        if doc is None:
            return 0
        if hasattr(doc, "pages"):
            try:
                return int(len(doc.pages))
            except Exception:
                return 0
        if hasattr(doc, "num_pages"):
            try:
                return int(doc.num_pages)
            except Exception:
                return 0
        return 0

    def _extract_sections_from_markdown(self, text: str) -> List[str]:
        if not text:
            return []
        sections: List[str] = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped.startswith("#"):
                continue
            title = stripped.lstrip("#").strip()
            if title:
                sections.append(title[:200])
            if len(sections) >= 50:
                break
        return sections

    def _extract_tables_from_markdown(self, text: str) -> int:
        if not text:
            return 0
        # Heuristica simples de tabela markdown.
        matches = re.findall(r"\|.+\|\n\|[\s:\-|]+\|", text)
        return len(matches)

    async def _extract_with_fallback(self, file_path: str, ext: str) -> ExtractionResult:
        extractors = self._get_fallback_extractors()

        if ext == ".doc":
            return await asyncio.to_thread(self._extract_doc_binary_sync, file_path)

        extractor = extractors.get(ext)
        if extractor:
            text = await extractor(file_path)
            metadata: Dict[str, Any] = {
                "extraction_engine": "fallback",
                "fallback_library": getattr(extractor, "__name__", "unknown"),
            }
            if ext == ".zip" and isinstance(text, dict):
                return ExtractionResult(
                    text=str(text.get("extracted_text") or ""),
                    metadata={
                        **metadata,
                        "zip_files": text.get("files", []),
                        "zip_total_files": text.get("total_files", 0),
                        "zip_errors": text.get("errors", []),
                    },
                )
            return ExtractionResult(text=str(text or ""), metadata=metadata)

        if ext in {".txt", ".md"}:
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as fh:
                    return ExtractionResult(
                        text=fh.read(),
                        metadata={"extraction_engine": "plain_text"},
                    )
            except OSError as exc:
                return ExtractionResult(
                    text="",
                    metadata={"extraction_engine": "plain_text", "error": str(exc)},
                )

        if ext in {".html", ".htm"}:
            try:
                from bs4 import BeautifulSoup

                with open(file_path, "r", encoding="utf-8", errors="ignore") as fh:
                    soup = BeautifulSoup(fh.read(), "html.parser")
                    return ExtractionResult(
                        text=soup.get_text("\n"),
                        metadata={"extraction_engine": "html_fallback"},
                    )
            except Exception as exc:
                return ExtractionResult(
                    text="",
                    metadata={"extraction_engine": "html_fallback", "error": str(exc)},
                )

        return ExtractionResult(
            text="",
            metadata={
                "extraction_engine": "unsupported",
                "error": f"Formato nao suportado: {ext}",
            },
        )

    def _get_fallback_extractors(self) -> Dict[str, Any]:
        from app.services.document_processor import (
            extract_text_from_csv,
            extract_text_from_docx,
            extract_text_from_odt,
            extract_text_from_pdf,
            extract_text_from_pptx,
            extract_text_from_rtf,
            extract_text_from_xlsx,
            extract_text_from_zip,
        )

        return {
            ".pdf": extract_text_from_pdf,
            ".docx": extract_text_from_docx,
            ".odt": extract_text_from_odt,
            ".pptx": extract_text_from_pptx,
            ".xlsx": extract_text_from_xlsx,
            ".xls": extract_text_from_xlsx,
            ".csv": extract_text_from_csv,
            ".rtf": extract_text_from_rtf,
            ".zip": extract_text_from_zip,
        }

    def _extract_doc_binary_sync(self, file_path: str) -> ExtractionResult:
        try:
            proc = subprocess.run(
                ["antiword", file_path],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if proc.returncode == 0:
                return ExtractionResult(
                    text=proc.stdout or "",
                    metadata={"extraction_engine": "antiword"},
                )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        except Exception as exc:
            return ExtractionResult(
                text="",
                metadata={"extraction_engine": "antiword", "error": str(exc)},
            )

        return ExtractionResult(
            text="",
            metadata={
                "extraction_engine": "unsupported",
                "error": ".doc binario requer antiword/LibreOffice",
            },
        )


@lru_cache(maxsize=1)
def get_docling_adapter() -> DoclingAdapter:
    return DoclingAdapter()
