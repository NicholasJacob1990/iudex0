from app.services.ai.skills.loader import load_builtin_skills, parse_skill_markdown
from app.services.ai.skills.matcher import match_skill, render_skill_prompt
from app.services.ai.skills.models import SkillDefinition, SkillMatch


def test_parse_skill_markdown_valid_frontmatter():
    markdown = """---
name: custom-skill
description: Skill de teste
triggers: ["foo", "bar", "baz"]
tools_required: ["search_rag", "verify_citation"]
subagent_model: claude-haiku-4-5
prefer_workflow: false
prefer_agent: true
---

## Instructions
Faça algo útil.
"""
    skill = parse_skill_markdown(markdown, source="test")
    assert skill is not None
    assert skill.name == "custom-skill"
    assert skill.triggers == ["foo", "bar", "baz"]
    assert skill.tools_required == ["search_rag", "verify_citation"]
    assert "Faça algo útil." in skill.instructions


def test_parse_skill_markdown_missing_required_fields_returns_none():
    markdown = """---
name: invalid-skill
description: sem campos obrigatórios
---

conteúdo
"""
    skill = parse_skill_markdown(markdown, source="test")
    assert skill is None


def test_parse_skill_markdown_rejects_conflicting_prefer_flags():
    markdown = """---
name: invalid-routing
description: conflito de roteamento
triggers: ["gatilho um", "gatilho dois", "gatilho tres"]
tools_required: ["search_rag"]
prefer_workflow: true
prefer_agent: true
---

## Instructions
Conteudo minimo.
"""
    skill = parse_skill_markdown(markdown, source="test")
    assert skill is None


def test_parse_skill_markdown_rejects_tools_required_denied_overlap():
    markdown = """---
name: invalid-tools
description: conflito de ferramentas
triggers: ["gatilho um", "gatilho dois", "gatilho tres"]
tools_required: ["search_rag", "verify_citation"]
tools_denied: ["verify_citation"]
prefer_workflow: false
prefer_agent: true
---

## Instructions
Conteudo minimo.
"""
    skill = parse_skill_markdown(markdown, source="test")
    assert skill is None


def test_match_skill_selects_highest_trigger_hits():
    a = SkillDefinition(
        name="skill-a",
        description="A",
        triggers=["analisar", "petição"],
        tools_required=["search_rag"],
        instructions="A",
        source="test",
    )
    b = SkillDefinition(
        name="skill-b",
        description="B",
        triggers=["resumir processo"],
        tools_required=["ask_graph"],
        instructions="B",
        source="test",
    )

    match = match_skill([a, b], "preciso analisar petição inicial agora")
    assert match is not None
    assert match.skill.name == "skill-a"
    assert match.score == 2.0


def test_render_skill_prompt_contains_key_sections():
    skill = SkillDefinition(
        name="skill-x",
        description="Descrição X",
        triggers=["gatilho x"],
        tools_required=["search_rag", "verify_citation"],
        instructions="Use linguagem objetiva.",
        source="test",
        subagent_model="claude-haiku-4-5",
    )
    match = SkillMatch(skill=skill, score=1.0, matched_triggers=["gatilho x"])
    prompt = render_skill_prompt(match)

    assert "SKILL ATIVA: skill-x" in prompt
    assert "Tools requeridas: search_rag, verify_citation" in prompt
    assert "Subagent model sugerido: claude-haiku-4-5" in prompt
    assert "Use linguagem objetiva." in prompt


def test_load_builtin_skills_returns_versioned_skills():
    skills = load_builtin_skills()
    names = {s.name for s in skills}
    assert "petition-analysis" in names
    assert "contract-review" in names
    assert "document-drafting" in names
    drafting = next(s for s in skills if s.name == "document-drafting")
    assert drafting.prefer_workflow is True
    assert drafting.prefer_agent is False
