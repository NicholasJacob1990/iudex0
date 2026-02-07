from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple, Any, Optional, Callable
from datetime import datetime
import re
import os

from app.services.ai.citations.style_registry import (
    default_heading_for_style,
    normalize_citation_style,
)
from app.services.ai.citations.forense_br_formatter import format_forense_br_reference
from app.services.ai.citations.bluebook_formatter import format_bluebook_reference
from app.services.ai.citations.apa_formatter import format_apa_reference
from app.services.ai.citations.chicago_formatter import format_chicago_reference
from app.services.ai.citations.harvard_formatter import format_harvard_reference
from app.services.ai.citations.oscola_formatter import format_oscola_reference
from app.services.ai.citations.ecli_formatter import format_ecli_reference
from app.services.ai.citations.vancouver_formatter import format_vancouver_reference
from app.services.ai.citations.inline_formatter import format_inline_reference
from app.services.ai.citations.numeric_formatter import format_numeric_reference
from app.services.ai.citations.alwd_formatter import format_alwd_reference


@dataclass(frozen=True)
class Source:
    n: int
    title: str
    url: str
    page_number: Optional[int] = None
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    source_file: Optional[str] = None
    doc_id: Optional[str] = None
    chunk_uid: Optional[str] = None
    chunk_index: Optional[int] = None
    source_page: Optional[int] = None
    highlight_text: Optional[str] = None
    viewer_url: Optional[str] = None
    download_url: Optional[str] = None
    source_url: Optional[str] = None
    viewer_kind: Optional[str] = None


def stable_numbering(items: Iterable[Tuple[str, str]]) -> Tuple[Dict[str, int], List[Source]]:
    """
    items: iterable of (url, title) in first-appearance order
    """
    url_to_n: Dict[str, int] = {}
    sources: List[Source] = []
    for url, title in items:
        if not url:
            continue
        if url not in url_to_n:
            url_to_n[url] = len(url_to_n) + 1
            sources.append(Source(n=url_to_n[url], title=title or url, url=url))
    return url_to_n, sources


def render_perplexity(text: str, sources: List[Source]) -> str:
    footer = "\n\nFontes:\n" + "\n".join(
        [f"[{s.n}] {s.title} — {s.url}" for s in sources]
    )
    return (text or "").rstrip() + footer


def sources_to_citations(sources: List[Source]) -> List[dict]:
    citations: List[dict] = []
    for s in sources or []:
        normalized_page = (
            s.page_number
            if s.page_number is not None
            else (s.source_page if s.source_page is not None else None)
        )
        normalized_source_url = s.source_url or s.url
        citation: dict = {
            "number": s.n,
            "title": s.title,
            "url": s.url or normalized_source_url,
        }
        if normalized_page is not None:
            citation["source_page"] = normalized_page
        if s.highlight_text:
            citation["highlight_text"] = s.highlight_text
            citation["quote"] = s.highlight_text
        # Incluir proveniência se disponível
        if (
            normalized_page is not None
            or s.source_file
            or s.doc_id
            or s.chunk_uid
            or s.chunk_index is not None
        ):
            citation["provenance"] = {
                "doc_id": s.doc_id,
                "chunk_uid": s.chunk_uid,
                "chunk_index": s.chunk_index,
                "page_number": normalized_page,
                "line_start": s.line_start,
                "line_end": s.line_end,
                "source_file": s.source_file,
            }
        if any([s.viewer_url, s.download_url, normalized_source_url, s.viewer_kind, normalized_page, s.highlight_text]):
            citation["viewer"] = {
                "viewer_url": s.viewer_url,
                "download_url": s.download_url,
                "source_url": normalized_source_url,
                "source_page": normalized_page,
                "highlight_text": s.highlight_text,
                "viewer_kind": s.viewer_kind,
            }
        citations.append(citation)
    return citations


