'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { useParams } from 'next/navigation';
import {
  Play,
  Loader2,
  CheckCircle2,
  AlertTriangle,
  Sparkles,
  Lock,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { apiClient } from '@/lib/api-client';

interface PublishedWorkflow {
  id: string;
  name: string;
  description: string;
  slug: string;
  graph_json: { nodes: any[]; edges: any[] };
  require_auth: boolean;
}

interface RunEvent {
  type: string;
  data: Record<string, any>;
  timestamp: number;
}

export default function PublishedWorkflowPage() {
  const params = useParams();
  const slug = params.slug as string;

  const [workflow, setWorkflow] = useState<PublishedWorkflow | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [input, setInput] = useState('');
  const [output, setOutput] = useState('');
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [status, setStatus] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      try {
        const res = await apiClient.fetchWithAuth(`/workflows/app/${slug}`);
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          if (res.status === 401) {
            setError('auth_required');
          } else if (res.status === 403) {
            setError('forbidden');
          } else if (res.status === 404) {
            setError('not_found');
          } else {
            setError(err.detail || 'Erro ao carregar app');
          }
          return;
        }
        const data = await res.json();
        setWorkflow(data);
      } catch {
        setError('Erro ao carregar app');
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [slug]);

  const handleRun = useCallback(async () => {
    if (!workflow) return;
    setRunning(true);
    setOutput('');
    setEvents([]);
    setStatus('running');

    try {
      const response = await apiClient.fetchWithAuth(
        `/workflows/${workflow.id}/test`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ input_data: { input } }),
        }
      );

      if (!response.ok) {
        setStatus('error');
        setRunning(false);
        return;
      }

      const reader = response.body?.getReader();
      if (!reader) {
        setStatus('error');
        setRunning(false);
        return;
      }

      const decoder = new TextDecoder();
      let buffer = '';
      let finalStatus = 'running';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.startsWith('data:')) continue;
          try {
            const parsed = JSON.parse(line.slice(5).trim());
            const evtData = parsed.data || parsed;
            const evtType = parsed.type || 'message';

            setEvents((prev) => [
              ...prev,
              { type: evtType, data: evtData, timestamp: Date.now() },
            ]);

            if (evtData.content) {
              setOutput((prev) => prev + evtData.content);
            }
            if (
              evtData.status === 'completed' ||
              evtType === 'done'
            ) {
              finalStatus = 'completed';
              setStatus('completed');
            }
            if (evtData.error || evtType === 'error') {
              finalStatus = 'error';
              setStatus('error');
            }
          } catch {
            /* skip parse errors */
          }
        }
      }

      if (finalStatus === 'running') {
        setStatus('completed');
      }
    } catch {
      setStatus('error');
    } finally {
      setRunning(false);
    }
  }, [workflow, input]);

  // Loading state
  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50 dark:bg-slate-950">
        <Loader2 className="h-8 w-8 text-indigo-500 animate-spin" />
      </div>
    );
  }

  // Error states
  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50 dark:bg-slate-950">
        <div className="text-center max-w-sm">
          {error === 'auth_required' ? (
            <>
              <Lock className="h-10 w-10 text-amber-500 mx-auto mb-3" />
              <h1 className="text-lg font-semibold text-slate-800 dark:text-slate-200 mb-1">
                Login necessario
              </h1>
              <p className="text-sm text-slate-500 mb-4">
                Este app requer autenticacao para acessar.
              </p>
              <Button
                onClick={() =>
                  (window.location.href = `/login?redirect=/app/${slug}`)
                }
                className="bg-indigo-600 hover:bg-indigo-500 text-white"
              >
                Fazer Login
              </Button>
            </>
          ) : error === 'forbidden' ? (
            <>
              <Lock className="h-10 w-10 text-red-500 mx-auto mb-3" />
              <h1 className="text-lg font-semibold text-slate-800 dark:text-slate-200 mb-1">
                Acesso negado
              </h1>
              <p className="text-sm text-slate-500">
                Voce nao tem permissao para acessar este app.
              </p>
            </>
          ) : error === 'not_found' ? (
            <>
              <AlertTriangle className="h-10 w-10 text-slate-400 mx-auto mb-3" />
              <h1 className="text-lg font-semibold text-slate-800 dark:text-slate-200 mb-1">
                App nao encontrado
              </h1>
              <p className="text-sm text-slate-500">
                Este app nao existe ou foi despublicado.
              </p>
            </>
          ) : (
            <>
              <AlertTriangle className="h-10 w-10 text-red-400 mx-auto mb-3" />
              <h1 className="text-lg font-semibold text-slate-800 dark:text-slate-200 mb-1">
                Erro
              </h1>
              <p className="text-sm text-slate-500">{error}</p>
            </>
          )}
        </div>
      </div>
    );
  }

  if (!workflow) return null;

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950">
      {/* Header */}
      <header className="bg-white dark:bg-slate-900 border-b border-slate-200 dark:border-slate-800">
        <div className="max-w-3xl mx-auto px-6 py-4">
          <div className="flex items-center gap-3">
            <Sparkles className="h-5 w-5 text-indigo-500" />
            <div>
              <h1 className="text-lg font-bold text-slate-900 dark:text-slate-100">
                {workflow.name}
              </h1>
              {workflow.description && (
                <p className="text-xs text-slate-500 mt-0.5">
                  {workflow.description}
                </p>
              )}
            </div>
          </div>
        </div>
      </header>

      {/* Main content */}
      <main className="max-w-3xl mx-auto px-6 py-8">
        {/* Input */}
        <div className="mb-6">
          <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-2 block">
            Dados de Entrada
          </label>
          <Textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Digite o texto de entrada..."
            className="h-32"
          />
          <Button
            onClick={handleRun}
            disabled={running || !input.trim()}
            className="mt-3 gap-1.5 bg-indigo-600 hover:bg-indigo-500 text-white"
          >
            {running ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Play className="h-3.5 w-3.5" />
            )}
            Executar
          </Button>
        </div>

        {/* Events / Steps */}
        {events.length > 0 && (
          <div className="mb-6">
            <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-2 flex items-center gap-2">
              {status === 'completed' ? (
                <CheckCircle2 className="h-4 w-4 text-emerald-500" />
              ) : status === 'error' ? (
                <AlertTriangle className="h-4 w-4 text-red-500" />
              ) : (
                <Loader2 className="h-4 w-4 text-blue-500 animate-spin" />
              )}
              Etapas ({events.length})
            </h2>
            <div className="space-y-1 max-h-48 overflow-y-auto border rounded-lg p-3 bg-white dark:bg-slate-900">
              {events.map((evt, i) => (
                <div
                  key={i}
                  className="flex items-center gap-2 text-xs text-slate-600 dark:text-slate-400"
                >
                  <span className="text-slate-400 w-6 text-right">
                    {i + 1}.
                  </span>
                  <span className="truncate">
                    {evt.data?.node_id
                      ? `${evt.data.node_id} — ${evt.data.status || evt.type}`
                      : evt.type}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Output */}
        {output && (
          <div>
            <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-2">
              Resultado
            </h2>
            <div className="border rounded-lg p-4 bg-white dark:bg-slate-900 text-sm text-slate-800 dark:text-slate-200 whitespace-pre-wrap">
              {output}
            </div>
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-200 dark:border-slate-800 mt-auto">
        <div className="max-w-3xl mx-auto px-6 py-3 text-center">
          <p className="text-[10px] text-slate-400">
            Powered by Iudex
          </p>
        </div>
      </footer>
    </div>
  );
}
