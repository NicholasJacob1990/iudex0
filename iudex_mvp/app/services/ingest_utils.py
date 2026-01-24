
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from pypdf import PdfReader
import io


@dataclass
class Chunk:
    text: str
    page: Optional[int] = None
    chunk_index: int = 0


def chunk_text(text: str, *, chunk_chars: int = 1200, overlap: int = 200, page: Optional[int] = None) -> List[Chunk]:
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
    reader = PdfReader(io.BytesIO(pdf_bytes))
    out: List[Tuple[int, str]] = []
    for i, page in enumerate(reader.pages, start=1):
        try:
            txt = page.extract_text() or ""
        except Exception:
            txt = ""
        out.append((i, txt))
    return out
