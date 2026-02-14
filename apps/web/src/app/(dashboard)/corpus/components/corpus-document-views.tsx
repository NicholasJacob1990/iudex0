'use client';

import {
  FileText,
  Eye,
  CheckCircle2,
  Clock,
  AlertCircle,
  Loader2,
  Trash2,
  RefreshCw,
  FolderOpen,
  MoveRight,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { formatDate, formatFileSize } from '@/lib/utils';
import type { CorpusViewMode } from './corpus-view-controls';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface DocumentItem {
  id: string;
  name: string;
  collection: string | null;
  scope: string | null;
  jurisdiction?: string | null;
  source_id?: string | null;
  status: string;
  ingested_at: string | null;
  expires_at: string | null;
  chunk_count: number | null;
  file_type: string | null;
  size_bytes: number | null;
  folder_path?: string | null;
}

interface DocumentViewProps {
  documents: DocumentItem[];
  viewMode: CorpusViewMode;
  isLoading: boolean;
  onView?: (id: string, name: string) => void;
  onDelete?: (id: string, name: string) => void;
  onReindex?: (id: string, name: string) => void;
  onMove?: (id: string, name: string) => void;
}

// ---------------------------------------------------------------------------
// Status config
// ---------------------------------------------------------------------------

const statusConfig: Record<string, { label: string; icon: React.ComponentType<{ className?: string }>; color: string }> = {
  ingested: { label: 'Indexado', icon: CheckCircle2, color: 'bg-emerald-100 text-emerald-700' },
  pending: { label: 'Pendente', icon: Clock, color: 'bg-amber-100 text-amber-700' },
  processing: { label: 'Processando', icon: Loader2, color: 'bg-blue-100 text-blue-700' },
  failed: { label: 'Falhou', icon: AlertCircle, color: 'bg-red-100 text-red-700' },
};

// ---------------------------------------------------------------------------
// Loading skeleton
// ---------------------------------------------------------------------------

function LoadingSkeleton({ viewMode }: { viewMode: CorpusViewMode }) {
  if (viewMode === 'grid') {
    return (
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-36 rounded-2xl" />
        ))}
      </div>
    );
  }
  return (
    <div className="space-y-2">
      {Array.from({ length: 5 }).map((_, i) => (
        <Skeleton key={i} className="h-16 rounded-xl" />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Empty state
// ---------------------------------------------------------------------------

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center p-12 text-center">
      <FileText className="h-12 w-12 text-muted-foreground/30 mb-4" />
      <p className="text-sm font-medium text-foreground">Nenhum documento encontrado</p>
      <p className="text-xs text-muted-foreground mt-1">
        Envie documentos ou ajuste os filtros.
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// List View
// ---------------------------------------------------------------------------

function ListView({
  documents,
  onView,
  onDelete,
  onReindex,
  onMove,
}: {
  documents: DocumentItem[];
  onView?: (id: string, name: string) => void;
  onDelete?: (id: string, name: string) => void;
  onReindex?: (id: string, name: string) => void;
  onMove?: (id: string, name: string) => void;
}) {
  return (
    <div className="rounded-2xl border border-white/70 bg-white/95 shadow-soft overflow-hidden">
      {/* Header */}
      <div className="hidden lg:grid lg:grid-cols-12 gap-4 px-5 py-3 border-b border-outline/10 text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
        <div className="col-span-4">Nome</div>
        <div className="col-span-1">Juris</div>
        <div className="col-span-2">Tipo</div>
        <div className="col-span-2">Status</div>
        <div className="col-span-2">Data</div>
        <div className="col-span-1 text-right">Acoes</div>
      </div>

      {/* Rows */}
      <div className="divide-y divide-outline/10">
        {documents.map((doc) => {
          const status = statusConfig[doc.status] ?? statusConfig.pending;
          const StatusIcon = status.icon;
          return (
            <div
              key={doc.id}
              className="grid grid-cols-1 lg:grid-cols-12 gap-2 lg:gap-4 px-5 py-3 hover:bg-muted/30 transition-colors items-center"
            >
              <div className="col-span-4 flex items-center gap-3">
                <FileText className="h-4 w-4 text-primary shrink-0" />
                <div className="min-w-0">
                  <p className="text-sm font-medium text-foreground truncate">{doc.name}</p>
                  <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground">
                    <span>{formatFileSize(doc.size_bytes ?? 0)}</span>
                    {doc.chunk_count != null && <span>| {doc.chunk_count} chunks</span>}
                    {doc.folder_path && (
                      <span className="flex items-center gap-0.5">
                        | <FolderOpen className="h-3 w-3" /> {doc.folder_path}
                      </span>
                    )}
                  </div>
                </div>
              </div>
              <div className="col-span-1 space-y-1">
                {doc.jurisdiction ? (
                  <Badge variant="outline" className="rounded-full text-[10px]">
                    {String(doc.jurisdiction).toUpperCase()}
                  </Badge>
                ) : (
                  <span className="text-xs text-muted-foreground">—</span>
                )}
                {doc.source_id ? (
                  <Badge variant="secondary" className="rounded-full text-[10px]">
                    {String(doc.source_id)}
                  </Badge>
                ) : null}
              </div>
              <div className="col-span-2">
                <Badge variant="outline" className="rounded-full text-[10px]">
                  {doc.collection || doc.file_type || 'N/A'}
                </Badge>
              </div>
              <div className="col-span-2">
                <Badge className={`rounded-full text-[10px] border-0 gap-1 ${status.color}`}>
                  <StatusIcon className={`h-3 w-3 ${doc.status === 'processing' ? 'animate-spin' : ''}`} />
                  {status.label}
                </Badge>
              </div>
              <div className="col-span-2">
                <p className="text-xs text-muted-foreground">
                  {doc.ingested_at ? formatDate(doc.ingested_at) : 'Pendente'}
                </p>
              </div>
              <div className="col-span-1 flex items-center justify-end gap-1">
                {onView && (
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8 rounded-full"
                    onClick={() => onView(doc.id, doc.name)}
                    title="Abrir origem"
                  >
                    <Eye className="h-3.5 w-3.5" />
                  </Button>
                )}
                {onMove && (
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8 rounded-full"
                    onClick={() => onMove(doc.id, doc.name)}
                    title="Mover"
                  >
                    <MoveRight className="h-3.5 w-3.5" />
                  </Button>
                )}
                {onReindex && (
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8 rounded-full"
                    onClick={() => onReindex(doc.id, doc.name)}
                    title="Reindexar"
                  >
                    <RefreshCw className="h-3.5 w-3.5" />
                  </Button>
                )}
                {onDelete && (
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8 rounded-full text-destructive"
                    onClick={() => onDelete(doc.id, doc.name)}
                    title="Excluir"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Grid View
// ---------------------------------------------------------------------------

function GridView({
  documents,
  onView,
  onDelete,
  onReindex,
}: {
  documents: DocumentItem[];
  onView?: (id: string, name: string) => void;
  onDelete?: (id: string, name: string) => void;
  onReindex?: (id: string, name: string) => void;
}) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {documents.map((doc) => {
        const status = statusConfig[doc.status] ?? statusConfig.pending;
        const StatusIcon = status.icon;
        return (
          <Card
            key={doc.id}
            className="group rounded-2xl border-white/70 bg-white/95 shadow-soft hover:shadow-md transition-all"
          >
            <CardContent className="p-4 space-y-3">
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-3 min-w-0">
                  <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10 shrink-0">
                    <FileText className="h-5 w-5 text-primary" />
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-foreground truncate" title={doc.name}>
                      {doc.name}
                    </p>
                    <p className="text-[10px] text-muted-foreground">
                      {formatFileSize(doc.size_bytes ?? 0)}
                    </p>
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-2 flex-wrap">
                <Badge className={`rounded-full text-[10px] border-0 gap-1 ${status.color}`}>
                  <StatusIcon className={`h-3 w-3 ${doc.status === 'processing' ? 'animate-spin' : ''}`} />
                  {status.label}
                </Badge>
                {doc.jurisdiction && (
                  <Badge variant="outline" className="rounded-full text-[10px]">
                    {String(doc.jurisdiction).toUpperCase()}
                  </Badge>
                )}
                {doc.source_id && (
                  <Badge variant="secondary" className="rounded-full text-[10px]">
                    {String(doc.source_id)}
                  </Badge>
                )}
                {doc.collection && (
                  <Badge variant="outline" className="rounded-full text-[10px]">
                    {doc.collection}
                  </Badge>
                )}
              </div>

              {doc.folder_path && (
                <div className="flex items-center gap-1 text-[10px] text-muted-foreground">
                  <FolderOpen className="h-3 w-3" />
                  <span className="truncate">{doc.folder_path}</span>
                </div>
              )}

              <div className="flex items-center justify-between text-[10px] text-muted-foreground">
                <span>
                  {doc.ingested_at ? formatDate(doc.ingested_at) : 'Pendente'}
                </span>
                <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                  {onView && (
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-6 w-6 rounded-full"
                      onClick={() => onView(doc.id, doc.name)}
                    >
                      <Eye className="h-3 w-3" />
                    </Button>
                  )}
                  {onReindex && (
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-6 w-6 rounded-full"
                      onClick={() => onReindex(doc.id, doc.name)}
                    >
                      <RefreshCw className="h-3 w-3" />
                    </Button>
                  )}
                  {onDelete && (
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-6 w-6 rounded-full text-destructive"
                      onClick={() => onDelete(doc.id, doc.name)}
                    >
                      <Trash2 className="h-3 w-3" />
                    </Button>
                  )}
                </div>
              </div>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Grouped View
// ---------------------------------------------------------------------------

function GroupedView({
  documents,
  onView,
  onDelete,
  onReindex,
}: {
  documents: DocumentItem[];
  onView?: (id: string, name: string) => void;
  onDelete?: (id: string, name: string) => void;
  onReindex?: (id: string, name: string) => void;
}) {
  // Group by folder_path
  const groups = new Map<string, DocumentItem[]>();

  for (const doc of documents) {
    const key = doc.folder_path || '(Raiz)';
    if (!groups.has(key)) {
      groups.set(key, []);
    }
    groups.get(key)!.push(doc);
  }

  const sortedGroups = Array.from(groups.entries()).sort(([a], [b]) => a.localeCompare(b));

  return (
    <div className="space-y-6">
      {sortedGroups.map(([folderPath, docs]) => (
        <div key={folderPath}>
          <div className="flex items-center gap-2 mb-3">
            <FolderOpen className="h-4 w-4 text-primary" />
            <h3 className="text-sm font-semibold text-foreground">{folderPath}</h3>
            <Badge variant="outline" className="rounded-full text-[10px]">
              {docs.length} doc{docs.length !== 1 ? 's' : ''}
            </Badge>
          </div>

          <div className="rounded-2xl border border-white/70 bg-white/95 shadow-soft overflow-hidden">
            <div className="divide-y divide-outline/10">
              {docs.map((doc) => {
                const status = statusConfig[doc.status] ?? statusConfig.pending;
                const StatusIcon = status.icon;
                return (
                  <div
                    key={doc.id}
                    className="flex items-center gap-3 px-4 py-2.5 hover:bg-muted/30 transition-colors"
                  >
                    <FileText className="h-4 w-4 text-primary shrink-0" />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-foreground truncate">{doc.name}</p>
                      <p className="text-[10px] text-muted-foreground">
                        {formatFileSize(doc.size_bytes ?? 0)}
                        {doc.ingested_at && ` | ${formatDate(doc.ingested_at)}`}
                      </p>
                    </div>
                    <Badge className={`rounded-full text-[10px] border-0 gap-1 ${status.color}`}>
                      <StatusIcon className={`h-3 w-3 ${doc.status === 'processing' ? 'animate-spin' : ''}`} />
                      {status.label}
                    </Badge>
                    <div className="flex items-center gap-1 shrink-0">
                      {onView && (
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7 rounded-full"
                          onClick={() => onView(doc.id, doc.name)}
                        >
                          <Eye className="h-3 w-3" />
                        </Button>
                      )}
                      {onReindex && (
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7 rounded-full"
                          onClick={() => onReindex(doc.id, doc.name)}
                        >
                          <RefreshCw className="h-3 w-3" />
                        </Button>
                      )}
                      {onDelete && (
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7 rounded-full text-destructive"
                          onClick={() => onDelete(doc.id, doc.name)}
                        >
                          <Trash2 className="h-3 w-3" />
                        </Button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main DocumentViews Component
// ---------------------------------------------------------------------------

export function CorpusDocumentViews({
  documents,
  viewMode,
  isLoading,
  onView,
  onDelete,
  onReindex,
  onMove,
}: DocumentViewProps) {
  if (isLoading) {
    return <LoadingSkeleton viewMode={viewMode} />;
  }

  if (!documents.length) {
    return <EmptyState />;
  }

  switch (viewMode) {
    case 'grid':
      return (
        <GridView
          documents={documents}
          onView={onView}
          onDelete={onDelete}
          onReindex={onReindex}
        />
      );
    case 'grouped':
      return (
        <GroupedView
          documents={documents}
          onView={onView}
          onDelete={onDelete}
          onReindex={onReindex}
        />
      );
    case 'list':
    default:
      return (
        <ListView
          documents={documents}
          onView={onView}
          onDelete={onDelete}
          onReindex={onReindex}
          onMove={onMove}
        />
      );
  }
}
