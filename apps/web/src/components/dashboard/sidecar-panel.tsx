'use client';

import { useState } from 'react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';
import { useCanvasStore } from '@/stores/canvas-store';
import {
    FileSearch,
    Scale,
    History,
    Users,
    ChevronRight,
    ExternalLink,
    AlertTriangle,
    CheckCircle2,
    XCircle,
    BookOpen,
} from 'lucide-react';
import { cn } from '@/lib/utils';

interface SidecarPanelProps {
    collapsed?: boolean;
    onToggleCollapse?: () => void;
    className?: string;
}

export function SidecarPanel({
    collapsed = false,
    onToggleCollapse,
    className,
}: SidecarPanelProps) {
    const { contentHistory, historyIndex, citationAudit, metadata } = useCanvasStore();
    const [activeTab, setActiveTab] = useState('fontes');

    // Extract sources from metadata if available
    const ragSources = metadata?.rag_sources || [];
    const auditData = metadata?.audit || null;
    const agentDebate = metadata?.debate || null;

    if (collapsed) {
        return (
            <div className="flex flex-col items-center py-4 px-1 border-l border-outline/30 bg-muted/10 h-full">
                <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8 mb-4"
                    onClick={onToggleCollapse}
                    title="Expandir painel"
                >
                    <ChevronRight className="h-4 w-4 rotate-180" />
                </Button>
                <div className="flex flex-col gap-3 items-center text-muted-foreground">
                    <FileSearch className="h-4 w-4" />
                    <Scale className="h-4 w-4" />
                    <History className="h-4 w-4" />
                    <Users className="h-4 w-4" />
                </div>
            </div>
        );
    }

    return (
        <div className={cn("flex flex-col h-full border-l border-outline/30 bg-muted/5", className)}>
            {/* Header */}
            <div className="flex items-center justify-between px-3 py-2 border-b border-outline/20">
                <span className="text-xs font-semibold text-foreground uppercase tracking-wide">
                    Painel de Controle
                </span>
                {onToggleCollapse && (
                    <Button
                        variant="ghost"
                        size="icon"
                        className="h-6 w-6"
                        onClick={onToggleCollapse}
                    >
                        <ChevronRight className="h-3 w-3" />
                    </Button>
                )}
            </div>

            {/* Tabs */}
            <Tabs value={activeTab} onValueChange={setActiveTab} className="flex-1 flex flex-col overflow-hidden">
                <TabsList className="w-full justify-start rounded-none border-b border-outline/20 bg-transparent h-auto p-0">
                    <TabsTrigger
                        value="fontes"
                        className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent text-xs py-2 px-3"
                    >
                        <FileSearch className="h-3 w-3 mr-1" />
                        Fontes
                    </TabsTrigger>
                    <TabsTrigger
                        value="audit"
                        className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent text-xs py-2 px-3"
                    >
                        <Scale className="h-3 w-3 mr-1" />
                        Audit
                    </TabsTrigger>
                    <TabsTrigger
                        value="versoes"
                        className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent text-xs py-2 px-3"
                    >
                        <History className="h-3 w-3 mr-1" />
                        Versões
                    </TabsTrigger>
                </TabsList>

                {/* Fontes Tab */}
                <TabsContent value="fontes" className="flex-1 overflow-y-auto p-3 m-0">
                    {ragSources.length > 0 ? (
                        <div className="space-y-2">
                            {ragSources.map((source: any, idx: number) => (
                                <div key={idx} className="p-2 rounded-lg border border-outline/20 bg-background/50 text-xs">
                                    <div className="flex items-start gap-2">
                                        <BookOpen className="h-3.5 w-3.5 text-primary mt-0.5 flex-shrink-0" />
                                        <div className="flex-1 min-w-0">
                                            <p className="font-medium truncate">{source.title || source.filename || `Fonte ${idx + 1}`}</p>
                                            <p className="text-muted-foreground truncate text-[10px]">{source.type || 'Documento'}</p>
                                        </div>
                                        <Button variant="ghost" size="icon" className="h-5 w-5 flex-shrink-0">
                                            <ExternalLink className="h-3 w-3" />
                                        </Button>
                                    </div>
                                </div>
                            ))}
                        </div>
                    ) : (
                        <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
                            <FileSearch className="h-8 w-8 opacity-20 mb-2" />
                            <p className="text-xs text-center">Nenhuma fonte RAG utilizada.</p>
                            <p className="text-[10px] text-center">Adicione documentos ao contexto.</p>
                        </div>
                    )}
                </TabsContent>

                {/* Auditoria Tab */}
                <TabsContent value="audit" className="flex-1 overflow-y-auto p-3 m-0">
                    {citationAudit.length > 0 ? (
                        <div className="space-y-2">
                            {citationAudit.map((citation, idx) => (
                                <div
                                    key={idx}
                                    className={cn(
                                        "p-2 rounded-lg border text-xs",
                                        citation.status === 'valid' && "border-green-200 bg-green-50/50",
                                        citation.status === 'suspicious' && "border-yellow-200 bg-yellow-50/50",
                                        citation.status === 'hallucination' && "border-red-200 bg-red-50/50",
                                    )}
                                >
                                    <div className="flex items-start gap-2">
                                        {citation.status === 'valid' && <CheckCircle2 className="h-3.5 w-3.5 text-green-600 mt-0.5" />}
                                        {citation.status === 'suspicious' && <AlertTriangle className="h-3.5 w-3.5 text-yellow-600 mt-0.5" />}
                                        {citation.status === 'hallucination' && <XCircle className="h-3.5 w-3.5 text-red-600 mt-0.5" />}
                                        <div className="flex-1">
                                            <p className="font-medium">{citation.citation}</p>
                                            {citation.message && (
                                                <p className="text-muted-foreground text-[10px] mt-1">{citation.message}</p>
                                            )}
                                        </div>
                                    </div>
                                </div>
                            ))}
                        </div>
                    ) : (
                        <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
                            <Scale className="h-8 w-8 opacity-20 mb-2" />
                            <p className="text-xs text-center">Nenhuma citação auditada.</p>
                            <p className="text-[10px] text-center">Execute a auditoria no documento.</p>
                        </div>
                    )}
                </TabsContent>

                {/* Versões Tab */}
                <TabsContent value="versoes" className="flex-1 overflow-y-auto p-3 m-0">
                    {contentHistory.length > 0 ? (
                        <div className="space-y-2">
                            {contentHistory.map((entry, idx) => (
                                <div
                                    key={idx}
                                    className={cn(
                                        "p-2 rounded-lg border text-xs cursor-pointer transition-colors",
                                        idx === historyIndex
                                            ? "border-primary bg-primary/5"
                                            : "border-outline/20 bg-background/50 hover:bg-muted/50"
                                    )}
                                >
                                    <div className="flex items-center justify-between">
                                        <div className="flex items-center gap-2">
                                            <span className="font-mono text-[10px] text-muted-foreground">v{idx + 1}</span>
                                            <span className="font-medium">{entry.label}</span>
                                        </div>
                                        {idx === historyIndex && (
                                            <span className="text-[10px] text-primary font-medium">Atual</span>
                                        )}
                                    </div>
                                    <p className="text-muted-foreground text-[10px] mt-1">
                                        {new Date(entry.timestamp).toLocaleTimeString('pt-BR', {
                                            hour: '2-digit',
                                            minute: '2-digit'
                                        })}
                                    </p>
                                </div>
                            ))}
                        </div>
                    ) : (
                        <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
                            <History className="h-8 w-8 opacity-20 mb-2" />
                            <p className="text-xs text-center">Nenhuma versão registrada.</p>
                            <p className="text-[10px] text-center">O histórico aparece após edições.</p>
                        </div>
                    )}
                </TabsContent>
            </Tabs>
        </div>
    );
}

export default SidecarPanel;
