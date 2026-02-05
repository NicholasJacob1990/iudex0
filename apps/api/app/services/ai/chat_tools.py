"""
Chat Tools — Native function calling for agent models in chat stream.

Provides tool definitions and execution for OpenAI/Claude/Gemini providers
without requiring external MCP servers. Uses existing internal services directly.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger


# ---------------------------------------------------------------------------
# Tool definitions (subset useful for chat context)
# ---------------------------------------------------------------------------

CHAT_TOOLS: List[Dict[str, Any]] = [
    {
        "name": "web_search",
        "description": (
            "Pesquisa na web. Use para buscar informações atuais, jurisprudência, "
            "notícias, doutrina ou qualquer tema que precise de dados atualizados."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Query de busca"},
                "search_type": {
                    "type": "string",
                    "enum": ["general", "legal"],
                    "default": "general",
                    "description": "Tipo: general ou legal (fontes jurídicas)",
                },
                "max_results": {
                    "type": "integer",
                    "default": 8,
                    "description": "Número máximo de resultados",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_jurisprudencia",
        "description": (
            "Pesquisa jurisprudência em base local (STF, STJ, TRFs, TJs). "
            "Retorna precedentes, ementas e decisões relevantes."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Termos de busca"},
                "court": {
                    "type": "string",
                    "description": "Tribunal específico (STF, STJ, etc). Vazio = todos.",
                },
                "limit": {"type": "integer", "default": 10},
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_legislacao",
        "description": (
            "Pesquisa legislação (leis, decretos, portarias). "
            "Retorna textos legais vigentes e informações normativas."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Termos de busca ou número da lei"},
                "tipo": {
                    "type": "string",
                    "description": "Tipo: lei, decreto, portaria, etc. Vazio = todos.",
                },
                "limit": {"type": "integer", "default": 10},
            },
            "required": ["query"],
        },
    },
]

CHAT_TOOL_NAMES = {t["name"] for t in CHAT_TOOLS}


# ---------------------------------------------------------------------------
# Format helpers — convert to provider-specific schemas
# ---------------------------------------------------------------------------

def get_openai_chat_tools() -> List[Dict[str, Any]]:
    """Tool definitions in OpenAI function-calling format."""
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["parameters"],
            },
        }
        for t in CHAT_TOOLS
    ]


def get_anthropic_chat_tools() -> List[Dict[str, Any]]:
    """Tool definitions in Anthropic tool_use format."""
    return [
        {
            "name": t["name"],
            "description": t["description"],
            "input_schema": t["parameters"],
        }
        for t in CHAT_TOOLS
    ]


def get_gemini_chat_tools():
    """Tool definitions for Gemini function calling (google.genai types)."""
    try:
        from google.genai import types

        declarations = []
        for t in CHAT_TOOLS:
            # Clean schema for Gemini (remove 'default' which it doesn't accept)
            clean_props = {}
            for k, v in t["parameters"].get("properties", {}).items():
                prop = {pk: pv for pk, pv in v.items() if pk != "default"}
                clean_props[k] = prop

            declarations.append(
                types.FunctionDeclaration(
                    name=t["name"],
                    description=t["description"],
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            k: types.Schema(**_to_gemini_schema(v))
                            for k, v in clean_props.items()
                        },
                        required=t["parameters"].get("required", []),
                    ),
                )
            )
        return types.Tool(function_declarations=declarations)
    except Exception as e:
        logger.warning(f"Failed to build Gemini chat tools: {e}")
        return None


def _to_gemini_schema(prop: Dict[str, Any]) -> Dict[str, Any]:
    """Convert JSON Schema property to Gemini Schema kwargs."""
    type_map = {
        "string": "STRING",
        "integer": "INTEGER",
        "number": "NUMBER",
        "boolean": "BOOLEAN",
        "array": "ARRAY",
        "object": "OBJECT",
    }
    result: Dict[str, Any] = {
        "type": type_map.get(prop.get("type", "string"), "STRING"),
    }
    if "description" in prop:
        result["description"] = prop["description"]
    if "enum" in prop:
        result["enum"] = prop["enum"]
    return result


# ---------------------------------------------------------------------------
# Tool execution — dispatch to real services
# ---------------------------------------------------------------------------

async def execute_chat_tool(
    tool_name: str,
    arguments: Dict[str, Any],
) -> Dict[str, Any]:
    """Execute a chat tool and return results."""
    if tool_name == "web_search":
        return await _exec_web_search(arguments)
    elif tool_name == "search_jurisprudencia":
        return await _exec_search_jurisprudencia(arguments)
    elif tool_name == "search_legislacao":
        return await _exec_search_legislacao(arguments)
    else:
        return {"error": f"Unknown tool: {tool_name}"}


async def _exec_web_search(args: Dict[str, Any]) -> Dict[str, Any]:
    query = str(args.get("query", ""))
    search_type = str(args.get("search_type", "general"))
    max_results = int(args.get("max_results", 8))
    try:
        from app.services.web_search_service import web_search_service

        if search_type == "legal":
            result = await web_search_service.search_legal(query, num_results=max_results)
        else:
            result = await web_search_service.search(query, num_results=max_results)
        return result if isinstance(result, dict) else {"results": result}
    except Exception as e:
        logger.warning(f"web_search failed: {e}")
        return {"error": str(e), "query": query}


async def _exec_search_jurisprudencia(args: Dict[str, Any]) -> Dict[str, Any]:
    query = str(args.get("query", ""))
    court = args.get("court") or None
    limit = int(args.get("limit", 10))
    try:
        from app.services.jurisprudence_service import jurisprudence_service

        result = await jurisprudence_service.search(query, court=court, limit=limit)
        return result if isinstance(result, dict) else {"results": result}
    except Exception as e:
        logger.warning(f"search_jurisprudencia failed: {e}")
        return {"error": str(e), "query": query}


async def _exec_search_legislacao(args: Dict[str, Any]) -> Dict[str, Any]:
    query = str(args.get("query", ""))
    tipo = args.get("tipo") or None
    limit = int(args.get("limit", 10))
    try:
        from app.services.legislation_service import legislation_service

        result = await legislation_service.search(query, tipo=tipo, limit=limit)
        return result if isinstance(result, dict) else {"results": result}
    except Exception as e:
        logger.warning(f"search_legislacao failed: {e}")
        return {"error": str(e), "query": query}


# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------

def _safe_json(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return {}
    try:
        parsed = json.loads(value.strip())
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Tool loops — non-streaming, return (final_text, tool_trace)
# ---------------------------------------------------------------------------

async def run_openai_chat_tool_loop(
    *,
    client: Any,
    model: str,
    system_instruction: str,
    user_prompt: str,
    max_tokens: int,
    temperature: float,
    max_rounds: int = 4,
) -> Tuple[str, List[Dict[str, Any]]]:
    """OpenAI tool loop using internal chat tools."""
    tools = get_openai_chat_tools()
    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": system_instruction},
        {"role": "user", "content": user_prompt},
    ]
    tool_trace: List[Dict[str, Any]] = []

    for _ in range(max_rounds):
        kwargs: Dict[str, Any] = dict(
            model=model,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            max_tokens=max_tokens,
        )
        # Reasoning models don't support temperature
        if not model.startswith(("o1", "o3", "o4")):
            kwargs["temperature"] = temperature

        resp = await client.chat.completions.create(**kwargs)
        choice = resp.choices[0]
        msg = choice.message
        content = getattr(msg, "content", None)
        tool_calls = getattr(msg, "tool_calls", None)

        if tool_calls:
            messages.append({
                "role": "assistant",
                "content": content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in tool_calls
                ],
            })
            for tc in tool_calls:
                name = tc.function.name
                args = _safe_json(tc.function.arguments)
                try:
                    result = await execute_chat_tool(name, args)
                    preview = json.dumps(result, ensure_ascii=False)[:500]
                    tool_trace.append({"name": name, "arguments": args, "result_preview": preview})
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(result, ensure_ascii=False),
                    })
                except Exception as e:
                    logger.warning(f"Chat tool call failed ({name}): {e}")
                    tool_trace.append({"name": name, "arguments": args, "result_preview": f"ERROR: {e}"})
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps({"error": str(e)}),
                    })
            continue

        if isinstance(content, str) and content.strip():
            return content, tool_trace
        break

    return "Não foi possível concluir a resposta com ferramentas.", tool_trace


async def run_anthropic_chat_tool_loop(
    *,
    client: Any,
    model: str,
    system_instruction: str,
    user_prompt: str,
    max_tokens: int,
    temperature: float,
    max_rounds: int = 4,
) -> Tuple[str, List[Dict[str, Any]]]:
    """Anthropic tool loop using internal chat tools."""
    tools = get_anthropic_chat_tools()
    messages: List[Dict[str, Any]] = [
        {"role": "user", "content": [{"type": "text", "text": user_prompt}]},
    ]
    tool_trace: List[Dict[str, Any]] = []

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
        text_blocks = [b for b in content_blocks if getattr(b, "type", None) == "text"]

        if tool_uses:
            messages.append({"role": "assistant", "content": content_blocks})
            tool_results = []
            for tu in tool_uses:
                name = tu.name
                args = tu.input if isinstance(tu.input, dict) else {}
                try:
                    result = await execute_chat_tool(name, args)
                    preview = json.dumps(result, ensure_ascii=False)[:500]
                    tool_trace.append({"name": name, "arguments": args, "result_preview": preview})
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": json.dumps(result, ensure_ascii=False),
                    })
                except Exception as e:
                    logger.warning(f"Chat tool call failed ({name}): {e}")
                    tool_trace.append({"name": name, "arguments": args, "result_preview": f"ERROR: {e}"})
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": json.dumps({"error": str(e)}),
                        "is_error": True,
                    })
            messages.append({"role": "user", "content": tool_results})
            continue

        final_text = " ".join(getattr(b, "text", "") for b in text_blocks).strip()
        if final_text:
            return final_text, tool_trace
        break

    return "Não foi possível concluir a resposta com ferramentas.", tool_trace


async def run_gemini_chat_tool_loop(
    *,
    client: Any,
    model: str,
    system_instruction: str,
    user_prompt: str,
    max_tokens: int,
    temperature: float,
    max_rounds: int = 4,
) -> Tuple[str, List[Dict[str, Any]]]:
    """Gemini tool loop using internal chat tools."""
    try:
        from google.genai import types
    except ImportError:
        return "Google GenAI SDK não disponível.", []

    tool_defs = get_gemini_chat_tools()
    if not tool_defs:
        return "Falha ao construir ferramentas Gemini.", []

    tool_trace: List[Dict[str, Any]] = []
    contents = [types.Content(role="user", parts=[types.Part.from_text(text=user_prompt)])]

    for _ in range(max_rounds):
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            max_output_tokens=max_tokens,
            temperature=temperature,
            tools=[tool_defs],
        )
        response = await client.aio.models.generate_content(
            model=model,
            contents=contents,
            config=config,
        )

        # Check for function calls in response
        parts = response.candidates[0].content.parts if response.candidates else []
        fn_calls = [p for p in parts if p.function_call]
        text_parts = [p for p in parts if p.text]

        if fn_calls:
            # Append model response to history
            contents.append(response.candidates[0].content)

            # Execute each function call
            fn_responses = []
            for fc_part in fn_calls:
                fc = fc_part.function_call
                name = fc.name
                args = dict(fc.args) if fc.args else {}
                try:
                    result = await execute_chat_tool(name, args)
                    preview = json.dumps(result, ensure_ascii=False)[:500]
                    tool_trace.append({"name": name, "arguments": args, "result_preview": preview})
                    fn_responses.append(
                        types.Part.from_function_response(
                            name=name,
                            response=result,
                        )
                    )
                except Exception as e:
                    logger.warning(f"Chat tool call failed ({name}): {e}")
                    tool_trace.append({"name": name, "arguments": args, "result_preview": f"ERROR: {e}"})
                    fn_responses.append(
                        types.Part.from_function_response(
                            name=name,
                            response={"error": str(e)},
                        )
                    )

            contents.append(types.Content(role="user", parts=fn_responses))
            continue

        # No function calls — extract text
        final_text = " ".join(p.text for p in text_parts).strip()
        if final_text:
            return final_text, tool_trace
        break

    return "Não foi possível concluir a resposta com ferramentas.", tool_trace
