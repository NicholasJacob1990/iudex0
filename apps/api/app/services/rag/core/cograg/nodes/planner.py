"""
CogGRAG Planner Node — Top-down query decomposition.

Implements the cognitive decomposition step from CogGRAG (2503.06567v2):
  1. Evaluate query complexity
  2. Extract legal conditions/constraints
  3. Generate sub-questions as a mind-map tree (BFS, level-by-level)

Used as a LangGraph node in the CognitiveRAG StateGraph.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any, Dict, List, Optional

from app.services.rag.core.cograg.mindmap import (
    CognitiveTree,
    MindMapNode,
    NodeState,
)

logger = logging.getLogger("rag.cograg.planner")

# Try importing Gemini
try:
    from google import genai as _new_genai

    _HAS_NEW_GENAI = True
except ImportError:
    _HAS_NEW_GENAI = False

try:
    import google.generativeai as genai
except ImportError:
    genai = None  # type: ignore

# Budget tracker (optional)
try:
    from app.services.rag.core.budget_tracker import BudgetTracker, estimate_tokens
except ImportError:
    BudgetTracker = None  # type: ignore
    estimate_tokens = None  # type: ignore


# ═══════════════════════════════════════════════════════════════════════════
# Prompts (Portuguese, legal domain)
# ═══════════════════════════════════════════════════════════════════════════

EXTRACT_CONDITIONS_PROMPT = """\
Voce e um analista juridico. Dada a consulta abaixo, extraia as condicoes \
e restricoes contextuais relevantes para a analise.

Consulta: {query}

Responda em JSON:
{{
  "condicoes": "texto descritivo das condicoes, restricoes e contexto juridico relevante",
  "temas_macro": ["tema1", "tema2"],
  "entidades_chave": ["entidade1", "entidade2"]
}}

Responda APENAS o JSON, sem texto adicional."""

DECOMPOSE_PROMPT = """\
Voce e um analista juridico especializado em decomposicao de problemas complexos.

Consulta principal: {query}
Condicoes e contexto: {conditions}
Sub-questoes ja geradas em niveis anteriores:
{existing_questions}

Gere de 2 a {max_children} sub-questoes que, respondidas em conjunto, \
permitem responder a consulta principal de forma completa.

Regras:
- Cada sub-questao deve ser atomica e especifica
- Nao repita sub-questoes ja listadas
- Foco em aspectos juridicos distintos (fato, direito, jurisprudencia, procedimento)
- Use linguagem tecnico-juridica precisa

Responda em JSON:
{{
  "sub_questoes": [
    {{"pergunta": "texto da sub-questao", "tipo": "fato|direito|jurisprudencia|procedimento"}}
  ]
}}

Responda APENAS o JSON, sem texto adicional."""


# ═══════════════════════════════════════════════════════════════════════════
# Complexity Heuristics
# ═══════════════════════════════════════════════════════════════════════════

# Patterns that indicate a complex query needing decomposition
_COMPLEXITY_PATTERNS = [
    r"\be\b.*\be\b",                        # Multiple conjunctions
    r"\bou\b.*\bou\b",                      # Multiple disjunctions
    r"\bquais\b.*\bdiferenc",               # Comparison questions
    r"\bcompare\b",                         # Explicit comparison
    r"\bcomo\b.*\be\b.*\bquando\b",        # Multi-aspect question
    r"\bresponsabilidad\w+\s+\w+\s+\w+",  # Complex legal concept
    r"\bprescrição\b.*\binterrupção\b",    # Multi-concept legal
    r"\bnulidad\w+.*\bcontrat\w+",         # Compound legal issue
]

# Patterns for simple queries that should NOT decompose
_SIMPLE_PATTERNS = [
    r"^art\.?\s*\d+",                          # Direct article citation
    r"^§\s*\d+",                               # Direct paragraph citation
    r"^sumula\s+\d+",                          # Direct sumula citation
    r"^o que (e|é|significa)\b",               # Simple definition
    r"^qual\s+(e|é)\s+o\s+(prazo|valor)\b",   # Simple factual question
    r"^\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}", # CNJ number lookup
]

# Minimum length for decomposition consideration
_MIN_QUERY_LENGTH = 25


def is_complex_query(query: str) -> bool:
    """Heuristic: should this query be decomposed into sub-questions?"""
    q = query.strip().lower()

    # Too short → no decomposition
    if len(q) < _MIN_QUERY_LENGTH:
        return False

    # Simple patterns → no decomposition
    for pat in _SIMPLE_PATTERNS:
        if re.search(pat, q, re.IGNORECASE):
            return False

    # Complexity patterns → decompose
    for pat in _COMPLEXITY_PATTERNS:
        if re.search(pat, q, re.IGNORECASE):
            return True

    # Word count heuristic: > 12 words suggests complexity
    if len(q.split()) > 12:
        return True

    return False


# ═══════════════════════════════════════════════════════════════════════════
# LLM Helper
# ═══════════════════════════════════════════════════════════════════════════

async def _call_gemini(
    prompt: str,
    model_name: str = "gemini-2.0-flash",
    max_tokens: int = 500,
    temperature: float = 0.3,
    *,
    operation: str = "planner",
) -> str:
    """Call Gemini asynchronously via thread. Returns raw text."""

    def _sync() -> str:
        try:
            if _HAS_NEW_GENAI:
                import os
                client = _new_genai.Client(api_key=os.getenv("GEMINI_API_KEY", os.getenv("GOOGLE_API_KEY", "")))
                resp = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config={"max_output_tokens": max_tokens, "temperature": temperature},
                )
                return resp.text.strip() if resp and resp.text else ""
            elif genai is not None:
                model = genai.GenerativeModel(model_name)
                resp = model.generate_content(prompt)
                return resp.text.strip() if resp and resp.text else ""
            else:
                logger.warning("No Gemini SDK available")
                return ""
        except Exception as exc:
            logger.warning(f"Gemini call failed: {exc}")
            return ""

    t0 = time.perf_counter()
    result = await asyncio.to_thread(_sync)
    latency_ms = (time.perf_counter() - t0) * 1000.0
    try:
        from app.services.rag.core.metrics import get_latency_collector

        collector = get_latency_collector()
        collector.record(f"cograg.llm.{operation}", latency_ms)
    except Exception:
        pass
    return result


def _parse_json(text: str) -> Dict[str, Any]:
    """Best-effort JSON parse, stripping markdown fences if present."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```\w*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON object in text
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
    return {}


