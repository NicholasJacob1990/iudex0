'use client';

import React, { useCallback, useEffect, useState } from 'react';
import {
  ClipboardList,
  Loader2,
  ChevronDown,
  ChevronUp,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Clock,
  Zap,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { apiClient } from '@/lib/api-client';

interface AuditEntry {
  id: string;
  user_name: string;
  user_email: string;
  started_at: string;
  completed_at: string | null;
  status: 'completed' | 'error' | 'running' | 'pending' | 'paused_hil' | 'cancelled';
  input_summary: string;
  output_summary: string;
  duration_ms: number | null;
  error_message: string | null;
  trigger_type: string;
}

interface AuditResponse {
  items: AuditEntry[];
  total: number;
  page: number;
  limit: number;
  pages: number;
}

interface AuditTrailProps {
  workflowId: string;
}

export function AuditTrail({ workflowId }: AuditTrailProps) {
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [expandedEntry, setExpandedEntry] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [hasMore, setHasMore] = useState(false);

  const fetchAudit = useCallback(async (p: number = 1) => {
    setLoading(true);
    try {
      const res = await apiClient.fetchWithAuth(
        `/workflows/${workflowId}/audit?page=${p}&limit=10`
      );
      const data: AuditResponse = await res.json();
      const items = data.items || [];
      if (p === 1) {
        setEntries(items);
      } else {
        setEntries((prev) => [...prev, ...items]);
      }
      setTotal(data.total || 0);
      setHasMore(p < (data.pages || 1));
      setPage(p);
    } catch {
      console.error('Failed to load audit trail');
    } finally {
      setLoading(false);
    }
  }, [workflowId]);

  useEffect(() => {
    if (expanded && entries.length === 0) {
      fetchAudit();
    }
  }, [expanded, entries.length, fetchAudit]);

  const statusIcon = (s: string) => {
    if (s === 'completed')
      return <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500 shrink-0" />;
    if (s === 'error')
      return <XCircle className="h-3.5 w-3.5 text-red-500 shrink-0" />;
    if (s === 'running')
      return <Loader2 className="h-3.5 w-3.5 text-blue-500 animate-spin shrink-0" />;
    if (s === 'paused_hil')
      return <Clock className="h-3.5 w-3.5 text-amber-500 shrink-0" />;
    if (s === 'cancelled')
      return <XCircle className="h-3.5 w-3.5 text-slate-400 shrink-0" />;
    return <Clock className="h-3.5 w-3.5 text-slate-400 shrink-0" />;
  };

  const statusLabel = (s: string) => {
    const labels: Record<string, string> = {
      completed: 'Concluido',
      error: 'Erro',
      running: 'Executando',
      pending: 'Pendente',
      paused_hil: 'Aguardando revisao',
      cancelled: 'Cancelado',
    };
    return labels[s] || s;
  };

  const triggerLabel = (t: string) => {
    const labels: Record<string, string> = {
      manual: 'Manual',
      test: 'Teste',
      scheduled: 'Agendado',
      webhook: 'Webhook',
    };
    return labels[t] || t;
  };

  const formatDuration = (ms: number | null) => {
    if (!ms) return '-';
    if (ms < 1000) return `${ms}ms`;
    if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
    return `${Math.round(ms / 60000)}min`;
  };

  return (
    <div className="border rounded-lg bg-white dark:bg-slate-900">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 w-full px-4 py-2.5 text-left hover:bg-slate-50 dark:hover:bg-slate-800 rounded-lg transition-colors"
      >
        <ClipboardList className="h-4 w-4 text-slate-500" />
        <span className="text-sm font-medium text-slate-700 dark:text-slate-300 flex-1">
          Historico de Execucoes
          {total > 0 && (
            <span className="ml-2 text-xs font-normal text-slate-400">
              ({total})
            </span>
          )}
        </span>
        {loading ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin text-slate-400" />
        ) : expanded ? (
          <ChevronUp className="h-3.5 w-3.5 text-slate-400" />
        ) : (
          <ChevronDown className="h-3.5 w-3.5 text-slate-400" />
        )}
      </button>

      {expanded && (
        <div className="border-t border-slate-200 dark:border-slate-700 px-4 py-2 space-y-1 max-h-80 overflow-y-auto">
          {entries.length === 0 && !loading && (
            <p className="text-xs text-slate-400 py-3 text-center">
              Nenhuma execucao registrada
            </p>
          )}
          {entries.map((entry) => (
            <div
              key={entry.id}
              className="border-b border-slate-100 dark:border-slate-800 last:border-0"
            >
              <button
                onClick={() =>
                  setExpandedEntry(expandedEntry === entry.id ? null : entry.id)
                }
                className="w-full flex items-center gap-2 py-2 text-left"
              >
                {statusIcon(entry.status)}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-medium text-slate-700 dark:text-slate-300 truncate">
                      {entry.user_name}
                    </span>
                    <span className="text-[10px] text-slate-400 shrink-0">
                      {new Date(entry.started_at).toLocaleString('pt-BR', {
                        day: '2-digit',
                        month: '2-digit',
                        year: '2-digit',
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 mt-0.5">
                    <span className="text-[10px] text-slate-400">
                      {statusLabel(entry.status)}
                    </span>
                    {entry.trigger_type && entry.trigger_type !== 'manual' && (
                      <span className="text-[10px] text-slate-400 flex items-center gap-0.5">
                        <Zap className="h-2.5 w-2.5" />
                        {triggerLabel(entry.trigger_type)}
                      </span>
                    )}
                  </div>
                </div>
                <span className="text-[10px] text-slate-400 shrink-0">
                  {formatDuration(entry.duration_ms)}
                </span>
              </button>

              {expandedEntry === entry.id && (
                <div className="pl-6 pb-2 space-y-1.5">
                  <div className="text-[10px] text-slate-400">
                    {entry.user_email}
                  </div>

                  {entry.input_summary && (
                    <div>
                      <p className="text-[10px] text-slate-500 font-medium">
                        Input:
                      </p>
                      <p className="text-xs text-slate-600 dark:text-slate-400 bg-slate-50 dark:bg-slate-800 rounded px-2 py-1 break-words">
                        {entry.input_summary}
                      </p>
                    </div>
                  )}

                  {entry.output_summary && (
                    <div>
                      <p className="text-[10px] text-slate-500 font-medium">
                        Output:
                      </p>
                      <p className="text-xs text-slate-600 dark:text-slate-400 bg-slate-50 dark:bg-slate-800 rounded px-2 py-1 break-words">
                        {entry.output_summary}
                      </p>
                    </div>
                  )}

                  {entry.error_message && (
                    <div className="flex items-start gap-1.5 bg-red-50 dark:bg-red-950 rounded px-2 py-1">
                      <AlertTriangle className="h-3 w-3 text-red-500 mt-0.5 shrink-0" />
                      <p className="text-xs text-red-600 dark:text-red-400 break-words">
                        {entry.error_message}
                      </p>
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}

          {loading && entries.length > 0 && (
            <div className="flex justify-center py-2">
              <Loader2 className="h-4 w-4 animate-spin text-slate-400" />
            </div>
          )}

          {hasMore && !loading && (
            <Button
              variant="ghost"
              size="sm"
              className="w-full text-xs"
              onClick={() => fetchAudit(page + 1)}
            >
              Carregar mais
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
