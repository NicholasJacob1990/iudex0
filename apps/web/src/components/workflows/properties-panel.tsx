'use client';

import React, { useEffect, useState, useCallback } from 'react';
import { X, FileText, Loader2, Globe, Folder, Scale, Search, Database, Pencil, Paperclip, Upload, Plus, Minus, Check, ChevronDown } from 'lucide-react';
import { useWorkflowOptions } from '@/hooks/use-workflow-options';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useWorkflowStore } from '@/stores/workflow-store';
import { apiClient } from '@/lib/api-client';
import { MODEL_REGISTRY, AGENT_REGISTRY } from '@/config/models';
import { VariableAutocomplete } from './variable-autocomplete';
import { PromptEditor } from './prompt-editor';
import { CorpusPickerModal } from './corpus-picker-modal';

const MODEL_OPTIONS = Object.values(MODEL_REGISTRY)
  .filter((m) => m.id !== 'internal-rag')
  .map((m) => ({ value: m.id, label: m.label, provider: m.provider }));

const LEGAL_MODE_OPTIONS = [
  { value: 'minuta', label: 'Minuta' },
  { value: 'parecer', label: 'Parecer' },
  { value: 'chat', label: 'Chat' },
  { value: 'analysis', label: 'Análise' },
];

const THINKING_LEVELS = [
  { value: 'low', label: 'Baixo' },
  { value: 'medium', label: 'Médio' },
  { value: 'high', label: 'Alto' },
];

const AGENT_OPTIONS = Object.values(AGENT_REGISTRY).map((a) => ({
  value: a.id,
  label: a.label,
  provider: a.provider,
  description: a.description,
  tooltip: a.tooltip,
}));

const AGGREGATION_OPTIONS = [
  { value: 'merge', label: 'Merge (juntar)' },
  { value: 'best', label: 'Best (melhor)' },
  { value: 'vote', label: 'Vote (votação)' },
];

