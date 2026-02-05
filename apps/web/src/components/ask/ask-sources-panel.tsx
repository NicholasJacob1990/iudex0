'use client';

import * as React from 'react';
import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from '@/components/ui/hover-card';
import {
  X,
  ChevronDown,
  ChevronRight,
  FileText,
  Folder,
  Link as LinkIcon,
  ExternalLink,
  Quote,
  CircleDot,
  AlertCircle,
  CheckCircle,
  MinusCircle,
  Scale,
  BookOpen,
  Mic,
  BrainCircuit,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import type { ContextItem } from '@/stores/context-store';

interface Citation {
  id: string;
  title: string;
  source: string;
  snippet?: string;
  signal?: 'positive' | 'negative' | 'caution' | 'neutral';
  url?: string;
}

export interface AskSourcesPanelProps {
  citations: Citation[];
  contextItems: ContextItem[];
  onRemoveItem: (id: string) => void;
  onClose: () => void;
}

// Shepard's signal colors and icons
const getSignalConfig = (signal?: Citation['signal']) => {
  switch (signal) {
    case 'positive':
      return {
        color: 'text-green-600 bg-green-50 border-green-200',
        icon: CheckCircle,
        label: 'Positivo',
      };
    case 'negative':
      return {
        color: 'text-red-600 bg-red-50 border-red-200',
        icon: AlertCircle,
        label: 'Negativo',
      };
    case 'caution':
      return {
        color: 'text-yellow-600 bg-yellow-50 border-yellow-200',
        icon: AlertCircle,
        label: 'Cautela',
      };
    case 'neutral':
    default:
      return {
        color: 'text-gray-600 bg-gray-50 border-gray-200',
        icon: MinusCircle,
        label: 'Neutro',
      };
  }
};

// Context item icon
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
      return Scale;
    case 'audio':
      return Mic;
  }
};

function CitationCard({ citation }: { citation: Citation }) {
  const signalConfig = getSignalConfig(citation.signal);
  const SignalIcon = signalConfig.icon;

  const citationContent = (
    <div className="group rounded-lg border bg-card p-3 hover:bg-accent/50 transition-colors cursor-pointer">
      <div className="flex items-start gap-2">
        <SignalIcon className={cn('h-4 w-4 shrink-0 mt-0.5', signalConfig.color.split(' ')[0])} />
        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-2">
            <h4 className="text-sm font-medium line-clamp-2">{citation.title}</h4>
            {citation.url && (
              <ExternalLink className="h-3 w-3 text-muted-foreground shrink-0 opacity-0 group-hover:opacity-100 transition-opacity" />
            )}
          </div>
          <p className="text-xs text-muted-foreground mt-1">{citation.source}</p>
          {citation.signal && (
            <Badge
              variant="outline"
              className={cn('mt-2 text-xs', signalConfig.color)}
            >
              {signalConfig.label}
            </Badge>
          )}
        </div>
      </div>
    </div>
  );

  // If there's a snippet, wrap in HoverCard for preview
  if (citation.snippet) {
    return (
      <HoverCard>
        <HoverCardTrigger asChild>
          {citation.url ? (
            <a
              href={citation.url}
              target="_blank"
              rel="noopener noreferrer"
              className="block"
            >
              {citationContent}
            </a>
          ) : (
            citationContent
          )}
        </HoverCardTrigger>
        <HoverCardContent className="w-80">
          <div className="space-y-2">
            <div className="flex items-start gap-2">
              <Quote className="h-4 w-4 text-muted-foreground shrink-0 mt-0.5" />
              <p className="text-xs text-muted-foreground italic line-clamp-6">
                {citation.snippet}
              </p>
            </div>
          </div>
        </HoverCardContent>
      </HoverCard>
    );
  }

  // Without snippet, just render clickable if URL exists
  return citation.url ? (
    <a href={citation.url} target="_blank" rel="noopener noreferrer" className="block">
      {citationContent}
    </a>
  ) : (
    citationContent
  );
}

function ContextItemCard({
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
}

export function AskSourcesPanel({
  citations,
  contextItems,
  onRemoveItem,
  onClose,
}: AskSourcesPanelProps) {
  const [citationsOpen, setCitationsOpen] = useState(true);
  const [contextOpen, setContextOpen] = useState(true);

  return (
    <div className="flex flex-col h-full border-l bg-background">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b">
        <h3 className="text-sm font-medium">Fontes e Citações</h3>
        <Button variant="ghost" size="icon" className="h-8 w-8" onClick={onClose}>
          <X className="h-4 w-4" />
          <span className="sr-only">Fechar</span>
        </Button>
      </div>

      <ScrollArea className="flex-1">
        <div className="p-4 space-y-4">
          {/* Citations Section */}
          {citations.length > 0 && (
            <Collapsible open={citationsOpen} onOpenChange={setCitationsOpen}>
              <div className="space-y-3">
                <CollapsibleTrigger asChild>
                  <Button
                    variant="ghost"
                    className="w-full justify-between p-2 h-auto hover:bg-accent/50"
                  >
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
                  {citations.map((citation) => (
                    <CitationCard key={citation.id} citation={citation} />
                  ))}
                </CollapsibleContent>
              </div>
            </Collapsible>
          )}

          {/* Separator between sections */}
          {citations.length > 0 && contextItems.length > 0 && <Separator />}

          {/* Context Items Section */}
          {contextItems.length > 0 && (
            <Collapsible open={contextOpen} onOpenChange={setContextOpen}>
              <div className="space-y-3">
                <CollapsibleTrigger asChild>
                  <Button
                    variant="ghost"
                    className="w-full justify-between p-2 h-auto hover:bg-accent/50"
                  >
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
                    <ContextItemCard
                      key={item.id}
                      item={item}
                      onRemove={onRemoveItem}
                    />
                  ))}
                </CollapsibleContent>
              </div>
            </Collapsible>
          )}

          {/* Empty state */}
          {citations.length === 0 && contextItems.length === 0 && (
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
