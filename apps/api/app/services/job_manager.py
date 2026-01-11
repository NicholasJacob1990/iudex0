
import sqlite3
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List

logger = logging.getLogger("JobManager")

class JobManager:
    """
    Gerencia persistência de jobs e cache inteligente para Deep Research.
    Usa SQLite para armazenar resultados de pesquisas custosas (TTL 7 dias).
    """
    
    def __init__(self, db_path: str = "jobs.db"):
        # Garante que o diretório de dados existe
        base_dir = Path(__file__).parent.parent / "data"
        base_dir.mkdir(parents=True, exist_ok=True)
        
        self.db_path = str(base_dir / db_path)
        self._init_db()
    
    def _init_db(self):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Tabela de jobs (para LangGraph persistence futuramente)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    jobid TEXT PRIMARY KEY,
                    status TEXT,
                    config TEXT,
                    result TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    progress INTEGER
                )
            """)
            
            # NOVA: Tabela de cache Deep Research
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS deep_research_cache (
                    cache_key TEXT PRIMARY KEY,
                    query_hash TEXT,
                    report TEXT,
                    sources TEXT,
                    thinking_steps TEXT,
                    created_at TEXT,
                    expires_at TEXT,
                    usage_count INTEGER DEFAULT 0
                )
            """)
            
            # Índice para limpeza de cache expirado
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_expires 
                ON deep_research_cache(expires_at)
            """)
            
            # Índice para hash da query
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_query_hash 
                ON deep_research_cache(query_hash)
            """)
            
            conn.commit()
            conn.close()
            logger.info(f"✅ JobManager DB inicializado em: {self.db_path}")
            
        except Exception as e:
            logger.error(f"❌ Erro ao inicializar JobManager DB: {e}")
    
    def cache_deep_research(
        self,
        query: str,
        report: str,
        sources: List[Dict[str, Any]],
        thinking_steps: List[Dict[str, Any]],
        ttl_hours: int = 168  # 7 dias default
    ) -> str:
        """Salva resultado Deep Research no cache"""
        import hashlib
        
        try:
            # Gera hash da query (normalizada)
            query_normalized = query.lower().strip()
            query_hash = hashlib.sha256(query_normalized.encode()).hexdigest()
            
            # Cache key única com prefixo
            cache_key = f"dr_{query_hash[:16]}"
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            now = datetime.now().isoformat()
            expires = (datetime.now() + timedelta(hours=ttl_hours)).isoformat()
            
            # Upsert (Insert or Replace)
            # Preserva usage_count se já existir
            usage_count = 0
            cursor.execute("SELECT usage_count FROM deep_research_cache WHERE cache_key = ?", (cache_key,))
            row = cursor.fetchone()
            if row:
                usage_count = row[0]
            
            cursor.execute("""
                INSERT OR REPLACE INTO deep_research_cache
                (cache_key, query_hash, report, sources, thinking_steps, created_at, expires_at, usage_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                cache_key,
                query_hash,
                report,
                json.dumps(sources, ensure_ascii=False),
                json.dumps(thinking_steps, ensure_ascii=False),
                now,
                expires,
                usage_count
            ))
            
            conn.commit()
            conn.close()
            
            logger.info(f"💾 Deep Research cacheado: {cache_key} (expira em {ttl_hours}h)")
            return cache_key
            
        except Exception as e:
            logger.error(f"❌ Erro ao salvar cache Deep Research: {e}")
            return ""
    
    def get_cached_deep_research(self, query: str) -> Optional[Dict[str, Any]]:
        """Busca no cache por query"""
        import hashlib
        
        try:
            query_normalized = query.lower().strip()
            query_hash = hashlib.sha256(query_normalized.encode()).hexdigest()
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT cache_key, report, sources, thinking_steps, created_at
                FROM deep_research_cache
                WHERE query_hash = ? AND expires_at > ?
            """, (query_hash, datetime.now().isoformat()))
            
            row = cursor.fetchone()
            
            if row:
                cache_key = row[0]
                
                # Incrementa contador de uso de forma atômica
                cursor.execute("""
                    UPDATE deep_research_cache 
                    SET usage_count = usage_count + 1
                    WHERE cache_key = ?
                """, (cache_key,))
                conn.commit()
                conn.close()
                
                logger.info(f"✅ Cache BIT: {cache_key}")
                
                return {
                    "cache_key": row[0],
                    "report": row[1],
                    "sources": json.loads(row[2]),
                    "thinking_steps": json.loads(row[3]),
                    "cached_at": row[4],
                    "from_cache": True
                }
            
            conn.close()
            return None
            
        except Exception as e:
            logger.error(f"❌ Erro ao ler cache Deep Research: {e}")
            return None
    
    def clean_expired_cache(self) -> int:
        """Remove cache expirado e retorna contagem de deletados"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                DELETE FROM deep_research_cache
                WHERE expires_at < ?
            """, (datetime.now().isoformat(),))
            
            deleted = cursor.rowcount
            conn.commit()
            conn.close()
            
            if deleted > 0:
                logger.info(f"🧹 Limpeza de cache: {deleted} itens expirados removidos.")
                
            return deleted
        except Exception as e:
            logger.error(f"❌ Erro na limpeza de cache: {e}")
            return 0

# Instância global
job_manager = JobManager()
