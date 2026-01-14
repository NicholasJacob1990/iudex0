'use client';

import { useEffect, useMemo, useState } from 'react';
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
    Bot,
    Brain,
    AlertTriangle,
    Scale,
    ShieldCheck,
    Undo2,
    Redo2,
    Check,
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
import { QualityPanel } from './quality-panel';
import { Badge } from '@/components/ui/badge';
import { ApplyTemplateDialog } from './apply-template-dialog';

export function CanvasContainer() {
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
    const { reviewData, currentChat } = useChatStore();

    const [diffDialogOpen, setDiffDialogOpen] = useState(false);
    const [currentSuggestion, setCurrentSuggestion] = useState<typeof pendingSuggestions[0] | null>(null);
    const [processTab, setProcessTab] = useState<'drafts' | 'divergences' | 'committee'>('drafts');
    const [hideEditBanner, setHideEditBanner] = useState(false);
    const [now, setNow] = useState(() => Date.now());
    const [applyTemplateOpen, setApplyTemplateOpen] = useState(false);

    const isExpanded = state === 'expanded';
    const hasDocument = Boolean((content || '').trim());
    const latestThinking = useMemo(() => {
        const messages = currentChat?.messages || [];
        for (let i = messages.length - 1; i >= 0; i -= 1) {
            const msg: any = messages[i];
            if (msg?.role !== 'assistant') continue;
            const text = typeof msg?.thinking === 'string'
                ? msg.thinking.trim()
                : typeof msg?.metadata?.thinking === 'string'
                    ? msg.metadata.thinking.trim()
                    : '';
            if (text) return text;
        }
        return '';
    }, [currentChat?.messages]);

    const sectionLabelForSuggestion = (rawContent: string, fromIndex: number) => {
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
    };

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
    }, [content, pendingSuggestions]);

    useEffect(() => {
        const tick = window.setInterval(() => setNow(Date.now()), 30_000);
        return () => window.clearInterval(tick);
    }, []);

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

    // O TipTap consome HTML. O backend pode devolver Markdown (especialmente em geração de documentos),
    // então fazemos conversão + sanitização aqui quando o conteúdo não parece HTML.
    const editorHtml = useMemo(() => {
        const raw = (content || '').trim();
        if (!raw) return '';

        // Heurística: só considera "HTML" se tiver tags típicas de documento (evita falso positivo com "<PRIVATE_PERSON>")
        const looksLikeHtml = /<(p|h1|h2|h3|h4|h5|h6|div|ul|ol|li|table|thead|tbody|tr|td|th|blockquote|strong|em|span)(\s|>)/i.test(
            raw
        );
        if (looksLikeHtml) return raw;

        try {
            return parseMarkdownToHtmlSync(raw);
        } catch (e) {
            console.error('Error parsing markdown for canvas:', e);
            return raw;
        }
    }, [content]);

    const qualityContent = useMemo(() => {
        const raw = (content || '').trim();
        if (!raw) return '';

        const looksLikeHtml = /<(p|h1|h2|h3|h4|h5|h6|div|ul|ol|li|table|thead|tbody|tr|td|th|blockquote|strong|em|span)(\s|>)/i.test(
            raw
        );
        if (!looksLikeHtml) return raw;
        if (typeof window === 'undefined') return raw;

        const normalizeWhitespace = (value: string) =>
            value.replace(/\s+/g, ' ').replace(/\u00a0/g, ' ').trim();

        const parser = new DOMParser();
        const doc = parser.parseFromString(raw, 'text/html');
        const blocks: string[] = [];

        const pushBlock = (value: string | string[]) => {
            if (Array.isArray(value)) {
                const cleaned = value.filter((line) => line.trim().length > 0);
                if (cleaned.length > 0) blocks.push(cleaned.join('\n'));
                return;
            }
            const cleaned = normalizeWhitespace(value);
            if (cleaned) blocks.push(cleaned);
        };

        const renderTable = (table: Element) => {
            const rows = Array.from(table.querySelectorAll('tr'));
            if (rows.length === 0) return;
            const lines: string[] = [];
            rows.forEach((row, index) => {
                const cells = Array.from(row.querySelectorAll('th,td')).map((cell) =>
                    normalizeWhitespace(cell.textContent || '')
                );
                if (cells.length === 0) return;
                lines.push(`| ${cells.join(' | ')} |`);
                if (index === 0) {
                    lines.push(`| ${cells.map(() => '---').join(' | ')} |`);
                }
            });
            pushBlock(lines);
        };

        const renderList = (list: Element, ordered: boolean) => {
            const items = Array.from(list.querySelectorAll('li'));
            if (items.length === 0) return;
            const lines = items.map((item, idx) => {
                const text = normalizeWhitespace(item.textContent || '');
                if (!text) return '';
                const prefix = ordered ? `${idx + 1}.` : '-';
                return `${prefix} ${text}`;
            }).filter(Boolean);
            pushBlock(lines);
        };

        const processElement = (element: Element) => {
            const tag = element.tagName.toLowerCase();
            if (tag === 'h1' || tag === 'h2' || tag === 'h3' || tag === 'h4' || tag === 'h5' || tag === 'h6') {
                const level = parseInt(tag.replace('h', ''), 10) || 1;
                const text = normalizeWhitespace(element.textContent || '');
                if (text) pushBlock(`${'#'.repeat(Math.min(level, 6))} ${text}`);
                return;
            }
            if (tag === 'p') {
                pushBlock(element.textContent || '');
                return;
            }
            if (tag === 'blockquote') {
                const text = normalizeWhitespace(element.textContent || '');
                if (text) pushBlock(`> ${text}`);
                return;
            }
            if (tag === 'table') {
                renderTable(element);
                return;
            }
            if (tag === 'ul') {
                renderList(element, false);
                return;
            }
            if (tag === 'ol') {
                renderList(element, true);
                return;
            }
            Array.from(element.children).forEach(processElement);
        };

        Array.from(doc.body.children).forEach(processElement);

        if (blocks.length === 0) {
            return normalizeWhitespace(doc.body.textContent || '');
        }

        return blocks.join('\n\n');
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
    const committeeScore = Number.isFinite(Number(committeeReport?.score))
        ? Number(committeeReport?.score)
        : null;
    const committeeReviews = useMemo(() => {
        const reviews = committeeReport?.individual_reviews;
        if (!reviews || typeof reviews !== 'object') return [];
        const scores = (committeeReport?.score_by_agent || {}) as Record<string, number>;
        const entries = Object.entries(reviews as Record<string, string>).map(([agent, review]) => {
            const scoreValue = scores[agent];
            const score = Number.isFinite(Number(scoreValue)) ? Number(scoreValue) : null;
            return { agent, review: String(review || ''), score };
        });
        return entries.sort((a, b) => {
            if (a.score === null && b.score === null) return a.agent.localeCompare(b.agent);
            if (a.score === null) return 1;
            if (b.score === null) return -1;
            return b.score - a.score;
        });
    }, [committeeReport]);
    const hasCommitteeScores = committeeReviews.some((entry) => entry.score !== null);
    const decisionPayload = metadata?.decision || {
        final_decision: metadata?.final_decision,
        final_decision_reasons: metadata?.final_decision_reasons,
        final_decision_score: metadata?.final_decision_score,
        final_decision_target: metadata?.final_decision_target,
    };
    const decisionValue = decisionPayload?.final_decision;
    const decisionReasons: string[] = Array.isArray(decisionPayload?.final_decision_reasons)
        ? decisionPayload.final_decision_reasons
        : [];

    const decisionLabelMap: Record<string, string> = {
        APPROVED: 'Aprovado',
        NEED_EVIDENCE: 'Pendencias documentais',
        NEED_REWRITE: 'Reescrever minuta',
        NEED_HUMAN_REVIEW: 'Revisao humana obrigatoria',
    };
    const decisionReasonLabelMap: Record<string, string> = {
        missing_critical_docs: 'Documentos criticos pendentes',
        missing_noncritical_docs: 'Documentos nao criticos pendentes',
        audit_reprovado: 'Auditoria reprovada',
        audit_ressalvas: 'Auditoria com ressalvas',
        divergence_detected: 'Divergencias entre agentes',
        quality_gate_force_hil: 'Quality gate exigiu HIL',
        score_below_target: 'Nota abaixo do alvo',
        agent_disagreement: 'Discordancia entre notas',
        override_noncritical_docs: 'Prosseguir com ressalva',
        blocked_by_human: 'Bloqueado por decisao humana',
        force_final_hil: 'HIL final obrigatorio',
        proposal_submitted: 'Proposta humana enviada',
        final_rejected: 'Aprovacao final recusada',
    };

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

    const summarizeReview = (text: string) => {
        const firstLine = text.split('\n').find((line) => line.trim().length > 0) || '';
        const cleaned = firstLine.replace(/\s+/g, ' ').trim();
        if (!cleaned) return 'Sem resumo.';
        return cleaned.length > 140 ? `${cleaned.slice(0, 140)}...` : cleaned;
    };

    const handleCopyCommitteeReviews = async () => {
        if (!committeeReviews.length) return;
        const payload = committeeReviews.map((entry) => {
            const scoreLabel = entry.score !== null ? ` (nota ${entry.score.toFixed(1)})` : '';
            return `${entry.agent}${scoreLabel}\n${entry.review || 'Parecer não disponível.'}`;
        }).join('\n\n');
        try {
            await navigator.clipboard.writeText(payload);
            toast.success('Pareceres copiados.');
        } catch {
            toast.error('Não foi possível copiar os pareceres.');
        }
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
                                const auditText = metadata?.audit?.audit_report_markdown || metadata?.divergences;
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
                                    const auditText = metadata?.audit?.audit_report_markdown || metadata?.divergences;
                                    exportToDocx(content, 'Minuta-Iudex', auditText);
                                }}>
                                    <FileType className="mr-2 h-4 w-4" />
                                    <span>Word (.docx) (+ Auditoria)</span>
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
                            <TabsTrigger value="process" className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent px-2 h-full text-xs font-medium">Relatório do Agente</TabsTrigger>
                            <TabsTrigger value="audit" className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent px-2 h-full text-xs font-medium">
                                <span className="flex items-center gap-1">
                                    <Scale className="h-3 w-3" />
                                    Auditoria
                                </span>
                            </TabsTrigger>
                        </TabsList>

                        {/* Summary metrics in the bar */}
                        {metadata && (
                            <div className="hidden md:flex items-center gap-4 text-[10px] text-muted-foreground uppercase font-semibold">
                                <span>{metadata.model || 'AI'}</span>
                                <span>{metadata.latency?.toFixed(1)}s</span>
                                {costInfo?.total_tokens && <span>{costInfo.total_tokens} tokens</span>}
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

                    <TabsContent value="process" className="flex-1 overflow-y-auto p-6 bg-white space-y-6 m-0">
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <div className="p-4 rounded-xl border border-outline/30 bg-sand/10">
                                <h4 className="text-sm font-bold mb-3 flex items-center gap-2">
                                    <FileText className="h-4 w-4 text-primary" />
                                    Métricas de Execução
                                </h4>
                                <div className="space-y-2 text-xs">
                                    <div className="flex justify-between border-b border-outline/10 pb-1">
                                        <span className="text-muted-foreground">Tokens de Entrada</span>
                                        <span className="font-mono">{costInfo?.input_tokens || 0}</span>
                                    </div>
                                    <div className="flex justify-between border-b border-outline/10 pb-1">
                                        <span className="text-muted-foreground">Tokens de Saída</span>
                                        <span className="font-mono">{costInfo?.output_tokens || 0}</span>
                                    </div>
                                    <div className="flex justify-between border-b border-outline/10 pb-1">
                                        <span className="text-muted-foreground">Custo Estimado</span>
                                        <span className="text-green-600 font-bold">${costInfo?.total_cost?.toFixed(4) || '0.00'}</span>
                                    </div>
                                    <div className="flex justify-between pt-1">
                                        <span className="text-muted-foreground">Tempo Total</span>
                                        <span className="font-medium">{metadata?.latency?.toFixed(2)}s</span>
                                    </div>
                                </div>
                            </div>

                            <div className="p-4 rounded-xl border border-outline/30 bg-blue-50/30">
                                <h4 className="text-sm font-bold mb-3 flex items-center gap-2">
                                    <Bot className="h-4 w-4 text-blue-600" />
                                    Consenso e Agentes
                                </h4>
                                <div className="space-y-2 text-xs">
                                    <div className="flex justify-between border-b border-outline/10 pb-1">
                                        <span className="text-muted-foreground">Consenso Atingido</span>
                                        <span className={metadata?.consensus ? "text-green-600 font-bold" : "text-orange-600 font-bold"}>
                                            {metadata?.consensus ? "Sim" : "Mesclado"}
                                        </span>
                                    </div>
                                    <div className="flex justify-between border-b border-outline/10 pb-1">
                                        <span className="text-muted-foreground">Estratégia</span>
                                        <span>Multi-Agente (Hierárquico)</span>
                                    </div>
                                    <div className="flex justify-between pt-1">
                                        <span className="text-muted-foreground">Modelos em Debate</span>
                                        <span className="truncate">{metadata?.models?.join(', ') || 'GPT-5.2, Claude 4.5'}</span>
                                    </div>
                                </div>
                            </div>
                        </div>
                        <div className="p-4 rounded-xl border border-outline/30 bg-violet-50/20">
                            <h4 className="text-sm font-bold mb-3 flex items-center gap-2">
                                <Brain className="h-4 w-4 text-violet-600" />
                                Processo de raciocínio
                            </h4>
                            <p className="text-xs text-muted-foreground whitespace-pre-wrap max-h-[220px] overflow-y-auto">
                                {latestThinking || 'Nenhuma descrição de raciocínio foi fornecida até agora.'}
                            </p>
                        </div>
                        {decisionValue && (
                            <div className="p-4 rounded-xl border border-outline/30 bg-emerald-50/20">
                                <h4 className="text-sm font-bold mb-3 flex items-center gap-2">
                                    <Scale className="h-4 w-4 text-emerald-600" />
                                    Decisao Final
                                </h4>
                                <div className="space-y-2 text-xs">
                                    <div className="flex justify-between border-b border-outline/10 pb-1">
                                        <span className="text-muted-foreground">Status</span>
                                        <span className="font-medium">
                                            {decisionLabelMap[decisionValue] || decisionValue}
                                        </span>
                                    </div>
                                    {(decisionPayload?.final_decision_score || decisionPayload?.final_decision_target) && (
                                        <div className="flex justify-between border-b border-outline/10 pb-1">
                                            <span className="text-muted-foreground">Nota</span>
                                            <span className="font-mono">
                                                {decisionPayload?.final_decision_score ?? '-'}
                                                {decisionPayload?.final_decision_target ? ` / ${decisionPayload.final_decision_target}` : ''}
                                            </span>
                                        </div>
                                    )}
                                    {decisionReasons.length > 0 && (
                                        <div className="pt-1 space-y-1">
                                            <span className="text-muted-foreground">Motivos</span>
                                            <ul className="list-disc pl-5 space-y-1">
                                                {decisionReasons.slice(0, 6).map((reason) => (
                                                    <li key={reason} className="text-foreground/80">
                                                        {decisionReasonLabelMap[reason] || reason}
                                                    </li>
                                                ))}
                                            </ul>
                                        </div>
                                    )}
                                </div>
                            </div>
                        )}

                        <Tabs value={processTab} onValueChange={(value) => setProcessTab(value as 'drafts' | 'divergences' | 'committee')} className="w-full">
                            <TabsList className="h-9 w-full justify-start bg-muted/20 p-1">
                                <TabsTrigger value="drafts" className="text-xs h-7 px-3">Drafts</TabsTrigger>
                                <TabsTrigger value="divergences" className="text-xs h-7 px-3">Divergências</TabsTrigger>
                                <TabsTrigger value="committee" className="text-xs h-7 px-3">Minuta Final</TabsTrigger>
                            </TabsList>

                            <TabsContent value="drafts" className="mt-4 space-y-6">
                                {metadata?.processed_sections && metadata.processed_sections.length > 0 ? (
                                    <div className="space-y-6">
                                        <h4 className="text-sm font-bold flex items-center gap-2 pb-2 border-b border-outline/10">
                                            <Bot className="h-4 w-4 text-purple-600" />
                                            Detalhamento por Seção (Minuta AI)
                                        </h4>

                                        {metadata.processed_sections.map((section: any, idx: number) => {
                                            const drafts = section.drafts || {};
                                            const draftEntries = (() => {
                                                if (drafts?.drafts_by_model && typeof drafts.drafts_by_model === 'object') {
                                                    return Object.entries(drafts.drafts_by_model)
                                                        .filter(([, text]) => Boolean(text))
                                                        .map(([modelId, text]) => ({
                                                            key: modelId,
                                                            label: modelId,
                                                            content: text as string,
                                                        }));
                                                }
                                                return [
                                                    { key: 'gpt', label: 'GPT Draft', content: drafts.gpt_v1 },
                                                    { key: 'claude', label: 'Claude Draft', content: drafts.claude_v1 },
                                                    { key: 'gemini', label: 'Gemini Draft', content: drafts.gemini_v1 },
                                                ].filter((entry) => Boolean(entry.content));
                                            })();

                                            return (
                                                <div key={idx} className="border border-outline/20 rounded-xl overflow-hidden bg-white shadow-sm">
                                                    <div className="bg-muted/30 px-4 py-3 border-b border-outline/10 flex justify-between items-center">
                                                        <h5 className="font-semibold text-sm text-foreground/80">{section.section_title || `Seção ${idx + 1}`}</h5>
                                                        {section.has_significant_divergence && (
                                                            <span className="text-[10px] bg-orange-100 text-orange-700 px-2 py-0.5 rounded-full font-bold uppercase tracking-wider">
                                                                Divergência
                                                            </span>
                                                        )}
                                                    </div>

                                                    <div className="p-4">
                                                        {section.divergence_details && (
                                                            <div className="mb-4 p-3 bg-orange-50/50 border border-orange-100/50 rounded-lg text-xs text-muted-foreground">
                                                                <span className="font-bold text-orange-700 block mb-1">⚠️ Pontos de Debate:</span>
                                                                {section.divergence_details}
                                                            </div>
                                                        )}

                                                        <Tabs defaultValue="final" className="w-full">
                                                            <TabsList className="h-8 mb-4 w-full justify-start bg-muted/20 p-1">
                                                                <TabsTrigger value="final" className="text-xs h-6 px-3">Final (Juiz)</TabsTrigger>
                                                                {draftEntries.map((entry) => (
                                                                    <TabsTrigger key={entry.key} value={entry.key} className="text-xs h-6 px-3">
                                                                        {entry.label}
                                                                    </TabsTrigger>
                                                                ))}
                                                            </TabsList>

                                                            <TabsContent value="final" className="mt-0">
                                                                <div className="text-xs font-mono bg-muted/10 p-3 rounded-lg border border-outline/10 whitespace-pre-wrap max-h-[300px] overflow-y-auto">
                                                                    {section.merged_content || metadata.full_document || "Conteúdo consolidado não disponível nesta visualização resumida."}
                                                                </div>
                                                            </TabsContent>

                                                            {draftEntries.map((entry) => (
                                                                <TabsContent key={entry.key} value={entry.key} className="mt-0">
                                                                    <div className="text-xs font-mono bg-slate-50/20 p-3 rounded-lg border border-outline/10 whitespace-pre-wrap max-h-[300px] overflow-y-auto text-muted-foreground">
                                                                        {entry.content}
                                                                    </div>
                                                                </TabsContent>
                                                            ))}
                                                        </Tabs>
                                                    </div>
                                                </div>
                                            );
                                        })}
                                    </div>
                                ) : (
                                    <div className="flex flex-col items-center justify-center py-10 text-muted-foreground">
                                        <Maximize2 className="h-8 w-8 mb-4 opacity-20" />
                                        <p className="text-sm">Nenhum draft disponível ainda.</p>
                                    </div>
                                )}
                            </TabsContent>

                            <TabsContent value="divergences" className="mt-4 space-y-4">
                                {metadata?.processed_sections?.length ? (
                                    <div className="space-y-4">
                                        {metadata.processed_sections
                                            .filter((section: any) => section?.divergence_details || section?.has_significant_divergence)
                                            .map((section: any, idx: number) => (
                                                <div key={`${section.section_title || 'sec'}-${idx}`} className="rounded-xl border border-orange-100 bg-orange-50/20 p-4">
                                                    <div className="flex items-center justify-between mb-2">
                                                        <span className="text-sm font-semibold text-orange-700">{section.section_title || `Seção ${idx + 1}`}</span>
                                                        {section.has_significant_divergence && (
                                                            <span className="text-[10px] bg-orange-100 text-orange-700 px-2 py-0.5 rounded-full font-bold uppercase tracking-wider">
                                                                Divergência
                                                            </span>
                                                        )}
                                                    </div>
                                                    <p className="text-xs text-muted-foreground whitespace-pre-wrap">
                                                        {section.divergence_details || 'Divergência detectada pelos agentes.'}
                                                    </p>
                                                </div>
                                            ))}
                                    </div>
                                ) : metadata?.divergences ? (
                                    <div className="space-y-3">
                                        <h4 className="text-sm font-bold flex items-center gap-2">
                                            <AlertTriangle className="h-4 w-4 text-orange-500" />
                                            Log de Divergências (Legacy)
                                        </h4>
                                        <div className="p-4 rounded-xl border border-orange-100 bg-orange-50/20 text-xs font-mono whitespace-pre-wrap max-h-[400px] overflow-y-auto">
                                            {metadata.divergences}
                                        </div>
                                    </div>
                                ) : (
                                    <div className="flex flex-col items-center justify-center py-10 text-muted-foreground">
                                        <Check className="h-8 w-8 mb-4 opacity-20" />
                                        <p className="text-sm">Nenhuma divergência crítica detectada.</p>
                                    </div>
                                )}
                            </TabsContent>

                            <TabsContent value="committee" className="mt-4 space-y-4">
                                {committeeReport ? (
                                    <div className="rounded-xl border border-outline/20 bg-slate-50/40 p-5 space-y-3">
                                        <div className="flex items-center justify-between">
                                            <div>
                                                <h4 className="text-sm font-bold">Parecer do Sistema</h4>
                                                <p className="text-xs text-muted-foreground">
                                                    Agentes: {(committeeReport.agents_participated || []).join(', ') || '—'}
                                                </p>
                                            </div>
                                            <div className="text-right">
                                                <div className="text-[10px] uppercase text-muted-foreground">Nota</div>
                                                <div className={(committeeScore ?? 0) >= 7 ? "text-green-600 text-lg font-bold" : "text-amber-600 text-lg font-bold"}>
                                                    {committeeScore !== null ? committeeScore.toFixed(1) : '—'}
                                                </div>
                                            </div>
                                        </div>

                                        {committeeReport.critical_problems?.length > 0 && (
                                            <div className="rounded-lg border border-orange-100 bg-white p-3 text-xs">
                                                <span className="font-semibold text-orange-700 block mb-2">Problemas críticos</span>
                                                <ul className="space-y-1 text-muted-foreground">
                                                    {committeeReport.critical_problems.map((problem: string, idx: number) => (
                                                        <li key={`${problem}-${idx}`}>• {problem}</li>
                                                    ))}
                                                </ul>
                                            </div>
                                        )}

                                        {committeeReport.individual_reviews && (
                                            <div className="rounded-lg border border-outline/20 bg-white p-3 text-xs">
                                                <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
                                                    <div className="space-y-0.5">
                                                        <span className="font-semibold text-slate-700 block">Pareceres individuais</span>
                                                        {hasCommitteeScores && (
                                                            <span className="text-[10px] text-muted-foreground">Ordenados por nota</span>
                                                        )}
                                                    </div>
                                                    <Button
                                                        variant="outline"
                                                        size="sm"
                                                        className="h-6 px-2 text-[10px]"
                                                        onClick={handleCopyCommitteeReviews}
                                                    >
                                                        <Copy className="mr-1 h-3 w-3" />
                                                        Copiar
                                                    </Button>
                                                </div>
                                                <div className="space-y-3">
                                                    {committeeReviews.map((entry) => (
                                                        <details key={entry.agent} className="rounded-lg border border-outline/10 bg-slate-50/40 p-2">
                                                            <summary className="flex cursor-pointer items-center justify-between gap-2 text-[10px] text-slate-500">
                                                                <span className="flex items-center gap-2">
                                                                    <span className="font-semibold uppercase">{entry.agent}</span>
                                                                    {entry.score !== null && (
                                                                        <span className="text-emerald-600 font-semibold">{entry.score.toFixed(1)}</span>
                                                                    )}
                                                                </span>
                                                                <span className="truncate max-w-[65%] text-muted-foreground">
                                                                    {summarizeReview(entry.review)}
                                                                </span>
                                                            </summary>
                                                            <div className="mt-2 text-[11px] text-muted-foreground whitespace-pre-wrap">
                                                                {entry.review || 'Parecer não disponível.'}
                                                            </div>
                                                        </details>
                                                    ))}
                                                </div>
                                            </div>
                                        )}

                                        {committeeReport.markdown && (
                                            <div className="text-xs font-mono bg-white/80 p-3 rounded-lg border border-outline/10 whitespace-pre-wrap max-h-[320px] overflow-y-auto">
                                                {committeeReport.markdown}
                                            </div>
                                        )}
                                    </div>
                                ) : (
                                    <div className="flex flex-col items-center justify-center py-10 text-muted-foreground">
                                        <Scale className="h-10 w-10 mb-4 opacity-10" />
                                        <p className="text-sm">Relatório da minuta final ainda não disponível.</p>
                                    </div>
                                )}
                            </TabsContent>
                        </Tabs>
                    </TabsContent>

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
                                        <p className="text-xs text-muted-foreground">Auditado em {metadata.audit.audit_date || 'Data desconhecida'} por {metadata.audit.model_used || 'IA'}</p>
                                    </div>
                                </div>

                                {/* Report Content */}
                                <div className="space-y-3">
                                    <h4 className="text-sm font-bold flex items-center gap-2">
                                        <FileText className="h-4 w-4 text-gray-500" />
                                        Relatório de Conformidade
                                    </h4>
                                    <div className="p-6 rounded-xl border border-outline/20 bg-gray-50/50 text-sm prose prose-sm max-w-none whitespace-pre-wrap font-serif">
                                        {metadata.audit.audit_report_markdown}
                                    </div>
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

                        {/* Structural Quality Control - HIL */}
                        <div className="mt-6 pt-6 border-t border-outline/20">
                            <QualityPanel
                                rawContent={qualityContent}
                                formattedContent={qualityContent}
                                documentName={metadata?.title || 'Documento'}
                                onContentUpdated={(newContent) => setContent(newContent)}
                            />
                        </div>
                    </TabsContent>
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
