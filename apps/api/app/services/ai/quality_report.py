"""
Quality Report - Artefato consolidado de qualidade

Gera relatório completo de qualidade por seção e geral:
- Métricas de compressão
- Referências omitidas
- Correções estruturais
- Status de auditoria
- Decisão HIL
- Patches aplicados

Formato: JSON (para API) e Markdown (para visualização).
"""
from typing import Dict, Any, List
from dataclasses import dataclass, field, asdict
from datetime import datetime
from loguru import logger


@dataclass
class SectionQualityReport:
    """Relatório de qualidade por seção."""
    section_title: str
    word_count: int = 0
    has_divergence: bool = False
    divergence_summary: str = ""
    claims_requiring_citation: List[Dict[str, Any]] = field(default_factory=list)
    removed_claims: List[Dict[str, Any]] = field(default_factory=list)
    risk_flags: List[str] = field(default_factory=list)
    quality_gate_passed: bool = True
    quality_gate_notes: List[str] = field(default_factory=list)
    compression_ratio: float = 1.0
    metrics: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DocumentQualityReport:
    """Relatório consolidado de qualidade do documento."""
    document_id: str = "unknown"
    mode: str = "PETICAO"
    generated_at: str = ""
    total_sections: int = 0
    total_words: int = 0
    quality_gate_passed: bool = True
    avg_compression_ratio: float = 1.0
    missing_references: List[str] = field(default_factory=list)
    duplicates_removed: int = 0
    headings_normalized: int = 0
    artifacts_cleaned: int = 0
    audit_status: str = "pending"
    audit_issues: List[str] = field(default_factory=list)
    citations_total: int = 0
    citations_suspicious: int = 0
    hil_required: bool = False
    hil_level: str = "none"
    triggered_factors: List[str] = field(default_factory=list)
    patches_generated: int = 0
    patches_applied: int = 0
    targeted_patch_used: bool = False
    sections: List[SectionQualityReport] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["sections"] = [s.to_dict() if hasattr(s, "to_dict") else s for s in self.sections]
        return d


def count_words(text: str) -> int:
    """Conta palavras em um texto."""
    import re
    clean = re.sub(r'[#*_`|>\-\[\]\(\)]', ' ', text)
    return len(re.findall(r'\b\w+\b', clean))


def generate_quality_report(state: dict) -> DocumentQualityReport:
    """Gera relatório consolidado de qualidade a partir do state do LangGraph."""
    now = datetime.now().isoformat()
    
    processed_sections = state.get("processed_sections", [])
    hil_checklist = state.get("hil_checklist", {})
    quality_gate_results = state.get("quality_gate_results", [])
    structural_fix = state.get("structural_fix_result", {})
    patch_result = state.get("patch_result", {})
    
    section_reports: List[SectionQualityReport] = []
    total_words = 0
    compression_ratios: List[float] = []
    all_missing_refs: List[str] = []
    
    for i, section in enumerate(processed_sections):
        if not isinstance(section, dict):
            continue
        content = section.get("merged_content", "")
        word_count = count_words(content)
        total_words += word_count
        
        qg = quality_gate_results[i] if i < len(quality_gate_results) else {}
        if isinstance(qg, dict):
            compression_ratio = qg.get("compression_ratio", 1.0)
            compression_ratios.append(compression_ratio)
            all_missing_refs.extend(qg.get("missing_references", []))
        else:
            compression_ratio = 1.0
        
        section_reports.append(SectionQualityReport(
            section_title=section.get("section_title", f"Seção {i+1}"),
            word_count=word_count,
            has_divergence=section.get("has_significant_divergence", False),
            divergence_summary=section.get("divergence_details", ""),
            claims_requiring_citation=section.get("claims_requiring_citation", []),
            removed_claims=section.get("removed_claims", []),
            risk_flags=section.get("risk_flags", []),
            quality_gate_passed=qg.get("passed", True) if isinstance(qg, dict) else True,
            quality_gate_notes=qg.get("notes", []) if isinstance(qg, dict) else [],
            compression_ratio=compression_ratio,
            metrics=section.get("metrics", {})
        ))
    
    avg_compression = sum(compression_ratios) / len(compression_ratios) if compression_ratios else 1.0
    
    notes = hil_checklist.get("evaluation_notes", [])
    if isinstance(notes, str):
        notes = [notes]
    
    report = DocumentQualityReport(
        document_id=state.get("job_id", "unknown"),
        mode=state.get("mode", "PETICAO"),
        generated_at=now,
        total_sections=len(section_reports),
        total_words=total_words,
        quality_gate_passed=state.get("quality_gate_passed", True),
        avg_compression_ratio=round(avg_compression, 3),
        missing_references=list(set(all_missing_refs))[:10],
        duplicates_removed=structural_fix.get("duplicates_removed", 0),
        headings_normalized=structural_fix.get("headings_normalized", 0),
        artifacts_cleaned=structural_fix.get("artifacts_cleaned", 0),
        audit_status=state.get("audit_status", "pending"),
        audit_issues=(state.get("audit_issues", []) or [])[:10],
        citations_total=hil_checklist.get("num_citacoes_externas", 0),
        citations_suspicious=hil_checklist.get("num_citacoes_suspeitas", 0),
        hil_required=hil_checklist.get("requires_hil", False),
        hil_level=hil_checklist.get("hil_level", "none"),
        triggered_factors=hil_checklist.get("triggered_factors", []),
        patches_generated=patch_result.get("patches_generated", 0),
        patches_applied=patch_result.get("patches_applied", 0),
        targeted_patch_used=state.get("targeted_patch_used", False),
        sections=section_reports,
        notes=notes
    )
    
    return report


