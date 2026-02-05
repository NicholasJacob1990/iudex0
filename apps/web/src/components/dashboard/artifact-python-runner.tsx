'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { type CodeArtifact } from '@/stores/canvas-store';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import {
    Play,
    Square,
    Loader2,
    Terminal,
    AlertCircle,
    CheckCircle2,
    Download,
    Trash2,
} from 'lucide-react';
import { toast } from 'sonner';

// Pyodide type declarations
declare global {
    interface Window {
        loadPyodide?: (config?: { indexURL?: string }) => Promise<PyodideInterface>;
        pyodide?: PyodideInterface;
    }
}

interface PyodideInterface {
    runPython: (code: string) => any;
    runPythonAsync: (code: string) => Promise<any>;
    loadPackagesFromImports: (code: string) => Promise<void>;
    setStdout: (options: { batched: (output: string) => void }) => void;
    setStderr: (options: { batched: (output: string) => void }) => void;
    globals: Map<string, any>;
}

interface PythonRunnerProps {
    artifact: CodeArtifact;
    className?: string;
}

type ExecutionStatus = 'idle' | 'loading' | 'running' | 'success' | 'error';

interface OutputLine {
    type: 'stdout' | 'stderr' | 'result' | 'info';
    content: string;
    timestamp: number;
}

const PYODIDE_CDN = 'https://cdn.jsdelivr.net/pyodide/v0.25.0/full/';

