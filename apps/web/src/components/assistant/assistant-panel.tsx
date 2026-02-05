'use client';

import React, { useState, useRef, useEffect, useCallback } from 'react';
import { MessageSquare, X, Send, Loader2, Sparkles, Minimize2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { apiClient } from '@/lib/api-client';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  citations?: Array<{ source?: string; title?: string; id?: string }>;
  timestamp: number;
}

interface AssistantPanelProps {
  open: boolean;
  onClose: () => void;
  contextType?: 'workflow' | 'document' | 'corpus' | null;
  contextId?: string | null;
  contextLabel?: string;
}

export function AssistantPanel({
  open,
  onClose,
  contextType,
  contextId,
  contextLabel,
}: AssistantPanelProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [minimized, setMinimized] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Focus input when opened
  useEffect(() => {
    if (open && !minimized) {
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [open, minimized]);

  const handleSend = useCallback(async () => {
    if (!input.trim() || streaming) return;

    const userMessage: Message = {
      role: 'user',
      content: input.trim(),
      timestamp: Date.now(),
    };
    setMessages((prev) => [...prev, userMessage]);
    const currentInput = input.trim();
    setInput('');
    setStreaming(true);

    const assistantMessage: Message = {
      role: 'assistant',
      content: '',
      timestamp: Date.now(),
    };
    setMessages((prev) => [...prev, assistantMessage]);

    try {
      const response = await apiClient.fetchWithAuth('/assistant/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: currentInput,
          context_type: contextType || null,
          context_id: contextId || null,
          conversation_history: messages.map((m) => ({
            role: m.role,
            content: m.content,
          })),
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const reader = response.body?.getReader();
      if (!reader) throw new Error('No reader');

      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.startsWith('data:')) continue;
          try {
            const parsed = JSON.parse(line.slice(5).trim());
            if (parsed.content) {
              setMessages((prev) => {
                const updated = [...prev];
                const last = updated[updated.length - 1];
                if (last?.role === 'assistant') {
                  last.content += parsed.content;
                }
                return [...updated];
              });
            }
            if (parsed.citations) {
              setMessages((prev) => {
                const updated = [...prev];
                const last = updated[updated.length - 1];
                if (last?.role === 'assistant') {
                  last.citations = parsed.citations;
                }
                return [...updated];
              });
            }
          } catch {
            // skip parse errors
          }
        }
      }
    } catch (err: unknown) {
      const errorMsg =
        err instanceof Error ? err.message : 'Erro desconhecido';
      setMessages((prev) => {
        const updated = [...prev];
        const last = updated[updated.length - 1];
        if (last?.role === 'assistant') {
          last.content = `Erro ao processar mensagem: ${errorMsg}. Tente novamente.`;
        }
        return [...updated];
      });
    } finally {
      setStreaming(false);
    }
  }, [input, streaming, messages, contextType, contextId]);

  if (!open) return null;

  if (minimized) {
    return (
      <button
        onClick={() => setMinimized(false)}
        className="fixed bottom-4 right-4 z-50 flex items-center gap-2 px-4 py-2.5 bg-violet-600 text-white rounded-full shadow-lg hover:bg-violet-500 transition-colors"
      >
        <MessageSquare className="h-4 w-4" />
        <span className="text-sm font-medium">Assistente</span>
        {messages.length > 0 && (
          <span className="bg-white/20 text-xs px-1.5 py-0.5 rounded-full">
            {messages.length}
          </span>
        )}
      </button>
    );
  }

  return (
    <div className="fixed right-0 top-0 h-full w-[400px] z-50 bg-white dark:bg-slate-900 border-l border-slate-200 dark:border-slate-700 shadow-2xl flex flex-col">
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-slate-200 dark:border-slate-700 bg-gradient-to-r from-violet-50 to-indigo-50 dark:from-violet-950 dark:to-indigo-950">
        <Sparkles className="h-4 w-4 text-violet-500" />
        <div className="flex-1 min-w-0">
          <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-200">
            Assistente
          </h3>
          {contextLabel && (
            <p className="text-[10px] text-violet-600 dark:text-violet-400 truncate">
              Contexto: {contextLabel}
            </p>
          )}
        </div>
        <button
          onClick={() => setMinimized(true)}
          className="p-1 hover:bg-slate-200 dark:hover:bg-slate-700 rounded"
        >
          <Minimize2 className="h-3.5 w-3.5 text-slate-400" />
        </button>
        <button
          onClick={onClose}
          className="p-1 hover:bg-slate-200 dark:hover:bg-slate-700 rounded"
        >
          <X className="h-3.5 w-3.5 text-slate-400" />
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
        {messages.length === 0 && (
          <div className="text-center py-8">
            <Sparkles className="h-8 w-8 text-violet-300 mx-auto mb-3" />
            <p className="text-sm text-slate-500">Como posso ajudar?</p>
            {contextType && (
              <p className="text-xs text-slate-400 mt-1">
                Tenho acesso ao contexto do{' '}
                {contextType === 'workflow'
                  ? 'workflow'
                  : contextType === 'document'
                    ? 'documento'
                    : 'corpus'}{' '}
                atual.
              </p>
            )}
          </div>
        )}
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[85%] rounded-xl px-3 py-2 text-sm ${
                msg.role === 'user'
                  ? 'bg-violet-600 text-white'
                  : 'bg-slate-100 dark:bg-slate-800 text-slate-800 dark:text-slate-200'
              }`}
            >
              <p className="whitespace-pre-wrap">{msg.content}</p>
              {msg.citations && msg.citations.length > 0 && (
                <div className="mt-2 pt-2 border-t border-slate-200 dark:border-slate-700">
                  <p className="text-[10px] text-slate-500 mb-1">Fontes:</p>
                  {msg.citations.map((c, j) => (
                    <p
                      key={j}
                      className="text-[10px] text-slate-400 truncate"
                    >
                      [{j + 1}] {c.title || c.source}
                    </p>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
        {streaming &&
          messages[messages.length - 1]?.role === 'assistant' &&
          !messages[messages.length - 1]?.content && (
            <div className="flex justify-start">
              <div className="bg-slate-100 dark:bg-slate-800 rounded-xl px-3 py-2">
                <Loader2 className="h-4 w-4 animate-spin text-violet-500" />
              </div>
            </div>
          )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="border-t border-slate-200 dark:border-slate-700 px-4 py-3">
        <div className="flex gap-2">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
            placeholder="Pergunte ao assistente..."
            className="flex-1 h-10 max-h-24 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-violet-500"
            rows={1}
          />
          <Button
            size="icon"
            onClick={handleSend}
            disabled={!input.trim() || streaming}
            className="h-10 w-10 bg-violet-600 hover:bg-violet-500 text-white shrink-0"
          >
            {streaming ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
          </Button>
        </div>
      </div>
    </div>
  );
}
