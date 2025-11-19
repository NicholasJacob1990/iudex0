'use client';

import { useState, useEffect } from 'react';
import { DocumentEditor } from '@/components/editor/document-editor';
import { ChatInterface } from '@/components/chat';
import { ContextSelector } from '@/components/chat/context-selector';
import { ContextDashboard } from '@/components/chat/context-dashboard';
import { useChatStore } from '@/stores';
import { Button } from '@/components/ui/button';
import {
    Maximize2,
    Minimize2,
    PanelLeftClose,
    PanelLeftOpen,
    Share2,
    Download,
    Sparkles
} from 'lucide-react';
import { cn } from '@/lib/utils';

export default function GeneratorPage() {
    const [isLeftPanelOpen, setIsLeftPanelOpen] = useState(true);
    const { currentChat, isSending, isAgentRunning, agentSteps } = useChatStore();
    const [editorContent, setEditorContent] = useState('');

    // Effect to update editor content when AI generates a "document"
    useEffect(() => {
        if (currentChat?.messages.length) {
            const lastMessage = currentChat.messages[currentChat.messages.length - 1];
            if (lastMessage.role === 'assistant' && (lastMessage.content.includes('# ') || lastMessage.content.length > 100)) {
                // Simple heuristic: if it looks like markdown/long text, put it in the editor
                // Convert markdown to HTML (simplified for demo)
                const htmlContent = lastMessage.content
                    .replace(/^# (.*$)/gim, '<h1>$1</h1>')
                    .replace(/^## (.*$)/gim, '<h2>$1</h2>')
                    .replace(/^### (.*$)/gim, '<h3>$1</h3>')
                    .replace(/\*\*(.*)\*\*/gim, '<strong>$1</strong>')
                    .replace(/\n/gim, '<br />');

                setEditorContent(htmlContent);
            }
        }
    }, [currentChat?.messages]);

    return (
        <div className="flex h-[calc(100vh-4rem)] overflow-hidden bg-background">
            {/* Left Panel - AI Counsel */}
            <div
                className={cn(
                    "flex flex-col border-r border-white/10 bg-[#0F1115] transition-all duration-300 ease-in-out",
                    isLeftPanelOpen ? "w-[450px]" : "w-0 opacity-0 overflow-hidden"
                )}
            >
                <div className="flex items-center justify-between border-b border-white/5 p-4">
                    <div className="flex items-center gap-2">
                        <Sparkles className="h-4 w-4 text-indigo-400" />
                        <span className="font-display font-semibold text-foreground">AI Counsel</span>
                    </div>
                    <div className="flex items-center gap-2">
                        <div className="flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1">
                            <span className="text-[10px] font-medium text-muted-foreground">Rigoroso</span>
                            <button
                                className="relative h-4 w-8 rounded-full bg-indigo-500 transition-colors focus:outline-none"
                                onClick={() => { }} // Todo: Connect to store
                            >
                                <div className="absolute right-0.5 top-0.5 h-3 w-3 rounded-full bg-white shadow-sm transition-transform" />
                            </button>
                        </div>
                        <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => setIsLeftPanelOpen(false)}
                            className="h-8 w-8 text-muted-foreground hover:text-foreground"
                        >
                            <PanelLeftClose className="h-4 w-4" />
                        </Button>
                    </div>
                </div>

                <div className="flex flex-1 flex-col overflow-hidden bg-muted/30">
                    {/* Context Indicator & Selector */}
                    <div className="border-b border-white/5 bg-white/5 backdrop-blur-sm">
                        <div className="flex items-center gap-2 px-4 py-2 text-xs text-muted-foreground border-b border-white/5">
                            <div className="flex h-2 w-2 animate-pulse rounded-full bg-emerald-500" />
                            <span className="font-medium text-emerald-400">Contexto Infinito Ativo</span>
                            <span className="ml-auto opacity-70">1.2M tokens</span>
                        </div>
                        <ContextSelector />
                    </div>

                    {/* Agent Process View (Overlay or Inline) */}
                    {isAgentRunning && (
                        <div className="border-b border-white/10 bg-indigo-950/20 p-4">
                            <h3 className="mb-3 text-xs font-semibold text-indigo-300 uppercase tracking-wider">
                                Processo Multi-Agente
                            </h3>
                            <div className="space-y-3">
                                {agentSteps.map((step) => (
                                    <div key={step.id} className="flex items-start gap-3">
                                        <div className={cn(
                                            "mt-0.5 flex h-5 w-5 items-center justify-center rounded-full border text-[10px]",
                                            step.status === 'completed' ? "border-emerald-500/50 bg-emerald-500/20 text-emerald-400" :
                                                step.status === 'working' ? "border-indigo-500/50 bg-indigo-500/20 text-indigo-400 animate-pulse" :
                                                    "border-white/10 bg-white/5 text-muted-foreground"
                                        )}>
                                            {step.status === 'completed' ? '✓' :
                                                step.status === 'working' ? '●' :
                                                    '○'}
                                        </div>
                                        <div className="flex-1 space-y-1">
                                            <div className="flex items-center justify-between">
                                                <span className={cn(
                                                    "text-xs font-medium",
                                                    step.status === 'working' ? "text-indigo-300" : "text-foreground"
                                                )}>
                                                    {step.agent === 'strategist' && 'Estrategista'}
                                                    {step.agent === 'researcher' && 'Pesquisador'}
                                                    {step.agent === 'drafter' && 'Redator'}
                                                    {step.agent === 'reviewer' && 'Revisor'}
                                                </span>
                                                {step.status === 'working' && (
                                                    <span className="text-[10px] text-indigo-400 animate-pulse">Processando...</span>
                                                )}
                                            </div>
                                            <p className="text-[11px] text-muted-foreground leading-tight">
                                                {step.details || step.message}
                                            </p>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Chat Interface */}
                    <div className="flex-1 overflow-hidden">
                        {currentChat ? (
                            <ChatInterface chatId={currentChat.id} />
                        ) : (
                            <ContextDashboard />
                        )}
                    </div>
                </div>
            </div>

            {/* Right Panel - Document Canvas */}
            <div className="flex flex-1 flex-col bg-muted/30">
                {/* Toolbar */}
                <div className="flex h-14 items-center justify-between border-b border-border bg-background px-6">
                    <div className="flex items-center gap-2">
                        {!isLeftPanelOpen && (
                            <Button
                                variant="ghost"
                                size="icon"
                                onClick={() => setIsLeftPanelOpen(true)}
                                className="mr-2 h-8 w-8"
                            >
                                <PanelLeftOpen className="h-4 w-4" />
                            </Button>
                        )}
                        <h2 className="font-display font-medium text-foreground">
                            {currentChat?.title || 'Minuta Sem Título'}
                        </h2>
                        <span className="rounded-full bg-yellow-500/10 px-2 py-0.5 text-[10px] font-medium text-yellow-600">
                            {isSending || isAgentRunning ? 'Gerando...' : 'Rascunho'}
                        </span>
                    </div>

                    <div className="flex items-center gap-2">
                        <Button variant="ghost" size="sm" className="text-muted-foreground">
                            <Share2 className="mr-2 h-4 w-4" />
                            Compartilhar
                        </Button>
                        <Button size="sm" className="bg-primary text-primary-foreground hover:bg-primary/90">
                            <Download className="mr-2 h-4 w-4" />
                            Exportar
                        </Button>
                    </div>
                </div>

                {/* Editor Container */}
                <div className="flex-1 overflow-y-auto bg-muted/30 p-8">
                    <DocumentEditor
                        content={editorContent}
                        onChange={setEditorContent}
                        placeholder="Comece a escrever sua minuta ou peça para a IA..."
                        editable={true}
                    />
                </div>
            </div>
        </div>
    );
}
