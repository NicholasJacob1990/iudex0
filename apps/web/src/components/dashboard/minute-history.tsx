'use client';

import { useMemo, useState } from 'react';
import { Edit3, Copy, Search } from 'lucide-react';
import { minuteHistory, type HistoryGroup } from '@/data/mock';
import { cn, formatDate } from '@/lib/utils';
import { Input } from '@/components/ui/input';

type HistoryItem = (typeof minuteHistory)[number];

interface MinuteHistoryGridProps {
  items?: HistoryItem[];
}

const GROUP_ORDER: HistoryGroup[] = ['Hoje', 'Últimos 7 dias', 'Últimos 30 dias'];

export function MinuteHistoryGrid({ items = minuteHistory }: MinuteHistoryGridProps) {
  const [query, setQuery] = useState('');

  const grouped = useMemo(() => {
    const filtered = items.filter((item) =>
      item.title.toLowerCase().includes(query.toLowerCase())
    );
    const base: Record<HistoryGroup, HistoryItem[]> = {
      Hoje: [],
      'Últimos 7 dias': [],
      'Últimos 30 dias': [],
    };
    return filtered.reduce((acc, item) => {
      acc[item.group].push(item);
      return acc;
    }, base);
  }, [items, query]);

  return (
    <div className="rounded-3xl border border-white/70 bg-white/90 p-5 shadow-soft">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div>
          <h2 className="font-display text-xl text-foreground">Histórico de Minutas</h2>
          <p className="text-sm text-muted-foreground">
            Selecione uma minuta anterior para continuar editando ou visualizar.
          </p>
        </div>
        <div className="relative w-full md:w-72">
          <Search className="absolute left-4 top-3 h-4 w-4 text-muted-foreground" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Buscar por histórico..."
            className="h-11 rounded-full border-transparent bg-sand pl-11"
          />
        </div>
      </div>

      <div className="mt-5 space-y-6">
        {GROUP_ORDER.map((group) => {
          const values = grouped[group];
          if (!values.length) return null;
          return (
            <section key={group} className="space-y-3">
              <div className="flex items-center justify-between text-sm font-semibold text-muted-foreground">
                <span>{group}</span>
                <span className="text-xs uppercase tracking-wide">{values.length} minutas</span>
              </div>
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                {values.map((item) => (
                  <article
                    key={item.id}
                    className="group rounded-2xl border border-white/70 bg-white/90 p-4 shadow-soft transition hover:-translate-y-0.5"
                  >
                    <p className="line-clamp-2 font-semibold text-foreground">{item.title}</p>
                    <p className="mt-2 text-xs text-muted-foreground">{item.jurisdiction}</p>
                    <p className="text-xs text-muted-foreground">{formatDate(new Date(item.date))}</p>
                    <div className="mt-3 flex items-center justify-between text-xs text-muted-foreground">
                      <span className="chip bg-lavender/50 text-foreground">
                        {item.tokens} tokens
                      </span>
                      <div className="flex gap-2 text-muted-foreground">
                        <button
                          type="button"
                          className="rounded-full border border-outline/60 p-1 hover:text-primary"
                          aria-label="Editar"
                        >
                          <Edit3 className="h-4 w-4" />
                        </button>
                        <button
                          type="button"
                          className="rounded-full border border-outline/60 p-1 hover:text-primary"
                          aria-label="Duplicar"
                        >
                          <Copy className="h-4 w-4" />
                        </button>
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}

