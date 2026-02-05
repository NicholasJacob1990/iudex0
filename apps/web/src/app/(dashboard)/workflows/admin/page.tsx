'use client';

import React, { useEffect, useState, useCallback } from 'react';
import {
  Shield,
  Loader2,
  CheckCircle2,
  XCircle,
  Clock,
  FileText,
  BarChart3,
  Filter,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { apiClient } from '@/lib/api-client';
import { toast } from 'sonner';
import { useRouter } from 'next/navigation';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface DashboardWorkflow {
  id: string;
  name: string;
  status: string;
  category: string | null;
  run_count: number;
  created_by: string;
  updated_at: string | null;
}

interface DashboardData {
  workflows: DashboardWorkflow[];
  total: number;
  by_status: Record<string, number>;
}

interface PendingWorkflow {
  id: string;
  name: string;
  submitted_by: string | null;
  submitted_at: string | null;
  description: string | null;
}

interface ApprovalQueueData {
  pending: PendingWorkflow[];
  count: number;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const STATUS_LABELS: Record<string, string> = {
  draft: 'Rascunho',
  pending_approval: 'Pendente',
  approved: 'Aprovado',
  published: 'Publicado',
  rejected: 'Rejeitado',
  archived: 'Arquivado',
};

const STATUS_COLORS: Record<string, string> = {
  draft: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300',
  pending_approval: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400',
  approved: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
  published: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
  rejected: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
  archived: 'bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400',
};

const CATEGORY_LABELS: Record<string, string> = {
  general: 'Geral',
  transactional: 'Transacional',
  litigation: 'Contencioso',
  financial: 'Financeiro',
  administrative: 'Administrativo',
  labor: 'Trabalhista',
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function WorkflowAdminPage() {
  const router = useRouter();
  const [activeTab, setActiveTab] = useState<'dashboard' | 'approval'>('dashboard');
  const [loading, setLoading] = useState(true);
  const [dashboard, setDashboard] = useState<DashboardData | null>(null);
  const [queue, setQueue] = useState<ApprovalQueueData | null>(null);
  const [statusFilter, setStatusFilter] = useState<string>('');

  const fetchDashboard = useCallback(async () => {
    try {
      const data = await apiClient.getAdminDashboard();
      setDashboard(data);
    } catch {
      toast.error('Erro ao carregar dashboard');
    }
  }, []);

  const fetchQueue = useCallback(async () => {
    try {
      const data = await apiClient.getApprovalQueue();
      setQueue(data);
    } catch {
      toast.error('Erro ao carregar fila de aprovacao');
    }
  }, []);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      await Promise.all([fetchDashboard(), fetchQueue()]);
      setLoading(false);
    };
    load();
  }, [fetchDashboard, fetchQueue]);

  const handleApprove = async (workflowId: string) => {
    try {
      await apiClient.approveWorkflow(workflowId, true);
      toast.success('Workflow aprovado');
      await Promise.all([fetchDashboard(), fetchQueue()]);
    } catch {
      toast.error('Erro ao aprovar workflow');
    }
  };

  const handleReject = async (workflowId: string) => {
    const reason = window.prompt('Motivo da rejeicao (opcional):');
    try {
      await apiClient.approveWorkflow(workflowId, false, reason || undefined);
      toast.success('Workflow rejeitado');
      await Promise.all([fetchDashboard(), fetchQueue()]);
    } catch {
      toast.error('Erro ao rejeitar workflow');
    }
  };

  const filteredWorkflows = dashboard?.workflows.filter((w) =>
    statusFilter ? w.status === statusFilter : true
  ) ?? [];

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-8 w-8 text-indigo-500 animate-spin" />
      </div>
    );
  }

  const byStatus = dashboard?.by_status ?? {};

  return (
    <div className="max-w-6xl mx-auto px-6 py-8">
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <Shield className="h-6 w-6 text-indigo-500" />
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">
            Painel Administrativo de Workflows
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-0.5">
            Monitore e gerencie todos os workflows da organizacao
          </p>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <StatCard
          label="Total"
          value={dashboard?.total ?? 0}
          icon={<BarChart3 className="h-5 w-5 text-indigo-500" />}
        />
        <StatCard
          label="Publicados"
          value={byStatus['published'] ?? 0}
          icon={<CheckCircle2 className="h-5 w-5 text-green-500" />}
        />
        <StatCard
          label="Pendentes"
          value={byStatus['pending_approval'] ?? 0}
          icon={<Clock className="h-5 w-5 text-amber-500" />}
        />
        <StatCard
          label="Rascunho"
          value={byStatus['draft'] ?? 0}
          icon={<FileText className="h-5 w-5 text-slate-400" />}
        />
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-slate-200 dark:border-slate-700 mb-6">
        <button
          onClick={() => setActiveTab('dashboard')}
          className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
            activeTab === 'dashboard'
              ? 'border-indigo-500 text-indigo-600 dark:text-indigo-400'
              : 'border-transparent text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'
          }`}
        >
          Todos os Workflows
        </button>
        <button
          onClick={() => setActiveTab('approval')}
          className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
            activeTab === 'approval'
              ? 'border-indigo-500 text-indigo-600 dark:text-indigo-400'
              : 'border-transparent text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'
          }`}
        >
          Fila de Aprovacao
          {(queue?.count ?? 0) > 0 && (
            <span className="ml-2 inline-flex items-center justify-center h-5 w-5 rounded-full bg-amber-500 text-white text-[10px] font-bold">
              {queue?.count}
            </span>
          )}
        </button>
      </div>

      {/* Dashboard Tab */}
      {activeTab === 'dashboard' && (
        <>
          {/* Filter */}
          <div className="flex items-center gap-3 mb-4">
            <Filter className="h-4 w-4 text-slate-400" />
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="border rounded-md px-3 py-1.5 text-sm bg-white dark:bg-slate-900 border-slate-200 dark:border-slate-700"
            >
              <option value="">Todos os status</option>
              {Object.entries(STATUS_LABELS).map(([key, label]) => (
                <option key={key} value={key}>{label}</option>
              ))}
            </select>
            <span className="text-xs text-slate-400">
              {filteredWorkflows.length} workflow(s)
            </span>
          </div>

          {/* Table */}
          <div className="border rounded-lg overflow-hidden border-slate-200 dark:border-slate-700">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 dark:bg-slate-800/50">
                <tr>
                  <th className="text-left px-4 py-3 font-medium text-slate-600 dark:text-slate-300">Nome</th>
                  <th className="text-left px-4 py-3 font-medium text-slate-600 dark:text-slate-300">Status</th>
                  <th className="text-left px-4 py-3 font-medium text-slate-600 dark:text-slate-300 hidden md:table-cell">Categoria</th>
                  <th className="text-right px-4 py-3 font-medium text-slate-600 dark:text-slate-300 hidden sm:table-cell">Runs</th>
                  <th className="text-right px-4 py-3 font-medium text-slate-600 dark:text-slate-300 hidden lg:table-cell">Ultima Atualizacao</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {filteredWorkflows.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="text-center py-8 text-slate-400">
                      Nenhum workflow encontrado
                    </td>
                  </tr>
                ) : (
                  filteredWorkflows.map((wf) => (
                    <tr
                      key={wf.id}
                      className="hover:bg-slate-50 dark:hover:bg-slate-800/30 cursor-pointer transition-colors"
                      onClick={() => router.push(`/workflows/${wf.id}`)}
                    >
                      <td className="px-4 py-3 font-medium text-slate-800 dark:text-slate-200 truncate max-w-[200px]">
                        {wf.name}
                      </td>
                      <td className="px-4 py-3">
                        <span className={`inline-block text-[11px] px-2 py-0.5 rounded-full font-medium ${STATUS_COLORS[wf.status] ?? STATUS_COLORS['draft']}`}>
                          {STATUS_LABELS[wf.status] ?? wf.status}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-slate-500 dark:text-slate-400 hidden md:table-cell">
                        {wf.category ? (CATEGORY_LABELS[wf.category] ?? wf.category) : '-'}
                      </td>
                      <td className="px-4 py-3 text-right tabular-nums text-slate-600 dark:text-slate-300 hidden sm:table-cell">
                        {wf.run_count}
                      </td>
                      <td className="px-4 py-3 text-right text-slate-400 text-xs hidden lg:table-cell">
                        {wf.updated_at
                          ? new Date(wf.updated_at).toLocaleDateString('pt-BR', {
                              day: '2-digit',
                              month: '2-digit',
                              year: 'numeric',
                              hour: '2-digit',
                              minute: '2-digit',
                            })
                          : '-'}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* Approval Queue Tab */}
      {activeTab === 'approval' && (
        <>
          {(queue?.pending.length ?? 0) === 0 ? (
            <div className="text-center py-16">
              <CheckCircle2 className="h-12 w-12 text-green-300 mx-auto mb-4" />
              <p className="text-slate-500 dark:text-slate-400">
                Nenhum workflow pendente de aprovacao
              </p>
            </div>
          ) : (
            <div className="grid gap-4">
              {queue?.pending.map((wf) => (
                <div
                  key={wf.id}
                  className="flex items-start gap-4 p-4 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900"
                >
                  <div className="h-10 w-10 rounded-lg bg-amber-100 dark:bg-amber-500/20 flex items-center justify-center shrink-0">
                    <Clock className="h-5 w-5 text-amber-600 dark:text-amber-400" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <h3 className="font-semibold text-slate-800 dark:text-slate-200">
                      {wf.name}
                    </h3>
                    {wf.description && (
                      <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5 line-clamp-2">
                        {wf.description}
                      </p>
                    )}
                    <div className="flex items-center gap-3 mt-2 text-[11px] text-slate-400">
                      {wf.submitted_at && (
                        <span>
                          Enviado em{' '}
                          {new Date(wf.submitted_at).toLocaleDateString('pt-BR', {
                            day: '2-digit',
                            month: '2-digit',
                            year: 'numeric',
                          })}
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <Button
                      size="sm"
                      variant="outline"
                      className="gap-1 h-8 text-xs text-red-600 border-red-200 hover:bg-red-50 dark:border-red-800 dark:hover:bg-red-950"
                      onClick={() => handleReject(wf.id)}
                    >
                      <XCircle className="h-3.5 w-3.5" />
                      Rejeitar
                    </Button>
                    <Button
                      size="sm"
                      className="gap-1 h-8 text-xs bg-green-600 hover:bg-green-500 text-white"
                      onClick={() => handleApprove(wf.id)}
                    >
                      <CheckCircle2 className="h-3.5 w-3.5" />
                      Aprovar
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Stat Card
// ---------------------------------------------------------------------------

function StatCard({
  label,
  value,
  icon,
}: {
  label: string;
  value: number;
  icon: React.ReactNode;
}) {
  return (
    <div className="flex items-center gap-3 p-4 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900">
      <div className="shrink-0">{icon}</div>
      <div>
        <p className="text-2xl font-bold text-slate-900 dark:text-white">{value}</p>
        <p className="text-xs text-slate-500 dark:text-slate-400">{label}</p>
      </div>
    </div>
  );
}
