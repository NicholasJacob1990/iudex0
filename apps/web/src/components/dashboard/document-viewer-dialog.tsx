'use client';

import { useState } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { FileText, ChevronLeft, ChevronRight, Zap, List } from 'lucide-react';
import { cn } from '@/lib/utils';

interface DocumentViewerDialogProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    document: {
        id: string;
        name: string;
        pages?: number;
        content?: string;
    };
}

export function DocumentViewerDialog({ open, onOpenChange, document }: DocumentViewerDialogProps) {
    const [currentPage, setCurrentPage] = useState(1);
    const [pageRange, setPageRange] = useState({ start: 1, end: document.pages || 1 });
    const [showIndex, setShowIndex] = useState(false);
    const totalPages = document.pages || 1;

    const handleOCRPage = (page: number) => {
        // TODO: Implement OCR for specific page
        console.log('OCR page:', page);
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
                            <Button size="sm" variant="outline" className="w-full rounded-full text-xs">
                                Aplicar Seleção
                            </Button>
                        </div>

                        <div className="rounded-2xl border border-outline/30 bg-sand/20 p-4 space-y-3">
                            <h3 className="text-sm font-semibold text-foreground">OCR</h3>
                            <Button
                                size="sm"
                                variant="outline"
                                className="w-full rounded-full text-xs gap-2"
                                onClick={() => handleOCRPage(currentPage)}
                            >
                                <Zap className="h-3 w-3" />
                                OCR Página Atual
                            </Button>
                            <p className="text-[10px] text-muted-foreground">
                                Reconhecimento óptico de caracteres para páginas digitalizadas
                            </p>
                        </div>

                        <div className="rounded-2xl border border-outline/30 bg-sand/20 p-4 space-y-3">
                            <h3 className="text-sm font-semibold text-foreground">Consumo de Tokens</h3>
                            <div className="space-y-1">
                                <div className="flex justify-between text-xs">
                                    <span className="text-muted-foreground">Página atual:</span>
                                    <span className="font-semibold text-primary">~450 tokens</span>
                                </div>
                                <div className="flex justify-between text-xs">
                                    <span className="text-muted-foreground">Total:</span>
                                    <span className="font-semibold text-foreground">~{totalPages * 450} tokens</span>
                                </div>
                            </div>
                        </div>

                        <Button
                            size="sm"
                            variant="outline"
                            className="w-full rounded-full text-xs gap-2"
                            onClick={() => setShowIndex(!showIndex)}
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
                                onClick={() => setCurrentPage(Math.max(1, currentPage - 1))}
                                disabled={currentPage === 1}
                            >
                                <ChevronLeft className="h-4 w-4" />
                            </Button>
                            <span className="text-sm font-semibold">
                                Página {currentPage} de {totalPages}
                            </span>
                            <Button
                                size="sm"
                                variant="ghost"
                                className="rounded-full"
                                onClick={() => setCurrentPage(Math.min(totalPages, currentPage + 1))}
                                disabled={currentPage === totalPages}
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
                                                page === currentPage
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
                                    <p className="text-muted-foreground text-center py-8">
                                        Conteúdo da página {currentPage}
                                    </p>
                                    <p className="text-sm text-foreground">
                                        {document.content || 'Visualização do documento será exibida aqui.'}
                                    </p>
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            </DialogContent>
        </Dialog>
    );
}
