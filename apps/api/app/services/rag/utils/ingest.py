"""
RAG Ingest Utilities

Provides chunking and PDF extraction utilities for document ingestion.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from pypdf import PdfReader
import io


@dataclass
class Chunk:
    """Represents a text chunk with metadata."""
    text: str
    page: Optional[int] = None
    chunk_index: int = 0


def chunk_text(
    text: str,
    *,
    chunk_chars: int = 1200,
    overlap: int = 200,
    page: Optional[int] = None,
) -> List[Chunk]:
    """
    Split text into overlapping chunks.

    Args:
        text: Text to split
        chunk_chars: Maximum characters per chunk
        overlap: Number of overlapping characters between chunks
        page: Optional page number for metadata

    Returns:
        List of Chunk objects
    """
    text = (text or "").strip()
    if not text:
        return []

    chunks: List[Chunk] = []
    i = 0
    idx = 0
    step = max(1, chunk_chars - overlap)

    while i < len(text):
        part = text[i : i + chunk_chars].strip()
        if part:
            chunks.append(Chunk(text=part, page=page, chunk_index=idx))
            idx += 1
        i += step

    return chunks


def extract_pdf_pages(pdf_bytes: bytes) -> List[Tuple[int, str]]:
    """
    Extract text from PDF pages.

    Args:
        pdf_bytes: PDF file content as bytes

    Returns:
        List of (page_number, text) tuples
    """
    reader = PdfReader(io.BytesIO(pdf_bytes))
    out: List[Tuple[int, str]] = []

    for i, page in enumerate(reader.pages, start=1):
        try:
            txt = page.extract_text() or ""
        except Exception:
            txt = ""
        out.append((i, txt))

    return out


def chunk_document(
    text: str,
    *,
    chunk_chars: int = 1200,
    overlap: int = 200,
    doc_id: Optional[str] = None,
) -> List[dict]:
    """
    Chunk a document and return list of dicts ready for ingestion.

    Args:
        text: Document text
        chunk_chars: Maximum characters per chunk
        overlap: Overlap between chunks
        doc_id: Optional document ID

    Returns:
        List of chunk dictionaries with text and metadata
    """
    chunks = chunk_text(text, chunk_chars=chunk_chars, overlap=overlap)
    return [
        {
            "text": c.text,
            "chunk_index": c.chunk_index,
            "doc_id": doc_id,
            "page": c.page,
        }
        for c in chunks
    ]


def chunk_pdf(
    pdf_bytes: bytes,
    *,
    chunk_chars: int = 1200,
    overlap: int = 200,
    doc_id: Optional[str] = None,
) -> List[dict]:
    """
    Extract and chunk a PDF document.

    Args:
        pdf_bytes: PDF file content
        chunk_chars: Maximum characters per chunk
        overlap: Overlap between chunks
        doc_id: Optional document ID

    Returns:
        List of chunk dictionaries with text and metadata
    """
    pages = extract_pdf_pages(pdf_bytes)
    all_chunks: List[dict] = []
    global_idx = 0

    for page_num, page_text in pages:
        page_chunks = chunk_text(
            page_text,
            chunk_chars=chunk_chars,
            overlap=overlap,
            page=page_num,
        )
        for chunk in page_chunks:
            all_chunks.append({
                "text": chunk.text,
                "chunk_index": global_idx,
                "page": chunk.page,
                "doc_id": doc_id,
            })
            global_idx += 1

    return all_chunks
