'use client';

import * as React from 'react';
import { useMemo, useState } from 'react';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { X, ChevronDown, ChevronRight, FileText, Folder, Link as LinkIcon, CircleDot, BookOpen, Mic, BrainCircuit, FileSearch, ExternalLink } from 'lucide-react';
import type { ContextItem } from '@/stores/context-store';

export interface AskCitationItem {
  id: string;
  title: string;
  source: string;
  snippet?: string;
  signal?: 'positive' | 'negative' | 'caution' | 'neutral';
  url?: string;
  documentId?: string;
  chunkUid?: string;
  chunkIndex?: number;
  pageNumber?: number;
  lineStart?: number;
  lineEnd?: number;
  sourceFile?: string;
  viewerKind?: 'pdf_native' | 'office_html' | 'external' | 'unavailable' | string;
  viewerUrl?: string;
  downloadUrl?: string;
  sourceUrl?: string;
  highlightText?: string;
}

export interface AskSourcesPanelProps {
  citations: AskCitationItem[];
  contextItems: ContextItem[];
  onRemoveItem: (id: string) => void;
  onClose: () => void;
  onOpenEvidence?: (citation: AskCitationItem) => void;
}

const getContextIcon = (type: ContextItem['type']) => {
  switch (type) {
    case 'file':
      return FileText;
    case 'folder':
      return Folder;
    case 'link':
      return LinkIcon;
    case 'model':
      return BrainCircuit;
    case 'legislation':
      return BookOpen;
    case 'jurisprudence':
      return FileSearch;
    case 'audio':
      return Mic;
  }
};

const ContextItemCard = React.memo(function ContextItemCard({
  item,
  onRemove,
}: {
  item: ContextItem;
  onRemove: (id: string) => void;
}) {
  const Icon = getContextIcon(item.type);

  return (
    <div className="group flex items-center gap-2 rounded-lg border bg-card p-2 hover:bg-accent/50 transition-colors">
      <Icon className="h-4 w-4 text-muted-foreground shrink-0" />
      <span className="flex-1 text-sm truncate">{item.name}</span>
      <Button
        variant="ghost"
        size="icon"
        className="h-6 w-6 opacity-0 group-hover:opacity-100 transition-opacity"
        onClick={() => onRemove(item.id)}
      >
        <X className="h-3 w-3" />
        <span className="sr-only">Remover</span>
      </Button>
    </div>
  );
});

