'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { cn } from '@/lib/utils';
import { formatDate } from '@/lib/utils';
import { User, Bot, Check, Copy, RotateCcw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';
import { useCanvasStore } from '@/stores/canvas-store';
import { DiffConfirmDialog } from '@/components/dashboard/diff-confirm-dialog';
import { parseMarkdownToHtmlSync } from '@/lib/markdown-parser';
import { DiagramViewer } from '@/components/dashboard/diagram-viewer';
import { ActivityPanel, type ActivityStep, type Citation } from './activity-panel';

interface Message {
  id: string;
  content: string;
  role: 'user' | 'assistant';
  timestamp: string;
  thinking?: string;
  isThinking?: boolean;  // NEW: Track if currently streaming thinking
  metadata?: any;
}

interface ChatMessageProps {
  message: Message;
  onCopy?: (message: Message) => void;
  onRegenerate?: (message: Message) => void;
  disableRegenerate?: boolean;
}

type CitationItem = {
  number: string;
  title?: string;
  url?: string;
  quote?: string;
};

// NEW: Loading dots component for thinking animation
function LoadingDots() {
  return (
    <span className="inline-flex gap-1">
      <span className="animate-bounce h-1 w-1 rounded-full bg-slate-400" style={{ animationDelay: '0ms' }} />
      <span className="animate-bounce h-1 w-1 rounded-full bg-slate-400" style={{ animationDelay: '150ms' }} />
      <span className="animate-bounce h-1 w-1 rounded-full bg-slate-400" style={{ animationDelay: '300ms' }} />
    </span>
  );
}

function escapeAttr(value: string) {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function injectCitationHtml(html: string, citationMap: Map<string, CitationItem>) {
  if (!html || citationMap.size === 0) return html;
  return html.replace(/\[(\d{1,3})\]/g, (match, num) => {
    const citation = citationMap.get(String(num));
    if (!citation) return match;
    const title = citation.title || citation.url || `Fonte ${num}`;
    const href =
      typeof citation.url === 'string' && /^https?:\/\//i.test(citation.url.trim())
        ? citation.url.trim()
        : '#';
    const tooltip = [title, citation.quote].filter(Boolean).join(' — ');
    return `<sup class="citation-inline" data-citation="${num}"><a href="${escapeAttr(href)}" target="_blank" rel="noreferrer noopener" title="${escapeAttr(tooltip)}">[${num}]</a></sup>`;
  });
}

export function ChatMessage({ message, onCopy, onRegenerate, disableRegenerate }: ChatMessageProps) {
  const isUser = message.role === 'user';
  const canvasSuggestion = !isUser ? message.metadata?.canvas_suggestion : null;
  const [diffOpen, setDiffOpen] = useState(false);
  const [thinkingOpen, setThinkingOpen] = useState(false);
  const autoOpenedRef = useRef(false);
  const [activityOpen, setActivityOpen] = useState(false);
  const activityAutoOpenedRef = useRef(false);
  const showActions = !isUser && (onCopy || onRegenerate);
  const modelLabel = !isUser ? (message.metadata?.model ? String(message.metadata.model) : '') : '';
  const thinkingEnabled = typeof message.metadata?.thinking_enabled === 'boolean'
    ? message.metadata.thinking_enabled
    : true;
  const rawThinkingText = typeof message.thinking === 'string'
    ? message.thinking.trim()
    : typeof message.metadata?.thinking === 'string'
      ? message.metadata.thinking.trim()
      : '';
  const thinkingText = thinkingEnabled ? rawThinkingText : '';
  const thinkingChunks = thinkingEnabled && Array.isArray(message.metadata?.thinkingChunks)
    ? message.metadata.thinkingChunks
      .filter((chunk: any) => chunk && typeof chunk.text === 'string')
      .map((chunk: any) => ({
        type: chunk.type === 'research' ? 'research' : chunk.type === 'summary' ? 'summary' : 'llm',
        text: String(chunk.text || '').trim(),
      }))
      .filter((chunk: { text: string }) => chunk.text)
    : [];
  // For Activity Panel: show ALL thinking chunks (not just summary)
  const allThinkingChunks = thinkingChunks;
  const hasThinkingContent = thinkingChunks.length > 0 || !!thinkingText;
  // Still track if actively thinking
  const isActivelyThinking = thinkingEnabled && !!message.isThinking;
  const canvasWrite = !isUser ? message.metadata?.canvas_write : null;
  const showCanvasApply = !isUser && !!canvasWrite;
  const showCanvasSuggestion = !isUser && !!canvasSuggestion;
  const [nowMs, setNowMs] = useState(() => Date.now());

  const streamTimes = useMemo(() => {
    const meta = message.metadata || {};
    const toNum = (v: any) => {
      const n = typeof v === 'number' ? v : Number(v);
      return Number.isFinite(n) ? n : null;
    };
    return {
      t0: toNum(meta.stream_t0),
      tAnswerStart: toNum(meta.stream_t_answer_start),
      tDone: toNum(meta.stream_t_done),
    };
  }, [message.metadata]);
  const isStreaming = !isUser && !streamTimes.tDone && !!(
    streamTimes.t0 ||
    streamTimes.tAnswerStart ||
    (thinkingEnabled && message.isThinking)
  );
  const activity = !isUser ? (message.metadata?.activity as any) : null;
  const activitySteps: Array<{ id: string; title: string; status?: string; detail?: string }> =
    activity && Array.isArray(activity.steps) ? activity.steps : [];
  const filteredActivitySteps = thinkingEnabled
    ? activitySteps
    : activitySteps.filter((step) => {
      const id = String(step?.id || '').toLowerCase();
      return !id.includes('thinking') && !id.includes('thought') && !id.includes('reason');
    });

  const citations: CitationItem[] = useMemo(() => {
    const raw = message.metadata?.citations;
    if (!Array.isArray(raw)) return [];
    return raw
      .map((item: any, idx: number) => {
        const number = String(item?.number ?? item?.n ?? item?.id ?? idx + 1);
        return {
          number,
          title: typeof item?.title === 'string' ? item.title : undefined,
          url: typeof item?.url === 'string' ? item.url : undefined,
          quote: typeof item?.quote === 'string' ? item.quote : undefined,
        } as CitationItem;
      })
      .filter((item: CitationItem) => item.number);
  }, [message.metadata]);

  const citationMap = useMemo(() => {
    const map = new Map<string, CitationItem>();
    citations.forEach((item) => {
      map.set(String(item.number), item);
    });
    return map;
  }, [citations]);

  useEffect(() => {
    if (isUser) return;
    if (!streamTimes.t0 && !streamTimes.tAnswerStart) return;
    if (streamTimes.tDone) return;
    const id = window.setInterval(() => setNowMs(Date.now()), 250);
    return () => window.clearInterval(id);
  }, [isUser, streamTimes.t0, streamTimes.tAnswerStart, streamTimes.tDone]);

  const thinkingSeconds = streamTimes.t0
    ? Math.max(0, Math.floor(((streamTimes.tAnswerStart ?? nowMs) - streamTimes.t0) / 1000))
    : null;
  const writingSeconds = streamTimes.tAnswerStart
    ? Math.max(0, Math.floor(((streamTimes.tDone ?? nowMs) - streamTimes.tAnswerStart) / 1000))
    : null;
  const showTimers = !isUser && (streamTimes.t0 || streamTimes.tAnswerStart);
  const contentParts = useMemo(() => {
    const raw = String(message.content || '');
    if (!raw) {
      return [{ key: 'md-0', type: 'markdown' as const, html: '' }];
    }
    const parts: Array<{ key?: string; type: 'markdown' | 'mermaid'; content?: string; html?: string }> = [];
    const mermaidRegex = /```mermaid\s*([\s\S]*?)```/gi;
    let lastIndex = 0;
    let match: RegExpExecArray | null;

    while ((match = mermaidRegex.exec(raw)) !== null) {
      if (match.index > lastIndex) {
        const segment = raw.slice(lastIndex, match.index);
        if (segment.length) {
          parts.push({ type: 'markdown', content: segment });
        }
      }
      const diagram = (match[1] || '').trim();
      if (diagram) {
        parts.push({ type: 'mermaid', content: diagram });
      }
      lastIndex = match.index + match[0].length;
    }

    const tail = raw.slice(lastIndex);
    if (tail.length) {
      parts.push({ type: 'markdown', content: tail });
    }

    if (!parts.length) {
      parts.push({ type: 'markdown', content: raw });
    }

    return parts.map((part, index) => ({
      ...part,
      key: `${part.type}-${index}`,
      html: part.type === 'markdown'
        ? injectCitationHtml(parseMarkdownToHtmlSync(part.content || ''), citationMap)
        : undefined,
    }));
  }, [message.content, citationMap]);

  useEffect(() => {
    if (isUser) return;
    if (autoOpenedRef.current) return;
    if (isStreaming || hasThinkingContent) {
      setThinkingOpen(true);
      autoOpenedRef.current = true;
    }
  }, [isUser, isStreaming, hasThinkingContent]);

  useEffect(() => {
    if (isUser) return;
    if (activityAutoOpenedRef.current) return;
    // Só abre Activity quando tiver algo "real" como pesquisa/fontes (igual à referência).
    if (filteredActivitySteps.length > 0 || citations.length > 0) {
      setActivityOpen(true);
      activityAutoOpenedRef.current = true;
    }
  }, [isUser, filteredActivitySteps.length, citations.length]);

  // Determine if sources should show inline in the message bubble (when Activity panel is closed)
  const hasActivityContent = filteredActivitySteps.length > 0 || citations.length > 0 || hasThinkingContent;
  const showActivityPanelNow = (activityOpen || thinkingOpen) && hasActivityContent;
  const showSourcesInBubble = !showActivityPanelNow && !isUser && citations.length > 0;

  const handleApplySuggestion = () => {
    if (!canvasSuggestion?.original || !canvasSuggestion?.replacement) {
      toast.error('Sugestão inválida para aplicar.');
      return;
    }

    const label = canvasSuggestion.action === 'shorten'
      ? 'Chat: Resumir trecho'
      : canvasSuggestion.action === 'improve'
        ? 'Chat: Melhorar trecho'
        : 'Chat: Aplicar trecho';

    const result = useCanvasStore.getState().applyTextReplacement(
      canvasSuggestion.original,
      canvasSuggestion.replacement,
      label
    );

    if (result.success) {
      toast.success('Sugestão aplicada ao documento.');
      useCanvasStore.getState().setHighlightedText(null);
      setDiffOpen(false);
      return;
    }

    if (result.reason === 'not_found') {
      toast.error('Trecho original não encontrado no documento.');
      return;
    }

    toast.error('Não foi possível aplicar a sugestão.');
  };

  const handleOpenDiff = () => {
    if (canvasSuggestion?.original) {
      useCanvasStore.getState().setHighlightedText(canvasSuggestion.original);
    }
    setDiffOpen(true);
  };

  const handleCloseDiff = () => {
    useCanvasStore.getState().setHighlightedText(null);
    setDiffOpen(false);
  };

  return (
    <>
      <div
        className={cn(
          'flex items-start gap-3 animate-fade-in',
          isUser && 'flex-row-reverse'
        )}
      >
        {/* Avatar */}
        <div
          className={cn(
            'flex h-10 w-10 items-center justify-center rounded-full border shadow-sm',
            isUser ? 'bg-gradient-to-br from-emerald-500 to-emerald-600 border-emerald-500 text-white' : 'bg-white border-slate-200 text-slate-600'
          )}
        >
          {isUser ? (
            <User className="h-5 w-5 text-white" />
          ) : (
            <Bot className="h-5 w-5 text-slate-600" />
          )}
        </div>

        {/* Message Content */}
        <div className={cn('flex flex-1 flex-col gap-1', isUser && 'items-end')}>
          {/* NEW: Unified Activity Panel (ChatGPT style) */}
          {!isUser && (
            <ActivityPanel
              steps={filteredActivitySteps as ActivityStep[]}
              citations={citations as Citation[]}
              thinkingChunks={allThinkingChunks}
              thinkingText={thinkingText}
              isThinking={isActivelyThinking}
              startTime={streamTimes.t0}
              endTime={streamTimes.tDone}
              open={activityOpen || thinkingOpen}
              onOpenChange={(open) => {
                setActivityOpen(open);
                setThinkingOpen(open);
              }}
              isStreaming={isStreaming}
            />
          )}
          <div
            className={cn(
              'max-w-[min(98%,110ch)] rounded-2xl border px-6 py-5 transition-all duration-200',
              isUser
                ? 'ml-auto bg-gradient-to-br from-slate-100 to-slate-50 text-black border-slate-200/60 shadow-sm'
                : 'bg-white text-black border-slate-200/80 shadow-[0_2px_8px_-4px_rgba(0,0,0,0.05)] hover:shadow-[0_4px_12px_-6px_rgba(0,0,0,0.08)]'
            )}
          >
            <div className="chat-markdown">
              {contentParts.map((part) => (
                part.type === 'mermaid' ? (
                  <div key={part.key} className="my-3">
                    <DiagramViewer code={part.content || ''} compact />
                  </div>
                ) : (
                  <div key={part.key} dangerouslySetInnerHTML={{ __html: part.html || '' }} />
                )
              ))}
            </div>
            {showSourcesInBubble && (
              <div className="mt-4 border-t border-slate-200 pt-3 text-xs text-slate-500">
                <div className="mb-2 font-semibold text-slate-600">Fontes</div>
                <div className="space-y-2">
                  {citations.map((item) => (
                    <div key={`${item.number}-${item.url || item.title || ''}`} className="space-y-1">
                      <a
                        href={item.url || '#'}
                        target="_blank"
                        rel="noreferrer noopener"
                        className="inline-flex items-center gap-2 text-slate-700 hover:text-slate-900"
                      >
                        <span className="rounded-full border border-slate-300 bg-white px-1.5 py-0.5 text-[10px] font-semibold">
                          [{item.number}]
                        </span>
                        <span className="truncate">
                          {item.title || item.url || `Fonte ${item.number}`}
                        </span>
                      </a>
                      {item.quote && (
                        <div className="text-[11px] text-slate-500">
                          {item.quote.slice(0, 220)}
                          {item.quote.length > 220 ? '…' : ''}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
          <div className={cn('mt-0.5 flex flex-col gap-1', isUser && 'items-end')}>
            {showTimers && (
              <div className={cn('flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-400', isUser && 'justify-end')}>
                {thinkingEnabled && typeof thinkingSeconds === 'number' && (
                  <span className="inline-flex items-center gap-1">
                    {streamTimes.tAnswerStart ? 'Pensou por' : 'Pensando há'} {thinkingSeconds}s
                  </span>
                )}
                {typeof writingSeconds === 'number' && (
                  <span className="inline-flex items-center gap-1 text-emerald-700">
                    {streamTimes.tDone ? `Escreveu em ${writingSeconds}s` : `Escrevendo (${writingSeconds}s)`}
                    {!streamTimes.tDone && <LoadingDots />}
                  </span>
                )}
              </div>
            )}
            <p className={cn('text-xs text-slate-400', isUser && 'text-right')}>
              {formatDate(message.timestamp)}
            </p>

            {!isUser && (modelLabel || showCanvasApply || showCanvasSuggestion) && (
              <div className="flex items-center gap-2 flex-wrap">
                {modelLabel && (
                  <span className="inline-flex items-center gap-1 rounded bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-700">
                    {modelLabel}
                  </span>
                )}
                {showCanvasApply && (
                  <span className="inline-flex items-center gap-1 rounded bg-emerald-50 px-2 py-1 text-[10px] font-semibold text-emerald-700">
                    Aplica no canvas
                  </span>
                )}
                {!showCanvasApply && showCanvasSuggestion && (
                  <span className="inline-flex items-center gap-1 rounded bg-amber-50 px-2 py-1 text-[10px] font-semibold text-amber-700">
                    Sugestão de edição
                  </span>
                )}
              </div>
            )}
          </div>

          {showActions && (
            <div className="flex items-center gap-2 text-slate-500">
              {onCopy && (
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-6 gap-1 px-2 text-xs text-slate-500 hover:bg-slate-100 hover:text-slate-700"
                  onClick={() => onCopy(message)}
                >
                  <Copy className="h-3 w-3" />
                  Copiar
                </Button>
              )}
              {onRegenerate && (
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-6 gap-1 px-2 text-xs text-slate-500 hover:bg-slate-100 hover:text-slate-700"
                  onClick={() => onRegenerate(message)}
                  disabled={disableRegenerate}
                >
                  <RotateCcw className="h-3 w-3" />
                  Regerar
                </Button>
              )}
            </div>
          )}

          {!isUser && canvasSuggestion && (
            <div className="mt-2 flex items-center gap-2">
              <Button size="sm" variant="secondary" onClick={handleOpenDiff}>
                <Check className="mr-1 h-3.5 w-3.5" />
                Revisar e aplicar
              </Button>
              <span className="text-xs text-muted-foreground">Substitui apenas o trecho selecionado</span>
            </div>
          )}
        </div>
      </div>

      {!isUser && canvasSuggestion && (
        <DiffConfirmDialog
          open={diffOpen}
          onOpenChange={(open) => (open ? handleOpenDiff() : handleCloseDiff())}
          title="Sugestão do Chat"
          description="Revise a alteração sugerida antes de aplicar no documento."
          original={canvasSuggestion.original}
          replacement={canvasSuggestion.replacement}
          onAccept={handleApplySuggestion}
          onReject={handleCloseDiff}
        />
      )}
    </>
  );
}
