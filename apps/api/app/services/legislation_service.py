"""
Legislation Service
Busca em base local de legislação brasileira
"""

from typing import Dict, List, Any, Optional
from loguru import logger
import json
from pathlib import Path


class LegislationService:
    """Serviço de busca de legislação em base local"""
    
    def __init__(self):
        self.database_path = Path(__file__).parent.parent / "data" / "legislation_database.json"
        self.laws: List[Dict[str, Any]] = []
        self._load_database()
        logger.info(f"LegislationService inicializado com {len(self.laws)} leis")
    
    def _load_database(self):
        """Carrega base de dados de legislação"""
        try:
            if self.database_path.exists():
                with open(self.database_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.laws = data.get("legislation", [])
                    logger.info(f"Base de legislação carregada: {len(self.laws)} leis")
            else:
                logger.warning(f"Base de dados não encontrada: {self.database_path}")
                self.laws = []
        except Exception as e:
            logger.error(f"Erro ao carregar base de legislação: {e}")
            self.laws = []
    
    async def search(
        self,
        query: str,
        tipo: Optional[str] = None,
        limit: int = 10
    ) -> Dict[str, Any]:
        """
        Busca legislação na base local
        
        Args:
            query: Termo de busca
            tipo: Filtrar por tipo (Código, Lei, etc)
            limit: Número máximo de resultados
            
        Returns:
            Dicionário com resultados da busca
        """
        logger.info(f"Buscando legislação: '{query}' (tipo={tipo})")
        
        try:
            query_lower = query.lower()
            results = []
            
            for law in self.laws:
                score = self._calculate_relevance(law, query_lower, tipo)
                
                if score > 0:
                    results.append({
                        **law,
                        "relevance_score": score
                    })
            
            # Ordenar por relevância
            results.sort(key=lambda x: x["relevance_score"], reverse=True)
            results = results[:limit]
            
            return {
                "success": True,
                "query": query,
                "total": len(results),
                "results": results,
                "filters": {
                    "tipo": tipo
                }
            }
            
        except Exception as e:
            logger.error(f"Erro na busca de legislação: {e}")
            return {
                "success": False,
                "error": str(e),
                "results": []
            }
    
    def _calculate_relevance(
        self,
        law: Dict[str, Any],
        query: str,
        tipo: Optional[str]
    ) -> float:
        """Calcula score de relevância da lei"""
        score = 0.0
        
        # Filtro obrigatório de tipo
        if tipo and law.get("tipo", "").lower() != tipo.lower():
            return 0.0
        
        # Busca no texto
        searchable_text = " ".join([
            law.get("nome", ""),
            law.get("ementa", ""),
            law.get("numero", ""),
            " ".join(law.get("tags", []))
        ]).lower()
        
        # Contar ocorrências de termos da query
        query_terms = query.split()
        for term in query_terms:
            if len(term) > 2:
                count = searchable_text.count(term)
                score += count * 1.0
        
        # Bonus por correspondência exata no nome
        if query in law.get("nome", "").lower():
            score += 10.0
        
        # Bonus por correspondência no número
        if query in law.get("numero", "").lower():
            score += 15.0
        
        # Bonus para códigos principais
        if law.get("tipo") == "Código":
            score += 2.0
        
        return score
    
    async def get_by_id(self, law_id: str) -> Optional[Dict[str, Any]]:
        """Busca lei específica por ID"""
        for law in self.laws:
            if law.get("id") == law_id:
                return law
        return None
    
    async def get_by_type(self, tipo: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Retorna leis de um tipo específico"""
        results = [
            law for law in self.laws
            if law.get("tipo", "").lower() == tipo.lower()
        ]
        return results[:limit]
    
    async def get_recent_laws(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Retorna leis mais recentes"""
        sorted_laws = sorted(
            self.laws,
            key=lambda x: x.get("ano", 0),
            reverse=True
        )
        return sorted_laws[:limit]
    
    async def get_by_tags(self, tags: List[str], limit: int = 10) -> List[Dict[str, Any]]:
        """Busca leis por tags"""
        results = []
        for law in self.laws:
            law_tags = [t.lower() for t in law.get("tags", [])]
            if any(tag.lower() in law_tags for tag in tags):
                results.append(law)
        
        return results[:limit]
    
    def get_statistics(self) -> Dict[str, Any]:
        """Retorna estatísticas da base de dados"""
        tipos = {}
        decades = {}
        
        for law in self.laws:
            # Contar por tipo
            tipo = law.get("tipo", "Outro")
            tipos[tipo] = tipos.get(tipo, 0) + 1
            
            # Contar por década
            ano = law.get("ano", 0)
            if ano > 0:
                decade = (ano // 10) * 10
                decades[f"{decade}s"] = decades.get(f"{decade}s", 0) + 1
        
        return {
            "total_laws": len(self.laws),
            "by_type": tipos,
            "by_decade": decades,
            "database_path": str(self.database_path)
        }


# Instância global
legislation_service = LegislationService()
