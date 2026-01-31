"""
Policy Engine - Enforces tool execution policies.

Policies:
- allow: Auto-execute without user approval
- ask: Request user approval before execution
- deny: Block execution unless explicitly overridden

Supports:
- Per-tool policies
- Per-tenant overrides
- Rate limiting
- Audit logging
"""

from typing import Any, Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from loguru import logger

from .tool_registry import ToolPolicy, ToolRegistry, tool_registry


class PolicyDecision(str, Enum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"
    RATE_LIMITED = "rate_limited"


@dataclass
class PolicyContext:
    """Context for policy evaluation."""

    user_id: str
    tenant_id: str
    tool_name: str
    arguments: Dict[str, Any]
    session_id: Optional[str] = None
    case_id: Optional[str] = None


@dataclass
class PolicyResult:
    """Result of policy evaluation."""

    decision: PolicyDecision
    reason: Optional[str] = None
    requires_approval: bool = False
    approval_message: Optional[str] = None


class PolicyEngine:
    """Enforces tool execution policies."""

    def __init__(self):
        self._tenant_overrides: Dict[str, Dict[str, ToolPolicy]] = {}
        self._rate_limits: Dict[str, int] = {}  # tool_name -> calls per minute
        self._call_counts: Dict[str, List[datetime]] = {}  # key -> timestamps
        self._audit_log: List[Dict[str, Any]] = []
        self._max_audit_log_size: int = 10000  # Prevent unbounded growth

    def set_tenant_override(
        self,
        tenant_id: str,
        tool_name: str,
        policy: ToolPolicy,
    ) -> None:
        """Set a tenant-specific policy override for a tool."""
        if tenant_id not in self._tenant_overrides:
            self._tenant_overrides[tenant_id] = {}
        self._tenant_overrides[tenant_id][tool_name] = policy
        logger.info(f"Set override for {tenant_id}/{tool_name}: {policy.value}")

    def remove_tenant_override(self, tenant_id: str, tool_name: str) -> bool:
        """Remove a tenant-specific policy override."""
        if tenant_id in self._tenant_overrides:
            if tool_name in self._tenant_overrides[tenant_id]:
                del self._tenant_overrides[tenant_id][tool_name]
                logger.info(f"Removed override for {tenant_id}/{tool_name}")
                return True
        return False

    def get_tenant_overrides(self, tenant_id: str) -> Dict[str, ToolPolicy]:
        """Get all policy overrides for a tenant."""
        return self._tenant_overrides.get(tenant_id, {}).copy()

    def set_rate_limit(self, tool_name: str, calls_per_minute: int) -> None:
        """Set rate limit for a tool."""
        self._rate_limits[tool_name] = calls_per_minute
        logger.info(f"Set rate limit for {tool_name}: {calls_per_minute}/min")

    def remove_rate_limit(self, tool_name: str) -> bool:
        """Remove rate limit for a tool."""
        if tool_name in self._rate_limits:
            del self._rate_limits[tool_name]
            return True
        return False

    async def check_policy(self, context: PolicyContext) -> PolicyResult:
        """Check if a tool execution is allowed."""
        tool = tool_registry.get(context.tool_name)
        if not tool:
            logger.warning(f"Policy check failed: tool not found: {context.tool_name}")
            return PolicyResult(
                decision=PolicyDecision.DENY,
                reason=f"Tool not found: {context.tool_name}",
            )

        # Check rate limit first
        if self._is_rate_limited(context.tool_name, context.tenant_id):
            logger.warning(f"Rate limited: {context.tenant_id}/{context.tool_name}")
            return PolicyResult(
                decision=PolicyDecision.RATE_LIMITED,
                reason="Rate limit exceeded. Please try again later.",
            )

        # Get effective policy (tenant override > tool default)
        policy = self._get_effective_policy(
            context.tenant_id,
            context.tool_name,
            tool.policy,
        )

        # Map policy to decision
        if policy == ToolPolicy.DENY:
            logger.info(f"Tool denied: {context.tool_name} for tenant {context.tenant_id}")
            return PolicyResult(
                decision=PolicyDecision.DENY,
                reason=f"Tool '{context.tool_name}' is denied for this tenant",
            )

        if policy == ToolPolicy.ASK:
            return PolicyResult(
                decision=PolicyDecision.ASK,
                requires_approval=True,
                approval_message=self._generate_approval_message(tool, context),
            )

        return PolicyResult(decision=PolicyDecision.ALLOW)

    def _get_effective_policy(
        self,
        tenant_id: str,
        tool_name: str,
        default: ToolPolicy,
    ) -> ToolPolicy:
        """Get the effective policy considering tenant overrides."""
        overrides = self._tenant_overrides.get(tenant_id, {})
        return overrides.get(tool_name, default)

    def _is_rate_limited(self, tool_name: str, tenant_id: str) -> bool:
        """Check if a tool is rate limited for a tenant."""
        limit = self._rate_limits.get(tool_name)
        if not limit:
            return False

        key = f"{tenant_id}:{tool_name}"
        now = datetime.now()

        # Clean old entries (older than 1 minute)
        if key in self._call_counts:
            self._call_counts[key] = [
                ts for ts in self._call_counts[key]
                if (now - ts).total_seconds() < 60
            ]
        else:
            self._call_counts[key] = []

        return len(self._call_counts[key]) >= limit

    def record_call(self, context: PolicyContext) -> None:
        """Record a tool call for rate limiting and audit."""
        key = f"{context.tenant_id}:{context.tool_name}"
        now = datetime.now()

        # Record for rate limiting
        if key not in self._call_counts:
            self._call_counts[key] = []
        self._call_counts[key].append(now)

        # Audit log entry
        audit_entry = {
            "timestamp": now.isoformat(),
            "tool_name": context.tool_name,
            "user_id": context.user_id,
            "tenant_id": context.tenant_id,
            "session_id": context.session_id,
            "case_id": context.case_id,
            "arguments_preview": str(context.arguments)[:200],
        }
        self._audit_log.append(audit_entry)

        # Trim audit log if too large
        if len(self._audit_log) > self._max_audit_log_size:
            self._audit_log = self._audit_log[-self._max_audit_log_size:]

        logger.debug(f"Recorded call: {context.tool_name} by {context.user_id}")

    def _generate_approval_message(self, tool, context: PolicyContext) -> str:
        """Generate a user-friendly approval message."""
        return (
            f"O agente quer executar '{tool.name}': "
            f"{tool.description[:100]}..."
        )

    def get_audit_log(
        self,
        tenant_id: Optional[str] = None,
        user_id: Optional[str] = None,
        tool_name: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Get audit log entries with optional filtering."""
        logs = self._audit_log

        if tenant_id:
            logs = [l for l in logs if l.get("tenant_id") == tenant_id]
        if user_id:
            logs = [l for l in logs if l.get("user_id") == user_id]
        if tool_name:
            logs = [l for l in logs if l.get("tool_name") == tool_name]

        return logs[-limit:]

    def clear_audit_log(self, tenant_id: Optional[str] = None) -> int:
        """Clear audit log entries. Returns count of removed entries."""
        if tenant_id:
            original_count = len(self._audit_log)
            self._audit_log = [
                l for l in self._audit_log
                if l.get("tenant_id") != tenant_id
            ]
            return original_count - len(self._audit_log)
        else:
            count = len(self._audit_log)
            self._audit_log = []
            return count

    def get_rate_limit_status(
        self,
        tool_name: str,
        tenant_id: str,
    ) -> Dict[str, Any]:
        """Get current rate limit status for a tool/tenant combination."""
        limit = self._rate_limits.get(tool_name)
        if not limit:
            return {"limited": False, "limit": None, "current": 0}

        key = f"{tenant_id}:{tool_name}"
        now = datetime.now()

        # Count recent calls
        if key in self._call_counts:
            recent_calls = [
                ts for ts in self._call_counts[key]
                if (now - ts).total_seconds() < 60
            ]
            current = len(recent_calls)
        else:
            current = 0

        return {
            "limited": current >= limit,
            "limit": limit,
            "current": current,
            "remaining": max(0, limit - current),
        }


# Global policy engine
policy_engine = PolicyEngine()
