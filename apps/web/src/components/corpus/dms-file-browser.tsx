'use client';

import React, { useState, useEffect, useCallback } from 'react';
import {
  Folder,
  File,
  FileText,
  Image as ImageIcon,
  FileSpreadsheet,
  ChevronRight,
  ArrowLeft,
  Search,
  Download,
  Loader2,
  Check,
  X,
  Home,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Checkbox } from '@/components/ui/checkbox';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { toast } from 'sonner';
import { apiClient } from '@/lib/api-client';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface DMSFileItem {
  id: string;
  name: string;
  mime_type: string;
  size?: number | null;
  is_folder: boolean;
  modified_at?: string | null;
  parent_id?: string | null;
  web_url?: string | null;
}

interface BreadcrumbItem {
  id: string | null;
  name: string;
}

interface Props {
  integrationId: string;
  onImportComplete?: (documentIds: string[]) => void;
  targetCorpusProjectId?: string;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatFileSize(bytes?: number | null): string {
  if (!bytes) return '';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

function FileIcon({ mimeType, isFolder }: { mimeType: string; isFolder: boolean }) {
  if (isFolder) return <Folder className="h-5 w-5 text-blue-500" />;
  if (mimeType.includes('pdf')) return <FileText className="h-5 w-5 text-red-500" />;
  if (mimeType.includes('image')) return <ImageIcon className="h-5 w-5 text-green-500" />;
  if (mimeType.includes('spreadsheet') || mimeType.includes('excel'))
    return <FileSpreadsheet className="h-5 w-5 text-emerald-600" />;
  if (mimeType.includes('document') || mimeType.includes('word'))
    return <FileText className="h-5 w-5 text-blue-600" />;
  return <File className="h-5 w-5 text-slate-400" />;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function DMSFileBrowser({ integrationId, onImportComplete, targetCorpusProjectId }: Props) {
  const [files, setFiles] = useState<DMSFileItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [currentFolderId, setCurrentFolderId] = useState<string | null>(null);
  const [breadcrumb, setBreadcrumb] = useState<BreadcrumbItem[]>([{ id: null, name: 'Raiz' }]);
  const [searchQuery, setSearchQuery] = useState('');
  const [searching, setSearching] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [importing, setImporting] = useState(false);
  const [nextPageToken, setNextPageToken] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);

  const loadFiles = useCallback(
    async (folderId: string | null, pageToken?: string | null, query?: string) => {
      const isLoadMore = !!pageToken;
      if (isLoadMore) {
        setLoadingMore(true);
      } else {
        setLoading(true);
      }

      try {
        const res = await apiClient.getDMSFiles(integrationId, {
          folder_id: folderId || undefined,
          page_token: pageToken || undefined,
          query: query || undefined,
        });

        if (isLoadMore) {
          setFiles((prev) => [...prev, ...(res.files || [])]);
        } else {
          setFiles(res.files || []);
        }
        setNextPageToken(res.next_page_token || null);
      } catch {
        toast.error('Erro ao carregar arquivos');
      } finally {
        setLoading(false);
        setLoadingMore(false);
      }
    },
    [integrationId]
  );

  useEffect(() => {
    loadFiles(currentFolderId);
  }, [currentFolderId, loadFiles]);

  function navigateToFolder(folder: DMSFileItem) {
    setSelectedIds(new Set());
    setSearchQuery('');
    setCurrentFolderId(folder.id);
    setBreadcrumb((prev) => [...prev, { id: folder.id, name: folder.name }]);
  }

  function navigateToBreadcrumb(index: number) {
    setSelectedIds(new Set());
    setSearchQuery('');
    const item = breadcrumb[index];
    setCurrentFolderId(item.id);
    setBreadcrumb(breadcrumb.slice(0, index + 1));
  }

  async function handleSearch() {
    if (!searchQuery.trim()) {
      loadFiles(currentFolderId);
      return;
    }
    setSearching(true);
    await loadFiles(currentFolderId, null, searchQuery.trim());
    setSearching(false);
  }

  function toggleSelection(fileId: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(fileId)) {
        next.delete(fileId);
      } else {
        next.add(fileId);
      }
      return next;
    });
  }

  function selectAll() {
    const fileItems = files.filter((f) => !f.is_folder);
    if (selectedIds.size === fileItems.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(fileItems.map((f) => f.id)));
    }
  }

  async function importSelected() {
    if (selectedIds.size === 0) return;
    setImporting(true);
    try {
      const res = await apiClient.importDMSFiles(integrationId, {
        file_ids: Array.from(selectedIds),
        target_corpus_project_id: targetCorpusProjectId,
      });

      if (res.errors?.length) {
        toast.warning(`Importados ${res.imported_count} arquivo(s) com ${res.errors.length} erro(s)`);
      } else {
        toast.success(`${res.imported_count} arquivo(s) importado(s) com sucesso!`);
      }
      setSelectedIds(new Set());
      onImportComplete?.(res.document_ids || []);
    } catch {
      toast.error('Erro ao importar arquivos');
    } finally {
      setImporting(false);
    }
  }

  const fileItems = files.filter((f) => !f.is_folder);
  const folderItems = files.filter((f) => f.is_folder);

  return (
    <div className="flex flex-col h-full">
      {/* Toolbar */}
      <div className="flex items-center gap-2 border-b p-3">
        {/* Breadcrumb */}
        <div className="flex items-center gap-1 flex-1 overflow-x-auto text-sm">
          {breadcrumb.map((item, index) => (
            <React.Fragment key={index}>
              {index > 0 && <ChevronRight className="h-3 w-3 text-muted-foreground flex-shrink-0" />}
              <button
                className={`hover:text-primary whitespace-nowrap ${
                  index === breadcrumb.length - 1
                    ? 'font-medium text-foreground'
                    : 'text-muted-foreground'
                }`}
                onClick={() => navigateToBreadcrumb(index)}
              >
                {index === 0 ? <Home className="h-4 w-4" /> : item.name}
              </button>
            </React.Fragment>
          ))}
        </div>
      </div>

      {/* Search */}
      <div className="flex items-center gap-2 border-b p-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            className="pl-9"
            placeholder="Buscar arquivos..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
          />
        </div>
        <Button variant="outline" size="sm" onClick={handleSearch} disabled={searching}>
          {searching ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Buscar'}
        </Button>
        {searchQuery && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setSearchQuery('');
              loadFiles(currentFolderId);
            }}
          >
            <X className="h-4 w-4" />
          </Button>
        )}
      </div>

      {/* File List */}
      <ScrollArea className="flex-1">
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        ) : files.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
            <Folder className="h-12 w-12 mb-2 opacity-50" />
            <p className="text-sm">Pasta vazia</p>
          </div>
        ) : (
          <div className="divide-y">
            {/* Folders first */}
            {folderItems.map((item) => (
              <button
                key={item.id}
                className="flex items-center gap-3 w-full px-4 py-3 hover:bg-muted/50 text-left"
                onClick={() => navigateToFolder(item)}
              >
                <FileIcon mimeType={item.mime_type} isFolder={true} />
                <div className="flex-1 min-w-0">
                  <p className="truncate text-sm font-medium">{item.name}</p>
                </div>
                <ChevronRight className="h-4 w-4 text-muted-foreground" />
              </button>
            ))}

            {/* Files */}
            {fileItems.map((item) => (
              <div
                key={item.id}
                className={`flex items-center gap-3 px-4 py-3 hover:bg-muted/50 cursor-pointer ${
                  selectedIds.has(item.id) ? 'bg-primary/5' : ''
                }`}
                onClick={() => toggleSelection(item.id)}
              >
                <Checkbox
                  checked={selectedIds.has(item.id)}
                  onCheckedChange={() => toggleSelection(item.id)}
                />
                <FileIcon mimeType={item.mime_type} isFolder={false} />
                <div className="flex-1 min-w-0">
                  <p className="truncate text-sm">{item.name}</p>
                  <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    {item.size && <span>{formatFileSize(item.size)}</span>}
                    {item.modified_at && (
                      <span>
                        {new Date(item.modified_at).toLocaleDateString('pt-BR')}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            ))}

            {/* Load more */}
            {nextPageToken && (
              <div className="flex justify-center py-3">
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={loadingMore}
                  onClick={() => loadFiles(currentFolderId, nextPageToken)}
                >
                  {loadingMore ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : null}
                  Carregar mais
                </Button>
              </div>
            )}
          </div>
        )}
      </ScrollArea>

      {/* Bottom action bar */}
      {fileItems.length > 0 && (
        <div className="flex items-center justify-between border-t p-3 bg-muted/30">
          <div className="flex items-center gap-3">
            <Button variant="ghost" size="sm" onClick={selectAll}>
              {selectedIds.size === fileItems.length ? (
                <>
                  <X className="mr-1 h-3 w-3" /> Limpar seleção
                </>
              ) : (
                <>
                  <Check className="mr-1 h-3 w-3" /> Selecionar tudo
                </>
              )}
            </Button>
            {selectedIds.size > 0 && (
              <Badge variant="secondary">{selectedIds.size} selecionado(s)</Badge>
            )}
          </div>
          <Button
            disabled={selectedIds.size === 0 || importing}
            onClick={importSelected}
          >
            {importing ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Importando...
              </>
            ) : (
              <>
                <Download className="mr-2 h-4 w-4" />
                Importar {selectedIds.size > 0 ? `(${selectedIds.size})` : ''}
              </>
            )}
          </Button>
        </div>
      )}
    </div>
  );
}
