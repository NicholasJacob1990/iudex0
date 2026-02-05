"""
Unified Context Store — Shared memory between Chat, Agent, and Workflow.

Bridges context across the three layers (Chat → Agent → Workflow) using:
- Redis for fast session-scoped context (conversation history, metadata)
- Vector embeddings for semantic retrieval of relevant past interactions
- ChromaDB for persistent vector storage

This service ensures that when a user promotes a chat to an agent,
or exports an agent result to a workflow, the full context travels
with the operation.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from loguru import logger

from app.core.redis import get_redis


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CONTEXT_TTL_SECONDS = 72 * 60 * 60  # 72h
CONTEXT_KEY_PREFIX = "uctx"  # Unified ConTeXt
MAX_CONTEXT_ITEMS = 100
MAX_HISTORY_MESSAGES = 50


class ContextLayer(str, Enum):
    """Origin layer of the context."""
    CHAT = "chat"
    AGENT = "agent"
    WORKFLOW = "workflow"


class ContextItemType(str, Enum):
    """Type of context item."""
    MESSAGE = "message"
    TOOL_RESULT = "tool_result"
    RAG_RESULT = "rag_result"
    AGENT_OUTPUT = "agent_output"
    WORKFLOW_OUTPUT = "workflow_output"
    USER_NOTE = "user_note"


@dataclass
class ContextItem:
    """A single item in the unified context."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    type: ContextItemType = ContextItemType.MESSAGE
    layer: ContextLayer = ContextLayer.CHAT
    content: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "layer": self.layer.value,
            "content": self.content,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ContextItem:
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            type=ContextItemType(data.get("type", "message")),
            layer=ContextLayer(data.get("layer", "chat")),
            content=data.get("content", ""),
            metadata=data.get("metadata", {}),
            timestamp=data.get("timestamp", ""),
        )


# ---------------------------------------------------------------------------
# Unified Context Store
# ---------------------------------------------------------------------------