// ── Template picker — loads templates from /models ────────────────────
function TemplatePicker({
  selectedId,
  onSelect,
  onClear,
}: {
  selectedId: string;
  onSelect: (id: string, name: string, content: string) => void;
  onClear: () => void;
}) {
  const [templates, setTemplates] = useState<Array<{ id: string; name: string; description: string }>>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);

  const fetchTemplates = async () => {
    if (templates.length > 0) {
      setOpen(true);
      return;
    }
    setLoading(true);
    try {
      const data = await apiClient.getTemplates(0, 100);
      const items = data.templates || data.items || data || [];
      setTemplates(Array.isArray(items) ? items : []);
      setOpen(true);
    } catch {
      setTemplates([]);
    } finally {
      setLoading(false);
    }
  };

  const selectedTemplate = templates.find((t) => t.id === selectedId);

  return (
    <div>
      <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">
        Template da biblioteca
      </label>
      {selectedId && selectedTemplate ? (
        <div className="flex items-center gap-2 p-2 rounded-lg bg-indigo-50 dark:bg-indigo-500/10 border border-indigo-200 dark:border-indigo-500/30">
          <FileText className="h-4 w-4 text-indigo-500 shrink-0" />
          <span className="text-xs font-medium text-indigo-700 dark:text-indigo-300 truncate flex-1">
            {selectedTemplate.name}
          </span>
          <button
            onClick={() => { onClear(); setOpen(false); }}
            className="text-slate-400 hover:text-red-500 transition-colors"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      ) : selectedId ? (
        <div className="flex items-center gap-2 p-2 rounded-lg bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700">
          <FileText className="h-4 w-4 text-slate-400 shrink-0" />
          <span className="text-xs text-slate-500 truncate flex-1">ID: {selectedId}</span>
          <button onClick={onClear} className="text-slate-400 hover:text-red-500">
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      ) : (
        <Button
          variant="outline"
          size="sm"
          className="w-full gap-1.5 text-xs"
          onClick={fetchTemplates}
          disabled={loading}
        >
          {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <FileText className="h-3.5 w-3.5" />}
          Selecionar da biblioteca
        </Button>
      )}

      {open && !selectedId && (
        <div className="mt-2 max-h-48 overflow-y-auto rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900">
          {templates.length === 0 ? (
            <p className="text-xs text-slate-400 p-3 text-center">Nenhum modelo encontrado</p>
          ) : (
            templates.map((t) => (
              <button
                key={t.id}
                onClick={() => {
                  onSelect(t.id, t.name, t.description || '');
                  setOpen(false);
                }}
                className="w-full text-left px-3 py-2 hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors border-b border-slate-100 dark:border-slate-800 last:border-0"
              >
                <p className="text-xs font-medium text-slate-700 dark:text-slate-300 truncate">{t.name}</p>
                {t.description && (
                  <p className="text-[10px] text-slate-400 truncate mt-0.5">
                    {t.description.slice(0, 80)}...
                  </p>
                )}
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
}

const SOURCE_ICONS: Record<string, React.ElementType> = {
  web_search: Globe,
  vault_file: FileText,
  vault_folder: Folder,
  legal_db: Scale,
  brazilian_legal: Scale,
  rag: Search,
  corpus: Database,
  pje: Scale,
  bnp: Scale,
};

interface EmbeddedFileInfo {
  id: string;
  name: string;
  size: number;
  mime_type: string;
}

export function PropertiesPanel() {
  const { nodes, selectedNodeId, updateNodeData, selectNode, removeNode } = useWorkflowStore();
  const workflowId = useWorkflowStore((s) => s.id);
  const node = nodes.find((n) => n.id === selectedNodeId);
  const [corpusModalOpen, setCorpusModalOpen] = useState(false);
  const [editingCorpusIdx, setEditingCorpusIdx] = useState<number | null>(null);

  // Embedded files state
  const [embeddedFiles, setEmbeddedFiles] = useState<EmbeddedFileInfo[]>([]);
  const [embeddedFilesLoaded, setEmbeddedFilesLoaded] = useState(false);
  const [isUploadingEmbedded, setIsUploadingEmbedded] = useState(false);

  // Tools & models from API + registry
  const {
    tools: availableTools,
    toolsByCategory,
    gatewayTools,
    gatewayToolsByCategory,
    modelsByProvider,
    isLoading: toolsLoading,
  } = useWorkflowOptions();

  const loadEmbeddedFiles = useCallback(async () => {
    if (!workflowId || embeddedFilesLoaded) return;
    try {
      const resp = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/workflows/${workflowId}/files`,
        { headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` } }
      );
      if (resp.ok) {
        const respData = await resp.json();
        setEmbeddedFiles(respData.files || []);
      }
    } catch { /* ignore */ }
    setEmbeddedFilesLoaded(true);
  }, [workflowId, embeddedFilesLoaded]);

  useEffect(() => {
    if (workflowId && !embeddedFilesLoaded) loadEmbeddedFiles();
  }, [workflowId, embeddedFilesLoaded, loadEmbeddedFiles]);

  const handleEmbeddedFileUpload = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!workflowId || !e.target.files?.length) return;
    setIsUploadingEmbedded(true);
    try {
      for (const file of Array.from(e.target.files)) {
        const formData = new FormData();
        formData.append('file', file);
        const resp = await fetch(
          `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/workflows/${workflowId}/files`,
          {
            method: 'POST',
            headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` },
            body: formData,
          }
        );
        if (resp.ok) {
          const respData = await resp.json();
          setEmbeddedFiles((prev) => [...prev, respData.file]);
        } else {
          toast.error(`Erro ao enviar ${file.name}`);
        }
      }
      toast.success('Arquivo(s) enviado(s)');
    } catch {
      toast.error('Erro ao enviar arquivo');
    } finally {
      setIsUploadingEmbedded(false);
      e.target.value = '';
    }
  }, [workflowId]);

  const removeEmbeddedFile = useCallback(async (fileId: string) => {
    if (!workflowId) return;
    try {
      const resp = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/workflows/${workflowId}/files/${fileId}`,
        {
          method: 'DELETE',
          headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` },
        }
      );
      if (resp.ok) {
        setEmbeddedFiles((prev) => prev.filter((f) => f.id !== fileId));
        toast.success('Arquivo removido');
      }
    } catch {
      toast.error('Erro ao remover');
    }
  }, [workflowId]);

  if (!node) return null;

  const data = node.data;
  const nodeType = node.type;

  const update = (key: string, value: any) => {
    updateNodeData(node.id, { [key]: value });
  };

  // ---------------------------------------------------------------------------
  // Tool-call helpers (JSON args + ask_graph preset)
  // ---------------------------------------------------------------------------

  const safeParseJsonObject = (raw: string): Record<string, any> | null => {
    try {
      const parsed = JSON.parse(raw);
      return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? (parsed as Record<string, any>) : null;
    } catch {
      return null;
    }
  };

  const buildArgsText = (obj: Record<string, any>) => {
    try {
      return JSON.stringify(obj, null, 2);
    } catch {
      return '';
    }
  };

  const getToolCallArgs = (): Record<string, any> => {
    if (data && typeof (data as any).arguments === 'object' && (data as any).arguments && !Array.isArray((data as any).arguments)) {
      return (data as any).arguments as Record<string, any>;
    }
    if (typeof (data as any).tool_input === 'string' && (data as any).tool_input.trim()) {
      return safeParseJsonObject((data as any).tool_input) || {};
    }
    if (data && typeof (data as any).tool_input === 'object' && (data as any).tool_input && !Array.isArray((data as any).tool_input)) {
      return (data as any).tool_input as Record<string, any>;
    }
    return {};
  };

  const setToolCallArgs = (obj: Record<string, any>) => {
    update('arguments', obj);
    // Keep legacy field as the raw editor backing store.
    update('tool_input', buildArgsText(obj));
  };

  const ASK_GRAPH_OPERATIONS: Array<{ value: string; label: string }> = [
    { value: 'search', label: 'search (Buscar entidades)' },
    { value: 'path', label: 'path (Caminho entre entidades)' },
    { value: 'neighbors', label: 'neighbors (Vizinhos semânticos)' },
    { value: 'cooccurrence', label: 'cooccurrence (Co-ocorrência)' },
    { value: 'count', label: 'count (Contagem)' },
    { value: 'discover_hubs', label: 'discover_hubs (Hubs)' },
    { value: 'legal_chain', label: 'legal_chain (Cadeia legal)' },
    { value: 'precedent_network', label: 'precedent_network (Rede de precedentes)' },
    { value: 'related_entities', label: 'related_entities (Arestas diretas)' },
    { value: 'entity_stats', label: 'entity_stats (Estatísticas)' },
    { value: 'text2cypher', label: 'text2cypher (Pergunta -> Cypher RO)' },
    { value: 'betweenness_centrality', label: 'betweenness_centrality (GDS)' },
    { value: 'community_detection', label: 'community_detection (GDS)' },
    { value: 'node_similarity', label: 'node_similarity (GDS)' },
    { value: 'pagerank_personalized', label: 'pagerank_personalized (GDS)' },
    { value: 'shortest_path_weighted', label: 'shortest_path_weighted (GDS)' },
    { value: 'degree_centrality', label: 'degree_centrality (GDS)' },
    { value: 'closeness_centrality', label: 'closeness_centrality (GDS)' },
    { value: 'eigenvector_centrality', label: 'eigenvector_centrality (GDS)' },
    { value: 'leiden', label: 'leiden (GDS)' },
    { value: 'k_core_decomposition', label: 'k_core_decomposition (GDS)' },
    { value: 'knn', label: 'knn (GDS)' },
    { value: 'adamic_adar', label: 'adamic_adar (GDS)' },
    { value: 'node2vec', label: 'node2vec (GDS)' },
    { value: 'harmonic_centrality', label: 'harmonic_centrality (GDS)' },
    { value: 'yens_k_shortest_paths', label: 'yens_k_shortest_paths (GDS)' },
    { value: 'link_entities', label: 'link_entities (Escrita no grafo, requer preflight)' },
  ];

  const ENTITY_TYPES = ['lei', 'artigo', 'sumula', 'tema', 'tribunal', 'tese', 'conceito', 'principio', 'instituto'] as const;

  const toolCallArgs = nodeType === 'tool_call' ? getToolCallArgs() : {};
  const askGraphOp = (toolCallArgs.operation as string) || 'search';
  const askGraphParams =
    toolCallArgs.params && typeof toolCallArgs.params === 'object' && !Array.isArray(toolCallArgs.params)
      ? (toolCallArgs.params as Record<string, any>)
      : {};

  const setAskGraph = (patch: { operation?: string; params?: Record<string, any>; scope?: string; include_global?: boolean }) => {
    const next = {
      ...toolCallArgs,
      ...(patch.operation ? { operation: patch.operation } : {}),
      ...(patch.scope !== undefined ? { scope: patch.scope || undefined } : {}),
      ...(patch.include_global !== undefined ? { include_global: !!patch.include_global } : {}),
      params: patch.params ? patch.params : askGraphParams,
    };
    setToolCallArgs(next);
  };

  return (
    <div className="w-80 border-l border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-4 overflow-y-auto flex flex-col gap-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-200">Propriedades</h3>
        <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => selectNode(null)}>
          <X className="h-4 w-4" />
        </Button>
      </div>

      {/* Label */}
      <div>
        <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">Nome</label>
        <Input
          value={data.label || ''}
          onChange={(e) => update('label', e.target.value)}
          placeholder="Nome do nó"
          className="h-8 text-sm"
        />
      </div>

      {/* Description */}
      <div>
        <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">Descrição</label>
        <textarea
          value={data.description || ''}
          onChange={(e) => update('description', e.target.value)}
          placeholder="Descrição opcional"
          rows={2}
          className="w-full rounded-md border border-slate-200 dark:border-slate-700 bg-transparent px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
        />
      </div>

      {/* Optional Step Toggle — for input-type nodes */}
      {['file_upload', 'selection'].includes(nodeType!) && (
        <div className="border-b border-slate-200 dark:border-slate-700 pb-3 mb-3">
          <div className="flex items-center justify-between">
            <label className="text-xs font-medium text-slate-500">Passo Opcional</label>
            <button
              onClick={() => update('optional', !data.optional)}
              className={`relative w-9 h-5 rounded-full transition-colors ${
                data.optional ? 'bg-amber-500' : 'bg-slate-300 dark:bg-slate-600'
              }`}
            >
              <span className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white transition-transform ${
                data.optional ? 'translate-x-4' : ''
              }`} />
            </button>
          </div>
          {data.optional && (
            <div className="mt-2">
              <label className="text-xs text-slate-400 mb-1 block">Template padrao (quando nao preenchido)</label>
              <textarea
                value={data.default_template || ''}
                onChange={(e) => update('default_template', e.target.value)}
                placeholder="Valor padrao quando o usuario nao fornecer entrada..."
                className="w-full h-16 rounded-md border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-2 py-1.5 text-xs resize-none"
              />
            </div>
          )}
        </div>
      )}

      {/* Type-specific fields */}
      {nodeType === 'prompt' && (
        <>
          <div>
            <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">Modelo</label>
            <select
              value={data.model || 'claude-4.5-sonnet'}
              onChange={(e) => update('model', e.target.value)}
              className="w-full h-8 rounded-md border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-2 text-sm"
            >
              {(['anthropic', 'openai', 'google', 'xai', 'perplexity', 'openrouter'] as const).map((provider) => {
                const group = MODEL_OPTIONS.filter((m) => m.provider === provider);
                if (!group.length) return null;
                const labels: Record<string, string> = { anthropic: 'Anthropic', openai: 'OpenAI', google: 'Google', xai: 'xAI', perplexity: 'Perplexity', openrouter: 'Meta / OpenRouter' };
                return (
                  <optgroup key={provider} label={labels[provider] || provider}>
                    {group.map((m) => (
                      <option key={m.value} value={m.value}>{m.label}</option>
                    ))}
                  </optgroup>
                );
              })}
            </select>
          </div>
          <div>
            <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">Prompt Template</label>
            <PromptEditor
              value={data.prompt || ''}
              onChange={(val) => update('prompt', val)}
              currentNodeId={node.id}
              placeholder="Escreva o prompt... Use {{ ou @ para referenciar outros nos"
              rows={6}
            />
          </div>
          {/* Knowledge Sources */}
          <div className="pt-3 border-t border-slate-200 dark:border-slate-700 space-y-2">
            <div className="flex items-center justify-between">
              <label className="text-xs font-semibold text-slate-600 dark:text-slate-300 block">
                Fontes de Conhecimento
              </label>
              <span className={`text-[10px] font-medium ${(data.knowledge_sources || []).length >= 2 ? 'text-amber-500' : 'text-slate-400'}`}>
                {(data.knowledge_sources || []).length} / 2
              </span>
            </div>
            {(data.knowledge_sources || []).length >= 2 && (
              <div className="bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800 rounded-md px-2.5 py-1.5 text-[10px] text-amber-700 dark:text-amber-400">
                Máximo de 2 fontes atingido
              </div>
            )}
            <div className="space-y-1.5">
              {(data.knowledge_sources || []).map((src: any, idx: number) => {
                const IconComp = SOURCE_ICONS[src.type] || Search;
                const label = src.type === 'web_search'
                  ? 'Web Search'
                  : src.type === 'vault_file'
                    ? (src.label || 'Arquivo')
                    : src.type === 'vault_folder'
                      ? (src.label || 'Pasta')
                      : src.type === 'legal_db'
                        ? (src.db_type === 'legislation' ? 'Legislação' : 'Jurisprudência')
                        : src.type === 'brazilian_legal'
                          ? (src.label || 'Bases Jurídicas BR')
                          : src.type === 'rag'
                            ? 'RAG Search'
                            : src.type === 'corpus'
                              ? (src.label || 'Corpus')
                              : src.type === 'pje'
                                ? (src.label || 'PJe')
                                : src.type === 'bnp'
                                  ? (src.label || 'BNP (Precedentes)')
                                  : src.type;
                return (
                  <div
                    key={idx}
                    className="flex items-center gap-2 bg-slate-50 dark:bg-slate-800 rounded-md px-2.5 py-1.5 text-xs transition-all duration-200"
                  >
                    <IconComp className="h-3.5 w-3.5 text-slate-400 shrink-0" />
                    <span className="flex-1 truncate">{label}</span>
                    {src.type === 'corpus' && (
                      <button
                        onClick={() => {
                          setEditingCorpusIdx(idx);
                          setCorpusModalOpen(true);
                        }}
                        className="text-slate-400 hover:text-blue-500 transition-colors"
                        title="Editar"
                      >
                        <Pencil className="h-3 w-3" />
                      </button>
                    )}
                    <button
                      onClick={() => {
                        const sources = [...(data.knowledge_sources || [])];
                        sources.splice(idx, 1);
                        update('knowledge_sources', sources);
                      }}
                      className="text-red-400 hover:text-red-600 text-xs transition-colors"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </div>
                );
              })}
            </div>
            {(data.knowledge_sources || []).length < 2 && (
              <select
                value=""
                onChange={(e) => {
                  if (!e.target.value) return;
                  const sources = [...(data.knowledge_sources || [])];
                  const type = e.target.value;
                  if (type === 'web_search') {
                    sources.push({ type: 'web_search' });
                  } else if (type === 'jurisprudence') {
                    sources.push({ type: 'legal_db', db_type: 'jurisprudence', label: 'Jurisprudência' });
                  } else if (type === 'legislation') {
                    sources.push({ type: 'legal_db', db_type: 'legislation', label: 'Legislação' });
                  } else if (type === 'rag') {
                    sources.push({ type: 'rag', label: 'RAG Search' });
                  } else if (type === 'brazilian_legal') {
                    sources.push({
                      type: 'brazilian_legal',
                      databases: ['stf', 'stj', 'legislacao'],
                      limit: 5,
                      label: 'Bases Jurídicas BR',
                    } as any);
                  } else if (type === 'pje') {
                    sources.push({
                      type: 'pje',
                      mode: 'auto',
                      label: 'PJe (TecJustiça)',
                    } as any);
                  } else if (type === 'bnp') {
                    sources.push({
                      type: 'bnp',
                      tipo: 'todos',
                      limit: 10,
                      label: 'BNP (Precedentes)',
                    } as any);
                  } else if (type === 'corpus') {
                    setEditingCorpusIdx(null);
                    setCorpusModalOpen(true);
                    e.target.value = '';
                    return;
                  }
                  update('knowledge_sources', sources);
                  e.target.value = '';
                }}
                className="w-full h-8 rounded-md border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-2 text-xs"
              >
                <option value="">+ Adicionar fonte...</option>
                <option value="web_search">Web Search</option>
                <option value="jurisprudence">Jurisprudência</option>
                <option value="legislation">Legislação</option>
                <option value="rag">RAG / Knowledge Base</option>
                <option value="brazilian_legal">Bases Jurídicas BR (STF/STJ/Legislação)</option>
                <option value="pje">PJe (Processo Judicial Eletrônico)</option>
                <option value="bnp">BNP (Precedentes Qualificados)</option>
                <option value="corpus">Corpus (Busca Híbrida)</option>
              </select>
            )}
            <p className="text-[10px] text-slate-400">
              Fontes carregadas em runtime e injetadas como contexto no prompt.
            </p>
            <CorpusPickerModal
              open={corpusModalOpen}
              onClose={() => { setCorpusModalOpen(false); setEditingCorpusIdx(null); }}
              initialCollections={editingCorpusIdx !== null ? ((data.knowledge_sources?.[editingCorpusIdx] as any)?.collections || []) : []}
              initialScope={editingCorpusIdx !== null ? ((data.knowledge_sources?.[editingCorpusIdx] as any)?.scope || 'global') : 'global'}
              onConfirm={(config) => {
                const sources = [...(data.knowledge_sources || [])];
                if (editingCorpusIdx !== null) {
                  sources[editingCorpusIdx] = config;
                } else {
                  if (sources.length >= 2) return; // Enforce max 2 sources
                  sources.push(config);
                }
                update('knowledge_sources', sources);
                setCorpusModalOpen(false);
                setEditingCorpusIdx(null);
              }}
            />
          </div>
        </>
      )}

      {nodeType === 'deep_research' && (
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">Modo</label>
              <select
                value={data.mode || 'hard'}
                onChange={(e) => update('mode', e.target.value)}
                className="w-full h-8 rounded-md border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-2 text-sm"
              >
                <option value="hard">hard (multi-provider + agent)</option>
                <option value="normal">normal</option>
              </select>
            </div>
            <div>
              <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">Effort</label>
              <select
                value={data.effort || 'medium'}
                onChange={(e) => update('effort', e.target.value)}
                className="w-full h-8 rounded-md border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-2 text-sm"
              >
                <option value="low">low</option>
                <option value="medium">medium</option>
                <option value="high">high</option>
              </select>
            </div>
          </div>

          {(data.mode || 'hard') !== 'hard' && (
            <div>
              <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">Provider (opcional)</label>
              <select
                value={data.provider || ''}
                onChange={(e) => update('provider', e.target.value || undefined)}
                className="w-full h-8 rounded-md border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-2 text-sm"
              >
                <option value="">auto</option>
                <option value="openai">openai</option>
                <option value="perplexity">perplexity</option>
                <option value="google">google</option>
              </select>
            </div>
          )}

          {(data.mode || 'hard') === 'hard' && (
            <>
              <div>
                <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">Providers</label>
                <div className="grid grid-cols-2 gap-2 rounded-md border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-2">
                  {['gemini', 'perplexity', 'openai', 'rag_global', 'rag_local'].map((p) => {
                    const checked = Array.isArray(data.providers) ? data.providers.includes(p) : false;
                    return (
                      <label key={p} className="flex items-center gap-2 text-xs text-slate-700 dark:text-slate-300 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={() => {
                            const current = Array.isArray(data.providers) ? [...data.providers] : [];
                            if (checked) {
                              update('providers', current.filter((x) => x !== p));
                            } else {
                              update('providers', [...current, p]);
                            }
                          }}
                          className="rounded border-slate-300 text-emerald-600"
                        />
                        <span className="truncate">{p}</span>
                      </label>
                    );
                  })}
                </div>
                <p className="text-[10px] text-slate-400 mt-1">
                  Dica: quanto mais providers, maior latência e custo.
                </p>
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">Timeout/prov (s)</label>
                  <Input
                    type="number"
                    value={data.timeout_per_provider ?? 120}
                    onChange={(e) => update('timeout_per_provider', parseInt(e.target.value || '0', 10) || 120)}
                    min={10}
                    max={900}
                    className="h-8 text-sm"
                  />
                </div>
                <div>
                  <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">Timeout total (s)</label>
                  <Input
                    type="number"
                    value={data.total_timeout ?? 300}
                    onChange={(e) => update('total_timeout', parseInt(e.target.value || '0', 10) || 300)}
                    min={30}
                    max={3600}
                    className="h-8 text-sm"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">search_focus (opcional)</label>
                  <Input
                    value={data.search_focus || ''}
                    onChange={(e) => update('search_focus', e.target.value || undefined)}
                    placeholder="ex: jurisprudencia"
                    className="h-8 text-sm"
                  />
                </div>
                <div>
                  <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">domain_filter (opcional)</label>
                  <Input
                    value={data.domain_filter || ''}
                    onChange={(e) => update('domain_filter', e.target.value || undefined)}
                    placeholder="ex: stf.jus.br"
                    className="h-8 text-sm"
                  />
                </div>
              </div>
            </>
          )}

          <div>
            <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">Query</label>
            <PromptEditor
              value={data.query || ''}
              onChange={(val) => update('query', val)}
              currentNodeId={node.id}
              placeholder="Descreva o tema e (opcionalmente) instruções de formato. Use {{user_input_1}} ou @variáveis."
              rows={8}
            />
          </div>

          <div className="flex items-center justify-between">
            <label className="text-xs text-slate-600 dark:text-slate-400">Incluir fontes (citations)</label>
            <button
              onClick={() => update('include_sources', data.include_sources === false ? true : false)}
              className={`relative w-9 h-5 rounded-full transition-colors ${
                data.include_sources !== false ? 'bg-emerald-500' : 'bg-slate-300 dark:bg-slate-600'
              }`}
            >
              <span
                className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white transition-transform ${
                  data.include_sources !== false ? 'translate-x-4' : ''
                }`}
              />
            </button>
          </div>
        </div>
      )}

      {nodeType === 'rag_search' && (
        <>
          <div>
            <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">Limite de resultados</label>
            <Input
              type="number"
              value={data.limit || 10}
              onChange={(e) => update('limit', parseInt(e.target.value) || 10)}
              min={1}
              max={50}
              className="h-8 text-sm"
            />
          </div>
          <div>
            <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">Fontes (uma por linha)</label>
            <textarea
              value={(data.sources || []).join('\n')}
              onChange={(e) => update('sources', e.target.value.split('\n').filter(Boolean))}
              placeholder="jurisprudencia&#10;legislacao&#10;doutrina"
              rows={3}
              className="w-full rounded-md border border-slate-200 dark:border-slate-700 bg-transparent px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
            />
          </div>
        </>
      )}

      {nodeType === 'selection' && (
        <>
          <div>
            <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">Campo</label>
            <Input
              value={data.collects || 'selection'}
              onChange={(e) => update('collects', e.target.value)}
              className="h-8 text-sm"
            />
          </div>
          <div>
            <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">Opções (uma por linha)</label>
            <textarea
              value={(data.options || []).join('\n')}
              onChange={(e) => update('options', e.target.value.split('\n').filter(Boolean))}
              placeholder="Opção A&#10;Opção B&#10;Opção C"
              rows={4}
              className="w-full rounded-md border border-slate-200 dark:border-slate-700 bg-transparent px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
            />
          </div>
        </>
      )}

      {nodeType === 'condition' && (
        <>
          <div>
            <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">Campo de condição</label>
            <Input
              value={data.condition_field || 'selection'}
              onChange={(e) => update('condition_field', e.target.value)}
              className="h-8 text-sm"
            />
          </div>
          <div>
            <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">
              Ramos (valor=nó_destino, um por linha)
            </label>
            <textarea
              value={
                data.branches
                  ? Object.entries(data.branches)
                      .map(([k, v]) => `${k}=${v}`)
                      .join('\n')
                  : ''
              }
              onChange={(e) => {
                const branches: Record<string, string> = {};
                e.target.value.split('\n').filter(Boolean).forEach((line) => {
                  const [k, ...rest] = line.split('=');
                  if (k && rest.length) branches[k.trim()] = rest.join('=').trim();
                });
                update('branches', branches);
              }}
              placeholder="sim=node_1&#10;nao=node_2"
              rows={4}
              className="w-full rounded-md border border-slate-200 dark:border-slate-700 bg-transparent px-3 py-2 text-sm font-mono resize-none focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
            />
          </div>
        </>
      )}

      {nodeType === 'human_review' && (
        <div>
          <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">Instruções</label>
          <textarea
            value={data.instructions || ''}
            onChange={(e) => update('instructions', e.target.value)}
            placeholder="Revise o conteúdo e aprove."
            rows={3}
            className="w-full rounded-md border border-slate-200 dark:border-slate-700 bg-transparent px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
          />
        </div>
      )}

      {nodeType === 'tool_call' && (
        <div className="space-y-3">
          <div>
            <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">Tool</label>
            {toolsLoading ? (
              <div className="flex items-center gap-2 text-xs text-slate-400 py-2">
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Carregando tools...
              </div>
            ) : gatewayTools.length > 0 ? (
              <select
                value={data.tool_name || ''}
                onChange={(e) => update('tool_name', e.target.value)}
                className="w-full h-8 rounded-md border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-2 text-sm"
              >
                <option value="">Selecione uma tool...</option>
                {gatewayToolsByCategory.map((group) => (
                  <optgroup key={group.category} label={group.category.toUpperCase()}>
                    {group.tools.map((t) => (
                      <option key={t.value} value={t.value}>{t.label}</option>
                    ))}
                  </optgroup>
                ))}
              </select>
            ) : (
              <Input
                value={data.tool_name || ''}
                onChange={(e) => update('tool_name', e.target.value)}
                placeholder="search_jurisprudencia"
                className="h-8 text-sm"
              />
            )}
            {data.tool_name && gatewayTools.find((t) => t.value === data.tool_name)?.description && (
              <p className="text-[10px] text-slate-400 mt-1">
                {gatewayTools.find((t) => t.value === data.tool_name)!.description.slice(0, 120)}
              </p>
            )}
          </div>

          {/* ask_graph preset */}
          {data.tool_name === 'ask_graph' && (
            <div className="space-y-2 rounded-md border border-slate-200 dark:border-slate-700 bg-slate-50/60 dark:bg-slate-800/40 p-3">
              <div className="flex items-center justify-between">
                <p className="text-[10px] font-semibold text-slate-500 dark:text-slate-400 uppercase">ask_graph preset</p>
                <button
                  className="text-[10px] text-slate-500 hover:text-slate-700 dark:hover:text-slate-300"
                  onClick={() => setToolCallArgs({ operation: 'search', params: { query: '', limit: 20 } })}
                  type="button"
                >
                  Reset
                </button>
              </div>

              <div>
                <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">Operação</label>
                <select
                  value={askGraphOp}
                  onChange={(e) => setAskGraph({ operation: e.target.value, params: {} })}
                  className="w-full h-8 rounded-md border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 px-2 text-sm"
                >
                  {ASK_GRAPH_OPERATIONS.map((op) => (
                    <option key={op.value} value={op.value}>{op.label}</option>
                  ))}
                </select>
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">Scope</label>
                  <select
                    value={(toolCallArgs.scope as string) || ''}
                    onChange={(e) => setAskGraph({ scope: e.target.value })}
                    className="w-full h-8 rounded-md border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 px-2 text-sm"
                  >
                    <option value="">(padrão)</option>
                    <option value="private">private</option>
                    <option value="local">local</option>
                    <option value="group">group</option>
                    <option value="global">global</option>
                  </select>
                </div>
                <div className="flex items-end justify-between gap-2">
                  <label className="text-xs text-slate-600 dark:text-slate-400">include_global</label>
                  <input
                    type="checkbox"
                    checked={toolCallArgs.include_global !== false}
                    onChange={(e) => setAskGraph({ include_global: e.target.checked })}
                    className="h-4 w-4 rounded border-slate-300"
                  />
                </div>
              </div>

              {/* Params by operation */}
              {askGraphOp === 'search' && (
                <div className="grid grid-cols-2 gap-2">
                  <div className="col-span-2">
                    <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">query</label>
                    <Input
                      value={askGraphParams.query || ''}
                      onChange={(e) => setAskGraph({ params: { ...askGraphParams, query: e.target.value } })}
                      className="h-8 text-sm"
                    />
                  </div>
                  <div>
                    <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">entity_type</label>
                    <select
                      value={askGraphParams.entity_type || ''}
                      onChange={(e) => setAskGraph({ params: { ...askGraphParams, entity_type: e.target.value || undefined } })}
                      className="w-full h-8 rounded-md border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 px-2 text-sm"
                    >
                      <option value="">(qualquer)</option>
                      {ENTITY_TYPES.map((t) => (
                        <option key={t} value={t}>{t}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">limit</label>
                    <Input
                      type="number"
                      value={askGraphParams.limit ?? 20}
                      onChange={(e) => setAskGraph({ params: { ...askGraphParams, limit: parseInt(e.target.value || '0', 10) || 20 } })}
                      className="h-8 text-sm"
                    />
                  </div>
                </div>
              )}

              {askGraphOp === 'path' && (
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">source_id</label>
                    <Input
                      value={askGraphParams.source_id || ''}
                      onChange={(e) => setAskGraph({ params: { ...askGraphParams, source_id: e.target.value } })}
                      className="h-8 text-sm"
                    />
                  </div>
                  <div>
                    <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">target_id</label>
                    <Input
                      value={askGraphParams.target_id || ''}
                      onChange={(e) => setAskGraph({ params: { ...askGraphParams, target_id: e.target.value } })}
                      className="h-8 text-sm"
                    />
                  </div>
                  <div>
                    <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">max_hops</label>
                    <Input
                      type="number"
                      value={askGraphParams.max_hops ?? 4}
                      onChange={(e) => setAskGraph({ params: { ...askGraphParams, max_hops: parseInt(e.target.value || '0', 10) || 4 } })}
                      className="h-8 text-sm"
                    />
                  </div>
                  <div>
                    <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">limit</label>
                    <Input
                      type="number"
                      value={askGraphParams.limit ?? 5}
                      onChange={(e) => setAskGraph({ params: { ...askGraphParams, limit: parseInt(e.target.value || '0', 10) || 5 } })}
                      className="h-8 text-sm"
                    />
                  </div>
                </div>
              )}

              {askGraphOp === 'neighbors' && (
                <div className="grid grid-cols-2 gap-2">
                  <div className="col-span-2">
                    <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">entity_id</label>
                    <Input
                      value={askGraphParams.entity_id || ''}
                      onChange={(e) => setAskGraph({ params: { ...askGraphParams, entity_id: e.target.value } })}
                      className="h-8 text-sm"
                    />
                  </div>
                  <div>
                    <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">limit</label>
                    <Input
                      type="number"
                      value={askGraphParams.limit ?? 20}
                      onChange={(e) => setAskGraph({ params: { ...askGraphParams, limit: parseInt(e.target.value || '0', 10) || 20 } })}
                      className="h-8 text-sm"
                    />
                  </div>
                </div>
              )}

              {askGraphOp === 'cooccurrence' && (
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">entity1_id</label>
                    <Input
                      value={askGraphParams.entity1_id || ''}
                      onChange={(e) => setAskGraph({ params: { ...askGraphParams, entity1_id: e.target.value } })}
                      className="h-8 text-sm"
                    />
                  </div>
                  <div>
                    <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">entity2_id</label>
                    <Input
                      value={askGraphParams.entity2_id || ''}
                      onChange={(e) => setAskGraph({ params: { ...askGraphParams, entity2_id: e.target.value } })}
                      className="h-8 text-sm"
                    />
                  </div>
                </div>
              )}

              {askGraphOp === 'count' && (
                <div className="grid grid-cols-2 gap-2">
                  <div className="col-span-2">
                    <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">query (opcional)</label>
                    <Input
                      value={askGraphParams.query || ''}
                      onChange={(e) => setAskGraph({ params: { ...askGraphParams, query: e.target.value || undefined } })}
                      className="h-8 text-sm"
                    />
                  </div>
                  <div>
                    <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">entity_type</label>
                    <select
                      value={askGraphParams.entity_type || ''}
                      onChange={(e) => setAskGraph({ params: { ...askGraphParams, entity_type: e.target.value || undefined } })}
                      className="w-full h-8 rounded-md border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 px-2 text-sm"
                    >
                      <option value="">(qualquer)</option>
                      {ENTITY_TYPES.map((t) => (
                        <option key={t} value={t}>{t}</option>
                      ))}
                    </select>
                  </div>
                </div>
              )}

              {askGraphOp === 'discover_hubs' && (
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">top_n</label>
                    <Input
                      type="number"
                      value={askGraphParams.top_n ?? 20}
                      onChange={(e) => setAskGraph({ params: { ...askGraphParams, top_n: parseInt(e.target.value || '0', 10) || 20 } })}
                      className="h-8 text-sm"
                    />
                  </div>
                </div>
              )}

              {askGraphOp === 'text2cypher' && (
                <div>
                  <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">question</label>
                  <textarea
                    value={askGraphParams.question || ''}
                    onChange={(e) => setAskGraph({ params: { ...askGraphParams, question: e.target.value } })}
                    rows={3}
                    className="w-full rounded-md border border-slate-200 dark:border-slate-700 bg-transparent px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
                  />
                </div>
              )}

              {(askGraphOp === 'legal_chain' || askGraphOp === 'shortest_path_weighted' || askGraphOp === 'yens_k_shortest_paths') && (
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">source_id</label>
                    <Input
                      value={askGraphParams.source_id || ''}
                      onChange={(e) => setAskGraph({ params: { ...askGraphParams, source_id: e.target.value } })}
                      className="h-8 text-sm"
                    />
                  </div>
                  <div>
                    <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">target_id</label>
                    <Input
                      value={askGraphParams.target_id || ''}
                      onChange={(e) => setAskGraph({ params: { ...askGraphParams, target_id: e.target.value } })}
                      className="h-8 text-sm"
                    />
                  </div>
                  {askGraphOp === 'legal_chain' && (
                    <>
                      <div>
                        <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">max_hops</label>
                        <Input
                          type="number"
                          value={askGraphParams.max_hops ?? 4}
                          onChange={(e) => setAskGraph({ params: { ...askGraphParams, max_hops: parseInt(e.target.value || '0', 10) || 4 } })}
                          className="h-8 text-sm"
                        />
                      </div>
                      <div>
                        <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">limit</label>
                        <Input
                          type="number"
                          value={askGraphParams.limit ?? 20}
                          onChange={(e) => setAskGraph({ params: { ...askGraphParams, limit: parseInt(e.target.value || '0', 10) || 20 } })}
                          className="h-8 text-sm"
                        />
                      </div>
                    </>
                  )}
                  {askGraphOp === 'shortest_path_weighted' && (
                    <>
                      <div>
                        <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">weight_property (opcional)</label>
                        <Input
                          value={askGraphParams.weight_property || ''}
                          onChange={(e) => setAskGraph({ params: { ...askGraphParams, weight_property: e.target.value || undefined } })}
                          className="h-8 text-sm"
                        />
                      </div>
                      <div>
                        <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">direction</label>
                        <select
                          value={askGraphParams.direction || 'OUTGOING'}
                          onChange={(e) => setAskGraph({ params: { ...askGraphParams, direction: e.target.value } })}
                          className="w-full h-8 rounded-md border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 px-2 text-sm"
                        >
                          <option value="OUTGOING">OUTGOING</option>
                          <option value="INCOMING">INCOMING</option>
                          <option value="BOTH">BOTH</option>
                        </select>
                      </div>
                    </>
                  )}
                  {askGraphOp === 'yens_k_shortest_paths' && (
                    <div>
                      <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">k</label>
                      <Input
                        type="number"
                        value={askGraphParams.k ?? 3}
                        onChange={(e) => setAskGraph({ params: { ...askGraphParams, k: parseInt(e.target.value || '0', 10) || 3 } })}
                        className="h-8 text-sm"
                      />
                    </div>
                  )}
                </div>
              )}

              {askGraphOp === 'precedent_network' && (
                <div className="grid grid-cols-2 gap-2">
                  <div className="col-span-2">
                    <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">decision_id</label>
                    <Input
                      value={askGraphParams.decision_id || ''}
                      onChange={(e) => setAskGraph({ params: { ...askGraphParams, decision_id: e.target.value } })}
                      className="h-8 text-sm"
                    />
                  </div>
                  <div>
                    <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">limit</label>
                    <Input
                      type="number"
                      value={askGraphParams.limit ?? 20}
                      onChange={(e) => setAskGraph({ params: { ...askGraphParams, limit: parseInt(e.target.value || '0', 10) || 20 } })}
                      className="h-8 text-sm"
                    />
                  </div>
                </div>
              )}

              {askGraphOp === 'related_entities' && (
                <div className="grid grid-cols-2 gap-2">
                  <div className="col-span-2">
                    <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">entity_id</label>
                    <Input
                      value={askGraphParams.entity_id || ''}
                      onChange={(e) => setAskGraph({ params: { ...askGraphParams, entity_id: e.target.value } })}
                      className="h-8 text-sm"
                    />
                  </div>
                  <div className="col-span-2">
                    <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">relation_filter (opcional)</label>
                    <Input
                      value={askGraphParams.relation_filter || ''}
                      onChange={(e) => setAskGraph({ params: { ...askGraphParams, relation_filter: e.target.value || undefined } })}
                      className="h-8 text-sm"
                    />
                  </div>
                  <div>
                    <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">limit</label>
                    <Input
                      type="number"
                      value={askGraphParams.limit ?? 20}
                      onChange={(e) => setAskGraph({ params: { ...askGraphParams, limit: parseInt(e.target.value || '0', 10) || 20 } })}
                      className="h-8 text-sm"
                    />
                  </div>
                </div>
              )}

              {/* Generic knobs for many GDS ops */}
              {[
                'betweenness_centrality',
                'community_detection',
                'weakly_connected_components',
                'triangle_count',
                'degree_centrality',
                'closeness_centrality',
                'eigenvector_centrality',
                'leiden',
                'k_core_decomposition',
                'harmonic_centrality',
                'bridges',
                'articulation_points',
                'strongly_connected_components',
                'all_pairs_shortest_path',
              ].includes(askGraphOp) && (
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">entity_type</label>
                    <select
                      value={askGraphParams.entity_type || ''}
                      onChange={(e) => setAskGraph({ params: { ...askGraphParams, entity_type: e.target.value || undefined } })}
                      className="w-full h-8 rounded-md border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 px-2 text-sm"
                    >
                      <option value="">(qualquer)</option>
                      {ENTITY_TYPES.map((t) => (
                        <option key={t} value={t}>{t}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">limit</label>
                    <Input
                      type="number"
                      value={askGraphParams.limit ?? 20}
                      onChange={(e) => setAskGraph({ params: { ...askGraphParams, limit: parseInt(e.target.value || '0', 10) || 20 } })}
                      className="h-8 text-sm"
                    />
                  </div>
                </div>
              )}

              {askGraphOp === 'node_similarity' && (
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">entity_type</label>
                    <select
                      value={askGraphParams.entity_type || ''}
                      onChange={(e) => setAskGraph({ params: { ...askGraphParams, entity_type: e.target.value || undefined } })}
                      className="w-full h-8 rounded-md border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 px-2 text-sm"
                    >
                      <option value="">(qualquer)</option>
                      {ENTITY_TYPES.map((t) => (
                        <option key={t} value={t}>{t}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">top_k</label>
                    <Input
                      type="number"
                      value={askGraphParams.top_k ?? 10}
                      onChange={(e) => setAskGraph({ params: { ...askGraphParams, top_k: parseInt(e.target.value || '0', 10) || 10 } })}
                      className="h-8 text-sm"
                    />
                  </div>
                  <div className="col-span-2">
                    <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">entity_id (opcional)</label>
                    <Input
                      value={askGraphParams.entity_id || ''}
                      onChange={(e) => setAskGraph({ params: { ...askGraphParams, entity_id: e.target.value || undefined } })}
                      className="h-8 text-sm"
                    />
                  </div>
                </div>
              )}

              {askGraphOp === 'pagerank_personalized' && (
                <div className="grid grid-cols-2 gap-2">
                  <div className="col-span-2">
                    <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">source_ids (csv)</label>
                    <Input
                      value={Array.isArray(askGraphParams.source_ids) ? askGraphParams.source_ids.join(',') : (askGraphParams.source_ids || '')}
                      onChange={(e) => {
                        const ids = e.target.value.split(',').map((s) => s.trim()).filter(Boolean);
                        setAskGraph({ params: { ...askGraphParams, source_ids: ids } });
                      }}
                      className="h-8 text-sm"
                    />
                  </div>
                  <div>
                    <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">entity_type</label>
                    <select
                      value={askGraphParams.entity_type || ''}
                      onChange={(e) => setAskGraph({ params: { ...askGraphParams, entity_type: e.target.value || undefined } })}
                      className="w-full h-8 rounded-md border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 px-2 text-sm"
                    >
                      <option value="">(qualquer)</option>
                      {ENTITY_TYPES.map((t) => (
                        <option key={t} value={t}>{t}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">limit</label>
                    <Input
                      type="number"
                      value={askGraphParams.limit ?? 20}
                      onChange={(e) => setAskGraph({ params: { ...askGraphParams, limit: parseInt(e.target.value || '0', 10) || 20 } })}
                      className="h-8 text-sm"
                    />
                  </div>
                </div>
              )}

              {askGraphOp === 'adamic_adar' && (
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">node1_id</label>
                    <Input
                      value={askGraphParams.node1_id || ''}
                      onChange={(e) => setAskGraph({ params: { ...askGraphParams, node1_id: e.target.value } })}
                      className="h-8 text-sm"
                    />
                  </div>
                  <div>
                    <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">node2_id</label>
                    <Input
                      value={askGraphParams.node2_id || ''}
                      onChange={(e) => setAskGraph({ params: { ...askGraphParams, node2_id: e.target.value } })}
                      className="h-8 text-sm"
                    />
                  </div>
                </div>
              )}

              {askGraphOp === 'node2vec' && (
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">entity_type</label>
                    <select
                      value={askGraphParams.entity_type || ''}
                      onChange={(e) => setAskGraph({ params: { ...askGraphParams, entity_type: e.target.value || undefined } })}
                      className="w-full h-8 rounded-md border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 px-2 text-sm"
                    >
                      <option value="">(qualquer)</option>
                      {ENTITY_TYPES.map((t) => (
                        <option key={t} value={t}>{t}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">embedding_dimension</label>
                    <Input
                      type="number"
                      value={askGraphParams.embedding_dimension ?? 128}
                      onChange={(e) => setAskGraph({ params: { ...askGraphParams, embedding_dimension: parseInt(e.target.value || '0', 10) || 128 } })}
                      className="h-8 text-sm"
                    />
                  </div>
                  <div>
                    <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">iterations</label>
                    <Input
                      type="number"
                      value={askGraphParams.iterations ?? 10}
                      onChange={(e) => setAskGraph({ params: { ...askGraphParams, iterations: parseInt(e.target.value || '0', 10) || 10 } })}
                      className="h-8 text-sm"
                    />
                  </div>
                  <div>
                    <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">limit</label>
                    <Input
                      type="number"
                      value={askGraphParams.limit ?? 200}
                      onChange={(e) => setAskGraph({ params: { ...askGraphParams, limit: parseInt(e.target.value || '0', 10) || 200 } })}
                      className="h-8 text-sm"
                    />
                  </div>
                </div>
              )}

              {askGraphOp === 'link_entities' && (
                <div className="space-y-2">
                  <p className="text-[10px] text-amber-600 dark:text-amber-400">
                    Escrita no grafo: use preflight (confirm=false) e só confirme após aprovação explícita.
                  </p>
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">source_id</label>
                      <Input
                        value={askGraphParams.source_id || ''}
                        onChange={(e) => setAskGraph({ params: { ...askGraphParams, source_id: e.target.value } })}
                        className="h-8 text-sm"
                      />
                    </div>
                    <div>
                      <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">target_id</label>
                      <Input
                        value={askGraphParams.target_id || ''}
                        onChange={(e) => setAskGraph({ params: { ...askGraphParams, target_id: e.target.value } })}
                        className="h-8 text-sm"
                      />
                    </div>
                    <div className="col-span-2">
                      <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">relation_type</label>
                      <Input
                        value={askGraphParams.relation_type || ''}
                        onChange={(e) => setAskGraph({ params: { ...askGraphParams, relation_type: e.target.value || undefined } })}
                        className="h-8 text-sm"
                      />
                    </div>
                    <div className="flex items-center justify-between col-span-2">
                      <label className="text-xs text-slate-600 dark:text-slate-400">confirm</label>
                      <input
                        type="checkbox"
                        checked={!!askGraphParams.confirm}
                        onChange={(e) => setAskGraph({ params: { ...askGraphParams, confirm: e.target.checked } })}
                        className="h-4 w-4 rounded border-slate-300"
                      />
                    </div>
                    <div className="col-span-2">
                      <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">preflight_token (opcional)</label>
                      <Input
                        value={askGraphParams.preflight_token || ''}
                        onChange={(e) => setAskGraph({ params: { ...askGraphParams, preflight_token: e.target.value || undefined } })}
                        className="h-8 text-sm"
                      />
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          <div>
            <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">Arguments (JSON)</label>
            <textarea
              value={data.tool_input || buildArgsText(toolCallArgs)}
              onChange={(e) => {
                update('tool_input', e.target.value);
                const parsed = safeParseJsonObject(e.target.value);
                if (parsed) update('arguments', parsed);
              }}
              placeholder='{"operation":"search","params":{"query":"...","limit":20}}'
              rows={4}
              className="w-full rounded-md border border-slate-200 dark:border-slate-700 bg-transparent px-3 py-2 text-sm font-mono resize-none focus:outline-none focus:ring-2 focus:ring-cyan-500/50"
            />
            <p className="text-[10px] text-slate-400 mt-1">
              Dica: para o grafo use a tool `ask_graph` (operações tipadas). O preset acima preenche esse JSON automaticamente.
            </p>
          </div>
        </div>
      )}

      {/* Claude Agent Node */}
      {nodeType === 'claude_agent' && (
        <div className="space-y-3">
          {/* Agent Type Selector */}
          <div>
            <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">Tipo de Agente</label>
            <select
              value={data.agent_type || 'claude-agent'}
              onChange={(e) => update('agent_type', e.target.value)}
              className="w-full h-8 rounded-md border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-2 text-sm"
            >
              {AGENT_OPTIONS.map((a) => (
                <option key={a.value} value={a.value}>{a.label}</option>
              ))}
            </select>
            {AGENT_OPTIONS.find((a) => a.value === (data.agent_type || 'claude-agent'))?.tooltip && (
              <p className="text-[10px] text-slate-400 mt-1">
                {AGENT_OPTIONS.find((a) => a.value === (data.agent_type || 'claude-agent'))!.tooltip.slice(0, 150)}
              </p>
            )}
          </div>
          <div>
            <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">Modelo</label>
            <select
              value={data.model || 'claude-4.5-sonnet'}
              onChange={(e) => update('model', e.target.value)}
              className="w-full h-8 rounded-md border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-2 text-sm"
            >
              {modelsByProvider.map((group) => (
                <optgroup key={group.provider} label={group.label}>
                  {group.models.map((m) => (
                    <option key={m.value} value={m.value}>{m.label}</option>
                  ))}
                </optgroup>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">System Prompt</label>
            <textarea
              value={data.system_prompt || ''}
              onChange={(e) => update('system_prompt', e.target.value)}
              placeholder="Voce e um assistente juridico especializado..."
              rows={4}
              className="w-full rounded-md border border-slate-200 dark:border-slate-700 bg-transparent px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
            />
          </div>
          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="text-xs font-medium text-slate-500 dark:text-slate-400">
                Tools Disponíveis
              </label>
              <span className="text-[10px] text-slate-400">
                {(data.tool_names || []).length} selecionada(s)
              </span>
            </div>
            {toolsLoading ? (
              <div className="flex items-center gap-2 text-xs text-slate-400 py-2">
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Carregando...
              </div>
            ) : (
              <div className="max-h-40 overflow-y-auto rounded-md border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800">
                {toolsByCategory.map((group) => (
                  <div key={group.category}>
                    <p className="text-[10px] font-semibold text-slate-400 uppercase px-2 pt-2 pb-1">
                      {group.category}
                    </p>
                    {group.tools.map((tool) => {
                      const checked = (data.tool_names || []).includes(tool.value);
                      return (
                        <label
                          key={tool.value}
                          className="flex items-center gap-2 px-2 py-1 hover:bg-slate-50 dark:hover:bg-slate-700 cursor-pointer"
                        >
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={() => {
                              const current = [...(data.tool_names || [])];
                              if (checked) {
                                update('tool_names', current.filter((n: string) => n !== tool.value));
                              } else {
                                update('tool_names', [...current, tool.value]);
                              }
                            }}
                            className="rounded border-slate-300 text-indigo-600"
                          />
                          <span className="text-xs text-slate-700 dark:text-slate-300 truncate">{tool.label}</span>
                        </label>
                      );
                    })}
                  </div>
                ))}
                {availableTools.length === 0 && (
                  <p className="text-xs text-slate-400 p-2 text-center">Nenhuma tool disponível</p>
                )}
              </div>
            )}
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">Max Iterações</label>
              <Input
                type="number"
                value={data.max_iterations || 10}
                onChange={(e) => update('max_iterations', parseInt(e.target.value) || 10)}
                min={1}
                max={50}
                className="h-8 text-sm"
              />
            </div>
            <div>
              <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">Max Tokens</label>
              <Input
                type="number"
                value={data.max_tokens || 4096}
                onChange={(e) => update('max_tokens', parseInt(e.target.value) || 4096)}
                min={256}
                max={32768}
                className="h-8 text-sm"
              />
            </div>
          </div>
          {/* Capabilities toggles */}
          <div className="space-y-2 pt-2 border-t border-slate-200 dark:border-slate-700">
            <p className="text-[10px] font-semibold text-slate-400 uppercase">Capacidades</p>
            <div className="flex items-center justify-between">
              <label className="text-xs text-slate-600 dark:text-slate-400">Web Search</label>
              <button
                onClick={() => update('enable_web_search', !data.enable_web_search)}
                className={`relative w-9 h-5 rounded-full transition-colors ${
                  data.enable_web_search ? 'bg-indigo-500' : 'bg-slate-300 dark:bg-slate-600'
                }`}
              >
                <span className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white transition-transform ${
                  data.enable_web_search ? 'translate-x-4' : ''
                }`} />
              </button>
            </div>
            <div className="flex items-center justify-between">
              <label className="text-xs text-slate-600 dark:text-slate-400">Deep Research</label>
              <button
                onClick={() => update('enable_deep_research', !data.enable_deep_research)}
                className={`relative w-9 h-5 rounded-full transition-colors ${
                  data.enable_deep_research ? 'bg-indigo-500' : 'bg-slate-300 dark:bg-slate-600'
                }`}
              >
                <span className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white transition-transform ${
                  data.enable_deep_research ? 'translate-x-4' : ''
                }`} />
              </button>
            </div>
            <div className="flex items-center justify-between">
              <label className="text-xs text-slate-600 dark:text-slate-400">Execução de Código</label>
              <button
                onClick={() => update('enable_code_execution', !data.enable_code_execution)}
                className={`relative w-9 h-5 rounded-full transition-colors ${
                  data.enable_code_execution ? 'bg-indigo-500' : 'bg-slate-300 dark:bg-slate-600'
                }`}
              >
                <span className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white transition-transform ${
                  data.enable_code_execution ? 'translate-x-4' : ''
                }`} />
              </button>
            </div>
            <div className="flex items-center justify-between">
              <label className="text-xs text-slate-600 dark:text-slate-400">Incluir MCP Tools</label>
              <button
                onClick={() => update('include_mcp', !data.include_mcp)}
                className={`relative w-9 h-5 rounded-full transition-colors ${
                  data.include_mcp ? 'bg-indigo-500' : 'bg-slate-300 dark:bg-slate-600'
                }`}
              >
                <span className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white transition-transform ${
                  data.include_mcp ? 'translate-x-4' : ''
                }`} />
              </button>
            </div>
            <div className="flex items-center justify-between">
              <label className="text-xs text-slate-600 dark:text-slate-400">Usar Agent SDK</label>
              <button
                onClick={() => update('use_sdk', data.use_sdk === false ? true : false)}
                className={`relative w-9 h-5 rounded-full transition-colors ${
                  data.use_sdk !== false ? 'bg-indigo-500' : 'bg-slate-300 dark:bg-slate-600'
                }`}
              >
                <span className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white transition-transform ${
                  data.use_sdk !== false ? 'translate-x-4' : ''
                }`} />
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Parallel Agents Node */}
      {nodeType === 'parallel_agents' && (
        <div className="space-y-3">
          {/* Prompts list */}
          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="text-xs font-medium text-slate-500 dark:text-slate-400">
                Prompts dos Agentes
              </label>
              <button
                onClick={() => {
                  const prompts = [...(data.prompts || []), ''];
                  update('prompts', prompts);
                }}
                className="text-xs text-fuchsia-600 hover:text-fuchsia-500 font-medium flex items-center gap-0.5"
              >
                <Plus className="h-3 w-3" /> Adicionar
              </button>
            </div>
            <div className="space-y-2">
              {(data.prompts || ['']).map((prompt: string, idx: number) => (
                <div key={idx} className="relative">
                  <textarea
                    value={prompt}
                    onChange={(e) => {
                      const prompts = [...(data.prompts || [''])];
                      prompts[idx] = e.target.value;
                      update('prompts', prompts);
                    }}
                    placeholder={`Prompt do agente ${idx + 1}...`}
                    rows={2}
                    className="w-full rounded-md border border-slate-200 dark:border-slate-700 bg-transparent px-3 py-2 pr-8 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-fuchsia-500/50"
                  />
                  {(data.prompts || []).length > 1 && (
                    <button
                      onClick={() => {
                        const prompts = (data.prompts || []).filter((_: string, i: number) => i !== idx);
                        update('prompts', prompts);
                      }}
                      className="absolute top-1.5 right-1.5 text-red-400 hover:text-red-600"
                    >
                      <Minus className="h-3.5 w-3.5" />
                    </button>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* Models multi-select */}
          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="text-xs font-medium text-slate-500 dark:text-slate-400">Modelos</label>
              <span className="text-[10px] text-slate-400">
                {(data.models || []).length} selecionado(s)
              </span>
            </div>
            <div className="max-h-36 overflow-y-auto rounded-md border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800">
              {modelsByProvider.map((group) => (
                <div key={group.provider}>
                  <p className="text-[10px] font-semibold text-slate-400 uppercase px-2 pt-2 pb-1">
                    {group.label}
                  </p>
                  {group.models.map((m) => {
                    const checked = (data.models || []).includes(m.value);
                    return (
                      <label
                        key={m.value}
                        className="flex items-center gap-2 px-2 py-1 hover:bg-slate-50 dark:hover:bg-slate-700 cursor-pointer"
                      >
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={() => {
                            const current = [...(data.models || [])];
                            if (checked) {
                              update('models', current.filter((id: string) => id !== m.value));
                            } else {
                              update('models', [...current, m.value]);
                            }
                          }}
                          className="rounded border-slate-300 text-fuchsia-600"
                        />
                        <span className="text-xs text-slate-700 dark:text-slate-300">{m.label}</span>
                      </label>
                    );
                  })}
                </div>
              ))}
            </div>
          </div>

          {/* Tools multi-select */}
          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="text-xs font-medium text-slate-500 dark:text-slate-400">Tools</label>
              <span className="text-[10px] text-slate-400">
                {(data.tool_names || []).length} selecionada(s)
              </span>
            </div>
            {toolsLoading ? (
              <div className="flex items-center gap-2 text-xs text-slate-400 py-2">
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Carregando...
              </div>
            ) : (
              <div className="max-h-36 overflow-y-auto rounded-md border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800">
                {toolsByCategory.map((group) => (
                  <div key={group.category}>
                    <p className="text-[10px] font-semibold text-slate-400 uppercase px-2 pt-2 pb-1">
                      {group.category}
                    </p>
                    {group.tools.map((tool) => {
                      const checked = (data.tool_names || []).includes(tool.value);
                      return (
                        <label
                          key={tool.value}
                          className="flex items-center gap-2 px-2 py-1 hover:bg-slate-50 dark:hover:bg-slate-700 cursor-pointer"
                        >
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={() => {
                              const current = [...(data.tool_names || [])];
                              if (checked) {
                                update('tool_names', current.filter((n: string) => n !== tool.value));
                              } else {
                                update('tool_names', [...current, tool.value]);
                              }
                            }}
                            className="rounded border-slate-300 text-fuchsia-600"
                          />
                          <span className="text-xs text-slate-700 dark:text-slate-300 truncate">{tool.label}</span>
                        </label>
                      );
                    })}
                  </div>
                ))}
                {availableTools.length === 0 && (
                  <p className="text-xs text-slate-400 p-2 text-center">Nenhuma tool disponível</p>
                )}
              </div>
            )}
          </div>

          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">Max Paralelo</label>
              <Input
                type="number"
                value={data.max_parallel || 3}
                onChange={(e) => update('max_parallel', parseInt(e.target.value) || 3)}
                min={1}
                max={10}
                className="h-8 text-sm"
              />
            </div>
            <div>
              <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">Agregação</label>
              <select
                value={data.aggregation_strategy || 'merge'}
                onChange={(e) => update('aggregation_strategy', e.target.value)}
                className="w-full h-8 rounded-md border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-2 text-sm"
              >
                <option value="merge">Merge (juntar)</option>
                <option value="best">Best (melhor)</option>
                <option value="vote">Vote (votação)</option>
              </select>
            </div>
          </div>
        </div>
      )}

      {nodeType === 'file_upload' && (
        <div>
          <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">Tipo de arquivo</label>
          <Input
            value={data.accepts || '*'}
            onChange={(e) => update('accepts', e.target.value)}
            placeholder=".pdf,.docx"
            className="h-8 text-sm"
          />
        </div>
      )}

      {/* User Input Node */}
      {nodeType === 'user_input' && (
        <div className="space-y-3">
          <div>
            <label className="text-xs font-medium text-slate-600 dark:text-slate-400">Tipo de Input</label>
            <select
              value={data.input_type || 'text'}
              onChange={(e) => update('input_type', e.target.value)}
              className="mt-1 w-full rounded-md border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 px-2 py-1.5 text-sm"
            >
              <option value="text">Texto</option>
              <option value="file">Arquivo</option>
              <option value="both">Texto + Arquivo</option>
              <option value="selection">Seleção</option>
            </select>
          </div>
          <div>
            <label className="text-xs font-medium text-slate-600 dark:text-slate-400">Nome do Campo</label>
            <input
              type="text"
              value={data.collects || 'input'}
              onChange={(e) => update('collects', e.target.value)}
              className="mt-1 w-full rounded-md border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 px-2 py-1.5 text-sm"
              placeholder="input"
            />
          </div>
          <div>
            <label className="text-xs font-medium text-slate-600 dark:text-slate-400">Placeholder</label>
            <input
              type="text"
              value={data.placeholder || ''}
              onChange={(e) => update('placeholder', e.target.value)}
              className="mt-1 w-full rounded-md border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 px-2 py-1.5 text-sm"
              placeholder="Texto de ajuda..."
            />
          </div>
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="optional-toggle"
              checked={!!data.optional}
              onChange={(e) => update('optional', e.target.checked)}
              className="rounded border-slate-300"
            />
            <label htmlFor="optional-toggle" className="text-xs font-medium text-slate-600 dark:text-slate-400">
              Campo Opcional
            </label>
          </div>
          {data.optional && (
            <div>
              <label className="text-xs font-medium text-slate-600 dark:text-slate-400">
                Texto Padrão (usado quando vazio)
              </label>
              <textarea
                value={data.default_text || ''}
                onChange={(e) => update('default_text', e.target.value)}
                rows={3}
                className="mt-1 w-full rounded-md border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 px-2 py-1.5 text-sm resize-y"
                placeholder="Contexto padrão quando o usuário não fornecer input..."
              />
            </div>
          )}
        </div>
      )}

      {/* Output Node */}
      {nodeType === 'output' && (
        <div className="space-y-3">
          <div className="flex items-center gap-2 mb-2">
            <input
              type="checkbox"
              id="show-all-toggle"
              checked={data.show_all !== false}
              onChange={(e) => update('show_all', e.target.checked)}
              className="rounded border-slate-300"
            />
            <label htmlFor="show-all-toggle" className="text-xs font-medium text-slate-600 dark:text-slate-400">
              Mostrar todas as saídas
            </label>
          </div>

          {data.show_all === false && (
            <>
              <label className="text-xs font-medium text-slate-600 dark:text-slate-400">
                Seções da Resposta
              </label>
              <div className="space-y-2">
                {(data.sections || []).map((section: any, idx: number) => (
                  <div
                    key={idx}
                    draggable
                    onDragStart={(e) => {
                      e.dataTransfer.setData('text/plain', String(idx));
                      e.currentTarget.style.opacity = '0.5';
                    }}
                    onDragEnd={(e) => { e.currentTarget.style.opacity = '1'; }}
                    onDragOver={(e) => e.preventDefault()}
                    onDrop={(e) => {
                      e.preventDefault();
                      const fromIdx = parseInt(e.dataTransfer.getData('text/plain'), 10);
                      if (isNaN(fromIdx) || fromIdx === idx) return;
                      const sections = [...(data.sections || [])];
                      const [moved] = sections.splice(fromIdx, 1);
                      sections.splice(idx, 0, moved);
                      const reordered = sections.map((s: any, i: number) => ({ ...s, order: i }));
                      update('sections', reordered);
                    }}
                    className="flex gap-2 items-start bg-slate-50 dark:bg-slate-800 rounded-md p-2 cursor-grab active:cursor-grabbing"
                  >
                    <div className="flex-1 space-y-1">
                      <input
                        type="text"
                        value={section.label || ''}
                        onChange={(e) => {
                          const sections = [...(data.sections || [])];
                          sections[idx] = { ...sections[idx], label: e.target.value };
                          update('sections', sections);
                        }}
                        className="w-full rounded border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 px-2 py-1 text-xs"
                        placeholder="Título da seção"
                      />
                      <input
                        type="text"
                        value={section.variable_ref || ''}
                        onChange={(e) => {
                          const sections = [...(data.sections || [])];
                          sections[idx] = { ...sections[idx], variable_ref: e.target.value };
                          update('sections', sections);
                        }}
                        className="w-full rounded border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 px-2 py-1 text-xs font-mono"
                        placeholder="@node_id"
                      />
                    </div>
                    <button
                      onClick={() => {
                        const sections = (data.sections || []).filter((_: any, i: number) => i !== idx);
                        update('sections', sections);
                      }}
                      className="text-red-400 hover:text-red-600 mt-1"
                    >
                      <span className="text-xs">✕</span>
                    </button>
                  </div>
                ))}
              </div>
              <button
                onClick={() => {
                  const sections = [...(data.sections || []), { label: '', variable_ref: '', order: (data.sections || []).length }];
                  update('sections', sections);
                }}
                className="w-full text-xs text-indigo-600 dark:text-indigo-400 hover:underline text-left"
              >
                + Adicionar seção
              </button>
            </>
          )}
        </div>
      )}

      {nodeType === 'review_table' && (
        <div className="space-y-4">
          {/* Model */}
          <div>
            <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">Modelo</label>
            <select
              value={data.model || 'claude-sonnet-4-20250514'}
              onChange={(e) => update('model', e.target.value)}
              className="w-full h-8 rounded-md border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-2 text-sm"
            >
              {(['anthropic', 'openai', 'google', 'xai', 'perplexity', 'openrouter'] as const).map((provider) => {
                const group = MODEL_OPTIONS.filter((m) => m.provider === provider);
                if (!group.length) return null;
                const labels: Record<string, string> = { anthropic: 'Anthropic', openai: 'OpenAI', google: 'Google', xai: 'xAI', perplexity: 'Perplexity', openrouter: 'Meta / OpenRouter' };
                return (
                  <optgroup key={provider} label={labels[provider] || provider}>
                    {group.map((m) => (
                      <option key={m.value} value={m.value}>{m.label}</option>
                    ))}
                  </optgroup>
                );
              })}
            </select>
          </div>

          {/* Prompt prefix */}
          <div>
            <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">Instrução de Extração</label>
            <textarea
              value={data.prompt_prefix || ''}
              onChange={(e) => update('prompt_prefix', e.target.value)}
              placeholder="Extraia as seguintes informações de cada documento..."
              rows={3}
              className="w-full rounded-md border border-slate-200 dark:border-slate-700 bg-transparent px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-teal-500/50"
            />
          </div>

          {/* Columns */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-xs font-medium text-slate-500 dark:text-slate-400">Colunas</label>
              <button
                onClick={() => {
                  const cols = [...(data.columns || [])];
                  cols.push({ id: `col_${Date.now()}`, name: '', description: '' });
                  update('columns', cols);
                }}
                className="text-xs text-teal-600 hover:text-teal-500 font-medium"
              >
                + Adicionar
              </button>
            </div>
            <div className="space-y-2">
              {(data.columns || []).map((col: any, idx: number) => (
                <div key={col.id || idx} className="flex gap-2 items-start p-2 rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800">
                  <div className="flex-1 space-y-1">
                    <input
                      value={col.name || ''}
                      onChange={(e) => {
                        const cols = [...(data.columns || [])];
                        cols[idx] = { ...cols[idx], name: e.target.value };
                        update('columns', cols);
                      }}
                      placeholder="Nome da coluna"
                      className="w-full h-7 rounded border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-2 text-xs"
                    />
                    <input
                      value={col.description || ''}
                      onChange={(e) => {
                        const cols = [...(data.columns || [])];
                        cols[idx] = { ...cols[idx], description: e.target.value };
                        update('columns', cols);
                      }}
                      placeholder="Instrução de extração"
                      className="w-full h-7 rounded border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-2 text-xs"
                    />
                  </div>
                  <button
                    onClick={() => {
                      const cols = (data.columns || []).filter((_: any, i: number) => i !== idx);
                      update('columns', cols);
                    }}
                    className="text-red-400 hover:text-red-600 text-sm mt-1 transition-colors"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </div>
              ))}
            </div>
            {(data.columns || []).length === 0 && (
              <p className="text-[10px] text-slate-400 mt-1">
                Adicione colunas para definir quais dados extrair de cada documento.
              </p>
            )}
          </div>
        </div>
      )}

      {nodeType === 'legal_workflow' && (
        <>
          <div>
            <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">Modo</label>
            <select
              value={data.mode || 'minuta'}
              onChange={(e) => update('mode', e.target.value)}
              className="w-full h-8 rounded-md border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-2 text-sm"
            >
              {LEGAL_MODE_OPTIONS.map((m) => (
                <option key={m.value} value={m.value}>{m.label}</option>
              ))}
            </select>
          </div>
          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="text-xs font-medium text-slate-500 dark:text-slate-400">Modelos</label>
              <span className="text-[10px] text-slate-400">
                {(data.models || []).length} selecionado(s)
              </span>
            </div>
            {/* Selected models as chips */}
            {(data.models || []).length > 0 && (
              <div className="flex flex-wrap gap-1 mb-2">
                {(data.models || []).map((modelId: string) => (
                  <span
                    key={modelId}
                    className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-indigo-100 dark:bg-indigo-500/20 text-indigo-700 dark:text-indigo-300 text-[10px] font-medium"
                  >
                    {modelId}
                    <button
                      onClick={() => update('models', (data.models || []).filter((id: string) => id !== modelId))}
                      className="text-indigo-400 hover:text-red-500"
                    >
                      <X className="h-2.5 w-2.5" />
                    </button>
                  </span>
                ))}
              </div>
            )}
            <div className="max-h-36 overflow-y-auto rounded-md border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800">
              {modelsByProvider.map((group) => (
                <div key={group.provider}>
                  <p className="text-[10px] font-semibold text-slate-400 uppercase px-2 pt-2 pb-1">
                    {group.label}
                  </p>
                  {group.models.map((m) => {
                    const checked = (data.models || []).includes(m.value);
                    return (
                      <label
                        key={m.value}
                        className="flex items-center gap-2 px-2 py-1 hover:bg-slate-50 dark:hover:bg-slate-700 cursor-pointer"
                      >
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={() => {
                            const current = [...(data.models || [])];
                            if (checked) {
                              update('models', current.filter((id: string) => id !== m.value));
                            } else {
                              update('models', [...current, m.value]);
                            }
                          }}
                          className="rounded border-slate-300 text-indigo-600"
                        />
                        <span className="text-xs text-slate-700 dark:text-slate-300">{m.label}</span>
                      </label>
                    );
                  })}
                </div>
              ))}
            </div>
          </div>
          <div>
            <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">Tese (opcional)</label>
            <textarea
              value={data.tese || ''}
              onChange={(e) => update('tese', e.target.value)}
              placeholder="Argumento central do documento..."
              rows={3}
              className="w-full rounded-md border border-slate-200 dark:border-slate-700 bg-transparent px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
            />
          </div>
          <div>
            <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">Tipo de documento</label>
            <Input
              value={data.doc_kind || ''}
              onChange={(e) => update('doc_kind', e.target.value)}
              placeholder="petição inicial, contestação, recurso..."
              className="h-8 text-sm"
            />
          </div>
          <div>
            <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">Estilo de citação</label>
            <select
              value={data.citation_style || 'abnt'}
              onChange={(e) => update('citation_style', e.target.value)}
              className="w-full h-8 rounded-md border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-2 text-sm"
            >
              <option value="abnt">ABNT</option>
              <option value="ieee">IEEE</option>
              <option value="forense">Forense</option>
            </select>
          </div>
          <div>
            <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">Nível de raciocínio</label>
            <select
              value={data.thinking_level || 'medium'}
              onChange={(e) => update('thinking_level', e.target.value)}
              className="w-full h-8 rounded-md border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-2 text-sm"
            >
              {THINKING_LEVELS.map((t) => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
          </div>
          {/* Template / Outline */}
          <div className="pt-3 border-t border-slate-200 dark:border-slate-700">
            <label className="text-xs font-semibold text-slate-600 dark:text-slate-300 mb-2 block">
              Estrutura / Template
            </label>
            {/* Template selector from /models page */}
            <TemplatePicker
              selectedId={data.template_id || ''}
              onSelect={(id, name, content) => {
                update('template_id', id);
                if (content && !data.template_structure) {
                  update('template_structure', content);
                }
              }}
              onClear={() => {
                update('template_id', '');
              }}
            />
            <div className="mt-2">
              <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">
                Template (markdown) — customizado ou carregado acima
              </label>
              <textarea
                value={data.template_structure || ''}
                onChange={(e) => update('template_structure', e.target.value)}
                placeholder={"# I. Introdução\n# II. Dos Fatos\n# III. Do Direito\n# IV. Dos Pedidos"}
                rows={5}
                className="w-full rounded-md border border-slate-200 dark:border-slate-700 bg-transparent px-3 py-2 text-sm font-mono resize-none focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
              />
              <p className="text-[10px] text-slate-400 mt-1">
                O template selecionado acima é carregado em runtime. Edite aqui para override manual.
              </p>
            </div>
            <div className="mt-2">
              <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">
                Seções do outline (uma por linha)
              </label>
              <textarea
                value={(data.outline || []).join('\n')}
                onChange={(e) => update('outline', e.target.value.split('\n').filter(Boolean))}
                placeholder={"Introdução\nDos Fatos\nDo Direito\nDos Pedidos"}
                rows={4}
                className="w-full rounded-md border border-slate-200 dark:border-slate-700 bg-transparent px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
              />
              <p className="text-[10px] text-slate-400 mt-1">
                Alternativa ao template. Lista de títulos de seção.
              </p>
            </div>
          </div>

          {/* HIL Control */}
          <div className="pt-3 border-t border-slate-200 dark:border-slate-700">
            <label className="text-xs font-semibold text-slate-600 dark:text-slate-300 mb-2 block">
              Pontos de Revisão Humana
            </label>
            <div className="flex items-center gap-2 mb-2">
              <input
                type="checkbox"
                checked={data.hil_outline || false}
                onChange={(e) => update('hil_outline', e.target.checked)}
                className="rounded border-slate-300"
                id="hil_outline"
              />
              <label htmlFor="hil_outline" className="text-xs text-slate-600 dark:text-slate-400">
                Revisar outline antes de prosseguir
              </label>
            </div>
            <div>
              <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">
                Política de HIL por seção
              </label>
              <select
                value={data.hil_section_policy || 'divergence_only'}
                onChange={(e) => update('hil_section_policy', e.target.value)}
                className="w-full h-8 rounded-md border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-2 text-sm"
              >
                <option value="all">Todas as seções</option>
                <option value="divergence_only">Apenas se houver divergência</option>
                <option value="high_risk_only">Apenas alto risco</option>
                <option value="none">Nenhuma</option>
              </select>
            </div>
            <div className="mt-2">
              <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">
                Seções específicas com HIL (uma por linha)
              </label>
              <textarea
                value={(data.hil_sections || []).join('\n')}
                onChange={(e) => update('hil_sections', e.target.value.split('\n').filter(Boolean))}
                placeholder={"Dos Pedidos\nDo Direito"}
                rows={3}
                className="w-full rounded-md border border-slate-200 dark:border-slate-700 bg-transparent px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
              />
              <p className="text-[10px] text-slate-400 mt-1">
                Seções que sempre pausam para revisão humana.
              </p>
            </div>
            <div className="flex items-center gap-2 mt-2">
              <input
                type="checkbox"
                checked={data.force_final_hil || false}
                onChange={(e) => update('force_final_hil', e.target.checked)}
                className="rounded border-slate-300"
                id="force_final_hil"
              />
              <label htmlFor="force_final_hil" className="text-xs text-slate-600 dark:text-slate-400">
                Forçar revisão final (mesmo com auto-approve)
              </label>
            </div>
            <div className="flex items-center gap-2 mt-2">
              <input
                type="checkbox"
                checked={data.auto_approve || false}
                onChange={(e) => update('auto_approve', e.target.checked)}
                className="rounded border-slate-300"
                id="auto_approve"
              />
              <label htmlFor="auto_approve" className="text-xs text-slate-600 dark:text-slate-400">
                Auto-aprovar HIL (pular revisões intermediárias)
              </label>
            </div>
          </div>
        </>
      )}

      {/* Embedded Files Section */}
      {workflowId && (
        <div className="border-t border-slate-200 dark:border-slate-700 pt-3 mt-3">
          <div className="flex items-center justify-between mb-2">
            <label className="text-xs font-medium text-slate-500 flex items-center gap-1.5">
              <Paperclip className="h-3.5 w-3.5" />
              Arquivos Embutidos
            </label>
            <span className="text-[10px] text-slate-400">
              {embeddedFiles.length} arquivo(s)
            </span>
          </div>
          <p className="text-[10px] text-slate-400 mb-2">
            Arquivos permanentes disponiveis para todos os usuarios deste workflow
          </p>

          {/* List embedded files */}
          {embeddedFiles.map((file) => (
            <div key={file.id} className="flex items-center gap-2 py-1 text-xs text-slate-600 dark:text-slate-400">
              <FileText className="h-3 w-3 shrink-0" />
              <span className="truncate flex-1">{file.name || `Arquivo`}</span>
              <button onClick={() => removeEmbeddedFile(file.id)} className="text-red-400 hover:text-red-500">
                <X className="h-3 w-3" />
              </button>
            </div>
          ))}

          {/* Upload button */}
          <label className="flex items-center justify-center gap-1.5 mt-2 py-2 border border-dashed border-slate-300 dark:border-slate-600 rounded-lg cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors">
            {isUploadingEmbedded ? (
              <Loader2 className="h-3.5 w-3.5 text-slate-400 animate-spin" />
            ) : (
              <Upload className="h-3.5 w-3.5 text-slate-400" />
            )}
            <span className="text-xs text-slate-500">
              {isUploadingEmbedded ? 'Enviando...' : 'Adicionar arquivo'}
            </span>
            <input
              type="file"
              className="hidden"
              onChange={handleEmbeddedFileUpload}
              disabled={isUploadingEmbedded}
            />
          </label>
        </div>
      )}

      {/* ── Trigger ─────────────────────────────────────────── */}
      {nodeType === 'trigger' && (
        <div className="space-y-3">
          <div>
            <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">Tipo de Trigger</label>
            <select
              value={data.trigger_type || 'webhook'}
              onChange={(e) => update('trigger_type', e.target.value)}
              className="w-full h-8 rounded-md border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-2 text-sm"
            >
              <option value="teams_command">Comando Teams</option>
              <option value="outlook_email">Email Outlook</option>
              <option value="djen_movement">Movimentacao DJEN/DataJud</option>
              <option value="schedule">Agendamento (Cron)</option>
              <option value="webhook">Webhook</option>
            </select>
          </div>

          {data.trigger_type === 'teams_command' && (
            <>
              <div>
                <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">Comando</label>
                <Input
                  value={data.trigger_config?.command || ''}
                  onChange={(e) => update('trigger_config', { ...data.trigger_config, command: e.target.value })}
                  placeholder="/minutar"
                  className="h-8 text-sm"
                />
              </div>
              <div>
                <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">Palavras-chave (separadas por virgula)</label>
                <Input
                  value={(data.trigger_config?.keywords || []).join(', ')}
                  onChange={(e) => update('trigger_config', { ...data.trigger_config, keywords: e.target.value.split(',').map((s: string) => s.trim()).filter(Boolean) })}
                  placeholder="minuta, contrato, prazo"
                  className="h-8 text-sm"
                />
              </div>
            </>
          )}

          {data.trigger_type === 'outlook_email' && (
            <>
              <div>
                <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">Filtro por Remetente</label>
                <Input
                  value={data.trigger_config?.sender_filter || ''}
                  onChange={(e) => update('trigger_config', { ...data.trigger_config, sender_filter: e.target.value })}
                  placeholder="@tribunal.jus.br"
                  className="h-8 text-sm"
                />
              </div>
              <div>
                <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">Assunto Contem</label>
                <Input
                  value={data.trigger_config?.subject_contains || ''}
                  onChange={(e) => update('trigger_config', { ...data.trigger_config, subject_contains: e.target.value })}
                  placeholder="intimacao, contrato"
                  className="h-8 text-sm"
                />
              </div>
              <div>
                <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">Corpo Contem</label>
                <Input
                  value={data.trigger_config?.body_contains || ''}
                  onChange={(e) => update('trigger_config', { ...data.trigger_config, body_contains: e.target.value })}
                  placeholder="urgente, prazo"
                  className="h-8 text-sm"
                />
              </div>
              <div>
                <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">Palavras-chave (assunto + corpo)</label>
                <Input
                  value={(data.trigger_config?.keywords || []).join(', ')}
                  onChange={(e) => update('trigger_config', { ...data.trigger_config, keywords: e.target.value.split(',').map((s: string) => s.trim()).filter(Boolean) })}
                  placeholder="minuta, contrato, recurso"
                  className="h-8 text-sm"
                />
              </div>
              <div className="border-t border-slate-200 dark:border-slate-700 pt-2 mt-2">
                <p className="text-[10px] text-slate-400 dark:text-slate-500 mb-2">Comandos por email (ex: &quot;IUDEX: minutar contrato&quot;)</p>
                <div>
                  <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">Comando</label>
                  <Input
                    value={data.trigger_config?.command || ''}
                    onChange={(e) => update('trigger_config', { ...data.trigger_config, command: e.target.value })}
                    placeholder="minutar, pesquisar, analisar"
                    className="h-8 text-sm"
                  />
                </div>
                <div className="mt-2">
                  <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">Prefixo customizado</label>
                  <Input
                    value={data.trigger_config?.command_prefix || ''}
                    onChange={(e) => update('trigger_config', { ...data.trigger_config, command_prefix: e.target.value })}
                    placeholder="IUDEX (padrao), ou seu prefixo"
                    className="h-8 text-sm"
                  />
                  <p className="text-[10px] text-slate-400 dark:text-slate-500 mt-1">Prefixos padrao: IUDEX:, VORBIUM:, [IUDEX], [VORBIUM]</p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={data.trigger_config?.require_attachment || false}
                  onChange={(e) => update('trigger_config', { ...data.trigger_config, require_attachment: e.target.checked })}
                  className="rounded"
                />
                <label className="text-xs text-slate-600 dark:text-slate-400">Requer anexo</label>
              </div>
            </>
          )}

          {data.trigger_type === 'djen_movement' && (
            <>
              <div>
                <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">NPU do Processo</label>
                <Input
                  value={data.trigger_config?.npu || ''}
                  onChange={(e) => update('trigger_config', { ...data.trigger_config, npu: e.target.value })}
                  placeholder="0000000-00.0000.0.00.0000"
                  className="h-8 text-sm"
                />
              </div>
              <div>
                <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">OAB</label>
                <Input
                  value={data.trigger_config?.oab || ''}
                  onChange={(e) => update('trigger_config', { ...data.trigger_config, oab: e.target.value })}
                  placeholder="123456/SP"
                  className="h-8 text-sm"
                />
              </div>
              <div>
                <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">Tipos de Movimento</label>
                <Input
                  value={(data.trigger_config?.movement_types || []).join(', ')}
                  onChange={(e) => update('trigger_config', { ...data.trigger_config, movement_types: e.target.value.split(',').map((s: string) => s.trim()).filter(Boolean) })}
                  placeholder="intimacao, despacho, sentenca"
                  className="h-8 text-sm"
                />
              </div>
            </>
          )}

          {data.trigger_type === 'schedule' && (
            <>
              <div>
                <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">Cron Expression</label>
                <Input
                  value={data.trigger_config?.cron || ''}
                  onChange={(e) => update('trigger_config', { ...data.trigger_config, cron: e.target.value })}
                  placeholder="0 8 * * 1-5"
                  className="h-8 text-sm font-mono"
                />
                <div className="flex gap-1 mt-1 flex-wrap">
                  {[
                    { label: 'Diario 8h', value: '0 8 * * *' },
                    { label: 'Seg-Sex 8h', value: '0 8 * * 1-5' },
                    { label: 'Semanal Seg', value: '0 9 * * 1' },
                    { label: 'Mensal', value: '0 9 1 * *' },
                  ].map((preset) => (
                    <button
                      key={preset.value}
                      onClick={() => update('trigger_config', { ...data.trigger_config, cron: preset.value })}
                      className="text-[10px] px-1.5 py-0.5 rounded bg-amber-50 dark:bg-amber-500/10 text-amber-600 dark:text-amber-400 hover:bg-amber-100 transition-colors"
                    >
                      {preset.label}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">Timezone</label>
                <select
                  value={data.trigger_config?.timezone || 'America/Sao_Paulo'}
                  onChange={(e) => update('trigger_config', { ...data.trigger_config, timezone: e.target.value })}
                  className="w-full h-8 rounded-md border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-2 text-sm"
                >
                  <option value="America/Sao_Paulo">Brasilia (GMT-3)</option>
                  <option value="America/Manaus">Manaus (GMT-4)</option>
                  <option value="UTC">UTC</option>
                </select>
              </div>
            </>
          )}

          {data.trigger_type === 'webhook' && (
            <div>
              <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">URL do Webhook</label>
              <p className="text-[10px] text-slate-400">
                A URL sera gerada ao salvar o workflow. Dados recebidos via POST serao injetados como input.
              </p>
            </div>
          )}
        </div>
      )}

      {/* ── Delivery ────────────────────────────────────────── */}
      {nodeType === 'delivery' && (
        <div className="space-y-3">
          <div>
            <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">Tipo de Entrega</label>
            <select
              value={data.delivery_type || 'email'}
              onChange={(e) => update('delivery_type', e.target.value)}
              className="w-full h-8 rounded-md border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-2 text-sm"
            >
              <option value="email">Email (Microsoft Graph)</option>
              <option value="teams_message">Mensagem Teams</option>
              <option value="calendar_event">Evento no Calendario</option>
              <option value="webhook_out">Webhook (POST)</option>
              <option value="outlook_reply">Responder Email Original</option>
            </select>
          </div>

          {data.delivery_type === 'email' && (
            <>
              <div>
                <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">Destinatario(s)</label>
                <Input
                  value={data.delivery_config?.to || ''}
                  onChange={(e) => update('delivery_config', { ...data.delivery_config, to: e.target.value })}
                  placeholder="email@exemplo.com ou {{trigger_event.sender}}"
                  className="h-8 text-sm"
                />
              </div>
              <div>
                <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">Assunto</label>
                <Input
                  value={data.delivery_config?.subject || ''}
                  onChange={(e) => update('delivery_config', { ...data.delivery_config, subject: e.target.value })}
                  placeholder="Resultado: {{trigger_event.subject}}"
                  className="h-8 text-sm"
                />
              </div>
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={data.delivery_config?.include_output_attachment || false}
                  onChange={(e) => update('delivery_config', { ...data.delivery_config, include_output_attachment: e.target.checked })}
                  className="rounded"
                />
                <label className="text-xs text-slate-600 dark:text-slate-400">Incluir output como anexo</label>
              </div>
              {data.delivery_config?.include_output_attachment && (
                <div>
                  <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">Nome do anexo (output)</label>
                  <Input
                    value={data.delivery_config?.output_attachment_name || ''}
                    onChange={(e) => update('delivery_config', { ...data.delivery_config, output_attachment_name: e.target.value })}
                    placeholder="workflow_output.html"
                    className="h-8 text-sm"
                  />
                </div>
              )}
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={data.delivery_config?.forward_attachments || false}
                  onChange={(e) => update('delivery_config', { ...data.delivery_config, forward_attachments: e.target.checked })}
                  className="rounded"
                />
                <label className="text-xs text-slate-600 dark:text-slate-400">Encaminhar anexos do email original</label>
              </div>
              {data.delivery_config?.forward_attachments && (
                <div>
                  <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">Filtrar anexos (extensoes)</label>
                  <Input
                    value={(data.delivery_config?.attachment_filter || []).join(', ')}
                    onChange={(e) => {
                      const raw = e.target.value || '';
                      const parts = raw
                        .split(/[,\\s]+/g)
                        .map((p) => p.trim())
                        .filter(Boolean)
                        .map((p) => (p.startsWith('.') ? p : `.${p}`));
                      update('delivery_config', { ...data.delivery_config, attachment_filter: parts });
                    }}
                    placeholder=".pdf, .docx"
                    className="h-8 text-sm"
                  />
                  <p className="text-[10px] text-slate-400 mt-1">Deixe vazio para encaminhar todos os anexos.</p>
                </div>
              )}
            </>
          )}

          {data.delivery_type === 'teams_message' && (
            <>
              <div>
                <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">Formato</label>
                <select
                  value={data.delivery_config?.format || 'card'}
                  onChange={(e) => update('delivery_config', { ...data.delivery_config, format: e.target.value })}
                  className="w-full h-8 rounded-md border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-2 text-sm"
                >
                  <option value="card">Adaptive Card</option>
                  <option value="text">Texto simples</option>
                </select>
              </div>
              <p className="text-[10px] text-slate-400">
                A mensagem sera enviada no chat/canal que disparou o trigger.
              </p>
            </>
          )}

          {data.delivery_type === 'calendar_event' && (
            <>
              <div>
                <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">Titulo do Evento</label>
                <Input
                  value={data.delivery_config?.subject || ''}
                  onChange={(e) => update('delivery_config', { ...data.delivery_config, subject: e.target.value })}
                  placeholder="Prazo: {{output.prazo}}"
                  className="h-8 text-sm"
                />
              </div>
              <div>
                <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">Data/Hora Inicio</label>
                <Input
                  value={data.delivery_config?.start || ''}
                  onChange={(e) => update('delivery_config', { ...data.delivery_config, start: e.target.value })}
                  placeholder="{{output.prazo}} ou 2025-12-31T09:00:00"
                  className="h-8 text-sm"
                />
              </div>
              <div>
                <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">Duracao (minutos)</label>
                <Input
                  type="number"
                  value={data.delivery_config?.duration_minutes || 60}
                  onChange={(e) => update('delivery_config', { ...data.delivery_config, duration_minutes: parseInt(e.target.value) || 60 })}
                  className="h-8 text-sm"
                />
              </div>
              <div>
                <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">Participantes</label>
                <Input
                  value={data.delivery_config?.attendees || ''}
                  onChange={(e) => update('delivery_config', { ...data.delivery_config, attendees: e.target.value })}
                  placeholder="email1@ex.com, email2@ex.com"
                  className="h-8 text-sm"
                />
              </div>
              <div>
                <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">Lembrete (min antes)</label>
                <Input
                  type="number"
                  value={data.delivery_config?.reminder_minutes || 15}
                  onChange={(e) => update('delivery_config', { ...data.delivery_config, reminder_minutes: parseInt(e.target.value) || 15 })}
                  className="h-8 text-sm"
                />
              </div>
            </>
          )}

          {data.delivery_type === 'webhook_out' && (
            <>
              <div>
                <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">URL de Destino</label>
                <Input
                  value={data.delivery_config?.url || ''}
                  onChange={(e) => update('delivery_config', { ...data.delivery_config, url: e.target.value })}
                  placeholder="https://api.exemplo.com/webhook"
                  className="h-8 text-sm"
                />
              </div>
              <div>
                <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">Metodo HTTP</label>
                <select
                  value={data.delivery_config?.method || 'POST'}
                  onChange={(e) => update('delivery_config', { ...data.delivery_config, method: e.target.value })}
                  className="w-full h-8 rounded-md border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-2 text-sm"
                >
                  <option value="POST">POST</option>
                  <option value="PUT">PUT</option>
                </select>
              </div>
            </>
          )}

          {data.delivery_type === 'outlook_reply' && (
            <div>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                Responde automaticamente ao email que disparou o trigger, incluindo o resultado do workflow no corpo da resposta.
              </p>
              <div className="flex items-center gap-2 mt-2">
                <input
                  type="checkbox"
                  checked={data.delivery_config?.include_original_quote ?? true}
                  onChange={(e) => update('delivery_config', { ...data.delivery_config, include_original_quote: e.target.checked })}
                  className="rounded"
                />
                <label className="text-xs text-slate-600 dark:text-slate-400">Incluir citacao original</label>
              </div>
              <div className="flex items-center gap-2 mt-2">
                <input
                  type="checkbox"
                  checked={data.delivery_config?.include_output_attachment || false}
                  onChange={(e) => update('delivery_config', { ...data.delivery_config, include_output_attachment: e.target.checked })}
                  className="rounded"
                />
                <label className="text-xs text-slate-600 dark:text-slate-400">Incluir output como anexo</label>
              </div>
              {data.delivery_config?.include_output_attachment && (
                <div className="mt-2">
                  <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">Nome do anexo (output)</label>
                  <Input
                    value={data.delivery_config?.output_attachment_name || ''}
                    onChange={(e) => update('delivery_config', { ...data.delivery_config, output_attachment_name: e.target.value })}
                    placeholder="workflow_output.html"
                    className="h-8 text-sm"
                  />
                </div>
              )}
              <div className="flex items-center gap-2 mt-2">
                <input
                  type="checkbox"
                  checked={data.delivery_config?.forward_attachments || false}
                  onChange={(e) => update('delivery_config', { ...data.delivery_config, forward_attachments: e.target.checked })}
                  className="rounded"
                />
                <label className="text-xs text-slate-600 dark:text-slate-400">Encaminhar anexos do email original</label>
              </div>
              {data.delivery_config?.forward_attachments && (
                <div className="mt-2">
                  <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">Filtrar anexos (extensoes)</label>
                  <Input
                    value={(data.delivery_config?.attachment_filter || []).join(', ')}
                    onChange={(e) => {
                      const raw = e.target.value || '';
                      const parts = raw
                        .split(/[,\\s]+/g)
                        .map((p) => p.trim())
                        .filter(Boolean)
                        .map((p) => (p.startsWith('.') ? p : `.${p}`));
                      update('delivery_config', { ...data.delivery_config, attachment_filter: parts });
                    }}
                    placeholder=".pdf, .docx"
                    className="h-8 text-sm"
                  />
                  <p className="text-[10px] text-slate-400 mt-1">Deixe vazio para encaminhar todos os anexos.</p>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Duplicate & Delete */}
      <div className="mt-auto pt-4 border-t border-slate-200 dark:border-slate-700 space-y-2">
        <Button
          variant="outline"
          size="sm"
          className="w-full"
          onClick={() => {
            const newId = `${node.type}_${Date.now()}`;
            useWorkflowStore.getState().addNode({
              ...node,
              id: newId,
              position: { x: node.position.x + 50, y: node.position.y + 50 },
              data: { ...node.data, label: `${node.data.label} (cópia)` },
            } as any);
            selectNode(null);
          }}
        >
          Duplicar nó
        </Button>
        <Button
          variant="destructive"
          size="sm"
          className="w-full"
          onClick={() => {
            removeNode(node.id);
            selectNode(null);
          }}
        >
          Remover nó
        </Button>
      </div>
    </div>
  );
}
