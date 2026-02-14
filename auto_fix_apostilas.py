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
import unicodedata
from pathlib import Path
from difflib import SequenceMatcher
from datetime import datetime
from typing import Optional, Tuple, List, Dict, Any

sys.path.insert(0, '/Users/nicholasjacob/Documents/Aplicativos/Iudex')

MEDIA_DIR = "/Users/nicholasjacob/Downloads/MediaExtractor"
STRUCTURAL_SUGGESTIONS_FILE = os.path.join(MEDIA_DIR, "STRUCTURAL_SUGGESTIONS.json")
SEMANTIC_PATCHES_FILE = os.path.join(MEDIA_DIR, "SEMANTIC_PATCHES_REVIEW.md")

STRUCTURAL_MODE_CONFIG = {
    # APOSTILA/FIDELIDADE: mais tolerante a repetição didática (limiares mais altos).
    "APOSTILA": {
        "near_similarity_threshold": 0.93,
        "near_jaccard_threshold": 0.72,
        "gray_zone_low": 0.80,
        "gray_zone_high": 0.88,
        "min_paragraph_chars": 70,
        "max_scan_candidates": 240,
    },
    "FIDELIDADE": {
        "near_similarity_threshold": 0.95,
        "near_jaccard_threshold": 0.76,
        "gray_zone_low": 0.84,
        "gray_zone_high": 0.92,
        "min_paragraph_chars": 90,
        "max_scan_candidates": 240,
    },
    # AUDIENCIA/REUNIAO/DEPOIMENTO: mais rigoroso com repetições.
    "AUDIENCIA": {
        "near_similarity_threshold": 0.88,
        "near_jaccard_threshold": 0.64,
        "gray_zone_low": 0.80,
        "gray_zone_high": 0.88,
        "min_paragraph_chars": 60,
        "max_scan_candidates": 280,
    },
    "REUNIAO": {
        "near_similarity_threshold": 0.88,
        "near_jaccard_threshold": 0.64,
        "gray_zone_low": 0.80,
        "gray_zone_high": 0.88,
        "min_paragraph_chars": 60,
        "max_scan_candidates": 280,
    },
    "DEPOIMENTO": {
        "near_similarity_threshold": 0.89,
        "near_jaccard_threshold": 0.65,
        "gray_zone_low": 0.80,
        "gray_zone_high": 0.88,
        "min_paragraph_chars": 60,
        "max_scan_candidates": 280,
    },
}

_LEGITIMATE_DUPLICATE_PATTERNS = [
    # Títulos/quadros/tabelas
    re.compile(r"(?i)\b(quadro[-\s]?s[íi]ntese|tabela|como a banca cobra|pegadinha|quadro resumo)\b"),
    # Blocos de referência legal padronizados (muito comuns e legítimos)
    re.compile(r"(?i)^\s*(art\.?|artigo|lei|decreto|s[úu]mula|tema|resp|re|adi|adpf|ac[óo]rd[ãa]o)\b"),
    re.compile(r"(?i)\b(base legal|jurisprud[êe]ncia|refer[êe]ncia(?:s)?|fundamento legal)\b"),
    # Estruturas de checklist/sumário didático
    re.compile(r"(?i)^\s*(item|conceito|defini[çc][ãa]o|detalhes|dica de prova)\b"),
]

_HEADING_SKIP_KEYWORDS_H2 = (
    "sumário",
    "sumario",
    "bibliografia",
    "referências",
    "referencias",
)

_HEADING_SKIP_KEYWORDS_H3_H4 = (
    "quadro",
    "tabela",
    "síntese",
    "sintese",
    "esquema",
    "pegadinha",
    "banca",
)

_HEADING_RE = re.compile(r'^(#{2,4})\s+(.+)$')
_TABLE_HEADING_RE = re.compile(r'^(#{2,5})\s*(?:[📋🎯]\s*)?(.*)$', re.IGNORECASE)

_TABLE_HEADING_KEYWORDS = (
    "tabela",
    "quadro",
    "síntese",
    "sintese",
    "pegadinha",
    "banca",
)

_STOPWORDS_PT = {
    "para", "pela", "pelo", "como", "mais", "menos", "sobre", "entre", "depois", "antes", "quando",
    "onde", "outra", "outro", "outros", "outras", "seu", "sua", "seus", "suas", "que", "porque",
    "pois", "isso", "essa", "esse", "esta", "este", "estas", "estes", "nao", "não", "sim", "com",
    "sem", "dos", "das", "nos", "nas", "por", "pro", "pra", "uma", "uns", "umas", "na", "no", "em",
    "ao", "aos", "as", "os", "de", "da", "do", "e", "a", "o", "um", "ser", "sao", "são",
}


def _strip_accents(text: str) -> str:
    return "".join(
        ch for ch in unicodedata.normalize("NFKD", text or "")
        if not unicodedata.combining(ch)
    )


def _sanitize_heading_title_text(value: str) -> str:
    text = re.sub(r"\s+", " ", (value or "").strip())
    if not text:
        return ""

    previous = None
    while previous != text:
        previous = text
        # Remove markdown markers indevidos no início do título (ex.: "## Responsabilidade ...")
        text = re.sub(r"^(?:#+\s*)+", "", text).strip()
        # Remove numeração duplicada acidental (ex.: "41. 41. Título")
        text = re.sub(r"^(\d+(?:\.\d+)*)\.?\s+\1\.?\s+", r"\1. ", text)

    text = re.sub(r"^[\-\–\—:;|]+\s*", "", text).strip()
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _normalize_heading_for_match(value: str) -> str:
    text = _sanitize_heading_title_text(value)
    text = re.sub(r'^(\d+(?:\.\d+)*)\.?\s+', '', text).strip()
    text = _strip_accents(text).lower()
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _keyword_set(texto: str) -> set[str]:
    tokens = re.findall(r"[A-Za-zÀ-ÿ0-9]+", (texto or "").lower())
    return {
        t for t in tokens
        if len(t) >= 4 and t not in _STOPWORDS_PT and not t.isdigit()
    }


def _keyword_similarity(a: str, b: str) -> float:
    sa = _keyword_set(a)
    sb = _keyword_set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / max(1, len(sa | sb))


def _extract_headings_for_tables(lines: List[str]) -> List[Dict[str, Any]]:
    headings: List[Dict[str, Any]] = []
    in_fence = False
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith(("```", "~~~")):
            in_fence = not in_fence
            continue
        if in_fence:
            continue

        m = _HEADING_RE.match(stripped)
        if not m:
            continue

        level = len(m.group(1))
        raw_title = m.group(2).strip()
        number, title = _parse_heading_number(raw_title)
        headings.append(
            {
                "line": idx,
                "level": level,
                "raw": raw_title,
                "title": title,
                "number": number,
            }
        )
    return headings


def _looks_like_table_separator(line: str) -> bool:
    s = (line or "").strip()
    if not s:
        return False
    return bool(re.match(r'^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?\s*$', s))


def _looks_like_table_row(line: str) -> bool:
    s = (line or "").strip()
    if not s or "|" not in s:
        return False
    cells = [c.strip() for c in s.split("|")]
    return len([c for c in cells if c]) >= 2


def _extract_table_blocks(lines: List[str], start: int, end: int) -> List[Dict[str, Any]]:
    blocks: List[Dict[str, Any]] = []
    i = max(0, start)
    end = min(len(lines), max(start, end))
    while i < end:
        stripped = lines[i].strip()
        m = _TABLE_HEADING_RE.match(stripped)
        if not m:
            i += 1
            continue

        heading_text = m.group(2).strip()
        if not any(tok in heading_text.lower() for tok in _TABLE_HEADING_KEYWORDS):
            i += 1
            continue

        j = i + 1
        while j < end and not lines[j].strip():
            j += 1

        if j + 1 >= end or not _looks_like_table_row(lines[j]) or not _looks_like_table_separator(lines[j + 1]):
            i += 1
            continue

        k = j + 2
        while k < end and _looks_like_table_row(lines[k]):
            k += 1
        while k < end and not lines[k].strip():
            k += 1

        blocks.append(
            {
                "start": i,
                "end": k,
                "heading_text": heading_text,
                "heading_line": i,
                "text": "\n".join(lines[i:k]).strip(),
            }
        )
        i = k

    return blocks


