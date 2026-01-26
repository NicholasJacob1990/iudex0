import pytest


@pytest.mark.asyncio
async def test_deep_research_cache_hit_replays_step_sources(monkeypatch):
    # Cache hits should still emit step.* events so the UI Activity Panel shows sources consistently.
    from app.services.ai.deep_research_service import deep_research_service
    import app.services.ai.deep_research_service as dr_mod

    cached = {
        "cache_key": "k1",
        "report": "cached report",
        "thinking_steps": [{"text": "cached thinking"}],
        "sources": [{"number": 1, "title": "Source A", "url": "https://example.com/a"}],
    }

    monkeypatch.setattr(dr_mod.job_manager, "get_cached_deep_research", lambda _key: cached)

    events = []
    async for ev in deep_research_service.stream_research_task("q", config={"provider": "openai"}):
        events.append(ev)

    types = [e.get("type") for e in events]
    assert "cache_hit" in types
    assert "step.start" in types
    assert "step.add_source" in types
    assert "step.done" in types
    assert types[-1] == "done"

    done = next(e for e in events if e.get("type") == "done")
    assert isinstance(done.get("sources"), list)
    assert any(s.get("url") == "https://example.com/a" for s in done["sources"])


@pytest.mark.asyncio
async def test_deep_research_cache_hit_fallback_sources(monkeypatch):
    from app.services.ai.deep_research_service import deep_research_service
    import app.services.ai.deep_research_service as dr_mod

    cached = {
        "cache_key": "k2",
        "report": "cached report",
        "thinking_steps": [],
        "sources": [],
    }

    monkeypatch.setattr(dr_mod.job_manager, "get_cached_deep_research", lambda _key: cached)
    async def _fake_fallback(**_kwargs):
        return [{"number": 1, "title": "Fallback", "url": "https://example.com/fallback"}]

    monkeypatch.setattr(deep_research_service, "_fallback_web_sources", _fake_fallback)

    events = []
    async for ev in deep_research_service.stream_research_task("q", config={"provider": "openai"}):
        events.append(ev)

    done = next(e for e in events if e.get("type") == "done")
    assert any(s.get("url") == "https://example.com/fallback" for s in done.get("sources") or [])
    assert any(e.get("type") == "step.add_source" and e.get("source", {}).get("url") == "https://example.com/fallback" for e in events)


@pytest.mark.asyncio
async def test_deep_research_cache_hit_errors_without_sources(monkeypatch):
    from app.services.ai.deep_research_service import deep_research_service
    import app.services.ai.deep_research_service as dr_mod

    cached = {
        "cache_key": "k3",
        "report": "cached report",
        "thinking_steps": [],
        "sources": [],
    }

    monkeypatch.setattr(dr_mod.job_manager, "get_cached_deep_research", lambda _key: cached)
    async def _fake_empty_fallback(**_kwargs):
        return []

    monkeypatch.setattr(deep_research_service, "_fallback_web_sources", _fake_empty_fallback)

    events = []
    async for ev in deep_research_service.stream_research_task("q", config={"provider": "openai"}):
        events.append(ev)

    types = [e.get("type") for e in events]
    assert "error" in types
    assert "done" not in types
