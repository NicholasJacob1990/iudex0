from __future__ import annotations

from typing import Any, List, Tuple

from .base import Source, stable_numbering


def _get(obj: Any, key: str, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def gemini_extract_perplexity(resp: Any) -> tuple[str, List[Source]]:
    """
    resp: retorno do generate_content com grounding habilitado.
    """
    text = _get(resp, "text", None)
    if not text:
        cands = _get(resp, "candidates", []) or []
        if cands:
            content = _get(cands[0], "content", None)
            parts = _get(content, "parts", []) or []
            text = _get(parts[0], "text", "") if parts else ""
        else:
            text = ""

    cands = _get(resp, "candidates", []) or []
    if not cands:
        return text or "", []

    md = _get(cands[0], "grounding_metadata", None)
    if not md:
        return text or "", []

    supports = _get(md, "grounding_supports", []) or _get(md, "groundingSupports", []) or []
    chunks = _get(md, "grounding_chunks", []) or _get(md, "groundingChunks", []) or []

    url_title_stream: List[Tuple[str, str]] = []
    for s in supports:
        idxs = _get(s, "grounding_chunk_indices", None) or _get(s, "groundingChunkIndices", []) or []
        for i in idxs:
            if i < 0 or i >= len(chunks):
                continue
            web = _get(chunks[i], "web", None) or {}
            url = _get(web, "uri", "")
            title = _get(web, "title", "")
            url_title_stream.append((url, title))

    url_to_n, sources = stable_numbering(url_title_stream)

    def _end_index(s):
        seg = _get(s, "segment", None) or {}
        return _get(seg, "end_index", None) or _get(seg, "endIndex", -1)

    for s in sorted(supports, key=_end_index, reverse=True):
        seg = _get(s, "segment", None) or {}
        end_i = _get(seg, "end_index", None) or _get(seg, "endIndex", None)
        if end_i is None:
            continue

        idxs = _get(s, "grounding_chunk_indices", None) or _get(s, "groundingChunkIndices", []) or []
        nums = []
        for i in idxs:
            if i < 0 or i >= len(chunks):
                continue
            web = _get(chunks[i], "web", None) or {}
            url = _get(web, "uri", "")
            n = url_to_n.get(url)
            if n:
                nums.append(n)

        if nums:
            cit = " " + "".join([f"[{n}]" for n in sorted(set(nums))])
            text = (text or "")[:end_i] + cit + (text or "")[end_i:]

    return (text or ""), sources
