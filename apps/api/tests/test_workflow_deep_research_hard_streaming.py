import uuid

import pytest

from app.services.ai.shared.sse_protocol import SSEEventType
from app.services.ai.workflow_runner import WorkflowRunner


@pytest.mark.asyncio
async def test_workflow_deep_research_hard_streams_tokens(monkeypatch):
    """
    Ensure the deep_research node (hard mode) can stream tokens to the workflow
    SSE stream via JobManager polling in WorkflowRunner.
    """
    async def fake_stream(_query: str, config=None):  # noqa: ARG001
        yield {"type": "hard_research_start", "providers": (config or {}).get("providers", [])}
        yield {"type": "study_token", "delta": "Hello "}
        yield {"type": "study_token", "delta": "world"}
        yield {
            "type": "study_done",
            "sources": [{"url": "https://example.com", "title": "Example"}],
            "sources_count": 1,
            "iterations": 1,
            "elapsed_ms": 5,
            "provider_summaries": {"gemini": "OK"},
        }

    from app.services.ai import deep_research_hard_service as hard_mod

    monkeypatch.setattr(hard_mod.deep_research_hard_service, "stream_hard_research", fake_stream)

    graph_json = {
        "nodes": [
            {
                "id": "deep_1",
                "type": "deep_research",
                "position": {"x": 0, "y": 0},
                "data": {
                    "label": "Hard Deep Research",
                    "mode": "hard",
                    "effort": "low",
                    "providers": ["gemini"],
                    "query": "{{input}}",
                    "include_sources": True,
                },
            },
            {
                "id": "out_1",
                "type": "output",
                "position": {"x": 0, "y": 140},
                "data": {"label": "Output", "show_all": True},
            },
        ],
        "edges": [{"id": "e1", "source": "deep_1", "target": "out_1"}],
    }

    runner = WorkflowRunner(db=None)
    job_id = f"test_job_{uuid.uuid4()}"

    tokens = []
    done = False

    async for ev in runner.run_streaming(graph_json, input_data={"input": "any"}, job_id=job_id):
        if ev.type == SSEEventType.TOKEN:
            tokens.append(ev.data.get("token", ""))
        if ev.type == SSEEventType.DONE:
            done = True

    assert "".join(tokens) == "Hello world"
    assert done is True

