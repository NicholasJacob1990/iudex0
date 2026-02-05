'use client';

import * as React from 'react';
import { useState, useCallback } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import {
  Loader2,
  Wand2,
  Type,
  Hash,
  Calendar,
  ToggleLeft,
  DollarSign,
  List,
  User,
  Sparkles,
  FileText,
  Check,
} from 'lucide-react';
import apiClient from '@/lib/api-client';
import type { DynamicColumn, ExtractionType } from '@/types/review-table';

interface ColumnBuilderModalProps {
  tableId: string;
  open: boolean;
  onClose: () => void;
  onColumnCreated: (column: DynamicColumn) => void;
}

const EXTRACTION_TYPES: Array<{
  value: ExtractionType;
  label: string;
  icon: React.ReactNode;
  description: string;
}> = [
  {
    value: 'text',
    label: 'Texto',
    icon: <Type className="h-4 w-4" />,
    description: 'Texto livre, nomes, descricoes',
  },
  {
    value: 'number',
    label: 'Numero',
    icon: <Hash className="h-4 w-4" />,
    description: 'Valores numericos, quantidades',
  },
  {
    value: 'date',
    label: 'Data',
    icon: <Calendar className="h-4 w-4" />,
    description: 'Datas e periodos',
  },
  {
    value: 'boolean',
    label: 'Sim/Nao',
    icon: <ToggleLeft className="h-4 w-4" />,
    description: 'Respostas binarias',
  },
  {
    value: 'currency',
    label: 'Valor Monetario',
    icon: <DollarSign className="h-4 w-4" />,
    description: 'Valores em reais',
  },
  {
    value: 'list',
    label: 'Lista',
    icon: <List className="h-4 w-4" />,
    description: 'Multiplos valores',
  },
  {
    value: 'entity',
    label: 'Entidade',
    icon: <User className="h-4 w-4" />,
    description: 'Pessoas, empresas, lugares',
  },
];

const SUGGESTED_PROMPTS = [
  'Qual e a data do contrato?',
  'Qual e o valor total?',
  'Quem sao as partes envolvidas?',
  'Qual e o prazo de vigencia?',
  'Existe clausula de rescisao?',
  'Qual e o objeto do contrato?',
];

