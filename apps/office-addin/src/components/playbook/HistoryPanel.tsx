/**
 * Painel de historico de analises de playbook.
 *
 * Gap 11: Permite visualizar e restaurar analises anteriores
 * armazenadas no cache do servidor.
 */

import { useState, useEffect, useCallback } from 'react';
import { usePlaybookStore } from '@/stores/playbook-store';

// ── Types ──────────────────────────────────────────────────────

export interface PlaybookRunHistoryItem {
  id: string;
  playbook_id: string;
  playbook_name: string;
  document_name?: string;
  created_at: string;
  stats: {
    total_rules: number;
    compliant: number;
    needs_review: number;
    non_compliant: number;
    not_found: number;
    risk_score: number;
    total_redlines: number;
  };
}

interface HistoryPanelProps {
  /** Callback quando uma analise e selecionada para restaurar */
  onRestore?: (runId: string) => void;
  /** Se o painel deve aparecer inline ou como modal */
  variant?: 'inline' | 'modal';
  /** Limite de itens a exibir */
  limit?: number;
}

// ── Component ──────────────────────────────────────────────────

export function HistoryPanel({
  onRestore,
  variant = 'inline',
  limit = 10,
}: HistoryPanelProps) {
  const [history, setHistory] = useState<PlaybookRunHistoryItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [restoring, setRestoring] = useState<string | null>(null);

  // Buscar historico ao montar
  useEffect(() => {
    fetchHistory();
  }, [limit]);

  const fetchHistory = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      const items = await getPlaybookRunHistory(limit);
      setHistory(items);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Erro ao carregar historico'
      );
    } finally {
      setIsLoading(false);
    }
  }, [limit]);

  const handleRestore = useCallback(
    async (runId: string) => {
      setRestoring(runId);

      try {
        // Restaurar analise do cache
        const result = await restorePlaybookRun(runId);

        if (result.success) {
          // Atualizar store com dados restaurados
          usePlaybookStore.setState({
            state: 'results',
            clauses: result.clauses,
            redlines: result.redlines,
            summary: result.summary,
            stats: result.stats,
            selectedPlaybook: {
              id: result.playbook_id,
              name: result.playbook_name,
              rules_count: result.stats.total_rules,
              scope: 'personal',
              party_perspective: 'neutro',
            },
            appliedRedlines: new Set(),
            rejectedRedlines: new Set(),
            reviewedRedlines: new Set(),
          });

          onRestore?.(runId);
        } else {
          setError(result.error || 'Erro ao restaurar analise');
        }
      } catch (err) {
        setError(
          err instanceof Error ? err.message : 'Erro ao restaurar analise'
        );
      } finally {
        setRestoring(null);
      }
    },
    [onRestore]
  );

  // ── Render ────────────────────────────────────────────────────

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-8">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-brand border-t-transparent" />
        <span className="ml-2 text-office-sm text-text-secondary">
          Carregando historico...
        </span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded bg-red-50 p-3">
        <p className="text-office-sm text-status-error">{error}</p>
        <button
          onClick={fetchHistory}
          className="mt-2 text-office-xs text-brand hover:underline"
        >
          Tentar novamente
        </button>
      </div>
    );
  }

  if (history.length === 0) {
    return (
      <div className="py-8 text-center">
        <p className="text-office-sm text-text-tertiary">
          Nenhuma analise recente encontrada.
        </p>
        <p className="mt-1 text-office-xs text-text-tertiary">
          Execute um playbook para ver o historico aqui.
        </p>
      </div>
    );
  }

  return (
    <div className={variant === 'modal' ? 'max-h-[400px] overflow-y-auto' : ''}>
      <div className="space-y-2">
        {history.map((item) => (
          <HistoryCard
            key={item.id}
            item={item}
            onRestore={handleRestore}
            isRestoring={restoring === item.id}
          />
        ))}
      </div>
    </div>
  );
}

// ── HistoryCard ────────────────────────────────────────────────

interface HistoryCardProps {
  item: PlaybookRunHistoryItem;
  onRestore: (runId: string) => void;
  isRestoring: boolean;
}

function HistoryCard({ item, onRestore, isRestoring }: HistoryCardProps) {
  const riskColor =
    item.stats.risk_score >= 70
      ? 'text-status-error'
      : item.stats.risk_score >= 40
        ? 'text-status-warning'
        : 'text-status-success';

  const formattedDate = formatRelativeDate(item.created_at);

  return (
    <div className="office-card">
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <h4 className="text-office-sm font-medium text-text-primary">
            {item.playbook_name}
          </h4>
          {item.document_name && (
            <p className="mt-0.5 text-office-xs text-text-tertiary">
              {item.document_name}
            </p>
          )}
        </div>
        <span className={`text-office-base font-bold ${riskColor}`}>
          {item.stats.risk_score.toFixed(0)}
        </span>
      </div>

      {/* Stats */}
      <div className="mt-2 flex flex-wrap gap-2 text-office-xs">
        <span className="text-status-success">
          {item.stats.compliant} conformes
        </span>
        <span className="text-status-warning">
          {item.stats.needs_review} revisao
        </span>
        <span className="text-status-error">
          {item.stats.non_compliant} nao conformes
        </span>
        {item.stats.total_redlines > 0 && (
          <span className="font-medium text-brand">
            {item.stats.total_redlines} redlines
          </span>
        )}
      </div>

      {/* Footer */}
      <div className="mt-2 flex items-center justify-between">
        <span className="text-office-xs text-text-tertiary">{formattedDate}</span>
        <button
          onClick={() => onRestore(item.id)}
          disabled={isRestoring}
          className="text-office-xs font-medium text-brand hover:underline disabled:opacity-50"
        >
          {isRestoring ? 'Restaurando...' : 'Restaurar'}
        </button>
      </div>
    </div>
  );
}

