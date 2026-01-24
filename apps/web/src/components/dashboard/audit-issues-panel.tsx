"use client";

import { AlertCircle, AlertTriangle, CheckCircle, Loader2, ChevronDown, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { HilIssue } from "@/lib/preventive-hil";
import { diffLines } from 'diff';
import { useState } from "react";
import { cn } from "@/lib/utils";

export interface AutoAppliedSummary {
    structural: string[];
    content: string[];
    total: number;
}

export interface HilDiagnostics {
    contentChanged?: boolean | null;
    contentError?: string | null;
    contentChange?: {
        before_chars?: number;
        after_chars?: number;
    } | null;
    evidence?: Array<{
        issueId?: string;
        reference?: string;
        suggestedSection?: string;
        snippet?: string;
    }>;
}

function PatchPreview({ original, replacement }: { original: string; replacement: string }) {
    if (!replacement) return null;

    // Simple heuristic to avoid showing diff for generic instructions
    if (replacement.length < 10 || replacement.toLowerCase().startsWith('revisar')) {
        return <div className="text-xs text-gray-500 italic">Sugestão: {replacement}</div>;
    }

    try {
        const diff = diffLines(original || "", replacement);
        return (
            <div className="text-xs font-mono bg-white p-2 border rounded overflow-x-auto whitespace-pre-wrap">
                {diff.map((part, i) => (
                    <span
                        key={i}
                        className={cn(
                            part.added ? 'bg-green-100 text-green-800 decoration-clone' :
                                part.removed ? 'bg-red-50 text-red-800 line-through decoration-clone' :
                                    'text-gray-500'
                        )}
                    >
                        {part.value}
                    </span>
                ))}
            </div>
        );
    } catch (e) {
        return <div className="text-xs text-red-500">Erro ao gerar preview do patch.</div>;
    }
}

interface AuditIssuesPanelProps {
    issues?: HilIssue[];
    selectedIssueIds?: Set<string> | string[];
    selectedModelLabel?: string;
    hasRawForHil?: boolean;
    isApplying?: boolean;
    isAuditOutdated?: boolean;
    autoAppliedSummary?: AutoAppliedSummary | null;
    hilDiagnostics?: HilDiagnostics | null;
    readOnly?: boolean;
    onToggleIssue?: (id: string) => void;
    onApplySelected?: () => void;
    onAutoApplyStructural?: () => void;
    onAutoApplyContent?: () => void;
    onReviewIssue?: (issue: HilIssue) => void;
}

const resolveIssueId = (issue: HilIssue, idx: number) => {
    return issue?.id || issue?.fingerprint || issue?.key || `${issue?.type || "issue"}-${idx}`;
};

export function AuditIssuesPanel({
    issues = [],
    selectedIssueIds,
    selectedModelLabel,
    hasRawForHil = false,
    isApplying = false,
    isAuditOutdated = false,
    autoAppliedSummary,
    hilDiagnostics,
    readOnly = false,
    onToggleIssue,
    onApplySelected,
    onAutoApplyStructural,
    onAutoApplyContent,
    onReviewIssue,
}: AuditIssuesPanelProps) {
    const selectedSet =
        selectedIssueIds instanceof Set ? selectedIssueIds : new Set(selectedIssueIds || []);
    const modelLabel = selectedModelLabel || "IA";
    const structuralIssueCount = issues.filter((i) => i?.fix_type === "structural").length;
    const contentIssueCount = issues.length - structuralIssueCount;
    const allowSelection = !readOnly && typeof onToggleIssue === "function";
    const allowApply = !readOnly && typeof onApplySelected === "function";
    const showAutoApply = Boolean(onAutoApplyStructural || onAutoApplyContent);

    // State to track expanded issues for details
    const [expandedIssues, setExpandedIssues] = useState<Set<string>>(new Set());

    const toggleExpand = (id: string, e: React.MouseEvent) => {
        e.preventDefault();
        e.stopPropagation();
        setExpandedIssues(prev => {
            const next = new Set(prev);
            if (next.has(id)) next.delete(id);
            else next.add(id);
            return next;
        });
    };

    const descriptionNode = allowApply ? (
        <>
            Selecione os issues que deseja corrigir. Issues <strong>estruturais</strong> são corrigidos localmente; issues de{" "}
            <strong>conteúdo</strong> usam IA ({modelLabel}).
        </>
    ) : (
        "Visualize os issues detectados pela auditoria."
    );

    return (
        <div className="space-y-4">
            {autoAppliedSummary && autoAppliedSummary.total > 0 && (
                <div className="bg-emerald-50 border border-emerald-300 rounded-lg p-4">
                    <div className="flex items-start justify-between mb-2">
                        <h3 className="font-semibold text-emerald-900 flex items-center gap-2">
                            <CheckCircle className="h-5 w-5 text-emerald-600" />
                            Correções Aplicadas
                        </h3>
                        {isAuditOutdated && (
                            <span className="text-xs px-2 py-1 bg-orange-100 text-orange-700 rounded-md flex items-center gap-1">
                                <AlertTriangle className="h-3 w-3" />
                                Auditoria desatualizada
                            </span>
                        )}
                        {!isAuditOutdated && issues.length === 0 && (
                            <span className="text-xs px-2 py-1 bg-green-100 text-green-700 rounded-md flex items-center gap-1">
                                <CheckCircle className="h-3 w-3" />
                                Auditoria atualizada
                            </span>
                        )}
                    </div>
                    <div className="space-y-3">
                        <div className="flex gap-2 text-sm flex-wrap">
                            {autoAppliedSummary.structural.length > 0 && (
                                <span className="px-2 py-1 bg-purple-100 text-purple-800 rounded-md text-xs font-medium">
                                    🔧 {autoAppliedSummary.structural.length} Estrutural(is)
                                </span>
                            )}
                            {autoAppliedSummary.content.length > 0 && (
                                <span className="px-2 py-1 bg-blue-100 text-blue-800 rounded-md text-xs font-medium">
                                    🤖 {autoAppliedSummary.content.length} Conteúdo (IA)
                                </span>
                            )}
                            <span className="text-xs text-emerald-700 self-center">
                                Total: {autoAppliedSummary.total} correção(ões)
                            </span>
                        </div>

                        {autoAppliedSummary.structural.length > 0 && (
                            <details className="text-xs">
                                <summary className="cursor-pointer text-emerald-800 font-medium hover:text-emerald-900">
                                    Ver correções estruturais ({autoAppliedSummary.structural.length})
                                </summary>
                                <ul className="mt-2 ml-4 space-y-1 text-emerald-700 list-disc">
                                    {autoAppliedSummary.structural.slice(0, 20).map((fix, idx) => (
                                        <li key={idx}>{fix}</li>
                                    ))}
                                    {autoAppliedSummary.structural.length > 20 && (
                                        <li className="text-emerald-600 italic">
                                            ... e mais {autoAppliedSummary.structural.length - 20} correções
                                        </li>
                                    )}
                                </ul>
                            </details>
                        )}

                        {autoAppliedSummary.content.length > 0 && (
                            <details className="text-xs">
                                <summary className="cursor-pointer text-emerald-800 font-medium hover:text-emerald-900">
                                    Ver correções de conteúdo ({autoAppliedSummary.content.length})
                                </summary>
                                <ul className="mt-2 ml-4 space-y-1 text-emerald-700 list-disc">
                                    {autoAppliedSummary.content.slice(0, 20).map((fix, idx) => (
                                        <li key={idx}>{fix}</li>
                                    ))}
                                    {autoAppliedSummary.content.length > 20 && (
                                        <li className="text-emerald-600 italic">
                                            ... e mais {autoAppliedSummary.content.length - 20} correções
                                        </li>
                                    )}
                                </ul>
                            </details>
                        )}
                    </div>
                </div>
            )}

            <div className="bg-orange-50 border border-orange-200 rounded-lg p-4">
                <h3 className="font-semibold text-orange-800 mb-2 flex items-center gap-2">
                    <AlertCircle className="h-5 w-5" />
                    Issues Detectados pela Auditoria
                </h3>
                <p className="text-sm text-orange-700 mb-4">{descriptionNode}</p>

                {!hasRawForHil && issues.length > 0 && allowApply && (
                    <div className="flex items-start gap-3 p-3 rounded-lg border border-orange-300 bg-orange-100 mb-4">
                        <AlertCircle className="h-5 w-5 text-orange-600 flex-shrink-0 mt-0.5" />
                        <div className="text-sm">
                            <p className="font-medium text-orange-800">Transcrição RAW não disponível</p>
                            <p className="text-orange-700 mt-1">
                                Correções de conteúdo via IA estão desabilitadas. Apenas correções estruturais podem ser aplicadas.
                                Para habilitar correções de conteúdo, refaça a transcrição com a opção &quot;Usar cache RAW&quot; desabilitada.
                            </p>
                        </div>
                    </div>
                )}

                {issues.length > 0 && (
                    <div className="flex flex-wrap gap-2 mb-4">
                        <span className="text-xs px-2 py-1 bg-purple-100 text-purple-800 rounded-full">
                            🔧 Estruturais: {structuralIssueCount}
                        </span>
                        <span className="text-xs px-2 py-1 bg-blue-100 text-blue-800 rounded-full">
                            🤖 Conteúdo (IA): {contentIssueCount}
                        </span>
                    </div>
                )}

                {issues.length > 0 && showAutoApply && (
                    <div className="flex flex-wrap items-center gap-2 mb-4">
                        {onAutoApplyStructural && (
                            <Button
                                variant="outline"
                                size="sm"
                                onClick={onAutoApplyStructural}
                                disabled={isApplying || structuralIssueCount === 0}
                            >
                                Auto-corrigir estruturais
                            </Button>
                        )}
                        {onAutoApplyContent && (
                            <Button
                                variant="outline"
                                size="sm"
                                onClick={onAutoApplyContent}
                                disabled={isApplying || contentIssueCount === 0 || !hasRawForHil}
                            >
                                Auto-corrigir conteúdo (IA)
                            </Button>
                        )}
                        {!hasRawForHil && (
                            <span className="text-[11px] text-muted-foreground">
                                RAW necessário para correções de conteúdo.
                            </span>
                        )}
                    </div>
                )}

                {hilDiagnostics && (
                    <div className="rounded-md border border-orange-200 bg-white p-3 text-xs text-gray-700 mb-4">
                        <div className="flex flex-wrap gap-3">
                            <span>
                                Alteração no conteúdo:{" "}
                                {hilDiagnostics.contentChanged === true
                                    ? "Sim"
                                    : hilDiagnostics.contentChanged === false
                                        ? "Não"
                                        : "—"}
                            </span>
                            {hilDiagnostics.contentChange && (
                                <span>
                                    {hilDiagnostics.contentChange.before_chars ?? 0} →{" "}
                                    {hilDiagnostics.contentChange.after_chars ?? 0} chars
                                </span>
                            )}
                            {hilDiagnostics.contentError && (
                                <span className="text-red-600">
                                    Erro conteúdo: {hilDiagnostics.contentError}
                                </span>
                            )}
                        </div>
                        <div className="mt-2">
                            <div className="font-medium text-gray-600">Evidências usadas</div>
                            {hilDiagnostics.evidence && hilDiagnostics.evidence.length > 0 ? (
                                <div className="mt-2 space-y-2">
                                    {hilDiagnostics.evidence.map((item, idx) => (
                                        <div key={`${item.issueId || "issue"}-${idx}`} className="rounded border bg-gray-50 p-2">
                                            {(item.reference || item.suggestedSection) && (
                                                <div className="text-[10px] text-gray-500">
                                                    {item.reference ? `Ref: ${item.reference}` : "Ref: —"}
                                                    {item.suggestedSection ? ` · Seção: ${item.suggestedSection}` : ""}
                                                </div>
                                            )}
                                            <div className="mt-1 whitespace-pre-wrap text-[11px] text-gray-700">
                                                {item.snippet}
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            ) : (
                                <div className="mt-1 text-[11px] text-gray-500">
                                    Nenhuma evidência disponível (RAW ausente ou referência não localizada).
                                </div>
                            )}
                        </div>
                    </div>
                )}

                {issues.length === 0 && (
                    <div className="text-center py-8 text-gray-500">
                        <CheckCircle className="h-12 w-12 mx-auto mb-2 text-green-500" />
                        <p className="font-medium text-green-700">Nenhum issue detectado!</p>
                        <p className="text-sm">O documento passou na auditoria de qualidade.</p>
                    </div>
                )}

                <div className="space-y-2 max-h-[500px] overflow-y-auto">
                    {issues.map((issue, idx) => {
                        const issueId = resolveIssueId(issue, idx);
                        const isSelected = selectedSet.has(issueId);
                        const typeLabel = String(issue?.type || issue?.title || "issue").replace(/_/g, " ");
                        const isStructural = issue?.fix_type === "structural";
                        const isExpanded = expandedIssues.has(issueId);
                        const hasDetails = (issue.evidence_formatted || issue.verdict || (issue.raw_evidence && issue.raw_evidence.length > 0));

                        // Extract Evidence from Issue
                        const evidenceRaw = issue.raw_evidence?.[0];
                        const rawText = typeof evidenceRaw === 'string' ? evidenceRaw : evidenceRaw?.snippet || "";

                        return (
                            <div
                                key={issueId}
                                className={`rounded-lg border transition-all duration-200 ${isSelected
                                    ? "bg-orange-100 border-orange-300"
                                    : "bg-white border-gray-200 hover:bg-gray-50"
                                    }`}
                            >
                                <label className={`flex items-start gap-3 p-3 cursor-pointer ${allowSelection ? "" : "cursor-not-allowed"}`}>
                                    <input
                                        type="checkbox"
                                        checked={isSelected}
                                        disabled={!allowSelection}
                                        onChange={() => (allowSelection ? onToggleIssue?.(issueId) : undefined)}
                                        className="mt-1 h-4 w-4 rounded border-gray-300 text-orange-600 focus:ring-orange-500"
                                    />
                                    <div className="flex-1">
                                        <div className="flex items-center justify-between gap-2">
                                            <div className="flex items-center gap-2 flex-wrap">
                                                <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${isStructural
                                                    ? "bg-purple-100 text-purple-800"
                                                    : "bg-blue-100 text-blue-800"
                                                    }`}>
                                                    {isStructural ? "🔧 Estrutural" : "🤖 Conteúdo"}
                                                </span>
                                                <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${issue?.severity === "warning" ? "bg-yellow-100 text-yellow-800" : "bg-gray-100 text-gray-700"
                                                    }`}>
                                                    {typeLabel}
                                                </span>
                                                {!isStructural && onReviewIssue && (
                                                    <Button
                                                        type="button"
                                                        variant="secondary"
                                                        size="sm"
                                                        className="h-6 px-2 text-[11px]"
                                                        onClick={(event) => {
                                                            event.preventDefault();
                                                            event.stopPropagation();
                                                            onReviewIssue(issue);
                                                        }}
                                                    >
                                                        Revisar com contexto
                                                    </Button>
                                                )}
                                            </div>
                                            {hasDetails && (
                                                <Button
                                                    variant="ghost"
                                                    size="sm"
                                                    className="h-6 w-6 p-0 rounded-full"
                                                    onClick={(e) => toggleExpand(issueId, e)}
                                                >
                                                    {isExpanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                                                </Button>
                                            )}
                                        </div>

                                        {/* Title / Description */}
                                        {issue?.description && (
                                            <p className="text-sm font-medium text-gray-800 mt-2">{issue.description}</p>
                                        )}

                                        {/* Collapsed content (brief) */}
                                        {!isExpanded && (
                                            <>
                                                {issue?.suggestion && (
                                                    <p className="text-xs text-gray-500 mt-1 line-clamp-1">💡 {issue.suggestion}</p>
                                                )}
                                                {issue?.reference && (
                                                    <p className="text-xs text-gray-500 mt-1">🔎 Ref: {issue.reference}</p>
                                                )}
                                            </>
                                        )}

                                        {/* Expanded Detail View - The Format User Requested */}
                                        {isExpanded && (
                                            <div className="mt-3 space-y-3 border-t border-gray-100 pt-3 text-sm">
                                                {/* Verdict */}
                                                {issue.verdict && (
                                                    <div className="flex items-center gap-2">
                                                        <span className="font-bold text-gray-700">Veredito:</span>
                                                        <span className={cn(
                                                            "px-2 py-0.5 rounded text-xs font-semibold uppercase",
                                                            issue.verdict.toLowerCase().includes('confirmado') ? "bg-red-100 text-red-800" :
                                                                issue.verdict.toLowerCase().includes('falso') ? "bg-green-100 text-green-800" :
                                                                    "bg-gray-100 text-gray-700"
                                                        )}>
                                                            {issue.verdict}
                                                        </span>
                                                    </div>
                                                )}

                                                {/* Evidence Raw */}
                                                {rawText && (
                                                    <div>
                                                        <div className="text-xs font-semibold text-gray-500 uppercase mb-1">Evidence Raw</div>
                                                        <div className="bg-gray-50 p-2 rounded border border-gray-200 text-xs text-gray-700 whitespace-pre-wrap font-mono">
                                                            {rawText}
                                                        </div>
                                                    </div>
                                                )}

                                                {/* Evidence Formatted */}
                                                <div>
                                                    <div className="text-xs font-semibold text-gray-500 uppercase mb-1">Evidence Formatted</div>
                                                    <div className="bg-gray-50 p-2 rounded border border-gray-200 text-xs text-gray-700 whitespace-pre-wrap font-mono">
                                                        {issue.evidence_formatted || (
                                                            <span className="italic text-gray-400">Conteúdo ausente ou não identificado no formatado.</span>
                                                        )}
                                                    </div>
                                                </div>

                                                {/* Patch Suggestion */}
                                                {issue.suggestion && (
                                                    <div>
                                                        <div className="text-xs font-semibold text-gray-500 uppercase mb-1">Sugestão / Patch</div>
                                                        <PatchPreview
                                                            original={issue.evidence_formatted || ""}
                                                            replacement={issue.suggestion}
                                                        />
                                                    </div>
                                                )}

                                                {issue.suggested_section && <div className="text-xs text-gray-500">📍 Seção: {issue.suggested_section}</div>}
                                                {issue.reference && <div className="text-xs text-gray-500">🔎 Referência: {issue.reference}</div>}
                                            </div>
                                        )}
                                    </div>
                                </label>
                            </div>
                        );
                    })}
                </div>

                {allowApply && (
                    <div className="flex justify-between items-center mt-4 pt-4 border-t border-orange-200">
                        <span className="text-sm text-orange-700">
                            {selectedSet.size} de {issues.length} selecionados
                        </span>
                        <Button
                            onClick={onApplySelected}
                            disabled={selectedSet.size === 0 || isApplying}
                            className="bg-orange-600 hover:bg-orange-700"
                        >
                            {isApplying ? (
                                <>
                                    <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Aplicando...
                                </>
                            ) : (
                                <>
                                    <CheckCircle className="mr-2 h-4 w-4" /> Aplicar Correções
                                </>
                            )}
                        </Button>
                    </div>
                )}
            </div>
        </div>
    );
}
