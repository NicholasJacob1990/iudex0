'use client';

import React, { useState, useMemo } from 'react';
import dynamic from 'next/dynamic';
import { useCanvasStore, type CodeArtifact, type ArtifactLanguage } from '@/stores/canvas-store';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import {
    Copy,
    Check,
    Play,
    Code2,
    FileCode,
    Trash2,
    Download,
    ChevronDown,
    ChevronRight,
    Loader2,
    ExternalLink,
    RefreshCw,
    GitCompareArrows,
} from 'lucide-react';
import { toast } from 'sonner';
import { CodeHighlighter } from './artifact-code-highlighter';
import { ArtifactExporter } from './artifact-exporter';

// Loading fallback - defined first so it can be used in dynamic imports
function LoadingFallback() {
    return (
        <div className="flex items-center justify-center p-8 bg-muted/30 rounded-lg">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
    );
}

// Dynamic import with ssr: false for browser-only components (GPT recommended)
const SandpackPreview = dynamic(() => import('./artifact-sandpack-preview'), {
    ssr: false,
    loading: () => <LoadingFallback />,
});
const PythonRunner = dynamic(() => import('./artifact-python-runner'), {
    ssr: false,
    loading: () => <LoadingFallback />,
});
const ArtifactDiffSelector = dynamic(
    () => import('./artifact-diff-view').then(m => ({ default: m.ArtifactDiffSelector })),
    { ssr: false, loading: () => <LoadingFallback /> }
);

// Language display names and icons
const LANGUAGE_META: Record<ArtifactLanguage, { label: string; color: string }> = {
    typescript: { label: 'TypeScript', color: 'bg-blue-500' },
    javascript: { label: 'JavaScript', color: 'bg-yellow-500' },
    jsx: { label: 'JSX', color: 'bg-cyan-500' },
    tsx: { label: 'TSX', color: 'bg-blue-600' },
    python: { label: 'Python', color: 'bg-green-500' },
    html: { label: 'HTML', color: 'bg-orange-500' },
    css: { label: 'CSS', color: 'bg-purple-500' },
    json: { label: 'JSON', color: 'bg-gray-500' },
    sql: { label: 'SQL', color: 'bg-indigo-500' },
    bash: { label: 'Bash', color: 'bg-slate-600' },
    markdown: { label: 'Markdown', color: 'bg-slate-500' },
    yaml: { label: 'YAML', color: 'bg-red-400' },
    rust: { label: 'Rust', color: 'bg-orange-600' },
    go: { label: 'Go', color: 'bg-cyan-600' },
    java: { label: 'Java', color: 'bg-red-600' },
    csharp: { label: 'C#', color: 'bg-purple-600' },
    react: { label: 'React', color: 'bg-cyan-400' },
    vue: { label: 'Vue', color: 'bg-green-400' },
    svelte: { label: 'Svelte', color: 'bg-orange-400' },
    other: { label: 'Code', color: 'bg-gray-400' },
};

// Check if artifact can be previewed/executed
const isPreviewable = (artifact: CodeArtifact): boolean => {
    return ['html', 'react', 'jsx', 'tsx', 'vue', 'svelte'].includes(artifact.language) ||
        artifact.type === 'component' ||
        artifact.type === 'html';
};

// Check if artifact can run Python
const isPythonExecutable = (artifact: CodeArtifact): boolean => {
    return artifact.language === 'python';
};

interface ArtifactPreviewProps {
    artifact: CodeArtifact;
}

