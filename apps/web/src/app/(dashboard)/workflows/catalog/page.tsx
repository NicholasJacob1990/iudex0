'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Search, Filter, Play, Grid3X3, Loader2, Download, Sparkles, Tag, X } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { apiClient } from '@/lib/api-client';
import { useRouter } from 'next/navigation';
import { toast } from 'sonner';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  BackgroundVariant,
  type Node,
  type Edge,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

interface CatalogWorkflow {
  id: string;
  name: string;
  description: string | null;
  category: string | null;
  practice_area: string | null;
  output_type: string | null;
  run_count: number;
  tags: string[];
  graph_json?: { nodes: any[]; edges: any[] };
}

const CATEGORIES = [
  { value: '', label: 'Todas' },
  { value: 'general', label: 'Geral' },
  { value: 'transactional', label: 'Transacional' },
  { value: 'litigation', label: 'Contencioso' },
  { value: 'financial', label: 'Financeiro' },
  { value: 'administrative', label: 'Administrativo' },
  { value: 'labor', label: 'Trabalhista' },
];

const OUTPUT_TYPES = [
  { value: '', label: 'Todos' },
  { value: 'table', label: 'Tabela' },
  { value: 'memo', label: 'Memo' },
  { value: 'document', label: 'Documento' },
  { value: 'checklist', label: 'Checklist' },
  { value: 'timeline', label: 'Timeline' },
];

const COLLECTIONS: Array<{ id: string; label: string; tags: string[] }> = [
  { id: 'inbox', label: 'Inbox/Email', tags: ['email', 'outlook', 'async', 'triage', 'teams'] },
  { id: 'grafo', label: 'Grafo', tags: ['grafo', 'graph', 'kg', 'neo4j', 'fraude', 'risco'] },
  { id: 'djen', label: 'DJEN/DataJud', tags: ['djen', 'datajud', 'publicações', 'processo', 'cnj'] },
  { id: 'contratos', label: 'Contratos', tags: ['contrato', 'cláusulas', 'redline', 'due diligence', 'tabela'] },
  { id: 'litigio', label: 'Litígio', tags: ['litígio', 'processual', 'depoimento', 'audiência', 'cronologia'] },
  { id: 'qualidade', label: 'QA/Citações', tags: ['cpc', 'citações', 'qa', 'checklist'] },
  { id: 'pesquisa', label: 'Pesquisa', tags: ['deep research', 'jurisprudência', 'legislação', 'web'] },
];

