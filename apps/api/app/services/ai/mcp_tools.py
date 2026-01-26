from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from app.services.mcp_hub import mcp_hub, MCPHubError


MCP_TOOL_SEARCH_NAME = "mcp_tool_search"
MCP_TOOL_CALL_NAME = "mcp_tool_call"


def _normalize_server_labels(value: Any) -> Optional[List[str]]:
    if not isinstance(value, list):
        return None
    labels = [str(x).strip() for x in value if str(x).strip()]
    return labels or None


def get_openai_mcp_function_tools() -> List[Dict[str, Any]]:
    """
    OpenAI ChatCompletions tool schema for the two MCP helper tools.

    We intentionally keep the tool surface minimal to avoid stuffing the model with
    thousands of MCP tool definitions.
    """
    return [
        {
            "type": "function",
            "function": {
                "name": MCP_TOOL_SEARCH_NAME,
                "description": (
                    "Search available MCP tools across configured MCP servers. "
                    "Use this first to discover the right tool, then call mcp_tool_call."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query for tool name/description."},
                        "server_labels": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional allowlist of MCP server labels to search.",
                        },
                        "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": MCP_TOOL_CALL_NAME,
                "description": "Execute a tool on a specific MCP server.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "server_label": {"type": "string", "description": "MCP server label."},
                        "tool_name": {"type": "string", "description": "Tool name to call."},
                        "arguments": {"type": "object", "description": "Tool arguments (JSON object)."},
                    },
                    "required": ["server_label", "tool_name", "arguments"],
                },
            },
        },
    ]


def get_anthropic_mcp_tools() -> List[Dict[str, Any]]:
    """
    Anthropic tool schema for the same two MCP helper tools.
    """
    return [
        {
            "name": MCP_TOOL_SEARCH_NAME,
            "description": (
                "Search available MCP tools across configured MCP servers. "
                "Use this first to discover the right tool, then call mcp_tool_call."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query for tool name/description."},
                    "server_labels": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional allowlist of MCP server labels to search.",
                    },
                    "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
                },
                "required": ["query"],
            },
        },
        {
            "name": MCP_TOOL_CALL_NAME,
            "description": "Execute a tool on a specific MCP server.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "server_label": {"type": "string", "description": "MCP server label."},
                    "tool_name": {"type": "string", "description": "Tool name to call."},
                    "arguments": {"type": "object", "description": "Tool arguments (JSON object)."},
                },
                "required": ["server_label", "tool_name", "arguments"],
            },
        },
    ]


async def execute_mcp_tool(
    tool_name: str,
    arguments: Dict[str, Any],
    *,
    allowed_server_labels: Optional[List[str]] = None,
) -> Dict[str, Any]:
    if tool_name == MCP_TOOL_SEARCH_NAME:
        query = str(arguments.get("query") or "")
        server_labels = _normalize_server_labels(arguments.get("server_labels"))
        if allowed_server_labels:
            if server_labels is None:
                server_labels = list(allowed_server_labels)
            else:
                allowed = set(allowed_server_labels)
                server_labels = [s for s in server_labels if s in allowed]
                if not server_labels:
                    raise MCPHubError("No allowed MCP servers for this search.")
        limit_raw = arguments.get("limit", 20)
        try:
            limit = int(limit_raw)
        except (TypeError, ValueError):
            limit = 20
        return await mcp_hub.tool_search(query, server_labels=server_labels, limit=limit)
    if tool_name == MCP_TOOL_CALL_NAME:
        server_label = str(arguments.get("server_label") or "")
        if allowed_server_labels and server_label not in set(allowed_server_labels):
            raise MCPHubError(f"MCP server not allowed for this request: {server_label}")
        mcp_tool_name = str(arguments.get("tool_name") or "")
        tool_args = arguments.get("arguments") or {}
        if not isinstance(tool_args, dict):
            tool_args = {}
        return await mcp_hub.tool_call(server_label, mcp_tool_name, tool_args)
    raise MCPHubError(f"Unknown MCP helper tool: {tool_name}")


