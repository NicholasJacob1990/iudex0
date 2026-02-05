'use client';

import React, { useMemo } from 'react';
import { diffLines, diffWords, type Change } from 'diff';
import { type CodeArtifact } from '@/stores/canvas-store';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { ArrowLeftRight, Plus, Minus, Equal } from 'lucide-react';

interface ArtifactDiffViewProps {
    original: CodeArtifact;
    modified: CodeArtifact;
    mode?: 'lines' | 'words' | 'split';
    className?: string;
}

interface DiffStats {
    additions: number;
    deletions: number;
    unchanged: number;
}

function computeStats(changes: Change[]): DiffStats {
    return changes.reduce(
        (acc, change) => {
            const lines = change.value.split('\n').filter(Boolean).length || 1;
            if (change.added) acc.additions += lines;
            else if (change.removed) acc.deletions += lines;
            else acc.unchanged += lines;
            return acc;
        },
        { additions: 0, deletions: 0, unchanged: 0 }
    );
}

export function ArtifactDiffView({
    original,
    modified,
    mode = 'lines',
    className,
}: ArtifactDiffViewProps) {
    const changes = useMemo(() => {
        if (mode === 'words') {
            return diffWords(original.code, modified.code);
        }
        return diffLines(original.code, modified.code);
    }, [original.code, modified.code, mode]);

    const stats = useMemo(() => computeStats(changes), [changes]);

    // Split view: side-by-side comparison
    if (mode === 'split') {
        return (
            <div className={cn("border rounded-lg overflow-hidden", className)}>
                {/* Header */}
                <div className="flex items-center justify-between px-4 py-2 bg-muted/30 border-b">
                    <div className="flex items-center gap-4 text-xs">
                        <span className="flex items-center gap-1 text-red-600">
                            <Minus className="h-3 w-3" />
                            {stats.deletions} removidas
                        </span>
                        <span className="flex items-center gap-1 text-green-600">
                            <Plus className="h-3 w-3" />
                            {stats.additions} adicionadas
                        </span>
                    </div>
                    <ArrowLeftRight className="h-4 w-4 text-muted-foreground" />
                </div>

                {/* Split panels */}
                <div className="grid grid-cols-2 divide-x">
                    {/* Original */}
                    <div className="bg-red-50/30 dark:bg-red-950/20">
                        <div className="px-3 py-1.5 bg-red-100/50 dark:bg-red-900/30 text-xs font-medium text-red-700 dark:text-red-300 border-b">
                            {original.title} (original)
                        </div>
                        <pre className="p-3 text-xs font-mono overflow-auto max-h-[400px]">
                            {original.code}
                        </pre>
                    </div>

                    {/* Modified */}
                    <div className="bg-green-50/30 dark:bg-green-950/20">
                        <div className="px-3 py-1.5 bg-green-100/50 dark:bg-green-900/30 text-xs font-medium text-green-700 dark:text-green-300 border-b">
                            {modified.title} (modificado)
                        </div>
                        <pre className="p-3 text-xs font-mono overflow-auto max-h-[400px]">
                            {modified.code}
                        </pre>
                    </div>
                </div>
            </div>
        );
    }

    // Unified diff view
    return (
        <div className={cn("border rounded-lg overflow-hidden", className)}>
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-2 bg-muted/30 border-b">
                <div className="flex items-center gap-2">
                    <span className="text-sm font-medium">
                        {original.title} → {modified.title}
                    </span>
                </div>
                <div className="flex items-center gap-4 text-xs">
                    <span className="flex items-center gap-1 text-red-600">
                        <Minus className="h-3 w-3" />
                        {stats.deletions}
                    </span>
                    <span className="flex items-center gap-1 text-green-600">
                        <Plus className="h-3 w-3" />
                        {stats.additions}
                    </span>
                    <span className="flex items-center gap-1 text-muted-foreground">
                        <Equal className="h-3 w-3" />
                        {stats.unchanged}
                    </span>
                </div>
            </div>

            {/* Diff content */}
            <div className="bg-slate-900 p-4 overflow-auto max-h-[500px]">
                <pre className="text-xs font-mono">
                    {changes.map((change, index) => {
                        const lines = change.value.split('\n');
                        return lines.map((line, lineIndex) => {
                            // Skip empty lines at the end
                            if (lineIndex === lines.length - 1 && !line) return null;

                            return (
                                <div
                                    key={`${index}-${lineIndex}`}
                                    className={cn(
                                        "px-2 py-0.5 -mx-2",
                                        change.added && "bg-green-500/20 text-green-300",
                                        change.removed && "bg-red-500/20 text-red-300",
                                        !change.added && !change.removed && "text-slate-300"
                                    )}
                                >
                                    <span className="inline-block w-4 text-slate-500 select-none mr-2">
                                        {change.added ? '+' : change.removed ? '-' : ' '}
                                    </span>
                                    {line || ' '}
                                </div>
                            );
                        });
                    })}
                </pre>
            </div>
        </div>
    );
}

