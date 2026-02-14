'use client';

import React, { useCallback, useRef, useEffect, useState } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  addEdge,
  useNodesState,
  useEdgesState,
  SelectionMode,
  type Node,
  type Edge,
  type Connection,
  type NodeMouseHandler,
  BackgroundVariant,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import {
  Save, Play, Plus, ArrowLeft, Loader2, Globe,
  Upload, ListChecks, GitBranch, BrainCircuit, Search, Eye, Wrench, Scale,
  FormInput, FileOutput, FlaskConical, Sparkles, Table2, MessageSquare,
  Undo2, Redo2, Bot, GitMerge, Zap, Send, BookOpen,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { toast } from 'sonner';

import { nodeTypes } from './node-types';
import { PropertiesPanel } from './properties-panel';
import { RunViewer } from './run-viewer';
import { VersionHistory } from './version-history';
import { AuditTrail } from './audit-trail';
import { useWorkflowStore, type WorkflowNode, type WorkflowEdge } from '@/stores/workflow-store';
import { apiClient } from '@/lib/api-client';
import { EmbeddedFilesPanel } from './embedded-files-panel';
import { NLInputDialog } from './nl-input-dialog';
import { ImprovePanel } from './improve-panel';
import { PublishDialog } from './publish-dialog';
import { AssistantPanel } from '@/components/assistant';

// ── Toolbar items ────────────────────────────────────────────────
const NODE_PALETTE = [
  { type: 'trigger', label: 'Trigger', icon: Zap, color: 'amber' },
  { type: 'user_input', label: 'Input', icon: FormInput, color: 'teal' },
  { type: 'file_upload', label: 'Upload', icon: Upload, color: 'emerald' },
  { type: 'selection', label: 'Seleção', icon: ListChecks, color: 'amber' },
  { type: 'condition', label: 'Condição', icon: GitBranch, color: 'orange' },
  { type: 'prompt', label: 'Prompt', icon: BrainCircuit, color: 'violet' },
  { type: 'deep_research', label: 'Research', icon: BookOpen, color: 'emerald' },
  { type: 'claude_agent', label: 'Agente', icon: Bot, color: 'indigo' },
  { type: 'parallel_agents', label: 'Paralelo', icon: GitMerge, color: 'fuchsia' },
  { type: 'rag_search', label: 'RAG', icon: Search, color: 'blue' },
  { type: 'human_review', label: 'Revisão', icon: Eye, color: 'rose' },
  { type: 'tool_call', label: 'Tool', icon: Wrench, color: 'cyan' },
  { type: 'legal_workflow', label: 'Minuta', icon: Scale, color: 'indigo' },
  { type: 'review_table', label: 'Tabela', icon: Table2, color: 'teal' },
  { type: 'output', label: 'Resposta', icon: FileOutput, color: 'emerald' },
  { type: 'delivery', label: 'Entrega', icon: Send, color: 'green' },
] as const;

interface WorkflowBuilderProps {
  workflowId?: string;
}

const normalizeWorkflowGraph = (rawGraph: unknown): { nodes: any[]; edges: any[] } => {
  let parsed: any = rawGraph;

  if (typeof parsed === 'string') {
    try {
      parsed = JSON.parse(parsed);
    } catch {
      parsed = {};
    }
  }

  if (!parsed || typeof parsed !== 'object') {
    return { nodes: [], edges: [] };
  }

  return {
    nodes: Array.isArray((parsed as any).nodes) ? (parsed as any).nodes : [],
    edges: Array.isArray((parsed as any).edges) ? (parsed as any).edges : [],
  };
};

export function WorkflowBuilder({ workflowId }: WorkflowBuilderProps) {
  const store = useWorkflowStore();
  // Pull stable action refs for effects so dependency arrays don't include `store` (which changes on any update).
  const setMetadata = useWorkflowStore((s) => s.setMetadata);
  const setNodesInStore = useWorkflowStore((s) => s.setNodes);
  const setEdgesInStore = useWorkflowStore((s) => s.setEdges);
  const setDirty = useWorkflowStore((s) => s.setDirty);
  const resetAll = useWorkflowStore((s) => s.resetAll);
  const reactFlowWrapper = useRef<HTMLDivElement>(null);
  const [isLoading, setIsLoading] = useState(!!workflowId);
  const [nlDialogOpen, setNlDialogOpen] = useState(false);
  const [improvePanelOpen, setImprovePanelOpen] = useState(false);
  const [publishDialogOpen, setPublishDialogOpen] = useState(false);
  const [publishedSlug, setPublishedSlug] = useState<string | null>(null);
  const [assistantOpen, setAssistantOpen] = useState(false);

  // Refs to track the last array pushed from local → store,
  // so the store→local useEffect can skip when the store update originated locally.
  const lastLocalNodes = useRef<WorkflowNode[] | null>(null);
  const lastLocalEdges = useRef<WorkflowEdge[] | null>(null);

  // Sync React Flow states with store
  const [nodes, setNodes, onNodesChange] = useNodesState(store.nodes as Node[]);
  const [edges, setEdges, onEdgesChange] = useEdgesState(store.edges as Edge[]);

  // Sync from store → local (skip when the change originated from local → store)
  useEffect(() => {
    if (store.nodes === lastLocalNodes.current) return;
    setNodes(store.nodes as Node[]);
  }, [store.nodes, setNodes]);
  useEffect(() => {
    if (store.edges === lastLocalEdges.current) return;
    setEdges(store.edges as Edge[]);
  }, [store.edges, setEdges]);

  // Sync local → store on meaningful changes
  const handleNodesChange = useCallback(
    (changes: any[]) => {
      onNodesChange(changes);
      const meaningful = changes.some((c: any) => c.type !== 'select');
      if (meaningful) {
        setTimeout(() => {
          setNodes((prev: any) => {
            lastLocalNodes.current = prev;
            store.setNodes(prev);
            return prev;
          });
        }, 0);
      }
    },
    [onNodesChange, store, setNodes]
  );

  const handleEdgesChange = useCallback(
    (changes: any[]) => {
      onEdgesChange(changes);
      setTimeout(() => {
        setEdges((prev: any) => {
          lastLocalEdges.current = prev;
          store.setEdges(prev);
          return prev;
        });
      }, 0);
    },
    [onEdgesChange, store, setEdges]
  );

  const onConnect = useCallback(
    (params: Connection) => {
      store.pushHistory();
      setEdges((eds: any) => {
        const next = addEdge({ ...params, animated: true }, eds);
        lastLocalEdges.current = next;
        store.setEdges(next);
        return next;
      });
    },
    [setEdges, store]
  );

  const onNodeClick: NodeMouseHandler = useCallback(
    (_event, node) => {
      store.selectNode(node.id);
    },
    [store]
  );

  const onPaneClick = useCallback(() => {
    store.selectNode(null);
  }, [store]);

  // Load existing workflow
  useEffect(() => {
    if (!workflowId) {
      setIsLoading(false);
      return;
    }
    (async () => {
      try {
        const wf = await apiClient.getWorkflow(workflowId);
        const graph = normalizeWorkflowGraph((wf as any).graph_json);
        const tags = Array.isArray((wf as any).tags) ? (wf as any).tags : [];

        setMetadata({ id: wf.id, name: wf.name, description: wf.description || '', tags });
        setNodesInStore(graph.nodes);
        setEdgesInStore(graph.edges);
        setDirty(false);
        setPublishedSlug(wf.published_slug || null);
      } catch (err: any) {
        const status = err?.response?.status;
        const detail = err?.response?.data?.detail;
        if (status === 403) {
          toast.error('Sem permissão para acessar este workflow.');
        } else if (status === 404) {
          toast.error('Workflow não encontrado.');
        } else {
          toast.error('Erro ao carregar workflow');
        }
        // Keep a breadcrumb for debugging (API base, status, etc.)
        console.error('[WorkflowBuilder] getWorkflow failed', { status, detail, err });
      } finally {
        setIsLoading(false);
      }
    })();
    return () => {
      resetAll();
    };
  }, [
    workflowId,
    resetAll,
    setDirty,
    setEdgesInStore,
    setMetadata,
    setNodesInStore,
  ]);

  // ── Performance warning ───────────────────────────────────────
  useEffect(() => {
    if (store.nodes.length > 25) {
      toast.warning('Workflows com mais de 25 nós podem ter desempenho reduzido. Considere modularizar.', { id: 'perf-warning', duration: 5000 });
    }
  }, [store.nodes.length]);

  // ── Add node ───────────────────────────────────────────────────
  const addNode = useCallback(
    (type: string) => {
      const id = `${type}_${Date.now()}`;
      const defaultLabels: Record<string, string> = {
        trigger: 'Trigger',
        user_input: 'Input do Usuário',
        file_upload: 'Upload de Arquivo',
        selection: 'Seleção',
        condition: 'Condição',
        prompt: 'Prompt LLM',
        deep_research: 'Deep Research',
        claude_agent: 'Agente IA',
        parallel_agents: 'Agentes Paralelos',
        rag_search: 'Pesquisa RAG',
        human_review: 'Revisão Humana',
        tool_call: 'Chamada de Tool',
        legal_workflow: 'Gerar Minuta',
        review_table: 'Tabela de Revisão',
        output: 'Resposta Final',
        delivery: 'Entrega',
      };

      const newNode = {
        id,
        type,
        position: { x: 250 + Math.random() * 100, y: 100 + store.nodes.length * 120 },
        data: {
          label: defaultLabels[type] || type,
          ...(type === 'prompt' ? { model: 'claude-4.5-sonnet', prompt: '' } : {}),
          ...(type === 'deep_research' ? { mode: 'hard', effort: 'medium', provider: undefined, providers: ['gemini', 'perplexity', 'openai', 'rag_global', 'rag_local'], timeout_per_provider: 120, total_timeout: 300, search_focus: undefined, domain_filter: undefined, include_sources: true, query: '' } : {}),
          ...(type === 'rag_search' ? { limit: 10, sources: [] } : {}),
          ...(type === 'selection' ? { collects: 'selection', options: [] } : {}),
          ...(type === 'condition' ? { condition_field: 'selection', branches: {} } : {}),
          ...(type === 'human_review' ? { instructions: 'Revise o conteúdo e aprove.' } : {}),
          ...(type === 'claude_agent' ? { agent_type: 'claude-agent', model: 'claude-4.5-sonnet', system_prompt: '', tool_names: [], max_iterations: 10, max_tokens: 4096, include_mcp: false, use_sdk: true, enable_web_search: false, enable_deep_research: false, enable_code_execution: false } : {}),
          ...(type === 'parallel_agents' ? { prompts: [''], models: ['claude-4.5-sonnet'], tool_names: [], max_parallel: 3, aggregation_strategy: 'merge' } : {}),
          ...(type === 'tool_call' ? { tool_name: '' } : {}),
          ...(type === 'legal_workflow' ? { mode: 'minuta', models: ['claude-4.5-sonnet'], citation_style: 'abnt', auto_approve: false, thinking_level: 'medium' } : {}),
          ...(type === 'user_input' ? { input_type: 'text', collects: 'input', optional: false } : {}),
          ...(type === 'review_table' ? { columns: [], model: 'claude-sonnet-4-20250514', prompt_prefix: 'Extraia as seguintes informações de cada documento:' } : {}),
          ...(type === 'trigger' ? { trigger_type: 'webhook', trigger_config: {} } : {}),
          ...(type === 'delivery' ? { delivery_type: 'email', delivery_config: {} } : {}),
          ...(type === 'output' ? { sections: [], show_all: true } : {}),
        },
      };
      store.addNode(newNode as any);
    },
    [store]
  );

  // ── Save ───────────────────────────────────────────────────────
  const handleSave = useCallback(async () => {
    if (!store.name.trim()) {
      toast.error(`Defina um nome para o workflow`);
      return;
    }
    store.setSaving(true);
    try {
      const graphJson = { nodes: store.nodes, edges: store.edges };
      let savedWorkflowId = store.id;

      if (savedWorkflowId) {
        await apiClient.updateWorkflow(savedWorkflowId, {
          name: store.name,
          description: store.description || undefined,
          graph_json: graphJson,
          tags: store.tags,
        });
      } else {
        const created = await apiClient.createWorkflow({
          name: store.name,
          description: store.description || undefined,
          graph_json: graphJson,
          tags: store.tags,
        });
        savedWorkflowId = created.id;
        store.setMetadata({ id: created.id });
      }

      let triggerSyncFailed = false;
      if (savedWorkflowId) {
        const triggerNodes = graphJson.nodes.filter((node: any) => node?.type === `trigger` && node?.data);
        const scheduleTrigger = triggerNodes.find((node: any) => node.data?.trigger_type === `schedule`);
        const webhookTrigger = triggerNodes.find((node: any) => node.data?.trigger_type === `webhook`);

        try {
          if (scheduleTrigger) {
            const triggerConfig = scheduleTrigger.data?.trigger_config || {};
            const cronRaw = typeof triggerConfig.cron === `string` ? triggerConfig.cron.trim() : ``;
            const timezone =
              typeof triggerConfig.timezone === `string` && triggerConfig.timezone.trim()
                ? triggerConfig.timezone
                : `America/Sao_Paulo`;

            await apiClient.updateWorkflowSchedule(savedWorkflowId, {
              cron: cronRaw || null,
              enabled: Boolean(cronRaw),
              timezone,
            });
          } else {
            await apiClient.updateWorkflowSchedule(savedWorkflowId, {
              cron: null,
              enabled: false,
              timezone: `America/Sao_Paulo`,
            });
          }

          if (webhookTrigger) {
            await apiClient.ensureWorkflowWebhookSecret(savedWorkflowId);
          } else {
            await apiClient.disableWorkflowWebhook(savedWorkflowId);
          }
        } catch (triggerSyncError) {
          triggerSyncFailed = true;
          console.error(`[WorkflowBuilder] trigger sync failed`, triggerSyncError);
        }
      }

      store.setDirty(false);
      if (triggerSyncFailed) {
        toast.success(`Workflow salvo com pendencias na ativacao de triggers`);
      } else {
        toast.success(`Workflow salvo`);
      }
    } catch {
      toast.error(`Erro ao salvar`);
    } finally {
      store.setSaving(false);
    }
  }, [store]);

  // ── Run ────────────────────────────────────────────────────────
  const handleRun = useCallback(async () => {
    if (!store.id) {
      toast.error('Salve o workflow antes de executar');
      return;
    }
    store.startRun('');

    try {
      const response = await apiClient.runWorkflow(store.id, { input_data: {} });
      const reader = response.body?.getReader();
      if (!reader) {
        store.setRunStatus('error');
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

            store.addRunEvent({ type: evtType, data: evtData, timestamp: Date.now() });

            // Update run_id from first event
            if (evtData.run_id && !store.runId) {
              store.startRun(evtData.run_id);
            }

            // HIL detection
            if (evtData.status === 'paused_hil') {
              store.setHIL(evtData.node_id || '', evtData.instructions || '');
            }
            // Completion
            if (evtData.status === 'completed' || evtType === 'done') {
              store.setRunStatus('completed');
            }
            // Error
            if (evtData.error || evtType === 'error') {
              store.setRunStatus('error');
            }
          } catch { /* skip parse errors */ }
        }
      }

      // If stream ended without explicit status
      if (store.runStatus === 'running') {
        store.setRunStatus('completed');
      }
    } catch (err: any) {
      store.addRunEvent({ type: 'error', data: { error: err.message }, timestamp: Date.now() });
      store.setRunStatus('error');
    }
  }, [store]);

  // ── Keyboard shortcuts ──────────────────────────────────────
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      const tag = target.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || target.isContentEditable) return;

      const mod = e.metaKey || e.ctrlKey;

      if (mod && !e.shiftKey && e.key === 'z') {
        e.preventDefault();
        store.undo();
        return;
      }
      if ((mod && e.shiftKey && e.key === 'z') || (mod && e.key === 'y')) {
        e.preventDefault();
        store.redo();
        return;
      }
      if (mod && e.key === 's') {
        e.preventDefault();
        handleSave();
        return;
      }
      if (mod && e.key === 'c') {
        const count = store.nodes.filter((n) => n.selected).length;
        if (count > 0) {
          e.preventDefault();
          store.copySelected();
          toast.success(`${count} nó(s) copiado(s)`, { duration: 1500 });
        }
        return;
      }
      if (mod && e.key === 'v') {
        const clipCount = store.clipboardNodes?.length ?? 0;
        if (clipCount > 0) {
          e.preventDefault();
          store.paste();
          toast.success(`${clipCount} nó(s) colado(s)`, { duration: 1500 });
        }
        return;
      }
      if (e.key === 'Delete' || e.key === 'Backspace') {
        const count = store.nodes.filter((n) => n.selected).length;
        if (count > 0) {
          e.preventDefault();
          store.removeSelectedNodes();
          toast.success(`${count} nó(s) removido(s)`, { duration: 1500 });
        }
        return;
      }
    };

    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [store, handleSave]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="h-8 w-8 text-indigo-500 animate-spin" />
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Top bar */}
      <div className="flex items-center gap-3 px-4 py-2 border-b border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900">
        <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => window.history.back()}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <Input
          value={store.name}
          onChange={(e) => store.setMetadata({ name: e.target.value })}
          placeholder="Nome do Workflow"
          className="h-8 max-w-xs text-sm font-semibold border-none shadow-none focus-visible:ring-0 px-0"
        />
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8"
          disabled={(store.undoStack?.length ?? 0) === 0}
          onClick={() => store.undo()}
          title="Desfazer (Ctrl+Z)"
        >
          <Undo2 className="h-4 w-4" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8"
          disabled={(store.redoStack?.length ?? 0) === 0}
          onClick={() => store.redo()}
          title="Refazer (Ctrl+Shift+Z)"
        >
          <Redo2 className="h-4 w-4" />
        </Button>
        <EmbeddedFilesPanel />
        <Button
          variant="outline"
          size="sm"
          onClick={() => setNlDialogOpen(true)}
          className="gap-1.5 border-violet-300 dark:border-violet-700 text-violet-700 dark:text-violet-300 hover:bg-violet-50 dark:hover:bg-violet-950"
        >
          <Sparkles className="h-3.5 w-3.5" />
          Criar com IA
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={() => store.id && window.open(`/workflows/${store.id}/test`, '_blank')}
          disabled={!store.id}
          className="gap-1.5"
        >
          <FlaskConical className="h-3.5 w-3.5" />
          Testar
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={() => setImprovePanelOpen(true)}
          disabled={!store.id}
          className="gap-1.5 border-amber-300 dark:border-amber-700 text-amber-700 dark:text-amber-300 hover:bg-amber-50 dark:hover:bg-amber-950"
        >
          <Sparkles className="h-3.5 w-3.5" />
          Melhorar
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={() => setAssistantOpen(true)}
          className="gap-1.5 border-violet-300 dark:border-violet-700 text-violet-700 dark:text-violet-300 hover:bg-violet-50 dark:hover:bg-violet-950"
        >
          <MessageSquare className="h-3.5 w-3.5" />
          Assistente
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={() => setPublishDialogOpen(true)}
          disabled={!store.id}
          className={`gap-1.5 ${
            publishedSlug
              ? 'border-emerald-300 dark:border-emerald-700 text-emerald-700 dark:text-emerald-300 hover:bg-emerald-50 dark:hover:bg-emerald-950'
              : ''
          }`}
        >
          <Globe className="h-3.5 w-3.5" />
          {publishedSlug ? 'Publicado' : 'Publicar'}
        </Button>
        <div className="flex-1" />
        <Button
          variant="outline"
          size="sm"
          onClick={handleSave}
          disabled={store.isSaving || !store.isDirty}
          className="gap-1.5"
        >
          {store.isSaving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
          Salvar
        </Button>
        <Button
          size="sm"
          onClick={handleRun}
          disabled={store.isRunning || !store.id}
          className="gap-1.5 bg-emerald-600 hover:bg-emerald-500 text-white"
        >
          {store.isRunning ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
          Executar
        </Button>
      </div>

      <div className="flex flex-1 min-h-0">
        {/* Node palette sidebar */}
        <div className="w-14 border-r border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-950 flex flex-col items-center py-3 gap-2">
          {NODE_PALETTE.map((item) => (
            <button
              key={item.type}
              onClick={() => addNode(item.type)}
              title={item.label}
              className="h-10 w-10 rounded-lg flex items-center justify-center hover:bg-slate-200 dark:hover:bg-slate-800 transition-colors group"
            >
              <item.icon className="h-4.5 w-4.5 text-slate-500 group-hover:text-slate-800 dark:group-hover:text-slate-200" />
            </button>
          ))}
        </div>

        {/* Canvas */}
        <div ref={reactFlowWrapper} className="flex-1 relative">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={handleNodesChange}
            onEdgesChange={handleEdgesChange}
            onConnect={onConnect}
            onNodeClick={onNodeClick}
            onPaneClick={onPaneClick}
            nodeTypes={nodeTypes as any}
            fitView
            selectionOnDrag
            panOnDrag={[1, 2]}
            selectionMode={SelectionMode.Partial}
            multiSelectionKeyCode="Shift"
            className="bg-slate-50 dark:bg-slate-950"
          >
            <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="#e2e8f0" />
            <Controls className="!bg-white dark:!bg-slate-800 !border-slate-200 dark:!border-slate-700 !shadow-sm" />
            <MiniMap
              className="!bg-white dark:!bg-slate-800 !border-slate-200 dark:!border-slate-700"
              nodeColor="#818cf8"
              maskColor="rgba(0,0,0,0.08)"
            />
          </ReactFlow>
        </div>

        {/* Properties panel (node selected) or History panels (no node selected) */}
        {store.selectedNodeId ? (
          <PropertiesPanel />
        ) : store.id ? (
          <div className="w-72 border-l border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 overflow-y-auto p-3 space-y-3">
            <AuditTrail workflowId={store.id} />
            <VersionHistory
              workflowId={store.id}
              onRestore={() => window.location.reload()}
            />
          </div>
        ) : null}
      </div>

      {/* Run viewer */}
      <RunViewer />

      {/* NL to Graph dialog */}
      <NLInputDialog open={nlDialogOpen} onOpenChange={setNlDialogOpen} />

      {/* Improve panel */}
      {store.id && (
        <ImprovePanel
          workflowId={store.id}
          open={improvePanelOpen}
          onClose={() => setImprovePanelOpen(false)}
          onApplySuggestion={(nodeId, suggestedChange) => {
            store.updateNodeData(nodeId, { prompt: suggestedChange });
            store.setDirty(true);
          }}
        />
      )}

      {/* Contextual Assistant */}
      <AssistantPanel
        open={assistantOpen}
        onClose={() => setAssistantOpen(false)}
        contextType="workflow"
        contextId={store.id || null}
        contextLabel={store.name || 'Workflow'}
      />

      {/* Publish Dialog */}
      {store.id && (
        <PublishDialog
          open={publishDialogOpen}
          onClose={() => setPublishDialogOpen(false)}
          workflowId={store.id}
          workflowName={store.name}
          currentSlug={publishedSlug}
          onPublished={(slug) => setPublishedSlug(slug)}
          onUnpublished={() => setPublishedSlug(null)}
        />
      )}
    </div>
  );
}
