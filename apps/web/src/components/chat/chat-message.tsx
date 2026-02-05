'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { cn } from '@/lib/utils';
import { formatDate } from '@/lib/utils';
import { User, Bot, Check, Copy, RotateCcw, Globe, ExternalLink, Rocket, ThumbsUp, ThumbsDown, Share2, RefreshCw } from 'lucide-react';
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
  onPromoteToAgent?: (message: Message) => void;
  onFeedback?: (message: Message, type: 'up' | 'down') => void;
  onShare?: (message: Message) => void;
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

// ============================================================================
// Response Sources Tabs (Perplexity style — Resposta | Fontes)
// ============================================================================

function ResponseSourcesTabs({ citations }: { citations: CitationItem[] }) {
  const [activeTab, setActiveTab] = useState<'sources'>('sources');

  function citationDomain(url?: string): string {
    if (!url) return '';
    try { return new URL(url).hostname.replace(/^www\./i, ''); } catch { return ''; }
  }
  function getFaviconUrl(url?: string): string | null {
    if (!url) return null;
    try { return `https://www.google.com/s2/favicons?domain=${new URL(url).hostname}&sz=32`; } catch { return null; }
  }

  return (
    <div className="mt-4 border-t border-slate-100 pt-3">
      {/* Tab header */}
      <div className="flex items-center gap-1 mb-3">
        <button
          type="button"
          onClick={() => setActiveTab('sources')}
          className={cn(
            'inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors',
            'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300',
          )}
        >
          <Globe className="h-3 w-3" />
          Fontes
          <span className="ml-0.5 rounded-full bg-slate-200 dark:bg-slate-700 px-1.5 py-0.5 text-[10px] font-semibold">
            {citations.length}
          </span>
        </button>
      </div>

      {/* Sources list */}
      {activeTab === 'sources' && (
        <div className="grid gap-2">
          {citations.map((item) => {
            const domain = citationDomain(item.url);
            const favicon = getFaviconUrl(item.url);

            return (
              <a
                key={`tab-${item.number}-${item.url || item.title || ''}`}
                href={item.url || '#'}
                target="_blank"
                rel="noreferrer noopener"
                className={cn(
                  'flex items-start gap-3 rounded-lg border border-slate-100 dark:border-slate-800 p-3 transition-all group',
                  item.url ? 'hover:border-slate-300 hover:bg-slate-50/50 dark:hover:bg-slate-800/50' : 'pointer-events-none opacity-60',
                )}
              >
                {/* Favicon */}
                <div className="flex h-8 w-8 items-center justify-center rounded-md bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 shrink-0">
                  {favicon ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={favicon} alt="" className="h-4 w-4 rounded-sm" onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }} />
                  ) : (
                    <Globe className="h-3.5 w-3.5 text-slate-400" />
                  )}
                </div>

                {/* Content */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="rounded-full border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 px-1.5 py-0.5 text-[10px] font-bold text-slate-500 shrink-0">
                      {item.number}
                    </span>
                    <span className="text-sm font-medium text-slate-700 dark:text-slate-300 truncate group-hover:text-slate-900 dark:group-hover:text-slate-100">
                      {item.title || domain || `Fonte ${item.number}`}
                    </span>
                    <ExternalLink className="h-3 w-3 text-slate-300 group-hover:text-slate-400 shrink-0 ml-auto" />
                  </div>
                  {domain && (
                    <span className="text-[11px] text-slate-400 dark:text-slate-500">{domain}</span>
                  )}
                  {item.quote && (
                    <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-400 leading-relaxed line-clamp-2">
                      {item.quote}
                    </p>
                  )}
                </div>
              </a>
            );
          })}
        </div>
      )}
    </div>
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

