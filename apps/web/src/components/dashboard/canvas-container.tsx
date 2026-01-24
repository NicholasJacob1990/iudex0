'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useCanvasStore, useChatStore } from '@/stores';
import type { CanvasTab } from '@/stores/canvas-store';
import { DocumentEditor } from '@/components/editor/document-editor';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
    X,
    Maximize2,
    Minimize2,
    Printer,
    Download,
    Copy,
    FileText,
    FileCode,
    FileType,
    AlertTriangle,
    Scale,
    ShieldCheck,
    Undo2,
    Redo2,
    Info
} from 'lucide-react';
import { cn } from '@/lib/utils';
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuLabel,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { toast } from 'sonner';
import { exportToDocx, exportToHtml, exportToTxt, handlePrint } from '@/lib/export-utils';
import { parseMarkdownToHtmlSync } from '@/lib/markdown-parser';
import { DocumentVersionBadge } from './document-version-badge';
import { DiffConfirmDialog } from './diff-confirm-dialog';
import { AuditIssuesPanel } from './audit-issues-panel';
import { MarkdownPreview } from './markdown-editor-panel';
import { Badge } from '@/components/ui/badge';
import { ApplyTemplateDialog } from './apply-template-dialog';
import { ProcessView } from './process-view';
import type { HilIssue } from '@/lib/preventive-hil';
import { JobQualityPanel, JobQualityPipelinePanel } from '@/components/dashboard/quality';
import { QualityGatePanel } from './quality-gate-panel';
import { HilChecklistPanel } from './hil-checklist-panel';

function injectFootnoteRefsIntoHtml(html: string): string {
    const raw = String(html || '');
    if (!raw) return raw;
    if (typeof window === 'undefined') return raw;
    if (!/\[\d{1,3}\]/.test(raw)) return raw;
    if (raw.includes('data-footnote-ref')) return raw;

    try {
        const parser = new DOMParser();
        const doc = parser.parseFromString(raw, 'text/html');

        const headingCandidates = Array.from(doc.querySelectorAll('h1,h2,h3,h4,h5,h6,p'));
        const refsStart = headingCandidates.find((el) => {
            const txt = (el.textContent || '').trim();
            return /^(referências|referencias|references|fontes)\b/i.test(txt);
        }) || null;

        const shouldSkipNode = (node: Node) => {
            const el = (node as any)?.parentElement as HTMLElement | null;
            if (!el) return false;
            if (el.closest('code,pre,a,script,style')) return true;
            if (refsStart) {
                const pos = refsStart.compareDocumentPosition(node);
                const isAfter =
                    Boolean(pos & Node.DOCUMENT_POSITION_FOLLOWING)
                    || refsStart === node
                    || refsStart.contains(node);
                if (isAfter) return true;
            }
            return false;
        };

        const walker = doc.createTreeWalker(doc.body, NodeFilter.SHOW_TEXT);
        const targets: Text[] = [];
        let current = walker.nextNode();
        while (current) {
            const txt = current.nodeValue || '';
            if (txt && /\[\d{1,3}\]/.test(txt) && !shouldSkipNode(current)) {
                targets.push(current as Text);
            }
            current = walker.nextNode();
        }

        for (const textNode of targets) {
            const value = textNode.nodeValue || '';
            const re = /\[(\d{1,3})\]/g;
            let m: RegExpExecArray | null;
            let lastIdx = 0;
            const frag = doc.createDocumentFragment();

            while ((m = re.exec(value)) !== null) {
                const startIdx = m.index;
                const endIdx = startIdx + m[0].length;
                const num = m[1];

                if (startIdx > lastIdx) {
                    frag.appendChild(doc.createTextNode(value.slice(lastIdx, startIdx)));
                }

                const span = doc.createElement('span');
                span.setAttribute('data-footnote-ref', String(num));
                span.textContent = String(num);
                frag.appendChild(span);

                lastIdx = endIdx;
            }

            if (lastIdx < value.length) {
                frag.appendChild(doc.createTextNode(value.slice(lastIdx)));
            }

            textNode.parentNode?.replaceChild(frag, textNode);
        }

        return doc.body.innerHTML || raw;
    } catch (e) {
        console.warn('Failed to inject footnote refs:', e);
        return raw;
    }
}

const extractAuditIssuesPayload = (metadata: any) => {
    const candidates = [
        metadata?.audit_issues,
        metadata?.audit?.audit_issues,
        metadata?.audit?.issues,
        metadata?.audit?.hil_issues,
        metadata?.hil_issues,
        metadata?.audit?.issues_detected,
        metadata?.issues,
    ];
    for (const candidate of candidates) {
        if (Array.isArray(candidate)) return candidate;
    }
    return null;
};