export function AskSourcesPanel({
  citations,
  contextItems,
  onRemoveItem,
  onClose,
  onOpenEvidence,
}: AskSourcesPanelProps) {
  const [citationsOpen, setCitationsOpen] = useState(true);
  const [contextOpen, setContextOpen] = useState(true);
  const [documentsOpen, setDocumentsOpen] = useState<Record<string, boolean>>({});

  const groupedByDocument = useMemo(() => {
    const groups = new Map<
      string,
      {
        key: string;
        title: string;
        source: string;
        citations: AskCitationItem[];
      }
    >();

    for (const citation of citations) {
      const docKey =
        String(citation.documentId || '').trim() ||
        String(citation.sourceFile || '').trim() ||
        String(citation.source || '').trim() ||
        'outros';

      const existing = groups.get(docKey);
      if (existing) {
        existing.citations.push(citation);
        continue;
      }

      groups.set(docKey, {
        key: docKey,
        title:
          String(citation.sourceFile || '').trim() ||
          String(citation.title || '').trim() ||
          `Documento ${groups.size + 1}`,
        source: String(citation.source || '').trim() || 'Fonte',
        citations: [citation],
      });
    }

    const result = Array.from(groups.values()).map((group) => ({
      ...group,
      citations: [...group.citations].sort((a, b) => {
        const pageA = a.pageNumber || 0;
        const pageB = b.pageNumber || 0;
        if (pageA !== pageB) return pageA - pageB;
        return String(a.id).localeCompare(String(b.id));
      }),
    }));
    return result.sort((a, b) => a.title.localeCompare(b.title, 'pt-BR'));
  }, [citations]);

  const handleOpenEvidence = (citation: AskCitationItem) => {
    if (onOpenEvidence) {
      onOpenEvidence(citation);
      return;
    }
    const fallbackUrl =
      (citation.viewerUrl && String(citation.viewerUrl).trim()) ||
      (citation.sourceUrl && String(citation.sourceUrl).trim()) ||
      (citation.url && String(citation.url).trim()) ||
      '';
    if (!fallbackUrl) return;
    window.open(fallbackUrl, '_blank', 'noopener,noreferrer');
  };

  return (
    <div className="flex flex-col h-full border-l bg-background">
      <div className="flex items-center justify-between px-4 py-3 border-b">
        <h3 className="text-sm font-medium">Fontes e Citações</h3>
        <Button variant="ghost" size="icon" className="h-8 w-8" onClick={onClose}>
          <X className="h-4 w-4" />
          <span className="sr-only">Fechar</span>
        </Button>
      </div>

      <ScrollArea className="flex-1">
        <div className="p-4 space-y-4">
          {groupedByDocument.length > 0 && (
            <Collapsible open={citationsOpen} onOpenChange={setCitationsOpen}>
              <div className="space-y-3">
                <CollapsibleTrigger asChild>
                  <Button variant="ghost" className="w-full justify-between p-2 h-auto hover:bg-accent/50">
                    <div className="flex items-center gap-2">
                      {citationsOpen ? (
                        <ChevronDown className="h-4 w-4 text-muted-foreground" />
                      ) : (
                        <ChevronRight className="h-4 w-4 text-muted-foreground" />
                      )}
                      <span className="text-sm font-medium">Citações</span>
                      <Badge variant="secondary" className="text-xs">
                        {citations.length}
                      </Badge>
                    </div>
                  </Button>
                </CollapsibleTrigger>

                <CollapsibleContent className="space-y-2">
                  {groupedByDocument.map((group) => {
                    const isOpen = documentsOpen[group.key] ?? true;
                    const firstCitation = group.citations[0];
                    return (
                      <div key={group.key} className="rounded-xl border bg-card/40 p-2">
                        <button
                          type="button"
                          className="flex w-full items-start justify-between gap-2 rounded-lg px-2 py-1 text-left hover:bg-accent/40"
                          onClick={() =>
                            setDocumentsOpen((prev) => ({
                              ...prev,
                              [group.key]: !isOpen,
                            }))
                          }
                        >
                          <div className="min-w-0">
                            <p className="truncate text-sm font-medium">{group.title}</p>
                            <p className="text-[11px] text-muted-foreground">
                              {group.source} • {group.citations.length} evidência(s)
                            </p>
                          </div>
                          <div className="flex items-center gap-1">
                            {firstCitation.viewerKind ? (
                              <Badge variant="outline" className="rounded-full text-[10px]">
                                {firstCitation.viewerKind}
                              </Badge>
                            ) : null}
                            {isOpen ? (
                              <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
                            ) : (
                              <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
                            )}
                          </div>
                        </button>

                        {isOpen ? (
                          <div className="mt-2 space-y-2">
                            {group.citations.map((citation) => {
                              const pageInfo = citation.pageNumber ? `p. ${citation.pageNumber}` : null;
                              const lineInfo =
                                citation.lineStart && citation.lineEnd
                                  ? citation.lineStart === citation.lineEnd
                                    ? `linha ${citation.lineStart}`
                                    : `linhas ${citation.lineStart}-${citation.lineEnd}`
                                  : null;
                              const metaLine = [pageInfo, lineInfo].filter(Boolean).join(' • ');
                              return (
                                <div key={citation.id} className="rounded-lg border bg-white/80 p-2">
                                  <div className="flex items-start justify-between gap-2">
                                    <p className="text-xs font-medium leading-5">
                                      {citation.title || `Fonte ${citation.id}`}
                                    </p>
                                    <Button
                                      variant="outline"
                                      size="sm"
                                      className="h-7 rounded-full px-2 text-[11px] gap-1"
                                      onClick={() => handleOpenEvidence(citation)}
                                    >
                                      <ExternalLink className="h-3 w-3" />
                                      Abrir evidência
                                    </Button>
                                  </div>
                                  {citation.snippet ? (
                                    <p className="mt-1 text-[11px] text-muted-foreground line-clamp-3">
                                      {citation.snippet}
                                    </p>
                                  ) : null}
                                  <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                                    {metaLine ? (
                                      <Badge variant="secondary" className="rounded-full text-[10px]">
                                        {metaLine}
                                      </Badge>
                                    ) : null}
                                    {citation.chunkIndex != null ? (
                                      <Badge variant="outline" className="rounded-full text-[10px]">
                                        chunk {citation.chunkIndex}
                                      </Badge>
                                    ) : null}
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        ) : null}
                      </div>
                    );
                  })}
                </CollapsibleContent>
              </div>
            </Collapsible>
          )}

          {groupedByDocument.length > 0 && contextItems.length > 0 && <Separator />}

          {contextItems.length > 0 && (
            <Collapsible open={contextOpen} onOpenChange={setContextOpen}>
              <div className="space-y-3">
                <CollapsibleTrigger asChild>
                  <Button variant="ghost" className="w-full justify-between p-2 h-auto hover:bg-accent/50">
                    <div className="flex items-center gap-2">
                      {contextOpen ? (
                        <ChevronDown className="h-4 w-4 text-muted-foreground" />
                      ) : (
                        <ChevronRight className="h-4 w-4 text-muted-foreground" />
                      )}
                      <span className="text-sm font-medium">Contexto</span>
                      <Badge variant="secondary" className="text-xs">
                        {contextItems.length}
                      </Badge>
                    </div>
                  </Button>
                </CollapsibleTrigger>

                <CollapsibleContent className="space-y-2">
                  {contextItems.map((item) => (
                    <ContextItemCard key={item.id} item={item} onRemove={onRemoveItem} />
                  ))}
                </CollapsibleContent>
              </div>
            </Collapsible>
          )}

          {groupedByDocument.length === 0 && contextItems.length === 0 && (
            <div className="text-center py-8 text-muted-foreground">
              <CircleDot className="h-8 w-8 mx-auto mb-2 opacity-20" />
              <p className="text-sm">Nenhuma fonte ou citação disponível</p>
            </div>
          )}
        </div>
      </ScrollArea>
    </div>
  );
}
