from __future__ import annotations

import re
from enum import Enum
from typing import List, Optional

from app.services.ai.shared.unified_tools import ALL_UNIFIED_TOOLS


class GraphIntent(str, Enum):
    GRAPH_NONE = "graph_none"
    GRAPH_BASIC = "graph_basic"
    GRAPH_GDS = "graph_gds"
    GRAPH_RISK = "graph_risk"
    GRAPH_WRITE = "graph_write"


_GRAPH_TOOLS = {"ask_graph", "scan_graph_risk", "audit_graph_edge", "audit_graph_chain"}

_KW_GDS = re.compile(
    r"\b(centralidade|pagerank|eigenvector|betweenness|closeness|k-?core|"
    r"comunidad|cluster|leiden|louvain|similaridad|knn|adamic|"
    r"ponte|bridges?|articulation|triangul|triangle)\b",
    re.IGNORECASE,
)
_KW_BASIC = re.compile(
    r"\b(caminho|path|cadeia|conecta|conex[aã]o|vizinhos?|neighbors?|"
    r"coocorr|co-?ocorr|buscar|search|contar|stats|count)\b",
    re.IGNORECASE,
)
_KW_RISK = re.compile(
    r"\b(risco|fraude|auditar|audit|sinal|suspeit|nepotismo|conflito de interesse|"
    r"lavagem|laranja)\b",
    re.IGNORECASE,
)
_KW_WRITE = re.compile(
    r"\b(conecte|crie aresta|criar aresta|linkar|link|relacione|adicionar rela[cç][aã]o)\b",
    re.IGNORECASE,
)


def is_graph_ui_mode(extra_instructions: Optional[str]) -> bool:
    text = (extra_instructions or "").strip().lower()
    if not text:
        return False
    if "modo grafo (ui)" in text:
        return True
    # Heuristic signals from chat context or injected hints.
    if "source: 'graph_page'" in text or "source=graph_page" in text or "graph_page" in text:
        return True
    return False


def classify_graph_intent(
    *,
    user_prompt: str,
    extra_instructions: Optional[str] = None,
) -> GraphIntent:
    prompt = (user_prompt or "").strip()
    extra = (extra_instructions or "").strip()
    ui_mode = is_graph_ui_mode(extra)

    # UI mode defaults to GRAPH_BASIC so "normal" questions still can use ask_graph,
    # but risk/write can override.
    if ui_mode:
        if _KW_RISK.search(prompt):
            return GraphIntent.GRAPH_RISK
        if _KW_WRITE.search(prompt):
            return GraphIntent.GRAPH_WRITE
        if _KW_GDS.search(prompt):
            return GraphIntent.GRAPH_GDS
        return GraphIntent.GRAPH_BASIC

    # Non-UI contexts: only enable graph tools if the user clearly asked about graph/GDS/risk.
    if _KW_RISK.search(prompt):
        return GraphIntent.GRAPH_RISK
    if _KW_GDS.search(prompt):
        return GraphIntent.GRAPH_GDS
    if _KW_BASIC.search(prompt):
        return GraphIntent.GRAPH_BASIC
    if _KW_WRITE.search(prompt):
        return GraphIntent.GRAPH_WRITE
    return GraphIntent.GRAPH_NONE


def build_tool_allowlist(
    *,
    user_prompt: str,
    extra_instructions: Optional[str] = None,
) -> List[str]:
    """
    Return tool allowlist for agent executors.

    Default: everything except graph tools, then selectively enable ask_graph / risk tools.
    """
    base = [t.name for t in ALL_UNIFIED_TOOLS if t.name not in _GRAPH_TOOLS]
    intent = classify_graph_intent(user_prompt=user_prompt, extra_instructions=extra_instructions)

    # Always include ask_graph for graph intent and graph UI mode.
    if intent in (GraphIntent.GRAPH_BASIC, GraphIntent.GRAPH_GDS, GraphIntent.GRAPH_RISK, GraphIntent.GRAPH_WRITE):
        base.append("ask_graph")

    # Only enable risk tools when explicitly requested.
    if intent == GraphIntent.GRAPH_RISK:
        base.extend(["scan_graph_risk", "audit_graph_edge", "audit_graph_chain"])

    # Dedup, keep order.
    out: List[str] = []
    seen = set()
    for name in base:
        key = str(name).strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(str(name).strip())
    return out

