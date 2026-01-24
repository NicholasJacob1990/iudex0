
import os
import sqlite3
import json
import logging
import shutil
from copy import deepcopy
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock
from typing import Optional, Dict, Any, List

from app.core.config import settings

logger = logging.getLogger("JobManager")

class JobManager:
    """
    Gerencia persistência de jobs e cache inteligente para Deep Research.
    Usa SQLite para armazenar resultados de pesquisas custosas (TTL 7 dias).
    """
    
    def __init__(self, db_path: str = "jobs.db"):
        legacy_base = Path(__file__).parent.parent / "data"
        legacy_db = legacy_base / db_path

        storage_path = Path(settings.LOCAL_STORAGE_PATH) if settings else Path("./storage")
        if not storage_path.is_absolute():
            backend_root = Path(__file__).resolve().parents[2]
            storage_path = backend_root / storage_path
        base_dir = storage_path / "job_manager"
        target_db = base_dir / db_path

        try:
            base_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            logger.warning(f"⚠️ Falha ao criar diretório de jobs em {base_dir}: {exc}")
            self.db_path = str(legacy_db)
        else:
            if legacy_db.exists() and not target_db.exists():
                try:
                    shutil.copy2(legacy_db, target_db)
                except Exception as exc:
                    logger.warning(f"⚠️ Falha ao migrar jobs.db para {target_db}: {exc}")
                    self.db_path = str(legacy_db)
                else:
                    self.db_path = str(target_db)
            else:
                self.db_path = str(target_db)
        self._init_db()
        self._event_lock = Lock()
        self._event_counters: Dict[str, int] = {}
        self._event_queues: Dict[str, deque] = {}
        try:
            max_events = int(os.getenv("JOB_EVENT_MAX", "20000"))
        except (TypeError, ValueError):
            max_events = 20000
        self._event_max = max(1000, min(max_events, 100000))
        self._api_counters: Dict[str, Dict[str, Any]] = {}
        self._job_users: Dict[str, str] = {}

    def set_job_user(self, job_id: str, user_id: Optional[str]) -> None:
        job_id = str(job_id or "").strip()
        user_key = str(user_id or "").strip()
        if not job_id:
            return
        if not user_key:
            self._job_users.pop(job_id, None)
            return
        self._job_users[job_id] = user_key

    def get_job_user(self, job_id: str) -> Optional[str]:
        job_id = str(job_id or "").strip()
        if not job_id:
            return None
        return self._job_users.get(job_id)

    def build_event(
        self,
        job_id: str,
        event_type: Any,
        payload: Optional[Dict[str, Any]] = None,
        *,
        phase: Optional[str] = None,
        node: Optional[str] = None,
        section: Optional[str] = None,
        agent: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a standard event envelope without enqueueing."""
        if isinstance(event_type, dict):
            event: Dict[str, Any] = dict(event_type)
            event.setdefault("v", 1)
            event.setdefault("job_id", job_id)
            event.setdefault("ts", f"{datetime.utcnow().isoformat()}Z")
            if payload is not None and "data" not in event:
                event["data"] = dict(payload) if isinstance(payload, dict) else {"value": payload}
            return event

        data = {}
        if payload is not None:
            if isinstance(payload, dict):
                data = dict(payload)
            else:
                data = {"value": payload}

        if phase is None and isinstance(payload, dict):
            phase = payload.get("phase")
        if node is None and isinstance(payload, dict):
            node = payload.get("node")
        if section is None and isinstance(payload, dict):
            section = payload.get("section")
        if agent is None and isinstance(payload, dict):
            agent = payload.get("agent")

        return {
            "v": 1,
            "job_id": job_id,
            "ts": f"{datetime.utcnow().isoformat()}Z",
            "type": str(event_type),
            "phase": phase,
            "node": node,
            "section": section,
            "agent": agent,
            "data": data,
        }

    def emit_event(
        self,
        job_id: Optional[str],
        event_type: Any,
        payload: Optional[Dict[str, Any]] = None,
        *,
        phase: Optional[str] = None,
        node: Optional[str] = None,
        section: Optional[str] = None,
        agent: Optional[str] = None,
    ) -> Optional[int]:
        """Store a lightweight event for SSE consumers."""
        if not job_id:
            return None

        event = self.build_event(
            job_id,
            event_type,
            payload,
            phase=phase,
            node=node,
            section=section,
            agent=agent,
        )

        with self._event_lock:
            next_id = self._event_counters.get(job_id, 0) + 1
            self._event_counters[job_id] = next_id
            event["id"] = next_id

            queue = self._event_queues.get(job_id)
            if queue is None:
                queue = deque(maxlen=self._event_max)
                self._event_queues[job_id] = queue
            queue.append(event)

        return next_id

    def list_events(self, job_id: str, after_id: int = 0) -> List[Dict[str, Any]]:
        """Return events for a job after a given id."""
        if not job_id:
            return []
        with self._event_lock:
            queue = list(self._event_queues.get(job_id, []))
        if not queue:
            return []
        return [event for event in queue if int(event.get("id", 0)) > int(after_id)]

    def clear_events(self, job_id: str) -> None:
        """Drop stored events for a job (best-effort cleanup)."""
        if not job_id:
            return
        with self._event_lock:
            self._event_queues.pop(job_id, None)
            self._event_counters.pop(job_id, None)
            self._api_counters.pop(job_id, None)
        self._job_users.pop(job_id, None)

    def record_api_call(
        self,
        job_id: str,
        *,
        kind: str,
        provider: str,
        model: Optional[str] = None,
        success: Optional[bool] = None,
        cached: Optional[bool] = None,
        meta: Optional[Dict[str, Any]] = None,
        points: Optional[int] = None,
    ) -> None:
        if not job_id:
            return
        payload = {
            "ts": f"{datetime.utcnow().isoformat()}Z",
            "kind": kind,
            "provider": provider,
            "model": model,
            "success": success,
            "cached": cached,
            "meta": dict(meta) if isinstance(meta, dict) else None,
        }
        with self._event_lock:
            bucket = self._api_counters.get(job_id)
            if bucket is None:
                bucket = {
                    "total": 0,
                    "by_kind": {},
                    "by_provider": {},
                    "by_model": {},
                    "success": 0,
                    "errors": 0,
                    "cached": 0,
                    "last_call": None,
                    "points_total": 0,
                    "points_by_kind": {},
                    "points_by_provider": {},
                    "points_by_model": {},
                }
                self._api_counters[job_id] = bucket

            bucket["total"] += 1
            if kind:
                by_kind = bucket["by_kind"]
                by_kind[kind] = int(by_kind.get(kind, 0)) + 1
            if provider:
                by_provider = bucket["by_provider"]
                by_provider[provider] = int(by_provider.get(provider, 0)) + 1
            if model:
                by_model = bucket["by_model"]
                by_model[model] = int(by_model.get(model, 0)) + 1
            if success is True:
                bucket["success"] += 1
            elif success is False:
                bucket["errors"] += 1
            if cached:
                bucket["cached"] += 1
            if points is not None:
                points_value = int(points)
                bucket["points_total"] += points_value
                if kind:
                    points_by_kind = bucket["points_by_kind"]
                    points_by_kind[kind] = int(points_by_kind.get(kind, 0)) + points_value
                if provider:
                    points_by_provider = bucket["points_by_provider"]
                    points_by_provider[provider] = int(points_by_provider.get(provider, 0)) + points_value
                if model:
                    points_by_model = bucket["points_by_model"]
                    points_by_model[model] = int(points_by_model.get(model, 0)) + points_value
                payload["points"] = points_value
            bucket["last_call"] = payload

    def get_api_counters(self, job_id: str) -> Dict[str, Any]:
        if not job_id:
            return {}
        with self._event_lock:
            payload = self._api_counters.get(job_id)
            if not payload:
                return {}
            return deepcopy(payload)
    
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

            # NOVA: Tabela de jobs de transcrição (persistência simples)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS transcription_jobs (
                    jobid TEXT PRIMARY KEY,
                    job_type TEXT,
                    status TEXT,
                    config TEXT,
                    file_names TEXT,
                    file_paths TEXT,
                    result_path TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    progress INTEGER,
                    stage TEXT,
                    message TEXT,
                    error TEXT
                )
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_transcription_jobs_status
                ON transcription_jobs(status)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_transcription_jobs_created
                ON transcription_jobs(created_at)
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

    def clean_workflow_documents(
        self,
        ttl_days: Optional[int] = None,
        max_bytes: Optional[int] = None,
    ) -> Dict[str, Any]:
        from app.services.ai.document_store import cleanup_workflow_documents

        result = cleanup_workflow_documents(ttl_days=ttl_days, max_bytes=max_bytes)
        if result.get("removed"):
            logger.info(f"🧹 Workflow documents cleaned: {result}")
        return result

    def create_transcription_job(
        self,
        job_id: str,
        job_type: str,
        config: Dict[str, Any],
        file_names: List[str],
        file_paths: List[str],
        status: str = "queued",
        progress: int = 0,
        stage: str = "queued",
        message: str = "Aguardando início",
        result_path: Optional[str] = None,
    ) -> None:
        try:
            now = datetime.utcnow().isoformat()
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO transcription_jobs (
                    jobid, job_type, status, config, file_names, file_paths,
                    result_path, created_at, updated_at, progress, stage, message, error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                job_id,
                job_type,
                status,
                json.dumps(config, ensure_ascii=False),
                json.dumps(file_names, ensure_ascii=False),
                json.dumps(file_paths, ensure_ascii=False),
                result_path,
                now,
                now,
                progress,
                stage,
                message,
                None,
            ))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"❌ Erro ao criar job de transcrição: {e}")

    def update_transcription_job(
        self,
        job_id: str,
        status: Optional[str] = None,
        progress: Optional[int] = None,
        stage: Optional[str] = None,
        message: Optional[str] = None,
        result_path: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        try:
            fields = []
            values: list[Any] = []
            if status is not None:
                fields.append("status = ?")
                values.append(status)
            if progress is not None:
                fields.append("progress = ?")
                values.append(progress)
            if stage is not None:
                fields.append("stage = ?")
                values.append(stage)
            if message is not None:
                fields.append("message = ?")
                values.append(message)
            if result_path is not None:
                fields.append("result_path = ?")
                values.append(result_path)
            if error is not None:
                fields.append("error = ?")
                values.append(error)

            if not fields:
                return

            fields.append("updated_at = ?")
            values.append(datetime.utcnow().isoformat())
            values.append(job_id)

            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                f"UPDATE transcription_jobs SET {', '.join(fields)} WHERE jobid = ?",
                values,
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"❌ Erro ao atualizar job de transcrição: {e}")

    def get_transcription_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT jobid, job_type, status, config, file_names, file_paths,
                       result_path, created_at, updated_at, progress, stage, message, error
                FROM transcription_jobs
                WHERE jobid = ?
            """, (job_id,))
            row = cursor.fetchone()
            conn.close()
            if not row:
                return None
            return {
                "job_id": row[0],
                "job_type": row[1],
                "status": row[2],
                "config": json.loads(row[3]) if row[3] else {},
                "file_names": json.loads(row[4]) if row[4] else [],
                "file_paths": json.loads(row[5]) if row[5] else [],
                "result_path": row[6],
                "created_at": row[7],
                "updated_at": row[8],
                "progress": row[9],
                "stage": row[10],
                "message": row[11],
                "error": row[12],
            }
        except Exception as e:
            logger.error(f"❌ Erro ao ler job de transcrição: {e}")
            return None

    def list_transcription_jobs(
        self,
        limit: int = 20,
        status: Optional[str] = None,
        job_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            where_clauses = []
            values: list[Any] = []
            if status:
                where_clauses.append("status = ?")
                values.append(status)
            if job_type:
                where_clauses.append("job_type = ?")
                values.append(job_type)

            query = """
                SELECT jobid, job_type, status, config, file_names,
                       result_path, created_at, updated_at, progress, stage, message, error
                FROM transcription_jobs
            """
            if where_clauses:
                query += " WHERE " + " AND ".join(where_clauses)
            query += " ORDER BY created_at DESC LIMIT ?"
            values.append(int(limit))

            cursor.execute(query, values)
            rows = cursor.fetchall()
            conn.close()

            jobs = []
            for row in rows:
                jobs.append({
                    "job_id": row[0],
                    "job_type": row[1],
                    "status": row[2],
                    "config": json.loads(row[3]) if row[3] else {},
                    "file_names": json.loads(row[4]) if row[4] else [],
                    "result_path": row[5],
                    "created_at": row[6],
                    "updated_at": row[7],
                    "progress": row[8],
                    "stage": row[9],
                    "message": row[10],
                    "error": row[11],
                })
            return jobs
        except Exception as e:
            logger.error(f"❌ Erro ao listar jobs de transcrição: {e}")
            return []

    def delete_transcription_job(self, job_id: str) -> bool:
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM transcription_jobs WHERE jobid = ?",
                (job_id,),
            )
            deleted = cursor.rowcount
            conn.commit()
            conn.close()
            return deleted > 0
        except Exception as e:
            logger.error(f"❌ Erro ao excluir job de transcrição: {e}")
            return False

# Instância global
job_manager = JobManager()
