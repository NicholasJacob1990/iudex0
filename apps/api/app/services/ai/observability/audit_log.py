from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Deque, Dict, List, Optional
import json
import os
import uuid


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_iso(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _safe_input(value: Any, *, max_chars: int) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        text = str(value)
        return text[:max_chars]
    if isinstance(value, dict):
        rendered: Dict[str, Any] = {}
        for key, item in list(value.items())[:50]:
            if isinstance(item, (dict, list)):
                dumped = json.dumps(item, default=str)
                rendered[str(key)] = dumped[:max_chars]
            elif item is None:
                rendered[str(key)] = None
            else:
                rendered[str(key)] = str(item)[:max_chars]
        return rendered
    if isinstance(value, list):
        rendered_list: List[Any] = []
        for item in value[:50]:
            if isinstance(item, (dict, list)):
                dumped = json.dumps(item, default=str)
                rendered_list.append(dumped[:max_chars])
            elif item is None:
                rendered_list.append(None)
            else:
                rendered_list.append(str(item)[:max_chars])
        return rendered_list
    return str(value)[:max_chars]


@dataclass
class ToolAuditEntry:
    id: str
    timestamp: str
    event_type: str
    tool_name: str
    user_id: Optional[str] = None
    tenant_id: Optional[str] = None
    session_id: Optional[str] = None
    project_id: Optional[str] = None
    job_id: Optional[str] = None
    provider: Optional[str] = None
    tool_id: Optional[str] = None
    permission_decision: Optional[str] = None
    permission_source: Optional[str] = None
    permission_rule_scope: Optional[str] = None
    permission_rule_id: Optional[str] = None
    success: Optional[bool] = None
    duration_ms: Optional[int] = None
    error: Optional[str] = None
    tool_input: Any = None
    metadata: Dict[str, Any] = None  # type: ignore[assignment]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "tool_name": self.tool_name,
            "user_id": self.user_id,
            "tenant_id": self.tenant_id,
            "session_id": self.session_id,
            "project_id": self.project_id,
            "job_id": self.job_id,
            "provider": self.provider,
            "tool_id": self.tool_id,
            "permission_decision": self.permission_decision,
            "permission_source": self.permission_source,
            "permission_rule_scope": self.permission_rule_scope,
            "permission_rule_id": self.permission_rule_id,
            "success": self.success,
            "duration_ms": self.duration_ms,
            "error": self.error,
            "tool_input": self.tool_input,
            "metadata": self.metadata or {},
        }


