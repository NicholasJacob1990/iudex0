"""Utilities for large-document chunking and multi-pass preprocessing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List
import math
import re


@dataclass(frozen=True)
class TextChunk:
    """Represents a contiguous document chunk."""

    index: int
    text: str
    start_char: int
    end_char: int


def estimate_pages(text: str, *, chars_per_page: int = 4000) -> int:
    """Best-effort page estimate based on character count."""

    if not text:
        return 0
    safe_cpp = max(500, int(chars_per_page or 4000))
    return max(1, int(math.ceil(len(text) / float(safe_cpp))))


def classify_document_route(pages: int) -> str:
    """Classifies routing mode using the same thresholds as orchestration router."""

    pages = int(pages or 0)
    if pages <= 0:
        return "default"
    if pages <= 100:
        return "direct"
    if pages <= 500:
        return "rag_enhanced"
    if pages <= 2000:
        return "chunked_rag"
    return "multi_pass"


def split_text_for_multi_pass(
    text: str,
    *,
    max_chunk_chars: int = 24000,
    overlap_chars: int = 800,
    max_chunks: int = 64,
) -> List[TextChunk]:
    """Splits text into overlapping chunks with paragraph/sentence boundary preference."""

    raw = (text or "").strip()
    if not raw:
        return []

    chunk_limit = max(4000, int(max_chunk_chars or 24000))
    overlap = max(0, min(chunk_limit // 3, int(overlap_chars or 0)))
    cap = max(1, int(max_chunks or 64))

    chunks: List[TextChunk] = []
    start = 0
    idx = 0
    text_len = len(raw)

    while start < text_len and idx < cap:
        end = min(text_len, start + chunk_limit)

        if end < text_len:
            paragraph_break = raw.rfind("\n\n", max(start + 1, end - 1200), min(text_len, end + 1200))
            if paragraph_break > start:
                end = paragraph_break
            else:
                sentence_break = raw.rfind(". ", max(start + 1, end - 500), min(text_len, end + 500))
                if sentence_break > start:
                    end = sentence_break + 1

        chunk_text = raw[start:end].strip()
        if not chunk_text:
            break

        chunks.append(TextChunk(index=idx, text=chunk_text, start_char=start, end_char=end))
        idx += 1

        if end >= text_len:
            break

        next_start = max(start + 1, end - overlap)
        if next_start <= start:
            next_start = end
        start = next_start

    if start < text_len and chunks:
        last = chunks[-1]
        merged_tail = (last.text + "\n\n" + raw[start:]).strip()
        chunks[-1] = TextChunk(
            index=last.index,
            text=merged_tail,
            start_char=last.start_char,
            end_char=text_len,
        )

    return chunks


def build_chunk_summary_prompt(chunk_text: str, chunk_index: int, total_chunks: int) -> str:
    """Prompt used to summarize one chunk before synthesis."""

    return (
        "# ROLE\n"
        "Você é um analista jurídico especializado em compressão factual.\n\n"
        "# TASK\n"
        f"Resuma o bloco {chunk_index}/{total_chunks} mantendo apenas fatos, pedidos, fundamentos e riscos.\n"
        "Não invente dados. Preserve números de processo, datas, valores e nomes quando existirem.\n\n"
        "# OUTPUT\n"
        "- Use bullets curtos\n"
        "- Máximo de 220 palavras\n"
        "- Sem markdown extra além dos bullets\n\n"
        "# BLOCO\n"
        f"{chunk_text[:90000]}"
    )


def merge_chunk_summaries(summaries: List[str], *, max_chars: int = 48000) -> str:
    """Merges chunk summaries into a single compact context."""

    cleaned = [re.sub(r"\s+", " ", (s or "")).strip() for s in summaries if str(s or "").strip()]
    if not cleaned:
        return ""

    merged = "\n\n".join(f"[Chunk {i + 1}] {item}" for i, item in enumerate(cleaned))
    if len(merged) <= max_chars:
        return merged

    safe_max = max(4000, int(max_chars or 48000))
    return merged[:safe_max].rsplit(" ", 1)[0].strip()
