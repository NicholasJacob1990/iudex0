'use client';

import React, { useState } from 'react';
import JSZip from 'jszip';
import { type CodeArtifact, type ArtifactLanguage } from '@/stores/canvas-store';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
    DialogTrigger,
} from '@/components/ui/dialog';
import { Download, FolderArchive, FileCode, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';

// File extension mapping
const extensionMap: Record<ArtifactLanguage, string> = {
    typescript: 'ts',
    javascript: 'js',
    jsx: 'jsx',
    tsx: 'tsx',
    python: 'py',
    html: 'html',
    css: 'css',
    json: 'json',
    sql: 'sql',
    bash: 'sh',
    markdown: 'md',
    yaml: 'yaml',
    rust: 'rs',
    go: 'go',
    java: 'java',
    csharp: 'cs',
    react: 'tsx',
    vue: 'vue',
    svelte: 'svelte',
    other: 'txt',
};

// Folder structure by language type
const folderMap: Record<ArtifactLanguage, string> = {
    typescript: 'src',
    javascript: 'src',
    jsx: 'src/components',
    tsx: 'src/components',
    python: 'scripts',
    html: 'public',
    css: 'styles',
    json: 'config',
    sql: 'database',
    bash: 'scripts',
    markdown: 'docs',
    yaml: 'config',
    rust: 'src',
    go: 'src',
    java: 'src/main/java',
    csharp: 'src',
    react: 'src/components',
    vue: 'src/components',
    svelte: 'src/components',
    other: 'misc',
};

interface ArtifactExporterProps {
    artifacts: CodeArtifact[];
    className?: string;
}

export function ArtifactExporter({ artifacts, className }: ArtifactExporterProps) {
    const [open, setOpen] = useState(false);
    const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set(artifacts.map(a => a.id)));
    const [isExporting, setIsExporting] = useState(false);
    const [includeReadme, setIncludeReadme] = useState(true);
    const [organizeByLanguage, setOrganizeByLanguage] = useState(true);

    const toggleArtifact = (id: string) => {
        const newSelected = new Set(selectedIds);
        if (newSelected.has(id)) {
            newSelected.delete(id);
        } else {
            newSelected.add(id);
        }
        setSelectedIds(newSelected);
    };

    const selectAll = () => {
        setSelectedIds(new Set(artifacts.map(a => a.id)));
    };

    const selectNone = () => {
        setSelectedIds(new Set());
    };

    const generateFilename = (artifact: CodeArtifact): string => {
        const safeName = artifact.title
            .toLowerCase()
            .replace(/[^a-z0-9]+/g, '-')
            .replace(/^-|-$/g, '');
        const ext = extensionMap[artifact.language] || 'txt';
        return `${safeName}.${ext}`;
    };

    const generateReadme = (selected: CodeArtifact[]): string => {
        const lines: string[] = [
            '# Code Artifacts Export',
            '',
            `Generated: ${new Date().toISOString()}`,
            '',
            '## Contents',
            '',
        ];

        // Group by language
        const byLang = selected.reduce((acc, a) => {
            const lang = a.language;
            if (!acc[lang]) acc[lang] = [];
            acc[lang].push(a);
            return acc;
        }, {} as Record<string, CodeArtifact[]>);

        for (const [lang, items] of Object.entries(byLang)) {
            lines.push(`### ${lang.charAt(0).toUpperCase() + lang.slice(1)}`);
            lines.push('');
            for (const item of items) {
                const path = organizeByLanguage
                    ? `${folderMap[item.language as ArtifactLanguage]}/${generateFilename(item)}`
                    : generateFilename(item);
                lines.push(`- **${item.title}** - \`${path}\``);
                if (item.description) {
                    lines.push(`  - ${item.description}`);
                }
            }
            lines.push('');
        }

        lines.push('---');
        lines.push('');
        lines.push('*Exported from Iudex AI Platform*');

        return lines.join('\n');
    };

    const handleExport = async () => {
        const selected = artifacts.filter(a => selectedIds.has(a.id));
        if (selected.length === 0) {
            toast.error('Selecione pelo menos um artifact');
            return;
        }

        setIsExporting(true);

        try {
            const zip = new JSZip();

            // Add artifacts
            for (const artifact of selected) {
                const filename = generateFilename(artifact);
                const path = organizeByLanguage
                    ? `${folderMap[artifact.language as ArtifactLanguage]}/${filename}`
                    : filename;

                zip.file(path, artifact.code);
            }

            // Add README
            if (includeReadme) {
                zip.file('README.md', generateReadme(selected));
            }

            // Generate ZIP
            const blob = await zip.generateAsync({
                type: 'blob',
                compression: 'DEFLATE',
                compressionOptions: { level: 9 },
            });

            // Download
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `artifacts-${Date.now()}.zip`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);

            toast.success(`${selected.length} artifact(s) exportados`);
            setOpen(false);
        } catch (error) {
            console.error('Export error:', error);
            toast.error('Erro ao exportar artifacts');
        } finally {
            setIsExporting(false);
        }
    };

    if (artifacts.length === 0) {
        return null;
    }

    return (
        <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
                <Button variant="outline" size="sm" className={cn("gap-2", className)}>
                    <FolderArchive className="h-4 w-4" />
                    Exportar ZIP
                </Button>
            </DialogTrigger>
            <DialogContent className="max-w-md">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <FolderArchive className="h-5 w-5" />
                        Exportar Artifacts
                    </DialogTitle>
                    <DialogDescription>
                        Selecione os artifacts para incluir no arquivo ZIP
                    </DialogDescription>
                </DialogHeader>

                <div className="space-y-4 py-4">
                    {/* Options */}
                    <div className="flex items-center gap-4 text-sm">
                        <label className="flex items-center gap-2 cursor-pointer">
                            <Checkbox
                                checked={includeReadme}
                                onCheckedChange={(checked) => setIncludeReadme(!!checked)}
                            />
                            Incluir README.md
                        </label>
                        <label className="flex items-center gap-2 cursor-pointer">
                            <Checkbox
                                checked={organizeByLanguage}
                                onCheckedChange={(checked) => setOrganizeByLanguage(!!checked)}
                            />
                            Organizar por pasta
                        </label>
                    </div>

                    {/* Selection controls */}
                    <div className="flex items-center justify-between">
                        <span className="text-sm text-muted-foreground">
                            {selectedIds.size} de {artifacts.length} selecionados
                        </span>
                        <div className="flex gap-2">
                            <Button variant="ghost" size="sm" onClick={selectAll}>
                                Todos
                            </Button>
                            <Button variant="ghost" size="sm" onClick={selectNone}>
                                Nenhum
                            </Button>
                        </div>
                    </div>

                    {/* Artifact list */}
                    <div className="border rounded-lg divide-y max-h-[300px] overflow-y-auto">
                        {artifacts.map((artifact) => (
                            <label
                                key={artifact.id}
                                className="flex items-center gap-3 p-3 cursor-pointer hover:bg-muted/50"
                            >
                                <Checkbox
                                    checked={selectedIds.has(artifact.id)}
                                    onCheckedChange={() => toggleArtifact(artifact.id)}
                                />
                                <FileCode className="h-4 w-4 text-muted-foreground" />
                                <div className="flex-1 min-w-0">
                                    <div className="font-medium text-sm truncate">
                                        {artifact.title}
                                    </div>
                                    <div className="text-xs text-muted-foreground">
                                        {artifact.language} • {artifact.code.length} chars
                                    </div>
                                </div>
                            </label>
                        ))}
                    </div>
                </div>

                <DialogFooter>
                    <Button variant="outline" onClick={() => setOpen(false)}>
                        Cancelar
                    </Button>
                    <Button
                        onClick={handleExport}
                        disabled={selectedIds.size === 0 || isExporting}
                    >
                        {isExporting ? (
                            <>
                                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                                Exportando...
                            </>
                        ) : (
                            <>
                                <Download className="h-4 w-4 mr-2" />
                                Exportar ({selectedIds.size})
                            </>
                        )}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

export default ArtifactExporter;
