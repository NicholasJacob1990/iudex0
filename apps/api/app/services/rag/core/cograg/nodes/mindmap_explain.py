"""
MindMap-Explain Node — produce an explicit reasoning graph artifact.

This is inspired by the MindMap paper (2308.09729): represent reasoning as a graph/mind map.
We keep the main CogRAG pipeline intact; this node only materializes an artifact for:
- audit/debug (UI / trace)
- post-hoc explainability

Design goals:
- Cheap by default (rule-based, no LLM dependency)
- Uses the already-produced sub-questions/sub-answers and references ([ref:...]) + KG triples.
"""

from __future__ import annotations

import hashlib
import time
from typing import Any, Dict, List, Optional, Tuple


def _short(s: str, n: int = 140) -> str:
    s = (s or "").strip()
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def _hash_id(text: str) -> str:
    return hashlib.md5((text or "").encode("utf-8")).hexdigest()[:12]


def _collect_refs_from_subanswers(sub_answers: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    refs_by_node: Dict[str, List[str]] = {}
    for sa in sub_answers or []:
        nid = str(sa.get("node_id", "") or "")
        refs = sa.get("evidence_refs") or []
        out: List[str] = []
        seen = set()
        if isinstance(refs, list):
            for r in refs:
                rr = str(r).strip()
                if rr and rr not in seen:
                    seen.add(rr)
                    out.append(rr)
        refs_by_node[nid] = out
    return refs_by_node


def _collect_triples_by_node(evidence_map: Dict[str, Any], *, max_triples_per_node: int = 8) -> Dict[str, List[str]]:
    triples_by_node: Dict[str, List[str]] = {}
    for node_id, ev in (evidence_map or {}).items():
        node_id = str(node_id)
        triples = ev.get("graph_triples") or []
        lines: List[str] = []
        for tr in (triples or [])[:max_triples_per_node]:
            if isinstance(tr, dict) and tr.get("text"):
                lines.append(str(tr["text"]))
            elif isinstance(tr, str):
                lines.append(tr)
        triples_by_node[node_id] = lines
    return triples_by_node


def _collect_paths_by_node(evidence_map: Dict[str, Any], *, max_paths_per_node: int = 6) -> Dict[str, List[Tuple[str, str]]]:
    paths_by_node: Dict[str, List[Tuple[str, str]]] = {}
    for node_id, ev in (evidence_map or {}).items():
        node_id = str(node_id)
        paths = ev.get("graph_paths") or []
        out: List[Tuple[str, str]] = []
        for p in (paths or [])[:max_paths_per_node]:
            if not isinstance(p, dict):
                continue
            uid = str(p.get("path_uid") or "").strip()
            txt = str(p.get("path_text") or "").strip()
            if uid and txt:
                out.append((uid, txt))
        paths_by_node[node_id] = out
    return paths_by_node


def _build_mermaid(nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]]) -> str:
    """
    Mermaid graph TD with safe labels.
    """
    def esc(label: str) -> str:
        label = (label or "").replace("\n", " ").replace("\"", "'")
        return _short(label, 60)

    lines = ["graph TD"]
    for n in nodes:
        nid = n["id"]
        label = esc(n.get("label") or "")
        lines.append(f'  {nid}["{label}"]')
    for e in edges:
        src = e["from"]
        dst = e["to"]
        rel = esc(e.get("type") or "")
        if rel:
            lines.append(f"  {src} -->|{rel}| {dst}")
        else:
            lines.append(f"  {src} --> {dst}")
    return "\n".join(lines)


