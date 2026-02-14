"""
JusBrasil search service.

Supports:
1. Native JusBrasil API (when JUSBRASIL_API_URL + JUSBRASIL_API_KEY are configured)
2. Fallback via WebSearchService constrained to jusbrasil.com.br
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import httpx
from loguru import logger

from app.core.config import settings


def _to_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = default
    return max(minimum, min(maximum, parsed))


class JusBrasilService:
    """Client for JusBrasil search with robust fallback."""

    def __init__(
        self,
        *,
        api_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout_seconds: float = 20.0,
    ) -> None:
        self.api_url = (api_url or settings.JUSBRASIL_API_URL or "").strip().rstrip("/")
        self.api_key = (api_key or settings.JUSBRASIL_API_KEY or "").strip()
        self.timeout_seconds = float(timeout_seconds)

    async def search(
        self,
        *,
        query: str,
        tribunal: Optional[str] = None,
        tipo: Optional[str] = None,
        data_inicio: Optional[str] = None,
        data_fim: Optional[str] = None,
        max_results: int = 10,
        use_cache: bool = True,
    ) -> Dict[str, Any]:
        """
        Search legal content in JusBrasil.

        Prefers native API when configured; falls back to domain-restricted web
        search otherwise.
        """
        clean_query = str(query or "").strip()
        if not clean_query:
            return {"success": False, "error": "query is required", "results": [], "total": 0}

        limit = _to_int(max_results, default=10, minimum=1, maximum=30)
        if self.api_url and self.api_key:
            try:
                api_result = await self._search_native_api(
                    query=clean_query,
                    tribunal=tribunal,
                    tipo=tipo,
                    data_inicio=data_inicio,
                    data_fim=data_fim,
                    max_results=limit,
                )
                if api_result.get("success"):
                    return api_result
            except Exception as exc:
                logger.warning(f"JusBrasil API failed, falling back to web search: {exc}")

        fallback = await self._search_with_web_fallback(
            query=clean_query,
            tribunal=tribunal,
            tipo=tipo,
            data_inicio=data_inicio,
            data_fim=data_fim,
            max_results=limit,
            use_cache=use_cache,
        )
        fallback["used_fallback"] = True
        return fallback

    async def _search_native_api(
        self,
        *,
        query: str,
        tribunal: Optional[str],
        tipo: Optional[str],
        data_inicio: Optional[str],
        data_fim: Optional[str],
        max_results: int,
    ) -> Dict[str, Any]:
        endpoint = f"{self.api_url}/search" if not self.api_url.endswith("/search") else self.api_url
        params: Dict[str, Any] = {"query": query, "limit": max_results}
        if tribunal:
            params["tribunal"] = tribunal
        if tipo:
            params["tipo"] = tipo
        if data_inicio:
            params["data_inicio"] = data_inicio
        if data_fim:
            params["data_fim"] = data_fim

        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "X-API-Key": self.api_key,
        }

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.get(endpoint, params=params, headers=headers)
            response.raise_for_status()
            payload = response.json()

        items, total = self._normalize_response(payload, max_results)
        return {
            "success": True,
            "query": query,
            "results": items,
            "total": total,
            "source": "jusbrasil_api",
            "used_fallback": False,
        }

    async def _search_with_web_fallback(
        self,
        *,
        query: str,
        tribunal: Optional[str],
        tipo: Optional[str],
        data_inicio: Optional[str],
        data_fim: Optional[str],
        max_results: int,
        use_cache: bool,
    ) -> Dict[str, Any]:
        from app.services.web_search_service import web_search_service

        query_parts = [query]
        if tribunal:
            query_parts.append(str(tribunal))
        if tipo:
            query_parts.append(str(tipo))
        if data_inicio or data_fim:
            query_parts.append("jurisprudencia")

        query_text = " ".join(p for p in query_parts if str(p).strip())
        search_payload = await web_search_service.search(
            query=query_text,
            num_results=max_results,
            use_cache=use_cache,
            country="BR",
            domain_filter=["jusbrasil.com.br"],
            language_filter=["pt"],
        )

        raw_items = search_payload.get("results", []) if isinstance(search_payload, dict) else []
        normalized: List[Dict[str, Any]] = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or item.get("link") or "").strip()
            if "jusbrasil.com.br" not in url.lower():
                continue
            title = str(item.get("title") or "").strip()
            snippet = str(item.get("snippet") or item.get("summary") or "").strip()
            normalized.append(
                {
                    "title": title,
                    "url": url,
                    "snippet": snippet,
                    "court": self._infer_court_from_text(f"{title} {snippet}"),
                    "process_number": item.get("process_number"),
                    "date": item.get("date"),
                    "relevance_score": item.get("relevance_score") or item.get("score"),
                    "source": "jusbrasil_web",
                }
            )

        return {
            "success": True,
            "query": query,
            "results": normalized[:max_results],
            "total": len(normalized[:max_results]),
            "source": search_payload.get("source", "web_search")
            if isinstance(search_payload, dict)
            else "web_search",
        }

    def _normalize_response(
        self,
        payload: Any,
        max_results: int,
    ) -> Tuple[List[Dict[str, Any]], int]:
        if isinstance(payload, dict):
            if isinstance(payload.get("items"), list):
                raw_items = payload["items"]
            elif isinstance(payload.get("results"), list):
                raw_items = payload["results"]
            else:
                raw_items = []
            total = int(payload.get("total") or payload.get("count") or len(raw_items))
        elif isinstance(payload, list):
            raw_items = payload
            total = len(raw_items)
        else:
            raw_items = []
            total = 0

        normalized: List[Dict[str, Any]] = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or item.get("name") or item.get("headline") or "").strip()
            url = str(item.get("url") or item.get("link") or "").strip()
            snippet = str(
                item.get("snippet")
                or item.get("summary")
                or item.get("excerpt")
                or item.get("content")
                or ""
            ).strip()
            if not title and not url:
                continue
            normalized.append(
                {
                    "title": title,
                    "url": url,
                    "snippet": snippet,
                    "court": item.get("tribunal") or item.get("court") or self._infer_court_from_text(title),
                    "process_number": item.get("process_number") or item.get("processo"),
                    "date": item.get("date") or item.get("published_at"),
                    "relevance_score": item.get("score") or item.get("relevance_score"),
                    "source": "jusbrasil_api",
                }
            )

        return normalized[:max_results], min(total, max_results) if total else len(normalized[:max_results])

    @staticmethod
    def _infer_court_from_text(text: str) -> Optional[str]:
        text_upper = str(text or "").upper()
        markers = [
            "STF",
            "STJ",
            "TST",
            "TRF1",
            "TRF2",
            "TRF3",
            "TRF4",
            "TRF5",
            "TRF6",
            "TJSP",
            "TJRJ",
            "TJMG",
            "TJRS",
            "TJPR",
            "TJSC",
        ]
        for marker in markers:
            if marker in text_upper:
                return marker
        return None


jusbrasil_service = JusBrasilService()


def get_jusbrasil_service() -> JusBrasilService:
    return jusbrasil_service