export function ColumnBuilderModal({
  tableId,
  open,
  onClose,
  onColumnCreated,
}: ColumnBuilderModalProps) {
  const [prompt, setPrompt] = useState('');
  const [columnName, setColumnName] = useState('');
  const [extractionType, setExtractionType] = useState<ExtractionType>('text');
  const [isLoading, setIsLoading] = useState(false);
  const [isPreviewing, setIsPreviewing] = useState(false);
  const [previewResult, setPreviewResult] = useState<{
    suggested_name: string;
    extraction_type: string;
    sample_value: unknown;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleReset = useCallback(() => {
    setPrompt('');
    setColumnName('');
    setExtractionType('text');
    setPreviewResult(null);
    setError(null);
  }, []);

  const handleClose = useCallback(() => {
    handleReset();
    onClose();
  }, [handleReset, onClose]);

  const handlePreview = useCallback(async () => {
    if (!prompt.trim()) return;

    setIsPreviewing(true);
    setError(null);
    setPreviewResult(null);

    try {
      const result = await apiClient.previewColumnExtraction(tableId, prompt.trim());
      setPreviewResult(result);

      // Auto-fill suggestions
      if (result.suggested_name && !columnName) {
        setColumnName(result.suggested_name);
      }
      if (result.extraction_type) {
        setExtractionType(result.extraction_type as ExtractionType);
      }
    } catch (err: unknown) {
      const errorMessage = err instanceof Error ? err.message : 'Erro ao gerar preview';
      setError(errorMessage);
    } finally {
      setIsPreviewing(false);
    }
  }, [tableId, prompt, columnName]);

  const handleCreate = useCallback(async () => {
    if (!prompt.trim()) return;

    setIsLoading(true);
    setError(null);

    try {
      const column = await apiClient.createDynamicColumn(
        tableId,
        prompt.trim(),
        columnName.trim() || undefined,
        extractionType
      );
      onColumnCreated(column);
      handleClose();
    } catch (err: unknown) {
      const errorMessage = err instanceof Error ? err.message : 'Erro ao criar coluna';
      setError(errorMessage);
    } finally {
      setIsLoading(false);
    }
  }, [tableId, prompt, columnName, extractionType, onColumnCreated, handleClose]);

  const handleSuggestedPrompt = useCallback((suggestedPrompt: string) => {
    setPrompt(suggestedPrompt);
    setPreviewResult(null);
  }, []);

  return (
    <Dialog open={open} onOpenChange={(isOpen) => !isOpen && handleClose()}>
      <DialogContent className="sm:max-w-[600px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Wand2 className="h-5 w-5 text-primary" />
            Adicionar Nova Coluna
          </DialogTitle>
          <DialogDescription>
            Descreva em linguagem natural qual informacao voce deseja extrair de cada
            documento.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6 py-4">
          {/* Prompt input */}
          <div className="space-y-2">
            <Label htmlFor="prompt" className="flex items-center gap-2">
              <Sparkles className="h-4 w-4" />
              O que voce quer extrair?
            </Label>
            <Textarea
              id="prompt"
              value={prompt}
              onChange={(e) => {
                setPrompt(e.target.value);
                setPreviewResult(null);
              }}
              placeholder="Ex: Qual e a data de assinatura do contrato?"
              className="min-h-[80px]"
            />

            {/* Suggested prompts */}
            <div className="flex flex-wrap gap-1.5 pt-1">
              {SUGGESTED_PROMPTS.slice(0, 4).map((suggestion) => (
                <Badge
                  key={suggestion}
                  variant="secondary"
                  className="cursor-pointer hover:bg-secondary/80 text-xs"
                  onClick={() => handleSuggestedPrompt(suggestion)}
                >
                  {suggestion}
                </Badge>
              ))}
            </div>
          </div>

          {/* Preview button */}
          <Button
            variant="outline"
            size="sm"
            onClick={handlePreview}
            disabled={!prompt.trim() || isPreviewing}
            className="w-full"
          >
            {isPreviewing ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                Analisando...
              </>
            ) : (
              <>
                <FileText className="h-4 w-4 mr-2" />
                Testar em documento de amostra
              </>
            )}
          </Button>

          {/* Preview result */}
          {previewResult && (
            <Alert className="bg-green-50 dark:bg-green-950/20 border-green-200">
              <Check className="h-4 w-4 text-green-600" />
              <AlertDescription className="text-green-800 dark:text-green-200">
                <div className="space-y-1">
                  <p className="font-medium">Preview da extracao:</p>
                  <p className="text-sm">
                    <span className="text-muted-foreground">Valor extraido: </span>
                    <span className="font-mono">
                      {JSON.stringify(previewResult.sample_value)}
                    </span>
                  </p>
                  <p className="text-sm">
                    <span className="text-muted-foreground">Nome sugerido: </span>
                    {previewResult.suggested_name}
                  </p>
                </div>
              </AlertDescription>
            </Alert>
          )}

          {/* Column name */}
          <div className="space-y-2">
            <Label htmlFor="columnName">Nome da coluna (opcional)</Label>
            <Input
              id="columnName"
              value={columnName}
              onChange={(e) => setColumnName(e.target.value)}
              placeholder="Sera gerado automaticamente se deixar vazio"
            />
          </div>

          {/* Extraction type */}
          <div className="space-y-2">
            <Label>Tipo de extracao</Label>
            <Select
              value={extractionType}
              onValueChange={(value) => setExtractionType(value as ExtractionType)}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {EXTRACTION_TYPES.map((type) => (
                  <SelectItem key={type.value} value={type.value}>
                    <div className="flex items-center gap-2">
                      {type.icon}
                      <div>
                        <span>{type.label}</span>
                        <span className="ml-2 text-xs text-muted-foreground">
                          - {type.description}
                        </span>
                      </div>
                    </div>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Error message */}
          {error && (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={handleClose} disabled={isLoading}>
            Cancelar
          </Button>
          <Button onClick={handleCreate} disabled={!prompt.trim() || isLoading}>
            {isLoading ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                Criando...
              </>
            ) : (
              <>
                <Wand2 className="h-4 w-4 mr-2" />
                Criar Coluna
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
