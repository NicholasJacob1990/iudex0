"""
Post-processing pipeline for transcription results.

Applies:
1. Legal dictionary rescoring (common Whisper misrecognitions of legal terms)
2. Punctuation restoration (rules-based for PT-BR legal context)
3. Text normalization (whitespace, casing for legal acronyms)

Usage:
    from app.services.transcription_postprocessing import postprocess_transcription
    result = postprocess_transcription(parsed_result)
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 1. Legal Dictionary — Common Whisper misrecognitions → correct forms
# ---------------------------------------------------------------------------
# Format: (regex pattern, replacement, description)
# Patterns are case-insensitive and match word boundaries
LEGAL_CORRECTIONS: List[Tuple[str, str, str]] = [
    # Split words (Whisper frequently splits compound legal terms)
    (r"\ba\s+gravo\b", "agravo", "agravo split"),
    (r"\bem\s+bargo\b", "embargo", "embargo split"),
    (r"\bem\s+bargos\b", "embargos", "embargos split"),
    (r"\bman\s+dado\b", "mandado", "mandado split"),
    (r"\bli\s+minar\b", "liminar", "liminar split"),
    (r"\bcom\s+petência\b", "competência", "competência split"),
    (r"\bjuris\s+dição\b", "jurisdição", "jurisdição split"),
    (r"\bju\s+risprudência\b", "jurisprudência", "jurisprudência split"),
    (r"\btu\s+tela\b", "tutela", "tutela split"),
    (r"\bexe\s+quente\b", "exequente", "exequente split"),
    (r"\blitis\s+consórcio\b", "litisconsórcio", "litisconsórcio split"),
    (r"\binter\s+locutória\b", "interlocutória", "interlocutória split"),
    (r"\bpreju\s+dicial\b", "prejudicial", "prejudicial split"),

    # Common phonetic confusions in PT-BR legal context
    (r"\bação pelo\b", "acórdão", "ação pelo → acórdão (context)"),
    (r"\bcesso\s+especial\b", "recurso especial", "cesso especial"),
    (r"\brecurço\b", "recurso", "recurço → recurso"),
    (r"\brecurços\b", "recursos", "recurços → recursos"),
    (r"\bhavias\s+corpus\b", "habeas corpus", "havias corpus"),
    (r"\bhábeas\s+corpus\b", "habeas corpus", "hábeas corpus"),
    (r"\babias\s+corpus\b", "habeas corpus", "abias corpus"),

    # Tribunal abbreviations (Whisper doesn't know legal acronyms)
    (r"\best\.?\s*[ée]\.?\s*efe\b", "STF", "es tê efe → STF"),
    (r"\best\.?\s*[ée]\.?\s*jota\b", "STJ", "es tê jota → STJ"),
    (r"\best\.?\s*[ée]\.?\s*t[eê]\b", "STF", "es tê tê → STF (context)"),
    (r"\bté erre éfe\b", "TRF", "té erre éfe → TRF"),
    (r"\bté erre tê\b", "TRT", "té erre tê → TRT"),
    (r"\btê esse tê\b", "TST", "tê esse tê → TST"),
    (r"\bcê pê cê\b", "CPC", "cê pê cê → CPC"),
    (r"\bcê dê cê\b", "CDC", "cê dê cê → CDC"),
    (r"\bcê éle tê\b", "CLT", "cê éle tê → CLT"),

    # Honorifics and legal titles
    (r"\bmeritíssima?\b", "meritíssimo", "meritíssima → meritíssimo (gendered)"),
    (r"\bexcelentíssima?\b", "excelentíssimo", "excelentíssima (normalize)"),

    # Legal process terms
    (r"\bdez embargo\b", "desembargo", "dez embargo"),
    (r"\bdez embargador\b", "desembargador", "dez embargador"),
    (r"\bdez embargadora\b", "desembargadora", "dez embargadora"),
    (r"\bpetição in icial\b", "petição inicial", "petição in icial"),
    (r"\bcontestaç ão\b", "contestação", "contestaç ão"),

    # Numbers in legal references (common Whisper errors)
    (r"\bartigo\s+(\d+)\s*,\s*(\d+)\b", r"artigo \1.\2", "artigo comma → dot"),
]

# Compiled patterns for performance
_COMPILED_CORRECTIONS: Optional[List[Tuple[re.Pattern, str]]] = None


def _get_compiled_corrections() -> List[Tuple[re.Pattern, str]]:
    global _COMPILED_CORRECTIONS
    if _COMPILED_CORRECTIONS is None:
        _COMPILED_CORRECTIONS = [
            (re.compile(pattern, re.IGNORECASE), replacement)
            for pattern, replacement, _ in LEGAL_CORRECTIONS
        ]
    return _COMPILED_CORRECTIONS


def apply_legal_dictionary(text: str) -> Tuple[str, int]:
    """Apply legal dictionary corrections to text.

    Returns (corrected_text, correction_count).
    """
    corrections = _get_compiled_corrections()
    count = 0

    for pattern, replacement in corrections:
        new_text, n = pattern.subn(replacement, text)
        if n > 0:
            count += n
            text = new_text

    return text, count


# ---------------------------------------------------------------------------
# 2. Punctuation Restoration — Rules-based for PT-BR legal text
# ---------------------------------------------------------------------------
# Legal text patterns that commonly need punctuation
PUNCTUATION_RULES: List[Tuple[str, str]] = [
    # Add period before common sentence starters (if missing)
    (r"([a-záéíóúâêôãõç])\s+(Artigo|Art\.|Parágrafo|Par\.|Inciso|Alínea|§)\s", r"\1. \2 "),

    # Add comma before conjunctions in legal text
    (r"(\w)\s+(porém|contudo|todavia|entretanto|não obstante)\s", r"\1, \2 "),

    # Add colon after "decide" / "determina" / "declara" patterns
    (r"((?:decide|determina|declara|resolve|defere|indefere))\s+([A-Z])", r"\1: \2"),

    # Normalize multiple spaces
    (r"\s{2,}", " "),

    # Ensure sentence-ending punctuation
    (r"([a-záéíóúâêôãõç])\s*$", r"\1."),
]

_COMPILED_PUNCTUATION: Optional[List[Tuple[re.Pattern, str]]] = None


def _get_compiled_punctuation() -> List[Tuple[re.Pattern, str]]:
    global _COMPILED_PUNCTUATION
    if _COMPILED_PUNCTUATION is None:
        _COMPILED_PUNCTUATION = [
            (re.compile(pattern), replacement)
            for pattern, replacement in PUNCTUATION_RULES
        ]
    return _COMPILED_PUNCTUATION


def restore_punctuation(text: str) -> str:
    """Apply rules-based punctuation restoration for PT-BR legal text."""
    rules = _get_compiled_punctuation()
    for pattern, replacement in rules:
        text = pattern.sub(replacement, text)
    return text


# ---------------------------------------------------------------------------
# 3. Legal Acronym Normalization
# ---------------------------------------------------------------------------
LEGAL_ACRONYMS = {
    "stf", "stj", "tst", "trf", "trt", "tjsp", "tjrj", "tjmg", "tjrs",
    "tjpr", "tjsc", "tjba", "tjpe", "tjce", "tjgo", "tjdf", "tjma",
    "cpc", "cpp", "clt", "cdc", "ctb", "eca", "ldb", "lgpd",
    "inss", "fgts", "irpf", "irpj", "csll",
    "oab", "cnj", "mp", "dpf", "pf",
}


def normalize_acronyms(text: str) -> str:
    """Uppercase known legal acronyms that Whisper may lowercase."""
    words = text.split()
    result = []
    for word in words:
        clean = word.strip(".,;:!?()[]\"'")
        if clean.lower() in LEGAL_ACRONYMS:
            # Preserve surrounding punctuation
            prefix = word[:len(word) - len(word.lstrip(".,;:!?()[]\"'"))]
            suffix = word[len(word.rstrip(".,;:!?()[]\"'")):]
            result.append(f"{prefix}{clean.upper()}{suffix}")
        else:
            result.append(word)
    return " ".join(result)


# ---------------------------------------------------------------------------
# 4. Segment-level post-processing
# ---------------------------------------------------------------------------
def postprocess_segment(segment: Dict[str, Any]) -> Dict[str, Any]:
    """Apply post-processing to a single segment."""
    text = segment.get("text", "")
    if not text:
        return segment

    # Apply legal dictionary
    text, _ = apply_legal_dictionary(text)

    # Normalize acronyms
    text = normalize_acronyms(text)

    segment = {**segment, "text": text}
    return segment


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------
def postprocess_transcription(result: Dict[str, Any]) -> Dict[str, Any]:
    """Apply full post-processing pipeline to a transcription result.

    Modifies:
    - result["text"]: Full text with corrections
    - result["segments"]: Each segment text corrected
    - Adds result["postprocessing"]: Stats about corrections applied
    """
    text = result.get("text", "")
    segments = result.get("segments", [])

    if not text:
        return result

    # 1. Legal dictionary on full text
    corrected_text, dict_corrections = apply_legal_dictionary(text)

    # 2. Punctuation restoration
    corrected_text = restore_punctuation(corrected_text)

    # 3. Acronym normalization
    corrected_text = normalize_acronyms(corrected_text)

    # 4. Apply to segments
    corrected_segments = [postprocess_segment(seg) for seg in segments]

    # Build result
    result = {**result}
    result["text"] = corrected_text
    result["segments"] = corrected_segments

    postprocessing_stats: Dict[str, Any] = {
        "legal_dictionary_corrections": dict_corrections,
        "punctuation_restored": True,
        "acronyms_normalized": True,
    }

    if dict_corrections > 0:
        logger.info(
            "Post-processing applied: %d legal dictionary corrections",
            dict_corrections,
        )

    result["postprocessing"] = postprocessing_stats
    return result


# ---------------------------------------------------------------------------
# 5. LLM-based hallucination detection (async, optional)
# ---------------------------------------------------------------------------
async def detect_hallucinations_llm(
    text: str,
    segments: List[Dict[str, Any]],
    duration: Optional[float] = None,
) -> Dict[str, Any]:
    """Score transcription segments for hallucination likelihood using Gemini Flash.

    Returns:
    {
        "overall_score": 0.15,  # 0=clean, 1=all hallucinated
        "flagged_segments": [
            {"index": 5, "text": "...", "score": 0.95, "reason": "..."}
        ],
        "model": "gemini-2.0-flash",
    }
    """
    import os

    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.debug("Gemini API key not configured — skipping hallucination detection")
        return {"overall_score": 0.0, "flagged_segments": [], "model": "none", "skipped": True}

    if not segments or len(segments) < 2:
        return {"overall_score": 0.0, "flagged_segments": [], "model": "none", "skipped": True}

    # Only check suspicious segments to minimize API calls
    # Heuristic: segments that are very short, repeat, or appear at silence boundaries
    suspicious_indices = _find_suspicious_segments(segments, duration)
    if not suspicious_indices:
        return {"overall_score": 0.0, "flagged_segments": [], "model": "gemini-2.0-flash"}

    # Build prompt with suspicious segments for LLM evaluation
    segments_text = "\n".join(
        f"[{i}] ({segments[i].get('start', 0):.1f}s-{segments[i].get('end', 0):.1f}s): \"{segments[i].get('text', '')}\""
        for i in suspicious_indices[:20]  # Limit to 20 segments
    )

    prompt = f"""Analyze these transcription segments from a Brazilian legal hearing/deposition for hallucination.

