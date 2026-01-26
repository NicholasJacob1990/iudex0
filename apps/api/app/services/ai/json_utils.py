import json
from typing import Any, Dict


def extract_first_json_object(text: str) -> Dict[str, Any]:
    """
    Best-effort extraction of the first JSON object (dict) from model output.

    Why not regex?
    - Regex is greedy and can easily over-capture when the model includes extra braces.
    - This scanner respects JSON strings/escapes and returns the first balanced object.
    """
    if not text:
        return {}

    stripped = text.strip()
    if not stripped:
        return {}

    # Fast path: the whole payload is JSON.
    try:
        payload = json.loads(stripped)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        pass

    start = stripped.find("{")
    if start < 0:
        return {}

    in_string = False
    escape = False
    depth = 0

    for idx in range(start, len(stripped)):
        ch = stripped[idx]
        if in_string:
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            depth += 1
            continue
        if ch == "}":
            depth -= 1
            if depth == 0:
                candidate = stripped[start : idx + 1]
                try:
                    payload = json.loads(candidate)
                    return payload if isinstance(payload, dict) else {}
                except Exception:
                    return {}

    return {}