def _safe_json_loads(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return {}
    text = value.strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


async def run_openai_tool_loop(
    *,
    client: Any,
    model: str,
    system_instruction: str,
    user_prompt: str,
    max_tokens: int,
    temperature: float,
    allowed_server_labels: Optional[List[str]] = None,
    max_rounds: int = 6,
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Non-streaming tool loop for OpenAI ChatCompletions.

    Returns: (final_text, tool_trace)
    tool_trace is a list of {name, arguments, result_preview}.
    """
    tools = get_openai_mcp_function_tools()
    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": system_instruction},
        {"role": "user", "content": user_prompt},
    ]
    tool_trace: List[Dict[str, Any]] = []

    for round_idx in range(max_rounds):
        resp = await client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            max_tokens=max_tokens,
            temperature=temperature,
        )
        choice = resp.choices[0]
        msg = choice.message
        content = getattr(msg, "content", None)
        tool_calls = getattr(msg, "tool_calls", None)

        if tool_calls:
            messages.append(
                {
                    "role": "assistant",
                    "content": content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": getattr(tc, "type", "function"),
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in tool_calls
                    ],
                }
            )

            for tc in tool_calls:
                name = tc.function.name
                args = _safe_json_loads(tc.function.arguments)
                try:
                    result = await execute_mcp_tool(
                        name,
                        args,
                        allowed_server_labels=allowed_server_labels,
                    )
                    preview = json.dumps(result, ensure_ascii=False)[:500]
                    tool_trace.append({"name": name, "arguments": args, "result_preview": preview})
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": json.dumps(result, ensure_ascii=False),
                        }
                    )
                except Exception as e:
                    logger.warning(f"MCP tool call failed ({name}): {e}")
                    tool_trace.append({"name": name, "arguments": args, "result_preview": f"ERROR: {e}"})
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": json.dumps({"error": str(e)}, ensure_ascii=False),
                        }
                    )
            continue

        if isinstance(content, str) and content.strip():
            return content, tool_trace
        # If there's no content and no tool call, stop to avoid infinite loop.
        break

    return "Não foi possível concluir a resposta com ferramentas MCP.", tool_trace


async def run_anthropic_tool_loop(
    *,
    client: Any,
    model: str,
    system_instruction: str,
    user_prompt: str,
    max_tokens: int,
    temperature: float,
    allowed_server_labels: Optional[List[str]] = None,
    max_rounds: int = 6,
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Non-streaming tool loop for Anthropic Messages API.

    Returns: (final_text, tool_trace)
    """
    tools = get_anthropic_mcp_tools()
    tool_trace: List[Dict[str, Any]] = []

    # Anthropic expects content blocks for tool usage.
    messages: List[Dict[str, Any]] = [
        {"role": "user", "content": [{"type": "text", "text": user_prompt}]},
    ]

    for _ in range(max_rounds):
        resp = await client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_instruction,
            messages=messages,
            tools=tools,
        )
        content_blocks = getattr(resp, "content", None) or []
        tool_uses = [b for b in content_blocks if getattr(b, "type", None) == "tool_use"]
        text_blocks = [b for b in content_blocks if getattr(b, "type", None) in ("text", "output_text")]

        if tool_uses:
            # Append assistant tool_use blocks as-is
            messages.append({"role": "assistant", "content": content_blocks})

            # Execute tools and respond with tool_result blocks
            tool_results: List[Dict[str, Any]] = []
            for b in tool_uses:
                tool_name = getattr(b, "name", "") or ""
                tool_input = getattr(b, "input", None) or {}
                tool_id = getattr(b, "id", None) or getattr(b, "tool_use_id", None) or ""
                args = tool_input if isinstance(tool_input, dict) else {}
                try:
                    result = await execute_mcp_tool(
                        str(tool_name),
                        args,
                        allowed_server_labels=allowed_server_labels,
                    )
                    preview = json.dumps(result, ensure_ascii=False)[:500]
                    tool_trace.append({"name": tool_name, "arguments": args, "result_preview": preview})
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_id,
                            "content": json.dumps(result, ensure_ascii=False),
                        }
                    )
                except Exception as e:
                    logger.warning(f"MCP tool call failed ({tool_name}): {e}")
                    tool_trace.append({"name": tool_name, "arguments": args, "result_preview": f"ERROR: {e}"})
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_id,
                            "content": json.dumps({"error": str(e)}, ensure_ascii=False),
                        }
                    )

            messages.append({"role": "user", "content": tool_results})
            continue

        if text_blocks:
            text = "".join(getattr(b, "text", "") or "" for b in text_blocks).strip()
            if text:
                return text, tool_trace
        break

    return "Não foi possível concluir a resposta com ferramentas MCP.", tool_trace


