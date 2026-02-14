'use client';

import React, { useEffect, useState } from 'react';
import { X, Play, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { apiClient } from '@/lib/api-client';
import { useRouter } from 'next/navigation';

interface WorkflowPickerModalProps {
  open: boolean;
  onClose: () => void;
  folderId?: string;
  runInput?: string;
}

interface WorkflowItem {
  id: string;
  name: string;
  description: string | null;
}

export function WorkflowPickerModal({ open, onClose, folderId, runInput }: WorkflowPickerModalProps) {
  const router = useRouter();
  const [workflows, setWorkflows] = useState<WorkflowItem[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    apiClient.listWorkflows()
      .then((data) => setWorkflows(data))
      .catch(() => setWorkflows([]))
      .finally(() => setLoading(false));
  }, [open]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center">
      <div className="bg-white dark:bg-slate-900 rounded-xl shadow-xl w-full max-w-md p-5">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-200">Selecionar Workflow</h3>
          <button onClick={onClose}><X className="h-4 w-4 text-slate-400" /></button>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-6 w-6 text-indigo-500 animate-spin" />
          </div>
        ) : workflows.length === 0 ? (
          <p className="text-xs text-slate-400 text-center py-8">Nenhum workflow encontrado</p>
        ) : (
          <div className="max-h-64 overflow-y-auto space-y-1.5">
            {workflows.map((wf) => (
              <button
                key={wf.id}
                onClick={() => {
                  const params = new URLSearchParams();
                  if (folderId) params.set('folder_id', folderId);
                  if (runInput?.trim()) params.set('input', runInput.trim());
                  const queryString = params.toString();
                  router.push(`/workflows/${wf.id}/run${queryString ? `?${queryString}` : ''}`);
                  onClose();
                }}
                className="w-full text-left px-3 py-2.5 rounded-lg hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors border border-slate-200 dark:border-slate-700 flex items-center gap-3"
              >
                <Play className="h-4 w-4 text-indigo-500 shrink-0" />
                <div className="min-w-0 flex-1">
                  <p className="text-xs font-medium text-slate-700 dark:text-slate-300 truncate">{wf.name}</p>
                  {wf.description && (
                    <p className="text-[10px] text-slate-400 truncate">{wf.description}</p>
                  )}
                </div>
              </button>
            ))}
          </div>
        )}

        <div className="mt-4">
          <Button variant="outline" size="sm" className="w-full" onClick={onClose}>Cancelar</Button>
        </div>
      </div>
    </div>
  );
}
