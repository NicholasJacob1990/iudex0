'use client';

import { useEffect, useMemo, useState } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { FileText, ChevronLeft, ChevronRight, Zap, List } from 'lucide-react';
import { cn, formatDate, formatFileSize } from '@/lib/utils';
import apiClient from '@/lib/api-client';
import { toast } from 'sonner';

interface DocumentViewerDialogProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    document: {
        id: string;
        name: string;
        type?: string;
        status?: string;
        size?: number;
        created_at?: string;
        content?: string | null;
        extracted_text?: string | null;
        doc_metadata?: Record<string, any>;
        tags?: string[];
    };
}

export function DocumentViewerDialog({ open, onOpenChange, document }: DocumentViewerDialogProps) {
    const [currentPage, setCurrentPage] = useState(1);
    const [showIndex, setShowIndex] = useState(false);
    const [pageRange, setPageRange] = useState({ start: 1, end: 1 });
    const fileSize = Number((document as any).size ?? (document as any).file_size ?? 0);
    const rawText = useMemo(() => {
        const text = document.extracted_text || document.content || '';
        return typeof text === 'string' ? text.trim() : '';
    }, [document.extracted_text, document.content]);
    const pages = useMemo(() => {
        if (!rawText) return [''];
        const pageSize = 4000;
        const chunks: string[] = [];
        for (let i = 0; i < rawText.length; i += pageSize) {
            chunks.push(rawText.slice(i, i + pageSize).trim());
        }
        return chunks.length ? chunks : [''];
    }, [rawText]);
    const totalPages = Math.max(1, pages.length);
    const clampedCurrentPage = Math.min(Math.max(currentPage, 1), totalPages);
    const currentPageText = pages[clampedCurrentPage - 1] || '';
    const estimatedTokens = rawText ? Math.max(1, Math.ceil(rawText.length / 4)) : 0;
    const tokensPerPage = totalPages ? Math.ceil(estimatedTokens / totalPages) : 0;

    useEffect(() => {
        setCurrentPage(1);
        setPageRange({ start: 1, end: totalPages });
        setShowIndex(false);
    }, [document.id, totalPages]);

    const handleApplySelection = () => {
        const start = Math.min(Math.max(pageRange.start, 1), totalPages);
        const end = Math.min(Math.max(pageRange.end, start), totalPages);
        setPageRange({ start, end });
        setCurrentPage(start);
    };

    const handleOCRDocument = async () => {
        try {
            toast.info('Enfileirando OCR...');
            await apiClient.applyDocumentOcr(document.id);
            toast.success('OCR enfileirado. Atualize o documento em alguns instantes.');
        } catch (error) {
            toast.error('Não foi possível enfileirar o OCR.');
        }
    };

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="max-w-5xl h-[80vh] flex flex-col">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <FileText className="h-5 w-5 text-primary" />
                        {document.name}
                    </DialogTitle>
                </DialogHeader>

                <div className="flex flex-1 gap-4 overflow-hidden">
                    {/* Left Sidebar - Controls */}
                    <div className="w-64 space-y-4 overflow-y-auto">
                        <div className="rounded-2xl border border-outline/30 bg-sand/20 p-4 space-y-2">
                            <h3 className="text-sm font-semibold text-foreground">Detalhes</h3>
                            <div className="space-y-1 text-xs text-muted-foreground">
                                <div className="flex justify-between">
                                    <span>Tipo</span>
                                    <span className="font-semibold text-foreground">{document.type || '—'}</span>
                                </div>
                                <div className="flex justify-between">
                                    <span>Status</span>
                                    <span className="font-semibold text-foreground">{document.status || '—'}</span>
                                </div>
                                <div className="flex justify-between">
                                    <span>Tamanho</span>
                                    <span className="font-semibold text-foreground">{formatFileSize(fileSize)}</span>
                                </div>
                                <div className="flex justify-between">
                                    <span>Criado</span>
                                    <span className="font-semibold text-foreground">{formatDate(document.created_at || '')}</span>
                                </div>
                                {document.tags?.length ? (
                                    <div className="flex flex-wrap gap-1 pt-1">
                                        {document.tags.map((tag) => (
                                            <span key={tag} className="chip bg-white/80 text-[10px] text-foreground">
                                                {tag}
                                            </span>
                                        ))}
                                    </div>
                                ) : null}
                            </div>
                        </div>

                        <div className="rounded-2xl border border-outline/30 bg-sand/20 p-4 space-y-3">
                            <h3 className="text-sm font-semibold text-foreground">Seleção de Páginas</h3>
                            <div className="space-y-2">
                                <div>
                                    <Label htmlFor="start-page" className="text-xs">Página inicial</Label>
                                    <Input
                                        id="start-page"
                                        type="number"
                                        min={1}
                                        max={totalPages}
                                        value={pageRange.start}
                                        onChange={(e) => setPageRange({ ...pageRange, start: parseInt(e.target.value) || 1 })}
                                        className="h-8 text-xs"
                                    />
                                </div>
                                <div>
                                    <Label htmlFor="end-page" className="text-xs">Página final</Label>
                                    <Input
                                        id="end-page"
                                        type="number"
                                        min={1}
                                        max={totalPages}
                                        value={pageRange.end}
                                        onChange={(e) => setPageRange({ ...pageRange, end: parseInt(e.target.value) || totalPages })}
                                        className="h-8 text-xs"
                                    />
                                </div>
                            </div>
                            <Button size="sm" variant="outline" className="w-full rounded-full text-xs" onClick={handleApplySelection}>
                                Aplicar Seleção
                            </Button>
                        </div>

                        <div className="rounded-2xl border border-outline/30 bg-sand/20 p-4 space-y-3">
                            <h3 className="text-sm font-semibold text-foreground">OCR</h3>
                            <Button
                                size="sm"
                                variant="outline"
                                className="w-full rounded-full text-xs gap-2"
                                onClick={handleOCRDocument}
                            >
                                <Zap className="h-3 w-3" />
                                OCR Documento
                            </Button>
                            <p className="text-[10px] text-muted-foreground">
                                Reconhecimento óptico de caracteres para documentos digitalizados
                            </p>
                        </div>

                        <div className="rounded-2xl border border-outline/30 bg-sand/20 p-4 space-y-3">
                            <h3 className="text-sm font-semibold text-foreground">Consumo de Tokens</h3>
                            <div className="space-y-1">
                                <div className="flex justify-between text-xs">
                                    <span className="text-muted-foreground">Página atual:</span>
                                    <span className="font-semibold text-primary">~{tokensPerPage} tokens</span>
                                </div>
                                <div className="flex justify-between text-xs">
                                    <span className="text-muted-foreground">Total:</span>
                                    <span className="font-semibold text-foreground">~{estimatedTokens} tokens</span>
                                </div>
                            </div>
                        </div>

                        <Button
                            size="sm"
                            variant="outline"
                            className="w-full rounded-full text-xs gap-2"
                            onClick={() => setShowIndex(!showIndex)}
                            disabled={totalPages <= 1}
                        >
                            <List className="h-3 w-3" />
                            {showIndex ? 'Ocultar' : 'Mostrar'} Índice
                        </Button>
                    </div>

                    {/* Main Content Area */}
                    <div className="flex-1 flex flex-col gap-4">
                        {/* Page Navigation */}
                        <div className="flex items-center justify-between rounded-2xl border border-outline/30 bg-white/90 p-3">
                            <Button
                                size="sm"
                                variant="ghost"
                                className="rounded-full"
                                onClick={() => setCurrentPage(Math.max(1, clampedCurrentPage - 1))}
                                disabled={clampedCurrentPage === 1}
                            >
                                <ChevronLeft className="h-4 w-4" />
                            </Button>
                            <span className="text-sm font-semibold">
                                Página {clampedCurrentPage} de {totalPages}
                            </span>
                            <Button
                                size="sm"
                                variant="ghost"
                                className="rounded-full"
                                onClick={() => setCurrentPage(Math.min(totalPages, clampedCurrentPage + 1))}
                                disabled={clampedCurrentPage === totalPages}
                            >
                                <ChevronRight className="h-4 w-4" />
                            </Button>
                        </div>

                        {/* Document Content */}
                        <div className="flex-1 rounded-2xl border border-outline/30 bg-white p-6 overflow-y-auto">
                            {showIndex ? (
                                <div className="space-y-2">
                                    <h3 className="font-semibold text-foreground mb-4">Índice do Documento</h3>
                                    {Array.from({ length: totalPages }, (_, i) => i + 1).map((page) => (
                                        <button
                                            key={page}
                                            onClick={() => {
                                                setCurrentPage(page);
                                                setShowIndex(false);
                                            }}
                                            className={cn(
                                                "w-full text-left px-3 py-2 rounded-lg text-sm transition-colors",
                                                page === clampedCurrentPage
                                                    ? "bg-primary/10 text-primary font-semibold"
                                                    : "hover:bg-sand/50 text-foreground"
                                            )}
                                        >
                                            Página {page}
                                        </button>
                                    ))}
                                </div>
                            ) : (
                                <div className="prose prose-sm max-w-none">
                                    {!rawText ? (
                                        <p className="text-sm text-muted-foreground text-center py-8">
                                            Nenhum texto extraído. Se for PDF/imagem, rode o OCR.
                                        </p>
                                    ) : (
                                        <pre className="whitespace-pre-wrap text-sm text-foreground">
                                            {currentPageText || 'Página sem conteúdo.'}
                                        </pre>
                                    )}
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            </DialogContent>
        </Dialog>
    );
}
