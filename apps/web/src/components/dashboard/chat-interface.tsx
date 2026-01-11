"use client";

import { useState, useRef, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Send, FileText, Bot, User, Sparkles, Download, Save } from 'lucide-react';
import apiClient from '@/lib/api-client';
import { cn } from '@/lib/utils';
import ReactMarkdown from 'react-markdown';

interface ChatMessage {
    id: string;
    role: 'user' | 'assistant';
    content: string;
    sources?: any[];
}

export function ChatInterface({ caseId, caseContextFiles }: { caseId: string, caseContextFiles?: string[] }) {
    const [messages, setMessages] = useState<ChatMessage[]>([
        {
            id: 'welcome',
            role: 'assistant',
            content: 'Olá! Sou seu assistente jurídico. Os documentos do caso já estão no contexto. Como posso ajudar?'
        }
    ]);
    const [input, setInput] = useState('');
    const [loading, setLoading] = useState(false);
    const scrollRef = useRef<HTMLDivElement>(null);

    // Auto-scroll to bottom
    useEffect(() => {
        if (scrollRef.current) {
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
        }
    }, [messages]);

    const handleSend = async () => {
        if (!input.trim() || loading) return;

        const userMsg: ChatMessage = {
            id: Date.now().toString(),
            role: 'user',
            content: input
        };

        setMessages(prev => [...prev, userMsg]);
        setInput('');
        setLoading(true);

        try {
            // Prepare history for API
            const history = messages.map(m => ({
                role: m.role,
                content: m.content
            }));

            const response = await apiClient.chatWithDocs({
                case_id: caseId,
                message: userMsg.content,
                conversation_history: history,
                context_files: caseContextFiles || []
            });

            const assistantMsg: ChatMessage = {
                id: (Date.now() + 1).toString(),
                role: 'assistant',
                content: response.reply,
                sources: response.sources_used
            };

            setMessages(prev => [...prev, assistantMsg]);
        } catch (error) {
            console.error(error);
            const errorMsg: ChatMessage = {
                id: (Date.now() + 1).toString(),
                role: 'assistant',
                content: '❌ Ocorreu um erro ao processar sua mensagem. Tente novamente.'
            };
            setMessages(prev => [...prev, errorMsg]);
        } finally {
            setLoading(false);
        }
    };

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSend();
        }
    };

    return (
        <div className="flex flex-col h-[600px] border rounded-xl bg-card">
            {/* Header */}
            <div className="p-4 border-b flex justify-between items-center bg-muted/20 rounded-t-xl">
                <div className="flex items-center gap-2">
                    <Bot className="h-5 w-5 text-indigo-600" />
                    <div>
                        <h3 className="font-semibold text-sm">Chat Jurídico com Documentos</h3>
                        <p className="text-[10px] text-muted-foreground">
                            {caseContextFiles?.length || 0} arquivos no contexto
                        </p>
                    </div>
                </div>
                <div className="flex gap-2">
                    <Button variant="ghost" size="sm" title="Exportar Conversa">
                        <Download className="h-4 w-4" />
                    </Button>
                </div>
            </div>

            {/* Messages Area */}
            <ScrollArea className="flex-1 p-4" ref={scrollRef}>
                <div className="space-y-4">
                    {messages.map((msg) => (
                        <div
                            key={msg.id}
                            className={cn(
                                "flex gap-3 max-w-[85%]",
                                msg.role === 'user' ? "ml-auto flex-row-reverse" : "mr-auto"
                            )}
                        >
                            <div className={cn(
                                "h-8 w-8 rounded-full flex items-center justify-center shrink-0",
                                msg.role === 'user' ? "bg-indigo-600 text-white" : "bg-emerald-600 text-white"
                            )}>
                                {msg.role === 'user' ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
                            </div>

                            <div className={cn(
                                "rounded-lg p-3 text-sm leading-relaxed shadow-sm",
                                msg.role === 'user'
                                    ? "bg-indigo-600 text-white"
                                    : "bg-white border text-foreground"
                            )}>
                                {msg.role === 'assistant' ? (
                                    <div className="prose prose-sm dark:prose-invert max-w-none">
                                        <ReactMarkdown>{msg.content}</ReactMarkdown>
                                    </div>
                                ) : (
                                    <div className="whitespace-pre-wrap">{msg.content}</div>
                                )}

                                {/* Sources / Citations */}
                                {msg.sources && msg.sources.length > 0 && (
                                    <div className="mt-3 pt-2 border-t text-xs text-muted-foreground/80">
                                        <p className="font-semibold mb-1 flex items-center gap-1">
                                            <FileText className="h-3 w-3" /> Fontes Citadas:
                                        </p>
                                        <ul className="list-disc pl-4 space-y-1">
                                            {msg.sources.map((src, idx) => (
                                                <li key={idx}>
                                                    DOC: {src.doc_id || "Desconhecido"} (Score: {src.score?.toFixed(2)})
                                                </li>
                                            ))}
                                        </ul>
                                    </div>
                                )}
                            </div>
                        </div>
                    ))}

                    {loading && (
                        <div className="flex gap-3 mr-auto max-w-[80%]">
                            <div className="h-8 w-8 rounded-full bg-emerald-600 text-white flex items-center justify-center shrink-0">
                                <Bot className="h-4 w-4" />
                            </div>
                            <div className="bg-white border rounded-lg p-3 flex items-center gap-2">
                                <Sparkles className="h-4 w-4 animate-spin text-emerald-600" />
                                <span className="text-xs text-muted-foreground">Analisando documentos...</span>
                            </div>
                        </div>
                    )}
                </div>
            </ScrollArea>

            {/* Input Area */}
            <div className="p-4 border-t bg-muted/20 rounded-b-xl">
                <div className="flex gap-2 relative">
                    <Textarea
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        onKeyDown={handleKeyDown}
                        placeholder="Faça uma pergunta sobre os documentos..."
                        className="min-h-[50px] max-h-[150px] resize-none pr-12 bg-background"
                        disabled={loading}
                    />
                    <Button
                        size="icon"
                        className="absolute right-2 bottom-2 h-8 w-8 bg-indigo-600 hover:bg-indigo-700"
                        onClick={handleSend}
                        disabled={!input.trim() || loading}
                    >
                        <Send className="h-4 w-4" />
                    </Button>
                </div>
                <div className="mt-2 flex justify-center gap-2">
                    {['Resumir o caso', 'Quais os principais fatos?', 'Analisar riscos'].map(suggestion => (
                        <Button
                            key={suggestion}
                            variant="outline"
                            size="sm"
                            className="text-[10px] h-6 px-2 rounded-full bg-background hover:bg-muted"
                            onClick={() => setInput(suggestion)}
                        >
                            {suggestion}
                        </Button>
                    ))}
                </div>
            </div>
        </div>
    );
}