export function ChatMessage({ message, onCopy, onRegenerate, onPromoteToAgent, onFeedback, onShare, disableRegenerate }: ChatMessageProps) {
  const [feedbackGiven, setFeedbackGiven] = useState<'up' | 'down' | null>(null);
  const isUser = message.role === 'user';
  const canvasSuggestion = !isUser ? message.metadata?.canvas_suggestion : null;
  const [diffOpen, setDiffOpen] = useState(false);
  const [thinkingOpen, setThinkingOpen] = useState(false);
  const autoOpenedRef = useRef(false);
  const [activityOpen, setActivityOpen] = useState(false);
  const activityAutoOpenedRef = useRef(false);
  const showActions = !isUser && (onCopy || onRegenerate || onPromoteToAgent);
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

  // Sources inside the Harvey-like Activity panel. Keep in-bubble sources as fallback only.
  const showSourcesInBubble = !isUser && citations.length > 0 && filteredActivitySteps.length === 0;

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

  // Only show thinking timer if there was actual thinking content
  const showThinkingTimer = thinkingEnabled && hasThinkingContent && typeof thinkingSeconds === 'number' && thinkingSeconds > 0;

  return (
    <>
      <div
        className={cn(
          'flex items-start gap-3 animate-fade-in',
          isUser && 'flex-row-reverse'
        )}
      >
        {/* Avatar — only for user messages */}
        {isUser && (
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br from-emerald-500 to-emerald-600 text-white shadow-sm">
            <User className="h-4 w-4" />
          </div>
        )}

        {/* Message Content */}
        <div className={cn('flex flex-1 flex-col gap-1', isUser && 'items-end')}>
          {/* NEW: Unified Activity Panel (ChatGPT style) */}
          {!isUser && (
            <ActivityPanel
              steps={filteredActivitySteps as ActivityStep[]}
              citations={citations as Citation[]}
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
                ? 'ml-auto bg-gradient-to-br from-slate-100 to-slate-50 dark:from-slate-800 dark:to-slate-900 text-black dark:text-slate-100 border-slate-200/60 dark:border-slate-700/60 shadow-sm'
                : 'bg-white dark:bg-slate-900 text-black dark:text-slate-100 border-slate-200/80 dark:border-slate-700/80 shadow-[0_2px_8px_-4px_rgba(0,0,0,0.05)] hover:shadow-[0_4px_12px_-6px_rgba(0,0,0,0.08)] dark:shadow-[0_2px_8px_-4px_rgba(0,0,0,0.3)]'
            )}
          >
            <div
              className="chat-markdown"
              onClick={(e) => {
                const btn = (e.target as HTMLElement).closest('.code-block-copy');
                if (!btn) return;
                const code = btn.getAttribute('data-code') || '';
                // Decode HTML entities
                const txt = new DOMParser().parseFromString(code, 'text/html').documentElement.textContent || '';
                navigator.clipboard.writeText(txt).then(() => {
                  const svg = btn.querySelector('svg');
                  if (svg) {
                    svg.style.color = '#34d399';
                    setTimeout(() => { svg.style.color = ''; }, 1200);
                  }
                });
              }}
            >
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
            {/* Response Tabs: Resposta / Fontes (Perplexity style) */}
            {showSourcesInBubble && (
              <ResponseSourcesTabs citations={citations} />
            )}
          </div>
          <div className={cn('mt-0.5 flex flex-col gap-1', isUser && 'items-end')}>
            {/* Only show timers if meaningful */}
            {(showThinkingTimer || (isStreaming && typeof writingSeconds === 'number')) && (
              <div className={cn('flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-400', isUser && 'justify-end')}>
                {showThinkingTimer && (
                  <span className="inline-flex items-center gap-1">
                    {streamTimes.tAnswerStart ? 'Pensou por' : 'Pensando há'} {thinkingSeconds}s
                  </span>
                )}
                {isStreaming && typeof writingSeconds === 'number' && (
                  <span className="inline-flex items-center gap-1 text-emerald-600">
                    Escrevendo ({writingSeconds}s) <LoadingDots />
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
                  <span className="inline-flex items-center gap-1 rounded bg-slate-100 dark:bg-slate-800 px-2 py-1 text-xs font-semibold text-slate-700 dark:text-slate-300">
                    {modelLabel}
                  </span>
                )}
                {showCanvasApply && (
                  <span className="inline-flex items-center gap-1 rounded bg-emerald-50 dark:bg-emerald-900/30 px-2 py-1 text-[10px] font-semibold text-emerald-700 dark:text-emerald-400">
                    Aplica no canvas
                  </span>
                )}
                {!showCanvasApply && showCanvasSuggestion && (
                  <span className="inline-flex items-center gap-1 rounded bg-amber-50 dark:bg-amber-900/30 px-2 py-1 text-[10px] font-semibold text-amber-700 dark:text-amber-400">
                    Sugestão de edição
                  </span>
                )}
              </div>
            )}
          </div>

          {/* Compact Action Icons (Harvey.ai / Gemini style) */}
          {showActions && (
            <div className="flex items-center gap-0.5 mt-1">
              {/* Thumbs Up */}
              <button
                type="button"
                onClick={() => {
                  setFeedbackGiven('up');
                  onFeedback?.(message, 'up');
                }}
                className={cn(
                  'p-1.5 rounded-md transition-colors',
                  feedbackGiven === 'up'
                    ? 'text-emerald-600 bg-emerald-50 dark:bg-emerald-900/30'
                    : 'text-slate-400 hover:text-slate-600 hover:bg-slate-100 dark:hover:bg-slate-800'
                )}
                title="Boa resposta"
              >
                <ThumbsUp className="h-3.5 w-3.5" />
              </button>

              {/* Thumbs Down */}
              <button
                type="button"
                onClick={() => {
                  setFeedbackGiven('down');
                  onFeedback?.(message, 'down');
                }}
                className={cn(
                  'p-1.5 rounded-md transition-colors',
                  feedbackGiven === 'down'
                    ? 'text-red-600 bg-red-50 dark:bg-red-900/30'
                    : 'text-slate-400 hover:text-slate-600 hover:bg-slate-100 dark:hover:bg-slate-800'
                )}
                title="Resposta ruim"
              >
                <ThumbsDown className="h-3.5 w-3.5" />
              </button>

              {/* Divider */}
              <div className="w-px h-4 bg-slate-200 dark:bg-slate-700 mx-1" />

              {/* Copy */}
              {onCopy && (
                <button
                  type="button"
                  onClick={() => onCopy(message)}
                  className="p-1.5 rounded-md text-slate-400 hover:text-slate-600 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
                  title="Copiar"
                >
                  <Copy className="h-3.5 w-3.5" />
                </button>
              )}

              {/* Regenerate */}
              {onRegenerate && (
                <button
                  type="button"
                  onClick={() => onRegenerate(message)}
                  disabled={disableRegenerate}
                  className={cn(
                    'p-1.5 rounded-md transition-colors',
                    disableRegenerate
                      ? 'text-slate-300 cursor-not-allowed'
                      : 'text-slate-400 hover:text-slate-600 hover:bg-slate-100 dark:hover:bg-slate-800'
                  )}
                  title="Regenerar resposta"
                >
                  <RefreshCw className="h-3.5 w-3.5" />
                </button>
              )}

              {/* Share */}
              {onShare && (
                <button
                  type="button"
                  onClick={() => onShare(message)}
                  className="p-1.5 rounded-md text-slate-400 hover:text-slate-600 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
                  title="Compartilhar"
                >
                  <Share2 className="h-3.5 w-3.5" />
                </button>
              )}

              {/* Promote to Agent */}
              {onPromoteToAgent && (
                <>
                  <div className="w-px h-4 bg-slate-200 dark:bg-slate-700 mx-1" />
                  <button
                    type="button"
                    onClick={() => onPromoteToAgent(message)}
                    className="p-1.5 rounded-md text-indigo-400 hover:text-indigo-600 hover:bg-indigo-50 dark:hover:bg-indigo-900/30 transition-colors"
                    title="Continuar com agente autônomo"
                  >
                    <Rocket className="h-3.5 w-3.5" />
                  </button>
                </>
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
