"""
job_manager.py - Persistent Job Management for Juridico AI
Uses SQLite to store job status and results.
"""
import sqlite3
import json
import uuid
import logging
from datetime import datetime
from typing import Dict, Optional, Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("JobManager")

class JobManager:
    def __init__(self, db_path: str = "jobs.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize SQLite database"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    config JSON,
                    result JSON,
                    progress INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # Performance indexes
            conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at DESC)")
            conn.commit()

    def create_job(self, config: Dict[str, Any]) -> str:
        """Create a new job and return ID"""
        job_id = str(uuid.uuid4())
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO jobs (job_id, status, config, progress, created_at) VALUES (?, ?, ?, ?, ?)",
                (job_id, "pending", json.dumps(config), 0, datetime.now().isoformat())
            )
        
        logger.info(f"Job created: {job_id}")
        return job_id

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve job details"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,))
            row = cursor.fetchone()
            
            if row:
                job = dict(row)
                if job['config']:
                    job['config'] = json.loads(job['config'])
                if job['result']:
                    try:
                        job['result'] = json.loads(job['result'])
                    except:
                        job['result'] = None
                return job
            return None

    def update_job(self, job_id: str, status: Optional[str] = None, result: Optional[Dict] = None, progress: int = 0):
        """Update job status, result, and progress"""
        updates = []
        params = []
        
        if status:
            updates.append("status = ?")
            params.append(status)
        
        if result is not None:
            updates.append("result = ?")
            params.append(json.dumps(result))
            
        if progress > 0:
            updates.append("progress = ?")
            params.append(progress)
            
        updates.append("updated_at = ?")
        params.append(datetime.now().isoformat())
        
        params.append(job_id)
        
        query = f"UPDATE jobs SET {', '.join(updates)} WHERE job_id = ?"
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(query, params)
            
    def list_jobs(self, limit: int = 10):
        """List recent jobs"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT job_id, status, created_at FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,))
            return [dict(row) for row in cursor.fetchall()]

    def cleanup_old_jobs(self, days: int = 7) -> int:
        """
        Delete jobs older than `days` days.
        Returns the number of deleted jobs.
        """
        from datetime import timedelta
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("DELETE FROM jobs WHERE created_at < ?", (cutoff,))
            deleted = cursor.rowcount
            conn.commit()
        
        if deleted > 0:
            logger.info(f"Cleanup: {deleted} jobs older than {days} days deleted.")
        return deleted

# Global instance for easy import if needed
job_manager = JobManager()
