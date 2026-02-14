from types import SimpleNamespace

import pytest

from app.api.endpoints import chats
from app.services.ai.skills.models import SkillDefinition, SkillMatch


@pytest.mark.asyncio
async def test_resolve_matched_skill_prompt_returns_rendered_prompt(monkeypatch):
    skill = SkillDefinition(
        name="petition-analysis",
        description="Analisa petições",
        triggers=["analisar petição"],
        tools_required=["search_rag", "verify_citation"],
        instructions="Faça análise objetiva.",
        source="test",
        subagent_model="claude-haiku-4-5",
    )
    match = SkillMatch(skill=skill, score=1.0, matched_triggers=["analisar petição"])

    async def fake_match_user_skill(**kwargs):
        return match

    monkeypatch.setattr(
        "app.services.ai.skills.matcher.match_user_skill",
        fake_match_user_skill,
    )

    prompt, name, ctx = await chats._resolve_matched_skill_prompt(
        user_id="user-1",
        user_input="quero analisar petição inicial",
        db=SimpleNamespace(),
    )

    assert name == "petition-analysis"
    assert "SKILL ATIVA: petition-analysis" in prompt
    assert "Tools requeridas: search_rag, verify_citation" in prompt
    assert ctx.get("skill_matched") is True


@pytest.mark.asyncio
async def test_resolve_matched_skill_prompt_returns_empty_when_no_match(monkeypatch):
    async def fake_match_user_skill(**kwargs):
        return None

    monkeypatch.setattr(
        "app.services.ai.skills.matcher.match_user_skill",
        fake_match_user_skill,
    )

    prompt, name, ctx = await chats._resolve_matched_skill_prompt(
        user_id="user-1",
        user_input="mensagem sem gatilho",
        db=SimpleNamespace(),
    )

    assert prompt == ""
    assert name is None
    assert ctx == {}


@pytest.mark.asyncio
async def test_resolve_matched_skill_prompt_fail_open_on_exception(monkeypatch):
    async def fake_match_user_skill(**kwargs):
        raise RuntimeError("matcher failed")

    monkeypatch.setattr(
        "app.services.ai.skills.matcher.match_user_skill",
        fake_match_user_skill,
    )

    prompt, name, ctx = await chats._resolve_matched_skill_prompt(
        user_id="user-1",
        user_input="qualquer coisa",
        db=SimpleNamespace(),
    )

    assert prompt == ""
    assert name is None
    assert ctx == {}

