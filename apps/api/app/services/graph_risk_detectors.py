"""
Graph Risk Detectors — deterministic Cypher-based signals.

Design goal: keep detectors deterministic and explainable.
LLMs can be used for narrative/reporting, but the signals should come from
reproducible graph queries.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional

from app.schemas.graph_risk import RiskProfile, RiskSignal


DetectorFn = Callable[..., Awaitable[List[RiskSignal]]]


@dataclass(frozen=True)
class Detector:
    detector_id: str
    scenario: str
    title: str
    run: DetectorFn


def default_include_candidates(profile: RiskProfile) -> bool:
    if profile == RiskProfile.precision:
        return False
    if profile == RiskProfile.recall:
        return True
    return False


def default_limits(profile: RiskProfile) -> Dict[str, Any]:
    # Tighten defaults for precision, loosen for recall.
    if profile == RiskProfile.precision:
        return {"limit": 15, "min_shared_docs": 3}
    if profile == RiskProfile.recall:
        return {"limit": 50, "min_shared_docs": 1}
    return {"limit": 30, "min_shared_docs": 2}


def filter_detectors(
    detectors: List[Detector],
    *,
    requested: Optional[List[str]],
) -> List[Detector]:
    if not requested:
        return detectors
    wanted = {str(x).strip().lower() for x in requested if str(x).strip()}
    if not wanted:
        return detectors
    out: List[Detector] = []
    for d in detectors:
        if d.detector_id.lower() in wanted or d.scenario.lower() in wanted:
            out.append(d)
    return out