// Component to select two artifacts and compare them
interface ArtifactDiffSelectorProps {
    artifacts: CodeArtifact[];
    className?: string;
}

export function ArtifactDiffSelector({ artifacts, className }: ArtifactDiffSelectorProps) {
    const [originalId, setOriginalId] = React.useState<string | null>(null);
    const [modifiedId, setModifiedId] = React.useState<string | null>(null);
    const [mode, setMode] = React.useState<'lines' | 'words' | 'split'>('lines');

    const original = artifacts.find(a => a.id === originalId);
    const modified = artifacts.find(a => a.id === modifiedId);

    if (artifacts.length < 2) {
        return (
            <div className={cn("text-center py-8 text-muted-foreground", className)}>
                Precisa de pelo menos 2 artifacts para comparar
            </div>
        );
    }

    return (
        <div className={cn("space-y-4", className)}>
            {/* Selectors */}
            <div className="flex items-center gap-4">
                <div className="flex-1">
                    <label className="text-xs font-medium text-muted-foreground mb-1 block">
                        Original
                    </label>
                    <select
                        value={originalId || ''}
                        onChange={(e) => setOriginalId(e.target.value || null)}
                        className="w-full px-3 py-2 text-sm border rounded-md bg-background"
                    >
                        <option value="">Selecionar...</option>
                        {artifacts.map(a => (
                            <option key={a.id} value={a.id} disabled={a.id === modifiedId}>
                                {a.title} ({a.language})
                            </option>
                        ))}
                    </select>
                </div>

                <ArrowLeftRight className="h-5 w-5 text-muted-foreground mt-5" />

                <div className="flex-1">
                    <label className="text-xs font-medium text-muted-foreground mb-1 block">
                        Modificado
                    </label>
                    <select
                        value={modifiedId || ''}
                        onChange={(e) => setModifiedId(e.target.value || null)}
                        className="w-full px-3 py-2 text-sm border rounded-md bg-background"
                    >
                        <option value="">Selecionar...</option>
                        {artifacts.map(a => (
                            <option key={a.id} value={a.id} disabled={a.id === originalId}>
                                {a.title} ({a.language})
                            </option>
                        ))}
                    </select>
                </div>
            </div>

            {/* Mode selector */}
            <div className="flex items-center gap-2">
                <span className="text-xs text-muted-foreground">Modo:</span>
                <div className="flex rounded-md border">
                    {(['lines', 'words', 'split'] as const).map((m) => (
                        <button
                            key={m}
                            onClick={() => setMode(m)}
                            className={cn(
                                "px-3 py-1 text-xs capitalize",
                                mode === m ? "bg-primary text-primary-foreground" : "hover:bg-muted"
                            )}
                        >
                            {m === 'lines' ? 'Linhas' : m === 'words' ? 'Palavras' : 'Lado a lado'}
                        </button>
                    ))}
                </div>
            </div>

            {/* Diff view */}
            {original && modified ? (
                <ArtifactDiffView
                    original={original}
                    modified={modified}
                    mode={mode}
                />
            ) : (
                <div className="text-center py-8 text-muted-foreground border rounded-lg">
                    Selecione dois artifacts para comparar
                </div>
            )}
        </div>
    );
}

export default ArtifactDiffView;
