"""
False Positive Prevention Module

Validates HIL detections against the raw content (source of truth)
to prevent false positives before presenting to users.
"""

import re
import hashlib
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from difflib import SequenceMatcher, get_close_matches
from loguru import logger


class ConfidenceLevel(str, Enum):
    """Confidence levels for HIL detections."""
    VERY_HIGH = "very_high"  # 0.95+ - Almost certain
    HIGH = "high"            # 0.85-0.94 - Confident
    MEDIUM = "medium"        # 0.70-0.84 - Needs review
    LOW = "low"              # 0.50-0.69 - Likely false positive
    VERY_LOW = "very_low"    # <0.50 - Probable false positive


@dataclass
class ValidationThresholds:
    """Configurable thresholds for false positive prevention."""
    # Structural detection
    min_paragraph_length: int = 50
    min_section_content_length: int = 100
    section_title_similarity: float = 0.90
    section_content_similarity: float = 0.70

    # Law reference matching
    min_law_digits: int = 3
    min_law_value: int = 100
    law_edit_distance: int = 2  # Increased from 1

    # Compression analysis
    compression_critical_threshold: float = 0.50  # Changed from 0.70
    compression_warning_threshold: float = 0.70   # Changed from 0.85
    compression_ok_threshold: float = 0.85

    # Semantic patch validation
    min_evidence_snippets: int = 1
    evidence_match_threshold: float = 0.60
    patch_anchor_fuzzy_threshold: float = 0.80
    patch_old_text_fuzzy_threshold: float = 0.85

    # Confidence thresholds for filtering
    min_confidence_to_show: float = 0.50  # Below this, don't show to user
    min_confidence_for_auto_apply: float = 0.90  # Above this, can auto-apply


@dataclass
class ValidationResult:
    """Result of validating a HIL issue against raw content."""
    is_valid: bool
    confidence: float
    confidence_level: ConfidenceLevel
    evidence_found: List[str] = field(default_factory=list)
    validation_notes: List[str] = field(default_factory=list)
    should_show_to_user: bool = True
    can_auto_apply: bool = False


