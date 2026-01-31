"""
Evidence Scorer — Score evidence by authority, recency, and type.

Scoring dimensions:
1. Authority: STF=1.0, STJ=0.9, TRF=0.7, TJ=0.6, Doutrina=0.5
2. Evidence type: jurisprudencia=0.9, legislacao=0.85, pericia=0.8, fato=0.7
3. Stance bonus: pro/contra evidence gets weight boost over neutro

The final score is stored as the `weight` property on (:Evidence) nodes.
"""

from __future__ import annotations

import re
from typing import Any, Dict


# =============================================================================
# AUTHORITY SCORES
# =============================================================================

TRIBUNAL_AUTHORITY: Dict[str, float] = {
    "stf": 1.0,
    "stj": 0.95,
    "tst": 0.9,
    "tse": 0.85,
    "trf": 0.75,
    "trf1": 0.75,
    "trf2": 0.75,
    "trf3": 0.75,
    "trf4": 0.75,
    "trf5": 0.75,
    "trt": 0.65,
    "tj": 0.6,
}

EVIDENCE_TYPE_SCORE: Dict[str, float] = {
    "jurisprudencia": 0.9,
    "legislacao": 0.85,
    "pericia": 0.8,
    "doutrina": 0.7,
    "fato": 0.65,
    "documento": 0.6,
}

_TRIBUNAL_RE = re.compile(
    r"\b(STF|STJ|TST|TSE|TRF[1-5]?|TJ[A-Z]{2}|TRT\d{1,2})\b",
    re.IGNORECASE,
)


# =============================================================================
# SCORER
# =============================================================================

def score_evidence(evidence: Dict[str, Any]) -> float:
    """
    Score a piece of evidence based on authority, type, and stance.

    Args:
        evidence: Dict with 'text', 'evidence_type', 'stance' (optional keys)

    Returns:
        Weight between 0.0 and 1.0
    """
    text = evidence.get("text", "")
    ev_type = evidence.get("evidence_type", "documento").lower()
    stance = evidence.get("stance", "neutro").lower()

    # 1. Base score from evidence type
    base = EVIDENCE_TYPE_SCORE.get(ev_type, 0.5)

    # 2. Authority bonus from tribunal mentions
    authority_bonus = 0.0
    tribunals = _TRIBUNAL_RE.findall(text)
    if tribunals:
        # Use highest authority tribunal found
        max_auth = 0.0
        for t in tribunals:
            key = t.lower()
            # Normalize TJ variants
            if key.startswith("tj"):
                key = "tj"
            elif key.startswith("trf"):
                key = "trf"
            elif key.startswith("trt"):
                key = "trt"
            auth = TRIBUNAL_AUTHORITY.get(key, 0.5)
            max_auth = max(max_auth, auth)
        authority_bonus = max_auth * 0.15  # Max +0.15 for STF

    # 3. Stance bonus
    stance_bonus = 0.05 if stance in ("pro", "contra") else 0.0

    # Combine
    score = min(1.0, base + authority_bonus + stance_bonus)

    return round(score, 2)


def score_by_tribunal(tribunal_name: str) -> float:
    """Get authority score for a tribunal name."""
    key = tribunal_name.strip().lower()
    if key.startswith("tj"):
        key = "tj"
    elif key.startswith("trf"):
        key = "trf"
    elif key.startswith("trt"):
        key = "trt"
    return TRIBUNAL_AUTHORITY.get(key, 0.5)
