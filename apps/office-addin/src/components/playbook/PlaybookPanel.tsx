import { useEffect, useState, useCallback, useRef } from 'react';
import { usePlaybookStore } from '@/stores/playbook-store';
import type { ClauseData, RecommendedPlaybook } from '@/api/client';
import { recommendPlaybook } from '@/api/client';
import { ClauseCard } from './ClauseCard';
import { RedlinePreview } from './RedlinePreview';
import { HistoryButton, HistoryModal } from './HistoryPanel';
import { ToastContainer, useGlobalToast, toast } from '@/components/ui/Toast';
import { Spinner } from '@/components/ui/Spinner';
import {
  navigateToText,
  applyRedlineAsComment,
  applyRedlineWithHighlight,
  applyRedlineAsTrackedChange,
  applyBatchRedlines,
  highlightClauses,
  clearHighlights,
  type RedlineOperation,
} from '@/office/redline-engine';
import { exportAuditReport, type ExportFormat } from '@/api/audit-export';
import { useDocumentStore } from '@/stores/document-store';

// Intervalo para verificar modificacoes no documento (em ms)
const MODIFICATION_CHECK_INTERVAL = 10000; // 10 segundos

export function PlaybookPanel() {
  const {
    state,
    playbooks,
    selectedPlaybook,
    summary,
    stats,
    redlines,
    error,
    filterClassification,
    filterSeverity,
    reviewTab,
    highlightedClauseId,
    appliedRedlines,
    rejectedRedlines,
    documentModified,
    loadPlaybooks,
    runPlaybookAnalysis,
    reset,
    setFilterClassification,
    setFilterSeverity,
    setReviewTab,
    setHighlightedClause,
    markRedlineApplied,
    markRedlineRejected,
    filteredClauses,
    pendingRedlines,
    reviewProgress,
    toRedlineOperations,
    getRedlineForClause,
    initSyncListener,
    checkDocumentModification,
    updateDocumentHash,
  } = usePlaybookStore();

  const [previewClause, setPreviewClause] = useState<ClauseData | null>(null);
  const [batchLoading, setBatchLoading] = useState<string | null>(null);
  const [showRedlinesOnly, setShowRedlinesOnly] = useState(false);
  const [showExportMenu, setShowExportMenu] = useState(false);
  const [exportLoading, setExportLoading] = useState<ExportFormat | null>(null);
  const modificationCheckRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Gap 11: Historico de analises
  const [showHistory, setShowHistory] = useState(false);

  // Gap 12: Recomendacoes de playbooks
  const [recommendations, setRecommendations] = useState<RecommendedPlaybook[]>([]);
  const [recommendationLoading, setRecommendationLoading] = useState(false);
  const [documentType, setDocumentType] = useState<string | null>(null);

  const { toasts, dismissToast } = useGlobalToast();
  const fullText = useDocumentStore((s) => s.fullText);
  const loadFullText = useDocumentStore((s) => s.loadFullText);

  useEffect(() => {
    loadPlaybooks();
  }, [loadPlaybooks]);

  // Gap 12: Carregar recomendacoes quando playbooks estiverem disponiveis
  useEffect(() => {
    const fetchRecommendations = async () => {
      // Carregar texto do documento se necessario
      if (!fullText) {
        await loadFullText();
      }

      const text = useDocumentStore.getState().fullText;
      if (!text || text.length < 100) return;

      setRecommendationLoading(true);
      try {
        // Pegar primeiros 2000 caracteres para classificacao
        const excerpt = text.slice(0, 2000);
        const result = await recommendPlaybook({ document_excerpt: excerpt });
        setRecommendations(result.recommended);
        setDocumentType(result.document_type);
      } catch (err) {
        console.error('Erro ao buscar recomendacoes:', err);
        // Nao mostrar erro ao usuario - feature opcional
      } finally {
        setRecommendationLoading(false);
      }
    };

    if (playbooks.length > 0 && state === 'idle') {
      fetchRecommendations();
    }
  }, [playbooks.length, state, fullText, loadFullText]);

  // Gap 5: Inicializar listener de sincronizacao entre abas
  useEffect(() => {
    const cleanup = initSyncListener();
    return cleanup;
  }, [initSyncListener]);

  // Gap 6: Verificar modificacoes no documento periodicamente quando em resultados
  useEffect(() => {
    if (state === 'results') {
      // Verificar imediatamente
      checkDocumentModification();

      // Configurar verificacao periodica
      modificationCheckRef.current = setInterval(() => {
        checkDocumentModification();
      }, MODIFICATION_CHECK_INTERVAL);

      return () => {
        if (modificationCheckRef.current) {
          clearInterval(modificationCheckRef.current);
          modificationCheckRef.current = null;
        }
      };
    }
  }, [state, checkDocumentModification]);

  const clauses = filteredClauses();
  const progress = reviewProgress();
  const pending = pendingRedlines();

  // Filter to show only clauses with redlines if toggle is on
  const displayClauses = showRedlinesOnly
    ? clauses.filter((c) => c.redline_id)
    : clauses;

  // Navigate to clause in document
  const handleNavigate = useCallback(
    async (clause: ClauseData) => {
      if (!clause.original_text) return;
      setHighlightedClause(clause.rule_id);
      await navigateToText(clause.original_text.slice(0, 255));
    },
    [setHighlightedClause]
  );

  // Apply single redline as OOXML tracked change
  const handleApplyTrackedChange = useCallback(
    async (clause: ClauseData) => {
      const redline = getRedlineForClause(clause.rule_id);
      if (!redline) {
        throw new Error('Redline nao encontrado');
      }

      const op: RedlineOperation = {
        id: redline.redline_id,
        action: 'replace',
        originalText: clause.original_text || '',
        suggestedText: clause.suggested_redline,
        comment: clause.explanation,
        severity: (clause.severity === 'critical' || clause.severity === 'high'
          ? 'critical'
          : clause.severity === 'medium'
            ? 'warning'
            : 'info') as 'critical' | 'warning' | 'info',
        ruleName: clause.rule_name,
        ooxml: redline.ooxml,
      };

      const result = await applyRedlineAsTrackedChange(op);
      if (result.success) {
        markRedlineApplied(redline.redline_id);
        toast.success('Redline aplicado com sucesso');
      } else {
        throw new Error(result.error || 'Falha ao aplicar redline');
      }
    },
    [getRedlineForClause, markRedlineApplied]
  );

  // Apply single redline as comment
  const handleApplyComment = useCallback(
    async (clause: ClauseData) => {
      const redline = getRedlineForClause(clause.rule_id);
      const id = redline?.redline_id || clause.rule_id;

      const op: RedlineOperation = {
        id,
        action: 'comment',
        originalText: clause.original_text || '',
        suggestedText: clause.suggested_redline,
        comment: clause.explanation,
        severity: (clause.severity === 'critical' || clause.severity === 'high'
          ? 'critical'
          : clause.severity === 'medium'
            ? 'warning'
            : 'info') as 'critical' | 'warning' | 'info',
        ruleName: clause.rule_name,
      };
      const result = await applyRedlineAsComment(op);
      if (result.success) {
        if (redline) markRedlineApplied(redline.redline_id);
        toast.success('Comentario adicionado');
      } else {
        throw new Error(result.error || 'Falha ao adicionar comentario');
      }
    },
    [getRedlineForClause, markRedlineApplied]
  );

  // Apply single redline with highlight
  const handleApplyHighlight = useCallback(
    async (clause: ClauseData) => {
      const redline = getRedlineForClause(clause.rule_id);
      const id = redline?.redline_id || clause.rule_id;

      const op: RedlineOperation = {
        id,
        action: 'comment',
        originalText: clause.original_text || '',
        suggestedText: clause.suggested_redline,
        comment: clause.explanation,
        severity: (clause.severity === 'critical' || clause.severity === 'high'
          ? 'critical'
          : clause.severity === 'medium'
            ? 'warning'
            : 'info') as 'critical' | 'warning' | 'info',
        ruleName: clause.rule_name,
      };
      const result = await applyRedlineWithHighlight(op);
      if (result.success) {
        if (redline) markRedlineApplied(redline.redline_id);
        toast.success('Trecho destacado');
      } else {
        throw new Error(result.error || 'Falha ao destacar trecho');
      }
    },
    [getRedlineForClause, markRedlineApplied]
  );

  // Reject redline
  const handleReject = useCallback(
    async (clause: ClauseData) => {
      const redline = getRedlineForClause(clause.rule_id);
      if (redline) {
        markRedlineRejected(redline.redline_id);
        toast.info('Redline rejeitado');
      }
    },
    [getRedlineForClause, markRedlineRejected]
  );

  // Accept from preview modal
  const handleAcceptRedline = useCallback(async () => {
    if (!previewClause) return;
    try {
      await handleApplyTrackedChange(previewClause);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Erro ao aplicar redline');
    }
    setPreviewClause(null);
  }, [previewClause, handleApplyTrackedChange]);

  // Batch: highlight all non-compliant in document
  const handleHighlightAll = useCallback(async () => {
    setBatchLoading('highlight');
    try {
      const toHighlight = usePlaybookStore
        .getState()
        .clauses.filter(
          (c) =>
            c.classification !== 'compliant' &&
            c.classification !== 'conforme' &&
            c.original_text
        )
        .map((c) => ({
          text: c.original_text || '',
          severity: (c.severity === 'critical' || c.severity === 'high'
            ? 'critical'
            : c.severity === 'medium'
              ? 'warning'
              : 'info') as 'critical' | 'warning' | 'info',
          classification: c.classification,
        }));
      const count = await highlightClauses(toHighlight);
      toast.success(`${count} trechos destacados no documento`);
    } catch {
      toast.error('Erro ao destacar trechos');
    } finally {
      setBatchLoading(null);
    }
  }, []);

  // Batch: apply all redlines as tracked changes
  const handleBatchTrackedChanges = useCallback(async () => {
    setBatchLoading('apply');
    try {
      const ops = toRedlineOperations();
      if (ops.length === 0) {
        toast.warning('Nenhum redline pendente para aplicar');
        setBatchLoading(null);
        return;
      }
      const result = await applyBatchRedlines(ops, 'tracked-change');
      result.results.forEach((r) => {
        if (r.success) markRedlineApplied(r.operationId);
      });
      if (result.applied === result.total) {
        toast.success(`${result.applied} redlines aplicados com sucesso`);
      } else {
        toast.warning(`${result.applied}/${result.total} redlines aplicados`);
      }
    } catch {
      toast.error('Erro ao aplicar redlines');
    } finally {
      setBatchLoading(null);
    }
  }, [toRedlineOperations, markRedlineApplied]);

  // Batch: apply all as comments
  const handleBatchComments = useCallback(async () => {
    setBatchLoading('comment');
    try {
      const ops = toRedlineOperations();
      if (ops.length === 0) {
        toast.warning('Nenhum redline pendente');
        setBatchLoading(null);
        return;
      }
      const result = await applyBatchRedlines(ops, 'comment');
      result.results.forEach((r) => {
        if (r.success) markRedlineApplied(r.operationId);
      });
      toast.success(`${result.applied}/${result.total} comentarios aplicados`);
    } catch {
      toast.error('Erro ao aplicar comentarios');
    } finally {
      setBatchLoading(null);
    }
  }, [toRedlineOperations, markRedlineApplied]);

  // Clear document highlights
  const handleClearHighlights = useCallback(async () => {
    setBatchLoading('clear');
    try {
      await clearHighlights();
      toast.success('Destaques removidos');
    } catch {
      toast.error('Erro ao limpar destaques');
    } finally {
      setBatchLoading(null);
    }
  }, []);

  // Gap 6: Reanalisar documento apos modificacoes
  const handleReanalyze = useCallback(async () => {
    if (selectedPlaybook) {
      await runPlaybookAnalysis(selectedPlaybook);
    }
  }, [selectedPlaybook, runPlaybookAnalysis]);

  // Gap 6: Ignorar warning de modificacao e atualizar hash
  const handleIgnoreModification = useCallback(async () => {
    await updateDocumentHash();
  }, [updateDocumentHash]);

  // Gap 8: Export audit report
  const handleExport = useCallback(async (format: ExportFormat) => {
    setShowExportMenu(false);
    setExportLoading(format);

    try {
      const storeState = usePlaybookStore.getState();
      const runId = storeState.playbookRunId || selectedPlaybook?.id;
      if (!runId) {
        toast.error('ID do playbook nao encontrado');
        setExportLoading(null);
        return;
      }

      await exportAuditReport({
        playbookRunId: runId,
        playbookName: selectedPlaybook?.name || 'Playbook',
        format,
        clauses: storeState.clauses,
        redlines: storeState.redlines,
        appliedRedlines: [...storeState.appliedRedlines],
        rejectedRedlines: [...storeState.rejectedRedlines],
        stats: storeState.stats,
        summary: storeState.summary,
      });

      toast.success(`Relatorio exportado em ${format.toUpperCase()}`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Erro ao exportar relatorio');
    } finally {
      setExportLoading(null);
    }
  }, [selectedPlaybook]);

  // ── Selecting playbook ─────────────────────────────────

  if (state === 'idle' || state === 'loading-playbooks') {
    return (
      <div className="h-full overflow-y-auto p-office-md">
        <ToastContainer toasts={toasts} onDismiss={dismissToast} />

        {/* Header com botao de historico */}
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-office-lg font-semibold">Run Playbook</h2>
          <HistoryButton onClick={() => setShowHistory(true)} />
        </div>

        <p className="mb-4 text-office-sm text-text-secondary">
          Selecione um playbook para analisar o documento e gerar redlines automaticos.
        </p>

        {error && (
          <p className="mb-3 rounded bg-red-50 p-2 text-office-sm text-status-error">
            {error}
          </p>
        )}

        {state === 'loading-playbooks' && (
          <div className="flex items-center gap-2 text-office-sm text-text-secondary">
            <Spinner size="sm" />
            Carregando...
          </div>
        )}

        {playbooks.length === 0 && state !== 'loading-playbooks' && !error && (
          <p className="text-office-sm text-text-tertiary">
            Nenhum playbook encontrado. Crie um no Iudex Web.
          </p>
        )}

        {/* Gap 12: Recomendacoes de playbooks */}
        {recommendations.length > 0 && (
          <div className="mb-4">
            <div className="mb-2 flex items-center gap-2">
              <span className="text-office-xs font-medium text-text-secondary">
                Recomendados para este documento
              </span>
              {documentType && (
                <span className="rounded-full bg-blue-100 px-2 py-0.5 text-office-xs text-blue-700">
                  {documentType}
                </span>
              )}
            </div>
            <div className="space-y-2">
              {recommendations.map((rec) => {
                const pb = playbooks.find((p) => p.id === rec.id);
                if (!pb) return null;
                return (
                  <button
                    key={rec.id}
                    onClick={() => runPlaybookAnalysis(pb)}
                    className="office-card w-full cursor-pointer border-brand/30 bg-blue-50/30 text-left hover:border-brand"
                  >
                    <div className="flex items-start justify-between">
                      <p className="text-office-base font-medium">{rec.name}</p>
                      <span className="shrink-0 rounded-full bg-brand/10 px-2 py-0.5 text-office-xs font-medium text-brand">
                        {Math.round(rec.relevance_score * 100)}% match
                      </span>
                    </div>
                    <p className="mt-1 text-office-xs text-text-secondary">
                      {rec.reason}
                    </p>
                  </button>
                );
              })}
            </div>
            <div className="mt-3 border-t border-gray-100 pt-3">
              <span className="text-office-xs font-medium text-text-secondary">
                Todos os playbooks
              </span>
            </div>
          </div>
        )}

        {recommendationLoading && (
          <div className="mb-4 flex items-center gap-2 text-office-xs text-text-tertiary">
            <Spinner size="xs" />
            Analisando documento...
          </div>
        )}

        {/* Lista completa de playbooks */}
        <div className="space-y-2">
          {playbooks.map((pb) => (
            <button
              key={pb.id}
              onClick={() => runPlaybookAnalysis(pb)}
              className="office-card w-full cursor-pointer text-left hover:border-brand"
            >
              <p className="text-office-base font-medium">{pb.name}</p>
              {pb.description && (
                <p className="mt-1 text-office-xs text-text-secondary">
                  {pb.description}
                </p>
              )}
              <div className="mt-1 flex gap-2 text-office-xs text-text-tertiary">
                <span>{pb.rules_count} regras</span>
                {pb.area && <span>| {pb.area}</span>}
              </div>
            </button>
          ))}
        </div>

        {/* Gap 11: Modal de historico */}
        <HistoryModal
          isOpen={showHistory}
          onClose={() => setShowHistory(false)}
          onRestore={() => setShowHistory(false)}
        />
      </div>
    );
  }

  // ── Analyzing ──────────────────────────────────────────

  if (state === 'analyzing') {
    return (
      <div className="flex h-full items-center justify-center p-office-md">
        <ToastContainer toasts={toasts} onDismiss={dismissToast} />
        <div className="text-center">
          <Spinner size="lg" className="mx-auto mb-3" />
          <p className="text-office-sm text-text-secondary">
            Analisando com &ldquo;{selectedPlaybook?.name}&rdquo;...
          </p>
          <p className="mt-1 text-office-xs text-text-tertiary">
            Gerando redlines e classificacoes
          </p>
        </div>
      </div>
    );
  }

  // ── Results ────────────────────────────────────────────

  const riskColor =
    stats.risk_score >= 70
      ? 'text-status-error'
      : stats.risk_score >= 40
        ? 'text-status-warning'
        : 'text-status-success';

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <ToastContainer toasts={toasts} onDismiss={dismissToast} />

      {/* Header */}
      <div className="border-b border-gray-200 p-office-md">
        <div className="flex items-center justify-between">
          <h2 className="text-office-base font-semibold">
            {selectedPlaybook?.name}
          </h2>
          <div className="flex items-center gap-2">
            {/* Gap 8: Export dropdown */}
            <div className="relative">
              <button
                onClick={() => setShowExportMenu(!showExportMenu)}
                disabled={exportLoading !== null}
                className="flex items-center gap-1 rounded border border-gray-300 bg-white px-2 py-1 text-office-xs font-medium text-text-primary hover:bg-surface-tertiary disabled:opacity-50"
              >
                {exportLoading ? (
                  <Spinner size="xs" />
                ) : (
                  <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                  </svg>
                )}
                Exportar
                <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </button>
              {showExportMenu && (
                <div className="absolute right-0 top-full z-10 mt-1 w-32 rounded-md border border-gray-200 bg-white py-1 shadow-lg">
                  <button
                    onClick={() => handleExport('json')}
                    className="flex w-full items-center gap-2 px-3 py-1.5 text-office-xs hover:bg-surface-tertiary"
                  >
                    <span className="w-8 font-medium text-blue-600">JSON</span>
                    <span className="text-text-tertiary">Dados brutos</span>
                  </button>
                  <button
                    onClick={() => handleExport('csv')}
                    className="flex w-full items-center gap-2 px-3 py-1.5 text-office-xs hover:bg-surface-tertiary"
                  >
                    <span className="w-8 font-medium text-green-600">CSV</span>
                    <span className="text-text-tertiary">Para Excel</span>
                  </button>
                  <button
                    onClick={() => handleExport('pdf')}
                    className="flex w-full items-center gap-2 px-3 py-1.5 text-office-xs hover:bg-surface-tertiary"
                  >
                    <span className="w-8 font-medium text-red-600">PDF</span>
                    <span className="text-text-tertiary">Relatorio</span>
                  </button>
                </div>
              )}
            </div>
            <button
              onClick={reset}
              className="text-office-xs text-brand hover:underline"
            >
              Voltar
            </button>
          </div>
        </div>

        {/* Gap 6: Document modification warning */}
        {documentModified && (
          <div className="mt-2 rounded-md border border-amber-300 bg-amber-50 p-2">
            <div className="flex items-start gap-2">
              <svg
                className="mt-0.5 h-4 w-4 flex-shrink-0 text-amber-600"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                />
              </svg>
              <div className="flex-1">
                <p className="text-office-xs font-medium text-amber-800">
                  Documento modificado
                </p>
                <p className="mt-0.5 text-office-xs text-amber-700">
                  O documento foi alterado desde a ultima analise. Os redlines podem nao corresponder ao texto atual.
                </p>
                <div className="mt-2 flex gap-2">
                  <button
                    onClick={handleReanalyze}
                    className="rounded bg-amber-600 px-2 py-1 text-office-xs font-medium text-white hover:bg-amber-700"
                  >
                    Reanalisar
                  </button>
                  <button
                    onClick={handleIgnoreModification}
                    className="rounded border border-amber-300 bg-white px-2 py-1 text-office-xs font-medium text-amber-700 hover:bg-amber-50"
                  >
                    Ignorar
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Risk score */}
        <div className="mt-2 flex items-center gap-3">
          <span className={`text-office-lg font-bold ${riskColor}`}>
            {stats.risk_score.toFixed(0)}
          </span>
          <span className="text-office-xs text-text-tertiary">Risk Score</span>
        </div>

        {/* Stats bar */}
        <div className="mt-2 flex flex-wrap gap-3 text-office-xs">
          <span className="text-status-success">
            {stats.compliant} conformes
          </span>
          <span className="text-status-warning">
            {stats.needs_review} revisao
          </span>
          <span className="text-status-error">
            {stats.non_compliant} nao conformes
          </span>
          <span className="text-text-tertiary">
            {stats.not_found} ausentes
          </span>
          <span className="font-medium text-brand">
            {stats.total_redlines} redlines
          </span>
        </div>

        {/* Review progress */}
        {redlines.length > 0 && (
          <div className="mt-2">
            <div className="flex items-center justify-between text-office-xs">
              <span className="text-text-secondary">
                Progresso: {progress.reviewed}/{progress.total} revisados
              </span>
              <span className="font-medium">{progress.percentage}%</span>
            </div>
            <div className="mt-1 h-1.5 w-full rounded-full bg-gray-200">
              <div
                className="h-1.5 rounded-full bg-brand transition-all"
                style={{ width: `${progress.percentage}%` }}
              />
            </div>
          </div>
        )}

        {summary && (
          <p className="mt-2 text-office-xs text-text-secondary line-clamp-3">
            {summary}
          </p>
        )}

        {/* Review tabs */}
        <div className="mt-3 flex gap-1.5">
          <TabChip
            label="Todos"
            active={reviewTab === 'all'}
            onClick={() => setReviewTab('all')}
          />
          <TabChip
            label="Revisados"
            active={reviewTab === 'reviewed'}
            onClick={() => setReviewTab('reviewed')}
          />
          <TabChip
            label="Pendentes"
            active={reviewTab === 'pending'}
            onClick={() => setReviewTab('pending')}
          />
        </div>

        {/* Classification filters */}
        <div className="mt-2 flex flex-wrap gap-1.5">
          <FilterChip
            label="Todos"
            active={filterClassification === 'all'}
            onClick={() => setFilterClassification('all')}
          />
          <FilterChip
            label="Nao conforme"
            active={filterClassification === 'non_compliant'}
            onClick={() => setFilterClassification('non_compliant')}
          />
          <FilterChip
            label="Revisao"
            active={filterClassification === 'needs_review'}
            onClick={() => setFilterClassification('needs_review')}
          />
          <FilterChip
            label="Ausente"
            active={filterClassification === 'not_found'}
            onClick={() => setFilterClassification('not_found')}
          />
          <FilterChip
            label="Conforme"
            active={filterClassification === 'compliant'}
            onClick={() => setFilterClassification('compliant')}
          />
          <span className="mx-1 border-l border-gray-200" />
          <FilterChip
            label="Critico"
            active={filterSeverity === 'critical'}
            onClick={() =>
              setFilterSeverity(filterSeverity === 'critical' ? 'all' : 'critical')
            }
          />
          <FilterChip
            label="Alto"
            active={filterSeverity === 'high'}
            onClick={() =>
              setFilterSeverity(filterSeverity === 'high' ? 'all' : 'high')
            }
          />
        </div>

        {/* Redlines-only toggle */}
        <div className="mt-2 flex items-center gap-2">
          <button
            onClick={() => setShowRedlinesOnly(!showRedlinesOnly)}
            className={`rounded px-2 py-0.5 text-office-xs font-medium transition-colors ${
              showRedlinesOnly
                ? 'bg-brand text-white'
                : 'bg-surface-tertiary text-text-secondary'
            }`}
          >
            Somente redlines
          </button>
        </div>

        {/* Batch actions */}
        {pending.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            <BatchButton
              label={`Apply All (${pending.length})`}
              variant="primary"
              loading={batchLoading === 'apply'}
              disabled={batchLoading !== null}
              onClick={handleBatchTrackedChanges}
            />
            <BatchButton
              label="Comentar tudo"
              loading={batchLoading === 'comment'}
              disabled={batchLoading !== null}
              onClick={handleBatchComments}
            />
            <BatchButton
              label="Destacar tudo"
              loading={batchLoading === 'highlight'}
              disabled={batchLoading !== null}
              onClick={handleHighlightAll}
            />
            <BatchButton
              label="Limpar destaques"
              loading={batchLoading === 'clear'}
              disabled={batchLoading !== null}
              onClick={handleClearHighlights}
            />
          </div>
        )}
      </div>

      {/* Clause list */}
      <div className="flex-1 overflow-y-auto p-office-md">
        {displayClauses.length === 0 && (
          <p className="text-office-sm text-text-tertiary">
            Nenhuma clausula encontrada com os filtros selecionados.
          </p>
        )}

        <div className="space-y-3">
          {displayClauses.map((clause) => {
            const redline = getRedlineForClause(clause.rule_id);
            const isApplied = redline
              ? appliedRedlines.has(redline.redline_id)
              : false;
            const isRejected = redline
              ? rejectedRedlines.has(redline.redline_id)
              : false;

            return (
              <ClauseCard
                key={clause.rule_id}
                clause={clause}
                redline={redline}
                isHighlighted={highlightedClauseId === clause.rule_id}
                isApplied={isApplied}
                isRejected={isRejected}
                onNavigate={handleNavigate}
                onApplyComment={handleApplyComment}
                onApplyHighlight={handleApplyHighlight}
                onApplyTrackedChange={handleApplyTrackedChange}
                onPreviewRedline={setPreviewClause}
                onReject={handleReject}
              />
            );
          })}
        </div>
      </div>

      {/* Redline preview modal */}
      {previewClause && (
        <RedlinePreview
          clause={previewClause}
          redline={getRedlineForClause(previewClause.rule_id)}
          onAccept={handleAcceptRedline}
          onReject={() => setPreviewClause(null)}
        />
      )}
    </div>
  );
}

