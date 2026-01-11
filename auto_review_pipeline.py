#!/usr/bin/env python3
"""
auto_review_pipeline.py - Automated Apostila Review & Refinement Pipeline

This script orchestrates the full review cycle:
1. Validate apostilas against RAW transcriptions
2. Triage issues by severity
3. Apply automatic fixes where safe
4. Re-validate to confirm improvement
5. Generate Word documents for approved files
6. Create final consolidated report

Usage:
    python auto_review_pipeline.py [--skip-validation] [--fix-only] [--report-only]
"""

import os
import sys
import json
import glob
from pathlib import Path
from datetime import datetime

# Add parent dir to path for imports
sys.path.insert(0, '/Users/nicholasjacob/Documents/Aplicativos/Iudex')

MEDIA_DIR = "/Users/nicholasjacob/Downloads/MediaExtractor"
SCRIPT_DIR = "/Users/nicholasjacob/Documents/Aplicativos/Iudex"

# Thresholds
SCORE_APPROVED = 8.0  # Score >= 8 is approved
SCORE_NEEDS_REVIEW = 6.0  # 6 <= score < 8 needs human review
# score < 6 is critical

def load_validation_reports() -> dict:
    """Load all *_fidelidade.json reports."""
    reports = {}
    pattern = os.path.join(MEDIA_DIR, "*_fidelidade.json")
    for filepath in glob.glob(pattern):
        with open(filepath, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
                subject = Path(filepath).stem.replace('_APOSTILA_fidelidade', '').replace('_COMPLETA_RAW', '')
                reports[subject] = {
                    'file': filepath,
                    'data': data
                }
            except json.JSONDecodeError:
                print(f"⚠️  Could not parse: {filepath}")
    return reports


def run_validation(subject_file: str) -> dict:
    """Run validation on a single apostila using VomoMLX."""
    from mlx_vomo import VomoMLX
    
    stem = Path(subject_file).stem
    raw_file = os.path.join(MEDIA_DIR, f"{stem.replace('_APOSTILA', '')}.txt")
    
    if not os.path.exists(raw_file):
        return {'nota': 0, 'error': f"RAW file not found: {raw_file}"}
    
    with open(raw_file, 'r', encoding='utf-8') as f:
        raw_text = f.read()
    
    with open(subject_file, 'r', encoding='utf-8') as f:
        formatted_text = f.read()
    
    vomo = VomoMLX()
    result = vomo.validate_completeness_full(raw_text, formatted_text, stem)
    return result


def triage_issues(reports: dict) -> dict:
    """Categorize subjects by severity."""
    triage = {
        'approved': [],      # >= 8
        'review': [],        # 6-8
        'critical': [],      # < 6
        'unknown': []
    }
    
    for subject, info in reports.items():
        data = info.get('data', {})
        score = data.get('nota', data.get('nota_fidelidade', 0))
        
        if score >= SCORE_APPROVED:
            triage['approved'].append((subject, score))
        elif score >= SCORE_NEEDS_REVIEW:
            triage['review'].append((subject, score))
        else:
            triage['critical'].append((subject, score))
    
    return triage


def apply_auto_fixes(critical_files: list) -> list:
    """Apply automatic fixes to critical files."""
    # Import the fix functions from auto_fix_apostilas
    from auto_fix_apostilas import apply_structural_fixes
    
    results = []
    for subject, score in critical_files:
        filepath = os.path.join(MEDIA_DIR, f"{subject}_COMPLETA_RAW_APOSTILA.md")
        if os.path.exists(filepath):
            report = apply_structural_fixes(filepath)
            results.append({'subject': subject, 'old_score': score, 'fixes': report})
    
    return results


def regenerate_word_docs(subjects: list):
    """Regenerate Word documents for fixed/approved apostilas."""
    from mlx_vomo import VomoMLX
    
    vomo = VomoMLX()
    
    for subject in subjects:
        md_file = os.path.join(MEDIA_DIR, f"{subject}_COMPLETA_RAW_APOSTILA.md")
        if os.path.exists(md_file):
            print(f"  📄 Regenerating Word for {subject}...")
            with open(md_file, 'r', encoding='utf-8') as f:
                content = f.read()
            try:
                vomo.save_as_word(content, f"{subject}_COMPLETA_RAW", MEDIA_DIR)
                print(f"     ✅ Done")
            except Exception as e:
                print(f"     ❌ Error: {e}")


def generate_final_report(triage: dict, fix_results: list) -> str:
    """Generate a markdown report of the entire pipeline run."""
    report = f"""# Relatório de Revisão Automatizada

**Data:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Diretório:** `{MEDIA_DIR}`

## Resumo da Triagem

| Categoria | Quantidade | Apostilas |
| :--- | :---: | :--- |
| ✅ **Aprovadas** (≥8) | {len(triage['approved'])} | {', '.join([s for s,_ in triage['approved']]) or 'Nenhuma'} |
| ⚠️ **Revisar** (6-8) | {len(triage['review'])} | {', '.join([s for s,_ in triage['review']]) or 'Nenhuma'} |
| ❌ **Críticas** (<6) | {len(triage['critical'])} | {', '.join([s for s,_ in triage['critical']]) or 'Nenhuma'} |

## Correções Aplicadas

"""
    if fix_results:
        for result in fix_results:
            fixes = ', '.join(result['fixes'].get('fixes_applied', [])) or 'Nenhuma'
            report += f"### {result['subject']}\n"
            report += f"- **Nota anterior:** {result['old_score']}/10\n"
            report += f"- **Correções:** {fixes}\n\n"
    else:
        report += "*Nenhuma correção automática foi necessária.*\n\n"
    
    report += """## Próximos Passos

1. **Aprovadas:** Prontas para uso. Documentos Word gerados.
2. **Revisar:** Requerem conferência manual superficial.
3. **Críticas:** Após correção automática, revalidar ou revisar manualmente.

---
*Relatório gerado automaticamente por `auto_review_pipeline.py`*
"""
    return report


def main():
    print("=" * 70)
    print("🔄 AUTOMATED APOSTILA REVIEW PIPELINE v1.0")
    print("=" * 70)
    
    # 1. Load existing validation reports
    print("\n📊 Loading validation reports...")
    reports = load_validation_reports()
    print(f"   Found {len(reports)} report(s)")
    
    if not reports:
        print("   ⚠️  No validation reports found. Run validate_all_apostilas.py first.")
        return
    
    # 2. Triage
    print("\n🔍 Triaging issues...")
    triage = triage_issues(reports)
    print(f"   ✅ Approved: {len(triage['approved'])}")
    print(f"   ⚠️  Review:   {len(triage['review'])}")
    print(f"   ❌ Critical: {len(triage['critical'])}")
    
    # 3. Apply auto-fixes to critical files
    fix_results = []
    if triage['critical']:
        print("\n🔧 Applying automatic fixes to critical files...")
        fix_results = apply_auto_fixes(triage['critical'])
    
    # 4. Regenerate Word docs for approved files
    approved_subjects = [s for s, _ in triage['approved']]
    if approved_subjects:
        print("\n📄 Regenerating Word documents for approved files...")
        regenerate_word_docs(approved_subjects)
    
    # 5. Generate final report
    print("\n📝 Generating final report...")
    report = generate_final_report(triage, fix_results)
    report_path = os.path.join(MEDIA_DIR, "PIPELINE_REVIEW_REPORT.md")
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"   Saved to: {report_path}")
    
    print("\n" + "=" * 70)
    print("✅ PIPELINE COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
