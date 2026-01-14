from __future__ import annotations

from typing import Any, List, Tuple

from .base import Source, stable_numbering


def _get(obj: Any, key: str, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def claude_extract_perplexity(resp: Any) -> tuple[str, List[Source]]:
    """
    resp: retorno do messages.create (Anthropic). Considera que as citações venham em blocos type='text' com .citations.
    """
    content = _get(resp, "content", []) or []
    url_title_stream: List[Tuple[str, str]] = []

    for block in content:
        if _get(block, "type") != "text":
            continue
        citations = _get(block, "citations", []) or []
        for c in citations:
            url_title_stream.append((_get(c, "url", ""), _get(c, "title", "")))

    url_to_n, sources = stable_numbering(url_title_stream)

    parts: List[str] = []
    for block in content:
        if _get(block, "type") != "text":
            continue
        txt = _get(block, "text", "") or ""
        citations = _get(block, "citations", []) or []
        nums = []
        for c in citations:
            url = _get(c, "url", "")
            n = url_to_n.get(url)
            if n:
                nums.append(n)
        if nums:
            txt = txt.rstrip() + " " + "".join([f"[{n}]" for n in sorted(set(nums))])
        parts.append(txt)

    return "\n".join([p for p in parts if p]).strip(), sources
