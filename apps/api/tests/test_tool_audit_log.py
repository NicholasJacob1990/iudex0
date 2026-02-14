from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.ai.claude_agent.permissions import PermissionManager
from app.services.ai.executors.base import (
    AgentProvider,
    BaseAgentExecutor,
    ExecutorConfig,
    ExecutorState,
)
from app.services.ai.observability.audit_log import (
    AgentToolAuditLog,
    get_tool_audit_log,
    reset_tool_audit_log,
)


class _DummyExecutor(BaseAgentExecutor):
    @property
    def provider(self) -> AgentProvider:
        return AgentProvider.OPENAI

    async def run(self, prompt: str, system_prompt=None, context=None, job_id=None, **kwargs):
        if False:
            yield {}  # pragma: no cover

    async def resume(self, job_id: str, tool_results=None, **kwargs):
        if False:
            yield {}  # pragma: no cover

    def _get_tools_for_provider(self, tool_names=None, include_mcp: bool = True):
        return []

    def _extract_tool_name(self, tool_def):
        return str(tool_def.get("name", ""))


def test_audit_log_records_and_exports_jsonl():
    log = AgentToolAuditLog(max_entries=50, max_input_chars=120)
    log.record_permission_decision(
        tool_name="search_rag",
        decision="allow",
        user_id="user-1",
        session_id="sess-1",
        source="permission_manager",
        rule_scope="system",
        tool_input={"query": "precedentes"},
    )
    log.record_tool_execution(
        tool_name="search_rag",
        success=True,
        user_id="user-1",
        session_id="sess-1",
        duration_ms=37,
        tool_input={"query": "precedentes"},
    )

    rows = log.list_entries(user_id="user-1", limit=10)
    assert len(rows) == 2
    assert rows[0]["event_type"] == "permission_decision"
    assert rows[1]["event_type"] == "tool_execution"

    jsonl = log.export_jsonl(user_id="user-1", limit=10)
    lines = [line for line in jsonl.splitlines() if line.strip()]
    assert len(lines) == 2
    assert '"tool_name": "search_rag"' in lines[0]


def test_audit_log_clear_by_user():
    log = AgentToolAuditLog(max_entries=50)
    log.record_permission_decision(tool_name="a", decision="ask", user_id="u1")
    log.record_permission_decision(tool_name="b", decision="deny", user_id="u2")

    removed = log.clear(user_id="u1")
    assert removed == 1

    rows = log.list_entries(limit=10)
    assert len(rows) == 1
    assert rows[0]["user_id"] == "u2"


@pytest.mark.asyncio
async def test_permission_manager_check_writes_audit_entry():
    reset_tool_audit_log()
    pm = PermissionManager(
        db=MagicMock(),
        user_id="user-pm",
        session_id="sess-pm",
        project_id="case-pm",
    )
    pm._get_rules = AsyncMock(return_value=[])  # type: ignore[method-assign]

    result = await pm.check("search_rag", {"query": "stf"})
    assert result.decision in ("allow", "ask", "deny")

    rows = get_tool_audit_log().list_entries(
        user_id="user-pm",
        event_type="permission_decision",
        limit=20,
    )
    assert len(rows) >= 1
    latest = rows[-1]
    assert latest["tool_name"] == "search_rag"
    assert latest["permission_source"] == "permission_manager"
    assert latest["session_id"] == "sess-pm"
    assert latest["project_id"] == "case-pm"


@pytest.mark.asyncio
async def test_base_executor_fallback_permission_and_execution_are_audited():
    reset_tool_audit_log()

    cfg = ExecutorConfig(default_permission_mode="ask", tool_permissions={"echo_tool": "allow"})
    executor = _DummyExecutor(config=cfg)
    executor._state = ExecutorState(job_id="job-audit")
    await executor._init_permission_manager(
        db_session=None,
        user_id="user-exec",
        session_id="sess-exec",
        project_id="case-exec",
    )
    executor._tool_registry["echo_tool"] = lambda text="": {"echo": text}

    decision = await executor._check_permission("echo_tool", {"text": "oi"})
    assert decision == "allow"
    result = await executor._execute_tool("echo_tool", {"text": "oi"})
    assert result == {"echo": "oi"}

    rows = get_tool_audit_log().list_entries(user_id="user-exec", limit=50)
    permission_entries = [r for r in rows if r.get("event_type") == "permission_decision"]
    execution_entries = [r for r in rows if r.get("event_type") == "tool_execution"]

    assert permission_entries
    assert execution_entries
    assert permission_entries[-1]["permission_source"] == "executor_config"
    assert execution_entries[-1]["tool_name"] == "echo_tool"
    assert execution_entries[-1]["success"] is True
