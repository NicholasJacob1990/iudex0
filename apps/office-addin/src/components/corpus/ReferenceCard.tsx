import type { CorpusResult } from '@/api/client';

interface ReferenceCardProps {
  result: CorpusResult;
  isExpanded: boolean;
  isSelected: boolean;
  onToggleExpand: () => void;
  onToggleSelect: () => void;
  onInsert: () => void;
  onInsertAsFootnote: () => void;
  onCopyText: () => void;
  onUseAsContext: () => void;
}

export function ReferenceCard({
  result,
  isExpanded,
  isSelected,
  onToggleExpand,
  onToggleSelect,
  onInsert,
  onInsertAsFootnote,
  onCopyText,
  onUseAsContext,
}: ReferenceCardProps) {
  const scorePercent = (result.score * 100).toFixed(0);
  const scoreColor =
    result.score >= 0.8
      ? 'text-status-success bg-green-50'
      : result.score >= 0.5
        ? 'text-status-warning bg-amber-50'
        : 'text-text-tertiary bg-surface-tertiary';

  return (
    <div
      className={`office-card transition-all ${
        isSelected ? 'ring-2 ring-brand ring-offset-1' : ''
      }`}
    >
      {/* Header */}
      <div className="flex items-start gap-2">
        {/* Checkbox */}
        <input
          type="checkbox"
          checked={isSelected}
          onChange={onToggleSelect}
          className="mt-0.5 h-3.5 w-3.5 shrink-0 rounded border-gray-300 text-brand focus:ring-brand"
        />

        <div className="min-w-0 flex-1">
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

          {/* Source */}
          {result.source && (
            <p className="mt-0.5 text-office-xs text-text-tertiary">
              {result.source}
            </p>
          )}

          {/* Content preview */}
          <p
            className={`mt-1 text-office-xs leading-relaxed text-text-secondary ${
              isExpanded ? '' : 'line-clamp-3'
            }`}
          >
            {result.content}
          </p>

          {/* Expand toggle */}
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
                <span
                  key={key}
                  className="rounded bg-surface-tertiary px-1.5 py-0.5 text-office-xs text-text-tertiary"
                >
                  {key}: {String(value)}
                </span>
              ))}
            </div>
          )}

          {/* Actions */}
          <div className="mt-2 flex flex-wrap gap-2">
            <ActionLink label="Inserir no doc" onClick={onInsert} />
            <ActionLink label="Nota de rodape" onClick={onInsertAsFootnote} />
            <ActionLink label="Copiar" onClick={onCopyText} />
            <ActionLink label="Usar como contexto" onClick={onUseAsContext} />
          </div>
        </div>
      </div>
    </div>
  );
}

function ActionLink({
  label,
  onClick,
}: {
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      onClick={(e) => {
        e.stopPropagation();
        onClick();
      }}
      className="text-office-xs font-medium text-brand hover:underline"
    >
      {label}
    </button>
  );
}
