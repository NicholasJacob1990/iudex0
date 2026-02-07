from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import re

from app.services.ai.skills.loader import parse_skill_markdown

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None  # type: ignore


_DEFAULT_TOOLS = ["search_rag", "search_jurisprudencia", "verify_citation"]
_BANNED_TOOLS = {"bash", "file_delete", "file_write"}
_ALLOWED_CITATION_STYLES = {
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
_ALLOWED_OUTPUT_FORMATS = {"chat", "document", "checklist", "json"}
_ALLOWED_AUDIENCES = {"beginner", "advanced", "both"}
_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


@dataclass
class SkillDraftData:
    name: str
    description: str
    version: str
    audience: str
    directive: str
    triggers: List[str]
    tools_required: List[str]
    tools_denied: List[str]
    subagent_model: str
    citation_style: str
    output_format: str
    prefer_workflow: bool
    prefer_agent: bool
    guardrails: List[str]
    examples: List[str]


def slugify_skill_name(value: str) -> str:
    raw = (value or "").strip().lower()
    raw = re.sub(r"[^a-z0-9\s_-]", "", raw)
    raw = re.sub(r"[\s_]+", "-", raw)
    raw = re.sub(r"-+", "-", raw).strip("-")
    return raw[:80] or "skill-custom"


def infer_triggers(directive: str, *, minimum: int = 3, maximum: int = 12) -> List[str]:
    text = (directive or "").strip()
    base = [s.strip(" .") for s in re.split(r"[,;\n]", text) if s.strip()]
    triggers: List[str] = []

    for candidate in base:
        low = candidate.lower()
        if len(low) < 4:
            continue
        if low not in triggers:
            triggers.append(low)
        if len(triggers) >= maximum:
            break

    fallback = [
        "analisar documento",
        "revisar peça",
        "gerar parecer",
        "verificar conformidade",
        "resumir caso",
    ]
    for item in fallback:
        if len(triggers) >= minimum:
            break
        if item not in triggers:
            triggers.append(item)

    return triggers[:maximum]


def _dedup(items: List[str]) -> List[str]:
    out: List[str] = []
    for it in items:
        clean = str(it or "").strip()
        if clean and clean not in out:
            out.append(clean)
    return out


def _normalize_examples(examples: Optional[List[Any]]) -> List[str]:
    normalized: List[str] = []
    for item in examples or []:
        if isinstance(item, dict):
            prompt = str(item.get("prompt") or "").strip()
            expected = str(item.get("expected_behavior") or "").strip()
            if prompt and expected:
                normalized.append(f"{prompt} => {expected}")
            elif prompt:
                normalized.append(prompt)
            continue
        text = str(item or "").strip()
        if text:
            normalized.append(text)
    return _dedup(normalized)


def build_skill_markdown(data: SkillDraftData) -> str:
    triggers = _dedup(data.triggers)
    tools_required = _dedup(data.tools_required)
    tools_denied = _dedup(data.tools_denied)
    guardrails = _dedup(data.guardrails)
    examples = _dedup(data.examples)

    def _yaml_list(items: List[str]) -> str:
        if not items:
            return " []"
        return "\n" + "\n".join([f"  - {item}" for item in items])

    frontmatter = [
        "---",
        f"name: {slugify_skill_name(data.name)}",
        f"description: {data.description or data.directive[:120]}",
        f"version: {data.version}",
        f"audience: {data.audience}",
        f"triggers:{_yaml_list(triggers)}",
        f"tools_required:{_yaml_list(tools_required)}",
        f"tools_denied:{_yaml_list(tools_denied)}",
        f"subagent_model: {data.subagent_model}",
        f"citation_style: {data.citation_style}",
        f"output_format: {data.output_format}",
        f"prefer_workflow: {str(bool(data.prefer_workflow)).lower()}",
        f"prefer_agent: {str(bool(data.prefer_agent)).lower()}",
        f"guardrails:{_yaml_list(guardrails)}",
        f"examples:{_yaml_list(examples)}",
        "---",
        "",
        "## Instructions",
        "1. Entenda objetivo, contexto e restrições do usuário.",
        "2. Execute apenas as tools necessárias com foco em precisão jurídica.",
        "3. Estruture a resposta no formato solicitado e com citações quando aplicável.",
        "4. Se faltar evidência, sinalize lacunas sem inventar fatos.",
        "",
        "## Context",
        data.directive.strip(),
    ]

    return "\n".join(frontmatter).strip() + "\n"


def _parse_frontmatter(markdown: str) -> Tuple[Dict[str, Any], str]:
    text = (markdown or "").lstrip()
    if not text.startswith("---\n"):
        return {}, markdown or ""

    _, _, remainder = text.partition("---\n")
    raw, sep, body = remainder.partition("\n---\n")
    if not sep:
        return {}, markdown or ""

    if yaml:
        try:
            parsed = yaml.safe_load(raw) or {}
            if isinstance(parsed, dict):
                return parsed, body
        except Exception:
            pass

    parsed: Dict[str, Any] = {}
    for line in raw.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        parsed[key.strip()] = value.strip()
    return parsed, body


def validate_skill_markdown(markdown: str) -> Dict[str, Any]:
    errors: List[str] = []
    warnings: List[str] = []
    improvements: List[str] = []
    security_violations: List[str] = []

    parsed_skill = parse_skill_markdown(markdown or "", source="runtime")
    frontmatter, _ = _parse_frontmatter(markdown or "")

    if parsed_skill is None:
        errors.append("Frontmatter inválido ou campos obrigatórios ausentes (name, triggers, tools_required).")
        return {
            "valid": False,
            "errors": errors,
            "warnings": warnings,
            "routing": {
                "precision_estimate": 0.0,
                "recall_estimate": 0.0,
            },
            "quality_score": 0.0,
            "tpr": 0.0,
            "fpr": 1.0,
            "security_violations": ["invalid_frontmatter"],
            "improvements": ["Corrigir frontmatter YAML com campos obrigatórios de SkillV1."],
            "parsed": None,
        }

    triggers = [str(t).strip() for t in (frontmatter.get("triggers") or parsed_skill.triggers or []) if str(t).strip()]
    tools_required = [str(t).strip() for t in (frontmatter.get("tools_required") or parsed_skill.tools_required or []) if str(t).strip()]
    tools_denied = [str(t).strip() for t in (frontmatter.get("tools_denied") or []) if str(t).strip()]
    guardrails = [str(t).strip() for t in (frontmatter.get("guardrails") or []) if str(t).strip()]
    examples = [str(t).strip() for t in (frontmatter.get("examples") or []) if str(t).strip()]
    citation_style = str(frontmatter.get("citation_style") or "abnt").strip().lower()
    output_format = str(frontmatter.get("output_format") or "document").strip().lower()
    audience = str(frontmatter.get("audience") or "both").strip().lower()
    version = str(frontmatter.get("version") or "1.0.0").strip()
    prefer_workflow = bool(frontmatter.get("prefer_workflow", False))
    prefer_agent = bool(frontmatter.get("prefer_agent", True))

    if len(triggers) < 3:
        errors.append("SkillV1 exige pelo menos 3 triggers.")
    if len(triggers) > 12:
        errors.append("SkillV1 permite no máximo 12 triggers.")

    if not _SEMVER_RE.match(version):
        errors.append("version deve seguir semver (ex: 1.0.0).")

    if audience not in _ALLOWED_AUDIENCES:
        errors.append("audience inválido (use beginner|advanced|both).")

    if citation_style not in _ALLOWED_CITATION_STYLES:
        errors.append("citation_style inválido para SkillV1.")

    if output_format not in _ALLOWED_OUTPUT_FORMATS:
        errors.append("output_format inválido (chat|document|checklist|json).")

    if prefer_workflow and prefer_agent:
        errors.append("prefer_workflow e prefer_agent não podem ser true ao mesmo tempo.")

    if not guardrails:
        warnings.append("Skill sem guardrails explícitos.")
        improvements.append("Adicionar pelo menos 1 guardrail para reduzir risco operacional.")

    if len(examples) and not 2 <= len(examples) <= 10:
        errors.append("Quando informado, examples deve conter entre 2 e 10 itens.")
    elif not examples:
        improvements.append("Adicionar 2-10 exemplos melhora precisão de roteamento e avaliação.")

    overlap = sorted(set(tools_required).intersection(set(tools_denied)))
    if overlap:
        errors.append(f"tools_required e tools_denied possuem conflito: {', '.join(overlap)}")

    banned_used = sorted(_BANNED_TOOLS.intersection(set(tools_required)))
    if banned_used:
        warnings.append(f"Ferramentas de alto risco em tools_required: {', '.join(banned_used)}")
        security_violations.append("high_risk_tools_required")
        improvements.append("Mover ferramentas de alto risco para tools_denied.")

    avg_trigger_len = sum(len(t) for t in triggers) / max(1, len(triggers))
    precision = min(0.98, 0.35 + (min(12, len(triggers)) / 24.0) + (min(40.0, avg_trigger_len) / 120.0))
    recall = min(0.98, 0.30 + (min(8, len(triggers)) / 20.0))
    fpr = max(0.0, round(1.0 - precision, 3))
    quality_score = max(
        0.0,
        min(
            1.0,
            round(
                (precision * 0.45)
                + (recall * 0.35)
                + (0.2 if len(examples) >= 2 else 0.05)
                - (0.1 if security_violations else 0.0)
                - (0.05 * min(3, len(errors))),
                3,
            ),
        ),
    )

    if avg_trigger_len < 8:
        warnings.append("Triggers muito curtas tendem a aumentar falso positivo no matcher.")
        improvements.append("Use triggers mais descritivas (>= 8 caracteres) para reduzir FPR.")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "quality_score": quality_score,
        "tpr": round(recall, 3),
        "fpr": fpr,
        "security_violations": security_violations,
        "improvements": _dedup(improvements),
        "routing": {
            "precision_estimate": round(precision, 3),
            "recall_estimate": round(recall, 3),
        },
        "parsed": {
            "name": parsed_skill.name,
            "description": parsed_skill.description,
            "triggers": parsed_skill.triggers,
            "tools_required": parsed_skill.tools_required,
            "subagent_model": parsed_skill.subagent_model,
            "version": version,
            "audience": audience,
            "citation_style": citation_style,
            "output_format": output_format,
            "prefer_workflow": prefer_workflow,
            "prefer_agent": prefer_agent,
        },
    }


