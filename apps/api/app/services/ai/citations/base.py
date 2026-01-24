from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple, Any, Optional
from datetime import datetime
import re
import os


@dataclass(frozen=True)
class Source:
    n: int
    title: str
    url: str


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
        citations.append({
            "number": s.n,
            "title": s.title,
            "url": s.url,
        })
    return citations


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


def append_references_section(
    text: str,
    citations: List[dict],
    *,
    heading: str = "References",
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

    lines: List[str] = ["", "", f"{heading}:", ""]
    for n in ordered:
        item = by_number.get(n) or {}
        title = str(item.get("title") or f"Fonte {n}").strip()
        url = str(item.get("url") or "").strip()
        lines.append(f"[{n}] {format_reference_abnt(title=title, url=url)}")

    return body + "\n" + "\n".join(lines).rstrip() + "\n"
