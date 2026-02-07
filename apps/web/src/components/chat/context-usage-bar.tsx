'use client';

import { useMemo } from 'react';
import { cn } from '@/lib/utils';
import { AlertTriangle } from 'lucide-react';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { useChatStore } from '@/stores/chat-store';
import { useContextStore } from '@/stores/context-store';
import { getModelConfig, MODEL_REGISTRY, type ModelId } from '@/config/models';

// Constants for token estimation
const CHARS_PER_TOKEN = 4; // Rough approximation: 1 token ~ 4 characters
const DEFAULT_SYSTEM_PROMPT_TOKENS = 2000; // Estimated system prompt size
const RESPONSE_RESERVE_TOKENS = 4096; // Reserved tokens for response
const RAG_CHUNK_TOKENS = 1500; // Average tokens per RAG chunk

interface ContextBreakdown {
  modelName: string;
  contextWindow: number;
  systemAndHistory: number;
  attachments: number;
  attachmentCount: number;
  ragChunks: number;
  ragChunkCount: number;
  cacheSavedTokens: number;
  cacheSavedPercent: number;
  quotaUsedPoints: number;
  quotaLimitPoints: number;
  quotaRemainingPoints: number;
  haikuDelegations: number;
  responseReserve: number;
  totalUsed: number;
  available: number;
  percentUsed: number;
}

/**
 * Estimates token count from text/bytes
 * Rough approximation: 1 token ~ 4 characters
 */
function estimateTokens(bytes: number): number {
  return Math.ceil(bytes / CHARS_PER_TOKEN);
}

/**
 * Estimates token count for message history
 */
function estimateHistoryTokens(messages: any[]): number {
  if (!Array.isArray(messages)) return 0;
  return messages.reduce((total, msg) => {
    const content = typeof msg?.content === 'string' ? msg.content : '';
    return total + estimateTokens(content.length);
  }, 0);
}

/**
 * Formats token count in K notation (e.g., 84K)
 */
function formatTokens(tokens: number): string {
  if (tokens >= 1000) {
    return `${Math.round(tokens / 1000)}K`;
  }
  return tokens.toString();
}

function readUsageMetric(usage: any, paths: string[]): number {
  for (const path of paths) {
    const parts = path.split('.');
    let current: any = usage;
    for (const part of parts) {
      if (current == null || typeof current !== 'object') {
        current = undefined;
        break;
      }
      current = current[part];
    }
    const value = Number(current);
    if (Number.isFinite(value) && value > 0) {
      return value;
    }
  }
  return 0;
}

interface ContextUsageBarProps {
  className?: string;
  compact?: boolean;
}

