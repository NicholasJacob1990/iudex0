"""
Quality Pipeline - Wrapper para single-model e multiagente

Aplica o pipeline de qualidade completo fora do LangGraph:
1. Quality Gate (heurística)
2. Structural Fix (dedup/normalize)
3. Quality Report (artefato)

Usado por DocumentGenerator e JuridicoGeminiAdapter.
"""
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from loguru import logger

from app.services.ai.quality_gate import quality_gate, QualityGateResult
from app.services.ai.structural_fix import structural_fix, StructuralFixResult
from app.services.ai.quality_report import (
    generate_quality_report,
    report_to_markdown,
    DocumentQualityReport,
    SectionQualityReport
)


@dataclass
class QualityPipelineResult:
    """Resultado completo do pipeline de qualidade."""
    document: str
    quality_gate: QualityGateResult
    structural_fix: StructuralFixResult
    quality_report: DocumentQualityReport
    needs_hil: bool
    safe_mode: bool
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "document": self.document,
            "quality_gate": self.quality_gate.to_dict(),
            "structural_fix": self.structural_fix.to_dict(),
            "quality_report": self.quality_report.to_dict(),
            "needs_hil": self.needs_hil,
            "safe_mode": self.safe_mode
        }


def apply_quality_pipeline(
    input_context: str,
    generated_document: str,
    mode: str = "PETICAO",
    job_id: str = "inline",
    sections: Optional[List[Dict[str, Any]]] = None
) -> QualityPipelineResult:
    """
    Aplica pipeline de qualidade completo em documento gerado.
    """
    logger.info(f"Quality Pipeline: iniciando para {mode} ({len(generated_document)} chars)")
    
    # 1. Quality Gate
    gate_result = quality_gate(input_context, generated_document)
    logger.info(f"Quality Gate: passed={gate_result.passed}, ratio={gate_result.compression_ratio:.2f}")
    
    # 2. Structural Fix
    fix_result, fixed_document = structural_fix(generated_document)
    logger.info(
        f"Structural Fix: {fix_result.duplicates_removed} duplicados, "
        f"{fix_result.headings_normalized} headings"
    )
    
    # 3. Preparar state simulado para Quality Report
    if sections:
        processed_sections = sections
    else:
        processed_sections = [{
            "section_title": "Documento",
            "merged_content": fixed_document,
            "has_significant_divergence": False,
            "claims_requiring_citation": [],
            "removed_claims": [],
            "risk_flags": [],
            "metrics": {}
        }]
    
    state = {
        "job_id": job_id,
        "mode": mode,
        "full_document": fixed_document,
        "processed_sections": processed_sections,
        "quality_gate_passed": gate_result.passed,
        "quality_gate_results": [{
            "section": "Documento",
            "passed": gate_result.passed,
            "compression_ratio": gate_result.compression_ratio,
            "missing_references": gate_result.missing_references,
            "notes": gate_result.notes
        }],
        "structural_fix_result": fix_result.to_dict(),
        "hil_checklist": {
            "requires_hil": gate_result.force_hil,
            "hil_level": "review" if gate_result.force_hil else "none",
            "triggered_factors": gate_result.notes if gate_result.force_hil else [],
            "evaluation_notes": gate_result.notes
        },
        "audit_status": "pending",
        "audit_issues": [],
        "patch_result": {},
        "targeted_patch_used": False
    }
    
    quality_report = generate_quality_report(state)
    
    needs_hil = gate_result.force_hil
    safe_mode = gate_result.safe_mode
    
    logger.info(f"Quality Pipeline: concluído. needs_hil={needs_hil}, safe_mode={safe_mode}")
    
    return QualityPipelineResult(
        document=fixed_document,
        quality_gate=gate_result,
        structural_fix=fix_result,
        quality_report=quality_report,
        needs_hil=needs_hil,
        safe_mode=safe_mode
    )


async def apply_quality_pipeline_async(
    input_context: str,
    generated_document: str,
    mode: str = "PETICAO",
    job_id: str = "inline",
    sections: Optional[List[Dict[str, Any]]] = None
) -> QualityPipelineResult:
    """Versão assíncrona do pipeline de qualidade."""
    return apply_quality_pipeline(
        input_context=input_context,
        generated_document=generated_document,
        mode=mode,
        job_id=job_id,
        sections=sections
    )


def get_quality_summary(result: QualityPipelineResult) -> str:
    """Gera resumo textual do resultado do pipeline."""
    gate = result.quality_gate
    fix = result.structural_fix
    
    parts = []
    if result.needs_hil:
        parts.append("⚠️ Requer revisão humana")
    elif result.safe_mode:
        parts.append("⚠️ Modo seguro ativado")
    else:
        parts.append("✅ Qualidade OK")
    
    parts.append(f"Compressão: {gate.compression_ratio:.2f}")
    if gate.missing_references:
        parts.append(f"Refs omitidas: {len(gate.missing_references)}")
    if fix.duplicates_removed > 0:
        parts.append(f"Duplicados: -{fix.duplicates_removed}")
    if fix.headings_normalized > 0:
        parts.append(f"Headings: {fix.headings_normalized} normalizados")
    
    return " | ".join(parts)

