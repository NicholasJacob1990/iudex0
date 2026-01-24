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
        "hil_outline_enabled": False,  # Rápido: Pula revisão de outline
        "strict_document_gate": False,
        "recursion_limit": 140,
        "style_refine_max_rounds": 1,
        "max_research_verifier_attempts": 1,
        "max_rag_retries": 1,
        "rag_retry_expand_scope": False,
        "crag_min_best_score": 0.40,
        "crag_min_avg_score": 0.30,
    },
    "padrao": {
        "target_section_score": 9.0,
        "target_final_score": 9.4,
        "max_rounds": 2,
        "hil_section_policy": "optional",
        "hil_final_required": True,
        "hil_outline_enabled": True,  # Padrão: Permite revisão de outline
        "strict_document_gate": False,
        "recursion_limit": 200,
        "style_refine_max_rounds": 2,
        "max_research_verifier_attempts": 1,
        "max_rag_retries": 1,
        "rag_retry_expand_scope": False,
        "crag_min_best_score": 0.45,
        "crag_min_avg_score": 0.35,
    },
    "rigoroso": {
        "target_section_score": 9.4,
        "target_final_score": 9.8,
        "max_rounds": 4,
        "hil_section_policy": "required",
        "hil_final_required": True,
        "hil_outline_enabled": True,  # Rigoroso: Revisão de outline obrigatória
        "strict_document_gate": False,
        "recursion_limit": 260,
        "style_refine_max_rounds": 3,
        "max_research_verifier_attempts": 2,
        "max_rag_retries": 2,
        "rag_retry_expand_scope": True,
        "crag_min_best_score": 0.50,
        "crag_min_avg_score": 0.40,
    },
    "auditoria": {
        "target_section_score": 9.6,
        "target_final_score": 10.0,
        "max_rounds": 6,
        "hil_section_policy": "required",
        "hil_final_required": True,
        "hil_outline_enabled": True,  # Auditoria: Revisão de outline obrigatória
        "strict_document_gate": True,
        "recursion_limit": 320,
        "style_refine_max_rounds": 4,
        "max_research_verifier_attempts": 3,
        "max_rag_retries": 3,
        "rag_retry_expand_scope": True,
        "crag_min_best_score": 0.55,
        "crag_min_avg_score": 0.45,
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
            "hil_outline_enabled",
            "recursion_limit",
            "strict_document_gate",
            "style_refine_max_rounds",
            "max_research_verifier_attempts",
            "max_rag_retries",
            "rag_retry_expand_scope",
            "crag_min_best_score",
            "crag_min_avg_score",
        ):
            if overrides.get(key) is not None:
                base[key] = overrides[key]
    return base
