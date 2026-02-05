'use client';

import { useState } from 'react';
import {
  Users,
  ChevronDown,
  ChevronRight,
  FileText,
  HardDrive,
  AlertTriangle,
  ArrowRightLeft,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Input } from '@/components/ui/input';
import {
  useCorpusAdminUsers,
  useCorpusAdminUserDocuments,
  useTransferDocumentOwnership,
  type CorpusAdminUserStats,
} from '../hooks/use-corpus';
import { formatFileSize, formatDateTime } from '@/lib/utils';
import { toast } from 'sonner';

function UserDocumentsRow({ user, orgUsers }: { user: CorpusAdminUserStats; orgUsers: CorpusAdminUserStats[] }) {
  const [skip, setSkip] = useState(0);
  const [transferDocId, setTransferDocId] = useState<string | null>(null);
  const [transferTargetId, setTransferTargetId] = useState('');
  const limit = 10;

  const { data: docs, isLoading } = useCorpusAdminUserDocuments(user.user_id, {
    skip,
    limit,
  });

  const transferMutation = useTransferDocumentOwnership();

  const handleTransfer = async (documentId: string) => {
    if (!transferTargetId) {
      toast.error('Selecione o novo proprietario.');
      return;
    }
    try {
      const result = await transferMutation.mutateAsync({
        documentId,
        newOwnerId: transferTargetId,
      });
      if (result.success) {
        toast.success(result.message);
        setTransferDocId(null);
        setTransferTargetId('');
      } else {
        toast.error(result.message);
      }
    } catch {
      toast.error('Erro ao transferir documento.');
    }
  };

  if (isLoading) {
    return (
      <div className="p-4 space-y-2">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-10 w-full rounded-lg" />
        ))}
      </div>
    );
  }

  if (!docs || docs.items.length === 0) {
    return (
      <div className="p-4 text-center">
        <p className="text-sm text-muted-foreground">Nenhum documento encontrado.</p>
      </div>
    );
  }

  return (
    <div className="p-4 space-y-3">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs text-muted-foreground border-b">
              <th className="text-left pb-2 font-medium">Documento</th>
              <th className="text-left pb-2 font-medium">Escopo</th>
              <th className="text-left pb-2 font-medium">Status</th>
              <th className="text-left pb-2 font-medium">Tamanho</th>
              <th className="text-left pb-2 font-medium">Ingerido em</th>
              <th className="text-right pb-2 font-medium">Acoes</th>
            </tr>
          </thead>
          <tbody>
            {docs.items.map((doc) => (
              <tr key={doc.id} className="border-b border-muted/30 last:border-0">
                <td className="py-2 pr-4">
                  <p className="font-medium text-foreground truncate max-w-[200px]" title={doc.name}>
                    {doc.name}
                  </p>
                  <p className="text-[10px] text-muted-foreground">{doc.id.slice(0, 12)}...</p>
                </td>
                <td className="py-2 pr-4">
                  <Badge variant="outline" className="rounded-full text-[10px]">
                    {doc.scope || '-'}
                  </Badge>
                </td>
                <td className="py-2 pr-4">
                  <Badge
                    variant="outline"
                    className={`rounded-full text-[10px] ${
                      doc.status === 'ingested'
                        ? 'border-green-200 text-green-700 bg-green-50'
                        : doc.status === 'failed'
                          ? 'border-red-200 text-red-700 bg-red-50'
                          : 'border-amber-200 text-amber-700 bg-amber-50'
                    }`}
                  >
                    {doc.status === 'ingested'
                      ? 'Ingerido'
                      : doc.status === 'failed'
                        ? 'Falha'
                        : doc.status === 'processing'
                          ? 'Processando'
                          : 'Pendente'}
                  </Badge>
                </td>
                <td className="py-2 pr-4 text-xs text-muted-foreground">
                  {doc.size_bytes ? formatFileSize(doc.size_bytes) : '-'}
                </td>
                <td className="py-2 pr-4 text-xs text-muted-foreground">
                  {doc.ingested_at ? formatDateTime(doc.ingested_at) : '-'}
                </td>
                <td className="py-2 text-right">
                  {transferDocId === doc.id ? (
                    <div className="flex items-center gap-2 justify-end">
                      <select
                        className="text-xs border rounded px-2 py-1 max-w-[150px]"
                        value={transferTargetId}
                        onChange={(e) => setTransferTargetId(e.target.value)}
                      >
                        <option value="">Selecionar...</option>
                        {orgUsers
                          .filter((u) => u.user_id !== user.user_id)
                          .map((u) => (
                            <option key={u.user_id} value={u.user_id}>
                              {u.user_name}
                            </option>
                          ))}
                      </select>
                      <Button
                        size="sm"
                        variant="default"
                        className="h-6 text-[10px] px-2"
                        onClick={() => handleTransfer(doc.id)}
                        disabled={transferMutation.isPending}
                      >
                        Transferir
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-6 text-[10px] px-2"
                        onClick={() => {
                          setTransferDocId(null);
                          setTransferTargetId('');
                        }}
                      >
                        Cancelar
                      </Button>
                    </div>
                  ) : (
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-6 text-[10px] px-2 gap-1"
                      onClick={() => setTransferDocId(doc.id)}
                    >
                      <ArrowRightLeft className="h-3 w-3" />
                      Transferir
                    </Button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Paginacao */}
      {docs.total > limit && (
        <div className="flex items-center justify-between pt-2">
          <p className="text-xs text-muted-foreground">
            Mostrando {skip + 1}-{Math.min(skip + limit, docs.total)} de {docs.total}
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
              disabled={skip + limit >= docs.total}
            >
              Proximo
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

export function CorpusAdminUsersPanel() {
  const [skip, setSkip] = useState(0);
  const [expandedUserId, setExpandedUserId] = useState<string | null>(null);
  const limit = 20;

  const { data: usersData, isLoading, error } = useCorpusAdminUsers({ skip, limit });

  if (isLoading) {
    return (
      <div className="space-y-4">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-16 rounded-2xl" />
        ))}
      </div>
    );
  }

  if (error || !usersData) {
    return (
      <Card className="rounded-2xl border-white/70 bg-white/95 shadow-soft p-8 text-center">
        <AlertTriangle className="h-8 w-8 text-amber-500 mx-auto mb-2" />
        <p className="text-sm text-muted-foreground">
          Falha ao carregar usuarios do Corpus.
        </p>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <Card className="rounded-2xl border-white/70 bg-white/95 shadow-soft">
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Users className="h-4 w-4 text-purple-500" />
              <CardTitle className="text-base">
                Usuarios ({usersData.total})
              </CardTitle>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {usersData.items.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-6">
              Nenhum usuario com documentos no Corpus.
            </p>
          ) : (
            <div className="space-y-2">
              {usersData.items.map((user) => {
                const isExpanded = expandedUserId === user.user_id;

                return (
                  <div
                    key={user.user_id}
                    className="rounded-xl border border-muted/50 overflow-hidden"
                  >
                    {/* User Row */}
                    <button
                      className="w-full flex items-center justify-between p-4 hover:bg-muted/20 transition-colors text-left"
                      onClick={() =>
                        setExpandedUserId(isExpanded ? null : user.user_id)
                      }
                    >
                      <div className="flex items-center gap-4">
                        <div className="flex h-10 w-10 items-center justify-center rounded-full bg-purple-100">
                          <span className="text-sm font-bold text-purple-600">
                            {user.user_name.charAt(0).toUpperCase()}
                          </span>
                        </div>
                        <div>
                          <p className="text-sm font-medium text-foreground">
                            {user.user_name}
                          </p>
                          <p className="text-xs text-muted-foreground">
                            {user.user_email}
                          </p>
                        </div>
                      </div>

                      <div className="flex items-center gap-6">
                        <div className="text-right hidden sm:block">
                          <div className="flex items-center gap-1 text-xs text-muted-foreground">
                            <FileText className="h-3 w-3" />
                            <span>{user.doc_count} docs</span>
                          </div>
                        </div>
                        <div className="text-right hidden sm:block">
                          <div className="flex items-center gap-1 text-xs text-muted-foreground">
                            <HardDrive className="h-3 w-3" />
                            <span>{formatFileSize(user.storage_bytes)}</span>
                          </div>
                        </div>
                        <div className="text-right hidden md:block">
                          <p className="text-xs text-muted-foreground">
                            {user.last_activity
                              ? formatDateTime(user.last_activity)
                              : 'Sem atividade'}
                          </p>
                        </div>
                        <div className="flex items-center gap-1">
                          {user.collections_used.map((c) => (
                            <Badge
                              key={c}
                              variant="secondary"
                              className="text-[10px] rounded-full hidden lg:inline-flex"
                            >
                              {c}
                            </Badge>
                          ))}
                        </div>
                        {isExpanded ? (
                          <ChevronDown className="h-4 w-4 text-muted-foreground" />
                        ) : (
                          <ChevronRight className="h-4 w-4 text-muted-foreground" />
                        )}
                      </div>
                    </button>

                    {/* Expanded Documents */}
                    {isExpanded && (
                      <div className="border-t border-muted/50 bg-muted/10">
                        <UserDocumentsRow user={user} orgUsers={usersData.items} />
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          {/* Paginacao */}
          {usersData.total > limit && (
            <div className="flex items-center justify-between pt-4">
              <p className="text-xs text-muted-foreground">
                Mostrando {skip + 1}-{Math.min(skip + limit, usersData.total)} de{' '}
                {usersData.total}
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
                  disabled={skip + limit >= usersData.total}
                >
                  Proximo
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
