import json
import re
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Import FidelityMatcher para validação de issues
try:
    from app.services.fidelity_matcher import FidelityMatcher
    HAS_FIDELITY_MATCHER = True
except ImportError:
    HAS_FIDELITY_MATCHER = False


def _safe_read_text(path_value: Optional[str]) -> str:
    if not path_value:
        return ""
    try:
        return Path(path_value).read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _safe_read_json(path_value: Optional[str]) -> Optional[Dict[str, Any]]:
    if not path_value:
        return None
    try:
        with open(path_value, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _normalize_score(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            return float(value)
        except Exception:
            return None
    if isinstance(value, str):
        match = re.search(r"([0-9]+(?:[.,][0-9]+)?)", value)
        if match:
            try:
                return float(match.group(1).replace(",", "."))
            except Exception:
                return None
    return None


def _normalize_severity(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if "cr" in raw:
        return "critical"
    if "alta" in raw:
        return "high"
    if "media" in raw or "média" in raw:
        return "medium"
    if "baixa" in raw:
        return "low"
    if raw:
        return raw
    return "info"


def _issue(
    *,
    source: str,
    category: str,
    description: str,
    severity: str = "info",
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    payload = {
        "source": source,
        "category": category,
        "severity": severity,
        "description": description,
    }
    if extra:
        payload.update(extra)
    return payload


def _coerce_item(item: Any) -> Dict[str, Any]:
    if isinstance(item, dict):
        return item
    return {"descricao": str(item)}


@dataclass
class AuditContext:
    report_paths: Dict[str, Any]
    raw_text: str
    formatted_text: str
    analysis_report: Optional[Dict[str, Any]]
    validation_report: Optional[Dict[str, Any]]
    output_dir: Path


class AuditPlugin:
    id: str = "base"
    label: str = "Base"

    def run(self, ctx: AuditContext) -> Dict[str, Any]:
        raise NotImplementedError


class PreventiveFidelityPlugin(AuditPlugin):
    id = "preventive_fidelity"
    label = "Auditoria preventiva de fidelidade"

    def run(self, ctx: AuditContext) -> Dict[str, Any]:
        json_path = ctx.report_paths.get("preventive_fidelity_json_path")
        md_path = ctx.report_paths.get("preventive_fidelity_md_path")
        data = _safe_read_json(json_path)
        md = _safe_read_text(md_path)

        score = None
        status = "skipped"
        issues: List[Dict[str, Any]] = []

        if isinstance(data, dict):
            score = _normalize_score(data.get("nota_fidelidade"))
            approved = bool(data.get("aprovado", True))
            status = "ok" if approved else "warning"
            recommendation = data.get("recomendacao_hil") or {}
            if bool(recommendation.get("pausar_para_revisao")):
                status = "warning"
            if data.get("erro"):
                status = "error"
                issues.append(
                    _issue(
                        source=self.id,
                        category="error",
                        severity="critical",
                        description=str(data.get("erro")),
                    )
                )
            for key, category in (
                ("omissoes_criticas", "omissao"),
                ("distorcoes", "distorcao"),
                ("alucinacoes", "alucinacao"),
                ("problemas_estruturais", "estrutura"),
                ("problemas_contexto", "contexto"),
            ):
                for item in data.get(key, []) or []:
                    item_dict = _coerce_item(item)
                    desc = item_dict.get("impacto") or item_dict.get("descricao") or item_dict.get("trecho_raw")
                    if not desc:
                        desc = json.dumps(item_dict, ensure_ascii=False)[:240]
                    issues.append(
                        _issue(
                            source=self.id,
                            category=category,
                            severity=_normalize_severity(item_dict.get("gravidade")),
                            description=str(desc),
                            extra={"raw_item": item_dict},
                        )
                    )
            sources = data.get("auditoria_fontes")
            if isinstance(sources, dict):
                source_score = _normalize_score(sources.get("nota_consistencia"))
                source_errors = sources.get("erros_criticos") or []
                source_ambiguities = sources.get("ambiguidades") or []
                sources_inconclusive = bool(sources.get("inconclusivo")) or (
                    len(source_errors) == 0
                    and len(source_ambiguities) == 0
                    and (source_score is None or source_score <= 0)
                ) or (
                    len(source_errors) == 0 and bool(sources.get("erro"))
                )
                if source_score is not None and not sources_inconclusive:
                    score = min(score, source_score) if score is not None else source_score
                if not sources_inconclusive and "aprovado" in sources and not bool(sources.get("aprovado")):
                    status = "warning"
                for item in source_errors:
                    item_dict = _coerce_item(item)
                    desc = (
                        item_dict.get("correcao_sugerida")
                        or item_dict.get("problema")
                        or item_dict.get("descricao")
                        or item_dict.get("trecho_formatado")
                    )
                    if not desc:
                        desc = json.dumps(item_dict, ensure_ascii=False)[:240]
                    issues.append(
                        _issue(
                            source=self.id,
                            category="autoria",
                            severity=_normalize_severity(item_dict.get("gravidade") or "alta"),
                            description=str(desc),
                            extra={"raw_item": item_dict},
                        )
                    )
                for item in source_ambiguities:
                    item_dict = _coerce_item(item)
                    desc = item_dict.get("sugestao") or item_dict.get("problema") or item_dict.get("descricao")
                    if not desc:
                        desc = json.dumps(item_dict, ensure_ascii=False)[:240]
                    issues.append(
                        _issue(
                            source=self.id,
                            category="autoria_ambiguidade",
                            severity="medium",
                            description=str(desc),
                            extra={"raw_item": item_dict},
                        )
                    )
                if isinstance(sources.get("erro"), str) and sources.get("erro").strip() and not source_errors:
                    issues.append(
                        _issue(
                            source=self.id,
                            category="autoria",
                            severity="warning",
                            description=sources.get("erro").strip(),
                        )
                    )
        elif md:
            status = "info"
            score = _normalize_score(md)
            match = re.search(r"\*\*Status:\*\*\s*(.+)", md, re.IGNORECASE)
            if match and "requer" in match.group(1).lower():
                status = "warning"

        return {
            "id": self.id,
            "label": self.label,
            "status": status,
            "score": score,
            "report_paths": {
                "json": json_path,
                "md": md_path,
            },
            "issues": issues,
        }


class ValidationPlugin(AuditPlugin):
    id = "validation_fidelity"
    label = "Validacao de fidelidade (full)"

    def run(self, ctx: AuditContext) -> Dict[str, Any]:
        data = ctx.validation_report or {}
        score = _normalize_score(data.get("score"))
        status = "ok" if data.get("approved") else "warning"
        if data.get("error"):
            status = "error"

        issues: List[Dict[str, Any]] = []
        for omission in data.get("omissions", []) or []:
            issues.append(_issue(source=self.id, category="omissao", severity="warning", description=str(omission)))
        for distortion in data.get("distortions", []) or []:
            issues.append(_issue(source=self.id, category="distorcao", severity="warning", description=str(distortion)))
        for structural in data.get("structural_issues", []) or []:
            issues.append(_issue(source=self.id, category="estrutura", severity="info", description=str(structural)))

        return {
            "id": self.id,
            "label": self.label,
            "status": status,
            "score": score,
            "report_paths": {},
            "issues": issues,
        }


class StructuralAnalysisPlugin(AuditPlugin):
    id = "structural_analysis"
    label = "Analise estrutural"

    def run(self, ctx: AuditContext) -> Dict[str, Any]:
        data = ctx.analysis_report or {}
        status = "ok"
        if data.get("error"):
            status = "error"
        elif data.get("total_issues", 0):
            status = "warning"

        issues: List[Dict[str, Any]] = []
        for fix in data.get("pending_fixes", []) or []:
            desc = fix.get("description") or fix.get("title") or fix.get("type") or "Issue estrutural"
            issues.append(
                _issue(
                    source=self.id,
                    category="estrutura",
                    severity=_normalize_severity(fix.get("severity")),
                    description=str(desc),
                    extra={"fix": fix},
                )
            )
        return {
            "id": self.id,
            "label": self.label,
            "status": status,
            "score": None,
            "report_paths": {},
            "issues": issues,
        }


class LegalAuditPlugin(AuditPlugin):
    id = "legal_audit"
    label = "Auditoria juridica"

    def run(self, ctx: AuditContext) -> Dict[str, Any]:
        report_path = ctx.report_paths.get("legal_audit_path") or ctx.report_paths.get("audit_path")
        report_text = _safe_read_text(report_path)
        status = "skipped" if not report_text else "info"
        issues: List[Dict[str, Any]] = []
        if report_text:
            for line in report_text.splitlines():
                if "🔴" in line:
                    issues.append(
                        _issue(
                            source=self.id,
                            category="juridico",
                            severity="warning",
                            description=line.strip(),
                        )
                    )
            if "Reprovado" in report_text:
                status = "warning"
        return {
            "id": self.id,
            "label": self.label,
            "status": status,
            "score": None,
            "report_paths": {"md": report_path},
            "issues": issues,
        }


class CoveragePlugin(AuditPlugin):
    id = "coverage_check"
    label = "Validacao de cobertura"

    def run(self, ctx: AuditContext) -> Dict[str, Any]:
        coverage_path = ctx.report_paths.get("coverage_path")
        struct_path = ctx.report_paths.get("structure_audit_path")
        coverage_text = _safe_read_text(coverage_path)
        struct_text = _safe_read_text(struct_path)
        status = "skipped"
        issues: List[Dict[str, Any]] = []
        if coverage_text or struct_text:
            status = "info"
        for text in (coverage_text, struct_text):
            if not text:
                continue
            for line in text.splitlines():
                if "⚠️" in line or "ALERTA" in line.upper():
                    issues.append(
                        _issue(
                            source=self.id,
                            category="cobertura",
                            severity="info",
                            description=line.strip(),
                        )
                    )
        return {
            "id": self.id,
            "label": self.label,
            "status": status,
            "score": None,
            "report_paths": {"coverage": coverage_path, "structure": struct_path},
            "issues": issues,
        }


def _build_report_keys(report_paths: Dict[str, Any]) -> Dict[str, Any]:
    mapping = {
        "preventive_fidelity_json": report_paths.get("preventive_fidelity_json_path"),
        "preventive_fidelity_md": report_paths.get("preventive_fidelity_md_path"),
        "legal_audit_md": report_paths.get("legal_audit_path") or report_paths.get("audit_path"),
        "fidelity_backup_json": report_paths.get("fidelity_path"),
        "analysis_json": report_paths.get("analysis_path"),
        "validation_json": report_paths.get("validation_path"),
        "coverage_txt": report_paths.get("coverage_path"),
        "structure_audit_txt": report_paths.get("structure_audit_path"),
        "suggestions_json": report_paths.get("suggestions_path"),
        "docx": report_paths.get("docx_path"),
        "md": report_paths.get("md_path"),
        "raw": report_paths.get("raw_path"),
    }
    return {k: v for k, v in mapping.items() if v}


def run_audit_pipeline(
    *,
    output_dir: Path,
    report_paths: Dict[str, Any],
    raw_text: str,
    formatted_text: str,
    analysis_report: Optional[Dict[str, Any]],
    validation_report: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    ctx = AuditContext(
        report_paths=report_paths,
        raw_text=raw_text or "",
        formatted_text=formatted_text or "",
        analysis_report=analysis_report,
        validation_report=validation_report,
        output_dir=output_dir,
    )

    plugins: List[AuditPlugin] = [
        PreventiveFidelityPlugin(),
        ValidationPlugin(),
        StructuralAnalysisPlugin(),
        LegalAuditPlugin(),
        CoveragePlugin(),
    ]

    modules: List[Dict[str, Any]] = []
    issues: List[Dict[str, Any]] = []
    scores: Dict[str, float] = {}

    for plugin in plugins:
        try:
            result = plugin.run(ctx)
        except Exception as exc:
            result = {
                "id": plugin.id,
                "label": plugin.label,
                "status": "error",
                "score": None,
                "error": str(exc),
                "report_paths": {},
                "issues": [],
            }
        modules.append(result)
        issues.extend(result.get("issues", []) or [])
        if result.get("score") is not None:
            scores[plugin.id] = float(result["score"])

    # Consolidated score policy:
    # - If preventive and validation exist, use the most conservative value (minimum).
    # - Otherwise, fall back to whichever is available.
    summary_score = None
    preventive_score = scores.get("preventive_fidelity")
    validation_score = scores.get("validation_fidelity")
    if preventive_score is not None and validation_score is not None:
        summary_score = min(float(preventive_score), float(validation_score))
        logger.debug(
            "Consolidated audit score using conservative policy min(preventive=%s, validation=%s) => %s",
            preventive_score,
            validation_score,
            summary_score,
        )
    elif preventive_score is not None:
        summary_score = float(preventive_score)
    elif validation_score is not None:
        summary_score = float(validation_score)

    # NOVO: Validar issues para remover falsos positivos E enriquecer com evidências
    validated_issues = issues
    false_positives_count = 0
    enriched_count = 0
    if HAS_FIDELITY_MATCHER and ctx.raw_text and ctx.formatted_text:
        validated_issues = []
        for issue in issues:
            # Sempre enriquece com evidências (RAW + formatado)
            enriched = FidelityMatcher.enrich_issue_with_evidence(
                issue.copy(), ctx.raw_text, ctx.formatted_text
            )
            if enriched.get("has_evidence"):
                enriched_count += 1
            
            # Valida apenas issues de conteúdo (não estruturais)
            if issue.get("category") in ("omissao", "alucinacao", "distorcao"):
                # Para alucinações, usa validação específica que verifica nomes de pessoas
                if issue.get("category") == "alucinacao":
                    validated = FidelityMatcher.validate_hallucination_issue(
                        enriched, ctx.raw_text, ctx.formatted_text
                    )
                else:
                    validated = FidelityMatcher.validate_issue(
                        enriched, ctx.raw_text, ctx.formatted_text
                    )
                if validated.get("is_false_positive"):
                    false_positives_count += 1
                    logger.info(
                        f"⏭️ Falso positivo removido: {validated.get('description', '')[:60]}..."
                    )
                    continue
                validated_issues.append(validated)
            else:
                validated_issues.append(enriched)
        
        if false_positives_count > 0:
            logger.info(f"✅ {false_positives_count} falsos positivos removidos pelo FidelityMatcher")
        if enriched_count > 0:
            logger.info(f"📋 {enriched_count} issues enriquecidas com evidências RAW/formatado")
    
    issues = validated_issues

    status = "ok"
    if any(mod.get("status") in {"warning", "error"} for mod in modules):
        status = "warning"
    if any(issue.get("severity") == "critical" for issue in issues):
        status = "warning"

    report_keys = _build_report_keys(report_paths)
    summary = {
        "version": "v1.1",  # Versão atualizada com validação de falsos positivos
        "generated_at": datetime.utcnow().isoformat(),
        "status": status,
        "score": summary_score,
        "scores": scores,
        # Nome explícito para diferenciar diagnóstico de correções HIL aplicáveis.
        "diagnostic_issues_total": len(issues),
        # Compatibilidade retroativa com consumidores legados.
        "issues_total": len(issues),
        "issues": issues[:200],
        "false_positives_removed": false_positives_count,  # NOVO: para debug
    }

    payload = {
        "summary": summary,
        "modules": modules,
        "report_keys": report_keys,
    }

    summary_path = output_dir / "audit_summary.json"
    try:
        summary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        summary_path = None

    return {
        "summary": summary,
        "summary_path": str(summary_path) if summary_path else None,
        "report_keys": report_keys,
        "modules": modules,
    }
