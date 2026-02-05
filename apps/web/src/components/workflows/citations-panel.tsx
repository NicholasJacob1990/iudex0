'use client';

import React, { useState } from 'react';
import { BookOpen, ChevronDown, ChevronRight, ExternalLink, FileText, X } from 'lucide-react';
import { Button } from '@/components/ui/button';

export interface CitationProvenance {
  page_number?: number | null;
  line_start?: number | null;
  line_end?: number | null;
  source_file?: string | null;
  doc_id?: string | null;
}

export interface Citation {
  number: number;
  source: string;
  excerpt: string;
  url?: string;
  provenance?: CitationProvenance | null;
}

interface CitationsPanelProps {
  citations: Citation[];
  isOpen: boolean;
  onToggle: () => void;
}

export function CitationsPanel({ citations, isOpen, onToggle }: CitationsPanelProps) {
  const [expandedItems, setExpandedItems] = useState<Set<number>>(new Set());

  if (!isOpen || citations.length === 0) return null;

  const toggleExpand = (num: number) => {
    setExpandedItems((prev) => {
      const next = new Set(prev);
      if (next.has(num)) {
        next.delete(num);
      } else {
        next.add(num);
      }
      return next;
    });
  };

  return (
    <div className="border-l border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 w-72 flex flex-col max-h-[300px]">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-slate-200 dark:border-slate-700">
        <div className="flex items-center gap-2">
          <BookOpen className="h-4 w-4 text-blue-500" />
          <span className="text-xs font-semibold text-slate-600 dark:text-slate-300">
            Citações ({citations.length})
          </span>
        </div>
        <Button variant="ghost" size="icon" className="h-6 w-6" onClick={onToggle}>
          <X className="h-3.5 w-3.5" />
        </Button>
      </div>

      {/* Citations list */}
      <div className="flex-1 overflow-y-auto px-3 py-2 space-y-1.5">
        {citations
          .sort((a, b) => a.number - b.number)
          .map((citation) => {
            const isExpanded = expandedItems.has(citation.number);
            return (
              <div
                key={citation.number}
                className="rounded-md border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50"
              >
                <button
                  type="button"
                  onClick={() => toggleExpand(citation.number)}
                  className="flex items-start gap-2 w-full px-2.5 py-2 text-left"
                >
                  {isExpanded ? (
                    <ChevronDown className="h-3.5 w-3.5 text-slate-400 mt-0.5 shrink-0" />
                  ) : (
                    <ChevronRight className="h-3.5 w-3.5 text-slate-400 mt-0.5 shrink-0" />
                  )}
                  <div className="flex-1 min-w-0">
                    <span className="text-xs font-medium text-blue-600 dark:text-blue-400">
                      [{citation.number}]
                    </span>{' '}
                    <span className="text-xs text-slate-700 dark:text-slate-300 truncate">
                      {citation.source}
                    </span>
                  </div>
                  {citation.url && (
                    <a
                      href={citation.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      onClick={(e) => e.stopPropagation()}
                      className="shrink-0"
                    >
                      <ExternalLink className="h-3 w-3 text-slate-400 hover:text-blue-500" />
                    </a>
                  )}
                </button>
                {isExpanded && (
                  <div className="px-2.5 pb-2 pt-0 border-t border-slate-200 dark:border-slate-700">
                    {citation.provenance && (
                      <div className="flex items-center gap-1.5 pt-1.5 pb-1">
                        <FileText className="h-3 w-3 text-slate-400 shrink-0" />
                        <span className="text-[10px] text-slate-500 dark:text-slate-400">
                          {formatProvenance(citation.provenance)}
                        </span>
                      </div>
                    )}
                    {citation.excerpt && (
                      <p className="text-xs text-slate-500 dark:text-slate-400 leading-relaxed pt-1">
                        {citation.excerpt}
                      </p>
                    )}
                  </div>
                )}
              </div>
            );
          })}
      </div>
    </div>
  );
}

/**
 * Formata informações de proveniência para exibição.
 */
function formatProvenance(prov: CitationProvenance): string {
  const parts: string[] = [];

  if (prov.source_file) {
    parts.push(`Fonte: ${prov.source_file}`);
  }

  if (prov.page_number != null) {
    parts.push(`p. ${prov.page_number}`);
  }

  if (prov.line_start != null && prov.line_end != null) {
    if (prov.line_start === prov.line_end) {
      parts.push(`linha ${prov.line_start}`);
    } else {
      parts.push(`linhas ${prov.line_start}-${prov.line_end}`);
    }
  }

  return parts.length > 0 ? parts.join(', ') : 'Proveniência desconhecida';
}

/**
 * Parses citation references from LLM output text.
 * Looks for patterns like: [1] Source name - excerpt
 */
export function parseCitations(text: string): Citation[] {
  if (!text) return [];

  const citations: Citation[] = [];
  const regex = /\[(\d+)\]\s*(.+?)(?:\s*[-–—]\s*(.+?))?(?=\n\[|\n*$)/gm;
  let match: RegExpExecArray | null;

  while ((match = regex.exec(text)) !== null) {
    const num = parseInt(match[1], 10);
    const source = match[2].trim();
    const excerpt = (match[3] || '').trim();

    // Avoid duplicates
    if (!citations.some((c) => c.number === num)) {
      citations.push({ number: num, source, excerpt });
    }
  }

  return citations.sort((a, b) => a.number - b.number);
}
