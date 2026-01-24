from typing import List, Dict, Any

from app.services.web_search_service import DEFAULT_BREADTH_KEYWORDS, is_breadth_first, plan_queries


_DEEP_RESEARCH_HINTS = (
    "divergencia",
    "divergência",
    "comparar",
    "comparacao",
    "comparação",
    "panorama",
    "mapeamento",
    "tendencias",
    "tendências",
    "aprofundar",
    "aprofundada",
    "complexo",
    "complexa",
    "jurisprudencia",
    "jurisprudência",
    "precedente",
    "precedentes",
)


def _normalize_policy(policy: str | None) -> str:
    value = (policy or "auto").strip().lower()
    return value if value in ("auto", "force") else "auto"


def _should_auto_enable_web(query: str) -> bool:
    if not query:
        return False
    ql = query.lower()
    if is_breadth_first(query):
        return True
    if len(query) > 180 or len(query.split()) > 18:
        return True
    if any(k in ql for k in DEFAULT_BREADTH_KEYWORDS):
        return True
    if any(k in ql for k in ("atual", "atualizada", "recente", "mudanca", "mudança", "novidade")):
        return True
    return False


def _should_auto_enable_deep(query: str) -> bool:
    if not query:
        return False
    ql = query.lower()
    if len(query) > 260 or len(query.split()) > 28:
        return True
    return any(k in ql for k in _DEEP_RESEARCH_HINTS)


def decide_research_flags(
    query: str,
    web_search: bool,
    deep_research: bool,
    research_policy: str | None = None,
) -> Dict[str, Any]:
    """
    Decide effective research flags based on UI toggles and research policy.
    - policy=force: honor UI toggles exactly.
    - policy=auto: keep user toggles, but enable if heuristics indicate.
    """
    policy = _normalize_policy(research_policy)
    effective_web = bool(web_search)
    effective_deep = bool(deep_research)
    reason = "user" if effective_web or effective_deep else "disabled"

    if policy == "auto" and not (effective_web or effective_deep):
        auto_web = _should_auto_enable_web(query)
        auto_deep = _should_auto_enable_deep(query)
        effective_web = auto_web
        effective_deep = auto_deep
        reason = "auto" if (auto_web or auto_deep) else "disabled"

    planned_queries: List[str] = []
    if effective_web or effective_deep:
        planned_queries = plan_queries(query, max_queries=4)

    return {
        "web_search": effective_web,
        "deep_research": effective_deep,
        "policy": policy,
        "reason": reason,
        "planned_queries": planned_queries,
    }
