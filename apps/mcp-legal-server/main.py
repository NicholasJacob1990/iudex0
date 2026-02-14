from __future__ import annotations

from typing import Any, Dict
import inspect
import uuid

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from app.services.ai.observability.audit_log import get_tool_audit_log
from app.services.ai.shared.mcp_contracts import get_mcp_contracts
from app.services.ai.tool_gateway.tool_registry import tool_registry


class JsonRpcRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: Any = None
    method: str
    params: Dict[str, Any] = {}


app = FastAPI(title="Iudex MCP Legal Server", version="0.1.0")
contracts = get_mcp_contracts()
audit_log = get_tool_audit_log()


@app.on_event("startup")
async def _startup() -> None:
    tool_registry.initialize()


@app.get("/health")
async def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "tools_count": len(tool_registry.list_names()),
        "contracts": contracts.snapshot(),
    }


@app.post("/rpc")
async def rpc(
    body: JsonRpcRequest,
    x_tenant_id: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
    x_session_id: str | None = Header(default=None),
) -> Dict[str, Any]:
    tenant_id = (x_tenant_id or "default").strip()
    user_id = (x_user_id or "").strip() or None
    session_id = (x_session_id or "").strip() or None

    try:
        result = await _dispatch(
            method=body.method,
            params=body.params or {},
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
        )
        return {"jsonrpc": "2.0", "id": body.id, "result": result}
    except Exception as exc:
        return {
            "jsonrpc": "2.0",
            "id": body.id,
            "error": {"code": -32000, "message": str(exc)},
        }


async def _dispatch(
    *,
    method: str,
    params: Dict[str, Any],
    tenant_id: str,
    user_id: str | None,
    session_id: str | None,
) -> Dict[str, Any]:
    normalized = (method or "").strip().lower()
    if normalized in {"tools/list", "tools.list"}:
        return _tools_list(tenant_id=tenant_id)
    if normalized in {"tools/call", "tools.call"}:
        tool_name = str(params.get("name") or "").strip()
        arguments = params.get("arguments") or {}
        if not tool_name:
            raise HTTPException(status_code=400, detail="Missing tool name")
        if not isinstance(arguments, dict):
            raise HTTPException(status_code=400, detail="Tool arguments must be an object")
        return await _tools_call(
            tool_name=tool_name,
            arguments=arguments,
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
        )
    raise HTTPException(status_code=404, detail=f"Unsupported MCP method: {method}")


def _tools_list(*, tenant_id: str) -> Dict[str, Any]:
    tools = []
    for tool in tool_registry.list_tools():
        acl = contracts.check_acl(tenant_id, "legal", tool.name)
        if not acl.allowed:
            continue
        tools.append(
            {
                "name": tool.name,
                "description": tool.description,
                "inputSchema": tool.input_schema,
            }
        )
    return {"tools": tools}


async def _tools_call(
    *,
    tool_name: str,
    arguments: Dict[str, Any],
    tenant_id: str,
    user_id: str | None,
    session_id: str | None,
) -> Dict[str, Any]:
    full_name = f"legal.{tool_name}"
    acl = contracts.check_acl(tenant_id, "legal", tool_name)
    if not acl.allowed:
        audit_log.record_permission_decision(
            tool_name=full_name,
            decision="deny",
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
            source="mcp_standalone_acl",
            provider="mcp",
            tool_input=arguments,
            metadata={"reason": acl.reason},
        )
        raise HTTPException(status_code=403, detail="Tool blocked by ACL")

    rate = contracts.consume_rate_limit(tenant_id, "legal", tool_name)
    if not rate.allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Retry in {rate.retry_after_seconds}s",
        )

    cached = contracts.get_cached_result(
        tenant_id=tenant_id,
        server_label="legal",
        tool_name=tool_name,
        arguments=arguments,
    )
    if cached is not None:
        audit_log.record_tool_execution(
            tool_name=full_name,
            success=True,
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
            provider="mcp",
            permission_decision="allow",
            tool_input=arguments,
            metadata={"cached": True},
        )
        return cached.get("value", cached)

    tool_def = tool_registry.get(tool_name)
    if not tool_def:
        raise HTTPException(status_code=404, detail=f"Unknown tool: {tool_name}")

    payload = dict(arguments or {})
    signature = inspect.signature(tool_def.function)
    if "tenant_id" in signature.parameters and "tenant_id" not in payload:
        payload["tenant_id"] = tenant_id
    if "user_id" in signature.parameters and "user_id" not in payload and user_id:
        payload["user_id"] = user_id
    if "session_id" in signature.parameters and "session_id" not in payload and session_id:
        payload["session_id"] = session_id
    if "request_id" in signature.parameters and "request_id" not in payload:
        payload["request_id"] = str(uuid.uuid4())

    result = tool_def.function(**payload)
    if inspect.isawaitable(result):
        result = await result

    normalized = result if isinstance(result, dict) else {"result": result}
    contracts.set_cached_result(
        tenant_id=tenant_id,
        server_label="legal",
        tool_name=tool_name,
        arguments=arguments,
        value={"value": normalized},
    )
    audit_log.record_tool_execution(
        tool_name=full_name,
        success=True,
        tenant_id=tenant_id,
        user_id=user_id,
        session_id=session_id,
        provider="mcp",
        permission_decision="allow",
        tool_input=arguments,
        metadata={"cached": False},
    )
    return normalized
