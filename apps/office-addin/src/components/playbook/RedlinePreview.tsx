import type { ClauseData, RedlineData } from '@/api/client';

interface RedlinePreviewProps {
  clause: ClauseData;
  redline?: RedlineData;
  onAccept: () => void;
  onReject: () => void;
}

const severityLabels: Record<string, string> = {
  critical: 'Critico',
  high: 'Alto',
  medium: 'Medio',
  low: 'Baixo',
};

const classificationLabels: Record<string, string> = {
  compliant: 'Conforme',
  needs_review: 'Necessita Revisao',
  non_compliant: 'Nao Conforme',
  not_found: 'Nao Encontrada',
};

export function RedlinePreview({
  clause,
  redline,
  onAccept,
  onReject,
}: RedlinePreviewProps) {
  const suggestedText = clause.suggested_redline || redline?.suggested_text;
  if (!suggestedText) return null;

  const originalText = clause.original_text || redline?.original_text || '';
  const severity = clause.severity || redline?.severity || '';
  const classification = clause.classification || redline?.classification || '';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
      <div className="max-h-[80vh] w-full max-w-md overflow-y-auto rounded-lg bg-white shadow-xl">
        {/* Header */}
        <div className="border-b border-gray-200 p-4">
          <h3 className="text-office-base font-semibold">Preview do Redline</h3>
          <p className="mt-1 text-office-xs text-text-secondary">
            {clause.rule_name}
          </p>
          <div className="mt-1.5 flex gap-2 text-office-xs">
            <span className="rounded bg-gray-100 px-1.5 py-0.5 text-text-secondary">
              {classificationLabels[classification] || classification}
            </span>
            <span className="rounded bg-gray-100 px-1.5 py-0.5 text-text-secondary">
              Severidade: {severityLabels[severity] || severity}
            </span>
            {redline && (
              <span className="rounded bg-brand/10 px-1.5 py-0.5 text-brand">
                Confianca: {Math.round((redline.confidence || 0) * 100)}%
              </span>
            )}
          </div>
        </div>

        {/* Content */}
        <div className="space-y-4 p-4">
          {/* Original */}
          {originalText && (
            <div>
              <p className="mb-1 text-office-xs font-medium text-status-error">
                Texto original (sera removido):
              </p>
              <div className="rounded border border-red-200 bg-red-50 p-3">
                <p className="text-office-sm leading-relaxed text-red-900 line-through">
                  {originalText}
                </p>
              </div>
            </div>
          )}

          {/* Suggested */}
          <div>
            <p className="mb-1 text-office-xs font-medium text-status-success">
              Texto sugerido (sera inserido):
            </p>
            <div className="rounded border border-green-200 bg-green-50 p-3">
              <p className="text-office-sm leading-relaxed text-green-900">
                {suggestedText}
              </p>
            </div>
          </div>

          {/* Explanation */}
          <div className="rounded bg-surface-tertiary p-3">
            <p className="text-office-xs font-medium text-text-primary">
              Justificativa:
            </p>
            <p className="mt-1 text-office-xs text-text-secondary">
              {clause.explanation}
            </p>
          </div>

          {/* AI Comment */}
          {clause.comment && (
            <div className="rounded bg-blue-50 p-3">
              <p className="text-office-xs font-medium text-blue-800">
                Raciocinio da IA:
              </p>
              <p className="mt-1 text-office-xs text-blue-700">
                {clause.comment}
              </p>
            </div>
          )}

          {/* OOXML info */}
          {redline?.ooxml && (
            <p className="text-[10px] text-text-tertiary">
              Tracked change OOXML disponivel - sera inserido como revisao no Word
            </p>
          )}
        </div>

        {/* Actions */}
        <div className="flex gap-2 border-t border-gray-200 p-4">
          <button
            onClick={onReject}
            className="flex-1 rounded border border-gray-300 px-3 py-2 text-office-sm font-medium text-text-secondary hover:bg-surface-tertiary"
          >
            Cancelar
          </button>
          <button
            onClick={onAccept}
            className="flex-1 rounded bg-brand px-3 py-2 text-office-sm font-medium text-white hover:bg-brand/90"
          >
            Aplicar Redline
          </button>
        </div>
      </div>
    </div>
  );
}
