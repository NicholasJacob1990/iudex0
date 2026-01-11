'use client';

import { useEffect, useMemo, useState } from 'react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Plus, Search, Sparkles, FolderTree, Clock3 } from 'lucide-react';
import { cn, formatDateTime } from '@/lib/utils';
import { useLibraryStore } from '@/stores';

export default function LibrariansPage() {
  const [query, setQuery] = useState('');
  const { librarians, isLoading, fetchLibrarians } = useLibraryStore();

  useEffect(() => {
    fetchLibrarians().catch(() => {
      // erros tratados no interceptor
    });
  }, [fetchLibrarians]);

  const filtered = useMemo(
    () =>
      librarians.filter(
        (item) =>
          item.name.toLowerCase().includes(query.toLowerCase()) ||
          item.description.toLowerCase().includes(query.toLowerCase())
      ),
    [query]
  );

  return (
    <div className="space-y-8">
      <div className="flex flex-col gap-4 rounded-3xl border border-white/70 bg-white/95 p-6 shadow-soft lg:flex-row lg:items-center lg:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase text-muted-foreground">Bibliotecários</p>
          <h1 className="font-display text-3xl text-foreground">Ative grupos de recursos em 1 clique.</h1>
          <p className="text-sm text-muted-foreground">
            Reúna documentos, modelos, legislações e jurisprudências em coleções reusáveis.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <div className="relative">
            <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Buscar bibliotecário..."
              className="h-10 w-64 rounded-full border-outline/40 bg-white/70 pl-10"
            />
          </div>
          <Button className="rounded-full bg-primary text-primary-foreground">
            <Plus className="mr-2 h-4 w-4" />
            Novo
          </Button>
        </div>
      </div>

      {isLoading ? (
        <div className="flex flex-col items-center justify-center gap-3 rounded-3xl border border-dashed border-outline/60 bg-white/80 p-10 text-center shadow-soft">
          <p className="text-sm text-muted-foreground">Carregando bibliotecários...</p>
        </div>
      ) : filtered.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-3 rounded-3xl border border-dashed border-outline/60 bg-white/80 p-10 text-center shadow-soft">
          <Sparkles className="h-8 w-8 text-primary" />
          <p className="text-lg font-semibold text-foreground">Nenhum bibliotecário configurado.</p>
          <p className="text-sm text-muted-foreground max-w-lg">
            Crie grupos temáticos para ativar vários recursos (documentos, modelos, leis e precedentes) de uma só vez.
          </p>
          <Button className="rounded-full bg-primary text-primary-foreground">
            <Plus className="mr-2 h-4 w-4" />
            Criar bibliotecário
          </Button>
        </div>
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {filtered.map((item) => (
            <div
              key={item.id}
              className="rounded-3xl border border-white/70 bg-white/90 p-5 shadow-soft transition hover:-translate-y-0.5"
            >
              <div className="flex items-start justify-between gap-4">
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <FolderTree className="h-4 w-4 text-primary" />
                    <h3 className="font-display text-lg text-foreground">{item.name}</h3>
                  </div>
                  <p className="text-sm text-muted-foreground">{item.description}</p>
                  <div className="flex flex-wrap items-center gap-2 text-xs font-semibold text-muted-foreground">
                    {item.resources.map((resource) => (
                      <span key={resource} className="chip bg-sand text-foreground">
                        {resource}
                      </span>
                    ))}
                  </div>
                </div>
                <span className="flex items-center gap-1 rounded-full bg-lavender/60 px-3 py-1 text-[11px] font-semibold text-foreground">
                  <Clock3 className="h-3.5 w-3.5" />
                  {item.updated_at ? formatDateTime(item.updated_at) : 'Sem data'}
                </span>
              </div>
              <div className="mt-4 flex flex-wrap items-center gap-2">
                <ActionButton label="Ativar agora" accent />
                <ActionButton label="Editar" />
                <ActionButton label="Duplicar" />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ActionButton({ label, accent }: { label: string; accent?: boolean }) {
  return (
    <button
      type="button"
      className={cn(
        'rounded-full border px-3 py-1 text-xs font-semibold transition hover:-translate-y-0.5',
        accent
          ? 'border-primary bg-primary text-primary-foreground shadow-soft'
          : 'border-outline/50 bg-white text-foreground hover:border-primary/50'
      )}
    >
      {label}
    </button>
  );
}
