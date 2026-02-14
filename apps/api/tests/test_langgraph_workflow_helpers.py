import pytest

from app.services.ai import langgraph_legal_workflow as wf
from app.services.ai.document_chunker import TextChunk


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


@pytest.mark.asyncio
async def test_audit_node_attaches_citation_subagent_report(monkeypatch):
    async def fake_citation_subagent(state, full_document, citations_map):
        return {
            "subagent_enabled": True,
            "subagent_status": "ok",
            "coverage": 0.9,
            "claims_without_citation": [],
            "suspicious_citations": [],
            "summary": "ok",
        }

    monkeypatch.setattr(wf, "_maybe_run_citation_subagent", fake_citation_subagent)
    monkeypatch.setattr(
        wf.audit_service,
        "audit_document",
        lambda _doc: {"audit_report_markdown": "Aprovado", "citations": []},
    )

    state = {
        "full_document": "Documento final com citacao [1].",
        "citations_map": {"1": {"title": "Fonte 1"}},
    }
    result = await wf.audit_node(state)

    assert result["citation_subagent_report"]["subagent_status"] == "ok"
    assert result["audit_report"]["citation_subagent"]["subagent_status"] == "ok"


def test_entry_router_routes_large_docs_to_multi_pass_prepare():
    state = {
        "input_text": "A" * 20000,
        "document_route": "chunked_rag",
        "estimated_pages": 850,
    }
    assert wf.entry_router(state) == "multi_pass_prepare"


@pytest.mark.asyncio
async def test_multi_pass_prepare_node_is_noop_for_small_docs():
    state = {
        "input_text": "texto curto",
        "estimated_pages": 1,
        "document_route": "direct",
    }
    result = await wf.multi_pass_prepare_node(state)

    assert result["input_text"] == "texto curto"
    assert result["document_route"] == "direct"
    assert result["estimated_pages"] == 1
    assert "multi_pass_report" not in result or result["multi_pass_report"] is None


@pytest.mark.asyncio
async def test_multi_pass_prepare_node_summarizes_large_docs(monkeypatch):
    chunks = [
        TextChunk(index=0, text="Fatos relevantes do bloco 1", start_char=0, end_char=100),
        TextChunk(index=1, text="Fundamentos relevantes do bloco 2", start_char=101, end_char=200),
    ]

    monkeypatch.setattr(wf, "split_text_for_multi_pass", lambda *args, **kwargs: chunks)
    async def fake_call(model, prompt, **kwargs):
        if "bloco 1/2" in prompt.lower():
            return "Resumo sintético do chunk 1"
        return "Resumo sintético do chunk 2"

    monkeypatch.setattr(wf, "_call_model_any_async", fake_call)

    state = {
        "job_id": "",
        "input_text": "texto original muito grande",
        "document_route": "chunked_rag",
        "estimated_pages": 900,
    }
    result = await wf.multi_pass_prepare_node(state)

    assert result["original_input_text"] == "texto original muito grande"
    assert "[Chunk 1]" in result["input_text"]
    assert "[Chunk 2]" in result["input_text"]
    report = result["multi_pass_report"]
    assert report["status"] == "prepared"
    assert report["chunks_total"] == 2
    assert report["document_route"] == "chunked_rag"


@pytest.mark.asyncio
async def test_run_workflow_async_wraps_langsmith_trace(monkeypatch):
    entered = {"value": False}
    exited = {"value": False}

    class DummyTrace:
        def __enter__(self):
            entered["value"] = True
            return None

        def __exit__(self, exc_type, exc, tb):
            exited["value"] = True
            return False

    class DummyApp:
        async def ainvoke(self, initial_state, config=None):
            return {"job_id": initial_state.get("job_id"), "full_document": "ok"}

    monkeypatch.setattr(wf, "langsmith_trace", lambda *args, **kwargs: DummyTrace())
    monkeypatch.setattr(wf, "legal_workflow_app", DummyApp())

    result = await wf.run_workflow_async({"job_id": "job-trace"})

    assert entered["value"] is True
    assert exited["value"] is True
    assert result["full_document"] == "ok"
