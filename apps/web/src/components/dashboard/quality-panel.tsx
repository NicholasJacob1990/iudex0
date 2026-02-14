/** @deprecated Use UnifiedAuditPanel instead. This component will be removed in a future release. */
"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import {
    Loader2,
    CheckCircle,
    AlertTriangle,
    XCircle,
    Wrench,
    ShieldCheck,
    AlertCircle,
    ListChecks,
    FileWarning,
    ClipboardList,
    Copy,
    FileInput,
    Scale,
    Download,
    FileDown,
    RefreshCw,
} from "lucide-react";
import { toast } from "sonner";
import apiClient from "@/lib/api-client";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { buildQualityHilIssues, type HilIssue } from "@/lib/preventive-hil";

interface HilPatch {
    anchor_text?: string;
    old_text?: string;
    new_text?: string;
    confidence?: string;
    confidence_score?: number;
    validation_notes?: string[];
}

interface PendingFix {
    id: string;
    type: string;  // duplicate_paragraph, duplicate_section, heading_numbering, omission, distortion
                   // For hearings: speaker_inconsistency, timestamp_error, speaker_alignment_error, evidence_gap, contradiction, incomplete_statement
    description: string;
    action: string;  // REMOVE, MERGE, RENUMBER, INSERT, REPLACE
    severity: string;
    source?: string;  // structural_audit, fidelity_audit, preventive_audit
    fingerprint?: string;
    title?: string;
    patch?: HilPatch;
    evidence?: string[];
    // Validation fields
    confidence?: number;
    confidence_level?: string;  // very_high, high, medium, low, very_low
    validation_notes?: string[];
    can_auto_apply?: boolean;
    // Hearing-specific fields
    segment_id?: string;
    speaker_id?: string;
    timestamp?: string;
    suggestion?: string;
}

// Hearing-specific types
interface HearingSegment {
    id?: string;
    text: string;
    speaker_id?: string;
    speaker_label?: string;
    speaker_role?: string;
    start?: number;
    end?: number;
    confidence?: number;
}

interface Speaker {
    speaker_id: string;
    name?: string;
    label?: string;
    role?: string;
    party?: string;
}

interface HearingValidationIssue {
    id: string;
    type: string;
    description: string;
    severity: string;
    segment_id?: string;
    speaker_id?: string;
    timestamp?: string;
    suggestion?: string;
}

interface HearingValidationResult {
    document_name: string;
    validated_at: string;
    approved: boolean;
    score: number;
    mode: string;
    completude_rate: number;
    speaker_identification_rate: number;
    evidence_preservation_rate: number;
    chronology_valid: boolean;
    issues: HearingValidationIssue[];
    total_issues: number;
    requires_review: boolean;
    review_reason?: string;
    critical_areas: string[];
}

interface HearingChecklist {
    document_name: string;
    total_references: number;
    by_speaker: Record<string, any[]>;
    by_category: Record<string, any[]>;
    timeline: any[];
    checklist_markdown: string;
}

interface QualityReport {
    document_name: string;
    validated_at: string;
    approved: boolean;
    score: number;
    omissions: string[];
    distortions: string[];
    structural_issues: string[];
    observations: string;
    error?: string;
}

interface JobMetadata {
    template_type?: string;
    prompt_type?: string;
    category?: string;
    tags?: string[];
}

interface QualityPanelProps {
    rawContent: string;
    formattedContent: string;
    documentName: string;
    /** Mode for validation rules: APOSTILA/FIDELIDADE/AUDIENCIA/REUNIAO/DEPOIMENTO */
    documentMode?: string;
    /** Model selection for long-running HIL ops */
    modelSelection?: string;
    jobId?: string;
    initialQuality?: StoredQualityState | null;
    onContentUpdated?: (newContent: string) => void;
    storageKey?: string;
    /** UI variant: 'full' (default) or 'dashboard' (read-only summary) */
    variant?: 'full' | 'dashboard';
    /** Explicitly mark as legal apostila */
    isLegalApostila?: boolean;
    /** Job metadata for auto-detection */
    jobMetadata?: JobMetadata;

    // Hearing/Meeting specific props
    /** Content type: 'apostila' | 'hearing' | 'meeting' */
    contentType?: 'apostila' | 'hearing' | 'meeting';
    /** Hearing segments (for hearing mode) */
    segments?: HearingSegment[];
    /** Identified speakers (for hearing mode) */
    speakers?: Speaker[];
    /** Hearing mode: AUDIENCIA, REUNIAO, DEPOIMENTO */
    hearingMode?: 'AUDIENCIA' | 'REUNIAO' | 'DEPOIMENTO';

    // Synchronization props (for unified audit state)
    /** External audit issues from parent (HIL tab) */
    externalAuditIssues?: PendingFix[];
    /** Whether audit is outdated (content changed since last audit) */
    isAuditOutdated?: boolean;
    /** Callback when issues are updated (after applying fixes) */
    onIssuesUpdated?: (issues: PendingFix[]) => void;
    /** Callback when audit becomes outdated */
    onAuditOutdatedChange?: (outdated: boolean) => void;
    /** Convert content alerts into HIL issues (dashboard summary) */
    onConvertContentAlerts?: (issues: HilIssue[]) => void;

    /** Hearing/meeting: notify parent after updating hearing payload */
    onHearingUpdated?: (payload: any) => void;
    // Consolidated audit data (from audit_summary.json)
    consolidatedScore?: number | null;
    consolidatedStatus?: string | null;
}

interface AnalyzeResponse {
    document_name: string;
    analyzed_at: string;
    total_issues: number;
    pending_fixes: PendingFix[];
    requires_approval: boolean;
    error?: string;
    // v4.0 Content Issues
    compression_ratio?: number;
    compression_warning?: string;
    missing_laws?: string[];
    missing_sumulas?: string[];
    missing_decretos?: string[];
    missing_julgados?: string[];
    total_content_issues?: number;
}

interface StoredQualityState {
    validation_report?: QualityReport | null;
    analysis_result?: AnalyzeResponse | null;
    selected_fix_ids?: string[];
    applied_fixes?: string[];
    suggestions?: string | null;
    needs_revalidate?: boolean;
}

interface QualityUiState {
    severityFilter?: "all" | "high" | "medium" | "low";
    selectedFixIds?: string[];
}

interface QualitySummaryState {
    validated_at?: string;
    score?: number;
    approved?: boolean;
    total_issues?: number;
    total_content_issues?: number;
    analyzed_at?: string;
}

// Legal document detection patterns
const LEGAL_NAME_PATTERNS = [
    /apostila.*jur[íi]dic/i,
    /aula.*direito/i,
    /direito.*aula/i,
    /curso.*direito/i,
    /direito.*curso/i,
    /jur[íi]dic/i,
    /legal/i,
    /constitucional/i,
    /civil/i,
    /penal/i,
    /trabalhista/i,
    /tribut[áa]ri/i,
    /administrativo/i,
    /processo.*civil/i,
    /processo.*penal/i,
    /cpc/i,
    /cpp/i,
    /oab/i,
    /concurso.*p[úu]blico/i,
    /magistratura/i,
    /promotor/i,
    /defensor/i,
    /advogado/i,
];

const LEGAL_TEMPLATE_TYPES = [
    "legal",
    "juridico",
    "juridica",
    "direito",
    "law",
    "apostila_juridica",
    "aula_direito",
    "curso_direito",
    "oab",
    "concurso",
];

const LEGAL_PROMPT_TYPES = [
    "legal",
    "juridico",
    "juridica",
    "law",
    "direito",
    "apostila_legal",
];

const LEGAL_TAGS = [
    "direito",
    "juridico",
    "legal",
    "law",
    "oab",
    "concurso",
    "apostila",
];

function detectLegalApostila(
    documentName: string,
    jobMetadata?: JobMetadata,
    explicitFlag?: boolean
): boolean {
    // Method 1: Explicit prop
    if (explicitFlag === true) return true;
    if (explicitFlag === false) return false;

    // Method 2: Job metadata
    if (jobMetadata) {
        const templateType = jobMetadata.template_type?.toLowerCase() || "";
        const promptType = jobMetadata.prompt_type?.toLowerCase() || "";
        const category = jobMetadata.category?.toLowerCase() || "";
        const tags = jobMetadata.tags?.map(t => t.toLowerCase()) || [];

        if (LEGAL_TEMPLATE_TYPES.some(t => templateType.includes(t))) return true;
        if (LEGAL_PROMPT_TYPES.some(t => promptType.includes(t))) return true;
        if (LEGAL_TEMPLATE_TYPES.some(t => category.includes(t))) return true;
        if (tags.some(tag => LEGAL_TAGS.some(lt => tag.includes(lt)))) return true;
    }

    // Method 3: Document name patterns
    const nameLower = documentName.toLowerCase();
    if (LEGAL_NAME_PATTERNS.some(pattern => pattern.test(nameLower))) return true;

    return false;
}