def build_skill_draft(
    *,
    directive: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
    version: str = "1.0.0",
    audience: str = "both",
    triggers: Optional[List[str]] = None,
    tools_required: Optional[List[str]] = None,
    tools_denied: Optional[List[str]] = None,
    subagent_model: str = "claude-haiku-4-5",
    citation_style: str = "abnt",
    output_format: str = "document",
    prefer_workflow: bool = False,
    prefer_agent: bool = True,
    guardrails: Optional[List[str]] = None,
    examples: Optional[List[Any]] = None,
) -> str:
    directive = (directive or "").strip()
    normalized_prefer_workflow = bool(prefer_workflow)
    normalized_prefer_agent = bool(prefer_agent)
    if normalized_prefer_workflow and normalized_prefer_agent:
        normalized_prefer_agent = False

    draft = SkillDraftData(
        name=name or slugify_skill_name(directive) or "skill-custom",
        description=description or directive[:180],
        version=version if _SEMVER_RE.match(str(version)) else "1.0.0",
        audience=audience if audience in _ALLOWED_AUDIENCES else "both",
        directive=directive,
        triggers=triggers or infer_triggers(directive),
        tools_required=tools_required or list(_DEFAULT_TOOLS),
        tools_denied=tools_denied or [],
        subagent_model=subagent_model,
        citation_style=citation_style if citation_style in _ALLOWED_CITATION_STYLES else "abnt",
        output_format=output_format if output_format in _ALLOWED_OUTPUT_FORMATS else "document",
        prefer_workflow=normalized_prefer_workflow,
        prefer_agent=normalized_prefer_agent,
        guardrails=guardrails or [
            "Não inventar fatos.",
            "Sinalizar incertezas quando faltarem evidências.",
            "Seguir o estilo de citação solicitado.",
        ],
        examples=_normalize_examples(examples) or [
            "analisar petição inicial com foco em preliminares",
            "revisar minuta contratual e apontar riscos críticos",
        ],
    )
    return build_skill_markdown(draft)
