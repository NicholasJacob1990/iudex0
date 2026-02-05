'use client';

import React, { useState, useEffect } from 'react';
import { Search, Star, Download, Store } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';
import { apiClient } from '@/lib/api-client';

interface MarketplaceItem {
  id: string;
  title: string;
  description?: string;
  category: string;
  tags: string[];
  download_count: number;
  avg_rating: number;
  rating_count: number;
  resource_type: string;
  created_at: string;
}

const CATEGORIES = [
  { value: '', label: 'Todos' },
  { value: 'minutas', label: 'Minutas' },
  { value: 'workflows', label: 'Workflows' },
  { value: 'prompts', label: 'Prompts' },
  { value: 'clausulas', label: 'Cláusulas' },
  { value: 'agents', label: 'Agentes' },
  { value: 'pareceres', label: 'Pareceres' },
];

export default function MarketplacePage() {
  const [items, setItems] = useState<MarketplaceItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState('');
  const [sort, setSort] = useState('popular');
  const [page, setPage] = useState(1);
  const [installing, setInstalling] = useState<string | null>(null);

  const loadItems = React.useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (category) params.set('category', category);
      if (search) params.set('search', search);
      params.set('sort', sort);
      params.set('page', String(page));
      const res = await apiClient.request(`/marketplace?${params}`);
      setItems(res.items || []);
      setTotal(res.total || 0);
    } catch {
      toast.error('Erro ao carregar marketplace');
    } finally {
      setLoading(false);
    }
  }, [category, search, sort, page]);

  useEffect(() => {
    loadItems();
  }, [loadItems]);

  async function install(itemId: string) {
    setInstalling(itemId);
    try {
      await apiClient.request(`/marketplace/${itemId}/install`, { method: 'POST' });
      toast.success('Instalado com sucesso!');
      await loadItems();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Erro ao instalar';
      toast.error(message);
    } finally {
      setInstalling(null);
    }
  }

  function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    setPage(1);
    loadItems();
  }

  return (
    <div className="max-w-6xl mx-auto px-6 py-8">
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <Store className="h-6 w-6 text-indigo-500" />
        <h1 className="text-2xl font-bold text-slate-800 dark:text-slate-100">Marketplace</h1>
      </div>

      {/* Search + Filters */}
      <div className="flex flex-col sm:flex-row gap-3 mb-6">
        <form onSubmit={handleSearch} className="flex-1 flex gap-2">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
            <Input
              placeholder="Buscar templates, workflows..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-9"
            />
          </div>
          <Button type="submit" variant="outline" size="icon">
            <Search className="h-4 w-4" />
          </Button>
        </form>
        <div className="flex gap-2">
          <select
            value={category}
            onChange={(e) => { setCategory(e.target.value); setPage(1); }}
            className="h-9 rounded-md border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 text-sm"
          >
            {CATEGORIES.map((c) => (
              <option key={c.value} value={c.value}>{c.label}</option>
            ))}
          </select>
          <select
            value={sort}
            onChange={(e) => { setSort(e.target.value); setPage(1); }}
            className="h-9 rounded-md border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 text-sm"
          >
            <option value="popular">Mais populares</option>
            <option value="recent">Mais recentes</option>
            <option value="rating">Melhor avaliados</option>
          </select>
        </div>
      </div>

      {/* Grid */}
      {loading ? (
        <div className="text-center py-12 text-slate-400">Carregando...</div>
      ) : items.length === 0 ? (
        <div className="text-center py-12 text-slate-400">Nenhum item encontrado</div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {items.map((item) => (
            <div
              key={item.id}
              className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-4 hover:shadow-md transition-shadow"
            >
              <div className="flex items-start justify-between mb-2">
                <span className="text-xs px-2 py-0.5 rounded-full bg-indigo-100 dark:bg-indigo-500/20 text-indigo-600 dark:text-indigo-300 font-medium">
                  {item.category}
                </span>
                <span className="text-xs text-slate-400">{item.resource_type}</span>
              </div>
              <h3 className="font-semibold text-slate-800 dark:text-slate-200 mb-1">{item.title}</h3>
              {item.description && (
                <p className="text-xs text-slate-500 line-clamp-2 mb-3">{item.description}</p>
              )}
              {item.tags.length > 0 && (
                <div className="flex flex-wrap gap-1 mb-3">
                  {item.tags.slice(0, 4).map((tag) => (
                    <span key={tag} className="text-[10px] px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-slate-500">
                      {tag}
                    </span>
                  ))}
                </div>
              )}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3 text-xs text-slate-400">
                  <span className="flex items-center gap-1">
                    <Star className="h-3 w-3 text-amber-400" />
                    {item.avg_rating.toFixed(1)} ({item.rating_count})
                  </span>
                  <span className="flex items-center gap-1">
                    <Download className="h-3 w-3" />
                    {item.download_count}
                  </span>
                </div>
                <Button
                  size="sm"
                  variant="outline"
                  className="h-7 text-xs"
                  onClick={() => install(item.id)}
                  disabled={installing === item.id}
                >
                  {installing === item.id ? 'Instalando...' : 'Instalar'}
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Pagination */}
      {total > 20 && (
        <div className="flex justify-center gap-2 mt-6">
          <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>
            Anterior
          </Button>
          <span className="text-sm text-slate-500 self-center">
            Pagina {page} de {Math.ceil(total / 20)}
          </span>
          <Button variant="outline" size="sm" disabled={page * 20 >= total} onClick={() => setPage(page + 1)}>
            Proxima
          </Button>
        </div>
      )}
    </div>
  );
}
