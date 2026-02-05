import { Loader2, Check, Sparkles } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Badge } from '@/components/ui/badge';

interface AskStreamingStatusProps {
  status: string;
  stepsCount: number;
  isStreaming: boolean;
}

export function AskStreamingStatus({ status, stepsCount, isStreaming }: AskStreamingStatusProps) {
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
    </div>
  );
}