def _is_table_closure_heading(title_text: str) -> bool:
    normalized = _normalize_heading_for_match(title_text)
    if not normalized:
        return False
    return any(
        token in normalized
        for token in (
            "quadro-sintese",
            "quadro sintese",
            "quadro resumo",
            "como a banca cobra",
            "pegadinha",
            "tabela",
        )
    )


def _detect_heading_markdown_artifacts(content: str) -> List[Dict[str, Any]]:
    if not content:
        return []

    issues: List[Dict[str, Any]] = []
    for idx, line in enumerate(content.splitlines()):
        m = _HEADING_RE.match(line.strip())
        if not m:
            continue
        level = len(m.group(1))
        if level < 2 or level > 4:
            continue

        raw = (m.group(2) or "").strip()
        number, clean_title = _parse_heading_number(raw)
        rewritten_raw = _compose_heading_raw(number, clean_title)
        if not rewritten_raw:
            continue

        if raw != rewritten_raw:
            confidence = 0.99 if "#" in raw else 0.95
            issues.append(
                {
                    "id": f"heading_markdown_artifact_{idx}",
                    "type": "heading_markdown_artifact",
                    "heading_line": idx + 1,
                    "heading_level": level,
                    "old_raw": raw,
                    "new_raw": rewritten_raw,
                    "old_title": clean_title,
                    "new_title": clean_title,
                    "diff_preview": f"- {raw}\n+ {rewritten_raw}",
                    "confidence": confidence,
                    "reason": "Título contém marcadores Markdown/numeração residual dentro do texto do heading.",
                    "action": "CLEAN_RECOMMENDED",
                }
            )
    return issues


def _detect_table_heading_level_issues(content: str) -> List[Dict[str, Any]]:
    if not content:
        return []

    lines = content.splitlines()
    blocks = _extract_table_blocks(lines, 0, len(lines))
    if not blocks:
        return []

    issues: List[Dict[str, Any]] = []
    seen: set[int] = set()
    for block in blocks:
        line_idx = int(block.get("heading_line", -1))
        if line_idx < 0 or line_idx >= len(lines) or line_idx in seen:
            continue
        seen.add(line_idx)

        m = _HEADING_RE.match(lines[line_idx].strip())
        if not m:
            continue
        old_level = len(m.group(1))
        if old_level >= 4:
            continue

        old_raw = (m.group(2) or "").strip()
        if not _is_table_closure_heading(old_raw):
            continue

        _, clean_title = _parse_heading_number(old_raw)
        if not clean_title:
            continue

        issues.append(
            {
                "id": f"table_heading_level_{line_idx}",
                "type": "table_heading_level",
                "heading_line": line_idx + 1,
                "old_level": old_level,
                "new_level": 4,
                "old_raw": old_raw,
                "new_raw": clean_title,
                "table_heading": block.get("heading_text"),
                "diff_preview": f"- {'#' * old_level} {old_raw}\n+ #### {clean_title}",
                "confidence": 0.96,
                "reason": "Heading de tabela em nível alto (H2/H3) polui a hierarquia e o sumário.",
                "action": "DEMOTE_RECOMMENDED",
            }
        )
    return issues


def _detect_table_misplacements(content: str) -> List[Dict[str, Any]]:
    if not content:
        return []

    lines = content.splitlines()
    headings = _extract_headings_for_tables(lines)
    if not headings:
        return []

    issues: List[Dict[str, Any]] = []
    seen_keys: set[str] = set()

    h2_headings = [h for h in headings if h.get("level") == 2]
    for idx, h2 in enumerate(h2_headings):
        sec_start = int(h2["line"])
        sec_end = int(h2_headings[idx + 1]["line"]) if idx + 1 < len(h2_headings) else len(lines)
        h3_children = [h for h in headings if h.get("level") == 3 and sec_start < int(h["line"]) < sec_end]
        if not h3_children:
            continue
        first_h3_line = int(h3_children[0]["line"])
        intro_tables = _extract_table_blocks(lines, sec_start + 1, first_h3_line)
        for tb in intro_tables:
            key = f"intro:{h2.get('raw')}:{tb.get('heading_text')}"
            if key in seen_keys:
                continue
            seen_keys.add(key)
            issues.append(
                {
                    "strategy": "h2_intro_to_section_end",
                    "table_heading": tb.get("heading_text"),
                    "section_title": h2.get("raw"),
                    "current_section": f"{h2.get('raw')} (abertura)",
                    "target_section": f"{h2.get('raw')} (fechamento)",
                    "after_section": f"{h2.get('raw')} (fechamento)",
                    "confidence": 0.92,
                    "reason": "Tabela de síntese detectada na abertura de H2 com subtópicos H3; deve fechar a seção mãe.",
                }
            )

    section_entries: List[Dict[str, Any]] = []
    for idx, h in enumerate(headings):
        start = int(h["line"]) + 1
        end = int(headings[idx + 1]["line"]) if idx + 1 < len(headings) else len(lines)
        parent_idx = None
        for j in range(idx - 1, -1, -1):
            if int(headings[j]["level"]) < int(h["level"]):
                parent_idx = j
                break
        section_entries.append(
            {
                "heading": h,
                "start": start,
                "end": end,
                "parent_idx": parent_idx,
            }
        )

    def _context_slice(start_line: int, end_line: int, *, tail: bool = False, max_lines: int = 3) -> str:
        chunk = lines[max(0, start_line):max(0, end_line)]
        nonempty = [ln.strip() for ln in chunk if ln.strip()]
        if not nonempty:
            return ""
        if tail:
            return " ".join(nonempty[-max_lines:])
        return " ".join(nonempty[:max_lines])

    for sec in section_entries:
        h = sec["heading"]
        parent_idx = sec["parent_idx"]
        if parent_idx is None:
            continue
        if "." not in (".".join(str(x) for x in (h.get("number") or ())) if h.get("number") else "") and int(h.get("level", 2)) < 3:
            continue

        parent = headings[parent_idx]
        table_blocks = _extract_table_blocks(lines, int(sec["start"]), int(sec["end"]))
        if not table_blocks:
            continue

        for block in table_blocks:
            current_context = _context_slice(int(sec["start"]), int(block["start"]), tail=True)
            parent_context = _context_slice(int(section_entries[parent_idx]["start"]), int(h["line"]), tail=True)
            current_score = _keyword_similarity(f"{h.get('title', '')} {current_context}", block.get("text", ""))
            parent_score = _keyword_similarity(f"{parent.get('title', '')} {parent_context}", block.get("text", ""))
            diff = parent_score - current_score
            if parent_score >= 0.08 and diff >= 0.08:
                confidence = min(0.96, round(0.58 + min(0.25, diff) + (0.20 * parent_score), 4))
                key = f"parent:{h.get('raw')}:{parent.get('raw')}:{block.get('heading_text')}"
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                issues.append(
                    {
                        "strategy": "subtopic_to_parent_before_subtopic",
                        "table_heading": block.get("heading_text"),
                        "section_title": parent.get("raw"),
                        "subtopic_title": h.get("raw"),
                        "subtopic_level": int(h.get("level", 3)),
                        "current_section": h.get("raw"),
                        "target_section": parent.get("raw"),
                        "after_section": parent.get("raw"),
                        "confidence": confidence,
                        "reason": (
                            "Tabela parece vinculada ao tópico mãe por similaridade léxica "
                            f"(parent={parent_score:.3f}, current={current_score:.3f})."
                        ),
                    }
                )

    return issues


def _find_heading_line(lines: List[str], *, level: int, raw_title: str) -> Optional[int]:
    target = _normalize_heading_for_match(raw_title)
    for idx, line in enumerate(lines):
        m = _HEADING_RE.match(line.strip())
        if not m:
            continue
        if len(m.group(1)) != level:
            continue
        title = _normalize_heading_for_match(m.group(2))
        if title == target:
            return idx
    return None


