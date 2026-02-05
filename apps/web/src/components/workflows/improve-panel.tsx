'use client';

import React, { useEffect, useState } from 'react';
import { Sparkles, Loader2, X, ArrowRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from '@/components/ui/sheet';
import { apiClient } from '@/lib/api-client';
import { toast } from 'sonner';

interface Suggestion {
  type: string;
  node_id: string | null;
  title: string;
  description: string;
  suggested_change?: string;
  impact: 'high' | 'medium' | 'low';
}

interface ImprovePanelProps {
  workflowId: string;
  open: boolean;
  onClose: () => void;
  onApplySuggestion: (nodeId: string, suggestedChange: string) => void;
}

const impactConfig: Record<string, { label: string; className: string }> = {
  high: { label: 'Alto', className: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400 border-red-200 dark:border-red-800' },
  medium: { label: 'Médio', className: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400 border-amber-200 dark:border-amber-800' },
  low: { label: 'Baixo', className: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400 border-green-200 dark:border-green-800' },
};

const typeLabels: Record<string, string> = {
  prompt_improvement: 'Melhoria de Prompt',
  structure: 'Estrutura',
  missing_node: 'Nó Faltando',
  performance: 'Performance',
};

export function ImprovePanel({ workflowId, open, onClose, onApplySuggestion }: ImprovePanelProps) {
  const [loading, setLoading] = useState(false);
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [summary, setSummary] = useState('');
  const [fetched, setFetched] = useState(false);

  useEffect(() => {
    if (!open || fetched || !workflowId) return;

    const fetchSuggestions = async () => {
      setLoading(true);
      try {
        const data = await apiClient.improveWorkflow(workflowId);
        setSuggestions(data.suggestions || []);
        setSummary(data.summary || '');
        setFetched(true);
      } catch {
        toast.error('Erro ao obter sugestões de melhoria');
      } finally {
        setLoading(false);
      }
    };

    fetchSuggestions();
  }, [open, fetched, workflowId]);

  // Reset when closed
  useEffect(() => {
    if (!open) {
      setFetched(false);
      setSuggestions([]);
      setSummary('');
    }
  }, [open]);

  const handleApply = (suggestion: Suggestion) => {
    if (suggestion.node_id && suggestion.suggested_change) {
      onApplySuggestion(suggestion.node_id, suggestion.suggested_change);
      toast.success(`Sugestão aplicada ao nó ${suggestion.node_id}`);
    }
  };

  return (
    <Sheet open={open} onOpenChange={(isOpen) => !isOpen && onClose()}>
      <SheetContent className="w-[440px] sm:w-[540px] overflow-y-auto">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-violet-500" />
            Melhorar Workflow
          </SheetTitle>
          <SheetDescription>
            Sugestões de melhoria geradas por IA para otimizar seu workflow.
          </SheetDescription>
        </SheetHeader>

        <div className="mt-6 space-y-4">
          {loading && (
            <div className="flex flex-col items-center justify-center py-12 gap-3">
              <Loader2 className="h-8 w-8 text-violet-500 animate-spin" />
              <p className="text-sm text-muted-foreground">Analisando workflow...</p>
            </div>
          )}

          {!loading && summary && (
            <div className="rounded-lg border border-violet-200 dark:border-violet-800 bg-violet-50 dark:bg-violet-950/30 p-4">
              <p className="text-sm text-violet-800 dark:text-violet-300">{summary}</p>
            </div>
          )}

          {!loading && suggestions.length === 0 && fetched && (
            <div className="text-center py-8">
              <p className="text-sm text-muted-foreground">Nenhuma sugestão encontrada. Seu workflow parece estar bem estruturado!</p>
            </div>
          )}

          {!loading && suggestions.map((suggestion, index) => {
            const impact = impactConfig[suggestion.impact] || impactConfig.low;
            const typeLabel = typeLabels[suggestion.type] || suggestion.type;

            return (
              <div
                key={index}
                className="rounded-lg border border-slate-200 dark:border-slate-700 p-4 space-y-3"
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <Badge variant="outline" className="text-[10px] px-1.5 py-0">
                        {typeLabel}
                      </Badge>
                      <Badge variant="outline" className={`text-[10px] px-1.5 py-0 ${impact.className}`}>
                        {impact.label}
                      </Badge>
                    </div>
                    <h4 className="text-sm font-medium">{suggestion.title}</h4>
                  </div>
                </div>

                <p className="text-sm text-muted-foreground">{suggestion.description}</p>

                {suggestion.suggested_change && (
                  <div className="rounded-md bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 p-3">
                    <p className="text-xs font-medium text-muted-foreground mb-1">Mudança sugerida:</p>
                    <p className="text-xs whitespace-pre-wrap">{suggestion.suggested_change}</p>
                  </div>
                )}

                {suggestion.node_id && suggestion.suggested_change && (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => handleApply(suggestion)}
                    className="gap-1.5 text-violet-700 dark:text-violet-300 border-violet-300 dark:border-violet-700 hover:bg-violet-50 dark:hover:bg-violet-950"
                  >
                    <ArrowRight className="h-3.5 w-3.5" />
                    Aplicar
                  </Button>
                )}
              </div>
            );
          })}
        </div>
      </SheetContent>
    </Sheet>
  );
}
