import uuid

import pytest


@pytest.mark.asyncio
async def test_multichat_deep_research_merges_sources_without_nameerror(monkeypatch):
    """
    Regression: ChatService.dispatch_turn used _merge_citations in the deep-research branch
    before defining it, which raised UnboundLocalError when dense_research was enabled.
    """

    from app.services.chat_service import ChatOrchestrator, ThreadManager

    chat = ChatOrchestrator()
    # Use an isolated sqlite file to avoid interacting with any existing threads/messages.
    chat.thread_manager = ThreadManager(db_path=f"test_chat_{uuid.uuid4().hex}.db")
    thread = chat.thread_manager.create_thread("test")

    class DummyDeepResearch:
        async def stream_research_task(self, query: str, config=None):
            # Minimal events: ensure "done" provides sources for merge.
            yield {"type": "step.start", "step_name": "Pesquisando", "step_id": "s1"}
            yield {"type": "step.add_source", "step_id": "s1", "source": {"title": "X", "url": "https://example.com"}}
            yield {"type": "done", "sources": [{"title": "X", "url": "https://example.com"}]}

    # Patch the module-level deep_research_service imported in chat_service.py
    monkeypatch.setattr("app.services.chat_service.deep_research_service", DummyDeepResearch())

    # "force" policy + dense_research + effort => deep research branch executes.
    events = []
    async for event in chat.dispatch_turn(
        thread.id,
        "Pergunta de teste",
        selected_models=["unknown-model"],
        dense_research=True,
        deep_research_effort="low",
        research_policy="force",
    ):
        events.append(event)

    # The generator should complete and at least one citation must survive to the final "done" payload.
    done_events = [e for e in events if isinstance(e, dict) and e.get("type") == "done"]
    assert done_events, "Expected a final done event"
    assert any(
        (e.get("citations") or []) for e in done_events
    ), "Expected citations to be present when deep research returned sources"

