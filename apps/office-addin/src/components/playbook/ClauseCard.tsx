import { useState } from 'react';
import type { ClauseData, RedlineData } from '@/api/client';
import { Spinner } from '@/components/ui/Spinner';

type ActionType = 'apply' | 'comment' | 'highlight' | 'reject' | null;

interface ClauseCardProps {
  clause: ClauseData;
  redline?: RedlineData;
  isHighlighted: boolean;
  isApplied: boolean;
  isRejected: boolean;
  onNavigate: (clause: ClauseData) => void;
  onApplyComment: (clause: ClauseData) => Promise<void> | void;
  onApplyHighlight: (clause: ClauseData) => Promise<void> | void;
  onApplyTrackedChange: (clause: ClauseData) => Promise<void> | void;
  onPreviewRedline: (clause: ClauseData) => void;
  onReject: (clause: ClauseData) => Promise<void> | void;
}

const classificationLabels: Record<string, string> = {
  compliant: 'Conforme',
  needs_review: 'Revisao',
  non_compliant: 'Nao conforme',
  not_found: 'Ausente',
  // Legacy
  conforme: 'Conforme',
  nao_conforme: 'Nao conforme',
  ausente: 'Ausente',
  parcial: 'Parcial',
};

const classificationColors: Record<string, string> = {
  compliant: 'border-l-status-success',
  needs_review: 'border-l-status-warning',
  non_compliant: 'border-l-status-error',
  not_found: 'border-l-gray-400',
  // Legacy
  conforme: 'border-l-status-success',
  nao_conforme: 'border-l-status-error',
  ausente: 'border-l-status-warning',
  parcial: 'border-l-status-info',
};

const classificationBadgeColors: Record<string, string> = {
  compliant: 'bg-green-100 text-green-800',
  needs_review: 'bg-amber-100 text-amber-800',
  non_compliant: 'bg-red-100 text-red-800',
  not_found: 'bg-gray-100 text-gray-600',
  conforme: 'bg-green-100 text-green-800',
  nao_conforme: 'bg-red-100 text-red-800',
  ausente: 'bg-amber-100 text-amber-800',
  parcial: 'bg-blue-100 text-blue-800',
};

const severityBadge: Record<string, string> = {
  critical: 'bg-red-100 text-status-error',
  high: 'bg-orange-100 text-orange-700',
  medium: 'bg-amber-100 text-status-warning',
  low: 'bg-blue-100 text-status-info',
  warning: 'bg-amber-100 text-status-warning',
  info: 'bg-blue-100 text-status-info',
};

const severityLabels: Record<string, string> = {
  critical: 'Critico',
  high: 'Alto',
  medium: 'Medio',
  low: 'Baixo',
  warning: 'Atencao',
  info: 'Info',
};

