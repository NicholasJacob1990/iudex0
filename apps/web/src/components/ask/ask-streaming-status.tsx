import { Loader2, Check, Sparkles } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Badge } from '@/components/ui/badge';

interface AskStreamingStatusProps {
  status: string;
  stepsCount: number;
  isStreaming: boolean;
  minPages?: number;
  maxPages?: number;
  estimatedPages?: number;
  documentRoute?: string;
}

type RoutingBucket = 'Direct' | 'RAG Enhanced' | 'Chunked RAG' | 'Multi-pass';

function normalizeDocumentRoute(route?: string): RoutingBucket | null {
  const value = String(route || '').trim().toLowerCase();
  if (!value) return null;
  if (value === 'direct') return 'Direct';
  if (value === 'rag_enhanced') return 'RAG Enhanced';
  if (value === 'chunked_rag') return 'Chunked RAG';
  if (value === 'multi_pass') return 'Multi-pass';
  return null;
}

function inferRoutingBucket(minPages?: number, maxPages?: number): { pages: number; bucket: RoutingBucket } | null {
  const min = Number.isFinite(Number(minPages)) ? Math.max(0, Number(minPages)) : 0;
  const max = Number.isFinite(Number(maxPages)) ? Math.max(0, Number(maxPages)) : 0;
  const pages = min && max ? Math.round((min + max) / 2) : Math.max(min, max);
  if (!pages) return null;

  if (pages <= 100) return { pages, bucket: 'Direct' };
  if (pages <= 500) return { pages, bucket: 'RAG Enhanced' };
  if (pages <= 2000) return { pages, bucket: 'Chunked RAG' };
  return { pages, bucket: 'Multi-pass' };
}

export function AskStreamingStatus({
  status,
  stepsCount,
  isStreaming,
  minPages,
  maxPages,
  estimatedPages,
  documentRoute,
}: AskStreamingStatusProps) {
  // If not streaming and no status, return null
  if (!isStreaming && !status) {
    return null;
  }

  // Determine the icon based on state
  const renderIcon = () => {
    if (!isStreaming) {
      return <Check className="h-4 w-4 text-green-600" />;
    }

    // Animate the loader when streaming
    return <Loader2 className="h-4 w-4 animate-spin text-indigo-600" />;
  };

  // Determine status message
  const getStatusMessage = () => {
    if (!isStreaming) {
      return `Concluído em ${stepsCount} ${stepsCount === 1 ? 'etapa' : 'etapas'}`;
    }
    return status || 'Processando...';
  };

  const explicitBucket = normalizeDocumentRoute(documentRoute);
  const explicitPages = Number.isFinite(Number(estimatedPages))
    ? Math.max(0, Math.floor(Number(estimatedPages)))
    : 0;
  const routingInfo = explicitBucket
    ? {
      pages: explicitPages,
      bucket: explicitBucket,
    }
    : inferRoutingBucket(minPages, maxPages);
  const showRoutingHint = isStreaming && !!routingInfo;

  return (
    <div className="flex items-center gap-2">
      {/* Icon with pulsing effect when streaming */}
      <div
        className={cn(
          'flex h-8 w-8 items-center justify-center rounded-full transition-all',
          isStreaming
            ? 'bg-indigo-50 shadow-[0_0_10px_rgba(99,102,241,0.2)]'
            : 'bg-green-50'
        )}
      >
        {renderIcon()}
      </div>

      {/* Status text */}
      <span
        className={cn(
          'text-sm font-medium transition-colors',
          isStreaming ? 'text-indigo-600' : 'text-green-600'
        )}
      >
        {getStatusMessage()}
      </span>

      {/* Step count badge (only show when streaming) */}
      {isStreaming && stepsCount > 0 && (
        <Badge
          variant="secondary"
          className={cn(
            'ml-1 animate-pulse',
            'bg-indigo-100 text-indigo-700 border-indigo-200'
          )}
        >
          Etapa {stepsCount}
        </Badge>
      )}

      {showRoutingHint && (
        <Badge variant="outline" className="ml-1 text-[10px]">
          {routingInfo.pages > 0
            ? `📄 ${routingInfo.pages}pg → ${routingInfo.bucket}`
            : `📄 ${routingInfo.bucket}`}
        </Badge>
      )}
    </div>
  );
}
