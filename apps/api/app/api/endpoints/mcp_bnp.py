"""BNP (Banco Nacional de Precedentes) MCP endpoint.

Exposes the BNP MCP server as a JSON-RPC HTTP endpoint so it can be
consumed by the MCPHub like any other external MCP server.
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Request

from app.services.mcp_servers.bnp_server import BNPMCPServer

router = APIRouter(prefix="/mcp/bnp", tags=["mcp-bnp"])
_server = BNPMCPServer()


@router.post("/rpc")
async def bnp_rpc(request: Request) -> Dict[str, Any]:
    """JSON-RPC endpoint for the BNP MCP server."""
    body = await request.json()
    method = body.get("method", "")
    params = body.get("params", {})
    result = await _server.handle_request(method, params)
    return {"jsonrpc": "2.0", "id": body.get("id", 1), "result": result}
