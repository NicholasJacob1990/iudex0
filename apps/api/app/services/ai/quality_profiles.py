"""
Quality Profiles - Preset thresholds for refinement + HIL policy.
"""

from typing import Any, Dict, Optional


QUALITY_PROFILES: Dict[str, Dict[str, Any]] = {
    "rapido": {
        "target_section_score": 8.5,
        "target_final_score": 9.0,
        "max_rounds": 1,
        "hil_section_policy": "none",
        "hil_final_required": True,
        "strict_document_gate": False,
        "recursion_limit": 140,
    },
    "padrao": {
        "target_section_score": 9.0,
        "target_final_score": 9.4,
        "max_rounds": 2,
        "hil_section_policy": "optional",
        "hil_final_required": True,
        "strict_document_gate": False,
        "recursion_limit": 200,
    },
    "rigoroso": {
        "target_section_score": 9.4,
        "target_final_score": 9.8,
        "max_rounds": 4,
        "hil_section_policy": "required",
        "hil_final_required": True,
        "strict_document_gate": False,
        "recursion_limit": 260,
    },
    "auditoria": {
        "target_section_score": 9.6,
        "target_final_score": 10.0,
        "max_rounds": 6,
        "hil_section_policy": "required",
        "hil_final_required": True,
        "strict_document_gate": True,
        "recursion_limit": 320,
    },
}


def resolve_quality_profile(
    profile: Optional[str],
    overrides: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Resolve profile presets with optional numeric overrides.
    """
    base = QUALITY_PROFILES.get((profile or "").lower(), QUALITY_PROFILES["padrao"]).copy()
    if overrides:
        for key in (
            "target_section_score",
            "target_final_score",
            "max_rounds",
            "hil_section_policy",
            "hil_final_required",
            "recursion_limit",
            "strict_document_gate",
        ):
            if overrides.get(key) is not None:
                base[key] = overrides[key]
    return base
