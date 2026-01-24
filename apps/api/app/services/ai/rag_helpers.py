import asyncio
import json
import logging
import os
import re
from typing import List, Optional

from app.services.ai.agent_clients import (
    get_gpt_client,
    get_claude_client,
    get_gemini_client,
)
from app.services.ai.genai_utils import extract_genai_text
from app.services.ai.model_registry import get_api_model_name

logger = logging.getLogger("RAGHelpers")

DEFAULT_GPT_MODEL = "gpt-5.2"
DEFAULT_CLAUDE_MODEL = "claude-4.5-sonnet"
DEFAULT_GEMINI_MODEL = "gemini-3-flash"


def _compact_history(history: List[dict], max_items: int = 6, max_chars: int = 1500) -> str:
    if not history:
        return ""
    selected = history[-max_items:]
    lines = []
    total = 0
    for item in selected:
        role = item.get("role", "user")
        content = (item.get("content") or "").strip()
        if not content:
            continue
        remaining = max_chars - total
        if remaining <= 0:
            break
        snippet = content[:remaining]
        lines.append(f"{role}: {snippet}")
        total += len(snippet)
    return "\n".join(lines)


async def _call_llm(
    prompt: str,
    *,
    max_tokens: int,
    temperature: float,
    preferred: Optional[List[str]] = None,
) -> str:
    preferred = preferred or ["gemini", "gpt", "claude"]
    for provider in preferred:
        if provider == "gemini":
            client = get_gemini_client()
            if not client:
                continue

            def _sync_call() -> str:
                config = None
                try:
                    from google.genai import types as genai_types
                    config = genai_types.GenerateContentConfig(
                        max_output_tokens=max_tokens,
                        temperature=temperature,
                    )
                except Exception:
                    config = None
                if config:
                    resp = client.models.generate_content(
                        model=get_api_model_name(DEFAULT_GEMINI_MODEL),
                        contents=prompt,
                        config=config,
                    )
                else:
                    resp = client.models.generate_content(
                        model=get_api_model_name(DEFAULT_GEMINI_MODEL),
                        contents=prompt,
                    )
                text = extract_genai_text(resp) or ""
                return text.strip()

            try:
                return await asyncio.to_thread(_sync_call)
            except Exception as exc:
                logger.warning(f"Gemini helper failed: {exc}")
                continue

        if provider == "gpt":
            client = get_gpt_client()
            if not client:
                continue

            def _sync_call() -> str:
                resp = client.chat.completions.create(
                    model=get_api_model_name(DEFAULT_GPT_MODEL),
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                if not resp.choices:
                    return ""
                return (resp.choices[0].message.content or "").strip()

            try:
                return await asyncio.to_thread(_sync_call)
            except Exception as exc:
                logger.warning(f"GPT helper failed: {exc}")
                continue

        if provider == "claude":
            client = get_claude_client()
            if not client:
                continue

            def _sync_call() -> str:
                resp = client.messages.create(
                    model=get_api_model_name(DEFAULT_CLAUDE_MODEL),
                    max_tokens=max_tokens,
                    messages=[{"role": "user", "content": prompt}],
                )
                return "".join(getattr(b, "text", "") for b in resp.content).strip()

            try:
                return await asyncio.to_thread(_sync_call)
            except Exception as exc:
                logger.warning(f"Claude helper failed: {exc}")
                continue

    return ""


async def rewrite_query_with_history(
    query: str,
    history: Optional[List[dict]] = None,
    summary_text: Optional[str] = None,
) -> str:
    history_block = _compact_history(history or [])
    summary_block = (summary_text or "").strip()
    if not history_block and not summary_block:
        return query

    prompt = (
        "You are a retrieval query rewriter.\n"
        "Rewrite the user question into a standalone search query.\n"
        "Keep it short, include key entities, avoid quotes, no extra text.\n\n"
        f"Summary:\n{summary_block or 'none'}\n\n"
        f"History:\n{history_block or 'none'}\n\n"
        f"Question:\n{query}\n\n"
        "Rewrite:"
    )
    rewritten = await _call_llm(prompt, max_tokens=160, temperature=0.2)
    cleaned = rewritten.strip().strip('"').strip("'")
    return cleaned or query


async def generate_hypothetical_document(
    query: str,
    history: Optional[List[dict]] = None,
    summary_text: Optional[str] = None,
) -> str:
    history_block = _compact_history(history or [], max_items=4, max_chars=800)
    summary_block = (summary_text or "").strip()
    prompt = (
        "Write a short, factual hypothetical document that would answer the question.\n"
        "Use domain terms, 6-10 sentences, no citations, no lists.\n\n"
        f"Summary:\n{summary_block or 'none'}\n\n"
        f"History:\n{history_block or 'none'}\n\n"
        f"Question:\n{query}\n\n"
        "Hypothetical document:"
    )
    text = await _call_llm(prompt, max_tokens=420, temperature=0.2)
    return text.strip()


def _extract_json(text: str) -> dict:
    if not text:
        return {}
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        return {}
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}


