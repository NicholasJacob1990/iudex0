from unittest.mock import AsyncMock

import pytest

from app.services.ai.claude_agent.permissions import PermissionManager, PermissionRule


@pytest.mark.asyncio
async def test_web_profile_hard_denies_shell_tool(monkeypatch):
    manager = PermissionManager(
        db=AsyncMock(),
        user_id="user-1",
        security_profile="web",
    )

    async def _fake_rules():
        return []

    monkeypatch.setattr(manager, "_get_rules", _fake_rules)

    result = await manager.check("bash", {"command": "ls"})
    assert result.decision == "deny"


@pytest.mark.asyncio
async def test_server_profile_allows_sandbox_tool_when_default_is_deny(monkeypatch):
    manager = PermissionManager(
        db=AsyncMock(),
        user_id="user-1",
        security_profile="server",
    )

    async def _fake_rules():
        return [
            PermissionRule(
                tool_name="bash",
                mode="deny",
                scope="system",
                is_system=True,
            )
        ]

    monkeypatch.setattr(manager, "_get_rules", _fake_rules)

    result = await manager.check("bash", {"command": "ls"})
    assert result.decision == "allow"


@pytest.mark.asyncio
async def test_server_profile_keeps_explicit_user_deny(monkeypatch):
    manager = PermissionManager(
        db=AsyncMock(),
        user_id="user-1",
        security_profile="server",
    )

    async def _fake_rules():
        return [
            PermissionRule(
                id="rule-1",
                tool_name="bash",
                mode="deny",
                scope="global",
                is_system=False,
            )
        ]

    monkeypatch.setattr(manager, "_get_rules", _fake_rules)

    result = await manager.check("bash", {"command": "ls"})
    assert result.decision == "deny"
