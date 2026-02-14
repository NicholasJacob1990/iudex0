"""Security profile policy for tool execution contexts."""

from __future__ import annotations

from enum import Enum
from fnmatch import fnmatch


class SecurityProfile(str, Enum):
    """Execution context profile for permission checks."""

    WEB = "web"
    SERVER = "server"

    @classmethod
    def from_value(cls, value: object) -> "SecurityProfile":
        raw = str(value or "").strip().lower()
        if raw == cls.SERVER.value:
            return cls.SERVER
        return cls.WEB


# WEB profile must hard-block shell/filesystem style tools.
WEB_HARD_DENY_PATTERNS: tuple[str, ...] = (
    "bash",
    "execute_command",
    "execute_*",
    "system_command",
    "system_*",
    "file_*",
    "read_file",
    "write_file",
    "delete_file",
    "filesystem_*",
    "mcp__*bash*",
    "mcp__*shell*",
    "mcp__*execute*",
    "mcp__*filesystem*",
    "mcp__*file*",
)

# SERVER profile can allow these tools when sandbox controls are in place.
SERVER_SANDBOX_TOOL_PATTERNS: tuple[str, ...] = WEB_HARD_DENY_PATTERNS


def matches_tool_pattern(tool_name: str, patterns: tuple[str, ...]) -> bool:
    name = str(tool_name or "").strip()
    if not name:
        return False
    return any(fnmatch(name, pattern) for pattern in patterns)


def is_web_hard_denied_tool(tool_name: str) -> bool:
    return matches_tool_pattern(tool_name, WEB_HARD_DENY_PATTERNS)


def is_server_sandbox_tool(tool_name: str) -> bool:
    return matches_tool_pattern(tool_name, SERVER_SANDBOX_TOOL_PATTERNS)
