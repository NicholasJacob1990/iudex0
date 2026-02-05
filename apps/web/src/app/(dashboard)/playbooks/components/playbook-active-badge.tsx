'use client';

import React from 'react';
import { BookCheck, X } from 'lucide-react';
import { useChatStore } from '@/stores';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';

/**
 * PlaybookActiveBadge — small inline badge shown in the chat area
 * when a playbook is active. Includes a dismiss button.
 */
export function PlaybookActiveBadge({ className }: { className?: string }) {
  const { selectedPlaybookId, selectedPlaybookName, selectedPlaybookPrompt, clearPlaybook } =
    useChatStore();

  if (!selectedPlaybookId) return null;

  const isReady = !!selectedPlaybookPrompt;

  return (
    <div
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium transition-all',
        isReady
          ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
          : 'border-amber-200 bg-amber-50 text-amber-700',
        className
      )}
    >
      <BookCheck className="h-3 w-3 flex-shrink-0" />
      <span className="max-w-[140px] truncate">{selectedPlaybookName || 'Playbook'}</span>
      {!isReady && <span className="text-[10px] opacity-70">carregando...</span>}
      <button
        onClick={() => {
          clearPlaybook();
          toast.info('Playbook removido da revisao');
        }}
        className={cn(
          'rounded-full p-0.5 transition-colors',
          isReady ? 'hover:bg-emerald-200' : 'hover:bg-amber-200'
        )}
        title="Remover playbook"
      >
        <X className="h-2.5 w-2.5" />
      </button>
    </div>
  );
}