class FalsePositivePrevention:
    """
    Validates HIL detections against raw content to prevent false positives.
    Raw content is the SOURCE OF TRUTH.
    """

    def __init__(self, thresholds: Optional[ValidationThresholds] = None):
        self.thresholds = thresholds or ValidationThresholds()

    # =========================================================================
    # MAIN VALIDATION METHODS
    # =========================================================================

    def validate_hil_issue(
        self,
        issue: Dict[str, Any],
        raw_content: str,
        formatted_content: str,
    ) -> ValidationResult:
        """
        Validates a single HIL issue against raw content.
        Returns validation result with confidence score.
        """
        issue_type = issue.get("type", "")

        if issue_type == "omission":
            return self._validate_omission(issue, raw_content, formatted_content)
        elif issue_type == "distortion":
            return self._validate_distortion(issue, raw_content, formatted_content)
        elif issue_type == "duplicate_paragraph":
            return self._validate_duplicate_paragraph(issue, raw_content, formatted_content)
        elif issue_type == "duplicate_section":
            return self._validate_duplicate_section(issue, raw_content, formatted_content)
        elif issue_type == "heading_numbering":
            return self._validate_heading_numbering(issue, formatted_content)
        else:
            # Unknown type - medium confidence
            return ValidationResult(
                is_valid=True,
                confidence=0.70,
                confidence_level=ConfidenceLevel.MEDIUM,
                validation_notes=[f"Tipo desconhecido: {issue_type}"]
            )

    def validate_all_issues(
        self,
        issues: List[Dict[str, Any]],
        raw_content: str,
        formatted_content: str,
    ) -> List[Dict[str, Any]]:
        """
        Validates all HIL issues and enriches them with confidence scores.
        Filters out likely false positives.
        """
        validated_issues = []

        for issue in issues:
            result = self.validate_hil_issue(issue, raw_content, formatted_content)

            # Enrich issue with validation data
            issue["confidence"] = result.confidence
            issue["confidence_level"] = result.confidence_level.value
            issue["evidence"] = result.evidence_found
            issue["validation_notes"] = result.validation_notes
            issue["can_auto_apply"] = result.can_auto_apply

            # Filter based on confidence threshold
            if result.should_show_to_user and result.confidence >= self.thresholds.min_confidence_to_show:
                validated_issues.append(issue)
            else:
                logger.info(
                    f"🚫 Filtrado por baixa confiança ({result.confidence:.2f}): "
                    f"{issue.get('type')} - {issue.get('description', '')[:50]}..."
                )

        return validated_issues

    # =========================================================================
    # OMISSION VALIDATION
    # =========================================================================

    def _validate_omission(
        self,
        issue: Dict[str, Any],
        raw_content: str,
        formatted_content: str,
    ) -> ValidationResult:
        """
        Validates an omission claim by checking if content exists in raw but not in formatted.
        """
        description = issue.get("description", "")
        patch = issue.get("patch", {}) or {}
        new_text = patch.get("new_text", "")

        notes = []
        confidence = 0.50  # Base confidence
        evidence = []

        # 1. Check if the omitted content is actually in the raw
        raw_evidence = self._find_evidence_in_raw(raw_content, description)
        if raw_evidence:
            evidence.extend(raw_evidence)
            confidence += 0.20
            notes.append(f"✓ Encontrada evidência no RAW ({len(raw_evidence)} trechos)")
        else:
            confidence -= 0.20
            notes.append("✗ Não encontrada evidência clara no RAW")

        # 2. Check if the content is really missing from formatted
        if new_text:
            # Check if similar content already exists in formatted
            similarity = self._text_similarity(new_text, formatted_content)
            if similarity > 0.80:
                confidence -= 0.30
                notes.append(f"⚠️ Conteúdo similar já existe no formatado (sim: {similarity:.2f})")
            elif similarity > 0.50:
                confidence -= 0.10
                notes.append(f"⚠️ Conteúdo parcialmente presente (sim: {similarity:.2f})")
            else:
                confidence += 0.15
                notes.append("✓ Conteúdo realmente ausente do formatado")

        # 3. Validate patch anchor exists
        anchor = patch.get("anchor_text", "")
        if anchor:
            anchor_found, anchor_match = self._fuzzy_find_in_text(anchor, formatted_content)
            if anchor_found:
                confidence += 0.10
                notes.append("✓ Âncora encontrada no formatado")
            else:
                confidence -= 0.15
                notes.append("⚠️ Âncora não encontrada - patch pode falhar")

        # 4. Check for legal references in raw vs formatted
        legal_refs_raw = self._extract_legal_references(description + " " + " ".join(raw_evidence))
        if legal_refs_raw:
            refs_in_formatted = sum(1 for ref in legal_refs_raw if ref.lower() in formatted_content.lower())
            if refs_in_formatted < len(legal_refs_raw):
                confidence += 0.10
                notes.append(f"✓ Referências legais omitidas: {len(legal_refs_raw) - refs_in_formatted}")

        # Clamp confidence
        confidence = max(0.0, min(1.0, confidence))

        return ValidationResult(
            is_valid=confidence >= 0.50,
            confidence=confidence,
            confidence_level=self._confidence_to_level(confidence),
            evidence_found=evidence,
            validation_notes=notes,
            should_show_to_user=confidence >= self.thresholds.min_confidence_to_show,
            can_auto_apply=confidence >= self.thresholds.min_confidence_for_auto_apply,
        )

    # =========================================================================
    # DISTORTION VALIDATION
    # =========================================================================

    def _validate_distortion(
        self,
        issue: Dict[str, Any],
        raw_content: str,
        formatted_content: str,
    ) -> ValidationResult:
        """
        Validates a distortion claim by checking if the correction matches raw content.
        """
        description = issue.get("description", "")
        patch = issue.get("patch", {}) or {}
        old_text = patch.get("old_text", "")
        new_text = patch.get("new_text", "")

        notes = []
        confidence = 0.50
        evidence = []

        # 1. Check if old_text exists in formatted (with fuzzy matching)
        if old_text:
            found, match = self._fuzzy_find_in_text(
                old_text,
                formatted_content,
                threshold=self.thresholds.patch_old_text_fuzzy_threshold
            )
            if found:
                confidence += 0.15
                notes.append(f"✓ Texto original encontrado no formatado")
                if match != old_text:
                    notes.append(f"  (fuzzy match: '{match[:50]}...')")
            else:
                confidence -= 0.25
                notes.append("✗ Texto original não encontrado no formatado")

        # 2. Check if new_text matches raw content
        if new_text:
            raw_evidence = self._find_evidence_in_raw(raw_content, new_text)
            if raw_evidence:
                evidence.extend(raw_evidence)
                confidence += 0.25
                notes.append(f"✓ Correção corresponde ao RAW ({len(raw_evidence)} trechos)")
            else:
                # Check semantic similarity with raw
                similarity = self._text_similarity(new_text, raw_content)
                if similarity > 0.70:
                    confidence += 0.10
                    notes.append(f"✓ Correção similar ao RAW (sim: {similarity:.2f})")
                else:
                    confidence -= 0.20
                    notes.append("⚠️ Correção não encontrada no RAW - possível alucinação")

        # 3. Check if old and new are actually different
        if old_text and new_text:
            similarity = self._text_similarity(old_text, new_text)
            if similarity > 0.95:
                confidence -= 0.30
                notes.append("✗ Textos são quase idênticos - não há distorção real")
            elif similarity < 0.30:
                confidence += 0.05
                notes.append("✓ Correção é significativamente diferente")

        # 4. Validate legal references in correction
        legal_refs_new = self._extract_legal_references(new_text)
        legal_refs_raw = self._extract_legal_references(raw_content)
        if legal_refs_new:
            valid_refs = sum(
                1 for ref in legal_refs_new
                if self._reference_exists_in_text(ref, raw_content, legal_refs_raw)
            )
            if valid_refs == len(legal_refs_new):
                confidence += 0.10
                notes.append("✓ Referências legais validadas contra RAW")
            else:
                confidence -= 0.15
                notes.append(f"⚠️ {len(legal_refs_new) - valid_refs} referências não confirmadas no RAW")

        confidence = max(0.0, min(1.0, confidence))

        return ValidationResult(
            is_valid=confidence >= 0.50,
            confidence=confidence,
            confidence_level=self._confidence_to_level(confidence),
            evidence_found=evidence,
            validation_notes=notes,
            should_show_to_user=confidence >= self.thresholds.min_confidence_to_show,
            can_auto_apply=confidence >= self.thresholds.min_confidence_for_auto_apply,
        )

    # =========================================================================
    # STRUCTURAL VALIDATION
    # =========================================================================

    def _validate_duplicate_paragraph(
        self,
        issue: Dict[str, Any],
        raw_content: str,
        formatted_content: str,
    ) -> ValidationResult:
        """
        Validates duplicate paragraph detection.
        Checks if it's truly a duplicate vs. intentional repetition.
        """
        description = issue.get("description", "")
        fingerprint = issue.get("fingerprint", "")

        notes = []
        confidence = 0.80  # Structural issues start with higher confidence

        # 1. Check if the paragraph appears multiple times in raw
        # (intentional repetition in source)
        paragraph_text = self._extract_text_from_description(description)
        if paragraph_text:
            raw_occurrences = self._count_occurrences(paragraph_text, raw_content)
            formatted_occurrences = self._count_occurrences(paragraph_text, formatted_content)

            if raw_occurrences > 1:
                confidence -= 0.30
                notes.append(f"⚠️ Parágrafo aparece {raw_occurrences}x no RAW - pode ser repetição intencional")
            else:
                confidence += 0.10
                notes.append("✓ Parágrafo aparece 1x no RAW - duplicação no formatado")

            if formatted_occurrences > 2:
                confidence += 0.05
                notes.append(f"✓ Múltiplas duplicações ({formatted_occurrences}x) no formatado")

        # 2. Check context around duplicates (different sections?)
        # This is a heuristic - duplicates in different sections might be intentional

        confidence = max(0.0, min(1.0, confidence))

        return ValidationResult(
            is_valid=confidence >= 0.50,
            confidence=confidence,
            confidence_level=self._confidence_to_level(confidence),
            validation_notes=notes,
            should_show_to_user=True,  # Always show structural issues
            can_auto_apply=confidence >= 0.90,
        )

    def _validate_duplicate_section(
        self,
        issue: Dict[str, Any],
        raw_content: str,
        formatted_content: str,
    ) -> ValidationResult:
        """
        Validates duplicate section detection.
        """
        title = issue.get("title", "")

        notes = []
        confidence = 0.75

        # Check if section title appears in raw
        if title:
            clean_title = re.sub(r'^#+\s*\d*\.?\s*', '', title).strip()
            raw_occurrences = self._count_occurrences(clean_title, raw_content, case_sensitive=False)

            if raw_occurrences > 1:
                confidence -= 0.20
                notes.append(f"⚠️ Título aparece {raw_occurrences}x no RAW")
            else:
                confidence += 0.15
                notes.append("✓ Título único no RAW - seção duplicada no formatado")

        confidence = max(0.0, min(1.0, confidence))

        return ValidationResult(
            is_valid=confidence >= 0.50,
            confidence=confidence,
            confidence_level=self._confidence_to_level(confidence),
            validation_notes=notes,
            should_show_to_user=True,
            can_auto_apply=confidence >= 0.90,
        )

    def _validate_heading_numbering(
        self,
        issue: Dict[str, Any],
        formatted_content: str,
    ) -> ValidationResult:
        """
        Validates heading numbering issues.
        This is deterministic so always high confidence.
        """
        return ValidationResult(
            is_valid=True,
            confidence=0.95,
            confidence_level=ConfidenceLevel.VERY_HIGH,
            validation_notes=["✓ Numeração sequencial incorreta - correção determinística"],
            should_show_to_user=True,
            can_auto_apply=True,
        )

    # =========================================================================
    # COMPRESSION ANALYSIS
    # =========================================================================

    def analyze_compression(
        self,
        raw_content: str,
        formatted_content: str,
    ) -> Dict[str, Any]:
        """
        Analyzes compression ratio and determines if it's intentional summarization
        or data loss.
        """
        raw_len = len(raw_content)
        formatted_len = len(formatted_content)

        if raw_len == 0:
            return {
                "ratio": 1.0,
                "status": "ok",
                "is_intentional_summarization": False,
                "notes": ["RAW vazio"]
            }

        ratio = formatted_len / raw_len
        notes = []
        is_intentional = False

        # Check for summarization markers
        summarization_markers = [
            r'\bresumindo\b', r'\bem resumo\b', r'\bsíntese\b',
            r'\bpontos principais\b', r'\bdestaques\b', r'\bglossário\b',
            r'\bíndice\b', r'\bsumário\b'
        ]
        has_summarization_markers = any(
            re.search(pattern, formatted_content, re.IGNORECASE)
            for pattern in summarization_markers
        )

        # Check for removed metadata (timestamps, speaker names, etc.)
        metadata_patterns = [
            r'\[\d{2}:\d{2}(:\d{2})?\]',  # Timestamps
            r'^[A-Z\s]+:',  # Speaker names
            r'\[inaudível\]', r'\[ruído\]',  # Noise markers
        ]
        raw_metadata_count = sum(
            len(re.findall(pattern, raw_content, re.MULTILINE))
            for pattern in metadata_patterns
        )

        # Adjust ratio for metadata removal
        estimated_metadata_chars = raw_metadata_count * 15  # Rough estimate
        adjusted_ratio = formatted_len / max(1, raw_len - estimated_metadata_chars)

        # Determine status
        if has_summarization_markers:
            is_intentional = True
            notes.append("📝 Documento parece ser um resumo/síntese intencional")

        if raw_metadata_count > 10:
            notes.append(f"ℹ️ ~{raw_metadata_count} marcadores de metadata removidos do RAW")
            notes.append(f"   Ratio ajustado: {adjusted_ratio:.2%}")

        if ratio < self.thresholds.compression_critical_threshold:
            if is_intentional:
                status = "warning"
                notes.append("⚠️ Compressão alta mas aparenta ser intencional")
            else:
                status = "critical"
                notes.append("🚨 Possível perda significativa de conteúdo")
        elif ratio < self.thresholds.compression_warning_threshold:
            status = "warning"
            notes.append("⚠️ Revisar possíveis omissões")
        else:
            status = "ok"
            notes.append("✓ Ratio de compressão aceitável")

        return {
            "ratio": ratio,
            "adjusted_ratio": adjusted_ratio,
            "status": status,
            "is_intentional_summarization": is_intentional,
            "metadata_removed_count": raw_metadata_count,
            "notes": notes,
        }

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _find_evidence_in_raw(
        self,
        raw_content: str,
        search_text: str,
        max_snippets: int = 3,
        window: int = 300,
    ) -> List[str]:
        """Finds relevant snippets in raw content."""
        if not raw_content or not search_text:
            return []

        snippets = []

        # Extract keywords and phrases
        keywords = self._extract_keywords(search_text)

        for keyword in keywords[:5]:
            if len(keyword) < 3:
                continue

            pattern = re.escape(keyword)
            for match in re.finditer(pattern, raw_content, re.IGNORECASE):
                start = max(0, match.start() - window)
                end = min(len(raw_content), match.end() + window)
                snippet = raw_content[start:end].strip()

                if snippet and snippet not in snippets:
                    snippets.append(f"...{snippet}...")
                    if len(snippets) >= max_snippets:
                        return snippets

        return snippets

    def _extract_keywords(self, text: str) -> List[str]:
        """Extracts meaningful keywords from text."""
        keywords = []

        # Legal references
        legal_patterns = [
            r'[Ll]ei\s*(?:n[º°]?\s*)?([\d.]+(?:/\d+)?)',
            r'[Aa]rt(?:igo)?\.?\s*(\d+)',
            r'[Ss]úmula\s*(?:[Vv]inculante\s*)?(?:n[º°]?\s*)?(\d+)',
            r'[Dd]ecreto\s*(?:n[º°]?\s*)?([\d.]+)',
        ]

        for pattern in legal_patterns:
            matches = re.findall(pattern, text)
            keywords.extend(matches)

        # Quoted text
        quoted = re.findall(r'"([^"]+)"', text)
        keywords.extend(quoted)

        # Long words (likely important terms)
        words = re.findall(r'\b[A-Za-zÀ-ÿ]{6,}\b', text)
        keywords.extend(words[:10])

        return list(set(keywords))

    def _extract_legal_references(self, text: str) -> List[str]:
        """Extracts legal references from text."""
        refs = []

        patterns = [
            r'[Ll]ei\s*(?:n[º°]?\s*)?([\d.]+(?:/\d+)?)',
            r'[Aa]rt(?:igo)?\.?\s*(\d+)',
            r'[Ss]úmula\s*(?:[Vv]inculante\s*)?\s*(\d+)',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, text)
            refs.extend(matches)

        return list(set(refs))

    def _reference_exists_in_text(
        self,
        ref: str,
        text: str,
        known_refs: List[str],
    ) -> bool:
        """Checks if a legal reference exists in text with fuzzy matching."""
        # Direct match
        if ref in text:
            return True

        # Fuzzy match against known references
        normalized_ref = self._normalize_law_number(ref)
        for known in known_refs:
            normalized_known = self._normalize_law_number(known)
            if self._law_numbers_match(normalized_ref, normalized_known):
                return True

        return False

    def _normalize_law_number(self, number: str) -> str:
        """Normalizes a law number for comparison."""
        # Remove dots, slashes, year suffixes
        cleaned = re.sub(r'[./]', '', str(number))
        # Remove year suffix (last 2-4 digits if preceded by year pattern)
        cleaned = re.sub(r'(\d{4,})(?:19|20)\d{2}$', r'\1', cleaned)
        return cleaned

    def _law_numbers_match(self, num1: str, num2: str) -> bool:
        """Checks if two law numbers match with edit distance tolerance."""
        if num1 == num2:
            return True

        # Edit distance check (now 2 instead of 1)
        if abs(len(num1) - len(num2)) <= 1:
            distance = self._edit_distance(num1, num2)
            if distance <= self.thresholds.law_edit_distance:
                return True

        # Prefix/suffix match
        if len(num1) >= 4 and len(num2) >= 4:
            if num1.endswith(num2) or num2.endswith(num1):
                return True

        return False

    def _edit_distance(self, s1: str, s2: str) -> int:
        """Calculates Levenshtein edit distance."""
        if len(s1) < len(s2):
            return self._edit_distance(s2, s1)

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

    def _text_similarity(self, text1: str, text2: str) -> float:
        """Calculates similarity between two texts."""
        if not text1 or not text2:
            return 0.0

        # Normalize texts
        t1 = re.sub(r'\s+', ' ', text1.lower().strip())
        t2 = re.sub(r'\s+', ' ', text2.lower().strip())

        return SequenceMatcher(None, t1, t2).ratio()

    def _fuzzy_find_in_text(
        self,
        needle: str,
        haystack: str,
        threshold: float = 0.80,
    ) -> Tuple[bool, str]:
        """
        Finds text in haystack with fuzzy matching.
        Returns (found, matched_text).
        """
        if not needle or not haystack:
            return False, ""

        # Exact match
        if needle in haystack:
            return True, needle

        # Normalize for comparison
        needle_norm = re.sub(r'\s+', ' ', needle.lower().strip())

        # Sliding window search
        needle_len = len(needle_norm)
        haystack_norm = re.sub(r'\s+', ' ', haystack.lower())

        best_match = ""
        best_ratio = 0.0

        # Check in windows
        for i in range(0, len(haystack_norm) - needle_len + 1, needle_len // 4):
            window = haystack_norm[i:i + needle_len + 20]  # Slightly larger window
            ratio = SequenceMatcher(None, needle_norm, window[:len(needle_norm)]).ratio()

            if ratio > best_ratio:
                best_ratio = ratio
                # Get original text (not normalized)
                best_match = haystack[i:i + needle_len + 20][:len(needle)]

        if best_ratio >= threshold:
            return True, best_match

        return False, ""

    def _count_occurrences(
        self,
        text: str,
        content: str,
        case_sensitive: bool = True,
    ) -> int:
        """Counts occurrences of text in content."""
        if not text or not content:
            return 0

        if not case_sensitive:
            text = text.lower()
            content = content.lower()

        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text.strip())
        content = re.sub(r'\s+', ' ', content)

        return content.count(text)

    def _extract_text_from_description(self, description: str) -> str:
        """Extracts the actual text content from an issue description."""
        # Try to find quoted text
        quoted = re.findall(r'"([^"]+)"', description)
        if quoted:
            return quoted[0]

        # Try to find text after colon
        if ':' in description:
            return description.split(':', 1)[1].strip()[:200]

        return description[:200]

    def _confidence_to_level(self, confidence: float) -> ConfidenceLevel:
        """Converts numeric confidence to level."""
        if confidence >= 0.95:
            return ConfidenceLevel.VERY_HIGH
        elif confidence >= 0.85:
            return ConfidenceLevel.HIGH
        elif confidence >= 0.70:
            return ConfidenceLevel.MEDIUM
        elif confidence >= 0.50:
            return ConfidenceLevel.LOW
        else:
            return ConfidenceLevel.VERY_LOW


# Singleton instance with default thresholds
false_positive_prevention = FalsePositivePrevention()
