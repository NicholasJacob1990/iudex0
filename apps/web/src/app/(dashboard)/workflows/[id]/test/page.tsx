'use client';

import React, { useState, useCallback } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { Play, ArrowLeft, Loader2, CheckCircle2, AlertTriangle, FlaskConical } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { apiClient } from '@/lib/api-client';

interface TestEvent {
  type: string;
  data: Record<string, any>;
  timestamp: number;
}

export default function WorkflowTestPage() {
  const params = useParams();
  const router = useRouter();
  const workflowId = params.id as string;

  const [input, setInput] = useState('');
  const [running, setRunning] = useState(false);
  const [events, setEvents] = useState<TestEvent[]>([]);
  const [status, setStatus] = useState<string | null>(null);
  const [output, setOutput] = useState<string>('');

  const handleTest = useCallback(async () => {
    setRunning(true);
    setEvents([]);
    setStatus('running');
    setOutput('');

    try {
      const response = await apiClient.fetchWithAuth(`/workflows/${workflowId}/test`, {
        method: 'POST',
        body: JSON.stringify({ input_data: { input } }),
        headers: { 'Content-Type': 'application/json' },
      });

      const reader = response.body?.getReader();
      if (!reader) {
        setStatus('error');
        setRunning(false);
        return;
      }

      const decoder = new TextDecoder();
      let buffer = '';

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

            setEvents((prev) => [...prev, { type: evtType, data: evtData, timestamp: Date.now() }]);

            if (evtData.content) {
              setOutput((prev) => prev + evtData.content);
            }
            if (evtData.status === 'completed' || evtType === 'done') {
              setStatus('completed');
            }
            if (evtData.error || evtType === 'error') {
              setStatus('error');
            }
          } catch { /* skip */ }
        }
      }

      if (status === 'running') setStatus('completed');
    } catch (err: any) {
      setStatus('error');
      setEvents((prev) => [...prev, { type: 'error', data: { error: err.message }, timestamp: Date.now() }]);
    } finally {
      setRunning(false);
    }
  }, [workflowId, input, status]);

  return (
    <div className="max-w-3xl mx-auto px-6 py-8">
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <Button variant="ghost" size="icon" onClick={() => router.back()}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <FlaskConical className="h-5 w-5 text-violet-500" />
        <h1 className="text-lg font-bold text-slate-900 dark:text-slate-100">
          Modo de Teste
        </h1>
        <span className="text-xs text-slate-500 bg-violet-100 dark:bg-violet-900 px-2 py-0.5 rounded">
          Transiente
        </span>
      </div>

      {/* Input */}
      <div className="mb-6">
        <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-2 block">
          Dados de Entrada
        </label>
        <Textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Digite o texto de entrada para testar o workflow..."
          className="h-32"
        />
        <Button
          onClick={handleTest}
          disabled={running}
          className="mt-3 gap-1.5 bg-violet-600 hover:bg-violet-500 text-white"
        >
          {running ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Play className="h-3.5 w-3.5" />
          )}
          Testar
        </Button>
      </div>

      {/* Events */}
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
          <div className="space-y-1 max-h-48 overflow-y-auto border rounded-lg p-3 bg-slate-50 dark:bg-slate-950">
            {events.map((evt, i) => (
              <div key={i} className="flex items-center gap-2 text-xs text-slate-600 dark:text-slate-400">
                <span className="text-slate-400 w-6 text-right">{i + 1}.</span>
                <span className="truncate">
                  {evt.data?.node_id ? `${evt.data.node_id} — ${evt.data.status || evt.type}` : evt.type}
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
    </div>
  );
}
