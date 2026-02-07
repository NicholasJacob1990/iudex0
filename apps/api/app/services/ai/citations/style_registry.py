from __future__ import annotations

from typing import Final

CANONICAL_CITATION_STYLES: Final[frozenset[str]] = frozenset(
    {
        "abnt",
        "forense_br",
        "bluebook",
        "harvard",
        "apa",
        "chicago",
        "oscola",
        "ecli",
        "vancouver",
        "inline",
        "numeric",
        "alwd",
    }
)

# Backward compatibility with existing payloads.
LEGACY_CITATION_STYLE_ALIASES: Final[dict[str, str]] = {
    "forense": "forense_br",
    "hibrido": "abnt",
}

_STYLE_HEADINGS: Final[dict[str, str]] = {
    "abnt": "REFERÊNCIAS BIBLIOGRÁFICAS",
    "forense_br": "REFERÊNCIAS FORENSES",
    "bluebook": "REFERENCES (BLUEBOOK)",
    "harvard": "REFERENCES (HARVARD)",
    "apa": "REFERENCES (APA)",
    "chicago": "REFERENCES (CHICAGO)",
    "oscola": "TABLE OF AUTHORITIES (OSCOLA)",
    "ecli": "REFERENCES (ECLI)",
    "vancouver": "REFERENCES (VANCOUVER)",
    "inline": "FONTES",
    "numeric": "REFERÊNCIAS NUMERADAS",
    "alwd": "REFERENCES (ALWD)",
}


def normalize_citation_style(style: str | None, *, default: str = "forense_br") -> str:
    raw = str(style or "").strip().lower()
    if not raw:
        return default

    canonical = LEGACY_CITATION_STYLE_ALIASES.get(raw, raw)
    if canonical in CANONICAL_CITATION_STYLES:
        return canonical
    return default


def is_valid_citation_style(style: str | None) -> bool:
    raw = str(style or "").strip().lower()
    if not raw:
        return False
    canonical = LEGACY_CITATION_STYLE_ALIASES.get(raw, raw)
    return canonical in CANONICAL_CITATION_STYLES


def citation_style_regex_pattern() -> str:
    """
    Regex pattern used by API schemas.
    Includes canonical styles and legacy aliases.
    """
    return (
        r"^(forense|hibrido|abnt|forense_br|bluebook|harvard|apa|chicago|oscola|"
        r"ecli|vancouver|inline|numeric|alwd)$"
    )


def default_heading_for_style(style: str | None) -> str:
    canonical = normalize_citation_style(style)
    return _STYLE_HEADINGS.get(canonical, "REFERÊNCIAS")
