'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Search, Filter, Play, Grid3X3, Loader2, Download } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { apiClient } from '@/lib/api-client';
import { useRouter } from 'next/navigation';
import { toast } from 'sonner';

interface CatalogWorkflow {
  id: string;
  name: string;
  description: string | null;
  category: string | null;
  practice_area: string | null;
  output_type: string | null;
  run_count: number;
  tags: string[];
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

export default function WorkflowCatalogPage() {
  const router = useRouter();
  const [workflows, setWorkflows] = useState<CatalogWorkflow[]>([]);
  const [loading, setLoading] = useState(true);
  const [cloning, setCloning] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState('');
  const [outputType, setOutputType] = useState('');

  const searchRef = useRef(search);

  useEffect(() => {
    searchRef.current = search;
  }, [search]);

  const fetchCatalog = useCallback(async (searchValue?: string) => {
    setLoading(true);
    try {
      const data = await apiClient.getWorkflowCatalog({
        category: category || undefined,
        output_type: outputType || undefined,
        search: (searchValue ?? searchRef.current) || undefined,
      });
      setWorkflows(data);
    } catch {
      toast.error('Erro ao carregar catálogo de templates');
    } finally {
      setLoading(false);
    }
  }, [category, outputType]);

  useEffect(() => {
    fetchCatalog();
  }, [fetchCatalog]);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    fetchCatalog(search);
  };

  return (
    <div className="max-w-6xl mx-auto px-6 py-8">
      <div className="flex items-center gap-3 mb-6">
        <Grid3X3 className="h-6 w-6 text-indigo-500" />
        <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">
          Catalogo de Workflows
        </h1>
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
          value={outputType}
          onChange={(e) => setOutputType(e.target.value)}
          className="border rounded-md px-3 py-2 text-sm bg-white dark:bg-slate-900 border-slate-200 dark:border-slate-700"
        >
          {OUTPUT_TYPES.map((t) => (
            <option key={t.value} value={t.value}>{t.label}</option>
          ))}
        </select>
      </div>

      {/* Grid */}
      {loading ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="h-8 w-8 text-indigo-500 animate-spin" />
        </div>
      ) : workflows.length === 0 ? (
        <div className="text-center py-16 text-slate-500">
          Nenhum workflow encontrado
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {workflows.map((wf) => (
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
              <div className="flex items-center justify-between">
                <span className="text-[10px] text-slate-400">
                  {wf.run_count} execuções
                </span>
                <div className="flex gap-1">
                  <Button
                    size="sm"
                    variant="outline"
                    className="gap-1 h-7 text-xs"
                    onClick={() => router.push(`/workflows/${wf.id}`)}
                  >
                    <Play className="h-3 w-3" />
                    Ver
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
    </div>
  );
}
