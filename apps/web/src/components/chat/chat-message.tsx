'use client';

import { useState } from 'react';
import { cn } from '@/lib/utils';
import { formatDate } from '@/lib/utils';
import { User, Bot, Check } from 'lucide-react';
import { TokenUsageBar } from './token-usage-bar';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';
import { useCanvasStore } from '@/stores/canvas-store';
import { DiffConfirmDialog } from '@/components/dashboard/diff-confirm-dialog';

interface Message {
  id: string;
  content: string;
  role: 'user' | 'assistant';
  timestamp: string;
  metadata?: any;
}

interface ChatMessageProps {
  message: Message;
}

export function ChatMessage({ message }: ChatMessageProps) {
  const isUser = message.role === 'user';
  const canvasSuggestion = !isUser ? message.metadata?.canvas_suggestion : null;
  const [diffOpen, setDiffOpen] = useState(false);

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
          'flex items-start space-x-3 animate-fade-in',
          isUser && 'flex-row-reverse space-x-reverse'
        )}
      >
        {/* Avatar */}
        <div
          className={cn(
            'flex h-8 w-8 items-center justify-center rounded-full',
            isUser ? 'bg-primary' : 'bg-secondary'
          )}
        >
          {isUser ? (
            <User className="h-4 w-4 text-primary-foreground" />
          ) : (
            <Bot className="h-4 w-4 text-secondary-foreground" />
          )}
        </div>

      {/* Message Content */}
      <div className={cn('flex-1 space-y-1', isUser && 'items-end')}>
        <div
          className={cn(
            'rounded-lg px-4 py-2 max-w-[80%]',
            isUser
              ? 'bg-primary text-primary-foreground ml-auto'
              : 'bg-secondary text-secondary-foreground'
          )}
        >
          <p className="text-sm whitespace-pre-wrap">{message.content}</p>
        </div>
        <p className={cn('text-xs text-muted-foreground', isUser && 'text-right')}>
          {formatDate(message.timestamp)}
          {!isUser && message.metadata?.model && (
            <span className="ml-2 inline-flex items-center gap-1 rounded bg-muted px-1.5 py-0.5 text-[10px] font-medium text-foreground">
              {/* Ideally render icon here too */}
              {message.metadata.model}
            </span>
          )}
        </p>

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