const normalizeHilIssue = (issue: any, index: number): HilIssue => {
    const base = issue && typeof issue === 'object' ? issue : { description: String(issue) };
    const id = String(
        base.id
        || base.fingerprint
        || base.key
        || base.issue_id
        || `${base.type || base.title || 'issue'}-${index}`
    );
    const fixTypeRaw = String(base.fix_type || base.category || base.kind || '').toLowerCase();
    const fixType = fixTypeRaw.includes('struct') || fixTypeRaw.includes('estrut')
        ? 'structural'
        : base.fix_type || base.category || base.kind;
    return {
        ...base,
        id,
        type: base.type || base.title || base.kind || 'issue',
        fix_type: fixType,
    };
};

const adaptAuditIssuesFromMetadata = (metadata: any) => {
    const payload = extractAuditIssuesPayload(metadata);
    if (!Array.isArray(payload)) return { issues: [] as HilIssue[], hasSource: false };
    return {
        issues: payload.map((issue, index) => normalizeHilIssue(issue, index)),
        hasSource: true,
    };
};

const hasRawForHilFromMetadata = (metadata: any) => {
    const raw = metadata?.raw_content || metadata?.raw_document || metadata?.raw_text || metadata?.raw;
    if (typeof raw === 'string') return raw.trim().length > 0;
    return Boolean(raw);
};

