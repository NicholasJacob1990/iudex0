'use client';

import { Database, FileText, HardDrive, Clock, Loader2 } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { useCorpusStats } from '../hooks/use-corpus';
import { formatFileSize, formatDateTime } from '@/lib/utils';
import { Skeleton } from '@/components/ui/skeleton';

export function CorpusStats() {
  const { data: stats, isLoading } = useCorpusStats();

  if (isLoading) {
    return (
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Card key={i} className="rounded-2xl border-white/70 bg-white/95 shadow-soft">
            <CardContent className="p-5">
              <Skeleton className="h-4 w-24 mb-3" />
              <Skeleton className="h-8 w-16 mb-1" />
              <Skeleton className="h-3 w-32" />
            </CardContent>
          </Card>
        ))}
      </div>
    );
  }

  if (!stats) return null;

  const collectionCount = Object.keys(stats.by_collection).length;
  const storageMb = stats.storage_size_mb ?? 0;
  const storageBytes = storageMb * 1024 * 1024;

  const cards = [
    {
      label: 'Total de Documentos',
      value: stats.total_documents.toLocaleString('pt-BR'),
      description: `Global: ${(stats.by_scope.global ?? 0).toLocaleString('pt-BR')} | Privado: ${(stats.by_scope.private ?? 0).toLocaleString('pt-BR')} | Local: ${(stats.by_scope.local ?? 0).toLocaleString('pt-BR')}`,
      icon: FileText,
      color: 'text-indigo-500',
      bg: 'bg-indigo-50',
    },
    {
      label: 'Colecoes',
      value: collectionCount.toString(),
      description: Object.entries(stats.by_collection)
        .map(([k, v]) => `${k}: ${v.toLocaleString('pt-BR')}`)
        .join(' | '),
      icon: Database,
      color: 'text-purple-500',
      bg: 'bg-purple-50',
    },
    {
      label: 'Armazenamento',
      value: formatFileSize(storageBytes),
      description: `${(stats.by_scope.private ?? 0).toLocaleString('pt-BR')} docs privados indexados`,
      icon: HardDrive,
      color: 'text-emerald-500',
      bg: 'bg-emerald-50',
    },
    {
      label: 'Ultima Indexacao',
      value: stats.last_indexed_at ? formatDateTime(stats.last_indexed_at) : 'N/A',
      description: stats.pending_ingestion > 0
        ? `${stats.pending_ingestion} pendente(s)`
        : stats.failed_ingestion > 0
          ? `${stats.failed_ingestion} com falha`
          : 'Fila de ingestao vazia',
      icon: stats.pending_ingestion > 0 ? Loader2 : Clock,
      color: 'text-amber-500',
      bg: 'bg-amber-50',
      iconAnimation: stats.pending_ingestion > 0 ? 'animate-spin' : '',
    },
  ];

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {cards.map((card) => {
        const Icon = card.icon;
        return (
          <Card key={card.label} className="rounded-2xl border-white/70 bg-white/95 shadow-soft">
            <CardContent className="p-5">
              <div className="flex items-center gap-3 mb-3">
                <div className={`flex h-9 w-9 items-center justify-center rounded-xl ${card.bg}`}>
                  <Icon className={`h-4 w-4 ${card.color} ${'iconAnimation' in card ? card.iconAnimation : ''}`} />
                </div>
                <p className="text-xs font-semibold uppercase text-muted-foreground">{card.label}</p>
              </div>
              <p className="text-2xl font-bold text-foreground">{card.value}</p>
              <p className="mt-1 text-xs text-muted-foreground truncate" title={card.description}>
                {card.description}
              </p>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
