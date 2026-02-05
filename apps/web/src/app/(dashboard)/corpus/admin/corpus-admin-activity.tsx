'use client';

import { useState } from 'react';
import { Activity, AlertTriangle, Filter } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { useCorpusAdminActivity } from '../hooks/use-corpus';
import { formatDateTime } from '@/lib/utils';

const ACTION_LABELS: Record<string, { label: string; color: string }> = {
  ingest: { label: 'Ingerido', color: 'border-green-200 text-green-700 bg-green-50' },
  failed: { label: 'Falha', color: 'border-red-200 text-red-700 bg-red-50' },
  pending: { label: 'Pendente', color: 'border-amber-200 text-amber-700 bg-amber-50' },
  processing: { label: 'Processando', color: 'border-blue-200 text-blue-700 bg-blue-50' },
  delete: { label: 'Removido', color: 'border-gray-200 text-gray-700 bg-gray-50' },
  promote: { label: 'Promovido', color: 'border-purple-200 text-purple-700 bg-purple-50' },
  extend_ttl: { label: 'TTL Estendido', color: 'border-teal-200 text-teal-700 bg-teal-50' },
};

export function CorpusAdminActivityPanel() {
  const [skip, setSkip] = useState(0);
  const [actionFilter, setActionFilter] = useState<string | undefined>(undefined);
  const limit = 50;

  const { data: activityData, isLoading, error } = useCorpusAdminActivity({
    skip,
    limit,
    action: actionFilter,
  });

  if (isLoading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 8 }).map((_, i) => (
          <Skeleton key={i} className="h-14 rounded-xl" />
        ))}
      </div>
    );
  }

  if (error || !activityData) {
    return (
      <Card className="rounded-2xl border-white/70 bg-white/95 shadow-soft p-8 text-center">
        <AlertTriangle className="h-8 w-8 text-amber-500 mx-auto mb-2" />
        <p className="text-sm text-muted-foreground">
          Falha ao carregar atividades do Corpus.
        </p>
      </Card>
    );
  }

  const actionOptions = [
    { value: undefined, label: 'Todos' },
    { value: 'ingested', label: 'Ingeridos' },
    { value: 'failed', label: 'Com falha' },
    { value: 'pending', label: 'Pendentes' },
    { value: 'processing', label: 'Processando' },
  ];

  return (
    <Card className="rounded-2xl border-white/70 bg-white/95 shadow-soft">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Activity className="h-4 w-4 text-indigo-500" />
            <CardTitle className="text-base">
              Atividade ({activityData.total})
            </CardTitle>
          </div>
          <div className="flex items-center gap-2">
            <Filter className="h-3 w-3 text-muted-foreground" />
            <div className="flex gap-1">
              {actionOptions.map((opt) => (
                <Button
                  key={opt.label}
                  size="sm"
                  variant={actionFilter === opt.value ? 'default' : 'outline'}
                  className="h-6 text-[10px] px-2 rounded-full"
                  onClick={() => {
                    setActionFilter(opt.value);
                    setSkip(0);
                  }}
                >
                  {opt.label}
                </Button>
              ))}
            </div>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {activityData.items.length === 0 ? (
          <p className="text-sm text-muted-foreground text-center py-8">
            Nenhuma atividade encontrada.
          </p>
        ) : (
          <div className="space-y-2">
            {activityData.items.map((item, idx) => {
              const actionInfo = ACTION_LABELS[item.action] || {
                label: item.action,
                color: 'border-gray-200 text-gray-700 bg-gray-50',
              };

              return (
                <div
                  key={`${item.document_id}-${idx}`}
                  className="flex items-center gap-4 rounded-xl bg-muted/20 px-4 py-3"
                >
                  {/* Indicador de status */}
                  <div
                    className={`h-2 w-2 rounded-full flex-shrink-0 ${
                      item.action === 'ingest'
                        ? 'bg-green-500'
                        : item.action === 'failed'
                          ? 'bg-red-500'
                          : item.action === 'processing'
                            ? 'bg-blue-500'
                            : 'bg-amber-500'
                    }`}
                  />

                  {/* Info do documento */}
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-foreground truncate">
                      {item.document_name}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      por <span className="font-medium">{item.user_name}</span>
                      {item.details?.scope && (
                        <span> &middot; escopo: {item.details.scope}</span>
                      )}
                      {item.details?.collection && (
                        <span> &middot; colecao: {item.details.collection}</span>
                      )}
                    </p>
                  </div>

                  {/* Badge de acao */}
                  <Badge
                    variant="outline"
                    className={`text-[10px] rounded-full flex-shrink-0 ${actionInfo.color}`}
                  >
                    {actionInfo.label}
                  </Badge>

                  {/* Timestamp */}
                  <span className="text-[10px] text-muted-foreground whitespace-nowrap flex-shrink-0">
                    {item.timestamp ? formatDateTime(item.timestamp) : '-'}
                  </span>
                </div>
              );
            })}
          </div>
        )}

        {/* Paginacao */}
        {activityData.total > limit && (
          <div className="flex items-center justify-between pt-4">
            <p className="text-xs text-muted-foreground">
              Mostrando {skip + 1}-{Math.min(skip + limit, activityData.total)} de{' '}
              {activityData.total}
            </p>
            <div className="flex gap-2">
              <Button
                size="sm"
                variant="outline"
                className="h-7 text-xs"
                onClick={() => setSkip(Math.max(0, skip - limit))}
                disabled={skip === 0}
              >
                Anterior
              </Button>
              <Button
                size="sm"
                variant="outline"
                className="h-7 text-xs"
                onClick={() => setSkip(skip + limit)}
                disabled={skip + limit >= activityData.total}
              >
                Proximo
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
