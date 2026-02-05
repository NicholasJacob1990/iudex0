'use client';

import {
  FileText,
  HardDrive,
  Users,
  Clock,
  AlertTriangle,
  Loader2,
  TrendingUp,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { useCorpusAdminOverview } from '../hooks/use-corpus';
import { formatFileSize, formatDateTime } from '@/lib/utils';

export function CorpusAdminOverviewPanel() {
  const { data: overview, isLoading, error } = useCorpusAdminOverview();

  if (isLoading) {
    return (
      <div className="space-y-6">
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
        <div className="grid gap-4 sm:grid-cols-2">
          <Skeleton className="h-64 rounded-2xl" />
          <Skeleton className="h-64 rounded-2xl" />
        </div>
      </div>
    );
  }

  if (error || !overview) {
    return (
      <Card className="rounded-2xl border-white/70 bg-white/95 shadow-soft p-8 text-center">
        <AlertTriangle className="h-8 w-8 text-amber-500 mx-auto mb-2" />
        <p className="text-sm text-muted-foreground">
          Falha ao carregar dados administrativos do Corpus.
        </p>
      </Card>
    );
  }

  const cards = [
    {
      label: 'Total de Documentos',
      value: overview.total_documents.toLocaleString('pt-BR'),
      description: Object.entries(overview.by_scope)
        .map(([k, v]) => `${k}: ${v.toLocaleString('pt-BR')}`)
        .join(' | ') || 'Nenhum documento',
      icon: FileText,
      color: 'text-indigo-500',
      bg: 'bg-indigo-50',
    },
    {
      label: 'Armazenamento Total',
      value: formatFileSize(overview.total_storage_bytes),
      description: `${overview.active_users} usuario(s) ativo(s)`,
      icon: HardDrive,
      color: 'text-emerald-500',
      bg: 'bg-emerald-50',
    },
    {
      label: 'Usuarios Ativos',
      value: overview.active_users.toLocaleString('pt-BR'),
      description: 'Com pelo menos 1 documento no Corpus',
      icon: Users,
      color: 'text-purple-500',
      bg: 'bg-purple-50',
    },
    {
      label: 'Fila de Ingestao',
      value: (
        overview.pending_ingestion + overview.processing_ingestion
      ).toLocaleString('pt-BR'),
      description: overview.failed_ingestion > 0
        ? `${overview.failed_ingestion} com falha`
        : overview.processing_ingestion > 0
          ? `${overview.processing_ingestion} em processamento`
          : 'Fila vazia',
      icon: overview.processing_ingestion > 0 ? Loader2 : Clock,
      color: overview.failed_ingestion > 0 ? 'text-red-500' : 'text-amber-500',
      bg: overview.failed_ingestion > 0 ? 'bg-red-50' : 'bg-amber-50',
      iconAnimation: overview.processing_ingestion > 0 ? 'animate-spin' : '',
    },
  ];

  return (
    <div className="space-y-6">
      {/* Stats Cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {cards.map((card) => {
          const Icon = card.icon;
          return (
            <Card
              key={card.label}
              className="rounded-2xl border-white/70 bg-white/95 shadow-soft"
            >
              <CardContent className="p-5">
                <div className="flex items-center gap-3 mb-3">
                  <div
                    className={`flex h-9 w-9 items-center justify-center rounded-xl ${card.bg}`}
                  >
                    <Icon
                      className={`h-4 w-4 ${card.color} ${
                        'iconAnimation' in card ? card.iconAnimation : ''
                      }`}
                    />
                  </div>
                  <p className="text-xs font-semibold uppercase text-muted-foreground">
                    {card.label}
                  </p>
                </div>
                <p className="text-2xl font-bold text-foreground">{card.value}</p>
                <p
                  className="mt-1 text-xs text-muted-foreground truncate"
                  title={card.description}
                >
                  {card.description}
                </p>
              </CardContent>
            </Card>
          );
        })}
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Top Contribuidores */}
        <Card className="rounded-2xl border-white/70 bg-white/95 shadow-soft">
          <CardHeader className="pb-3">
            <div className="flex items-center gap-2">
              <TrendingUp className="h-4 w-4 text-indigo-500" />
              <CardTitle className="text-base">Top Contribuidores</CardTitle>
            </div>
          </CardHeader>
          <CardContent>
            {overview.top_contributors.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-4">
                Nenhum contribuidor encontrado.
              </p>
            ) : (
              <div className="space-y-3">
                {overview.top_contributors.map((user, idx) => (
                  <div
                    key={user.user_id}
                    className="flex items-center justify-between rounded-xl bg-muted/30 p-3"
                  >
                    <div className="flex items-center gap-3">
                      <div className="flex h-8 w-8 items-center justify-center rounded-full bg-indigo-100 text-xs font-bold text-indigo-600">
                        {idx + 1}
                      </div>
                      <div>
                        <p className="text-sm font-medium text-foreground">
                          {user.user_name}
                        </p>
                        <p className="text-xs text-muted-foreground">{user.user_email}</p>
                      </div>
                    </div>
                    <div className="text-right">
                      <p className="text-sm font-semibold text-foreground">
                        {user.doc_count} docs
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {formatFileSize(user.storage_bytes)}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Atividade Recente */}
        <Card className="rounded-2xl border-white/70 bg-white/95 shadow-soft">
          <CardHeader className="pb-3">
            <div className="flex items-center gap-2">
              <Clock className="h-4 w-4 text-amber-500" />
              <CardTitle className="text-base">Atividade Recente</CardTitle>
            </div>
          </CardHeader>
          <CardContent>
            {overview.recent_activity.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-4">
                Nenhuma atividade recente.
              </p>
            ) : (
              <div className="space-y-2 max-h-80 overflow-y-auto">
                {overview.recent_activity.slice(0, 15).map((activity, idx) => (
                  <div
                    key={`${activity.document_id}-${idx}`}
                    className="flex items-center justify-between rounded-lg bg-muted/20 px-3 py-2"
                  >
                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-medium text-foreground truncate">
                        {activity.document_name}
                      </p>
                      <p className="text-[10px] text-muted-foreground">
                        {activity.user_id?.slice(0, 8)}...
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge
                        variant="outline"
                        className={`text-[10px] rounded-full ${
                          activity.action === 'ingest'
                            ? 'border-green-200 text-green-700 bg-green-50'
                            : activity.action === 'failed'
                              ? 'border-red-200 text-red-700 bg-red-50'
                              : 'border-amber-200 text-amber-700 bg-amber-50'
                        }`}
                      >
                        {activity.action === 'ingest'
                          ? 'Ingerido'
                          : activity.action === 'failed'
                            ? 'Falha'
                            : 'Pendente'}
                      </Badge>
                      {activity.timestamp && (
                        <span className="text-[10px] text-muted-foreground whitespace-nowrap">
                          {formatDateTime(activity.timestamp)}
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Distribuicao por Colecao */}
      {Object.keys(overview.by_collection).length > 0 && (
        <Card className="rounded-2xl border-white/70 bg-white/95 shadow-soft">
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Distribuicao por Colecao</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {Object.entries(overview.by_collection).map(([name, count]) => (
                <div
                  key={name}
                  className="flex items-center justify-between rounded-xl bg-muted/30 p-3"
                >
                  <span className="text-sm font-medium text-foreground capitalize">
                    {name}
                  </span>
                  <Badge variant="secondary" className="rounded-full">
                    {count.toLocaleString('pt-BR')} chunks
                  </Badge>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
