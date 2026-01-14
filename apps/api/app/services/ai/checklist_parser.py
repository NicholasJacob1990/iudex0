from typing import List, Dict, Any, Optional
import re


def _normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (value or "").lower()).strip("_")


def _detect_critical_heading(text: str) -> Optional[bool]:
    lowered = text.lower().strip()
    if re.search(r"\bn[a\u00e3]o\s+cr[i\u00ed]tico", lowered):
        return False
    if re.search(r"\bnon\s*critical\b", lowered):
        return False
    if re.search(r"\bcr[i\u00ed]tico", lowered):
        return True
    return None


def _strip_item_prefix(text: str) -> str:
    cleaned = re.sub(r"^[-*•]\s*", "", text)
    cleaned = re.sub(r"^\d+[\.)]\s*", "", cleaned)
    return cleaned.strip()


def _split_inline_items(text: str) -> List[str]:
    if ";" in text:
        parts = text.split(";")
    elif "," in text:
        parts = text.split(",")
    else:
        parts = [text]
    return [part.strip() for part in parts if part.strip()]


def parse_document_checklist_from_prompt(prompt: str) -> List[Dict[str, Any]]:
    if not prompt:
        return []

    lines = prompt.splitlines()
    items: List[Dict[str, Any]] = []
    in_block = False
    current_critical: Optional[bool] = None

    for raw_line in lines:
        raw = raw_line.strip()
        if not in_block:
            if not raw:
                continue
            lowered = raw.lower()
            if "checklist" in lowered and (
                "complementar" in lowered
                or "document" in lowered
                or lowered.endswith(":")
                or lowered == "checklist"
                or lowered.startswith("[checklist")
            ):
                in_block = True
                current_critical = _detect_critical_heading(raw)
                if ":" in raw:
                    remainder = raw.split(":", 1)[1].strip()
                    for label in _split_inline_items(remainder):
                        items.append({"label": label, "critical": bool(current_critical)})
                continue
            continue

        if not raw:
            continue
        cleaned_heading = raw.lstrip("#").strip()
        if re.match(r"^fim\s+do\s+checklist", cleaned_heading.lower()) or re.match(r"^fim\s+checklist", cleaned_heading.lower()):
            break

        heading_critical = _detect_critical_heading(cleaned_heading)
        if heading_critical is not None:
            current_critical = heading_critical
            if ":" in cleaned_heading:
                remainder = cleaned_heading.split(":", 1)[1].strip()
                for label in _split_inline_items(remainder):
                    items.append({"label": label, "critical": bool(current_critical)})
            continue

        if re.match(r"^#{1,6}\s", raw) or re.match(r"^---+$", raw) or re.match(r"^```", raw):
            break

        label = _strip_item_prefix(raw)
        if not label:
            continue

        inline_critical: Optional[bool] = None
        lowered_label = label.lower()
        if re.search(r"\bn[a\u00e3]o\s+cr[i\u00ed]tico", lowered_label):
            inline_critical = False
        elif re.search(r"\bcr[i\u00ed]tico", lowered_label):
            inline_critical = True

        if inline_critical is not None:
            label = re.sub(r"\bn[a\u00e3]o\s+cr[i\u00ed]tico\b", "", label, flags=re.IGNORECASE)
            label = re.sub(r"\bcr[i\u00ed]tico\b", "", label, flags=re.IGNORECASE)
            label = label.strip(" -()[]")

        if not label:
            continue

        items.append({
            "label": label,
            "critical": bool(inline_critical if inline_critical is not None else current_critical),
        })

    return items


def merge_document_checklist_hints(
    primary: Optional[List[Dict[str, Any]]],
    secondary: Optional[List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    merged: List[Dict[str, Any]] = []
    index: Dict[str, int] = {}

    def _normalize_item(raw: Any) -> Optional[Dict[str, Any]]:
        if isinstance(raw, str):
            label = raw.strip()
            if not label:
                return None
            return {"label": label, "critical": False}
        if not isinstance(raw, dict):
            return None
        label = str(raw.get("label") or raw.get("name") or "").strip()
        if not label:
            return None
        return {
            "id": raw.get("id"),
            "label": label,
            "critical": bool(raw.get("critical", False)),
        }

    for source in (primary or [], secondary or []):
        for raw in source:
            normalized = _normalize_item(raw)
            if not normalized:
                continue
            key = _normalize_key(str(normalized.get("id") or normalized["label"]))
            if not key:
                key = f"item_{len(merged)+1}"
            if key in index:
                if normalized.get("critical"):
                    merged[index[key]]["critical"] = True
                continue
            merged.append(normalized)
            index[key] = len(merged) - 1

    return merged
