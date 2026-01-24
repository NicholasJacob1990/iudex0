from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Dict, Iterable, Tuple

from loguru import logger

DEFAULT_MAX_STATE_CHARS = 20000
DEFAULT_PREVIEW_CHARS = 3000
DEFAULT_TTL_DAYS = 14


def _safe_slug(value: str, fallback: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", (value or "").strip()).strip("_").lower()
    return slug or fallback


def _get_storage_root() -> Path:
    try:
        from app.core.config import settings
        base_dir = Path(settings.LOCAL_STORAGE_PATH)
    except Exception:
        base_dir = Path("./storage")
    root = base_dir / "workflow_documents"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _iter_document_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        if path.is_file():
            yield path


def _read_int_env(name: str, default: Optional[int] = None) -> Optional[int]:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def persist_full_document(text: str, job_id: str) -> Optional[str]:
    if not text:
        return None
    job_slug = _safe_slug(job_id or "job", "job")
    path = _get_storage_root() / f"{job_slug}.md"
    try:
        path.write_text(text, encoding="utf-8")
        return str(path)
    except Exception as exc:
        logger.warning(f"Could not persist full_document: {exc}")
        return None


def load_full_document(path: Optional[str]) -> str:
    if not path:
        return ""
    try:
        return Path(path).read_text(encoding="utf-8")
    except Exception as exc:
        logger.warning(f"Could not load full_document from {path}: {exc}")
        return ""


def resolve_full_document(state: Mapping[str, Any]) -> str:
    text = state.get("full_document") or ""
    if text:
        return text
    ref = state.get("full_document_ref")
    loaded = load_full_document(ref)
    if loaded:
        return loaded
    return state.get("full_document_preview") or ""


def store_full_document_state(
    state: Mapping[str, Any],
    text: str,
    *,
    preview_chars: int = DEFAULT_PREVIEW_CHARS,
    max_state_chars: Optional[int] = None,
) -> Dict[str, Any]:
    if max_state_chars is None:
        try:
            max_state_chars = int(os.getenv("MAX_FULL_DOCUMENT_STATE_CHARS", DEFAULT_MAX_STATE_CHARS))
        except Exception:
            max_state_chars = DEFAULT_MAX_STATE_CHARS

    job_id = state.get("job_id") or "langgraph-job"
    ref = persist_full_document(text, job_id)
    preview = text[:preview_chars] if text else ""

    updated = {
        **state,
        "full_document_ref": ref,
        "full_document_preview": preview,
        "full_document_chars": len(text or ""),
    }

    # Keep full_document in state only when small or persistence failed.
    if not text:
        updated["full_document"] = ""
    elif ref and len(text) > max_state_chars:
        updated["full_document"] = ""
    else:
        updated["full_document"] = text

    return updated


def cleanup_workflow_documents(
    ttl_days: Optional[int] = None,
    max_bytes: Optional[int] = None,
) -> Dict[str, int]:
    if ttl_days is None:
        ttl_days = _read_int_env("WORKFLOW_DOC_TTL_DAYS", DEFAULT_TTL_DAYS)
    if max_bytes is None:
        max_bytes = _read_int_env("WORKFLOW_DOC_MAX_BYTES", 0)

    if ttl_days is not None and ttl_days <= 0:
        ttl_days = None
    if max_bytes is not None and max_bytes <= 0:
        max_bytes = None

    root = _get_storage_root()
    now = datetime.now(timezone.utc).timestamp()

    removed = 0
    removed_bytes = 0

    files: list[Tuple[Path, float, int]] = []
    for path in _iter_document_files(root):
        try:
            stat = path.stat()
        except OSError:
            continue
        files.append((path, stat.st_mtime, stat.st_size))

    if ttl_days is not None:
        cutoff = now - (ttl_days * 86400)
        remaining: list[Tuple[Path, float, int]] = []
        for path, mtime, size in files:
            if mtime < cutoff:
                try:
                    path.unlink(missing_ok=True)
                    removed += 1
                    removed_bytes += size
                except OSError:
                    remaining.append((path, mtime, size))
            else:
                remaining.append((path, mtime, size))
        files = remaining

    if max_bytes is not None:
        files.sort(key=lambda item: item[1])
        total_bytes = sum(size for _, _, size in files)
        while files and total_bytes > max_bytes:
            path, mtime, size = files.pop(0)
            try:
                path.unlink(missing_ok=True)
                removed += 1
                removed_bytes += size
                total_bytes -= size
            except OSError:
                continue

    remaining_bytes = 0
    remaining_count = 0
    for path in _iter_document_files(root):
        try:
            stat = path.stat()
        except OSError:
            continue
        remaining_count += 1
        remaining_bytes += stat.st_size

    result = {
        "removed": removed,
        "removed_bytes": removed_bytes,
        "remaining": remaining_count,
        "remaining_bytes": remaining_bytes,
    }
    if removed:
        logger.info("Workflow document cleanup: %s", result)
    return result