# ═══════════════════════════════════════════════════════════════════════════
# Planner Node (LangGraph)
# ═══════════════════════════════════════════════════════════════════════════

async def planner_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    LangGraph node: decompose a complex query into a mind-map tree.

    Reads from state:
        - query, tenant_id, scope, case_id

    Writes to state:
        - mind_map: serialised CognitiveTree
        - sub_questions: list of leaf sub-question dicts
        - temas: macro themes extracted
        - metrics.planner_*
    """
    query: str = state["query"]
    start = time.time()

    logger.info(f"[CogGRAG:Planner] Decomposing: '{query[:80]}...'")

    # ── Complexity check ──────────────────────────────────────────────
    if not is_complex_query(query):
        logger.info("[CogGRAG:Planner] Simple query → skip decomposition")
        tree = CognitiveTree(root_question=query, max_depth=1)
        root = tree.root()
        if root:
            root.state = NodeState.END  # Leaf-only tree

        latency = int((time.time() - start) * 1000)
        try:
            from app.services.rag.core.metrics import get_latency_collector

            get_latency_collector().record("cograg.node.planner", float(latency))
        except Exception:
            pass

        return {
            "mind_map": tree.to_dict(),
            "sub_questions": [{"node_id": root.node_id, "question": query, "level": 0}] if root else [],
            "temas": [],
            "metrics": {
                **state.get("metrics", {}),
                "planner_latency_ms": latency,
                "planner_decomposed": False,
                "planner_leaf_count": 1,
            },
        }

    # ── Step 1: Extract conditions ────────────────────────────────────
    conditions_prompt = EXTRACT_CONDITIONS_PROMPT.format(query=query)
    conditions_raw = await _call_gemini(conditions_prompt, operation="planner.conditions")
    conditions_data = _parse_json(conditions_raw)
    conditions_text = conditions_data.get("condicoes", "")
    temas = conditions_data.get("temas_macro", [])

    # ── Step 2: Build tree via BFS decomposition ──────────────────────
    tree = CognitiveTree(
        root_question=query,
        conditions=conditions_text,
        max_depth=state.get("cograg_max_depth", 3),
        max_children=state.get("cograg_max_children", 4),
    )

    # BFS: decompose level by level
    current_level_nodes = [tree.root()] if tree.root() else []

    for level in range(tree.max_depth):
        if not current_level_nodes:
            break

        next_level_nodes: List[MindMapNode] = []

        for parent in current_level_nodes:
            # Collect existing questions to avoid repetition
            existing = [n.question for n in tree.nodes.values() if n.node_id != parent.node_id]

            decompose_prompt = DECOMPOSE_PROMPT.format(
                query=parent.question,
                conditions=tree.conditions,
                existing_questions="\n".join(f"- {q}" for q in existing) or "(nenhuma)",
                max_children=tree.max_children,
            )
            decompose_raw = await _call_gemini(decompose_prompt, operation="planner.decompose")
            decompose_data = _parse_json(decompose_raw)

            sub_qs = decompose_data.get("sub_questoes", [])
            if not sub_qs:
                parent.state = NodeState.END
                continue

            for sq in sub_qs[: tree.max_children]:
                pergunta = sq.get("pergunta", "").strip()
                if not pergunta:
                    continue
                child = tree.add_child(
                    parent_id=parent.node_id,
                    question=pergunta,
                    state=NodeState.CONTINUE if level + 1 < tree.max_depth - 1 else NodeState.END,
                )
                if child:
                    next_level_nodes.append(child)

        current_level_nodes = next_level_nodes

    # Mark all remaining CONTINUE nodes with no children as END
    for node in tree.nodes.values():
        if node.state == NodeState.CONTINUE and not node.children:
            node.state = NodeState.END

    # ── Build output ──────────────────────────────────────────────────
    leaves = tree.leaves()
    sub_questions = [
        {"node_id": n.node_id, "question": n.question, "level": n.level}
        for n in leaves
    ]

    latency = int((time.time() - start) * 1000)
    logger.info(
        f"[CogGRAG:Planner] Tree built: {tree.node_count()} nodes, "
        f"{tree.leaf_count()} leaves, depth {tree.max_level()}, {latency}ms"
    )

    try:
        from app.services.rag.core.metrics import get_latency_collector

        get_latency_collector().record("cograg.node.planner", float(latency))
    except Exception:
        pass

    return {
        "mind_map": tree.to_dict(),
        "sub_questions": sub_questions,
        "temas": temas,
        "metrics": {
            **state.get("metrics", {}),
            "planner_latency_ms": latency,
            "planner_decomposed": True,
            "planner_node_count": tree.node_count(),
            "planner_leaf_count": tree.leaf_count(),
            "planner_max_level": tree.max_level(),
        },
    }