export function ContextUsageBar({ className, compact = false }: ContextUsageBarProps) {
  const {
    selectedModels,
    selectedModel,
    chatMode,
    currentChat,
    ragScope,
  } = useChatStore();

  const { items: contextItems } = useContextStore();

  // Calculate context usage breakdown
  const breakdown = useMemo<ContextBreakdown>(() => {
    // Get the primary model (smallest context window for multi-model mode)
    const modelIds = chatMode === 'multi-model' ? selectedModels : [selectedModel || selectedModels[0]];
    const validModelIds = modelIds.filter(Boolean) as string[];

    if (validModelIds.length === 0) {
      return {
        modelName: 'Nenhum modelo',
        contextWindow: 200000,
        systemAndHistory: 0,
        attachments: 0,
        attachmentCount: 0,
        ragChunks: 0,
        ragChunkCount: 0,
        cacheSavedTokens: 0,
        cacheSavedPercent: 0,
        quotaUsedPoints: 0,
        quotaLimitPoints: 0,
        quotaRemainingPoints: 0,
        haikuDelegations: 0,
        responseReserve: RESPONSE_RESERVE_TOKENS,
        totalUsed: 0,
        available: 200000,
        percentUsed: 0,
      };
    }

    // Get the smallest context window among selected models
    const modelConfigs = validModelIds
      .map((id) => {
        const config = MODEL_REGISTRY[id as ModelId];
        return config ? { id, contextWindow: config.contextWindow, label: config.label } : null;
      })
      .filter(Boolean) as { id: string; contextWindow: number; label: string }[];

    const minContextModel = modelConfigs.reduce(
      (min, model) => (model.contextWindow < min.contextWindow ? model : min),
      modelConfigs[0] || { id: '', contextWindow: 200000, label: 'Modelo' }
    );

    const contextWindow = minContextModel.contextWindow;
    const modelName = minContextModel.label;

    // Estimate system prompt + history tokens
    const messages = currentChat?.messages || [];
    const historyTokens = estimateHistoryTokens(messages);
    const systemAndHistory = DEFAULT_SYSTEM_PROMPT_TOKENS + historyTokens;

    // Estimate cache savings from message telemetry (if available)
    let cacheSavedTokens = 0;
    let measuredInputTokens = 0;
    let quotaUsedPoints = 0;
    let quotaLimitPoints = 0;
    let quotaRemainingPoints = 0;
    let haikuDelegations = 0;
    for (const message of messages) {
      const usage = (message as any)?.metadata?.token_usage;
      if (!usage || typeof usage !== 'object') continue;
      measuredInputTokens += readUsageMetric(usage, ['usage.input_tokens', 'input_tokens']);
      cacheSavedTokens += readUsageMetric(usage, [
        'usage.cached_tokens_in',
        'cached_tokens_in',
        'usage.cached_input_tokens',
        'cached_input_tokens',
        'usage.cache_read_input_tokens',
        'cache_read_input_tokens',
        'usage.cached_content_token_count',
        'cached_content_token_count',
      ]);
    }
    for (const message of messages) {
      const billing = (message as any)?.metadata?.billing;
      if (billing && typeof billing === 'object') {
        const used = readUsageMetric(billing, [
          'points_used',
          'points_total',
          'total_points',
          'usage.points_used',
          'usage.points_total',
        ]);
        const limit = readUsageMetric(billing, [
          'points_limit',
          'points_budget',
          'budget_points',
          'quota.points_limit',
          'quota.limit',
        ]);
        const remaining = readUsageMetric(billing, [
          'points_available',
          'available_points',
          'remaining_points',
          'quota.remaining',
        ]);
        if (used > 0) quotaUsedPoints = used;
        if (limit > 0) quotaLimitPoints = limit;
        if (remaining > 0) quotaRemainingPoints = remaining;
      }

      const steps = Array.isArray((message as any)?.metadata?.activity?.steps)
        ? (message as any).metadata.activity.steps
        : [];
      haikuDelegations += steps.filter((step: any) => {
        const kind = String(step?.kind || '').toLowerCase();
        const id = String(step?.id || '').toLowerCase();
        const title = String(step?.title || '').toLowerCase();
        return (
          kind === 'delegate_subtask' ||
          id === 'delegate_subtask' ||
          id.includes('delegate') ||
          title.includes('delegado para haiku')
        );
      }).length;
    }
    if (quotaLimitPoints > 0 && quotaRemainingPoints <= 0 && quotaUsedPoints > 0) {
      quotaRemainingPoints = Math.max(0, quotaLimitPoints - quotaUsedPoints);
    }
    const cacheSavedPercent =
      measuredInputTokens > 0
        ? Math.min(99, (cacheSavedTokens / measuredInputTokens) * 100)
        : 0;

    // Estimate attachment tokens (files in context)
    const attachmentCount = contextItems.filter((item) => item.type === 'file').length;
    // Rough estimate: each attached file adds ~2K tokens on average (depends on size)
    const attachmentTokens = attachmentCount * 2000;

    // Estimate RAG chunks (if RAG is enabled)
    let ragChunkCount = 0;
    if (ragScope) {
      // Estimate chunks based on scope
      // case_and_global = 8 chunks, case_only = 4 chunks, global_only = 3 chunks
      ragChunkCount = ragScope === 'case_and_global' ? 8 : ragScope === 'case_only' ? 4 : 3;
    }
    const ragTokens = ragChunkCount * RAG_CHUNK_TOKENS;

    // Calculate totals
    const totalUsed = systemAndHistory + attachmentTokens + ragTokens + RESPONSE_RESERVE_TOKENS;
    const available = Math.max(0, contextWindow - totalUsed);
    const percentUsed = Math.min(100, (totalUsed / contextWindow) * 100);

    return {
      modelName,
      contextWindow,
      systemAndHistory,
      attachments: attachmentTokens,
      attachmentCount,
      ragChunks: ragTokens,
      ragChunkCount,
      cacheSavedTokens,
      cacheSavedPercent,
      quotaUsedPoints,
      quotaLimitPoints,
      quotaRemainingPoints,
      haikuDelegations,
      responseReserve: RESPONSE_RESERVE_TOKENS,
      totalUsed,
      available,
      percentUsed,
    };
  }, [selectedModels, selectedModel, chatMode, currentChat, contextItems, ragScope]);

  // Determine color based on usage percentage
  const getColorClass = (percent: number): string => {
    if (percent <= 50) return 'bg-emerald-500';
    if (percent <= 80) return 'bg-amber-500';
    return 'bg-red-500';
  };

  const getTextColorClass = (percent: number): string => {
    if (percent <= 50) return 'text-emerald-600 dark:text-emerald-400';
    if (percent <= 80) return 'text-amber-600 dark:text-amber-400';
    return 'text-red-600 dark:text-red-400';
  };

  const colorClass = getColorClass(breakdown.percentUsed);
  const textColorClass = getTextColorClass(breakdown.percentUsed);
  const isWarning = breakdown.percentUsed > 80;

  // Tooltip content with detailed breakdown
  const tooltipContent = (
    <div className="space-y-2 p-1 text-xs min-w-[220px]">
      <div className="font-medium border-b border-border pb-1">
        {breakdown.modelName} ({formatTokens(breakdown.contextWindow)} tokens)
      </div>

      <div className="space-y-1 text-muted-foreground">
        <div className="flex justify-between">
          <span>Sistema + historico:</span>
          <span className="font-mono">
            {formatTokens(breakdown.systemAndHistory)} ({((breakdown.systemAndHistory / breakdown.contextWindow) * 100).toFixed(1)}%)
          </span>
        </div>

        {breakdown.attachmentCount > 0 && (
          <div className="flex justify-between">
            <span>Anexos ({breakdown.attachmentCount} arquivos):</span>
            <span className="font-mono">
              {formatTokens(breakdown.attachments)} ({((breakdown.attachments / breakdown.contextWindow) * 100).toFixed(1)}%)
            </span>
          </div>
        )}

        {breakdown.ragChunkCount > 0 && (
          <div className="flex justify-between">
            <span>RAG chunks:</span>
            <span className="font-mono">
              {formatTokens(breakdown.ragChunks)} ({((breakdown.ragChunks / breakdown.contextWindow) * 100).toFixed(1)}%)
            </span>
          </div>
        )}

        {breakdown.cacheSavedTokens > 0 && (
          <div className="flex justify-between">
            <span>💾 Cache:</span>
            <span className="font-mono text-emerald-600 dark:text-emerald-400">
              -{formatTokens(breakdown.cacheSavedTokens)} (-{breakdown.cacheSavedPercent.toFixed(0)}%)
            </span>
          </div>
        )}

        {(breakdown.quotaLimitPoints > 0 || breakdown.quotaUsedPoints > 0) && (
          <div className="flex justify-between">
            <span>📊 Quota:</span>
            <span className="font-mono">
              {breakdown.quotaLimitPoints > 0
                ? `${Math.round(breakdown.quotaUsedPoints)}/${Math.round(breakdown.quotaLimitPoints)} pts`
                : `${Math.round(breakdown.quotaUsedPoints)} pts`}
              {breakdown.quotaRemainingPoints > 0
                ? ` (${Math.round(breakdown.quotaRemainingPoints)} disp.)`
                : ''}
            </span>
          </div>
        )}

        {breakdown.haikuDelegations > 0 && (
          <div className="flex justify-between">
            <span>⚡ Delegações Haiku:</span>
            <span className="font-mono">{breakdown.haikuDelegations}</span>
          </div>
        )}

        <div className="flex justify-between">
          <span>Reserva resposta:</span>
          <span className="font-mono">
            {formatTokens(breakdown.responseReserve)} ({((breakdown.responseReserve / breakdown.contextWindow) * 100).toFixed(1)}%)
          </span>
        </div>
      </div>

      <div className="border-t border-border pt-1 flex justify-between font-medium">
        <span>Total usado / Disponivel:</span>
        <span className={cn('font-mono', textColorClass)}>
          {formatTokens(breakdown.totalUsed)} / {formatTokens(breakdown.available)}
        </span>
      </div>

      {isWarning && (
        <div className="text-red-500 text-[10px] flex items-center gap-1 mt-1">
          <AlertTriangle className="h-3 w-3" />
          Contexto quase cheio. Considere limpar historico.
        </div>
      )}
    </div>
  );

  if (compact) {
    return (
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <div
              className={cn(
                'flex items-center gap-1.5 px-2 py-1 rounded-md bg-muted/50 cursor-help',
                className
              )}
            >
              <div className="h-1.5 w-12 bg-secondary rounded-full overflow-hidden">
                <div
                  className={cn('h-full transition-all duration-300', colorClass)}
                  style={{ width: `${Math.min(breakdown.percentUsed, 100)}%` }}
                />
              </div>
              <span className={cn('text-[10px] font-mono', textColorClass)}>
                {breakdown.percentUsed.toFixed(0)}%
              </span>
              {isWarning && <AlertTriangle className="h-3 w-3 text-red-500" />}
            </div>
          </TooltipTrigger>
          <TooltipContent side="top" className="p-2">
            {tooltipContent}
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    );
  }

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <div
            className={cn(
              'flex items-center gap-2 text-xs text-muted-foreground cursor-help',
              className
            )}
          >
            <span className="text-[11px]">Contexto:</span>

            {/* Progress bar */}
            <div className="h-2 w-24 bg-secondary rounded-full overflow-hidden">
              <div
                className={cn('h-full transition-all duration-300', colorClass)}
                style={{ width: `${Math.min(breakdown.percentUsed, 100)}%` }}
              />
            </div>

            {/* Usage text */}
            <span className={cn('text-[11px] font-mono', textColorClass)}>
              {breakdown.percentUsed.toFixed(0)}% ({formatTokens(breakdown.totalUsed)} / {formatTokens(breakdown.contextWindow)} tokens)
            </span>

            {isWarning && (
              <AlertTriangle className="h-3.5 w-3.5 text-red-500 animate-pulse" />
            )}
          </div>
        </TooltipTrigger>
        <TooltipContent side="top" className="p-2">
          {tooltipContent}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
