'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { cn } from '@/lib/utils';
import {
  ChevronDown,
  ChevronRight,
  X,
  Globe,
  Brain,
  Search,
  FileText,
  Loader2,
  CheckCircle2,
  AlertCircle,
  ExternalLink,
  MoreHorizontal,
} from 'lucide-react';

// ============================================================================
// Types
// ============================================================================

export interface ActivityStep {
  id: string;
  title: string;
  status?: 'running' | 'done' | 'error';
  detail?: string;
  tags?: string[];
  t?: number;
}

export interface Citation {
  number: string;
  title?: string;
  url?: string;
  quote?: string;
}

interface ThinkingChunk {
  type: 'research' | 'summary' | 'llm';
  text: string;
}

interface ActivityPanelProps {
  // Activity steps (search, deep research, etc.)
  steps: ActivityStep[];
  // Citations/sources
  citations: Citation[];
  // Thinking content
  thinkingChunks: ThinkingChunk[];
  thinkingText: string;
  isThinking: boolean;
  // Timing
  startTime?: number | null;
  endTime?: number | null;
  // Control
  open: boolean;
  onOpenChange: (open: boolean) => void;
  // Stream status
  isStreaming: boolean;
}

// ============================================================================
// Helpers
// ============================================================================

function formatDuration(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  const m = Math.floor(s / 60);
  const rem = s % 60;
  if (m <= 0) return `${rem}s`;
  return `${m}m ${rem}s`;
}

function citationDomain(url?: string): string {
  if (!url) return '';
  try {
    return new URL(url).hostname.replace(/^www\./i, '');
  } catch {
    return '';
  }
}

function getFaviconUrl(url?: string): string | null {
  if (!url) return null;
  try {
    const hostname = new URL(url).hostname;
    return `https://www.google.com/s2/favicons?domain=${hostname}&sz=32`;
  } catch {
    return null;
  }
}

function getStepIcon(step: ActivityStep) {
  const id = step.id.toLowerCase();
  if (id.includes('search') || id.includes('web')) {
    return <Globe className="h-3.5 w-3.5" />;
  }
  if (id.includes('deep') || id.includes('research')) {
    return <Search className="h-3.5 w-3.5" />;
  }
  if (id.includes('thought') || id.includes('thinking') || id.includes('reason')) {
    return <Brain className="h-3.5 w-3.5" />;
  }
  if (id.includes('doc') || id.includes('file') || id.includes('rag')) {
    return <FileText className="h-3.5 w-3.5" />;
  }
  return <Brain className="h-3.5 w-3.5" />;
}

// ============================================================================
// Loading Indicator
// ============================================================================

function LoadingPulse() {
  return (
    <span className="relative flex h-2 w-2">
      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75" />
      <span className="relative inline-flex rounded-full h-2 w-2 bg-blue-500" />
    </span>
  );
}

// ============================================================================
// Domain Chip Component (ChatGPT style)
// ============================================================================

interface DomainChipProps {
  domain: string;
  url?: string;
}

function DomainChip({ domain, url }: DomainChipProps) {
  const favicon = getFaviconUrl(url || `https://${domain}`);

  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 dark:bg-slate-800 px-2 py-0.5 text-[11px] font-medium text-slate-600 dark:text-slate-400 border border-slate-200 dark:border-slate-700">
      {favicon && (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={favicon}
          alt=""
          className="h-3 w-3 rounded-sm"
          onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
        />
      )}
      <Globe className="h-2.5 w-2.5 text-slate-400" />
      {domain}
    </span>
  );
}

// ============================================================================
// Thinking Item Component (ChatGPT bullet-point style)
// ============================================================================

interface ThinkingItemProps {
  title: string;
  description?: string;
  tags?: string[];
  isActive?: boolean;
  isLast?: boolean;
}

