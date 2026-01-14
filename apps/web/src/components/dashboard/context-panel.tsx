'use client';

import { useEffect } from 'react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Search, FileText, Layers, Gavel, Scale, UploadCloud } from 'lucide-react';
import { useContextStore } from '@/stores';
import { cn } from '@/lib/utils';
import apiClient from '@/lib/api-client';

const ICONS = {
  documents: FileText,
  models: Layers,
  jurisprudence: Gavel,
  legislation: Scale,
} as const;

export function ContextPanel() {
  const { search, setSearch, sources, toggleSource, toggleMeta, setSourceCounts } = useContextStore();

  useEffect(() => {
    let mounted = true;
    const loadCounts = async () => {
      try {
        const [docs, models, juris, legis] = await Promise.all([
          apiClient.getDocuments(0, 1),
          apiClient.getLibraryItems(0, 1, undefined, 'MODEL'),
          apiClient.getLibraryItems(0, 1, undefined, 'JURISPRUDENCE'),
          apiClient.getLibraryItems(0, 1, undefined, 'LEGISLATION'),
        ]);
        if (!mounted) return;
        setSourceCounts({
          documents: docs.total ?? 0,
          models: models.total ?? 0,
          jurisprudence: juris.total ?? 0,
          legislation: legis.total ?? 0,
        });
      } catch {
        // Silencioso: mantém contagens atuais
      }
    };

    loadCounts();
    return () => {
      mounted = false;
    };
  }, [setSourceCounts]);

  return (
    <section className="rounded-3xl border border-white/70 bg-white/95 p-5 shadow-soft">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs font-semibold uppercase text-muted-foreground">Contexto</p>
          <h2 className="font-display text-xl text-foreground">Adicione contexto à conversa</h2>
        </div>
        <span className="text-xs font-semibold uppercase text-primary">Sem limites</span>
      </div>

      <div className="relative mt-4">
        <Search className="absolute left-4 top-3 h-4 w-4 text-muted-foreground" />
        <Input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Buscar na biblioteca..."
          className="h-11 rounded-2xl border-transparent bg-sand pl-11"
        />
      </div>

      <div className="mt-4 space-y-3">
        {sources
          .filter((source) => source.label.toLowerCase().includes(search.toLowerCase()))
          .map((source) => {
            const Icon = ICONS[source.id];
            return (
              <div
                key={source.id}
                className={cn(
                  'rounded-2xl border border-outline/50 px-4 py-3 transition',
                  source.enabled ? 'bg-primary/5 shadow-soft' : 'bg-sand/60'
                )}
              >
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <span className="rounded-2xl bg-primary/10 p-2 text-primary">
                      <Icon className="h-4 w-4" />
                    </span>
                    <div>
                      <p className="font-semibold text-foreground">{source.label}</p>
                      <p className="text-xs text-muted-foreground">{source.description}</p>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => toggleSource(source.id)}
                    className={cn(
                      'rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-wide',
                      source.enabled
                        ? 'border-primary bg-primary text-primary-foreground'
                        : 'border-outline text-muted-foreground'
                    )}
                  >
                    {source.enabled ? 'Anexado' : 'Anexar'}
                  </button>
                </div>

                <div className="mt-3 flex flex-wrap items-center gap-2 text-xs font-semibold text-muted-foreground">
                  <span className="chip bg-white text-foreground">{source.count} itens</span>
                  {source.meta?.ocr !== undefined && (
                    <TogglePill
                      label="OCR"
                      active={Boolean(source.meta.ocr)}
                      onClick={() => toggleMeta(source.id, 'ocr')}
                    />
                  )}
                  {source.meta?.rigorous !== undefined && (
                    <TogglePill
                      label="Modo rigoroso"
                      active={Boolean(source.meta.rigorous)}
                      onClick={() => toggleMeta(source.id, 'rigorous')}
                    />
                  )}
                  <Button variant="ghost" size="sm" className="rounded-full border border-outline/50 text-xs">
                    <UploadCloud className="mr-1 h-3.5 w-3.5" />
                    Arquivos
                  </Button>
                </div>
              </div>
            );
          })}
      </div>
    </section>
  );
}

function TogglePill({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'rounded-full px-3 py-1 text-[11px] uppercase',
        active ? 'bg-primary text-primary-foreground' : 'bg-sand text-muted-foreground'
      )}
    >
      {label}
    </button>
  );
}
