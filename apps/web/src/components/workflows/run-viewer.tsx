'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { BookOpen, CheckCircle2, Circle, Loader2, AlertTriangle, Eye, X, Download, FileText, FileSpreadsheet, FileDown, Send, Share2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useWorkflowStore, type RunEvent } from '@/stores/workflow-store';
import { apiClient } from '@/lib/api-client';
import { CitationsPanel, parseCitations, type Citation } from './citations-panel';

export function RunViewer() {
  const {
    isRunning, runEvents, runStatus, runId,
    hilPending, hilNodeId, hilInstructions,
    clearHIL, setRunStatus, addRunEvent, setHIL,
    resetRun,
  } = useWorkflowStore();
  const scrollRef = useRef<HTMLDivElement>(null);
  const followUpScrollRef = useRef<HTMLDivElement>(null);
  const [citationsOpen, setCitationsOpen] = useState(false);

  // Follow-up state
  const [followUpQuestion, setFollowUpQuestion] = useState('');
  const [followUpMessages, setFollowUpMessages] = useState<Array<{ role: 'user' | 'assistant'; content: string }>>([]);
  const [isFollowUpStreaming, setIsFollowUpStreaming] = useState(false);

  // Share state
  const [shareOpen, setShareOpen] = useState(false);
  const [shareInput, setShareInput] = useState('');
  const [shareMessage, setShareMessage] = useState('');
  const [shareOrgWide, setShareOrgWide] = useState(false);
  const [shareStatus, setShareStatus] = useState<'idle' | 'sending' | 'sent' | 'error'>('idle');
  const shareTimeoutRef = useRef<number | null>(null);

  // Cleanup share timeout on unmount
  useEffect(() => {
    return () => {
      if (shareTimeoutRef.current) clearTimeout(shareTimeoutRef.current);
    };
  }, []);

  // Collect citations from run events (step_outputs and LLM output text)
  const citations = useMemo<Citation[]>(() => {
    const allCitations: Citation[] = [];
    const seen = new Set<number>();

    for (const evt of runEvents) {
      const data = evt.data;
      // Citations from step_outputs (backend-parsed)
      if (data?.citations && Array.isArray(data.citations)) {
        for (const c of data.citations) {
          if (typeof c === 'object' && c.number && !seen.has(c.number)) {
            seen.add(c.number);
            allCitations.push({
              number: c.number,
              source: c.source || '',
              excerpt: c.excerpt || '',
              url: c.url,
            });
          }
        }
      }
      // Also try to parse from output text in done/completed events
      if ((evt.type === 'done' || data?.status === 'completed') && data?.output) {
        const parsed = parseCitations(data.output);
        for (const c of parsed) {
          if (!seen.has(c.number)) {
            seen.add(c.number);
            allCitations.push(c);
          }
        }
      }
      // Check step_outputs in metadata
      if (data?.step_outputs) {
        for (const stepData of Object.values(data.step_outputs)) {
          const step = stepData as Record<string, any>;
          if (step?.citations && Array.isArray(step.citations)) {
            for (const c of step.citations) {
              if (typeof c === 'object' && c.number && !seen.has(c.number)) {
                seen.add(c.number);
                allCitations.push({
                  number: c.number,
                  source: c.source || '',
                  excerpt: c.excerpt || '',
                  url: c.url,
                });
              }
            }
          }
        }
      }
    }

    return allCitations.sort((a, b) => a.number - b.number);
  }, [runEvents]);

  // Progress tracking from SSE events
  const progress = useMemo(() => {
    let stepNumber = 0;
    let totalSteps = 0;
    let elapsedSeconds: number | null = null;

    for (const evt of runEvents) {
      const data = evt.data;
      if (data?.step_number && data?.total_steps) {
        stepNumber = data.step_number;
        totalSteps = data.total_steps;
      }
      if (data?.elapsed_seconds !== undefined) {
        elapsedSeconds = data.elapsed_seconds;
      }
      // Also check nested metadata in done events
      if (evt.type === 'done' && data?.metadata) {
        if (data.metadata.elapsed_seconds !== undefined) {
          elapsedSeconds = data.metadata.elapsed_seconds;
        }
        if (data.metadata.total_steps) {
          totalSteps = data.metadata.total_steps;
        }
      }
    }

    return { stepNumber, totalSteps, elapsedSeconds };
  }, [runEvents]);

  const formatElapsed = (seconds: number): string => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    if (mins > 0) return `${mins}m ${secs}s`;
    return `${secs}s`;
  };

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [runEvents]);

  const [exportOpen, setExportOpen] = useState(false);

  // Scroll follow-up messages into view
  useEffect(() => {
    if (followUpScrollRef.current) {
      followUpScrollRef.current.scrollTop = followUpScrollRef.current.scrollHeight;
    }
  }, [followUpMessages]);

  const handleFollowUp = useCallback(async () => {
    if (!runId || !followUpQuestion.trim() || isFollowUpStreaming) return;

    const question = followUpQuestion.trim();
    setFollowUpQuestion('');
    setFollowUpMessages((prev) => [...prev, { role: 'user', content: question }]);
    setIsFollowUpStreaming(true);

    try {
      const response = await apiClient.followUpRun(runId, question);
      const reader = response.body?.getReader();
      if (!reader) {
        setIsFollowUpStreaming(false);
        return;
      }

      const decoder = new TextDecoder();
      let buffer = '';
      let assistantText = '';

      // Add empty assistant message that we'll update progressively
      setFollowUpMessages((prev) => [...prev, { role: 'assistant', content: '' }]);

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
            if (parsed.type === 'token' && parsed.data?.token) {
              assistantText += parsed.data.token;
              const text = assistantText;
              setFollowUpMessages((prev) => {
                const updated = [...prev];
                updated[updated.length - 1] = { role: 'assistant', content: text };
                return updated;
              });
            }
          } catch { /* skip malformed lines */ }
        }
      }
    } catch (err: any) {
      setFollowUpMessages((prev) => [
        ...prev,
        { role: 'assistant', content: `Erro: ${err.message || 'Falha ao processar follow-up'}` },
      ]);
    } finally {
      setIsFollowUpStreaming(false);
    }
  }, [runId, followUpQuestion, isFollowUpStreaming]);

  const handleShare = useCallback(async () => {
    if (!runId) return;

    if (!shareOrgWide && !shareInput.trim()) return;

    setShareStatus('sending');
    try {
      if (shareOrgWide) {
        await apiClient.shareRunWithOrg(runId, shareMessage || undefined);
      } else {
        const userIds = shareInput.split(',').map((s) => s.trim()).filter(Boolean);
        if (userIds.length === 0) {
          setShareStatus('error');
          return;
        }
        await apiClient.shareRun(runId, userIds, shareMessage || undefined);
      }
      setShareStatus('sent');
      shareTimeoutRef.current = window.setTimeout(() => {
        setShareOpen(false);
        setShareInput('');
        setShareMessage('');
        setShareOrgWide(false);
        setShareStatus('idle');
      }, 2000);
    } catch {
      setShareStatus('error');
      shareTimeoutRef.current = window.setTimeout(() => setShareStatus('idle'), 3000);
    }
  }, [runId, shareInput, shareMessage, shareOrgWide]);

  if (!isRunning && runEvents.length === 0) return null;

  const handleExport = (format: string) => {
    if (!runId) return;
    setExportOpen(false);
    window.open(`/api/workflows/runs/${runId}/export/${format}`, '_blank');
  };

  const handleApprove = async () => {
    if (!runId) return;
    clearHIL();
    try {
      const response = await apiClient.resumeWorkflowRun(runId, { approved: true });
      const reader = response.body?.getReader();
      if (!reader) return;
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
            processSSEEvent(parsed);
          } catch { /* skip */ }
        }
      }
    } catch (err: any) {
      addRunEvent({ type: 'error', data: { error: err.message }, timestamp: Date.now() });
      setRunStatus('error');
    }
  };

  const handleReject = async () => {
    if (!runId) return;
    clearHIL();
    try {
      await apiClient.resumeWorkflowRun(runId, { approved: false });
      setRunStatus('rejected');
    } catch { /* ignore */ }
  };

  const processSSEEvent = (parsed: any) => {
    const evtData = parsed.data || parsed;
    const evtType = parsed.type || 'message';
    addRunEvent({ type: evtType, data: evtData, timestamp: Date.now() });

    if (evtData.status === 'paused_hil') {
      setHIL(evtData.node_id || '', evtData.instructions || '');
    }
    if (evtData.status === 'completed' || evtType === 'done') {
      setRunStatus('completed');
    }
    if (evtData.error || evtType === 'error') {
      setRunStatus('error');
    }
  };

  const statusIcon = (evt: RunEvent) => {
    if (evt.type === 'error') return <AlertTriangle className="h-3.5 w-3.5 text-red-500 shrink-0" />;
    if (evt.type === 'done') return <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500 shrink-0" />;
    if (evt.data?.status === 'running' || evt.type === 'workflow_node_start')
      return <Loader2 className="h-3.5 w-3.5 text-blue-500 animate-spin shrink-0" />;
    if (evt.data?.status === 'completed' || evt.type === 'workflow_node_end')
      return <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500 shrink-0" />;
    if (evt.data?.status === 'paused_hil')
      return <Eye className="h-3.5 w-3.5 text-amber-500 shrink-0" />;
    return <Circle className="h-3.5 w-3.5 text-slate-300 shrink-0" />;
  };

  const eventLabel = (evt: RunEvent): string => {
    if (evt.data?.node_id) return `${evt.data.node_id} — ${evt.data.status || evt.type}`;
    if (evt.data?.error) return `Erro: ${evt.data.error}`;
    if (evt.type === 'done') return 'Workflow concluído';
    return evt.type;
  };

  return (
    <div className="border-t border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-950 flex max-h-[400px]">
      {/* Main content */}
      <div className="flex-1 flex flex-col min-w-0">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-slate-200 dark:border-slate-700">
        <div className="flex items-center gap-2">
          {isRunning ? (
            <Loader2 className="h-4 w-4 text-blue-500 animate-spin" />
          ) : runStatus === 'completed' ? (
            <CheckCircle2 className="h-4 w-4 text-emerald-500" />
          ) : runStatus === 'error' ? (
            <AlertTriangle className="h-4 w-4 text-red-500" />
          ) : (
            <Circle className="h-4 w-4 text-slate-400" />
          )}
          <span className="text-xs font-semibold text-slate-600 dark:text-slate-300">
            {isRunning ? 'Executando...' : runStatus === 'completed' ? 'Concluído' : runStatus === 'error' ? 'Erro' : runStatus || 'Execução'}
          </span>
        </div>
        <div className="flex items-center gap-1">
          {/* Citations toggle */}
          {citations.length > 0 && (
            <Button
              variant="ghost"
              size="icon"
              className={`h-6 w-6 ${citationsOpen ? 'text-blue-500' : ''}`}
              title={`Citações (${citations.length})`}
              onClick={() => setCitationsOpen(!citationsOpen)}
            >
              <BookOpen className="h-3.5 w-3.5" />
            </Button>
          )}
          {/* Share button — only for completed runs */}
          {!isRunning && runStatus === 'completed' && (
            <div className="relative">
              <Button
                variant="ghost"
                size="icon"
                className={`h-6 w-6 ${shareOpen ? 'text-blue-500' : ''}`}
                title="Compartilhar"
                onClick={() => { setShareOpen(!shareOpen); setExportOpen(false); }}
              >
                <Share2 className="h-3.5 w-3.5" />
              </Button>
              {shareOpen && (
                <div className="absolute right-0 top-7 z-50 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-md shadow-lg p-3 min-w-[260px]">
                  <p className="text-xs font-semibold text-slate-700 dark:text-slate-300 mb-2">Compartilhar resultado</p>
                  <label className="flex items-center gap-2 mb-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={shareOrgWide}
                      onChange={(e) => setShareOrgWide(e.target.checked)}
                      className="rounded border-slate-300"
                    />
                    <span className="text-xs text-slate-600 dark:text-slate-400">Toda a organização</span>
                  </label>
                  {!shareOrgWide && (
                    <input
                      type="text"
                      className="w-full text-xs px-2 py-1.5 border border-slate-300 dark:border-slate-600 rounded bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-300 mb-2 focus:outline-none focus:ring-1 focus:ring-blue-500"
                      placeholder="IDs ou emails (separados por vírgula)"
                      value={shareInput}
                      onChange={(e) => setShareInput(e.target.value)}
                    />
                  )}
                  <textarea
                    className="w-full text-xs px-2 py-1.5 border border-slate-300 dark:border-slate-600 rounded bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-300 mb-2 resize-none focus:outline-none focus:ring-1 focus:ring-blue-500"
                    placeholder="Mensagem (opcional)"
                    rows={2}
                    value={shareMessage}
                    onChange={(e) => setShareMessage(e.target.value)}
                  />
                  <div className="flex items-center justify-between">
                    {shareStatus === 'sent' ? (
                      <span className="text-xs text-emerald-600">Compartilhado!</span>
                    ) : shareStatus === 'error' ? (
                      <span className="text-xs text-red-500">Erro ao compartilhar</span>
                    ) : (
                      <span />
                    )}
                    <Button
                      size="sm"
                      className="text-xs h-7"
                      disabled={shareStatus === 'sending' || (!shareOrgWide && !shareInput.trim())}
                      onClick={handleShare}
                    >
                      {shareStatus === 'sending' ? (
                        <Loader2 className="h-3 w-3 animate-spin mr-1" />
                      ) : (
                        <Share2 className="h-3 w-3 mr-1" />
                      )}
                      Enviar
                    </Button>
                  </div>
                </div>
              )}
            </div>
          )}
          {/* Export dropdown — only for completed runs */}
          {!isRunning && runStatus === 'completed' && (
            <div className="relative">
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6"
                title="Exportar resultado"
                onClick={() => { setExportOpen(!exportOpen); setShareOpen(false); }}
              >
                <Download className="h-3.5 w-3.5" />
              </Button>
              {exportOpen && (
                <div className="absolute right-0 top-7 z-50 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-md shadow-lg py-1 min-w-[160px]">
                  <button
                    className="flex items-center gap-2 w-full px-3 py-1.5 text-xs text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700"
                    onClick={() => handleExport('docx')}
                  >
                    <FileText className="h-3.5 w-3.5 text-blue-500" />
                    Word (.docx)
                  </button>
                  <button
                    className="flex items-center gap-2 w-full px-3 py-1.5 text-xs text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700"
                    onClick={() => handleExport('xlsx')}
                  >
                    <FileSpreadsheet className="h-3.5 w-3.5 text-emerald-500" />
                    Excel (.xlsx)
                  </button>
                  <button
                    className="flex items-center gap-2 w-full px-3 py-1.5 text-xs text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700"
                    onClick={() => handleExport('pdf')}
                  >
                    <FileDown className="h-3.5 w-3.5 text-red-500" />
                    PDF (.pdf)
                  </button>
                </div>
              )}
            </div>
          )}
          {!isRunning && (
            <Button variant="ghost" size="icon" className="h-6 w-6" onClick={resetRun}>
              <X className="h-3.5 w-3.5" />
            </Button>
          )}
        </div>
      </div>

      {/* Progress bar */}
      {progress.totalSteps > 0 && (
        <div className="px-4 py-2 border-b border-slate-200 dark:border-slate-700">
          {runStatus === 'completed' ? (
            <div className="flex items-center gap-2 text-xs text-emerald-600 dark:text-emerald-400">
              <CheckCircle2 className="h-3.5 w-3.5 shrink-0" />
              <span>
                Concluído em {progress.totalSteps} etapa{progress.totalSteps !== 1 ? 's' : ''}
                {progress.elapsedSeconds !== null && ` (${formatElapsed(progress.elapsedSeconds)})`}
              </span>
            </div>
          ) : (
            <>
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs text-slate-500 dark:text-slate-400">
                  Etapa {progress.stepNumber} de {progress.totalSteps}
                </span>
                <span className="text-xs text-slate-400 dark:text-slate-500">
                  {Math.round((progress.stepNumber / progress.totalSteps) * 100)}%
                </span>
              </div>
              <div className="w-full h-1.5 bg-slate-200 dark:bg-slate-700 rounded-full overflow-hidden">
                <div
                  className="h-full bg-blue-500 rounded-full transition-all duration-300"
                  style={{ width: `${Math.round((progress.stepNumber / progress.totalSteps) * 100)}%` }}
                />
              </div>
            </>
          )}
        </div>
      )}

      {/* Events log */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-2 space-y-1">
        {runEvents.map((evt, i) => (
          <div key={i} className="flex items-start gap-2 text-xs text-slate-600 dark:text-slate-400">
            {statusIcon(evt)}
            <span className="truncate">{eventLabel(evt)}</span>
          </div>
        ))}
      </div>

      {/* HIL Modal */}
      {hilPending && (
        <div className="border-t border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-950/50 px-4 py-3">
          <div className="flex items-center gap-2 mb-2">
            <Eye className="h-4 w-4 text-amber-600" />
            <span className="text-sm font-semibold text-amber-800 dark:text-amber-300">Revisão Humana Necessária</span>
          </div>
          {hilInstructions && (
            <p className="text-xs text-amber-700 dark:text-amber-400 mb-3">{hilInstructions}</p>
          )}
          <div className="flex gap-2">
            <Button size="sm" className="bg-emerald-600 hover:bg-emerald-500 text-white" onClick={handleApprove}>
              Aprovar
            </Button>
            <Button size="sm" variant="outline" className="border-red-300 text-red-600 hover:bg-red-50" onClick={handleReject}>
              Rejeitar
            </Button>
          </div>
        </div>
      )}

      {/* Follow-up chat — only for completed runs */}
      {!isRunning && runStatus === 'completed' && (
        <div className="border-t border-slate-200 dark:border-slate-700">
          {/* Follow-up messages */}
          {followUpMessages.length > 0 && (
            <div ref={followUpScrollRef} className="max-h-[120px] overflow-y-auto px-4 py-2 space-y-2">
              {followUpMessages.map((msg, i) => (
                <div
                  key={i}
                  className={`text-xs px-2 py-1.5 rounded ${
                    msg.role === 'user'
                      ? 'bg-blue-50 dark:bg-blue-950/30 text-blue-800 dark:text-blue-300 ml-8'
                      : 'bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 mr-8'
                  }`}
                >
                  <span className="whitespace-pre-wrap">{msg.content}</span>
                  {msg.role === 'assistant' && msg.content === '' && isFollowUpStreaming && (
                    <Loader2 className="h-3 w-3 text-blue-500 animate-spin inline-block ml-1" />
                  )}
                </div>
              ))}
            </div>
          )}
          {/* Follow-up input */}
          <div className="flex items-center gap-2 px-4 py-2">
            <input
              type="text"
              className="flex-1 text-xs px-3 py-1.5 border border-slate-300 dark:border-slate-600 rounded-md bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-300 placeholder-slate-400 focus:outline-none focus:ring-1 focus:ring-blue-500"
              placeholder="Fazer uma pergunta sobre o resultado..."
              value={followUpQuestion}
              onChange={(e) => setFollowUpQuestion(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleFollowUp();
                }
              }}
              disabled={isFollowUpStreaming}
            />
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7 shrink-0"
              disabled={isFollowUpStreaming || !followUpQuestion.trim()}
              onClick={handleFollowUp}
              title="Enviar pergunta"
            >
              {isFollowUpStreaming ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Send className="h-3.5 w-3.5" />
              )}
            </Button>
          </div>
        </div>
      )}
      </div>

      {/* Citations Panel (right side) */}
      <CitationsPanel
        citations={citations}
        isOpen={citationsOpen}
        onToggle={() => setCitationsOpen(false)}
      />
    </div>
  );
}
