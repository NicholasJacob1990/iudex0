'use client';

import * as React from 'react';
import { useState, useCallback } from 'react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import {
  Check,
  X,
  AlertTriangle,
  Shield,
  ShieldCheck,
  Pencil,
  FileText,
  Loader2,
} from 'lucide-react';
import type { CellExtraction, DynamicColumn } from '@/types/review-table';

interface TableCellProps {
  cell: CellExtraction | undefined;
  column: DynamicColumn;
  documentName?: string;
  onVerify: (cellId: string, verified: boolean, correction?: string) => Promise<void>;
  showConfidence?: boolean;
  isLoading?: boolean;
}

const getConfidenceColor = (confidence: number): string => {
  if (confidence >= 0.8) return 'bg-green-500';
  if (confidence >= 0.5) return 'bg-yellow-500';
  return 'bg-red-500';
};

const getConfidenceLabel = (confidence: number): string => {
  if (confidence >= 0.8) return 'Alta confianca';
  if (confidence >= 0.5) return 'Media confianca';
  return 'Baixa confianca';
};

const formatCellValue = (
  value: string | number | boolean | null,
  extractionType: string
): string => {
  if (value === null || value === undefined) return '-';

  switch (extractionType) {
    case 'boolean':
      return value ? 'Sim' : 'Nao';
    case 'currency':
      if (typeof value === 'number') {
        return new Intl.NumberFormat('pt-BR', {
          style: 'currency',
          currency: 'BRL',
        }).format(value);
      }
      return String(value);
    case 'date':
      if (typeof value === 'string') {
        try {
          return new Date(value).toLocaleDateString('pt-BR');
        } catch {
          return value;
        }
      }
      return String(value);
    case 'number':
      if (typeof value === 'number') {
        return new Intl.NumberFormat('pt-BR').format(value);
      }
      return String(value);
    case 'list':
      if (Array.isArray(value)) {
        return value.join(', ');
      }
      return String(value);
    default:
      return String(value);
  }
};