def _heuristic_multi_queries(query: str, max_queries: int) -> List[str]:
    cleaned = re.sub(r"[\n\r\t]+", " ", (query or "")).strip()
    if not cleaned:
        return []
    base = cleaned
    tokens = [t for t in re.split(r"[\s,;:()\[\]{}]+", cleaned) if len(t) >= 4]
    keywords = " ".join(tokens[:10]).strip()
    alt = ""
    if "?" in cleaned:
        alt = cleaned.replace("?", "").strip()
    variants = [base]
    if keywords and keywords.lower() != base.lower():
        variants.append(keywords)
    if alt and alt.lower() != base.lower():
        variants.append(alt)
    # Dedup and cap
    seen = set()
    out = []
    for q in variants:
        key = q.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(q)
        if len(out) >= max_queries:
            break
    return out


async def generate_multi_queries(
    query: str,
    history: Optional[List[dict]] = None,
    summary_text: Optional[str] = None,
    max_queries: int = 3,
    use_llm: Optional[bool] = None,
) -> List[str]:
    if max_queries <= 1:
        return [query]
    if use_llm is None:
        use_llm = os.getenv("RAG_MULTI_QUERY_LLM", "false").lower() in ("1", "true", "yes", "on")
    base_list = _heuristic_multi_queries(query, max_queries=max_queries)
    if not use_llm:
        return base_list or [query]

    history_block = _compact_history(history or [], max_items=4, max_chars=800)
    summary_block = (summary_text or "").strip()
    prompt = (
        "Generate up to {max_q} alternative search queries for a legal RAG system.\n"
        "Keep each query short, no quotes, no bullets, one per line.\n\n"
        f"Summary:\n{summary_block or 'none'}\n\n"
        f"History:\n{history_block or 'none'}\n\n"
        f"Question:\n{query}\n\n"
        "Queries:"
    ).format(max_q=max_queries)
    response = await _call_llm(prompt, max_tokens=200, temperature=0.2)
    lines = [ln.strip(" -•\t") for ln in (response or "").splitlines() if ln.strip()]
    merged = base_list[:]
    seen = {q.lower() for q in merged}
    for ln in lines:
        if not ln:
            continue
        key = ln.lower()
        if key in seen:
            continue
        seen.add(key)
        merged.append(ln)
        if len(merged) >= max_queries:
            break
    return merged[:max_queries] if merged else base_list or [query]


def evaluate_crag_gate(
    results: List[dict],
    min_best_score: float,
    min_avg_top3_score: float,
) -> dict:
    if not results:
        return {
            "gate_passed": True,
            "safe_mode": False,
            "best_score": 0.0,
            "avg_top3": 0.0,
            "reason": "No RAG results, skipping gate",
        }

    scores = [float(r.get("final_score") or r.get("score") or 0.0) for r in results]
    best = max(scores) if scores else 0.0
    top3 = scores[:3]
    avg_top3 = sum(top3) / len(top3) if top3 else 0.0
    gate_passed = best >= min_best_score and avg_top3 >= min_avg_top3_score

    return {
        "gate_passed": gate_passed,
        "safe_mode": not gate_passed,
        "best_score": best,
        "avg_top3": avg_top3,
        "reason": f"best={best:.2f}, avg_top3={avg_top3:.2f}, thresholds=({min_best_score}, {min_avg_top3_score})",
    }


def _heuristic_sources(query: str, available_sources: List[str]) -> List[str]:
    q = (query or "").lower()
    selected = []
    if any(term in q for term in ("juris", "sumula", "precedente", "acordao", "stj", "stf")):
        selected.append("juris")
    if any(term in q for term in ("lei", "artigo", "norma", "decreto", "constituicao")):
        selected.append("lei")
    if any(term in q for term in ("modelo", "peticao", "contestacao", "recurso", "contrato", "clausula")):
        selected.append("pecas_modelo")
    if any(term in q for term in ("sei", "processo interno", "nota tecnica")):
        selected.append("sei")
    if not selected:
        selected = available_sources[:]
    return [s for s in selected if s in available_sources]


async def route_rag_sources(
    query: str,
    available_sources: List[str],
    history: Optional[List[dict]] = None,
    summary_text: Optional[str] = None,
) -> List[str]:
    if not available_sources:
        return []
    history_block = _compact_history(history or [], max_items=4, max_chars=800)
    summary_block = (summary_text or "").strip()
    sources_list = ", ".join(available_sources)
    prompt = (
        "You are a routing agent for a legal RAG system.\n"
        "Pick the best sources from the available list.\n"
        "Return JSON only: {\"sources\": [\"...\"]}\n\n"
        f"Available sources: {sources_list}\n\n"
        f"Summary:\n{summary_block or 'none'}\n\n"
        f"History:\n{history_block or 'none'}\n\n"
        f"Question:\n{query}\n\n"
        "JSON:"
    )
    response = await _call_llm(prompt, max_tokens=120, temperature=0.0)
    payload = _extract_json(response)
    routed = payload.get("sources") if isinstance(payload, dict) else None
    if isinstance(routed, list):
        cleaned = [str(item).strip().lower() for item in routed if str(item).strip()]
        cleaned = [s for s in cleaned if s in available_sources]
        if cleaned:
            return list(dict.fromkeys(cleaned))
    return _heuristic_sources(query, available_sources)
