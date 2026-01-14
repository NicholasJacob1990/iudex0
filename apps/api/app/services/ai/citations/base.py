from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple


@dataclass(frozen=True)
class Source:
    n: int
    title: str
    url: str


def stable_numbering(items: Iterable[Tuple[str, str]]) -> Tuple[Dict[str, int], List[Source]]:
    """
    items: iterable of (url, title) in first-appearance order
    """
    url_to_n: Dict[str, int] = {}
    sources: List[Source] = []
    for url, title in items:
        if not url:
            continue
        if url not in url_to_n:
            url_to_n[url] = len(url_to_n) + 1
            sources.append(Source(n=url_to_n[url], title=title or url, url=url))
    return url_to_n, sources


def render_perplexity(text: str, sources: List[Source]) -> str:
    footer = "\n\nFontes:\n" + "\n".join(
        [f"[{s.n}] {s.title} — {s.url}" for s in sources]
    )
    return (text or "").rstrip() + footer