function ThinkingItem({ title, description, tags, isActive, isLast }: ThinkingItemProps) {
  const [expanded, setExpanded] = useState(false);
  const hasDescription = !!description?.trim();
  const hasTags = tags && tags.length > 0;

  return (
    <div className="relative pl-4">
      {/* Bullet point */}
      <div className="absolute left-0 top-1.5 flex items-center justify-center">
        {isActive ? (
          <LoadingPulse />
        ) : (
          <span className="h-1.5 w-1.5 rounded-full bg-slate-400 dark:bg-slate-500" />
        )}
      </div>

      {/* Content */}
      <div className="space-y-1">
        <button
          type="button"
          onClick={() => hasDescription && setExpanded(!expanded)}
          disabled={!hasDescription}
          className={cn(
            "text-left w-full",
            hasDescription && "cursor-pointer hover:text-slate-900 dark:hover:text-slate-100",
            !hasDescription && "cursor-default"
          )}
        >
          <span className={cn(
            "text-sm font-medium text-slate-700 dark:text-slate-300",
            isActive && "text-slate-900 dark:text-slate-100"
          )}>
            {title}
            {isActive && isLast && (
              <span className="ml-1 text-slate-400 dark:text-slate-500">...</span>
            )}
          </span>
          {hasDescription && (
            <ChevronRight className={cn(
              "inline-block ml-1 h-3 w-3 text-slate-400 transition-transform",
              expanded && "rotate-90"
            )} />
          )}
        </button>

        {/* Description (collapsed by default) */}
        {hasDescription && expanded && (
          <p className="text-xs text-slate-500 dark:text-slate-400 leading-relaxed pl-0.5">
            {description}
          </p>
        )}

        {/* Domain chips */}
        {hasTags && (
          <div className="flex flex-wrap gap-1.5 pt-1">
            {tags.slice(0, 6).map((tag, idx) => (
              <DomainChip key={`${tag}-${idx}`} domain={tag} />
            ))}
            {tags.length > 6 && (
              <span className="inline-flex items-center gap-1 text-[11px] text-slate-400 dark:text-slate-500">
                <MoreHorizontal className="h-3 w-3" />
                {tags.length - 6} more
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ============================================================================
// Activity Step Item (for non-thinking steps like search, research)
// ============================================================================

interface StepItemProps {
  step: ActivityStep;
  isStreaming: boolean;
}

function StepItem({ step, isStreaming }: StepItemProps) {
  const [expanded, setExpanded] = useState(false);
  const hasDetail = !!step.detail?.trim();
  const hasTags = step.tags && step.tags.length > 0;
  const isRunning = step.status === 'running' && isStreaming;

  return (
    <div className="relative pl-4">
      {/* Bullet point with status */}
      <div className="absolute left-0 top-1.5 flex items-center justify-center">
        {isRunning ? (
          <LoadingPulse />
        ) : step.status === 'done' ? (
          <CheckCircle2 className="h-3 w-3 text-emerald-500" />
        ) : step.status === 'error' ? (
          <AlertCircle className="h-3 w-3 text-red-500" />
        ) : (
          <span className="h-1.5 w-1.5 rounded-full bg-slate-400 dark:bg-slate-500" />
        )}
      </div>

      {/* Content */}
      <div className="space-y-1">
        <button
          type="button"
          onClick={() => hasDetail && setExpanded(!expanded)}
          disabled={!hasDetail}
          className={cn(
            "flex items-center gap-2 text-left w-full",
            hasDetail && "cursor-pointer hover:text-slate-900 dark:hover:text-slate-100"
          )}
        >
          <span className="text-slate-400 dark:text-slate-500">
            {getStepIcon(step)}
          </span>
          <span className={cn(
            "text-sm font-medium text-slate-700 dark:text-slate-300 flex-1",
            isRunning && "text-slate-900 dark:text-slate-100"
          )}>
            {step.title}
          </span>
          {hasDetail && (
            <ChevronRight className={cn(
              "h-3 w-3 text-slate-400 transition-transform",
              expanded && "rotate-90"
            )} />
          )}
        </button>

        {/* Detail (collapsed by default) */}
        {hasDetail && expanded && (
          <pre className="text-xs text-slate-500 dark:text-slate-400 whitespace-pre-wrap font-sans leading-relaxed pl-5 max-h-[120px] overflow-y-auto">
            {step.detail}
          </pre>
        )}

        {/* Domain chips */}
        {hasTags && (
          <div className="flex flex-wrap gap-1.5 pt-1 pl-5">
            {step.tags!.slice(0, 6).map((tag, idx) => (
              <DomainChip key={`${tag}-${idx}`} domain={tag} />
            ))}
            {step.tags!.length > 6 && (
              <span className="inline-flex items-center gap-1 text-[11px] text-slate-400">
                <MoreHorizontal className="h-3 w-3" />
                {step.tags!.length - 6} more
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ============================================================================
// Thinking Section (Collapsible, ChatGPT style)
// ============================================================================

interface ThinkingSectionProps {
  chunks: ThinkingChunk[];
  text: string;
  isThinking: boolean;
  isStreaming: boolean;
}

function ThinkingSection({ chunks, text, isThinking, isStreaming }: ThinkingSectionProps) {
  const [expanded, setExpanded] = useState(true);
  const contentRef = useRef<HTMLDivElement>(null);

  // Use ALL chunks passed to us (parent already filters for safe ones)
  const allChunks = chunks;
  const safeText = text.trim();
  const hasContent = allChunks.length > 0 || !!safeText;

  // Parse thinking text into bullet-point items
  const thinkingItems = useMemo(() => {
    const items: { title: string; description?: string; tags?: string[] }[] = [];

    // Parse from chunks - use ALL chunks passed to us
    for (const chunk of allChunks) {
      const lines = chunk.text.split('\n').filter(l => l.trim());
      for (const line of lines) {
        // Try to extract title from common patterns
        const cleanLine = line.replace(/^[-•*]\s*/, '').trim();
        if (cleanLine.length > 10) {
          items.push({ title: cleanLine.slice(0, 100) + (cleanLine.length > 100 ? '...' : '') });
        }
      }
    }

    // If no structured items, create one from raw text
    if (items.length === 0 && safeText) {
      const lines = safeText.split('\n').filter(l => l.trim());
      for (const line of lines.slice(0, 10)) {
        const cleanLine = line.replace(/^[-•*]\s*/, '').trim();
        if (cleanLine.length > 5) {
          items.push({ title: cleanLine.slice(0, 100) + (cleanLine.length > 100 ? '...' : '') });
        }
      }
    }

    return items;
  }, [allChunks, safeText]);

  // Auto-scroll to bottom when streaming
  useEffect(() => {
    if (isThinking && contentRef.current && expanded) {
      contentRef.current.scrollTop = contentRef.current.scrollHeight;
    }
  }, [chunks, text, isThinking, expanded]);

  // Don't show section if there's no content AND not actively thinking
  if (!hasContent && !isThinking) return null;

  // Don't show section if streaming is done and there's no real content
  if (!isStreaming && !hasContent) return null;

  return (
    <div className="space-y-2">
      {/* Section header */}
      <button
        type="button"
        onClick={() => !isStreaming && setExpanded(!expanded)}
        disabled={isStreaming && isThinking}
        className={cn(
          "flex items-center gap-2 text-left w-full",
          !isStreaming && "hover:opacity-80 cursor-pointer"
        )}
      >
        <span className="text-sm font-semibold text-slate-700 dark:text-slate-300">
          Processo de raciocínio
        </span>
        {isThinking && isStreaming && (
          <span className="text-xs text-slate-400 dark:text-slate-500">
            • em andamento...
          </span>
        )}
        {!isStreaming && hasContent && (
          <span className="text-xs text-slate-400 dark:text-slate-500">
            • concluído
          </span>
        )}
        <ChevronDown className={cn(
          "h-3.5 w-3.5 text-slate-400 transition-transform ml-auto",
          !expanded && "-rotate-90"
        )} />
      </button>

      {/* Content */}
      {expanded && (
        <div
          ref={contentRef}
          className="space-y-3 max-h-[300px] overflow-y-auto pr-1"
        >
          {thinkingItems.length > 0 ? (
            thinkingItems.map((item, idx) => (
              <ThinkingItem
                key={`thinking-${idx}`}
                title={item.title}
                description={item.description}
                tags={item.tags}
                isActive={isThinking && isStreaming && idx === thinkingItems.length - 1}
                isLast={idx === thinkingItems.length - 1}
              />
            ))
          ) : isThinking && isStreaming ? (
            <div className="pl-4 relative">
              <div className="absolute left-0 top-1.5">
                <LoadingPulse />
              </div>
              <span className="text-sm text-slate-500 dark:text-slate-400 animate-pulse">
                Analisando o contexto...
              </span>
            </div>
          ) : hasContent ? (
            // Fallback: show raw text if no structured items but has content
            <div className="pl-4 text-sm text-slate-600 dark:text-slate-400 whitespace-pre-wrap">
              {safeText || allChunks.map(c => c.text).join('\n')}
            </div>
          ) : null}
        </div>
      )}
    </div>
  );
}


// ============================================================================
// Sources Section (ChatGPT style)
// ============================================================================

interface SourcesSectionProps {
  citations: Citation[];
}

function SourcesSection({ citations }: SourcesSectionProps) {
  const [expanded, setExpanded] = useState(true);

  if (citations.length === 0) return null;

  return (
    <div className="space-y-2 border-t border-slate-100 dark:border-slate-800 pt-3 mt-3">
      {/* Section header */}
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 hover:opacity-80 transition-opacity w-full text-left"
      >
        <span className="text-sm font-semibold text-slate-700 dark:text-slate-300">
          Sources
        </span>
        <span className="text-sm text-slate-400 dark:text-slate-500">
          · {citations.length}
        </span>
        <ChevronDown className={cn(
          "h-3.5 w-3.5 text-slate-400 transition-transform ml-auto",
          !expanded && "-rotate-90"
        )} />
      </button>

      {/* Sources list */}
      {expanded && (
        <div className="space-y-1.5 max-h-[200px] overflow-y-auto">
          {citations.map((item, idx) => {
            const domain = citationDomain(item.url);
            const favicon = getFaviconUrl(item.url);

            return (
              <a
                key={`source-${item.number}-${idx}`}
                href={item.url || '#'}
                target="_blank"
                rel="noreferrer noopener"
                className={cn(
                  "flex items-start gap-2.5 rounded-lg px-2 py-1.5 transition-colors group",
                  item.url ? 'hover:bg-slate-50 dark:hover:bg-slate-800' : 'pointer-events-none opacity-70'
                )}
              >
                {/* Favicon */}
                <span className="flex-shrink-0 mt-0.5">
                  {favicon ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={favicon}
                      alt=""
                      className="h-4 w-4 rounded"
                      onError={(e) => {
                        (e.target as HTMLImageElement).style.display = 'none';
                        (e.target as HTMLImageElement).nextElementSibling?.classList.remove('hidden');
                      }}
                    />
                  ) : null}
                  <Globe className={cn("h-4 w-4 text-slate-400", favicon && "hidden")} />
                </span>

                {/* Content */}
                <div className="flex-1 min-w-0">
                  <div className="text-[10px] text-slate-400 dark:text-slate-500 truncate">
                    {domain || 'source'}
                  </div>
                  <div className="text-sm font-medium text-slate-700 dark:text-slate-300 leading-snug line-clamp-2 group-hover:text-slate-900 dark:group-hover:text-slate-100 transition-colors">
                    {item.title || item.url || `Fonte ${item.number}`}
                  </div>
                  {item.quote && (
                    <div className="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5 line-clamp-2">
                      {item.quote}
                    </div>
                  )}
                </div>

                {/* External link icon */}
                {item.url && (
                  <ExternalLink className="h-3 w-3 text-slate-300 dark:text-slate-600 group-hover:text-slate-400 dark:group-hover:text-slate-500 flex-shrink-0 mt-1 transition-colors" />
                )}
              </a>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ============================================================================
// Main Component: ActivityPanel (ChatGPT style)
// ============================================================================

export function ActivityPanel({
  steps,
  citations,
  thinkingChunks,
  thinkingText,
  isThinking,
  startTime,
  endTime,
  open,
  onOpenChange,
  isStreaming,
}: ActivityPanelProps) {
  const [nowMs, setNowMs] = useState(() => Date.now());

  // Timer update while streaming
  useEffect(() => {
    if (!isStreaming || !startTime) return;
    const id = window.setInterval(() => setNowMs(Date.now()), 250);
    return () => window.clearInterval(id);
  }, [isStreaming, startTime]);

  // Calculate duration
  const durationSeconds = useMemo(() => {
    if (!startTime) return null;
    const end = endTime ?? nowMs;
    return Math.max(0, (end - startTime) / 1000);
  }, [startTime, endTime, nowMs]);

  // Check if we have any content to show
  const hasContent = steps.length > 0 ||
    citations.length > 0 ||
    thinkingChunks.length > 0 ||
    thinkingText.trim() ||
    isThinking;

  if (!open || !hasContent) return null;

  return (
    <div className="w-full max-w-[min(92%,76ch)] rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 shadow-sm overflow-hidden mb-2">
      {/* Header - ChatGPT style */}
      <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 px-4 py-2.5 bg-slate-50/50 dark:bg-slate-800/50">
        <div className="flex items-center gap-2">
          {/* Three dots menu indicator */}
          <button
            type="button"
            className="p-0.5 -ml-1 rounded hover:bg-slate-200/50 dark:hover:bg-slate-700/50 transition-colors"
          >
            <MoreHorizontal className="h-4 w-4 text-slate-400 dark:text-slate-500" />
          </button>

          <span className="text-sm font-semibold text-slate-700 dark:text-slate-300">
            Activity
          </span>

          {/* Timer */}
          {typeof durationSeconds === 'number' && (
            <span className="text-sm text-slate-400 dark:text-slate-500">
              · {formatDuration(durationSeconds)}
            </span>
          )}
        </div>

        {/* Close button */}
        <button
          type="button"
          className={cn(
            "rounded-md p-1 -mr-1 text-slate-400 dark:text-slate-500 transition-colors hover:bg-slate-200/50 dark:hover:bg-slate-700/50 hover:text-slate-600 dark:hover:text-slate-300",
            isStreaming && "cursor-not-allowed opacity-50"
          )}
          aria-label="Fechar Activity"
          onClick={() => {
            if (isStreaming) return;
            onOpenChange(false);
          }}
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* Content */}
      <div className="px-4 py-3 space-y-4">
        {/* Thinking Section */}
        <ThinkingSection
          chunks={thinkingChunks}
          text={thinkingText}
          isThinking={isThinking}
          isStreaming={isStreaming}
        />

        {/* Activity Steps (search, research, etc.) */}
        {steps.length > 0 && (
          <div className="space-y-3">
            {steps.map((step) => (
              <StepItem key={step.id} step={step} isStreaming={isStreaming} />
            ))}
          </div>
        )}

        {/* Sources */}
        <SourcesSection citations={citations} />
      </div>
    </div>
  );
}
