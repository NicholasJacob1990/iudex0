'use client';

import { useState, useMemo, useCallback } from 'react';
import {
  ChevronDown,
  ChevronUp,
  Download,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  HelpCircle,
  Shield,
  Check,
  Clock,
  Filter,
  User,
  MessageCircle,
  X,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { cn } from '@/lib/utils';
import {
  type PlaybookAnalysis,
  type PlaybookAnalysisResult,
  type AnalysisResultStatus,
  type ClauseReviewInfo,
  STATUS_COLORS,
  STATUS_LABELS,
  SEVERITY_COLORS,
  SEVERITY_LABELS,
  useReviewClauses,
} from '../hooks';

type ReviewFilter = 'todas' | 'pendentes' | 'revisadas';
type StatusFilter = 'todos' | 'compliant' | 'review' | 'non_compliant' | 'not_found';

interface PlaybookAnalysisPanelProps {
  analysis: PlaybookAnalysis;
  onExport?: () => void;
  onAnalysisUpdated?: (updated: PlaybookAnalysis) => void;
}

const statusIcons: Record<AnalysisResultStatus, React.ReactNode> = {
  compliant: <CheckCircle2 className="h-4 w-4 text-green-500" />,
  review: <AlertTriangle className="h-4 w-4 text-yellow-500" />,
  non_compliant: <XCircle className="h-4 w-4 text-red-500" />,
  not_found: <HelpCircle className="h-4 w-4 text-slate-400" />,
};

function RiskScoreGauge({ score }: { score: number }) {
  const getColor = (s: number) => {
    if (s >= 80) return 'text-green-500';
    if (s >= 60) return 'text-yellow-500';
    if (s >= 40) return 'text-orange-500';
    return 'text-red-500';
  };

  const getLabel = (s: number) => {
    if (s >= 80) return 'Baixo Risco';
    if (s >= 60) return 'Risco Moderado';
    if (s >= 40) return 'Risco Elevado';
    return 'Alto Risco';
  };

  return (
    <div className="flex flex-col items-center gap-3 p-6 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900">
      <div className="relative h-32 w-32">
        <svg className="h-32 w-32 -rotate-90" viewBox="0 0 120 120">
          <circle
            cx="60"
            cy="60"
            r="50"
            fill="none"
            stroke="currentColor"
            strokeWidth="10"
            className="text-slate-100 dark:text-slate-800"
          />
          <circle
            cx="60"
            cy="60"
            r="50"
            fill="none"
            stroke="currentColor"
            strokeWidth="10"
            strokeLinecap="round"
            strokeDasharray={`${(score / 100) * 314} 314`}
            className={getColor(score)}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <Shield className={cn('h-5 w-5 mb-1', getColor(score))} />
          <span className={cn('text-2xl font-bold', getColor(score))}>{score}</span>
        </div>
      </div>
      <div className="text-center">
        <p className={cn('text-sm font-semibold', getColor(score))}>{getLabel(score)}</p>
        <p className="text-xs text-slate-500 mt-0.5">Score de conformidade</p>
      </div>
      <Progress value={score} className="h-2 w-full" />
    </div>
  );
}

function ResultSummary({ results }: { results: PlaybookAnalysisResult[] }) {
  const counts = {
    compliant: results.filter((r) => r.status === 'compliant').length,
    review: results.filter((r) => r.status === 'review').length,
    non_compliant: results.filter((r) => r.status === 'non_compliant').length,
    not_found: results.filter((r) => r.status === 'not_found').length,
  };

  return (
    <div className="grid grid-cols-4 gap-3">
      {([
        { key: 'compliant', label: 'Conformes', icon: CheckCircle2, color: 'text-green-500', bg: 'bg-green-50 dark:bg-green-900/10' },
        { key: 'review', label: 'Revisao', icon: AlertTriangle, color: 'text-yellow-500', bg: 'bg-yellow-50 dark:bg-yellow-900/10' },
        { key: 'non_compliant', label: 'Nao conformes', icon: XCircle, color: 'text-red-500', bg: 'bg-red-50 dark:bg-red-900/10' },
        { key: 'not_found', label: 'Nao encontrados', icon: HelpCircle, color: 'text-slate-400', bg: 'bg-slate-50 dark:bg-slate-800' },
      ] as const).map(({ key, label, icon: Icon, color, bg }) => (
        <div key={key} className={cn('rounded-lg p-3 text-center', bg)}>
          <Icon className={cn('h-5 w-5 mx-auto mb-1', color)} />
          <p className="text-lg font-bold text-slate-800 dark:text-slate-200">
            {counts[key]}
          </p>
          <p className="text-[10px] text-slate-500">{label}</p>
        </div>
      ))}
    </div>
  );
}

function ReviewProgressBar({
  reviewed,
  total,
}: {
  reviewed: number;
  total: number;
}) {
  const percentage = total > 0 ? Math.round((reviewed / total) * 100) : 0;

  return (
    <div className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-4 space-y-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Check className="h-4 w-4 text-green-500" />
          <span className="text-sm font-medium text-slate-700 dark:text-slate-300">
            Progresso da Revisao
          </span>
        </div>
        <span className="text-sm font-semibold text-slate-800 dark:text-slate-200">
          {reviewed}/{total} ({percentage}%)
        </span>
      </div>
      <div className="h-2.5 w-full rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden">
        <div
          className="h-full rounded-full bg-green-500 transition-all duration-500"
          style={{ width: `${percentage}%` }}
        />
      </div>
    </div>
  );
}

function ReviewFilterBar({
  filter,
  onFilterChange,
  counts,
}: {
  filter: ReviewFilter;
  onFilterChange: (f: ReviewFilter) => void;
  counts: { todas: number; pendentes: number; revisadas: number };
}) {
  const tabs: { key: ReviewFilter; label: string }[] = [
    { key: 'todas', label: `Todas (${counts.todas})` },
    { key: 'pendentes', label: `Pendentes (${counts.pendentes})` },
    { key: 'revisadas', label: `Revisadas (${counts.revisadas})` },
  ];

  return (
    <div className="flex items-center gap-1 rounded-lg bg-slate-100 dark:bg-slate-800 p-1">
      <Filter className="h-3.5 w-3.5 text-slate-400 ml-2 mr-1" />
      {tabs.map(({ key, label }) => (
        <button
          key={key}
          onClick={() => onFilterChange(key)}
          className={cn(
            'px-3 py-1.5 text-xs font-medium rounded-md transition-all',
            filter === key
              ? 'bg-white dark:bg-slate-700 text-slate-800 dark:text-slate-200 shadow-sm'
              : 'text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'
          )}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Status Filter Chips (Task #3)
// ---------------------------------------------------------------------------

const STATUS_FILTER_CONFIG: {
  key: StatusFilter;
  label: string;
  icon: React.ElementType;
  activeClass: string;
}[] = [
  { key: 'todos', label: 'Todos', icon: Filter, activeClass: 'bg-slate-600 text-white' },
  { key: 'compliant', label: 'Aceitavel', icon: CheckCircle2, activeClass: 'bg-green-600 text-white' },
  { key: 'review', label: 'Precisa Revisao', icon: AlertTriangle, activeClass: 'bg-yellow-500 text-white' },
  { key: 'non_compliant', label: 'Inaceitavel', icon: XCircle, activeClass: 'bg-red-600 text-white' },
];

function StatusFilterChips({
  active,
  onChange,
  counts,
}: {
  active: StatusFilter;
  onChange: (f: StatusFilter) => void;
  counts: Record<StatusFilter, number>;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      {STATUS_FILTER_CONFIG.map(({ key, label, icon: Icon, activeClass }) => {
        const isActive = active === key;
        return (
          <button
            key={key}
            onClick={() => onChange(key)}
            className={cn(
              'inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-all border',
              isActive
                ? `${activeClass} border-transparent`
                : 'bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300 border-slate-200 dark:border-slate-700 hover:border-slate-300'
            )}
          >
            <Icon className="h-3.5 w-3.5" />
            {label}
            <Badge
              className={cn(
                'h-5 min-w-[20px] px-1.5 text-[10px] border-0 rounded-full',
                isActive
                  ? 'bg-white/20 text-white'
                  : 'bg-slate-100 dark:bg-slate-700 text-slate-500 dark:text-slate-400'
              )}
            >
              {counts[key]}
            </Badge>
          </button>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Comment Bubble (Task #1)
// ---------------------------------------------------------------------------

function CommentBubble({ comment }: { comment: string }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="relative inline-flex">
      <button
        onClick={(e) => {
          e.stopPropagation();
          setOpen(!open);
        }}
        className={cn(
          'flex items-center justify-center h-6 w-6 rounded-full transition-colors',
          open
            ? 'bg-indigo-100 text-indigo-600 dark:bg-indigo-900/30 dark:text-indigo-400'
            : 'bg-slate-100 text-slate-400 hover:bg-indigo-50 hover:text-indigo-500 dark:bg-slate-800 dark:hover:bg-indigo-900/20'
        )}
        title="Ver comentario da IA"
      >
        <MessageCircle className="h-3.5 w-3.5" />
      </button>
      {open && (
        <div className="absolute right-0 top-8 z-50 w-72 rounded-lg border border-indigo-200 dark:border-indigo-800 bg-white dark:bg-slate-900 shadow-lg p-3 animate-in fade-in-0 zoom-in-95">
          <div className="flex items-start justify-between gap-2 mb-1.5">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-indigo-600 dark:text-indigo-400">
              Comentario da IA
            </p>
            <button
              onClick={(e) => {
                e.stopPropagation();
                setOpen(false);
              }}
              className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-300"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
          <p className="text-xs text-slate-700 dark:text-slate-300 leading-relaxed">
            {comment}
          </p>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Analysis Result Card
// ---------------------------------------------------------------------------

function AnalysisResultCard({
  result,
  reviewInfo,
  onToggleReview,
  isReviewing,
}: {
  result: PlaybookAnalysisResult;
  reviewInfo?: ClauseReviewInfo | null;
  onToggleReview: (ruleId: string, reviewed: boolean) => void;
  isReviewing: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const isReviewed = !!reviewInfo;

  return (
    <div
      className={cn(
        'rounded-lg border overflow-hidden transition-all',
        isReviewed
          ? 'border-green-200 dark:border-green-800/50 bg-green-50/30 dark:bg-green-900/5'
          : 'border-slate-200 dark:border-slate-700'
      )}
    >
      <div className="flex items-center">
        {/* Review checkbox */}
        <button
          onClick={(e) => {
            e.stopPropagation();
            onToggleReview(result.rule_id, !isReviewed);
          }}
          disabled={isReviewing}
          className={cn(
            'flex items-center justify-center h-full px-3 py-3 border-r transition-colors shrink-0',
            isReviewed
              ? 'border-green-200 dark:border-green-800/50 bg-green-50 dark:bg-green-900/20'
              : 'border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800/50'
          )}
          title={isReviewed ? 'Marcar como pendente' : 'Marcar como revisada'}
        >
          <div
            className={cn(
              'h-5 w-5 rounded border-2 flex items-center justify-center transition-all',
              isReviewed
                ? 'bg-green-500 border-green-500'
                : 'border-slate-300 dark:border-slate-600',
              isReviewing && 'opacity-50'
            )}
          >
            {isReviewed && <Check className="h-3 w-3 text-white" />}
          </div>
        </button>

        {/* Main content button */}
        <button
          onClick={() => setExpanded(!expanded)}
          className={cn(
            'flex-1 flex items-center gap-3 px-4 py-3 text-left hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors',
            isReviewed && 'opacity-75'
          )}
        >
          {statusIcons[result.status]}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span
                className={cn(
                  'text-sm font-medium truncate',
                  isReviewed
                    ? 'text-slate-500 dark:text-slate-400 line-through decoration-green-400/50'
                    : 'text-slate-800 dark:text-slate-200'
                )}
              >
                {result.rule_name}
              </span>
              <Badge variant="outline" className="text-[10px] shrink-0">
                {result.clause_type}
              </Badge>
              {isReviewed && (
                <Badge className="text-[10px] border-0 bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400 shrink-0">
                  Revisada
                </Badge>
              )}
            </div>
          </div>
          {/* Comment bubble icon */}
          {result.comment && <CommentBubble comment={result.comment} />}
          <Badge className={cn('text-[10px] border-0 shrink-0', STATUS_COLORS[result.status])}>
            {STATUS_LABELS[result.status]}
          </Badge>
          <Badge className={cn('text-[10px] border-0 shrink-0', SEVERITY_COLORS[result.severity])}>
            {SEVERITY_LABELS[result.severity]}
          </Badge>
          {expanded ? (
            <ChevronUp className="h-4 w-4 text-slate-400 shrink-0" />
          ) : (
            <ChevronDown className="h-4 w-4 text-slate-400 shrink-0" />
          )}
        </button>
      </div>

      {expanded && (
        <div className="px-4 pb-4 space-y-3 border-t border-slate-100 dark:border-slate-800 pt-3 ml-[52px]">
          {result.original_text && (
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 mb-1">
                Texto Original
              </p>
              <div className="rounded-lg bg-slate-50 dark:bg-slate-800 p-3 text-sm text-slate-700 dark:text-slate-300">
                {result.original_text}
              </div>
            </div>
          )}

          <div>
            <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 mb-1">
              Analise
            </p>
            <div className="rounded-lg bg-blue-50 dark:bg-blue-900/10 p-3 text-sm text-slate-700 dark:text-slate-300">
              {result.explanation}
            </div>
          </div>

          {/* AI Comment (expanded view) */}
          {result.comment && (
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-wider text-indigo-500 mb-1">
                Comentario da IA
              </p>
              <div className="rounded-lg bg-indigo-50 dark:bg-indigo-900/10 border border-indigo-200 dark:border-indigo-800 p-3 text-sm text-slate-700 dark:text-slate-300">
                <div className="flex items-start gap-2">
                  <MessageCircle className="h-4 w-4 text-indigo-500 shrink-0 mt-0.5" />
                  <span>{result.comment}</span>
                </div>
              </div>
            </div>
          )}

          {result.suggested_redline && (
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 mb-1">
                Redline Sugerido
              </p>
              <div className="rounded-lg bg-amber-50 dark:bg-amber-900/10 border border-amber-200 dark:border-amber-800 p-3 text-sm text-slate-700 dark:text-slate-300">
                {result.suggested_redline}
              </div>
            </div>
          )}

          {/* Review info */}
          {isReviewed && reviewInfo && (
            <div className="rounded-lg bg-green-50 dark:bg-green-900/10 border border-green-200 dark:border-green-800 p-3">
              <p className="text-[10px] font-semibold uppercase tracking-wider text-green-600 dark:text-green-400 mb-1">
                Revisao
              </p>
              <div className="flex items-center gap-3 text-xs text-green-700 dark:text-green-300">
                <span className="flex items-center gap-1">
                  <User className="h-3 w-3" />
                  {reviewInfo.reviewed_by}
                </span>
                <span className="flex items-center gap-1">
                  <Clock className="h-3 w-3" />
                  {new Date(reviewInfo.reviewed_at).toLocaleString('pt-BR')}
                </span>
                <Badge className="text-[10px] border-0 bg-green-200 text-green-800 dark:bg-green-800 dark:text-green-200">
                  {reviewInfo.status === 'approved'
                    ? 'Aprovada'
                    : reviewInfo.status === 'rejected'
                      ? 'Rejeitada'
                      : 'Modificada'}
                </Badge>
              </div>
              {reviewInfo.notes && (
                <p className="text-xs text-green-600 dark:text-green-400 mt-1.5">
                  {reviewInfo.notes}
                </p>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function PlaybookAnalysisPanel({ analysis, onExport, onAnalysisUpdated }: PlaybookAnalysisPanelProps) {
  const [reviewFilter, setReviewFilter] = useState<ReviewFilter>('todas');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('todos');
  const reviewMutation = useReviewClauses();

  const reviewedClauses = useMemo(() => analysis.reviewed_clauses ?? {}, [analysis.reviewed_clauses]);

  const reviewCounts = useMemo(() => {
    const total = analysis.results.length;
    const reviewed = analysis.results.filter((r) => !!reviewedClauses[r.rule_id]).length;
    return {
      todas: total,
      revisadas: reviewed,
      pendentes: total - reviewed,
    };
  }, [analysis.results, reviewedClauses]);

  // Status counts for filter chips
  const statusCounts = useMemo(() => {
    return {
      todos: analysis.results.length,
      compliant: analysis.results.filter((r) => r.status === 'compliant').length,
      review: analysis.results.filter((r) => r.status === 'review').length,
      non_compliant: analysis.results.filter((r) => r.status === 'non_compliant').length,
      not_found: analysis.results.filter((r) => r.status === 'not_found').length,
    };
  }, [analysis.results]);

  const filteredResults = useMemo(() => {
    let results = analysis.results;

    // Apply status filter
    if (statusFilter !== 'todos') {
      results = results.filter((r) => r.status === statusFilter);
    }

    // Apply review filter
    if (reviewFilter === 'revisadas') {
      results = results.filter((r) => !!reviewedClauses[r.rule_id]);
    } else if (reviewFilter === 'pendentes') {
      results = results.filter((r) => !reviewedClauses[r.rule_id]);
    }

    return results;
  }, [analysis.results, reviewedClauses, reviewFilter, statusFilter]);

  const handleToggleReview = useCallback(
    async (ruleId: string, reviewed: boolean) => {
      // Only allow review toggle on persisted analyses (with real IDs)
      if (!analysis.id || analysis.id.startsWith('analysis-')) {
        return;
      }

      if (reviewed) {
        const updatedAnalysis = await reviewMutation.mutateAsync({
          playbookId: analysis.playbook_id,
          analysisId: analysis.id,
          reviews: {
            [ruleId]: { status: 'approved' },
          },
        });
        onAnalysisUpdated?.(updatedAnalysis);
      }
    },
    [analysis.id, analysis.playbook_id, reviewMutation, onAnalysisUpdated]
  );

  const canReview = analysis.id && !analysis.id.startsWith('analysis-');

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold text-slate-800 dark:text-slate-200">
            Resultado da Analise
          </h3>
          <p className="text-xs text-slate-500 mt-0.5">
            Documento: {analysis.document_name} | Executada em{' '}
            {new Date(analysis.created_at).toLocaleString('pt-BR')}
          </p>
        </div>
        {onExport && (
          <Button variant="outline" size="sm" className="gap-1.5" onClick={onExport}>
            <Download className="h-3.5 w-3.5" />
            Exportar
          </Button>
        )}
      </div>

      {/* Risk Score */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <RiskScoreGauge score={analysis.risk_score} />
        <div className="lg:col-span-2">
          <ResultSummary results={analysis.results} />
        </div>
      </div>

      {/* Review Progress */}
      {canReview && (
        <ReviewProgressBar
          reviewed={reviewCounts.revisadas}
          total={reviewCounts.todas}
        />
      )}

      {/* Status Filter Chips (Task #3) */}
      <StatusFilterChips
        active={statusFilter}
        onChange={setStatusFilter}
        counts={statusCounts}
      />

      {/* Results list */}
      <div className="space-y-3">
        <div className="flex items-center justify-between gap-4">
          <h4 className="text-sm font-semibold text-slate-600 dark:text-slate-300">
            Resultado por Clausula ({filteredResults.length}
            {filteredResults.length !== analysis.results.length
              ? ` de ${analysis.results.length}`
              : ''})
          </h4>
          {canReview && (
            <ReviewFilterBar
              filter={reviewFilter}
              onFilterChange={setReviewFilter}
              counts={reviewCounts}
            />
          )}
        </div>
        <div className="space-y-2">
          {filteredResults.map((result) => (
            <AnalysisResultCard
              key={result.rule_id}
              result={result}
              reviewInfo={reviewedClauses[result.rule_id] as ClauseReviewInfo | undefined}
              onToggleReview={handleToggleReview}
              isReviewing={reviewMutation.isPending}
            />
          ))}
          {filteredResults.length === 0 && (
            <div className="text-center py-8 text-sm text-slate-400">
              {statusFilter !== 'todos'
                ? `Nenhuma clausula com status "${STATUS_LABELS[statusFilter as AnalysisResultStatus] ?? statusFilter}"`
                : reviewFilter === 'revisadas'
                  ? 'Nenhuma clausula revisada ainda'
                  : reviewFilter === 'pendentes'
                    ? 'Todas as clausulas foram revisadas'
                    : 'Nenhum resultado encontrado'}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
