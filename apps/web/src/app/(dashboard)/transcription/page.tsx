'use client';

import { useState, useRef, useEffect, useCallback, useMemo, type CSSProperties } from 'react';
	import { Upload, FileAudio, FileVideo, Mic, CheckCircle, AlertCircle, Loader2, FileText, FileType, Book, MessageSquare, ChevronUp, ChevronDown, X, Users, Gavel, ListChecks, Star, Clock, Trash2, Info, AlertTriangle, Edit3, Search, RefreshCw, SlidersHorizontal, Plus, PanelRightOpen, LayoutTemplate, Heading, Table2, Scissors, ArrowLeftRight, Type } from 'lucide-react';
import { toast } from 'sonner';
import apiClient from '@/lib/api-client';
import { useDocumentStore } from '@/stores/document-store';
	import { Button } from '@/components/ui/button';
	import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
	import { Label } from '@/components/ui/label';
	import { Badge } from '@/components/ui/badge';
	import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion';
	// import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
	// import { Textarea } from '@/components/ui/textarea';
	// import { ScrollArea } from '@/components/ui/scroll-area';
	// import { Separator } from '@/components/ui/separator';
import { Switch } from '@/components/ui/switch';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { QualityPanel } from '@/components/dashboard/quality-panel';
import { AuditIssuesPanel } from '@/components/dashboard/audit-issues-panel';
import { PreventiveAuditPanel } from '@/components/dashboard/preventive-audit-panel';
import { TranscriptionPromptPicker } from '@/components/dashboard/transcription-prompt-picker';
import { SyncedTranscriptViewer } from '@/components/dashboard/synced-transcript-viewer';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { DiffConfirmDialog } from '@/components/dashboard/diff-confirm-dialog';
import { MarkdownEditorPanel, MarkdownPreview, RichHtmlPreview } from '@/components/dashboard/markdown-editor-panel';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Textarea } from '@/components/ui/textarea';
import { Input } from '@/components/ui/input';
import { buildPreventiveHilIssues, type HilIssue } from '@/lib/preventive-hil';
import { buildPreventiveAuditStatus } from '@/lib/preventive-audit';
import { AnimatedContainer } from '@/components/ui/animated-container';

function SettingInfoPopover({ children }: { children: React.ReactNode }) {
    const [open, setOpen] = useState(false);

    return (
        <Popover open={open} onOpenChange={setOpen}>
            <PopoverTrigger asChild>
                <button
                    type="button"
                    className="inline-flex h-5 w-5 items-center justify-center rounded-md border border-input bg-background text-muted-foreground hover:text-foreground"
                    aria-label="Ajuda"
                    onClick={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        setOpen((value) => !value);
                    }}
                >
                    <Info className="h-3.5 w-3.5" />
                </button>
            </PopoverTrigger>
            <PopoverContent side="top" className="max-w-sm text-xs leading-relaxed">
                {children}
            </PopoverContent>
        </Popover>
    );
}

type PromptSnippet = { id: string; title: string; template: string };
type DocumentTheme = { id: string; title: string; description: string };
type DocumentLayout = {
    margins: 'compact' | 'normal' | 'wide';
    headerText: string;
    footerText: string;
    showHeaderFooter: boolean;
    pageFrame: boolean;
    fontFamily: string;
    fontSize: number;
    lineHeight: number;
    paragraphSpacing: number;
};

const PROMPT_SNIPPETS = {
    apostila: [
        {
            id: 'apostila-table-columns',
            title: 'Ajustar colunas do Quadro-síntese',
            template: [
                'Personalização de TABELAS (sem alterar tom/estrutura):',
                '- No **Quadro-síntese**, use estas colunas (mantendo regras de não inventar):',
                '  1) Conceito/tema',
                '  2) Regra/definição (1 frase)',
                '  3) Requisitos/condições',
                '  4) Base legal/jurisprudência citada (ou "—")',
                '  5) Exemplo/pegadinha (ou "—")',
                '- Não gere a "Tabela 2 — Como a banca cobra / pegadinhas".',
            ].join('\n'),
        },
        {
            id: 'apostila-resumo',
            title: 'Adicionar resumo por tópico',
            template: [
                'Após o quadro-síntese de cada tópico, adicione:',
                '#### 🧾 Resumo do tópico (8 bullets)',
                '- 8 bullets curtos, objetivos, **sem inventar**.',
            ].join('\n'),
        },
        {
            id: 'apostila-fluxograma',
            title: 'Adicionar fluxograma (Mermaid)',
            template: [
                'Após o quadro-síntese de cada tópico, adicione:',
                '#### 🔁 Fluxograma (Mermaid)',
                '```mermaid',
                'flowchart TD',
                '  A[Conceito] --> B[Requisitos]',
                '  B --> C[Consequência/efeito]',
                '```',
                'Regras: use apenas nós/etapas que aparecerem no trecho; se faltar informação, omita o nó.',
            ].join('\n'),
        },
        {
            id: 'apostila-mapa-mental',
            title: 'Adicionar mapa mental (bullets)',
            template: [
                'Após o quadro-síntese de cada tópico, adicione:',
                '#### 🧠 Mapa mental (bullets)',
                '- Tema',
                '  - Subtema 1',
                '    - Pontos-chave (apenas do trecho)',
                '  - Subtema 2',
            ].join('\n'),
        },
        {
            id: 'apostila-questionario',
            title: 'Adicionar questionário + gabarito',
            template: [
                'Após o quadro-síntese de cada tópico, adicione:',
                '#### 📝 Questionário (5 questões)',
                '- 5 questões (múltipla escolha ou V/F), baseadas **somente** no trecho.',
                '#### ✅ Gabarito',
                '- 1) A',
                '- 2) C',
                '- 3) V',
                '- 4) F',
                '- 5) B',
            ].join('\n'),
        },
    ] satisfies PromptSnippet[],
    hearingAudiencia: [
        {
            id: 'audiencia-registro-colunas',
            title: 'Customizar tabela de decisões/atos',
            template: [
                'Personalização de TABELAS/EXTRAS (sem alterar tom/estrutura):',
                '- Quando houver atos/decisões **explícitos**, inclua também a coluna "Documento/Prova citada" (ou "—").',
                '- Não invente prazo/responsável/timestamp: se não estiver dito, use "—".',
            ].join('\n'),
        },
        {
            id: 'audiencia-providencias',
            title: 'Lista de providências (se ditas)',
            template: [
                'Ao final da fase em que surgirem determinações **explícitas**, adicione:',
                '#### ✅ Providências (somente as ditas em audiência)',
                '- Liste em bullets curtos: ação + responsável (se dito) + prazo (se dito).',
                '- Se não estiver dito, use "—" e **não invente**.',
            ].join('\n'),
        },
    ] satisfies PromptSnippet[],
    hearingReuniao: [
        {
            id: 'reuniao-tabela-colunas',
            title: 'Customizar tabela de encaminhamentos',
            template: [
                'Personalização de TABELAS/EXTRAS (sem alterar tom/estrutura):',
                '- Na tabela de "Decisões e encaminhamentos", adicione a coluna "Dependências/Pré-requisitos" (ou "—").',
                '- Não invente responsável/prazo; se não estiver dito, use "—".',
            ].join('\n'),
        },
        {
            id: 'reuniao-checklist',
            title: 'Checklist de ações (se explícitas)',
            template: [
                'Ao final de cada pauta com encaminhamentos **explícitos**, adicione:',
                '#### ✅ Checklist de ações',
                '- [ ] Ação (responsável — / prazo —)',
                '- [ ] Ação (responsável — / prazo —)',
                'Regras: só crie itens a partir do que foi dito; se faltar responsável/prazo, deixe "—".',
            ].join('\n'),
        },
    ] satisfies PromptSnippet[],
    fidelity: [
        {
            id: 'fidelidade-safe',
            title: 'Fidelidade: ajustes mínimos',
            template: [
                'Ajustes permitidos (sem mexer em estrutura):',
                '- Corrigir apenas gramática/pontuação.',
                '- Remover muletas (“né”, “tipo”) quando não afetar sentido.',
                '- Não resumir e não reorganizar tópicos.',
            ].join('\n'),
        },
    ] satisfies PromptSnippet[],
    depoimento: [
        {
            id: 'depoimento-safe',
            title: 'Depoimento: ajustes mínimos',
            template: [
                'Ajustes permitidos (sem mexer em estrutura):',
                '- Manter perguntas e respostas em sequência.',
                '- Uma fala por parágrafo quando houver identificação.',
                '- Não resumir e não transformar em discurso indireto.',
            ].join('\n'),
        },
    ] satisfies PromptSnippet[],
} as const;

const DOCUMENT_THEMES: DocumentTheme[] = [
    {
        id: 'classic',
        title: 'Clássico',
        description: 'Tabela padrão com zebra suave e cabeçalho claro.',
    },
    {
        id: 'minimal',
        title: 'Minimal',
        description: 'Sem zebra, bordas discretas e visual limpo.',
    },
    {
        id: 'executive',
        title: 'Executivo',
        description: 'Cabeçalho destacado e contraste maior.',
    },
    {
        id: 'academic',
        title: 'Acadêmico',
        description: 'Linhas sutis e foco em legibilidade.',
    },
];