class AgentToolAuditLog:
    """
    Audit log estruturado de tool calls/permissions para compliance (fase 4.4).

    In-memory ring buffer com export JSONL filtrável.
    """

    def __init__(
        self,
        *,
        max_entries: int = 20000,
        max_input_chars: int = 800,
    ) -> None:
        self._max_entries = max(500, int(max_entries))
        self._max_input_chars = max(80, int(max_input_chars))
        self._lock = Lock()
        self._entries: Deque[ToolAuditEntry] = deque(maxlen=self._max_entries)

    def _append(self, entry: ToolAuditEntry) -> None:
        with self._lock:
            self._entries.append(entry)

    def record_permission_decision(
        self,
        *,
        tool_name: str,
        decision: str,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        session_id: Optional[str] = None,
        project_id: Optional[str] = None,
        job_id: Optional[str] = None,
        provider: Optional[str] = None,
        tool_id: Optional[str] = None,
        tool_input: Optional[Dict[str, Any]] = None,
        source: str = "permission_manager",
        rule_scope: Optional[str] = None,
        rule_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._append(
            ToolAuditEntry(
                id=str(uuid.uuid4()),
                timestamp=_utc_now_iso(),
                event_type="permission_decision",
                tool_name=str(tool_name or "unknown"),
                user_id=str(user_id) if user_id else None,
                tenant_id=str(tenant_id) if tenant_id else None,
                session_id=str(session_id) if session_id else None,
                project_id=str(project_id) if project_id else None,
                job_id=str(job_id) if job_id else None,
                provider=str(provider) if provider else None,
                tool_id=str(tool_id) if tool_id else None,
                permission_decision=str(decision or "").strip().lower() or None,
                permission_source=str(source or "unknown"),
                permission_rule_scope=str(rule_scope) if rule_scope else None,
                permission_rule_id=str(rule_id) if rule_id else None,
                tool_input=_safe_input(tool_input, max_chars=self._max_input_chars),
                metadata=dict(metadata or {}),
            )
        )

    def record_tool_execution(
        self,
        *,
        tool_name: str,
        success: bool,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        session_id: Optional[str] = None,
        project_id: Optional[str] = None,
        job_id: Optional[str] = None,
        provider: Optional[str] = None,
        tool_id: Optional[str] = None,
        duration_ms: Optional[int] = None,
        error: Optional[str] = None,
        tool_input: Optional[Dict[str, Any]] = None,
        permission_decision: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._append(
            ToolAuditEntry(
                id=str(uuid.uuid4()),
                timestamp=_utc_now_iso(),
                event_type="tool_execution",
                tool_name=str(tool_name or "unknown"),
                user_id=str(user_id) if user_id else None,
                tenant_id=str(tenant_id) if tenant_id else None,
                session_id=str(session_id) if session_id else None,
                project_id=str(project_id) if project_id else None,
                job_id=str(job_id) if job_id else None,
                provider=str(provider) if provider else None,
                tool_id=str(tool_id) if tool_id else None,
                permission_decision=(
                    str(permission_decision).strip().lower()
                    if permission_decision is not None
                    else None
                ),
                success=bool(success),
                duration_ms=int(duration_ms) if duration_ms is not None else None,
                error=(str(error)[: self._max_input_chars] if error else None),
                tool_input=_safe_input(tool_input, max_chars=self._max_input_chars),
                metadata=dict(metadata or {}),
            )
        )

    def list_entries(
        self,
        *,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        tool_name: Optional[str] = None,
        event_type: Optional[str] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        limit: int = 500,
    ) -> List[Dict[str, Any]]:
        since_iso = _to_iso(since)
        until_iso = _to_iso(until)
        limit = max(1, min(10000, int(limit)))
        with self._lock:
            rows = [entry.to_dict() for entry in self._entries]

        def _matches(entry: Dict[str, Any]) -> bool:
            if user_id and entry.get("user_id") != str(user_id):
                return False
            if tenant_id and entry.get("tenant_id") != str(tenant_id):
                return False
            if tool_name and entry.get("tool_name") != str(tool_name):
                return False
            if event_type and entry.get("event_type") != str(event_type):
                return False
            ts = str(entry.get("timestamp") or "")
            if since_iso and ts < since_iso:
                return False
            if until_iso and ts > until_iso:
                return False
            return True

        filtered = [row for row in rows if _matches(row)]
        if len(filtered) > limit:
            filtered = filtered[-limit:]
        return filtered

    def export_jsonl(self, **filters: Any) -> str:
        rows = self.list_entries(**filters)
        return "\n".join(json.dumps(row, ensure_ascii=False, default=str) for row in rows)

    def clear(self, *, user_id: Optional[str] = None, tenant_id: Optional[str] = None) -> int:
        with self._lock:
            original = len(self._entries)
            if not user_id and not tenant_id:
                self._entries.clear()
                return original

            kept: Deque[ToolAuditEntry] = deque(maxlen=self._max_entries)
            for entry in self._entries:
                matches_user = (not user_id) or (entry.user_id == str(user_id))
                matches_tenant = (not tenant_id) or (entry.tenant_id == str(tenant_id))
                if not (matches_user and matches_tenant):
                    kept.append(entry)
            self._entries = kept
            return original - len(self._entries)


_tool_audit_singleton: Optional[AgentToolAuditLog] = None


def get_tool_audit_log() -> AgentToolAuditLog:
    global _tool_audit_singleton
    if _tool_audit_singleton is None:
        _tool_audit_singleton = AgentToolAuditLog(
            max_entries=int(os.getenv("IUDEX_TOOL_AUDIT_MAX_ENTRIES", "20000") or 20000),
            max_input_chars=int(os.getenv("IUDEX_TOOL_AUDIT_MAX_INPUT_CHARS", "800") or 800),
        )
    return _tool_audit_singleton


def reset_tool_audit_log() -> None:
    get_tool_audit_log().clear()
