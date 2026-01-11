"""
Jurisprudence Search Service
Busca em base local de precedentes jurídicos brasileiros
"""

from typing import Dict, List, Any, Optional
from loguru import logger
import json
from pathlib import Path


class JurisprudenceService:
    """Serviço de busca de jurisprudência em base local"""
    
    def __init__(self):
        self.database_path = Path(__file__).parent.parent / "data" / "jurisprudence_database.json"
        self.precedents: List[Dict[str, Any]] = []
        self._load_database()
        logger.info(f"JurisprudenceService inicializado com {len(self.precedents)} precedentes")
    
    def _load_database(self):
        """Carrega base de dados de precedentes"""
        try:
            if self.database_path.exists():
                with open(self.database_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.precedents = data.get("precedents", [])
                    logger.info(f"Base de jurisprudência carregada: {len(self.precedents)} precedentes")
            else:
                logger.warning(f"Base de dados não encontrada: {self.database_path}")
                self.precedents = []
        except Exception as e:
            logger.error(f"Erro ao carregar base de jurisprudência: {e}")
            self.precedents = []
    
    async def search(
        self,
        query: str,
        court: Optional[str] = None,
        tema: Optional[str] = None,
        limit: int = 10
    ) -> Dict[str, Any]:
        """
        Busca precedentes na base local
        
        Args:
            query: Termo de busca
            court: Filtrar por tribunal (STF, STJ, TST, etc)
            tema: Filtrar por tema
            limit: Número máximo de resultados
            
        Returns:
            Dicionário com resultados da busca
        """
        logger.info(f"Buscando jurisprudência: '{query}' (court={court}, tema={tema})")
        
        try:
            query_lower = query.lower()
            results = []
            
            for precedent in self.precedents:
                score = self._calculate_relevance(precedent, query_lower, court, tema)
                
                if score > 0:
                    results.append({
                        **precedent,
                        "relevance_score": score
                    })
            
            # Ordenar por relevância
            results.sort(key=lambda x: x["relevance_score"], reverse=True)
            results = results[:limit]
            
            # Formatar para compatibilidade com frontend existente
            items = [
                {
                    "id": p.get("id"),
                    "court": p.get("tribunal"),
                    "title": f"{p.get('tipo')} {p.get('numero')}",
                    "summary": p.get("ementa", "")[:300] + "...",
                    "date": p.get("data"),
                    "tags": p.get("tags", []),
                    "processNumber": p.get("numero"),
                    "tema": p.get("tema"),
                    "relator": p.get("relator"),
                    "decisao": p.get("decisao"),
                    "url": p.get("url"),
                    "source": "local_database",
                    "relevance_score": p.get("relevance_score", 0)
                }
                for p in results
            ]
            
            return {
                "items": items,
                "total": len(items),
                "query": query,
                "court": court
            }
            
        except Exception as e:
            logger.error(f"Erro na busca de jurisprudência: {e}")
            return {
                "items": [],
                "total": 0,
                "query": query,
                "error": str(e)
            }
    
    def _calculate_relevance(
        self,
        precedent: Dict[str, Any],
        query: str,
        court: Optional[str],
        tema: Optional[str]
    ) -> float:
        """Calcula score de relevância do precedente"""
        score = 0.0
        
        # Filtros obrigatórios
        if court and precedent.get("tribunal", "").upper() != court.upper():
            return 0.0
        
        if tema and tema.lower() not in precedent.get("tema", "").lower():
            return 0.0
        
        # Busca no texto
        searchable_text = " ".join([
            precedent.get("ementa", ""),
            precedent.get("tema", ""),
            precedent.get("numero", ""),
            " ".join(precedent.get("tags", []))
        ]).lower()
        
        # Contar ocorrências de termos da query
        query_terms = query.split()
        for term in query_terms:
            if len(term) > 2:
                count = searchable_text.count(term)
                score += count * 1.0
        
        # Bonus por correspondência exata
        if query in searchable_text:
            score += 5.0
        
        # Bonus por tribunal superior
        if precedent.get("tribunal") in ["STF", "STJ"]:
            score += 2.0
        
        return score
    
    async def get_by_tribunal(self, tribunal: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Retorna precedentes de um tribunal específico"""
        results = [
            p for p in self.precedents
            if p.get("tribunal", "").upper() == tribunal.upper()
        ]
        return results[:limit]
    
    async def get_recent_precedents(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Retorna precedentes mais recentes"""
        sorted_precedents = sorted(
            self.precedents,
            key=lambda x: x.get("data", ""),
            reverse=True
        )
        return sorted_precedents[:limit]
    
    def get_statistics(self) -> Dict[str, Any]:
        """Retorna estatísticas da base de dados"""
        tribunals = {}
        temas = {}
        
        for precedent in self.precedents:
            tribunal = precedent.get("tribunal", "Outro")
            tribunals[tribunal] = tribunals.get(tribunal, 0) + 1
            
            tema = precedent.get("tema", "Outros")
            temas[tema] = temas.get(tema, 0) + 1
        
        return {
            "total_precedents": len(self.precedents),
            "by_tribunal": tribunals,
            "by_tema": dict(list(temas.items())[:10]),
            "database_path": str(self.database_path)
        }


# Instância global
jurisprudence_service = JurisprudenceService()