export function PythonRunner({ artifact, className }: PythonRunnerProps) {
    const [status, setStatus] = useState<ExecutionStatus>('idle');
    const [output, setOutput] = useState<OutputLine[]>([]);
    const [pyodideLoaded, setPyodideLoaded] = useState(false);
    const [loadProgress, setLoadProgress] = useState(0);
    const outputRef = useRef<HTMLDivElement>(null);
    const abortRef = useRef(false);

    // Define addOutput first, before useEffect that uses it
    const addOutput = useCallback((type: OutputLine['type'], content: string) => {
        setOutput(prev => [...prev, { type, content, timestamp: Date.now() }]);
    }, []);

    // Load Pyodide script
    useEffect(() => {
        if (window.pyodide) {
            setPyodideLoaded(true);
            return;
        }

        const script = document.createElement('script');
        script.src = `${PYODIDE_CDN}pyodide.js`;
        script.async = true;

        script.onload = async () => {
            try {
                setStatus('loading');
                setLoadProgress(10);

                const pyodide = await window.loadPyodide!({
                    indexURL: PYODIDE_CDN,
                });

                setLoadProgress(100);
                window.pyodide = pyodide;
                setPyodideLoaded(true);
                setStatus('idle');

                addOutput('info', 'Pyodide carregado com sucesso');
            } catch (error) {
                console.error('Failed to load Pyodide:', error);
                setStatus('error');
                addOutput('stderr', `Erro ao carregar Pyodide: ${error}`);
            }
        };

        script.onerror = () => {
            setStatus('error');
            addOutput('stderr', 'Falha ao carregar Pyodide CDN');
        };

        document.body.appendChild(script);

        return () => {
            // Don't remove script, keep Pyodide loaded
        };
    }, [addOutput]);

    const clearOutput = () => {
        setOutput([]);
    };

    // Auto-scroll output
    useEffect(() => {
        if (outputRef.current) {
            outputRef.current.scrollTop = outputRef.current.scrollHeight;
        }
    }, [output]);

    const runCode = async () => {
        if (!window.pyodide || status === 'running') return;

        abortRef.current = false;
        setStatus('running');
        clearOutput();
        addOutput('info', `Executando: ${artifact.title}`);

        const pyodide = window.pyodide;

        // Set up stdout/stderr capture
        pyodide.setStdout({
            batched: (text) => {
                if (!abortRef.current) {
                    addOutput('stdout', text);
                }
            },
        });

        pyodide.setStderr({
            batched: (text) => {
                if (!abortRef.current) {
                    addOutput('stderr', text);
                }
            },
        });

        try {
            // Load any imports
            addOutput('info', 'Carregando dependências...');
            await pyodide.loadPackagesFromImports(artifact.code);

            if (abortRef.current) {
                addOutput('info', 'Execução cancelada');
                setStatus('idle');
                return;
            }

            // Run the code
            addOutput('info', 'Executando código...');
            const result = await pyodide.runPythonAsync(artifact.code);

            if (result !== undefined && result !== null) {
                addOutput('result', `Resultado: ${String(result)}`);
            }

            setStatus('success');
            addOutput('info', 'Execução concluída');
        } catch (error: any) {
            setStatus('error');
            addOutput('stderr', error.message || String(error));
        }
    };

    const stopExecution = () => {
        abortRef.current = true;
        setStatus('idle');
        addOutput('info', 'Execução interrompida pelo usuário');
    };

    const downloadOutput = () => {
        const content = output.map(o => `[${o.type}] ${o.content}`).join('\n');
        const blob = new Blob([content], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${artifact.title.replace(/\s+/g, '-')}-output.txt`;
        a.click();
        URL.revokeObjectURL(url);
        toast.success('Output baixado');
    };

    return (
        <div className={cn("border rounded-lg overflow-hidden", className)}>
            {/* Toolbar */}
            <div className="flex items-center justify-between px-3 py-2 bg-muted/30 border-b">
                <div className="flex items-center gap-2">
                    <Terminal className="h-4 w-4 text-muted-foreground" />
                    <span className="text-sm font-medium">Python Runner</span>
                    {status === 'loading' && (
                        <span className="text-xs text-muted-foreground">
                            Carregando Pyodide ({loadProgress}%)
                        </span>
                    )}
                </div>

                <div className="flex items-center gap-1">
                    {status === 'running' ? (
                        <Button
                            variant="ghost"
                            size="sm"
                            onClick={stopExecution}
                            className="h-7 text-red-600 hover:text-red-700"
                        >
                            <Square className="h-3.5 w-3.5 mr-1" />
                            Parar
                        </Button>
                    ) : (
                        <Button
                            variant="ghost"
                            size="sm"
                            onClick={runCode}
                            disabled={!pyodideLoaded || status === 'loading'}
                            className="h-7"
                        >
                            {status === 'loading' ? (
                                <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" />
                            ) : (
                                <Play className="h-3.5 w-3.5 mr-1" />
                            )}
                            Executar
                        </Button>
                    )}

                    <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7"
                        onClick={clearOutput}
                        disabled={output.length === 0}
                    >
                        <Trash2 className="h-3.5 w-3.5" />
                    </Button>

                    <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7"
                        onClick={downloadOutput}
                        disabled={output.length === 0}
                    >
                        <Download className="h-3.5 w-3.5" />
                    </Button>
                </div>
            </div>

            {/* Output */}
            <div
                ref={outputRef}
                className="bg-slate-900 text-slate-100 p-3 font-mono text-xs min-h-[200px] max-h-[400px] overflow-y-auto"
            >
                {output.length === 0 ? (
                    <div className="text-slate-500 text-center py-8">
                        {pyodideLoaded
                            ? 'Clique em "Executar" para rodar o código Python'
                            : 'Carregando ambiente Python...'}
                    </div>
                ) : (
                    output.map((line, index) => (
                        <div
                            key={index}
                            className={cn(
                                "py-0.5 flex items-start gap-2",
                                line.type === 'stderr' && "text-red-400",
                                line.type === 'result' && "text-emerald-400",
                                line.type === 'info' && "text-blue-400 italic"
                            )}
                        >
                            <span className="opacity-50 select-none">
                                {line.type === 'stdout' && '›'}
                                {line.type === 'stderr' && '!'}
                                {line.type === 'result' && '='}
                                {line.type === 'info' && '#'}
                            </span>
                            <span className="whitespace-pre-wrap break-all">
                                {line.content}
                            </span>
                        </div>
                    ))
                )}

                {status === 'running' && (
                    <div className="flex items-center gap-2 py-2 text-blue-400">
                        <Loader2 className="h-3 w-3 animate-spin" />
                        <span>Executando...</span>
                    </div>
                )}
            </div>

            {/* Status bar */}
            <div className="px-3 py-1.5 bg-slate-800 border-t border-slate-700 flex items-center justify-between text-xs">
                <div className="flex items-center gap-2">
                    {status === 'success' && (
                        <>
                            <CheckCircle2 className="h-3 w-3 text-emerald-400" />
                            <span className="text-emerald-400">Sucesso</span>
                        </>
                    )}
                    {status === 'error' && (
                        <>
                            <AlertCircle className="h-3 w-3 text-red-400" />
                            <span className="text-red-400">Erro</span>
                        </>
                    )}
                    {status === 'idle' && pyodideLoaded && (
                        <span className="text-slate-500">Pronto</span>
                    )}
                </div>
                <span className="text-slate-500">
                    Pyodide {pyodideLoaded ? '✓' : '...'}
                </span>
            </div>
        </div>
    );
}

export default PythonRunner;
