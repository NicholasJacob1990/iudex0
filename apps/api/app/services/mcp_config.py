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