def _apply_table_misplacement_fixes(content: str, moves: List[Dict[str, Any]]) -> Tuple[str, List[str]]:
    if not content or not moves:
        return content, []

    lines = content.splitlines()
    applied: List[str] = []

    for move in moves:
        strategy = str(move.get("strategy") or "").strip().lower()
        table_heading = str(move.get("table_heading") or "").strip()
        if not strategy or not table_heading:
            continue

        headings = _extract_headings_for_tables(lines)
        if not headings:
            break

        if strategy == "h2_intro_to_section_end":
            section_title = str(move.get("section_title") or "").strip()
            h2_line = _find_heading_line(lines, level=2, raw_title=section_title)
            if h2_line is None:
                continue

            next_h2_line = len(lines)
            for h in headings:
                if int(h.get("level", 0)) == 2 and int(h.get("line", -1)) > h2_line:
                    next_h2_line = int(h["line"])
                    break

            first_h3_line = None
            for h in headings:
                line_no = int(h.get("line", -1))
                if int(h.get("level", 0)) == 3 and h2_line < line_no < next_h2_line:
                    first_h3_line = line_no
                    break
            if first_h3_line is None:
                continue

            intro_blocks = _extract_table_blocks(lines, h2_line + 1, first_h3_line)
            block = next((tb for tb in intro_blocks if _normalize_heading_for_match(tb.get("heading_text", "")) == _normalize_heading_for_match(table_heading)), None)
            if not block:
                continue

            block_lines = lines[block["start"]:block["end"]]
            del lines[block["start"]:block["end"]]
            insert_at = next_h2_line
            if insert_at > block["start"]:
                insert_at = max(h2_line + 1, insert_at - (block["end"] - block["start"]))

            while insert_at > h2_line + 1 and insert_at <= len(lines) and not lines[insert_at - 1].strip():
                insert_at -= 1
            if insert_at < len(lines) and lines[insert_at - 1].strip():
                block_lines = [""] + block_lines
            block_lines.append("")
            for offset, bl in enumerate(block_lines):
                lines.insert(insert_at + offset, bl)

            applied.append(
                f"Moved misplaced table '{table_heading[:70]}' to end of section '{section_title[:70]}'"
            )

        elif strategy == "subtopic_to_parent_before_subtopic":
            subtopic_title = str(move.get("subtopic_title") or "").strip()
            subtopic_level = int(move.get("subtopic_level") or 3)
            subtopic_line = _find_heading_line(lines, level=subtopic_level, raw_title=subtopic_title)
            if subtopic_line is None:
                subtopic_line = _find_heading_line(lines, level=3, raw_title=subtopic_title)
            if subtopic_line is None:
                continue

            next_heading_line = len(lines)
            for h in headings:
                line_no = int(h.get("line", -1))
                if line_no > subtopic_line:
                    next_heading_line = line_no
                    break

            sub_blocks = _extract_table_blocks(lines, subtopic_line + 1, next_heading_line)
            block = next((tb for tb in sub_blocks if _normalize_heading_for_match(tb.get("heading_text", "")) == _normalize_heading_for_match(table_heading)), None)
            if not block:
                continue

            block_lines = lines[block["start"]:block["end"]]
            del lines[block["start"]:block["end"]]
            insert_at = subtopic_line
            if insert_at > len(lines):
                insert_at = len(lines)
            if insert_at > 0 and lines[insert_at - 1].strip():
                block_lines = [""] + block_lines
            block_lines.append("")
            for offset, bl in enumerate(block_lines):
                lines.insert(insert_at + offset, bl)

            current_section = str(move.get("current_section") or subtopic_title)
            target_section = str(move.get("target_section") or move.get("section_title") or "")
            applied.append(
                "Moved misplaced table "
                f"'{table_heading[:70]}' from '{current_section[:70]}' to '{target_section[:70]}'"
            )

    return "\n".join(lines), applied


def _table_row_count_from_block(lines: List[str], block: Dict[str, Any]) -> int:
    start = int(block.get("start", 0))
    end = int(block.get("end", 0))
    count = 0
    for line in lines[max(0, start):max(0, end)]:
        if _looks_like_table_row(line):
            count += 1
    return count


def _table_integrity_signature(content: str) -> Dict[str, Any]:
    lines = content.splitlines()
    blocks = _extract_table_blocks(lines, 0, len(lines))

    headings: List[str] = []
    heading_rows: List[str] = []
    for block in blocks:
        heading_norm = _normalize_heading_for_match(str(block.get("heading_text") or ""))
        row_count = _table_row_count_from_block(lines, block)
        headings.append(heading_norm)
        heading_rows.append(f"{heading_norm}:{row_count}")

    return {
        "table_count": len(blocks),
        "headings_sorted": sorted(headings),
        "heading_rows_sorted": sorted(heading_rows),
    }


def _validate_table_move_integrity(before_content: str, after_content: str) -> Tuple[bool, str]:
    before_sig = _table_integrity_signature(before_content)
    after_sig = _table_integrity_signature(after_content)

    if int(before_sig["table_count"]) != int(after_sig["table_count"]):
        return False, (
            f"table_count mudou {before_sig['table_count']} -> {after_sig['table_count']}"
        )

    if before_sig["headings_sorted"] != after_sig["headings_sorted"]:
        return False, "conjunto de headings de tabela mudou"

    if before_sig["heading_rows_sorted"] != after_sig["heading_rows_sorted"]:
        return False, "quantidade de linhas por tabela mudou"

    return True, ""


def _normalize_structural_mode(mode: Optional[str], filepath: Optional[str] = None) -> str:
    raw = str(mode or "").strip().upper()
    if raw in STRUCTURAL_MODE_CONFIG:
        return raw
    name = str(filepath or "").upper()
    for candidate in ("AUDIENCIA", "REUNIAO", "DEPOIMENTO", "FIDELIDADE", "APOSTILA"):
        if candidate in name:
            return candidate
    return "APOSTILA"


def _normalize_paragraph_for_similarity(text: str) -> str:
    value = (text or "").strip().lower()
    value = "".join(
        ch for ch in unicodedata.normalize("NFKD", value)
        if not unicodedata.combining(ch)
    )
    # Remove markdown decorativo simples
    value = re.sub(r"[*_`>#~\-]{1,}", " ", value)
    value = re.sub(r"\|", " ", value)
    # Mantém letras/números para similaridade lexical
    value = re.sub(r"[^\w\s]", " ", value, flags=re.UNICODE)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _paragraph_token_set(normalized: str) -> set[str]:
    return {
        token for token in re.findall(r"[a-zà-ÿ0-9]{3,}", normalized, flags=re.IGNORECASE)
        if not token.isdigit()
    }


