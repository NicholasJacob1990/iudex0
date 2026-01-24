import asyncio
import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class RagRouterDecision:
    rag_mode: str
    graph_rag_enabled: bool
    argument_graph_enabled: bool
    graph_hops: int
    reasons: List[str] = field(default_factory=list)
    used_llm: bool = False
    llm_confidence: Optional[float] = None
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    llm_thinking_level: Optional[str] = None
    llm_schema_enforced: Optional[bool] = None
    ambiguous: Optional[bool] = None
    ambiguous_reason: Optional[str] = None
    signals: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RouterLLMResult:
    text: str
    provider: Optional[str] = None
    model: Optional[str] = None
    thinking_level: Optional[str] = None
    schema_enforced: bool = False


ROUTER_JSON_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "route": {
            "type": "string",
            "enum": [
                "retrieval_only",
                "retrieval_graphrag",
                "retrieval_argumentrag",
                "retrieval_both",
            ],
        },
        "graph_hops": {"type": "integer", "minimum": 1, "maximum": 5},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "reasons": {"type": "array", "items": {"type": "string"}, "minItems": 0, "maxItems": 6},
    },
    "required": ["route", "graph_hops", "confidence", "reasons"],
    "additionalProperties": False,
}


_RE_GRAPH = re.compile(
    r"(\bart\.?\s*\d+\b|\bartigo\b|\bconstitui[cç][aã]o\b|\blei\b|\bdecreto\b|\bportaria\b|\bresolu[cç][aã]o\b|"
    r"\bs[úu]mula\b|\btema\b|\btese\b|\bre\s*p(?:\.|)\b|\bres[p]?\b|\badi\b|\badpf\b|\bagrg\b|\bms\b|\bhc\b)",
    flags=re.IGNORECASE,
)
_RE_GRAPH_RELATION = re.compile(
    r"(rela[cç][aã]o|conex[aã]o|vincul|hierarq|correla[cç][aã]o|compatibil|entendimento|precedente)",
    flags=re.IGNORECASE,
)
_RE_ARGUMENT = re.compile(
    r"(prova|evid[eê]ncia|documento|anexo|impugna|contesta|nega|refuta|contradit[oó]r|"
    r"houve|ocorreu|quando|quem|onde|como|por\s+qu[eê]|incidente|fraude|n[aã]o\s+conformidade|auditoria)",
    flags=re.IGNORECASE,
)

_RE_MULTI_PART = re.compile(r"(\b(e|ou)\b|/|;|\?|:)", flags=re.IGNORECASE)
_RE_NUM = re.compile(r"\b\d{1,6}\b")
_RE_QUOTED = re.compile(r"\"[^\"]{6,}\"|'[^']{6,}'")


def score_signals(query: str) -> dict:
    text = (query or "").strip()
    if not text:
        return {"legal_score": 0.0, "arg_score": 0.0, "complexity": 0.0, "tokens": 0}
    tokens = [t for t in re.split(r"\s+", text) if t]
    token_count = len(tokens)

    legal_hits = 0.0
    arg_hits = 0.0
    if _RE_GRAPH.search(text):
        legal_hits += 2.0
    if _RE_GRAPH_RELATION.search(text):
        legal_hits += 1.0
    if _RE_ARGUMENT.search(text):
        arg_hits += 2.0

    if re.search(r"\b(stf|stj|tst|trf|tj|cnj)\b", text, flags=re.IGNORECASE):
        legal_hits += 1.0
    if _RE_NUM.search(text):
        legal_hits += 0.5
    if _RE_QUOTED.search(text):
        arg_hits += 0.5

    complexity = 0.0
    if token_count >= 18:
        complexity += 1.0
    if token_count >= 35:
        complexity += 1.0
    if _RE_MULTI_PART.search(text):
        complexity += 0.5
    if text.count("?") >= 2:
        complexity += 0.5

    return {
        "legal_score": legal_hits,
        "arg_score": arg_hits,
        "complexity": complexity,
        "tokens": token_count,
    }


def is_ambiguous(
    query: str,
    *,
    legal_score: float,
    arg_score: float,
    complexity: float,
    tokens: int,
) -> Tuple[bool, str]:
    text = (query or "").strip()
    if not text:
        return False, "empty"
    if tokens <= 5 and (legal_score + arg_score) <= 1:
        return True, "very_short_vague"
    if (legal_score + arg_score) == 0 and complexity >= 1.0:
        return True, "complex_but_no_signals"
    if legal_score > 0 and arg_score > 0:
        return False, "both_signals"
    if (legal_score + arg_score) == 1 and complexity >= 1.0:
        return True, "weak_signal_complex_query"
    return False, "clear_enough"


