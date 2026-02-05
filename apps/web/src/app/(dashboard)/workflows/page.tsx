'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { Plus, Workflow, Loader2, Trash2, Play } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { apiClient } from '@/lib/api-client';
import { toast } from 'sonner';
import { useRouter } from 'next/navigation';
import { useQueryClient } from '@tanstack/react-query';
import { prefetchFns } from '@/lib/prefetch';

interface WorkflowItem {
  id: string;
  name: string;
  description: string | null;
  is_active: boolean;
  tags: string[];
  updated_at: string;
}

export default function WorkflowsListPage() {
  const [workflows, setWorkflows] = useState<WorkflowItem[]>([]);
  const [loading, setLoading] = useState(true);
  const router = useRouter();
  const queryClient = useQueryClient();

  const handlePrefetchDetail = useCallback(
    (id: string) => {
      try { prefetchFns.workflowDetail(queryClient, id); } catch { /* silencioso */ }
    },
    [queryClient]
  );

  const fetchWorkflows = async () => {
    try {
      const data = await apiClient.listWorkflows();
      setWorkflows(data);
    } catch {
      toast.error('Erro ao carregar workflows');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchWorkflows();
  }, []);

  const handleCreate = async () => {
    try {
      const created = await apiClient.createWorkflow({
        name: 'Novo Workflow',
        graph_json: { nodes: [], edges: [] },
      });
      router.push(`/workflows/${created.id}`);
    } catch {
      toast.error('Erro ao criar workflow');
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await apiClient.deleteWorkflow(id);
      setWorkflows((prev) => prev.filter((w) => w.id !== id));
      toast.success('Workflow removido');
    } catch {
      toast.error('Erro ao remover');
    }
  };

  return (
    <div className="container mx-auto px-6 py-8 max-w-5xl">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Workflows</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            Crie e gerencie fluxos visuais com LangGraph
          </p>
        </div>
        <Button onClick={handleCreate} className="gap-2 bg-indigo-600 hover:bg-indigo-500 text-white">
          <Plus className="h-4 w-4" />
          Novo Workflow
        </Button>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="h-8 w-8 text-indigo-500 animate-spin" />
        </div>
      ) : workflows.length === 0 ? (
        <div className="text-center py-20">
          <Workflow className="h-12 w-12 text-slate-300 mx-auto mb-4" />
          <p className="text-slate-500 dark:text-slate-400 mb-4">Nenhum workflow criado ainda</p>
          <Button onClick={handleCreate} variant="outline" className="gap-2">
            <Plus className="h-4 w-4" />
            Criar primeiro workflow
          </Button>
        </div>
      ) : (
        <div className="grid gap-4">
          {workflows.map((wf) => (
            <div
              key={wf.id}
              className="group flex items-center gap-4 p-4 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 hover:border-indigo-300 dark:hover:border-indigo-700 transition-colors cursor-pointer"
              onClick={() => router.push(`/workflows/${wf.id}`)}
              onMouseEnter={() => handlePrefetchDetail(wf.id)}
            >
              <div className="h-10 w-10 rounded-lg bg-indigo-100 dark:bg-indigo-500/20 flex items-center justify-center shrink-0">
                <Workflow className="h-5 w-5 text-indigo-600 dark:text-indigo-400" />
              </div>
              <div className="flex-1 min-w-0">
                <h3 className="font-semibold text-slate-800 dark:text-slate-200 truncate">{wf.name}</h3>
                {wf.description && (
                  <p className="text-xs text-slate-500 dark:text-slate-400 truncate mt-0.5">{wf.description}</p>
                )}
                <div className="flex items-center gap-2 mt-1">
                  {wf.tags.map((tag) => (
                    <span key={tag} className="text-[10px] px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-slate-500">
                      {tag}
                    </span>
                  ))}
                  <span className="text-[10px] text-slate-400">
                    {new Date(wf.updated_at).toLocaleDateString('pt-BR')}
                  </span>
                </div>
              </div>
              <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8 text-red-500 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-950"
                  onClick={(e) => {
                    e.stopPropagation();
                    handleDelete(wf.id);
                  }}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
