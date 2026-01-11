#!/usr/bin/env python3
"""
auto_fix_apostilas.py - Apostila Correction Script (v3.0 HIL)

Implements Human-in-the-Loop (HIL) for ALL fixes:
1. Structural Fixes: Generates suggestions file, requires --apply to execute
2. Semantic Fixes: Generates suggestions for manual review (unchanged)

New Features:
- --dry-run: Default mode, only generates suggestions
- --apply-structural: Apply all pending structural fixes
- --fingerprint: Enable global fingerprint-based deduplication
"""

import os
import re
import sys
import json
import argparse
import hashlib
from pathlib import Path
from difflib import SequenceMatcher
from datetime import datetime

sys.path.insert(0, '/Users/nicholasjacob/Documents/Aplicativos/Iudex')

MEDIA_DIR = "/Users/nicholasjacob/Downloads/MediaExtractor"
STRUCTURAL_SUGGESTIONS_FILE = os.path.join(MEDIA_DIR, "STRUCTURAL_SUGGESTIONS.json")
SEMANTIC_PATCHES_FILE = os.path.join(MEDIA_DIR, "SEMANTIC_PATCHES_REVIEW.md")

# ==============================================================================
# FINGERPRINTING
# ==============================================================================

def compute_paragraph_fingerprint(text: str) -> str:
    """Compute MD5 hash of normalized paragraph text."""
    normalized = re.sub(r'\s+', ' ', text.lower().strip())
    return hashlib.md5(normalized.encode('utf-8')).hexdigest()[:12]


def build_global_fingerprint_index(files: list[str]) -> dict:
    """Build index of all paragraph fingerprints across multiple files."""
    index = {}  # fingerprint -> [(file, para_index, text_preview)]
    
    for filepath in files:
        if not os.path.exists(filepath):
            continue
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        paragraphs = content.split('\n\n')
        for i, para in enumerate(paragraphs):
            if len(para.strip()) < 50:
                continue
            fp = compute_paragraph_fingerprint(para)
            if fp not in index:
                index[fp] = []
            index[fp].append({
                'file': os.path.basename(filepath),
                'index': i,
                'preview': para[:100].replace('\n', ' ')
            })
    return index


def find_cross_file_duplicates(index: dict) -> list:
    """Find paragraphs that appear in multiple files."""
    duplicates = []
    for fp, occurrences in index.items():
        files = set(o['file'] for o in occurrences)
        if len(files) > 1:
            duplicates.append({
                'fingerprint': fp,
                'occurrences': occurrences,
                'files': list(files)
            })
    return duplicates


# ==============================================================================
# CONTENT VALIDATION (v4.0 - Omissions & Compression)
# ==============================================================================

def normalize_law_number(raw_num: str) -> str:
    """Normalize law numbers to standard format (e.g., 866693 -> 8666/93, 14133 -> 14133)."""
    raw_num = raw_num.replace('.', '').replace('/', '').strip()
    
    if not raw_num.isdigit():
        return raw_num
    
    n = int(raw_num)
    
    # If already has year suffix (e.g., 1413321 = 14133/21 = Lei 14.133/2021)
    # Heuristic: Brazilian laws typically have 4-5 digit numbers + 2-4 digit year
    if len(raw_num) >= 6:
        # Try to split: last 2 digits as year if plausible
        potential_year = int(raw_num[-2:])
        potential_law = raw_num[:-2]
        
        # Years 90-99 (1990s) or 00-25 (2000s-2020s) are most common
        if (90 <= potential_year <= 99) or (0 <= potential_year <= 30):
            year_full = 1900 + potential_year if potential_year >= 90 else 2000 + potential_year
            return f"{potential_law}/{potential_year:02d}"
    
    # If the number is reasonable as-is (4-5 digits = law number without year)
    if 1000 <= n <= 99999:
        return raw_num
    
    return raw_num


def is_valid_law_ref(law_num: str) -> bool:
    """Validate if a law reference is plausible."""
    clean = law_num.replace('.', '').replace('/', '').strip()
    
    # Must have at least 3 digits
    if len(clean) < 3:
        return False
    
    # Filter out noise like "1", "2", "10", "100"
    try:
        n = int(clean.split('/')[0])
        if n < 100:
            return False
    except:
        return False
    
    return True


