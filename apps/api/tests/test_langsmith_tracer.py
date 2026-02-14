from app.services.ai.observability import langsmith_tracer as tracer


def test_is_langsmith_enabled_requires_flag_and_key(monkeypatch):
    monkeypatch.delenv("IUDEX_LANGSMITH_ENABLED", raising=False)
    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    assert tracer.is_langsmith_enabled() is False

    monkeypatch.setenv("IUDEX_LANGSMITH_ENABLED", "true")
    assert tracer.is_langsmith_enabled() is False

    monkeypatch.setenv("LANGSMITH_API_KEY", "test-key")
    assert tracer.is_langsmith_enabled() is True


def test_langsmith_trace_is_fail_open_when_unavailable(monkeypatch):
    monkeypatch.setenv("IUDEX_LANGSMITH_ENABLED", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "test-key")
    monkeypatch.setattr(tracer, "_load_trace_callable", lambda: None)

    entered = False
    with tracer.langsmith_trace("unit-test"):
        entered = True

    assert entered is True


def test_extract_langsmith_run_metadata_from_object():
    class DummyRun:
        id = "run-123"
        url = "https://smith.langchain.com/public/run-123"

    metadata = tracer.extract_langsmith_run_metadata(DummyRun())
    assert metadata["langsmith_run_id"] == "run-123"
    assert metadata["langsmith_trace_url"] == "https://smith.langchain.com/public/run-123"


def test_extract_langsmith_run_metadata_from_dict():
    metadata = tracer.extract_langsmith_run_metadata(
        {
            "run_id": "run-abc",
            "trace_url": "https://smith.langchain.com/public/run-abc",
        }
    )
    assert metadata["langsmith_run_id"] == "run-abc"
    assert metadata["langsmith_trace_url"] == "https://smith.langchain.com/public/run-abc"
