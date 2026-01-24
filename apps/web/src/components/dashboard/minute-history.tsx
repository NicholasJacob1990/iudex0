'use client';

import { useEffect, useMemo, useState } from 'react';
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
  audit?: {
    status?: string;
    date?: string;
  };
  quality?: {
    score?: number;
    approved?: boolean;
    validated_at?: string;
    total_issues?: number;
    total_content_issues?: number;
    analyzed_at?: string;
  };
}

interface MinuteHistoryGridProps {
  items?: HistoryItem[];
}

const GROUP_ORDER: HistoryGroup[] = ['Hoje', 'Últimos 7 dias', 'Últimos 30 dias'];
const DRAFT_STORAGE_PREFIX = 'iudex_chat_drafts_';
const QUALITY_SUMMARY_PREFIX = 'iudex_quality_summary:';
const QUALITY_CHAT_PREFIX = 'chat:';

const getDraftStorageKey = (chatId: string) => `${DRAFT_STORAGE_PREFIX}${chatId}`;

const formatAuditLabel = (status?: string) => {
  if (!status) return 'Sem auditoria';
  const normalized = status.toLowerCase();
  if (normalized.includes('aprov')) return 'Auditoria aprovada';
  if (normalized.includes('reprov')) return 'Auditoria reprovada';
  if (normalized.includes('pend') || normalized.includes('revis')) return 'Auditoria em revisão';
  return `Auditoria ${status}`;
};

const auditChipClass = (status?: string) => {
  if (!status) return 'bg-sand/70 text-muted-foreground';
  const normalized = status.toLowerCase();
  if (normalized.includes('aprov')) return 'bg-emerald-100/80 text-emerald-800';
  if (normalized.includes('reprov')) return 'bg-rose-100/80 text-rose-700';
  if (normalized.includes('pend') || normalized.includes('revis')) return 'bg-amber-100/80 text-amber-800';
  return 'bg-lavender/50 text-foreground';
};

const formatQualityLabel = (quality?: HistoryItem['quality']) => {
  if (!quality) return null;
  if (typeof quality.score === 'number') {
    return `Qualidade ${quality.score.toFixed(1)}/10`;
  }
  if (typeof quality.total_issues === 'number') {
    return quality.total_issues === 0
      ? 'Qualidade ok'
      : `Qualidade ${quality.total_issues} pend.`;
  }
  return null;
};

const qualityChipClass = (quality?: HistoryItem['quality']) => {
  if (!quality) return 'bg-sand/70 text-muted-foreground';
  if (typeof quality.score === 'number') {
    if (quality.score >= 8) return 'bg-emerald-100/80 text-emerald-800';
    if (quality.score >= 6) return 'bg-amber-100/80 text-amber-800';
    return 'bg-rose-100/80 text-rose-700';
  }
  if (typeof quality.total_issues === 'number') {
    return quality.total_issues > 0
      ? 'bg-amber-100/80 text-amber-800'
      : 'bg-emerald-100/80 text-emerald-800';
  }
  return 'bg-sand/70 text-muted-foreground';
};

const getQualityTimestamp = (quality?: HistoryItem['quality']) =>
  quality?.validated_at || quality?.analyzed_at || '';

export function MinuteHistoryGrid({ items = [] }: MinuteHistoryGridProps) {
  const [query, setQuery] = useState('');
  const [duplicatingId, setDuplicatingId] = useState<string | null>(null);
  const router = useRouter();
  const { duplicateChat } = useChatStore();

  const handleEdit = (chatId: string) => {
    router.push(`/minuta/${chatId}`);
  };

  const handleDuplicate = async (item: HistoryItem) => {
    if (duplicatingId) {
      return;
    }
    setDuplicatingId(item.id);
    try {
      const newChat = await duplicateChat(item.id);
      if (typeof window !== 'undefined') {
        const stored = localStorage.getItem(getDraftStorageKey(item.id));
        if (stored && newChat?.id) {
          localStorage.setItem(getDraftStorageKey(newChat.id), stored);
        }
        const qualityStored = localStorage.getItem(`${QUALITY_SUMMARY_PREFIX}${QUALITY_CHAT_PREFIX}${item.id}`);
        if (qualityStored && newChat?.id) {
          localStorage.setItem(`${QUALITY_SUMMARY_PREFIX}${QUALITY_CHAT_PREFIX}${newChat.id}`, qualityStored);
        }
      }
      if (newChat?.id) {
        router.push(`/minuta/${newChat.id}`);
      }
    } catch (e) {
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
                {values.map((item) => {
                  const qualityLabel = formatQualityLabel(item.quality);
                  return (
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
                      <div className="mt-2 flex flex-wrap gap-2 text-[11px]">
                        <span
                          className={`chip ${auditChipClass(item.audit?.status)}`}
                          title={item.audit?.date ? `Auditado em ${formatDate(item.audit.date)}` : 'Sem data de auditoria'}
                        >
                          {formatAuditLabel(item.audit?.status)}
                        </span>
                        {qualityLabel && (
                          <span
                            className={`chip ${qualityChipClass(item.quality)}`}
                            title={
                              getQualityTimestamp(item.quality)
                                ? `Última atualização ${formatDate(getQualityTimestamp(item.quality))}`
                                : 'Sem data de qualidade'
                            }
                          >
                            {qualityLabel}
                          </span>
                        )}
                      </div>
                      <p className="mt-2 text-xs text-muted-foreground">{item.jurisdiction ?? 'Sem jurisdição'}</p>
                      <p className="text-xs text-muted-foreground">{formatDate(item.date)}</p>
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
                  );
                })}
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}