def _extract_json(text: str) -> dict:
    if not text:
        return {}
    try:
        payload = json.loads(text.strip())
        if isinstance(payload, dict):
            return payload
    except Exception:
        pass
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        return {}
    try:
        payload = json.loads(match.group(0))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _clamp_hops(hops: int) -> int:
    try:
        hops = int(hops)
    except Exception:
        hops = 2
    return max(1, min(hops, 5))


async def _call_router_llm(
    prompt: str,
    *,
    max_tokens: int = 220,
    temperature: float = 0.0,
    schema: Optional[Dict[str, Any]] = None,
    thinking_level: Optional[str] = None,
) -> RouterLLMResult:
    preferred = [p.strip().lower() for p in os.getenv("RAG_ROUTER_LLM_PROVIDERS", "gemini").split(",") if p.strip()]
    preferred = preferred or ["gemini"]
    for provider in preferred:
        if provider == "gemini":
            try:
                from app.services.ai.agent_clients import get_gemini_client
                from app.services.ai.genai_utils import extract_genai_text
                from app.services.ai.model_registry import get_api_model_name
            except Exception:
                continue
            client = get_gemini_client()
            if not client:
                continue
            model_id = os.getenv("RAG_ROUTER_LLM_MODEL", "gemini-3-flash").strip() or "gemini-3-flash"

            def _sync_call() -> RouterLLMResult:
                config = None
                schema_enforced = False
                try:
                    from google.genai import types as genai_types
                    cfg_kwargs = {
                        "max_output_tokens": max_tokens,
                        "temperature": temperature,
                        "response_mime_type": "application/json",
                    }
                    if schema:
                        cfg_kwargs["response_json_schema"] = schema
                    if thinking_level:
                        try:
                            cfg_kwargs["thinking_config"] = genai_types.ThinkingConfig(
                                thinking_level=thinking_level,
                                include_thoughts=False,
                            )
                        except Exception:
                            pass
                    try:
                        config = genai_types.GenerateContentConfig(**cfg_kwargs)
                        schema_enforced = bool(schema)
                    except TypeError:
                        cfg_kwargs.pop("response_json_schema", None)
                        schema_enforced = False
                        config = genai_types.GenerateContentConfig(**cfg_kwargs)
                except Exception:
                    config = None
                    schema_enforced = False
                if config:
                    resp = client.models.generate_content(
                        model=get_api_model_name(model_id),
                        contents=prompt,
                        config=config,
                    )
                else:
                    resp = client.models.generate_content(
                        model=get_api_model_name(model_id),
                        contents=prompt,
                    )
                return RouterLLMResult(
                    text=(extract_genai_text(resp) or "").strip(),
                    provider="gemini",
                    model=get_api_model_name(model_id),
                    thinking_level=thinking_level,
                    schema_enforced=schema_enforced,
                )

            try:
                return await asyncio.to_thread(_sync_call)
            except Exception:
                continue

        if provider == "gpt":
            try:
                from app.services.ai.agent_clients import get_gpt_client
                from app.services.ai.model_registry import get_api_model_name
            except Exception:
                continue
            client = get_gpt_client()
            if not client:
                continue
            model_id = os.getenv("RAG_ROUTER_LLM_MODEL", "gpt-5.2").strip() or "gpt-5.2"

            def _sync_call() -> RouterLLMResult:
                resp = client.chat.completions.create(
                    model=get_api_model_name(model_id),
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                if not resp.choices:
                    return RouterLLMResult(text="", provider="gpt", model=get_api_model_name(model_id))
                return RouterLLMResult(
                    text=(resp.choices[0].message.content or "").strip(),
                    provider="gpt",
                    model=get_api_model_name(model_id),
                )

            try:
                return await asyncio.to_thread(_sync_call)
            except Exception:
                continue

        if provider == "claude":
            try:
                from app.services.ai.agent_clients import get_claude_client
                from app.services.ai.model_registry import get_api_model_name
            except Exception:
                continue
            client = get_claude_client()
            if not client:
                continue
            model_id = os.getenv("RAG_ROUTER_LLM_MODEL", "claude-4.5-sonnet").strip() or "claude-4.5-sonnet"

            def _sync_call() -> RouterLLMResult:
                resp = client.messages.create(
                    model=get_api_model_name(model_id),
                    max_tokens=max_tokens,
                    messages=[{"role": "user", "content": prompt}],
                )
                return RouterLLMResult(
                    text="".join(getattr(b, "text", "") for b in resp.content).strip(),
                    provider="claude",
                    model=get_api_model_name(model_id),
                )

            try:
                return await asyncio.to_thread(_sync_call)
            except Exception:
                continue

    return RouterLLMResult(text="")


def _apply_llm_route(
    base: RagRouterDecision,
    llm_payload: dict,
    *,
    allow_graph: bool,
    allow_argument: bool,
    llm_provider: Optional[str] = None,
    llm_model: Optional[str] = None,
    llm_thinking_level: Optional[str] = None,
    llm_schema_enforced: Optional[bool] = None,
    ambiguous: Optional[bool] = None,
    ambiguous_reason: Optional[str] = None,
    signals: Optional[Dict[str, Any]] = None,
) -> RagRouterDecision:
    route = str(llm_payload.get("route") or "").strip().lower()
    hops = _clamp_hops(llm_payload.get("graph_hops") or base.graph_hops)
    confidence = llm_payload.get("confidence")
    try:
        confidence = float(confidence) if confidence is not None else None
    except Exception:
        confidence = None
    if confidence is not None:
        confidence = max(0.0, min(confidence, 1.0))
    reasons = llm_payload.get("reasons")
    if not isinstance(reasons, list):
        reasons = []
    reasons = [str(r).strip() for r in reasons if str(r).strip()][:6]

    enable_graph = False
    enable_arg = False
    if route in ("retrieval_graphrag", "graphrag"):
        enable_graph = True
    elif route in ("retrieval_argumentrag", "argumentrag"):
        enable_arg = True
    elif route in ("retrieval_both", "both"):
        enable_graph = True
        enable_arg = True
    elif route in ("retrieval_only", "only", "retrieval"):
        enable_graph = False
        enable_arg = False
    else:
        enable_graph = base.graph_rag_enabled
        enable_arg = base.argument_graph_enabled

    if not allow_graph:
        enable_graph = False
    if not allow_argument:
        enable_arg = False

    return RagRouterDecision(
        rag_mode=base.rag_mode,
        graph_rag_enabled=bool(enable_graph),
        argument_graph_enabled=bool(enable_arg),
        graph_hops=hops,
        reasons=(base.reasons + ["llm_router"] + reasons)[:10],
        used_llm=True,
        llm_confidence=confidence,
        llm_provider=llm_provider,
        llm_model=llm_model,
        llm_thinking_level=llm_thinking_level,
        llm_schema_enforced=llm_schema_enforced,
        ambiguous=ambiguous,
        ambiguous_reason=ambiguous_reason,
        signals=signals or {},
    )

def decide_rag_route(
    query: str,
    *,
    rag_mode: str,
    graph_hops: int = 2,
    allow_graph: bool = True,
    allow_argument: bool = True,
) -> RagRouterDecision:
    """
    Router simples (rule-based) para decidir quando habilitar GraphRAG e/ou ArgumentRAG.

    Regras:
    - `rag_mode="manual"`: não altera flags, apenas normaliza `graph_hops`.
    - `rag_mode="auto"`: habilita GraphRAG/ArgumentRAG quando há sinais na query.
    """
    mode = (rag_mode or "manual").strip().lower()
    if mode not in ("auto", "manual"):
        mode = "manual"

    cleaned = (query or "").strip()
    hops = int(graph_hops or 2)
    if hops < 1:
        hops = 1
    if hops > 5:
        hops = 5

    if mode != "auto" or not cleaned:
        return RagRouterDecision(
            rag_mode=mode,
            graph_rag_enabled=False,
            argument_graph_enabled=False,
            graph_hops=hops,
            reasons=["manual_mode_or_empty_query"],
        )

    reasons: List[str] = []
    enable_graph = bool(allow_graph and (_RE_GRAPH.search(cleaned) or _RE_GRAPH_RELATION.search(cleaned)))
    enable_argument = bool(allow_argument and _RE_ARGUMENT.search(cleaned))

    if enable_graph:
        reasons.append("graph_signals")
    if enable_argument:
        reasons.append("argument_signals")
    if not reasons:
        reasons.append("no_signals")

    if enable_graph and _RE_GRAPH_RELATION.search(cleaned):
        hops = max(hops, 3)

    return RagRouterDecision(
        rag_mode=mode,
        graph_rag_enabled=bool(enable_graph),
        argument_graph_enabled=bool(enable_argument),
        graph_hops=hops,
        reasons=reasons,
    )


async def decide_rag_route_hybrid(
    query: str,
    *,
    rag_mode: str,
    graph_hops: int = 2,
    allow_graph: bool = True,
    allow_argument: bool = True,
    risk_mode: str = "high",
    roles: Optional[List[str]] = None,
    groups: Optional[List[str]] = None,
) -> RagRouterDecision:
    """
    Router em 2 camadas:
    - Regras baratas sempre.
    - LLM opcional apenas quando a query estiver ambígua e `RAG_ROUTER_LLM_ENABLED=true`.
    """
    base = decide_rag_route(
        query,
        rag_mode=rag_mode,
        graph_hops=graph_hops,
        allow_graph=allow_graph,
        allow_argument=allow_argument,
    )
    if base.rag_mode != "auto":
        return base

    signals = score_signals(query)
    ambiguous, why = is_ambiguous(
        query,
        legal_score=float(signals.get("legal_score") or 0.0),
        arg_score=float(signals.get("arg_score") or 0.0),
        complexity=float(signals.get("complexity") or 0.0),
        tokens=int(signals.get("tokens") or 0),
    )
    llm_enabled = os.getenv("RAG_ROUTER_LLM_ENABLED", "false").lower() in ("1", "true", "yes", "on")
    if not llm_enabled:
        return RagRouterDecision(
            rag_mode=base.rag_mode,
            graph_rag_enabled=base.graph_rag_enabled,
            argument_graph_enabled=base.argument_graph_enabled,
            graph_hops=base.graph_hops,
            reasons=(base.reasons + ["llm_router_disabled"] + [f"ambiguous:{ambiguous}:{why}"])[:10],
            ambiguous=ambiguous,
            ambiguous_reason=why,
            signals=signals,
        )
    force_llm = str(risk_mode).strip().lower() in ("high", "strict") and bool((query or "").strip())
    if not ambiguous and not force_llm:
        return RagRouterDecision(
            rag_mode=base.rag_mode,
            graph_rag_enabled=base.graph_rag_enabled,
            argument_graph_enabled=base.argument_graph_enabled,
            graph_hops=base.graph_hops,
            reasons=(base.reasons + [f"not_ambiguous:{why}"])[:10],
            ambiguous=False,
            ambiguous_reason=why,
            signals=signals,
        )

    thinking_level = "low"
    if why in ("complex_but_no_signals", "weak_signal_complex_query") or float(signals.get("complexity") or 0.0) >= 1.5:
        thinking_level = "high"

    roles = roles or []
    groups = groups or []
    base_for_llm = base
    if force_llm and not ambiguous:
        base_for_llm = RagRouterDecision(
            rag_mode=base.rag_mode,
            graph_rag_enabled=base.graph_rag_enabled,
            argument_graph_enabled=base.argument_graph_enabled,
            graph_hops=base.graph_hops,
            reasons=(base.reasons + ["force_llm:risk_mode_high"])[:10],
        )
        why = f"{why}|forced_high_risk"
    prompt = (
        "You are a router for a legal/compliance RAG system.\n"
        "Decide whether to enable GraphRAG and/or ArgumentRAG.\n"
        "Return ONLY JSON with keys: route, graph_hops, confidence, reasons.\n"
        "Do NOT decide access control or scopes.\n"
        f"risk_mode={risk_mode}\n"
        f"roles={roles}\n"
        f"groups={groups}\n"
        f"signals={signals}\n"
        f"question={query}\n"
        "JSON:"
    )
    text_result = await _call_router_llm(
        prompt,
        max_tokens=220,
        temperature=0.0,
        schema=ROUTER_JSON_SCHEMA,
        thinking_level=thinking_level,
    )
    payload = _extract_json(text_result.text)
    if not payload:
        return RagRouterDecision(
            rag_mode=base_for_llm.rag_mode,
            graph_rag_enabled=base_for_llm.graph_rag_enabled,
            argument_graph_enabled=base_for_llm.argument_graph_enabled,
            graph_hops=base_for_llm.graph_hops,
            reasons=(base_for_llm.reasons + ["llm_router_empty"])[:10],
            used_llm=True,
            llm_provider=text_result.provider,
            llm_model=text_result.model,
            llm_thinking_level=thinking_level,
            llm_schema_enforced=text_result.schema_enforced,
            ambiguous=ambiguous,
            ambiguous_reason=why,
            signals=signals,
        )

    route = str(payload.get("route") or "").strip().lower()
    if str(risk_mode).strip().lower() in ("high", "strict") and route in ("no_retrieval", "none"):
        payload["route"] = "retrieval_only"
        payload.setdefault("reasons", [])
        if isinstance(payload["reasons"], list):
            payload["reasons"].append("clamp:no_retrieval_in_high_risk")

    return _apply_llm_route(
        base_for_llm,
        payload,
        allow_graph=allow_graph,
        allow_argument=allow_argument,
        llm_provider=text_result.provider,
        llm_model=text_result.model,
        llm_thinking_level=thinking_level,
        llm_schema_enforced=text_result.schema_enforced,
        ambiguous=ambiguous,
        ambiguous_reason=why,
        signals=signals,
    )
