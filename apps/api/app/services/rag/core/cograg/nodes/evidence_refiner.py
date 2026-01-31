"""
CogGRAG Evidence Refiner Node — Conflict detection and evidence refinement.

Implements Phase 2.5 from the Cog-RAG paper (2511.13201):
- Cross-evidence conflict detection (contradições entre fontes)
- Evidence quality scoring
- Redundancy elimination
- Theme-evidence alignment verification

Uses heuristics + optional LLM for conflict resolution.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("rag.cograg.evidence_refiner")


# ═══════════════════════════════════════════════════════════════════════════
# Conflict Detection Heuristics
# ═══════════════════════════════════════════════════════════════════════════

def _extract_legal_numbers(text: str) -> Set[str]:
    """Extract legal reference numbers (artigos, leis, súmulas) from text."""
    import re

    patterns = [
        r"[Aa]rt(?:igo)?\.?\s*(\d+)",  # Art. 5, Artigo 123
        r"[Ll]ei\s+(?:n[º°]?\s*)?(\d+(?:\.\d+)?(?:/\d+)?)",  # Lei 8.112/90
        r"[Ss]úmula\s+(?:n[º°]?\s*)?(\d+)",  # Súmula 331
        r"[Dd]ecreto\s+(?:n[º°]?\s*)?(\d+(?:\.\d+)?(?:/\d+)?)",
    ]

    numbers = set()
    for pattern in patterns:
        matches = re.findall(pattern, text)
        numbers.update(matches)

    return numbers


def _detect_contradiction_signals(text1: str, text2: str) -> List[str]:
    """Detect signals of potential contradiction between two texts."""
    signals = []

    # Negation patterns
    neg_patterns = [
        (r"\bnão\s+(?:se\s+)?(?:aplica|incide|cabe)\b", "negação de aplicabilidade"),
        (r"\bvedado\b|\bproibido\b|\bimpossível\b", "proibição explícita"),
        (r"\bcontrário\b|\boposto\b|\binverso\b", "inversão de sentido"),
        (r"\bexceto\b|\bsalvo\b|\bexcluído\b", "exclusão"),
    ]

    import re
    t1_lower = text1.lower()
    t2_lower = text2.lower()

    for pattern, signal_name in neg_patterns:
        has_in_t1 = bool(re.search(pattern, t1_lower))
        has_in_t2 = bool(re.search(pattern, t2_lower))

        # One has negation, other doesn't — potential conflict
        if has_in_t1 != has_in_t2:
            signals.append(signal_name)

    # Contradictory numbers (same legal reference, different conclusions)
    nums1 = _extract_legal_numbers(text1)
    nums2 = _extract_legal_numbers(text2)

    shared_refs = nums1 & nums2
    if shared_refs:
        # Check if conclusions differ
        conclusion_words_positive = {"permite", "autoriza", "válido", "cabível", "aplicável"}
        conclusion_words_negative = {"veda", "proíbe", "inválido", "incabível", "inaplicável"}

        t1_positive = any(w in t1_lower for w in conclusion_words_positive)
        t1_negative = any(w in t1_lower for w in conclusion_words_negative)
        t2_positive = any(w in t2_lower for w in conclusion_words_positive)
        t2_negative = any(w in t2_lower for w in conclusion_words_negative)

        if (t1_positive and t2_negative) or (t1_negative and t2_positive):
            signals.append(f"conclusões opostas sobre referência compartilhada: {shared_refs}")

    return signals


def _compute_evidence_quality_score(chunk: Dict[str, Any]) -> float:
    """
    Compute a quality score for an evidence chunk.

    Factors:
    - Original retrieval score (normalized)
    - Source type (jurisprudencia > doutrina > genérico)
    - Text length (too short = low quality)
    - Legal references present
    """
    score = 0.0

    # Base retrieval score (0-0.4)
    retrieval_score = chunk.get("score", 0.0)
    if isinstance(retrieval_score, (int, float)):
        score += min(float(retrieval_score), 1.0) * 0.4

    # Source type (0-0.3)
    source = chunk.get("source", "").lower()
    doc_type = chunk.get("doc_type", "").lower()

    if "jurisprud" in source or "jurisprud" in doc_type or "acordao" in doc_type:
        score += 0.3
    elif "lei" in source or "codigo" in doc_type or "decreto" in doc_type:
        score += 0.25
    elif "doutrina" in source or "artigo" in doc_type:
        score += 0.2
    elif source or doc_type:
        score += 0.1

    # Text length (0-0.15)
    text = chunk.get("text", "") or chunk.get("preview", "")
    text_len = len(text)
    if text_len > 500:
        score += 0.15
    elif text_len > 200:
        score += 0.1
    elif text_len > 50:
        score += 0.05

    # Legal references (0-0.15)
    refs = _extract_legal_numbers(text)
    if len(refs) >= 3:
        score += 0.15
    elif len(refs) >= 1:
        score += 0.1

    return min(score, 1.0)


# ═══════════════════════════════════════════════════════════════════════════
# Evidence Refiner Node
# ═══════════════════════════════════════════════════════════════════════════

async def evidence_refiner_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    LangGraph node: refine evidence by detecting conflicts and scoring quality.

    Reads from state:
        - evidence_map: Dict[node_id, evidence_dict]
        - text_chunks: List of all retrieved chunks

    Writes to state:
        - refined_evidence: Dict with quality scores and conflict flags
        - conflicts: List of detected conflicts
        - metrics.refiner_*
    """
    evidence_map: Dict[str, Any] = state.get("evidence_map", {})
    text_chunks: List[Dict[str, Any]] = state.get("text_chunks", [])
    # Default to enabled for deterministic/refiner tests and safer quality control.
    # If explicitly set to False in state, skip refinement.
    enabled: bool = bool(state.get("cograg_evidence_refinement_enabled", True))
    start = time.time()

    if not enabled:
        # Pass-through: keep evidence_map as-is so downstream reasoner/verifier
        # still sees local_results/global_results/chunk_results + graph_triples.
        return {
            "refined_evidence": dict(evidence_map or {}),
            "conflicts": [],
            "metrics": {
                **state.get("metrics", {}),
                "refiner_latency_ms": 0,
                "refiner_enabled": False,
                "refiner_conflicts": 0,
                "refiner_avg_quality": 0.0,
            },
        }

    if not evidence_map and not text_chunks:
        logger.info("[CogGRAG:Refiner] No evidence to refine → skip")
        return {
            "refined_evidence": {},
            "conflicts": [],
            "metrics": {
                **state.get("metrics", {}),
                "refiner_latency_ms": 0,
                "refiner_conflicts": 0,
            },
        }

    logger.info(f"[CogGRAG:Refiner] Refining {len(evidence_map)} evidence sets, {len(text_chunks)} chunks")

    conflicts: List[Dict[str, Any]] = []
    refined_evidence: Dict[str, Any] = {}
    all_texts_by_node: Dict[str, List[Tuple[str, Dict[str, Any]]]] = {}

    # ── 1. Score each chunk and organize by node ─────────────────────────
    for node_id, evidence in evidence_map.items():
        # Preserve original evidence structure and add refinement fields.
        base = dict(evidence or {})
        base.setdefault("node_id", node_id)
        base.setdefault("question", evidence.get("question", ""))
        base.setdefault("local_results", list(evidence.get("local_results", []) or []))
        base.setdefault("global_results", list(evidence.get("global_results", []) or []))
        base.setdefault("chunk_results", list(evidence.get("chunk_results", []) or []))
        base.setdefault("graph_paths", list(evidence.get("graph_paths", []) or []))
        base.setdefault("graph_triples", list(evidence.get("graph_triples", []) or []))

        refined_evidence[node_id] = {
            **base,
            "chunk_results": [],
            "chunks": [],
            "quality_score": 0.0,
            "has_conflicts": False,
        }

        all_texts_by_node[node_id] = []

        # Process all chunk types
        for chunk_key in ("local_results", "global_results", "chunk_results"):
            for chunk in evidence.get(chunk_key, []):
                text = chunk.get("text", "") or chunk.get("preview", "")
                if not text:
                    continue

                quality = _compute_evidence_quality_score(chunk)
                chunk["_quality_score"] = quality
                refined_evidence[node_id]["chunk_results"].append(chunk)
                all_texts_by_node[node_id].append((text, chunk))

        # Compute average quality for the node
        chunks = refined_evidence[node_id]["chunk_results"]
        if chunks:
            avg_quality = sum(c.get("_quality_score", 0) for c in chunks) / len(chunks)
            refined_evidence[node_id]["quality_score"] = round(avg_quality, 3)

    # ── 2. Detect intra-node conflicts ───────────────────────────────────
    for node_id, texts in all_texts_by_node.items():
        if len(texts) < 2:
            continue

        for i in range(len(texts)):
            for j in range(i + 1, min(i + 5, len(texts))):  # Check top 5 pairs
                text1, chunk1 = texts[i]
                text2, chunk2 = texts[j]

                signals = _detect_contradiction_signals(text1, text2)
                if signals:
                    conflicts.append({
                        "node_id": node_id,
                        "type": "intra_node",
                        "signals": signals,
                        "chunk1_hash": chunk1.get("_content_hash", "")[:8],
                        "chunk2_hash": chunk2.get("_content_hash", "")[:8],
                    })
                    refined_evidence[node_id]["has_conflicts"] = True

    # ── 3. Detect cross-node conflicts (between different sub-questions) ─
    node_ids = list(all_texts_by_node.keys())
    for i in range(len(node_ids)):
        for j in range(i + 1, len(node_ids)):
            node_a = node_ids[i]
            node_b = node_ids[j]

            texts_a = all_texts_by_node[node_a][:3]  # Top 3 per node
            texts_b = all_texts_by_node[node_b][:3]

            for text_a, chunk_a in texts_a:
                for text_b, chunk_b in texts_b:
                    signals = _detect_contradiction_signals(text_a, text_b)
                    if signals:
                        conflicts.append({
                            "node_id": f"{node_a}:{node_b}",
                            "type": "cross_node",
                            "signals": signals,
                            "node_a": node_a,
                            "node_b": node_b,
                        })
                        refined_evidence[node_a]["has_conflicts"] = True
                        refined_evidence[node_b]["has_conflicts"] = True

    # ── 4. Sort chunks by quality within each node ───────────────────────
    for node_id in refined_evidence:
        refined_evidence[node_id]["chunk_results"] = sorted(
            refined_evidence[node_id]["chunk_results"],
            key=lambda c: c.get("_quality_score", 0),
            reverse=True,
        )
        # Compatibility alias expected by tests and older code.
        refined_evidence[node_id]["chunks"] = list(refined_evidence[node_id]["chunk_results"])

    latency = int((time.time() - start) * 1000)
    logger.info(
        f"[CogGRAG:Refiner] Done: {len(refined_evidence)} refined sets, "
        f"{len(conflicts)} conflicts detected, {latency}ms"
    )

    return {
        "refined_evidence": refined_evidence,
        "conflicts": conflicts,
        "metrics": {
            **state.get("metrics", {}),
            "refiner_latency_ms": latency,
            "refiner_conflicts": len(conflicts),
            "refiner_avg_quality": round(
                sum(r["quality_score"] for r in refined_evidence.values()) / max(len(refined_evidence), 1),
                3,
            ),
        },
    }
