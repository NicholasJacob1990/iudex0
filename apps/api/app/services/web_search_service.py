"""
Web Search Service with Intelligent Caching
Busca web com cache para reduzir custos de API
"""

from typing import Dict, List, Any, Optional, Iterable
from loguru import logger
import asyncio
import hashlib
import json
import os
from pathlib import Path
from datetime import datetime, timedelta
import httpx
from bs4 import BeautifulSoup
import re


class WebSearchService:
    """Serviço de busca web com cache inteligente"""
    
    def __init__(self):
        self.cache_dir = Path(__file__).parent.parent / "data" / "search_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_ttl_days = 7  # Cachear por 7 dias
        self.primary_locale = {
            "gl": os.getenv("WEB_SEARCH_PRIMARY_GL", "br"),
            "hl": os.getenv("WEB_SEARCH_PRIMARY_HL", "pt"),
            "ddg_kl": os.getenv("WEB_SEARCH_PRIMARY_DDG_KL", "br-pt"),
        }
        self.secondary_locale = {
            "gl": os.getenv("WEB_SEARCH_SECONDARY_GL", "us"),
            "hl": os.getenv("WEB_SEARCH_SECONDARY_HL", "en"),
            "ddg_kl": os.getenv("WEB_SEARCH_SECONDARY_DDG_KL", "wt-wt"),
        }
        self.secondary_enabled = os.getenv("WEB_SEARCH_SECONDARY_ENABLED", "1") != "0"
        try:
            self.secondary_ratio = float(os.getenv("WEB_SEARCH_SECONDARY_RATIO", "0.3"))
        except ValueError:
            self.secondary_ratio = 0.3
        self.secondary_ratio = max(0.0, min(self.secondary_ratio, 0.8))
        logger.info("WebSearchService inicializado com cache")
    
    async def search(
        self,
        query: str,
        num_results: int = 10,
        max_results: Optional[int] = None,
        use_cache: bool = True
    ) -> Dict[str, Any]:
        """
        Busca web com cache inteligente
        
        Args:
            query: Termo de busca
            num_results: Número de resultados
            use_cache: Usar cache se disponível
            
        Returns:
            Dicionário com resultados
        """
        if max_results is not None:
            num_results = max_results
        logger.info(f"Buscando na web: '{query}'")
        
        # Verificar cache primeiro
        if use_cache:
            cached_result = self._get_from_cache(query)
            if cached_result:
                logger.info(f"Resultado encontrado no cache para '{query}'")
                return cached_result
        
        # Realizar busca real
        try:
            results = await self._perform_search(query, num_results)
            
            # Salvar no cache
            if use_cache:
                self._save_to_cache(query, results)
            
            return results
            
        except Exception as e:
            logger.error(f"Erro na busca web: {e}")
            return {
                "success": False,
                "query": query,
                "results": [],
                "error": str(e)
            }

    async def search_multi(
        self,
        query: str,
        num_results: int = 10,
        max_queries: int = 4,
        use_cache: bool = True
    ) -> Dict[str, Any]:
        """Busca web com múltiplas variações de query (multi-query RAG)."""
        queries = plan_queries(query, max_queries=max_queries)
        if not queries:
            return await self.search(query, num_results=num_results, use_cache=use_cache)

        per_query = max(3, int(num_results / max(1, len(queries))))
        tasks = [
            self.search(q, num_results=per_query, use_cache=use_cache)
            for q in queries
        ]

        results: List[Dict[str, Any]] = []
        cached_all = True
        for payload in await asyncio.gather(*tasks, return_exceptions=True):
            if isinstance(payload, Exception):
                logger.error(f"Erro multi-query: {payload}")
                cached_all = False
                continue
            if not payload.get("cached"):
                cached_all = False
            for item in payload.get("results", []) or []:
                results.append({**item, "query": payload.get("query")})

        deduped = _dedupe_results(results)
        source_candidates = {item.get("source") for item in deduped if item.get("source")}
        source = "serper-multi" if "serper" in source_candidates else "duckduckgo-multi"
        return {
            "success": True,
            "query": query,
            "queries": queries,
            "total": len(deduped),
            "results": deduped[:num_results],
            "source": source,
            "cached": cached_all,
        }
    
    async def _perform_search(
        self,
        query: str,
        num_results: int
    ) -> Dict[str, Any]:
        """Realiza busca usando Serper (se configurado) com fallback no DuckDuckGo."""
        serper_key = os.getenv("SERPER_API_KEY")
        if serper_key:
            try:
                return await self._perform_serper_search(query, num_results, serper_key)
            except Exception as e:
                logger.error(f"Erro ao buscar no Serper: {e}. Fazendo fallback no DuckDuckGo.")

        try:
            return await self._perform_duckduckgo_search(query, num_results)
        except Exception as e:
            logger.error(f"Erro ao buscar no DuckDuckGo: {e}")
            # Fallback para resultados simulados
            return self._generate_fallback_results(query, num_results)

    def _merge_locale_results(
        self,
        primary: List[Dict[str, Any]],
        secondary: List[Dict[str, Any]],
        limit: int
    ) -> List[Dict[str, Any]]:
        primary_deduped = _dedupe_results(primary)
        if not self.secondary_enabled or not secondary:
            return primary_deduped[:limit]

        secondary_deduped = _dedupe_results(secondary)
        secondary_quota = max(2, int(limit * self.secondary_ratio))
        if limit <= 1:
            secondary_quota = 0
        secondary_quota = min(secondary_quota, max(0, limit - 1))
        primary_quota = max(1, limit - secondary_quota) if limit > 0 else 0

        merged = primary_deduped[:primary_quota]
        seen = {item.get("url") for item in merged if item.get("url")}

        for item in secondary_deduped:
            if len(merged) >= limit:
                break
            url = item.get("url")
            if not url or url in seen:
                continue
            merged.append(item)
            seen.add(url)

        if len(merged) < limit:
            for item in primary_deduped[primary_quota:]:
                if len(merged) >= limit:
                    break
                url = item.get("url")
                if not url or url in seen:
                    continue
                merged.append(item)
                seen.add(url)

        return merged[:limit]

    async def _serper_request(
        self,
        query: str,
        num_results: int,
        api_key: str,
        gl: str,
        hl: str
    ) -> List[Dict[str, Any]]:
        serper_url = "https://google.serper.dev/search"
        payload = {"q": query, "num": num_results, "gl": gl, "hl": hl}

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                serper_url,
                json=payload,
                headers={
                    "X-API-KEY": api_key,
                    "Content-Type": "application/json",
                },
            )

        if response.status_code != 200:
            raise Exception(f"Serper retornou status {response.status_code}")

        data = response.json()
        results = []
        for item in data.get("organic", []) or []:
            results.append({
                "title": item.get("title", ""),
                "url": item.get("link", ""),
                "snippet": item.get("snippet", ""),
                "source": "serper",
            })
        return results

    async def _perform_serper_search(
        self,
        query: str,
        num_results: int,
        api_key: str
    ) -> Dict[str, Any]:
        """Realiza busca usando Serper (Google Search API)."""
        tasks = [
            self._serper_request(
                query,
                num_results,
                api_key,
                gl=self.primary_locale["gl"],
                hl=self.primary_locale["hl"],
            )
        ]
        if self.secondary_enabled:
            tasks.append(
                self._serper_request(
                    query,
                    num_results,
                    api_key,
                    gl=self.secondary_locale["gl"],
                    hl=self.secondary_locale["hl"],
                )
            )

        results_list = await asyncio.gather(*tasks)
        primary = results_list[0] if results_list else []
        secondary = results_list[1] if len(results_list) > 1 else []

        results = self._merge_locale_results(primary, secondary, num_results)
        return {
            "success": True,
            "query": query,
            "total": len(results),
            "results": results[:num_results],
            "source": "serper",
            "cached": False,
        }

    async def _duckduckgo_request(
        self,
        query: str,
        num_results: int,
        kl: str
    ) -> List[Dict[str, Any]]:
        ddg_url = "https://html.duckduckgo.com/html/"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                ddg_url,
                data={"q": query, "kl": kl},
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                }
            )

        if response.status_code != 200:
            raise Exception(f"DuckDuckGo retornou status {response.status_code}")

        return self._parse_duckduckgo_html(response.text, num_results)

    async def _perform_duckduckgo_search(
        self,
        query: str,
        num_results: int
    ) -> Dict[str, Any]:
        """Realiza busca usando DuckDuckGo HTML (gratuito)."""
        tasks = [
            self._duckduckgo_request(
                query,
                num_results,
                kl=self.primary_locale["ddg_kl"],
            )
        ]
        if self.secondary_enabled:
            tasks.append(
                self._duckduckgo_request(
                    query,
                    num_results,
                    kl=self.secondary_locale["ddg_kl"],
                )
            )

        results_list = await asyncio.gather(*tasks)
        primary = results_list[0] if results_list else []
        secondary = results_list[1] if len(results_list) > 1 else []

        results = self._merge_locale_results(primary, secondary, num_results)
        return {
            "success": True,
            "query": query,
            "total": len(results),
            "results": results,
            "source": "duckduckgo",
            "cached": False
        }
    
    def _parse_duckduckgo_html(self, html: str, limit: int) -> List[Dict[str, Any]]:
        """Parse do HTML do DuckDuckGo"""
        try:
            soup = BeautifulSoup(html, 'html.parser')
            results = []
            
            for result_div in soup.find_all('div', class_='result'):
                if len(results) >= limit:
                    break
                
                title_elem = result_div.find('a', class_='result__a')
                if not title_elem:
                    continue
                
                title = title_elem.get_text(strip=True)
                url = title_elem.get('href', '')
                
                snippet_elem = result_div.find('a', class_='result__snippet')
                snippet = snippet_elem.get_text(strip=True) if snippet_elem else ""
                
                results.append({
                    "title": title,
                    "url": url,
                    "snippet": snippet,
                    "source": "duckduckgo"
                })
            
            return results
            
        except Exception as e:
            logger.error(f"Erro ao parsear resultados do DuckDuckGo: {e}")
            return []
    
    def _generate_fallback_results(self, query: str, num_results: int) -> Dict[str, Any]:
        """Gera resultados de fallback quando busca real falha"""
        logger.warning("Usando resultados de fallback")
        
        results = [
            {
                "title": f"Resultado {i+1} para '{query}'",
                "url": f"https://exemplo.com/resultado-{i+1}",
                "snippet": f"Resultado de demonstração para '{query}'.",
                "source": "fallback"
            }
            for i in range(min(5, num_results))
        ]
        
        return {
            "success": True,
            "query": query,
            "total": len(results),
            "results": results,
            "source": "fallback",
            "cached": False
        }
    
    def _get_cache_key(self, query: str) -> str:
        """Gera chave de cache para query"""
        strategy = "|".join([
            self.primary_locale["gl"],
            self.primary_locale["hl"],
            self.primary_locale["ddg_kl"],
            self.secondary_locale["gl"],
            self.secondary_locale["hl"],
            self.secondary_locale["ddg_kl"],
            "secondary" if self.secondary_enabled else "primary",
            f"{self.secondary_ratio:.2f}",
        ])
        return hashlib.md5(f"{query.lower()}|{strategy}".encode()).hexdigest()
    
    def _get_cache_path(self, query: str) -> Path:
        """Retorna caminho do arquivo de cache"""
        cache_key = self._get_cache_key(query)
        return self.cache_dir / f"{cache_key}.json"
    
    def _get_from_cache(self, query: str) -> Optional[Dict[str, Any]]:
        """Busca resultado no cache"""
        try:
            cache_path = self._get_cache_path(query)
            
            if not cache_path.exists():
                return None
            
            with open(cache_path, 'r', encoding='utf-8') as f:
                cached_data = json.load(f)
            
            cached_time = datetime.fromisoformat(cached_data.get("cached_at"))
            if datetime.now() - cached_time > timedelta(days=self.cache_ttl_days):
                logger.info(f"Cache expirado para '{query}'")
                cache_path.unlink()
                return None
            
            cached_data["cached"] = True
            return cached_data
            
        except Exception as e:
            logger.error(f"Erro ao ler cache: {e}")
            return None
    
    def _save_to_cache(self, query: str, results: Dict[str, Any]):
        """Salva resultado no cache"""
        try:
            cache_path = self._get_cache_path(query)
            
            cache_data = {
                **results,
                "cached_at": datetime.now().isoformat()
            }
            
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"Resultado salvo no cache: {cache_path}")
            
        except Exception as e:
            logger.error(f"Erro ao salvar cache: {e}")
    
    def clear_cache(self, older_than_days: Optional[int] = None):
        """Limpa cache antigo"""
        try:
            count = 0
            for cache_file in self.cache_dir.glob("*.json"):
                if older_than_days:
                    file_time = datetime.fromtimestamp(cache_file.stat().st_mtime)
                    if datetime.now() - file_time > timedelta(days=older_than_days):
                        cache_file.unlink()
                        count += 1
                else:
                    cache_file.unlink()
                    count += 1
            
            logger.info(f"Cache limpo: {count} arquivos removidos")
            return count
            
        except Exception as e:
            logger.error(f"Erro ao limpar cache: {e}")
            return 0


