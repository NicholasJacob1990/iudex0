from app.services.ai.skills.skill_builder import (
    build_skill_draft,
    infer_triggers,
    validate_skill_markdown,
)
from app.schemas.skills import GenerateSkillRequest, PublishSkillRequest
from pydantic import ValidationError


def test_infer_triggers_enforces_minimum_and_maximum():
    triggers = infer_triggers("analisar petição", minimum=3, maximum=5)
    assert 3 <= len(triggers) <= 5


def test_build_skill_draft_produces_valid_skillv1_markdown():
    markdown = build_skill_draft(
        directive="Analisar petições iniciais trabalhistas com foco em preliminares e pedidos",
        name="petition-analysis-v1",
    )

    report = validate_skill_markdown(markdown)

    assert report["valid"] is True
    assert "name: petition-analysis-v1" in markdown
    assert "tools_required" in markdown


def test_validate_skill_markdown_detects_conflicts_and_risk_tools():
    markdown = """---
name: risky-skill
description: teste
triggers:
  - revisar
tools_required:
  - search_rag
  - bash
tools_denied:
  - search_rag
---

## Instructions
Executar revisão.
"""
    report = validate_skill_markdown(markdown)

    assert report["valid"] is False
    assert any("conflito" in err.lower() for err in report["errors"])
    assert any("alto risco" in warn.lower() for warn in report["warnings"])


def test_publish_skill_request_accepts_markdown_without_draft():
    payload = PublishSkillRequest(skill_markdown="---\nname: x\ntriggers:\n- a\ntools_required:\n- b\n---")
    assert payload.draft_id is None
    assert payload.skill_markdown is not None


def test_publish_skill_request_requires_draft_or_markdown():
    try:
        PublishSkillRequest()
    except ValidationError:
        return
    assert False, "ValidationError expected when draft_id and skill_markdown are missing"


def test_generate_skill_request_rejects_conflicting_preferences():
    try:
        GenerateSkillRequest(
            directive="Analisar petições com foco em nulidades e pedidos liminares.",
            triggers=["analisar peticao", "revisar peticao", "peticao inicial"],
            tools_required=["search_rag"],
            prefer_workflow=True,
            prefer_agent=True,
        )
    except ValidationError:
        return
    assert False, "ValidationError expected when prefer_workflow and prefer_agent are both true"


def test_generate_skill_request_rejects_tools_overlap():
    try:
        GenerateSkillRequest(
            directive="Revisar recurso especial com checklist de admissibilidade.",
            triggers=["revisar recurso", "recurso especial", "admissibilidade recursal"],
            tools_required=["search_rag", "verify_citation"],
            tools_denied=["verify_citation"],
        )
    except ValidationError:
        return
    assert False, "ValidationError expected when tools_required overlaps with tools_denied"


def test_validate_skill_markdown_returns_quality_metrics():
    markdown = build_skill_draft(
        directive="Analisar minuta contratual com foco em riscos de responsabilidade e compliance.",
        name="contract-risk-analysis",
        version="1.2.0",
        audience="advanced",
        prefer_workflow=True,
        prefer_agent=False,
        examples=[
            {"prompt": "revisar cláusula de indenização", "expected_behavior": "apontar riscos e propor redação"},
            {"prompt": "verificar compliance LGPD", "expected_behavior": "listar lacunas por cláusula"},
        ],
    )

    report = validate_skill_markdown(markdown)

    assert report["valid"] is True
    assert 0.0 <= report["quality_score"] <= 1.0
    assert 0.0 <= report["tpr"] <= 1.0
    assert 0.0 <= report["fpr"] <= 1.0
    assert report["parsed"]["version"] == "1.2.0"
    assert report["parsed"]["audience"] == "advanced"