def _clean_str(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    return text or None


def _as_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        parsed = int(str(value).strip())
    except Exception:
        return None
    return parsed if parsed > 0 else None


def _as_int_allow_zero(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        parsed = int(str(value).strip())
    except Exception:
        return None
    return parsed if parsed >= 0 else None


def normalize_citation_item(item: Dict[str, Any], *, default_number: Optional[int] = None) -> Dict[str, Any]:
    """
    Normaliza citação para contrato rico (compatível com legado).
    """
    raw = item if isinstance(item, dict) else {}
    provenance_in = raw.get("provenance") if isinstance(raw.get("provenance"), dict) else {}
    viewer_in = raw.get("viewer") if isinstance(raw.get("viewer"), dict) else {}

    number = _clean_str(raw.get("number") or raw.get("n") or raw.get("id"))
    if number is None and default_number is not None:
        number = str(default_number)

    page_number = (
        _as_int(provenance_in.get("page_number"))
        or _as_int(raw.get("page_number"))
        or _as_int(raw.get("source_page"))
        or _as_int(viewer_in.get("source_page"))
    )
    line_start = _as_int(provenance_in.get("line_start") or raw.get("line_start"))
    line_end = _as_int(provenance_in.get("line_end") or raw.get("line_end"))
    chunk_index = _as_int_allow_zero(provenance_in.get("chunk_index") or raw.get("chunk_index"))

    source_file = _clean_str(provenance_in.get("source_file") or raw.get("source_file"))
    doc_id = _clean_str(
        provenance_in.get("doc_id")
        or raw.get("doc_id")
        or raw.get("document_id")
    )
    chunk_uid = _clean_str(provenance_in.get("chunk_uid") or raw.get("chunk_uid"))

    highlight_text = _clean_str(
        raw.get("highlight_text")
        or viewer_in.get("highlight_text")
        or raw.get("quote")
        or raw.get("excerpt")
        or raw.get("snippet")
    )

    source_url = _clean_str(
        viewer_in.get("source_url")
        or raw.get("source_url")
        or raw.get("url")
    )
    viewer_url = _clean_str(viewer_in.get("viewer_url") or raw.get("viewer_url"))
    download_url = _clean_str(viewer_in.get("download_url") or raw.get("download_url"))
    viewer_kind = _clean_str(viewer_in.get("viewer_kind") or raw.get("viewer_kind"))

    citation: Dict[str, Any] = {}
    if number is not None:
        citation["number"] = number
    if _clean_str(raw.get("title")):
        citation["title"] = _clean_str(raw.get("title"))
    if source_url is not None:
        citation["url"] = source_url
    if highlight_text is not None:
        citation["quote"] = highlight_text
        citation["highlight_text"] = highlight_text
    if page_number is not None:
        citation["source_page"] = page_number

    provenance: Dict[str, Any] = {}
    if doc_id is not None:
        provenance["doc_id"] = doc_id
    if chunk_uid is not None:
        provenance["chunk_uid"] = chunk_uid
    if chunk_index is not None:
        provenance["chunk_index"] = chunk_index
    if page_number is not None:
        provenance["page_number"] = page_number
    if line_start is not None:
        provenance["line_start"] = line_start
    if line_end is not None:
        provenance["line_end"] = line_end
    if source_file is not None:
        provenance["source_file"] = source_file
    if provenance:
        citation["provenance"] = provenance

    viewer: Dict[str, Any] = {}
    if viewer_url is not None:
        viewer["viewer_url"] = viewer_url
    if download_url is not None:
        viewer["download_url"] = download_url
    if source_url is not None:
        viewer["source_url"] = source_url
    if page_number is not None:
        viewer["source_page"] = page_number
    if highlight_text is not None:
        viewer["highlight_text"] = highlight_text
    if viewer_kind is not None:
        viewer["viewer_kind"] = viewer_kind
    if viewer:
        citation["viewer"] = viewer

    # Preserve additional keys not covered above (backward compat with existing payloads).
    for k, v in raw.items():
        if k in citation:
            continue
        if k in {"provenance", "viewer"}:
            continue
        citation[k] = v

    return citation


def citation_merge_key(item: Dict[str, Any]) -> Optional[str]:
    """
    Chave estável de merge para evitar perda de citações.

    Prioridade:
    1. doc_id + chunk_index + page_number
    2. doc_id + chunk_uid + page_number
    3. url + page_number
    4. url
    5. number
    """
    if not isinstance(item, dict):
        return None
    provenance = item.get("provenance") if isinstance(item.get("provenance"), dict) else {}
    viewer = item.get("viewer") if isinstance(item.get("viewer"), dict) else {}

    doc_id = _clean_str(provenance.get("doc_id") or item.get("doc_id") or item.get("document_id"))
    chunk_index = _as_int_allow_zero(provenance.get("chunk_index") or item.get("chunk_index"))
    chunk_uid = _clean_str(provenance.get("chunk_uid") or item.get("chunk_uid"))
    page_number = _as_int(
        provenance.get("page_number")
        or item.get("source_page")
        or item.get("page_number")
        or viewer.get("source_page")
    )
    url = _clean_str(viewer.get("source_url") or item.get("url") or item.get("source_url"))
    number = _clean_str(item.get("number"))

    if doc_id and chunk_index is not None:
        return f"doc:{doc_id}|chunk_index:{chunk_index}|page:{page_number or 0}"
    if doc_id and chunk_uid:
        return f"doc:{doc_id}|chunk_uid:{chunk_uid}|page:{page_number or 0}"
    if url and page_number is not None:
        return f"url:{url}|page:{page_number}"
    if url:
        return f"url:{url}"
    if number:
        return f"number:{number}"
    return None


def _pt_br_access_date(now: datetime | None = None) -> str:
    dt = now or datetime.now()
    meses = [
        "jan.", "fev.", "mar.", "abr.", "maio", "jun.",
        "jul.", "ago.", "set.", "out.", "nov.", "dez."
    ]
    mes = meses[max(0, min(11, dt.month - 1))]
    return f"{dt.day:02d} {mes} {dt.year}"


def format_reference_abnt(*, title: str, url: str, accessed_at: datetime | None = None) -> str:
    """
    ABNT-like (simplified) reference line for web sources.
    """
    t = (title or "").strip() or "Fonte"
    u = (url or "").strip()
    if not u:
        return f"{t}."
    acesso = _pt_br_access_date(accessed_at)
    # Mantém simples: Título + Disponível em + Acesso em
    return f"{t}. Disponível em: {u}. Acesso em: {acesso}."


def _parse_reference_number(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except Exception:
        return None


def format_reference(
    *,
    style: str | None,
    title: str,
    url: str,
    source: Optional[Dict[str, Any]] = None,
    number: int | None = None,
    accessed_at: datetime | None = None,
) -> str:
    """
    Formata referência conforme o estilo solicitado.
    Fallback seguro: ABNT simplificado.
    """
    normalized_style = normalize_citation_style(style, default="abnt")
    payload: Dict[str, Any] = dict(source or {})
    payload.setdefault("title", title)
    payload.setdefault("url", url)

    if number is None:
        number = _parse_reference_number(payload.get("number"))

    if normalized_style == "abnt":
        try:
            return format_abnt_full_reference(payload)
        except Exception:
            return format_reference_abnt(title=title, url=url, accessed_at=accessed_at)

    formatter_map: Dict[str, Callable[..., str]] = {
        "forense_br": format_forense_br_reference,
        "bluebook": format_bluebook_reference,
        "harvard": format_harvard_reference,
        "apa": format_apa_reference,
        "chicago": format_chicago_reference,
        "oscola": format_oscola_reference,
        "ecli": format_ecli_reference,
        "vancouver": format_vancouver_reference,
        "inline": format_inline_reference,
        "numeric": format_numeric_reference,
        "alwd": format_alwd_reference,
    }
    formatter = formatter_map.get(normalized_style)
    if formatter is None:
        return format_reference_abnt(title=title, url=url, accessed_at=accessed_at)

    try:
        return formatter(payload, accessed_at=accessed_at, number=number)
    except Exception:
        return format_reference_abnt(title=title, url=url, accessed_at=accessed_at)


def _clean_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _extract_digits(value: str) -> List[str]:
    return re.findall(r"\d{4,}", value or "")


def _safe_basename(path_or_url: str) -> str:
    try:
        return os.path.basename(str(path_or_url or ""))
    except Exception:
        return str(path_or_url or "")


def format_autos_reference_abnt(
    *,
    kind: str,
    doc_label: str,
    title: Optional[str] = None,
    orgao: Optional[str] = None,
    issued_at: Optional[str] = None,
    locator: Optional[str] = None,
) -> str:
    """
    ABNT-like (simplified) reference line for autos/anexos (no URL).
    """
    k = _clean_spaces(kind) or "AUTOS"
    d = _clean_spaces(doc_label) or "Documento"
    t = _clean_spaces(title) or d
    o = _clean_spaces(orgao)
    date = _clean_spaces(issued_at)
    loc = _clean_spaces(locator)

    parts: List[str] = []
    if o:
        parts.append(o + ".")
    parts.append(f"{t}.")
    # Identificador dos autos (ex.: Doc. SEI nº 12345, fls. 15, Cláusula 5.2)
    parts.append(f"{k}: {d}.")
    if date:
        parts.append(f"{date}.")
    if loc:
        parts.append(f"{loc}.")
    return " ".join(parts).replace("..", ".").strip()


def extract_autos_citations(text: str) -> Dict[str, Dict[str, Any]]:
    """
    Extract citations that refer to autos/anexos, e.g.:
      [LAUDO - Doc. SEI nº 12345, p. 3]
      [INICIAL - fls. 15]
      [CONTRATO - Cláusula 5.2]
    Returns a dict keyed by "<kind> - <doc_label>" with locator info.
    """
    body = str(text or "")
    if not body:
        return {}

    refs: Dict[str, Dict[str, Any]] = {}

    def upsert(kind: str, doc_label: str, *, pages: Optional[List[str]] = None, locator: Optional[str] = None):
        k = _clean_spaces(kind)
        d = _clean_spaces(doc_label)
        if not d:
            return
        key = f"{k} - {d}" if k else d
        entry = refs.get(key) or {"kind": k or "AUTOS", "doc_label": d, "pages": set(), "locators": set()}
        if pages:
            for p in pages:
                if p:
                    entry["pages"].add(str(p))
        if locator:
            entry["locators"].add(_clean_spaces(locator))
        refs[key] = entry

    # Pattern: [TIPO - Doc. X, p. Y]
    for m in re.finditer(r"\[([^\[\]\n]{2,80}?)\s*-\s*(Doc\.[^,\]\n]{2,120}?),\s*p\.?\s*(\d{1,5})\]", body, flags=re.IGNORECASE):
        kind = m.group(1)
        doc_label = m.group(2)
        page = m.group(3)
        upsert(kind, doc_label, pages=[page], locator=f"p. {page}")

    # Pattern: [TIPO - fls. 15] / [TIPO - fl. 15]
    for m in re.finditer(r"\[([^\[\]\n]{2,80}?)\s*-\s*(fls?\.?\s*\d{1,6})\]", body, flags=re.IGNORECASE):
        kind = m.group(1)
        loc = m.group(2)
        upsert(kind, loc, locator=loc)

    # Pattern: [TIPO - Cláusula 5.2] / [TIPO - item X]
    for m in re.finditer(r"\[([^\[\]\n]{2,80}?)\s*-\s*(Cl[aá]usula\s*[0-9][^\]\n]{0,40}|item\s*[0-9][^\]\n]{0,40}|art\.?\s*\d+[^\]\n]{0,40})\]", body, flags=re.IGNORECASE):
        kind = m.group(1)
        loc = m.group(2)
        upsert(kind, loc, locator=loc)

    return refs


def _pick_doc_metadata(doc: Any) -> Dict[str, Any]:
    meta = getattr(doc, "doc_metadata", None)
    return meta if isinstance(meta, dict) else {}


def _match_autos_ref_to_doc(doc_label: str, attachment_docs: Optional[List[Any]]) -> Optional[Any]:
    if not attachment_docs:
        return None
    label = _clean_spaces(doc_label).lower()
    if not label:
        return None

    label_digits = set(_extract_digits(label))

    best = None
    best_score = 0
    for doc in attachment_docs:
        try:
            name = _clean_spaces(getattr(doc, "name", "")).lower()
            original = _clean_spaces(getattr(doc, "original_name", "")).lower()
            doc_id = _clean_spaces(getattr(doc, "id", "")).lower()
            url = _clean_spaces(getattr(doc, "url", "")).lower()
            base = _safe_basename(url).lower()
            meta = _pick_doc_metadata(doc)
            meta_blob = _clean_spaces(str(meta)).lower()
        except Exception:
            continue

        score = 0
        # strong: id substring
        if doc_id and doc_id in label:
            score += 10
        # filename match
        if name and name in label:
            score += 6
        if original and original in label:
            score += 6
        if base and base in label:
            score += 4

        # digits overlap heuristic (SEI, números de documento, etc.)
        doc_digits = set(_extract_digits(" ".join([name, original, base, meta_blob])))
        if label_digits and doc_digits:
            overlap = len(label_digits.intersection(doc_digits))
            score += overlap * 3

        if score > best_score:
            best_score = score
            best = doc

    # only accept if it looks meaningful
    return best if best_score >= 6 else None


def append_autos_references_section(
    text: str,
    *,
    attachment_docs: Optional[List[Any]] = None,
    max_items: int = 40,
) -> str:
    """
    Append a separate section "Referências (Anexos/Autos)" using autos-style citations.
    Does not modify the body; only appends a list at the end.
    """
    body = (text or "").rstrip()
    if not body:
        return text

    # Avoid duplicating if already present.
    if re.search(r"(?im)^\s{0,3}#{1,6}\s+referências\s*\(anexos/autos\)\b", body):
        return text

    refs = extract_autos_citations(body)
    if not refs:
        return text

    items = list(refs.values())
    items = items[: max(1, min(int(max_items or 40), 200))]

    lines: List[str] = ["", "---", "", "## Referências (Anexos/Autos)"]
    for entry in items:
        kind = entry.get("kind") or "AUTOS"
        doc_label = entry.get("doc_label") or "Documento"
        pages = sorted(entry.get("pages") or set(), key=lambda x: int(x) if str(x).isdigit() else str(x))
        locators = sorted(entry.get("locators") or set())
        locator = ""
        if pages:
            locator = f"p. {', '.join(pages)}"
        if locators and not locator:
            locator = "; ".join(locators[:2])
        elif locators and locator:
            locator = f"{locator}; {locators[0]}"

        matched = _match_autos_ref_to_doc(str(doc_label), attachment_docs)
        title = None
        orgao = None
        issued_at = None
        if matched is not None:
            title = getattr(matched, "name", None) or getattr(matched, "original_name", None)
            meta = _pick_doc_metadata(matched)
            orgao = meta.get("orgao") or meta.get("órgão") or meta.get("tribunal") or meta.get("instituicao") or meta.get("instituição")
            issued_at = meta.get("data") or meta.get("date") or meta.get("issued_at") or meta.get("issuedAt")

        lines.append(format_autos_reference_abnt(
            kind=str(kind),
            doc_label=str(doc_label),
            title=str(title) if title else None,
            orgao=str(orgao) if orgao else None,
            issued_at=str(issued_at) if issued_at else None,
            locator=locator or None,
        ))

    return body + "\n" + "\n".join(lines).rstrip() + "\n"


def format_abnt_full_reference(source: Dict[str, Any]) -> str:
    """
    Format a source as a full ABNT reference using the classifier.
    Delegates to abnt_classifier for type-specific formatting.
    """
    try:
        from app.services.ai.citations.abnt_classifier import format_abnt_full
        return format_abnt_full(source)
    except ImportError:
        # Fallback to simplified format
        return format_reference_abnt(
            title=source.get("title", "Fonte"),
            url=source.get("url", ""),
        )


def build_abnt_references(
    sources: List[dict],
    heading: str = "REFERÊNCIAS BIBLIOGRÁFICAS",
) -> str:
    """
    Build a complete ABNT references section.
    Uses the classifier for type-specific formatting.
    """
    return build_references_section(sources, style="abnt", heading=heading)


def build_references_section(
    sources: List[dict],
    *,
    style: str | None,
    heading: Optional[str] = None,
) -> str:
    """
    Gera seção de referências no estilo solicitado.
    """
    if not sources:
        return ""

    normalized_style = normalize_citation_style(style, default="abnt")
    resolved_heading = heading or default_heading_for_style(normalized_style)
    lines = [f"\n---\n\n## {resolved_heading}\n"]
    for i, source in enumerate(sources, 1):
        n = _parse_reference_number(source.get("number")) or i
        t = str(source.get("title") or f"Fonte {n}")
        u = str(source.get("url") or "")
        lines.append(
            f"[{n}] {format_reference(style=normalized_style, title=t, url=u, source=source, number=n)}"
        )
    return "\n".join(lines) + "\n"


def append_references_section(
    text: str,
    citations: List[dict],
    *,
    heading: Optional[str] = None,
    style: str | None = None,
    max_sources: int = 20,
    include_all_if_uncited: bool = False,
) -> str:
    """
    Append a copy-friendly references section to the final text, filtered to cited [n].
    Works for Chat responses (citations list), where the model is instructed to cite inline with [n].
    """
    body = (text or "").rstrip()
    if not body:
        return text
    if not citations:
        return text

    # Avoid duplicating if the model already produced a sources/references section.
    import re
    if re.search(r"(?im)^\s{0,3}#{1,6}\s+(fontes|references|referências|referencias)\b", body):
        return text
    if re.search(r"(?im)^\s*(fontes|references|referências|referencias)\s*:\s*$", body):
        return text

    cited_numbers = {
        int(n)
        for n in re.findall(r"\[(\d{1,3})\]", body)
        if str(n).isdigit()
    }
    if not cited_numbers and not include_all_if_uncited:
        # Se o modelo não citou [n] no texto, não inventar – apenas não anexar.
        return text

    by_number: Dict[int, dict] = {}
    for item in citations or []:
        try:
            n = int(item.get("number"))
        except Exception:
            continue
        if n not in by_number:
            by_number[n] = item

    ordered_source = sorted(by_number.keys()) if include_all_if_uncited and not cited_numbers else sorted(cited_numbers)
    ordered = [n for n in ordered_source if n in by_number][: max(1, min(20, int(max_sources or 20)))]
    if not ordered:
        return text

    normalized_style = normalize_citation_style(style, default="abnt")
    resolved_heading = heading or default_heading_for_style(normalized_style)

    lines: List[str] = ["", "", f"{resolved_heading}:", ""]
    for n in ordered:
        item = by_number.get(n) or {}
        title = str(item.get("title") or f"Fonte {n}").strip()
        url = str(item.get("url") or "").strip()
        lines.append(
            f"[{n}] {format_reference(style=normalized_style, title=title, url=url, source=item, number=n)}"
        )

    return body + "\n" + "\n".join(lines).rstrip() + "\n"
