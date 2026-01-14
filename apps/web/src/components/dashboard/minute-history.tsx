'use client';

import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Edit3, Copy, Search } from 'lucide-react';
import { formatDate } from '@/lib/utils';
import { Input } from '@/components/ui/input';
import { useChatStore } from '@/stores';
import { toast } from 'sonner';

export type HistoryGroup = 'Hoje' | 'Últimos 7 dias' | 'Últimos 30 dias';

export interface HistoryItem {
  id: string;
  title: string;
  date: string;
  group: HistoryGroup;
  jurisdiction?: string;
  tokens?: number;
}

interface MinuteHistoryGridProps {
  items?: HistoryItem[];
}

const GROUP_ORDER: HistoryGroup[] = ['Hoje', 'Últimos 7 dias', 'Últimos 30 dias'];
const DRAFT_STORAGE_PREFIX = 'iudex_chat_drafts_';

const getDraftStorageKey = (chatId: string) => `${DRAFT_STORAGE_PREFIX}${chatId}`;

export function MinuteHistoryGrid({ items = [] }: MinuteHistoryGridProps) {
  const [query, setQuery] = useState('');
  const [duplicatingId, setDuplicatingId] = useState<string | null>(null);
  const router = useRouter();
  const { duplicateChat } = useChatStore();

  const handleEdit = (chatId: string) => {
    router.push(`/minuta/${chatId}`);
  };

  const handleDuplicate = async (item: HistoryItem) => {
    if (duplicatingId) return;
    setDuplicatingId(item.id);
    try {
      const newChat = await duplicateChat(item.id);
      if (typeof window !== 'undefined') {
        const stored = localStorage.getItem(getDraftStorageKey(item.id));
        if (stored && newChat?.id) {
          localStorage.setItem(getDraftStorageKey(newChat.id), stored);
        }
      }
      if (newChat?.id) {
        router.push(`/minuta/${newChat.id}`);
      }
    } catch {
      toast.error('Não foi possível duplicar a minuta.');
    } finally {
      setDuplicatingId(null);
    }
  };

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
                    className="group cursor-pointer rounded-2xl border border-white/70 bg-white/90 p-4 shadow-soft transition hover:-translate-y-0.5"
                    role="button"
                    tabIndex={0}
                    onClick={() => handleEdit(item.id)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault();
                        handleEdit(item.id);
                      }
                    }}
                  >
                    <p className="line-clamp-2 font-semibold text-foreground">{item.title}</p>
                    <p className="mt-2 text-xs text-muted-foreground">{item.jurisdiction ?? 'Sem jurisdição'}</p>
                    <p className="text-xs text-muted-foreground">{formatDate(new Date(item.date))}</p>
                    <div className="mt-3 flex items-center justify-between text-xs text-muted-foreground">
                      <span className="chip bg-lavender/50 text-foreground">
                        {typeof item.tokens === 'number' ? `${item.tokens} tokens` : 'Sem contagem'}
                      </span>
                      <div className="flex gap-2 text-muted-foreground">
                        <button
                          type="button"
                          className="rounded-full border border-outline/60 p-1 hover:text-primary"
                          aria-label="Editar"
                          onClick={(event) => {
                            event.stopPropagation();
                            handleEdit(item.id);
                          }}
                        >
                          <Edit3 className="h-4 w-4" />
                        </button>
                        <button
                          type="button"
                          className="rounded-full border border-outline/60 p-1 hover:text-primary"
                          aria-label="Duplicar"
                          onClick={(event) => {
                            event.stopPropagation();
                            handleDuplicate(item);
                          }}
                          disabled={duplicatingId === item.id}
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
