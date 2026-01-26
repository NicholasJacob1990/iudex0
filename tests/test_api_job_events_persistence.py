import json
import os
import sys
from pathlib import Path


def _ensure_api_on_path():
    repo_root = Path(__file__).resolve().parents[1]
    api_root = repo_root / "apps" / "api"
    sys.path.insert(0, str(api_root))


def test_api_job_events_persisted_and_replayable(tmp_path, monkeypatch):
    _ensure_api_on_path()

    from app.core.config import settings
    from app.services.job_manager import JobManager

    monkeypatch.setattr(settings, "LOCAL_STORAGE_PATH", str(tmp_path))
    monkeypatch.setenv("JOB_EVENT_PERSIST", "true")

    jm = JobManager(db_path="jobs_test.db")
    job_id = "job-test-1"

    ev_id = jm.emit_event(job_id, "test_event", {"a": 1}, phase="research", node="planner")
    assert isinstance(ev_id, int) and ev_id > 0

    events = jm.list_events(job_id, after_id=0)
    assert len(events) >= 1
    assert events[0]["id"] == ev_id
    assert events[0]["type"] == "test_event"
    assert events[0]["channel"] == "research"
    assert events[0]["data"]["a"] == 1

    # New instance should still replay from DB.
    jm2 = JobManager(db_path="jobs_test.db")
    replay = jm2.list_events(job_id, after_id=0)
    assert any(e.get("id") == ev_id and e.get("data", {}).get("a") == 1 for e in replay)


def test_api_job_events_large_payload_is_spilled_to_file(tmp_path, monkeypatch):
    _ensure_api_on_path()

    from app.core.config import settings
    from app.services.job_manager import JobManager

    monkeypatch.setattr(settings, "LOCAL_STORAGE_PATH", str(tmp_path))
    monkeypatch.setenv("JOB_EVENT_PERSIST", "true")
    monkeypatch.setenv("JOB_EVENT_MAX_BYTES", "200")

    jm = JobManager(db_path="jobs_test.db")
    job_id = "job-test-2"

    base_id = jm.emit_event(job_id, "base", {"ok": True}, phase="audit", node="audit")
    assert base_id

    big_id = jm.emit_event(
        job_id,
        "big",
        {"text": "x" * 10000},
        phase="audit",
        node="audit",
    )
    assert big_id and big_id > base_id

    events = jm.list_events(job_id, after_id=base_id)
    assert len(events) >= 1
    big = events[0]
    assert big["id"] == big_id
    assert "_ref" in big["data"]

    ref = Path(big["data"]["_ref"])
    assert ref.exists()
    stored = json.loads(ref.read_text(encoding="utf-8"))
    assert stored["text"].startswith("x" * 100)


def test_api_job_events_clear_removes_db_rows(tmp_path, monkeypatch):
    _ensure_api_on_path()

    from app.core.config import settings
    from app.services.job_manager import JobManager

    monkeypatch.setattr(settings, "LOCAL_STORAGE_PATH", str(tmp_path))
    monkeypatch.setenv("JOB_EVENT_PERSIST", "true")

    jm = JobManager(db_path="jobs_test.db")
    job_id = "job-test-3"

    jm.emit_event(job_id, "one", {"n": 1})
    assert jm.list_events(job_id, after_id=0)

    jm.clear_events(job_id)
    assert jm.list_events(job_id, after_id=0) == []

