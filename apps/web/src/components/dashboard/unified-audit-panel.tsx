"use client";

import { useState, useMemo, useCallback } from "react";
import {
  AlertCircle,
  AlertTriangle,
  BookOpenText,
  CheckCircle,
  ChevronDown,
  ChevronRight,
  ClipboardList,
  Edit3,
  FileWarning,
  HelpCircle,
  ListChecks,
  Loader2,
  ScanSearch,
  RefreshCw,
  Shield,
  ShieldCheck,
  ShieldAlert,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { cn } from "@/lib/utils";
import type {
  AuditSummary,
  AuditSummaryIssue,
  AuditModule,
  AuditActionableIssue,
} from "@/lib/audit-types";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface ValidationReport {
  approved?: boolean;
  score?: number;
  validated_at?: string;
  omissions?: string[];
  distortions?: string[];
  observations?: string;
}

interface AnalysisResult {
  total_issues?: number;
  requires_approval?: boolean;
  compression_ratio?: number;
  compression_warning?: string;
  pending_fixes?: unknown[];
}

interface UnifiedAuditPanelProps {
  auditSummary?: AuditSummary | null;
  auditIssues?: AuditActionableIssue[];
  selectedIssueIds?: Set<string> | string[];
  isApplying?: boolean;
  isRegenerating?: boolean;
  isAuditOutdated?: boolean;
  readOnly?: boolean;
  selectedModelLabel?: string;
  validationReport?: ValidationReport | null;
  analysisResult?: AnalysisResult | null;
  onToggleIssue?: (id: string) => void;
  onApplySelected?: () => void;
  onAutoApplyStructural?: () => void;
  onAutoApplyContent?: () => void;
  onRegenerate?: () => void;
  onFixDiagnosticIssue?: (issue: AuditSummaryIssue, moduleId: string) => void;
  onFixDiagnosticModule?: (issues: AuditSummaryIssue[], moduleId: string) => void;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const SEVERITY_COLORS: Record<string, string> = {
  critical: "bg-red-100 text-red-800 border-red-300",
  high: "bg-orange-100 text-orange-800 border-orange-300",
  warning: "bg-amber-100 text-amber-800 border-amber-300",
  medium: "bg-yellow-100 text-yellow-800 border-yellow-300",
  low: "bg-blue-100 text-blue-800 border-blue-300",
  info: "bg-gray-100 text-gray-700 border-gray-300",
};

const STATUS_ICON: Record<string, React.ReactNode> = {
  ok: <ShieldCheck className="h-4 w-4 text-emerald-600" />,
  warning: <ShieldAlert className="h-4 w-4 text-amber-600" />,
  error: <AlertCircle className="h-4 w-4 text-red-600" />,
  skipped: <Shield className="h-4 w-4 text-gray-400" />,
  info: <Shield className="h-4 w-4 text-blue-500" />,
};

const SOURCE_LABELS: Record<string, string> = {
  preventive_audit: "Auditoria preventiva",
  preventive_fidelity: "Auditoria preventiva",
  validation_fidelity: "Validação de fidelidade",
  structural_analysis: "Análise estrutural",
  legal_audit: "Auditoria legal",
  unknown: "Não classificado",
};

const FIX_TYPE_LABELS: Record<string, string> = {
  structural: "Estrutural",
  content: "Conteúdo",
};

function severityBadge(severity: string) {
  const cls = SEVERITY_COLORS[severity] || SEVERITY_COLORS.info;
  return (
    <span className={cn("text-[10px] px-1.5 py-0.5 rounded border font-medium", cls)}>
      {severity}
    </span>
  );
}

function scoreDisplay(score: number | null | undefined) {
  if (score == null || !Number.isFinite(score)) return "—";
  return `${Number(score).toFixed(1)}/10`;
}

function sourceDisplay(source: string | undefined): string {
  const normalized = (source || "unknown").trim().toLowerCase();
  return SOURCE_LABELS[normalized] || source || SOURCE_LABELS.unknown;
}

function hasRawEvidence(issue: AuditActionableIssue): boolean {
  const value = (issue as { raw_evidence?: unknown }).raw_evidence;
  if (Array.isArray(value)) return value.length > 0;
  if (typeof value === "string") return value.trim().length > 0;
  return Boolean(value);
}

function formatTimestamp(ts: string | undefined | null): string {
  if (!ts) return "—";
  try {
    const d = new Date(ts);
    if (isNaN(d.getTime())) return "—";
    return d.toLocaleString("pt-BR", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "—";
  }
}

// ---------------------------------------------------------------------------
// Score Card
// ---------------------------------------------------------------------------

function ScoreCard({ summary }: { summary: AuditSummary["summary"] }) {
  const diagnosticIssuesTotal = Number(
    summary.diagnostic_issues_total ?? summary.issues_total ?? 0,
  );
  const statusLabel =
    summary.status === "ok"
      ? "Aprovado"
      : summary.status === "warning"
        ? "Em revisão"
        : "Erro";
  const statusColor =
    summary.status === "ok"
      ? "text-emerald-700 bg-emerald-50 border-emerald-200"
      : summary.status === "warning"
        ? "text-amber-700 bg-amber-50 border-amber-200"
        : "text-red-700 bg-red-50 border-red-200";

  return (
    <div className={cn("rounded-lg border p-4 space-y-2", statusColor)}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {STATUS_ICON[summary.status] || STATUS_ICON.info}
          <span className="font-semibold text-sm">{statusLabel}</span>
        </div>
        <span className="text-2xl font-bold tabular-nums">{scoreDisplay(summary.score)}</span>
      </div>
      <div className="flex items-center gap-3 text-xs opacity-80">
        <span>
          {diagnosticIssuesTotal} diagnóstico{diagnosticIssuesTotal !== 1 ? "s" : ""}
        </span>
        {summary.false_positives_removed > 0 && (
          <span>{summary.false_positives_removed} falso{summary.false_positives_removed !== 1 ? "s" : ""} positivo{summary.false_positives_removed !== 1 ? "s" : ""} removido{summary.false_positives_removed !== 1 ? "s" : ""}</span>
        )}
        {summary.version && <span>v{summary.version}</span>}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Metrics Grid (3 cards)
// ---------------------------------------------------------------------------

function MetricsGrid({
  summary,
  validationReport,
  analysisResult,
  hilCount,
}: {
  summary: AuditSummary["summary"];
  validationReport?: ValidationReport | null;
  analysisResult?: AnalysisResult | null;
  hilCount: number;
}) {
  const diagnosticIssuesTotal = Number(
    summary.diagnostic_issues_total ?? summary.issues_total ?? 0,
  );
  const valScore = validationReport?.score;
  const valApproved = validationReport?.approved;
  const omCount = validationReport?.omissions?.length ?? 0;
  const distCount = validationReport?.distortions?.length ?? 0;
  const hilRequiresApproval = analysisResult?.requires_approval;

  return (
    <div className="grid gap-3 md:grid-cols-3">
      {/* Fidelidade */}
      <div className="rounded-lg border bg-background p-3 space-y-1">
        <div className="flex items-center justify-between text-[10px] font-semibold text-muted-foreground uppercase tracking-wide">
          <span className="flex items-center gap-1.5">
            <ListChecks className="h-3.5 w-3.5" />
            Fidelidade
          </span>
          {valApproved != null && (
            <Badge variant={valApproved ? "default" : "outline"} className="text-[9px] h-4">
              {valApproved ? "Aprovado" : "Revisão necessária"}
            </Badge>
          )}
        </div>
        <div className="font-bold text-xl tabular-nums">
          {valScore != null && Number.isFinite(valScore)
            ? `${Number(valScore).toFixed(1)}`
            : "—"}
          <span className="text-sm text-muted-foreground font-normal">/10</span>
        </div>
        <div className="text-[10px] text-muted-foreground">
          {validationReport?.validated_at
            ? `Validação: ${formatTimestamp(validationReport.validated_at)}`
            : "Sem validação"}
        </div>
      </div>

      {/* Diagnósticos */}
      <div className="rounded-lg border bg-background p-3 space-y-1">
        <div className="flex items-center justify-between text-[10px] font-semibold text-muted-foreground uppercase tracking-wide">
          <span className="flex items-center gap-1.5">
            <FileWarning className="h-3.5 w-3.5" />
            Diagnósticos
          </span>
          <Badge variant={diagnosticIssuesTotal > 0 ? "outline" : "secondary"} className="text-[9px] h-4">
            {diagnosticIssuesTotal} diagnóstico{diagnosticIssuesTotal !== 1 ? "s" : ""}
          </Badge>
        </div>
        <div className="font-bold text-xl tabular-nums">
          {diagnosticIssuesTotal}
        </div>
        <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
          {omCount > 0 && <span>{omCount} omiss{omCount !== 1 ? "ões" : "ão"}</span>}
          {distCount > 0 && <span>{distCount} distorç{distCount !== 1 ? "ões" : "ão"}</span>}
          {omCount === 0 && distCount === 0 && <span>Sem omissões ou distorções</span>}
        </div>
      </div>

      {/* Correções HIL */}
      <div className="rounded-lg border bg-background p-3 space-y-1">
        <div className="flex items-center justify-between text-[10px] font-semibold text-muted-foreground uppercase tracking-wide">
          <span className="flex items-center gap-1.5">
            <ClipboardList className="h-3.5 w-3.5" />
            Correções HIL
          </span>
          <Badge
            variant={hilCount > 0 ? "destructive" : "secondary"}
            className="text-[9px] h-4"
          >
            {hilCount > 0 ? `${hilCount} pendente${hilCount !== 1 ? "s" : ""}` : "ok"}
          </Badge>
        </div>
        <div className="font-bold text-xl tabular-nums">
          {hilCount}
        </div>
        <div className="text-[10px] text-muted-foreground">
          {hilRequiresApproval ? "Aprovação necessária" : "Nenhuma aprovação pendente"}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Status Bar
// ---------------------------------------------------------------------------

function StatusBar({
  validationReport,
  analysisResult,
  generatedAt,
}: {
  validationReport?: ValidationReport | null;
  analysisResult?: AnalysisResult | null;
  generatedAt?: string;
}) {
  const approved = validationReport?.approved;
  const ratio = analysisResult?.compression_ratio;
  const ratioWarning = analysisResult?.compression_warning;
  const hilStatus = analysisResult?.requires_approval ? "pendente" : "ok";

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-full border bg-muted/30 px-4 py-2 text-[11px]">
      <div className="flex flex-wrap items-center gap-2">
        {approved != null && (
          <Badge variant={approved ? "default" : "outline"}>
            {approved ? "Documento aprovado" : "Revisão necessária"}
          </Badge>
        )}
        <span className="text-muted-foreground">
          Validação: {formatTimestamp(validationReport?.validated_at)}
        </span>
      </div>
      <div className="flex flex-wrap items-center gap-3 text-muted-foreground">
        <span>HIL: {hilStatus}</span>
        {ratio != null && Number.isFinite(ratio) && (
          <span className={ratioWarning ? (ratio < 0.7 ? "text-red-600 font-medium" : "text-yellow-700") : ""}>
            Taxa: {Math.round(ratio * 100)}%
            {ratioWarning && ` ${ratio < 0.7 ? "!!" : "!"}`}
          </span>
        )}
        {generatedAt && (
          <span>Auditoria: {formatTimestamp(generatedAt)}</span>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Audit Read Guide
// ---------------------------------------------------------------------------

function AuditReadGuide() {
  return (
    <div className="rounded-lg border bg-muted/30 p-3 space-y-2">
      <div className="flex items-center gap-2 text-sm font-medium">
        <HelpCircle className="h-4 w-4 text-muted-foreground" />
        Como ler esta auditoria
      </div>
      <ul className="text-xs text-muted-foreground space-y-1.5">
        <li className="flex items-start gap-2">
          <ScanSearch className="h-3.5 w-3.5 mt-0.5" />
          <span>
            <strong>Score consolidado</strong>: visão geral de risco (quanto menor, mais revisão humana necessária).
          </span>
        </li>
        <li className="flex items-start gap-2">
          <BookOpenText className="h-3.5 w-3.5 mt-0.5" />
          <span>
            <strong>Módulos</strong>: itens de diagnóstico (informativos) vindos das camadas preventiva, validação, estrutural e legal.
          </span>
        </li>
        <li className="flex items-start gap-2">
          <CheckCircle className="h-3.5 w-3.5 mt-0.5" />
          <span>
            <strong>Correções</strong>: diagnósticos e HIL podem ser enviados para correção por IA (individual, selecionados ou módulo inteiro), sempre com diff de confirmação antes de aplicar.
          </span>
        </li>
      </ul>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Module Breakdown
// ---------------------------------------------------------------------------

function DiagnosticEvidencePanel({
  issue,
}: {
  issue: AuditSummaryIssue;
}) {
  return (
    <div className="mt-2 pl-4 space-y-2 text-[11px] border-l-2 border-muted">
      {issue.evidence_raw && (
        <div>
          <div className="font-semibold text-muted-foreground mb-1">Evidência RAW:</div>
          <div className="bg-amber-50 dark:bg-amber-950/20 rounded p-2 whitespace-pre-wrap font-mono text-[10px] border border-amber-200 max-h-48 overflow-y-auto">
            {issue.evidence_raw}
          </div>
        </div>
      )}
      {issue.evidence_formatted && (
        <div>
          <div className="font-semibold text-muted-foreground mb-1">Trecho Formatado:</div>
          <div className="bg-blue-50 dark:bg-blue-950/20 rounded p-2 whitespace-pre-wrap text-[10px] border border-blue-200 max-h-48 overflow-y-auto">
            {issue.evidence_formatted}
          </div>
        </div>
      )}
      {!issue.evidence_raw && !issue.evidence_formatted && issue.raw_item && (
        <div>
          <div className="font-semibold text-muted-foreground mb-1">Dados brutos:</div>
          <pre className="bg-muted/40 rounded p-2 overflow-x-auto text-[10px] font-mono max-h-48 overflow-y-auto">
            {JSON.stringify(issue.raw_item, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}

function hasEvidence(issue: AuditSummaryIssue): boolean {
  return Boolean(issue.has_evidence || issue.evidence_raw || issue.evidence_formatted || issue.raw_item);
}

function ModuleBreakdown({
  modules,
  validationReport,
  onFixDiagnosticIssue,
  onFixDiagnosticModule,
  isApplying,
  readOnly,
}: {
  modules: AuditModule[];
  validationReport?: ValidationReport | null;
  onFixDiagnosticIssue?: (issue: AuditSummaryIssue, moduleId: string) => void;
  onFixDiagnosticModule?: (issues: AuditSummaryIssue[], moduleId: string) => void;
  isApplying?: boolean;
  readOnly?: boolean;
}) {
  const [expandedDiagIds, setExpandedDiagIds] = useState<Set<string>>(new Set());
  const [selectedDiagIds, setSelectedDiagIds] = useState<Set<string>>(new Set());

  const issueKey = (moduleId: string, idx: number) => `${moduleId}_${idx}`;

  const toggleDiagExpand = useCallback((key: string) => {
    setExpandedDiagIds((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }, []);

  const toggleDiagSelection = useCallback((key: string) => {
    setSelectedDiagIds((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }, []);

  const toggleModuleSelection = useCallback((moduleId: string, issueCount: number, select: boolean) => {
    setSelectedDiagIds((prev) => {
      const next = new Set(prev);
      for (let idx = 0; idx < issueCount; idx += 1) {
        const key = issueKey(moduleId, idx);
        if (select) next.add(key);
        else next.delete(key);
      }
      return next;
    });
  }, []);

  if (!modules?.length) return null;

  const omCount = validationReport?.omissions?.length ?? 0;
  const distCount = validationReport?.distortions?.length ?? 0;

  return (
    <div className="space-y-1">
      <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Módulos de Diagnóstico</h4>
      <Accordion type="multiple" className="space-y-1">
        {modules.map((mod) => {
          const issueCount = mod.issues?.length || 0;
          const isValidation = mod.id === "validation_fidelity";
          const isCoverage = mod.id === "coverage_check";
          const evidenceCount = mod.issues?.filter(hasEvidence).length || 0;
          const selectedIssues = mod.issues.filter((_, idx) => selectedDiagIds.has(issueKey(mod.id, idx)));
          const selectedCount = selectedIssues.length;
          const allSelected = issueCount > 0 && selectedCount === issueCount;

          return (
            <AccordionItem key={mod.id} value={mod.id} className="border rounded-md">
              <AccordionTrigger className="px-3 py-2 text-sm hover:no-underline">
                <div className="flex items-center gap-2 flex-1">
                  {STATUS_ICON[mod.status] || STATUS_ICON.info}
                  <span className="font-medium">{mod.label}</span>
                  {isValidation && (omCount > 0 || distCount > 0) && (
                    <div className="flex items-center gap-1 ml-1">
                      {omCount > 0 && (
                        <span className="text-[9px] px-1.5 py-0.5 rounded border bg-red-50 text-red-700 border-red-200">
                          {omCount} omiss.
                        </span>
                      )}
                      {distCount > 0 && (
                        <span className="text-[9px] px-1.5 py-0.5 rounded border bg-orange-50 text-orange-700 border-orange-200">
                          {distCount} dist.
                        </span>
                      )}
                    </div>
                  )}
                  {mod.score != null && (
                    <span className="text-xs text-muted-foreground ml-auto mr-2">
                      {scoreDisplay(mod.score)}
                    </span>
                  )}
                  {issueCount > 0 && (
                    <Badge variant="secondary" className="text-[10px] h-5">
                      {issueCount} diag.
                    </Badge>
                  )}
                  {evidenceCount > 0 && (
                    <span className="text-[9px] px-1.5 py-0.5 rounded border bg-emerald-50 text-emerald-700 border-emerald-200">
                      {evidenceCount} c/ evidência
                    </span>
                  )}
                  {selectedCount > 0 && (
                    <span className="text-[9px] px-1.5 py-0.5 rounded border bg-blue-50 text-blue-700 border-blue-200">
                      {selectedCount} sel.
                    </span>
                  )}
                </div>
              </AccordionTrigger>
              <AccordionContent className="px-3 pb-3">
                {mod.error && (
                  <p className="text-xs text-red-600 mb-2">{mod.error}</p>
                )}
                {!readOnly && issueCount > 0 && (
                  <div className="mb-2 flex flex-wrap justify-end gap-1.5">
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-6 text-[11px]"
                      disabled={isApplying}
                      onClick={() => toggleModuleSelection(mod.id, issueCount, !allSelected)}
                    >
                      {allSelected ? "Limpar seleção" : "Selecionar todos"}
                    </Button>
                    {onFixDiagnosticModule && selectedCount > 0 && (
                      <Button
                        size="sm"
                        variant="outline"
                        className="h-6 text-[11px]"
                        disabled={isApplying}
                        onClick={() => onFixDiagnosticModule(selectedIssues, mod.id)}
                      >
                        <Edit3 className="h-3 w-3 mr-1" />
                        Corrigir selecionados ({selectedCount})
                      </Button>
                    )}
                    {onFixDiagnosticModule && issueCount > 1 && (
                      <Button
                        size="sm"
                        variant="outline"
                        className="h-6 text-[11px]"
                        disabled={isApplying}
                        onClick={() => onFixDiagnosticModule(mod.issues, mod.id)}
                      >
                        <Edit3 className="h-3 w-3 mr-1" />
                        Corrigir módulo ({issueCount})
                      </Button>
                    )}
                  </div>
                )}
                {!readOnly && onFixDiagnosticModule && issueCount === 1 && (
                  <div className="mb-2 flex justify-end">
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-6 text-[11px]"
                      disabled={isApplying}
                      onClick={() => onFixDiagnosticModule(mod.issues, mod.id)}
                    >
                      <Edit3 className="h-3 w-3 mr-1" />
                      Corrigir módulo ({issueCount})
                    </Button>
                  </div>
                )}
                {issueCount === 0 ? (
                  <p className="text-xs text-muted-foreground">Nenhum item de diagnóstico detectado.</p>
                ) : isCoverage ? (
                  <div className="space-y-2">
                    <div className="text-xs text-muted-foreground space-y-1 whitespace-pre-wrap font-mono bg-muted/40 rounded p-2">
                      {mod.issues.map((issue, idx) => {
                        const expandKey = issueKey(mod.id, idx);
                        const isSelected = selectedDiagIds.has(expandKey);
                        const isExpanded = expandedDiagIds.has(expandKey);
                        return (
                          <div key={idx}>
                            <div className="flex items-start gap-1.5">
                              {!readOnly && (
                                <input
                                  type="checkbox"
                                  className="mt-[2px] h-3.5 w-3.5 accent-blue-600 shrink-0"
                                  checked={isSelected}
                                  onChange={() => toggleDiagSelection(expandKey)}
                                />
                              )}
                              <div className="flex-1 min-w-0">
                                <div
                                  className={cn("cursor-pointer hover:bg-muted/60 rounded px-1 -mx-1", isExpanded && "bg-muted/60")}
                                  onClick={() => hasEvidence(issue) && toggleDiagExpand(expandKey)}
                                >
                                  <span>{issue.description}</span>
                                  {hasEvidence(issue) && (
                                    <span className="inline-flex ml-1 text-[9px] text-emerald-600">[evidência]</span>
                                  )}
                                </div>
                              </div>
                            </div>
                            {!readOnly && onFixDiagnosticIssue && (
                              <div className="mt-1 pl-5">
                                <Button
                                  size="sm"
                                  variant="outline"
                                  className="text-[11px] h-6"
                                  disabled={isApplying}
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    onFixDiagnosticIssue(issue, mod.id);
                                  }}
                                >
                                  <Edit3 className="h-3 w-3 mr-1" />
                                  Corrigir com IA
                                </Button>
                              </div>
                            )}
                            {isExpanded && (
                              <DiagnosticEvidencePanel
                                issue={issue}
                              />
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ) : (
                  <ul className="space-y-1.5">
                    {mod.issues.map((issue, idx) => {
                      const expandKey = issueKey(mod.id, idx);
                      const isSelected = selectedDiagIds.has(expandKey);
                      const isExpanded = expandedDiagIds.has(expandKey);
                      const showExpand = hasEvidence(issue);

                      return (
                        <li key={idx} className={cn("rounded-md border p-2 text-xs transition-colors", isExpanded && "bg-muted/30")}>
                          <div className="flex items-start gap-1.5">
                            {!readOnly && (
                              <input
                                type="checkbox"
                                className="mt-0.5 h-3.5 w-3.5 accent-blue-600 shrink-0"
                                checked={isSelected}
                                onChange={() => toggleDiagSelection(expandKey)}
                              />
                            )}
                            {severityBadge(issue.severity)}
                            <span className="text-muted-foreground">[{issue.category}]</span>
                            <span className="flex-1">{issue.description}</span>
                            {issue.has_evidence && (
                              <span className="text-[9px] px-1.5 py-0.5 rounded border bg-emerald-50 text-emerald-700 border-emerald-200 shrink-0">
                                Evidência
                              </span>
                            )}
                            {showExpand && (
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  toggleDiagExpand(expandKey);
                                }}
                                className="p-0.5 text-muted-foreground hover:text-foreground shrink-0"
                              >
                                {isExpanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
                              </button>
                            )}
                          </div>
                          {!readOnly && onFixDiagnosticIssue && (
                            <div className="mt-1.5 pl-5">
                              <Button
                                size="sm"
                                variant="outline"
                                className="text-[11px] h-6"
                                disabled={isApplying}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  onFixDiagnosticIssue(issue, mod.id);
                                }}
                              >
                                <Edit3 className="h-3 w-3 mr-1" />
                                Corrigir com IA
                              </Button>
                            </div>
                          )}
                          {isExpanded && (
                            <DiagnosticEvidencePanel
                              issue={issue}
                            />
                          )}
                        </li>
                      );
                    })}
                  </ul>
                )}
              </AccordionContent>
            </AccordionItem>
          );
        })}
      </Accordion>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Actionable Issues (HIL)
// ---------------------------------------------------------------------------

function ActionableIssuesList({
  issues,
  selectedSet,
  isApplying,
  readOnly,
  selectedModelLabel,
  onToggleIssue,
  onApplySelected,
  onAutoApplyStructural,
  onAutoApplyContent,
}: {
  issues: AuditActionableIssue[];
  selectedSet: Set<string>;
  isApplying: boolean;
  readOnly: boolean;
  selectedModelLabel: string;
  onToggleIssue?: (id: string) => void;
  onApplySelected?: () => void;
  onAutoApplyStructural?: () => void;
  onAutoApplyContent?: () => void;
}) {
  const [fixTypeFilter, setFixTypeFilter] = useState<string>("all");
  const [severityFilter, setSeverityFilter] = useState<string>("all");
  const [categoryFilter, setCategoryFilter] = useState<string>("all");
  const [sourceFilter, setSourceFilter] = useState<string>("all");
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());

  const structuralCount = issues.filter((i) => i.fix_type === "structural").length;
  const contentCount = issues.length - structuralCount;

  const categories = useMemo(() => {
    const cats = new Set<string>();
    issues.forEach((i) => cats.add(i.type || "other"));
    return Array.from(cats).sort();
  }, [issues]);

  const sources = useMemo(() => {
    const srcs = new Set<string>();
    issues.forEach((i) => srcs.add(i.source || i.origin || "unknown"));
    return Array.from(srcs).sort();
  }, [issues]);

  const severities = useMemo(() => {
    const levels = new Set<string>();
    issues.forEach((i) => levels.add((i.severity || "info").toLowerCase()));
    return Array.from(levels).sort();
  }, [issues]);

  const severityCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    issues.forEach((issue) => {
      const level = (issue.severity || "info").toLowerCase();
      counts[level] = (counts[level] || 0) + 1;
    });
    return counts;
  }, [issues]);

  const filtered = useMemo(() => {
    const filteredIssues = issues.filter((issue) => {
      const issueSeverity = (issue.severity || "info").toLowerCase();
      const issueCategory = issue.type || "other";
      const issueSource = issue.source || issue.origin || "unknown";

      if (fixTypeFilter === "structural" && issue.fix_type !== "structural") return false;
      if (fixTypeFilter === "content" && issue.fix_type === "structural") return false;
      if (severityFilter !== "all" && issueSeverity !== severityFilter) return false;
      if (categoryFilter !== "all" && issueCategory !== categoryFilter) return false;
      if (sourceFilter !== "all" && issueSource !== sourceFilter) return false;
      return true;
    });
    return filteredIssues;
  }, [issues, fixTypeFilter, severityFilter, categoryFilter, sourceFilter]);

  const hasActiveFilters =
    fixTypeFilter !== "all" ||
    severityFilter !== "all" ||
    categoryFilter !== "all" ||
    sourceFilter !== "all";

  const toggleExpand = useCallback((id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  if (issues.length === 0) {
    return (
      <div className="text-center py-6 text-muted-foreground text-sm">
        <CheckCircle className="h-8 w-8 mx-auto mb-2 text-emerald-500" />
        Nenhuma correção pendente.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
          Correções HIL Aplicáveis ({issues.length})
        </h4>
        <div className="flex items-center gap-1.5">
          {structuralCount > 0 && onAutoApplyStructural && (
            <Button
              size="sm"
              variant="outline"
              onClick={onAutoApplyStructural}
              disabled={isApplying || readOnly}
              className="text-xs h-7"
            >
              Estruturais ({structuralCount})
            </Button>
          )}
          {contentCount > 0 && onAutoApplyContent && (
            <Button
              size="sm"
              variant="outline"
              onClick={onAutoApplyContent}
              disabled={isApplying || readOnly}
              className="text-xs h-7"
            >
              Conteúdo ({contentCount})
            </Button>
          )}
        </div>
      </div>

      <p className="text-xs text-muted-foreground">
        Correções de conteúdo usam IA ({selectedModelLabel}); estruturais são determinísticas.
      </p>

      {/* Filter chips */}
      <div className="flex flex-wrap gap-1">
        {["all", "structural", "content"].map((f) => (
          <button
            key={f}
            onClick={() => setFixTypeFilter(f)}
            className={cn(
              "text-[10px] px-2 py-0.5 rounded-full border transition-colors",
              fixTypeFilter === f
                ? "bg-foreground text-background border-foreground"
                : "bg-background text-muted-foreground border-border hover:border-foreground/30"
            )}
          >
            {f === "all" ? "Todos" : f === "structural" ? "Estrutural" : "Conteúdo"}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
        <label className="text-[11px] text-muted-foreground">
          Severidade
          <select
            className="mt-1 w-full h-8 rounded border bg-background px-2 text-xs"
            value={severityFilter}
            onChange={(e) => setSeverityFilter(e.target.value)}
          >
            <option value="all">Todas</option>
            {severities.map((level) => (
              <option key={level} value={level}>
                {level}
              </option>
            ))}
          </select>
        </label>
        <label className="text-[11px] text-muted-foreground">
          Categoria
          <select
            className="mt-1 w-full h-8 rounded border bg-background px-2 text-xs"
            value={categoryFilter}
            onChange={(e) => setCategoryFilter(e.target.value)}
          >
            <option value="all">Todas</option>
            {categories.map((category) => (
              <option key={category} value={category}>
                {category}
              </option>
            ))}
          </select>
        </label>
        <label className="text-[11px] text-muted-foreground">
          Módulo/Fonte
          <select
            className="mt-1 w-full h-8 rounded border bg-background px-2 text-xs"
            value={sourceFilter}
            onChange={(e) => setSourceFilter(e.target.value)}
          >
            <option value="all">Todos</option>
            {sources.map((source) => (
              <option key={source} value={source}>
                {source}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="flex flex-wrap items-center gap-1.5">
        {Object.entries(severityCounts)
          .sort((a, b) => a[0].localeCompare(b[0]))
          .map(([level, count]) => (
            <span key={level} className="text-[10px] px-1.5 py-0.5 rounded border bg-background">
              {level}: <strong>{count}</strong>
            </span>
          ))}
        <span className="text-[10px] text-muted-foreground ml-auto">
          Exibindo {filtered.length} de {issues.length} correç{issues.length === 1 ? "ão" : "ões"}
        </span>
        {hasActiveFilters && (
          <Button
            size="sm"
            variant="ghost"
            className="h-6 px-2 text-[10px]"
            onClick={() => {
              setFixTypeFilter("all");
              setSeverityFilter("all");
              setCategoryFilter("all");
              setSourceFilter("all");
            }}
          >
            Limpar filtros
          </Button>
        )}
      </div>

      {/* Issue list */}
      <ul className="space-y-1.5 max-h-[400px] overflow-y-auto">
        {filtered.length === 0 && (
          <li className="rounded-md border border-dashed p-3 text-xs text-muted-foreground">
            Nenhum item corresponde aos filtros atuais.
          </li>
        )}
        {filtered.map((issue) => {
          const id = issue.id;
          const selected = selectedSet.has(id);
          const expanded = expandedIds.has(id);
          const issueSource = sourceDisplay(issue.source || issue.origin);
          const fixTypeLabel = FIX_TYPE_LABELS[(issue.fix_type || "content").toLowerCase()] || "Conteúdo";

          return (
            <li
              key={id}
              className={cn(
                "rounded-md border p-2 text-xs transition-colors cursor-pointer",
                selected ? "bg-blue-50 border-blue-300" : "bg-background border-border hover:bg-muted/40"
              )}
            >
              <div className="flex items-start gap-2" onClick={() => !readOnly && onToggleIssue?.(id)}>
                {!readOnly && onToggleIssue && (
                  <input
                    type="checkbox"
                    checked={selected}
                    readOnly
                    className="mt-0.5 h-3.5 w-3.5 accent-blue-600 cursor-pointer"
                  />
                )}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5 flex-wrap mb-0.5">
                    {severityBadge(issue.severity)}
                    <span className="text-[10px] text-muted-foreground">{fixTypeLabel}</span>
                    {hasRawEvidence(issue) && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded border bg-emerald-50 text-emerald-700 border-emerald-200">
                        RAW disponível
                      </span>
                    )}
                  </div>
                  <p className="text-foreground leading-snug">{issue.description}</p>
                  <p className="mt-1 text-[10px] text-muted-foreground">
                    Categoria: {issue.type || "other"} | Fonte: {issueSource}
                  </p>
                </div>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    toggleExpand(id);
                  }}
                  className="p-0.5 text-muted-foreground hover:text-foreground shrink-0"
                >
                  {expanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
                </button>
              </div>
              {expanded && (
                <div className="mt-2 pl-6 space-y-1 text-[11px] text-muted-foreground">
                  {issue.suggestion && <p><strong>Sugestão:</strong> {issue.suggestion}</p>}
                  {issue.reference && <p><strong>Referência:</strong> {issue.reference}</p>}
                  {issue.source && <p><strong>Fonte:</strong> {issueSource}</p>}
                </div>
              )}
            </li>
          );
        })}
      </ul>

      {/* Apply button */}
      {!readOnly && onApplySelected && selectedSet.size > 0 && (
        <Button
          onClick={onApplySelected}
          disabled={isApplying}
          className="w-full"
          size="sm"
        >
          {isApplying ? (
            <>
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              Aplicando...
            </>
          ) : (
            `Aplicar ${selectedSet.size} correç${selectedSet.size === 1 ? "ão" : "ões"} selecionada${selectedSet.size === 1 ? "" : "s"}`
          )}
        </Button>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------

export function UnifiedAuditPanel({
  auditSummary,
  auditIssues = [],
  selectedIssueIds,
  isApplying = false,
  isRegenerating = false,
  isAuditOutdated = false,
  readOnly = false,
  selectedModelLabel = "IA",
  validationReport,
  analysisResult,
  onToggleIssue,
  onApplySelected,
  onAutoApplyStructural,
  onAutoApplyContent,
  onRegenerate,
  onFixDiagnosticIssue,
  onFixDiagnosticModule,
}: UnifiedAuditPanelProps) {
  const selectedSet =
    selectedIssueIds instanceof Set ? selectedIssueIds : new Set(selectedIssueIds || []);

  const summary = auditSummary?.summary;
  const modules = auditSummary?.modules;
  const diagnosticIssuesCount = useMemo(
    () =>
      (modules || []).reduce(
        (acc, mod) => acc + (Array.isArray(mod.issues) ? mod.issues.length : 0),
        0,
      ),
    [modules],
  );

  if (!summary) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-muted-foreground text-sm gap-3">
        <Shield className="h-10 w-10 opacity-40" />
        <p>Auditoria não disponível para este job.</p>
        {onRegenerate && (
          <Button size="sm" variant="outline" onClick={onRegenerate} disabled={isRegenerating}>
            {isRegenerating ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <RefreshCw className="h-4 w-4 mr-2" />}
            Gerar Auditoria
          </Button>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Outdated banner */}
      {isAuditOutdated && (
        <div className="flex items-center gap-2 bg-amber-50 border border-amber-200 text-amber-800 rounded-md px-3 py-2 text-xs">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          <span className="flex-1">O conteúdo foi alterado desde a última auditoria.</span>
          {onRegenerate && (
            <Button size="sm" variant="outline" onClick={onRegenerate} disabled={isRegenerating} className="text-xs h-6">
              {isRegenerating ? <Loader2 className="h-3 w-3 mr-1 animate-spin" /> : <RefreshCw className="h-3 w-3 mr-1" />}
              Regenerar
            </Button>
          )}
        </div>
      )}

      {/* Score Card */}
      <ScoreCard summary={summary} />

      {/* Metrics Grid */}
      <MetricsGrid
        summary={summary}
        validationReport={validationReport}
        analysisResult={analysisResult}
        hilCount={auditIssues.length}
      />

      {/* Status Bar */}
      <StatusBar
        validationReport={validationReport}
        analysisResult={analysisResult}
        generatedAt={summary.generated_at}
      />

      <AuditReadGuide />

      <div className="grid gap-3 md:grid-cols-2">
        <div className="rounded-lg border bg-muted/20 p-3 space-y-1">
          <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
            Issues Informativos (Diagnóstico)
          </div>
          <div className="text-xl font-bold tabular-nums">{diagnosticIssuesCount}</div>
          <p className="text-xs text-muted-foreground">
            Itens de análise dos módulos. Não aplicam patch automaticamente no documento.
          </p>
        </div>
        <div className="rounded-lg border bg-muted/20 p-3 space-y-1">
          <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
            Correções HIL Aplicáveis
          </div>
          <div className="text-xl font-bold tabular-nums">{auditIssues.length}</div>
          <p className="text-xs text-muted-foreground">
            Itens com ação disponível no fluxo HIL (individual ou em lote).
          </p>
        </div>
      </div>

      {/* Regenerate button (when not outdated) */}
      {!isAuditOutdated && onRegenerate && (
        <div className="flex justify-end">
          <Button
            size="sm"
            variant="ghost"
            onClick={onRegenerate}
            disabled={isRegenerating}
            className="text-xs h-7 text-muted-foreground"
          >
            {isRegenerating ? <Loader2 className="h-3 w-3 mr-1 animate-spin" /> : <RefreshCw className="h-3 w-3 mr-1" />}
            Regenerar auditoria
          </Button>
        </div>
      )}

      {/* Modules */}
      {modules && modules.length > 0 && (
        <ModuleBreakdown
          modules={modules}
          validationReport={validationReport}
          onFixDiagnosticIssue={onFixDiagnosticIssue}
          onFixDiagnosticModule={onFixDiagnosticModule}
          isApplying={isApplying}
          readOnly={readOnly}
        />
      )}

      {/* Actionable Issues */}
      <ActionableIssuesList
        issues={auditIssues}
        selectedSet={selectedSet}
        isApplying={isApplying}
        readOnly={readOnly}
        selectedModelLabel={selectedModelLabel}
        onToggleIssue={onToggleIssue}
        onApplySelected={onApplySelected}
        onAutoApplyStructural={onAutoApplyStructural}
        onAutoApplyContent={onAutoApplyContent}
      />
    </div>
  );
}