DEFAULT_STOPWORDS = {
    "a", "o", "os", "as", "de", "do", "da", "dos", "das", "e", "ou", "em", "no", "na",
    "nos", "nas", "um", "uma", "uns", "umas", "por", "para", "com", "sem", "que", "se",
    "sobre", "como", "mais", "menos", "muito", "muitos", "muita", "muitas", "já", "não",
    "sim", "ao", "aos", "à", "às", "lhe", "lhes", "seu", "sua", "seus", "suas", "isso",
    "isto", "aquilo", "entre", "também", "até", "ser", "estar", "ter", "faz", "fez",
    "the", "an", "of", "and", "or", "in", "on", "for", "with", "to", "from", "by",
    "is", "are", "was", "were", "be", "been", "being", "as", "at", "it", "its",
}

DEFAULT_BREADTH_KEYWORDS = (
    "liste", "listar", "mapeie", "mapeamento", "panorama", "overview", "comparar",
    "comparação", "contrapontos", "tendências", "tendencia", "mapa", "fontes",
    "jurisprudência", "jurisprudencia", "doutrina", "legislação", "legislacao",
    "levantamento", "conjunto", "todas", "todos", "abrangente",
)


def _dedupe_results(items: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    deduped = []
    for item in items:
        url = (item.get("url") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        deduped.append(item)
    return deduped


def plan_queries(query: str, max_queries: int = 4) -> List[str]:
    """Generate simple query variations to improve recall."""
    query = (query or "").strip()
    if not query:
        return []

    tokens = re.findall(r"[a-zA-ZÀ-ÿ0-9_-]{3,}", query.lower())
    keywords = [t for t in tokens if t not in DEFAULT_STOPWORDS]
    keywords = list(dict.fromkeys(keywords))

    queries = [query]
    year = datetime.now().year
    if len(query) > 20:
        queries.append(f"{query} {year}")

    if keywords:
        top = " ".join(keywords[:4])
        if top and top not in query.lower():
            queries.append(f"{top} {year}")

    if any(k in query.lower() for k in ("lei", "juris", "doutrin")):
        queries.append(f"{query} jurisprudência")
        queries.append(f"{query} doutrina")
    else:
        queries.append(f"{query} resumo")

    unique = []
    seen = set()
    for q in queries:
        qn = q.strip()
        if not qn or qn in seen:
            continue
        seen.add(qn)
        unique.append(qn)
        if len(unique) >= max_queries:
            break
    return unique


def is_breadth_first(query: str) -> bool:
    if not query:
        return False
    ql = query.lower()
    if ql.count("?") > 1:
        return True
    if len(query) > 160 or len(query.split()) > 18:
        return True
    if any(k in ql for k in DEFAULT_BREADTH_KEYWORDS):
        return True
    return False


def build_web_context(payload: Dict[str, Any], max_items: int = 8) -> str:
    """Format web search payload into a numbered evidence block."""
    results = (payload or {}).get("results") or []
    if not results:
        return ""

    lines = ["## PESQUISA WEB (fontes numeradas)"]
    for idx, res in enumerate(results[:max_items], start=1):
        title = res.get("title") or "Fonte"
        url = res.get("url") or ""
        snippet = res.get("snippet") or ""
        lines.append(f"[{idx}] {title} — {url}".strip())
        if snippet:
            lines.append(snippet.strip())
    return "\n".join(lines)


# Instância global
web_search_service = WebSearchService()
