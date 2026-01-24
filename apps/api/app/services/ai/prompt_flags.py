from dataclasses import dataclass
import re
from typing import Optional, Dict


_FLAG_RE = re.compile(r"\s+--(?P<key>[a-zA-Z_]+)\s+(?P<value>[^\s]+)\s*$")
_BOOL_TRUE = {"1", "true", "yes", "y", "on", "sim"}
_BOOL_FALSE = {"0", "false", "no", "n", "off", "nao"}


@dataclass
class PromptFlags:
    clean_text: str
    web_search: Optional[bool] = None
    reasoning_level: Optional[str] = None
    thinking_budget: Optional[int] = None
    verbosity: Optional[str] = None


def parse_prompt_flags(text: str) -> PromptFlags:
    remaining = text.rstrip()
    raw: Dict[str, str] = {}

    while True:
        match = _FLAG_RE.search(remaining)
        if not match:
            break
        key = match.group("key").strip().lower()
        value = _strip_value(match.group("value"))
        raw[key] = value
        remaining = remaining[: match.start()].rstrip()

    flags = PromptFlags(clean_text=remaining)

    if "web_search" in raw:
        parsed = _parse_bool(raw["web_search"])
        if parsed is not None:
            flags.web_search = parsed

    if "reasoning_effort" in raw:
        mapped = _normalize_reasoning_effort(raw["reasoning_effort"])
        if mapped:
            flags.reasoning_level = mapped

    # Alias for providers that expose "thinkingLevel" / "thinking_level" instead of "reasoning_effort".
    if "thinking_level" in raw and not flags.reasoning_level:
        mapped = _normalize_reasoning_effort(raw["thinking_level"])
        if mapped:
            flags.reasoning_level = mapped

    if "thinking_budget" in raw:
        parsed = _parse_int(raw["thinking_budget"])
        if parsed is not None:
            flags.thinking_budget = parsed

    if "verbosity" in raw:
        mapped = _normalize_verbosity(raw["verbosity"])
        if mapped:
            flags.verbosity = mapped

    return flags


def apply_verbosity_instruction(system_instruction: str, verbosity: Optional[str]) -> str:
    if verbosity == "low":
        return f"{system_instruction}\n- Seja conciso e direto."
    if verbosity == "high":
        return f"{system_instruction}\n- Forneca respostas detalhadas, com contexto e exemplos quando pertinente."
    return system_instruction


def clamp_thinking_budget(budget: Optional[int], model_id: Optional[str] = None) -> Optional[int]:
    if budget is None:
        return None
    try:
        value = int(budget)
    except (TypeError, ValueError):
        return None
    if value < 0:
        return None
    max_budget = 63999
    if model_id and "sonnet" in model_id.lower():
        max_budget = 31999
    return min(value, max_budget)


def _strip_value(value: str) -> str:
    cleaned = value.strip()
    if len(cleaned) >= 2:
        if (cleaned[0] == cleaned[-1]) and cleaned[0] in ("'", '"'):
            cleaned = cleaned[1:-1]
    return cleaned.strip().strip(".,;")


def _parse_bool(value: str) -> Optional[bool]:
    normalized = value.strip().lower()
    if normalized in _BOOL_TRUE:
        return True
    if normalized in _BOOL_FALSE:
        return False
    return None


def _parse_int(value: str) -> Optional[int]:
    try:
        normalized = str(value).replace(".", "").replace(",", "")
        return int(normalized)
    except (TypeError, ValueError):
        return None


def _normalize_reasoning_effort(value: str) -> Optional[str]:
    normalized = value.strip().lower()
    if normalized in ("none", "off", "disabled", "disable"):
        return "none"
    if normalized in ("minimal", "min"):
        return "minimal"
    if normalized in ("low", "l"):
        return "low"
    if normalized in ("medium", "med", "m", "standard"):
        return "medium"
    if normalized in ("high", "h", "extended"):
        return "high"
    if normalized in ("xhigh", "x-high", "x_high", "xh"):
        return "xhigh"
    return None


def _normalize_verbosity(value: str) -> Optional[str]:
    normalized = value.strip().lower()
    if normalized in ("low", "short", "concise"):
        return "low"
    if normalized in ("medium", "med", "balanced"):
        return "medium"
    if normalized in ("high", "long", "detailed"):
        return "high"
    return None
