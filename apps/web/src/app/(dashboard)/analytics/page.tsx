'use client';

import React, { useEffect, useState } from 'react';
import {
  BarChart3,
  TrendingUp,
  FileText,
  Workflow,
  Database,
  Loader2,
  Search,
  AlertCircle,
} from 'lucide-react';
import { apiClient } from '@/lib/api-client';

interface CorpusOverview {
  total_documents: number;
  total_searches: number;
  collections: { name: string; count: number; label: string }[];
  storage_mb: number;
}

interface TrendingTopic {
  query: string;
  count: number;
  trend: 'up' | 'down' | 'stable';
}

interface WorkflowStats {
  total: number;
  active: number;
  total_runs: number;
  top_workflows: { id: string; name: string; run_count: number }[];
  success_rate: number | null;
}

interface UsagePoint {
  date: string;
  searches: number;
  documents_added: number;
}

export default function AnalyticsPage() {
  const [overview, setOverview] = useState<CorpusOverview | null>(null);
  const [trending, setTrending] = useState<TrendingTopic[]>([]);
  const [workflowStats, setWorkflowStats] = useState<WorkflowStats | null>(null);
  const [usage, setUsage] = useState<UsagePoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      try {
        const [ovRes, trRes, wfRes, usRes] = await Promise.all([
          apiClient.fetchWithAuth('/analytics/corpus/overview'),
          apiClient.fetchWithAuth('/analytics/corpus/trending'),
          apiClient.fetchWithAuth('/analytics/workflows/stats'),
          apiClient.fetchWithAuth('/analytics/corpus/usage-over-time'),
        ]);

        if (!ovRes.ok || !trRes.ok || !wfRes.ok || !usRes.ok) {
          throw new Error('Falha ao carregar dados de analytics');
        }

        const [ov, tr, wf, us] = await Promise.all([
          ovRes.json(),
          trRes.json(),
          wfRes.json(),
          usRes.json(),
        ]);

        setOverview(ov);
        setTrending(tr);
        setWorkflowStats(wf);
        setUsage(us);
      } catch (err) {
        console.error('Failed to load analytics', err);
        setError('Falha ao carregar dados de analytics. Verifique a conexao com a API.');
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <Loader2 className="h-8 w-8 text-indigo-500 animate-spin" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center py-24 gap-3">
        <AlertCircle className="h-8 w-8 text-red-400" />
        <p className="text-sm text-slate-500 dark:text-slate-400">{error}</p>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto px-6 py-8">
      <div className="flex items-center gap-3 mb-8">
        <BarChart3 className="h-6 w-6 text-indigo-500" />
        <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">
          Analytics
        </h1>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <StatCard
          icon={FileText}
          label="Documentos"
          value={overview?.total_documents || 0}
          color="blue"
        />
        <StatCard
          icon={Search}
          label="Buscas (30d)"
          value={overview?.total_searches || 0}
          color="violet"
        />
        <StatCard
          icon={Workflow}
          label="Workflows"
          value={workflowStats?.total || 0}
          color="emerald"
        />
        <StatCard
          icon={Database}
          label="Armazenamento"
          value={`${overview?.storage_mb || 0} MB`}
          color="amber"
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        {/* Collections breakdown */}
        <div className="border border-slate-200 dark:border-slate-700 rounded-xl p-5 bg-white dark:bg-slate-900">
          <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-4 flex items-center gap-2">
            <Database className="h-4 w-4 text-indigo-500" />
            Corpus por Colecao
          </h2>
          <div className="space-y-3">
            {(overview?.collections || []).map((col) => {
              const maxCount = Math.max(
                ...(overview?.collections || []).map((c) => c.count),
                1
              );
              return (
                <div key={col.name}>
                  <div className="flex justify-between text-xs mb-1">
                    <span className="text-slate-600 dark:text-slate-400">
                      {col.label}
                    </span>
                    <span className="text-slate-500">
                      {col.count.toLocaleString()}
                    </span>
                  </div>
                  <div className="h-2 bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-indigo-500 rounded-full transition-all duration-500"
                      style={{
                        width: `${Math.min(100, (col.count / maxCount) * 100)}%`,
                      }}
                    />
                  </div>
                </div>
              );
            })}
            {(overview?.collections || []).length === 0 && (
              <p className="text-xs text-slate-400 py-4 text-center">
                Nenhuma colecao encontrada
              </p>
            )}
          </div>
        </div>

        {/* Trending topics */}
        <div className="border border-slate-200 dark:border-slate-700 rounded-xl p-5 bg-white dark:bg-slate-900">
          <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-4 flex items-center gap-2">
            <TrendingUp className="h-4 w-4 text-violet-500" />
            Topicos em Alta (30 dias)
          </h2>
          <div className="space-y-2">
            {trending.length === 0 ? (
              <p className="text-xs text-slate-400 py-4 text-center">
                Nenhuma busca registrada
              </p>
            ) : (
              trending.map((t, i) => (
                <div key={i} className="flex items-center gap-3 py-1.5">
                  <span className="text-xs text-slate-400 w-5 text-right">
                    {i + 1}.
                  </span>
                  <span className="text-sm text-slate-700 dark:text-slate-300 flex-1 truncate">
                    {t.query}
                  </span>
                  <span className="text-xs text-slate-500 bg-slate-100 dark:bg-slate-800 px-2 py-0.5 rounded">
                    {t.count}x
                  </span>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* Workflow Stats */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        {/* Top Workflows */}
        <div className="border border-slate-200 dark:border-slate-700 rounded-xl p-5 bg-white dark:bg-slate-900">
          <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-4 flex items-center gap-2">
            <Workflow className="h-4 w-4 text-emerald-500" />
            Workflows Mais Usados
          </h2>
          <div className="space-y-2">
            {(workflowStats?.top_workflows || []).length === 0 ? (
              <p className="text-xs text-slate-400 py-4 text-center">
                Nenhum workflow encontrado
              </p>
            ) : (
              (workflowStats?.top_workflows || []).map((wf, i) => (
                <div
                  key={wf.id}
                  className="flex items-center gap-3 py-2 border-b border-slate-100 dark:border-slate-800 last:border-0"
                >
                  <span className="text-xs text-slate-400 w-5 text-right">
                    {i + 1}.
                  </span>
                  <span className="text-sm text-slate-700 dark:text-slate-300 flex-1 truncate">
                    {wf.name}
                  </span>
                  <span className="text-xs font-medium text-emerald-600 bg-emerald-50 dark:bg-emerald-950 px-2 py-0.5 rounded">
                    {wf.run_count} execucoes
                  </span>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Workflow Summary */}
        <div className="border border-slate-200 dark:border-slate-700 rounded-xl p-5 bg-white dark:bg-slate-900">
          <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-4 flex items-center gap-2">
            <BarChart3 className="h-4 w-4 text-indigo-500" />
            Resumo de Workflows
          </h2>
          <div className="grid grid-cols-2 gap-4">
            <div className="p-3 bg-slate-50 dark:bg-slate-800 rounded-lg">
              <p className="text-2xl font-bold text-slate-900 dark:text-slate-100">
                {workflowStats?.total || 0}
              </p>
              <p className="text-xs text-slate-500">Total</p>
            </div>
            <div className="p-3 bg-slate-50 dark:bg-slate-800 rounded-lg">
              <p className="text-2xl font-bold text-emerald-600 dark:text-emerald-400">
                {workflowStats?.active || 0}
              </p>
              <p className="text-xs text-slate-500">Ativos</p>
            </div>
            <div className="p-3 bg-slate-50 dark:bg-slate-800 rounded-lg">
              <p className="text-2xl font-bold text-slate-900 dark:text-slate-100">
                {workflowStats?.total_runs || 0}
              </p>
              <p className="text-xs text-slate-500">Execucoes</p>
            </div>
            <div className="p-3 bg-slate-50 dark:bg-slate-800 rounded-lg">
              <p className="text-2xl font-bold text-indigo-600 dark:text-indigo-400">
                {workflowStats?.success_rate != null
                  ? `${workflowStats.success_rate}%`
                  : '--'}
              </p>
              <p className="text-xs text-slate-500">Taxa de Sucesso</p>
            </div>
          </div>
        </div>
      </div>

      {/* Usage over time */}
      {usage.length > 0 && (
        <div className="border border-slate-200 dark:border-slate-700 rounded-xl p-5 bg-white dark:bg-slate-900">
          <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-4">
            Uso nos Ultimos 30 Dias
          </h2>
          <div className="flex items-end gap-[2px] h-32">
            {usage.map((point, i) => {
              const maxVal = Math.max(
                ...usage.map((p) => p.searches + p.documents_added),
                1
              );
              const total = point.searches + point.documents_added;
              const height = (total / maxVal) * 100;
              return (
                <div
                  key={i}
                  className="flex-1 flex flex-col items-center justify-end"
                  title={`${point.date}: ${point.searches} buscas, ${point.documents_added} docs`}
                >
                  <div
                    className="w-full bg-indigo-400 dark:bg-indigo-500 rounded-t transition-all duration-300 hover:bg-indigo-500 dark:hover:bg-indigo-400"
                    style={{ height: `${Math.max(2, height)}%` }}
                  />
                </div>
              );
            })}
          </div>
          <div className="flex justify-between mt-2">
            <span className="text-[10px] text-slate-400">
              {usage[0]?.date}
            </span>
            <span className="text-[10px] text-slate-400">
              {usage[usage.length - 1]?.date}
            </span>
          </div>
          <div className="flex items-center gap-4 mt-3 text-[10px] text-slate-400">
            <div className="flex items-center gap-1">
              <div className="h-2 w-2 rounded-sm bg-indigo-400" />
              <span>Buscas + Documentos adicionados</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function StatCard({
  icon: Icon,
  label,
  value,
  color,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string | number;
  color: string;
}) {
  const colorMap: Record<string, string> = {
    blue: 'bg-blue-50 text-blue-600 dark:bg-blue-950 dark:text-blue-400',
    violet:
      'bg-violet-50 text-violet-600 dark:bg-violet-950 dark:text-violet-400',
    emerald:
      'bg-emerald-50 text-emerald-600 dark:bg-emerald-950 dark:text-emerald-400',
    amber:
      'bg-amber-50 text-amber-600 dark:bg-amber-950 dark:text-amber-400',
  };

  return (
    <div className="border border-slate-200 dark:border-slate-700 rounded-xl p-4 bg-white dark:bg-slate-900">
      <div className={`inline-flex p-2 rounded-lg ${colorMap[color]} mb-2`}>
        <Icon className="h-4 w-4" />
      </div>
      <p className="text-2xl font-bold text-slate-900 dark:text-slate-100">
        {typeof value === 'number' ? value.toLocaleString() : value}
      </p>
      <p className="text-xs text-slate-500">{label}</p>
    </div>
  );
}
