from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Iterable, Optional

from app.core.config import settings
from app.models.document import Document, DocumentType

RAG_LOCAL_EXTS = {".pdf", ".txt", ".md"}
PROMPT_INJECTION_MAX_CHARS = settings.ATTACHMENT_INJECTION_MAX_CHARS
PROMPT_INJECTION_MAX_FILES = settings.ATTACHMENT_INJECTION_MAX_FILES
UPLOAD_CACHE_MIN_BYTES = settings.UPLOAD_CACHE_MIN_BYTES
UPLOAD_CACHE_MIN_FILES = settings.UPLOAD_CACHE_MIN_FILES

_BINARY_TYPES = {
    DocumentType.IMAGE,
    DocumentType.AUDIO,
    DocumentType.VIDEO,
    DocumentType.ZIP,
}


@dataclass(frozen=True)
class DocContextStats:
    file_count: int
    total_bytes: int
    text_chars: int
    has_binary: bool
    has_missing_text: bool


@dataclass(frozen=True)
class FileContextStats:
    file_count: int
    total_bytes: int
    max_bytes: int
    has_dir: bool
    has_non_rag_ext: bool


def summarize_documents(docs: Iterable[Document]) -> DocContextStats:
    file_count = 0
    total_bytes = 0
    text_chars = 0
    has_binary = False
    has_missing_text = False

    for doc in docs:
        file_count += 1
        total_bytes += int(getattr(doc, "size", 0) or 0)
        if getattr(doc, "type", None) in _BINARY_TYPES:
            has_binary = True
        text = (getattr(doc, "extracted_text", None) or getattr(doc, "content", None) or "").strip()
        if text:
            text_chars += len(text)
        else:
            has_missing_text = True

    return DocContextStats(
        file_count=file_count,
        total_bytes=total_bytes,
        text_chars=text_chars,
        has_binary=has_binary,
        has_missing_text=has_missing_text,
    )


def summarize_context_files(paths: Iterable[str]) -> FileContextStats:
    file_count = 0
    total_bytes = 0
    max_bytes = 0
    has_dir = False
    has_non_rag_ext = False

    for raw_path in paths:
        path = str(raw_path or "").strip()
        if not path:
            continue
        if os.path.isdir(path):
            has_dir = True
            continue
        if not os.path.isfile(path):
            continue
        file_count += 1
        try:
            size = os.path.getsize(path)
        except OSError:
            size = 0
        total_bytes += size
        if size > max_bytes:
            max_bytes = size
        _, ext = os.path.splitext(path)
        if ext.lower() not in RAG_LOCAL_EXTS:
            has_non_rag_ext = True

    return FileContextStats(
        file_count=file_count,
        total_bytes=total_bytes,
        max_bytes=max_bytes,
        has_dir=has_dir,
        has_non_rag_ext=has_non_rag_ext,
    )


def supports_upload_cache(model_id: Optional[str]) -> bool:
    if not model_id:
        return False
    lowered = str(model_id).lower()
    if lowered == "internal-rag":
        return True
    return "gemini" in lowered


def decide_attachment_mode_from_docs(docs: Iterable[Document]) -> str:
    stats = summarize_documents(docs)
    if stats.file_count == 0:
        return "rag_local"
    if (
        stats.text_chars > 0
        and not stats.has_binary
        and not stats.has_missing_text
        and stats.file_count <= PROMPT_INJECTION_MAX_FILES
        and stats.text_chars <= PROMPT_INJECTION_MAX_CHARS
    ):
        return "prompt_injection"
    return "rag_local"


def decide_context_mode_from_paths(paths: Iterable[str], model_id: Optional[str]) -> str:
    stats = summarize_context_files(paths)
    if stats.has_dir:
        return "rag_local"
    if stats.file_count == 0:
        return "rag_local"
    if not supports_upload_cache(model_id):
        return "rag_local"
    if (
        stats.total_bytes >= UPLOAD_CACHE_MIN_BYTES
        or stats.file_count >= UPLOAD_CACHE_MIN_FILES
        or stats.has_non_rag_ext
    ):
        return "upload_cache"
    return "rag_local"
