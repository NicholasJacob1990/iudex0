'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { History, RotateCcw, ChevronDown, ChevronUp, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { apiClient } from '@/lib/api-client';
import { toast } from 'sonner';

interface Version {
  id: string;
  version: number;
  change_notes: string | null;
  created_by: string;
  created_at: string;
}

interface VersionHistoryProps {
  workflowId: string;
  onRestore?: () => void;
}

export function VersionHistory({ workflowId, onRestore }: VersionHistoryProps) {
  const [versions, setVersions] = useState<Version[]>([]);
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [restoring, setRestoring] = useState<number | null>(null);

  const fetchVersions = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiClient.fetchWithAuth(`/workflows/${workflowId}/versions`);
      const data = await res.json();
      setVersions(data);
    } catch {
      toast.error('Erro ao carregar versões');
    } finally {
      setLoading(false);
    }
  }, [workflowId]);

  useEffect(() => {
    if (expanded && versions.length === 0) {
      fetchVersions();
    }
  }, [expanded, versions.length, fetchVersions]);

  const handleRestore = async (versionNumber: number) => {
    setRestoring(versionNumber);
    try {
      await apiClient.fetchWithAuth(`/workflows/${workflowId}/versions/${versionNumber}/restore`, { method: 'POST' });
      toast.success(`Restaurado para versão ${versionNumber}`);
      onRestore?.();
    } catch {
      toast.error('Erro ao restaurar versão');
    } finally {
      setRestoring(null);
    }
  };

  return (
    <div className="border rounded-lg bg-white dark:bg-slate-900">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 w-full px-4 py-2.5 text-left hover:bg-slate-50 dark:hover:bg-slate-800 rounded-lg transition-colors"
      >
        <History className="h-4 w-4 text-slate-500" />
        <span className="text-sm font-medium text-slate-700 dark:text-slate-300 flex-1">
          Histórico de Versões
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
        <div className="border-t border-slate-200 dark:border-slate-700 px-4 py-2 space-y-2 max-h-60 overflow-y-auto">
          {versions.length === 0 && !loading && (
            <p className="text-xs text-slate-400 py-2">Nenhuma versão salva</p>
          )}
          {versions.map((v) => (
            <div
              key={v.id}
              className="flex items-center gap-2 py-1.5 border-b border-slate-100 dark:border-slate-800 last:border-0"
            >
              <div className="flex-1 min-w-0">
                <p className="text-xs font-medium text-slate-700 dark:text-slate-300">
                  v{v.version}
                </p>
                {v.change_notes && (
                  <p className="text-xs text-slate-500 truncate">{v.change_notes}</p>
                )}
                <p className="text-[10px] text-slate-400">
                  {new Date(v.created_at).toLocaleDateString('pt-BR')}
                </p>
              </div>
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7 shrink-0"
                onClick={() => handleRestore(v.version)}
                disabled={restoring !== null}
                title="Restaurar esta versão"
              >
                {restoring === v.version ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <RotateCcw className="h-3.5 w-3.5" />
                )}
              </Button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
