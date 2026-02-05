'use client';

import React, { useState, useCallback } from 'react';
import { Loader2, Sparkles } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { toast } from 'sonner';

import { apiClient } from '@/lib/api-client';
import { useWorkflowStore } from '@/stores/workflow-store';

const EXAMPLES = [
  {
    label: 'Revisao de contrato DPA',
    description:
      'Receba um contrato DPA em PDF, extraia as clausulas principais usando RAG, analise cada clausula com IA verificando conformidade com LGPD, apresente ao usuario para revisao humana, e gere um relatorio final com as clausulas conformes e nao-conformes.',
  },
  {
    label: 'Analise de jurisprudencia',
    description:
      'O usuario informa o tema juridico, faca uma busca RAG na base de jurisprudencia, use IA para analisar os julgados encontrados identificando tendencias e divergencias, e gere um resumo estruturado com citacoes.',
  },
  {
    label: 'Resumo de depoimento',
    description:
      'Receba o upload de um arquivo de transcricao de depoimento, use IA para identificar os pontos-chave e contradicoes, apresente para revisao humana, e gere um resumo executivo final.',
  },
] as const;

interface NLInputDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function NLInputDialog({ open, onOpenChange }: NLInputDialogProps) {
  const [description, setDescription] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const store = useWorkflowStore();

  const handleGenerate = useCallback(async () => {
    if (description.trim().length < 10) {
      toast.error('Descreva o workflow com pelo menos 10 caracteres');
      return;
    }

    setIsGenerating(true);
    try {
      const result = await apiClient.generateWorkflowFromNL(description);
      const graph = result.graph_json;

      if (graph.nodes?.length) {
        store.pushHistory();
        store.setNodes(graph.nodes);
        store.setEdges(graph.edges || []);
        store.setDirty(true);
        toast.success(`Workflow gerado com ${graph.nodes.length} etapas`);
        onOpenChange(false);
        setDescription('');
      } else {
        toast.error('O grafo gerado esta vazio. Tente uma descricao mais detalhada.');
      }
    } catch (err: any) {
      const detail = err?.response?.data?.detail || err?.message || 'Erro desconhecido';
      toast.error(`Erro ao gerar workflow: ${detail}`);
    } finally {
      setIsGenerating(false);
    }
  }, [description, store, onOpenChange]);

  const handleExampleClick = useCallback((desc: string) => {
    setDescription(desc);
  }, []);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[560px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-violet-500" />
            Criar Workflow com IA
          </DialogTitle>
          <DialogDescription>
            Descreva o workflow que deseja criar em linguagem natural. A IA vai gerar as etapas automaticamente.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <Textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Ex: Receba um contrato em PDF, analise as clausulas com IA, apresente para revisao humana e gere um relatorio final..."
            className="min-h-[120px] resize-none"
            disabled={isGenerating}
          />

          <div className="space-y-2">
            <p className="text-xs text-muted-foreground font-medium">Exemplos:</p>
            <div className="flex flex-wrap gap-2">
              {EXAMPLES.map((example) => (
                <button
                  key={example.label}
                  onClick={() => handleExampleClick(example.description)}
                  disabled={isGenerating}
                  className="text-xs px-3 py-1.5 rounded-full border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors text-slate-600 dark:text-slate-400 disabled:opacity-50"
                >
                  {example.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={isGenerating}
          >
            Cancelar
          </Button>
          <Button
            onClick={handleGenerate}
            disabled={isGenerating || description.trim().length < 10}
            className="gap-2 bg-violet-600 hover:bg-violet-500 text-white"
          >
            {isGenerating ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Gerando...
              </>
            ) : (
              <>
                <Sparkles className="h-4 w-4" />
                Gerar Workflow
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
