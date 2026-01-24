import pytest

from app.services.ai import langgraph_legal_workflow as wf


@pytest.mark.asyncio
async def test_outline_node_uses_dynamic_outline(monkeypatch):
    captured = {}

    async def fake_call(model_id, prompt, **kwargs):
        captured["prompt"] = prompt
        return "I - Sec 1\nII - Sec 2\nIII - Sec 3"

    monkeypatch.setattr(wf, "_call_model_any_async", fake_call)

    state = {
        "mode": "PETICAO",
        "input_text": "Caso de teste",
        "tese": "Tese central",
        "min_pages": 5,
        "max_pages": 7,
        "job_id": "",
        "strategist_model": "dummy-model",
    }

    result = await wf.outline_node(state)

    assert "I - Sec 1" in result.get("outline", [])
    guidance = wf._outline_size_guidance(5, 7)
    assert guidance in captured.get("prompt", "")


def test_parse_outline_response_lines():
    text = "I - FATOS\nII - DIREITO\nIII - PEDIDOS\n"
    out = wf._parse_outline_response(text)
    assert out == ["I - FATOS", "II - DIREITO", "III - PEDIDOS"]


def test_parse_outline_response_json():
    text = '["I - FATOS", "II - DIREITO", "III - PEDIDOS"]'
    out = wf._parse_outline_response(text)
    assert out == ["I - FATOS", "II - DIREITO", "III - PEDIDOS"]


def test_research_router_sei_only_forces_fact_check():
    state = {
        "audit_mode": "sei_only",
        "web_search_enabled": True,
        "deep_research_enabled": True,
    }
    assert wf.research_router(state) == "fact_check"


def test_research_retry_router_prefers_deep_research_on_insufficient_web():
    state = {
        "web_search_insufficient": True,
        "deep_research_enabled": True,
    }
    assert wf.research_retry_router(state) == "deep_research"


def test_ensure_review_schema_injects_defaults():
    sections = [
        {"section_title": "A", "merged_content": "texto"},
        {"section_title": "B", "merged_content": "texto", "review": {"critique": {"issues": ["x"]}}},
        {"section_title": "C", "merged_content": "texto", "review": {"critique": "bad", "revision": None, "merge": {}}},
    ]

    normalized = wf._ensure_review_schema(sections)

    for section in normalized:
        review = section.get("review")
        assert isinstance(review, dict)
        assert isinstance(review.get("critique"), dict)
        assert isinstance(review.get("revision"), dict)
        assert isinstance(review.get("merge"), dict)

        critique = review["critique"]
        revision = review["revision"]
        merge = review["merge"]

        assert isinstance(critique.get("issues"), list)
        assert isinstance(critique.get("summary"), str)
        assert isinstance(critique.get("by_agent"), dict)
        assert isinstance(revision.get("changelog"), list)
        assert isinstance(revision.get("resolved"), list)
        assert isinstance(revision.get("unresolved"), list)
        assert isinstance(merge.get("rationale"), str)
        assert isinstance(merge.get("decisions"), list)
        assert isinstance(merge.get("judge_structured"), dict)


def test_extract_json_strict_handles_code_fence():
    raw = "```json\n{\"ok\": true, \"n\": 2}\n```"
    parsed = wf.extract_json_strict(raw, expect="object")
    assert parsed == {"ok": True, "n": 2}


def test_validate_citations_detects_missing_and_orphans():
    text = "Trecho com [1] e [2]."
    citations_map = {"1": {"title": "Fonte 1"}, "3": {"title": "Fonte 3"}}
    report = wf.validate_citations(text, citations_map)
    assert report["used_keys"] == ["1", "2"]
    assert report["missing_keys"] == ["2"]
    assert "3" in report["orphan_keys"]
