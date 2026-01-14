from __future__ import annotations

from typing import Any, List, Tuple

from .base import Source, stable_numbering


def _get(obj: Any, key: str, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def openai_extract_perplexity(resp: Any) -> tuple[str, List[Source]]:
    """
    Espera o shape do Responses API: resp.output -> message -> content(output_text) -> annotations(url_citation).
    """
    output = _get(resp, "output", []) or []
    msg = next((o for o in output if _get(o, "type") == "message"), None)
    if not msg:
        return (_get(resp, "output_text", "") or ""), []

    content = _get(msg, "content", []) or []
    out_text = next((c for c in content if _get(c, "type") == "output_text"), None)
    if not out_text:
        return (_get(resp, "output_text", "") or ""), []

    text = _get(out_text, "text", "") or ""
    ann = _get(out_text, "annotations", []) or []
    cites = [a for a in ann if _get(a, "type") == "url_citation"]

    cites_sorted = sorted(cites, key=lambda a: _get(a, "start_index", 10**18))
    url_title_stream: List[Tuple[str, str]] = [
        (_get(a, "url", ""), _get(a, "title", "")) for a in cites_sorted
    ]
    url_to_n, sources = stable_numbering(url_title_stream)

    for a in sorted(cites, key=lambda x: _get(x, "end_index", -1), reverse=True):
        url = _get(a, "url", "")
        if not url:
            continue
        end_i = _get(a, "end_index", None)
        if end_i is None:
            continue
        n = url_to_n.get(url)
        if n:
            text = text[:end_i] + f" [{n}]" + text[end_i:]

    return text, sources