def extract_legal_references(text: str) -> dict:
    """Extract all legal references (laws, sumulas, articles) from text.
    
    v4.1: Improved normalization and validation to reduce false positives.
    """
    references = {
        'leis': set(),
        'sumulas': set(),
        'artigos': set(),
        'decretos': set(),
        'julgados': set()
    }
    
    # Laws: Lei 14.133, Lei nº 8.666, Lei 866693 (malformed), etc.
    # More permissive pattern to catch malformed transcriptions
    lei_pattern = r'[Ll]ei\s*(?:n[º°]?\s*)?(\d{3,8}(?:\.\d{3})?(?:/\d{2,4})?)'
    for match in re.finditer(lei_pattern, text):
        raw = match.group(1)
        normalized = normalize_law_number(raw)
        if is_valid_law_ref(normalized):
            references['leis'].add(normalized)
    
    # Sumulas: Súmula 473, Súmula Vinculante 13
    sumula_pattern = r'[Ss]úmula\s*(?:[Vv]inculante\s*)?(?:n[º°]?\s*)?(\d{1,4})'
    for match in re.finditer(sumula_pattern, text):
        num = match.group(1)
        if int(num) >= 1:  # Valid sumula numbers are positive
            references['sumulas'].add(f"Súmula {num}")
    
    # Articles: Art. 37, Artigo 5º (keep simple, less prone to false positives)
    artigo_pattern = r'[Aa]rt(?:igo)?\.?\s*(\d{1,4})'
    for match in re.finditer(artigo_pattern, text):
        references['artigos'].add(f"Art. {match.group(1)}")
    
    # Decrees: Decreto 51.078, Decreto Rio
    decreto_pattern = r'[Dd]ecreto\s*(?:Rio\s*)?(?:n[º°]?\s*)?(\d{3,6}(?:\.\d{3})?(?:/\d{2,4})?)'
    for match in re.finditer(decreto_pattern, text):
        raw = match.group(1)
        normalized = normalize_law_number(raw)
        if is_valid_law_ref(normalized):
            references['decretos'].add(normalized)
    
    # === EXPANDED LEGAL NER (v4.2) ===
    # Court decisions: STF, STJ, TST, TRF, TJ patterns
    julgado_patterns = [
        # Recursos: REsp, RE, RMS, AgRg, etc.
        r'(?:REsp|RE|RMS|Ag(?:Rg)?|RCL|EDcl|AI|AC)\s*(?:n[º°]?\s*)?[\d\./-]+',
        # Habeas Corpus e Mandados
        r'(?:HC|MS|MI|HD)\s*(?:n[º°]?\s*)?[\d\./-]+',
        # Ações de Controle Concentrado
        r'(?:ADI|ADPF|ADC|ADO)\s*(?:n[º°]?\s*)?\d+',
        # Acórdãos TCU/TCE
        r'Acórdão\s*(?:TCU|TCE[/-]?\w*)?\s*(?:n[º°]?\s*)?[\d\./-]+',
        # Pareceres AGU/PGE
        r'Parecer\s*(?:AGU|PGE|PGM|PGFN)?\s*(?:n[º°]?\s*)?[\d\./-]+',
        # Temas de Repercussão Geral
        r'(?:Tema|RG)\s*(?:n[º°]?\s*)?\d+\s*(?:STF|STJ)?',
        # Teses STF/STJ
        r'Tese\s*(?:STF|STJ)\s*(?:n[º°]?\s*)?\d+',
        # Informativos
        r'Informativo\s*(?:STF|STJ)?\s*(?:n[º°]?\s*)?\d+',
        # Súmulas de Tribunais Estaduais
        r'Súmula\s*(?:TJ[A-Z]{2}|TRF\d?)\s*(?:n[º°]?\s*)?\d+',
    ]
    
    for pattern in julgado_patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            julgado = match.group(0).strip()
            # Normalize spacing
            julgado = re.sub(r'\s+', ' ', julgado)
            if len(julgado) > 3:  # Avoid noise
                references['julgados'].add(julgado)
    
    return references