export function TableCell({
  cell,
  column,
  documentName,
  onVerify,
  showConfidence = true,
  isLoading = false,
}: TableCellProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [editValue, setEditValue] = useState('');
  const [isVerifying, setIsVerifying] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);

  const handleStartEdit = useCallback(() => {
    if (cell) {
      setEditValue(String(cell.value ?? ''));
      setIsEditing(true);
    }
  }, [cell]);

  const handleCancelEdit = useCallback(() => {
    setIsEditing(false);
    setEditValue('');
  }, []);

  const handleSaveEdit = useCallback(async () => {
    if (!cell) return;
    setIsVerifying(true);
    try {
      const correction = editValue !== String(cell.value ?? '') ? editValue : undefined;
      await onVerify(cell.id, true, correction);
      setIsEditing(false);
    } finally {
      setIsVerifying(false);
    }
  }, [cell, editValue, onVerify]);

  const handleVerify = useCallback(
    async (verified: boolean) => {
      if (!cell) return;
      setIsVerifying(true);
      try {
        await onVerify(cell.id, verified);
      } finally {
        setIsVerifying(false);
      }
    },
    [cell, onVerify]
  );

  // Loading state
  if (isLoading || !cell) {
    return (
      <div className="flex items-center justify-center h-full min-h-[40px] text-muted-foreground">
        {isLoading ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <span className="text-xs">-</span>
        )}
      </div>
    );
  }

  // Error state
  if (cell.status === 'error') {
    return (
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <div className="flex items-center gap-1 text-destructive">
              <AlertTriangle className="h-4 w-4" />
              <span className="text-xs truncate">Erro</span>
            </div>
          </TooltipTrigger>
          <TooltipContent>
            <p className="max-w-xs">{cell.error_message || 'Erro na extracao'}</p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    );
  }

  // Processing state
  if (cell.status === 'processing' || cell.status === 'pending') {
    return (
      <div className="flex items-center gap-2 text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        <span className="text-xs">Processando...</span>
      </div>
    );
  }

  const displayValue = cell.correction ?? cell.value;
  const formattedValue = formatCellValue(displayValue, column.extraction_type);
  const confidence = cell.confidence;

  return (
    <Popover open={isExpanded} onOpenChange={setIsExpanded}>
      <PopoverTrigger asChild>
        <div
          className={cn(
            'group relative flex items-center gap-2 px-2 py-1 min-h-[40px] cursor-pointer hover:bg-accent/50 rounded transition-colors',
            cell.is_verified && 'bg-green-50 dark:bg-green-950/20'
          )}
        >
          {/* Confidence indicator */}
          {showConfidence && (
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <div
                    className={cn(
                      'w-1.5 h-6 rounded-full shrink-0',
                      getConfidenceColor(confidence)
                    )}
                  />
                </TooltipTrigger>
                <TooltipContent>
                  <p>
                    {getConfidenceLabel(confidence)} ({Math.round(confidence * 100)}%)
                  </p>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          )}

          {/* Value */}
          <span className="flex-1 truncate text-sm">{formattedValue}</span>

          {/* Verification badge */}
          {cell.is_verified && (
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <ShieldCheck className="h-4 w-4 text-green-600 shrink-0" />
                </TooltipTrigger>
                <TooltipContent>
                  <p>Verificado</p>
                  {cell.verified_at && (
                    <p className="text-xs text-muted-foreground">
                      {new Date(cell.verified_at).toLocaleDateString('pt-BR')}
                    </p>
                  )}
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          )}

          {/* Correction indicator */}
          {cell.correction && (
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Pencil className="h-3 w-3 text-blue-600 shrink-0" />
                </TooltipTrigger>
                <TooltipContent>
                  <p>Valor corrigido</p>
                  <p className="text-xs text-muted-foreground">
                    Original: {formatCellValue(cell.value, column.extraction_type)}
                  </p>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          )}
        </div>
      </PopoverTrigger>

      <PopoverContent className="w-80" align="start">
        <div className="space-y-4">
          {/* Header */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Shield className="h-4 w-4 text-muted-foreground" />
              <span className="font-medium text-sm">{column.name}</span>
            </div>
            <div className="flex items-center gap-1">
              <span
                className={cn(
                  'px-2 py-0.5 rounded text-xs font-medium',
                  confidence >= 0.8
                    ? 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200'
                    : confidence >= 0.5
                      ? 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200'
                      : 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200'
                )}
              >
                {Math.round(confidence * 100)}%
              </span>
            </div>
          </div>

          {/* Value display/edit */}
          {isEditing ? (
            <div className="space-y-2">
              <Input
                value={editValue}
                onChange={(e) => setEditValue(e.target.value)}
                placeholder="Digite o valor correto..."
                autoFocus
              />
              <div className="flex gap-2">
                <Button
                  size="sm"
                  onClick={handleSaveEdit}
                  disabled={isVerifying}
                  className="flex-1"
                >
                  {isVerifying ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <>
                      <Check className="h-4 w-4 mr-1" />
                      Salvar
                    </>
                  )}
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={handleCancelEdit}
                  disabled={isVerifying}
                >
                  <X className="h-4 w-4" />
                </Button>
              </div>
            </div>
          ) : (
            <div className="p-3 bg-muted rounded-md">
              <p className="text-sm break-words">{formattedValue}</p>
              {cell.correction && (
                <p className="text-xs text-muted-foreground mt-1">
                  Original: {formatCellValue(cell.value, column.extraction_type)}
                </p>
              )}
            </div>
          )}

          {/* Source snippet */}
          {cell.source_snippet && (
            <div className="space-y-1">
              <div className="flex items-center gap-1 text-xs text-muted-foreground">
                <FileText className="h-3 w-3" />
                <span>Fonte</span>
                {cell.source_page && <span>(pag. {cell.source_page})</span>}
              </div>
              <div className="p-2 bg-muted/50 rounded text-xs italic max-h-24 overflow-y-auto">
                &quot;{cell.source_snippet}&quot;
              </div>
            </div>
          )}

          {/* Actions */}
          {!isEditing && (
            <div className="flex gap-2 pt-2 border-t">
              {!cell.is_verified ? (
                <>
                  <Button
                    size="sm"
                    variant="outline"
                    className="flex-1"
                    onClick={() => handleVerify(true)}
                    disabled={isVerifying}
                  >
                    {isVerifying ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <>
                        <Check className="h-4 w-4 mr-1" />
                        Verificar
                      </>
                    )}
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={handleStartEdit}
                    disabled={isVerifying}
                  >
                    <Pencil className="h-4 w-4" />
                  </Button>
                </>
              ) : (
                <>
                  <Button
                    size="sm"
                    variant="outline"
                    className="flex-1"
                    onClick={() => handleVerify(false)}
                    disabled={isVerifying}
                  >
                    {isVerifying ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <>
                        <X className="h-4 w-4 mr-1" />
                        Desfazer
                      </>
                    )}
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={handleStartEdit}
                    disabled={isVerifying}
                  >
                    <Pencil className="h-4 w-4" />
                  </Button>
                </>
              )}
            </div>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}
