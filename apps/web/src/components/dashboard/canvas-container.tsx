'use client';

import { useMemo, useState } from 'react';
import { useCanvasStore } from '@/stores';
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
    AlertTriangle,
    Scale,
    ShieldCheck,
    Undo2,
    Redo2,
    Check
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

export function CanvasContainer() {
    const {
        state, activeTab, content, metadata, costInfo, hideCanvas, toggleExpanded, setActiveTab,
        undo, redo, canUndo, canRedo, contentHistory, historyIndex,
        pendingSuggestions, acceptSuggestion, rejectSuggestion, setContent,
        highlightedText
    } = useCanvasStore();

    const [diffDialogOpen, setDiffDialogOpen] = useState(false);
    const [currentSuggestion, setCurrentSuggestion] = useState<typeof pendingSuggestions[0] | null>(null);

    const isExpanded = state === 'expanded';

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
                'relative flex h-full w-full flex-col bg-background transition-all duration-300'
            )}
        >
            {/* Control Bar */}
            <div className="flex items-center justify-between border-b border-outline/30 bg-muted/30 px-4 py-2">
                <div className="flex items-center gap-3">
                    <DocumentVersionBadge documentName={metadata?.title || 'Documento'} />

                    {/* Pending Suggestions Indicator */}
                    {pendingSuggestions.length > 0 && (
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
                            {pendingSuggestions.length} sugestão pendente
                        </Button>
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

                    <TabsContent value="editor" className="flex-1 overflow-y-auto p-8 bg-slate-50/50 m-0">
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

                        {/* Multi-Agent Draft Viewer */}
                        {metadata?.processed_sections && metadata.processed_sections.length > 0 ? (
                            <div className="space-y-6">
                                <h4 className="text-sm font-bold flex items-center gap-2 pb-2 border-b border-outline/10">
                                    <Bot className="h-4 w-4 text-purple-600" />
                                    Detalhamento por Seção (Comitê AI)
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
                                            {/* Divergence Alert if exists */}
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
                            /* Fallback for legacy jobs without detailed sections */
                            metadata?.divergences && (
                                <div className="space-y-3">
                                    <h4 className="text-sm font-bold flex items-center gap-2">
                                        <AlertTriangle className="h-4 w-4 text-orange-500" />
                                        Log de Divergências (Legacy)
                                    </h4>
                                    <div className="p-4 rounded-xl border border-orange-100 bg-orange-50/20 text-xs font-mono whitespace-pre-wrap max-h-[400px] overflow-y-auto">
                                        {metadata.divergences}
                                    </div>
                                </div>
                            )
                        )}

                        {!metadata?.divergences && !metadata?.processed_sections?.length && (
                            <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
                                <Maximize2 className="h-8 w-8 mb-4 opacity-20" />
                                <p className="text-sm">Nenhuma divergência crítica detectada pelo Juiz.</p>
                            </div>
                        )}
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
        </div>
    );
}
