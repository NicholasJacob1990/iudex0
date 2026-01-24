import { useState, useMemo, useEffect } from 'react';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { diffLines, Change } from 'diff';
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { AlertTriangle, Check, X, Diff, ChevronDown, ChevronUp, FileText, Split } from 'lucide-react';
import { cn } from '@/lib/utils';

interface DiffConfirmDialogProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    title?: string;
    description?: string;
    original: string;
    replacement: string;
    affectedSection?: string;
    changeStats?: {
        paragraphsChanged: number;
        totalParagraphs: number;
        wordsAdded: number;
        wordsRemoved: number;
    };
    onAccept: () => void;
    onReject: () => void;
    onAcceptPartial?: (content: string) => void;
}

export function DiffConfirmDialog({
    open,
    onOpenChange,
    title = 'Confirmar Alteração',
    description,
    original,
    replacement,
    affectedSection,
    changeStats,
    onAccept,
    onReject,
    onAcceptPartial,
}: DiffConfirmDialogProps) {
    const [showFullDiff, setShowFullDiff] = useState(false);
    const [viewMode, setViewMode] = useState<'diff' | 'preview'>('diff');
    const allowPartial = typeof onAcceptPartial === 'function';

    // Calculate change percentage
    const changePercentage = changeStats
        ? Math.round((changeStats.paragraphsChanged / changeStats.totalParagraphs) * 100)
        : 0;
    const isLargeChange = changePercentage > 50;

    // Compute differences using 'diff' library
    type DiffBlock =
        | { type: 'unchanged'; value: string }
        | {
            type: 'hunk';
            id: number;
            changes: Change[];
            originalText: string;
            replacementText: string;
        };

    const blocks = useMemo<DiffBlock[]>(() => {
        const diff = diffLines(original, replacement);
        const result: DiffBlock[] = [];
        let i = 0;
        let hunkId = 0;

        while (i < diff.length) {
            const part = diff[i];
            if (part.added || part.removed) {
                const hunkChanges: Change[] = [];
                while (i < diff.length && (diff[i].added || diff[i].removed)) {
                    hunkChanges.push(diff[i]);
                    i += 1;
                }
                const originalText = hunkChanges
                    .filter((item) => item.removed)
                    .map((item) => item.value)
                    .join('');
                const replacementText = hunkChanges
                    .filter((item) => item.added)
                    .map((item) => item.value)
                    .join('');
                result.push({
                    type: 'hunk',
                    id: hunkId,
                    changes: hunkChanges,
                    originalText,
                    replacementText,
                });
                hunkId += 1;
                continue;
            }

            const unchanged: Change[] = [];
            while (i < diff.length && !diff[i].added && !diff[i].removed) {
                unchanged.push(diff[i]);
                i += 1;
            }
            result.push({
                type: 'unchanged',
                value: unchanged.map((item) => item.value).join(''),
            });
        }

        return result;
    }, [original, replacement]);

    const hunkIds = useMemo(
        () => blocks.filter((block) => block.type === 'hunk').map((block) => block.id),
        [blocks]
    );
    const totalHunks = hunkIds.length;
    const [selectedHunks, setSelectedHunks] = useState<Set<number>>(new Set());

    useEffect(() => {
        if (!open) return;
        setShowFullDiff(false);
        setViewMode('diff');
        if (allowPartial && totalHunks > 0) {
            setSelectedHunks(new Set(hunkIds));
        }
    }, [open, allowPartial, totalHunks, hunkIds]);

    const selectedCount = selectedHunks.size;
    const showPartialControls = allowPartial && totalHunks > 0;

    const mergedContent = useMemo(() => {
        if (!showPartialControls) return replacement;
        return blocks
            .map((block) => {
                if (block.type === 'unchanged') return block.value;
                const shouldApply = selectedHunks.has(block.id);
                return shouldApply ? block.replacementText : block.originalText;
            })
            .join('');
    }, [blocks, selectedHunks, replacement, showPartialControls]);

    const handleSelectAll = () => {
        setSelectedHunks(new Set(hunkIds));
    };

    const handleClearSelection = () => {
        setSelectedHunks(new Set());
    };

    const renderDiff = () => {
        return (
            <div className="space-y-1 font-mono text-sm bg-muted/20 p-2 rounded-md border">
                {blocks.map((block, index) => {
                    if (block.type === 'hunk') {
                        const isSelected = !showPartialControls || selectedHunks.has(block.id);
                        return (
                            <div
                                key={`hunk-${block.id}`}
                                className={cn(
                                    'rounded-md border bg-background',
                                    isSelected ? 'border-emerald-200' : 'border-muted-foreground/30 opacity-80'
                                )}
                            >
                                <div className="flex flex-wrap items-center justify-between gap-2 border-b bg-muted/30 px-2 py-1 text-xs text-muted-foreground">
                                    <span>Trecho {block.id + 1}</span>
                                    {showPartialControls && (
                                        <label className="flex items-center gap-2">
                                            <Switch
                                                checked={isSelected}
                                                onCheckedChange={(checked) => {
                                                    setSelectedHunks((prev) => {
                                                        const next = new Set(prev);
                                                        if (checked) {
                                                            next.add(block.id);
                                                        } else {
                                                            next.delete(block.id);
                                                        }
                                                        return next;
                                                    });
                                                }}
                                            />
                                            <span>{isSelected ? 'Aplicar trecho' : 'Ignorar trecho'}</span>
                                        </label>
                                    )}
                                </div>
                                <div className="space-y-1 p-2">
                                    {block.changes.map((part, partIndex) => {
                                        const color = part.added
                                            ? 'bg-green-100 text-green-900 border-green-200 dark:bg-green-900/30 dark:text-green-300 dark:border-green-800'
                                            : part.removed
                                            ? 'bg-red-50 text-red-900 border-red-200 dark:bg-red-900/30 dark:text-red-300 dark:border-red-800 line-through decoration-red-900/50'
                                            : 'text-foreground/70';

                                        return (
                                            <div
                                                key={`${block.id}-${partIndex}`}
                                                className={cn(
                                                    'whitespace-pre-wrap px-2 py-0.5 border-l-2',
                                                    part.added ? 'border-green-500' : part.removed ? 'border-red-500' : 'border-transparent',
                                                    color
                                                )}
                                            >
                                                {part.value}
                                            </div>
                                        );
                                    })}
                                </div>
                            </div>
                        );
                    }

                    // Skip large unchanged blocks if not showing full diff
                    if (!showFullDiff && block.value.split('\n').length > 6) {
                        const lines = block.value.split('\n');
                        const start = lines.slice(0, 3).join('\n');
                        const end = lines.slice(-3).join('\n');
                        return (
                            <div key={index} className="py-2 text-muted-foreground bg-muted/30 text-center text-xs rounded my-1 border-y border-dashed">
                                <div className="whitespace-pre-wrap opacity-50 text-left px-2">{start}</div>
                                <div className="py-1 italic">... {lines.length - 6} linhas inalteradas ...</div>
                                <div className="whitespace-pre-wrap opacity-50 text-left px-2">{end}</div>
                            </div>
                        );
                    }

                    return (
                        <div
                            key={index}
                            className={cn(
                                'whitespace-pre-wrap px-2 py-0.5 border-l-2',
                                'border-transparent text-foreground/70'
                            )}
                        >
                            {block.value}
                        </div>
                    );
                })}
            </div>
        );
    };

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="sm:max-w-[800px] h-[80vh] flex flex-col p-0 gap-0">
                <DialogHeader className="px-6 py-4 border-b">
                    <DialogTitle className="flex items-center gap-2">
                        {isLargeChange && <AlertTriangle className="h-5 w-5 text-orange-500" />}
                        <Diff className="h-5 w-5 text-primary" />
                        {title}
                    </DialogTitle>
                    <DialogDescription>
                        {description || 'A IA propôs as seguintes alterações no documento. Revise antes de aplicar.'}
                    </DialogDescription>
                </DialogHeader>

                <div className="flex-1 overflow-hidden flex flex-col min-h-0 bg-muted/10">
                    <Tabs value={viewMode} onValueChange={(v) => setViewMode(v as any)} className="flex-1 flex flex-col h-full">
                        <div className="flex items-center justify-between px-6 py-2 border-b bg-background">
                            <TabsList className="grid w-[240px] grid-cols-2 h-8">
                                <TabsTrigger value="diff" className="text-xs">
                                    <Split className="h-3.5 w-3.5 mr-2" />
                                    Comparar (Diff)
                                </TabsTrigger>
                                <TabsTrigger value="preview" className="text-xs">
                                    <FileText className="h-3.5 w-3.5 mr-2" />
                                    Visualizar (Final)
                                </TabsTrigger>
                            </TabsList>

                            {changeStats && (
                                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                                    {affectedSection && (
                                        <span className="font-medium text-foreground max-w-[200px] truncate" title={affectedSection}>
                                            📍 {affectedSection}
                                        </span>
                                    )}
                                    <span>
                                        {changeStats.wordsAdded > 0 && <span className="text-green-600">+{changeStats.wordsAdded} palavras</span>}
                                        {changeStats.wordsAdded > 0 && changeStats.wordsRemoved > 0 && <span className="mx-1">/</span>}
                                        {changeStats.wordsRemoved > 0 && <span className="text-red-600">-{changeStats.wordsRemoved} palavras</span>}
                                    </span>
                                </div>
                            )}
                        </div>

                        <div className="flex-1 overflow-y-auto p-6">
                            <TabsContent value="diff" className="mt-0 space-y-4">
                                {showPartialControls && (
                                    <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border bg-muted/20 px-3 py-2 text-xs text-muted-foreground">
                                        <span>
                                            {selectedCount} de {totalHunks} trecho(s) selecionado(s)
                                        </span>
                                        <div className="flex items-center gap-2">
                                            <Button variant="ghost" size="sm" onClick={handleSelectAll}>
                                                Selecionar todos
                                            </Button>
                                            <Button variant="ghost" size="sm" onClick={handleClearSelection}>
                                                Limpar seleção
                                            </Button>
                                        </div>
                                    </div>
                                )}

                                {/* Large Change Warning */}
                                {isLargeChange && (
                                    <div className="flex items-start gap-3 p-3 rounded-lg border border-orange-200 bg-orange-50 mb-4">
                                        <AlertTriangle className="h-5 w-5 text-orange-500 flex-shrink-0 mt-0.5" />
                                        <div className="text-sm">
                                            <p className="font-medium text-orange-800">Alteração Significativa ({changePercentage}%)</p>
                                            <p className="text-orange-700 mt-1">
                                                Esta ação modifica grande parte do documento. Recomendamos revisar com atenção.
                                            </p>
                                        </div>
                                    </div>
                                )}

                                {renderDiff()}

                                {!showFullDiff && (
                                    <Button
                                        variant="ghost"
                                        size="sm"
                                        className="w-full mt-2 text-muted-foreground"
                                        onClick={() => setShowFullDiff(true)}
                                    >
                                        <ChevronDown className="h-4 w-4 mr-1" />
                                        Mostrar contexto completo
                                    </Button>
                                )}
                            </TabsContent>

                            <TabsContent value="preview" className="mt-0 h-full">
                                <div className="prose prose-sm dark:prose-invert max-w-none bg-background rounded-lg border p-6 min-h-full shadow-sm overflow-auto">
                                    <Markdown
                                        remarkPlugins={[remarkGfm]}
                                        components={{
                                            table: ({ node, ...props }) => (
                                                <table className="w-full border-collapse border border-zinc-300 my-4 text-sm" {...props} />
                                            ),
                                            thead: ({ node, ...props }) => (
                                                <thead className="bg-zinc-100 dark:bg-zinc-800" {...props} />
                                            ),
                                            tbody: ({ node, ...props }) => (
                                                <tbody className="bg-white dark:bg-zinc-950" {...props} />
                                            ),
                                            tr: ({ node, ...props }) => (
                                                <tr className="border-b border-zinc-300 dark:border-zinc-700" {...props} />
                                            ),
                                            th: ({ node, ...props }) => (
                                                <th className="border border-zinc-300 dark:border-zinc-700 px-4 py-2 text-left font-bold text-zinc-900 dark:text-zinc-100" {...props} />
                                            ),
                                            td: ({ node, ...props }) => (
                                                <td className="border border-zinc-300 dark:border-zinc-700 px-4 py-2 text-zinc-800 dark:text-zinc-300" {...props} />
                                            ),
                                            p: ({ node, ...props }) => (
                                                <p className="mb-4 leading-relaxed" {...props} />
                                            ),
                                            h1: ({ node, ...props }) => (
                                                <h1 className="text-2xl font-bold mb-4 mt-6 text-foreground" {...props} />
                                            ),
                                            h2: ({ node, ...props }) => (
                                                <h2 className="text-xl font-bold mb-3 mt-5 text-foreground" {...props} />
                                            ),
                                            h3: ({ node, ...props }) => (
                                                <h3 className="text-lg font-bold mb-2 mt-4 text-foreground" {...props} />
                                            ),
                                            ul: ({ node, ...props }) => (
                                                <ul className="list-disc pl-5 mb-4 space-y-1" {...props} />
                                            ),
                                            ol: ({ node, ...props }) => (
                                                <ol className="list-decimal pl-5 mb-4 space-y-1" {...props} />
                                            ),
                                            blockquote: ({ node, ...props }) => (
                                                <blockquote className="border-l-4 border-primary/30 pl-4 italic my-4 text-muted-foreground" {...props} />
                                            ),
                                        }}
                                    >
                                        {showPartialControls ? mergedContent : replacement}
                                    </Markdown>
                                </div>
                            </TabsContent>
                        </div>
                    </Tabs>
                </div>

                <DialogFooter className="px-6 py-4 border-t bg-background gap-2 sm:gap-0">
                    <div className="flex-1 flex justify-start">
                        {showPartialControls && (
                            <Button
                                variant="secondary"
                                onClick={() => onAcceptPartial?.(mergedContent)}
                                size="sm"
                                disabled={selectedCount === 0}
                            >
                                Aplicar Seleção
                            </Button>
                        )}
                    </div>
                    <Button variant="outline" onClick={onReject}>
                        <X className="h-4 w-4 mr-1" />
                        Rejeitar
                    </Button>
                    <Button
                        onClick={onAccept}
                        className={cn(isLargeChange && 'bg-orange-600 hover:bg-orange-700')}
                    >
                        <Check className="h-4 w-4 mr-1" />
                        {isLargeChange
                            ? 'Confirmar Grandes Alterações'
                            : showPartialControls
                                ? 'Aplicar tudo'
                                : 'Confirmar Alteração'}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
