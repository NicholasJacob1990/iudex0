"use client";

import React, { useState } from "react";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { Loader2, Copy, AlertTriangle, FileText, Split, CheckCircle } from "lucide-react";
import { toast } from "sonner";
import apiClient from "@/lib/api-client";

interface CrossFileDuplicatesModalProps {
    availableFiles: string[]; // List of file paths or names available for analysis
    onClose?: () => void;
}

interface DuplicateGroup {
    fingerprint: string;
    text_preview: string;
    occurrences: {
        file: string;
        count: number;
    }[];
}

interface AnalysisResult {
    analyzed_files: number;
    total_duplicates: number;
    duplicates: DuplicateGroup[];
    error?: string;
}

export function CrossFileDuplicatesModal({ availableFiles, onClose }: CrossFileDuplicatesModalProps) {
    const [isOpen, setIsOpen] = useState(false);
    const [selectedFiles, setSelectedFiles] = useState<Set<string>>(new Set());
    const [isAnalyzing, setIsAnalyzing] = useState(false);
    const [result, setResult] = useState<AnalysisResult | null>(null);

    const handleAnalyze = async () => {
        if (selectedFiles.size < 2) {
            toast.error("Selecione pelo menos 2 arquivos para análise cruzada.");
            return;
        }

        setIsAnalyzing(true);
        setResult(null);

        try {
            // Call the new API endpoint
            // Note: Currently assuming apiClient has a generic post method or we use fetch directly
            // Since we just added the endpoint, we might not have a typed method in apiClient yet.
            const response = await fetch('/api/advanced/cross-file-duplicates', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ files: Array.from(selectedFiles) })
            });

            if (!response.ok) throw new Error('Falha na análise');

            const data = await response.json();
            setResult(data);

            if (data.total_duplicates > 0) {
                toast.warning(`${data.total_duplicates} grupos de duplicatas encontrados!`);
            } else {
                toast.success("Nenhuma duplicata encontrada entre os arquivos.");
            }

        } catch (error: any) {
            toast.error("Erro na análise: " + (error.message || "Desconhecido"));
        } finally {
            setIsAnalyzing(false);
        }
    };

    const toggleFile = (file: string) => {
        const newSet = new Set(selectedFiles);
        if (newSet.has(file)) newSet.delete(file);
        else newSet.add(file);
        setSelectedFiles(newSet);
    };

    const selectAll = () => {
        if (selectedFiles.size === availableFiles.length) setSelectedFiles(new Set());
        else setSelectedFiles(new Set(availableFiles));
    };

    return (
        <Dialog open={isOpen} onOpenChange={setIsOpen}>
            <DialogTrigger asChild>
                <Button variant="outline" className="gap-2">
                    <Split className="w-4 h-4" />
                    Análise Cross-File
                </Button>
            </DialogTrigger>
            <DialogContent className="max-w-4xl max-h-[80vh] flex flex-col">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <Split className="w-5 h-5 text-indigo-600" />
                        Análise de Duplicatas entre Arquivos (Fingerprinting)
                    </DialogTitle>
                    <DialogDescription>
                        Detecta parágrafos idênticos ou muito similares compartilhados entre múltiplos documentos.
                    </DialogDescription>
                </DialogHeader>

                <div className="flex-1 overflow-hidden flex flex-col gap-4">
                    {/* File Selection */}
                    {!result && (
                        <div className="space-y-4">
                            <div className="flex items-center justify-between">
                                <h3 className="text-sm font-medium">Selecione arquivos para comparar:</h3>
                                <Button variant="ghost" size="sm" onClick={selectAll}>
                                    {selectedFiles.size === availableFiles.length ? "Desmarcar todos" : "Selecionar todos"}
                                </Button>
                            </div>
                            <ScrollArea className="h-[300px] border rounded-md p-4">
                                <div className="space-y-2">
                                    {availableFiles.map((file, i) => (
                                        <div key={i} className="flex items-center space-x-2">
                                            <Checkbox
                                                id={`file-${i}`}
                                                checked={selectedFiles.has(file)}
                                                onCheckedChange={() => toggleFile(file)}
                                            />
                                            <label
                                                htmlFor={`file-${i}`}
                                                className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70 cursor-pointer"
                                            >
                                                {file.split('/').pop()} {/* Show filename only */}
                                            </label>
                                        </div>
                                    ))}
                                </div>
                            </ScrollArea>

                            <div className="flex justify-end">
                                <Button onClick={handleAnalyze} disabled={isAnalyzing || selectedFiles.size < 2}>
                                    {isAnalyzing ? (
                                        <>
                                            <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Analisando...
                                        </>
                                    ) : (
                                        <>Iniciar Análise</>
                                    )}
                                </Button>
                            </div>
                        </div>
                    )}

                    {/* Results View */}
                    {result && (
                        <div className="flex flex-col h-full gap-4">
                            <div className="flex items-center justify-between bg-slate-50 dark:bg-slate-900 p-3 rounded-lg border">
                                <div className="flex gap-4 text-sm">
                                    <span>Arquivos analisados: <strong>{result.analyzed_files}</strong></span>
                                    <span>Duplicatas encontradas: <strong className="text-orange-600">{result.total_duplicates}</strong></span>
                                </div>
                                <Button variant="ghost" size="sm" onClick={() => setResult(null)}>
                                    Nova Análise
                                </Button>
                            </div>

                            <ScrollArea className="flex-1 border rounded-md">
                                <div className="p-4 space-y-6">
                                    {result.duplicates.length === 0 ? (
                                        <div className="text-center py-10 text-muted-foreground">
                                            <CheckCircle className="w-10 h-10 mx-auto mb-2 text-green-500" />
                                            <p>Nenhuma duplicata encontrada!</p>
                                        </div>
                                    ) : (
                                        result.duplicates.map((dup, idx) => (
                                            <div key={idx} className="border rounded-lg p-4 bg-card shadow-sm">
                                                <div className="mb-2 bg-slate-100 dark:bg-slate-800 p-2 rounded text-xs font-mono text-muted-foreground break-all">
                                                    Fingerprint: {dup.fingerprint.substring(0, 16)}...
                                                </div>

                                                <div className="mb-4">
                                                    <h4 className="text-xs font-semibold uppercase text-muted-foreground mb-1">Conteúdo Duplicado</h4>
                                                    <p className="text-sm italic text-slate-700 dark:text-slate-300 border-l-2 border-orange-300 pl-3 leading-relaxed">
                                                        &ldquo;{dup.text_preview}&rdquo;
                                                    </p>
                                                </div>

                                                <div>
                                                    <h4 className="text-xs font-semibold uppercase text-muted-foreground mb-2">Ocorrências ({dup.occurrences.length})</h4>
                                                    <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                                                        {dup.occurrences.map((occ, i) => (
                                                            <div key={i} className="flex items-center justify-between p-2 bg-slate-50 dark:bg-slate-900 rounded border text-sm">
                                                                <span className="truncate max-w-[200px]" title={occ.file}>
                                                                    {occ.file.split('/').pop()}
                                                                </span>
                                                                <Badge variant="secondary">x{occ.count}</Badge>
                                                            </div>
                                                        ))}
                                                    </div>
                                                </div>
                                            </div>
                                        ))
                                    )}
                                </div>
                            </ScrollArea>
                        </div>
                    )}
                </div>
            </DialogContent>
        </Dialog>
    );
}
