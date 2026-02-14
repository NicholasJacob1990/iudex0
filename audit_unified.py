"""
audit_unified.py — Motor de Unificação das 3 Camadas de Auditoria/HIL

Ingere resultados de:
  1. Auditoria Preventiva de Fidelidade (audit_fidelity_preventive.py)
  2. Análise Estrutural (auto_fix_apostilas.py)
  3. Validação Full-Context LLM (backup)

Produz um relatório único rankeado por severidade com cross-referencing
e sugestões de correção conjuntas.

v1.0 — 2026-02-11
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class FindingSeverity(str, Enum):
    CRITICA = "CRITICA"
    ALTA = "ALTA"
    MEDIA = "MEDIA"
    BAIXA = "BAIXA"

    def rank(self) -> int:
        return {"CRITICA": 4, "ALTA": 3, "MEDIA": 2, "BAIXA": 1}[self.value]


class FindingCategory(str, Enum):
    OMISSAO = "omissao"
    DISTORCAO = "distorcao"
    ALUCINACAO = "alucinacao"
    DUPLICACAO = "duplicacao"
    ESTRUTURA = "estrutura"
    CONTEXTO = "contexto"
    COMPRESSAO = "compressao"
    REFERENCIA_LEGAL = "referencia_legal"


class FindingSource(str, Enum):
    FIDELITY_PREVENTIVE = "fidelity_preventive"
    STRUCTURAL_ANALYSIS = "structural_analysis"
    FULL_CONTEXT_BACKUP = "full_context_backup"
    COVERAGE_CHECK = "coverage_check"
    CROSS_REFERENCE = "cross_reference"


class FindingVerdict(str, Enum):
    CONFIRMADO = "CONFIRMADO"
    PROVAVEL = "PROVAVEL"
    SUSPEITO = "SUSPEITO"
    FALSO_POSITIVO = "FALSO_POSITIVO"


class ActionType(str, Enum):
    REMOVE = "REMOVE"
    MERGE = "MERGE"
    RENAME = "RENAME"
    MOVE = "MOVE"
    DEMOTE = "DEMOTE"
    CLEAN = "CLEAN"
    INSERT = "INSERT"
    REPLACE = "REPLACE"
    VERIFY = "VERIFY"
    NONE = "NONE"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class CorrectionSuggestion:
    action: ActionType
    target_location: str = ""
    current_text: str = ""
    suggested_text: str = ""
    confidence: float = 0.0
    auto_applicable: bool = False


@dataclass
class UnifiedFinding:
    id: str
    category: FindingCategory
    severity: FindingSeverity
    verdict: FindingVerdict
    title: str
    detail: str
    sources: list[FindingSource]
    raw_findings: list[dict]
    corrections: list[CorrectionSuggestion] = field(default_factory=list)
    location: str = ""
    trecho_raw: str = ""
    trecho_formatado: str = ""
    cross_refs: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    @staticmethod
    def compute_id(category: str, sub_type: str, location: str) -> str:
        sig = f"{category}|{sub_type[:120]}|{location[:120]}"
        return hashlib.sha256(sig.encode("utf-8")).hexdigest()[:16]


@dataclass
class UnifiedMetrics:
    palavras_raw: int = 0
    palavras_formatado: int = 0
    taxa_retencao: float = 0.0
    dispositivos_legais_raw: int = 0
    dispositivos_legais_formatado: int = 0
    taxa_preservacao_dispositivos: float = 0.0
    taxa_compressao_estrutural: float = 0.0
    cobertura_fingerprint: float = 0.0


@dataclass
class HILRecommendation:
    pausar: bool = False
    motivo: str = ""
    areas_criticas: list[str] = field(default_factory=list)
    findings_criticos_ids: list[str] = field(default_factory=list)


@dataclass
class UnifiedReport:
    version: str = "1.0"
    timestamp: str = ""
    document_name: str = ""
    mode: str = "APOSTILA"

    raw_fidelity_result: dict = field(default_factory=dict)
    raw_structural_result: dict = field(default_factory=dict)
    raw_backup_result: dict = field(default_factory=dict)

    findings: list[UnifiedFinding] = field(default_factory=list)
    metrics: UnifiedMetrics = field(default_factory=UnifiedMetrics)
    hil_recommendation: HILRecommendation = field(default_factory=HILRecommendation)

    summary: dict = field(default_factory=dict)

    nota_fidelidade: float = 0.0
    nota_estrutural: float = 0.0
    nota_geral: float = 0.0
    aprovado: bool = True

    def compute_summary(self):
        by_sev = {"CRITICA": 0, "ALTA": 0, "MEDIA": 0, "BAIXA": 0}
        by_cat: dict[str, int] = {}
        fp_count = 0
        for f in self.findings:
            if f.verdict == FindingVerdict.FALSO_POSITIVO:
                fp_count += 1
                continue
            by_sev[f.severity.value] = by_sev.get(f.severity.value, 0) + 1
            by_cat[f.category.value] = by_cat.get(f.category.value, 0) + 1
        self.summary = {
            "total_findings": sum(by_sev.values()),
            "by_severity": by_sev,
            "by_category": by_cat,
            "false_positives_removed": fp_count,
        }

    def findings_sorted(self) -> list[UnifiedFinding]:
        active = [f for f in self.findings if f.verdict != FindingVerdict.FALSO_POSITIVO]
        return sorted(active, key=lambda f: (-f.severity.rank(), f.category.value))

    def to_dict(self) -> dict:
        self.compute_summary()
        return asdict(self)

    def save_json(self, path: str):
        with open(path, "w", encoding="utf-8") as fp:
            json.dump(self.to_dict(), fp, ensure_ascii=False, indent=2, default=str)

    @classmethod
    def load_json(cls, path: str) -> "UnifiedReport":
        with open(path, "r", encoding="utf-8") as fp:
            data = json.load(fp)
        report = cls()
        report.version = data.get("version", "1.0")
        report.timestamp = data.get("timestamp", "")
        report.document_name = data.get("document_name", "")
        report.mode = data.get("mode", "APOSTILA")
        report.raw_fidelity_result = data.get("raw_fidelity_result", {})
        report.raw_structural_result = data.get("raw_structural_result", {})
        report.raw_backup_result = data.get("raw_backup_result", {})
        report.nota_fidelidade = data.get("nota_fidelidade", 0.0)
        report.nota_estrutural = data.get("nota_estrutural", 0.0)
        report.nota_geral = data.get("nota_geral", 0.0)
        report.aprovado = data.get("aprovado", True)
        report.summary = data.get("summary", {})
        # Reconstituir findings
        for fd in data.get("findings", []):
            corrections = []
            for c in fd.get("corrections", []):
                corrections.append(CorrectionSuggestion(
                    action=ActionType(c.get("action", "NONE")),
                    target_location=c.get("target_location", ""),
                    current_text=c.get("current_text", ""),
                    suggested_text=c.get("suggested_text", ""),
                    confidence=c.get("confidence", 0.0),
                    auto_applicable=c.get("auto_applicable", False),
                ))
            report.findings.append(UnifiedFinding(
                id=fd.get("id", ""),
                category=FindingCategory(fd.get("category", "estrutura")),
                severity=FindingSeverity(fd.get("severity", "MEDIA")),
                verdict=FindingVerdict(fd.get("verdict", "PROVAVEL")),
                title=fd.get("title", ""),
                detail=fd.get("detail", ""),
                sources=[FindingSource(s) for s in fd.get("sources", [])],
                raw_findings=fd.get("raw_findings", []),
                corrections=corrections,
                location=fd.get("location", ""),
                trecho_raw=fd.get("trecho_raw", ""),
                trecho_formatado=fd.get("trecho_formatado", ""),
                cross_refs=fd.get("cross_refs", []),
                tags=fd.get("tags", []),
            ))
        # Reconstituir metrics
        m = data.get("metrics", {})
        report.metrics = UnifiedMetrics(
            palavras_raw=m.get("palavras_raw", 0),
            palavras_formatado=m.get("palavras_formatado", 0),
            taxa_retencao=m.get("taxa_retencao", 0.0),
            dispositivos_legais_raw=m.get("dispositivos_legais_raw", 0),
            dispositivos_legais_formatado=m.get("dispositivos_legais_formatado", 0),
            taxa_preservacao_dispositivos=m.get("taxa_preservacao_dispositivos", 0.0),
            taxa_compressao_estrutural=m.get("taxa_compressao_estrutural", 0.0),
            cobertura_fingerprint=m.get("cobertura_fingerprint", 0.0),
        )
        # Reconstituir HIL
        h = data.get("hil_recommendation", {})
        report.hil_recommendation = HILRecommendation(
            pausar=h.get("pausar", False),
            motivo=h.get("motivo", ""),
            areas_criticas=h.get("areas_criticas", []),
            findings_criticos_ids=h.get("findings_criticos_ids", []),
        )
        return report


# ---------------------------------------------------------------------------
# UnifiedAuditEngine
# ---------------------------------------------------------------------------

_GRAVIDADE_MAP = {
    "CRITICA": FindingSeverity.CRITICA, "CRÍTICA": FindingSeverity.CRITICA,
    "ALTA": FindingSeverity.ALTA,
    "MEDIA": FindingSeverity.MEDIA, "MÉDIA": FindingSeverity.MEDIA,
    "BAIXA": FindingSeverity.BAIXA,
}

_VERDICT_MAP = {
    "CONFIRMADO": FindingVerdict.CONFIRMADO,
    "SUSPEITO": FindingVerdict.SUSPEITO,
}

# Regex para extrair referência legal normalizada de texto livre
_LEI_NORM_RE = re.compile(
    r"(?:lei|lc|decreto|mp)\s*(?:complementar\s*)?n?[º°]?\s*([\d.]+)",
    re.IGNORECASE,
)
_SUMULA_NORM_RE = re.compile(r"s[úu]mula\s*n?[º°]?\s*(\d+)", re.IGNORECASE)


def _normalize_legal_ref(text: str) -> str:
    """Extrai e normaliza referência legal de texto livre."""
    text_lower = text.lower().strip()
    m = _LEI_NORM_RE.search(text_lower)
    if m:
        return f"lei_{m.group(1).replace('.', '')}"
    m = _SUMULA_NORM_RE.search(text_lower)
    if m:
        return f"sumula_{m.group(1)}"
    return text_lower[:60]


class UnifiedAuditEngine:

    def __init__(self, document_name: str, mode: str = "APOSTILA"):
        self.document_name = document_name
        self.mode = mode.upper()
        self.report = UnifiedReport(
            document_name=document_name,
            mode=self.mode,
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
        )
        # Index de normalização legal para cross-ref
        self._legal_index: dict[str, list[str]] = {}  # norm_ref -> [finding_id]

    # -----------------------------------------------------------------------
    # Ingest: Auditoria Preventiva de Fidelidade
    # -----------------------------------------------------------------------

    def ingest_fidelity(self, result: dict):
        if not isinstance(result, dict):
            return
        self.report.raw_fidelity_result = result

        # omissoes_criticas
        for item in result.get("omissoes_criticas") or []:
            tipo = str(item.get("tipo", "conteudo"))
            loc = str(item.get("localizacao_formatado", ""))
            fid = UnifiedFinding.compute_id("omissao", tipo, loc)
            f = UnifiedFinding(
                id=fid,
                category=FindingCategory.OMISSAO,
                severity=_GRAVIDADE_MAP.get(str(item.get("gravidade", "ALTA")).upper(), FindingSeverity.ALTA),
                verdict=_VERDICT_MAP.get(str(item.get("veredito", "")).upper(), FindingVerdict.PROVAVEL),
                title=f"Omissao: {tipo}",
                detail=str(item.get("impacto", "")),
                sources=[FindingSource.FIDELITY_PREVENTIVE],
                raw_findings=[item],
                trecho_raw=str(item.get("trecho_raw", "")),
                location=loc,
            )
            # Se for lei/sumula, indexar para cross-ref
            if tipo.lower() in ("lei", "sumula", "tema"):
                norm = _normalize_legal_ref(str(item.get("trecho_raw", tipo)))
                self._legal_index.setdefault(norm, []).append(fid)
            self._add_finding(f)

        # distorcoes
        for item in result.get("distorcoes") or []:
            tipo = str(item.get("tipo", "conteudo"))
            raw_trecho = str(item.get("trecho_raw", ""))[:80]
            fid = UnifiedFinding.compute_id("distorcao", tipo, raw_trecho)
            f = UnifiedFinding(
                id=fid,
                category=FindingCategory.DISTORCAO,
                severity=_GRAVIDADE_MAP.get(str(item.get("gravidade", "ALTA")).upper(), FindingSeverity.ALTA),
                verdict=_VERDICT_MAP.get(str(item.get("veredito", "")).upper(), FindingVerdict.PROVAVEL),
                title=f"Distorcao: {tipo}",
                detail=str(item.get("correcao", "")),
                sources=[FindingSource.FIDELITY_PREVENTIVE],
                raw_findings=[item],
                trecho_raw=str(item.get("trecho_raw", "")),
                trecho_formatado=str(item.get("trecho_formatado", "")),
                corrections=[CorrectionSuggestion(
                    action=ActionType.REPLACE,
                    target_location=str(item.get("trecho_formatado", ""))[:80],
                    current_text=str(item.get("trecho_formatado", "")),
                    suggested_text=str(item.get("correcao", "")),
                    confidence=0.85,
                )],
            )
            self._add_finding(f)

        # alucinacoes
        for item in result.get("alucinacoes") or []:
            trecho = str(item.get("trecho_formatado", ""))[:80]
            fid = UnifiedFinding.compute_id("alucinacao", trecho, "")
            acao = item.get("acao_sugerida", "verificar")
            confianca_str = str(item.get("confianca", "MEDIA")).upper()
            conf_val = {"ALTA": 0.9, "MEDIA": 0.7, "BAIXA": 0.5}.get(confianca_str, 0.7)
            f = UnifiedFinding(
                id=fid,
                category=FindingCategory.ALUCINACAO,
                severity=FindingSeverity.ALTA,
                verdict=_VERDICT_MAP.get(str(item.get("veredito", "")).upper(), FindingVerdict.SUSPEITO),
                title="Possivel alucinacao",
                detail=str(item.get("trecho_formatado", "")),
                sources=[FindingSource.FIDELITY_PREVENTIVE],
                raw_findings=[item],
                trecho_formatado=str(item.get("trecho_formatado", "")),
                corrections=[CorrectionSuggestion(
                    action=ActionType.VERIFY if acao == "verificar" else ActionType.REMOVE,
                    target_location="",
                    current_text=str(item.get("trecho_formatado", "")),
                    confidence=conf_val,
                )],
            )
            self._add_finding(f)

        # problemas_estruturais (do LLM)
        for item in result.get("problemas_estruturais") or []:
            tipo = str(item.get("tipo", ""))
            loc = str(item.get("localizacao", ""))
            fid = UnifiedFinding.compute_id("estrutura", tipo, loc)
            f = UnifiedFinding(
                id=fid,
                category=FindingCategory.ESTRUTURA,
                severity=FindingSeverity.MEDIA,
                verdict=FindingVerdict.PROVAVEL,
                title=f"Estrutural (LLM): {tipo}",
                detail=str(item.get("descricao", "")),
                sources=[FindingSource.FIDELITY_PREVENTIVE],
                raw_findings=[item],
                location=loc,
                tags=["llm_detected"],
            )
            self._add_finding(f)

        # problemas_contexto
        for item in result.get("problemas_contexto") or []:
            tipo = str(item.get("tipo", ""))
            loc = str(item.get("localizacao", ""))
            fid = UnifiedFinding.compute_id("contexto", tipo, loc)
            f = UnifiedFinding(
                id=fid,
                category=FindingCategory.CONTEXTO,
                severity=FindingSeverity.BAIXA,
                verdict=FindingVerdict.PROVAVEL,
                title=f"Contexto: {tipo}",
                detail=str(item.get("sugestao", "")),
                sources=[FindingSource.FIDELITY_PREVENTIVE],
                raw_findings=[item],
                location=loc,
            )
            self._add_finding(f)

        # Métricas
        metricas = result.get("metricas") or {}
        self.report.metrics.palavras_raw = metricas.get("palavras_raw", 0)
        self.report.metrics.palavras_formatado = metricas.get("palavras_formatado", 0)
        self.report.metrics.taxa_retencao = metricas.get("taxa_retencao", 0.0)
        self.report.metrics.dispositivos_legais_raw = metricas.get("dispositivos_legais_raw", 0)
        self.report.metrics.dispositivos_legais_formatado = metricas.get("dispositivos_legais_formatado", 0)
        self.report.metrics.taxa_preservacao_dispositivos = metricas.get("taxa_preservacao_dispositivos", 0.0)
        self.report.nota_fidelidade = float(result.get("nota_fidelidade", 0))

    # -----------------------------------------------------------------------
    # Ingest: Análise Estrutural
    # -----------------------------------------------------------------------

    def ingest_structural(self, result: dict):
        if not isinstance(result, dict):
            return
        self.report.raw_structural_result = result

        # duplicate_sections
        for item in result.get("duplicate_sections") or []:
            title = str(item.get("title", ""))[:80]
            fid = UnifiedFinding.compute_id("duplicacao", "section", title)
            f = UnifiedFinding(
                id=fid,
                category=FindingCategory.DUPLICACAO,
                severity=FindingSeverity.MEDIA,
                verdict=FindingVerdict.PROVAVEL,
                title=f"Secao duplicada: {title[:60]}",
                detail=f"Similar a: {item.get('similar_to', '')}",
                sources=[FindingSource.STRUCTURAL_ANALYSIS],
                raw_findings=[item],
                location=title,
                corrections=[CorrectionSuggestion(
                    action=ActionType.MERGE,
                    target_location=title,
                    confidence=0.90,
                )],
                tags=["regex_detected"],
            )
            self._add_finding(f)

        # duplicate_paragraphs
        for item in result.get("duplicate_paragraphs") or []:
            fp = str(item.get("fingerprint", ""))
            fid = UnifiedFinding.compute_id("duplicacao", "paragraph", fp)
            kind = item.get("duplicate_kind", "exact")
            f = UnifiedFinding(
                id=fid,
                category=FindingCategory.DUPLICACAO,
                severity=FindingSeverity.BAIXA,
                verdict=FindingVerdict.PROVAVEL,
                title=f"Paragrafo duplicado ({kind})",
                detail=str(item.get("reason", "")),
                sources=[FindingSource.STRUCTURAL_ANALYSIS],
                raw_findings=[item],
                location=f"line {item.get('line_index', '?')}",
                trecho_formatado=str(item.get("preview", "")),
                corrections=[CorrectionSuggestion(
                    action=ActionType.REMOVE,
                    target_location=f"line {item.get('line_index', '?')}",
                    confidence=float(item.get("confidence", 0.85)),
                    auto_applicable=(kind == "exact"),
                )],
                tags=["regex_detected"],
            )
            self._add_finding(f)

        # missing_laws
        for law in result.get("missing_laws") or []:
            norm = _normalize_legal_ref(f"lei {law}")
            fid = UnifiedFinding.compute_id("referencia_legal", "lei", norm)
            f = UnifiedFinding(
                id=fid,
                category=FindingCategory.REFERENCIA_LEGAL,
                severity=FindingSeverity.ALTA,
                verdict=FindingVerdict.PROVAVEL,
                title=f"Lei faltante: {law}",
                detail="Detectada no RAW mas ausente no formatado (regex)",
                sources=[FindingSource.STRUCTURAL_ANALYSIS],
                raw_findings=[{"type": "missing_law", "value": law}],
                tags=["legal_reference", "regex_detected"],
            )
            self._legal_index.setdefault(norm, []).append(fid)
            self._add_finding(f)

        # missing_sumulas
        for s in result.get("missing_sumulas") or []:
            norm = _normalize_legal_ref(f"sumula {s}")
            fid = UnifiedFinding.compute_id("referencia_legal", "sumula", norm)
            f = UnifiedFinding(
                id=fid,
                category=FindingCategory.REFERENCIA_LEGAL,
                severity=FindingSeverity.ALTA,
                verdict=FindingVerdict.PROVAVEL,
                title=f"Sumula faltante: {s}",
                detail="Detectada no RAW mas ausente no formatado (regex)",
                sources=[FindingSource.STRUCTURAL_ANALYSIS],
                raw_findings=[{"type": "missing_sumula", "value": s}],
                tags=["legal_reference", "regex_detected"],
            )
            self._legal_index.setdefault(norm, []).append(fid)
            self._add_finding(f)

        # missing_decretos
        for d in result.get("missing_decretos") or []:
            norm = _normalize_legal_ref(f"decreto {d}")
            fid = UnifiedFinding.compute_id("referencia_legal", "decreto", norm)
            f = UnifiedFinding(
                id=fid,
                category=FindingCategory.REFERENCIA_LEGAL,
                severity=FindingSeverity.MEDIA,
                verdict=FindingVerdict.PROVAVEL,
                title=f"Decreto faltante: {d}",
                detail="Detectado no RAW mas ausente no formatado (regex)",
                sources=[FindingSource.STRUCTURAL_ANALYSIS],
                raw_findings=[{"type": "missing_decreto", "value": d}],
                tags=["legal_reference", "regex_detected"],
            )
            self._add_finding(f)

        # missing_julgados
        for j in result.get("missing_julgados") or []:
            fid = UnifiedFinding.compute_id("referencia_legal", "julgado", str(j)[:80])
            f = UnifiedFinding(
                id=fid,
                category=FindingCategory.REFERENCIA_LEGAL,
                severity=FindingSeverity.MEDIA,
                verdict=FindingVerdict.PROVAVEL,
                title=f"Julgado faltante: {j}",
                detail="Detectado no RAW mas ausente no formatado (regex)",
                sources=[FindingSource.STRUCTURAL_ANALYSIS],
                raw_findings=[{"type": "missing_julgado", "value": j}],
                tags=["legal_reference", "regex_detected"],
            )
            self._add_finding(f)

        # heading_semantic_issues
        for item in result.get("heading_semantic_issues") or []:
            line = item.get("heading_line", "?")
            fid = UnifiedFinding.compute_id("estrutura", "heading_semantic", str(line))
            f = UnifiedFinding(
                id=fid,
                category=FindingCategory.ESTRUTURA,
                severity=FindingSeverity.BAIXA,
                verdict=FindingVerdict.PROVAVEL,
                title=f"Heading semantico: {str(item.get('reason', ''))[:60]}",
                detail=str(item.get("reason", "")),
                sources=[FindingSource.STRUCTURAL_ANALYSIS],
                raw_findings=[item],
                location=f"line {line}",
                corrections=[CorrectionSuggestion(
                    action=ActionType.RENAME,
                    target_location=f"line {line}",
                    current_text=str(item.get("old_raw", "")),
                    suggested_text=str(item.get("new_raw", "")),
                    confidence=float(item.get("confidence", 0.85)),
                    auto_applicable=True,
                )],
                tags=["regex_detected"],
            )
            self._add_finding(f)

        # heading_markdown_issues
        for item in result.get("heading_markdown_issues") or []:
            line = item.get("heading_line", "?")
            fid = UnifiedFinding.compute_id("estrutura", "heading_markdown", str(line))
            f = UnifiedFinding(
                id=fid,
                category=FindingCategory.ESTRUTURA,
                severity=FindingSeverity.BAIXA,
                verdict=FindingVerdict.PROVAVEL,
                title=f"Markdown artifact: {str(item.get('reason', ''))[:60]}",
                detail=str(item.get("reason", "")),
                sources=[FindingSource.STRUCTURAL_ANALYSIS],
                raw_findings=[item],
                location=f"line {line}",
                corrections=[CorrectionSuggestion(
                    action=ActionType.CLEAN,
                    target_location=f"line {line}",
                    current_text=str(item.get("old_raw", "")),
                    suggested_text=str(item.get("new_raw", "")),
                    confidence=0.95,
                    auto_applicable=True,
                )],
                tags=["regex_detected"],
            )
            self._add_finding(f)

        # table_heading_level_issues
        for item in result.get("table_heading_level_issues") or []:
            line = item.get("heading_line", "?")
            fid = UnifiedFinding.compute_id("estrutura", "table_level", str(line))
            f = UnifiedFinding(
                id=fid,
                category=FindingCategory.ESTRUTURA,
                severity=FindingSeverity.BAIXA,
                verdict=FindingVerdict.PROVAVEL,
                title=f"Nivel de heading de tabela",
                detail=str(item.get("reason", "")),
                sources=[FindingSource.STRUCTURAL_ANALYSIS],
                raw_findings=[item],
                location=f"line {line}",
                corrections=[CorrectionSuggestion(
                    action=ActionType.DEMOTE,
                    target_location=f"line {line}",
                    confidence=0.90,
                    auto_applicable=True,
                )],
                tags=["regex_detected"],
            )
            self._add_finding(f)

        # table_misplacements
        for item in result.get("table_misplacements") or []:
            line = item.get("line", "?")
            fid = UnifiedFinding.compute_id("estrutura", "table_misplaced", str(line))
            f = UnifiedFinding(
                id=fid,
                category=FindingCategory.ESTRUTURA,
                severity=FindingSeverity.MEDIA,
                verdict=FindingVerdict.PROVAVEL,
                title=f"Tabela mal posicionada: {str(item.get('table_heading', ''))[:50]}",
                detail=str(item.get("position_issue", "")),
                sources=[FindingSource.STRUCTURAL_ANALYSIS],
                raw_findings=[item],
                location=f"line {line}",
                corrections=[CorrectionSuggestion(
                    action=ActionType.MOVE,
                    target_location=str(item.get("mother_section", "")),
                    confidence=0.85,
                )],
                tags=["regex_detected"],
            )
            self._add_finding(f)

        # Compression ratio
        cr = result.get("compression_ratio")
        cw = result.get("compression_warning")
        if cr is not None:
            self.report.metrics.taxa_compressao_estrutural = float(cr)
        if cw:
            fid = UnifiedFinding.compute_id("compressao", "ratio", str(cr))
            f = UnifiedFinding(
                id=fid,
                category=FindingCategory.COMPRESSAO,
                severity=FindingSeverity.MEDIA,
                verdict=FindingVerdict.PROVAVEL,
                title=f"Compressao: {cw[:80]}",
                detail=f"Taxa: {cr}",
                sources=[FindingSource.STRUCTURAL_ANALYSIS],
                raw_findings=[{"compression_ratio": cr, "warning": cw}],
            )
            self._add_finding(f)

    # -----------------------------------------------------------------------
    # Ingest: Full-Context Backup
    # -----------------------------------------------------------------------

    def ingest_backup(self, result: dict):
        if not isinstance(result, dict):
            return
        self.report.raw_backup_result = result

        # Corroborar ou adicionar omissões
        for om in result.get("omissoes_graves") or result.get("omissoes") or []:
            om_str = str(om)
            fid = UnifiedFinding.compute_id("omissao", "backup", om_str[:80])
            self._add_source_or_create(
                fid, FindingSource.FULL_CONTEXT_BACKUP,
                fallback=UnifiedFinding(
                    id=fid,
                    category=FindingCategory.OMISSAO,
                    severity=FindingSeverity.MEDIA,
                    verdict=FindingVerdict.SUSPEITO,
                    title=f"Omissao (backup): {om_str[:60]}",
                    detail=om_str,
                    sources=[FindingSource.FULL_CONTEXT_BACKUP],
                    raw_findings=[{"omissao": om}],
                ),
            )

        # Corroborar distorções
        for d in result.get("distorcoes") or []:
            d_str = str(d)
            fid = UnifiedFinding.compute_id("distorcao", "backup", d_str[:80])
            self._add_source_or_create(
                fid, FindingSource.FULL_CONTEXT_BACKUP,
                fallback=UnifiedFinding(
                    id=fid,
                    category=FindingCategory.DISTORCAO,
                    severity=FindingSeverity.MEDIA,
                    verdict=FindingVerdict.SUSPEITO,
                    title=f"Distorcao (backup): {d_str[:60]}",
                    detail=d_str,
                    sources=[FindingSource.FULL_CONTEXT_BACKUP],
                    raw_findings=[{"distorcao": d}],
                ),
            )

    # -----------------------------------------------------------------------
    # Cross-Referencing
    # -----------------------------------------------------------------------

    def cross_reference(self):
        # Regra 1: Merge findings com mesma referência legal normalizada
        self._merge_legal_references()

        # Regra 2: Merge duplicações LLM ↔ structural
        self._merge_structural_duplicates()

        # Regra 3: Findings em 2+ fontes → CONFIRMADO
        for f in self.report.findings:
            if len(f.sources) >= 2 and f.verdict not in (FindingVerdict.FALSO_POSITIVO, FindingVerdict.CONFIRMADO):
                f.verdict = FindingVerdict.CONFIRMADO

        # Regra 4: Compressão alta + muitas omissões → elevar severidade
        omissao_count = len([
            f for f in self.report.findings
            if f.category == FindingCategory.OMISSAO
            and f.verdict != FindingVerdict.FALSO_POSITIVO
        ])
        has_compression = any(f.category == FindingCategory.COMPRESSAO for f in self.report.findings)
        if has_compression and omissao_count >= 3:
            for f in self.report.findings:
                if f.category == FindingCategory.OMISSAO and f.severity == FindingSeverity.MEDIA:
                    f.severity = FindingSeverity.ALTA
                    if "elevated_by_compression" not in f.tags:
                        f.tags.append("elevated_by_compression")

        # Gerar cross-refs bidirecionais
        self._generate_cross_refs()

    def _merge_legal_references(self):
        """Merge findings que referenciam a mesma lei/sumula de fontes diferentes."""
        for norm_ref, finding_ids in self._legal_index.items():
            if len(finding_ids) <= 1:
                continue
            # Encontrar os findings reais
            matched = [f for f in self.report.findings if f.id in finding_ids]
            if len(matched) <= 1:
                continue
            # Escolher o de maior severidade como principal
            matched.sort(key=lambda f: -f.severity.rank())
            primary = matched[0]
            for secondary in matched[1:]:
                for src in secondary.sources:
                    if src not in primary.sources:
                        primary.sources.append(src)
                primary.raw_findings.extend(secondary.raw_findings)
                for corr in secondary.corrections:
                    if corr not in primary.corrections:
                        primary.corrections.append(corr)
                if secondary.severity.rank() > primary.severity.rank():
                    primary.severity = secondary.severity
                # Marcar secondary como falso positivo (já mergeado)
                secondary.verdict = FindingVerdict.FALSO_POSITIVO
                secondary.tags.append("merged_into:" + primary.id)

    def _merge_structural_duplicates(self):
        """Merge duplicações detectadas por LLM e por regex na mesma região."""
        llm_dupes = [
            f for f in self.report.findings
            if f.category == FindingCategory.ESTRUTURA
            and "llm_detected" in f.tags
            and any(kw in f.title.lower() for kw in ("duplica", "repeti"))
        ]
        regex_dupes = [
            f for f in self.report.findings
            if f.category == FindingCategory.DUPLICACAO
            and "regex_detected" in f.tags
        ]
        for llm_f in llm_dupes:
            llm_loc = llm_f.location.lower()
            for regex_f in regex_dupes:
                regex_loc = regex_f.location.lower()
                # Heurística: se a localização LLM contém texto do regex ou vice-versa
                if (llm_loc and regex_loc and
                        (llm_loc in regex_loc or regex_loc in llm_loc or
                         _text_overlap(llm_loc, regex_loc) > 0.5)):
                    # Merge: regex corrobora LLM
                    for src in regex_f.sources:
                        if src not in llm_f.sources:
                            llm_f.sources.append(src)
                    llm_f.raw_findings.extend(regex_f.raw_findings)
                    llm_f.category = FindingCategory.DUPLICACAO  # mais específico
                    for corr in regex_f.corrections:
                        if corr not in llm_f.corrections:
                            llm_f.corrections.append(corr)
                    regex_f.verdict = FindingVerdict.FALSO_POSITIVO
                    regex_f.tags.append("merged_into:" + llm_f.id)

    def _generate_cross_refs(self):
        """Gera links bidirecionais entre findings da mesma categoria/região."""
        active = [f for f in self.report.findings if f.verdict != FindingVerdict.FALSO_POSITIVO]
        # Agrupar por categoria
        by_cat: dict[str, list[UnifiedFinding]] = {}
        for f in active:
            by_cat.setdefault(f.category.value, []).append(f)

        for cat, findings in by_cat.items():
            if len(findings) <= 1:
                continue
            for i, f1 in enumerate(findings):
                for f2 in findings[i + 1:]:
                    if f1.id != f2.id:
                        if f2.id not in f1.cross_refs:
                            f1.cross_refs.append(f2.id)
                        if f1.id not in f2.cross_refs:
                            f2.cross_refs.append(f1.id)

    # -----------------------------------------------------------------------
    # Scoring
    # -----------------------------------------------------------------------

    def compute_final_scores(self):
        active = [f for f in self.report.findings if f.verdict != FindingVerdict.FALSO_POSITIVO]
        criticas = [f for f in active if f.severity in (FindingSeverity.CRITICA, FindingSeverity.ALTA)]

        # Nota fidelidade: usar a da auditoria preventiva, ou calcular
        nota_fid = self.report.nota_fidelidade or 5.0

        # Nota estrutural: 10 - 0.5 por issue estrutural/duplicação
        structural_count = len([
            f for f in active
            if f.category in (FindingCategory.DUPLICACAO, FindingCategory.ESTRUTURA)
        ])
        nota_est = max(0.0, 10.0 - (structural_count * 0.5))

        self.report.nota_estrutural = round(nota_est, 2)
        self.report.nota_geral = round((nota_fid * 0.7) + (nota_est * 0.3), 2)
        self.report.aprovado = len(criticas) == 0 and self.report.nota_geral >= 7.0

        # HIL recommendation
        areas: set[str] = set()
        motivos: list[str] = []
        for f in criticas:
            areas.add(f.category.value)
            if f.verdict == FindingVerdict.CONFIRMADO:
                motivos.append(f.title[:80])

        self.report.hil_recommendation = HILRecommendation(
            pausar=len(criticas) > 0,
            motivo=" | ".join(motivos[:5]) if motivos else "",
            areas_criticas=sorted(areas),
            findings_criticos_ids=[f.id for f in criticas[:20]],
        )

    # -----------------------------------------------------------------------
    # Build
    # -----------------------------------------------------------------------

    def build(self) -> UnifiedReport:
        self.cross_reference()
        self.compute_final_scores()
        self.report.compute_summary()
        return self.report

    # -----------------------------------------------------------------------
    # Helpers internos
    # -----------------------------------------------------------------------

    def _add_finding(self, finding: UnifiedFinding):
        for existing in self.report.findings:
            if existing.id == finding.id:
                for src in finding.sources:
                    if src not in existing.sources:
                        existing.sources.append(src)
                existing.raw_findings.extend(finding.raw_findings)
                if finding.severity.rank() > existing.severity.rank():
                    existing.severity = finding.severity
                for corr in finding.corrections:
                    existing.corrections.append(corr)
                return
        self.report.findings.append(finding)

    def _add_source_or_create(self, f_id: str, source: FindingSource, fallback: UnifiedFinding):
        for existing in self.report.findings:
            if existing.id == f_id:
                if source not in existing.sources:
                    existing.sources.append(source)
                return
        self._add_finding(fallback)


# ---------------------------------------------------------------------------
# Utilitário de overlap textual
# ---------------------------------------------------------------------------

def _text_overlap(a: str, b: str) -> float:
    """Jaccard simples de palavras entre dois textos."""
    if not a or not b:
        return 0.0
    words_a = set(a.split())
    words_b = set(b.split())
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union)


# ---------------------------------------------------------------------------
# Geração de Relatório Markdown
# ---------------------------------------------------------------------------

def generate_unified_markdown(report: UnifiedReport, output_path: str):
    findings = report.findings_sorted()

    lines: list[str] = []
    w = lines.append

    w(f"# Relatório Unificado de Auditoria: {report.document_name}\n")
    w(f"**Modo:** {report.mode} | **Gerado em:** {report.timestamp} | **Versão:** {report.version}\n")

    # Status geral
    status = "APROVADO" if report.aprovado else "REQUER REVISÃO"
    w(f"\n## Status Geral: {status}\n")
    w("| Métrica | Valor |")
    w("|---------|-------|")
    w(f"| Nota Fidelidade | {report.nota_fidelidade:.1f}/10 |")
    w(f"| Nota Estrutural | {report.nota_estrutural:.1f}/10 |")
    w(f"| **Nota Geral** | **{report.nota_geral:.1f}/10** |")
    w(f"| Total Findings | {report.summary.get('total_findings', 0)} |")
    w(f"| Falsos Positivos Removidos | {report.summary.get('false_positives_removed', 0)} |")
    w("")

    # Métricas de cobertura
    m = report.metrics
    if m.palavras_raw > 0:
        w("## Métricas de Cobertura\n")
        w(f"- Palavras RAW: {m.palavras_raw:,} | Formatado: {m.palavras_formatado:,}")
        w(f"- Taxa de Retenção: {m.taxa_retencao:.1%}")
        w(f"- Dispositivos Legais: RAW={m.dispositivos_legais_raw} → Fmt={m.dispositivos_legais_formatado} ({m.taxa_preservacao_dispositivos:.1%})")
        w("")

    # Sumário por severidade
    w("## Sumário por Severidade\n")
    sev_icons = {"CRITICA": "🔴", "ALTA": "🟠", "MEDIA": "🟡", "BAIXA": "🟢"}
    for sev in ["CRITICA", "ALTA", "MEDIA", "BAIXA"]:
        count = report.summary.get("by_severity", {}).get(sev, 0)
        w(f"- {sev_icons.get(sev, '')} **{sev}**: {count}")
    w("")

    # Sumário por categoria
    by_cat = report.summary.get("by_category", {})
    if by_cat:
        w("## Sumário por Categoria\n")
        for cat, count in sorted(by_cat.items(), key=lambda x: -x[1]):
            w(f"- **{cat}**: {count}")
        w("")

    # HIL Recommendation
    hil = report.hil_recommendation
    if hil.pausar:
        w("## ⚠️ RECOMENDAÇÃO HIL: PAUSAR PARA REVISÃO\n")
        w(f"**Motivo:** {hil.motivo}")
        w(f"**Áreas críticas:** {', '.join(hil.areas_criticas)}")
        w("")

    # Findings
    if not findings:
        w("## Nenhum finding ativo\n")
    else:
        current_sev = None
        for finding in findings:
            if finding.severity != current_sev:
                current_sev = finding.severity
                icon = sev_icons.get(current_sev.value, "")
                w(f"\n## {icon} Findings — {current_sev.value}\n")

            verdict_badge = {
                "CONFIRMADO": "✅ CONFIRMADO",
                "PROVAVEL": "⚠️ PROVÁVEL",
                "SUSPEITO": "❓ SUSPEITO",
            }.get(finding.verdict.value, finding.verdict.value)

            sources_str = ", ".join(s.value for s in finding.sources)

            w(f"### {finding.title}")
            w(f"**[{verdict_badge}]** | Categoria: `{finding.category.value}` | Fontes: `{sources_str}` | ID: `{finding.id}`\n")

            if finding.detail:
                w(f"{finding.detail}\n")
            if finding.location:
                w(f"**Localização:** {finding.location}\n")
            if finding.trecho_raw:
                w(f"**Trecho RAW:**\n```\n{finding.trecho_raw[:400]}\n```\n")
            if finding.trecho_formatado:
                w(f"**Trecho Formatado:**\n```\n{finding.trecho_formatado[:400]}\n```\n")

            for corr in finding.corrections:
                auto_tag = " [AUTO-APLICÁVEL]" if corr.auto_applicable else ""
                w(f"**Correção sugerida{auto_tag}:** `{corr.action.value}`")
                if corr.current_text and corr.suggested_text:
                    w(f"- De: `{corr.current_text[:120]}`")
                    w(f"- Para: `{corr.suggested_text[:120]}`")
                elif corr.suggested_text:
                    w(f"- Sugestão: `{corr.suggested_text[:120]}`")
                w(f"- Confiança: {corr.confidence:.0%}\n")

            if finding.cross_refs:
                refs = ", ".join(f"`{cr}`" for cr in finding.cross_refs[:5])
                w(f"**Relacionado a:** {refs}\n")

            if finding.tags:
                tags_str = ", ".join(f"`{t}`" for t in finding.tags if not t.startswith("merged_into"))
                if tags_str:
                    w(f"**Tags:** {tags_str}\n")

            w("---\n")

    with open(output_path, "w", encoding="utf-8") as fp:
        fp.write("\n".join(lines))


# ---------------------------------------------------------------------------
# Comparação de Relatórios (para resume-hil)
# ---------------------------------------------------------------------------

def compare_reports(old: UnifiedReport, new: UnifiedReport) -> dict:
    """Compara dois relatórios e retorna delta de findings."""
    old_ids = {f.id for f in old.findings if f.verdict != FindingVerdict.FALSO_POSITIVO}
    new_ids = {f.id for f in new.findings if f.verdict != FindingVerdict.FALSO_POSITIVO}

    resolved = old_ids - new_ids
    persistent = old_ids & new_ids
    new_issues = new_ids - old_ids

    return {
        "resolved": sorted(resolved),
        "persistent": sorted(persistent),
        "new": sorted(new_issues),
        "resolved_count": len(resolved),
        "persistent_count": len(persistent),
        "new_count": len(new_issues),
    }