export function CanvasContainer({ mode = 'full' }: { mode?: 'full' | 'chat' }) {
    const {
        state, activeTab, content, metadata, costInfo, hideCanvas, toggleExpanded, setActiveTab,
        undo, redo, canUndo, canRedo, contentHistory, historyIndex,
        pendingSuggestions, acceptSuggestion, rejectSuggestion, acceptAllSuggestions, rejectAllSuggestions,
        acceptSuggestionsByIds, rejectSuggestionsByIds,
        setContent,
        highlightedText,
        lastEditedAt,
        outline
    } = useCanvasStore();
    const { reviewData, jobEvents, jobOutline } = useChatStore();

    useEffect(() => {
        if (mode === 'chat' && activeTab !== 'editor') {
            setActiveTab('editor');
        }
    }, [mode, activeTab, setActiveTab]);

    const [diffDialogOpen, setDiffDialogOpen] = useState(false);
    const [currentSuggestion, setCurrentSuggestion] = useState<typeof pendingSuggestions[0] | null>(null);
    const [hideEditBanner, setHideEditBanner] = useState(false);
    const [now, setNow] = useState(() => Date.now());
    const [applyTemplateOpen, setApplyTemplateOpen] = useState(false);
    const [selectedAuditIssueIds, setSelectedAuditIssueIds] = useState<Set<string>>(new Set());

    const isExpanded = state === 'expanded';
    const hasDocument = Boolean((content || '').trim());
    const totalTokensRaw = costInfo?.total_tokens;
    const pointsTotalRaw = costInfo?.points_total;
    const totalTokens = Number.isFinite(Number(totalTokensRaw)) ? Number(totalTokensRaw) : null;
    const pointsTotal = Number.isFinite(Number(pointsTotalRaw)) ? Number(pointsTotalRaw) : null;

    const sectionLabelForSuggestion = useCallback((rawContent: string, fromIndex: number) => {
        const contentTo = rawContent.slice(0, Math.max(0, fromIndex));
        if (!contentTo.trim()) return 'Sem seção';

        // Prefer store outline when available (deterministic)
        const outlined = (outline || []).filter((s) => typeof s.from === 'number')
            .sort((a, b) => Number(a.from) - Number(b.from));
        if (outlined.length) {
            let chosen = outlined[0];
            for (const sec of outlined) {
                if (Number(sec.from) <= fromIndex) {
                    chosen = sec;
                } else {
                    break;
                }
            }
            return chosen?.title || 'Sem seção';
        }

        // HTML heuristic: find nearest preceding <h1..h6>
        const isHtml = /<(p|h1|h2|h3|h4|h5|h6|div|ul|ol|li|table|thead|tbody|tr|td|th|blockquote|strong|em|span)(\s|>)/i.test(
            rawContent.trim()
        );
        if (isHtml) {
            // Walk backwards to find a heading start, then extract its inner text.
            let pos = contentTo.lastIndexOf('<h');
            while (pos >= 0) {
                const level = rawContent[pos + 2];
                if (level >= '1' && level <= '6') {
                    const gt = rawContent.indexOf('>', pos);
                    const end = rawContent.indexOf(`</h${level}>`, pos);
                    if (gt !== -1 && end !== -1 && end < fromIndex) {
                        const inner = rawContent.slice(gt + 1, end);
                        const text = inner.replace(/<[^>]+>/g, '').replace(/\s+/g, ' ').trim();
                        if (text) return text.length > 60 ? `${text.slice(0, 60)}…` : text;
                    }
                }
                pos = contentTo.lastIndexOf('<h', Math.max(0, pos - 1));
            }
            return 'Sem seção';
        }

        // Markdown heuristic: nearest preceding "# Heading"
        const matches = contentTo.match(/(^|\n)(#{1,6})\s+([^\n]+)/g);
        if (!matches?.length) return 'Sem seção';
        const last = matches[matches.length - 1];
        const line = last.replace(/^[\s\S]*\n/, '').trim();
        const title = line.replace(/^#{1,6}\s+/, '').trim();
        if (!title) return 'Sem seção';
        return title.length > 60 ? `${title.slice(0, 60)}…` : title;
    }, [outline]);

    const suggestionGroups = useMemo(() => {
        if (!pendingSuggestions.length) return [];
        const groups = new Map<string, string[]>();
        for (const s of pendingSuggestions) {
            const label = sectionLabelForSuggestion(content || '', s.from);
            const current = groups.get(label) || [];
            current.push(s.id);
            groups.set(label, current);
        }
        return Array.from(groups.entries())
            .map(([section, ids]) => ({ section, ids, count: ids.length }))
            .sort((a, b) => b.count - a.count || a.section.localeCompare(b.section));
    }, [content, pendingSuggestions, sectionLabelForSuggestion]);

    const { issues: baseAuditIssues, hasSource: hasAuditIssuesSource } = useMemo(
        () => adaptAuditIssuesFromMetadata(metadata),
        [metadata]
    );
    const combinedAuditIssues = baseAuditIssues;
    const hasRawForHil = hasRawForHilFromMetadata(metadata);
    const auditIssuesModelLabel = String(metadata?.model || metadata?.audit?.model_used || 'IA');
    const isAuditOutdated = Boolean(metadata?.audit_outdated || metadata?.audit?.is_outdated || metadata?.audit?.outdated);
    const showAuditIssuesPanel = hasAuditIssuesSource || combinedAuditIssues.length > 0;
    const hilRiskLevel = useMemo(() => {
        const metaCandidate =
            metadata?.hil_risk_level
            || metadata?.quality?.hil_risk_level
            || metadata?.quality_payload?.hil_risk_level
            || metadata?.qualityPayload?.hil_risk_level
            || null;
        if (typeof metaCandidate === 'string' && metaCandidate.trim()) return metaCandidate.trim().toUpperCase();

        for (let i = (jobEvents?.length || 0) - 1; i >= 0; i--) {
            const e = jobEvents[i];
            if (e?.type !== 'hil_evaluated') continue;
            const levelRaw = typeof e?.hil_risk_level === 'string' ? e.hil_risk_level : '';
            if (levelRaw.trim()) return levelRaw.trim().toUpperCase();
            const hilLevel = typeof e?.hil_level === 'string' ? e.hil_level : '';
            if (hilLevel === 'critical') return 'HIGH';
            if (hilLevel === 'review') return 'MED';
            const requiresHil = typeof e?.requires_hil === 'boolean' ? e.requires_hil : false;
            return requiresHil ? 'MED' : 'LOW';
        }
        return null;
    }, [metadata, jobEvents]);
    const hilRiskVariant = hilRiskLevel === 'HIGH' ? 'destructive' : hilRiskLevel === 'MED' ? 'secondary' : 'outline';

    useEffect(() => {
        const tick = window.setInterval(() => setNow(Date.now()), 30_000);
        return () => window.clearInterval(tick);
    }, []);

    useEffect(() => {
        if (combinedAuditIssues.length === 0) {
            setSelectedAuditIssueIds(new Set());
            return;
        }
        setSelectedAuditIssueIds((prev) => {
            if (!prev.size) return prev;
            const available = new Set(combinedAuditIssues.map((issue) => issue.id));
            const next = new Set<string>();
            prev.forEach((id) => {
                if (available.has(id)) next.add(id);
            });
            return next;
        });
    }, [combinedAuditIssues]);

    const formatRelative = (timestamp: number | null) => {
        if (!timestamp) return '—';
        const diffMs = Math.max(0, now - timestamp);
        const diffMin = Math.floor(diffMs / 60000);
        if (diffMin <= 0) return 'agora';
        if (diffMin === 1) return 'há 1 min';
        if (diffMin < 60) return `há ${diffMin} min`;
        const diffHr = Math.floor(diffMin / 60);
        if (diffHr === 1) return 'há 1 hora';
        if (diffHr < 24) return `há ${diffHr} horas`;
        const diffDay = Math.floor(diffHr / 24);
        return diffDay === 1 ? 'há 1 dia' : `há ${diffDay} dias`;
    };

    const toggleAuditIssue = useCallback((id: string) => {
        setSelectedAuditIssueIds((prev) => {
            const next = new Set(prev);
            if (next.has(id)) {
                next.delete(id);
            } else {
                next.add(id);
            }
            return next;
        });
    }, []);

    // O TipTap consome HTML. O backend pode devolver Markdown (especialmente em geração de documentos),
    // então fazemos conversão + sanitização aqui quando o conteúdo não parece HTML.
    const editorHtml = useMemo(() => {
        const raw = (content || '').trim();
        if (!raw) return '';

        // Heurística: só considera "HTML" se tiver tags típicas de documento (evita falso positivo com "<PRIVATE_PERSON>")
        const looksLikeHtml = /<(p|h1|h2|h3|h4|h5|h6|div|ul|ol|li|table|thead|tbody|tr|td|th|blockquote|strong|em|span)(\s|>)/i.test(
            raw
        );
        if (looksLikeHtml) return injectFootnoteRefsIntoHtml(raw);

        try {
            return injectFootnoteRefsIntoHtml(parseMarkdownToHtmlSync(raw));
        } catch (e) {
            console.error('Error parsing markdown for canvas:', e);
            return raw;
        }
    }, [content]);

    const hasDivergence = useMemo(() => {
        if (metadata?.has_any_divergence) return true;
        const summary = String(metadata?.divergence_summary || '').toLowerCase();
        if (!summary) return false;
        return !summary.includes('consenso');
    }, [metadata]);

    const hasAuditFailed = useMemo(() => {
        const status = metadata?.audit?.status || metadata?.audit_status || metadata?.audit?.audit_status;
        return String(status || '').toLowerCase() === 'reprovado';
    }, [metadata]);

    const committeeReport = metadata?.committee_review_report
        || (reviewData?.checkpoint === 'final' ? reviewData?.committee_review_report : null);
    const hasCommitteeDisagreement = Boolean(committeeReport?.score_disagreement);

    const pendingSignals = useMemo(() => {
        const signals: { label: string; variant: 'secondary' | 'destructive' | 'outline' }[] = [];
        if (hasCommitteeDisagreement) {
            signals.push({ label: 'Divergência extrema', variant: 'destructive' });
        }
        if (hasAuditFailed) {
            signals.push({ label: 'Auditoria reprovada', variant: 'destructive' });
        }
        if (reviewData) {
            signals.push({ label: 'HIL pendente', variant: 'secondary' });
        }
        if (hasDivergence) {
            signals.push({ label: 'Divergências', variant: 'outline' });
        }
        return signals;
    }, [hasCommitteeDisagreement, hasAuditFailed, hasDivergence, reviewData]);

    // Early return AFTER all hooks
    if (state === 'hidden') {
        return null;
    }

    const handleCopyContent = () => {
        // Remove HTML tags para copiar apenas texto
        const tempDiv = document.createElement('div');
        tempDiv.innerHTML = editorHtml;
        const text = tempDiv.textContent || tempDiv.innerText || '';

        navigator.clipboard.writeText(text);
        toast.success('Conteúdo copiado para a área de transferência');
    };

    return (
        <div
            className={cn(
                'relative flex h-full w-full flex-col bg-background transition-all duration-300 font-google-sans-text'
            )}
        >
            {/* Control Bar */}
            <div className="flex items-center justify-between border-b border-outline/30 bg-muted/30 px-4 py-2">
                <div className="flex items-center gap-3">
                    <DocumentVersionBadge documentName={metadata?.title || 'Documento'} />
                    <span className="hidden sm:inline text-[10px] uppercase tracking-wide text-muted-foreground font-semibold">
                        Editado {formatRelative(lastEditedAt)}
                    </span>
                    {pendingSignals.length > 0 && (
                        <div className="flex flex-wrap items-center gap-1">
                            {pendingSignals.map((signal) => (
                                <Badge
                                    key={signal.label}
                                    variant={signal.variant}
                                    className="h-6 px-2 text-[10px] uppercase tracking-wide"
                                >
                                    {signal.label}
                                </Badge>
                            ))}
                        </div>
                    )}

                    {/* Pending Suggestions Indicator */}
                    {pendingSuggestions.length > 0 && (
                        <div className="flex items-center gap-2">
                            <Button
                                variant="outline"
                                size="sm"
                                className="h-7 gap-1.5 border-orange-200 bg-orange-50 text-orange-700 hover:bg-orange-100"
                                onClick={() => {
                                    const suggestion = pendingSuggestions[0];
                                    setCurrentSuggestion(suggestion);
                                    setDiffDialogOpen(true);
                                }}
                            >
                                <AlertTriangle className="h-3.5 w-3.5" />
                                {pendingSuggestions.length} sugestão{pendingSuggestions.length > 1 ? 'ões' : ''} pendente{pendingSuggestions.length > 1 ? 's' : ''}
                            </Button>
                            <Button
                                variant="ghost"
                                size="sm"
                                className="h-7 text-[11px]"
                                onClick={() => {
                                    const { applied, skipped } = acceptAllSuggestions();
                                    if (!applied) {
                                        toast.info('Nenhuma sugestão aplicada.');
                                        return;
                                    }
                                    if (skipped) {
                                        toast.warning(`Aplicadas ${applied}. ${skipped} ficaram pendentes (overlap).`);
                                    } else {
                                        toast.success(`Aplicadas ${applied} sugestões.`);
                                    }
                                }}
                                title="Aplicar todas as sugestões (quando não houver overlap)"
                            >
                                Aplicar tudo
                            </Button>
                            <Button
                                variant="ghost"
                                size="sm"
                                className="h-7 text-[11px] text-muted-foreground hover:text-destructive"
                                onClick={() => {
                                    const count = rejectAllSuggestions();
                                    toast.info(`${count} sugestão${count > 1 ? 'ões' : ''} rejeitada${count > 1 ? 's' : ''}.`);
                                }}
                                title="Rejeitar todas as sugestões"
                            >
                                Rejeitar tudo
                            </Button>

                            <DropdownMenu>
                                <DropdownMenuTrigger asChild>
                                    <Button
                                        variant="ghost"
                                        size="sm"
                                        className="h-7 text-[11px]"
                                        title="Gerenciar sugestões por seção"
                                    >
                                        Por seção
                                    </Button>
                                </DropdownMenuTrigger>
                                <DropdownMenuContent align="start" className="w-[320px]">
                                    <DropdownMenuLabel>Sugestões por seção</DropdownMenuLabel>
                                    <DropdownMenuSeparator />
                                    {suggestionGroups.length ? (
                                        suggestionGroups.slice(0, 12).map((group) => (
                                            <DropdownMenuItem
                                                key={group.section}
                                                className="flex items-center justify-between gap-3"
                                                onSelect={(e) => e.preventDefault()}
                                            >
                                                <div className="min-w-0">
                                                    <div className="truncate font-medium text-xs">{group.section}</div>
                                                    <div className="text-[10px] text-muted-foreground">{group.count} sugestão{group.count > 1 ? 'ões' : ''}</div>
                                                </div>
                                                <div className="flex items-center gap-1">
                                                    <Button
                                                        variant="outline"
                                                        size="sm"
                                                        className="h-6 px-2 text-[10px]"
                                                        onClick={() => {
                                                            const { applied, skipped } = acceptSuggestionsByIds(group.ids);
                                                            if (!applied) {
                                                                toast.info('Nenhuma sugestão aplicada.');
                                                                return;
                                                            }
                                                            if (skipped) {
                                                                toast.warning(`Seção: aplicadas ${applied}. ${skipped} ficaram pendentes (overlap).`);
                                                            } else {
                                                                toast.success(`Seção: aplicadas ${applied} sugestões.`);
                                                            }
                                                        }}
                                                    >
                                                        Aplicar
                                                    </Button>
                                                    <Button
                                                        variant="ghost"
                                                        size="sm"
                                                        className="h-6 px-2 text-[10px] text-muted-foreground hover:text-destructive"
                                                        onClick={() => {
                                                            const count = rejectSuggestionsByIds(group.ids);
                                                            toast.info(`Seção: ${count} rejeitada${count > 1 ? 's' : ''}.`);
                                                        }}
                                                    >
                                                        Rejeitar
                                                    </Button>
                                                </div>
                                            </DropdownMenuItem>
                                        ))
                                    ) : (
                                        <DropdownMenuItem disabled>Nenhuma sugestão.</DropdownMenuItem>
                                    )}
                                    {suggestionGroups.length > 12 && (
                                        <>
                                            <DropdownMenuSeparator />
                                            <DropdownMenuItem disabled className="text-[10px] text-muted-foreground">
                                                Mostrando 12 seções (há mais).
                                            </DropdownMenuItem>
                                        </>
                                    )}
                                </DropdownMenuContent>
                            </DropdownMenu>
                        </div>
                    )}
                </div>

                <div className="flex items-center gap-1">
                    {/* Undo/Redo Buttons - Granular AI History */}
                    {contentHistory.length > 0 && (
                        <div className="mr-2 flex items-center gap-1 border-r border-outline/20 pr-2">
                            <Button
                                variant="ghost"
                                size="icon"
                                onClick={undo}
                                disabled={!canUndo()}
                                className="h-7 w-7 hover:bg-muted disabled:opacity-30"
                                title={`Desfazer (${historyIndex}/${contentHistory.length - 1})`}
                            >
                                <Undo2 className="h-4 w-4" />
                            </Button>
                            <Button
                                variant="ghost"
                                size="icon"
                                onClick={redo}
                                disabled={!canRedo()}
                                className="h-7 w-7 hover:bg-muted disabled:opacity-30"
                                title="Refazer"
                            >
                                <Redo2 className="h-4 w-4" />
                            </Button>
                        </div>
                    )}
                    {/* Action Buttons */}
                    <div className="mr-2 flex items-center gap-1 border-r border-outline/20 pr-2">
                        <Button
                            variant="outline"
                            size="sm"
                            className="h-7 gap-1.5 text-[11px]"
                            type="button"
                            onClick={(e) => {
                                // Protege contra qualquer click handler acima/overlay e evita submit acidental
                                e.preventDefault();
                                e.stopPropagation();
                                setApplyTemplateOpen(true);
                            }}
                            title="Aplicar template DOCX (gera um arquivo para download)"
                        >
                            <FileText className="h-3.5 w-3.5" />
                            Template DOCX
                        </Button>
                        <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => handlePrint(content)}
                            className="h-7 w-7 hover:bg-muted"
                            title="Imprimir"
                        >
                            <Printer className="h-4 w-4" />
                        </Button>

                        <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => {
                                const auditText =
                                    mode === 'chat'
                                        ? undefined
                                        : (metadata?.audit?.audit_report_markdown || metadata?.audit?.markdown || metadata?.divergences);
                                exportToDocx(content, 'Minuta-Iudex', auditText);
                            }}
                            className="h-7 w-7 hover:bg-muted"
                            title="Exportar Word (.docx)"
                        >
                            <FileType className="h-4 w-4" />
                        </Button>

                        <Button
                            variant="ghost"
                            size="icon"
                            onClick={handleCopyContent}
                            className="h-7 w-7 hover:bg-muted"
                            title="Copiar texto"
                        >
                            <Copy className="h-4 w-4" />
                        </Button>

                        <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                                <Button
                                    variant="ghost"
                                    size="icon"
                                    className="h-7 w-7 hover:bg-muted"
                                    title="Exportar"
                                >
                                    <Download className="h-4 w-4" />
                                </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end">
                                <DropdownMenuLabel>Exportar como</DropdownMenuLabel>
                                <DropdownMenuSeparator />
                                <DropdownMenuItem onClick={() => {
                                    const auditText =
                                        mode === 'chat'
                                            ? undefined
                                            : (metadata?.audit?.audit_report_markdown || metadata?.audit?.markdown || metadata?.divergences);
                                    exportToDocx(content, 'Minuta-Iudex', auditText);
                                }}>
                                    <FileType className="mr-2 h-4 w-4" />
                                    <span>{mode === 'chat' ? 'Word (.docx)' : 'Word (.docx) (+ Auditoria)'}</span>
                                </DropdownMenuItem>
                                <DropdownMenuItem onClick={() => exportToHtml(content, 'Minuta-Iudex')}>
                                    <FileCode className="mr-2 h-4 w-4" />
                                    <span>HTML</span>
                                </DropdownMenuItem>
                                <DropdownMenuItem onClick={() => exportToTxt(content, 'Minuta-Iudex')}>
                                    <FileText className="mr-2 h-4 w-4" />
                                    <span>Texto (.txt)</span>
                                </DropdownMenuItem>
                            </DropdownMenuContent>
                        </DropdownMenu>
                    </div>

                    <Button
                        variant="ghost"
                        size="icon"
                        onClick={toggleExpanded}
                        className="h-7 w-7 hover:bg-muted"
                        title={isExpanded ? 'Restaurar tamanho' : 'Expandir canvas'}
                    >
                        {isExpanded ? (
                            <Minimize2 className="h-4 w-4" />
                        ) : (
                            <Maximize2 className="h-4 w-4" />
                        )}
                    </Button>
                    <Button
                        variant="ghost"
                        size="icon"
                        onClick={hideCanvas}
                        className="h-7 w-7 hover:bg-destructive/10 hover:text-destructive"
                        title="Fechar canvas"
                    >
                        <X className="h-4 w-4" />
                    </Button>
                </div>
            </div>

            {/* Canvas Content */}
            <div className="flex-1 overflow-hidden flex flex-col">
                <Tabs value={activeTab} onValueChange={(value) => setActiveTab(value as CanvasTab)} className="flex-1 min-h-0 flex flex-col">
	                    <div className="px-4 border-b border-outline/20 bg-muted/10 h-10 flex items-center justify-between">
	                        <TabsList className="bg-transparent h-8 p-0 gap-4">
	                            <TabsTrigger value="editor" className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent px-2 h-full text-xs font-medium">Editor</TabsTrigger>
	                            {mode !== 'chat' && (
	                                <TabsTrigger value="process" className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent px-2 h-full text-xs font-medium">Relatório do Agente</TabsTrigger>
	                            )}
	                            {mode !== 'chat' && (
	                                <TabsTrigger value="audit" className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent px-2 h-full text-xs font-medium">
	                                    <span className="flex items-center gap-1">
	                                        <Scale className="h-3 w-3" />
	                                        Auditoria
	                                    </span>
	                                </TabsTrigger>
	                            )}
	                            {mode !== 'chat' && (
	                                <TabsTrigger value="quality" className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent px-2 h-full text-xs font-medium">
	                                    <span className="flex items-center gap-1">
	                                        <ShieldCheck className="h-3 w-3" />
	                                        Qualidade
	                                    </span>
	                                </TabsTrigger>
	                            )}
	                        </TabsList>

                        {/* Summary metrics in the bar */}
                        {metadata && (
                            <div className="hidden md:flex items-center gap-4 text-[10px] text-muted-foreground uppercase font-semibold">
                                <span>{metadata.model || 'AI'}</span>
                                <span>{metadata.latency?.toFixed(1)}s</span>
                                {totalTokens != null && <span>{totalTokens} tokens</span>}
                                {pointsTotal != null && <span>{pointsTotal} pontos</span>}
                            </div>
                        )}
                    </div>

                    <TabsContent value="editor" className="flex-1 overflow-auto p-8 bg-white m-0">
                        {hasDocument && !hideEditBanner && (
                            <div className="mb-4 flex items-start justify-between gap-3 rounded-xl border border-sky-200 bg-sky-50 px-4 py-3 text-xs text-sky-900">
                                <div className="flex items-start gap-2">
                                    <Info className="h-4 w-4 mt-0.5 text-sky-700" />
                                    <div>
                                        <span className="font-semibold">Este documento é editável.</span>{' '}
                                        A IA entende e preserva suas edições. Clique no texto para começar.
                                    </div>
                                </div>
                                <Button
                                    variant="ghost"
                                    size="sm"
                                    className="h-7 px-2 text-[11px]"
                                    onClick={() => setHideEditBanner(true)}
                                >
                                    Entendi
                                </Button>
                            </div>
                        )}
                        <DocumentEditor
                            content={editorHtml}
                            editable={true}
                            onChange={setContent}
                            highlightedText={highlightedText}
                        />
                    </TabsContent>
	                    {mode !== 'chat' && (
	                        <TabsContent value="process" className="flex-1 overflow-y-auto p-6 bg-white space-y-6 m-0">
	                            <ProcessView
	                                events={jobEvents}
	                                outline={jobOutline}
	                                metadata={metadata}
	                                costInfo={costInfo}
	                                reviewData={reviewData}
	                            />
	                        </TabsContent>
	                    )}
	
	                    {mode !== 'chat' && (
	                    <TabsContent value="audit" className="flex-1 overflow-y-auto p-6 bg-white space-y-6 m-0">
	                        {metadata?.audit ? (
	                            <>
                                {/* Audit Header */}
                                <div className="flex items-center gap-2 pb-4 border-b border-outline/10">
                                    <div className="h-10 w-10 rounded-full bg-indigo-50 flex items-center justify-center">
                                        <ShieldCheck className="h-5 w-5 text-indigo-600" />
                                    </div>
                                    <div>
                                        <h3 className="text-lg font-bold text-foreground">Compliance Jurídico</h3>
                                        <div className="flex items-center gap-2 flex-wrap">
                                            <p className="text-xs text-muted-foreground">
                                                Auditado em {metadata.audit.audit_date || 'Data desconhecida'} por {metadata.audit.model_used || 'IA'}
                                            </p>
                                            {hilRiskLevel && (
                                                <Badge variant={hilRiskVariant as any} className="text-[10px] h-5">
                                                    Risk: {hilRiskLevel}
                                                </Badge>
                                            )}
                                        </div>
                                    </div>
                                </div>

                                <QualityGatePanel events={jobEvents} />
                                <HilChecklistPanel events={jobEvents} metadata={metadata} className="pt-4 border-t border-outline/10" />

                                {/* Report Content */}
                                <div className="space-y-3 pt-4 border-t border-outline/10">
                                    <h4 className="text-sm font-bold flex items-center gap-2">
                                        <FileText className="h-4 w-4 text-gray-500" />
                                        Relatório de Conformidade
                                    </h4>
                                    <MarkdownPreview content={metadata.audit.audit_report_markdown || metadata.audit.markdown || ''} />
                                </div>

                                {/* Citations Analysis */}
                                {metadata.audit.citations && metadata.audit.citations.length > 0 && (
                                    <div className="space-y-3 pt-4 border-t border-outline/10">
                                        <h4 className="text-sm font-bold flex items-center gap-2">
                                            <Scale className="h-4 w-4 text-indigo-500" />
                                            Verificação de Citações (RAG)
                                        </h4>
                                        <div className="rounded-xl border border-outline/20 overflow-hidden">
                                            <table className="w-full text-xs">
                                                <thead className="bg-muted/30 text-muted-foreground font-medium">
                                                    <tr>
                                                        <th className="px-3 py-2 text-left">Citação</th>
                                                        <th className="px-3 py-2 text-left">Status</th>
                                                        <th className="px-3 py-2 text-left">Análise</th>
                                                    </tr>
                                                </thead>
                                                <tbody className="divide-y divide-outline/10">
                                                    {metadata.audit.citations.map((cit: any, i: number) => (
                                                        <tr key={i} className="hover:bg-muted/10">
                                                            <td className="px-3 py-2 font-mono text-blue-600">{cit.citation}</td>
                                                            <td className="px-3 py-2">
                                                                {cit.status === 'valid' && <span className="inline-flex items-center gap-1 text-green-600 bg-green-50 px-2 py-0.5 rounded-full ring-1 ring-inset ring-green-600/20">Válido</span>}
                                                                {cit.status === 'suspicious' && <span className="inline-flex items-center gap-1 text-orange-600 bg-orange-50 px-2 py-0.5 rounded-full ring-1 ring-inset ring-orange-600/20">Suspeito</span>}
                                                                {cit.status === 'hallucination' && <span className="inline-flex items-center gap-1 text-red-600 bg-red-50 px-2 py-0.5 rounded-full ring-1 ring-inset ring-red-600/20">Alucinação</span>}
                                                                {(cit.status === 'warning' || cit.status === 'not_found') && <span className="inline-flex items-center gap-1 text-yellow-600 bg-yellow-50 px-2 py-0.5 rounded-full ring-1 ring-inset ring-yellow-600/20">Verificar</span>}
                                                            </td>
                                                            <td className="px-3 py-2 text-muted-foreground">{cit.message}</td>
                                                        </tr>
                                                    ))}
                                                </tbody>
                                            </table>
                                        </div>
                                    </div>
                                )}

                            </>
                        ) : (
                            <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
                                <Scale className="h-12 w-12 mb-4 opacity-10" />
                                <p className="text-sm font-medium">Auditoria não disponível para este documento.</p>
                                <p className="text-xs">Gere o documento novamente com o Modo Agente ativo.</p>
                            </div>
                        )}

                        {showAuditIssuesPanel && (
                            <AuditIssuesPanel
                                issues={combinedAuditIssues}
                                selectedIssueIds={selectedAuditIssueIds}
                                selectedModelLabel={auditIssuesModelLabel}
                                hasRawForHil={hasRawForHil}
                                isAuditOutdated={isAuditOutdated}
                                readOnly
                                onToggleIssue={toggleAuditIssue}
                            />
                        )}
	                    </TabsContent>
	                    )}
	
	                    {mode !== 'chat' && (
	                    <TabsContent value="quality" className="flex-1 overflow-y-auto p-6 bg-white space-y-6 m-0">
	                        <div className="flex items-center gap-2 pb-4 border-b border-outline/10">
	                            <div className="h-10 w-10 rounded-full bg-emerald-50 flex items-center justify-center">
	                                <ShieldCheck className="h-5 w-5 text-emerald-600" />
                            </div>
                            <div>
                                <h3 className="text-lg font-bold text-foreground">Qualidade da Minuta</h3>
                                <p className="text-xs text-muted-foreground">Monitoramento estrutural e de pipeline</p>
                            </div>
                        </div>
                        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                            <div>
                                <JobQualityPipelinePanel events={jobEvents} />
                            </div>
                            <div>
                                <JobQualityPanel events={jobEvents} />
	                            </div>
	                        </div>
	                    </TabsContent>
	                    )}
	                </Tabs>
            </div>

            {/* Diff Confirm Dialog for AI Suggestions */}
            {currentSuggestion && (
                <DiffConfirmDialog
                    open={diffDialogOpen}
                    onOpenChange={setDiffDialogOpen}
                    title="Sugestão da IA"
                    description="A IA propôs as seguintes alterações. Revise cuidadosamente antes de aplicar."
                    original={currentSuggestion.original}
                    replacement={currentSuggestion.replacement}
                    affectedSection={currentSuggestion.label}
                    changeStats={{
                        paragraphsChanged: 1,
                        totalParagraphs: content.split('\n\n').length,
                        wordsAdded: currentSuggestion.replacement.split(/\s+/).length,
                        wordsRemoved: currentSuggestion.original.split(/\s+/).length,
                    }}
                    onAccept={() => {
                        acceptSuggestion(currentSuggestion.id);
                        setDiffDialogOpen(false);
                        setCurrentSuggestion(null);
                        toast.success('Sugestão aplicada!');
                    }}
                    onReject={() => {
                        rejectSuggestion(currentSuggestion.id);
                        setDiffDialogOpen(false);
                        setCurrentSuggestion(null);
                        toast.info('Sugestão rejeitada.');
                    }}
                />
            )}

            <ApplyTemplateDialog open={applyTemplateOpen} onOpenChange={setApplyTemplateOpen} />
        </div>
    );
}