def analyze_content_issues(formatted_path: str, raw_path: str = None) -> dict:
    """Analyze content issues: omissions, compression, missing references."""
    
    with open(formatted_path, 'r', encoding='utf-8') as f:
        formatted_text = f.read()
    
    issues = {
        'file': os.path.basename(formatted_path),
        'compression_ratio': 0.0,
        'compression_warning': None,
        'missing_laws': [],
        'missing_sumulas': [],
        'missing_decretos': [],
        'missing_julgados': [],
        'total_content_issues': 0
    }
    
    # Try to find corresponding RAW file
    if not raw_path:
        # Auto-discover: look for _RAW.txt in same folder or filename patterns
        folder = os.path.dirname(formatted_path)
        basename = os.path.basename(formatted_path)
        
        possible_raws = [
            formatted_path.replace('_FIDELIDADE.md', '_RAW.txt'),
            formatted_path.replace('_APOSTILA.md', '_RAW.txt'),
            formatted_path.replace('.md', '_RAW.txt'),
            os.path.join(folder, basename.split('_')[0] + '_RAW.txt'),
            os.path.join(folder, basename.split('_')[0] + '.txt'),
        ]
        
        for candidate in possible_raws:
            if os.path.exists(candidate):
                raw_path = candidate
                break
    
    if not raw_path or not os.path.exists(raw_path):
        issues['compression_warning'] = 'RAW file not found - cannot check omissions'
        return issues
    
    with open(raw_path, 'r', encoding='utf-8') as f:
        raw_text = f.read()
    
    # 1. Compression Ratio Analysis
    raw_len = len(raw_text)
    fmt_len = len(formatted_text)
    
    if raw_len > 0:
        issues['compression_ratio'] = round(fmt_len / raw_len, 2)
        
        if issues['compression_ratio'] < 0.7:
            issues['compression_warning'] = f"CRITICAL: Compression {issues['compression_ratio']:.0%} - possible content loss"
        elif issues['compression_ratio'] < 0.85:
            issues['compression_warning'] = f"WARNING: Compression {issues['compression_ratio']:.0%} - review for omissions"
    
    # 2. Legal Reference Comparison
    raw_refs = extract_legal_references(raw_text)
    fmt_refs = extract_legal_references(formatted_text)
    
    # Find missing references
    issues['missing_laws'] = list(raw_refs['leis'] - fmt_refs['leis'])
    issues['missing_sumulas'] = list(raw_refs['sumulas'] - fmt_refs['sumulas'])
    issues['missing_decretos'] = list(raw_refs['decretos'] - fmt_refs['decretos'])
    issues['missing_julgados'] = list(raw_refs['julgados'] - fmt_refs['julgados'])
    
    # Count total issues
    issues['total_content_issues'] = (
        len(issues['missing_laws']) + 
        len(issues['missing_sumulas']) + 
        len(issues['missing_decretos']) +
        len(issues['missing_julgados']) +
        (1 if issues['compression_warning'] else 0)
    )
    
    return issues


# ==============================================================================
# STRUCTURAL ANALYSIS (Suggestion Mode)
# ==============================================================================

