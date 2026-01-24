import json
import logging
from typing import Any, Dict, List, Optional

from app.core.redis import get_redis

logger = logging.getLogger(__name__)

DEFAULT_TTL_SECONDS = 24 * 60 * 60


class RAGMemoryStore:
    def __init__(self, ttl_seconds: Optional[int] = None):
        self.ttl_seconds = int(ttl_seconds or DEFAULT_TTL_SECONDS)

    def _key(self, conversation_id: str) -> str:
        return f"rag_memory:{conversation_id}"

    async def get_history(self, conversation_id: str) -> List[Dict[str, Any]]:
        if not conversation_id:
            return []
        try:
            client = get_redis()
            payload = await client.get(self._key(conversation_id))
            if not payload:
                return []
            data = json.loads(payload)
            return data if isinstance(data, list) else []
        except Exception as exc:
            logger.warning(f"RAG memory read failed: {exc}")
            return []

    async def set_history(self, conversation_id: str, history: List[Dict[str, Any]]) -> bool:
        if not conversation_id:
            return False
        try:
            client = get_redis()
            value = json.dumps(history or [])
            await client.setex(self._key(conversation_id), self.ttl_seconds, value)
            return True
        except Exception as exc:
            logger.warning(f"RAG memory write failed: {exc}")
            return False

    async def append_messages(self, conversation_id: str, messages: List[Dict[str, Any]]) -> bool:
        if not conversation_id:
            return False
        existing = await self.get_history(conversation_id)
        updated = (existing or []) + (messages or [])
        return await self.set_history(conversation_id, updated)