class UnifiedContextStore:
    """
    Shared context store accessible from Chat, Agent, and Workflow.

    Data flow:
        Chat → stores messages/RAG results
        Agent → reads chat context + stores tool results/output
        Workflow → reads agent output + stores step results

    Storage:
        Redis hash per user session:
            uctx:{user_id}:{session_id}:items  → JSON list of ContextItem
            uctx:{user_id}:{session_id}:meta   → JSON metadata
            uctx:{user_id}:active_session       → current session_id
    """

    def __init__(self, ttl: int = CONTEXT_TTL_SECONDS) -> None:
        self.ttl = ttl

    # -- Key helpers ----------------------------------------------------------

    def _items_key(self, user_id: str, session_id: str) -> str:
        return f"{CONTEXT_KEY_PREFIX}:{user_id}:{session_id}:items"

    def _meta_key(self, user_id: str, session_id: str) -> str:
        return f"{CONTEXT_KEY_PREFIX}:{user_id}:{session_id}:meta"

    def _active_key(self, user_id: str) -> str:
        return f"{CONTEXT_KEY_PREFIX}:{user_id}:active_session"

    # -- Session management ---------------------------------------------------

    async def create_session(
        self,
        user_id: str,
        source_layer: ContextLayer = ContextLayer.CHAT,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create a new context session and set it as active."""
        session_id = str(uuid.uuid4())
        client = get_redis()

        meta = {
            "session_id": session_id,
            "user_id": user_id,
            "source_layer": source_layer.value,
            "created_at": datetime.now(timezone.utc).isoformat(),
            **(metadata or {}),
        }

        await client.setex(
            self._meta_key(user_id, session_id),
            self.ttl,
            json.dumps(meta),
        )
        await client.setex(
            self._items_key(user_id, session_id),
            self.ttl,
            json.dumps([]),
        )
        await client.setex(
            self._active_key(user_id),
            self.ttl,
            session_id,
        )

        logger.debug(f"[UCS] Created session {session_id} for user {user_id}")
        return session_id

    async def get_active_session(self, user_id: str) -> Optional[str]:
        """Get the active context session for a user."""
        try:
            client = get_redis()
            return await client.get(self._active_key(user_id))
        except Exception:
            return None

    async def get_or_create_session(
        self,
        user_id: str,
        source_layer: ContextLayer = ContextLayer.CHAT,
    ) -> str:
        """Get active session or create one."""
        session_id = await self.get_active_session(user_id)
        if session_id:
            return session_id
        return await self.create_session(user_id, source_layer)

    # -- Context items --------------------------------------------------------

    async def add_item(
        self,
        user_id: str,
        session_id: str,
        item: ContextItem,
    ) -> bool:
        """Add a context item to the session."""
        try:
            client = get_redis()
            key = self._items_key(user_id, session_id)
            raw = await client.get(key)
            items = json.loads(raw) if raw else []

            items.append(item.to_dict())

            # Trim to max
            if len(items) > MAX_CONTEXT_ITEMS:
                items = items[-MAX_CONTEXT_ITEMS:]

            await client.setex(key, self.ttl, json.dumps(items))
            return True
        except Exception as e:
            logger.warning(f"[UCS] add_item failed: {e}")
            return False

    async def add_messages(
        self,
        user_id: str,
        session_id: str,
        messages: List[Dict[str, Any]],
        layer: ContextLayer = ContextLayer.CHAT,
    ) -> bool:
        """Bulk add conversation messages as context items."""
        try:
            client = get_redis()
            key = self._items_key(user_id, session_id)
            raw = await client.get(key)
            items = json.loads(raw) if raw else []

            for msg in messages[-MAX_HISTORY_MESSAGES:]:
                items.append(ContextItem(
                    type=ContextItemType.MESSAGE,
                    layer=layer,
                    content=msg.get("content", ""),
                    metadata={
                        "role": msg.get("role", "user"),
                        "model": msg.get("model", ""),
                    },
                ).to_dict())

            if len(items) > MAX_CONTEXT_ITEMS:
                items = items[-MAX_CONTEXT_ITEMS:]

            await client.setex(key, self.ttl, json.dumps(items))
            return True
        except Exception as e:
            logger.warning(f"[UCS] add_messages failed: {e}")
            return False

    async def get_items(
        self,
        user_id: str,
        session_id: str,
        layer: Optional[ContextLayer] = None,
        item_type: Optional[ContextItemType] = None,
        limit: int = 50,
    ) -> List[ContextItem]:
        """Get context items with optional filtering."""
        try:
            client = get_redis()
            raw = await client.get(self._items_key(user_id, session_id))
            if not raw:
                return []

            items = [ContextItem.from_dict(d) for d in json.loads(raw)]

            if layer:
                items = [i for i in items if i.layer == layer]
            if item_type:
                items = [i for i in items if i.type == item_type]

            return items[-limit:]
        except Exception as e:
            logger.warning(f"[UCS] get_items failed: {e}")
            return []

    async def get_context_string(
        self,
        user_id: str,
        session_id: str,
        max_chars: int = 20000,
    ) -> str:
        """Get formatted context string for injection into prompts."""
        items = await self.get_items(user_id, session_id)
        if not items:
            return ""

        parts: list[str] = []
        total = 0

        for item in reversed(items):
            entry = f"[{item.layer.value}/{item.type.value}] {item.content}"
            if total + len(entry) > max_chars:
                break
            parts.insert(0, entry)
            total += len(entry)

        return "\n".join(parts)

    # -- Cross-layer transfers ------------------------------------------------

    async def promote_chat_to_agent(
        self,
        user_id: str,
        chat_messages: List[Dict[str, Any]],
        chat_id: Optional[str] = None,
    ) -> str:
        """
        Promote a chat conversation to an agent context session.

        Takes the last N messages from chat, creates a new context session,
        and returns the session_id that the agent can use.
        """
        session_id = await self.create_session(
            user_id,
            source_layer=ContextLayer.CHAT,
            metadata={"promoted_from": "chat", "chat_id": chat_id},
        )

        await self.add_messages(
            user_id, session_id, chat_messages, layer=ContextLayer.CHAT
        )

        logger.info(
            f"[UCS] Promoted chat to agent: session={session_id}, "
            f"messages={len(chat_messages)}"
        )
        return session_id

    async def export_agent_to_workflow(
        self,
        user_id: str,
        agent_task_id: str,
        agent_result: str,
        agent_metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Export an agent result to a workflow context session.

        Creates a new session with the agent output as initial context.
        """
        session_id = await self.create_session(
            user_id,
            source_layer=ContextLayer.AGENT,
            metadata={
                "exported_from": "agent",
                "agent_task_id": agent_task_id,
                **(agent_metadata or {}),
            },
        )

        await self.add_item(
            user_id,
            session_id,
            ContextItem(
                type=ContextItemType.AGENT_OUTPUT,
                layer=ContextLayer.AGENT,
                content=agent_result,
                metadata={
                    "agent_task_id": agent_task_id,
                    **(agent_metadata or {}),
                },
            ),
        )

        logger.info(
            f"[UCS] Exported agent to workflow: session={session_id}, "
            f"task={agent_task_id}"
        )
        return session_id

    async def get_session_meta(
        self, user_id: str, session_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get session metadata."""
        try:
            client = get_redis()
            raw = await client.get(self._meta_key(user_id, session_id))
            return json.loads(raw) if raw else None
        except Exception:
            return None


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

unified_context = UnifiedContextStore()