def _jaccard_similarity(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / max(1, len(a | b))


def _is_legitimate_repetition(paragraph: str) -> Tuple[bool, str]:
    text = (paragraph or "").strip()
    if not text:
        return True, "empty"

    if text.startswith(("#", "|", "```", "> [!")):
        return True, "structural_block"

    # Linhas quase só de referência legal, listas/headers de tabela, etc.
    lowered = text.lower()
    for pattern in _LEGITIMATE_DUPLICATE_PATTERNS:
        if pattern.search(lowered):
            return True, "whitelist_pattern"

    # Citações legais muito curtas e padronizadas tendem a repetir legitimamente.
    if len(text) <= 160 and re.search(r"(?i)\b(art\.?|lei|s[úu]mula|tema)\b", text):
        return True, "short_legal_reference"

    return False, ""


def _duplicate_confidence(kind: str, seq_score: float, jac_score: float, threshold: float) -> float:
    if kind == "exact":
        return 0.99
    # Near duplicate confidence: proximity to threshold + lexical overlap.
    proximity = 0.0 if threshold <= 0 else max(0.0, min(1.0, seq_score / threshold))
    return max(0.0, min(0.98, round((0.62 * proximity) + (0.38 * jac_score), 4)))


def _parse_heading_number(title_text: str) -> Tuple[Optional[Tuple[int, ...]], str]:
    normalized = _sanitize_heading_title_text(title_text)
    match = re.match(r'^(\d+(?:\.\d+)*)\.?\s+(.+)$', normalized)
    if not match:
        return None, normalized
    number_tuple = tuple(int(part) for part in match.group(1).split("."))
    return number_tuple, _sanitize_heading_title_text(match.group(2))


def _should_skip_heading_numbering(title_text: str, *, level: Optional[int] = None) -> bool:
    title = (title_text or "").strip()
    if not title:
        return True
    if re.match(r'^[\U0001F300-\U0001F9FF]', title):
        return True
    lowered = title.lower()
    if level == 2:
        return any(keyword in lowered for keyword in _HEADING_SKIP_KEYWORDS_H2)
    return any(keyword in lowered for keyword in _HEADING_SKIP_KEYWORDS_H3_H4)


def _renumber_h2_h3_h4_headings(text: str) -> Tuple[str, bool]:
    lines = text.splitlines()
    counters = {2: 0, 3: 0, 4: 0}
    changed = False

    for idx, line in enumerate(lines):
        match = re.match(r'^(#{2,4})\s+(.+)$', line.strip())
        if not match:
            continue

        level = len(match.group(1))
        raw_title = match.group(2).strip()

        if _should_skip_heading_numbering(raw_title, level=level):
            continue

        number_tuple, clean_title = _parse_heading_number(raw_title)

        counters[level] += 1
        for deeper in range(level + 1, 5):
            counters[deeper] = 0

        expected_number = tuple(counters[lvl] for lvl in range(2, level + 1))
        expected_prefix = ".".join(str(x) for x in expected_number)
        rewritten = f"{'#' * level} {expected_prefix}. {clean_title}"

        if number_tuple != expected_number or rewritten != line.strip():
            lines[idx] = rewritten
            changed = True

    return "\n".join(lines), changed


def _heading_number_to_prefix(number: Optional[Tuple[int, ...]]) -> str:
    if not number:
        return ""
    return ".".join(str(part) for part in number)


def _compose_heading_raw(number: Optional[Tuple[int, ...]], title: str) -> str:
    clean_title = re.sub(r"\s+", " ", (title or "").strip())
    if not clean_title:
        return ""
    prefix = _heading_number_to_prefix(number)
    if prefix:
        return f"{prefix}. {clean_title}"
    return clean_title


def _extract_heading_sections(content: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    lines = content.splitlines()
    headings = _extract_headings_for_tables(lines)
    sections: List[Dict[str, Any]] = []
    if not headings:
        return sections, lines

    for idx, heading in enumerate(headings):
        start = int(heading["line"])
        end = int(headings[idx + 1]["line"]) if idx + 1 < len(headings) else len(lines)
        parent_idx = None
        for prev_idx in range(idx - 1, -1, -1):
            if int(headings[prev_idx]["level"]) < int(heading["level"]):
                parent_idx = prev_idx
                break

        body_lines = lines[start + 1:end]
        body_text = "\n".join(body_lines).strip()
        sections.append(
            {
                "idx": idx,
                "line": start,
                "level": int(heading["level"]),
                "raw": heading["raw"],
                "title": heading["title"],
                "number": heading["number"],
                "start": start + 1,
                "end": end,
                "text": body_text,
                "parent_idx": parent_idx,
            }
        )

    return sections, lines


def _derive_heading_title_from_body(body_text: str, current_title: str) -> Optional[str]:
    if not body_text:
        return None

    cleaned_lines: List[str] = []
    in_fence = False
    for line in body_text.splitlines():
        stripped = line.strip()
        if stripped.startswith(("```", "~~~")):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if not stripped:
            continue
        if stripped.startswith("#") or stripped.startswith("|"):
            continue
        if _looks_like_table_separator(stripped):
            continue
        if re.match(r"^\s*[-*+]\s+", stripped):
            continue
        candidate = re.sub(r"^\s*\d+(?:\.\d+)*[\)\.]?\s+", "", stripped)
        candidate = re.sub(r"\s+", " ", candidate).strip()
        if len(candidate) < 28:
            continue
        cleaned_lines.append(candidate)

    if not cleaned_lines:
        return None

    merged = " ".join(cleaned_lines)
    chunks = re.split(r"(?<=[\.\?!:;])\s+|\n+", merged)
    for chunk in chunks:
        normalized = re.sub(r"\s+", " ", chunk).strip(" .;:-")
        if len(normalized) < 24:
            continue
        words = re.findall(r"[A-Za-zÀ-ÿ0-9%/()\-]+", normalized, flags=re.UNICODE)
        if len(words) < 4:
            continue
        preview = " ".join(words[:12]).strip()
        preview = re.sub(r"\s+", " ", preview).strip(" .;:-")
        if len(preview) < 12:
            continue
        if _normalize_heading_for_match(preview) == _normalize_heading_for_match(current_title):
            continue
        if preview.isupper():
            preview = preview.title()
        else:
            preview = preview[0].upper() + preview[1:]
        return preview

    return None


def _detect_heading_semantic_issues(content: str, mode_norm: str) -> List[Dict[str, Any]]:
    if not content:
        return []

    sections, _ = _extract_heading_sections(content)
    if not sections:
        return []

    issues: List[Dict[str, Any]] = []
    seen_lines: set[int] = set()
    mode_is_strict = mode_norm in {"AUDIENCIA", "REUNIAO", "DEPOIMENTO"}
    mismatch_overlap_threshold = 0.24 if mode_is_strict else 0.18
    min_body_chars = 150 if mode_is_strict else 190

    for sec in sections:
        level = int(sec["level"])
        line = int(sec["line"])
        raw = str(sec["raw"] or "")
        clean_title = str(sec["title"] or "")
        body = str(sec["text"] or "")

        if level < 2 or level > 4:
            continue
        if line in seen_lines:
            continue
        if _should_skip_heading_numbering(raw, level=level):
            continue
        if len(body) < min_body_chars:
            continue

        parent_idx = sec.get("parent_idx")
        if parent_idx is not None and 0 <= int(parent_idx) < len(sections):
            parent = sections[int(parent_idx)]
            parent_title = str(parent.get("title") or "")
            title_to_parent = similarity(
                _normalize_heading_for_match(clean_title),
                _normalize_heading_for_match(parent_title),
            )
            parent_body_similarity = _keyword_similarity(body, str(parent.get("text") or ""))

            if title_to_parent >= 0.90 and parent_body_similarity <= 0.30:
                new_title = _derive_heading_title_from_body(body, clean_title)
                if new_title and similarity(
                    _normalize_heading_for_match(new_title),
                    _normalize_heading_for_match(clean_title),
                ) < 0.84:
                    confidence = min(
                        0.95,
                        round(0.66 + min(0.20, (title_to_parent - 0.90) * 1.8) + min(0.12, (0.30 - parent_body_similarity) * 0.5), 4),
                    )
                    issues.append(
                        {
                            "id": f"heading_parent_drift_{line}",
                            "type": "parent_child_topic_drift",
                            "heading_line": line + 1,
                            "heading_level": level,
                            "old_title": clean_title,
                            "new_title": new_title,
                            "old_raw": raw,
                            "new_raw": _compose_heading_raw(sec.get("number"), new_title),
                            "diff_preview": f"- {clean_title}\n+ {new_title}",
                            "confidence": confidence,
                            "reason": (
                                "Subtópico com título semanticamente muito próximo do tópico mãe, "
                                "mas com conteúdo divergente."
                            ),
                            "action": "RENAME_RECOMMENDED",
                        }
                    )
                    seen_lines.add(line)
                    continue

    for sec in sections:
        level = int(sec["level"])
        line = int(sec["line"])
        raw = str(sec["raw"] or "")
        clean_title = str(sec["title"] or "")
        body = str(sec["text"] or "")

        if level < 2 or level > 4:
            continue
        if line in seen_lines:
            continue
        if _should_skip_heading_numbering(raw, level=level):
            continue
        if len(body) < min_body_chars:
            continue

        title_keywords = _keyword_set(clean_title)
        body_keywords = _keyword_set(body)
        if len(body_keywords) < 5 or not title_keywords:
            continue

        overlap = len(title_keywords & body_keywords) / max(1, len(title_keywords))
        if overlap >= mismatch_overlap_threshold:
            continue

        new_title = _derive_heading_title_from_body(body, clean_title)
        if not new_title:
            continue
        if similarity(
            _normalize_heading_for_match(new_title),
            _normalize_heading_for_match(clean_title),
        ) >= 0.84:
            continue

        confidence = min(0.93, round(0.58 + min(0.28, (mismatch_overlap_threshold - overlap) * 1.8), 4))
        issues.append(
            {
                "id": f"heading_semantic_{line}",
                "type": "heading_semantic_mismatch",
                "heading_line": line + 1,
                "heading_level": level,
                "old_title": clean_title,
                "new_title": new_title,
                "old_raw": raw,
                "new_raw": _compose_heading_raw(sec.get("number"), new_title),
                "diff_preview": f"- {clean_title}\n+ {new_title}",
                "confidence": confidence,
                "reason": (
                    f"Baixa aderência entre título e conteúdo do bloco "
                    f"(overlap={overlap:.2f}, limiar={mismatch_overlap_threshold:.2f})."
                ),
                "action": "RENAME_RECOMMENDED",
            }
        )
        seen_lines.add(line)

    for idx, sec in enumerate(sections):
        level = int(sec["level"])
        line = int(sec["line"])
        raw = str(sec["raw"] or "")
        clean_title = str(sec["title"] or "")
        body = str(sec["text"] or "")
        parent_idx = sec.get("parent_idx")

        if level < 2 or level > 4:
            continue
        if line in seen_lines:
            continue
        if _should_skip_heading_numbering(raw, level=level):
            continue
        if len(body) < min_body_chars:
            continue

        sec_norm = _normalize_heading_for_match(clean_title)
        if not sec_norm:
            continue

        for other in sections[:idx]:
            other_level = int(other["level"])
            other_line = int(other["line"])
            if other_level != level:
                continue
            if other.get("parent_idx") != parent_idx:
                continue
            other_norm = _normalize_heading_for_match(str(other.get("title") or ""))
            if not other_norm or sec_norm == other_norm:
                continue

            title_similarity = similarity(sec_norm, other_norm)
            if title_similarity < 0.90:
                continue

            body_similarity = _keyword_similarity(body, str(other.get("text") or ""))
            if body_similarity >= 0.50:
                continue

            new_title = _derive_heading_title_from_body(body, clean_title)
            if not new_title:
                continue
            if similarity(_normalize_heading_for_match(new_title), sec_norm) >= 0.84:
                continue

            confidence = min(
                0.90,
                round(0.57 + min(0.18, (title_similarity - 0.90) * 1.5) + min(0.12, (0.50 - body_similarity) * 0.5), 4),
            )
            issues.append(
                {
                    "id": f"heading_near_duplicate_{line}",
                    "type": "near_duplicate_heading",
                    "heading_line": line + 1,
                    "heading_level": level,
                    "old_title": clean_title,
                    "new_title": new_title,
                    "old_raw": raw,
                    "new_raw": _compose_heading_raw(sec.get("number"), new_title),
                    "diff_preview": f"- {clean_title}\n+ {new_title}",
                    "confidence": confidence,
                    "reason": (
                        "Tópico muito parecido com outro no mesmo nível, mas com conteúdo diferente."
                    ),
                    "action": "RENAME_RECOMMENDED",
                }
            )
            seen_lines.add(line)
            break

    return issues

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
    """Normalize law numbers to a stable comparison key.

    We intentionally normalize to the *base law number* (no year), because the
    goal of the content-audit is to detect omissions between RAW and formatted
    outputs (not year-format differences).

    Examples:
    - 866693 -> 8666
    - 14.133/2021 -> 14133
    - 8.666/93 -> 8666
    - 14133 -> 14133
    """
    raw_num = (raw_num or "").strip()

    # If an explicit year suffix exists (e.g., 14.133/2021, 8.666/93), keep only the base number.
    if "/" in raw_num:
        base = raw_num.split("/", 1)[0]
        base_digits = re.sub(r"\D", "", base)
        return base_digits or raw_num

    raw_digits = re.sub(r"\D", "", raw_num)
    
    if not raw_digits.isdigit():
        return raw_num
    
    n = int(raw_digits)
    
    # Heuristic: sometimes transcriptions omit the slash: 866693 (8.666/93), 141332021 (14.133/2021)
    if len(raw_digits) >= 8:
        # Try last 4 digits as full year.
        potential_year4 = int(raw_digits[-4:])
        if 1900 <= potential_year4 <= 2035:
            return raw_digits[:-4]

    if len(raw_digits) >= 6:
        # Try last 2 digits as year (common in transcriptions).
        potential_year2 = int(raw_digits[-2:])
        if (90 <= potential_year2 <= 99) or (0 <= potential_year2 <= 30):
            return raw_digits[:-2]
    
    # If the number is reasonable as-is (4-5 digits = law number without year)
    if 1000 <= n <= 99999:
        return raw_digits
    
    return raw_digits


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


# Known common transcription errors and their correct versions (Brazilian law numbers)
KNOWN_LAW_CORRECTIONS = {
    "11455": "11445",   # Lei de Saneamento Básico (spoken typo)
    "13467": "13465",   # Lei da REURB (confusion with Reforma Trabalhista)
    "3874": "13874",    # Lei de Liberdade Econômica (missing prefix)
    "9637": "9637",     # Lei das OS (sometimes misheard)
    "8112": "8112",     # Estatuto dos Servidores
}


def _edit_distance(s1: str, s2: str) -> int:
    """Compute Levenshtein edit distance between two strings."""
    if len(s1) < len(s2):
        return _edit_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    
    return previous_row[-1]


def find_similar_law_in_set(raw_num: str, fmt_refs: set, max_edit_distance: int = 1) -> str | None:
    """Check if a similar law number exists in formatted refs (typo correction detection).
    
    Handles common transcription errors:
    - Single digit typos: 11455 vs 11445 (edit distance 1)
    - Missing prefix: 3874 vs 13874 (prefix check)
    - Transposed digits: 13467 vs 13465 (edit distance 1)
    
    Args:
        raw_num: The normalized law number from RAW transcription
        fmt_refs: Set of normalized law numbers from formatted output
        max_edit_distance: Maximum allowed edit distance for fuzzy match (default 1)
    
    Returns:
        The matching law number from fmt_refs if found, otherwise None
    """
    if not raw_num or not fmt_refs:
        return None
    
    raw_digits = re.sub(r'\D', '', raw_num)
    if not raw_digits:
        return None
    
    # 1. Check known corrections first (fastest path)
    if raw_digits in KNOWN_LAW_CORRECTIONS:
        corrected = KNOWN_LAW_CORRECTIONS[raw_digits]
        for fmt_ref in fmt_refs:
            fmt_digits = re.sub(r'\D', '', fmt_ref)
            if fmt_digits == corrected:
                return fmt_ref
    
    # 2. Check for prefix variations (e.g., 3874 -> 13874)
    # Only match if raw is exactly a suffix (prevents 12345 matching 13465)
    for fmt_ref in fmt_refs:
        fmt_digits = re.sub(r'\D', '', fmt_ref)
        # Check if raw is a suffix of formatted (missing prefix)
        if len(fmt_digits) > len(raw_digits) >= 4:  # Require at least 4 digits to avoid spurious matches
            if fmt_digits.endswith(raw_digits):
                return fmt_ref
    
    # 3. Fuzzy match using edit distance (handles typos)
    # STRICTER: Only for similar-length numbers (within 1 character) and edit distance = 1
    best_match = None
    best_distance = max_edit_distance + 1
    
    for fmt_ref in fmt_refs:
        fmt_digits = re.sub(r'\D', '', fmt_ref)
        
        # Only compare if lengths are very similar (within 1 character)
        # This prevents matching completely different numbers like 12345 vs 13465
        if abs(len(raw_digits) - len(fmt_digits)) > 1:
            continue
        
        distance = _edit_distance(raw_digits, fmt_digits)
        if distance <= max_edit_distance and distance < best_distance:
            best_distance = distance
            best_match = fmt_ref
    
    return best_match


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
    
    # Laws: Lei 14.133/2021, Lei nº 8.666/93, Lei 9637, Lei Municipal nº 5.026/2009, etc.
    # Accept common qualifiers between "Lei" and the number (Municipal/Federal/Complementar/etc.).
    # Accept 1-6 digits before separators to support "8.666" and "14.133".
    lei_pattern = (
        r"[Ll]ei"
        r"(?:\s+(?:Complementar|Municipal|Federal|Estadual|Org[âa]nica|Delegada|Nacional))?"
        r"\s*(?:n[º°]?\s*)?"
        r"(\d{1,6}(?:\.\d{3})*(?:/\d{2,4})?)"
    )
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
    
    # Decrees: Decreto 30.780/2009, Decreto 51.078, etc.
    decreto_pattern = r'[Dd]ecreto\s*(?:Rio\s*)?(?:n[º°]?\s*)?(\d{1,6}(?:\.\d{3})*(?:/\d{2,4})?)'
    for match in re.finditer(decreto_pattern, text):
        raw = match.group(1)
        normalized = normalize_law_number(raw)
        if is_valid_law_ref(normalized):
            references['decretos'].add(normalized)
    
    # === EXPANDED LEGAL NER (v4.2) ===
    # Court decisions: STF, STJ, TST, TRF, TJ patterns
    julgado_patterns = [
        # Recursos: REsp, RE, RMS, AgRg, etc. (word boundary prevents matching inside "relicitação", etc.)
        r'\b(?:REsp|RE|RMS|Ag(?:Rg)?|RCL|EDcl|AI|AC)\b\s*(?:n[º°]?\s*)?[\d\./-]+',
        # Habeas Corpus e Mandados (avoid false positives like "SMS 02/2025" -> "MS 02")
        r'\b(?:HC|MS|MI|HD)\b\s*(?:n[º°]?\s*)?[\d\./-]+',
        # Ações de Controle Concentrado (avoid matching substrings like "enunciado" -> "ado")
        r'\b(?:ADI|ADPF|ADC|ADO)\b\s*(?:n[º°]?\s*)?\d+',
        # Acórdãos TCU/TCE
        r'\bAcórdão\b\s*(?:TCU|TCE[/-]?\w*)?\s*(?:n[º°]?\s*)?[\d\./-]+',
        # Pareceres (require at least one digit to avoid matching "parecer.")
        r'\bParecer\b(?:\s+[A-Z]{2,15})*\s*(?:n[º°]?\s*)?\d[\d\./-]*',
        # Temas de Repercussão Geral (aceita separador de milhar: 1.234)
        r'\b(?:Tema|RG)\b\s*(?:n[º°]?\s*)?\d{1,4}(?:\.\d{3})*\s*(?:STF|STJ)?',
        # Teses STF/STJ
        r'\bTese\b\s*(?:STF|STJ)\s*(?:n[º°]?\s*)?\d+',
        # Informativos
        r'\bInformativo\b\s*(?:STF|STJ)?\s*(?:n[º°]?\s*)?\d+',
        # Súmulas de Tribunais Estaduais
        r'\bSúmula\b\s*(?:TJ[A-Z]{2}|TRF\d?)\s*(?:n[º°]?\s*)?\d+',
    ]
    
    for pattern in julgado_patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            julgado = match.group(0).strip()
            # Normalize spacing
            julgado = re.sub(r'\s+', ' ', julgado)
            # Normalize for case-insensitive comparison (reduces false positives like "Tema 32" vs "tema 32")
            julgado = julgado.lower()
            # Normalize Tema numbers: "tema 1.234" -> "tema 1234" (avoids false misses from punctuation)
            if julgado.startswith("tema") or julgado.startswith("rg"):
                digits = re.sub(r"\D+", "", julgado)
                if digits:
                    julgado = f"tema {digits}"
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
    
    # 2. Legal Reference Comparison with Fuzzy Matching (v4.3)
    raw_refs = extract_legal_references(raw_text)
    fmt_refs = extract_legal_references(formatted_text)
    
    # Find missing references using fuzzy matching to avoid false positives
    # from proactive corrections (e.g., 11.455 -> 11.445, 3874 -> 13.874)
    missing_laws = []
    for raw_law in raw_refs['leis']:
        if raw_law in fmt_refs['leis']:
            continue  # Exact match found
        
        # Check if a similar law number exists (likely a correction)
        similar = find_similar_law_in_set(raw_law, fmt_refs['leis'])
        if similar:
            # Law was likely corrected, not omitted - don't flag as missing
            print(f"  ℹ️  Law {raw_law} appears corrected to {similar} (not flagged as missing)")
            continue
        
        # No exact or fuzzy match - truly missing
        missing_laws.append(raw_law)
    
    issues['missing_laws'] = missing_laws
    issues['missing_sumulas'] = list(raw_refs['sumulas'] - fmt_refs['sumulas'])
    issues['missing_decretos'] = list(raw_refs['decretos'] - fmt_refs['decretos'])
    missing_julgados = list(raw_refs['julgados'] - fmt_refs['julgados'])

    def _tema_digits(value: str) -> str:
        m = re.search(r"\btema\s+(\d{1,6})\b", value or "", flags=re.IGNORECASE)
        return m.group(1) if m else ""

    def _is_close_digits(a: str, b: str) -> bool:
        if not a or not b or len(a) != len(b):
            return False
        # Hamming distance <= 1
        diff = sum(1 for x, y in zip(a, b) if x != y)
        return diff <= 1

    fmt_temas = { _tema_digits(j) for j in fmt_refs.get("julgados", set()) if isinstance(j, str) and j.startswith("tema") }
    fmt_temas = { t for t in fmt_temas if t }

    filtered_missing: list[str] = []
    for ref in missing_julgados:
        if not isinstance(ref, str):
            continue
        if ref.startswith("tema"):
            digits = _tema_digits(ref)
            if digits:
                # Common ASR variant: missing leading '1' for four-digit themes (234 -> 1234)
                if len(digits) == 3 and (f"1{digits}" in fmt_temas):
                    continue
                # Common ASR typo: one digit off (1933 -> 1033, etc.)
                if len(digits) == 4 and any(_is_close_digits(digits, fmt) for fmt in fmt_temas if len(fmt) == 4):
                    continue
        filtered_missing.append(ref)

    issues['missing_julgados'] = filtered_missing
    
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


def analyze_structural_issues(filepath: str, raw_path: str = None, mode: str = "APOSTILA") -> dict:
    """Analyze file for structural and content issues WITHOUT modifying it.
    
    Args:
        filepath: Path to the formatted markdown file
        raw_path: Optional path to the original RAW transcription for content validation
        mode: APOSTILA, FIDELIDADE, AUDIENCIA, REUNIAO, or DEPOIMENTO
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    mode_norm = _normalize_structural_mode(mode, filepath)
    mode_cfg = STRUCTURAL_MODE_CONFIG.get(mode_norm, STRUCTURAL_MODE_CONFIG["APOSTILA"])
    
    issues = {
        'file': os.path.basename(filepath),
        'filepath': filepath,
        'mode': mode_norm,
        'duplicate_sections': [],
        'duplicate_paragraphs': [],
        'heading_numbering_issues': [],
        'heading_semantic_issues': [],
        'heading_markdown_issues': [],
        'table_heading_level_issues': [],
        'table_misplacements': [],
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
        normalized = _normalize_heading_for_match(title)
        
        if normalized in seen_titles:
            issues['duplicate_sections'].append({
                'title': title,
                'similar_to': seen_titles[normalized],
                'action': 'MERGE_RECOMMENDED'
            })
        else:
            seen_titles[normalized] = title

    # 1b. Detect numbering/order issues for hierarchical headings (H2/H3/H4)
    heading_entries = []
    has_numbered_heading = False
    counters = {2: 0, 3: 0, 4: 0}
    for line in content.splitlines():
        heading_match = re.match(r'^(#{2,4})\s+(.+)$', line.strip())
        if not heading_match:
            continue

        level = len(heading_match.group(1))
        raw_title = heading_match.group(2).strip()
        if _should_skip_heading_numbering(raw_title, level=level):
            continue

        current_number, heading_text = _parse_heading_number(raw_title)
        if current_number is not None:
            has_numbered_heading = True

        counters[level] += 1
        for deeper in range(level + 1, 5):
            counters[deeper] = 0
        expected_number = tuple(counters[lvl] for lvl in range(2, level + 1))
        mismatch = current_number != expected_number

        heading_entries.append({
            "level": level,
            "number": current_number,
            "expected": expected_number,
            "title": heading_text,
            "mismatch": mismatch,
        })

    if heading_entries and has_numbered_heading:
        mismatch_count = sum(1 for entry in heading_entries if entry["mismatch"])
        if mismatch_count:
            issues['heading_numbering_issues'].append({
                'action': 'RENUMBER',
                'description': (
                    "Numeração hierárquica de títulos (H2/H3/H4) fora de sequência ou ausente "
                    f"em {mismatch_count} de {len(heading_entries)} títulos."
                )
            })

    # 1c. Detect headings with markdown artifacts inside title text (ex.: "41. ## ...")
    heading_markdown_issues = _detect_heading_markdown_artifacts(content)
    if heading_markdown_issues:
        for item in heading_markdown_issues:
            issues['heading_markdown_issues'].append(item)

    # 1d. Detect table headings that should be subordinate (H4) to avoid polluting ToC
    table_heading_level_issues = _detect_table_heading_level_issues(content)
    if table_heading_level_issues:
        for item in table_heading_level_issues:
            issues['table_heading_level_issues'].append(item)

    # 1e. Detect table misplacements relative to mother topic / section closing
    table_misplacements = _detect_table_misplacements(content)
    if table_misplacements:
        for item in table_misplacements:
            issues['table_misplacements'].append({
                **item,
                'action': 'MOVE_RECOMMENDED',
            })

    # 1f. Detect semantic drifts on heading titles/subtitles and propose deterministic rename
    heading_semantic_issues = _detect_heading_semantic_issues(content, mode_norm)
    if heading_semantic_issues:
        for item in heading_semantic_issues:
            issues['heading_semantic_issues'].append(item)
    
    # 2. Find duplicate paragraphs (exact + near) with mode-specific thresholds
    paragraphs = content.split('\n\n')
    seen_paras = {}  # fingerprint -> first paragraph index
    paragraph_records = []  # candidates for near-duplicate comparison
    exact_duplicates = 0
    near_duplicates = 0
    ignored_candidates = 0
    gray_zone_candidates = 0
    
    for i, para in enumerate(paragraphs):
        para_text = para.strip()
        if len(para_text) < int(mode_cfg["min_paragraph_chars"]):
            continue

        ignore_candidate, ignore_reason = _is_legitimate_repetition(para_text)
        if ignore_candidate:
            ignored_candidates += 1

        fp = compute_paragraph_fingerprint(para_text)
        normalized_para = _normalize_paragraph_for_similarity(para_text)
        token_set = _paragraph_token_set(normalized_para)

        # 2a) Exact duplicate by fingerprint (same normalized paragraph)
        if fp in seen_paras:
            if not ignore_candidate:
                issues['duplicate_paragraphs'].append({
                    'fingerprint': fp,
                    'line_index': i,
                    'preview': para_text[:80].replace('\n', ' '),
                    'duplicate_of_index': seen_paras[fp],
                    'duplicate_kind': 'exact',
                    'similarity_score': 1.0,
                    'jaccard_score': 1.0,
                    'confidence': _duplicate_confidence("exact", 1.0, 1.0, 1.0),
                    'reason': 'Fingerprint idêntico após normalização de parágrafo.',
                    'action': 'REMOVE_RECOMMENDED'
                })
                exact_duplicates += 1
            continue

        # Registrar primeira ocorrência para deduplicação exata futura.
        seen_paras[fp] = i

        # 2b) Near duplicate by lexical similarity (sem IA)
        if ignore_candidate:
            continue

        best_match = None
        scan_window = paragraph_records[-int(mode_cfg["max_scan_candidates"]):]
        for prev in scan_window:
            prev_norm = prev['normalized']
            # Guarda de tamanho para evitar comparações ruins.
            size_gap = abs(len(normalized_para) - len(prev_norm)) / max(1, max(len(normalized_para), len(prev_norm)))
            if size_gap > 0.35:
                continue

            jac = _jaccard_similarity(token_set, prev['token_set'])
            if jac < (float(mode_cfg['near_jaccard_threshold']) * 0.55):
                continue

            seq = similarity(normalized_para, prev_norm)
            composite = (0.72 * seq) + (0.28 * jac)

            if (
                float(mode_cfg['gray_zone_low']) <= seq < float(mode_cfg['gray_zone_high'])
                and jac >= (float(mode_cfg['near_jaccard_threshold']) * 0.90)
            ):
                gray_zone_candidates += 1

            if seq >= float(mode_cfg['near_similarity_threshold']) and jac >= float(mode_cfg['near_jaccard_threshold']):
                if best_match is None or composite > best_match['composite']:
                    best_match = {
                        'prev': prev,
                        'seq': seq,
                        'jac': jac,
                        'composite': composite,
                    }

        if best_match:
            seq = best_match['seq']
            jac = best_match['jac']
            prev = best_match['prev']
            issues['duplicate_paragraphs'].append({
                'fingerprint': fp,
                'line_index': i,
                'preview': para_text[:80].replace('\n', ' '),
                'duplicate_of_index': prev['line_index'],
                'duplicate_of_fingerprint': prev['fingerprint'],
                'duplicate_kind': 'near',
                'similarity_score': round(seq, 4),
                'jaccard_score': round(jac, 4),
                'confidence': _duplicate_confidence("near", seq, jac, float(mode_cfg['near_similarity_threshold'])),
                'reason': (
                    f"Quase duplicado detectado por similaridade lexical "
                    f"(seq={seq:.3f}, jaccard={jac:.3f}, modo={mode_norm})"
                ),
                'action': 'REMOVE_RECOMMENDED'
            })
            near_duplicates += 1

        paragraph_records.append({
            'line_index': i,
            'fingerprint': fp,
            'normalized': normalized_para,
            'token_set': token_set,
        })
    
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
        + len(issues['heading_semantic_issues'])
        + len(issues['heading_markdown_issues'])
        + len(issues['table_heading_level_issues'])
        + len(issues['table_misplacements'])
    )
    issues['dedup_metrics'] = {
        'mode': mode_norm,
        'exact_duplicates': exact_duplicates,
        'near_duplicates': near_duplicates,
        'ignored_candidates': ignored_candidates,
        'gray_zone_candidates': gray_zone_candidates,
        'near_similarity_threshold': float(mode_cfg['near_similarity_threshold']),
        'near_jaccard_threshold': float(mode_cfg['near_jaccard_threshold']),
        'gray_zone_low': float(mode_cfg['gray_zone_low']),
        'gray_zone_high': float(mode_cfg['gray_zone_high']),
    }
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


def _apply_heading_title_updates(content: str, updates: List[Dict[str, Any]]) -> Tuple[str, List[str]]:
    if not updates:
        return content, []

    lines = content.splitlines()
    applied: List[str] = []
    used_lines: set[int] = set()

    for item in updates:
        new_title = str(item.get("new_title") or "").strip()
        old_title = str(item.get("old_title") or "").strip()
        level = item.get("heading_level")
        line_hint = item.get("heading_line")
        if not new_title:
            continue

        candidate_idx: Optional[int] = None
        if isinstance(line_hint, int):
            idx = int(line_hint) - 1
            if 0 <= idx < len(lines):
                m = _HEADING_RE.match(lines[idx].strip())
                if m:
                    m_level = len(m.group(1))
                    _, clean_found = _parse_heading_number(m.group(2).strip())
                    if (level in (None, m_level)) and (
                        not old_title
                        or _normalize_heading_for_match(clean_found) == _normalize_heading_for_match(old_title)
                    ):
                        candidate_idx = idx

        if candidate_idx is None:
            for idx, line in enumerate(lines):
                if idx in used_lines:
                    continue
                m = _HEADING_RE.match(line.strip())
                if not m:
                    continue
                m_level = len(m.group(1))
                raw_found = m.group(2).strip()
                _, clean_found = _parse_heading_number(raw_found)
                if level not in (None, m_level):
                    continue
                if old_title and _normalize_heading_for_match(clean_found) != _normalize_heading_for_match(old_title):
                    continue
                candidate_idx = idx
                break

        if candidate_idx is None:
            continue

        m = _HEADING_RE.match(lines[candidate_idx].strip())
        if not m:
            continue

        level_prefix = m.group(1)
        current_raw = m.group(2).strip()
        number_tuple, current_clean = _parse_heading_number(current_raw)
        rewritten_raw = _compose_heading_raw(number_tuple, new_title)
        if not rewritten_raw:
            continue

        new_line = f"{level_prefix} {rewritten_raw}"
        if lines[candidate_idx].strip() == new_line.strip():
            continue

        lines[candidate_idx] = new_line
        used_lines.add(candidate_idx)
        applied.append(
            f"Renamed heading (line {candidate_idx + 1}): '{current_clean[:80]}' -> '{new_title[:80]}'"
        )

    return "\n".join(lines), applied


def _apply_heading_markdown_cleanup(content: str, issues: List[Dict[str, Any]]) -> Tuple[str, List[str]]:
    if not content or not issues:
        return content, []

    lines = content.splitlines()
    applied: List[str] = []

    for issue in issues:
        line_hint = issue.get("heading_line")
        if not isinstance(line_hint, int):
            continue
        idx = int(line_hint) - 1
        if idx < 0 or idx >= len(lines):
            continue

        m = _HEADING_RE.match(lines[idx].strip())
        if not m:
            continue

        current_level = len(m.group(1))
        expected_level = issue.get("heading_level")
        if isinstance(expected_level, int) and expected_level != current_level:
            continue

        new_raw = _sanitize_heading_title_text(str(issue.get("new_raw") or ""))
        if not new_raw:
            continue

        new_line = f"{'#' * current_level} {new_raw}"
        if lines[idx].strip() == new_line.strip():
            continue

        old_raw = m.group(2).strip()
        lines[idx] = new_line
        applied.append(
            f"Cleaned heading markdown artifact (line {idx + 1}): '{old_raw[:80]}' -> '{new_raw[:80]}'"
        )

    return "\n".join(lines), applied


def _apply_table_heading_level_fixes(content: str, issues: List[Dict[str, Any]]) -> Tuple[str, List[str]]:
    if not content or not issues:
        return content, []

    lines = content.splitlines()
    applied: List[str] = []

    for issue in issues:
        line_hint = issue.get("heading_line")
        if not isinstance(line_hint, int):
            continue
        idx = int(line_hint) - 1
        if idx < 0 or idx >= len(lines):
            continue

        m = _HEADING_RE.match(lines[idx].strip())
        if not m:
            continue

        old_level = len(m.group(1))
        old_raw = m.group(2).strip()
        new_level = int(issue.get("new_level") or 4)
        if new_level < 2:
            new_level = 2
        if new_level > 4:
            new_level = 4

        new_raw = _sanitize_heading_title_text(str(issue.get("new_raw") or ""))
        if not new_raw:
            _, title_only = _parse_heading_number(old_raw)
            new_raw = _sanitize_heading_title_text(title_only or old_raw)
        if not new_raw:
            continue

        new_line = f"{'#' * new_level} {new_raw}"
        if lines[idx].strip() == new_line.strip():
            continue

        lines[idx] = new_line
        applied.append(
            f"Demoted table heading to H{new_level} (line {idx + 1}): '{old_raw[:80]}'"
        )

    return "\n".join(lines), applied


# ==============================================================================
# APPLY FIXES (After Approval)
# ==============================================================================

def apply_structural_fixes_to_file(filepath: str, suggestions: dict) -> dict:
    """Apply approved structural fixes to a single file."""
    with open(filepath, 'r', encoding='utf-8') as f:
        original = f.read()
    
    content = original
    applied = []
    mode_norm = _normalize_structural_mode((suggestions or {}).get("mode"), filepath)
    
    # Remove duplicate paragraphs (exact + near):
    # - exact duplicates can be removed by repeated fingerprint
    # - near duplicates are removed by the explicit paragraph line_index from analysis
    duplicate_suggestions = suggestions.get('duplicate_paragraphs', []) or []
    allow_near_duplicate_auto_remove = True
    if mode_norm == "FIDELIDADE":
        force_value = os.getenv("IUDEX_FIDELIDADE_AUTO_REMOVE_NEAR_DUPLICATES", "0").strip().lower()
        allow_near_duplicate_auto_remove = force_value not in {"0", "false", "no", "off"}
        if not allow_near_duplicate_auto_remove:
            before_count = len(duplicate_suggestions)
            duplicate_suggestions = [
                dup for dup in duplicate_suggestions
                if str(dup.get("duplicate_kind") or "exact").strip().lower() != "near"
            ]
            skipped = before_count - len(duplicate_suggestions)
            if skipped > 0:
                applied.append(
                    f"Skipped {skipped} near-duplicate suggestion(s) in FIDELIDADE (HIL required)"
                )

    approved_fps = {
        dup.get('fingerprint')
        for dup in duplicate_suggestions
        if dup.get('fingerprint')
    }
    approved_line_indices: dict[int, dict] = {}
    for dup in duplicate_suggestions:
        line_index = dup.get("line_index")
        if line_index is None:
            continue
        try:
            approved_line_indices[int(line_index)] = dup
        except Exception:
            continue

    if approved_fps or approved_line_indices:
        paragraphs = content.split('\n\n')
        new_paragraphs = []
        seen_fps = set()

        for i, para in enumerate(paragraphs):
            if i in approved_line_indices:
                dup = approved_line_indices[i]
                dup_kind = str(dup.get("duplicate_kind") or "duplicate").lower()
                if dup_kind == "near":
                    score = dup.get("similarity_score")
                    if score is not None:
                        applied.append(
                            f"Removed near-duplicate paragraph at index {i} (sim={float(score):.3f})"
                        )
                    else:
                        applied.append(f"Removed near-duplicate paragraph at index {i}")
                else:
                    fp = dup.get("fingerprint") or ""
                    if fp:
                        applied.append(
                            f"Removed duplicate paragraph at index {i} (fingerprint: {fp})"
                        )
                    else:
                        applied.append(f"Removed duplicate paragraph at index {i}")
                continue

            current_fp = compute_paragraph_fingerprint(para) if len(para.strip()) >= 50 else None
            if current_fp in approved_fps:
                if current_fp in seen_fps:
                    applied.append(f"Removed duplicate paragraph (fingerprint: {current_fp})")
                    continue
                seen_fps.add(current_fp)
            new_paragraphs.append(para)
        
        content = '\n\n'.join(new_paragraphs)

    # Clean markdown artifacts embedded in heading titles
    heading_markdown_issues = suggestions.get('heading_markdown_issues', []) or []
    if heading_markdown_issues:
        updated_content, cleaned = _apply_heading_markdown_cleanup(content, heading_markdown_issues)
        if cleaned:
            content = updated_content
            applied.extend(cleaned)

    # Demote table closure headings from H2/H3 to H4 to preserve structural hierarchy
    table_heading_level_issues = suggestions.get('table_heading_level_issues', []) or []
    if table_heading_level_issues:
        updated_content, demoted = _apply_table_heading_level_fixes(content, table_heading_level_issues)
        if demoted:
            content = updated_content
            applied.extend(demoted)

    # Renumber H2/H3/H4 headings to restore hierarchical order/consistency
    if suggestions.get('renumber_headings') or suggestions.get('heading_numbering_issues'):
        renumbered, changed = _renumber_h2_h3_h4_headings(content)
        if changed:
            content = renumbered
            applied.append("Renumbered hierarchical headings (H2/H3/H4)")

    # Deterministic heading title rewrite (semantic drift / near-duplicate headings)
    heading_updates = suggestions.get('heading_title_updates', []) or suggestions.get('heading_semantic_issues', []) or []
    if heading_updates:
        updated_content, heading_updates_applied = _apply_heading_title_updates(content, heading_updates)
        if heading_updates_applied:
            content = updated_content
            applied.extend(heading_updates_applied)

    # Move misplaced tables (approved table_misplacements)
    table_misplacements = suggestions.get('table_misplacements', []) or []
    if table_misplacements:
        content_before_tables = content
        moved_content, table_moves_applied = _apply_table_misplacement_fixes(content, table_misplacements)
        if table_moves_applied:
            ok, reason = _validate_table_move_integrity(content_before_tables, moved_content)
            if ok:
                content = moved_content
                applied.extend(table_moves_applied)
            else:
                content = content_before_tables
                applied.append(
                    f"Rolled back table moves due integrity validation mismatch: {reason}"
                )

    # Remove duplicate sections by normalized title (keep first occurrence)
    dup_section_titles = {
        re.sub(r'^##\s*(\d+\.\s*)?', '', s.get('title', '')).strip().lower()
        for s in suggestions.get('duplicate_sections', [])
        if s.get('title')
    }
    if dup_section_titles:
        section_pattern = r'^(## .+?)(?=^## |\Z)'
        sections = re.findall(section_pattern, content, re.MULTILINE | re.DOTALL)
        
        # Only proceed if we found sections to process
        if sections:
            prefix_match = re.split(r'^## .+?$', content, maxsplit=1, flags=re.MULTILINE)
            prefix = prefix_match[0] if prefix_match else ""

            seen = set()
            kept_sections = []
            removed_count = 0
            for section in sections:
                lines = section.strip().split('\n')
                title = lines[0] if lines else ""
                normalized = re.sub(r'^##\s*(\d+\.\s*)?', '', title).strip().lower()
                if normalized in dup_section_titles and normalized in seen:
                    applied.append(f"Removed duplicate section: {title}")
                    removed_count += 1
                    continue
                seen.add(normalized)
                kept_sections.append(section.strip())

            # Only reconstruct content if we actually removed something
            if removed_count > 0 and kept_sections:
                content = prefix.rstrip() + ("\n\n" if prefix.strip() else "") + "\n\n".join(kept_sections)
            # If we removed everything (shouldn't happen), keep original
            elif removed_count > 0 and not kept_sections:
                # Revert - don't remove all content
                pass
    
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