Whisper ASR commonly hallucinates these patterns:
- Repetitive phrases unrelated to context
- YouTube-style phrases ("obrigado por assistir", "inscreva-se")
- Music/sound descriptions when none exist
- Fragments that don't fit the surrounding context
- Repeated identical short phrases

Audio duration: {duration or 'unknown'}s
Total segments: {len(segments)}

Suspicious segments to evaluate:
{segments_text}

For each segment, respond with a JSON array of objects:
[{{"index": <int>, "score": <0.0-1.0>, "reason": "<brief reason if score > 0.5>"}}]

Score meaning: 0.0 = definitely real speech, 1.0 = definitely hallucinated.
Only include segments with score > 0.3. Return empty array [] if all look legitimate.
Respond ONLY with the JSON array, no other text."""

    try:
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.0-flash")

        response = await model.generate_content_async(
            prompt,
            generation_config=genai.GenerationConfig(
                temperature=0.1,
                max_output_tokens=1024,
            ),
        )

        response_text = response.text.strip()
        # Parse JSON response
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]

        import json
        flagged = json.loads(response_text)

        if not isinstance(flagged, list):
            flagged = []

        # Calculate overall score
        if flagged:
            avg_score = sum(f.get("score", 0) for f in flagged) / len(suspicious_indices)
        else:
            avg_score = 0.0

        # Enrich flagged segments with text
        for f in flagged:
            idx = f.get("index", 0)
            if 0 <= idx < len(segments):
                f["text"] = segments[idx].get("text", "")

        return {
            "overall_score": round(avg_score, 3),
            "flagged_segments": [f for f in flagged if f.get("score", 0) > 0.5],
            "model": "gemini-2.0-flash",
            "segments_checked": len(suspicious_indices),
        }

    except Exception as e:
        logger.warning("LLM hallucination detection failed: %s", e)
        return {"overall_score": 0.0, "flagged_segments": [], "model": "gemini-2.0-flash", "error": str(e)}


def _find_suspicious_segments(
    segments: List[Dict[str, Any]],
    duration: Optional[float] = None,
) -> List[int]:
    """Identify segment indices that look suspicious (potential hallucinations).

    Heuristics:
    - Very short segments (< 1s) with short text
    - Repeated identical text within nearby segments
    - Segments near the end of audio (common hallucination zone)
    - Segments with very low word probability (if available)
    """
    suspicious: List[int] = []
    seen_texts: Dict[str, int] = {}

    for i, seg in enumerate(segments):
        text = seg.get("text", "").strip()
        seg_duration = seg.get("end", 0) - seg.get("start", 0)

        # Very short segment with short text
        if seg_duration < 0.5 and len(text) < 10:
            suspicious.append(i)
            continue

        # Repeated text (exact match within last 10 segments)
        normalized = text.lower().strip(".")
        if normalized in seen_texts and (i - seen_texts[normalized]) < 10:
            suspicious.append(i)
        seen_texts[normalized] = i

        # Segments in the last 5% of audio (common hallucination zone)
        if duration and duration > 30:
            if seg.get("end", 0) > duration * 0.95:
                suspicious.append(i)

    return sorted(set(suspicious))