function ArtifactPreview({ artifact }: ArtifactPreviewProps) {
    const [key, setKey] = useState(0);

    const handleRefresh = () => {
        setKey((k) => k + 1);
    };

    // For HTML artifacts, render in iframe
    if (artifact.language === 'html' || artifact.type === 'html') {
        const htmlContent = artifact.code.includes('<!DOCTYPE') || artifact.code.includes('<html')
            ? artifact.code
            : `<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: system-ui, sans-serif; padding: 1rem; margin: 0; }
    </style>
</head>
<body>
${artifact.code}
</body>
</html>`;

        return (
            <div className="relative border rounded-lg overflow-hidden bg-white">
                <div className="absolute top-2 right-2 z-10 flex gap-1">
                    <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7 bg-white/80 hover:bg-white shadow-sm"
                        onClick={handleRefresh}
                    >
                        <RefreshCw className="h-3.5 w-3.5" />
                    </Button>
                    <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7 bg-white/80 hover:bg-white shadow-sm"
                        onClick={() => {
                            const blob = new Blob([htmlContent], { type: 'text/html' });
                            const url = URL.createObjectURL(blob);
                            window.open(url, '_blank');
                        }}
                    >
                        <ExternalLink className="h-3.5 w-3.5" />
                    </Button>
                </div>
                <iframe
                    key={key}
                    srcDoc={htmlContent}
                    className="w-full h-[400px] border-0"
                    sandbox="allow-scripts allow-same-origin"
                    title={artifact.title}
                />
            </div>
        );
    }

    // For React/JSX/Vue/Svelte - use Sandpack (dynamic with loading already handles suspense)
    if (['react', 'jsx', 'tsx', 'vue', 'svelte', 'javascript', 'typescript'].includes(artifact.language) ||
        artifact.type === 'component') {
        return <SandpackPreview artifact={artifact} height={400} />;
    }

    // For Python - use Pyodide runner
    if (artifact.language === 'python') {
        return <PythonRunner artifact={artifact} />;
    }

    return null;
}

interface ArtifactCardProps {
    artifact: CodeArtifact;
    isActive: boolean;
    onSelect: () => void;
    onDelete: () => void;
}

