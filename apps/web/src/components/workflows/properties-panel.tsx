'use client';

import React, { useEffect, useState, useCallback } from 'react';
import { X, FileText, Loader2, Globe, Folder, Scale, Search, Database, Pencil, Paperclip, Upload } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useWorkflowStore } from '@/stores/workflow-store';
import { apiClient } from '@/lib/api-client';
import { MODEL_REGISTRY } from '@/config/models';
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
        <div>
          <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">Nome da Tool</label>
          <Input
            value={data.tool_name || ''}
            onChange={(e) => update('tool_name', e.target.value)}
            placeholder="search_jurisprudencia"
            className="h-8 text-sm"
          />
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
            <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 block">
              Modelos (um por linha)
            </label>
            <textarea
              value={(data.models || ['claude-sonnet-4-20250514']).join('\n')}
              onChange={(e) => update('models', e.target.value.split('\n').filter(Boolean))}
              placeholder="claude-sonnet-4-20250514&#10;gpt-4o"
              rows={3}
              className="w-full rounded-md border border-slate-200 dark:border-slate-700 bg-transparent px-3 py-2 text-sm font-mono resize-none focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
            />
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