def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def analyze_structural_issues(filepath: str, raw_path: str = None) -> dict:
    """Analyze file for structural and content issues WITHOUT modifying it.
    
    Args:
        filepath: Path to the formatted markdown file
        raw_path: Optional path to the original RAW transcription for content validation
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    issues = {
        'file': os.path.basename(filepath),
        'filepath': filepath,
        'duplicate_sections': [],
        'duplicate_paragraphs': [],
        'heading_numbering_issues': [],
        # Content validation fields (v4.0)
        'compression_ratio': None,
        'compression_warning': None,
        'missing_laws': [],
        'missing_sumulas': [],
        'missing_decretos': [],
        'missing_julgados': [],
        'total_issues': 0,
        'total_content_issues': 0
    }
    
    # 1. Find duplicate H2 sections (works with numbered and unnumbered headings)
    # Matches any line starting with ## followed by text
    section_pattern = r'^(## .+?)(?=^## |\Z)'
    sections = re.findall(section_pattern, content, re.MULTILINE | re.DOTALL)
    
    seen_titles = {}
    for section in sections:
        lines = section.strip().split('\n')
        title = lines[0] if lines else ""
        # Normalize: remove ##, optional numbering (1., 2., etc.), and extra whitespace
        normalized = re.sub(r'^##\s*(\d+\.\s*)?', '', title).strip().lower()
        
        if normalized in seen_titles:
            issues['duplicate_sections'].append({
                'title': title,
                'similar_to': seen_titles[normalized],
                'action': 'MERGE_RECOMMENDED'
            })
        else:
            seen_titles[normalized] = title

    # 1b. Detect numbering/order issues for H2 headings
    heading_entries = []
    for section in sections:
        lines = section.strip().split('\n')
        title = lines[0].strip() if lines else ""
        match = re.match(r'^##\s+(\d+)\.?\s+(.*)$', title)
        if match:
            number = int(match.group(1))
            heading_text = match.group(2).strip()
        else:
            number = None
            heading_text = re.sub(r'^##\s*', '', title).strip()
        heading_entries.append({"number": number, "title": heading_text})

    if heading_entries and any(entry["number"] is not None for entry in heading_entries):
        expected = list(range(1, len(heading_entries) + 1))
        mismatch_indices = [
            idx for idx, entry in enumerate(heading_entries)
            if entry["number"] != expected[idx]
        ]
        if mismatch_indices:
            issues['heading_numbering_issues'].append({
                'action': 'RENUMBER',
                'description': (
                    "Numeração de títulos H2 fora de sequência ou ausente "
                    f"em {len(mismatch_indices)} de {len(heading_entries)} títulos."
                )
            })
    
    # 2. Find duplicate paragraphs
    paragraphs = content.split('\n\n')
    seen_paras = {}
    
    for i, para in enumerate(paragraphs):
        if len(para.strip()) < 50:
            continue
        fp = compute_paragraph_fingerprint(para)
        if fp in seen_paras:
            issues['duplicate_paragraphs'].append({
                'fingerprint': fp,
                'line_index': i,
                'preview': para[:80].replace('\n', ' '),
                'duplicate_of_index': seen_paras[fp],
                'action': 'REMOVE_RECOMMENDED'
            })
        else:
            seen_paras[fp] = i
    
    # 3. Content validation (v4.0) - only if raw_path is provided or discoverable
    content_issues = analyze_content_issues(filepath, raw_path)
    issues['compression_ratio'] = content_issues.get('compression_ratio')
    issues['compression_warning'] = content_issues.get('compression_warning')
    issues['missing_laws'] = content_issues.get('missing_laws', [])
    issues['missing_sumulas'] = content_issues.get('missing_sumulas', [])
    issues['missing_decretos'] = content_issues.get('missing_decretos', [])
    issues['missing_julgados'] = content_issues.get('missing_julgados', [])
    issues['total_content_issues'] = content_issues.get('total_content_issues', 0)
    
    issues['total_issues'] = (
        len(issues['duplicate_sections'])
        + len(issues['duplicate_paragraphs'])
        + len(issues['heading_numbering_issues'])
    )
    return issues


def generate_structural_suggestions(files: list[str], use_fingerprint: bool = False) -> dict:
    """Analyze all files and generate suggestions JSON."""
    report = {
        'generated_at': datetime.now().isoformat(),
        'mode': 'dry-run',
        'files_analyzed': len(files),
        'suggestions': [],
        'cross_file_duplicates': []
    }
    
    for filepath in files:
        if os.path.exists(filepath):
            issues = analyze_structural_issues(filepath)
            if issues['total_issues'] > 0:
                report['suggestions'].append(issues)
    
    # Global fingerprint analysis
    if use_fingerprint:
        index = build_global_fingerprint_index(files)
        cross_dupes = find_cross_file_duplicates(index)
        report['cross_file_duplicates'] = cross_dupes
    
    return report


# ==============================================================================
# APPLY FIXES (After Approval)
# ==============================================================================

def apply_structural_fixes_to_file(filepath: str, suggestions: dict) -> dict:
    """Apply approved structural fixes to a single file."""
    with open(filepath, 'r', encoding='utf-8') as f:
        original = f.read()
    
    content = original
    applied = []
    
    # Remove duplicate paragraphs by approved fingerprint
    approved_fps = {dup.get('fingerprint') for dup in suggestions.get('duplicate_paragraphs', []) if dup.get('fingerprint')}
    if approved_fps:
        paragraphs = content.split('\n\n')
        new_paragraphs = []
        seen_fps = set()

        for para in paragraphs:
            current_fp = compute_paragraph_fingerprint(para) if len(para.strip()) >= 50 else None
            if current_fp in approved_fps:
                if current_fp in seen_fps:
                    applied.append(f"Removed duplicate paragraph (fingerprint: {current_fp})")
                    continue
                seen_fps.add(current_fp)
            new_paragraphs.append(para)

        content = '\n\n'.join(new_paragraphs)

    # Renumber H2 headings to restore order/consistency
    if suggestions.get('renumber_headings') or suggestions.get('heading_numbering_issues'):
        def _renumber_h2_headings(text: str) -> str:
            lines = text.splitlines()
            counter = 0
            for idx, line in enumerate(lines):
                match = re.match(r'^(##)\s+(?:(\d+)\.?\s+)?(.+)$', line.strip())
                if match:
                    counter += 1
                    title = match.group(3).strip()
                    lines[idx] = f"## {counter}. {title}"
            return "\n".join(lines)

        renumbered = _renumber_h2_headings(content)
        if renumbered != content:
            content = renumbered
            applied.append("Renumbered H2 headings")

    # Remove duplicate sections by normalized title (keep first occurrence)
    dup_section_titles = {
        re.sub(r'^##\s*(\d+\.\s*)?', '', s.get('title', '')).strip().lower()
        for s in suggestions.get('duplicate_sections', [])
        if s.get('title')
    }
    if dup_section_titles:
        section_pattern = r'^(## .+?)(?=^## |\Z)'
        sections = re.findall(section_pattern, content, re.MULTILINE | re.DOTALL)
        prefix_match = re.split(r'^## .+?$', content, maxsplit=1, flags=re.MULTILINE)
        prefix = prefix_match[0] if prefix_match else ""

        seen = set()
        kept_sections = []
        for section in sections:
            lines = section.strip().split('\n')
            title = lines[0] if lines else ""
            normalized = re.sub(r'^##\s*(\d+\.\s*)?', '', title).strip().lower()
            if normalized in dup_section_titles and normalized in seen:
                applied.append(f"Removed duplicate section: {title}")
                continue
            seen.add(normalized)
            kept_sections.append(section.strip())

        content = prefix.rstrip() + ("\n\n" if prefix.strip() else "") + "\n\n".join(kept_sections)
    
    # Backup and save
    if applied:
        backup_path = filepath.replace('.md', '_BACKUP.md')
        with open(backup_path, 'w', encoding='utf-8') as f:
            f.write(original)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
    
    return {
        'file': os.path.basename(filepath),
        'fixes_applied': applied,
        'original_size': len(original),
        'new_size': len(content)
    }


def apply_all_structural_fixes() -> list:
    """Load suggestions file and apply all fixes."""
    if not os.path.exists(STRUCTURAL_SUGGESTIONS_FILE):
        print("❌ No suggestions file found. Run with --dry-run first.")
        return []
    
    with open(STRUCTURAL_SUGGESTIONS_FILE, 'r', encoding='utf-8') as f:
        suggestions = json.load(f)
    
    results = []
    for file_suggestions in suggestions.get('suggestions', []):
        filepath = file_suggestions.get('filepath')
        if filepath and os.path.exists(filepath):
            result = apply_structural_fixes_to_file(filepath, file_suggestions)
            results.append(result)
            print(f"✅ Applied fixes to {result['file']}: {len(result['fixes_applied'])} changes")
    
    return results


# ==============================================================================
# SEMANTIC FIXES (Unchanged - Already HIL)
# ==============================================================================

def process_semantic_fixes() -> str:
    """Generate semantic suggestions (unchanged from v2)."""
    from mlx_vomo import VomoMLX
    import glob
    
    suggestions_report = f"# Semantic Patches Review\nGenerated: {datetime.now().isoformat()}\n\n"
    has_suggestions = False
    
    try:
        vomo = VomoMLX()
    except Exception as e:
        print(f"Failed to init VomoMLX: {e}")
        return ""

    raw_files = glob.glob(os.path.join(MEDIA_DIR, "*_COMPLETA_RAW.txt"))
    
    for raw_file in raw_files:
        stem = Path(raw_file).stem
        
        # Dynamic discovery logic
        md_file = None
        apostila_path = os.path.join(MEDIA_DIR, f"{stem}_APOSTILA.md")
        if os.path.exists(apostila_path):
             md_file = apostila_path
        else:
             candidates = glob.glob(os.path.join(MEDIA_DIR, f"{stem}_formatada*.md"))
             if candidates:
                 candidates.sort(key=os.path.getmtime, reverse=True)
                 md_file = candidates[0]
        
        if not md_file or not os.path.exists(md_file):
            continue
            
        print(f"\nValidating: {stem}...")
        try:
            with open(raw_file, 'r', encoding='utf-8') as f:
                raw_text = f.read()
            with open(md_file, 'r', encoding='utf-8') as f:
                formatted_text = f.read()
                
            result = vomo.validate_completeness_full(raw_text, formatted_text, stem)
            score = result.get('nota_fidelidade', result.get('nota', 10))
            omissions = result.get('omissoes_graves', result.get('omissoes', []))
            
            if score < 9.5 and omissions:
                suggestions_report += f"## {stem} (Score: {score}/10)\n"
                suggestions_report += f"**Omissões:** {', '.join(omissions[:5])}\n\n"
                has_suggestions = True
                
        except Exception as e:
            print(f"Error: {e}")
            
    if has_suggestions:
        with open(SEMANTIC_PATCHES_FILE, 'w', encoding='utf-8') as f:
            f.write(suggestions_report)
        return SEMANTIC_PATCHES_FILE
    return ""


# ==============================================================================
# MAIN
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(description="Apostila Auto-Fix Script v3.0 (HIL)")
    parser.add_argument('--dry-run', action='store_true', default=True,
                        help='Generate suggestions without applying (default)')
    parser.add_argument('--apply-structural', action='store_true',
                        help='Apply pending structural fixes from suggestions file')
    parser.add_argument('--fingerprint', action='store_true',
                        help='Enable cross-file fingerprint deduplication')
    parser.add_argument('--semantic', action='store_true',
                        help='Also generate semantic suggestions')
    args = parser.parse_args()
    
    print("=" * 60)
    print("APOSTILA AUTO-FIX SCRIPT v3.0 (Human-in-the-Loop)")
    print("=" * 60)
    
    # Dynamic discovery of target files (supports Fidelidade, Apostila, etc.)
    target_files = []
    # Find all COMPLETA_RAW txt files
    raw_candidates = glob.glob(os.path.join(MEDIA_DIR, "*_COMPLETA_RAW.txt"))
    
    for raw_path in raw_candidates:
        stem = Path(raw_path).stem
        # Look for corresponding markdown files
        # Priority: _APOSTILA.md -> _formatada_*.md -> any .md starting with stem
        
        apostila_path = os.path.join(MEDIA_DIR, f"{stem}_APOSTILA.md")
        if os.path.exists(apostila_path):
            target_files.append(apostila_path)
            continue
            
        # Try finding *formatada*.md
        formatted_candidates = glob.glob(os.path.join(MEDIA_DIR, f"{stem}_formatada*.md"))
        if formatted_candidates:
            # Sort by modification time (newest first)
            formatted_candidates.sort(key=os.path.getmtime, reverse=True)
            target_files.append(formatted_candidates[0])
            continue
            
        # Generic fallback: stem.md
        generic_path = os.path.join(MEDIA_DIR, f"{stem}.md")
        if os.path.exists(generic_path):
            target_files.append(generic_path)

    print(f"Found {len(target_files)} target markdown files.")
    
    if args.apply_structural:
        print("\n[MODE] APPLYING APPROVED STRUCTURAL FIXES...")
        results = apply_all_structural_fixes()
        print(f"\nApplied fixes to {len(results)} file(s).")
    else:
        print("\n[MODE] DRY-RUN - Generating Suggestions Only...")
        print(f"Fingerprint Mode: {'ENABLED' if args.fingerprint else 'DISABLED'}")
        
        report = generate_structural_suggestions(target_files, args.fingerprint)
        
        with open(STRUCTURAL_SUGGESTIONS_FILE, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        total_issues = sum(s['total_issues'] for s in report['suggestions'])
        print(f"\n📋 Structural Suggestions: {total_issues} issue(s) across {len(report['suggestions'])} file(s)")
        print(f"   Saved to: {STRUCTURAL_SUGGESTIONS_FILE}")
        
        if report['cross_file_duplicates']:
            print(f"   Cross-file duplicates: {len(report['cross_file_duplicates'])}")
        
        if args.semantic:
            print("\n[PHASE 2] Generating Semantic Suggestions...")
            semantic_file = process_semantic_fixes()
            if semantic_file:
                print(f"   Saved to: {semantic_file}")
        
        print("\n" + "=" * 60)
        print("NEXT STEPS:")
        print("1. Review the suggestions files")
        print("2. Run with --apply-structural to apply approved fixes")
        print("=" * 60)


if __name__ == "__main__":
    main()
