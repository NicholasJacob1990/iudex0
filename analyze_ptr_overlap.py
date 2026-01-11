#!/usr/bin/env python3
"""
analyze_ptr_overlap.py - PTR RAW Files Overlap Analyzer

Compares the 3 PTR lesson RAW files to determine:
1. Content overlap (redundancy)
2. Unique content per lesson (complementarity)
3. Fingerprint-based paragraph matching

Outputs a detailed report to help decide if consolidation is needed.
"""

import os
import sys
import hashlib
from pathlib import Path
from difflib import SequenceMatcher

sys.path.insert(0, '/Users/nicholasjacob/Documents/Aplicativos/Iudex')

MEDIA_DIR = "/Users/nicholasjacob/Downloads/MediaExtractor"
OUTPUT_REPORT = os.path.join(MEDIA_DIR, "PTR_OVERLAP_ANALYSIS.md")


def normalize_text(text: str) -> str:
    """Normalize text for comparison."""
    import re
    text = re.sub(r'\s+', ' ', text.lower().strip())
    return text


def compute_fingerprint(text: str) -> str:
    """Compute MD5 hash of normalized text."""
    return hashlib.md5(normalize_text(text).encode()).hexdigest()[:12]


def extract_paragraphs(content: str, min_length: int = 100) -> list:
    """Extract paragraphs of meaningful length."""
    paragraphs = content.split('\n\n')
    return [p.strip() for p in paragraphs if len(p.strip()) >= min_length]


def similarity(a: str, b: str) -> float:
    """Calculate text similarity."""
    return SequenceMatcher(None, normalize_text(a), normalize_text(b)).ratio()


def analyze_ptr_files():
    """Main analysis function."""
    # Find PTR RAW files
    ptr_files = []
    for f in os.listdir(MEDIA_DIR):
        if 'PTR' in f.upper() and '_RAW' in f.upper() and f.endswith('.txt'):
            ptr_files.append(os.path.join(MEDIA_DIR, f))
    
    if not ptr_files:
        print("❌ No PTR RAW files found.")
        return
    
    ptr_files.sort()
    print(f"Found {len(ptr_files)} PTR files:")
    for f in ptr_files:
        print(f"  - {os.path.basename(f)}")
    
    # Load content
    file_data = {}
    all_paragraphs = []
    
    for filepath in ptr_files:
        filename = os.path.basename(filepath)
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        paragraphs = extract_paragraphs(content)
        file_data[filename] = {
            'path': filepath,
            'content': content,
            'paragraphs': paragraphs,
            'fingerprints': set(compute_fingerprint(p) for p in paragraphs),
            'char_count': len(content),
            'para_count': len(paragraphs)
        }
        for p in paragraphs:
            all_paragraphs.append((filename, compute_fingerprint(p), p[:100]))
    
    # Build global fingerprint index
    fp_index = {}
    for filename, fp, preview in all_paragraphs:
        if fp not in fp_index:
            fp_index[fp] = []
        fp_index[fp].append((filename, preview))
    
    # Find overlaps (fingerprints in multiple files)
    overlaps = {fp: files for fp, files in fp_index.items() if len(set(f for f, _ in files)) > 1}
    
    # Calculate unique content per file
    file_unique = {}
    for filename, data in file_data.items():
        unique_fps = data['fingerprints'] - set(overlaps.keys())
        file_unique[filename] = len(unique_fps)
    
    # Generate report
    report = []
    report.append("# PTR RAW Files Overlap Analysis\n")
    report.append(f"**Generated:** {__import__('datetime').datetime.now().isoformat()}\n")
    report.append(f"**Files Analyzed:** {len(ptr_files)}\n\n")
    
    # File stats
    report.append("## File Statistics\n")
    report.append("| File | Characters | Paragraphs | Unique Paras |\n")
    report.append("| :--- | ---: | ---: | ---: |\n")
    for filename, data in file_data.items():
        unique = file_unique[filename]
        report.append(f"| {filename} | {data['char_count']:,} | {data['para_count']} | {unique} |\n")
    
    # Overlap summary
    total_shared = len(overlaps)
    report.append(f"\n## Overlap Summary\n")
    report.append(f"- **Shared paragraphs:** {total_shared}\n")
    report.append(f"- **Overlap percentage:** {100 * total_shared / len(fp_index):.1f}%\n\n")
    
    # Detailed overlaps
    if overlaps:
        report.append("## Detailed Overlaps\n")
        report.append("Paragraphs found in multiple files:\n\n")
        for i, (fp, files) in enumerate(list(overlaps.items())[:20]):  # Show first 20
            file_list = ", ".join(set(f for f, _ in files))
            preview = files[0][1]
            report.append(f"{i+1}. **{file_list}**\n")
            report.append(f"   > {preview}...\n\n")
    
    # Recommendation
    report.append("## Recommendation\n")
    overlap_ratio = len(overlaps) / len(fp_index) if fp_index else 0
    
    if overlap_ratio > 0.5:
        report.append("> ⚠️ **HIGH REDUNDANCY** - Consider consolidating files. Over 50% content overlap.\n")
    elif overlap_ratio > 0.2:
        report.append("> 🔶 **MODERATE REDUNDANCY** - Files have significant shared content but also unique material.\n")
    else:
        report.append("> ✅ **COMPLEMENTARY** - Files are mostly unique. Merging would be additive.\n")
    
    # Write report
    with open(OUTPUT_REPORT, 'w', encoding='utf-8') as f:
        f.write(''.join(report))
    
    print(f"\n✅ Analysis complete. Report saved to: {OUTPUT_REPORT}")
    print(f"   Shared paragraphs: {total_shared}")
    print(f"   Overlap ratio: {overlap_ratio:.1%}")


if __name__ == "__main__":
    analyze_ptr_files()
