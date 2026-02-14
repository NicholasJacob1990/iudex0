"""
Document viewer service for Corpus source navigation.

Hybrid strategy:
- PDF: native frontend viewer consumes /content.
- Office/OpenOffice: backend-generated HTML preview (rag-document-viewer when available).
"""

from __future__ import annotations

import html
import importlib
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

from loguru import logger

from app.core.config import settings
from app.models.document import Document

PDF_EXTENSIONS = {".pdf"}
OFFICE_EXTENSIONS = {
    ".doc",
    ".docx",
    ".odt",
    ".ppt",
    ".pptx",
    ".xls",
    ".xlsx",
    ".ods",
    ".odp",
}


class DocumentViewerService:
    """Resolves and generates viewer assets for corpus documents."""

    def __init__(self) -> None:
        self.preview_root = Path(settings.LOCAL_STORAGE_PATH).expanduser() / "viewer_previews"
        self.preview_root.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def resolve_viewer_kind(
        self,
        *,
        document: Document,
        local_path: Optional[str],
    ) -> str:
        ext = self._detect_extension(document=document, local_path=local_path)

        if local_path and ext in PDF_EXTENSIONS:
            return "pdf_native"
        if local_path and ext in OFFICE_EXTENSIONS:
            return "office_html"
        if self._resolve_external_url(document):
            return "external"
        return "unavailable"

    def build_source_data(
        self,
        *,
        document: Document,
        local_path: Optional[str],
    ) -> Dict[str, Any]:
        """Build normalized source payload used by /source and /viewer-manifest."""
        viewer_kind = self.resolve_viewer_kind(document=document, local_path=local_path)
        viewer_meta = self._get_viewer_meta(document)

        download_url = (
            f"/api/corpus/documents/{document.id}/content?download=true" if local_path else None
        )
        content_url = f"/api/corpus/documents/{document.id}/content" if local_path else None
        external_url = self._resolve_external_url(document)
        source_url = content_url or external_url

        preview_status = self._resolve_preview_status(
            viewer_kind=viewer_kind,
            local_path=local_path,
            viewer_meta=viewer_meta,
        )

        viewer_url: Optional[str]
        if viewer_kind == "pdf_native":
            viewer_url = content_url
        elif viewer_kind == "office_html":
            viewer_url = (
                f"/api/corpus/documents/{document.id}/preview"
                if preview_status == "ready"
                else None
            )
        elif viewer_kind == "external":
            viewer_url = external_url
        else:
            viewer_url = None

        page_count = self._extract_page_count(document)

        supports_page_jump = viewer_kind in {"pdf_native", "office_html"}
        supports_highlight = viewer_kind in {"pdf_native", "office_html"}

        return {
            "viewer_kind": viewer_kind,
            "preview_status": preview_status,
            "page_count": page_count,
            "viewer_url": viewer_url,
            "download_url": download_url,
            "source_url": source_url,
            "supports_page_jump": supports_page_jump,
            "supports_highlight": supports_highlight,
        }

    def get_preview_file_path(self, document: Document) -> Optional[str]:
        viewer_meta = self._get_viewer_meta(document)
        preview_path = str(viewer_meta.get("preview_path") or "").strip()
        if not preview_path:
            return None
        resolved = os.path.abspath(os.path.expanduser(preview_path))
        if os.path.isfile(resolved):
            return resolved
        return None

    def generate_office_preview(
        self,
        *,
        document: Document,
        local_path: str,
        extracted_text: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate preview HTML for office/openoffice files.

        Returns a viewer metadata payload to store in document.doc_metadata["viewer"].
        """
        viewer_kind = self.resolve_viewer_kind(document=document, local_path=local_path)
        now_iso = self._utcnow_iso()

        if viewer_kind != "office_html":
            return {
                "status": "not_supported",
                "kind": viewer_kind,
                "generated_at": now_iso,
                "error": None,
            }

        output_path = str((self.preview_root / f"{document.id}.html").resolve())

        existing_meta = self._get_viewer_meta(document)
        if existing_meta.get("status") == "ready" and os.path.isfile(output_path):
            return {
                "status": "ready",
                "kind": "office_html",
                "generated_at": str(existing_meta.get("generated_at") or now_iso),
                "preview_path": output_path,
                "engine": str(existing_meta.get("engine") or "cached"),
                "error": None,
            }

        engine = "rag-document-viewer"
        try:
            generated = self._try_generate_with_rag_document_viewer(
                input_path=local_path,
                output_path=output_path,
            )
            if not generated:
                engine = "fallback_html"
                self._write_fallback_preview_html(
                    output_path=output_path,
                    document=document,
                    extracted_text=extracted_text,
                )
            return {
                "status": "ready",
                "kind": "office_html",
                "generated_at": now_iso,
                "preview_path": output_path,
                "engine": engine,
                "error": None,
            }
        except Exception as exc:
            logger.warning(f"Falha ao gerar preview office {document.id}: {exc}")
            return {
                "status": "failed",
                "kind": "office_html",
                "generated_at": now_iso,
                "preview_path": output_path,
                "engine": engine,
                "error": str(exc),
            }

    # ------------------------------------------------------------------
    # Generation internals
    # ------------------------------------------------------------------

    def _try_generate_with_rag_document_viewer(self, *, input_path: str, output_path: str) -> bool:
        """
        Best-effort integration with rag-document-viewer.

        Accepts multiple APIs/CLIs to keep compatibility across package versions.
        """
        if not bool(getattr(settings, "RAG_VIEWER_OFFICE_PREVIEW_ENABLED", True)):
            return False

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        # Try Python API first.
        try:
            module = importlib.import_module("rag_document_viewer")
            for fn_name in (
                "generate_preview",
                "generate_html_preview",
                "convert_to_html",
                "render_preview",
            ):
                fn = getattr(module, fn_name, None)
                if not callable(fn):
                    continue
                for kwargs in (
                    {"input_path": input_path, "output_path": output_path},
                    {"input_file": input_path, "output_file": output_path},
                    {"source": input_path, "target": output_path},
                ):
                    try:
                        result = fn(**kwargs)
                        if os.path.isfile(output_path):
                            return True
                        if isinstance(result, str) and os.path.isfile(result):
                            shutil.copyfile(result, output_path)
                            return True
                    except TypeError:
                        continue
                    except Exception:
                        continue
        except Exception:
            pass

        # Try CLI fallback.
        for bin_name in ("rag-document-viewer", "rag_document_viewer"):
            executable = shutil.which(bin_name)
            if not executable:
                continue

            commands = [
                [executable, "--input", input_path, "--output", output_path],
                [executable, "render", "--input", input_path, "--output", output_path],
                [executable, input_path, output_path],
            ]
            for cmd in commands:
                try:
                    proc = subprocess.run(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        timeout=120,
                    )
                    if proc.returncode == 0 and os.path.isfile(output_path):
                        return True
                except Exception:
                    continue

        return False

    def _write_fallback_preview_html(
        self,
        *,
        output_path: str,
        document: Document,
        extracted_text: Optional[str],
    ) -> None:
        text = str(extracted_text or "").strip()
        if not text:
            text = (
                "Preview avançado indisponível para este arquivo neste ambiente. "
                "Use o botão de download para abrir no aplicativo nativo."
            )

        escaped_title = html.escape(document.original_name or document.name or document.id)
        escaped_text = html.escape(text[:400000])
        html_content = f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Preview - {escaped_title}</title>
  <style>
    :root {{ color-scheme: light; }}
    body {{ margin:0; font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif; background:#fafafa; color:#111827; }}
    .shell {{ max-width: 980px; margin: 0 auto; padding: 24px; }}
    .card {{ border:1px solid #e5e7eb; background:#ffffff; border-radius:12px; overflow:hidden; }}
    .header {{ padding:12px 16px; border-bottom:1px solid #e5e7eb; font-size:13px; color:#374151; }}
    .body {{ padding:16px; white-space:pre-wrap; line-height:1.55; font-size:14px; }}
    mark[data-hit="1"] {{ background:#fde68a; color:#111827; padding:0 2px; border-radius:3px; }}
  </style>
</head>
<body>
  <div class="shell">
    <div class="card">
      <div class="header">{escaped_title}</div>
      <div id="content" class="body">{escaped_text}</div>
    </div>
  </div>
  <script>
    (function () {{
      const params = new URLSearchParams(window.location.search);
      const q = (params.get("q") || "").trim();
      if (!q) return;
      const root = document.getElementById("content");
      if (!root) return;
      const plain = root.textContent || "";
      const idx = plain.toLowerCase().indexOf(q.toLowerCase());
      if (idx < 0) return;
      const before = plain.slice(0, idx);
      const hit = plain.slice(idx, idx + q.length);
      const after = plain.slice(idx + q.length);
      root.innerHTML = "";
      root.append(document.createTextNode(before));
      const mark = document.createElement("mark");
      mark.setAttribute("data-hit", "1");
      mark.textContent = hit;
      root.append(mark);
      root.append(document.createTextNode(after));
      setTimeout(function () {{
        mark.scrollIntoView({{ behavior: "smooth", block: "center" }});
      }}, 30);
    }})();
  </script>
</body>
</html>
"""
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(html_content, encoding="utf-8")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_preview_status(
        self,
        *,
        viewer_kind: str,
        local_path: Optional[str],
        viewer_meta: Dict[str, Any],
    ) -> str:
        if viewer_kind == "office_html":
            status = str(viewer_meta.get("status") or "").strip().lower()
            if status in {"ready", "processing", "failed", "not_supported"}:
                if status == "ready":
                    preview_path = str(viewer_meta.get("preview_path") or "").strip()
                    if preview_path and os.path.isfile(os.path.abspath(os.path.expanduser(preview_path))):
                        return "ready"
                    return "failed"
                return status
            return "processing" if local_path else "failed"
        if viewer_kind in {"pdf_native", "external"}:
            return "ready"
        return "not_supported"

    def _extract_page_count(self, document: Document) -> Optional[int]:
        metadata = document.doc_metadata if isinstance(document.doc_metadata, dict) else {}
        for key in ("pages", "page_count", "num_pages"):
            raw = metadata.get(key)
            if raw is None:
                continue
            try:
                value = int(str(raw).strip())
            except Exception:
                continue
            if value > 0:
                return value
        return None

    def _get_viewer_meta(self, document: Document) -> Dict[str, Any]:
        metadata = document.doc_metadata if isinstance(document.doc_metadata, dict) else {}
        viewer = metadata.get("viewer")
        return viewer if isinstance(viewer, dict) else {}

    def _detect_extension(self, *, document: Document, local_path: Optional[str]) -> str:
        for raw in (
            document.original_name,
            document.name,
            os.path.basename(local_path) if local_path else None,
        ):
            text = str(raw or "").strip()
            if not text:
                continue
            _, ext = os.path.splitext(text)
            if ext:
                return ext.lower()
        return ""

    def _resolve_external_url(self, document: Document) -> Optional[str]:
        metadata = document.doc_metadata if isinstance(document.doc_metadata, dict) else {}
        candidates = [
            document.url,
            metadata.get("source_url"),
            metadata.get("external_url"),
        ]
        for candidate in candidates:
            url = str(candidate or "").strip()
            if url.startswith(("http://", "https://")):
                return url
        return None

    @staticmethod
    def _utcnow_iso() -> str:
        from app.core.time_utils import utcnow

        return utcnow().isoformat()