def report_to_markdown(report: DocumentQualityReport) -> str:
    """Converte report para Markdown legível."""
    if report.quality_gate_passed and report.audit_status == "aprovado":
        status_emoji = "✅"
        status_text = "Aprovado"
    elif report.audit_status == "reprovado":
        status_emoji = "❌"
        status_text = "Reprovado"
    else:
        status_emoji = "⚠️"
        status_text = "Requer Revisão"
    
    md = f"""# {status_emoji} Relatório de Qualidade — {status_text}

**Documento**: {report.mode}  
**ID**: {report.document_id}  
**Gerado em**: {report.generated_at}

---

## 📊 Métricas Gerais

| Métrica | Valor |
|---------|-------|
| Seções | {report.total_sections} |
| Palavras | {report.total_words:,} |
| Ratio de Compressão (média) | {report.avg_compression_ratio:.2f} |
| Duplicados Removidos | {report.duplicates_removed} |
| Headings Normalizados | {report.headings_normalized} |
| Artefatos Limpos | {report.artifacts_cleaned} |

---

## 🔍 Quality Gate

**Status**: {"✅ Passou" if report.quality_gate_passed else "⚠️ Falhou"}

"""
    if report.missing_references:
        md += "**Referências Potencialmente Omitidas**:\n"
        for ref in report.missing_references[:10]:
            md += f"- {ref}\n"
        md += "\n"
    
    md += f"""---

## ⚖️ Auditoria

**Status**: {report.audit_status}  
**Citações**: {report.citations_total} total, {report.citations_suspicious} suspeitas

"""
    if report.audit_issues:
        md += "**Problemas Identificados**:\n"
        for issue in report.audit_issues[:10]:
            md += f"- {issue}\n"
        md += "\n"
    
    md += f"""---

## 🛑 HIL (Human-in-the-Loop)

**Requerido**: {"Sim" if report.hil_required else "Não"}  
**Nível**: {report.hil_level}

"""
    if report.triggered_factors:
        md += "**Fatores que Acionaram HIL**:\n"
        for factor in report.triggered_factors:
            md += f"- {factor}\n"
        md += "\n"
    
    md += f"""---

## 🔧 Patches

**Gerados**: {report.patches_generated}  
**Aplicados**: {report.patches_applied}  
**Método**: {"Targeted Patch (localizado)" if report.targeted_patch_used else "Reescrita Completa"}

---

## 📋 Qualidade por Seção

"""
    for section in report.sections:
        if isinstance(section, dict):
            title = section.get("section_title", "Seção")
            passed = section.get("quality_gate_passed", True)
            divergence = section.get("has_divergence", False)
            words = section.get("word_count", 0)
            claims = len(section.get("claims_requiring_citation", []))
            flags = len(section.get("risk_flags", []))
        else:
            title = section.section_title
            passed = section.quality_gate_passed
            divergence = section.has_divergence
            words = section.word_count
            claims = len(section.claims_requiring_citation)
            flags = len(section.risk_flags)
        
        status = "✅" if passed and not divergence else "⚠️"
        md += f"""### {status} {title}

| Métrica | Valor |
|---------|-------|
| Palavras | {words} |
| Divergência | {"Sim" if divergence else "Não"} |
| Claims Pendentes | {claims} |
| Risk Flags | {flags} |

"""
    if report.notes:
        md += "---\n\n## 📝 Notas\n\n"
        for note in report.notes:
            md += f"- {note}\n"
    return md


async def quality_report_node(state: dict) -> dict:
    """Nó do LangGraph que gera o relatório de qualidade."""
    report = generate_quality_report(state)
    report_dict = report.to_dict()
    report_md = report_to_markdown(report)
    
    logger.info(
        f"Quality Report: {report.total_sections} seções, "
        f"{report.total_words} palavras, "
        f"HIL={'Sim' if report.hil_required else 'Não'}"
    )
    
    return {
        **state,
        "quality_report": report_dict,
        "quality_report_markdown": report_md
    }

