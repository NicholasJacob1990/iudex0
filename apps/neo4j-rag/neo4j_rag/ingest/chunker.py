"""
Legal-aware document chunking.

Respects the normative chain principle:
- Articles (Art.) are atomic units — never split between Art and its §§/incisos
- If an article exceeds chunk_size, split at §/inciso boundaries but prepend caput
- Document-type-aware separators and chunk sizes
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import List, Optional, Tuple

from ..config import settings
from ..models import Chunk, DocumentType

# ─── Separators by document type ──────────────────────────────────

SEPARATORS_LEGISLACAO = [
    "\nCAPÍTULO", "\nTÍTULO", "\nLIVRO",
    "\nSeção", "\nSubseção",
    "\nArt.",
    "\n\n", "\n", ". ", " ",
]

SEPARATORS_JURISPRUDENCIA = [
    "\nEMENTA", "\nACÓRDÃO", "\nRELATÓRIO",
    "\nVOTO", "\nDISPOSITIVO",
    "\n\n", "\n", ". ", " ",
]

SEPARATORS_DEFAULT = ["\n\n", "\n", ". ", " "]

_RE_ARTIGO_START = re.compile(r"^\s*Art\.\s*\d+", re.MULTILINE)
_RE_PARAGRAFO = re.compile(r"\n\s*(?:§\s*\d+|Parágrafo único)", re.MULTILINE)


def _get_separators(doc_type: DocumentType) -> List[str]:
    if doc_type == DocumentType.LEGISLACAO:
        return SEPARATORS_LEGISLACAO
    elif doc_type == DocumentType.JURISPRUDENCIA:
        return SEPARATORS_JURISPRUDENCIA
    return SEPARATORS_DEFAULT


def _make_chunk_id(doc_id: str, position: int) -> str:
    raw = f"{doc_id}:{position}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _split_by_separators(
    text: str,
    separators: List[str],
    chunk_size: int,
    overlap: int,
) -> List[str]:
    """Recursive character text splitter with hierarchical separators."""
    if len(text) <= chunk_size:
        return [text] if text.strip() else []

    # Find the best separator for this level
    sep = separators[0] if separators else " "
    remaining_seps = separators[1:] if len(separators) > 1 else [" "]

    parts = text.split(sep)
    if len(parts) == 1 and remaining_seps:
        return _split_by_separators(text, remaining_seps, chunk_size, overlap)

    chunks = []
    current = ""
    for part in parts:
        candidate = (current + sep + part) if current else part
        if len(candidate) > chunk_size and current:
            chunks.append(current.strip())
            # Overlap: keep tail of previous chunk
            if overlap > 0 and len(current) > overlap:
                current = current[-overlap:] + sep + part
            else:
                current = part
        else:
            current = candidate

    if current.strip():
        chunks.append(current.strip())

    # Recursively split any chunks that are still too large
    result = []
    for c in chunks:
        if len(c) > chunk_size and remaining_seps:
            result.extend(_split_by_separators(c, remaining_seps, chunk_size, overlap))
        else:
            result.append(c)

    return result


def _extract_caput(artigo_text: str) -> str:
    """Extract the caput (first sentence/paragraph) of an article."""
    lines = artigo_text.strip().split("\n")
    caput_lines = []
    for line in lines:
        if _RE_PARAGRAFO.match("\n" + line) and caput_lines:
            break
        caput_lines.append(line)
        if len("\n".join(caput_lines)) > 300:
            break
    return "\n".join(caput_lines)


def _chunk_long_artigo(
    artigo_text: str,
    fonte_normativa: str,
    artigo_id: str,
    chunk_size: int,
) -> List[str]:
    """Split a long article at §/inciso boundaries, prepending caput to each chunk."""
    caput = _extract_caput(artigo_text)
    header = f"[{artigo_id} da {fonte_normativa}]\n{caput}\n[...continuação...]\n"

    parts = _RE_PARAGRAFO.split(artigo_text)
    if len(parts) <= 1:
        # Can't split further, just chunk normally
        return _split_by_separators(artigo_text, SEPARATORS_DEFAULT, chunk_size, 0)

    chunks = []
    current = header
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if len(current) + len(p) + 1 > chunk_size and current != header:
            chunks.append(current)
            current = header
        current += p + "\n"

    if current.strip() and current != header:
        chunks.append(current)

    return chunks


def chunk_document(
    text: str,
    doc_id: str,
    doc_type: DocumentType,
    *,
    chunk_size: Optional[int] = None,
    overlap: Optional[int] = None,
) -> List[Chunk]:
    """
    Chunk a document respecting legal structure.

    Returns a list of Chunk objects with position and hierarchy.
    """
    chunk_size = chunk_size or settings.chunk_size
    overlap = overlap or settings.chunk_overlap
    separators = _get_separators(doc_type)

    # For questões, keep entire document as single chunk
    if doc_type == DocumentType.QUESTAO and len(text) <= chunk_size * 2:
        return [Chunk(
            id=_make_chunk_id(doc_id, 0),
            text=text.strip(),
            doc_id=doc_id,
            position=0,
            hierarchy=["questao_completa"],
        )]

    raw_chunks = _split_by_separators(text, separators, chunk_size, overlap)

    chunks = []
    for i, raw in enumerate(raw_chunks):
        if not raw.strip():
            continue
        chunks.append(Chunk(
            id=_make_chunk_id(doc_id, i),
            text=raw.strip(),
            doc_id=doc_id,
            position=i,
        ))

    return chunks


def extract_text_from_file(path: Path) -> Tuple[str, DocumentType]:
    """Extract text from PDF or DOCX and infer document type.

    Note: .doc (legacy Word) is NOT supported — only .docx.
    """
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        import fitz
        doc = fitz.open(str(path))
        text = "\n".join(page.get_text() for page in doc)
        doc.close()
    elif suffix == ".docx":
        from docx import Document as DocxDocument
        doc = DocxDocument(str(path))
        text = "\n".join(p.text for p in doc.paragraphs)
    elif suffix == ".doc":
        raise ValueError(
            f"Legacy .doc format not supported: {path.name}. "
            "Convert to .docx first (e.g. with LibreOffice: "
            "libreoffice --headless --convert-to docx file.doc)"
        )
    else:
        text = path.read_text(encoding="utf-8", errors="replace")

    doc_type = _infer_document_type(text, path.name)
    return text, doc_type


def _infer_document_type(text: str, filename: str) -> DocumentType:
    """Infer document type from content and filename."""
    lower_name = filename.lower()
    lower_text = text[:2000].lower()

    if any(w in lower_name for w in ("questao", "questões", "prova", "gabarito")):
        return DocumentType.QUESTAO
    if any(w in lower_name for w in ("transcri", "aula")):
        return DocumentType.TRANSCRICAO
    if any(w in lower_text for w in ("ementa:", "acórdão", "relatório", "voto")):
        return DocumentType.JURISPRUDENCIA
    if _RE_ARTIGO_START.search(text[:5000]):
        return DocumentType.LEGISLACAO
    return DocumentType.APOSTILA