async def mindmap_explain_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    LangGraph node: create explicit reasoning_graph artifact (JSON + optional Mermaid).

    Gating:
      - runs if cograg_mindmap_explain_enabled OR cograg_audit_mode
      - also runs when verification_status in {'abstain','rejected'} to help debugging
    """
    enabled = bool(state.get("cograg_mindmap_explain_enabled", False))
    audit_mode = bool(state.get("cograg_audit_mode", False))
    status = str(state.get("verification_status", "") or "")
    fmt = str(state.get("cograg_mindmap_explain_format", "json") or "json").strip().lower()

    if not (enabled or audit_mode or status in ("abstain", "rejected")):
        return {"reasoning_graph": None, "reasoning_graph_mermaid": None}

    start = time.time()
    query = str(state.get("query", "") or "")
    sub_questions: List[Dict[str, Any]] = list(state.get("sub_questions") or [])
    sub_answers: List[Dict[str, Any]] = list(state.get("sub_answers") or [])
    evidence_map: Dict[str, Any] = dict(state.get("evidence_map") or {})

    refs_by_node = _collect_refs_from_subanswers(sub_answers)
    triples_by_node = _collect_triples_by_node(evidence_map)
    paths_by_node = _collect_paths_by_node(evidence_map)

    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []

    root_id = "Q"
    nodes.append({"id": root_id, "type": "query", "label": _short(query, 120)})

    # Nodes per sub-question + answer
    for sq in sub_questions:
        nid = str(sq.get("node_id", "") or "")
        if not nid:
            continue
        sq_id = f"SQ_{nid[:8]}"
        nodes.append({"id": sq_id, "type": "subquestion", "label": _short(str(sq.get('question', '')), 120)})
        edges.append({"from": root_id, "to": sq_id, "type": "decomposes_to"})

        sa = next((a for a in sub_answers if str(a.get("node_id", "")) == nid), None)
        if sa and sa.get("answer"):
            ans_id = f"ANS_{nid[:8]}"
            nodes.append({"id": ans_id, "type": "answer", "label": _short(str(sa.get("answer", "")), 140)})
            edges.append({"from": sq_id, "to": ans_id, "type": "answers"})

        # Evidence refs
        for ref in refs_by_node.get(nid, []):
            ref_id = f"REF_{_hash_id(ref)}"
            nodes.append({"id": ref_id, "type": "chunk_ref", "label": f"[ref:{ref}]"})
            edges.append({"from": sq_id, "to": ref_id, "type": "supported_by"})

        # KG triples
        for tr in triples_by_node.get(nid, [])[:8]:
            trid = f"TR_{_hash_id(tr)}"
            nodes.append({"id": trid, "type": "kg_triple", "label": _short(tr, 140)})
            edges.append({"from": sq_id, "to": trid, "type": "kg_support"})

        # KG paths
        for uid, txt in paths_by_node.get(nid, [])[:6]:
            pid = f"P_{_hash_id(uid)}"
            nodes.append({"id": pid, "type": "kg_path", "label": _short(f"[path:{uid}] {txt}", 140)})
            edges.append({"from": sq_id, "to": pid, "type": "kg_path_support"})

    # Deduplicate nodes by id (keep first)
    by_id: Dict[str, Dict[str, Any]] = {}
    for n in nodes:
        if n["id"] not in by_id:
            by_id[n["id"]] = n
    nodes = list(by_id.values())

    reasoning_graph = {
        "version": "mindmap_explain_v1",
        "query": query,
        "verification_status": status,
        "nodes": nodes,
        "edges": edges,
        "stats": {
            "sub_questions": len(sub_questions),
            "sub_answers": len(sub_answers),
            "ref_links": sum(len(v) for v in refs_by_node.values()),
            "kg_triples": sum(len(v) for v in triples_by_node.values()),
            "kg_paths": sum(len(v) for v in paths_by_node.values()),
        },
    }

    mermaid: Optional[str] = None
    if fmt in ("mermaid", "both"):
        mermaid = _build_mermaid(nodes, edges)

    latency = int((time.time() - start) * 1000)
    return {
        "reasoning_graph": reasoning_graph if fmt in ("json", "both") else None,
        "reasoning_graph_mermaid": mermaid,
        "metrics": {
            **state.get("metrics", {}),
            "mindmap_explain_latency_ms": latency,
            "mindmap_explain_enabled": True,
            "mindmap_explain_nodes": len(nodes),
            "mindmap_explain_edges": len(edges),
        },
    }