// ── API Functions ──────────────────────────────────────────────

import { api } from '@/api/client';

interface PlaybookRunHistoryResponse {
  items: PlaybookRunHistoryItem[];
  total: number;
}

/**
 * Busca historico de execucoes de playbook do usuario.
 */
async function getPlaybookRunHistory(
  limit: number = 10
): Promise<PlaybookRunHistoryItem[]> {
  const { data } = await api.get<PlaybookRunHistoryResponse>(
    '/word-addin/user/playbook-runs',
    { params: { limit } }
  );
  return data.items;
}

interface RestorePlaybookRunResponse {
  success: boolean;
  playbook_run_id: string;
  playbook_id: string;
  playbook_name: string;
  redlines: Array<{
    redline_id: string;
    rule_id: string;
    rule_name: string;
    clause_type: string;
    classification: string;
    severity: string;
    original_text: string;
    suggested_text: string;
    explanation: string;
    comment?: string;
    confidence: number;
    applied: boolean;
    rejected: boolean;
    reviewed: boolean;
    created_at: string;
    ooxml?: string;
  }>;
  clauses: Array<{
    rule_id: string;
    rule_name: string;
    clause_type: string;
    found_in_contract: boolean;
    original_text?: string;
    classification: string;
    severity: string;
    explanation: string;
    suggested_redline?: string;
    comment?: string;
    confidence: number;
    redline_id?: string;
  }>;
  stats: {
    total_rules: number;
    compliant: number;
    needs_review: number;
    non_compliant: number;
    not_found: number;
    risk_score: number;
    total_redlines: number;
  };
  summary: string;
  expires_at?: string;
  error?: string;
}

/**
 * Restaura uma execucao de playbook do cache.
 */
async function restorePlaybookRun(
  runId: string
): Promise<RestorePlaybookRunResponse> {
  const { data } = await api.get<RestorePlaybookRunResponse>(
    `/word-addin/playbook/run/${runId}/restore`
  );
  return data;
}

// ── Helpers ────────────────────────────────────────────────────

/**
 * Formata data relativa (ex: "ha 2 horas", "ontem").
 */
function formatRelativeDate(isoDate: string): string {
  const date = new Date(isoDate);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 1) return 'agora';
  if (diffMins < 60) return `ha ${diffMins} min`;
  if (diffHours < 24) return `ha ${diffHours}h`;
  if (diffDays === 1) return 'ontem';
  if (diffDays < 7) return `ha ${diffDays} dias`;

  return date.toLocaleDateString('pt-BR', {
    day: '2-digit',
    month: '2-digit',
    year: '2-digit',
  });
}

// ── HistoryButton ──────────────────────────────────────────────

interface HistoryButtonProps {
  onClick: () => void;
}

/**
 * Botao para abrir o painel de historico.
 */
export function HistoryButton({ onClick }: HistoryButtonProps) {
  return (
    <button
      onClick={onClick}
      className="flex items-center gap-1.5 rounded px-2 py-1 text-office-xs text-text-secondary hover:bg-surface-tertiary"
      title="Ver historico de analises"
    >
      <svg
        xmlns="http://www.w3.org/2000/svg"
        width="14"
        height="14"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <circle cx="12" cy="12" r="10" />
        <polyline points="12 6 12 12 16 14" />
      </svg>
      Historico
    </button>
  );
}

// ── HistoryModal ───────────────────────────────────────────────

interface HistoryModalProps {
  isOpen: boolean;
  onClose: () => void;
  onRestore?: (runId: string) => void;
}

export function HistoryModal({ isOpen, onClose, onRestore }: HistoryModalProps) {
  const handleRestore = useCallback(
    (runId: string) => {
      onRestore?.(runId);
      onClose();
    },
    [onRestore, onClose]
  );

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="mx-4 w-full max-w-md rounded-lg bg-white p-4 shadow-xl">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-office-base font-semibold">
            Historico de Analises
          </h3>
          <button
            onClick={onClose}
            className="rounded p-1 text-text-tertiary hover:bg-surface-tertiary"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        <HistoryPanel variant="modal" onRestore={handleRestore} />
      </div>
    </div>
  );
}
