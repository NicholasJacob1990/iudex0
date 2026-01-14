'use client';

import { useMemo, useState } from 'react';
import { cn } from '@/lib/utils';
import { formatDate } from '@/lib/utils';
import { User, Bot, Check, Copy, RotateCcw } from 'lucide-react';
import { TokenUsageBar } from './token-usage-bar';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';
import { useCanvasStore } from '@/stores/canvas-store';
import { DiffConfirmDialog } from '@/components/dashboard/diff-confirm-dialog';
import { parseMarkdownToHtmlSync } from '@/lib/markdown-parser';
import { DiagramViewer } from '@/components/dashboard/diagram-viewer';

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

export function ChatMessage({ message, onCopy, onRegenerate, disableRegenerate }: ChatMessageProps) {
  const isUser = message.role === 'user';
  const canvasSuggestion = !isUser ? message.metadata?.canvas_suggestion : null;
  const [diffOpen, setDiffOpen] = useState(false);
  const showActions = !isUser && (onCopy || onRegenerate);
  const thinkingText = typeof message.thinking === 'string'
    ? message.thinking.trim()
    : typeof message.metadata?.thinking === 'string'
      ? message.metadata.thinking.trim()
      : '';
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
      html: part.type === 'markdown' ? parseMarkdownToHtmlSync(part.content || '') : undefined,
    }));
  }, [message.content]);

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
            'flex h-8 w-8 items-center justify-center rounded-full border shadow-sm',
            isUser ? 'bg-emerald-600 border-emerald-600 text-white' : 'bg-white border-slate-200 text-slate-600'
          )}
        >
          {isUser ? (
            <User className="h-4 w-4 text-white" />
          ) : (
            <Bot className="h-4 w-4 text-slate-600" />
          )}
        </div>

        {/* Message Content */}
        <div className={cn('flex flex-1 flex-col gap-1', isUser && 'items-end')}>
          <div
            className={cn(
              'max-w-[85%] rounded-2xl border px-4 py-3 shadow-sm',
              isUser
                ? 'ml-auto bg-[#f4f4f5] text-black border-[#e5e7eb]'
                : 'bg-white text-black border-slate-200'
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
          </div>
          <p className={cn('text-[11px] text-slate-400', isUser && 'text-right')}>
            {formatDate(message.timestamp)}
            {!isUser && message.metadata?.model && (
              <span className="ml-2 inline-flex items-center gap-1 rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-600">
                {/* Ideally render icon here too */}
                {message.metadata.model}
              </span>
            )}
          </p>

          {!isUser && (thinkingText || message.isThinking) && (
            <details
              open
              className="mt-1 rounded-lg border border-slate-200 bg-slate-50/70 px-3 py-2 text-[11px] text-slate-600 animate-in fade-in duration-200"
            >
              <summary className="cursor-pointer font-semibold text-slate-500 flex items-center gap-2">
                Processo de raciocínio
                {message.isThinking && <LoadingDots />}
              </summary>
              <p className="mt-2 max-h-[220px] overflow-y-auto whitespace-pre-wrap">
                {thinkingText || (message.isThinking ? 'Analisando...' : '')}
              </p>
            </details>
          )}

          {showActions && (
            <div className="flex items-center gap-2 text-slate-500">
              {onCopy && (
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-6 gap-1 px-2 text-[11px] text-slate-500 hover:bg-slate-100 hover:text-slate-700"
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
                  className="h-6 gap-1 px-2 text-[11px] text-slate-500 hover:bg-slate-100 hover:text-slate-700"
                  onClick={() => onRegenerate(message)}
                  disabled={disableRegenerate}
                >
                  <RotateCcw className="h-3 w-3" />
                  Regerar
                </Button>
              )}
            </div>
          )}

          {/* Token Usage Bar for Assistant */}
          {!isUser && message.metadata?.token_usage && (
            <div className="mt-2 text-xs">
              <TokenUsageBar data={message.metadata.token_usage} compact />
            </div>
          )}

          {!isUser && canvasSuggestion && (
            <div className="mt-2 flex items-center gap-2">
              <Button size="sm" variant="secondary" onClick={handleOpenDiff}>
                <Check className="mr-1 h-3.5 w-3.5" />
                Revisar e aplicar
              </Button>
              <span className="text-[11px] text-muted-foreground">Substitui apenas o trecho selecionado</span>
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
