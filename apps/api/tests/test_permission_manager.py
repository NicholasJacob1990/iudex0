"""
Tests for PolicyEngine (tool_gateway) - policy decisions and enforcement.

Tests:
- ALLOW policy returns PolicyDecision.ALLOW
- DENY policy returns PolicyDecision.DENY
- ASK policy returns PolicyDecision.ASK
- Tenant overrides work
- Rate limiting works
- Record call / audit log works
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta

from app.services.ai.tool_gateway.policy_engine import (
    PolicyEngine,
    PolicyDecision,
    PolicyContext,
    PolicyResult,
)
from app.services.ai.tool_gateway.tool_registry import (
    ToolPolicy,
    ToolDefinition,
    ToolCategory,
    ToolRegistry,
)


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def engine():
    """Create a fresh PolicyEngine."""
    return PolicyEngine()


@pytest.fixture
def mock_registry():
    """Create a mock tool_registry with sample tools."""
    tools = {
        "search_jurisprudencia": ToolDefinition(
            name="search_jurisprudencia",
            description="Search case law",
            input_schema={"type": "object"},
            function=lambda **kwargs: {},
            policy=ToolPolicy.ALLOW,
            category=ToolCategory.RAG,
        ),
        "edit_document": ToolDefinition(
            name="edit_document",
            description="Edit a legal document",
            input_schema={"type": "object"},
            function=lambda **kwargs: {},
            policy=ToolPolicy.ASK,
            category=ToolCategory.DOCUMENT,
        ),
        "bash": ToolDefinition(
            name="bash",
            description="Execute shell commands",
            input_schema={"type": "object"},
            function=lambda **kwargs: {},
            policy=ToolPolicy.DENY,
            category=ToolCategory.SENSITIVE,
        ),
        "rate_limited_tool": ToolDefinition(
            name="rate_limited_tool",
            description="A rate-limited tool",
            input_schema={"type": "object"},
            function=lambda **kwargs: {},
            policy=ToolPolicy.ALLOW,
            category=ToolCategory.RAG,
        ),
    }

    registry = MagicMock(spec=ToolRegistry)
    registry.get = MagicMock(side_effect=lambda name: tools.get(name))
    return registry


@pytest.fixture
def ctx_allow():
    """PolicyContext for ALLOW tool."""
    return PolicyContext(
        user_id="user-1",
        tenant_id="tenant-1",
        tool_name="search_jurisprudencia",
        arguments={"query": "habeas corpus"},
    )


@pytest.fixture
def ctx_ask():
    """PolicyContext for ASK tool."""
    return PolicyContext(
        user_id="user-1",
        tenant_id="tenant-1",
        tool_name="edit_document",
        arguments={"content": "new text"},
    )


@pytest.fixture
def ctx_deny():
    """PolicyContext for DENY tool."""
    return PolicyContext(
        user_id="user-1",
        tenant_id="tenant-1",
        tool_name="bash",
        arguments={"command": "ls"},
    )


# =============================================================================
# POLICY DECISION TESTS
# =============================================================================


class TestPolicyDecisions:
    """Tests for basic policy decisions."""

    @pytest.mark.asyncio
    async def test_allow_policy_returns_allow(self, engine, mock_registry, ctx_allow):
        """ALLOW tool returns PolicyDecision.ALLOW."""
        with patch(
            "app.services.ai.tool_gateway.policy_engine.tool_registry",
            mock_registry,
        ):
            result = await engine.check_policy(ctx_allow)

        assert result.decision == PolicyDecision.ALLOW
        assert result.requires_approval is False

    @pytest.mark.asyncio
    async def test_deny_policy_returns_deny(self, engine, mock_registry, ctx_deny):
        """DENY tool returns PolicyDecision.DENY."""
        with patch(
            "app.services.ai.tool_gateway.policy_engine.tool_registry",
            mock_registry,
        ):
            result = await engine.check_policy(ctx_deny)

        assert result.decision == PolicyDecision.DENY
        assert result.reason is not None

    @pytest.mark.asyncio
    async def test_ask_policy_returns_ask(self, engine, mock_registry, ctx_ask):
        """ASK tool returns PolicyDecision.ASK with approval message."""
        with patch(
            "app.services.ai.tool_gateway.policy_engine.tool_registry",
            mock_registry,
        ):
            result = await engine.check_policy(ctx_ask)

        assert result.decision == PolicyDecision.ASK
        assert result.requires_approval is True
        assert result.approval_message is not None

    @pytest.mark.asyncio
    async def test_unknown_tool_returns_deny(self, engine, mock_registry):
        """Unknown tool name returns DENY."""
        ctx = PolicyContext(
            user_id="user-1",
            tenant_id="tenant-1",
            tool_name="nonexistent_tool",
            arguments={},
        )
        with patch(
            "app.services.ai.tool_gateway.policy_engine.tool_registry",
            mock_registry,
        ):
            result = await engine.check_policy(ctx)

        assert result.decision == PolicyDecision.DENY
        assert "not found" in result.reason.lower()


# =============================================================================
# TENANT OVERRIDE TESTS
# =============================================================================


class TestTenantOverrides:
    """Tests for tenant-specific policy overrides."""

    @pytest.mark.asyncio
    async def test_tenant_override_deny_to_allow(self, engine, mock_registry, ctx_deny):
        """Tenant override can change DENY to ALLOW."""
        engine.set_tenant_override("tenant-1", "bash", ToolPolicy.ALLOW)

        with patch(
            "app.services.ai.tool_gateway.policy_engine.tool_registry",
            mock_registry,
        ):
            result = await engine.check_policy(ctx_deny)

        assert result.decision == PolicyDecision.ALLOW

    @pytest.mark.asyncio
    async def test_tenant_override_allow_to_deny(self, engine, mock_registry, ctx_allow):
        """Tenant override can change ALLOW to DENY."""
        engine.set_tenant_override("tenant-1", "search_jurisprudencia", ToolPolicy.DENY)

        with patch(
            "app.services.ai.tool_gateway.policy_engine.tool_registry",
            mock_registry,
        ):
            result = await engine.check_policy(ctx_allow)

        assert result.decision == PolicyDecision.DENY

    @pytest.mark.asyncio
    async def test_tenant_override_does_not_affect_other_tenants(
        self, engine, mock_registry
    ):
        """Override for tenant-1 does not affect tenant-2."""
        engine.set_tenant_override("tenant-1", "bash", ToolPolicy.ALLOW)

        ctx_other_tenant = PolicyContext(
            user_id="user-2",
            tenant_id="tenant-2",
            tool_name="bash",
            arguments={"command": "ls"},
        )

        with patch(
            "app.services.ai.tool_gateway.policy_engine.tool_registry",
            mock_registry,
        ):
            result = await engine.check_policy(ctx_other_tenant)

        assert result.decision == PolicyDecision.DENY

    def test_get_tenant_overrides(self, engine):
        """get_tenant_overrides returns correct overrides."""
        engine.set_tenant_override("t1", "tool_a", ToolPolicy.ALLOW)
        engine.set_tenant_override("t1", "tool_b", ToolPolicy.DENY)

        overrides = engine.get_tenant_overrides("t1")
        assert overrides["tool_a"] == ToolPolicy.ALLOW
        assert overrides["tool_b"] == ToolPolicy.DENY

    def test_get_tenant_overrides_empty(self, engine):
        """Empty dict for unknown tenant."""
        assert engine.get_tenant_overrides("unknown") == {}

    def test_remove_tenant_override(self, engine):
        """remove_tenant_override removes the override."""
        engine.set_tenant_override("t1", "bash", ToolPolicy.ALLOW)
        assert engine.remove_tenant_override("t1", "bash") is True

        overrides = engine.get_tenant_overrides("t1")
        assert "bash" not in overrides

    def test_remove_nonexistent_override(self, engine):
        """Removing nonexistent override returns False."""
        assert engine.remove_tenant_override("t1", "nonexistent") is False


# =============================================================================
# RATE LIMITING TESTS
# =============================================================================


class TestRateLimiting:
    """Tests for rate limiting enforcement."""

    @pytest.mark.asyncio
    async def test_rate_limit_blocks_when_exceeded(self, engine, mock_registry):
        """Tool is blocked when rate limit is exceeded."""
        engine.set_rate_limit("rate_limited_tool", 2)  # 2 calls per minute

        ctx = PolicyContext(
            user_id="user-1",
            tenant_id="tenant-1",
            tool_name="rate_limited_tool",
            arguments={},
        )

        # Record 2 calls to fill the limit
        engine.record_call(ctx)
        engine.record_call(ctx)

        with patch(
            "app.services.ai.tool_gateway.policy_engine.tool_registry",
            mock_registry,
        ):
            result = await engine.check_policy(ctx)

        assert result.decision == PolicyDecision.RATE_LIMITED

    @pytest.mark.asyncio
    async def test_rate_limit_allows_under_limit(self, engine, mock_registry):
        """Tool is allowed when under rate limit."""
        engine.set_rate_limit("rate_limited_tool", 10)

        ctx = PolicyContext(
            user_id="user-1",
            tenant_id="tenant-1",
            tool_name="rate_limited_tool",
            arguments={},
        )

        # Record 1 call (under limit of 10)
        engine.record_call(ctx)

        with patch(
            "app.services.ai.tool_gateway.policy_engine.tool_registry",
            mock_registry,
        ):
            result = await engine.check_policy(ctx)

        assert result.decision == PolicyDecision.ALLOW

    def test_rate_limit_status(self, engine):
        """Rate limit status reports correct values."""
        engine.set_rate_limit("test_tool", 5)

        ctx = PolicyContext(
            user_id="u1",
            tenant_id="t1",
            tool_name="test_tool",
            arguments={},
        )
        engine.record_call(ctx)
        engine.record_call(ctx)

        status = engine.get_rate_limit_status("test_tool", "t1")
        assert status["limit"] == 5
        assert status["current"] == 2
        assert status["remaining"] == 3
        assert status["limited"] is False

    def test_rate_limit_status_no_limit(self, engine):
        """No rate limit returns unlimited status."""
        status = engine.get_rate_limit_status("no_limit_tool", "t1")
        assert status["limited"] is False
        assert status["limit"] is None

    def test_remove_rate_limit(self, engine):
        """Rate limit can be removed."""
        engine.set_rate_limit("tool_a", 5)
        assert engine.remove_rate_limit("tool_a") is True
        assert engine.remove_rate_limit("tool_a") is False  # Already removed


# =============================================================================
# RECORD CALL / AUDIT LOG TESTS
# =============================================================================


class TestRecordCall:
    """Tests for call recording and audit log."""

    def test_record_call_creates_audit_entry(self, engine):
        """record_call adds entry to audit log."""
        ctx = PolicyContext(
            user_id="user-1",
            tenant_id="tenant-1",
            tool_name="search_jurisprudencia",
            arguments={"query": "test"},
            session_id="sess-1",
            case_id="case-1",
        )

        engine.record_call(ctx)

        logs = engine.get_audit_log()
        assert len(logs) == 1
        assert logs[0]["tool_name"] == "search_jurisprudencia"
        assert logs[0]["user_id"] == "user-1"
        assert logs[0]["tenant_id"] == "tenant-1"
        assert logs[0]["session_id"] == "sess-1"

    def test_audit_log_filtering(self, engine):
        """Audit log can be filtered by tenant, user, tool."""
        for i in range(5):
            engine.record_call(PolicyContext(
                user_id=f"user-{i % 2}",
                tenant_id=f"tenant-{i % 3}",
                tool_name=f"tool-{i % 2}",
                arguments={},
            ))

        by_tenant = engine.get_audit_log(tenant_id="tenant-0")
        assert all(l["tenant_id"] == "tenant-0" for l in by_tenant)

        by_user = engine.get_audit_log(user_id="user-0")
        assert all(l["user_id"] == "user-0" for l in by_user)

        by_tool = engine.get_audit_log(tool_name="tool-1")
        assert all(l["tool_name"] == "tool-1" for l in by_tool)

    def test_audit_log_limit(self, engine):
        """Audit log respects limit parameter."""
        for i in range(10):
            engine.record_call(PolicyContext(
                user_id="u1",
                tenant_id="t1",
                tool_name="tool",
                arguments={},
            ))

        logs = engine.get_audit_log(limit=3)
        assert len(logs) == 3

    def test_audit_log_trimming(self, engine):
        """Audit log trims to max size."""
        engine._max_audit_log_size = 5

        for i in range(10):
            engine.record_call(PolicyContext(
                user_id="u1",
                tenant_id="t1",
                tool_name="tool",
                arguments={},
            ))

        assert len(engine._audit_log) <= 5

    def test_clear_audit_log_all(self, engine):
        """clear_audit_log removes all entries."""
        for i in range(5):
            engine.record_call(PolicyContext(
                user_id="u1",
                tenant_id="t1",
                tool_name="tool",
                arguments={},
            ))

        removed = engine.clear_audit_log()
        assert removed == 5
        assert len(engine.get_audit_log()) == 0

    def test_clear_audit_log_by_tenant(self, engine):
        """clear_audit_log can filter by tenant."""
        engine.record_call(PolicyContext(
            user_id="u1", tenant_id="t1", tool_name="tool", arguments={},
        ))
        engine.record_call(PolicyContext(
            user_id="u1", tenant_id="t2", tool_name="tool", arguments={},
        ))

        removed = engine.clear_audit_log(tenant_id="t1")
        assert removed == 1

        logs = engine.get_audit_log()
        assert len(logs) == 1
        assert logs[0]["tenant_id"] == "t2"


# =============================================================================
# POLICY RESULT DATACLASS TESTS
# =============================================================================


class TestPolicyResult:
    """Tests for PolicyResult dataclass."""

    def test_policy_result_defaults(self):
        result = PolicyResult(decision=PolicyDecision.ALLOW)
        assert result.reason is None
        assert result.requires_approval is False
        assert result.approval_message is None

    def test_policy_result_ask(self):
        result = PolicyResult(
            decision=PolicyDecision.ASK,
            requires_approval=True,
            approval_message="Please approve",
        )
        assert result.requires_approval is True
        assert result.approval_message == "Please approve"


class TestPolicyContext:
    """Tests for PolicyContext dataclass."""

    def test_context_optional_fields(self):
        ctx = PolicyContext(
            user_id="u1",
            tenant_id="t1",
            tool_name="tool",
            arguments={},
        )
        assert ctx.session_id is None
        assert ctx.case_id is None
