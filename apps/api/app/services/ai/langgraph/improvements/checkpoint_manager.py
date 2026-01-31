"""
Checkpoint Manager - Save and restore workflow state snapshots.
"""
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from loguru import logger


@dataclass
class CheckpointInfo:
    id: str
    job_id: str
    description: str
    created_at: str
    node_name: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


class CheckpointManager:
    """Manages workflow state checkpoints for save/restore."""

    def __init__(self):
        self._checkpoints: Dict[str, Dict[str, Any]] = {}
        self._index: Dict[str, List[str]] = {}  # job_id -> [checkpoint_ids]

    def create(self, job_id: str, state: Dict[str, Any], description: str, node_name: str = "") -> str:
        checkpoint_id = str(uuid.uuid4())
        self._checkpoints[checkpoint_id] = {
            "info": CheckpointInfo(
                id=checkpoint_id,
                job_id=job_id,
                description=description,
                created_at=datetime.utcnow().isoformat(),
                node_name=node_name,
            ),
            "state": state.copy(),
        }
        self._index.setdefault(job_id, []).append(checkpoint_id)
        logger.info(f"Checkpoint created: {checkpoint_id} for job {job_id}")
        return checkpoint_id

    def restore(self, checkpoint_id: str) -> Optional[Dict[str, Any]]:
        entry = self._checkpoints.get(checkpoint_id)
        if not entry:
            logger.warning(f"Checkpoint not found: {checkpoint_id}")
            return None
        logger.info(f"Restoring checkpoint: {checkpoint_id}")
        return entry["state"].copy()

    def list_checkpoints(self, job_id: str) -> List[CheckpointInfo]:
        ids = self._index.get(job_id, [])
        result = []
        for cid in ids:
            entry = self._checkpoints.get(cid)
            if entry:
                result.append(entry["info"])
        return result

    def delete(self, checkpoint_id: str) -> bool:
        entry = self._checkpoints.pop(checkpoint_id, None)
        if not entry:
            return False
        job_id = entry["info"].job_id
        if job_id in self._index:
            self._index[job_id] = [c for c in self._index[job_id] if c != checkpoint_id]
        return True


checkpoint_manager = CheckpointManager()
