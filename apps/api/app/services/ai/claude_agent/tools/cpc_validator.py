"""
CPC compliance validator for agent tools.

Provides deterministic checks for common CPC requirements in petitions and
procedural documents. This is intended as a fast, explainable first pass that
can be used by agentic flows and quality gates.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class CPCRule:
    """Single deterministic compliance rule."""

    rule_id: str
    article: str
    description: str
    terms: List[str]
    min_hits: int = 1
    severity: str = "high"  # high | medium | low


_DOCUMENT_TYPE_KEYWORDS: Dict[str, List[str]] = {
    "peticao_inicial": [
        "peticao inicial",
        "autor",
        "reu",
        "valor da causa",
        "dos pedidos",
    ],
    "contestacao": [
        "contestacao",
        "preliminar",
        "impugnacao",
        "art. 337",
        "art. 341",
    ],
    "apelacao": [
        "apelacao",
        "razoes de apelacao",
        "art. 1009",
        "reforma da sentenca",
    ],
    "agravo_instrumento": [
        "agravo de instrumento",
        "art. 1015",
        "efeito suspensivo",
    ],
    "embargos_declaracao": [
        "embargos de declaracao",
        "art. 1022",
        "obscuridade",
        "contradicao",
        "omissao",
    ],
}


_CPC_RULES: Dict[str, List[CPCRule]] = {
    "peticao_inicial": [
        CPCRule(
            rule_id="pi_enderecamento",
            article="CPC Art. 319, I",
            description="Endereco do juizo competente deve constar.",
            terms=["excelentissimo", "juiz", "vara"],
            min_hits=2,
        ),
        CPCRule(
            rule_id="pi_qualificacao_partes",
            article="CPC Art. 319, II",
            description="Qualificacao minima das partes (autor/reu, dados civis).",
            terms=["autor", "reu", "cpf", "cnpj", "endereco", "estado civil", "profissao"],
            min_hits=3,
        ),
        CPCRule(
            rule_id="pi_fatos_fundamentos",
            article="CPC Art. 319, III",
            description="Fatos e fundamentos juridicos devem estar descritos.",
            terms=["dos fatos", "do direito", "fundamentacao", "fundamentos juridicos"],
            min_hits=2,
        ),
        CPCRule(
            rule_id="pi_pedidos",
            article="CPC Art. 319, IV",
            description="Pedidos devem estar claros e determinados.",
            terms=["dos pedidos", "requer", "ante o exposto", "pede deferimento"],
            min_hits=2,
        ),
        CPCRule(
            rule_id="pi_valor_causa",
            article="CPC Art. 319, V",
            description="Valor da causa deve ser indicado.",
            terms=["valor da causa"],
            min_hits=1,
        ),
        CPCRule(
            rule_id="pi_provas",
            article="CPC Art. 319, VI",
            description="Deve haver indicacao de provas.",
            terms=["provas", "protesta por provas", "prova documental", "prova testemunhal"],
            min_hits=1,
            severity="medium",
        ),
    ],
    "contestacao": [
        CPCRule(
            rule_id="ct_tempestividade",
            article="CPC Art. 335",
            description="Contestacao deve indicar tempestividade/prazo de resposta.",
            terms=["tempestiva", "tempestividade", "prazo", "quinze dias uteis", "art. 335"],
            min_hits=1,
            severity="medium",
        ),
        CPCRule(
            rule_id="ct_preliminares",
            article="CPC Art. 337",
            description="Preliminares processuais devem ser enfrentadas quando cabiveis.",
            terms=["preliminar", "art. 337", "inepcia", "ilegitimidade", "incompetencia"],
            min_hits=1,
            severity="medium",
        ),
        CPCRule(
            rule_id="ct_impugnacao_especifica",
            article="CPC Art. 341",
            description="Contestacao deve impugnar especificamente os fatos.",
            terms=["impugna", "impugnacao especifica", "art. 341", "nega", "contesta"],
            min_hits=1,
        ),
        CPCRule(
            rule_id="ct_pedidos_finais",
            article="CPC Art. 336",
            description="Pedidos finais da defesa devem constar.",
            terms=["improcedencia", "pedido", "requer", "condenacao em custas"],
            min_hits=1,
        ),
    ],
    "apelacao": [
        CPCRule(
            rule_id="ap_cabimento",
            article="CPC Arts. 1.009 e 1.010",
            description="Apelacao deve explicitar cabimento e fundamentos recursais.",
            terms=["apelacao", "art. 1009", "art. 1010", "razoes recursais", "reforma da sentenca"],
            min_hits=2,
        ),
        CPCRule(
            rule_id="ap_pedidos",
            article="CPC Art. 1.010, IV",
            description="Deve apresentar pedido de reforma, anulacao ou integracao.",
            terms=["requer", "reforma", "anulacao", "novo julgamento"],
            min_hits=1,
        ),
    ],
    "agravo_instrumento": [
        CPCRule(
            rule_id="ai_cabimento",
            article="CPC Art. 1.015",
            description="Agravo de instrumento exige indicacao de cabimento.",
            terms=["agravo de instrumento", "art. 1015", "cabimento"],
            min_hits=2,
        ),
        CPCRule(
            rule_id="ai_pecas_obrigatorias",
            article="CPC Art. 1.017",
            description="Deve mencionar pecas obrigatorias/instrucao do recurso.",
            terms=["pecas obrigatorias", "certidao de intimacao", "peticao inicial", "contestacao"],
            min_hits=1,
            severity="medium",
        ),
    ],
    "embargos_declaracao": [
        CPCRule(
            rule_id="ed_vicio_decisao",
            article="CPC Art. 1.022",
            description="Embargos devem apontar omissao, contradicao, obscuridade ou erro material.",
            terms=["omissao", "contradicao", "obscuridade", "erro material", "art. 1022"],
            min_hits=1,
        ),
    ],
}


_DEADLINE_BY_DOCUMENT_TYPE = {
    "contestacao": 15,
    "apelacao": 15,
    "agravo_instrumento": 15,
    "embargos_declaracao": 5,
}


_DATE_PATTERNS = ("%Y-%m-%d", "%d/%m/%Y")


def _normalize_text(value: str) -> str:
    lowered = (value or "").lower()
    lowered = lowered.replace("ç", "c").replace("ã", "a").replace("á", "a")
    lowered = lowered.replace("â", "a").replace("é", "e").replace("ê", "e")
    lowered = lowered.replace("í", "i").replace("ó", "o").replace("ô", "o")
    lowered = lowered.replace("õ", "o").replace("ú", "u")
    return lowered


def _parse_date(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    raw = value.strip()
    for fmt in _DATE_PATTERNS:
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def _detect_document_type(text_norm: str) -> str:
    scores: Dict[str, int] = {}
    for doc_type, keywords in _DOCUMENT_TYPE_KEYWORDS.items():
        score = sum(1 for keyword in keywords if keyword in text_norm)
        if score:
            scores[doc_type] = score
    if not scores:
        return "generic"
    return max(scores.items(), key=lambda item: item[1])[0]


def _evaluate_rules(text_norm: str, rules: List[CPCRule]) -> List[Dict[str, Any]]:
    checks: List[Dict[str, Any]] = []
    for rule in rules:
        hits = [term for term in rule.terms if term in text_norm]
        passed = len(hits) >= rule.min_hits

        status = "pass" if passed else ("warning" if rule.severity == "medium" else "fail")
        checks.append(
            {
                "id": rule.rule_id,
                "article": rule.article,
                "description": rule.description,
                "status": status,
                "severity": rule.severity,
                "hits": hits,
                "missing_terms": [] if passed else rule.terms,
                "message": (
                    "Regra atendida."
                    if passed
                    else f"Regra nao atendida. Encontrado {len(hits)}/{rule.min_hits} termos esperados."
                ),
            }
        )
    return checks


def _evaluate_deadline(
    document_type: str,
    filing_date: Optional[str],
    reference_date: Optional[str],
) -> Optional[Dict[str, Any]]:
    limit_days = _DEADLINE_BY_DOCUMENT_TYPE.get(document_type)
    if not limit_days:
        return None

    filing = _parse_date(filing_date)
    reference = _parse_date(reference_date)
    if not filing or not reference:
        return {
            "id": "deadline_check",
            "article": "CPC - prazo processual",
            "status": "warning",
            "severity": "medium",
            "message": "Nao foi possivel validar prazo. Informe reference_date e filing_date (YYYY-MM-DD).",
            "limit_days": limit_days,
            "days_elapsed": None,
        }

    days_elapsed = (filing.date() - reference.date()).days
    on_time = days_elapsed <= limit_days
    return {
        "id": "deadline_check",
        "article": "CPC - prazo processual",
        "status": "pass" if on_time else "fail",
        "severity": "high",
        "message": (
            f"Prazo observado: {days_elapsed} dias corridos (limite de referencia: {limit_days})."
            if on_time
            else (
                f"Possivel intempestividade: {days_elapsed} dias corridos excedem o limite de referencia "
                f"({limit_days})."
            )
        ),
        "limit_days": limit_days,
        "days_elapsed": days_elapsed,
        "note": "Calculo em dias corridos (heuristica). Conferir dias uteis e suspensoes locais.",
    }


def _evaluate_general_flags(text_norm: str) -> List[Dict[str, Any]]:
    checks: List[Dict[str, Any]] = []

    if re.search(r"\bcpc/?73\b|codigo de processo civil de 1973", text_norm):
        checks.append(
            {
                "id": "legacy_cpc_reference",
                "article": "Atualizacao normativa",
                "description": "Referencia a CPC/73 detectada.",
                "status": "warning",
                "severity": "medium",
                "message": (
                    "Referencia ao CPC/73 encontrada. Verifique se a citacao e historica ou se deve ser "
                    "atualizada para CPC/2015."
                ),
            }
        )

    if "art." not in text_norm and "artigo" not in text_norm:
        checks.append(
            {
                "id": "missing_legal_basis",
                "article": "Fundamentacao juridica",
                "description": "Ausencia de citacao explicita de artigos.",
                "status": "warning",
                "severity": "low",
                "message": "Nenhuma referencia explicita a artigo foi detectada no texto.",
            }
        )

    return checks


def _build_summary(checks: List[Dict[str, Any]], strict_mode: bool) -> Dict[str, Any]:
    counts = {"pass": 0, "warning": 0, "fail": 0}
    score = 0.0
    max_score = float(len(checks) or 1)

    for check in checks:
        status = check.get("status", "warning")
        if strict_mode and status == "warning":
            status = "fail"
            check["status"] = "fail"
            check["message"] = f"{check.get('message', '')} (strict_mode: warning tratado como fail)".strip()

        if status not in counts:
            status = "warning"
        counts[status] += 1

        if status == "pass":
            score += 1.0
        elif status == "warning":
            score += 0.5

    normalized_score = round((score / max_score) * 100, 2)

    if counts["fail"] > 0:
        overall = "non_compliant"
    elif counts["warning"] > 0:
        overall = "partial"
    else:
        overall = "compliant"

    return {
        "overall_status": overall,
        "score": normalized_score,
        "counts": counts,
        "strict_mode": strict_mode,
    }


async def validate_cpc_compliance(
    document_text: str,
    document_type: str = "auto",
    filing_date: Optional[str] = None,
    reference_date: Optional[str] = None,
    strict_mode: bool = False,
) -> Dict[str, Any]:
    """
    Validate legal-document compliance against baseline CPC requirements.

    Args:
        document_text: Raw document text to analyze.
        document_type: auto, peticao_inicial, contestacao, apelacao,
            agravo_instrumento, embargos_declaracao.
        filing_date: Protocol date for deadline validation.
        reference_date: Date that starts counting the deadline.
        strict_mode: Convert warnings into failures in final summary.

    Returns:
        Structured compliance report.
    """
    text_norm = _normalize_text(document_text)
    resolved_type = (document_type or "auto").strip().lower()
    if resolved_type == "auto":
        resolved_type = _detect_document_type(text_norm)

    checks: List[Dict[str, Any]] = []
    rules = _CPC_RULES.get(resolved_type, [])
    checks.extend(_evaluate_rules(text_norm, rules))
    checks.extend(_evaluate_general_flags(text_norm))

    deadline_check = _evaluate_deadline(
        document_type=resolved_type,
        filing_date=filing_date,
        reference_date=reference_date,
    )
    if deadline_check:
        checks.append(deadline_check)

    summary = _build_summary(checks, strict_mode=strict_mode)

    return {
        "success": True,
        "document_type": resolved_type,
        "summary": summary,
        "checks": checks,
        "metadata": {
            "rules_applied": len(rules),
            "deadline_checked": bool(deadline_check),
            "text_length": len(document_text or ""),
        },
    }

