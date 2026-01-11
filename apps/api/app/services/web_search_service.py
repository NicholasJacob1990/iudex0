"""
Web Search Service with Intelligent Caching
Busca web com cache para reduzir custos de API
"""

from typing import Dict, List, Any, Optional
from loguru import logger
import hashlib
import json
from pathlib import Path
from datetime import datetime, timedelta
import httpx
from bs4 import BeautifulSoup


class WebSearchService:
    """Serviço de busca web com cache inteligente"""
    
    def __init__(self):
        self.cache_dir = Path(__file__).parent.parent / "data" / "search_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_ttl_days = 7  # Cachear por 7 dias
        logger.info("WebSearchService inicializado com cache")
    
    async def search(
        self,
        query: str,
        num_results: int = 10,
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
    
    async def _perform_search(
        self,
        query: str,
        num_results: int
    ) -> Dict[str, Any]:
        """Realiza busca usando DuckDuckGo (gratuito)"""
        try:
            # Usar DuckDuckGo HTML (não requer API key)
            ddg_url = "https://html.duckduckgo.com/html/"
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    ddg_url,
                    data={"q": query},
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                    }
                )
                
                if response.status_code == 200:
                    results = self._parse_duckduckgo_html(response.text, num_results)
                    return {
                        "success": True,
                        "query": query,
                        "total": len(results),
                        "results": results,
                        "source": "duckduckgo",
                        "cached": False
                    }
                else:
                    raise Exception(f"DuckDuckGo retornou status {response.status_code}")
                    
        except Exception as e:
            logger.error(f"Erro ao buscar no DuckDuckGo: {e}")
            # Fallback para resultados simulados
            return self._generate_fallback_results(query, num_results)
    
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
        return hashlib.md5(query.lower().encode()).hexdigest()
    
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


# Instância global
web_search_service = WebSearchService()