function TabChip({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`rounded px-2.5 py-1 text-office-xs font-medium transition-colors ${
        active
          ? 'bg-brand text-white'
          : 'bg-surface-tertiary text-text-secondary hover:bg-gray-200'
      }`}
    >
      {label}
    </button>
  );
}

function FilterChip({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`rounded-full px-2.5 py-0.5 text-office-xs font-medium transition-colors ${
        active
          ? 'bg-brand text-white'
          : 'bg-surface-tertiary text-text-secondary hover:bg-gray-200'
      }`}
    >
      {label}
    </button>
  );
}

function BatchButton({
  label,
  onClick,
  variant = 'default',
  loading = false,
  disabled = false,
}: {
  label: string;
  onClick: () => void;
  variant?: 'default' | 'primary';
  loading?: boolean;
  disabled?: boolean;
}) {
  const styles =
    variant === 'primary'
      ? 'bg-brand text-white hover:bg-brand/90'
      : 'border border-gray-300 bg-white text-text-primary hover:bg-surface-tertiary';

  return (
    <button
      onClick={onClick}
      disabled={disabled || loading}
      className={`flex items-center gap-1.5 rounded px-2 py-1 text-office-xs font-medium disabled:opacity-50 ${styles}`}
    >
      {loading && <Spinner size="xs" />}
      {label}
    </button>
  );
}