export function QualityPanel({
    rawContent,
    formattedContent,
    documentName,
    documentMode,
    modelSelection,
    jobId,
    initialQuality,
    onContentUpdated,
    storageKey,
    variant = 'full',
    isLegalApostila,
    jobMetadata,
    // Hearing-specific props
    contentType,
    segments,
    speakers,
    hearingMode = 'AUDIENCIA',
    // Synchronization props
    externalAuditIssues,
    isAuditOutdated: externalIsAuditOutdated,
    onIssuesUpdated,
    onAuditOutdatedChange,
    onConvertContentAlerts,
    onHearingUpdated,
    // Consolidated audit data
    consolidatedScore,
    consolidatedStatus,
}: QualityPanelProps) {
    const isDashboardVariant = variant === 'dashboard';
    // Determine if this is a hearing/meeting
    const isHearingContent = contentType === 'hearing' || contentType === 'meeting';

    // Detect if this is a legal apostila using all 3 methods (only for non-hearing content)
    const isLegalDocument = useMemo(
        () => !isHearingContent && detectLegalApostila(documentName, jobMetadata, isLegalApostila),
        [documentName, jobMetadata, isLegalApostila, isHearingContent]
    );
    const [isApplying, setIsApplying] = useState(false);
    const [isConvertingToHil, setIsConvertingToHil] = useState(false);
    const [isGeneratingChecklist, setIsGeneratingChecklist] = useState(false);
    const [legalChecklist, setLegalChecklist] = useState<{
        total_references: number;
        checklist_markdown: string;
        content_with_checklist?: string;
    } | null>(null);

    // Hearing-specific state
    const [isValidatingHearing, setIsValidatingHearing] = useState(false);
    const [hearingValidation, setHearingValidation] = useState<HearingValidationResult | null>(null);
    const [isGeneratingHearingChecklist, setIsGeneratingHearingChecklist] = useState(false);
    const [hearingChecklist, setHearingChecklist] = useState<HearingChecklist | null>(null);
    const [report, setReport] = useState<QualityReport | null>(null);
    const [analysisResult, setAnalysisResult] = useState<AnalyzeResponse | null>(null);
    const [pendingFixes, setPendingFixes] = useState<PendingFix[]>([]);
    const [selectedFixes, setSelectedFixes] = useState<Set<string>>(new Set());
    const [suggestions, setSuggestions] = useState<string | null>(null);
    const [appliedFixes, setAppliedFixes] = useState<string[]>([]);
    const [severityFilter, setSeverityFilter] = useState<"all" | "high" | "medium" | "low">("all");
    const [storedUiState, setStoredUiState] = useState<QualityUiState | null>(null);
    const [isRevalidating, setIsRevalidating] = useState(false);
    const uiStateRef = useRef<QualityUiState | null>(null);
    const summaryRef = useRef<QualitySummaryState | null>(null);

    const qualityStorageKey = useMemo(() => {
        if (storageKey) return storageKey;
        if (jobId) return `job:${jobId}`;
        if (documentName) return `doc:${documentName}`;
        return null;
    }, [storageKey, jobId, documentName]);

    const uiStorageKey = qualityStorageKey ? `iudex_quality_ui:${qualityStorageKey}` : null;
    const summaryStorageKey = qualityStorageKey ? `iudex_quality_summary:${qualityStorageKey}` : null;

    const persistQuality = async (update: Partial<StoredQualityState> & { fixed_content?: string }) => {
        if (!jobId) return;
        try {
            await apiClient.updateTranscriptionJobQuality(jobId, update);
        } catch (error) {
            console.warn("Falha ao persistir qualidade do job:", error);
        }
    };

    const normalizeScore = useCallback((value: unknown) => {
        const numeric = typeof value === "number" ? value : Number(value);
        if (!Number.isFinite(numeric)) return 0;
        return Math.max(0, Math.min(10, numeric));
    }, []);

    const normalizeReport = useCallback((input: any): QualityReport => ({
        document_name: input?.document_name || documentName,
        validated_at: input?.validated_at || new Date().toISOString(),
        approved: Boolean(input?.approved),
        score: normalizeScore(input?.score),
        omissions: Array.isArray(input?.omissions) ? input.omissions : [],
        distortions: Array.isArray(input?.distortions) ? input.distortions : [],
        structural_issues: Array.isArray(input?.structural_issues) ? input.structural_issues : [],
        observations: typeof input?.observations === "string" ? input.observations : "",
        error: typeof input?.error === "string" ? input.error : undefined,
    }), [documentName, normalizeScore]);

    const formatTimestamp = (value?: string | null) => {
        if (!value) return "—";
        const parsed = new Date(value);
        if (Number.isNaN(parsed.valueOf())) return value;
        return parsed.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
    };

    const hasConsolidatedScore =
        typeof consolidatedScore === "number" && Number.isFinite(consolidatedScore);
    const consolidatedStatusNormalized = String(consolidatedStatus || "").toLowerCase();
    const effectiveScore =
        hasConsolidatedScore
            ? normalizeScore(consolidatedScore)
            : (report ? normalizeScore(report.score) : null);
    const effectiveApproved =
        hasConsolidatedScore
            ? !["warning", "error", "critical", "reprovado", "failed", "blocked"].some((token) =>
                consolidatedStatusNormalized.includes(token)
            )
            : report?.approved;
    const effectiveStatusLabel = hasConsolidatedScore
        ? (consolidatedStatus || (effectiveApproved ? "ok" : "warning"))
        : (report ? (report.approved ? "Aprovado" : "Em revisão") : "—");

    const persistUiState = useCallback((patch: Partial<QualityUiState>) => {
        if (!uiStorageKey || typeof window === "undefined") return;
        const current = uiStateRef.current ?? {};
        const next = { ...current, ...patch };
        uiStateRef.current = next;
        setStoredUiState(next);
        try {
            localStorage.setItem(uiStorageKey, JSON.stringify(next));
        } catch {
            // ignore storage errors
        }
    }, [uiStorageKey]);

    const persistSummary = useCallback((patch: Partial<QualitySummaryState>) => {
        if (!summaryStorageKey || typeof window === "undefined") return;
        const current = summaryRef.current ?? {};
        const next = { ...current, ...patch };
        summaryRef.current = next;
        try {
            localStorage.setItem(summaryStorageKey, JSON.stringify(next));
        } catch {
            // ignore storage errors
        }
    }, [summaryStorageKey]);

    useEffect(() => {
        if (!uiStorageKey || typeof window === "undefined") return;
        try {
            const raw = localStorage.getItem(uiStorageKey);
            if (!raw) {
                setStoredUiState(null);
                return;
            }
            const parsed = JSON.parse(raw) as QualityUiState;
            uiStateRef.current = parsed;
            setStoredUiState(parsed);
        } catch {
            setStoredUiState(null);
        }
    }, [uiStorageKey]);

    useEffect(() => {
        if (!storedUiState?.severityFilter) return;
        setSeverityFilter(storedUiState.severityFilter);
    }, [storedUiState?.severityFilter]);

    const getScoreColor = (score: number) => {
        const safeScore = normalizeScore(score);
        if (safeScore >= 8) return "text-green-600";
        if (safeScore >= 6) return "text-yellow-600";
        return "text-red-600";
    };

    const getScoreIcon = (score: number) => {
        const safeScore = normalizeScore(score);
        if (safeScore >= 8) return <CheckCircle className="w-5 h-5 text-green-600" />;
        if (safeScore >= 6) return <AlertTriangle className="w-5 h-5 text-yellow-600" />;
        return <XCircle className="w-5 h-5 text-red-600" />;
    };

    // Use ref to avoid dependency cycle: initialQuality -> setSelectedFixes -> persistUiState -> storedUiState -> loop
    useEffect(() => {
        if (!initialQuality) {
            setReport(null);
            setAnalysisResult(null);
            setPendingFixes([]);
            setSelectedFixes(new Set());
            setSuggestions(null);
            setAppliedFixes([]);
            return;
        }

        if (initialQuality.validation_report) {
            setReport(normalizeReport(initialQuality.validation_report));
        } else {
            setReport(null);
        }

        if (initialQuality.analysis_result) {
            const normalizedPending = Array.isArray(initialQuality.analysis_result.pending_fixes)
                ? initialQuality.analysis_result.pending_fixes
                : [];
            const totalIssues =
                typeof initialQuality.analysis_result.total_issues === "number"
                    ? initialQuality.analysis_result.total_issues
                    : normalizedPending.length;
            const normalizedAnalysis = {
                ...initialQuality.analysis_result,
                pending_fixes: normalizedPending,
                total_issues: totalIssues,
            };
            setAnalysisResult(normalizedAnalysis);
            setPendingFixes(normalizedPending);
            // Use ref instead of state to avoid infinite loop
            const storedSelection = uiStateRef.current?.selectedFixIds ?? [];
            const available = new Set(normalizedPending.map((fix) => fix.id));
            const filteredStored = storedSelection.filter((id) => available.has(id));
            if (initialQuality.selected_fix_ids && initialQuality.selected_fix_ids.length > 0) {
                setSelectedFixes(new Set(initialQuality.selected_fix_ids));
            } else if (filteredStored.length > 0) {
                setSelectedFixes(new Set(filteredStored));
            } else {
                setSelectedFixes(new Set(normalizedPending.map((f) => f.id)));
            }
        } else {
            setAnalysisResult(null);
            setPendingFixes([]);
            setSelectedFixes(new Set());
        }

        setSuggestions(initialQuality.suggestions || null);
        setAppliedFixes(Array.isArray(initialQuality.applied_fixes) ? initialQuality.applied_fixes : []);
    }, [initialQuality, normalizeReport]); // Removed storedUiState to break cycle

    useEffect(() => {
        if (!storedUiState?.selectedFixIds?.length) return;
        if (selectedFixes.size > 0) return;
        if (!pendingFixes.length) return;
        if (jobId && (initialQuality?.selected_fix_ids?.length || 0) > 0) return;
        const available = new Set(pendingFixes.map((fix) => fix.id));
        const filtered = storedUiState.selectedFixIds.filter((id) => available.has(id));
        if (filtered.length > 0) {
            setSelectedFixes(new Set(filtered));
        }
    }, [storedUiState, selectedFixes.size, pendingFixes, jobId, initialQuality?.selected_fix_ids?.length]);

    // Track previous external issues to detect real external changes
    const prevExternalIssuesRef = useRef<PendingFix[] | undefined>(externalAuditIssues);
    const isUpdatingFromExternalRef = useRef(false);

    // Sync external audit issues with internal pendingFixes (one-way: external → internal)
    useEffect(() => {
        if (!externalAuditIssues || externalAuditIssues.length === 0) return;

        // Check if this is actually a new external update (not a reflection of our own change)
        const prevIds = prevExternalIssuesRef.current?.map(i => i.id).sort().join(',') ?? '';
        const newIds = externalAuditIssues.map(i => i.id).sort().join(',');

        if (prevIds === newIds) {
            // Same IDs, no real change
            prevExternalIssuesRef.current = externalAuditIssues;
            return;
        }

        // Mark that we're updating from external source
        isUpdatingFromExternalRef.current = true;
        prevExternalIssuesRef.current = externalAuditIssues;

        setPendingFixes(externalAuditIssues);
        setAnalysisResult(prev => prev ? {
            ...prev,
            pending_fixes: externalAuditIssues,
            total_issues: externalAuditIssues.length,
        } : null);

        // Reset flag after state update
        requestAnimationFrame(() => {
            isUpdatingFromExternalRef.current = false;
        });
    }, [externalAuditIssues]);

    // Track previous pendingFixes to detect internal changes
    const prevPendingFixesRef = useRef<PendingFix[]>(pendingFixes);
    useEffect(() => {
        // Skip if this update came from external sync
        if (isUpdatingFromExternalRef.current) {
            prevPendingFixesRef.current = pendingFixes;
            return;
        }

        // Only notify parent if this was an internal change
        const prevIds = prevPendingFixesRef.current.map(i => i.id).sort().join(',');
        const newIds = pendingFixes.map(i => i.id).sort().join(',');

        if (prevIds !== newIds && onIssuesUpdated) {
            onIssuesUpdated(pendingFixes);
        }
        prevPendingFixesRef.current = pendingFixes;
    }, [pendingFixes, onIssuesUpdated]);

    useEffect(() => {
        persistUiState({ severityFilter });
    }, [severityFilter, persistUiState]);

    useEffect(() => {
        persistUiState({ selectedFixIds: Array.from(selectedFixes) });
    }, [selectedFixes, persistUiState]);

    const handleApplyApproved = async () => {
        if (selectedFixes.size === 0) {
            toast.info("Selecione ao menos uma correção para aplicar.");
            return;
        }

        setIsApplying(true);

        try {
            const approvedFixes = pendingFixes.filter((fix) => selectedFixes.has(fix.id));
            const result = await apiClient.applyApprovedFixes({
                content: formattedContent,
                approved_fix_ids: Array.from(selectedFixes),
                approved_fixes: approvedFixes,
            });

            if (result.error) {
                toast.error("Erro ao aplicar: " + result.error);
                return;
            }

            if (result.success && result.fixed_content) {
                const fixesApplied = Array.isArray(result.fixes_applied) ? result.fixes_applied : [];
                
                if (fixesApplied.length === 0) {
                    // Backend returned success but no actual fixes were applied
                    toast.info("Nenhum parágrafo duplicado encontrado no conteúdo atual. O documento pode já ter sido corrigido.");
                    setAppliedFixes([]);
                    await persistQuality({
                        applied_fixes: [],
                        fixed_content: result.fixed_content,
                    });
                    return;
                }
                
                onContentUpdated?.(result.fixed_content);
                // Notify parent that audit is now outdated (content changed)
                onAuditOutdatedChange?.(true);
                const resolvedAnalysis = analysisResult
                    ? {
                          ...analysisResult,
                          pending_fixes: [],
                          total_issues: 0,
                          requires_approval: false,
                      }
                    : null;
                setPendingFixes([]);
                // Notify parent that issues were cleared
                onIssuesUpdated?.([]);
                setSelectedFixes(new Set());
                setAppliedFixes(fixesApplied);
                setAnalysisResult(resolvedAnalysis);
                await persistQuality({
                    analysis_result: resolvedAnalysis,
                    selected_fix_ids: [],
                    applied_fixes: fixesApplied,
                    fixed_content: result.fixed_content,
                });
                persistSummary({ total_issues: 0, analyzed_at: new Date().toISOString() });
                toast.success(
                    `${fixesApplied.length} correção(ões) aplicada(s). Redução: ${result.size_reduction}`
                );
            } else {
                toast.info("Nenhuma alteração realizada.");
            }
        } catch (error: any) {
            toast.error("Erro ao aplicar: " + (error.message || "Desconhecido"));
        } finally {
            setIsApplying(false);
        }
    };

    /**
     * Generate Legal Checklist: Extracts legal references and shows in separate panel
     */
    const handleGenerateChecklist = async () => {
        setIsGeneratingChecklist(true);
        setLegalChecklist(null);

        try {
            const result = await apiClient.generateLegalChecklist({
                content: formattedContent,
                document_name: documentName,
                include_counts: true,
                append_to_content: false, // Don't append, show in separate panel
            });

            if (result.total_references > 0) {
                setLegalChecklist({
                    total_references: result.total_references,
                    checklist_markdown: result.checklist_markdown,
                    content_with_checklist: result.content_with_checklist,
                });
                toast.success(
                    `${result.total_references} referência(s) legal(is) encontrada(s)!`
                );
            } else {
                toast.info("Nenhuma referência legal encontrada no documento.");
            }
        } catch (error: any) {
            toast.error("Erro ao gerar checklist: " + (error.message || "Desconhecido"));
        } finally {
            setIsGeneratingChecklist(false);
        }
    };

    /**
     * Copy checklist to clipboard
     */
    const handleCopyChecklist = async () => {
        if (!legalChecklist?.checklist_markdown) return;
        try {
            await navigator.clipboard.writeText(legalChecklist.checklist_markdown);
            toast.success("Checklist copiado para a área de transferência!");
        } catch {
            toast.error("Erro ao copiar checklist.");
        }
    };

    /**
     * Insert checklist at the end of the apostila
     */
    const handleInsertChecklist = () => {
        if (!legalChecklist?.checklist_markdown) return;
        const newContent = formattedContent + "\n\n" + legalChecklist.checklist_markdown;
        onContentUpdated?.(newContent);
        // Notify parent that audit is now outdated (content changed)
        onAuditOutdatedChange?.(true);
        toast.success("Checklist inserido ao final da apostila!");
    };

    /**
     * Export checklist as file
     */
    const handleExportChecklist = (format: "md" | "txt") => {
        if (!legalChecklist?.checklist_markdown) return;

        const content = legalChecklist.checklist_markdown;
        const mimeType = format === "md" ? "text/markdown" : "text/plain";
        const extension = format === "md" ? "md" : "txt";
        const fileName = `checklist_legal_${documentName.replace(/\s+/g, "_")}.${extension}`;

        const blob = new Blob([content], { type: `${mimeType};charset=utf-8` });
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = fileName;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);

        toast.success(`Checklist exportado como ${fileName}`);
    };

    /**
     * Export full apostila with checklist
     */
    const handleExportApostilaWithChecklist = () => {
        if (!legalChecklist?.checklist_markdown) return;

        const content = formattedContent + "\n\n" + legalChecklist.checklist_markdown;
        const fileName = `${documentName.replace(/\s+/g, "_")}_com_checklist.md`;

        const blob = new Blob([content], { type: "text/markdown;charset=utf-8" });
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = fileName;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);

        toast.success(`Apostila com checklist exportada!`);
    };

    // =========================================================================
    // HEARING/MEETING HANDLERS
    // =========================================================================

    /**
     * Validate hearing/meeting transcription
     */
    const handleValidateHearing = async () => {
        if (!isHearingContent || !segments?.length) {
            toast.error("Nenhum segmento de audiência disponível para validação.");
            return;
        }

        setIsValidatingHearing(true);
        setHearingValidation(null);

        try {
            const result = await apiClient.validateHearing({
                segments: segments,
                speakers: speakers || [],
                formatted_content: formattedContent,
                raw_content: rawContent,
                document_name: documentName,
                mode: hearingMode,
            });

            setHearingValidation(result);

            // Also set pending fixes from hearing validation
            const hearingIssues = Array.isArray(result.issues) ? result.issues : [];
            if (hearingIssues.length > 0) {
                const normalized: PendingFix[] = hearingIssues.map((issue) => ({
                    id: String(issue.id),
                    type: String(issue.type || "issue"),
                    description: String(issue.description || ""),
                    action: "REVIEW",
                    severity: String(issue.severity || "medium"),
                    source: "hearing_validation",
                    segment_id: issue.segment_id,
                    speaker_id: issue.speaker_id,
                    timestamp: issue.timestamp,
                    suggestion: issue.suggestion,
                }));
                setPendingFixes(normalized);
                setSelectedFixes(new Set(normalized.map((i) => i.id)));
            }

            if (result.approved) {
                toast.success(`Audiência validada! Nota: ${result.score}/10`);
            } else if (result.score >= 6) {
                toast.warning(`Qualidade intermediária. Nota: ${result.score}/10`);
            } else {
                toast.error(`Problemas detectados. Nota: ${result.score}/10`);
            }
        } catch (error: any) {
            toast.error("Erro ao validar audiência: " + (error.message || "Desconhecido"));
        } finally {
            setIsValidatingHearing(false);
        }
    };

    /**
     * Generate hearing-specific legal checklist with speaker attribution
     */
    const handleGenerateHearingChecklist = async () => {
        if (!isHearingContent || !segments?.length) {
            toast.error("Nenhum segmento de audiência disponível.");
            return;
        }

        setIsGeneratingHearingChecklist(true);
        setHearingChecklist(null);

        try {
            const result = await apiClient.generateHearingChecklist({
                segments: segments,
                speakers: speakers || [],
                formatted_content: formattedContent,
                document_name: documentName,
                include_timeline: true,
                group_by_speaker: true,
            });

            if (result.total_references > 0) {
                setHearingChecklist(result);
                toast.success(`${result.total_references} referência(s) legal(is) encontrada(s)!`);
            } else {
                toast.info("Nenhuma referência legal encontrada na audiência.");
            }
        } catch (error: any) {
            toast.error("Erro ao gerar checklist: " + (error.message || "Desconhecido"));
        } finally {
            setIsGeneratingHearingChecklist(false);
        }
    };

    const handleApplyHearingRevisions = async () => {
        if (!isHearingContent) return;
        if (!jobId) {
            toast.error("Abra/seleciona um job para aplicar correções.");
            return;
        }
        if (!pendingFixes.length || selectedFixes.size === 0) {
            toast.info("Nenhum issue selecionado para aplicar.");
            return;
        }
        const approved = pendingFixes.filter((i) => selectedFixes.has(i.id));
        if (!approved.length) {
            toast.info("Nenhum issue selecionado para aplicar.");
            return;
        }
        setIsApplying(true);
        const toastId = toast.loading(`Aplicando ${approved.length} correção(ões) por IA...`);
        try {
            const data = await apiClient.applyHearingRevisions(jobId, {
                approved_issues: approved,
                model_selection: modelSelection || undefined,
                regenerate_formatted: true,
            });
            if (!data?.success) {
                toast.error("Falha ao aplicar correções.", { id: toastId });
                return;
            }
            if (data?.payload) {
                onHearingUpdated?.(data.payload);
                if (typeof data.payload?.formatted_text === "string") {
                    onContentUpdated?.(data.payload.formatted_text);
                }
            }
            const applied = Array.isArray(data?.issues_applied) ? data.issues_applied : [];
            toast.success(`Correções aplicadas: ${applied.length}`, { id: toastId });
        } catch (e: any) {
            toast.error("Erro ao aplicar correções: " + (e?.message || "Desconhecido"), { id: toastId });
        } finally {
            setIsApplying(false);
        }
    };

    const handleRevalidateQuality = async () => {
        if (isHearingContent) {
            toast.info("Use a validação de audiência para reprocessar este conteúdo.");
            return;
        }
        if (!formattedContent) {
            toast.error("Conteúdo formatado indisponível para revalidação.");
            return;
        }
        setIsRevalidating(true);
        try {
            const [validation, analysis] = await Promise.all([
                rawContent
                    ? apiClient.validateDocumentQuality({
                        raw_content: rawContent,
                        formatted_content: formattedContent,
                        document_name: documentName,
                        mode: documentMode,
                    })
                    : null,
                apiClient.analyzeDocumentHIL({
                    content: formattedContent,
                    document_name: documentName,
                    raw_content: rawContent || undefined,
                }),
            ]);

            const normalizedReport = validation ? normalizeReport(validation) : null;
            if (normalizedReport) {
                setReport(normalizedReport);
                persistSummary({
                    validated_at: normalizedReport.validated_at,
                    score: normalizedReport.score,
                    approved: normalizedReport.approved,
                });
            }

            const normalizedPending = Array.isArray(analysis?.pending_fixes) ? analysis.pending_fixes : [];
            const totalIssues =
                typeof analysis?.total_issues === "number" ? analysis.total_issues : normalizedPending.length;
            const normalizedAnalysis: AnalyzeResponse = {
                ...(analysis || {}),
                pending_fixes: normalizedPending,
                total_issues: totalIssues,
            };
            setAnalysisResult(normalizedAnalysis);
            setPendingFixes(normalizedPending);
            const nextSelected = new Set(normalizedPending.map((fix) => fix.id));
            setSelectedFixes(nextSelected);
            persistSummary({
                analyzed_at: normalizedAnalysis.analyzed_at,
                total_issues: normalizedAnalysis.total_issues,
                total_content_issues: normalizedAnalysis.total_content_issues,
            });

            await persistQuality({
                validation_report: normalizedReport || undefined,
                analysis_result: normalizedAnalysis,
                selected_fix_ids: Array.from(nextSelected),
                needs_revalidate: false,
            });

            onAuditOutdatedChange?.(false);
            toast.success("Qualidade revalidada com sucesso.");
        } catch (error: any) {
            toast.error("Erro ao revalidar: " + (error?.message || "Desconhecido"));
        } finally {
            setIsRevalidating(false);
        }
    };

    /**
     * Copy hearing checklist to clipboard
     */
    const handleCopyHearingChecklist = async () => {
        if (!hearingChecklist?.checklist_markdown) return;
        try {
            await navigator.clipboard.writeText(hearingChecklist.checklist_markdown);
            toast.success("Checklist copiado para a área de transferência!");
        } catch {
            toast.error("Erro ao copiar checklist.");
        }
    };

    /**
     * Export hearing checklist as file
     */
    const handleExportHearingChecklist = (format: "md" | "txt") => {
        if (!hearingChecklist?.checklist_markdown) return;

        const content = hearingChecklist.checklist_markdown;
        const mimeType = format === "md" ? "text/markdown" : "text/plain";
        const extension = format === "md" ? "md" : "txt";
        const fileName = `checklist_audiencia_${documentName.replace(/\s+/g, "_")}.${extension}`;

        const blob = new Blob([content], { type: `${mimeType};charset=utf-8` });
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = fileName;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);

        toast.success(`Checklist exportado como ${fileName}`);
    };

    /**
     * Unified HIL: Converts validation results + structural issues to unified HIL issues
     */
    const handleConvertToUnifiedHil = async () => {
        setIsConvertingToHil(true);
        setPendingFixes([]);
        setAnalysisResult(null);
        setSelectedFixes(new Set());
        setAppliedFixes([]);

        try {
            // Get omissions and distortions from validation report if available
            const omissions = report?.omissions || [];
            const distortions = report?.distortions || [];

            const result = await apiClient.convertToHilIssues({
                raw_content: rawContent,
                formatted_content: formattedContent,
                document_name: documentName,
                omissions,
                distortions,
                include_structural: true,
            });

            if (result.error) {
                toast.error("Erro na conversão HIL: " + result.error);
                return;
            }

            const hilIssues = result.hil_issues || [];
            const normalizedAnalysis: AnalyzeResponse = {
                document_name: result.document_name,
                analyzed_at: result.converted_at,
                total_issues: result.total_issues,
                pending_fixes: hilIssues,
                requires_approval: result.requires_approval,
            };

            setAnalysisResult(normalizedAnalysis);
            setPendingFixes(hilIssues);

            // Select all by default
            const allIds = new Set(hilIssues.map((f) => f.id));
            setSelectedFixes(allIds);

            await persistQuality({
                analysis_result: normalizedAnalysis,
                selected_fix_ids: Array.from(allIds),
            });
            persistSummary({
                analyzed_at: result.converted_at,
                total_issues: result.total_issues,
            });

            if (hilIssues.length > 0) {
                toast.info(
                    `${result.total_issues} issue(s) encontrado(s): ${result.structural_count} estruturais, ${result.semantic_count} semânticos.`
                );
            } else {
                toast.success("Nenhum problema encontrado!");
            }
        } catch (error: any) {
            toast.error("Erro na conversão HIL: " + (error.message || "Desconhecido"));
        } finally {
            setIsConvertingToHil(false);
        }
    };

    /**
     * Unified HIL: Apply selected fixes (structural + semantic)
     */
    const handleApplyUnifiedHil = async () => {
        if (selectedFixes.size === 0) {
            toast.info("Selecione ao menos uma correção para aplicar.");
            return;
        }

        setIsApplying(true);

        try {
            const approvedFixes = pendingFixes.filter((fix) => selectedFixes.has(fix.id));

            const result = await apiClient.applyUnifiedHilFixes({
                content: formattedContent,
                raw_content: rawContent,
                approved_fixes: approvedFixes,
            });

            if (result.error) {
                toast.error("Erro ao aplicar: " + result.error);
                return;
            }

            if (result.success && result.fixed_content) {
                const fixesApplied = result.fixes_applied || [];

                if (fixesApplied.length === 0) {
                    toast.info("Nenhuma correção foi aplicada. O documento pode já estar correto.");
                    return;
                }

                onContentUpdated?.(result.fixed_content);
                // Notify parent that audit is now outdated (content changed)
                onAuditOutdatedChange?.(true);
                const resolvedAnalysis = analysisResult
                    ? {
                          ...analysisResult,
                          pending_fixes: [],
                          total_issues: 0,
                          requires_approval: false,
                      }
                    : null;

                setPendingFixes([]);
                // Notify parent that issues were cleared
                onIssuesUpdated?.([]);
                setSelectedFixes(new Set());
                setAppliedFixes(fixesApplied);
                setAnalysisResult(resolvedAnalysis);

                await persistQuality({
                    analysis_result: resolvedAnalysis,
                    selected_fix_ids: [],
                    applied_fixes: fixesApplied,
                    fixed_content: result.fixed_content,
                });
                persistSummary({ total_issues: 0, analyzed_at: new Date().toISOString() });

                toast.success(
                    `${fixesApplied.length} correção(ões) aplicada(s). ` +
                    `Estruturais: ${result.structural_applied}, Semânticas: ${result.semantic_applied}. ` +
                    `Variação: ${result.size_reduction}`
                );
            } else {
                toast.info("Nenhuma alteração realizada.");
            }
        } catch (error: any) {
            toast.error("Erro ao aplicar: " + (error.message || "Desconhecido"));
        } finally {
            setIsApplying(false);
        }
    };

    const toggleFix = (id: string) => {
        const newSelected = new Set(selectedFixes);
        if (newSelected.has(id)) {
            newSelected.delete(id);
        } else {
            newSelected.add(id);
        }
        setSelectedFixes(newSelected);
        void persistQuality({ selected_fix_ids: Array.from(newSelected) });
    };

    const contentAlertCount =
        typeof analysisResult?.total_content_issues === "number"
            ? analysisResult.total_content_issues
            : (analysisResult?.compression_warning ? 1 : 0)
            + (analysisResult?.missing_laws?.length || 0)
            + (analysisResult?.missing_sumulas?.length || 0)
            + (analysisResult?.missing_julgados?.length || 0)
            + (analysisResult?.missing_decretos?.length || 0);

    const contentAlertIssues = useMemo(
        () => buildQualityHilIssues(analysisResult),
        [analysisResult]
    );
    const canConvertContentAlerts =
        !isHearingContent
        && isDashboardVariant
        && typeof onConvertContentAlerts === "function"
        && contentAlertIssues.length > 0;

    const handleConvertContentAlerts = useCallback(() => {
        if (!onConvertContentAlerts) return;
        if (!contentAlertIssues.length) {
            toast.info("Nenhum alerta disponível para converter.");
            return;
        }
        onConvertContentAlerts(contentAlertIssues);
    }, [onConvertContentAlerts, contentAlertIssues]);

    const filteredPendingFixes = pendingFixes.filter((fix) =>
        severityFilter === "all" ? true : fix.severity === severityFilter
    );

    const severityCounts = pendingFixes.reduce(
        (acc, fix) => {
            const key = fix.severity as "high" | "medium" | "low";
            if (acc[key] !== undefined) acc[key] += 1;
            return acc;
        },
        { high: 0, medium: 0, low: 0 }
    );

    const selectVisibleFixes = () => {
        if (!filteredPendingFixes.length) return;
        const nextSelected = new Set(selectedFixes);
        filteredPendingFixes.forEach((fix) => nextSelected.add(fix.id));
        setSelectedFixes(nextSelected);
        void persistQuality({ selected_fix_ids: Array.from(nextSelected) });
    };

    const clearSelectedFixes = () => {
        setSelectedFixes(new Set());
        void persistQuality({ selected_fix_ids: [] });
    };

    const hasContentAlerts = Boolean(
        analysisResult?.compression_warning
        || (analysisResult?.missing_laws?.length || 0) > 0
        || (analysisResult?.missing_sumulas?.length || 0) > 0
        || (analysisResult?.missing_julgados?.length || 0) > 0
        || (analysisResult?.missing_decretos?.length || 0) > 0
    );

    return (
        <Card className="w-full rounded-3xl border border-white/80 bg-white/90 shadow-soft">
            <CardHeader className="border-b border-white/70 pb-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                        <CardTitle className="flex items-center gap-2 font-display text-lg text-foreground">
                            <ShieldCheck className="w-5 h-5 text-primary" />
                            {isDashboardVariant ? "Controle de Qualidade" : "Controle de Qualidade & Auditoria"}
                            {externalIsAuditOutdated && (
                                <Badge variant="outline" className="ml-2 bg-orange-50 text-orange-700 border-orange-200 text-[10px]">
                                    <AlertTriangle className="w-3 h-3 mr-1" />
                                    Desatualizado
                                </Badge>
                            )}
                        </CardTitle>
                        <CardDescription className="text-xs text-muted-foreground">
                            {isDashboardVariant
                                ? "Resumo e diagnósticos. Para aplicar correções, use a aba Correções (HIL)."
                                : "Validação jurídica, análise estrutural e correção assistida"}
                        </CardDescription>
                    </div>
                    {isDashboardVariant && !isHearingContent && (
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={handleRevalidateQuality}
                            disabled={isRevalidating || !formattedContent}
                        >
                            {isRevalidating ? (
                                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                            ) : (
                                <RefreshCw className="w-4 h-4 mr-2" />
                            )}
                            Revalidar Qualidade
                        </Button>
                    )}
                </div>
            </CardHeader>
            <CardContent className="space-y-6">
                {/* Audit Outdated Warning */}
                {externalIsAuditOutdated && (
                    <div className="flex items-start gap-3 p-3 rounded-lg border border-orange-300 bg-orange-50">
                        <AlertTriangle className="h-5 w-5 text-orange-600 flex-shrink-0 mt-0.5" />
                        <div className="text-sm">
                            <p className="font-medium text-orange-800">Auditoria Desatualizada</p>
                            <p className="text-orange-700 mt-1">
                                O documento foi modificado após a última auditoria. Execute uma nova análise para validar o estado atual.
                            </p>
                        </div>
                    </div>
                )}
                {/* Summary Metrics */}
                <div className="grid gap-3 md:grid-cols-3">
                    <div className="rounded-2xl border border-white/70 bg-white/90 p-4 shadow-soft">
                        <div className="flex items-center justify-between text-[10px] font-semibold text-muted-foreground uppercase tracking-wide">
                            <span className="flex items-center gap-2">
                                <ListChecks className="h-3.5 w-3.5" />
                                Fidelidade
                            </span>
                            <Badge variant={effectiveApproved ? "default" : "outline"}>
                                {effectiveStatusLabel}
                            </Badge>
                        </div>
                        <div className="mt-2 font-display text-2xl text-foreground">
                            {typeof effectiveScore === "number" ? `${effectiveScore.toFixed(1)}` : "—"}
                            <span className="text-sm text-muted-foreground">/10</span>
                        </div>
                        <div className="text-[10px] text-muted-foreground mt-1">
                            {hasConsolidatedScore ? "Nota consolidada de auditoria" : `Última validação: ${formatTimestamp(report?.validated_at)}`}
                        </div>
                    </div>
                    <div className="rounded-2xl border border-white/70 bg-white/90 p-4 shadow-soft">
                        <div className="flex items-center justify-between text-[10px] font-semibold text-muted-foreground uppercase tracking-wide">
                            <span className="flex items-center gap-2">
                                <FileWarning className="h-3.5 w-3.5" />
                                Alertas
                            </span>
                            <Badge variant={contentAlertCount > 0 ? "outline" : "secondary"}>
                                {contentAlertCount} alerta(s)
                            </Badge>
                        </div>
                        <div className="mt-2 font-display text-2xl text-foreground">
                            {contentAlertCount}
                        </div>
                        <div className="text-[10px] text-muted-foreground mt-1">
                            Última análise: {formatTimestamp(analysisResult?.analyzed_at)}
                        </div>
                    </div>
                    <div className="rounded-2xl border border-white/70 bg-white/90 p-4 shadow-soft">
                        <div className="flex items-center justify-between text-[10px] font-semibold text-muted-foreground uppercase tracking-wide">
                            <span className="flex items-center gap-2">
                                <ClipboardList className="h-3.5 w-3.5" />
                                Correções
                            </span>
                            <Badge variant={analysisResult?.total_issues ? "destructive" : "secondary"}>
                                {analysisResult?.total_issues ?? 0} pendente(s)
                            </Badge>
                        </div>
                        <div className="mt-2 font-display text-2xl text-foreground">
                            {analysisResult?.total_issues ?? 0}
                        </div>
                        <div className="text-[10px] text-muted-foreground mt-1">
                            Selecionadas: {selectedFixes.size}
                        </div>
                    </div>
                </div>

                {/* Status Bar */}
                <div className="flex flex-wrap items-center justify-between gap-3 rounded-full border border-white/70 bg-white/80 px-4 py-2 text-[11px]">
                    <div className="flex flex-wrap items-center gap-2">
                        <Badge variant={effectiveApproved ? "default" : "outline"}>
                            {typeof effectiveScore === "number"
                                ? (effectiveApproved ? "Documento aprovado" : "Revisão necessária")
                                : "Sem validação"}
                        </Badge>
                        <span className="text-muted-foreground">
                            Validação: {formatTimestamp(report?.validated_at)}
                        </span>
                    </div>
                    <div className="flex flex-wrap items-center gap-2 text-muted-foreground">
                        <span>Auditoria estrutural: {formatTimestamp(analysisResult?.analyzed_at)}</span>
                        <span>HIL: {analysisResult ? (analysisResult.requires_approval ? "pendente" : "ok") : "—"}</span>
                    </div>
                </div>

                {/* Actions Toolbar */}
                {!isDashboardVariant && (
                <div className="flex flex-wrap gap-2">
                    {isHearingContent ? (
                        /* Hearing/Meeting specific actions */
                        <>
                            <Button
                                variant="default"
                                onClick={handleValidateHearing}
                                disabled={isValidatingHearing || !segments?.length}
                                className="bg-indigo-600 hover:bg-indigo-700 text-white"
                            >
                                {isValidatingHearing ? (
                                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                                ) : (
                                    <ShieldCheck className="w-4 h-4 mr-2" />
                                )}
                                Validar Audiência
                            </Button>

                            <Button
                                variant="outline"
                                onClick={handleGenerateHearingChecklist}
                                disabled={isGeneratingHearingChecklist || !segments?.length}
                                className="border-emerald-300 text-emerald-700 hover:bg-emerald-50"
                            >
                                {isGeneratingHearingChecklist ? (
                                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                                ) : (
                                    <Scale className="w-4 h-4 mr-2" />
                                )}
                                Checklist Legal (por Falante)
                            </Button>
                        </>
                    ) : (
                        /* Apostila-specific actions */
                        <>
                            <Button
                                variant="default"
                                onClick={handleConvertToUnifiedHil}
                                disabled={isConvertingToHil}
                                className="bg-indigo-600 hover:bg-indigo-700 text-white"
                            >
                                {isConvertingToHil ? (
                                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                                ) : (
                                    <ShieldCheck className="w-4 h-4 mr-2" />
                                )}
                                Validação Completa
                            </Button>

                            {/* Only show for legal apostilas */}
                            {isLegalDocument && (
                                <Button
                                    variant="outline"
                                    onClick={handleGenerateChecklist}
                                    disabled={isGeneratingChecklist || !formattedContent}
                                    className="border-emerald-300 text-emerald-700 hover:bg-emerald-50"
                                >
                                    {isGeneratingChecklist ? (
                                        <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                                    ) : (
                                        <Scale className="w-4 h-4 mr-2" />
                                    )}
                                    Gerar Checklist Legal (Art. 927 CPC)
                                </Button>
                            )}
                        </>
                    )}
                </div>
                )}

                {/* Validation Report Card */}
                {report && (
                    <div className="rounded-2xl border border-white/70 bg-sand/50 p-4 shadow-soft dark:bg-slate-900/40">
                        <div className="flex items-center justify-between mb-4">
                            <h3 className="font-semibold flex items-center gap-2">
                                {getScoreIcon(report.score)}
                                Nota de Fidelidade: <span className={getScoreColor(report.score)}>{report.score}/10</span>
                            </h3>
                            <Badge variant={report.approved ? "default" : "destructive"}>
                                {report.approved ? "Aprovado" : "Revisão Necessária"}
                            </Badge>
                        </div>

                        {report.error && (
                            <div className="mb-3 text-sm text-red-600">
                                {report.error}
                            </div>
                        )}

                        <Accordion
                            type="multiple"
                            defaultValue={[
                                report.omissions?.length ? "omissions" : "",
                                report.distortions?.length ? "distortions" : "",
                                report.structural_issues?.length ? "structural" : "",
                                report.observations ? "observations" : "",
                            ].filter(Boolean)}
                            className="space-y-2"
                        >
                            {report.omissions?.length > 0 && (
                                <AccordionItem value="omissions" className="rounded-2xl border border-red-200/70 bg-white/95">
                                    <AccordionTrigger className="px-3 py-2 text-[13px] font-semibold text-red-700">
                                        <span className="flex items-center gap-2">
                                            <AlertCircle className="w-3 h-3" /> Omissões Graves
                                            <Badge variant="outline" className="h-5 text-[10px] border-red-200 text-red-600">
                                                {report.omissions.length}
                                            </Badge>
                                        </span>
                                    </AccordionTrigger>
                                    <AccordionContent className="px-3 pb-3">
                                        <ul className="list-disc list-inside text-sm text-slate-700 dark:text-slate-300">
                                            {report.omissions.map((o, i) => (
                                                <li key={i}>{o}</li>
                                            ))}
                                        </ul>
                                    </AccordionContent>
                                </AccordionItem>
                            )}

                            {report.distortions?.length > 0 && (
                                <AccordionItem value="distortions" className="rounded-2xl border border-amber-200/70 bg-white/95">
                                    <AccordionTrigger className="px-3 py-2 text-[13px] font-semibold text-amber-700">
                                        <span className="flex items-center gap-2">
                                            <AlertTriangle className="w-3 h-3" /> Distorções Detectadas
                                            <Badge variant="outline" className="h-5 text-[10px] border-amber-200 text-amber-600">
                                                {report.distortions.length}
                                            </Badge>
                                        </span>
                                    </AccordionTrigger>
                                    <AccordionContent className="px-3 pb-3">
                                        <ul className="list-disc list-inside text-sm text-slate-700 dark:text-slate-300">
                                            {report.distortions.map((d, i) => (
                                                <li key={i}>{d}</li>
                                            ))}
                                        </ul>
                                    </AccordionContent>
                                </AccordionItem>
                            )}

                            {report.structural_issues?.length > 0 && (
                                <AccordionItem value="structural" className="rounded-2xl border border-yellow-200/70 bg-white/95">
                                    <AccordionTrigger className="px-3 py-2 text-[13px] font-semibold text-yellow-700">
                                        <span className="flex items-center gap-2">
                                            <AlertTriangle className="w-3 h-3" /> Problemas Estruturais
                                            <Badge variant="outline" className="h-5 text-[10px] border-yellow-200 text-yellow-700">
                                                {report.structural_issues.length}
                                            </Badge>
                                        </span>
                                    </AccordionTrigger>
                                    <AccordionContent className="px-3 pb-3">
                                        <ul className="list-disc list-inside text-sm text-slate-700 dark:text-slate-300">
                                            {report.structural_issues.map((s, i) => (
                                                <li key={i}>{s}</li>
                                            ))}
                                        </ul>
                                    </AccordionContent>
                                </AccordionItem>
                            )}

                            {report.observations && (
                                <AccordionItem value="observations" className="rounded-2xl border border-white/70 bg-white/95">
                                    <AccordionTrigger className="px-3 py-2 text-[13px] font-semibold">
                                        <span className="flex items-center gap-2">
                                            Observações
                                            <Badge variant="outline" className="h-5 text-[10px]">
                                                1
                                            </Badge>
                                        </span>
                                    </AccordionTrigger>
                                    <AccordionContent className="px-3 pb-3 text-xs text-slate-500 italic">
                                        {report.observations}
                                    </AccordionContent>
                                </AccordionItem>
                            )}
                        </Accordion>
                    </div>
                )}

                {/* Hearing Validation Report Card */}
                {isHearingContent && hearingValidation && (
                    <div className="rounded-2xl border border-white/70 bg-blue-50/50 p-4 shadow-soft dark:bg-blue-900/20 animate-in fade-in slide-in-from-top-2">
                        <div className="flex items-center justify-between mb-4">
                            <h3 className="font-semibold flex items-center gap-2">
                                {getScoreIcon(hearingValidation.score)}
                                Validação de Audiência: <span className={getScoreColor(hearingValidation.score)}>{hearingValidation.score}/10</span>
                            </h3>
                            <div className="flex items-center gap-2">
                                <Badge variant="outline" className="text-[10px]">
                                    {hearingValidation.mode}
                                </Badge>
                                <Badge variant={hearingValidation.approved ? "default" : "destructive"}>
                                    {hearingValidation.approved ? "Aprovado" : "Revisão Necessária"}
                                </Badge>
                            </div>
                        </div>

                        {/* Metrics Grid */}
                        <div className="grid gap-3 md:grid-cols-4 mb-4">
                            <div className="rounded-xl border border-white/70 bg-white/90 p-3 dark:bg-slate-900/40">
                                <div className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide mb-1">
                                    Completude
                                </div>
                                <div className={`text-lg font-bold ${hearingValidation.completude_rate >= 0.9 ? 'text-green-600' : hearingValidation.completude_rate >= 0.7 ? 'text-yellow-600' : 'text-red-600'}`}>
                                    {(hearingValidation.completude_rate * 100).toFixed(1)}%
                                </div>
                                <div className="text-[10px] text-muted-foreground">Falas sem [inaudível]</div>
                            </div>

                            <div className="rounded-xl border border-white/70 bg-white/90 p-3 dark:bg-slate-900/40">
                                <div className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide mb-1">
                                    Identificação
                                </div>
                                <div className={`text-lg font-bold ${hearingValidation.speaker_identification_rate >= 0.8 ? 'text-green-600' : hearingValidation.speaker_identification_rate >= 0.6 ? 'text-yellow-600' : 'text-red-600'}`}>
                                    {(hearingValidation.speaker_identification_rate * 100).toFixed(1)}%
                                </div>
                                <div className="text-[10px] text-muted-foreground">Falantes identificados</div>
                            </div>

                            <div className="rounded-xl border border-white/70 bg-white/90 p-3 dark:bg-slate-900/40">
                                <div className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide mb-1">
                                    Preservação
                                </div>
                                <div className={`text-lg font-bold ${hearingValidation.evidence_preservation_rate >= 0.95 ? 'text-green-600' : hearingValidation.evidence_preservation_rate >= 0.8 ? 'text-yellow-600' : 'text-red-600'}`}>
                                    {(hearingValidation.evidence_preservation_rate * 100).toFixed(1)}%
                                </div>
                                <div className="text-[10px] text-muted-foreground">Evidências preservadas</div>
                            </div>

                            <div className="rounded-xl border border-white/70 bg-white/90 p-3 dark:bg-slate-900/40">
                                <div className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide mb-1">
                                    Cronologia
                                </div>
                                <div className={`text-lg font-bold ${hearingValidation.chronology_valid ? 'text-green-600' : 'text-red-600'}`}>
                                    {hearingValidation.chronology_valid ? 'OK' : 'Erro'}
                                </div>
                                <div className="text-[10px] text-muted-foreground">Ordem temporal</div>
                            </div>
                        </div>

                        {/* Review Reason */}
                        {hearingValidation.requires_review && hearingValidation.review_reason && (
                            <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 mb-4 dark:bg-amber-900/20 dark:border-amber-800">
                                <div className="flex items-start gap-2">
                                    <AlertTriangle className="w-4 h-4 text-amber-600 mt-0.5 shrink-0" />
                                    <div>
                                        <div className="text-sm font-medium text-amber-800 dark:text-amber-200">
                                            Requer Revisão HIL
                                        </div>
                                        <div className="text-xs text-amber-700 dark:text-amber-300 mt-1">
                                            {hearingValidation.review_reason}
                                        </div>
                                    </div>
                                </div>
                            </div>
                        )}

                        {/* Critical Areas */}
                        {hearingValidation.critical_areas.length > 0 && (
                            <div className="flex flex-wrap gap-2 mb-4">
                                <span className="text-xs font-medium text-muted-foreground">Áreas críticas:</span>
                                {hearingValidation.critical_areas.map((area) => (
                                    <Badge key={area} variant="outline" className="text-[10px] bg-red-50 text-red-700 border-red-200">
                                        {area.replace(/_/g, ' ')}
                                    </Badge>
                                ))}
                            </div>
                        )}

                        {/* Issues Count */}
                        {hearingValidation.total_issues > 0 && (
                            <div className="text-sm text-muted-foreground">
                                {hearingValidation.total_issues} problema(s) detectado(s). Veja abaixo para detalhes.
                            </div>
                        )}
                    </div>
                )}

                {/* Hearing Checklist Panel */}
                {isHearingContent && hearingChecklist && (
                    <div className="rounded-2xl border border-emerald-200/70 bg-emerald-50/50 p-4 shadow-soft animate-in fade-in slide-in-from-top-2 dark:bg-emerald-900/20 dark:border-emerald-800">
                        <div className="flex items-center justify-between mb-4">
                            <h3 className="font-semibold flex items-center gap-2 text-emerald-800 dark:text-emerald-200">
                                <Scale className="w-5 h-5" />
                                Checklist Legal - Audiência
                            </h3>
                            <div className="flex items-center gap-2">
                                <Badge variant="outline" className="bg-emerald-100 text-emerald-800 border-emerald-300">
                                    {hearingChecklist.total_references} referência(s)
                                </Badge>
                                <Button
                                    variant="ghost"
                                    size="sm"
                                    onClick={() => setHearingChecklist(null)}
                                    className="h-7 w-7 p-0 text-slate-500 hover:text-slate-700"
                                >
                                    <XCircle className="w-4 h-4" />
                                </Button>
                            </div>
                        </div>

                        {/* By Speaker summary */}
                        {Object.keys(hearingChecklist.by_speaker).length > 0 && (
                            <div className="mb-4">
                                <div className="text-xs font-semibold text-emerald-700 dark:text-emerald-300 mb-2">
                                    Referências por Falante:
                                </div>
                                <div className="flex flex-wrap gap-2">
                                    {Object.entries(hearingChecklist.by_speaker).map(([speaker, refs]) => (
                                        <Badge key={speaker} variant="outline" className="text-[10px] bg-white dark:bg-slate-800">
                                            {speaker}: {(refs as any[]).length}
                                        </Badge>
                                    ))}
                                </div>
                            </div>
                        )}

                        {/* Checklist content */}
                        <div className="max-h-[400px] overflow-y-auto pr-2 custom-scrollbar mb-4">
                            <pre className="whitespace-pre-wrap text-sm text-slate-700 dark:text-slate-300 font-mono bg-white dark:bg-slate-950 p-4 rounded-xl border border-emerald-200 dark:border-emerald-800">
                                {hearingChecklist.checklist_markdown}
                            </pre>
                        </div>

                        {/* Actions */}
                        <div className="flex flex-wrap items-center justify-end gap-2 pt-3 border-t border-emerald-200 dark:border-emerald-800">
                            <Button
                                variant="outline"
                                size="sm"
                                onClick={handleCopyHearingChecklist}
                                className="border-emerald-300 text-emerald-700 hover:bg-emerald-100"
                            >
                                <Copy className="w-3 h-3 mr-2" />
                                Copiar
                            </Button>
                            <Button
                                variant="outline"
                                size="sm"
                                onClick={() => handleExportHearingChecklist("md")}
                                className="border-emerald-300 text-emerald-700 hover:bg-emerald-100"
                            >
                                <Download className="w-3 h-3 mr-2" />
                                Exportar .md
                            </Button>
                            <Button
                                variant="outline"
                                size="sm"
                                onClick={() => handleExportHearingChecklist("txt")}
                                className="border-emerald-300 text-emerald-700 hover:bg-emerald-100"
                            >
                                <Download className="w-3 h-3 mr-2" />
                                Exportar .txt
                            </Button>
                        </div>
                    </div>
                )}

                {/* HIL Audit Interface */}
                {analysisResult && (
                    <div className="rounded-2xl border border-white/70 bg-white/90 p-4 shadow-soft animate-in fade-in slide-in-from-top-2 dark:bg-slate-950">
                        <div className="flex items-center justify-between mb-4">
                            <h3 className="font-semibold flex items-center gap-2">
                                <Wrench className="w-4 h-4 text-orange-500" />
                                Relatório de Auditoria
                            </h3>
                            <div className="flex flex-wrap items-center gap-2">
                                <Badge variant="outline" className="bg-orange-50 text-orange-700 border-orange-200">
                                    {analysisResult.total_issues > 0
                                        ? `${analysisResult.total_issues} correções pendentes`
                                        : "Nenhuma correção pendente"}
                                </Badge>
                                {typeof analysisResult.total_content_issues === "number" && analysisResult.total_content_issues > 0 && (
                                    <Badge variant="outline" className="bg-yellow-50 text-yellow-800 border-yellow-200">
                                        {analysisResult.total_content_issues} alerta(s) de conteúdo
                                    </Badge>
                                )}
                            </div>
                        </div>

                        {/* Content Alerts */}
                        {hasContentAlerts && (
                            <Accordion type="single" collapsible defaultValue="content-alerts" className="mb-4">
                            <AccordionItem value="content-alerts" className="rounded-2xl border border-yellow-200/70 bg-yellow-50/60 dark:bg-yellow-900/20">
                                    <AccordionTrigger className="px-3 py-2 text-[13px] font-semibold text-yellow-800 dark:text-yellow-200">
                                        <span className="flex items-center gap-2">
                                            <AlertTriangle className="w-3 h-3" /> Alertas de Conteúdo
                                            <Badge variant="outline" className="h-5 text-[10px] border-yellow-200 text-yellow-800">
                                                {contentAlertCount}
                                            </Badge>
                                        </span>
                                    </AccordionTrigger>
                                    <AccordionContent className="px-3 pb-3">
                                        {analysisResult.compression_warning && (
                                            <p className={`text-xs mb-2 ${analysisResult.compression_ratio && analysisResult.compression_ratio < 0.7 ? 'text-red-600 font-medium' : 'text-yellow-700 dark:text-yellow-300'}`}>
                                                {analysisResult.compression_ratio && analysisResult.compression_ratio < 0.7 ? '🚨' : '⚠️'} {analysisResult.compression_warning}
                                                {analysisResult.compression_ratio && (
                                                    <span className="ml-2 text-muted-foreground">
                                                        (Taxa: {Math.round(analysisResult.compression_ratio * 100)}%)
                                                    </span>
                                                )}
                                            </p>
                                        )}
                                        {analysisResult.missing_laws && analysisResult.missing_laws.length > 0 && (
                                            <div className="mb-2">
                                                <span className="text-xs font-medium text-yellow-800 dark:text-yellow-200">📜 Leis omitidas:</span>
                                                <div className="flex flex-wrap gap-1 mt-1">
                                                    {analysisResult.missing_laws.map((law, i) => (
                                                        <Badge key={i} variant="outline" className="text-[10px] bg-yellow-100 dark:bg-yellow-900/50 border-yellow-300">
                                                            Lei {law}
                                                        </Badge>
                                                    ))}
                                                </div>
                                            </div>
                                        )}
                                        {analysisResult.missing_sumulas && analysisResult.missing_sumulas.length > 0 && (
                                            <div className="mb-2">
                                                <span className="text-xs font-medium text-yellow-800 dark:text-yellow-200">⚖️ Súmulas omitidas:</span>
                                                <div className="flex flex-wrap gap-1 mt-1">
                                                    {analysisResult.missing_sumulas.map((sumula, i) => (
                                                        <Badge key={i} variant="outline" className="text-[10px] bg-purple-100 dark:bg-purple-900/50 border-purple-300">
                                                            {sumula}
                                                        </Badge>
                                                    ))}
                                                </div>
                                            </div>
                                        )}
                                        {analysisResult.missing_julgados && analysisResult.missing_julgados.length > 0 && (
                                            <div className="mb-2">
                                                <span className="text-xs font-medium text-yellow-800 dark:text-yellow-200">🔨 Julgados omitidos:</span>
                                                <div className="flex flex-wrap gap-1 mt-1">
                                                    {analysisResult.missing_julgados.map((julgado, i) => (
                                                        <Badge key={i} variant="outline" className="text-[10px] bg-blue-100 dark:bg-blue-900/50 border-blue-300">
                                                            {julgado}
                                                        </Badge>
                                                    ))}
                                                </div>
                                            </div>
                                        )}
                                        {analysisResult.missing_decretos && analysisResult.missing_decretos.length > 0 && (
                                            <div className="mb-2">
                                                <span className="text-xs font-medium text-yellow-800 dark:text-yellow-200">📋 Decretos omitidos:</span>
                                                <div className="flex flex-wrap gap-1 mt-1">
                                                    {analysisResult.missing_decretos.map((decreto, i) => (
                                                        <Badge key={i} variant="outline" className="text-[10px] bg-orange-100 dark:bg-orange-900/50 border-orange-300">
                                                            Decreto {decreto}
                                                        </Badge>
                                                    ))}
                                                </div>
                                            </div>
                                        )}
                                        {canConvertContentAlerts && (
                                            <div className="mt-3 flex flex-wrap items-center gap-2">
                                                <Button
                                                    variant="outline"
                                                    size="sm"
                                                    onClick={handleConvertContentAlerts}
                                                    className="border-yellow-300 text-yellow-800 hover:bg-yellow-100"
                                                >
                                                    Enviar alertas para Correções (HIL)
                                                </Button>
                                                <span className="text-[11px] text-muted-foreground">
                                                    Os alertas serão adicionados na aba Correções (HIL).
                                                </span>
                                            </div>
                                        )}
                                    </AccordionContent>
                                </AccordionItem>
                            </Accordion>
                        )}

                        {!isDashboardVariant && pendingFixes.length > 0 && (
                            <div className="mb-4 flex flex-wrap items-center gap-2 text-xs">
                                <span className="font-medium text-muted-foreground">Filtro:</span>
                                <Button
                                    variant={severityFilter === "all" ? "secondary" : "outline"}
                                    size="sm"
                                    className="h-7 rounded-full px-3 text-[11px]"
                                    onClick={() => setSeverityFilter("all")}
                                >
                                    Todas ({pendingFixes.length})
                                </Button>
                                <Button
                                    variant={severityFilter === "high" ? "secondary" : "outline"}
                                    size="sm"
                                    className="h-7 rounded-full px-3 text-[11px]"
                                    onClick={() => setSeverityFilter("high")}
                                >
                                    Alta ({severityCounts.high})
                                </Button>
                                <Button
                                    variant={severityFilter === "medium" ? "secondary" : "outline"}
                                    size="sm"
                                    className="h-7 rounded-full px-3 text-[11px]"
                                    onClick={() => setSeverityFilter("medium")}
                                >
                                    Média ({severityCounts.medium})
                                </Button>
                                <Button
                                    variant={severityFilter === "low" ? "secondary" : "outline"}
                                    size="sm"
                                    className="h-7 rounded-full px-3 text-[11px]"
                                    onClick={() => setSeverityFilter("low")}
                                >
                                    Baixa ({severityCounts.low})
                                </Button>
                                <div className="flex-1" />
                                <Button
                                    variant="outline"
                                    size="sm"
                                    className="h-7 rounded-full px-3 text-[11px]"
                                    onClick={selectVisibleFixes}
                                    disabled={!filteredPendingFixes.length}
                                >
                                    Selecionar visíveis
                                </Button>
                                <Button
                                    variant="ghost"
                                    size="sm"
                                    className="h-7 rounded-full px-3 text-[11px]"
                                    onClick={clearSelectedFixes}
                                    disabled={selectedFixes.size === 0}
                                >
                                    Limpar seleção
                                </Button>
                            </div>
                        )}

                        {/* Pending Fixes List */}
                        {pendingFixes.length > 0 && (
                            <div className="space-y-3 mb-6 max-h-[300px] overflow-y-auto pr-2 custom-scrollbar">
                                {filteredPendingFixes.length === 0 && (
                                    <div className="text-sm text-slate-500">
                                        Nenhuma correção para este filtro.
                                    </div>
                                )}
                                {filteredPendingFixes.map((fix) => {
                                    const labelMap: Record<string, string> = {
                                        duplicate_section: "Seção Duplicada",
                                        duplicate_paragraph: "Parágrafo Duplicado",
                                        heading_numbering: "Numeração de Títulos",
                                        omission: "Omissão",
                                        distortion: "Distorção",
                                    };
                                    const label = labelMap[fix.type] || fix.type;
                                    const isSemanticFix = fix.type === "omission" || fix.type === "distortion";
                                    const borderColor = isSemanticFix
                                        ? selectedFixes.has(fix.id)
                                            ? "bg-amber-50 border-amber-300 dark:bg-amber-900/20 dark:border-amber-700"
                                            : "bg-amber-50/50 border-amber-200/70 hover:bg-amber-50 dark:bg-amber-900/10 dark:border-amber-800"
                                        : selectedFixes.has(fix.id)
                                            ? "bg-primary/10 border-primary/30 dark:bg-slate-900/40 dark:border-slate-700"
                                            : "bg-white/80 border-white/70 hover:bg-white dark:bg-slate-900/30 dark:border-slate-800";
                                    return (
                                        <div
                                            key={fix.id}
                                            className={`flex items-start gap-3 p-3 rounded-xl border cursor-pointer transition-colors ${borderColor}`}
                                            onClick={(event) => {
                                                const target = event.target as HTMLElement;
                                                if (target.closest("[role='checkbox']")) return;
                                                toggleFix(fix.id);
                                            }}
                                        >
                                            <Checkbox
                                                checked={selectedFixes.has(fix.id)}
                                                onCheckedChange={() => toggleFix(fix.id)}
                                                className="mt-1"
                                            />
                                            <div className="flex-1">
                                                <div className="flex items-center justify-between flex-wrap gap-1">
                                                    <span className={`text-xs font-bold uppercase tracking-wider ${isSemanticFix ? "text-amber-700" : "text-slate-500"}`}>
                                                        {label}
                                                        {fix.source && (
                                                            <span className="ml-2 text-[9px] font-normal text-muted-foreground">
                                                                ({fix.source === "fidelity_audit" ? "fidelidade" : "estrutural"})
                                                            </span>
                                                        )}
                                                    </span>
                                                    <div className="flex items-center gap-1">
                                                        {/* Confidence indicator */}
                                                        {fix.confidence !== undefined && (
                                                            <Badge
                                                                className="text-[9px] h-4"
                                                                variant={
                                                                    fix.confidence >= 0.85 ? "default" :
                                                                    fix.confidence >= 0.70 ? "secondary" :
                                                                    fix.confidence >= 0.50 ? "outline" : "destructive"
                                                                }
                                                            >
                                                                {fix.confidence >= 0.85 ? "✓ Alta" :
                                                                 fix.confidence >= 0.70 ? "Média" :
                                                                 fix.confidence >= 0.50 ? "Baixa" : "⚠️ Incerta"}
                                                                {" "}{Math.round(fix.confidence * 100)}%
                                                            </Badge>
                                                        )}
                                                        <Badge
                                                            className="text-[10px] h-5"
                                                            variant={fix.severity === "high" ? "destructive" : isSemanticFix ? "outline" : "outline"}
                                                        >
                                                            {fix.action}
                                                        </Badge>
                                                    </div>
                                                </div>
                                                <p className="text-sm text-slate-700 dark:text-slate-300 mt-1 line-clamp-2">
                                                    {fix.description}
                                                </p>
                                                {/* Show patch preview for semantic fixes */}
                                                {isSemanticFix && fix.patch?.new_text && (
                                                    <div className="mt-2 p-2 bg-green-50 dark:bg-green-900/20 rounded border border-green-200 dark:border-green-800">
                                                        <span className="text-[10px] font-semibold text-green-700 dark:text-green-300">
                                                            Sugestão de correção:
                                                        </span>
                                                        <p className="text-xs text-green-800 dark:text-green-200 mt-1 line-clamp-3">
                                                            {fix.patch.new_text}
                                                        </p>
                                                    </div>
                                                )}
                                                {/* Show evidence for semantic fixes */}
                                                {isSemanticFix && fix.evidence && fix.evidence.length > 0 && (
                                                    <div className="mt-2 p-2 bg-blue-50 dark:bg-blue-900/20 rounded border border-blue-200 dark:border-blue-800">
                                                        <span className="text-[10px] font-semibold text-blue-700 dark:text-blue-300">
                                                            Evidência do RAW:
                                                        </span>
                                                        <p className="text-xs text-blue-800 dark:text-blue-200 mt-1 line-clamp-2 italic">
                                                            {fix.evidence[0]}
                                                        </p>
                                                    </div>
                                                )}
                                                {/* Show validation notes */}
                                                {fix.validation_notes && fix.validation_notes.length > 0 && (
                                                    <div className="mt-2 p-2 bg-slate-50 dark:bg-slate-800/50 rounded border border-slate-200 dark:border-slate-700">
                                                        <span className="text-[10px] font-semibold text-slate-600 dark:text-slate-400">
                                                            Validação contra RAW:
                                                        </span>
                                                        <ul className="text-[10px] text-slate-600 dark:text-slate-400 mt-1 space-y-0.5">
                                                            {fix.validation_notes.slice(0, 3).map((note, i) => (
                                                                <li key={i}>{note}</li>
                                                            ))}
                                                        </ul>
                                                    </div>
                                                )}
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>
                        )}

                        {!isDashboardVariant && analysisResult.total_issues === 0 && !hasContentAlerts && (
                            <div className="text-sm text-slate-500">
                                Nenhuma correção estrutural pendente.
                            </div>
                        )}

                        {!isDashboardVariant && appliedFixes.length > 0 && (
                            <div className="border border-green-200 bg-green-50/70 rounded-md p-3 text-sm">
                                <div className="font-medium text-green-700 mb-2">Correções aplicadas</div>
                                <ul className="list-disc pl-5 space-y-1 text-green-800">
                                    {appliedFixes.map((fix, idx) => (
                                        <li key={`${fix}-${idx}`}>{fix}</li>
                                    ))}
                                </ul>
                            </div>
                        )}

                        {/* Action Footer */}
                        {!isDashboardVariant && (
                        <div className="flex justify-end gap-3 pt-4 border-t">
                            <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => setAnalysisResult(null)}
                            >
                                Cancelar
                            </Button>
                            {pendingFixes.length > 0 && (() => {
                                if (isHearingContent) {
                                    return (
                                        <Button
                                            onClick={handleApplyHearingRevisions}
                                            disabled={isApplying || selectedFixes.size === 0}
                                            size="sm"
                                            className="bg-indigo-600 hover:bg-indigo-700 text-white"
                                        >
                                            {isApplying ? (
                                                <Loader2 className="w-3 h-3 mr-2 animate-spin" />
                                            ) : (
                                                <CheckCircle className="w-3 h-3 mr-2" />
                                            )}
                                            Aplicar {selectedFixes.size} Correções (IA)
                                        </Button>
                                    );
                                }
                                const hasSemanticFixes = pendingFixes.some(
                                    (f) => f.type === "omission" || f.type === "distortion"
                                );
                                const structuralCount = pendingFixes.filter(
                                    (f) => f.type !== "omission" && f.type !== "distortion"
                                ).length;
                                const semanticCount = pendingFixes.filter(
                                    (f) => f.type === "omission" || f.type === "distortion"
                                ).length;

                                return (
                                    <Button
                                        onClick={hasSemanticFixes ? handleApplyUnifiedHil : handleApplyApproved}
                                        disabled={isApplying || selectedFixes.size === 0}
                                        size="sm"
                                        className="bg-indigo-600 hover:bg-indigo-700 text-white"
                                    >
                                        {isApplying ? (
                                            <Loader2 className="w-3 h-3 mr-2 animate-spin" />
                                        ) : (
                                            <CheckCircle className="w-3 h-3 mr-2" />
                                        )}
                                        Aplicar {selectedFixes.size} Correções
                                        {hasSemanticFixes && (
                                            <span className="ml-1 text-[10px] opacity-80">
                                                ({structuralCount} est. + {semanticCount} sem.)
                                            </span>
                                        )}
                                    </Button>
                                );
                            })()}
                        </div>
                        )}
                    </div>
                )}

                {/* AI Suggestions Result */}
                {!isDashboardVariant && suggestions && (
                    <div className="p-4 border border-indigo-100 bg-indigo-50/50 rounded-md">
                        <h4 className="font-semibold text-indigo-900 mb-2 flex items-center gap-2">
                            <span className="text-lg">✨</span> Sugestões de Correção
                        </h4>
                        <pre className="whitespace-pre-wrap text-sm text-slate-700 dark:text-slate-300 font-mono bg-white dark:bg-slate-950 p-3 rounded border">
                            {suggestions}
                        </pre>
                        <p className="text-xs text-slate-500 mt-2 italic">
                            Copie o conteúdo acima e aplique manualmente no editor onde necessário.
                        </p>
                    </div>
                )}

                {/* Legal Checklist Panel */}
                {!isDashboardVariant && legalChecklist && (
                    <div className="rounded-2xl border border-emerald-200/70 bg-emerald-50/50 p-4 shadow-soft animate-in fade-in slide-in-from-top-2 dark:bg-emerald-900/20 dark:border-emerald-800">
                        <div className="flex items-center justify-between mb-4">
                            <h3 className="font-semibold flex items-center gap-2 text-emerald-800 dark:text-emerald-200">
                                <Scale className="w-5 h-5" />
                                Checklist de Referências Legais (Art. 927 CPC)
                            </h3>
                            <div className="flex items-center gap-2">
                                <Badge variant="outline" className="bg-emerald-100 text-emerald-800 border-emerald-300">
                                    {legalChecklist.total_references} referência(s)
                                </Badge>
                                <Button
                                    variant="ghost"
                                    size="sm"
                                    onClick={() => setLegalChecklist(null)}
                                    className="h-7 w-7 p-0 text-slate-500 hover:text-slate-700"
                                >
                                    <XCircle className="w-4 h-4" />
                                </Button>
                            </div>
                        </div>

                        {/* Checklist content */}
                        <div className="max-h-[400px] overflow-y-auto pr-2 custom-scrollbar mb-4">
                            <pre className="whitespace-pre-wrap text-sm text-slate-700 dark:text-slate-300 font-mono bg-white dark:bg-slate-950 p-4 rounded-xl border border-emerald-200 dark:border-emerald-800">
                                {legalChecklist.checklist_markdown}
                            </pre>
                        </div>

                        {/* Actions */}
                        <div className="flex flex-wrap items-center justify-between gap-3 pt-3 border-t border-emerald-200 dark:border-emerald-800">
                            <p className="text-xs text-emerald-700 dark:text-emerald-300 italic">
                                Inclui: Súmulas Vinculantes, ADI/ADC/ADPF, IAC, IRDR, Temas Repetitivos, Leis, Decretos, Códigos e mais.
                            </p>
                            <div className="flex flex-wrap items-center gap-2">
                                <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={handleCopyChecklist}
                                    className="border-emerald-300 text-emerald-700 hover:bg-emerald-100"
                                >
                                    <Copy className="w-3 h-3 mr-2" />
                                    Copiar
                                </Button>
                                <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={() => handleExportChecklist("md")}
                                    className="border-emerald-300 text-emerald-700 hover:bg-emerald-100"
                                >
                                    <Download className="w-3 h-3 mr-2" />
                                    Exportar .md
                                </Button>
                                <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={() => handleExportChecklist("txt")}
                                    className="border-emerald-300 text-emerald-700 hover:bg-emerald-100"
                                >
                                    <Download className="w-3 h-3 mr-2" />
                                    Exportar .txt
                                </Button>
                                <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={handleExportApostilaWithChecklist}
                                    className="border-blue-300 text-blue-700 hover:bg-blue-100"
                                >
                                    <FileDown className="w-3 h-3 mr-2" />
                                    Exportar Apostila + Checklist
                                </Button>
                                <Button
                                    variant="default"
                                    size="sm"
                                    onClick={handleInsertChecklist}
                                    className="bg-emerald-600 hover:bg-emerald-700 text-white"
                                >
                                    <FileInput className="w-3 h-3 mr-2" />
                                    Inserir na Apostila
                                </Button>
                            </div>
                        </div>
                    </div>
                )}
            </CardContent>
        </Card>
    );
}

export default QualityPanel;