def _extract_genai_text_full(resp: Any) -> str:
    try:
        from app.services.ai.genai_utils import extract_genai_text
    except Exception:
        extract_genai_text = None  # type: ignore

    if extract_genai_text:
        text = extract_genai_text(resp) or ""
        if text.strip():
            return text.strip()

    # Fallback: concatenate text parts
    try:
        cands = getattr(resp, "candidates", None) or []
        if not cands:
            return ""
        content = getattr(cands[0], "content", None)
        parts = getattr(content, "parts", None) or []
        out: List[str] = []
        for p in parts:
            t = getattr(p, "text", None)
            if isinstance(t, str) and t:
                out.append(t)
        return "".join(out).strip()
    except Exception:
        return ""


def _extract_genai_function_calls(resp: Any) -> List[Any]:
    try:
        cands = getattr(resp, "candidates", None) or []
        if not cands:
            return []
        content = getattr(cands[0], "content", None)
        parts = getattr(content, "parts", None) or []
        calls: List[Any] = []
        for p in parts:
            fc = getattr(p, "function_call", None)
            if fc is not None:
                calls.append(fc)
        return calls
    except Exception:
        return []


async def run_gemini_tool_loop(
    *,
    client: Any,
    model: str,
    system_instruction: str,
    user_prompt: str,
    max_tokens: int,
    temperature: float,
    allowed_server_labels: Optional[List[str]] = None,
    max_rounds: int = 6,
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Non-streaming tool loop for Google GenAI (Gemini) function calling.

    Returns: (final_text, tool_trace)
    """
    try:
        from google.genai import types
    except Exception:
        return "MCP tools indisponíveis: google-genai não instalado.", []

    tools_schema = get_openai_mcp_function_tools()
    function_decls = [
        types.FunctionDeclaration(
            name=str(t["function"]["name"]),
            description=str(t["function"]["description"]),
            parametersJsonSchema=t["function"]["parameters"],
        )
        for t in tools_schema
    ]
    tools = [types.Tool(function_declarations=function_decls)]

    # Conversation in GenAI uses Content(role, parts). Keep a minimal function-call trace.
    contents: List[Any] = [types.Content(role="user", parts=[types.Part(text=user_prompt)])]
    tool_trace: List[Dict[str, Any]] = []

    for _ in range(max_rounds):
        resp = await client.aio.models.generate_content(
            model=model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                max_output_tokens=max_tokens,
                temperature=temperature,
                tools=tools,
            ),
        )

        calls = _extract_genai_function_calls(resp)
        if not calls:
            text = _extract_genai_text_full(resp)
            if text.strip():
                return text.strip(), tool_trace
            break

        # Echo the function_call(s) as model content, then reply with function_response(s).
        model_parts = [types.Part(function_call=fc) for fc in calls]
        contents.append(types.Content(role="model", parts=model_parts))

        response_parts: List[Any] = []
        for fc in calls:
            name = str(getattr(fc, "name", "") or "")
            args = getattr(fc, "args", None) or {}
            call_id = getattr(fc, "id", None)
            safe_args = args if isinstance(args, dict) else {}
            try:
                result = await execute_mcp_tool(
                    name,
                    safe_args,
                    allowed_server_labels=allowed_server_labels,
                )
                preview = json.dumps(result, ensure_ascii=False)[:500]
                tool_trace.append({"name": name, "arguments": safe_args, "result_preview": preview})
                response_parts.append(
                    types.Part(
                        function_response=types.FunctionResponse(
                            id=call_id,
                            name=name,
                            response=result if isinstance(result, dict) else {"result": result},
                        )
                    )
                )
            except Exception as e:
                logger.warning(f"MCP tool call failed ({name}): {e}")
                tool_trace.append({"name": name, "arguments": safe_args, "result_preview": f"ERROR: {e}"})
                response_parts.append(
                    types.Part(
                        function_response=types.FunctionResponse(
                            id=call_id,
                            name=name,
                            response={"error": str(e)},
                        )
                    )
                )

        contents.append(types.Content(role="user", parts=response_parts))

    return "Não foi possível concluir a resposta com ferramentas MCP.", tool_trace