export default function WorkflowCatalogPage() {
  const router = useRouter();
  const [workflows, setWorkflows] = useState<CatalogWorkflow[]>([]);
  const [loading, setLoading] = useState(true);
  const [cloning, setCloning] = useState<string | null>(null);
  const [seeding, setSeeding] = useState(false);
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState('');
  const [practiceArea, setPracticeArea] = useState('');
  const [outputType, setOutputType] = useState('');
  const [tagQuery, setTagQuery] = useState('');
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [selectedCollection, setSelectedCollection] = useState<string>('');
  const [previewWorkflow, setPreviewWorkflow] = useState<CatalogWorkflow | null>(null);

  const searchRef = useRef(search);

  useEffect(() => {
    searchRef.current = search;
  }, [search]);

  const fetchCatalog = useCallback(async (searchValue?: string) => {
    setLoading(true);
    try {
      const data = await apiClient.getWorkflowCatalog({
        category: category || undefined,
        practice_area: practiceArea || undefined,
        output_type: outputType || undefined,
        search: (searchValue ?? searchRef.current) || undefined,
      });
      setWorkflows(data);
    } catch {
      toast.error('Erro ao carregar catálogo de templates');
    } finally {
      setLoading(false);
    }
  }, [category, practiceArea, outputType]);

  useEffect(() => {
    fetchCatalog();
  }, [fetchCatalog]);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    fetchCatalog(search);
  };

  const availablePracticeAreas = Array.from(
    new Set(workflows.map((w) => w.practice_area).filter(Boolean) as string[])
  ).sort((a, b) => a.localeCompare(b, 'pt-BR'));

  const availableTags = Array.from(
    new Set(
      workflows
        .flatMap((w) => (w.tags || []).map((t) => (t || '').trim()))
        .filter((t) => t.length > 0)
        .map((t) => t.toLowerCase())
    )
  ).sort((a, b) => a.localeCompare(b, 'pt-BR'));

  const normalizedTagQuery = tagQuery.trim().toLowerCase();
  const suggestedTags = normalizedTagQuery
    ? availableTags.filter((t) => t.includes(normalizedTagQuery)).slice(0, 12)
    : [];

  const addTag = (raw: string) => {
    const t = (raw || '').trim().toLowerCase();
    if (!t) return;
    setSelectedTags((prev) => (prev.includes(t) ? prev : [...prev, t]));
    setTagQuery('');
  };

  const removeTag = (t: string) => setSelectedTags((prev) => prev.filter((x) => x !== t));

  const clearTags = () => {
    setSelectedTags([]);
    setSelectedCollection('');
  };

  const filteredWorkflows = workflows.filter((w) => {
    if (selectedTags.length === 0) return true;
    const tags = (w.tags || []).map((t) => (t || '').trim().toLowerCase());
    return selectedTags.every((t) => tags.includes(t));
  });

  const previewNodes: Node[] = (previewWorkflow?.graph_json?.nodes || []).map((n: any) => ({
    ...n,
    // Render templates safely without using the full builder nodeTypes/store.
    type: 'default',
    data: { label: n?.data?.label || n?.data?.name || n?.type || 'Node' },
  }));
  const previewEdges: Edge[] = (previewWorkflow?.graph_json?.edges || []).map((e: any) => ({ ...e }));

  return (
    <div className="max-w-6xl mx-auto px-6 py-8">
      <div className="flex items-center justify-between gap-3 mb-6">
        <div className="flex items-center gap-3">
          <Grid3X3 className="h-6 w-6 text-indigo-500" />
          <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">
            Catalogo de Workflows
          </h1>
        </div>
        <Button
          variant="outline"
          className="gap-2"
          disabled={seeding}
          onClick={async () => {
            setSeeding(true);
            try {
              const res = await apiClient.seedWorkflowTemplates();
              toast.success(`Templates carregados: ${res.inserted} novos, ${res.skipped} já existiam.`);
              await fetchCatalog();
            } catch (e: any) {
              const msg = e?.response?.status === 403
                ? 'Sem permissão para carregar templates (precisa ser ADMIN).'
                : 'Erro ao carregar templates.';
              toast.error(msg);
            } finally {
              setSeeding(false);
            }
          }}
        >
          {seeding ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
          Carregar templates
        </Button>
      </div>

      {/* Collections */}
      <div className="flex flex-wrap gap-2 mb-4">
        {COLLECTIONS.map((c) => {
          const active = selectedCollection === c.id;
          return (
            <button
              key={c.id}
              type="button"
              className={`text-xs px-3 py-1.5 rounded-full border transition-colors ${
                active
                  ? 'bg-indigo-600 text-white border-indigo-600'
                  : 'bg-white dark:bg-slate-900 border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200 hover:border-indigo-300 dark:hover:border-indigo-700'
              }`}
              onClick={() => {
                setSelectedCollection(active ? '' : c.id);
                setSelectedTags(active ? [] : c.tags.map((t) => t.toLowerCase()));
              }}
              title={c.tags.join(', ')}
            >
              {c.label}
            </button>
          );
        })}
        {selectedTags.length > 0 && (
          <button
            type="button"
            className="text-xs px-3 py-1.5 rounded-full border bg-white dark:bg-slate-900 border-slate-200 dark:border-slate-700 text-slate-500 hover:text-slate-800 dark:hover:text-slate-100"
            onClick={clearTags}
          >
            Limpar tags
          </button>
        )}
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 mb-6">
        <form onSubmit={handleSearch} className="flex gap-2 flex-1 min-w-[200px]">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Buscar workflows..."
              className="pl-9"
            />
          </div>
          <Button type="submit" variant="outline" size="icon">
            <Filter className="h-4 w-4" />
          </Button>
        </form>

        <select
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          className="border rounded-md px-3 py-2 text-sm bg-white dark:bg-slate-900 border-slate-200 dark:border-slate-700"
        >
          {CATEGORIES.map((c) => (
            <option key={c.value} value={c.value}>{c.label}</option>
          ))}
        </select>

        <select
          value={practiceArea}
          onChange={(e) => setPracticeArea(e.target.value)}
          className="border rounded-md px-3 py-2 text-sm bg-white dark:bg-slate-900 border-slate-200 dark:border-slate-700"
          title="Área de atuação"
        >
          <option value="">Todas as áreas</option>
          {availablePracticeAreas.map((p) => (
            <option key={p} value={p}>{p}</option>
          ))}
        </select>

        <select
          value={outputType}
          onChange={(e) => setOutputType(e.target.value)}
          className="border rounded-md px-3 py-2 text-sm bg-white dark:bg-slate-900 border-slate-200 dark:border-slate-700"
        >
          {OUTPUT_TYPES.map((t) => (
            <option key={t.value} value={t.value}>{t.label}</option>
          ))}
        </select>
      </div>

      {/* Tag filter */}
      <div className="mb-6">
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative flex-1 min-w-[240px]">
            <Tag className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
            <Input
              value={tagQuery}
              onChange={(e) => setTagQuery(e.target.value)}
              placeholder="Filtrar por tags (ex: contrato, grafo, outlook...)"
              className="pl-9"
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  addTag(tagQuery);
                }
              }}
            />
            {suggestedTags.length > 0 && (
              <div className="absolute z-10 mt-1 w-full rounded-md border bg-white dark:bg-slate-900 border-slate-200 dark:border-slate-700 shadow-sm p-1">
                {suggestedTags.map((t) => (
                  <button
                    type="button"
                    key={t}
                    className="w-full text-left text-xs px-2 py-1 rounded hover:bg-slate-100 dark:hover:bg-slate-800"
                    onClick={() => addTag(t)}
                  >
                    {t}
                  </button>
                ))}
              </div>
            )}
          </div>
          <Button
            variant="outline"
            className="gap-2"
            onClick={() => addTag(tagQuery)}
            disabled={!tagQuery.trim()}
          >
            <Tag className="h-4 w-4" />
            Adicionar tag
          </Button>
        </div>

        {selectedTags.length > 0 && (
          <div className="flex flex-wrap gap-2 mt-3">
            {selectedTags.map((t) => (
              <button
                key={t}
                type="button"
                className="text-[11px] px-2 py-1 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-200 border border-slate-200 dark:border-slate-700 flex items-center gap-1"
                onClick={() => removeTag(t)}
                title="Remover tag"
              >
                {t}
                <X className="h-3 w-3 opacity-70" />
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Grid */}
      {loading ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="h-8 w-8 text-indigo-500 animate-spin" />
        </div>
      ) : filteredWorkflows.length === 0 ? (
        <div className="text-center py-16 text-slate-500 space-y-3">
          <div>Nenhum template encontrado com os filtros atuais.</div>
          <div>
            <Button
              variant="outline"
              className="gap-2"
              disabled={seeding}
              onClick={async () => {
                setSeeding(true);
                try {
                  const res = await apiClient.seedWorkflowTemplates();
                  toast.success(`Templates carregados: ${res.inserted} novos, ${res.skipped} já existiam.`);
                  await fetchCatalog();
                } catch (e: any) {
                  const msg = e?.response?.status === 403
                    ? 'Sem permissão para carregar templates (precisa ser ADMIN).'
                    : 'Erro ao carregar templates.';
                  toast.error(msg);
                } finally {
                  setSeeding(false);
                }
              }}
            >
              {seeding ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
              Carregar templates do sistema
            </Button>
          </div>
          <div className="text-xs text-slate-400">
            Se você acabou de adicionar templates no código, rode o seed no backend para inserir no banco.
          </div>
          <pre className="text-[11px] bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-200 rounded-md px-3 py-2 inline-block">
{`cd apps/api && python -m app.scripts.seed_workflow_templates`}
          </pre>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filteredWorkflows.map((wf) => (
            <div
              key={wf.id}
              className="border rounded-lg p-4 bg-white dark:bg-slate-900 hover:shadow-md transition-shadow"
            >
              <div className="flex items-start justify-between mb-2">
                <h3 className="font-semibold text-slate-900 dark:text-slate-100 text-sm">
                  {wf.name}
                </h3>
                {wf.category && (
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-indigo-100 dark:bg-indigo-900 text-indigo-700 dark:text-indigo-300">
                    {CATEGORIES.find((c) => c.value === wf.category)?.label || wf.category}
                  </span>
                )}
              </div>
              {wf.description && (
                <p className="text-xs text-slate-500 mb-3 line-clamp-2">{wf.description}</p>
              )}
              <div className="flex flex-wrap gap-1 mb-3">
                {wf.practice_area && (
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300">
                    {wf.practice_area}
                  </span>
                )}
                {(wf.tags || []).slice(0, 5).map((tag) => {
                  const t = (tag || '').trim().toLowerCase();
                  if (!t) return null;
                  const active = selectedTags.includes(t);
                  return (
                    <button
                      key={t}
                      type="button"
                      className={`text-[10px] px-1.5 py-0.5 rounded border ${
                        active
                          ? 'bg-indigo-50 dark:bg-indigo-950 border-indigo-200 dark:border-indigo-900 text-indigo-700 dark:text-indigo-300'
                          : 'bg-white dark:bg-slate-900 border-slate-200 dark:border-slate-700 text-slate-500 hover:border-indigo-200 dark:hover:border-indigo-900'
                      }`}
                      onClick={() => (active ? removeTag(t) : addTag(t))}
                      title="Filtrar por tag"
                    >
                      {t}
                    </button>
                  );
                })}
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[10px] text-slate-400">
                  {wf.run_count} execuções
                </span>
                <div className="flex gap-1">
                  <Button
                    size="sm"
                    variant="outline"
                    className="gap-1 h-7 text-xs"
                    onClick={() => setPreviewWorkflow(wf)}
                  >
                    <Play className="h-3 w-3" />
                    Prévia
                  </Button>
                  <Button
                    size="sm"
                    className="gap-1 h-7 text-xs bg-indigo-600 hover:bg-indigo-500 text-white"
                    disabled={cloning === wf.id}
                    onClick={async () => {
                      setCloning(wf.id);
                      try {
                        const cloned = await apiClient.cloneWorkflowTemplate(wf.id);
                        toast.success('Workflow instalado!');
                        router.push(`/workflows/${cloned.id}`);
                      } catch {
                        toast.error('Erro ao instalar workflow');
                      } finally {
                        setCloning(null);
                      }
                    }}
                  >
                    {cloning === wf.id ? <Loader2 className="h-3 w-3 animate-spin" /> : <Download className="h-3 w-3" />}
                    Instalar
                  </Button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      <Dialog
        open={!!previewWorkflow}
        onOpenChange={(open) => {
          if (!open) setPreviewWorkflow(null);
        }}
      >
        <DialogContent className="sm:max-w-4xl">
          <DialogHeader>
            <DialogTitle className="text-base">{previewWorkflow?.name}</DialogTitle>
            <DialogDescription className="text-xs">
              {previewWorkflow?.description || 'Template do sistema. Instale para editar e executar no seu workspace.'}
            </DialogDescription>
          </DialogHeader>

          <div className="rounded-lg border border-slate-200 dark:border-slate-800 overflow-hidden bg-slate-50 dark:bg-slate-950 h-[420px]">
            {previewNodes.length === 0 ? (
              <div className="h-full flex items-center justify-center text-xs text-slate-500">
                Este template não possui nós (vazio).
              </div>
            ) : (
              <ReactFlow
                nodes={previewNodes}
                edges={previewEdges}
                fitView
                nodesDraggable={false}
                nodesConnectable={false}
                elementsSelectable={false}
                panOnDrag
                zoomOnScroll
                zoomOnDoubleClick={false}
                proOptions={{ hideAttribution: true }}
                className="bg-slate-50 dark:bg-slate-950"
              >
                <Background variant={BackgroundVariant.Dots} gap={18} size={1} color="#e2e8f0" />
                <Controls className="!bg-white dark:!bg-slate-800 !border-slate-200 dark:!border-slate-700 !shadow-sm" />
                <MiniMap
                  className="!bg-white dark:!bg-slate-800 !border-slate-200 dark:!border-slate-700"
                  nodeColor="#818cf8"
                  maskColor="rgba(0,0,0,0.08)"
                />
              </ReactFlow>
            )}
          </div>

          <div className="flex items-center justify-end gap-2">
            <Button variant="outline" size="sm" onClick={() => setPreviewWorkflow(null)}>
              Fechar
            </Button>
            <Button
              size="sm"
              className="bg-indigo-600 hover:bg-indigo-500 text-white"
              disabled={!previewWorkflow || cloning === previewWorkflow?.id}
              onClick={async () => {
                if (!previewWorkflow) return;
                setCloning(previewWorkflow.id);
                try {
                  const cloned = await apiClient.cloneWorkflowTemplate(previewWorkflow.id);
                  toast.success('Workflow instalado!');
                  setPreviewWorkflow(null);
                  router.push(`/workflows/${cloned.id}`);
                } catch {
                  toast.error('Erro ao instalar workflow');
                } finally {
                  setCloning(null);
                }
              }}
            >
              {cloning === previewWorkflow?.id ? <Loader2 className="h-3 w-3 animate-spin" /> : <Download className="h-3 w-3" />}
              Instalar e abrir
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
