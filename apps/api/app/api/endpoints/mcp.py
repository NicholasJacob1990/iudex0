from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.services.mcp_hub import mcp_hub, MCPHubError
from app.services.ai.tool_gateway import (
    mcp_server,
    handle_mcp_http,
    handle_mcp_sse,
    tool_registry,
    policy_engine,
)


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


# =============================================================================
# Tool Gateway MCP Endpoints
# =============================================================================


@router.post("/gateway/rpc")
async def mcp_gateway_rpc(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    MCP JSON-RPC endpoint for Tool Gateway.

    This is the main entry point for all tool calls from any provider.
    """
    body = await request.json()

    context = {
        "user_id": str(current_user.id),
        "tenant_id": current_user.tenant_id or "default",
        "session_id": request.headers.get("X-Session-ID"),
    }

    result = await handle_mcp_http(body, context)
    return result


@router.get("/gateway/sse")
async def mcp_gateway_sse(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """
    MCP SSE endpoint for real-time events (approval requests, etc.)
    """
    context = {
        "user_id": str(current_user.id),
        "tenant_id": current_user.tenant_id or "default",
    }

    return await handle_mcp_sse(request, context)


@router.get("/gateway/tools")
async def list_gateway_tools(
    category: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    """
    List all tools available in the Tool Gateway.
    """
    tool_registry.initialize()

    from app.services.ai.tool_gateway.tool_registry import ToolCategory

    cat = None
    if category:
        try:
            cat = ToolCategory(category)
        except ValueError:
            pass

    tools = tool_registry.list_tools(category=cat)

    return {
        "total": len(tools),
        "tools": [
            {
                "name": t.name,
                "description": t.description[:200],
                "category": t.category.value,
                "policy": t.policy.value,
            }
            for t in tools
        ],
    }


@router.post("/gateway/approve/{approval_id}")
async def approve_tool_execution(
    approval_id: str,
    approved: bool = True,
    current_user: User = Depends(get_current_user),
):
    """
    Approve or deny a pending tool execution.
    """
    success = mcp_server.approve_tool(approval_id, approved)

    return {
        "success": success,
        "approval_id": approval_id,
        "approved": approved,
    }


@router.get("/gateway/audit")
async def get_audit_log(
    limit: int = 100,
    current_user: User = Depends(get_current_user),
):
    """
    Get audit log of tool executions.
    """
    tenant_id = current_user.tenant_id or "default"
    logs = policy_engine.get_audit_log(tenant_id=tenant_id, limit=limit)

    return {
        "total": len(logs),
        "logs": logs,
    }