export function ClauseCard({
  clause,
  redline,
  isHighlighted,
  isApplied,
  isRejected,
  onNavigate,
  onApplyComment,
  onApplyHighlight,
  onApplyTrackedChange,
  onPreviewRedline,
  onReject,
}: ClauseCardProps) {
  const [showActions, setShowActions] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [loadingAction, setLoadingAction] = useState<ActionType>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [lastAction, setLastAction] = useState<{
    type: ActionType;
    handler: () => Promise<void> | void;
  } | null>(null);

  const borderColor =
    classificationColors[clause.classification] || 'border-l-gray-300';
  const highlightRing = isHighlighted ? 'ring-2 ring-brand ring-offset-1' : '';
  const appliedOpacity = isApplied ? 'opacity-60' : '';
  const rejectedOpacity = isRejected ? 'opacity-40' : '';

  const isNonCompliant =
    clause.classification !== 'compliant' && clause.classification !== 'conforme';
  const hasRedline = !!redline;
  const hasSuggestion = !!clause.suggested_redline;
  const isLoading = loadingAction !== null;

  const executeAction = async (
    type: ActionType,
    handler: () => Promise<void> | void
  ) => {
    setLoadingAction(type);
    setActionError(null);
    setLastAction({ type, handler });

    try {
      await handler();
      setShowActions(false);
      setLastAction(null);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : 'Erro ao executar acao';
      setActionError(message);
    } finally {
      setLoadingAction(null);
    }
  };

  const handleRetry = async () => {
    if (lastAction) {
      await executeAction(lastAction.type, lastAction.handler);
    }
  };

  const dismissError = () => {
    setActionError(null);
    setLastAction(null);
  };

  return (
    <div
      className={`office-card border-l-4 ${borderColor} ${highlightRing} ${appliedOpacity} ${rejectedOpacity} transition-all`}
      onClick={() => onNavigate(clause)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => e.key === 'Enter' && onNavigate(clause)}
    >
      {/* Header: rule name + badges */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <span className="text-office-sm font-medium leading-tight">
            {clause.rule_name}
          </span>
          <span className="ml-1.5 text-office-xs text-text-tertiary">
            ({clause.clause_type})
          </span>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <span
            className={`rounded-full px-2 py-0.5 text-office-xs font-medium ${
              severityBadge[clause.severity] || 'bg-gray-100 text-gray-600'
            }`}
          >
            {severityLabels[clause.severity] || clause.severity}
          </span>
          <span
            className={`rounded-full px-2 py-0.5 text-office-xs font-medium ${
              classificationBadgeColors[clause.classification] ||
              'bg-gray-100 text-gray-600'
            }`}
          >
            {classificationLabels[clause.classification] || clause.classification}
          </span>
        </div>
      </div>

      {/* Confidence bar */}
      {clause.confidence > 0 && (
        <div className="mt-1 flex items-center gap-2">
          <div className="h-1 flex-1 rounded-full bg-gray-200">
            <div
              className="h-1 rounded-full bg-brand/60"
              style={{ width: `${clause.confidence * 100}%` }}
            />
          </div>
          <span className="text-[10px] text-text-tertiary">
            {Math.round(clause.confidence * 100)}%
          </span>
        </div>
      )}

      {/* Explanation */}
      <p className="mt-1.5 text-office-xs leading-relaxed text-text-secondary">
        {expanded
          ? clause.explanation
          : clause.explanation.slice(0, 150) +
            (clause.explanation.length > 150 ? '...' : '')}
        {clause.explanation.length > 150 && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              setExpanded(!expanded);
            }}
            className="ml-1 text-brand hover:underline"
          >
            {expanded ? 'ver menos' : 'ver mais'}
          </button>
        )}
      </p>

      {/* Comment / AI reasoning */}
      {clause.comment && (
        <p className="mt-1 text-office-xs italic text-text-tertiary">
          {clause.comment}
        </p>
      )}

      {/* Original text excerpt */}
      {clause.original_text && (
        <p className="mt-2 rounded bg-surface-tertiary p-2 text-office-xs text-text-secondary italic">
          &ldquo;
          {clause.original_text.slice(0, 200)}
          {clause.original_text.length > 200 ? '...' : ''}
          &rdquo;
        </p>
      )}

      {/* Suggested redline */}
      {hasSuggestion && isNonCompliant && (
        <div className="mt-2 rounded border border-green-200 bg-green-50 p-2">
          <p className="text-office-xs font-medium text-green-800">
            Sugestao de redline:
          </p>
          <p className="mt-0.5 text-office-xs text-green-700">
            {clause.suggested_redline!.slice(0, 300)}
            {clause.suggested_redline!.length > 300 ? '...' : ''}
          </p>
        </div>
      )}

      {/* Redline indicator */}
      {hasRedline && !isApplied && !isRejected && (
        <div className="mt-1.5 flex items-center gap-1">
          <div className="h-2 w-2 rounded-full bg-brand" />
          <span className="text-[10px] font-medium text-brand">
            Redline disponivel
          </span>
        </div>
      )}

      {/* Error message with retry */}
      {actionError && (
        <div
          className="mt-2 rounded border border-red-200 bg-red-50 p-2"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="flex items-start justify-between gap-2">
            <p className="text-office-xs text-red-700">{actionError}</p>
            <button
              onClick={dismissError}
              className="shrink-0 text-red-500 hover:text-red-700"
              aria-label="Fechar erro"
            >
              <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
          <button
            onClick={handleRetry}
            disabled={isLoading}
            className="mt-1.5 flex items-center gap-1 text-office-xs font-medium text-red-600 hover:text-red-800 disabled:opacity-50"
          >
            {loadingAction ? (
              <Spinner size="xs" />
            ) : (
              <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
            )}
            Tentar novamente
          </button>
        </div>
      )}

      {/* Action buttons */}
      {isNonCompliant && !isApplied && !isRejected && !actionError && (
        <div className="mt-2">
          {!showActions ? (
            <button
              onClick={(e) => {
                e.stopPropagation();
                setShowActions(true);
              }}
              className="text-office-xs font-medium text-brand hover:underline"
            >
              Acoes...
            </button>
          ) : (
            <div
              className="flex flex-wrap gap-1.5"
              onClick={(e) => e.stopPropagation()}
            >
              {hasRedline && (
                <ActionButton
                  label="Apply"
                  variant="primary"
                  loading={loadingAction === 'apply'}
                  disabled={isLoading}
                  onClick={() =>
                    executeAction('apply', () => onApplyTrackedChange(clause))
                  }
                />
              )}
              {hasSuggestion && (
                <ActionButton
                  label="Preview"
                  disabled={isLoading}
                  onClick={() => {
                    onPreviewRedline(clause);
                    setShowActions(false);
                  }}
                />
              )}
              <ActionButton
                label="Comentario"
                loading={loadingAction === 'comment'}
                disabled={isLoading}
                onClick={() =>
                  executeAction('comment', () => onApplyComment(clause))
                }
              />
              <ActionButton
                label="Destacar"
                loading={loadingAction === 'highlight'}
                disabled={isLoading}
                onClick={() =>
                  executeAction('highlight', () => onApplyHighlight(clause))
                }
              />
              {hasRedline && (
                <ActionButton
                  label="Rejeitar"
                  variant="danger"
                  loading={loadingAction === 'reject'}
                  disabled={isLoading}
                  onClick={() =>
                    executeAction('reject', () => onReject(clause))
                  }
                />
              )}
              <ActionButton
                label="Cancelar"
                variant="ghost"
                disabled={isLoading}
                onClick={() => setShowActions(false)}
              />
            </div>
          )}
        </div>
      )}

      {/* Status indicators */}
      {isApplied && (
        <div className="mt-2 flex items-center gap-1.5">
          <svg className="h-4 w-4 text-status-success" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
          </svg>
          <p className="text-office-xs font-medium text-status-success">
            Redline aplicado
          </p>
        </div>
      )}
      {isRejected && (
        <div className="mt-2 flex items-center gap-1.5">
          <svg className="h-4 w-4 text-text-tertiary" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
          <p className="text-office-xs font-medium text-text-tertiary">
            Redline rejeitado
          </p>
        </div>
      )}
    </div>
  );
}

function ActionButton({
  label,
  onClick,
  variant = 'default',
  loading = false,
  disabled = false,
}: {
  label: string;
  onClick: () => void;
  variant?: 'default' | 'primary' | 'danger' | 'ghost';
  loading?: boolean;
  disabled?: boolean;
}) {
  const styles = {
    default: 'bg-brand/10 text-brand hover:bg-brand/20',
    primary: 'bg-brand text-white hover:bg-brand/90',
    danger: 'bg-red-50 text-status-error hover:bg-red-100',
    ghost: 'bg-transparent text-text-tertiary hover:bg-surface-tertiary',
  };

  return (
    <button
      onClick={onClick}
      disabled={disabled || loading}
      className={`flex items-center gap-1.5 rounded px-2 py-1 text-office-xs font-medium transition-colors disabled:opacity-50 ${styles[variant]}`}
    >
      {loading && <Spinner size="xs" />}
      {label}
    </button>
  );
}