export default function TranscriptionPage() {
    const [files, setFiles] = useState<File[]>([]);
    const [publicUrl, setPublicUrl] = useState('');
    const [transcriptionType, setTranscriptionType] = useState<'apostila' | 'hearing'>('apostila');
    const [mode, setMode] = useState('FIDELIDADE');
    const [thinkingLevel, setThinkingLevel] = useState('medium');
    const [customPrompt, setCustomPrompt] = useState('');
    const [documentTheme, setDocumentTheme] = useState('classic');
    const [documentLayout, setDocumentLayout] = useState<DocumentLayout>({
        margins: 'normal',
        headerText: '',
        footerText: '',
        showHeaderFooter: true,
        pageFrame: true,
        fontFamily: '',
        fontSize: 15,
        lineHeight: 1.5,
        paragraphSpacing: 8,
    });
    const [highAccuracy, setHighAccuracy] = useState(false);
    const [enableDiarization, setEnableDiarization] = useState(false);
    const [isProcessing, setIsProcessing] = useState(false);
    const [selectedModel, setSelectedModel] = useState('gemini-3-flash-preview');
    const [result, setResult] = useState<string | null>(null);
    const [rawResult, setRawResult] = useState<string | null>(null);
    const [richTextHtml, setRichTextHtml] = useState<string | null>(null);
    const [richTextJson, setRichTextJson] = useState<any | null>(null);
    const [richTextMeta, setRichTextMeta] = useState<any | null>(null);
    const [previewMode, setPreviewMode] = useState<'formatted' | 'raw'>('formatted');
    const [isEditingResult, setIsEditingResult] = useState(false);
    const [draftResult, setDraftResult] = useState<string | null>(null);
    const [report, setReport] = useState<string | null>(null);
    const [reportPaths, setReportPaths] = useState<Record<string, any> | null>(null);
    const [preventiveAudit, setPreventiveAudit] = useState<any | null>(null);
    const [preventiveAuditMarkdown, setPreventiveAuditMarkdown] = useState<string | null>(null);
    const [preventiveAuditLoading, setPreventiveAuditLoading] = useState(false);
    const [preventiveAuditError, setPreventiveAuditError] = useState<string | null>(null);
    const [issueAssistantOpen, setIssueAssistantOpen] = useState(false);
    const [issueAssistantIssue, setIssueAssistantIssue] = useState<any | null>(null);
    const [issueAssistantInstruction, setIssueAssistantInstruction] = useState('');
    const [issueAssistantForce, setIssueAssistantForce] = useState(false);
    const [useRawCache, setUseRawCache] = useState(true);
    const [autoApplyFixes, setAutoApplyFixes] = useState(true);
    const [autoApplyContentFixes, setAutoApplyContentFixes] = useState(false);
    const [skipLegalAudit, setSkipLegalAudit] = useState(false);
    const [skipFidelityAudit, setSkipFidelityAudit] = useState(false);
    const [activeTab, setActiveTab] = useState('preview');
    const [hearingCaseId, setHearingCaseId] = useState('');
    const [hearingGoal, setHearingGoal] = useState('alegacoes_finais');
    const [hearingPayload, setHearingPayload] = useState<any | null>(null);
    const [hearingTranscript, setHearingTranscript] = useState<string | null>(null);
    const [hearingFormatted, setHearingFormatted] = useState<string | null>(null);
    const [hearingFormatMode, setHearingFormatMode] = useState<'none' | 'audiencia' | 'reuniao' | 'depoimento'>('audiencia');
    const [hearingUseCustomPrompt, setHearingUseCustomPrompt] = useState(false);
    const [hearingAllowIndirect, setHearingAllowIndirect] = useState(false);
    const [hearingAllowSummary, setHearingAllowSummary] = useState(false);
    const [hearingIncludeTimestamps, setHearingIncludeTimestamps] = useState(true);
    const [hearingCustomPrompt, setHearingCustomPrompt] = useState('');
    const [hearingDocumentTheme, setHearingDocumentTheme] = useState('classic');
    const [hearingDocumentLayout, setHearingDocumentLayout] = useState<DocumentLayout>({
        margins: 'normal',
        headerText: '',
        footerText: '',
        showHeaderFooter: true,
        pageFrame: true,
        fontFamily: '',
        fontSize: 15,
        lineHeight: 1.5,
        paragraphSpacing: 8,
    });
    const [hearingSpeakers, setHearingSpeakers] = useState<any[]>([]);
    const [enrollName, setEnrollName] = useState('');
    const [enrollRole, setEnrollRole] = useState('outro');
    const [enrollFile, setEnrollFile] = useState<File | null>(null);
    const [isEnrolling, setIsEnrolling] = useState(false);
    const [isSavingSpeakers, setIsSavingSpeakers] = useState(false);
    const [hearingCourt, setHearingCourt] = useState('');
    const [hearingCity, setHearingCity] = useState('');
    const [hearingDate, setHearingDate] = useState('');
    const [hearingNotes, setHearingNotes] = useState('');
    const [isDragActive, setIsDragActive] = useState(false);
    const [mediaUrl, setMediaUrl] = useState<string | null>(null);
    const [jobMediaFiles, setJobMediaFiles] = useState<Array<{ name: string; url: string }>>([]);
    const [playbackRate, setPlaybackRate] = useState(1);
    const [currentTime, setCurrentTime] = useState(0);
    const [mediaDuration, setMediaDuration] = useState(0);
    const [activeSegmentId, setActiveSegmentId] = useState<string | null>(null);
    const [etaSeconds, setEtaSeconds] = useState<number | null>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);
    const mediaRef = useRef<HTMLMediaElement | null>(null);
    const lastAutoSaveKeyRef = useRef<string | null>(null);
    const jobsSelectAllRef = useRef<HTMLInputElement>(null);
    const savedDocsSelectAllRef = useRef<HTMLInputElement>(null);
    const preventiveAuditKeyRef = useRef<string | null>(null);
    const [jobHistory, setJobHistory] = useState<any[]>([]);
    const [jobsLoading, setJobsLoading] = useState(false);
    const [savedDocuments, setSavedDocuments] = useState<any[]>([]);
    const [savedDocsLoading, setSavedDocsLoading] = useState(false);
    const [activeJobId, setActiveJobId] = useState<string | null>(null);
    const [activeDocumentName, setActiveDocumentName] = useState<string>('Documento');
    const [jobQuality, setJobQuality] = useState<any | null>(null);
    const [selectedJobIds, setSelectedJobIds] = useState<Set<string>>(new Set());
    const [selectedSavedDocIds, setSelectedSavedDocIds] = useState<Set<string>>(new Set());
    const [hilDiagnostics, setHilDiagnostics] = useState<{
        contentChanged?: boolean | null;
        contentError?: string | null;
        contentChange?: { before_chars?: number; after_chars?: number; delta_chars?: number } | null;
        evidence?: Array<{ issueId?: string; reference?: string; snippet?: string; suggestedSection?: string }>;
    } | null>(null);
    const [autoAppliedSummary, setAutoAppliedSummary] = useState<{
        structural: string[];
        content: string[];
        total: number;
    } | null>(null);

    // SSE Progress State
    const [progressStage, setProgressStage] = useState<string>('');
    const [progressPercent, setProgressPercent] = useState<number>(0);
    const [progressMessage, setProgressMessage] = useState<string>('');
    const [logs, setLogs] = useState<{ timestamp: string; message: string }[]>([]);
    const [progressLogsOpen, setProgressLogsOpen] = useState(false);
    const [progressDockMinimized, setProgressDockMinimized] = useState(false);

    // HIL Audit State
    const [auditIssues, setAuditIssues] = useState<any[]>([]);
    const [selectedIssues, setSelectedIssues] = useState<Set<string>>(new Set());

    const [isApplyingFixes, setIsApplyingFixes] = useState(false);
    const [showDiffConfirm, setShowDiffConfirm] = useState(false);
    const [pendingRevision, setPendingRevision] = useState<{ content: string; data: any; evidenceUsed?: any } | null>(null);
    const [isAuditOutdated, setIsAuditOutdated] = useState(false);
    const [settingsOpen, setSettingsOpen] = useState(false);
    const [followJobLive, setFollowJobLive] = useState(true);
    const [mainTab, setMainTab] = useState<'jobs' | 'preview'>('jobs');
    const [jobsSearch, setJobsSearch] = useState('');
    const [jobsStatusFilter, setJobsStatusFilter] = useState<'all' | 'completed' | 'running' | 'queued' | 'error' | 'canceled'>('all');
    const [jobsTypeFilter, setJobsTypeFilter] = useState<'all' | 'transcription' | 'hearing'>('all');
    const [jobsFromDate, setJobsFromDate] = useState('');
    const [jobsToDate, setJobsToDate] = useState('');
    const [savedDocsSearch, setSavedDocsSearch] = useState('');
    const [layoutDialogOpen, setLayoutDialogOpen] = useState(false);
    const [layoutDialogTab, setLayoutDialogTab] = useState<'tables' | 'margins' | 'header' | 'page' | 'breaks' | 'typography'>('tables');
    const refreshDocuments = useDocumentStore((state) => state.fetchDocuments);

    const isHearing = transcriptionType === 'hearing';
    const activeDocumentTheme = isHearing ? hearingDocumentTheme : documentTheme;
    const activeDocumentLayout = isHearing ? hearingDocumentLayout : documentLayout;
    const documentThemeClass = activeDocumentTheme ? `doc-theme-${activeDocumentTheme}` : 'doc-theme-classic';
    const documentLayoutClass = `doc-typography doc-margins-${activeDocumentLayout.margins}${activeDocumentLayout.pageFrame ? ' doc-page-frame' : ''}`;
    const isRawMode = !isHearing && mode === 'RAW';
    const hasActiveProgress = Boolean(progressStage || (isProcessing && progressMessage) || logs.length > 0);
    const documentTypographyStyle = useMemo(() => {
        const style: CSSProperties & Record<string, string> = {
            '--doc-font-size': `${activeDocumentLayout.fontSize}px`,
            '--doc-line-height': String(activeDocumentLayout.lineHeight),
            '--doc-paragraph-spacing': `${activeDocumentLayout.paragraphSpacing}px`,
        };
        if (activeDocumentLayout.fontFamily) {
            style['--doc-font-family'] = activeDocumentLayout.fontFamily;
        }
        return style;
    }, [
        activeDocumentLayout.fontFamily,
        activeDocumentLayout.fontSize,
        activeDocumentLayout.lineHeight,
        activeDocumentLayout.paragraphSpacing,
    ]);

    const setActiveTheme = useCallback((themeId: string) => {
        if (isHearing) {
            setHearingDocumentTheme(themeId);
        } else {
            setDocumentTheme(themeId);
        }
    }, [isHearing]);

    const updateActiveLayout = useCallback((patch: Partial<DocumentLayout>) => {
        if (isHearing) {
            setHearingDocumentLayout((prev) => ({ ...prev, ...patch }));
        } else {
            setDocumentLayout((prev) => ({ ...prev, ...patch }));
        }
    }, [isHearing]);

    const openLayoutDialog = useCallback(
        (tab?: 'tables' | 'margins' | 'header' | 'page' | 'breaks' | 'typography') => {
            if (tab) setLayoutDialogTab(tab);
            setLayoutDialogOpen(true);
        },
        [setLayoutDialogOpen, setLayoutDialogTab]
    );

    const previewHeaderText = (activeDocumentLayout.headerText || '').trim()
        || (activeDocumentName || '').trim()
        || (isHearing ? 'Audiência' : 'Documento');
    const previewFooterText = (activeDocumentLayout.footerText || '').trim();
    const plainLogsText = useMemo(
        () => logs.map((log) => `[${log.timestamp}] ${log.message}`).join('\n'),
        [logs]
    );
    const appendToPrompt = useCallback((current: string, snippet: string) => {
        const trimmed = snippet.trim();
        if (!trimmed) return current;
        return current?.trim() ? `${current.trim()}\n\n${trimmed}` : trimmed;
    }, []);
    const appendCustomPromptSnippet = useCallback(
        (snippet: string) => setCustomPrompt((prev) => appendToPrompt(prev, snippet)),
        [appendToPrompt]
    );
    const appendHearingCustomPromptSnippet = useCallback(
        (snippet: string) => setHearingCustomPrompt((prev) => appendToPrompt(prev, snippet)),
        [appendToPrompt]
    );
    const hasPreventiveAudit = !isHearing && Boolean(
        reportPaths?.preventive_fidelity_json_path || reportPaths?.preventive_fidelity_md_path
    );
    const preventiveRecommendation = preventiveAudit?.recomendacao_hil ?? null;
    const preventiveShouldBlock = Boolean(preventiveRecommendation?.pausar_para_revisao);
    const preventiveBlockReason = typeof preventiveRecommendation?.motivo === 'string' && preventiveRecommendation.motivo.trim()
        ? preventiveRecommendation.motivo.trim()
        : 'Auditoria preventiva recomenda revisão humana.';

    const normalizeReportPaths = (input: any) => {
        if (!input || typeof input !== 'object') return null;
        const next: Record<string, any> = { ...input };
        const reportKeys = input.audit_report_keys || input.report_keys;
        if (reportKeys && typeof reportKeys === 'object') {
            const mapping: Record<string, string> = {
                preventive_fidelity_json: 'preventive_fidelity_json_path',
                preventive_fidelity_md: 'preventive_fidelity_md_path',
                legal_audit_md: 'legal_audit_path',
                fidelity_backup_json: 'fidelity_path',
                analysis_json: 'analysis_path',
                validation_json: 'validation_path',
                coverage_txt: 'coverage_path',
                structure_audit_txt: 'structure_audit_path',
                suggestions_json: 'suggestions_path',
                docx: 'docx_path',
                md: 'md_path',
                raw: 'raw_path',
            };
            Object.entries(mapping).forEach(([sourceKey, targetKey]) => {
                if (!next[targetKey] && typeof reportKeys[sourceKey] === 'string') {
                    next[targetKey] = reportKeys[sourceKey];
                }
            });
            next.audit_report_keys = reportKeys;
        }
        return next;
    };

    const mergeReportKeys = (reports: any, auditSummary: any) => {
        const base = reports && typeof reports === 'object' ? { ...reports } : {};
        const summaryKeys = auditSummary?.report_keys || auditSummary?.reportKeys;
        if (summaryKeys && typeof summaryKeys === 'object') {
            base.audit_report_keys = { ...(base.audit_report_keys || {}), ...summaryKeys };
        }
        return Object.keys(base).length ? base : null;
    };

    const normalizeForMatch = (value: string) => {
        const input = String(value || '');
        return input
            .normalize('NFD')
            .replace(/[\u0300-\u036f]/g, '')
            .toLowerCase()
            .replace(/[^a-z0-9\s]/g, ' ')
            .replace(/\s+/g, ' ')
            .trim();
    };

    const getIssueReference = (issue: any) => {
        if (!issue) return '';
        const ref = typeof issue.reference === 'string' ? issue.reference : '';
        if (ref.trim()) return ref.trim();
        const desc = typeof issue.description === 'string' ? issue.description : '';
        if (desc.includes(':')) return desc.split(':').slice(1).join(':').trim();
        return '';
    };

    const getIssueRawSnippet = (issue: any) => {
        const evidence = Array.isArray(issue?.raw_evidence) ? issue.raw_evidence : [];
        if (!evidence.length) return '';
        const first = evidence[0];
        const snippet =
            typeof first === 'string'
                ? first
                : (first?.snippet ?? first?.text ?? '');
        return String(snippet || '').trim();
    };

    const extractSectionFromMarkdown = (markdown: string, suggestedSection: string, reference: string) => {
        const content = String(markdown || '');
        if (!content.trim()) {
            return { heading: '', section: '', found: false, note: 'Sem conteúdo formatado para extrair contexto.' };
        }
        const lines = content.split(/\r?\n/);
        const sectionTarget = normalizeForMatch(suggestedSection || '');
        const refTarget = normalizeForMatch(reference || '');

        const headings = lines
            .map((line, index) => ({ line, index }))
            .filter(({ line }) => /^#{1,6}\s+/.test(line));

        const scoreHeading = (headingLine: string) => {
            const normalized = normalizeForMatch(headingLine.replace(/^#{1,6}\s+/, ''));
            if (!normalized) return 0;
            if (sectionTarget && (normalized.includes(sectionTarget) || sectionTarget.includes(normalized))) return 100;
            const sectionTokens = new Set(sectionTarget.split(' ').filter((w) => w.length > 2));
            const headingTokens = new Set(normalized.split(' ').filter((w) => w.length > 2));
            let hit = 0;
            sectionTokens.forEach((t) => {
                if (headingTokens.has(t)) hit += 1;
            });
            return hit;
        };

        let best = { idx: -1, score: 0 };
        if (sectionTarget) {
            for (const h of headings) {
                const score = scoreHeading(h.line);
                if (score > best.score) best = { idx: h.index, score };
            }
        }

        const findHeadingByReference = () => {
            if (!refTarget) return -1;
            const refLineIndex = lines.findIndex((line) => normalizeForMatch(line).includes(refTarget));
            if (refLineIndex < 0) return -1;
            for (let i = refLineIndex; i >= 0; i -= 1) {
                if (/^#{1,6}\s+/.test(lines[i])) return i;
            }
            return -1;
        };

        let headingIndex = best.score > 1 ? best.idx : -1;
        if (headingIndex < 0) headingIndex = findHeadingByReference();

        if (headingIndex < 0) {
            const preview = lines.slice(0, 60).join('\n');
            return { heading: '', section: preview, found: false, note: 'Seção sugerida não encontrada; mostrando início do documento.' };
        }

        const headingLine = lines[headingIndex] || '';
        const levelMatch = headingLine.match(/^(#{1,6})\s+/);
        const level = levelMatch ? levelMatch[1].length : 2;
        let end = lines.length;
        for (let i = headingIndex + 1; i < lines.length; i += 1) {
            const m = lines[i].match(/^(#{1,6})\s+/);
            if (m && m[1].length <= level) {
                end = i;
                break;
            }
        }

        const section = lines.slice(headingIndex, end).join('\n').trim();
        return { heading: headingLine.replace(/^#{1,6}\s+/, '').trim(), section, found: true, note: '' };
    };
    const hearingRoles = [
        'juiz',
        'mp',
        'defesa',
        'testemunha',
        'serventuario',
        'parte',
        'perito',
        'outro',
    ];

    const formatDuration = (value?: number | null) => {
        if (value === null || value === undefined || Number.isNaN(value)) return '--:--';
        const total = Math.max(0, Math.floor(value));
        const hours = Math.floor(total / 3600);
        const minutes = Math.floor((total % 3600) / 60);
        const seconds = total % 60;
        if (hours > 0) {
            return `${hours}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
        }
        return `${minutes}:${String(seconds).padStart(2, '0')}`;
    };

    const formatTimestamp = (value?: number | null) => {
        if (value === null || value === undefined || Number.isNaN(value)) return '--:--';
        const total = Math.max(0, Math.floor(value));
        const hours = Math.floor(total / 3600);
        const minutes = Math.floor((total % 3600) / 60);
        const seconds = total % 60;
        return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
    };

    /**
     * Categoriza as correções auto-aplicadas de forma robusta.
     * Correções estruturais geralmente mencionam títulos, numeração, duplicação, formatação.
     * Correções de conteúdo mencionam missing_, compression, legal_audit, conteúdo/content.
     */
    const categorizeAutoAppliedFixes = (appliedFixes: string[]) => {
        if (!Array.isArray(appliedFixes) || appliedFixes.length === 0) {
            return { structural: [], content: [], total: 0 };
        }

        const structural: string[] = [];
        const content: string[] = [];

        for (const fix of appliedFixes) {
            const fixLower = String(fix).toLowerCase();

            // Correções de conteúdo (detectar primeiro, pois são mais específicas)
            if (
                fixLower.includes('missing_') ||          // Issues de omissão
                fixLower.includes('compression') ||       // Issues de compressão
                fixLower.includes('legal_audit') ||       // Auditoria jurídica
                fixLower.includes('conteúdo') ||          // Palavra-chave PT
                fixLower.includes('content') ||           // Palavra-chave EN
                fixLower.includes('omissão') ||           // Omissões
                fixLower.includes('omissao') ||
                fixLower.includes('lei') ||               // Leis/súmulas
                fixLower.includes('súmula') ||
                fixLower.includes('sumula') ||
                fixLower.includes('decreto') ||
                fixLower.includes('julgado') ||
                fixLower.includes('distorção') ||         // Distorções
                fixLower.includes('distorcao') ||
                fixLower.includes('alucinação') ||        // Alucinações
                fixLower.includes('alucinacao')
            ) {
                content.push(fix);
            }
            // Correções estruturais (padrões de formatação/estrutura)
            else if (
                fixLower.includes('título') ||
                fixLower.includes('titulo') ||
                fixLower.includes('heading') ||
                fixLower.includes('numeração') ||
                fixLower.includes('numeracao') ||
                fixLower.includes('duplicad') ||          // duplicado/duplicada
                fixLower.includes('órfã') ||
                fixLower.includes('orfa') ||
                fixLower.includes('orphan') ||
                fixLower.includes('seção') ||
                fixLower.includes('secao') ||
                fixLower.includes('section') ||
                fixLower.includes('formatação') ||
                fixLower.includes('formatacao') ||
                fixLower.includes('formatting') ||
                fixLower.includes('estrutura') ||
                fixLower.includes('structure')
            ) {
                structural.push(fix);
            }
            // Fallback: se não matchou nada específico, considerar estrutural
            // (a maioria das correções do auto_fix_apostilas é estrutural)
            else {
                structural.push(fix);
            }
        }

        return {
            structural,
            content,
            total: appliedFixes.length
        };
    };

    const formatJobTime = (value?: string) => {
        if (!value) return '';
        const parsed = new Date(value);
        if (Number.isNaN(parsed.getTime())) return value;
        return parsed.toLocaleString();
    };

    const isJobDeletable = (job: any) => !['running', 'queued'].includes(String(job?.status || ''));

    const resolveSavedDocumentId = useCallback((doc: any) => {
        const rawId = doc?.id ?? doc?.document_id ?? doc?.resource_id ?? doc?.doc_id;
        if (!rawId) return '';
        return String(rawId).trim();
    }, []);

    const normalizeSavedDocument = useCallback((doc: any) => {
        const resolvedId = resolveSavedDocumentId(doc);
        if (!resolvedId) return doc;
        return { ...doc, id: resolvedId };
    }, [resolveSavedDocumentId]);

    const filteredJobHistory = useMemo(() => {
        const search = jobsSearch.trim().toLowerCase();
        const fromMs = jobsFromDate ? new Date(`${jobsFromDate}T00:00:00`).getTime() : null;
        const toMs = jobsToDate ? new Date(`${jobsToDate}T23:59:59`).getTime() : null;

        return (jobHistory || []).filter((job: any) => {
            const status = String(job?.status || '').toLowerCase();
            if (jobsStatusFilter !== 'all' && status !== jobsStatusFilter) return false;

            const type = String(job?.job_type || '').toLowerCase();
            if (jobsTypeFilter !== 'all') {
                const normalized = jobsTypeFilter === 'transcription' ? 'transcription' : 'hearing';
                if (type !== normalized) return false;
            }

            if (fromMs || toMs) {
                const createdAt = job?.created_at || job?.updated_at;
                const createdMs = createdAt ? new Date(createdAt).getTime() : NaN;
                if (!Number.isFinite(createdMs)) return false;
                if (fromMs && createdMs < fromMs) return false;
                if (toMs && createdMs > toMs) return false;
            }

            if (!search) return true;
            const title = type === 'hearing'
                ? `caso ${job?.config?.case_id || ''} ${job?.job_id || ''}`
                : `${(job?.file_names || []).join(', ')} ${job?.job_id || ''}`;
            return title.toLowerCase().includes(search);
        });
    }, [jobHistory, jobsSearch, jobsStatusFilter, jobsTypeFilter, jobsFromDate, jobsToDate]);

    const filteredSavedDocuments = useMemo(() => {
        const search = savedDocsSearch.trim().toLowerCase();
        if (!search) return savedDocuments || [];
        return (savedDocuments || []).filter((doc: any) => {
            const name = String(doc?.name || '').toLowerCase();
            const id = String(resolveSavedDocumentId(doc) || '').toLowerCase();
            return name.includes(search) || id.includes(search);
        });
    }, [savedDocuments, savedDocsSearch, resolveSavedDocumentId]);

    const upsertSavedDocuments = (docs: any[]) => {
        if (!docs.length) return;
        setSavedDocuments((prev) => {
            const map = new Map<string, any>();
            [...docs, ...prev].forEach((doc) => {
                const normalized = normalizeSavedDocument(doc);
                const resolvedId = resolveSavedDocumentId(normalized);
                if (!resolvedId) return;
                map.set(resolvedId, normalized);
            });
            return Array.from(map.values());
        });
    };

    const formatApiError = (error: any, fallback: string) => {
        const data = error?.response?.data;
        const detail = data?.detail ?? data?.error ?? data?.message;
        if (typeof detail === 'string' && detail.trim()) return `${fallback} ${detail}`;
        if (typeof data === 'string' && data.trim()) return `${fallback} ${data}`;
        const message = error?.message;
        if (typeof message === 'string' && message.trim()) return `${fallback} ${message}`;
        return fallback;
    };

    const toggleJobSelection = (jobId: string, checked: boolean) => {
        setSelectedJobIds((prev) => {
            const next = new Set(prev);
            if (checked) {
                next.add(jobId);
            } else {
                next.delete(jobId);
            }
            return next;
        });
    };

    const toggleSavedDocSelection = (docId: string, checked: boolean) => {
        setSelectedSavedDocIds((prev) => {
            const next = new Set(prev);
            if (checked) {
                next.add(docId);
            } else {
                next.delete(docId);
            }
            return next;
        });
    };

    const handleSelectAllJobs = (checked: boolean) => {
        if (!checked) {
            setSelectedJobIds(new Set());
            return;
        }
        const ids = jobHistory
            .filter(isJobDeletable)
            .map((job) => job.job_id)
            .filter(Boolean);
        setSelectedJobIds(new Set(ids));
    };

    const handleSelectAllSavedDocs = (checked: boolean) => {
        if (!checked) {
            setSelectedSavedDocIds(new Set());
            return;
        }
        const ids = savedDocuments
            .map((doc) => resolveSavedDocumentId(doc))
            .filter(Boolean);
        setSelectedSavedDocIds(new Set(ids));
    };

    const handleFilesChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        if (e.target.files && e.target.files.length > 0) {
            const newFiles = Array.from(e.target.files);
            setFiles(prev => [...prev, ...newFiles]);
            setPublicUrl('');
        }
        e.target.value = '';
    };

    const removeFile = (index: number) => {
        setFiles(prev => prev.filter((_, i) => i !== index));
    };

    const moveFileUp = (index: number) => {
        if (index === 0) return;
        setFiles(prev => {
            const newFiles = [...prev];
            [newFiles[index - 1], newFiles[index]] = [newFiles[index], newFiles[index - 1]];
            return newFiles;
        });
    };

    const moveFileDown = (index: number) => {
        if (index === files.length - 1) return;
        setFiles(prev => {
            const newFiles = [...prev];
            [newFiles[index], newFiles[index + 1]] = [newFiles[index + 1], newFiles[index]];
            return newFiles;
        });
    };

    const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
        e.preventDefault();
        setIsDragActive(false);
        const droppedFiles = Array.from(e.dataTransfer.files || []);
        if (droppedFiles.length === 0) return;
        setFiles(prev => [...prev, ...droppedFiles]);
        setPublicUrl('');
    };

    const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
        e.preventDefault();
        setIsDragActive(true);
    };

    const handleDragLeave = () => {
        setIsDragActive(false);
    };

    useEffect(() => {
        if (!files[0]) {
            // Only clear mediaUrl if it's a blob URL (from local file)
            // Keep server URLs (from loaded jobs) intact
            setMediaUrl((prev) => {
                if (prev && prev.startsWith('blob:')) {
                    URL.revokeObjectURL(prev);
                    return null;
                }
                // If no files but we have a server URL, keep it
                return prev;
            });
            setMediaDuration(0);
            setCurrentTime(0);
            return;
        }
        // Create blob URL from local file
        const url = URL.createObjectURL(files[0]);
        setMediaUrl((prev) => {
            // Revoke old blob URL if exists
            if (prev && prev.startsWith('blob:')) {
                URL.revokeObjectURL(prev);
            }
            return url;
        });
        return () => {
            // Cleanup: only revoke blob URLs
            if (url.startsWith('blob:')) {
                URL.revokeObjectURL(url);
            }
        };
    }, [files]);

    useEffect(() => {
        if (mediaRef.current) {
            mediaRef.current.playbackRate = playbackRate;
        }
    }, [playbackRate]);

    const loadJobHistory = useCallback(async () => {
        try {
            setJobsLoading(true);
            const data = await apiClient.listTranscriptionJobs(20);
            setJobHistory(Array.isArray(data?.jobs) ? data.jobs : []);
        } catch (error) {
            console.error(error);
        } finally {
            setJobsLoading(false);
        }
    }, []);

    const loadSavedDocuments = useCallback(async () => {
        try {
            setSavedDocsLoading(true);
            const data = await apiClient.getDocuments(0, 100);
            const docs = Array.isArray(data?.documents) ? data.documents : [];
            const filtered = docs.filter((doc: any) =>
                Array.isArray(doc?.tags) && doc.tags.some((tag: string) => String(tag).toLowerCase() === 'transcricao')
            );
            const sorted = [...filtered].sort((a: any, b: any) => {
                const at = new Date(a?.created_at || 0).getTime();
                const bt = new Date(b?.created_at || 0).getTime();
                return bt - at;
            });
            setSavedDocuments(sorted.map(normalizeSavedDocument));
        } catch (error) {
            console.error(error);
        } finally {
            setSavedDocsLoading(false);
        }
    }, [normalizeSavedDocument]);

    useEffect(() => {
        loadJobHistory();
    }, [loadJobHistory]);

    useEffect(() => {
        loadSavedDocuments();
    }, [loadSavedDocuments]);

    useEffect(() => {
        const validIds = new Set(
            jobHistory
                .filter(isJobDeletable)
                .map((job) => job.job_id)
                .filter(Boolean)
        );
        setSelectedJobIds((prev) => new Set([...prev].filter((id) => validIds.has(id))));
    }, [jobHistory]);

    useEffect(() => {
        const validIds = new Set(
            savedDocuments
                .map((doc) => resolveSavedDocumentId(doc))
                .filter(Boolean)
        );
        setSelectedSavedDocIds((prev) => new Set([...prev].filter((id) => validIds.has(id))));
    }, [savedDocuments, resolveSavedDocumentId]);

    useEffect(() => {
        const deletableCount = jobHistory.filter(isJobDeletable).length;
        if (jobsSelectAllRef.current) {
            jobsSelectAllRef.current.indeterminate =
                selectedJobIds.size > 0 && selectedJobIds.size < deletableCount;
        }
    }, [jobHistory, selectedJobIds]);

    useEffect(() => {
        const selectableCount = savedDocuments
            .map((doc) => resolveSavedDocumentId(doc))
            .filter(Boolean).length;
        if (savedDocsSelectAllRef.current) {
            savedDocsSelectAllRef.current.indeterminate =
                selectedSavedDocIds.size > 0 && selectedSavedDocIds.size < selectableCount;
        }
    }, [savedDocuments, selectedSavedDocIds, resolveSavedDocumentId]);

    const extractReports = (content?: string | null) => {
        if (!content) return null;
        const reportRegex = /<!--\s*RELATÓRIO:([\s\S]*?)-->/gi;
        const matches = Array.from(content.matchAll(reportRegex));
        if (matches.length === 0) return null;
        const combined = matches
            .map((match) => match[1]?.trim())
            .filter(Boolean)
            .join("\n\n---\n\n");
        return combined || null;
    };

    const stripReportBlocks = (content?: string | null) => {
        if (!content) return content ?? null;
        const cleaned = content.replace(/<!--\s*RELATÓRIO:[\s\S]*?-->/gi, '');
        return cleaned.replace(/\n{3,}/g, '\n\n').trim();
    };

    const coerceNumber = (value: any, fallback: number) => {
        const parsed = Number(value);
        return Number.isFinite(parsed) ? parsed : fallback;
    };

    const handleInsertPageBreak = useCallback(() => {
        const marker = '\n\n<!-- PAGE_BREAK -->\n\n';
        const base = stripReportBlocks(draftResult ?? result ?? '') || '';
        const normalized = base.replace(/\s+$/g, '');
        const next = normalized.endsWith('<!-- PAGE_BREAK -->')
            ? normalized + '\n'
            : `${normalized}${marker}`;

        setDraftResult(next);
        setIsEditingResult(true);
        toast.success('Quebra de página inserida. Você pode movê-la no editor.');
    }, [draftResult, result, setDraftResult, setIsEditingResult, stripReportBlocks]);

    const enrichHilIssues = (issues: any[], rawText?: string | null, formattedText?: string | null) => {
        if (!Array.isArray(issues) || issues.length === 0) return Array.isArray(issues) ? issues : [];
        const raw = typeof rawText === 'string' ? rawText : '';
        const formatted = typeof formattedText === 'string' ? formattedText : '';
        if (!raw.trim()) return issues;

        const digitsOnly = (value: string) => String(value || '').replace(/\D+/g, '');
        const buildFuzzyDigitsPattern = (digits: string) => digits.split('').join('[\\s\\./-]*');

        const inferReference = (issue: any) => {
            const explicit = typeof issue?.reference === 'string' ? issue.reference.trim() : '';
            if (explicit) return explicit;
            const desc = typeof issue?.description === 'string' ? issue.description : '';
            const parts = desc.split(':');
            if (parts.length >= 2) return parts.slice(1).join(':').trim();
            return '';
        };

        const extractEvidence = (regex: RegExp, maxHits = 2, window = 260) => {
            const out: Array<{ match: string; start: number; end: number; snippet: string }> = [];
            regex.lastIndex = 0;
            let match: RegExpExecArray | null;
            while ((match = regex.exec(raw)) && out.length < maxHits) {
                const start = match.index;
                const end = start + match[0].length;
                const snippetStart = Math.max(0, start - window);
                const snippetEnd = Math.min(raw.length, end + window);
                const snippet = raw.slice(snippetStart, snippetEnd).trim();
                out.push({ match: match[0], start, end, snippet });
                if (!regex.global) break;
            }
            return out.filter((item) => item.snippet);
        };

        const stopwords = new Set([
            'para',
            'com',
            'sem',
            'uma',
            'uns',
            'umas',
            'por',
            'que',
            'dos',
            'das',
            'nos',
            'nas',
            'num',
            'numa',
            'mais',
            'menos',
            'sobre',
            'entre',
            'como',
            'quando',
            'onde',
            'pelo',
            'pela',
            'pelos',
            'pelas',
            'isso',
            'essa',
            'esse',
            'este',
            'esta',
            'ser',
            'ter',
            'sao',
            'não',
            'nao',
            'sim',
            'sua',
            'seu',
            'suas',
            'seus',
            'tambem',
            'também',
        ]);

        const keywords = (text: string) => {
            const tokens = String(text || '')
                .toLowerCase()
                .match(/[a-zà-ÿ0-9]{4,}/gi) || [];
            return new Set(
                tokens
                    .map((t) => t.toLowerCase())
                    .filter((t) => !stopwords.has(t))
            );
        };

        const headings: Array<{ title: string; start: number; end: number }> = [];
        if (formatted) {
            const matches = Array.from(formatted.matchAll(/^##\s+(.+)$/gm));
            matches.forEach((m, idx) => {
                const title = String(m[1] || '').trim();
                const start = m.index ?? 0;
                const end = idx + 1 < matches.length ? (matches[idx + 1].index ?? formatted.length) : formatted.length;
                if (title) headings.push({ title, start, end });
            });
        }

        const suggestSection = (evidence: Array<{ snippet: string }>) => {
            if (!headings.length || !formatted) return '';
            const kw = keywords(evidence.map((e) => e.snippet).join('\n\n'));
            if (!kw.size) return '';
            let bestTitle = '';
            let bestScore = 0;
            headings.slice(0, 60).forEach((h) => {
                const sample = formatted.slice(h.start, Math.min(h.end, h.start + 3500));
                const sectionKw = keywords(sample);
                let score = 0;
                kw.forEach((t) => {
                    if (sectionKw.has(t)) score += 1;
                });
                if (score > bestScore) {
                    bestScore = score;
                    bestTitle = h.title;
                }
            });
            return bestScore >= 2 ? bestTitle : '';
        };

        return issues.map((issue) => {
            if (!issue || typeof issue !== 'object') return issue;
            if (Array.isArray(issue.raw_evidence) && issue.raw_evidence.length > 0) return issue;
            if (String(issue.fix_type || '').toLowerCase() !== 'content') return issue;

            const type = String(issue.type || '');
            const reference = inferReference(issue);
            let evidence: Array<{ match: string; start: number; end: number; snippet: string }> = [];

            if (type === 'missing_law') {
                const digits = digitsOnly(reference);
                if (digits) {
                    const re = new RegExp(`\\blei\\s*(?:n[º°]?\\s*)?${buildFuzzyDigitsPattern(digits)}`, 'ig');
                    evidence = extractEvidence(re);
                }
            } else if (type === 'missing_decreto') {
                const digits = digitsOnly(reference);
                if (digits) {
                    const re = new RegExp(`\\bdecreto\\s*(?:rio\\s*)?(?:n[º°]?\\s*)?${buildFuzzyDigitsPattern(digits)}`, 'ig');
                    evidence = extractEvidence(re);
                }
            } else if (type === 'missing_sumula') {
                const num = digitsOnly(reference);
                if (num) {
                    const re = new RegExp(`\\bs[úu]mula\\s*(?:vinculante\\s*)?(?:n[º°]?\\s*)?${num}\\b`, 'ig');
                    evidence = extractEvidence(re);
                }
            } else if (type === 'missing_julgado') {
                if (reference) {
                    const escaped = reference.replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/\s+/g, '\\s+');
                    const re = new RegExp(escaped, 'ig');
                    evidence = extractEvidence(re);
                }
            }

            if (!evidence.length) return issue;

            const suggested = suggestSection(evidence);
            return {
                ...issue,
                reference: issue.reference || reference,
                suggested_section: issue.suggested_section || suggested || undefined,
                raw_evidence: evidence,
            };
        });
    };

    const buildHilEvidenceUsed = (issues: any[]) => {
        if (!Array.isArray(issues) || issues.length === 0) return [];
        const entries: Array<{ issueId?: string; reference?: string; snippet?: string; suggestedSection?: string }> = [];
        for (const issue of issues) {
            const rawEvidence = Array.isArray(issue?.raw_evidence) ? issue.raw_evidence : [];
            if (!rawEvidence.length) continue;
            const reference = typeof issue?.reference === 'string'
                ? issue.reference
                : (typeof issue?.description === 'string' && issue.description.includes(':')
                    ? issue.description.split(':').slice(1).join(':').trim()
                    : undefined);
            const suggestedSection = typeof issue?.suggested_section === 'string' ? issue.suggested_section : undefined;
            for (const item of rawEvidence) {
                const snippet = typeof item === 'string' ? item : (item?.snippet ?? item?.text ?? '');
                const text = String(snippet || '').trim();
                if (!text) continue;
                entries.push({
                    issueId: issue?.id,
                    reference,
                    suggestedSection,
                    snippet: text.length > 600 ? `${text.slice(0, 600)}…` : text,
                });
                if (entries.length >= 8) break;
            }
            if (entries.length >= 8) break;
        }
        return entries;
    };

    const processResponse = (
        content: string,
        rawContent?: string | null,
        rich?: { html?: string | null; json?: any; meta?: any } | null
    ) => {
        // Extrair relatório (<!-- RELATÓRIO: ... -->)
        setReport(extractReports(content));
        const cleaned = stripReportBlocks(content) || content;
        setResult(cleaned);
        setRawResult(rawContent ?? cleaned);
        setRichTextHtml(rich?.html ?? null);
        setRichTextJson(rich?.json ?? null);
        setRichTextMeta(rich?.meta ?? null);
        setIsEditingResult(false);
        setDraftResult(null);
        setHilDiagnostics(null);
    };

    const clearRichContent = useCallback(() => {
        setRichTextHtml(null);
        setRichTextJson(null);
        setRichTextMeta(null);
    }, []);

    const fetchPreventiveAudit = useCallback(async (force = false) => {
        if (isHearing || !activeJobId) {
            setPreventiveAudit(null);
            setPreventiveAuditMarkdown(null);
            setPreventiveAuditError(null);
            setPreventiveAuditLoading(false);
            preventiveAuditKeyRef.current = null;
            return;
        }

        const jsonPath = reportPaths?.preventive_fidelity_json_path || '';
        const mdPath = reportPaths?.preventive_fidelity_md_path || '';
        if (!jsonPath && !mdPath) {
            setPreventiveAudit(null);
            setPreventiveAuditMarkdown(null);
            setPreventiveAuditError(null);
            setPreventiveAuditLoading(false);
            preventiveAuditKeyRef.current = null;
            return;
        }

        const cacheKey = `${activeJobId}:${jsonPath}:${mdPath}`;
        if (!force && preventiveAuditKeyRef.current === cacheKey) return;
        preventiveAuditKeyRef.current = cacheKey;
        setPreventiveAuditLoading(true);
        setPreventiveAuditError(null);

        try {
            if (jsonPath) {
                try {
                    const blob = await apiClient.downloadTranscriptionReport(activeJobId, 'preventive_fidelity_json_path');
                    const text = await blob.text();
                    const sanitized = text.replace(/^\uFEFF/, '').trim();
                    const parsed = JSON.parse(sanitized);
                    setPreventiveAudit(parsed);
                    setPreventiveAuditMarkdown(null);
                    return;
                } catch (error) {
                    console.warn('Falha ao carregar auditoria preventiva (JSON). Tentando MD...', error);
                }
            }

            if (mdPath) {
                const blob = await apiClient.downloadTranscriptionReport(activeJobId, 'preventive_fidelity_md_path');
                const text = await blob.text();
                setPreventiveAudit(null);
                setPreventiveAuditMarkdown(text.replace(/^\uFEFF/, '').trim());
                return;
            }

            setPreventiveAudit(null);
            setPreventiveAuditMarkdown(null);
        } catch (error) {
            console.error(error);
            setPreventiveAudit(null);
            setPreventiveAuditMarkdown(null);
            setPreventiveAuditError('Falha ao carregar auditoria preventiva.');
            preventiveAuditKeyRef.current = null;
        } finally {
            setPreventiveAuditLoading(false);
        }
    }, [activeJobId, isHearing, reportPaths]);

    useEffect(() => {
        fetchPreventiveAudit();
    }, [fetchPreventiveAudit]);

    const handleRecomputePreventiveAudit = useCallback(async () => {
        if (!activeJobId) {
            toast.error('Nenhum job ativo.');
            return;
        }
        try {
            toast.info('Regerando auditoria preventiva...');
            const data = await apiClient.recomputeTranscriptionPreventiveAudit(activeJobId);
            const nextReports = data?.reports ?? null;
            const mergedReports = mergeReportKeys(nextReports, data?.audit_summary);
            if (mergedReports) {
                setReportPaths(normalizeReportPaths(mergedReports));
            }
            await fetchPreventiveAudit(true);
            toast.success('Auditoria preventiva atualizada.');
        } catch (error: any) {
            console.error(error);
            const status = error?.response?.status;
            if (status === 404) {
                toast.error('Endpoint não encontrado (backend desatualizado). Reinicie o backend e tente novamente.');
                return;
            }
            toast.error(formatApiError(error, 'Falha ao regerar auditoria preventiva.'));
        }
    }, [activeJobId, fetchPreventiveAudit]);

    const openIssueAssistant = useCallback((issue: any) => {
        const reference = getIssueReference(issue);
        const suggestedSection = typeof issue?.suggested_section === 'string' ? issue.suggested_section.trim() : '';
        const type = typeof issue?.type === 'string' ? issue.type : 'issue';
        const safeRef = reference ? ` (${reference})` : '';
        const safeSection = suggestedSection ? ` Seção: ${suggestedSection}.` : '';
        const instruction = `Objetivo: corrigir ${type}${safeRef}.${safeSection} ` +
            'Insira a referência no texto preservando o estilo e a estrutura. ' +
            'Use apenas informações presentes no RAW (sem inventar). ' +
            'Se a referência já estiver no texto, evite duplicar.';
        setIssueAssistantIssue(issue);
        setIssueAssistantInstruction(instruction);
        setIssueAssistantForce(false);
        setIssueAssistantOpen(true);
    }, []);

    const buildReportEntries = (reports: Record<string, string> | null) => {
        if (!reports) return [];
	        const orderedKeys: Array<[string, string]> = [
	            ['legal_audit_path', 'Auditoria jurídica (AUDITORIA.md)'],
	            ['audit_path', 'Auditoria jurídica (AUDITORIA.md)'],
	            ['structure_audit_path', 'Auditoria estrutural (verificacao.txt)'],
	            ['coverage_path', 'Validação (validacao.txt)'],
	            ['fidelity_path', 'Fidelidade (fidelidade.json)'],
	            ['preventive_fidelity_md_path', 'Auditoria preventiva (AUDITORIA_FIDELIDADE.md)'],
	            ['preventive_fidelity_json_path', 'Auditoria preventiva (AUDITORIA_FIDELIDADE.json)'],
	            ['revision_path', 'Revisão (REVISAO.md)'],
	            ['analysis_path', 'Análise estrutural (ANALISE.json)'],
	            ['validation_path', 'Validação de fidelidade (FIDELIDADE.json)'],
	            ['suggestions_path', 'Sugestões HIL (SUGESTOES.json)'],
	            ['format_source_path', 'Fonte usada na formatação (transcript_for_formatting.md)'],
	            ['transcript_no_timestamps_path', 'Transcrição sem timestamps (hearing_transcript_no_timestamps.md)'],
	            ['docx_path', 'Documento final (DOCX)'],
	            ['md_path', 'Documento final (MD)'],
	            ['raw_path', 'Transcrição RAW (txt)'],
	            ['original_md_path', 'Documento original (MD)'],
	            ['original_docx_path', 'Documento original (DOCX)'],
	        ];
        const seen = new Set<string>();
        return orderedKeys
            .map(([key, label]) => {
                const path = reports[key];
                if (!path || seen.has(path)) return null;
                seen.add(path);
                return { key, label };
            })
            .filter((entry): entry is { key: string; label: string } => Boolean(entry));
    };

    const handleDownloadReport = async (reportKey: string) => {
        if (!activeJobId) {
            toast.error('Nenhum job ativo para baixar relatórios.');
            return;
        }
        try {
            const blob = await apiClient.downloadTranscriptionReport(activeJobId, reportKey);
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            const path = reportPaths?.[reportKey] || '';
            const fileName = path.replace(/\\/g, '/').split('/').pop() || reportKey;
            a.download = fileName;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        } catch (error) {
            console.error(error);
            toast.error('Falha ao baixar o relatório.');
        }
    };

    const isTextFile = (file: File) => {
        const lower = file.name.toLowerCase();
        return file.type.startsWith('text/') || lower.endsWith('.txt') || lower.endsWith('.md');
    };

    const buildAutoSaveKey = (prefix: string) => {
        const names = files.map((f) => f.name).join('|');
        return `${prefix}:${names}:${Date.now()}`;
    };

    const sanitizeFilename = (value: string) =>
        value.replace(/[\\/:*?"<>|]+/g, '_').slice(0, 120) || 'transcricao';

    const autoSaveDocuments = async ({
        formattedContent,
        rawContent,
        displayName,
        tags,
        folderId,
    }: {
        formattedContent?: string | null;
        rawContent?: string | null;
        displayName: string;
        tags: string;
        folderId?: string;
    }) => {
        // DEBUG: Log values to diagnose save issues
        console.log('[autoSaveDocuments] Called with:', {
            displayName,
            tags,
            folderId,
            rawContentLength: rawContent?.length ?? 0,
            formattedContentLength: formattedContent?.length ?? 0,
            rawContentEmpty: !rawContent,
            formattedContentEmpty: !formattedContent,
            contentsAreEqual: rawContent === formattedContent,
        });

        const key = buildAutoSaveKey(displayName);
        if (lastAutoSaveKeyRef.current === key) {
            console.log('[autoSaveDocuments] Skipped: duplicate key', key);
            return;
        }
        lastAutoSaveKeyRef.current = key;

        const saveAttempt = async (useFolder: boolean) => {
            let savedCount = 0;
            const savedDocs: any[] = [];
            const currentFolderId = useFolder ? folderId : undefined;

            if (rawContent) {
                try {
                    const doc = await apiClient.createDocumentFromText({
                        title: `Transcrição RAW: ${displayName}`,
                        content: rawContent,
                        tags: `${tags},raw`,
                        folder_id: currentFolderId,
                    });
                    savedDocs.push(doc);
                    savedCount += 1;
                } catch (err) {
                    console.error('Erro ao salvar RAW:', err);
                    throw err;
                }
            }
            if (formattedContent && formattedContent !== rawContent) {
                try {
                    const doc = await apiClient.createDocumentFromText({
                        title: `Transcrição: ${displayName}`,
                        content: formattedContent,
                        tags,
                        folder_id: currentFolderId,
                    });
                    savedDocs.push(doc);
                    savedCount += 1;
                } catch (err) {
                    console.error('Erro ao salvar formatado:', err);
                    throw err;
                }
            }
            return { savedCount, savedDocs };
        };

        const ensureLibraryItems = async (docs: any[]) => {
            const validDocs = docs.filter((doc) => doc?.id);
            if (!validDocs.length) return;
            await Promise.allSettled(
                validDocs.map((doc) =>
                    apiClient.createLibraryItem({
                        type: 'DOCUMENT',
                        name: doc?.name || displayName,
                        description: null,
                        tags: Array.isArray(doc?.tags) ? doc.tags : [],
                        folder_id: doc?.folder_id || undefined,
                        resource_id: doc?.id,
                        token_count: 0,
                    })
                )
            );
        };

        try {
            const { savedCount, savedDocs } = await saveAttempt(true);
            if (savedCount > 0) {
                await ensureLibraryItems(savedDocs);
                upsertSavedDocuments(savedDocs);
                await refreshDocuments().catch(() => undefined);
                toast.success(`Transcrição salva automaticamente (${savedCount} arquivo${savedCount > 1 ? 's' : ''}).`);
            }
        } catch (error: any) {
            console.error('Auto-save failed with folder:', error);
            // Fallback: Tenta sem a pasta se houver folderId
            if (folderId) {
                try {
                    const { savedCount, savedDocs } = await saveAttempt(false);
                    if (savedCount > 0) {
                        await ensureLibraryItems(savedDocs);
                        upsertSavedDocuments(savedDocs);
                        await refreshDocuments().catch(() => undefined);
                        toast.warning(`Salvo automaticamente em "Meus Documentos" (Pasta/Caso não encontrado).`);
                    }
                } catch (retryError: any) {
                    console.error('Auto-save fallback failed:', retryError);
                    toast.error(formatApiError(retryError, 'Falha ao salvar automaticamente (mesmo sem pasta).'));
                }
            } else {
                const message = formatApiError(error, 'Falha ao salvar automaticamente os arquivos de transcrição.');
                toast.error(message);
            }
        }
    };

    const buildHearingExportContent = () => {
        if (!hearingPayload) return result || '';
        const baseText = hearingFormatted || hearingTranscript || result || '';
        const segments = (hearingPayload.segments || []) as any[];
        const speakers = (hearingPayload.speakers || []) as any[];
        const evidence = (hearingPayload.evidence || []) as any[];
        const timeline = (hearingPayload.timeline || []) as any[];
        const contradictions = (hearingPayload.contradictions || []) as any[];

        const metadataLines = [
            hearingCaseId ? `- Processo/Caso: ${hearingCaseId}` : null,
            hearingGoal ? `- Objetivo: ${hearingGoal}` : null,
            hearingCourt ? `- Vara/Tribunal: ${hearingCourt}` : null,
            hearingCity ? `- Comarca/Cidade: ${hearingCity}` : null,
            hearingDate ? `- Data: ${hearingDate}` : null,
            hearingNotes ? `- Observações: ${hearingNotes}` : null,
        ].filter(Boolean) as string[];

        const metadataSection = metadataLines.length
            ? ['## Metadados do Caso', '', ...metadataLines].join('\n')
            : '';

        const segmentMap = new Map<string, any>(segments.map((seg: any) => [String(seg.id), seg]));
        const speakerMap = new Map<string, any>(speakers.map((sp: any) => [String(sp.speaker_id), sp]));

        const evidenceLines = evidence.map((ev: any) => {
            const segId = (ev.segment_ids || [])[0];
            const seg = segmentMap.get(String(segId));
            const speaker = seg ? speakerMap.get(String(seg.speaker_id)) : null;
            const labelBase = speaker?.name || speaker?.label || seg?.speaker_label || 'Falante';
            const role = speaker?.role ? ` (${speaker.role})` : '';
            const ts = seg?.timestamp_hint ? ` [${seg.timestamp_hint}]` : '';
            const reasons = (ev.relevance_reasons || []).join(', ');
            const reasonText = reasons ? ` (${reasons})` : '';
            return `| ${ev.claim_normalized || '-'} | ${ev.quote_verbatim || ''} | ${labelBase}${role}${ts} | ${ev.relevance_score ?? ''}${reasonText} |`;
        });

        const evidenceTable = [
            '## Quadro de Evidencias',
            '',
            '| Fato | Citacao | Falante | Relevancia |',
            '| --- | --- | --- | --- |',
            ...(evidenceLines.length > 0 ? evidenceLines : ['| - | - | - | - |']),
        ].join('\n');

        const timelineSection = timeline.length
            ? [
                '## Linha do tempo',
                '',
                ...timeline.map((item: any) => `- ${item.date}: ${item.summary || ''}`),
            ].join('\n')
            : '';

        const contradictionsSection = contradictions.length
            ? [
                '## Contradicoes',
                '',
                ...contradictions.map((item: any) => `- ${item.topic}: ${item.samples?.join(' | ') || ''}`),
            ].join('\n')
            : '';

        return [metadataSection, baseText, evidenceTable, timelineSection, contradictionsSection].filter(Boolean).join('\n\n');
    };

    const seekToTime = (time?: number | null) => {
        if (time === null || time === undefined || Number.isNaN(time)) return;
        if (!mediaRef.current) return;
        mediaRef.current.currentTime = Math.max(0, time);
        mediaRef.current.play().catch(() => { });
    };

    const applyHearingPayload = (payload: any) => {
        const hearing = payload?.hearing || payload?.payload?.hearing || payload?.payload || payload;
        const resolveReportMap = (value: any) => {
            if (!value || typeof value !== 'object') return null;
            const entries = Object.entries(value);
            if (entries.length === 0) return null;
            const hasStringPath = entries.some(([, v]) => typeof v === 'string');
            return hasStringPath ? (value as Record<string, string>) : null;
        };
        const reportMap = resolveReportMap(payload?.paths)
            || resolveReportMap(payload?.payload?.paths)
            || resolveReportMap(payload?.reports);
        const auditSummary = payload?.audit_summary || payload?.reports?.audit_summary || payload?.payload?.audit_summary;
        setHearingPayload(hearing || null);
        setHearingSpeakers(hearing?.speakers || []);
        const transcript = hearing?.transcript_markdown || '';
        const formatted = hearing?.formatted_text || null;
        const cleanTranscript = stripReportBlocks(transcript) || transcript;
        const cleanFormatted = formatted ? (stripReportBlocks(formatted) || formatted) : null;
        setHearingTranscript(cleanTranscript);
        setHearingFormatted(cleanFormatted);
        const reportContent = extractReports(formatted) || extractReports(transcript);
        setReport(reportContent);
        // Preview padrão deve ser o resultado formatado (quando existir).
        setResult(cleanFormatted || cleanTranscript || null);
        clearRichContent();
        const mergedReports = mergeReportKeys(reportMap, auditSummary);
        if (mergedReports) {
            setReportPaths(normalizeReportPaths(mergedReports));
        } else {
            setReportPaths(null);
        }
        setActiveTab('preview');
    };

    const handleStreamError = (error: string) => {
        console.error(error);
        const normalized = String(error || '').toLowerCase();
        if (normalized.includes('timeout')) {
            toast.info('Conexão perdida. O job continua em andamento; use "Acompanhar" no Histórico.');
            setIsProcessing(false);
            setProgressStage('running');
            setProgressMessage('Processando em segundo plano...');
            setEtaSeconds(null);
            loadJobHistory().catch(() => undefined);
            return;
        }
        if (normalized.includes('cancel')) {
            toast.info('Job interrompido.');
        } else {
            toast.error(`Erro ao transcrever: ${error}`);
        }
        setIsProcessing(false);
        setProgressStage('');
        setEtaSeconds(null);
        loadJobHistory().catch(() => undefined);
    };

    const runJobStream = async (jobId: string, onComplete: (payload: any) => Promise<void> | void) => {
        const startTime = Date.now();

        const onProgress = (stage: string, progress: number, message: string) => {
            console.log('[SSE Progress]', { stage, progress, message });
            setProgressStage(stage);
            setProgressPercent(progress);
            setProgressMessage(message);

            if (progress > 0 && progress < 100) {
                const elapsed = (Date.now() - startTime) / 1000;
                const totalEstimate = elapsed / (progress / 100);
                const remaining = Math.max(totalEstimate - elapsed, 0);
                setEtaSeconds(Math.round(remaining));
            }

            const now = new Date();
            const timestamp = `${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}:${now.getSeconds().toString().padStart(2, '0')}`;
            const percentLabel = typeof progress === 'number' ? `[${progress}%] ` : '';
            setLogs(prev => [...prev, { timestamp, message: `${percentLabel}${message}` }]);

            if (stage === 'audit_complete') {
                try {
                    const auditData = JSON.parse(message);
                    const issues = Array.isArray(auditData.issues) ? auditData.issues : [];
                    setAuditIssues(issues);
                    setSelectedIssues(new Set(issues.map((i: any) => i.id)));
                    if (auditData.reports || auditData.audit_summary) {
                        const mergedReports = mergeReportKeys(auditData.reports, auditData.audit_summary);
                        if (mergedReports) {
                            setReportPaths(normalizeReportPaths(mergedReports));
                        }
                    }
                    if (auditData.auto_applied) {
                        const appliedFixes = Array.isArray(auditData.auto_applied_fixes)
                            ? auditData.auto_applied_fixes
                            : [];

                        // Categorizar correções usando função robusta
                        const { structural, content, total } = categorizeAutoAppliedFixes(appliedFixes);

                        // Armazenar resumo de auto-aplicações
                        setAutoAppliedSummary({ structural, content, total });

                        if (structural.length > 0 && content.length > 0) {
                            toast.success(
                                `Auto-aplicadas: ${structural.length} correção(ões) estrutural(is) + ${content.length} de conteúdo`,
                                { duration: 5000 }
                            );
                            console.log('🔧 Correções estruturais auto-aplicadas:', structural);
                            console.log('🤖 Correções de conteúdo auto-aplicadas:', content);
                        } else if (structural.length > 0) {
                            toast.success(
                                `${structural.length} correção(ões) estrutural(is) aplicada(s) automaticamente`,
                                { duration: 4000 }
                            );
                            console.log('🔧 Correções estruturais auto-aplicadas:', structural);
                        } else if (content.length > 0) {
                            toast.success(
                                `${content.length} correção(ões) de conteúdo aplicada(s) automaticamente via IA`,
                                { duration: 5000 }
                            );
                            console.log('🤖 Correções de conteúdo auto-aplicadas:', content);
                        } else if (total > 0) {
                            toast.success(
                                `${total} correção(ões) aplicada(s) automaticamente`,
                                { duration: 4000 }
                            );
                            console.log('✅ Correções auto-aplicadas:', appliedFixes);
                        }
                    } else {
                        setAutoAppliedSummary(null);
                    }
                } catch (e) {
                    console.warn('Failed to parse audit data:', e);
                }
            }
        };

        await apiClient.streamTranscriptionJob(
            jobId,
            onProgress,
            async (payload) => onComplete(payload),
            handleStreamError
        );
    };

    const handleJobCompletion = async (payload: any, shouldAutoSave: boolean) => {
        if (payload?.job_type === 'hearing' || payload?.payload) {
            setTranscriptionType('hearing');
            applyHearingPayload(payload?.payload || payload);
            setJobQuality(payload?.quality ?? null);
            setIsAuditOutdated(Boolean(payload?.quality?.needs_revalidate));
            setActiveDocumentName(
                hearingCaseId?.trim()
                    ? `Caso ${hearingCaseId.trim()}`
                    : files.length === 1
                        ? files[0]?.name || 'Audiência'
                        : 'Audiência'
            );
            setIsProcessing(false);
            setProgressPercent(100);
            setEtaSeconds(0);
            toast.success('Audiência processada com sucesso!');
            if (shouldAutoSave) {
                const hearing = payload?.payload || payload || {};
                const rawContent = hearing?.transcript_markdown || '';
                const formattedContent = hearing?.formatted_text || rawContent;
                const displayName = files.length === 1 ? files[0]?.name || hearingCaseId || 'audiencia' : hearingCaseId || 'audiencia';
                await autoSaveDocuments({
                    formattedContent,
                    rawContent,
                    displayName,
                    tags: `transcricao,audiencia,case:${hearingCaseId}`,
                    folderId: hearingCaseId, // Pass case ID as folder ID context
                });
            }
            await loadJobHistory();
            return;
        }

        setTranscriptionType('apostila');
        if (payload?.mode) {
            setMode(String(payload.mode));
        }
        setHearingPayload(null);
        setHearingTranscript(null);
        setHearingFormatted(null);
        setActiveDocumentName(
            files.length === 0
                ? 'Documento'
                : files.length === 1
                    ? files[0]?.name || 'Documento'
                    : `${files.length} arquivos`
        );
        const content = payload?.content ?? payload?.raw_content ?? '';
        const rawContent = payload?.raw_content ?? payload?.content ?? '';
        processResponse(content, rawContent, {
            html: payload?.rich_text_html ?? null,
            json: payload?.rich_text_json ?? null,
            meta: payload?.rich_text_meta ?? null,
        });
        setReportPaths(normalizeReportPaths(mergeReportKeys(payload?.reports ?? null, payload?.audit_summary)));
        setJobQuality(payload?.quality ?? null);
        setIsAuditOutdated(Boolean(payload?.quality?.needs_revalidate));
        setIsProcessing(false);
        setProgressPercent(100);
        setEtaSeconds(0);
        setActiveTab('preview');

        // Processar auto_applied_fixes se disponível
        if (payload?.auto_applied || (payload?.quality?.auto_applied_fixes && Array.isArray(payload.quality.auto_applied_fixes))) {
            const appliedFixes = Array.isArray(payload?.quality?.auto_applied_fixes)
                ? payload.quality.auto_applied_fixes
                : (Array.isArray(payload?.auto_applied_fixes) ? payload.auto_applied_fixes : []);

            if (appliedFixes.length > 0) {
                const { structural, content, total } = categorizeAutoAppliedFixes(appliedFixes);
                setAutoAppliedSummary({ structural, content, total });
                console.log('📊 Auto-aplicações detectadas no payload:', { structural, content, total });
            } else {
                setAutoAppliedSummary(null);
            }
        } else {
            setAutoAppliedSummary(null);
        }

        if (Array.isArray(payload?.audit_issues)) {
            const issues = enrichHilIssues(payload.audit_issues, rawContent, content);
            setAuditIssues(issues);
            setSelectedIssues(new Set(issues.map((i: any) => i.id)));
        } else {
            setAuditIssues([]);
            setSelectedIssues(new Set());
        }
        toast.success('Transcrição concluída com sucesso!');

        if (shouldAutoSave) {
            const displayName = files.length === 1 ? files[0]?.name || 'arquivo' : `${files.length}_arquivos`;
            await autoSaveDocuments({
                formattedContent: content,
                rawContent: rawContent || content,
                displayName,
                tags: `transcricao,${mode.toLowerCase()}`,
            });
        }

        await loadJobHistory();
    };

    const handleLoadJobResult = async (jobId: string) => {
        try {
            const data = await apiClient.getTranscriptionJobResult(jobId);
            setActiveJobId(jobId);
            setIsProcessing(false);
            setProgressStage('complete');
            setProgressPercent(100);
            setEtaSeconds(0);
            setLogs([]);
            setJobMediaFiles([]);

            // Load media URL from server (persisted audio/video)
            try {
                const mediaData = await apiClient.listJobMedia(jobId);
                if (Array.isArray(mediaData?.files) && mediaData.files.length > 0) {
                    const mapped = mediaData.files.map((f, idx) => ({
                        name: f?.name || `Arquivo ${idx + 1}`,
                        url: apiClient.getJobMediaUrl(jobId, idx),
                    }));
                    setJobMediaFiles(mapped);
                    setMediaUrl(mapped[0]?.url || null);
                    console.log('[handleLoadJobResult] Media URL loaded:', mapped[0]?.url);
                } else {
                    setMediaUrl(null);
                }
            } catch (mediaError) {
                console.warn('[handleLoadJobResult] Could not load media:', mediaError);
                setMediaUrl(null);
            }

            if (data?.job_type === 'hearing' || data?.payload) {
                setTranscriptionType('hearing');
                applyHearingPayload(data);
                setJobQuality(data?.quality ?? null);
                setIsAuditOutdated(Boolean(data?.quality?.needs_revalidate));
                setHearingDocumentTheme(String(data?.config?.document_theme || 'classic'));
                setHearingDocumentLayout((prev) => ({
                    ...prev,
                    margins: (String(data?.config?.document_margins || prev.margins) as DocumentLayout['margins']),
                    headerText: String(data?.config?.document_header || ''),
                    footerText: String(data?.config?.document_footer || ''),
                    showHeaderFooter: data?.config?.document_show_header_footer !== undefined
                        ? Boolean(data.config.document_show_header_footer)
                        : prev.showHeaderFooter,
                    pageFrame: data?.config?.document_page_frame !== undefined
                        ? Boolean(data.config.document_page_frame)
                        : prev.pageFrame,
                    fontFamily: String(data?.config?.document_font_family || prev.fontFamily || ''),
                    fontSize: coerceNumber(data?.config?.document_font_size, prev.fontSize),
                    lineHeight: coerceNumber(data?.config?.document_line_height, prev.lineHeight),
                    paragraphSpacing: coerceNumber(data?.config?.document_paragraph_spacing, prev.paragraphSpacing),
                }));
                const caseId = data?.payload?.case_id || data?.config?.case_id || data?.case_id;
                setActiveDocumentName(caseId ? `Caso ${caseId}` : 'Audiência');
                toast.success('Resultado de audiência carregado!');
            } else {
                setTranscriptionType('apostila');
                if (data?.mode) {
                    setMode(String(data.mode));
                }
                setHearingPayload(null);
                setHearingTranscript(null);
                setHearingFormatted(null);
                setDocumentTheme(String(data?.config?.document_theme || 'classic'));
                setDocumentLayout((prev) => ({
                    ...prev,
                    margins: (String(data?.config?.document_margins || prev.margins) as DocumentLayout['margins']),
                    headerText: String(data?.config?.document_header || ''),
                    footerText: String(data?.config?.document_footer || ''),
                    showHeaderFooter: data?.config?.document_show_header_footer !== undefined
                        ? Boolean(data.config.document_show_header_footer)
                        : prev.showHeaderFooter,
                    pageFrame: data?.config?.document_page_frame !== undefined
                        ? Boolean(data.config.document_page_frame)
                        : prev.pageFrame,
                    fontFamily: String(data?.config?.document_font_family || prev.fontFamily || ''),
                    fontSize: coerceNumber(data?.config?.document_font_size, prev.fontSize),
                    lineHeight: coerceNumber(data?.config?.document_line_height, prev.lineHeight),
                    paragraphSpacing: coerceNumber(data?.config?.document_paragraph_spacing, prev.paragraphSpacing),
                }));
                const fileNames = Array.isArray(data?.file_names) ? data.file_names.filter(Boolean) : [];
                setActiveDocumentName(fileNames.length ? fileNames.join(', ') : 'Documento');
                const content = data?.content ?? data?.raw_content ?? '';
                const rawContent = data?.raw_content ?? data?.content ?? '';
                processResponse(content, rawContent, {
                    html: data?.rich_text_html ?? null,
                    json: data?.rich_text_json ?? null,
                    meta: data?.rich_text_meta ?? null,
                });
                setReportPaths(normalizeReportPaths(mergeReportKeys(data?.reports ?? null, data?.audit_summary)));
                setJobQuality(data?.quality ?? null);
                setIsAuditOutdated(Boolean(data?.quality?.needs_revalidate));
                setActiveTab('preview');

                // Processar auto_applied_fixes se disponível
                if (data?.auto_applied || (data?.quality?.auto_applied_fixes && Array.isArray(data.quality.auto_applied_fixes))) {
                    const appliedFixes = Array.isArray(data?.quality?.auto_applied_fixes)
                        ? data.quality.auto_applied_fixes
                        : (Array.isArray(data?.auto_applied_fixes) ? data.auto_applied_fixes : []);

                    if (appliedFixes.length > 0) {
                        const { structural, content, total } = categorizeAutoAppliedFixes(appliedFixes);
                        setAutoAppliedSummary({ structural, content, total });
                        console.log('📊 Auto-aplicações detectadas no job carregado:', { structural, content, total });
                    } else {
                        setAutoAppliedSummary(null);
                    }
                } else {
                    setAutoAppliedSummary(null);
                }

                if (Array.isArray(data?.audit_issues)) {
                    const issues = enrichHilIssues(data.audit_issues, rawContent, content);
                    setAuditIssues(issues);
                    setSelectedIssues(new Set(issues.map((i: any) => i.id)));
                } else {
                    setAuditIssues([]);
                    setSelectedIssues(new Set());
                }
                toast.success('Resultado carregado!');
            }
        } catch (error: any) {
            console.error(error);
            toast.error(`Falha ao carregar resultado: ${error?.message || 'Erro desconhecido'}`);
        }
    };

    const handleResumeJob = async (jobId: string) => {
        setActiveJobId(jobId);
        setIsProcessing(true);
            setResult(null);
            clearRichContent();
        setRawResult(null);
        setReport(null);
        setReportPaths(null);
        setHearingPayload(null);
        setHearingTranscript(null);
        setHearingFormatted(null);
        setJobMediaFiles([]);
        setProgressStage('starting');
        setProgressPercent(0);
        setProgressMessage('Retomando...');
        setLogs([]);
        setActiveSegmentId(null);
        setCurrentTime(0);
        setEtaSeconds(null);

        await runJobStream(jobId, async (payload) => {
            await handleJobCompletion(payload, false);
        });
    };

    const handleDeleteJob = async (jobId: string) => {
        if (!confirm('Deseja excluir este job? Os relatórios e arquivos gerados serão removidos.')) return;
        try {
            await apiClient.deleteTranscriptionJob(jobId, true);
            setJobHistory((prev) => prev.filter((job) => job.job_id !== jobId));
            setSelectedJobIds((prev) => {
                const next = new Set(prev);
                next.delete(jobId);
                return next;
            });
            if (activeJobId === jobId) {
                setActiveJobId(null);
            }
            toast.success('Job excluído.');
        } catch (error: any) {
            console.error(error);
            toast.error(formatApiError(error, 'Falha ao excluir job:'));
        }
    };

    const handleDeleteSelectedJobs = async (jobIds?: string[]) => {
        const selectedIds = (jobIds ?? Array.from(selectedJobIds)).filter(Boolean);
        if (selectedIds.length === 0) {
            toast.info('Selecione ao menos um job.');
            return;
        }

        const jobsById = new Map(jobHistory.map((job) => [job.job_id, job]));
        const deletableIds = selectedIds.filter((id) => {
            const job = jobsById.get(id);
            return job && isJobDeletable(job);
        });
        if (deletableIds.length === 0) {
            toast.info('Nenhum job selecionado pode ser excluído.');
            return;
        }

        const skippedCount = selectedIds.length - deletableIds.length;
        const confirmMessage = skippedCount
            ? `Deseja excluir ${deletableIds.length} job(s)? ${skippedCount} em execução serão ignorados.`
            : `Deseja excluir ${deletableIds.length} job(s) selecionado(s)?`;
        if (!confirm(confirmMessage)) return;

        const results = await Promise.allSettled(
            deletableIds.map((id) => apiClient.deleteTranscriptionJob(id, true))
        );
        const deletedIds = deletableIds.filter((_, idx) => results[idx].status === 'fulfilled');
        const failedCount = results.filter((result) => result.status === 'rejected').length;

        if (deletedIds.length > 0) {
            setJobHistory((prev) => prev.filter((job) => !deletedIds.includes(job.job_id)));
            setSelectedJobIds((prev) => {
                const next = new Set(prev);
                deletedIds.forEach((id) => next.delete(id));
                return next;
            });
            if (activeJobId && deletedIds.includes(activeJobId)) {
                setActiveJobId(null);
            }
        }

        if (failedCount > 0) {
            toast.error(`Falha ao excluir ${failedCount} job(s).`);
        } else {
            toast.success(`Job${deletedIds.length > 1 ? 's' : ''} excluído${deletedIds.length > 1 ? 's' : ''}.`);
        }

        if (skippedCount > 0) {
            toast.info(`${skippedCount} job(s) em execução não foram excluídos.`);
        }
    };

    const handleCancelJob = async (jobId: string) => {
        if (!confirm('Deseja interromper este job agora?')) return;
        try {
            await apiClient.cancelTranscriptionJob(jobId);
            setJobHistory((prev) =>
                prev.map((job) =>
                    job.job_id === jobId
                        ? { ...job, status: 'canceled', stage: 'canceled', message: 'Cancelado pelo usuário.' }
                        : job
                )
            );
            if (activeJobId === jobId) {
                setIsProcessing(false);
                setProgressStage('canceled');
                setProgressMessage('Job interrompido.');
                setEtaSeconds(null);
            }
            toast.success('Job interrompido.');
        } catch (error: any) {
            console.error(error);
            toast.error(formatApiError(error, 'Falha ao interromper job:'));
        }
    };

    const handleDeleteSavedDocument = async (doc: any) => {
        const docId = resolveSavedDocumentId(doc);
        const docName = doc?.name;
        if (!docId) {
            toast.error('Não foi possível identificar o documento para exclusão.');
            return;
        }
        if (!confirm(`Deseja excluir "${docName || 'documento'}"?`)) return;
        try {
            await apiClient.deleteDocument(docId);
            setSavedDocuments((prev) =>
                prev.filter((item) => resolveSavedDocumentId(item) !== docId)
            );
            setSelectedSavedDocIds((prev) => {
                const next = new Set(prev);
                next.delete(docId);
                return next;
            });
            await refreshDocuments().catch(() => undefined);
            await loadSavedDocuments().catch(() => undefined);
            toast.success('Documento excluído.');
        } catch (error: any) {
            console.error(error);
            toast.error(formatApiError(error, 'Falha ao excluir documento:'));
        }
    };

    const handleDeleteSelectedSavedDocuments = async (docIds?: string[]) => {
        const selectedIds = (docIds ?? Array.from(selectedSavedDocIds)).filter(Boolean);
        if (selectedIds.length === 0) {
            toast.info('Selecione ao menos um arquivo.');
            return;
        }

        if (!confirm(`Deseja excluir ${selectedIds.length} arquivo(s) selecionado(s)?`)) return;

        const deletedIds: string[] = [];
        const failed: Array<{ id: string; error: any }> = [];

        for (const id of selectedIds) {
            try {
                await apiClient.deleteDocument(id);
                deletedIds.push(id);
            } catch (error: any) {
                failed.push({ id, error });
            }
        }

        if (deletedIds.length > 0) {
            setSavedDocuments((prev) =>
                prev.filter((item) => !deletedIds.includes(resolveSavedDocumentId(item)))
            );
            setSelectedSavedDocIds((prev) => {
                const next = new Set(prev);
                deletedIds.forEach((id) => next.delete(id));
                return next;
            });
            await refreshDocuments().catch(() => undefined);
            await loadSavedDocuments().catch(() => undefined);
        }

        if (failed.length > 0) {
            const nameEntries = savedDocuments
                .map((doc): [string, string | undefined] => [resolveSavedDocumentId(doc), doc?.name])
                .filter((entry): entry is [string, string | undefined] => Boolean(entry[0]));
            const nameMap = new Map<string, string | undefined>(nameEntries);
            const failedNames = failed
                .map((entry) => nameMap.get(entry.id))
                .filter(Boolean) as string[];
            const preview = failedNames.slice(0, 3).join(', ');
            const suffix = failedNames.length > 3 ? ` +${failedNames.length - 3}` : '';
            const detail = failed[0]?.error;
            const fallback = `Falha ao excluir ${failed.length} arquivo(s).`;
            const message = formatApiError(detail, fallback);
            toast.error(preview ? `${message} (${preview}${suffix})` : message);
        } else {
            toast.success(`Arquivo${deletedIds.length > 1 ? 's' : ''} excluído${deletedIds.length > 1 ? 's' : ''}.`);
        }
    };

    const handleSubmit = async () => {
        const urlValue = publicUrl.trim();
        const hasUrl = Boolean(urlValue);
        if (files.length === 0 && !hasUrl) {
            toast.error('Selecione um arquivo OU informe uma URL pública (YouTube).');
            return;
        }
        if (files.length > 0 && hasUrl) {
            toast.error('Escolha apenas uma fonte: arquivos OU URL (não ambos).');
            return;
        }

        setJobQuality(null);
        setJobMediaFiles([]);
        const onlyTextFiles = files.length > 0 && files.every(isTextFile);
        const options = {
            mode,
            thinking_level: thinkingLevel,
            custom_prompt: customPrompt || undefined,
            document_theme: documentTheme,
            document_header: (documentLayout.headerText || '').trim() || undefined,
            document_footer: (documentLayout.footerText || '').trim() || undefined,
            document_margins: documentLayout.margins,
            document_page_frame: documentLayout.pageFrame,
            document_show_header_footer: documentLayout.showHeaderFooter,
            document_font_family: documentLayout.fontFamily || undefined,
            document_font_size: documentLayout.fontSize,
            document_line_height: documentLayout.lineHeight,
            document_paragraph_spacing: documentLayout.paragraphSpacing,
            model_selection: selectedModel,
            high_accuracy: highAccuracy,
            diarization: enableDiarization ? true : undefined,
            diarization_strict: enableDiarization ? true : undefined,
            use_cache: useRawCache,
            auto_apply_fixes: autoApplyFixes,
            auto_apply_content_fixes: autoApplyContentFixes,
            skip_legal_audit: skipLegalAudit,
            skip_fidelity_audit: skipFidelityAudit,
            skip_sources_audit: skipFidelityAudit,
        };

        if (isHearing) {
            if (!hearingCaseId.trim()) {
                toast.error('Informe o número do processo/caso.');
                return;
            }
            if (!hasUrl && files.length > 1) {
                toast.error('Para audiências/reuniões, envie apenas um arquivo por vez.');
                return;
            }
            if (hearingUseCustomPrompt && hearingFormatMode !== 'none' && !hearingCustomPrompt.trim()) {
                toast.error('Informe o prompt personalizado para formatação.');
                return;
            }
            if (!hasUrl && files.length === 1 && isTextFile(files[0])) {
                toast.error('Audiências requerem arquivo de áudio ou vídeo.');
                return;
            }
        }

        if (!followJobLive) {
            try {
                if (isHearing) {
                    setActiveDocumentName(hearingCaseId?.trim() ? `Caso ${hearingCaseId.trim()}` : 'Audiência');
                    const formatEnabled = hearingFormatMode !== 'none';
                    const formatMode = formatEnabled ? hearingFormatMode.toUpperCase() : 'AUDIENCIA';
                    const customPrompt =
                        formatEnabled && hearingUseCustomPrompt ? hearingCustomPrompt.trim() : undefined;
                    const allowIndirect = formatEnabled && hearingAllowIndirect;
                    const allowSummary = formatEnabled && hearingAllowSummary;
                    const job = hasUrl
                        ? await apiClient.startHearingJobFromUrl(urlValue, {
                            case_id: hearingCaseId.trim(),
                            goal: hearingGoal,
                            thinking_level: thinkingLevel,
                            model_selection: selectedModel,
                            high_accuracy: highAccuracy,
                            format_mode: formatMode,
                            custom_prompt: customPrompt,
                            document_theme: hearingDocumentTheme,
                            document_header: (hearingDocumentLayout.headerText || '').trim() || undefined,
                            document_footer: (hearingDocumentLayout.footerText || '').trim() || undefined,
                            document_margins: hearingDocumentLayout.margins,
                            document_page_frame: hearingDocumentLayout.pageFrame,
                            document_show_header_footer: hearingDocumentLayout.showHeaderFooter,
                            document_font_family: hearingDocumentLayout.fontFamily || undefined,
                            document_font_size: hearingDocumentLayout.fontSize,
                            document_line_height: hearingDocumentLayout.lineHeight,
                            document_paragraph_spacing: hearingDocumentLayout.paragraphSpacing,
                            format_enabled: formatEnabled,
                            include_timestamps: hearingIncludeTimestamps,
                            allow_indirect: allowIndirect,
                            allow_summary: allowSummary,
                            use_cache: useRawCache,
                            auto_apply_fixes: autoApplyFixes,
                            auto_apply_content_fixes: autoApplyContentFixes,
                            skip_legal_audit: skipLegalAudit,
                            skip_fidelity_audit: skipFidelityAudit,
                            skip_sources_audit: skipFidelityAudit,
                        })
                        : await apiClient.startHearingJob(files[0], {
                            case_id: hearingCaseId.trim(),
                            goal: hearingGoal,
                            thinking_level: thinkingLevel,
                            model_selection: selectedModel,
                            high_accuracy: highAccuracy,
                            format_mode: formatMode,
                            custom_prompt: customPrompt,
                            document_theme: hearingDocumentTheme,
                            document_header: (hearingDocumentLayout.headerText || '').trim() || undefined,
                            document_footer: (hearingDocumentLayout.footerText || '').trim() || undefined,
                            document_margins: hearingDocumentLayout.margins,
                            document_page_frame: hearingDocumentLayout.pageFrame,
                            document_show_header_footer: hearingDocumentLayout.showHeaderFooter,
                            document_font_family: hearingDocumentLayout.fontFamily || undefined,
                            document_font_size: hearingDocumentLayout.fontSize,
                            document_line_height: hearingDocumentLayout.lineHeight,
                            document_paragraph_spacing: hearingDocumentLayout.paragraphSpacing,
                            format_enabled: formatEnabled,
                            include_timestamps: hearingIncludeTimestamps,
                            allow_indirect: allowIndirect,
                            allow_summary: allowSummary,
                            use_cache: useRawCache,
                            auto_apply_fixes: autoApplyFixes,
                            auto_apply_content_fixes: autoApplyContentFixes,
                            skip_legal_audit: skipLegalAudit,
                            skip_fidelity_audit: skipFidelityAudit,
                            skip_sources_audit: skipFidelityAudit,
                        });
                    if (job?.job_id) setActiveJobId(job.job_id);
                } else {
                    setActiveDocumentName(hasUrl ? 'URL pública' : (files.length === 1 ? files[0]?.name || 'Documento' : `${files.length} arquivos`));
                    const job = hasUrl
                        ? await apiClient.startTranscriptionJobFromUrl(urlValue, options)
                        : await apiClient.startTranscriptionJob(files, options);
                    if (job?.job_id) setActiveJobId(job.job_id);
                }
                toast.success('Job iniciado. Acompanhe no dashboard.');
                setFiles([]);
                setPublicUrl('');
                setSettingsOpen(false);
                setMainTab('jobs');
                await loadJobHistory().catch(() => undefined);
            } catch (error: any) {
                toast.error(formatApiError(error, 'Falha ao iniciar job.'));
            }
            return;
        }

        setIsProcessing(true);
        setResult(null);
        clearRichContent();
        setRawResult(null);
        setReport(null);
        setReportPaths(null);
        setHearingPayload(null);
        setHearingTranscript(null);
        setHearingFormatted(null);
        setProgressStage('starting');
        setProgressPercent(0);
        setProgressMessage('Iniciando...');
        setLogs([]); // Clear logs
        setActiveSegmentId(null);
        setCurrentTime(0);

        setEtaSeconds(null);
        setSettingsOpen(false);

        if (isHearing) {
            const formatEnabled = hearingFormatMode !== 'none';
            const formatMode = formatEnabled ? hearingFormatMode.toUpperCase() : 'AUDIENCIA';
            const customPrompt =
                formatEnabled && hearingUseCustomPrompt ? hearingCustomPrompt.trim() : undefined;
            const allowIndirect = formatEnabled && hearingAllowIndirect;
            const allowSummary = formatEnabled && hearingAllowSummary;

            try {
                const job = hasUrl
                    ? await apiClient.startHearingJobFromUrl(urlValue, {
                        case_id: hearingCaseId.trim(),
                        goal: hearingGoal,
                        thinking_level: thinkingLevel,
                        model_selection: selectedModel,
                        high_accuracy: highAccuracy,
                        format_mode: formatMode,
                        custom_prompt: customPrompt,
                        document_theme: hearingDocumentTheme,
                        document_header: (hearingDocumentLayout.headerText || '').trim() || undefined,
                        document_footer: (hearingDocumentLayout.footerText || '').trim() || undefined,
                        document_margins: hearingDocumentLayout.margins,
                        document_page_frame: hearingDocumentLayout.pageFrame,
                        document_show_header_footer: hearingDocumentLayout.showHeaderFooter,
                        document_font_family: hearingDocumentLayout.fontFamily || undefined,
                        document_font_size: hearingDocumentLayout.fontSize,
                        document_line_height: hearingDocumentLayout.lineHeight,
                        document_paragraph_spacing: hearingDocumentLayout.paragraphSpacing,
                        format_enabled: formatEnabled,
                        include_timestamps: hearingIncludeTimestamps,
                        allow_indirect: allowIndirect,
                        allow_summary: allowSummary,
                        use_cache: useRawCache,
                        auto_apply_fixes: autoApplyFixes,
                        auto_apply_content_fixes: autoApplyContentFixes,
                        skip_legal_audit: skipLegalAudit,
                        skip_fidelity_audit: skipFidelityAudit,
                        skip_sources_audit: skipFidelityAudit,
                    })
                    : await apiClient.startHearingJob(files[0], {
                        case_id: hearingCaseId.trim(),
                        goal: hearingGoal,
                        thinking_level: thinkingLevel,
                        model_selection: selectedModel,
                        high_accuracy: highAccuracy,
                        format_mode: formatMode,
                        custom_prompt: customPrompt,
                        document_theme: hearingDocumentTheme,
                        document_header: (hearingDocumentLayout.headerText || '').trim() || undefined,
                        document_footer: (hearingDocumentLayout.footerText || '').trim() || undefined,
                        document_margins: hearingDocumentLayout.margins,
                        document_page_frame: hearingDocumentLayout.pageFrame,
                        document_show_header_footer: hearingDocumentLayout.showHeaderFooter,
                        document_font_family: hearingDocumentLayout.fontFamily || undefined,
                        document_font_size: hearingDocumentLayout.fontSize,
                        document_line_height: hearingDocumentLayout.lineHeight,
                        document_paragraph_spacing: hearingDocumentLayout.paragraphSpacing,
                        format_enabled: formatEnabled,
                        include_timestamps: hearingIncludeTimestamps,
                        allow_indirect: allowIndirect,
                        allow_summary: allowSummary,
                        use_cache: useRawCache,
                        auto_apply_fixes: autoApplyFixes,
                        auto_apply_content_fixes: autoApplyContentFixes,
                        skip_legal_audit: skipLegalAudit,
                        skip_fidelity_audit: skipFidelityAudit,
                        skip_sources_audit: skipFidelityAudit,
                    });
                setActiveJobId(job.job_id);
                setMainTab('preview');
                await runJobStream(job.job_id, async (payload) => {
                    await handleJobCompletion(payload, true);
                });
            } catch (error: any) {
                handleStreamError(error.message || 'Falha ao iniciar job');
            }
            return;
        }
        try {
            const job = hasUrl
                ? await apiClient.startTranscriptionJobFromUrl(urlValue, options)
                : await apiClient.startTranscriptionJob(files, options);
            setActiveJobId(job.job_id);
            setMainTab('preview');
            await runJobStream(job.job_id, async (payload) => {
                await handleJobCompletion(payload, true);
            });
        } catch (error: any) {
            handleStreamError(error.message || 'Falha ao iniciar job');
        }
    };

    const triggerMarkdownDownload = (markdown: string, fileName: string) => {
        const blob = new Blob([markdown], { type: 'text/markdown' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = fileName;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    };

    const handleExportMD = () => {
        if (isHearing ? !hearingTranscript : !result) return;
        const exportContent = (isHearing ? buildHearingExportContent() : result) || '';
        triggerMarkdownDownload(exportContent, `transcricao-${new Date().getTime()}.md`);
        toast.success('Arquivo Markdown baixado!');
    };

    // New: HIL Validation Helper
    const handleImportMD = (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;

        const reader = new FileReader();
        reader.onload = (event) => {
            const content = event.target?.result as string;
            if (content) {
                processResponse(content, null, null);
                setReportPaths(null);
                toast.success('Arquivo carregado para revisão!');
            }
        };
        reader.readAsText(file);
    };
	    const handleExportDocx = async () => {
	        if (!isHearing && hasPreventiveAudit) {
	            if (preventiveAuditLoading) {
	                toast.info('Carregando auditoria preventiva...');
	            } else if (preventiveShouldBlock) {
	                toast.warning(`Revisão recomendada: ${preventiveBlockReason}`);
	            }
	        }
	        if (isHearing ? !hearingTranscript : !result) return;
	        try {
	            const exportContent = (isHearing ? buildHearingExportContent() : result) || '';
                const blob = await apiClient.exportDocx(exportContent, `transcricao-${new Date().getTime()}.docx`, {
                    document_theme: activeDocumentTheme,
                    document_header: (activeDocumentLayout.headerText || '').trim() || undefined,
                    document_footer: (activeDocumentLayout.footerText || '').trim() || undefined,
                    document_margins: activeDocumentLayout.margins,
                    document_font_family: activeDocumentLayout.fontFamily || undefined,
                    document_font_size: activeDocumentLayout.fontSize,
                    document_line_height: activeDocumentLayout.lineHeight,
                    document_paragraph_spacing: activeDocumentLayout.paragraphSpacing,
                });
	            const url = URL.createObjectURL(blob);
	            const a = document.createElement('a');
	            a.href = url;
	            a.download = `transcricao-${new Date().getTime()}.docx`;
	            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
            toast.success('Arquivo Word baixado!');
        } catch (error) {
            console.error(error);
            toast.error('Erro ao exportar Word.');
        }
    };

    const handleConvertPreventiveToHil = async () => {
        if (!preventiveAudit) {
            toast.info('Relatorio preventivo ainda nao disponivel.');
            return;
        }
        const localIssues = buildPreventiveHilIssues(preventiveAudit);
        if (localIssues.length === 0) {
            toast.info('Nenhum alerta preventivo para converter.');
            return;
        }

        if (!activeJobId) {
            const existingIds = new Set(auditIssues.map((issue: any) => issue?.id).filter(Boolean));
            const newIssues = localIssues.filter((issue: any) => issue?.id && !existingIds.has(issue.id));
            if (newIssues.length === 0) {
                toast.info('Alertas preventivos ja convertidos em issues HIL.');
                return;
            }
            setAuditIssues((prev) => [...prev, ...newIssues]);
            setSelectedIssues((prev) => {
                const next = new Set(prev);
                newIssues.forEach((issue: any) => {
                    if (issue?.id) next.add(issue.id);
                });
                return next;
            });
            toast.success(`${newIssues.length} issue(s) adicionada(s) a Revisao HIL.`);
            if (!hasRawForHil) {
                toast.warning('RAW necessario para aplicar correcoes de conteudo.');
            }
            return;
        }

        const beforeIds = new Set(auditIssues.map((issue: any) => issue?.id).filter(Boolean));
        const toastId = toast.loading('Convertendo alertas preventivos...');
        try {
            const data = await apiClient.convertPreventiveAlertsToHil(activeJobId);
            const merged = Array.isArray(data?.audit_issues) ? data.audit_issues : [];
            const addedIssues = merged.filter((issue: any) => issue?.id && !beforeIds.has(issue.id));
            if (merged.length > 0) {
                setAuditIssues(merged);
            }
            if (addedIssues.length > 0) {
                setSelectedIssues((prev) => {
                    const next = new Set(prev);
                    addedIssues.forEach((issue: any) => {
                        if (issue?.id) next.add(issue.id);
                    });
                    return next;
                });
                toast.success(`${addedIssues.length} issue(s) adicionada(s) a Revisao HIL.`, { id: toastId });
            } else {
                toast.info('Alertas preventivos ja convertidos em issues HIL.', { id: toastId });
            }
            if (!hasRawForHil) {
                toast.warning('RAW necessario para aplicar correcoes de conteudo.');
            }
        } catch (error: any) {
            console.error(error);
            const message = formatApiError(error, 'Falha ao converter alertas preventivos:');
            toast.error(message, { id: toastId });
        }
    };

    const handleConvertQualityAlertsToHil = (issues: HilIssue[]) => {
        if (!Array.isArray(issues) || issues.length === 0) {
            toast.info('Nenhum alerta de conteudo para converter.');
            return;
        }
        const existingIds = new Set(auditIssues.map((issue: any) => issue?.id).filter(Boolean));
        const existingRefs = new Set(
            auditIssues.map((issue: any) => `${issue?.type || ''}:${issue?.reference || ''}`)
        );
        const newIssues = issues.filter((issue) => {
            if (!issue?.id) return false;
            if (existingIds.has(issue.id)) return false;
            const refKey = `${issue?.type || ''}:${issue?.reference || ''}`;
            if (existingRefs.has(refKey)) return false;
            return true;
        });
        if (newIssues.length === 0) {
            toast.info('Alertas ja estao em Correcoes (HIL).');
            setActiveTab('hil');
            return;
        }
        const mergeLocal = () => {
            setAuditIssues((prevAudit) => [...prevAudit, ...newIssues]);
            setSelectedIssues((prevSelected) => {
                const next = new Set(prevSelected);
                newIssues.forEach((issue) => {
                    if (issue?.id) next.add(issue.id);
                });
                return next;
            });
            setActiveTab('hil');
            toast.success(`${newIssues.length} alerta(s) enviado(s) para Correcoes (HIL).`);
        };

        if (!activeJobId) {
            mergeLocal();
        } else {
            const toastId = toast.loading('Salvando alertas na Revisao HIL...');
            apiClient
                .mergeTranscriptionAuditIssues(activeJobId, newIssues)
                .then((data) => {
                    const merged = Array.isArray(data?.audit_issues) ? data.audit_issues : [];
                    if (merged.length > 0) setAuditIssues(merged);
                    setSelectedIssues((prevSelected) => {
                        const next = new Set(prevSelected);
                        newIssues.forEach((issue) => {
                            if (issue?.id) next.add(issue.id);
                        });
                        return next;
                    });
                    setActiveTab('hil');
                    toast.success(`${newIssues.length} alerta(s) enviado(s) para Correcoes (HIL).`, { id: toastId });
                })
                .catch((error: any) => {
                    console.error(error);
                    toast.error(formatApiError(error, 'Falha ao salvar alertas:'), { id: toastId });
                    // Best-effort fallback: still show locally.
                    mergeLocal();
                });
        }
        if (!hasRawForHil) {
            toast.warning('RAW necessario para aplicar correcoes de conteudo.');
        }
    };

    const handleGoToHil = () => {
        if (!result) {
            toast.info('Nenhum resultado disponivel para revisao HIL.');
            return;
        }
        setActiveTab('hil');
    };

    const handleSaveToLibrary = async (andChat = false) => {
        if ((isHearing ? !hearingTranscript : !result) || files.length === 0) return;
        const displayName = files.length === 1 ? files[0].name : `${files.length}_aulas_unificadas`;
        try {
            toast.info('Salvando na biblioteca...');
            const content = isHearing ? buildHearingExportContent() : (result as string);
            const doc = await apiClient.createDocumentFromText({
                title: `Transcrição: ${displayName}`,
                content,
                tags: isHearing ? 'transcricao,audiencia' : `transcricao,${mode.toLowerCase()}`
            });
            upsertSavedDocuments([doc]);
            if (doc?.id) {
                apiClient.createLibraryItem({
                    type: 'DOCUMENT',
                    name: doc?.name || `Transcrição: ${displayName}`,
                    description: null,
                    tags: Array.isArray(doc?.tags) ? doc.tags : [],
                    folder_id: doc?.folder_id || undefined,
                    resource_id: doc?.id,
                    token_count: 0,
                }).catch(() => undefined);
            }
            toast.success('Salvo na Biblioteca!');

            if (andChat) {
                // Criar chat e redirecionar
                toast.info('Criando chat...');
                const chat = await apiClient.createChat({
                    title: `Chat: ${displayName}`,
                    mode: 'DOCUMENT',
                    context: { initial_document_id: doc.id }
                });
                // Redireciona
                window.location.href = `/chat/${chat.id}?doc=${doc.id}`;
            }
        } catch (error: any) {
            console.error(error);
            toast.error(formatApiError(error, 'Erro ao salvar:'));
        }
    };

    const handleConfirmRevision = async (overrideContent?: string, isPartial = false) => {
        if (!pendingRevision) return;
        const { content: cleaned, data, evidenceUsed } = pendingRevision;
        const finalContent = typeof overrideContent === 'string' ? overrideContent : cleaned;
        setShowDiffConfirm(false);
        setPendingRevision(null);

            setResult(finalContent);
            clearRichContent();
        setIsAuditOutdated(true);

        if (activeJobId) {
            apiClient
                .updateTranscriptionJobQuality(activeJobId, {
                    fixed_content: finalContent,
                    applied_issue_ids: Array.from(new Set(data.applied_issue_ids || data.issues_applied || [])),
                })
                .then((resp) => {
                    if (resp?.quality) setJobQuality(resp.quality);
                })
                .catch(() => toast.warning('Correções aplicadas localmente, mas não foi possível salvar no histórico.'));
        }

        const appliedIds = new Set(data.applied_issue_ids || data.issues_applied || []);
        const skippedIds = new Set(data.skipped_issue_ids || []);
        const structuralCount = (data.structural_fixes_applied || []).length;
        const contentCount = (data.content_fixes_applied || []).length;
        const totalApplied = data.changes_made || 0;
        const hasErrors = data.structural_error || data.content_error;

        if (isPartial) {
            setSelectedIssues(new Set());
            toast.info('Aplicação parcial concluída. Revise os issues antes de finalizar.');
        } else {
            const remainingIssues = auditIssues.filter((i: any) => !appliedIds.has(i.id));
            setAuditIssues(remainingIssues);
            setSelectedIssues(new Set());

            // Atualizar painel de auto-aplicações com as correções manuais aplicadas agora
            if (totalApplied > 0) {
                const manuallyAppliedFixes: string[] = [];

                // Adicionar correções estruturais
                (data.structural_fixes_applied || []).forEach((fixId: string) => {
                    manuallyAppliedFixes.push(`[Manual] ${fixId}`);
                });

                // Adicionar correções de conteúdo
                (data.content_fixes_applied || []).forEach((fixId: string) => {
                    manuallyAppliedFixes.push(`[Manual] ${fixId}`);
                });

                // Se já existe resumo de auto-aplicações, adicionar as manuais
                if (autoAppliedSummary) {
                    const { structural, content, total } = categorizeAutoAppliedFixes(manuallyAppliedFixes);
                    setAutoAppliedSummary({
                        structural: [...autoAppliedSummary.structural, ...structural],
                        content: [...autoAppliedSummary.content, ...content],
                        total: autoAppliedSummary.total + total
                    });
                } else {
                    // Criar novo resumo apenas com as manuais
                    const { structural, content, total } = categorizeAutoAppliedFixes(manuallyAppliedFixes);
                    setAutoAppliedSummary({ structural, content, total });
                }
            }
        }

        setHilDiagnostics((prev) => ({
            contentChanged: typeof data?.content_changed === 'boolean' ? data.content_changed : prev?.contentChanged ?? null,
            contentError: data?.content_error || null,
            contentChange: data?.content_change || null,
            evidence: prev?.evidence ?? evidenceUsed,
        }));

        if (!isPartial) {
            if (totalApplied > 0) {
                let msg = `${totalApplied} correção(ões) aplicada(s)`;
                if (structuralCount > 0 && contentCount > 0) {
                    msg = `${structuralCount} estrutural(is) + ${contentCount} de conteúdo aplicadas`;
                } else if (contentCount > 0) {
                    msg = `${contentCount} correção(ões) de conteúdo aplicada(s) via ${data.model_used || 'LLM'}`;
                }
                toast.success(msg + '!');
            } else {
                toast.info('Nenhuma correção foi aplicada.');
            }

            if (data?.content_changed === false) {
                const change = data?.content_change || {};
                toast.info(`Sem mudanças detectadas no texto (${change.before_chars || 0} → ${change.after_chars || 0} chars).`);
            } else if (data?.content_changed === true && appliedIds.size === 0 && totalApplied === 0) {
                toast.info('Houve alteração no texto, mas nenhum issue foi marcado como aplicado.');
            }
        }

        if (hasErrors) {
            if (data.structural_error) toast.warning(`Erro estrutural: ${data.structural_error}`);
            if (data.content_error) toast.warning(`Erro de conteúdo: ${data.content_error}`);
        }

        if (skippedIds.size > 0) {
            toast.warning(`Correções ignoradas: ${data.skipped_reason || 'dados insuficientes'}.`);
        }

        if (!isPartial) {
            const remainingIssues = auditIssues.filter((i: any) => !appliedIds.has(i.id));
            if (remainingIssues.length > 0) {
                toast.info(`${remainingIssues.length} issue(s) restante(s) para revisão.`);
            }

            // Re-auditar após aplicação (se o usuário quiser)
            if (totalApplied > 0 && remainingIssues.length === 0) {
                toast.info('✅ Todas as correções foram aplicadas. Revalide a Qualidade para atualizar métricas e auditorias.', { duration: 3500 });
            } else if (remainingIssues.length > 0) {
                // Ainda há issues pendentes
                toast.info(`ℹ️ ${remainingIssues.length} issue(s) pendente(s). Revise ou aplique mais correções.`, { duration: 3000 });
            }
        }
    };

    const applyHilIssues = async (issuesToApply: any[], actionLabel: string) => {
        if (!result || issuesToApply.length === 0) {
            toast.info('Nenhuma correção disponível para aplicar.');
            return;
        }

        const hasRaw =
            typeof rawResult === 'string' &&
            rawResult.trim().length > 0;

        let approvedIssues = issuesToApply;
        if (!hasRaw) {
            const structuralOnly = issuesToApply.filter((i: any) => i?.fix_type === 'structural');
            const skippedCount = issuesToApply.length - structuralOnly.length;
            if (skippedCount > 0) {
                toast.warning(
                    'RAW não disponível. Correções de conteúdo foram ignoradas; aplique apenas estruturais.'
                );
            }
            approvedIssues = structuralOnly;
            if (approvedIssues.length === 0) {
                toast.error('Sem RAW para aplicar correções de conteúdo. Refaça a transcrição com RAW.');
                return;
            }
        }

        setIsApplyingFixes(true);
        let toastId: string | number | undefined;
        let slowTimer: ReturnType<typeof setTimeout> | null = null;
        try {
            const structuralToApply = approvedIssues.filter((i: any) => i?.fix_type === 'structural').length;
            const contentToApply = approvedIssues.length - structuralToApply;
            const hint = contentToApply > 0 ? ' (IA pode levar alguns minutos)' : '';
            const evidenceUsed = buildHilEvidenceUsed(approvedIssues);
            setHilDiagnostics({
                contentChanged: null,
                contentError: null,
                contentChange: null,
                evidence: evidenceUsed,
            });
            toastId = toast.loading(`${actionLabel}: ${structuralToApply} estrutural(is) + ${contentToApply} de conteúdo${hint}`);
            slowTimer = setTimeout(() => {
                if (toastId !== undefined) {
                    toast.info('Ainda aplicando correções... se demorar, selecione menos issues.', { id: toastId });
                }
            }, 12000);

            // NOTA: O LLM é chamado aqui primeiro para gerar as correções.
            // O diff de confirmação (DiffConfirmDialog) é mostrado DEPOIS, permitindo
            // que o usuário revise e aprove/rejeite o resultado antes de aplicá-lo ao documento.
            // Este é o comportamento correto: confirmar o OUTPUT do LLM, não o INPUT.
            const totalChars = (result?.length || 0) + (rawResult?.length || 0);
            const shouldUseJobSnapshot = Boolean(activeJobId) && totalChars > 600_000;
            if (shouldUseJobSnapshot) {
                toast.info('Documento grande: aplicando correções usando o snapshot do job para evitar falhas de rede.');
            }
            const data = await apiClient.applyTranscriptionRevisions({
                job_id: activeJobId || undefined,
                content: shouldUseJobSnapshot ? undefined : result,
                // Always prefer loading RAW from the job snapshot when available to reduce request size and avoid aborts.
                raw_content: activeJobId ? undefined : (rawResult || undefined),
                approved_issues: approvedIssues,
                model_selection: selectedModel
            });

            // CRITICAL: Only update result if we got valid content back
            const revisedContent = data.revised_content;
            const hasValidContent = typeof revisedContent === 'string' && revisedContent.trim().length > 0;

            if (!hasValidContent) {
                // Backend returned empty - DO NOT clear the current content
                console.error('Backend returned empty revised_content:', data);
                toast.error('Erro: o backend retornou conteúdo vazio. O documento original foi preservado.', { id: toastId });
                return;
            }

            // Additional sanity check: revised content shouldn't be drastically smaller
            const originalLen = result.length;
            const revisedLen = revisedContent.length;
            if (revisedLen < originalLen * 0.3) {
                console.warn('Revised content is much smaller than original:', { originalLen, revisedLen });
                toast.warning(`Atenção: conteúdo revisado muito menor que o original (${revisedLen} vs ${originalLen} chars). Verifique o resultado.`);
            }

            const cleaned = stripReportBlocks(revisedContent) || revisedContent;

            setPendingRevision({ content: cleaned, data, evidenceUsed: evidenceUsed || [] });
            setShowDiffConfirm(true);
            toast.dismiss(toastId);
            toast.info('Revise as alterações antes de aplicar.');
        } catch (error: any) {
            console.error(error);
            const message = formatApiError(error, 'Erro ao aplicar correções:');
            const lower = String(message || '').toLowerCase();
            if (lower.includes('aborted') || lower.includes('abort')) {
                toast.error(
                    'Erro ao aplicar correções: requisição foi interrompida (aborted). Tente novamente com menos issues ou reabra o preview e tente de novo.',
                    { id: toastId }
                );
            } else {
                toast.error(message, { id: toastId });
            }
            setHilDiagnostics((prev) => ({
                ...prev,
                contentError: message,
            }));
        } finally {
            if (slowTimer) clearTimeout(slowTimer);
            setIsApplyingFixes(false);
        }
    };

    const handleApplyFixes = async () => {
        if (!result || selectedIssues.size === 0) return;
        const approvedIssuesAll = auditIssues.filter(i => selectedIssues.has(i.id));
        await applyHilIssues(approvedIssuesAll, 'Aplicando correções');
    };

    const handleAutoApplyStructural = async () => {
        const structuralIssues = auditIssues.filter((i: any) => i?.fix_type === 'structural');
        if (structuralIssues.length === 0) {
            toast.info('Nenhuma correção estrutural disponível.');
            return;
        }
        await applyHilIssues(structuralIssues, 'Auto-corrigindo estruturais');
    };

    const handleAutoApplyContent = async () => {
        const contentIssues = auditIssues.filter((i: any) => i?.fix_type !== 'structural');
        if (contentIssues.length === 0) {
            toast.info('Nenhuma correção de conteúdo disponível.');
            return;
        }
        const hasRaw =
            typeof rawResult === 'string' &&
            rawResult.trim().length > 0;
        if (!hasRaw) {
            toast.error('Sem RAW para aplicar correções de conteúdo. Refaça a transcrição com RAW.');
            return;
        }
        await applyHilIssues(contentIssues, 'Auto-corrigindo conteúdo (IA)');
    };

    const toggleIssue = (id: string) => {
        setSelectedIssues(prev => {
            const newSet = new Set(prev);
            if (newSet.has(id)) {
                newSet.delete(id);
            } else {
                newSet.add(id);
            }
            return newSet;
        });
    };

    const handleEnrollSpeaker = async () => {
        if (!enrollFile || !hearingCaseId.trim() || !enrollName.trim()) {
            toast.error('Informe caso, nome e áudio para enrollment.');
            return;
        }
        setIsEnrolling(true);
        try {
            const response = await apiClient.enrollHearingSpeaker(enrollFile, {
                case_id: hearingCaseId.trim(),
                name: enrollName.trim(),
                role: enrollRole,
            });
            toast.success('Voz cadastrada com sucesso!');
            if (response?.speaker) {
                setHearingSpeakers(prev => [...prev, response.speaker]);
            }
            setEnrollFile(null);
            setEnrollName('');
        } catch (error: any) {
            console.error(error);
            toast.error('Erro ao cadastrar voz.');
        } finally {
            setIsEnrolling(false);
        }
    };

    const handleSaveSpeakers = async () => {
        if (!hearingCaseId.trim() || hearingSpeakers.length === 0) return;
        setIsSavingSpeakers(true);
        try {
            await apiClient.updateHearingSpeakers(
                hearingCaseId.trim(),
                hearingSpeakers.map((sp: any) => ({
                    speaker_id: sp.speaker_id,
                    name: sp.name,
                    role: sp.role,
                }))
            );
            toast.success('Falantes atualizados!');
        } catch (error: any) {
            console.error(error);
            toast.error('Erro ao salvar falantes.');
        } finally {
            setIsSavingSpeakers(false);
        }
    };

    const hasOutput = isHearing ? Boolean(hearingTranscript) : Boolean(result);
    const preventiveStatus = useMemo(() => buildPreventiveAuditStatus({
        audit: preventiveAudit,
        auditMarkdown: preventiveAuditMarkdown,
        loading: preventiveAuditLoading,
        recommendation: preventiveRecommendation,
    }), [preventiveAudit, preventiveAuditMarkdown, preventiveAuditLoading, preventiveRecommendation]);
    const preventiveShouldBlockDisplay = preventiveStatus.shouldBlockDisplay;
    const reportEntries = buildReportEntries(reportPaths);
    const primaryFile = files[0];
    const isVideoFile = Boolean(primaryFile?.type?.startsWith('video'));
    const hasRawForHil =
        typeof rawResult === 'string' &&
        rawResult.trim().length > 0;
    const deletableJobIds = jobHistory
        .filter(isJobDeletable)
        .map((job) => job.job_id)
        .filter(Boolean);
    const selectableSavedDocIds = savedDocuments
        .map((doc) => resolveSavedDocumentId(doc))
        .filter(Boolean);
    const allJobsSelected = deletableJobIds.length > 0 && selectedJobIds.size === deletableJobIds.length;
    const allDocsSelected = selectableSavedDocIds.length > 0 && selectedSavedDocIds.size === selectableSavedDocIds.length;
    const hearingSegments = useMemo(
        () => (hearingPayload?.segments || []) as any[],
        [hearingPayload]
    );
    const hearingBlocks = useMemo(
        () => (hearingPayload?.blocks || []) as any[],
        [hearingPayload]
    );
    const speakerMap = new Map<string, any>((hearingSpeakers as any[]).map((sp: any) => [String(sp.speaker_id), sp]));
    const blockMap = new Map<string, any>(hearingBlocks.map((block: any) => [String(block.id), block]));
    const validationReport = hearingPayload?.reports?.validation || null;
    const analysisReport = hearingPayload?.reports?.analysis || null;
    const auditWarnings: string[] = hearingPayload?.audit?.warnings || [];

    const missingSpeakerNames = hearingSpeakers.filter((sp: any) => !sp.name || sp.name === sp.label).length;
    const segmentsMissingTime = hearingSegments.filter((seg: any) => seg.start == null && !seg.timestamp_hint).length;
    const validationItems = [
        {
            id: 'speaker_names',
            label: 'Falantes com nome definido',
            ok: missingSpeakerNames === 0,
            detail: missingSpeakerNames ? `${missingSpeakerNames} sem nome confirmado` : 'OK',
        },
        {
            id: 'timestamps',
            label: 'Segmentos com timestamp',
            ok: segmentsMissingTime === 0,
            detail: segmentsMissingTime ? `${segmentsMissingTime} sem timestamp` : 'OK',
        },
        {
            id: 'evidence',
            label: 'Evidências relevantes detectadas',
            ok: (hearingPayload?.evidence || []).length > 0,
            detail: `${(hearingPayload?.evidence || []).length} evidências`,
        },
        {
            id: 'formatting',
            label: 'Texto formatado disponível',
            ok: Boolean(hearingFormatted),
            detail: hearingFormatted ? 'Formato aplicado' : 'Sem formatação',
        },
    ];

    useEffect(() => {
        if (!isHearing || hearingSegments.length === 0) return;
        const active = hearingSegments.find((seg: any) => {
            if (typeof seg.start !== 'number' || typeof seg.end !== 'number') return false;
            return currentTime >= seg.start && currentTime < seg.end;
        });
        if (!active && activeSegmentId) {
            setActiveSegmentId(null);
            return;
        }
        if (active && active.id !== activeSegmentId) {
            setActiveSegmentId(active.id);
        }
    }, [currentTime, hearingSegments, isHearing, activeSegmentId]);

    useEffect(() => {
        if (!activeSegmentId) return;
        const el = document.getElementById(`segment-${activeSegmentId}`);
        if (el) {
            el.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
    }, [activeSegmentId]);

    useEffect(() => {
        if (isProcessing) {
            setProgressDockMinimized(false);
        }
    }, [isProcessing]);

    return (
        <>
        <div className={`flex h-full flex-col gap-6 p-6 ${hasActiveProgress ? 'pb-28' : ''}`}>
            <AnimatedContainer>
            <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                <div>
                    <h1 className="text-3xl font-bold tracking-tight">Transcrições</h1>
                    <p className="text-muted-foreground">
                        Dashboard de jobs para acompanhar múltiplas transcrições em paralelo e abrir o preview/auditoria por job.
                    </p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                    <Button onClick={() => setSettingsOpen(true)}>
                        <Plus className="mr-2 h-4 w-4" />
                        Nova transcrição
                    </Button>
                    <Button
                        variant="outline"
                        onClick={() => loadJobHistory()}
                        disabled={jobsLoading}
                    >
                        <RefreshCw className={`mr-2 h-4 w-4 ${jobsLoading ? 'animate-spin' : ''}`} />
                        Atualizar
                    </Button>
                    <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => setSettingsOpen(true)}
                        title="Configurações"
                    >
                        <SlidersHorizontal className="h-5 w-5" />
                    </Button>
                </div>
            </div>
            </AnimatedContainer>

            <Tabs value={mainTab} onValueChange={(value) => setMainTab(value as typeof mainTab)} className="flex-1">
                <TabsList className="w-full justify-start">
                    <TabsTrigger value="jobs">Transcription Jobs</TabsTrigger>
                    <TabsTrigger value="preview">Resultado</TabsTrigger>
                </TabsList>

                <TabsContent value="jobs" className="mt-4">
                    {/* Dashboard de Jobs */}
                    <Card className="flex flex-col min-h-[700px]">
                    <CardHeader className="flex flex-row items-start justify-between gap-4 space-y-0">
                        <div className="space-y-1">
                            <CardTitle>Transcription Jobs</CardTitle>
                            <CardDescription>Filtre, selecione e abra jobs (em andamento ou concluídos).</CardDescription>
                        </div>
                        <div className="flex items-center gap-2">
                            <label className="flex items-center gap-2 text-xs text-muted-foreground">
                                <input
                                    ref={jobsSelectAllRef}
                                    type="checkbox"
                                    className="h-3.5 w-3.5 rounded border border-input"
                                    checked={allJobsSelected}
                                    disabled={deletableJobIds.length === 0}
                                    onChange={(e) => handleSelectAllJobs(e.target.checked)}
                                />
                                Selecionar
                            </label>
                            <Button
                                variant="outline"
                                size="sm"
                                onClick={() => handleDeleteSelectedJobs()}
                                disabled={selectedJobIds.size === 0}
                            >
                                <Trash2 className="mr-2 h-4 w-4" />
                                Excluir
                            </Button>
                        </div>
                    </CardHeader>
                    <CardContent className="flex-1 overflow-hidden">
                        <Tabs defaultValue="jobs" className="flex h-full flex-col">
                            <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                                <TabsList className="w-full md:w-auto">
                                    <TabsTrigger value="jobs">Jobs</TabsTrigger>
                                    <TabsTrigger value="saved">Arquivos salvos</TabsTrigger>
                                </TabsList>
                                {activeJobId ? (
                                    <div className="text-xs text-muted-foreground">
                                        Selecionado: <span className="font-mono">{activeJobId}</span>
                                    </div>
                                ) : (
                                    <div className="text-xs text-muted-foreground">
                                        Selecione um job para abrir no preview.
                                    </div>
                                )}
                            </div>

                            <TabsContent value="jobs" className="mt-4 flex-1 overflow-hidden">
                                <div className="grid gap-2 md:grid-cols-12">
                                    <div className="relative md:col-span-6">
                                        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                                        <Input
                                            value={jobsSearch}
                                            onChange={(e) => setJobsSearch(e.target.value)}
                                            placeholder="Buscar por arquivo, caso ou ID..."
                                            className="pl-9"
                                        />
                                    </div>
                                    <div className="md:col-span-3">
                                        <select
                                            className="flex h-10 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
                                            value={jobsStatusFilter}
                                            onChange={(e) => setJobsStatusFilter(e.target.value as any)}
                                        >
                                            <option value="all">Todos status</option>
                                            <option value="running">Em andamento</option>
                                            <option value="queued">Na fila</option>
                                            <option value="completed">Concluído</option>
                                            <option value="error">Erro</option>
                                            <option value="canceled">Cancelado</option>
                                        </select>
                                    </div>
                                    <div className="md:col-span-3">
                                        <select
                                            className="flex h-10 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
                                            value={jobsTypeFilter}
                                            onChange={(e) => setJobsTypeFilter(e.target.value as any)}
                                        >
                                            <option value="all">Todos tipos</option>
                                            <option value="transcription">Aula/Apostila</option>
                                            <option value="hearing">Audiência/Reunião</option>
                                        </select>
                                    </div>
                                    <div className="md:col-span-3">
                                        <Input
                                            type="date"
                                            value={jobsFromDate}
                                            onChange={(e) => setJobsFromDate(e.target.value)}
                                            placeholder="De"
                                        />
                                    </div>
                                    <div className="md:col-span-3">
                                        <Input
                                            type="date"
                                            value={jobsToDate}
                                            onChange={(e) => setJobsToDate(e.target.value)}
                                            placeholder="Até"
                                        />
                                    </div>
                                    <div className="md:col-span-6 flex items-center justify-end gap-2">
                                        <Button
                                            variant="ghost"
                                            size="sm"
                                            onClick={() => {
                                                setJobsSearch('');
                                                setJobsStatusFilter('all');
                                                setJobsTypeFilter('all');
                                                setJobsFromDate('');
                                                setJobsToDate('');
                                            }}
                                        >
                                            Limpar filtros
                                        </Button>
                                    </div>
                                </div>

                                <div className="mt-4 h-full overflow-auto rounded-md border">
                                    <div className="grid grid-cols-[28px_minmax(220px,1fr)_140px_140px_160px_160px_220px] gap-3 border-b bg-muted/40 px-3 py-2 text-xs font-medium text-muted-foreground">
                                        <div />
                                        <div>Arquivo/Caso</div>
                                        <div>Tipo</div>
                                        <div>Perfil</div>
                                        <div>Status</div>
                                        <div>Atualizado</div>
                                        <div className="text-right">Ações</div>
                                    </div>
                                    {jobsLoading ? (
                                        <div className="p-4 text-sm text-muted-foreground">Carregando jobs...</div>
                                    ) : filteredJobHistory.length === 0 ? (
                                        <div className="p-6 text-sm text-muted-foreground">Nenhum job encontrado com os filtros atuais.</div>
                                    ) : (
                                        filteredJobHistory.map((job: any) => {
                                            const type = String(job?.job_type || '').toLowerCase();
                                            const isH = type === 'hearing';
                                            const title = isH
                                                ? `Caso ${job?.config?.case_id || '—'}`
                                                : (job?.file_names || []).join(', ') || job?.job_id;
                                            const profile = isH ? (job?.config?.format_mode || '—') : (job?.config?.mode || '—');
                                            const status = String(job?.status || '');
                                            const canLoad = status === 'completed';
                                            const canResume = status === 'running' || status === 'queued';
                                            const canDelete = !canResume;
                                            const isSelected = Boolean(activeJobId && activeJobId === job?.job_id);
                                            const statusVariant = status === 'completed' ? 'default' : status === 'error' ? 'destructive' : 'secondary';

                                            return (
                                                <div
                                                    key={job.job_id}
                                                    className={`grid grid-cols-[28px_minmax(220px,1fr)_140px_140px_160px_160px_220px] gap-3 px-3 py-3 text-sm border-b last:border-b-0 ${isSelected ? 'bg-primary/5' : 'bg-background'}`}
                                                >
                                                    <div className="pt-0.5">
                                                        <input
                                                            type="checkbox"
                                                            className="h-3.5 w-3.5 rounded border border-input"
                                                            checked={selectedJobIds.has(job.job_id)}
                                                            disabled={!canDelete}
                                                            onChange={(e) => toggleJobSelection(job.job_id, e.target.checked)}
                                                            title={canDelete ? 'Selecionar job' : 'Job em execução'}
                                                        />
                                                    </div>
                                                    <button
                                                        type="button"
                                                        className="min-w-0 text-left"
                                                        onClick={() => setActiveJobId(job.job_id)}
                                                        title={title}
                                                    >
                                                        <div className="truncate font-medium">{title}</div>
                                                        <div className="truncate text-xs text-muted-foreground font-mono">{job.job_id}</div>
                                                    </button>
                                                    <div className="text-xs text-muted-foreground pt-0.5">
                                                        {isH ? 'Audiência' : 'Transcrição'}
                                                    </div>
                                                    <div className="text-xs text-muted-foreground pt-0.5 truncate" title={String(profile)}>
                                                        {String(profile)}
                                                    </div>
                                                    <div className="pt-0.5">
                                                        <div className="flex items-center gap-2">
                                                            <Badge variant={statusVariant as any}>{status}</Badge>
                                                            {typeof job.progress === 'number' ? (
                                                                <span className="text-xs text-muted-foreground">{job.progress}%</span>
                                                            ) : null}
                                                        </div>
                                                    </div>
                                                    <div className="text-xs text-muted-foreground pt-0.5">
                                                        {formatJobTime(job.updated_at || job.created_at)}
                                                    </div>
                                                    <div className="flex items-center justify-end gap-2">
                                                        {canLoad ? (
                                                            <Button
                                                                size="sm"
                                                                variant="secondary"
                                                                onClick={async () => {
                                                                    await handleLoadJobResult(job.job_id);
                                                                    setMainTab('preview');
                                                                }}
                                                            >
                                                                Abrir
                                                            </Button>
                                                        ) : null}
                                                        {canResume ? (
                                                            <Button size="sm" variant="outline" onClick={() => handleResumeJob(job.job_id)}>
                                                                Acompanhar
                                                            </Button>
                                                        ) : null}
                                                        {canResume ? (
                                                            <Button size="sm" variant="destructive" onClick={() => handleCancelJob(job.job_id)}>
                                                                Interromper
                                                            </Button>
                                                        ) : null}
                                                        <Button
                                                            size="icon"
                                                            variant="ghost"
                                                            className="h-8 w-8 text-destructive"
                                                            onClick={() => handleDeleteJob(job.job_id)}
                                                            disabled={!canDelete}
                                                            title={canDelete ? 'Excluir job' : 'Job em execução'}
                                                        >
                                                            <Trash2 className="h-4 w-4" />
                                                        </Button>
                                                    </div>
                                                </div>
                                            );
                                        })
                                    )}
                                </div>
                            </TabsContent>

                            <TabsContent value="saved" className="mt-4 flex-1 overflow-hidden">
                                <div className="grid gap-2 md:grid-cols-12">
                                    <div className="relative md:col-span-8">
                                        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                                        <Input
                                            value={savedDocsSearch}
                                            onChange={(e) => setSavedDocsSearch(e.target.value)}
                                            placeholder="Buscar por nome..."
                                            className="pl-9"
                                        />
                                    </div>
                                    <div className="md:col-span-4 flex items-center justify-end gap-2">
                                        <Button
                                            variant="outline"
                                            size="sm"
                                            onClick={loadSavedDocuments}
                                            disabled={savedDocsLoading}
                                        >
                                            <RefreshCw className={`mr-2 h-4 w-4 ${savedDocsLoading ? 'animate-spin' : ''}`} />
                                            Atualizar
                                        </Button>
                                        <label className="flex items-center gap-2 text-xs text-muted-foreground">
                                            <input
                                                ref={savedDocsSelectAllRef}
                                                type="checkbox"
                                                className="h-3.5 w-3.5 rounded border border-input"
                                                checked={allDocsSelected}
                                                disabled={selectableSavedDocIds.length === 0}
                                                onChange={(e) => handleSelectAllSavedDocs(e.target.checked)}
                                            />
                                            Selecionar
                                        </label>
                                        <Button
                                            variant="outline"
                                            size="sm"
                                            onClick={() => handleDeleteSelectedSavedDocuments()}
                                            disabled={selectedSavedDocIds.size === 0}
                                        >
                                            <Trash2 className="mr-2 h-4 w-4" />
                                            Excluir
                                        </Button>
                                    </div>
                                </div>

                                <div className="mt-4 h-full overflow-auto rounded-md border">
                                    <div className="grid grid-cols-[28px_minmax(220px,1fr)_180px_220px] gap-3 border-b bg-muted/40 px-3 py-2 text-xs font-medium text-muted-foreground">
                                        <div />
                                        <div>Nome</div>
                                        <div>Criado</div>
                                        <div className="text-right">Ações</div>
                                    </div>
                                    {savedDocsLoading ? (
                                        <div className="p-4 text-sm text-muted-foreground">Carregando...</div>
                                    ) : filteredSavedDocuments.length === 0 ? (
                                        <div className="p-6 text-sm text-muted-foreground">Nenhum arquivo salvo encontrado.</div>
                                    ) : (
                                        filteredSavedDocuments.map((doc: any) => {
                                            const docId = resolveSavedDocumentId(doc);
                                            const canSelect = Boolean(docId);
                                            return (
                                                <div
                                                    key={docId || `${doc?.name || 'documento'}-${doc?.created_at || ''}`}
                                                    className="grid grid-cols-[28px_minmax(220px,1fr)_180px_220px] gap-3 px-3 py-3 text-sm border-b last:border-b-0"
                                                >
                                                    <div className="pt-0.5">
                                                        <input
                                                            type="checkbox"
                                                            className="h-3.5 w-3.5 rounded border border-input"
                                                            checked={docId ? selectedSavedDocIds.has(docId) : false}
                                                            disabled={!canSelect}
                                                            onChange={(e) => docId && toggleSavedDocSelection(docId, e.target.checked)}
                                                        />
                                                    </div>
                                                    <div className="min-w-0">
                                                        <div className="truncate font-medium" title={doc?.name}>{doc?.name || 'Documento'}</div>
                                                        <div className="truncate text-xs text-muted-foreground font-mono">{docId || '—'}</div>
                                                    </div>
                                                    <div className="text-xs text-muted-foreground pt-0.5">
                                                        {formatJobTime(doc?.created_at)}
                                                    </div>
                                                    <div className="flex items-center justify-end gap-2">
                                                        <Button
                                                            size="sm"
                                                            variant="outline"
                                                            onClick={() => (window.location.href = '/documents')}
                                                        >
                                                            Abrir
                                                        </Button>
                                                        <Button
                                                            size="icon"
                                                            variant="ghost"
                                                            className="h-8 w-8 text-destructive"
                                                            onClick={() => handleDeleteSavedDocument(doc)}
                                                            disabled={!canSelect}
                                                            title={canSelect ? 'Excluir documento' : 'ID indisponível'}
                                                        >
                                                            <Trash2 className="h-4 w-4" />
                                                        </Button>
                                                    </div>
                                                </div>
                                            );
                                        })
                                    )}
                                </div>
                            </TabsContent>
                        </Tabs>
                    </CardContent>
                </Card>
                </TabsContent>

                <Dialog open={settingsOpen} onOpenChange={setSettingsOpen}>
                    <DialogContent className="fixed right-0 top-0 left-auto h-[100vh] w-full max-w-xl translate-x-0 translate-y-0 rounded-none p-0">
                        <Card className="h-full rounded-none border-0 shadow-none">
                            <CardHeader className="flex flex-row items-start justify-between gap-4 space-y-0 border-b">
                                <div className="space-y-1">
                                    <CardTitle>Nova transcrição</CardTitle>
                                    <CardDescription>Configure arquivos e parâmetros do job.</CardDescription>
                                </div>
                                <div className="flex items-center gap-2 pt-1">
                                    <Label htmlFor="follow-job-live" className="text-xs text-muted-foreground">
                                        Acompanhar ao vivo
                                    </Label>
                                    <Switch
                                        id="follow-job-live"
                                        checked={followJobLive}
                                        onCheckedChange={setFollowJobLive}
                                    />
                                </div>
                            </CardHeader>
                            <CardContent className="h-[calc(100vh-92px)] overflow-y-auto p-6 space-y-4">
                        <div className="space-y-2">
                            <Label>Tipo de Transcrição</Label>
                            <select
                                className="flex h-10 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                                value={transcriptionType}
                                onChange={(e) => {
                                    const value = e.target.value as 'apostila' | 'hearing';
                                    setTranscriptionType(value);
                                    setResult(null);
                                    clearRichContent();
                                    setReport(null);
                                    setHearingPayload(null);
                                    setHearingTranscript(null);
                                    setHearingFormatted(null);
                                    setAuditIssues([]);
                                }}
                            >
                                <option value="apostila">📚 Aula / Apostila</option>
                                <option value="hearing">⚖️ Audiência / Reunião</option>
                            </select>
                        </div>

	                        {/* Upload */}
	                        <div className="space-y-2">
	                            <Label>Arquivos (Áudio/Vídeo/Texto)</Label>
                            <div
                                className={`relative flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed p-4 text-center transition-colors ${isDragActive ? 'border-primary bg-primary/5' : 'border-muted-foreground/25'}`}
                                onDragOver={handleDragOver}
                                onDragLeave={handleDragLeave}
                                onDrop={handleDrop}
                            >
                                <input
                                    ref={fileInputRef}
                                    id="file-upload"
                                    type="file"
                                    multiple
                                    className="absolute inset-0 h-full w-full cursor-pointer opacity-0"
                                    accept="audio/*,video/*,.mp3,.wav,.m4a,.aac,.mp4,.mov,.mkv,.txt,.md"
                                    onClick={(e) => {
                                        (e.currentTarget as HTMLInputElement).value = '';
                                    }}
                                    onChange={handleFilesChange}
                                />
                                <Upload className="h-5 w-5 text-muted-foreground" />
                                <div className="text-sm font-medium">
                                    Arraste e solte aqui ou clique para selecionar
                                </div>
                                <div className="text-xs text-muted-foreground">
                                    Áudio/Vídeo/Texto (mp3, wav, m4a, mp4, mov, mkv, txt, md)
                                </div>
                            </div>
	                            {files.length > 0 && (
                                <div className="space-y-1 mt-2 max-h-40 overflow-y-auto">
                                    {files.map((file, idx) => (
                                        <div key={idx} className="flex items-center gap-1 text-xs bg-muted/50 rounded px-2 py-1">
                                            <span className="font-mono text-muted-foreground w-5">{idx + 1}.</span>
                                            {file.type.startsWith('video')
                                                ? <FileVideo className="h-3 w-3 flex-shrink-0" />
                                                : isTextFile(file)
                                                    ? <FileText className="h-3 w-3 flex-shrink-0" />
                                                    : <FileAudio className="h-3 w-3 flex-shrink-0" />
                                            }
                                            <span className="truncate flex-1" title={file.name}>{file.name}</span>
                                            <span className="text-muted-foreground flex-shrink-0">{(file.size / (1024 * 1024)).toFixed(1)}MB</span>
                                            <Button variant="ghost" size="icon" className="h-5 w-5" onClick={() => moveFileUp(idx)} disabled={idx === 0}>
                                                <ChevronUp className="h-3 w-3" />
                                            </Button>
                                            <Button variant="ghost" size="icon" className="h-5 w-5" onClick={() => moveFileDown(idx)} disabled={idx === files.length - 1}>
                                                <ChevronDown className="h-3 w-3" />
                                            </Button>
                                            <Button variant="ghost" size="icon" className="h-5 w-5 text-destructive" onClick={() => removeFile(idx)}>
                                                <X className="h-3 w-3" />
                                            </Button>
                                        </div>
                                    ))}
                                    <p className="text-xs text-muted-foreground mt-1">
                                        {files.length > 1 ? `📚 ${files.length} arquivos serão unificados na ordem acima` : ''}
                                    </p>
                                </div>
	                            )}
	                        </div>

                            <div className="space-y-2">
                                <Label>OU URL pública (YouTube)</Label>
                                <input
                                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                                    placeholder="https://www.youtube.com/watch?v=..."
                                    value={publicUrl}
                                    onChange={(e) => {
                                        const value = e.target.value;
                                        setPublicUrl(value);
                                        if (value.trim()) {
                                            setFiles([]);
                                        }
                                    }}
                                />
                                <p className="text-xs text-muted-foreground">
                                    Dica: por segurança, o backend aceita apenas hosts permitidos (default: youtube.com, youtu.be).
                                </p>
                            </div>
	
                        <div className="border-t border-border" />

                        {!isHearing && (
                            <div className="space-y-2">
                                <Label>Tema visual do documento</Label>
                                <select
                                    className="flex h-10 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                                    value={documentTheme}
                                    onChange={(e) => setDocumentTheme(e.target.value)}
                                >
                                    {DOCUMENT_THEMES.map((theme) => (
                                        <option key={theme.id} value={theme.id}>
                                            {theme.title}
                                        </option>
                                    ))}
                                </select>
                                <p className="text-xs text-muted-foreground">
                                    {DOCUMENT_THEMES.find((t) => t.id === documentTheme)?.description
                                        || 'Defina o estilo visual do preview (especialmente tabelas).'}
                                </p>
                            </div>
                        )}

                        {isHearing && (
                            <div className="space-y-2">
                                <Label>Tema visual do documento</Label>
                                <select
                                    className="flex h-10 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                                    value={hearingDocumentTheme}
                                    onChange={(e) => setHearingDocumentTheme(e.target.value)}
                                >
                                    {DOCUMENT_THEMES.map((theme) => (
                                        <option key={theme.id} value={theme.id}>
                                            {theme.title}
                                        </option>
                                    ))}
                                </select>
                                <p className="text-xs text-muted-foreground">
                                    {DOCUMENT_THEMES.find((t) => t.id === hearingDocumentTheme)?.description
                                        || 'Defina o estilo visual do preview (especialmente tabelas).'}
                                </p>
                            </div>
                        )}

                        <div className="border-t border-border" />

                        {!isHearing && (
                            <div className="space-y-2">
                                <Label>Modo de Formatação</Label>
                                <select
                                    className="flex h-10 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                                    value={mode}
                                    onChange={(e) => setMode(e.target.value)}
                                >
                                    <option value="APOSTILA">📚 Apostila (Didático)</option>
                                    <option value="FIDELIDADE">🎯 Fidelidade (Literal)</option>
                                    <option value="RAW">📝 Raw (Apenas Transcrição)</option>
                                </select>
                            </div>
                        )}

                        {isHearing && (
                            <div className="space-y-4">
                                <div className="space-y-2">
                                    <Label>Número do processo/caso</Label>
                                    <input
                                        className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                                        placeholder="ex: 0001234-56.2024.8.26.0001"
                                        value={hearingCaseId}
                                        onChange={(e) => setHearingCaseId(e.target.value)}
                                    />
                                </div>
                                <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                                    <div className="space-y-2">
                                        <Label>Vara/Tribunal</Label>
                                        <input
                                            className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                                            placeholder="Ex: 3ª Vara Cível"
                                            value={hearingCourt}
                                            onChange={(e) => setHearingCourt(e.target.value)}
                                        />
                                    </div>
                                    <div className="space-y-2">
                                        <Label>Comarca/Cidade</Label>
                                        <input
                                            className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                                            placeholder="Ex: São Paulo"
                                            value={hearingCity}
                                            onChange={(e) => setHearingCity(e.target.value)}
                                        />
                                    </div>
                                </div>
                                <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                                    <div className="space-y-2">
                                        <Label>Data da audiência</Label>
                                        <input
                                            type="date"
                                            className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                                            value={hearingDate}
                                            onChange={(e) => setHearingDate(e.target.value)}
                                        />
                                    </div>
                                    <div className="space-y-2">
                                        <Label>Observações</Label>
                                        <input
                                            className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                                            placeholder="Ex: audiência de instrução"
                                            value={hearingNotes}
                                            onChange={(e) => setHearingNotes(e.target.value)}
                                        />
                                    </div>
                                </div>
                                <div className="space-y-2">
                                    <Label>Objetivo jurídico</Label>
                                    <select
                                        className="flex h-10 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm"
                                        value={hearingGoal}
                                        onChange={(e) => setHearingGoal(e.target.value)}
                                    >
                                        <option value="peticao_inicial">Petição inicial</option>
                                        <option value="contestacao">Contestação</option>
                                        <option value="alegacoes_finais">Alegações finais</option>
                                        <option value="sentenca">Sentença</option>
                                    </select>
                                </div>
                                <div className="space-y-2">
                                    <Label>Modo de formatação (opcional)</Label>
                                    <select
                                        className="flex h-10 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm"
                                        value={hearingFormatMode}
                                        onChange={(e) => {
                                            const value = e.target.value as typeof hearingFormatMode;
                                            setHearingFormatMode(value);
                                            if (value === 'none') {
                                                setHearingUseCustomPrompt(false);
                                                setHearingAllowIndirect(false);
                                                setHearingAllowSummary(false);
                                            }
                                        }}
                                    >
                                        <option value="audiencia">Audiência (padrão)</option>
                                        <option value="reuniao">Reunião</option>
                                        <option value="depoimento">Depoimento</option>
                                        <option value="none">Sem formatação</option>
                                    </select>
                                    {hearingFormatMode !== 'none' && (
                                        <div className="space-y-2">
                                            <div className="flex items-center justify-between space-x-2 border p-3 rounded-md">
                                                <Label htmlFor="hearing-indirect" className="flex flex-col space-y-1">
                                                    <span>Permitir discurso indireto</span>
                                                    <span className="font-normal text-xs text-muted-foreground">
                                                        Reescreve falas em estilo indireto (ata).
                                                    </span>
                                                </Label>
                                                <Switch
                                                    id="hearing-indirect"
                                                    checked={hearingAllowIndirect}
                                                    onCheckedChange={setHearingAllowIndirect}
                                                />
                                            </div>
                                            <div className="flex items-center justify-between space-x-2 border p-3 rounded-md">
                                                <Label htmlFor="hearing-summary" className="flex flex-col space-y-1">
                                                    <span>Permitir ata resumida</span>
                                                    <span className="font-normal text-xs text-muted-foreground">
                                                        Condensa falas mantendo decisões e encaminhamentos.
                                                    </span>
                                                </Label>
                                                <Switch
                                                    id="hearing-summary"
                                                    checked={hearingAllowSummary}
                                                    onCheckedChange={setHearingAllowSummary}
                                                />
                                            </div>
                                            <div className="flex items-center justify-between space-x-2 border p-3 rounded-md">
                                                <Label htmlFor="hearing-timestamps" className="flex flex-col space-y-1">
                                                    <span>Incluir timestamps no resultado</span>
                                                    <span className="font-normal text-xs text-muted-foreground">
                                                        Controla timestamps apenas no texto formatado/preview; o RAW mantém timestamps para navegação e auditoria.
                                                    </span>
                                                </Label>
                                                <Switch
                                                    id="hearing-timestamps"
                                                    checked={hearingIncludeTimestamps}
                                                    onCheckedChange={setHearingIncludeTimestamps}
                                                />
                                            </div>
                                        </div>
                                    )}
                                    <div className="flex items-center justify-between space-x-2 border p-3 rounded-md">
                                        <Label htmlFor="hearing-custom-prompt" className="flex flex-col space-y-1">
                                            <span className="flex items-center gap-2">
                                                Prompt personalizado
                                                <SettingInfoPopover>
                                                    <div className="space-y-3">
                                                        <div className="font-semibold">O que pode ser customizado</div>
                                                        {hearingFormatMode === 'audiencia' || hearingFormatMode === 'reuniao' ? (
                                                            <div>
                                                                Este campo é usado para <span className="font-medium">TABELAS/EXTRAS</span> (ex.: tabela de decisões/encaminhamentos,
                                                                checklist, resumo final), sem alterar tom/estrutura do modo.
                                                            </div>
                                                        ) : (
                                                            <div>
                                                                Este campo substitui a camada de <span className="font-medium">estilo/tabelas</span> do modo selecionado (use com cuidado).
                                                            </div>
                                                        )}

                                                        <div className="font-semibold">Exemplos rápidos</div>
                                                        <div className="flex flex-wrap gap-2">
                                                            {hearingFormatMode === 'audiencia' &&
                                                                PROMPT_SNIPPETS.hearingAudiencia.map((s) => (
                                                                    <Button
                                                                        key={s.id}
                                                                        type="button"
                                                                        variant="outline"
                                                                        size="sm"
                                                                        className="h-7 px-2 text-[11px]"
                                                                        onClick={() => appendHearingCustomPromptSnippet(s.template)}
                                                                    >
                                                                        {s.title}
                                                                    </Button>
                                                                ))}
                                                            {hearingFormatMode === 'reuniao' &&
                                                                PROMPT_SNIPPETS.hearingReuniao.map((s) => (
                                                                    <Button
                                                                        key={s.id}
                                                                        type="button"
                                                                        variant="outline"
                                                                        size="sm"
                                                                        className="h-7 px-2 text-[11px]"
                                                                        onClick={() => appendHearingCustomPromptSnippet(s.template)}
                                                                    >
                                                                        {s.title}
                                                                    </Button>
                                                                ))}
                                                            {hearingFormatMode === 'depoimento' &&
                                                                PROMPT_SNIPPETS.depoimento.map((s) => (
                                                                    <Button
                                                                        key={s.id}
                                                                        type="button"
                                                                        variant="outline"
                                                                        size="sm"
                                                                        className="h-7 px-2 text-[11px]"
                                                                        onClick={() => appendHearingCustomPromptSnippet(s.template)}
                                                                    >
                                                                        {s.title}
                                                                    </Button>
                                                                ))}
                                                        </div>

                                                        <div className="text-muted-foreground">
                                                            Dica: evite usar <span className="font-mono">##</span> ou <span className="font-mono">###</span> aqui; se precisar de um anexo,
                                                            prefira <span className="font-mono">####</span>.
                                                        </div>
                                                    </div>
                                                </SettingInfoPopover>
                                            </span>
                                            <span className="font-normal text-xs text-muted-foreground">
                                                {hearingFormatMode === 'audiencia' || hearingFormatMode === 'reuniao'
                                                    ? 'Personaliza apenas tabelas/extras do modo selecionado.'
                                                    : 'Substitui estilo/tabelas do modo selecionado.'}
                                            </span>
                                        </Label>
                                        <Switch
                                            id="hearing-custom-prompt"
                                            checked={hearingUseCustomPrompt}
                                            onCheckedChange={setHearingUseCustomPrompt}
                                            disabled={hearingFormatMode === 'none'}
                                        />
                                    </div>
                                    {hearingUseCustomPrompt && hearingFormatMode !== 'none' && (
                                        <div className="space-y-2">
                                            {(hearingFormatMode === 'audiencia' || hearingFormatMode === 'reuniao') && (
                                                <div className="flex flex-wrap gap-2">
                                                    {(hearingFormatMode === 'audiencia'
                                                        ? PROMPT_SNIPPETS.hearingAudiencia
                                                        : PROMPT_SNIPPETS.hearingReuniao
                                                    ).map((s) => (
                                                        <Button
                                                            key={s.id}
                                                            type="button"
                                                            variant="outline"
                                                            size="sm"
                                                            className="h-7 px-2 text-[11px]"
                                                            onClick={() => appendHearingCustomPromptSnippet(s.template)}
                                                        >
                                                            {s.title}
                                                        </Button>
                                                    ))}
                                                </div>
                                            )}
                                            <textarea
                                                className="flex min-h-[90px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm resize-none"
                                                placeholder={
                                                    hearingFormatMode === 'audiencia' || hearingFormatMode === 'reuniao'
                                                        ? 'Personalize apenas tabelas/extras (ex.: checklist, colunas, anexos após o fechamento)...'
                                                        : 'Insira instruções de estilo/tabela para o texto formatado...'
                                                }
                                                value={hearingCustomPrompt}
                                                onChange={(e) => setHearingCustomPrompt(e.target.value)}
                                            />
                                        </div>
                                    )}
                                </div>
                                <div className="border rounded-md p-3 space-y-3">
                                    <div className="flex items-center gap-2 text-sm font-medium">
                                        <Users className="h-4 w-4" /> Enrollment de voz (opcional)
                                    </div>
                                    <div className="space-y-2">
                                        <Label>Nome do falante</Label>
                                        <input
                                            className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                                            value={enrollName}
                                            onChange={(e) => setEnrollName(e.target.value)}
                                            placeholder="Ex: Juiz Fulano"
                                        />
                                    </div>
                                    <div className="space-y-2">
                                        <Label>Papel</Label>
                                        <select
                                            className="flex h-9 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm"
                                            value={enrollRole}
                                            onChange={(e) => setEnrollRole(e.target.value)}
                                        >
                                            {hearingRoles.map(role => (
                                                <option key={role} value={role}>{role}</option>
                                            ))}
                                        </select>
                                    </div>
                                    <div className="space-y-2">
                                        <Label>Áudio (10-30s)</Label>
                                        <input
                                            type="file"
                                            accept="audio/*,.mp3,.wav,.m4a,.aac"
                                            onChange={(e) => setEnrollFile(e.target.files?.[0] || null)}
                                        />
                                    </div>
                                    <Button variant="secondary" onClick={handleEnrollSpeaker} disabled={isEnrolling}>
                                        {isEnrolling ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Gavel className="mr-2 h-4 w-4" />}
                                        Cadastrar voz
                                    </Button>
                                </div>
	                            </div>
	                        )}
	                        <Accordion type="single" collapsible className="rounded-md border">
	                            <AccordionItem value="advanced" className="border-b-0">
	                                <AccordionTrigger className="px-3 py-3 text-sm">
	                                    Configurações avançadas
	                                </AccordionTrigger>
	                                <AccordionContent className="px-3 pt-0 pb-3">
	                                    <div className="space-y-4">
	
	                                        {/* High Accuracy Switch */}
	                        <div className="flex items-center justify-between space-x-2 border p-3 rounded-md">
	                            <Label htmlFor="high-accuracy" className="flex flex-col space-y-1">
	                                <span>Alta Precisão (Beam Search)</span>
	                                <span className="font-normal text-xs text-muted-foreground">
	                                    Mais lento, mas ideal para termos jurídicos complexos.
                                </span>
                            </Label>
                            <Switch
                                id="high-accuracy"
                                checked={highAccuracy}
                                onCheckedChange={setHighAccuracy}
                            />
                        </div>

                        {/* Diarization Switch */}
                        <div className="flex items-center justify-between space-x-2 border p-3 rounded-md">
                            <Label htmlFor="diarization" className="flex flex-col space-y-1">
                                <span className="flex items-center gap-2">
                                    Diarização (separar falantes)
                                    <SettingInfoPopover>
                                        <div className="space-y-2">
                                            <div className="font-semibold">O que faz</div>
                                            <div>Detecta troca de falantes e marca o texto por SPEAKER (melhora quando há troca real de professores/participantes).</div>
                                            <div className="font-semibold">Quando usar</div>
                                            <div>✅ Reuniões, audiências e aulas com mais de um professor/falante.</div>
                                            <div className="font-semibold">Importante</div>
                                            <div>Requer Pyannote/Torch no backend e <code>HUGGING_FACE_TOKEN</code>. Ao ativar, o backend pode falhar se a diarização não estiver disponível.</div>
                                            <div className="font-semibold">Padrão</div>
                                            <div>Em audiências/reuniões: sempre ativa. Em apostilas: opcional.</div>
                                        </div>
                                    </SettingInfoPopover>
                                </span>
                                <span className="font-normal text-xs text-muted-foreground">
                                    {isHearing
                                        ? 'Sempre ativo em audiências/reuniões.'
                                        : 'Opcional nas apostilas: ativa apenas quando você ligar.'}
                                </span>
                            </Label>
                            <Switch
                                id="diarization"
                                checked={isHearing ? true : enableDiarization}
                                disabled={isHearing}
                                onCheckedChange={(value) => {
                                    if (isHearing) return;
                                    setEnableDiarization(value);
                                }}
                            />
                        </div>

                        <>
                            <div className="flex items-center justify-between space-x-2 border p-3 rounded-md">
                                <Label htmlFor="use-raw-cache" className="flex flex-col space-y-1">
                                    <span className="flex items-center gap-2">
                                        Usar cache RAW
                                        <SettingInfoPopover>
                                            <div className="space-y-2">
                                                <div className="font-semibold">Recomendação</div>
                                                <div>✅ Manter ligado (padrão).</div>
                                                <div className="font-semibold">O que faz</div>
                                                <div>Reaproveita a transcrição bruta (RAW) já gerada anteriormente para este mesmo arquivo. Isso acelera reprocessamentos e reduz custo.</div>
                                                <div className="font-semibold">Quando desligar</div>
                                                <div>Quando você quiser forçar uma nova transcrição do zero (por exemplo, se mudou a configuração de precisão ou acha que a transcrição bruta anterior ficou ruim).</div>
                                            </div>
                                        </SettingInfoPopover>
                                    </span>
                                    <span className="font-normal text-xs text-muted-foreground">
                                        Reaproveita transcrições brutas anteriores do mesmo arquivo.
                                    </span>
                                </Label>
                                <Switch
                                    id="use-raw-cache"
                                    checked={useRawCache}
                                    onCheckedChange={setUseRawCache}
                                />
                            </div>

                            <div className="flex items-center justify-between space-x-2 border p-3 rounded-md">
                                <Label htmlFor="auto-apply-fixes" className="flex flex-col space-y-1">
                                    <span className="flex items-center gap-2">
                                        Auto-aplicar correções estruturais
                                        <SettingInfoPopover>
                                            <div className="space-y-2">
                                                <div className="font-semibold">Recomendação</div>
                                                <div>✅ Manter ligado (padrão).</div>
                                                <div className="font-semibold">O que faz</div>
                                                <div>Corrige automaticamente problemas &quot;de forma&quot; (ex.: seções duplicadas, títulos fora de ordem, numeração de tópicos), sem mexer no conteúdo jurídico em si.</div>
                                                <div className="font-semibold">Importante</div>
                                                <div>Correções de conteúdo por IA continuam exigindo aprovação do usuário no HIL, a menos que a opção abaixo esteja ativada.</div>
                                            </div>
                                        </SettingInfoPopover>
                                    </span>
                                    <span className="font-normal text-xs text-muted-foreground">
                                        Aplica automaticamente as correções do auto_fix_apostilas após a auditoria.
                                    </span>
                                </Label>
                                <Switch
                                    id="auto-apply-fixes"
                                    checked={autoApplyFixes}
                                    onCheckedChange={setAutoApplyFixes}
                                    disabled={isRawMode}
                                />
                            </div>

                            <div className="flex items-center justify-between space-x-2 border p-3 rounded-md">
                                <Label htmlFor="auto-apply-content-fixes" className="flex flex-col space-y-1">
                                    <span className="flex items-center gap-2">
                                        Auto-aplicar correções de conteúdo (IA)
                                        <SettingInfoPopover>
                                            <div className="space-y-2">
                                                <div className="font-semibold">Recomendação</div>
                                                <div>⚠️ Manter desligado por padrão.</div>
                                                <div className="font-semibold">O que faz</div>
                                                <div>Aplica automaticamente correções de conteúdo identificadas pela auditoria usando IA (ex.: inserir leis/súmulas omitidas, corrigir citações incompletas).</div>
                                                <div className="font-semibold">Importante</div>
                                                <div>Requer transcrição RAW disponível. Sem RAW, correções de conteúdo são sempre ignoradas.</div>
                                                <div className="font-semibold">Quando usar</div>
                                                <div>Quando você confia na qualidade da auditoria e quer acelerar o processamento, evitando aprovações manuais no HIL.</div>
                                            </div>
                                        </SettingInfoPopover>
                                    </span>
                                    <span className="font-normal text-xs text-muted-foreground">
                                        Aplica automaticamente correções de conteúdo via IA (requer RAW). Use com cautela.
                                    </span>
                                </Label>
                                <Switch
                                    id="auto-apply-content-fixes"
                                    checked={autoApplyContentFixes}
                                    onCheckedChange={setAutoApplyContentFixes}
                                    disabled={isRawMode}
                                />
                            </div>

                            <div className="flex items-center justify-between space-x-2 border p-3 rounded-md">
                                <Label htmlFor="skip-legal-audit" className="flex flex-col space-y-1">
                                    <span className="flex items-center gap-2">
                                        Pular auditoria jurídica (IA)
                                        <SettingInfoPopover>
                                            <div className="space-y-2">
                                                <div className="font-semibold">Recomendação</div>
                                                <div>✅ Manter desligado (padrão).</div>
                                                <div className="font-semibold">O que faz</div>
                                                <div>Desativa a revisão jurídica por IA (ex.: checagem de citações, incoerências, datas suspeitas e problemas técnicos).</div>
                                                <div className="font-semibold">O que continua rodando</div>
                                                <div>A correção estrutural automática e a auditoria preventiva de fidelidade (comparação entre RAW e texto final) continuam.</div>
                                                <div className="font-semibold">Quando usar</div>
                                                <div>Para ganhar tempo/custo em rascunhos rápidos, ou quando você vai revisar juridicamente manualmente depois.</div>
                                            </div>
                                        </SettingInfoPopover>
                                    </span>
                                    <span className="font-normal text-xs text-muted-foreground">
                                        Desativa a auditoria jurídica por IA na formatação. A auditoria estrutural e a validação de fidelidade continuam.
                                    </span>
                                </Label>
                                <Switch
                                    id="skip-legal-audit"
                                    checked={skipLegalAudit}
                                    onCheckedChange={setSkipLegalAudit}
                                />
                            </div>

                            <div className="flex items-center justify-between space-x-2 border p-3 rounded-md">
                                <Label htmlFor="skip-fidelity-audit" className="flex flex-col space-y-1">
                                    <span className="flex items-center gap-2">
                                        Pular auditoria preventiva (fidelidade)
                                        <SettingInfoPopover>
                                            <div className="space-y-2">
                                                <div className="font-semibold">Recomendação</div>
                                                <div>✅ Manter desligado (padrão).</div>
                                                <div className="font-semibold">O que faz</div>
                                                <div>Desativa a comparação entre a transcrição bruta (RAW) e o texto final, usada para detectar omissões, trocas de nomes/autoria, números/datas alterados e possíveis “invenções”.</div>
                                                <div className="font-semibold">Quando usar</div>
                                                <div>Para processamentos muito rápidos/rascunhos, ou quando você não precisa dessa checagem agora.</div>
                                                <div className="font-semibold">Observação</div>
                                                <div>Mesmo ligada, ela só gera alertas e relatórios — não impede baixar o Word.</div>
                                            </div>
                                        </SettingInfoPopover>
                                    </span>
                                    <span className="font-normal text-xs text-muted-foreground">
                                        Desativa o confronto RAW x formatado (inclui autoria integrada) antes do DOCX. Não bloqueia exportação.
                                    </span>
                                </Label>
                                <Switch
                                    id="skip-fidelity-audit"
                                    checked={skipFidelityAudit}
                                    onCheckedChange={setSkipFidelityAudit}
                                    disabled={isRawMode}
                                />
                            </div>
                        </>

                        {/* Thinking Level */}
                        <div className="space-y-2">
                            <Label>Nível de Pensamento (Thinking Budget)</Label>
                            <select
                                className="flex h-10 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                                value={thinkingLevel}
                                onChange={(e) => setThinkingLevel(e.target.value)}
                            >
                                <option value="low">Baixo (Rápido - 8k tokens)</option>
                                <option value="medium">Médio (Padrão - 16k tokens)</option>
                                <option value="high">Alto (Complexo - 32k tokens)</option>
                            </select>
                        </div>

                        {/* Seleção de Modelo */}
                        <div className="space-y-2">
                            <Label>Modelo de IA</Label>
                            <select
                                className="flex h-10 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                                value={selectedModel}
                                onChange={(e) => setSelectedModel(e.target.value)}
                            >
                                <option value="gemini-3-flash-preview">Gemini 3 Flash (Recomendado)</option>
                                <option value="gpt-5-mini">GPT-5 Mini</option>
                            </select>
                        </div>

                        {!isHearing && !isRawMode && (
                            <div className="space-y-2">
                                <Label className="flex items-center gap-2">
                                    Prompt Customizado (Opcional)
                                    <SettingInfoPopover>
                                        <div className="space-y-3">
                                            <div className="font-semibold">O que pode ser customizado</div>
                                            {mode === 'APOSTILA' ? (
                                                <div>
                                                    Em <span className="font-medium">APOSTILA</span>, o campo customiza apenas <span className="font-medium">TABELAS/EXTRAS</span> (quadro-síntese,
                                                    resumo, fluxograma, mapa mental, questionário), sem alterar tom/estilo/estrutura do modo.
                                                </div>
                                            ) : (
                                                <div>
                                                    Em <span className="font-medium">{mode}</span>, o campo substitui a camada de <span className="font-medium">estilo/tabelas</span>. Evite mexer em estrutura.
                                                </div>
                                            )}

                                            <div className="font-semibold">Exemplos rápidos</div>
                                            <div className="flex flex-wrap gap-2">
                                                {(mode === 'APOSTILA'
                                                    ? PROMPT_SNIPPETS.apostila
                                                    : PROMPT_SNIPPETS.fidelity
                                                ).map((s) => (
                                                    <Button
                                                        key={s.id}
                                                        type="button"
                                                        variant="outline"
                                                        size="sm"
                                                        className="h-7 px-2 text-[11px]"
                                                        onClick={() => appendCustomPromptSnippet(s.template)}
                                                    >
                                                        {s.title}
                                                    </Button>
                                                ))}
                                            </div>

                                            <div className="text-muted-foreground">
                                                Dica: evite usar <span className="font-mono">##</span> ou <span className="font-mono">###</span> no custom. Se precisar de anexos, prefira{' '}
                                                <span className="font-mono">####</span>.
                                            </div>
                                        </div>
                                    </SettingInfoPopover>
                                </Label>
                                <p className="text-[10px] text-muted-foreground mt-1 mb-2">
                                    {mode === 'APOSTILA' ? (
                                        <>
                                            Personalize apenas <strong>TABELAS/EXTRAS</strong> (resumo, fluxograma, mapa mental, questionário). O tom e as demais regras do modo são preservados.
                                        </>
                                    ) : (
                                        <>
                                            ⚠️ Nota: Ao customizar, defina apenas <strong>ESTILO e TABELAS</strong>. Evite mexer em estrutura (títulos/ordem). O sistema preserva regras anti-duplicação.
                                        </>
                                    )}
                                </p>
                                {mode === 'APOSTILA' && (
                                    <div className="flex flex-wrap gap-2">
                                        {PROMPT_SNIPPETS.apostila.map((s) => (
                                            <Button
                                                key={s.id}
                                                type="button"
                                                variant="outline"
                                                size="sm"
                                                className="h-7 px-2 text-[11px]"
                                                onClick={() => appendCustomPromptSnippet(s.template)}
                                            >
                                                {s.title}
                                            </Button>
                                        ))}
                                    </div>
                                )}
                                <TranscriptionPromptPicker
                                    onReplace={(tpl) => setCustomPrompt(tpl)}
                                    onAppend={(tpl) => setCustomPrompt((prev) => (prev ? `${prev}\n\n${tpl}` : tpl))}
                                />
                                <textarea
                                    placeholder={
                                        mode === 'APOSTILA'
                                            ? 'Personalize tabelas/extras (ex.: colunas do quadro-síntese, resumo, fluxograma, mapa mental, questionário)...'
                                            : 'Sobrescreva as instruções de estilo/tabelas...'
                                    }
                                    className="flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 resize-none h-32"
                                    value={customPrompt}
                                    onChange={(e) => setCustomPrompt(e.target.value)}
	                                />
	                            </div>
	                        )}
	                                    </div>
	                                </AccordionContent>
	                            </AccordionItem>
	                        </Accordion>
	
	                        <Button
	                            className="w-full"
	                            onClick={handleSubmit}
	                            disabled={isProcessing || files.length === 0}
                        >
                            {isProcessing ? (
                                <>
                                    <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Processando...
                                </>
                            ) : (
                                <>
                                    <Mic className="mr-2 h-4 w-4" /> Transcrever
                                </>
                            )}
                        </Button>

                        <div className="relative w-full mt-4 border-t pt-4">
                            <div className="flex items-center justify-between mb-2 gap-2">
                                <Label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                                    Histórico de Jobs
                                </Label>
                                <div className="flex items-center gap-2">
                                    <label className="flex items-center gap-1 text-[10px] text-muted-foreground">
                                        <input
                                            ref={jobsSelectAllRef}
                                            type="checkbox"
                                            className="h-3 w-3 rounded border border-input"
                                            checked={allJobsSelected}
                                            disabled={deletableJobIds.length === 0}
                                            onChange={(e) => handleSelectAllJobs(e.target.checked)}
                                        />
                                        Todos
                                    </label>
                                    <Button
                                        variant="ghost"
                                        size="sm"
                                        className="h-6 px-2 text-[10px]"
                                        onClick={() => handleDeleteSelectedJobs()}
                                        disabled={selectedJobIds.size === 0}
                                    >
                                        Excluir selecionados
                                    </Button>
                                </div>
                            </div>
                            {activeJobId && (
                                <div className="text-[10px] text-muted-foreground mb-2">
                                    Job atual: <span className="font-mono">{activeJobId}</span>
                                </div>
                            )}
                            {jobsLoading ? (
                                <div className="text-xs text-muted-foreground">Carregando...</div>
                            ) : jobHistory.length === 0 ? (
                                <div className="text-xs text-muted-foreground">Nenhum job recente.</div>
                            ) : (
                                <div className="space-y-2 max-h-56 overflow-y-auto">
                                    {jobHistory.map((job) => {
                                        const jobLabel = job.job_type === 'hearing' ? 'Audiência' : 'Transcrição';
                                        const title = job.job_type === 'hearing'
                                            ? `Caso ${job.config?.case_id || '—'}`
                                            : (job.file_names || []).join(', ') || job.job_id;
                                        const canLoad = job.status === 'completed';
                                        const canResume = job.status === 'running' || job.status === 'queued';
                                        const canDelete = !canResume;
                                        return (
                                            <div key={job.job_id} className="flex items-center justify-between gap-2 text-xs border rounded-md px-2 py-2">
                                                <div className="flex items-start gap-2 min-w-0">
                                                    <input
                                                        type="checkbox"
                                                        className="mt-1 h-3 w-3 rounded border border-input"
                                                        checked={selectedJobIds.has(job.job_id)}
                                                        disabled={!canDelete}
                                                        onChange={(e) => toggleJobSelection(job.job_id, e.target.checked)}
                                                        title={canDelete ? 'Selecionar job' : 'Job em execução'}
                                                    />
                                                    <div className="min-w-0">
                                                        <div className="flex items-center gap-2">
                                                            <Badge variant={job.status === 'completed' ? 'default' : job.status === 'error' ? 'destructive' : 'secondary'}>
                                                                {job.status}
                                                            </Badge>
                                                            <span className="font-medium">{jobLabel}</span>
                                                        </div>
                                                        <div className="text-[11px] text-muted-foreground truncate" title={title}>
                                                            {title}
                                                        </div>
                                                        <div className="text-[10px] text-muted-foreground">
                                                            {formatJobTime(job.updated_at || job.created_at)}
                                                        </div>
                                                    </div>
                                                </div>
                                                <div className="flex flex-col items-end gap-1">
                                                    {typeof job.progress === 'number' && (
                                                        <span className="text-[10px] text-muted-foreground">{job.progress}%</span>
                                                    )}
                                                    {canLoad && (
                                                        <Button
                                                            size="sm"
                                                            variant="secondary"
                                                            onClick={async () => {
                                                                await handleLoadJobResult(job.job_id);
                                                                setMainTab('preview');
                                                            }}
                                                        >
                                                            Carregar
                                                        </Button>
                                                    )}
                                                    {canResume && (
                                                        <Button size="sm" variant="outline" onClick={() => handleResumeJob(job.job_id)}>
                                                            Acompanhar
                                                        </Button>
                                                    )}
                                                    {canResume && (
                                                        <Button size="sm" variant="destructive" onClick={() => handleCancelJob(job.job_id)}>
                                                            Interromper
                                                        </Button>
                                                    )}
                                                    <Button
                                                        size="icon"
                                                        variant="ghost"
                                                        className="h-7 w-7 text-destructive"
                                                        onClick={() => handleDeleteJob(job.job_id)}
                                                        disabled={!canDelete}
                                                        title={canDelete ? 'Excluir job' : 'Job em execução'}
                                                    >
                                                        <Trash2 className="h-4 w-4" />
                                                    </Button>
                                                </div>
                                            </div>
                                        );
                                    })}
                                </div>
                            )}
                        </div>

                        <div className="relative w-full mt-4 border-t pt-4">
                            <div className="flex items-center justify-between mb-2 gap-2">
                                <Label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                                    Arquivos salvos
                                </Label>
                                <div className="flex items-center gap-2">
                                    <label className="flex items-center gap-1 text-[10px] text-muted-foreground">
                                        <input
                                            ref={savedDocsSelectAllRef}
                                            type="checkbox"
                                            className="h-3 w-3 rounded border border-input"
                                            checked={allDocsSelected}
                                            disabled={selectableSavedDocIds.length === 0}
                                            onChange={(e) => handleSelectAllSavedDocs(e.target.checked)}
                                        />
                                        Todos
                                    </label>
                                    <Button
                                        variant="ghost"
                                        size="sm"
                                        className="h-6 px-2 text-[10px]"
                                        onClick={() => handleDeleteSelectedSavedDocuments()}
                                        disabled={selectedSavedDocIds.size === 0}
                                    >
                                        Excluir selecionados
                                    </Button>
                                    <Button
                                        variant="ghost"
                                        size="sm"
                                        className="h-6 px-2 text-[10px]"
                                        onClick={loadSavedDocuments}
                                        disabled={savedDocsLoading}
                                    >
                                        Atualizar
                                    </Button>
                                </div>
                            </div>
                            {savedDocsLoading ? (
                                <div className="text-xs text-muted-foreground">Carregando...</div>
                            ) : savedDocuments.length === 0 ? (
                                <div className="text-xs text-muted-foreground">Nenhum arquivo salvo ainda.</div>
                            ) : (
                                <div className="space-y-2 max-h-48 overflow-y-auto">
                                    {savedDocuments.map((doc) => {
                                        const docId = resolveSavedDocumentId(doc);
                                        const docKey = docId || `${doc?.name || 'documento'}-${doc?.created_at || ''}`;
                                        return (
                                            <div key={docKey} className="flex items-center justify-between gap-2 text-xs border rounded-md px-2 py-2">
                                                <div className="flex items-start gap-2 min-w-0">
                                                    <input
                                                        type="checkbox"
                                                        className="mt-1 h-3 w-3 rounded border border-input"
                                                        checked={docId ? selectedSavedDocIds.has(docId) : false}
                                                        disabled={!docId}
                                                        onChange={(e) => docId && toggleSavedDocSelection(docId, e.target.checked)}
                                                        title={docId ? 'Selecionar arquivo' : 'ID indisponível'}
                                                    />
                                                    <div className="min-w-0">
                                                        <div className="text-[11px] font-medium truncate" title={doc.name}>
                                                            {doc.name}
                                                        </div>
                                                        <div className="text-[10px] text-muted-foreground">
                                                            {formatJobTime(doc.created_at)}
                                                        </div>
                                                    </div>
                                                </div>
                                                <div className="flex items-center gap-2">
                                                    <Button
                                                        size="sm"
                                                        variant="outline"
                                                        className="text-[10px] h-6 px-2"
                                                        onClick={() => (window.location.href = '/documents')}
                                                    >
                                                        Abrir
                                                    </Button>
                                                    <Button
                                                        size="icon"
                                                        variant="ghost"
                                                        className="h-6 w-6 text-destructive"
                                                        onClick={() => handleDeleteSavedDocument(doc)}
                                                        disabled={!docId}
                                                        title={docId ? 'Excluir documento' : 'ID do documento indisponível'}
                                                    >
                                                        <Trash2 className="h-4 w-4" />
                                                    </Button>
                                                </div>
                                            </div>
                                        );
                                    })}
                                </div>
                            )}
                        </div>

                        {!isHearing && (
                            <div className="relative w-full mt-4 border-t pt-4">
                                <Label className="mb-2 block text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                                    Validação HIL (Offline)
                                </Label>
                                <div className="relative">
                                    <input
                                        type="file"
                                        accept=".md,.txt"
                                        onChange={handleImportMD}
                                        className="absolute inset-0 w-full h-full opacity-0 cursor-pointer z-10"
                                    />
                                    <Button variant="secondary" className="w-full" disabled={isProcessing}>
                                        <Upload className="mr-2 h-4 w-4" />
                                        Carregar Markdown Existente
                                    </Button>
                                </div>
                                <p className="text-[10px] text-muted-foreground mt-1 text-center">
                                    Carregue um arquivo local (.md) para usar o Painel de Qualidade.
                                </p>
                            </div>
                        )}

                            </CardContent>
                        </Card>
                    </DialogContent>
                </Dialog>

                <TabsContent value="preview" className="mt-4">
                {/* Resultado */}
                <Card className="flex flex-col min-h-[700px]">
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <div className="space-y-1">
                            <CardTitle>Resultado</CardTitle>
                            <CardDescription>
                                {result ? 'Visualização do documento gerado.' : 'Aguardando processamento...'}
                            </CardDescription>
                        </div>
                        {hasOutput && (
                            <div className="flex items-center gap-2">
                                <Button variant="outline" size="sm" onClick={() => handleSaveToLibrary(false)}>
                                    <Book className="mr-2 h-4 w-4" /> Salvar
                                </Button>
                                <Button size="sm" onClick={() => handleSaveToLibrary(true)}>
                                    <MessageSquare className="mr-2 h-4 w-4" /> Conversar
                                </Button>
                                <div className="h-4 w-[1px] bg-border mx-1" />
                                <Button variant="ghost" size="icon" onClick={handleExportMD} title="Baixar Markdown">
                                    <FileText className="h-4 w-4" />
                                </Button>
                                <Button
                                    variant="ghost"
                                    size="icon"
                                    onClick={handleExportDocx}
                                    disabled={!hasOutput}
                                    title="Baixar Word"
                                >
                                    <FileType className="h-4 w-4" />
                                </Button>
                            </div>
                        )}
                    </CardHeader>
                    <CardContent className="flex-1 p-0 overflow-hidden">
                        {hasOutput ? (
                            <Tabs value={activeTab} onValueChange={setActiveTab} className="flex flex-col h-full w-full overflow-hidden">
                                <div className="px-4 pt-2 border-b">
                                    <TabsList className="w-full justify-start">
                                        <TabsTrigger value="preview">{isHearing ? 'Transcrição' : 'Visualização'}</TabsTrigger>
                                        <TabsTrigger value="export">Exportar</TabsTrigger>
												{!isHearing && result && (
													<TabsTrigger value="hil" className={auditIssues.length > 0 ? "text-orange-600" : ""}>
														{auditIssues.length > 0 ? `Correções (HIL) (${auditIssues.length})` : 'Correções (HIL)'}
													</TabsTrigger>
												)}
										{!isHearing && hasPreventiveAudit && (
											<TabsTrigger
												value="preventive"
												className={preventiveShouldBlockDisplay ? "text-orange-600" : (preventiveAudit || preventiveAuditMarkdown) ? "text-green-600" : ""}
											>
												{preventiveShouldBlockDisplay ? '⚠️ Auditoria Preventiva' : 'Auditoria Preventiva'}
											</TabsTrigger>
										)}
										<TabsTrigger value="quality">{isHearing ? 'Qualidade' : 'Qualidade (Resumo)'}</TabsTrigger>
												{isHearing && hearingFormatted && <TabsTrigger value="formatted">Texto formatado</TabsTrigger>}
												{isHearing && <TabsTrigger value="speakers">Falantes</TabsTrigger>}
												{isHearing && <TabsTrigger value="evidence">Evidências</TabsTrigger>}
                                        {isHearing && <TabsTrigger value="validation">Validação</TabsTrigger>}
                                        {isHearing && (hearingPayload?.timeline || []).length > 0 && <TabsTrigger value="timeline">Linha do tempo</TabsTrigger>}
                                        {isHearing && (hearingPayload?.contradictions || []).length > 0 && <TabsTrigger value="contradictions">Contradições</TabsTrigger>}
                                        {isHearing && <TabsTrigger value="json">JSON</TabsTrigger>}
                                    </TabsList>
                                </div>

                                {/* HIL Audit Issues Tab */}
                                {!isHearing && (
                                    <TabsContent value="hil" className="flex-1 overflow-y-auto p-4 m-0 space-y-4">
                                        <AuditIssuesPanel
                                            issues={auditIssues}
                                            selectedIssueIds={selectedIssues}
                                            selectedModelLabel={selectedModel}
                                            hasRawForHil={hasRawForHil}
                                            isApplying={isApplyingFixes}
                                            isAuditOutdated={isAuditOutdated}
                                            autoAppliedSummary={autoAppliedSummary}
                                            hilDiagnostics={hilDiagnostics}
                                            onToggleIssue={toggleIssue}
                                            onApplySelected={handleApplyFixes}
                                            onAutoApplyStructural={handleAutoApplyStructural}
                                            onAutoApplyContent={handleAutoApplyContent}
                                            onReviewIssue={openIssueAssistant}
                                        />
                                    </TabsContent>
										)}

										<TabsContent value="preview" className="flex-1 overflow-hidden p-0 m-0 data-[state=active]:flex flex-col">
											{isHearing ? (
												<div className="flex h-full flex-col">
													<div className="border-b p-4 space-y-3">
														<div className="flex items-center justify-between text-sm">
                                                    <span className="font-medium">Reprodutor de áudio</span>
                                                    <span className="text-xs text-muted-foreground">
                                                        {formatDuration(currentTime)} / {formatDuration(mediaDuration)}
                                                    </span>
                                                </div>
                                                {mediaUrl ? (
                                                    isVideoFile ? (
                                                        <video
                                                            ref={(el) => {
                                                                mediaRef.current = el;
                                                            }}
                                                            src={mediaUrl}
                                                            controls
                                                            className="w-full rounded-md border"
                                                            onTimeUpdate={(e) => setCurrentTime(e.currentTarget.currentTime)}
                                                            onLoadedMetadata={(e) => setMediaDuration(e.currentTarget.duration || 0)}
                                                        />
                                                    ) : (
                                                        <audio
                                                            ref={(el) => {
                                                                mediaRef.current = el;
                                                            }}
                                                            src={mediaUrl}
                                                            controls
                                                            className="w-full"
                                                            onTimeUpdate={(e) => setCurrentTime(e.currentTarget.currentTime)}
                                                            onLoadedMetadata={(e) => setMediaDuration(e.currentTarget.duration || 0)}
                                                        />
                                                    )
                                                ) : (
                                                    <div className="text-xs text-muted-foreground">
                                                        Carregue um arquivo para habilitar o player.
                                                    </div>
                                                )}
                                                <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
                                                    <div className="flex items-center gap-2">
                                                        <span>Velocidade:</span>
                                                        <select
                                                            className="rounded-md border border-input bg-background px-2 py-1 text-xs"
                                                            value={playbackRate}
                                                            onChange={(e) => setPlaybackRate(Number(e.target.value))}
                                                        >
                                                            <option value={0.75}>0.75x</option>
                                                            <option value={1}>1x</option>
                                                            <option value={1.25}>1.25x</option>
                                                            <option value={1.5}>1.5x</option>
                                                            <option value={2}>2x</option>
                                                        </select>
                                                    </div>
                                                    <div className="flex items-center gap-1">
                                                        <Clock className="h-3 w-3" />
                                                        <span>Sincronizado por timestamp</span>
                                                    </div>
                                                </div>
                                            </div>
                                            <div className="flex-1 overflow-y-auto p-4 space-y-2 bg-muted/50">
                                                {report && (
                                                    <details className="bg-yellow-500/10 text-yellow-700 dark:text-yellow-400 rounded-md border border-yellow-200/70 dark:border-yellow-700/40 p-3">
                                                        <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wide">
                                                            Relatórios de Auditoria
                                                        </summary>
                                                        <div className="mt-3 text-sm font-medium whitespace-pre-wrap">
                                                            {report}
                                                        </div>
                                                    </details>
                                                )}
                                                {hearingSegments.length === 0 && (
                                                    <pre className="whitespace-pre-wrap text-sm font-mono text-foreground">
                                                        {(hearingTranscript || '').replace(/<!--\s*RELATÓRIO:[\s\S]*?-->/gi, '')}
                                                    </pre>
                                                )}
                                                {hearingSegments.map((seg: any) => {
                                                    const speaker = speakerMap.get(seg.speaker_id) || {};
                                                    const label = speaker?.name || speaker?.label || seg.speaker_label || 'Falante';
                                                    const role = speaker?.role ? ` (${speaker.role})` : '';
                                                    const timeLabel = seg.timestamp_hint || formatTimestamp(seg.start);
                                                    const isActive = seg.id === activeSegmentId;
                                                    const canSeek = typeof seg.start === 'number';
                                                    return (
                                                        <div
                                                            key={seg.id}
                                                            id={`segment-${seg.id}`}
                                                            className={`rounded-md border p-3 space-y-2 ${isActive ? 'border-primary bg-primary/5' : 'border-border bg-card'}`}
                                                        >
                                                            <div className="flex items-center justify-between text-xs text-muted-foreground">
                                                                {canSeek ? (
                                                                    <button
                                                                        className="font-mono hover:text-primary"
                                                                        onClick={() => seekToTime(seg.start)}
                                                                    >
                                                                        {timeLabel}
                                                                    </button>
                                                                ) : (
                                                                    <span className="font-mono">{timeLabel}</span>
                                                                )}
                                                                <span>{seg.id}</span>
                                                            </div>
                                                            <div className="text-sm font-medium">{label}{role}</div>
                                                            <div className="text-sm text-muted-foreground whitespace-pre-wrap">{seg.text}</div>
                                                        </div>
                                                    );
                                                })}
                                            </div>
                                        </div>
                                    ) : (
                                        <div className="flex-1 overflow-y-auto flex flex-col">
                                            {report && (
                                                <details className="bg-yellow-500/10 text-yellow-700 dark:text-yellow-400 rounded-md border border-yellow-200/70 dark:border-yellow-700/40 p-3 mx-4 mt-4">
                                                    <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wide">
                                                        Relatórios de Auditoria
                                                    </summary>
                                                    <div className="mt-3 text-sm font-medium whitespace-pre-wrap">
                                                        {report}
                                                    </div>
                                                </details>
                                            )}
                                            <div className="flex-1 p-4 min-h-0">
                                                {isEditingResult ? (
                                                    <div className="h-full flex flex-col gap-2">
                                                        {activeDocumentLayout.showHeaderFooter && (
                                                            <div className="flex items-center justify-between rounded-md border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
                                                                <span className="font-medium text-foreground">{previewHeaderText}</span>
                                                                <span>Layout</span>
                                                            </div>
                                                        )}
                                                        <div className="flex-1 min-h-0">
                                                            <MarkdownEditorPanel
                                                                content={draftResult ?? result ?? ''}
                                                                onChange={setDraftResult}
                                                                onOpenLayout={() => openLayoutDialog('tables')}
                                                                richContentHtml={richTextHtml}
                                                                richContentJson={richTextJson}
                                                                richPreviewHtml={richTextHtml}
                                                                onRichContentChange={(payload) => {
                                                                    setRichTextHtml(payload.html);
                                                                    setRichTextJson(payload.json);
                                                                    setRichTextMeta(payload.meta);
                                                                }}
                                                                onCancel={() => {
                                                                    setIsEditingResult(false);
                                                                    setDraftResult(null);
                                                                    toast.info('Edição cancelada.');
                                                                }}
                                                                onSave={async (markdown) => {
                                                                    const next = stripReportBlocks(markdown) || markdown || '';
                                                                    setResult(next);
                                                                    setIsEditingResult(false);
                                                                    setDraftResult(null);
                                                                    setIsAuditOutdated(true);
                                                                    if (activeJobId) {
                                                                        try {
                                                                            await apiClient.updateTranscriptionJobContent(activeJobId, {
                                                                                content: next,
                                                                            });
                                                                        } catch (error: any) {
                                                                            toast.error(error?.message || 'Falha ao salvar conteúdo.');
                                                                        }
                                                                    }
                                                                    toast.success('Alterações salvas!');
                                                                }}
                                                                onSaveRich={async (payload) => {
                                                                    if (!activeJobId) return;
                                                                    try {
                                                                        await apiClient.updateTranscriptionJobContent(activeJobId, {
                                                                            rich_text_html: payload.html,
                                                                            rich_text_json: payload.json,
                                                                            rich_text_meta: payload.meta,
                                                                        });
                                                                    } catch (error: any) {
                                                                        console.error(error);
                                                                    }
                                                                }}
                                                                onDownload={(markdown) => {
                                                                    const content = markdown || '';
                                                                    if (!content) return;
                                                                    triggerMarkdownDownload(content, `transcricao-${new Date().getTime()}.md`);
                                                                    toast.success('Arquivo Markdown baixado!');
                                                                }}
	                                                                className={`h-full ${documentThemeClass} ${documentLayoutClass}`}
	                                                                themeClassName={`${documentThemeClass} ${documentLayoutClass}`}
	                                                                style={documentTypographyStyle}
	                                                            />
                                                        </div>
                                                        {activeDocumentLayout.showHeaderFooter && (
                                                            <div className="flex items-center justify-between rounded-md border bg-muted/20 px-3 py-2 text-xs text-muted-foreground">
                                                                <span>{previewFooterText || '—'}</span>
                                                                <span>Página •</span>
                                                            </div>
                                                        )}
                                                    </div>
                                                ) : (
                                                    <div className="flex h-full flex-col gap-3">
                                                        <div className="flex items-center justify-between gap-2">
                                                            <div className="flex items-center gap-2">
                                                                <Button
                                                                    variant={previewMode === 'formatted' ? 'default' : 'outline'}
                                                                    size="sm"
                                                                    onClick={() => setPreviewMode('formatted')}
                                                                >
                                                                    <FileText className="mr-2 h-4 w-4" />
                                                                    Formatado
                                                                </Button>
                                                                <Button
                                                                    variant={previewMode === 'raw' ? 'default' : 'outline'}
                                                                    size="sm"
                                                                    onClick={() => setPreviewMode('raw')}
                                                                    disabled={isHearing ? !hearingTranscript : !rawResult}
                                                                    title={(isHearing ? !hearingTranscript : !rawResult) ? 'Transcrição RAW não disponível' : 'Ver transcrição original'}
                                                                >
                                                                    <FileText className="mr-2 h-4 w-4" />
                                                                    RAW
                                                                </Button>
                                                            </div>
                                                            <div className="flex items-center gap-2">
                                                                <Button
                                                                    variant="outline"
                                                                    size="icon"
                                                                    onClick={() => openLayoutDialog('page')}
                                                                    title="Layout da página"
                                                                >
                                                                    <LayoutTemplate className="h-4 w-4" />
                                                                </Button>
                                                                <Button
                                                                    variant="outline"
                                                                    size="icon"
                                                                    onClick={() => openLayoutDialog('header')}
                                                                    title="Cabeçalho e rodapé"
                                                                >
                                                                    <Heading className="h-4 w-4" />
                                                                </Button>
                                                                <Button
                                                                    variant="outline"
                                                                    size="icon"
                                                                    onClick={() => openLayoutDialog('typography')}
                                                                    title="Fonte e tamanho"
                                                                >
                                                                    <Type className="h-4 w-4" />
                                                                </Button>
                                                                <Button
                                                                    variant="outline"
                                                                    size="icon"
                                                                    onClick={() => openLayoutDialog('margins')}
                                                                    title="Margens"
                                                                >
                                                                    <ArrowLeftRight className="h-4 w-4" />
                                                                </Button>
                                                                <Button
                                                                    variant="outline"
                                                                    size="icon"
                                                                    onClick={() => openLayoutDialog('tables')}
                                                                    title="Tema / design das tabelas"
                                                                >
                                                                    <Table2 className="h-4 w-4" />
                                                                </Button>
                                                                <Button
                                                                    variant="outline"
                                                                    size="icon"
                                                                    onClick={handleInsertPageBreak}
                                                                    title="Quebra de página / seções"
                                                                    disabled={!hasOutput}
                                                                >
                                                                    <Scissors className="h-4 w-4" />
                                                                </Button>
                                                                <Button
                                                                    variant="outline"
                                                                    size="sm"
                                                                    onClick={() => openLayoutDialog('tables')}
                                                                    className="hidden md:inline-flex"
                                                                    title="Abrir painel completo de layout"
                                                                >
                                                                    <SlidersHorizontal className="mr-2 h-4 w-4" />
                                                                    Layout
                                                                </Button>
                                                                <Button
                                                                    variant="outline"
                                                                    size="sm"
                                                                    disabled={!hasOutput}
                                                                    onClick={() => {
                                                                        const initial = stripReportBlocks(result) || result || '';
                                                                        setDraftResult(initial);
                                                                        setIsEditingResult(true);
                                                                    }}
                                                                >
                                                                    <Edit3 className="mr-2 h-4 w-4" />
                                                                    Editar
                                                                </Button>
                                                            </div>
                                                        </div>

                                                        <div className="flex-1 overflow-y-auto">
                                                            {previewMode === 'raw' && (isHearing ? hearingTranscript : rawResult) ? (
                                                                <SyncedTranscriptViewer
                                                                    rawContent={(isHearing ? hearingTranscript : rawResult) || ''}
                                                                    mediaUrl={mediaUrl}
                                                                    mediaFiles={
                                                                        files.length > 0
                                                                            ? files.map((f) => ({ name: f.name, url: URL.createObjectURL(f) }))
                                                                            : jobMediaFiles
                                                                    }
                                                                    className="h-full border rounded-md"
                                                                />
                                                            ) : (
                                                                <div className="h-full flex flex-col gap-2">
                                                                    {activeDocumentLayout.showHeaderFooter && (
                                                                        <div className="flex items-center justify-between rounded-md border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
                                                                            <span className="font-medium text-foreground">{previewHeaderText}</span>
                                                                            <span>Preview</span>
                                                                        </div>
                                                                    )}
                                                                    <div className="flex-1 min-h-0">
                                                                        {richTextHtml ? (
                                                                            <RichHtmlPreview
                                                                                html={richTextHtml}
                                                                                className={`h-full ${documentThemeClass} ${documentLayoutClass}`}
                                                                                style={documentTypographyStyle}
                                                                            />
                                                                        ) : (
                                                                            <MarkdownPreview
                                                                                content={stripReportBlocks(result) || result || ''}
                                                                                className={`h-full ${documentThemeClass} ${documentLayoutClass}`}
                                                                                style={documentTypographyStyle}
                                                                            />
                                                                        )}
                                                                    </div>
                                                                    {activeDocumentLayout.showHeaderFooter && (
                                                                        <div className="flex items-center justify-between rounded-md border bg-muted/20 px-3 py-2 text-xs text-muted-foreground">
                                                                            <span>{previewFooterText || '—'}</span>
                                                                            <span>Página •</span>
                                                                        </div>
                                                                    )}
                                                                </div>
                                                            )}
                                                        </div>
                                                    </div>
                                                )}
                                            </div>
                                        </div>
                                    )}
                                </TabsContent>

                                <TabsContent value="export" className="flex-1 overflow-y-auto p-4 m-0 space-y-4">
                                    <div className="border rounded-md p-4 space-y-2">
                                        <div className="text-sm font-medium">Download</div>
                                        <div className="flex flex-wrap gap-2">
                                            <Button variant="outline" onClick={handleExportMD} disabled={!hasOutput}>
                                                <FileText className="mr-2 h-4 w-4" /> Markdown
                                            </Button>
                                            <Button
                                                variant="outline"
                                                onClick={handleExportDocx}
                                                disabled={!hasOutput}
                                            >
                                                <FileType className="mr-2 h-4 w-4" /> Word
                                            </Button>
                                        </div>
                                    </div>
                                    <div className="border rounded-md p-4 space-y-2">
                                        <div className="text-sm font-medium">Relatórios</div>
                                        {reportEntries.length > 0 ? (
                                            <div className="space-y-2">
                                                {reportEntries.map((entry) => (
                                                    <div key={entry.key} className="flex items-center justify-between gap-2">
                                                        <div className="text-xs text-muted-foreground">{entry.label}</div>
                                                        <Button
                                                            variant="outline"
                                                            size="sm"
                                                            onClick={() => handleDownloadReport(entry.key)}
                                                            disabled={!activeJobId}
                                                        >
                                                            Baixar
                                                        </Button>
                                                    </div>
                                                ))}
                                            </div>
                                        ) : (
                                            <div className="text-xs text-muted-foreground">
                                                Nenhum relatório disponível neste job.
                                            </div>
                                        )}
                                    </div>
                                    <div className="border rounded-md p-4 space-y-2">
                                        <div className="text-sm font-medium">Envio direto</div>
                                        <div className="flex flex-wrap gap-2">
                                            <Button variant="outline" onClick={() => handleSaveToLibrary(false)} disabled={!hasOutput}>
                                                <Book className="mr-2 h-4 w-4" /> Salvar na biblioteca
                                            </Button>
                                            <Button onClick={() => handleSaveToLibrary(true)} disabled={!hasOutput}>
                                                <MessageSquare className="mr-2 h-4 w-4" /> Salvar e conversar
                                            </Button>
                                        </div>
                                    </div>
                                    <div className="border rounded-md p-4 space-y-2">
                                        <div className="text-sm font-medium">Preview</div>
                                        <Button variant="ghost" onClick={() => setActiveTab('preview')}>
                                            Abrir visualização
                                        </Button>
                                    </div>
										</TabsContent>

										{!isHearing && hasPreventiveAudit && (
											<TabsContent value="preventive" className="flex-1 overflow-y-auto p-4 m-0 space-y-4">
												<PreventiveAuditPanel
													audit={preventiveAudit}
													auditMarkdown={preventiveAuditMarkdown}
													recommendation={preventiveRecommendation}
													status={preventiveStatus}
													loading={preventiveAuditLoading}
													error={preventiveAuditError}
													isAuditOutdated={isAuditOutdated}
													hasRawForHil={hasRawForHil}
													hasDocument={Boolean(result)}
													onConvertAlerts={handleConvertPreventiveToHil}
													onGoToHil={handleGoToHil}
													onDownloadReport={handleDownloadReport}
													canDownloadMd={Boolean(reportPaths?.preventive_fidelity_md_path)}
													canDownloadJson={Boolean(reportPaths?.preventive_fidelity_json_path)}
													onRecompute={handleRecomputePreventiveAudit}
													canRecompute={Boolean(activeJobId) && !preventiveAuditLoading}
													onReload={() => fetchPreventiveAudit(true)}
												/>
											</TabsContent>
										)}

										<TabsContent value="quality" className="flex-1 overflow-y-auto p-4 m-0">
												<QualityPanel
													rawContent={isHearing ? (hearingTranscript || '') : (rawResult || '')}
													formattedContent={isHearing ? (hearingFormatted || '') : (result || '')}
													documentName={activeDocumentName || 'Documento'}
													documentMode={!isHearing ? mode : undefined}
													modelSelection={selectedModel}
													jobId={activeJobId || undefined}
													initialQuality={jobQuality}
													onContentUpdated={isHearing ? setHearingFormatted : (content) => {
														setResult(content);
														clearRichContent();
													}}
												variant={isHearing ? 'full' : 'dashboard'}
												// Hearing-specific props
												contentType={isHearing ? 'hearing' : 'apostila'}
												segments={isHearing ? hearingSegments : undefined}
												speakers={isHearing ? hearingSpeakers : undefined}
												hearingMode={isHearing ? (hearingFormatMode === 'audiencia' ? 'AUDIENCIA' : hearingFormatMode === 'reuniao' ? 'REUNIAO' : 'DEPOIMENTO') : undefined}
												onHearingUpdated={isHearing ? (payload) => applyHearingPayload(payload) : undefined}
												// Synchronization props (unified audit state)
												externalAuditIssues={!isHearing ? auditIssues : undefined}
												isAuditOutdated={isAuditOutdated}
												onIssuesUpdated={!isHearing ? setAuditIssues : undefined}
												onAuditOutdatedChange={setIsAuditOutdated}
												onConvertContentAlerts={!isHearing ? handleConvertQualityAlertsToHil : undefined}
											/>
										</TabsContent>

                                {isHearing && (
                                    <>
                                        {hearingFormatted && (
                                            <TabsContent value="formatted" className="flex-1 overflow-y-auto p-4 m-0">
                                                <pre className="whitespace-pre-wrap text-sm font-mono text-foreground">
                                                    {hearingFormatted}
                                                </pre>
                                            </TabsContent>
                                        )}
                                        <TabsContent value="speakers" className="flex-1 overflow-y-auto p-4 m-0 space-y-4">
                                            <div className="flex items-center justify-between">
                                                <div className="text-sm text-muted-foreground">
                                                    Edite nomes e papéis. As alterações sobrescrevem o automático.
                                                </div>
                                                <Button size="sm" onClick={handleSaveSpeakers} disabled={isSavingSpeakers || hearingSpeakers.length === 0}>
                                                    {isSavingSpeakers ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                                                    Salvar falantes
                                                </Button>
                                            </div>
                                            <div className="space-y-2">
                                                {hearingSpeakers.map((sp) => (
                                                    <div key={sp.speaker_id} className="grid grid-cols-1 md:grid-cols-4 gap-2 border rounded-md p-3">
                                                        <div>
                                                            <Label className="text-xs">Label</Label>
                                                            <div className="text-sm font-mono">{sp.label}</div>
                                                        </div>
                                                        <div>
                                                            <Label className="text-xs">Nome</Label>
                                                            <input
                                                                className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                                                                value={sp.name || ''}
                                                                onChange={(e) => {
                                                                    const value = e.target.value;
                                                                    setHearingSpeakers(prev => prev.map(item => item.speaker_id === sp.speaker_id ? { ...item, name: value } : item));
                                                                }}
                                                            />
                                                        </div>
                                                        <div>
                                                            <Label className="text-xs">Papel</Label>
                                                            <select
                                                                className="flex h-9 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm"
                                                                value={sp.role || 'outro'}
                                                                onChange={(e) => {
                                                                    const value = e.target.value;
                                                                    setHearingSpeakers(prev => prev.map(item => item.speaker_id === sp.speaker_id ? { ...item, role: value } : item));
                                                                }}
                                                            >
                                                                {hearingRoles.map(role => (
                                                                    <option key={role} value={role}>{role}</option>
                                                                ))}
                                                            </select>
                                                        </div>
                                                        <div>
                                                            <Label className="text-xs">Confiança</Label>
                                                            <div className="text-sm">
                                                                {typeof sp.confidence === 'number'
                                                                    ? `${Math.round(sp.confidence * 100)}%`
                                                                    : '-'}
                                                            </div>
                                                        </div>
                                                    </div>
                                                ))}
                                            </div>
                                        </TabsContent>

                                        <TabsContent value="evidence" className="flex-1 overflow-y-auto p-4 m-0 space-y-3">
                                            <div className="flex items-center gap-2 text-sm font-medium">
                                                <ListChecks className="h-4 w-4" /> Quadro de evidências
                                            </div>
                                            <div className="space-y-2">
                                                {(hearingPayload?.evidence || []).length === 0 && (
                                                    <p className="text-sm text-muted-foreground">Nenhuma evidência relevante acima do limiar.</p>
                                                )}
                                                {(hearingPayload?.evidence || []).map((ev: any) => {
                                                    const block = blockMap.get(String(ev.block_id)) || {};
                                                    const topics = Array.isArray(ev.topics) && ev.topics.length > 0 ? ev.topics : (block.topics || []);
                                                    return (
                                                        <div key={ev.id} className="border rounded-md p-3 space-y-2">
                                                            <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                                                                <span className="flex items-center gap-1">
                                                                    <Star className="h-3 w-3" />
                                                                    {ev.relevance_score ?? '-'}
                                                                </span>
                                                                {block.act_type && <span className="rounded-full bg-muted px-2 py-0.5">Tipo: {block.act_type}</span>}
                                                                {topics.length > 0 && <span className="rounded-full bg-muted px-2 py-0.5">Tema: {topics.join(', ')}</span>}
                                                                {ev.relevance_reasons?.length ? (
                                                                    <span className="rounded-full bg-muted px-2 py-0.5">Motivos: {ev.relevance_reasons.join(', ')}</span>
                                                                ) : null}
                                                            </div>
                                                            <div className="text-sm font-medium">{ev.claim_normalized || 'Fato identificado'}</div>
                                                            <div className="text-sm text-muted-foreground">{ev.quote_verbatim}</div>
                                                        </div>
                                                    );
                                                })}
                                            </div>
                                        </TabsContent>

                                        <TabsContent value="validation" className="flex-1 overflow-y-auto p-4 m-0 space-y-4">
                                            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                                                <div className="border rounded-md p-4 space-y-3">
                                                    <div className="text-sm font-medium">Checklist de qualidade</div>
                                                    <div className="space-y-2">
                                                        {validationItems.map(item => (
                                                            <div key={item.id} className="flex items-start gap-2 text-sm">
                                                                {item.ok ? (
                                                                    <CheckCircle className="h-4 w-4 text-emerald-600" />
                                                                ) : (
                                                                    <AlertCircle className="h-4 w-4 text-orange-600" />
                                                                )}
                                                                <div>
                                                                    <div className="font-medium">{item.label}</div>
                                                                    <div className="text-xs text-muted-foreground">{item.detail}</div>
                                                                </div>
                                                            </div>
                                                        ))}
                                                    </div>
                                                </div>
                                                <div className="border rounded-md p-4 space-y-3">
                                                    <div className="text-sm font-medium">Estatísticas</div>
                                                    <div className="grid grid-cols-2 gap-3 text-xs text-muted-foreground">
                                                        <div>Segmentos: <span className="text-foreground font-medium">{hearingSegments.length}</span></div>
                                                        <div>Falantes: <span className="text-foreground font-medium">{hearingSpeakers.length}</span></div>
                                                        <div>Evidências: <span className="text-foreground font-medium">{(hearingPayload?.evidence || []).length}</span></div>
                                                        <div>Claims: <span className="text-foreground font-medium">{(hearingPayload?.claims || []).length}</span></div>
                                                        <div>Contradições: <span className="text-foreground font-medium">{(hearingPayload?.contradictions || []).length}</span></div>
                                                        <div>Timeline: <span className="text-foreground font-medium">{(hearingPayload?.timeline || []).length}</span></div>
                                                    </div>
                                                </div>
                                            </div>
                                            <div className="border rounded-md p-4 space-y-2">
                                                <div className="text-sm font-medium">Itens a revisar</div>
                                                <div className="space-y-1 text-sm text-muted-foreground">
                                                    {auditWarnings.length === 0 && !validationReport && !analysisReport && (
                                                        <div>Sem alertas adicionais.</div>
                                                    )}
                                                    {auditWarnings.length > 0 && (
                                                        <div>
                                                            <div className="font-medium text-foreground">Alertas do pipeline</div>
                                                            <ul className="list-disc list-inside">
                                                                {auditWarnings.map((warning) => (
                                                                    <li key={warning}>
                                                                        {warning === 'sem_match_enrollment' && 'Sem correspondência de enrollment'}
                                                                        {warning === 'sem_formatacao' && 'Texto sem formatação aplicada'}
                                                                        {warning === 'act_classification_truncated' && 'Classificação de atos truncada'}
                                                                        {warning === 'claims_truncated' && 'Claims truncados (limite de evidências)'}
                                                                        {!['sem_match_enrollment', 'sem_formatacao', 'act_classification_truncated', 'claims_truncated'].includes(warning) && warning}
                                                                    </li>
                                                                ))}
                                                            </ul>
                                                        </div>
                                                    )}
                                                    {validationReport && (
                                                        <div className="space-y-1">
                                                            <div className="font-medium text-foreground">Validação de fidelidade</div>
                                                            <div>Score: {validationReport.score ?? '-'} / 10</div>
                                                            {validationReport.omissions?.length ? (
                                                                <div>Omissões: {validationReport.omissions.length}</div>
                                                            ) : null}
                                                            {validationReport.structural_issues?.length ? (
                                                                <div>Problemas estruturais: {validationReport.structural_issues.length}</div>
                                                            ) : null}
                                                        </div>
                                                    )}
                                                    {analysisReport && (
                                                        <div className="space-y-1">
                                                            <div className="font-medium text-foreground">Análise estrutural</div>
                                                            <div>Issues pendentes: {analysisReport.total_issues ?? 0}</div>
                                                            {analysisReport.compression_warning && (
                                                                <div>Compressão excessiva detectada</div>
                                                            )}
                                                        </div>
                                                    )}
                                                </div>
                                            </div>
                                        </TabsContent>

                                        {(hearingPayload?.timeline || []).length > 0 && (
                                            <TabsContent value="timeline" className="flex-1 overflow-y-auto p-4 m-0 space-y-2">
                                                {(hearingPayload?.timeline || []).map((item: any) => (
                                                    <div key={item.id} className="border rounded-md p-3">
                                                        <div className="text-xs text-muted-foreground">{item.date}</div>
                                                        <div className="text-sm">{item.summary}</div>
                                                    </div>
                                                ))}
                                            </TabsContent>
                                        )}

                                        {(hearingPayload?.contradictions || []).length > 0 && (
                                            <TabsContent value="contradictions" className="flex-1 overflow-y-auto p-4 m-0 space-y-2">
                                                {(hearingPayload?.contradictions || []).map((item: any) => (
                                                    <div key={item.id} className="border rounded-md p-3 space-y-1">
                                                        <div className="text-sm font-medium">{item.topic}</div>
                                                        <div className="text-xs text-muted-foreground">{item.reason}</div>
                                                        <div className="text-sm">{(item.samples || []).join(' | ')}</div>
                                                    </div>
                                                ))}
                                            </TabsContent>
                                        )}

                                        <TabsContent value="json" className="flex-1 overflow-y-auto p-4 m-0">
                                            <pre className="whitespace-pre-wrap text-xs font-mono">
                                                {JSON.stringify(hearingPayload, null, 2)}
                                            </pre>
                                        </TabsContent>
                                    </>
                                )}
                            </Tabs>
                        ) : (
                            <div className="flex h-full items-center justify-center text-muted-foreground p-8">
                                {isProcessing ? (
                                    <div className="text-center p-8 w-full max-w-2xl mx-auto">
                                        <Loader2 className="h-12 w-12 animate-spin mx-auto mb-4 text-primary" />
                                        <p className="text-lg font-medium mb-2">{progressMessage}</p>

                                        <div className="w-full bg-muted rounded-full h-3 overflow-hidden mb-6">
                                            <div
                                                className="bg-primary h-3 rounded-full transition-all duration-500 ease-out"
                                                style={{ width: `${progressPercent}%` }}
                                            />
                                        </div>

                                        <div className="flex items-center justify-center gap-2 text-xs text-muted-foreground mb-4">
                                            <Clock className="h-3 w-3" />
                                            <span>
                                                ETA {etaSeconds !== null ? formatDuration(etaSeconds) : 'calculando...'}
                                            </span>
                                        </div>

                                        <div className="grid grid-cols-4 text-xs text-muted-foreground mt-2 mb-6 gap-2">
                                            <span className={`flex flex-col items-center gap-1 p-2 rounded-md transition-all ${progressStage === 'audio_optimization'
                                                ? 'bg-primary/10 text-primary font-medium border border-primary/30'
                                                : progressPercent > 20
                                                    ? 'text-green-600'
                                                    : ''
                                                }`}>
                                                <span className="text-lg">{progressPercent > 20 ? '✅' : '🔊'}</span>
                                                <span className="text-center">Áudio</span>
                                            </span>
                                            <span className={`flex flex-col items-center gap-1 p-2 rounded-md transition-all ${progressStage === 'transcription'
                                                ? 'bg-primary/10 text-primary font-medium border border-primary/30'
                                                : progressPercent > 60
                                                    ? 'text-green-600'
                                                    : ''
                                                }`}>
                                                <span className="text-lg">{progressPercent > 60 ? '✅' : '🎙️'}</span>
                                                <span className="text-center">Transcrição</span>
                                            </span>
                                            <span className={`flex flex-col items-center gap-1 p-2 rounded-md transition-all ${(progressStage === 'formatting' || progressStage === 'structuring')
                                                ? 'bg-primary/10 text-primary font-medium border border-primary/30'
                                                : progressPercent > 95
                                                    ? 'text-green-600'
                                                    : ''
                                                }`}>
                                                <span className="text-lg">{progressPercent > 95 ? '✅' : '✨'}</span>
                                                <span className="text-center">{isHearing ? 'Estruturação' : 'Formatação'}</span>
                                            </span>
                                            <span className={`flex flex-col items-center gap-1 p-2 rounded-md transition-all ${(progressStage === 'audit' || progressStage === 'audit_complete')
                                                ? 'bg-primary/10 text-primary font-medium border border-primary/30'
                                                : progressPercent >= 100
                                                    ? 'text-green-600'
                                                    : ''
                                                }`}>
                                                <span className="text-lg">{progressPercent >= 100 ? '✅' : '🔍'}</span>
                                                <span className="text-center">Auditoria</span>
                                            </span>
                                        </div>

	                                        <div className="mt-4 flex items-center justify-between gap-3">
	                                            <div className="text-[11px] text-muted-foreground">
	                                                Logs em tempo real do servidor
	                                                {logs.length ? ` · ${logs.length} linhas` : ''}
	                                            </div>
	                                            <Button
	                                                type="button"
	                                                variant="outline"
	                                                size="sm"
	                                                className="h-8"
	                                                onClick={() => setProgressLogsOpen(true)}
	                                                disabled={logs.length === 0}
	                                            >
	                                                Ver logs
	                                            </Button>
	                                        </div>
	                                    </div>
	                                ) : (
                                    <div className="text-center">
                                        <FileAudio className="h-12 w-12 mx-auto mb-4 opacity-20" />
                                        <p>Selecione um job em “Transcription Jobs” e clique em “Abrir”.</p>
                                    </div>
                                )}
                            </div>
                        )}
                    </CardContent>
                </Card>
                </TabsContent>
            </Tabs>

            {pendingRevision && (
                <DiffConfirmDialog
                    open={showDiffConfirm}
                    onOpenChange={(open) => {
                        if (!open) {
                            setShowDiffConfirm(false);
                            setPendingRevision(null);
                        }
                    }}
                    original={result || ''}
                    replacement={pendingRevision.content}
                    title="Confirmar Aplicação de Correções"
                    description="Verifique as alterações propostas pela IA antes de aplicar ao documento. Use 'Aplicar Seleção' para aprovar por trecho."
                    onAccept={handleConfirmRevision}
                    onAcceptPartial={(content) => handleConfirmRevision(content, true)}
                    onReject={() => {
                        setShowDiffConfirm(false);
                        setPendingRevision(null);
                        toast.info('Correções canceladas.');
                    }}
                    changeStats={
                        pendingRevision.data?.content_change
                            ? {
                                paragraphsChanged: 0,
                                totalParagraphs: (result || '').split('\n\n').length,
                                wordsAdded: Math.max(0, pendingRevision.data.content_change.delta_chars || 0),
                                wordsRemoved: Math.max(0, -(pendingRevision.data.content_change.delta_chars || 0)),
                            }
                            : undefined
                    }
                />
            )}

            <Dialog
                open={issueAssistantOpen}
                onOpenChange={(open) => {
                    setIssueAssistantOpen(open);
                    if (!open) {
                        setIssueAssistantIssue(null);
                        setIssueAssistantInstruction('');
                        setIssueAssistantForce(false);
                    }
                }}
            >
                <DialogContent className="max-w-5xl">
                    <DialogHeader>
                        <DialogTitle>Revisão assistida do issue</DialogTitle>
                        <DialogDescription>
                            Veja onde a correção entra no texto e gere uma prévia via IA; o diff de confirmação continua igual.
                        </DialogDescription>
                    </DialogHeader>

                    {(() => {
                        const issue = issueAssistantIssue;
                        const reference = getIssueReference(issue);
                        const suggestedSection = typeof issue?.suggested_section === 'string' ? issue.suggested_section.trim() : '';
                        const rawSnippet = getIssueRawSnippet(issue);
                        const context = extractSectionFromMarkdown(result || '', suggestedSection, reference);
                        const hasRefAlready = Boolean(reference && normalizeForMatch(result || '').includes(normalizeForMatch(reference)));
                        const canPreview = Boolean(issueAssistantForce || !hasRefAlready);

                        return (
                            <div className="space-y-4">
                                {issue && (
                                    <div className="rounded-md border bg-muted/20 p-3 text-sm">
                                        <div className="flex flex-wrap items-center justify-between gap-2">
                                            <div className="space-y-1">
                                                <div className="font-medium text-foreground">
                                                    {issue.type?.replace?.(/_/g, ' ') || 'issue'}
                                                </div>
                                                <div className="text-xs text-muted-foreground">
                                                    {reference ? `Referência: ${reference}` : 'Referência: —'}
                                                    {suggestedSection ? ` · Seção sugerida: ${suggestedSection}` : ''}
                                                </div>
                                            </div>
                                            {hasRefAlready && (
                                                <div className="flex flex-wrap items-center gap-2">
                                                    <div className="text-xs rounded-md bg-yellow-100 text-yellow-900 px-2 py-1 border border-yellow-200">
                                                        A referência já aparece no texto; pode ser falso positivo.
                                                    </div>
                                                    <label className="flex items-center gap-2 text-xs text-muted-foreground">
                                                        <input
                                                            type="checkbox"
                                                            className="h-4 w-4"
                                                            checked={issueAssistantForce}
                                                            onChange={(e) => setIssueAssistantForce(e.target.checked)}
                                                        />
                                                        Forçar prévia mesmo assim
                                                    </label>
                                                </div>
                                            )}
                                        </div>
                                        <div className="mt-2 text-sm text-foreground">{issue.description}</div>
                                        <div className="mt-1 text-xs text-muted-foreground">💡 {issue.suggestion}</div>
                                    </div>
                                )}

                                <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                                    <div className="space-y-2">
                                        <div className="text-xs font-semibold uppercase text-muted-foreground">Contexto no texto atual</div>
                                        <div className="rounded-md border p-3">
                                            {context.note && (
                                                <div className="mb-2 text-[11px] text-muted-foreground">
                                                    {context.note}
                                                </div>
                                            )}
                                            <MarkdownPreview content={stripReportBlocks(context.section) || context.section || ''} className="max-h-[360px]" />
                                        </div>
                                    </div>

                                    <div className="space-y-2">
                                        <div className="text-xs font-semibold uppercase text-muted-foreground">Evidência (RAW)</div>
                                        <div className="rounded-md border bg-muted/10 p-3">
                                            <pre className="whitespace-pre-wrap text-[12px] text-foreground max-h-[360px] overflow-auto">
                                                {(rawSnippet || '—').slice(0, 6000)}
                                            </pre>
                                        </div>
                                    </div>
                                </div>

                                <div className="space-y-2">
                                    <div className="text-xs font-semibold uppercase text-muted-foreground">Instrução para a IA</div>
                                    <Textarea
                                        value={issueAssistantInstruction}
                                        onChange={(e) => setIssueAssistantInstruction(e.target.value)}
                                        className="min-h-[100px]"
                                        placeholder="Descreva exatamente o que deseja que a IA faça (sem inventar conteúdo)."
                                    />
                                    <div className="text-[11px] text-muted-foreground">
                                        Dica: peça para inserir a referência na seção sugerida e evitar duplicação.
                                    </div>
                                </div>
                            </div>
                        );
                    })()}

                    <DialogFooter className="gap-2 sm:gap-2">
                        <Button
                            variant="outline"
                            onClick={() => {
                                setIssueAssistantOpen(false);
                            }}
                        >
                            Fechar
                        </Button>
                        {issueAssistantIssue && (
                            <Button
                                variant="outline"
                                onClick={() => {
                                    const issue = issueAssistantIssue;
                                    if (!issue?.id) {
                                        setIssueAssistantOpen(false);
                                        return;
                                    }
                                    setAuditIssues((prev) => prev.filter((i: any) => i?.id !== issue.id));
                                    setSelectedIssues((prev) => {
                                        const next = new Set(prev);
                                        next.delete(issue.id);
                                        return next;
                                    });
                                    setIssueAssistantOpen(false);
                                    toast.success('Issue marcado como já resolvido no texto.');
                                }}
                            >
                                Marcar como já consta
                            </Button>
                        )}
                        <Button
                            onClick={async () => {
                                const issue = issueAssistantIssue;
                                if (!issue) return;
                                if (!result) {
                                    toast.error('Sem conteúdo para revisar.');
                                    return;
                                }
                                const reference = getIssueReference(issue);
                                const suggestedSection = typeof issue?.suggested_section === 'string' ? issue.suggested_section.trim() : '';
                                const context = extractSectionFromMarkdown(result || '', suggestedSection, reference);
                                const hasRefAlready = Boolean(reference && normalizeForMatch(result || '').includes(normalizeForMatch(reference)));
                                if (hasRefAlready && !issueAssistantForce) {
                                    toast.info('A referência já aparece no texto. Marque como “já consta” ou force a prévia.');
                                    return;
                                }
                                const augmented = {
                                    ...issue,
                                    user_instruction: (issueAssistantInstruction || '').trim() || undefined,
                                    formatted_context: context.section || undefined,
                                };
                                setIssueAssistantOpen(false);
                                await applyHilIssues([augmented], 'Pré-visualizando correção (IA)');
                            }}
                            disabled={isApplyingFixes}
                        >
                            Pré-visualizar correção (IA)
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            <Dialog open={progressLogsOpen} onOpenChange={setProgressLogsOpen}>
                <DialogContent className="max-w-4xl">
                    <DialogHeader>
                        <DialogTitle>Logs do processamento</DialogTitle>
                        <DialogDescription>
                            Output em tempo real do servidor (útil para diagnosticar travamentos, falhas de diarização, etc.).
                        </DialogDescription>
                    </DialogHeader>
                    <div className="flex items-center justify-between gap-2">
                        <div className="text-xs text-muted-foreground">
                            {logs.length ? `${logs.length} linhas` : 'Sem logs ainda'}
                        </div>
                        <div className="flex items-center gap-2">
                            <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                onClick={async () => {
                                    try {
                                        await navigator.clipboard.writeText(plainLogsText || '');
                                        toast.success('Logs copiados.');
                                    } catch {
                                        toast.error('Não foi possível copiar os logs.');
                                    }
                                }}
                                disabled={!plainLogsText}
                            >
                                Copiar
                            </Button>
                            <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                onClick={() => setLogs([])}
                                disabled={logs.length === 0}
                            >
                                Limpar
                            </Button>
                        </div>
                    </div>
                    <div className="mt-3 rounded-md border bg-black/95 text-green-200 font-mono text-xs p-3 h-[60vh] overflow-y-auto">
                        {logs.length === 0 ? (
                            <div className="opacity-60">AGUARDANDO LOGS...</div>
                        ) : (
                            <pre className="whitespace-pre-wrap break-words">{plainLogsText}</pre>
                        )}
                    </div>
                </DialogContent>
            </Dialog>

            {hasActiveProgress && (
                <div className="fixed bottom-4 left-1/2 z-50 w-[min(960px,calc(100%-2rem))] -translate-x-1/2">
                    {progressDockMinimized ? (
                        <div className="flex justify-end">
                            <Button
                                type="button"
                                variant="outline"
                                className="bg-background/90 backdrop-blur"
                                onClick={() => setProgressDockMinimized(false)}
                            >
                                Progresso · {progressPercent}%
                            </Button>
                        </div>
                    ) : (
                        <div className="rounded-lg border bg-background/95 backdrop-blur shadow-lg p-3">
                            <div className="flex items-start gap-3">
                                <div className="flex-1 min-w-0">
                                    <div className="flex items-center justify-between gap-2">
                                        <div className="text-sm font-medium truncate">
                                            {progressMessage || (isProcessing ? 'Processando...' : 'Processo concluído')}
                                        </div>
                                        <div className="text-xs text-muted-foreground tabular-nums">
                                            {progressPercent}%
                                        </div>
                                    </div>
                                    <div className="mt-2 h-2 rounded-full bg-muted overflow-hidden">
                                        <div
                                            className="h-2 bg-primary transition-all duration-300 ease-out"
                                            style={{ width: `${Math.max(0, Math.min(100, progressPercent))}%` }}
                                        />
                                    </div>
                                    <div className="mt-2 flex items-center justify-between gap-2">
                                        <div className="text-[11px] text-muted-foreground">
                                            {progressStage ? `Etapa: ${progressStage}` : 'Etapa: —'}
                                            {etaSeconds !== null ? ` · ETA ${formatDuration(etaSeconds)}` : ''}
                                        </div>
                                        <div className="flex items-center gap-2">
                                            <Button
                                                type="button"
                                                variant="outline"
                                                size="sm"
                                                className="h-8"
                                                onClick={() => setProgressLogsOpen(true)}
                                                disabled={logs.length === 0}
                                            >
                                                Logs
                                            </Button>
                                            <Button
                                                type="button"
                                                variant="ghost"
                                                size="icon"
                                                className="h-8 w-8"
                                                onClick={() => setProgressDockMinimized(true)}
                                                title="Minimizar"
                                            >
                                                <X className="h-4 w-4" />
                                            </Button>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    )}
                </div>
            )}
        </div>

	        <Dialog open={layoutDialogOpen} onOpenChange={setLayoutDialogOpen}>
	            <DialogContent className="max-w-2xl">
	                <DialogHeader>
	                    <DialogTitle>Layout do documento</DialogTitle>
	                    <DialogDescription>
	                        Ajuste tema de tabelas, margens e cabeçalho/rodapé. Essas configurações afetam o preview e a exportação para Word.
	                    </DialogDescription>
	                </DialogHeader>

                <Tabs
                    value={layoutDialogTab}
                    onValueChange={(value) => setLayoutDialogTab(value as typeof layoutDialogTab)}
                    className="w-full"
                >
                    <TabsList className="grid w-full grid-cols-6">
                        <TabsTrigger value="page">Página</TabsTrigger>
                        <TabsTrigger value="header">Cabeçalho</TabsTrigger>
                        <TabsTrigger value="typography">Tipografia</TabsTrigger>
                        <TabsTrigger value="margins">Margens</TabsTrigger>
                        <TabsTrigger value="tables">Tabelas</TabsTrigger>
                        <TabsTrigger value="breaks">Seções</TabsTrigger>
                    </TabsList>

	                    <TabsContent value="page" className="mt-5">
	                        <div className="grid gap-4">
	                            <div className="flex items-center justify-between space-x-3 rounded-md border p-3">
	                                <Label htmlFor="doc-page-frame" className="flex flex-col space-y-1">
	                                    <span>Simular página (A4) no preview</span>
	                                    <span className="font-normal text-xs text-muted-foreground">
	                                        Centraliza e limita largura para leitura (apenas visual).
	                                    </span>
	                                </Label>
	                                <Switch
	                                    id="doc-page-frame"
	                                    checked={activeDocumentLayout.pageFrame}
	                                    onCheckedChange={(checked) => updateActiveLayout({ pageFrame: Boolean(checked) })}
	                                />
	                            </div>
	                        </div>
	                    </TabsContent>

	                    <TabsContent value="header" className="mt-5">
	                        <div className="grid gap-4">
	                            <div className="grid gap-3 md:grid-cols-2">
	                                <div className="grid gap-2">
	                                    <Label htmlFor="doc-header">Cabeçalho (opcional)</Label>
	                                    <Input
	                                        id="doc-header"
	                                        value={activeDocumentLayout.headerText}
	                                        onChange={(e) => updateActiveLayout({ headerText: e.target.value })}
	                                        placeholder="Ex.: Iudex — Apostila"
	                                    />
	                                    <p className="text-xs text-muted-foreground">
	                                        Se vazio, o Word usa automaticamente o nome do documento + modo.
	                                    </p>
	                                </div>
	                                <div className="grid gap-2">
	                                    <Label htmlFor="doc-footer">Rodapé (opcional)</Label>
	                                    <Input
	                                        id="doc-footer"
	                                        value={activeDocumentLayout.footerText}
	                                        onChange={(e) => updateActiveLayout({ footerText: e.target.value })}
	                                        placeholder="Ex.: Confidencial"
	                                    />
	                                    <p className="text-xs text-muted-foreground">
	                                        A paginação é mantida automaticamente no Word.
	                                    </p>
	                                </div>
	                            </div>

	                            <div className="flex items-center justify-between space-x-3 rounded-md border p-3">
	                                <Label htmlFor="doc-show-hf" className="flex flex-col space-y-1">
	                                    <span>Mostrar cabeçalho/rodapé no preview</span>
	                                    <span className="font-normal text-xs text-muted-foreground">
	                                        Apenas visual; não altera o RAW.
	                                    </span>
	                                </Label>
	                                <Switch
	                                    id="doc-show-hf"
	                                    checked={activeDocumentLayout.showHeaderFooter}
	                                    onCheckedChange={(checked) => updateActiveLayout({ showHeaderFooter: Boolean(checked) })}
	                                />
	                            </div>
	                        </div>
	                    </TabsContent>

	                    <TabsContent value="typography" className="mt-5">
	                        <div className="grid gap-4">
	                            <div className="grid gap-2">
	                                <Label>Fonte base</Label>
	                                <select
	                                    className="flex h-10 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
	                                    value={activeDocumentLayout.fontFamily}
	                                    onChange={(e) => updateActiveLayout({ fontFamily: e.target.value })}
	                                >
	                                    <option value="">Padrão do tema</option>
	                                    <option value="Arial">Arial</option>
	                                    <option value="Calibri">Calibri</option>
	                                    <option value="Times New Roman">Times New Roman</option>
	                                    <option value="Georgia">Georgia</option>
	                                    <option value="Inter">Inter</option>
	                                    <option value="Roboto">Roboto</option>
	                                </select>
	                            </div>
	                            <div className="grid gap-3 md:grid-cols-3">
	                                <div className="grid gap-2">
	                                    <Label>Tamanho da fonte (px)</Label>
	                                    <select
	                                        className="flex h-10 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
	                                        value={activeDocumentLayout.fontSize}
	                                        onChange={(e) => updateActiveLayout({ fontSize: Number(e.target.value) })}
	                                    >
	                                        {[11, 12, 13, 14, 15, 16, 18].map((size) => (
	                                            <option key={size} value={size}>
	                                                {size}px
	                                            </option>
	                                        ))}
	                                    </select>
	                                </div>
	                                <div className="grid gap-2">
	                                    <Label>Entrelinhas</Label>
	                                    <select
	                                        className="flex h-10 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
	                                        value={activeDocumentLayout.lineHeight}
	                                        onChange={(e) => updateActiveLayout({ lineHeight: Number(e.target.value) })}
	                                    >
	                                        {[1.15, 1.3, 1.5, 1.8, 2].map((lh) => (
	                                            <option key={lh} value={lh}>
	                                                {lh}
	                                            </option>
	                                        ))}
	                                    </select>
	                                </div>
	                                <div className="grid gap-2">
	                                    <Label>Espaçamento entre parágrafos</Label>
	                                    <select
	                                        className="flex h-10 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
	                                        value={activeDocumentLayout.paragraphSpacing}
	                                        onChange={(e) => updateActiveLayout({ paragraphSpacing: Number(e.target.value) })}
	                                    >
	                                        {[0, 8, 12, 16, 20, 24].map((spacing) => (
	                                            <option key={spacing} value={spacing}>
	                                                {spacing}px
	                                            </option>
	                                        ))}
	                                    </select>
	                                </div>
	                            </div>
	                            <p className="text-xs text-muted-foreground">
	                                Essas opções controlam a tipografia global do preview e do DOCX, sem alterar o RAW.
	                            </p>
	                        </div>
	                    </TabsContent>

	                    <TabsContent value="margins" className="mt-5">
	                        <div className="grid gap-2">
	                            <Label>Margens (preview e DOCX)</Label>
	                            <select
	                                className="flex h-10 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
	                                value={activeDocumentLayout.margins}
	                                onChange={(e) => updateActiveLayout({ margins: e.target.value as DocumentLayout['margins'] })}
	                            >
	                                <option value="compact">Compacta</option>
	                                <option value="normal">Normal</option>
	                                <option value="wide">Ampla</option>
	                            </select>
	                        </div>
	                    </TabsContent>

	                    <TabsContent value="tables" className="mt-5">
	                        <div className="grid gap-2">
	                            <Label>Tema de tabelas</Label>
	                            <select
	                                className="flex h-10 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
	                                value={activeDocumentTheme}
	                                onChange={(e) => setActiveTheme(e.target.value)}
	                            >
	                                {DOCUMENT_THEMES.map((theme) => (
	                                    <option key={theme.id} value={theme.id}>
	                                        {theme.title}
	                                    </option>
	                                ))}
	                            </select>
	                            <p className="text-xs text-muted-foreground">
	                                {DOCUMENT_THEMES.find((t) => t.id === activeDocumentTheme)?.description
	                                    || 'Define o estilo visual do documento (principalmente tabelas).'}
	                            </p>
	                        </div>
	                    </TabsContent>

	                    <TabsContent value="breaks" className="mt-5">
	                        <div className="grid gap-3">
	                            <p className="text-sm text-muted-foreground">
	                                Use quebras de página para separar seções no Word. Isso não altera o RAW e é
	                                exportado como nova página.
	                            </p>
	                            <div className="flex items-center justify-between rounded-md border p-3">
	                                <div className="space-y-1">
	                                    <div className="text-sm font-medium">Quebra de página</div>
	                                    <div className="text-xs text-muted-foreground">
	                                        Insere o marcador <code>{'<!-- PAGE_BREAK -->'}</code> no documento.
	                                    </div>
	                                </div>
	                                <Button variant="outline" size="sm" disabled={!hasOutput} onClick={handleInsertPageBreak}>
	                                    <Scissors className="mr-2 h-4 w-4" />
	                                    Inserir
	                                </Button>
	                            </div>
	                        </div>
	                    </TabsContent>
	                </Tabs>

	                <DialogFooter className="gap-2">
	                    <Button variant="outline" onClick={() => setLayoutDialogOpen(false)}>
	                        Fechar
	                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
        </>
    );
}
