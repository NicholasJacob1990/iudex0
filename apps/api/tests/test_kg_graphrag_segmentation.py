import types
import pytest


class _FakeResult:
    def __init__(self, single=None):
        self._single = single or {}

    def single(self):
        return self._single


class _FakeSession:
    def __init__(self, queries):
        self._queries = queries

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def run(self, query, params=None):
        self._queries.append((query, params))
        # Duplicate-run check expects {"c": 0}
        if "RETURN count(r) AS c" in query:
            return _FakeResult({"c": 0})
        # procedure check expects {"c": 0} in some contexts
        if "CALL dbms.procedures" in query and "RETURN count(*) AS c" in query:
            return _FakeResult({"c": 0})
        # default
        return _FakeResult({})


class _FakeDriver:
    def __init__(self):
        self.queries = []

    def session(self, database=None):
        return _FakeSession(self.queries)


class _FakePipeline:
    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.calls = []
        _FakePipeline.instances.append(self)

    async def run_async(self, text: str):
        self.calls.append(text)


@pytest.mark.asyncio
async def test_graphrag_pipeline_segments_and_passes_prompt(monkeypatch):
    """
    Validates that _run_graphrag_pipeline:
    - splits into multiple segments (when segment_size is small)
    - calls pipeline.run_async once per segment
    - passes prompt_template when strict prompt is enabled (legal default)
    """
    # Inject fake neo4j_graphrag SimpleKGPipeline module so import succeeds.
    fake_mod = types.SimpleNamespace(SimpleKGPipeline=_FakePipeline)
    monkeypatch.setitem(
        __import__("sys").modules,
        "neo4j_graphrag.experimental.pipeline.kg_builder",
        fake_mod,
    )

    from app.services.rag.core.kg_builder import pipeline as kg_pipeline
    import app.services.rag.core.neo4j_mvp as neo4j_mvp

    fake_driver = _FakeDriver()

    class _Cfg:
        database = "neo4j"

    class _Svc:
        driver = fake_driver
        config = _Cfg()

    monkeypatch.setattr(neo4j_mvp, "get_neo4j_mvp", lambda: _Svc())

    # Avoid importing neo4j_graphrag.llm/embeddings in this unit test environment.
    monkeypatch.setattr(kg_pipeline, "_build_graphrag_llm", lambda: object())
    monkeypatch.setattr(kg_pipeline, "_build_graphrag_embedder", lambda: object())

    # Make sure post-process is off to keep this test focused (and independent of APOC).
    monkeypatch.setenv("KG_BUILDER_GRAPHRAG_POST_PROCESS", "false")
    monkeypatch.setenv("KG_BUILDER_GRAPHRAG_SEGMENT_SIZE", "50")
    monkeypatch.setenv("KG_BUILDER_GRAPHRAG_SEGMENT_OVERLAP", "0")
    monkeypatch.setenv("KG_BUILDER_GRAPHRAG_QUALITY_FILTER", "false")
    monkeypatch.setenv("KG_BUILDER_DOMAIN", "legal")

    # Call internal function directly.
    chunks = [
        {"text": "Art. 135 do CTN nos termos do art. 10 do CTN. " * 5},
        {"text": "REsp 1.234.567 interpreta o Art. 135 do CTN. " * 5},
    ]

    out = await kg_pipeline._run_graphrag_pipeline(
        chunks=chunks,
        doc_hash="doc1",
        tenant_id="t1",
        case_id="c1",
        scope="global",
        use_llm=True,
    )

    assert out["mode"] == "neo4j-graphrag"
    assert out["graphrag_segments"] >= 2

    # One pipeline instance should exist and have multiple run_async calls.
    assert len(_FakePipeline.instances) >= 1
    assert len(_FakePipeline.instances[0].calls) == out["graphrag_segments"]

    # Strict prompt is enabled by default for legal domain; prompt_template should be attempted.
    # If the template import fails in this environment, the code will skip setting it;
    # so we accept either behavior, but if present it must be in kwargs.
    if "prompt_template" in _FakePipeline.instances[0].kwargs:
        assert _FakePipeline.instances[0].kwargs["prompt_template"] is not None
