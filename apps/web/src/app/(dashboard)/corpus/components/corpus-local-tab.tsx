'use client';

import { useState } from 'react';
import {
  FileText,
  Clock,
  ArrowUpRight,
  Trash2,
  Timer,
  AlertTriangle,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Progress } from '@/components/ui/progress';
import {
  useCorpusDocuments,
  useDeleteCorpusDocument,
  usePromoteDocument,
  useExtendDocumentTTL,
} from '../hooks/use-corpus';
import { formatDate, formatFileSize } from '@/lib/utils';
import { toast } from 'sonner';
import { CorpusExportButton } from './corpus-export-button';

function getTTLInfo(expiresAt: string | null): { daysLeft: number; hoursLeft: number; percentage: number; isUrgent: boolean } {
  if (!expiresAt) return { daysLeft: 0, hoursLeft: 0, percentage: 0, isUrgent: true };
  const now = Date.now();
  const expiry = new Date(expiresAt).getTime();
  const totalTTL = 7 * 24 * 60 * 60 * 1000; // 7 dias
  const remaining = Math.max(0, expiry - now);
  const daysLeft = Math.floor(remaining / (24 * 60 * 60 * 1000));
  const hoursLeft = Math.floor((remaining % (24 * 60 * 60 * 1000)) / (60 * 60 * 1000));
  const percentage = Math.min(100, (remaining / totalTTL) * 100);
  return { daysLeft, hoursLeft, percentage, isUrgent: daysLeft <= 1 };
}

export function CorpusLocalTab() {
  const { data, isLoading } = useCorpusDocuments({ scope: 'local' });
  const deleteDocument = useDeleteCorpusDocument();
  const promoteDocument = usePromoteDocument();
  const extendTTL = useExtendDocumentTTL();

  const handleDelete = async (id: string, name: string) => {
    if (!confirm(`Deseja excluir "${name}"?`)) return;
    try {
      await deleteDocument.mutateAsync(id);
      toast.success(`"${name}" removido.`);
    } catch {
      toast.error('Erro ao remover documento.');
    }
  };

  const handlePromote = async (id: string, name: string) => {
    try {
      await promoteDocument.mutateAsync(id);
      toast.success(`"${name}" promovido ao Corpus Privado.`);
    } catch {
      toast.error('Erro ao promover documento.');
    }
  };

  const handleExtendTTL = async (id: string, name: string) => {
    try {
      await extendTTL.mutateAsync({ documentId: id, days: 7 });
      toast.success(`TTL de "${name}" estendido por +7 dias.`);
    } catch {
      toast.error('Erro ao estender TTL.');
    }
  };

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-20 rounded-2xl" />
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-24 rounded-2xl" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Info Banner */}
      <div className="rounded-2xl border border-amber-200 bg-amber-50/80 p-4 shadow-soft">
        <div className="flex items-start gap-3">
          <Timer className="h-5 w-5 text-amber-600 shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-medium text-amber-900">Documentos temporarios</p>
            <p className="text-xs text-amber-700 mt-1">
              Documentos enviados em sessoes de chat sao mantidos por 7 dias. Promova ao Corpus Privado para retencao permanente, ou estenda o prazo.
            </p>
          </div>
        </div>
      </div>

      <div className="flex justify-end">
        <CorpusExportButton
          filters={{ scope: 'local' }}
          label="Exportar"
        />
      </div>

      {/* Documents List */}
      {!data?.items.length ? (
        <div className="flex flex-col items-center justify-center rounded-2xl border border-white/70 bg-white/95 p-12 shadow-soft text-center">
          <Clock className="h-12 w-12 text-muted-foreground/30 mb-4" />
          <p className="text-sm font-medium text-foreground">Nenhum documento temporario</p>
          <p className="text-xs text-muted-foreground mt-1">
            Documentos enviados durante sessoes de chat aparecerao aqui.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {data.items.map((doc) => {
            const ttl = getTTLInfo(doc.expires_at);
            return (
              <div
                key={doc.id}
                className="rounded-2xl border border-white/70 bg-white/95 p-4 shadow-soft"
              >
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <div className="flex items-center gap-3 min-w-0">
                    <FileText className="h-5 w-5 text-primary shrink-0" />
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-foreground truncate">{doc.name}</p>
                      <div className="flex items-center gap-2 text-[10px] text-muted-foreground mt-0.5">
                        <span>{formatFileSize(doc.size_bytes ?? 0)}</span>
                        {doc.ingested_at && (
                          <>
                            <span>|</span>
                            <span>Ingerido em {formatDate(doc.ingested_at)}</span>
                          </>
                        )}
                        {doc.chunk_count != null && (
                          <>
                            <span>|</span>
                            <span>{doc.chunk_count} chunks</span>
                          </>
                        )}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <Button
                      variant="outline"
                      size="sm"
                      className="rounded-full gap-1 text-xs"
                      onClick={() => handleExtendTTL(doc.id, doc.name)}
                      disabled={extendTTL.isPending}
                    >
                      <Timer className="h-3 w-3" />
                      +7 dias
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      className="rounded-full gap-1 text-xs"
                      onClick={() => handlePromote(doc.id, doc.name)}
                      disabled={promoteDocument.isPending}
                    >
                      <ArrowUpRight className="h-3 w-3" />
                      Promover
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8 rounded-full text-destructive"
                      onClick={() => handleDelete(doc.id, doc.name)}
                      disabled={deleteDocument.isPending}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </div>

                {/* TTL Progress */}
                <div className="mt-3 space-y-1.5">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1.5">
                      {ttl.isUrgent && <AlertTriangle className="h-3 w-3 text-amber-500" />}
                      <span className={`text-[10px] font-medium ${ttl.isUrgent ? 'text-amber-600' : 'text-muted-foreground'}`}>
                        {ttl.daysLeft > 0
                          ? `${ttl.daysLeft}d ${ttl.hoursLeft}h restantes`
                          : `${ttl.hoursLeft}h restantes`}
                      </span>
                    </div>
                    {doc.expires_at && (
                      <span className="text-[10px] text-muted-foreground">
                        Expira em {formatDate(doc.expires_at)}
                      </span>
                    )}
                  </div>
                  <Progress
                    value={ttl.percentage}
                    className={`h-1.5 ${ttl.isUrgent ? '[&>div]:bg-amber-500' : '[&>div]:bg-indigo-500'}`}
                  />
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Summary */}
      {data?.items && data.items.length > 0 && (
        <div className="text-center">
          <p className="text-xs text-muted-foreground">
            {data.items.length} documento(s) temporario(s) | Expiracao automatica apos 7 dias de inatividade
          </p>
        </div>
      )}
    </div>
  );
}
