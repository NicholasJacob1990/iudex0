import asyncio
import logging
import re
from typing import Any, Dict, List, Tuple, Optional

from app.services.url_scraper_service import url_scraper_service
from app.services.web_search_service import DEFAULT_STOPWORDS
from app.services.document_processor import DocumentChunker

try:
    from rank_bm25 import BM25Okapi
except Exception:
    BM25Okapi = None

logger = logging.getLogger("WebRAGService")

_TOKEN_RE = re.compile(r"[A-Za-zÀ-ÿ0-9]{3,}")


def _tokenize(text: str) -> List[str]:
    tokens = _TOKEN_RE.findall((text or "").lower())
    return [t for t in tokens if t not in DEFAULT_STOPWORDS]


def _score_overlap(query_tokens: List[str], doc_tokens: List[str]) -> float:
    if not query_tokens or not doc_tokens:
        return 0.0
    doc_set = set(doc_tokens)
    return float(sum(1 for t in query_tokens if t in doc_set))


def _dedupe_results(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    deduped = []
    for item in results or []:
        url = (item.get("url") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        deduped.append(item)
    return deduped


class WebRAGService:
    def __init__(self):
        self.chunker = DocumentChunker(chunk_size=500, overlap=80)

    async def _fetch_doc(self, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        url = (item.get("url") or "").strip()
        if not url:
            return None
        data = await url_scraper_service.extract_content_from_url(url)
        if not data or data.get("error"):
            return None
        content = (data.get("content") or "").strip()
        if not content or content.startswith("[PDF -"):
            return None
        return {
            "url": url,
            "title": data.get("title") or item.get("title") or url,
            "content": content,
            "snippet": data.get("metadata", {}).get("description") or item.get("snippet") or "",
            "source": item.get("source"),
            "query": item.get("query"),
        }

    async def build_web_rag_context(
        self,
        query: str,
        results: List[Dict[str, Any]],
        max_docs: int = 3,
        max_chunks: int = 6,
        max_chars: int = 6000,
        max_concurrency: int = 3,
        url_to_number: Optional[Dict[str, int]] = None,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        deduped = _dedupe_results(results)
        if not deduped:
            return "", []

        selected = deduped[:max_docs]
        sem = asyncio.Semaphore(max_concurrency)

        async def _guarded_fetch(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
            async with sem:
                return await self._fetch_doc(item)

        fetched = await asyncio.gather(*[_guarded_fetch(item) for item in selected], return_exceptions=True)
        docs: List[Dict[str, Any]] = []
        for item in fetched:
            if isinstance(item, Exception) or not item:
                continue
            docs.append(item)

        if not docs:
            return self._fallback_context(deduped, max_chars=max_chars, url_to_number=url_to_number)

        chunks: List[Dict[str, Any]] = []
        for doc in docs:
            raw = doc.get("content") or ""
            for chunk in self.chunker.chunk_by_tokens(raw, metadata={"url": doc.get("url"), "title": doc.get("title")}):
                text = (chunk.content or "").strip()
                if len(text) < 120:
                    continue
                chunks.append({
                    "url": doc.get("url"),
                    "title": doc.get("title"),
                    "text": text[:1200],
                    "source": doc.get("source"),
                    "query": doc.get("query"),
                })

        if not chunks:
            return self._fallback_context(deduped, max_chars=max_chars, url_to_number=url_to_number)

        query_tokens = _tokenize(query)
        tokenized_chunks = [_tokenize(c["text"]) for c in chunks]

        scores: List[float] = []
        if BM25Okapi and query_tokens:
            try:
                bm25 = BM25Okapi(tokenized_chunks)
                scores = list(bm25.get_scores(query_tokens))
            except Exception as exc:
                logger.warning(f"BM25 falhou, usando overlap: {exc}")
                scores = [_score_overlap(query_tokens, tokens) for tokens in tokenized_chunks]
        else:
            scores = [_score_overlap(query_tokens, tokens) for tokens in tokenized_chunks]

        ranked = []
        for chunk, score in zip(chunks, scores):
            ranked.append({**chunk, "score": float(score)})
        ranked.sort(key=lambda x: x.get("score", 0.0), reverse=True)

        lines = ["## PESQUISA WEB (trechos selecionados)"]
        selected_chunks: List[Dict[str, Any]] = []
        total_chars = len("\n".join(lines))
        per_url_count: Dict[str, int] = {}
        for chunk in ranked:
            if len(selected_chunks) >= max_chunks:
                break
            url = chunk.get("url") or ""
            if not url:
                continue
            per_url_count[url] = per_url_count.get(url, 0) + 1
            if per_url_count[url] > 2:
                continue

            title = chunk.get("title") or url
            snippet = chunk.get("text") or ""
            number = url_to_number.get(url) if url_to_number and url in url_to_number else None
            try:
                number = int(number)
            except (TypeError, ValueError):
                number = None
            if not number or number <= 0:
                number = len(selected_chunks) + 1
            entry = f"[{number}] {title} — {url}\n{snippet}\n"
            if total_chars + len(entry) > max_chars and selected_chunks:
                break
            selected_chunks.append({
                "number": number,
                "title": title,
                "url": url,
                "snippet": snippet,
                "score": chunk.get("score", 0.0),
                "source": chunk.get("source"),
                "query": chunk.get("query"),
            })
            total_chars += len(entry)

        if not selected_chunks:
            return self._fallback_context(deduped, max_chars=max_chars, url_to_number=url_to_number)

        selected_chunks.sort(key=lambda x: (x["number"], -x.get("score", 0.0)))
        citations: List[Dict[str, Any]] = []
        lines = ["## PESQUISA WEB (trechos selecionados)"]
        for chunk in selected_chunks:
            lines.append(f"[{chunk['number']}] {chunk['title']} — {chunk['url']}")
            lines.append(chunk["snippet"])
            citations.append({
                "number": chunk["number"],
                "title": chunk["title"],
                "url": chunk["url"],
                "quote": (chunk["snippet"] or "")[:300],
                "source": chunk.get("source"),
                "query": chunk.get("query"),
            })

        return "\n".join(lines).strip(), citations

    def _fallback_context(
        self,
        results: List[Dict[str, Any]],
        max_chars: int = 4000,
        url_to_number: Optional[Dict[str, int]] = None,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        lines = ["## PESQUISA WEB (resumo de fontes)"]
        citations: List[Dict[str, Any]] = []
        total_chars = len("\n".join(lines))
        for idx, res in enumerate(results[:8], start=1):
            title = res.get("title") or "Fonte"
            url = res.get("url") or ""
            snippet = res.get("snippet") or ""
            number = url_to_number.get(url) if url_to_number and url in url_to_number else None
            number = int(number) if isinstance(number, int) and number > 0 else idx
            entry = f"[{number}] {title} — {url}\n{snippet}\n"
            if total_chars + len(entry) > max_chars and citations:
                break
            lines.append(f"[{number}] {title} — {url}".strip())
            if snippet:
                lines.append(snippet.strip())
            citations.append({
                "number": number,
                "title": title,
                "url": url,
                "quote": snippet[:300],
                "source": res.get("source"),
                "query": res.get("query"),
            })
            total_chars += len(entry)

        return "\n".join(lines).strip(), citations


web_rag_service = WebRAGService()
