"""
Tests for the unified audit endpoint.

Verifies:
- auto_applied vs pending_hil separation
- structural issues are classified correctly
- content issues always go to pending_hil
- deduplication works
- score computation
"""

import hashlib
from unittest.mock import AsyncMock, patch

import pytest

from app.schemas.audit_unified import (
    UnifiedAuditIssue,
    UnifiedAuditResponse,
    UnifiedIssueType,
    UnifiedSeverity,
    compute_fingerprint,
    deduplicate_issues,
    determine_fix_type,
    normalize_issue_type,
    normalize_severity,
)


# ---------------------------------------------------------------------------
# Schema helpers
# ---------------------------------------------------------------------------

class TestNormalizeSeverity:
    def test_critical(self):
        assert normalize_severity("critical") == UnifiedSeverity.critical

    def test_warning_maps_to_high(self):
        assert normalize_severity("warning") == UnifiedSeverity.high

    def test_unknown_defaults_to_medium(self):
        assert normalize_severity("unknown") == UnifiedSeverity.medium

    def test_empty_defaults_to_medium(self):
        assert normalize_severity("") == UnifiedSeverity.medium


class TestDetermineFixType:
    def test_explicit_structural(self):
        assert determine_fix_type("any", "structural") == "structural"

    def test_explicit_content(self):
        assert determine_fix_type("any", "content") == "content"

    def test_duplicate_paragraph_is_structural(self):
        assert determine_fix_type("duplicate_paragraph", "") == "structural"

    def test_heading_numbering_is_structural(self):
        assert determine_fix_type("heading_numbering", "") == "structural"

    def test_unknown_defaults_to_content(self):
        assert determine_fix_type("some_random_type", "") == "content"


class TestNormalizeIssueType:
    def test_preventive_omissao(self):
        assert normalize_issue_type("preventive_omissao") == UnifiedIssueType.omission

    def test_preventive_alucinacao(self):
        assert normalize_issue_type("preventive_alucinacao") == UnifiedIssueType.hallucination

    def test_duplicate_paragraph(self):
        assert normalize_issue_type("duplicate_paragraph") == UnifiedIssueType.structural

    def test_unknown_falls_back_to_structural(self):
        assert normalize_issue_type("totally_unknown") == UnifiedIssueType.structural


class TestDeduplication:
    def test_keeps_highest_confidence(self):
        fp = compute_fingerprint("omission", "test desc")
        issue_low = UnifiedAuditIssue(
            id="a", type=UnifiedIssueType.omission, severity=UnifiedSeverity.high,
            fix_type="content", source="preventive", fingerprint=fp, confidence=0.5,
        )
        issue_high = UnifiedAuditIssue(
            id="b", type=UnifiedIssueType.omission, severity=UnifiedSeverity.high,
            fix_type="content", source="quality", fingerprint=fp, confidence=0.9,
        )
        result = deduplicate_issues([issue_low, issue_high])
        assert len(result) == 1
        assert result[0].id == "b"

    def test_no_fingerprint_kept(self):
        issue = UnifiedAuditIssue(
            id="x", type=UnifiedIssueType.structural, severity=UnifiedSeverity.low,
            fix_type="structural", source="structural_analysis", fingerprint="", confidence=0.5,
        )
        result = deduplicate_issues([issue])
        assert len(result) == 1


# ---------------------------------------------------------------------------
# Endpoint normalization
# ---------------------------------------------------------------------------

class TestNormalizePreventiveIssues:
    """Test preventive audit JSON → UnifiedAuditIssue conversion."""

    def test_omissoes_criticas(self):
        from app.api.endpoints.audit_unified import normalize_preventive_issues

        audit = {
            "omissoes_criticas": [
                {
                    "tipo": "omissao",
                    "gravidade": "alta",
                    "descricao": "Lei 14.133 ausente",
                    "trecho_raw": "conforme a lei quatorze mil",
                    "correcao": "Inserir referencia a Lei 14.133",
                    "confianca": "alta",
                }
            ],
            "distorcoes": [],
            "alucinacoes": [],
        }
        issues = normalize_preventive_issues(audit)
        assert len(issues) == 1
        issue = issues[0]
        assert issue.fix_type == "content"
        assert issue.source == "preventive"
        assert issue.confidence == 0.85  # "alta" → 0.85
        assert "omissao" in issue.original_type

    def test_empty_audit(self):
        from app.api.endpoints.audit_unified import normalize_preventive_issues

        assert normalize_preventive_issues({}) == []
        assert normalize_preventive_issues(None) == []


class TestNormalizeQualityIssues:
    """Test quality analysis → UnifiedAuditIssue conversion."""

    def test_structural_fix(self):
        from app.api.endpoints.audit_unified import normalize_quality_issues

        analysis = {
            "pending_fixes": [
                {
                    "id": "dup_001",
                    "type": "duplicate_paragraph",
                    "fix_type": "structural",
                    "severity": "medium",
                    "description": "Paragrafo duplicado na secao 5",
                    "action": "Remover duplicata",
                    "confidence": 0.95,
                    "can_auto_apply": True,
                }
            ]
        }
        issues = normalize_quality_issues(analysis)
        assert len(issues) == 1
        issue = issues[0]
        assert issue.fix_type == "structural"
        assert issue.source == "structural_analysis"
        assert issue.can_auto_apply is True

    def test_missing_references(self):
        from app.api.endpoints.audit_unified import normalize_quality_issues

        analysis = {
            "pending_fixes": [],
            "missing_laws": ["Lei 14.133/2021"],
            "missing_sumulas": [],
        }
        issues = normalize_quality_issues(analysis)
        assert len(issues) == 1
        assert issues[0].type == UnifiedIssueType.missing_reference
        assert issues[0].fix_type == "content"


# ---------------------------------------------------------------------------
# Response structure
# ---------------------------------------------------------------------------

class TestUnifiedAuditResponse:
    """Test the response model includes auto_applied and pending_hil."""

    def test_response_has_auto_applied(self):
        resp = UnifiedAuditResponse(
            score=9.0,
            status="ok",
            total_issues=2,
            issues=[],
            auto_applied=[
                UnifiedAuditIssue(
                    id="auto_1", type=UnifiedIssueType.structural,
                    severity=UnifiedSeverity.low, fix_type="structural",
                    source="structural_analysis", confidence=1.0,
                    can_auto_apply=True, hil_ready=False,
                    description="Duplicata removida",
                )
            ],
            pending_hil=[
                UnifiedAuditIssue(
                    id="hil_1", type=UnifiedIssueType.omission,
                    severity=UnifiedSeverity.high, fix_type="content",
                    source="preventive", confidence=0.8,
                    description="Lei ausente",
                )
            ],
        )
        assert len(resp.auto_applied) == 1
        assert len(resp.pending_hil) == 1
        assert resp.auto_applied[0].hil_ready is False
        assert resp.pending_hil[0].fix_type == "content"

    def test_empty_response(self):
        resp = UnifiedAuditResponse()
        assert resp.auto_applied == []
        assert resp.pending_hil == []
        assert resp.score is None
