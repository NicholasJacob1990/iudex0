import json

import pytest

from app.services.ai.claude_agent.tools import citation_validator_agent as cva


@pytest.mark.asyncio
async def test_validate_citations_with_subagent_falls_back_without_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    result = await cva.validate_citations_with_subagent(
        document_text="Trecho com [1] e [2].",
        citations_map={"1": {"title": "Fonte 1"}, "3": {"title": "Fonte 3"}},
        session_key="job-1",
    )

    assert result["subagent_enabled"] is False
    assert result["subagent_status"] == "skipped_no_api_key"
    assert result["missing_keys"] == ["2"]
    assert "3" in result["orphan_keys"]


@pytest.mark.asyncio
async def test_validate_citations_with_subagent_merges_structured_response(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    async def fake_get_or_create_session(self, session_key: str):
        assert session_key == "job-merge"
        return object()

    async def fake_run_subagent(self, **kwargs):
        payload = {
            "coverage": 0.75,
            "claims_without_citation": ["Afirmacao X sem suporte"],
            "suspicious_citations": [{"key": "2", "reason": "Fonte nao menciona o dispositivo citado"}],
            "summary": "Validacao concluida.",
        }
        return {"text": json.dumps(payload), "metadata": {"model": "claude-haiku-4-5"}}

    monkeypatch.setattr(cva.CitationValidatorSubagentPool, "_get_or_create_session", fake_get_or_create_session)
    monkeypatch.setattr(cva.CitationValidatorSubagentPool, "_run_subagent", fake_run_subagent)

    result = await cva.validate_citations_with_subagent(
        document_text="Trecho juridico [1] [2].",
        citations_map={"1": {"title": "Fonte 1"}, "2": {"title": "Fonte 2"}},
        session_key="job-merge",
    )

    assert result["subagent_enabled"] is True
    assert result["subagent_status"] == "ok"
    assert result["coverage"] == 0.75
    assert result["claims_without_citation"] == ["Afirmacao X sem suporte"]
    assert result["suspicious_citations"][0]["key"] == "2"
    assert result["subagent_metadata"]["model"] == "claude-haiku-4-5"


@pytest.mark.asyncio
async def test_validate_citations_with_subagent_handles_subagent_failure(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    async def fake_get_or_create_session(self, session_key: str):
        return object()

    async def fake_run_subagent(self, **kwargs):
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(cva.CitationValidatorSubagentPool, "_get_or_create_session", fake_get_or_create_session)
    monkeypatch.setattr(cva.CitationValidatorSubagentPool, "_run_subagent", fake_run_subagent)

    result = await cva.validate_citations_with_subagent(
        document_text="Texto com [1].",
        citations_map={"1": {"title": "Fonte 1"}},
        session_key="job-failure",
    )

    assert result["subagent_enabled"] is True
    assert result["subagent_status"] == "failed"
    assert "deterministico" in result["summary"].lower()

