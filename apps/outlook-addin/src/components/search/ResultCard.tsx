/**
 * Card de resultado de busca no corpus.
 *
 * Exibe titulo, score, fonte, conteudo e acoes.
 */

import { Badge, Text } from '@fluentui/react-components';
import type { CorpusResult } from '@/api/client';

interface ResultCardProps {
  result: CorpusResult;
  isExpanded: boolean;
  onToggleExpand: () => void;
  onCopy: () => void;
}

export function ResultCard({
  result,
  isExpanded,
  onToggleExpand,
  onCopy,
}: ResultCardProps) {
  const scorePercent = (result.score * 100).toFixed(0);
  const scoreColor =
    result.score >= 0.8
      ? 'text-status-success bg-green-50'
      : result.score >= 0.5
        ? 'text-status-warning bg-amber-50'
        : 'text-text-tertiary bg-surface-tertiary';

  return (
    <div className="office-card">
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <button
          onClick={onToggleExpand}
          className="text-left text-office-sm font-medium hover:text-brand"
        >
          {result.title}
        </button>
        <span
          className={`shrink-0 rounded px-1.5 py-0.5 text-office-xs font-medium ${scoreColor}`}
        >
          {scorePercent}%
        </span>
      </div>

      {/* Fonte */}
      {result.source && (
        <Text size={100} className="mt-0.5 block text-text-tertiary">
          {result.source}
        </Text>
      )}

      {/* Conteudo */}
      <Text
        size={200}
        className={`mt-1 block leading-relaxed text-text-secondary ${
          isExpanded ? '' : 'line-clamp-3'
        }`}
      >
        {result.content}
      </Text>

      {/* Expandir/Colapsar */}
      {result.content.length > 200 && (
        <button
          onClick={onToggleExpand}
          className="mt-1 text-office-xs text-brand hover:underline"
        >
          {isExpanded ? 'Ver menos' : 'Ver mais'}
        </button>
      )}

      {/* Metadata */}
      {result.metadata && Object.keys(result.metadata).length > 0 && isExpanded && (
        <div className="mt-2 flex flex-wrap gap-1">
          {Object.entries(result.metadata).map(([key, value]) => (
            <Badge key={key} appearance="outline" size="small">
              {key}: {String(value)}
            </Badge>
          ))}
        </div>
      )}

      {/* Acoes */}
      <div className="mt-2 flex gap-2">
        <button
          onClick={(e) => {
            e.stopPropagation();
            onCopy();
          }}
          className="text-office-xs font-medium text-brand hover:underline"
        >
          Copiar
        </button>
      </div>
    </div>
  );
}
