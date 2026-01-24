import os
import time
from pathlib import Path

from app.core.config import settings
from app.services.ai import document_store


def _set_storage_root(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "LOCAL_STORAGE_PATH", str(tmp_path))
    return document_store._get_storage_root()


def test_persist_and_load_full_document(tmp_path, monkeypatch):
    _set_storage_root(tmp_path, monkeypatch)
    path = document_store.persist_full_document("conteudo", "job-1")
    assert path is not None
    assert Path(path).exists()
    assert document_store.load_full_document(path) == "conteudo"


def test_store_full_document_state_large_clears_full_document(tmp_path, monkeypatch):
    _set_storage_root(tmp_path, monkeypatch)
    state = {"job_id": "job-1"}
    text = "x" * 50
    updated = document_store.store_full_document_state(
        state,
        text,
        preview_chars=5,
        max_state_chars=10,
    )
    assert updated["full_document"] == ""
    assert updated["full_document_ref"]
    assert updated["full_document_preview"] == "x" * 5


def test_resolve_full_document_prefers_inline(tmp_path, monkeypatch):
    root = _set_storage_root(tmp_path, monkeypatch)
    inline_state = {"full_document": "inline"}
    assert document_store.resolve_full_document(inline_state) == "inline"

    path = root / "job-2.md"
    path.write_text("arquivo", encoding="utf-8")
    ref_state = {"full_document": "", "full_document_ref": str(path)}
    assert document_store.resolve_full_document(ref_state) == "arquivo"


def test_cleanup_workflow_documents_ttl(tmp_path, monkeypatch):
    root = _set_storage_root(tmp_path, monkeypatch)
    old_file = root / "old.md"
    new_file = root / "new.md"
    old_file.write_text("old", encoding="utf-8")
    new_file.write_text("new", encoding="utf-8")

    old_time = time.time() - (2 * 86400)
    os.utime(old_file, (old_time, old_time))

    result = document_store.cleanup_workflow_documents(ttl_days=1, max_bytes=None)
    assert result["removed"] >= 1
    assert not old_file.exists()
    assert new_file.exists()


def test_cleanup_workflow_documents_size(tmp_path, monkeypatch):
    root = _set_storage_root(tmp_path, monkeypatch)
    oldest = root / "oldest.md"
    middle = root / "middle.md"
    newest = root / "newest.md"

    oldest.write_text("a" * 10, encoding="utf-8")
    middle.write_text("b" * 10, encoding="utf-8")
    newest.write_text("c" * 3, encoding="utf-8")

    now = time.time()
    os.utime(oldest, (now - 300, now - 300))
    os.utime(middle, (now - 200, now - 200))
    os.utime(newest, (now - 100, now - 100))

    result = document_store.cleanup_workflow_documents(ttl_days=None, max_bytes=10)
    assert result["remaining_bytes"] <= 10
    assert not oldest.exists()
    assert not middle.exists()
    assert newest.exists()
