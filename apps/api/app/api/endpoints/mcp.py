from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException

from app.core.security import get_current_user

from app.services.mcp_hub import mcp_hub, MCPHubError


router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("/servers")
async def list_servers() -> Dict[str, Any]:
    return {"servers": mcp_hub.list_servers()}


@router.post("/tools/search")
async def mcp_tool_search(
    query: str = Body(..., embed=True),
    server_labels: Optional[List[str]] = Body(default=None, embed=True),
    limit: int = Body(default=20, embed=True, ge=1, le=100),
) -> Dict[str, Any]:
    try:
        return await mcp_hub.tool_search(query, server_labels=server_labels, limit=limit)
    except MCPHubError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/tools/call")
async def mcp_tool_call(
    server_label: str = Body(..., embed=True),
    tool_name: str = Body(..., embed=True),
    arguments: Dict[str, Any] = Body(default_factory=dict, embed=True),
) -> Dict[str, Any]:
    try:
        return await mcp_hub.tool_call(server_label, tool_name, arguments)
    except MCPHubError as e:
        raise HTTPException(status_code=400, detail=str(e))