function ArtifactCard({ artifact, isActive, onSelect, onDelete }: ArtifactCardProps) {
    const [expanded, setExpanded] = useState(true);
    const [showPreview, setShowPreview] = useState(false);
    const meta = LANGUAGE_META[artifact.language] || LANGUAGE_META.other;
    const canPreview = isPreviewable(artifact) || isPythonExecutable(artifact);

    const handleDownload = () => {
        const ext = artifact.language === 'typescript' ? 'ts'
            : artifact.language === 'javascript' ? 'js'
            : artifact.language === 'python' ? 'py'
            : artifact.language;
        const filename = `${artifact.title.toLowerCase().replace(/\s+/g, '-')}.${ext}`;
        const blob = new Blob([artifact.code], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        a.click();
        URL.revokeObjectURL(url);
        toast.success(`Baixado: ${filename}`);
    };

    return (
        <div
            className={cn(
                "border rounded-xl overflow-hidden transition-all",
                isActive ? "border-primary ring-2 ring-primary/20" : "border-border",
                artifact.isStreaming && "border-blue-400 animate-pulse"
            )}
        >
            {/* Header */}
            <div
                className={cn(
                    "flex items-center gap-2 px-4 py-3 cursor-pointer",
                    isActive ? "bg-primary/5" : "bg-muted/30 hover:bg-muted/50"
                )}
                onClick={onSelect}
            >
                <button
                    onClick={(e) => { e.stopPropagation(); setExpanded(!expanded); }}
                    className="p-0.5 hover:bg-muted rounded"
                >
                    {expanded ? (
                        <ChevronDown className="h-4 w-4 text-muted-foreground" />
                    ) : (
                        <ChevronRight className="h-4 w-4 text-muted-foreground" />
                    )}
                </button>

                <div className={cn("w-2 h-2 rounded-full", meta.color)} />

                <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                        <span className="font-medium text-sm truncate">{artifact.title}</span>
                        {artifact.isStreaming && (
                            <Loader2 className="h-3 w-3 animate-spin text-blue-500" />
                        )}
                    </div>
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                        <span>{meta.label}</span>
                        {artifact.agent && (
                            <>
                                <span>•</span>
                                <span>{artifact.agent}</span>
                            </>
                        )}
                    </div>
                </div>

                <div className="flex items-center gap-1">
                    {canPreview && (
                        <Button
                            variant="ghost"
                            size="icon"
                            className="h-7 w-7"
                            onClick={(e) => { e.stopPropagation(); setShowPreview(!showPreview); }}
                            title={showPreview ? "Mostrar código" : "Preview"}
                        >
                            <Play className={cn("h-3.5 w-3.5", showPreview && "text-primary")} />
                        </Button>
                    )}
                    <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7"
                        onClick={(e) => { e.stopPropagation(); handleDownload(); }}
                        title="Download"
                    >
                        <Download className="h-3.5 w-3.5" />
                    </Button>
                    <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7 text-destructive hover:text-destructive"
                        onClick={(e) => { e.stopPropagation(); onDelete(); }}
                        title="Deletar"
                    >
                        <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                </div>
            </div>

            {/* Content */}
            {expanded && (
                <div className="p-4 border-t">
                    {artifact.description && (
                        <p className="text-sm text-muted-foreground mb-3">
                            {artifact.description}
                        </p>
                    )}

                    {showPreview && canPreview ? (
                        <ArtifactPreview artifact={artifact} />
                    ) : (
                        <CodeHighlighter
                            code={artifact.code}
                            language={artifact.language}
                            isStreaming={artifact.isStreaming}
                            showLineNumbers
                            maxHeight={400}
                        />
                    )}
                </div>
            )}
        </div>
    );
}

type ViewMode = 'list' | 'diff';

export function CodeArtifactViewer() {
    const {
        codeArtifacts,
        activeArtifactId,
        setActiveArtifact,
        deleteArtifact,
        clearArtifacts,
    } = useCanvasStore();

    const [viewMode, setViewMode] = useState<ViewMode>('list');

    const sortedArtifacts = useMemo(() =>
        [...codeArtifacts].sort((a, b) => b.createdAt - a.createdAt),
        [codeArtifacts]
    );

    if (sortedArtifacts.length === 0) {
        return (
            <div className="flex flex-col items-center justify-center h-full p-8 text-center">
                <FileCode className="h-16 w-16 text-muted-foreground/30 mb-4" />
                <h3 className="text-lg font-medium text-muted-foreground mb-2">
                    Nenhum artefato de código
                </h3>
                <p className="text-sm text-muted-foreground/70 max-w-md">
                    Quando a IA gerar código, snippets ou componentes, eles aparecerão aqui
                    para você revisar, copiar ou executar.
                </p>
            </div>
        );
    }

    return (
        <div className="space-y-4">
            {/* Header */}
            <div className="flex items-center justify-between flex-wrap gap-2">
                <div className="flex items-center gap-2">
                    <Code2 className="h-5 w-5 text-primary" />
                    <span className="font-medium">
                        {sortedArtifacts.length} artefato{sortedArtifacts.length !== 1 && 's'}
                    </span>
                </div>

                <div className="flex items-center gap-2">
                    {/* View Mode Toggle */}
                    {sortedArtifacts.length >= 2 && (
                        <div className="flex rounded-md border">
                            <button
                                onClick={() => setViewMode('list')}
                                className={cn(
                                    "px-2 py-1 text-xs",
                                    viewMode === 'list' ? "bg-primary text-primary-foreground" : "hover:bg-muted"
                                )}
                                title="Lista"
                            >
                                <Code2 className="h-3.5 w-3.5" />
                            </button>
                            <button
                                onClick={() => setViewMode('diff')}
                                className={cn(
                                    "px-2 py-1 text-xs",
                                    viewMode === 'diff' ? "bg-primary text-primary-foreground" : "hover:bg-muted"
                                )}
                                title="Comparar"
                            >
                                <GitCompareArrows className="h-3.5 w-3.5" />
                            </button>
                        </div>
                    )}

                    {/* Export ZIP */}
                    <ArtifactExporter artifacts={sortedArtifacts} />

                    {/* Clear All */}
                    <Button
                        variant="ghost"
                        size="sm"
                        className="text-destructive hover:text-destructive"
                        onClick={() => {
                            if (confirm('Remover todos os artefatos?')) {
                                clearArtifacts();
                            }
                        }}
                    >
                        <Trash2 className="h-3.5 w-3.5 mr-1.5" />
                        Limpar
                    </Button>
                </div>
            </div>

            {/* Content based on view mode */}
            {viewMode === 'diff' ? (
                <ArtifactDiffSelector artifacts={sortedArtifacts} />
            ) : (
                /* Artifact List */
                <div className="space-y-3">
                    {sortedArtifacts.map((artifact) => (
                        <ArtifactCard
                            key={artifact.id}
                            artifact={artifact}
                            isActive={artifact.id === activeArtifactId}
                            onSelect={() => setActiveArtifact(artifact.id)}
                            onDelete={() => deleteArtifact(artifact.id)}
                        />
                    ))}
                </div>
            )}
        </div>
    );
}

export default CodeArtifactViewer;
