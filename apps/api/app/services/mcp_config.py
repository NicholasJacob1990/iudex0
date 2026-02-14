from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class MCPServerConfig:
    label: str
    url: str
    allowed_tools: Optional[List[str]] = None
    # Optional auth: {"type":"bearer","token_env":"ENV_NAME"} or {"type":"header","name":"X-Api-Key","value_env":"ENV"}
    auth: Optional[Dict[str, Any]] = None


def load_mcp_servers_from_env() -> List[MCPServerConfig]:
    """
    Load MCP server connector configs.

    Env:
      - IUDEX_MCP_SERVERS: JSON array:
        [
          {"label":"brave","url":"https://.../mcp","allowed_tools":["search"],"auth":{"type":"bearer","token_env":"BRAVE_MCP_TOKEN"}}
        ]
    """
    raw = (os.getenv("IUDEX_MCP_SERVERS") or "").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    servers: List[MCPServerConfig] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()
        url = str(item.get("url") or item.get("server_url") or "").strip()
        if not label or not url:
            continue
        allowed = item.get("allowed_tools")
        allowed_tools: Optional[List[str]]
        if isinstance(allowed, list):
            allowed_tools = [str(x).strip() for x in allowed if str(x).strip()]
        else:
            allowed_tools = None
        auth = item.get("auth")
        if not isinstance(auth, dict):
            auth = None
        servers.append(MCPServerConfig(label=label, url=url, allowed_tools=allowed_tools, auth=auth))
    return servers


# Built-in MCP servers (always available, no external URL needed)
BUILTIN_MCP_SERVERS = [
    {
        "label": "bnp",
        "name": "Banco Nacional de Precedentes",
        "builtin": True,
        "handler_class": "app.services.mcp_servers.bnp_server.BNPMCPServer",
    },
    {
        "label": "neo4j-graph",
        "name": "Neo4j Legal Knowledge Graph",
        "builtin": True,
        "handler_class": "app.services.mcp_servers.neo4j_server.Neo4jMCPServer",
    },
]


def load_builtin_mcp_servers() -> List[MCPServerConfig]:
    """Load built-in MCP servers that run in-process."""
    servers: List[MCPServerConfig] = []
    for entry in BUILTIN_MCP_SERVERS:
        label = entry.get("label", "")
        # Built-in servers use a special URL scheme to indicate they are in-process
        url = f"builtin://{label}"
        servers.append(
            MCPServerConfig(
                label=label,
                url=url,
                auth={"type": "builtin", "handler_class": entry["handler_class"]},
            )
        )
    return servers


def load_user_mcp_servers(preferences: dict) -> List[MCPServerConfig]:
    """Load MCP servers configured by the user from their preferences."""
    raw = preferences.get("mcp_servers", [])
    servers: List[MCPServerConfig] = []
    for entry in raw:
        if not isinstance(entry, dict) or not entry.get("label") or not entry.get("url"):
            continue
        url = entry["url"]
        # Security: enforce HTTPS in production (allow localhost for dev)
        if not url.startswith("https://") and not url.startswith("http://localhost"):
            continue
        allowed = entry.get("allowed_tools")
        allowed_tools: Optional[List[str]]
        if isinstance(allowed, list):
            allowed_tools = [str(x).strip() for x in allowed if str(x).strip()]
        else:
            allowed_tools = None
        auth = entry.get("auth")
        if not isinstance(auth, dict):
            auth = None
        servers.append(MCPServerConfig(
            label=f"user_{entry['label']}",
            url=url,
            allowed_tools=allowed_tools,
            auth=auth,
        ))
    return servers

