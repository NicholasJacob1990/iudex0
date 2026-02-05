'use client';

import * as React from 'react';
import { useState, useCallback } from 'react';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Badge } from '@/components/ui/badge';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  GripVertical,
  Eye,
  EyeOff,
  MoreVertical,
  Trash2,
  RefreshCw,
  Plus,
  Columns3,
  Loader2,
  Type,
  Hash,
  Calendar,
  ToggleLeft,
  DollarSign,
  List,
  User,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import apiClient from '@/lib/api-client';
import { useReviewTableStore } from '@/stores/review-table-store';
import type { DynamicColumn, ExtractionType } from '@/types/review-table';

interface ManageColumnsPanelProps {
  tableId: string;
  open: boolean;
  onClose: () => void;
  onAddColumn: () => void;
}

const getTypeIcon = (type: ExtractionType) => {
  switch (type) {
    case 'text':
      return <Type className="h-3 w-3" />;
    case 'number':
      return <Hash className="h-3 w-3" />;
    case 'date':
      return <Calendar className="h-3 w-3" />;
    case 'boolean':
      return <ToggleLeft className="h-3 w-3" />;
    case 'currency':
      return <DollarSign className="h-3 w-3" />;
    case 'list':
      return <List className="h-3 w-3" />;
    case 'entity':
      return <User className="h-3 w-3" />;
    default:
      return <Type className="h-3 w-3" />;
  }
};

const getTypeLabel = (type: ExtractionType) => {
  const labels: Record<ExtractionType, string> = {
    text: 'Texto',
    number: 'Numero',
    date: 'Data',
    boolean: 'Sim/Nao',
    currency: 'Valor',
    list: 'Lista',
    entity: 'Entidade',
  };
  return labels[type] || type;
};

interface ColumnItemProps {
  column: DynamicColumn;
  isVisible: boolean;
  onToggleVisibility: () => void;
  onDelete: () => void;
  onReprocess: () => void;
  isDeleting: boolean;
  isReprocessing: boolean;
  isDragging?: boolean;
  dragHandleProps?: React.HTMLAttributes<HTMLDivElement>;
}

function ColumnItem({
  column,
  isVisible,
  onToggleVisibility,
  onDelete,
  onReprocess,
  isDeleting,
  isReprocessing,
  isDragging,
  dragHandleProps,
}: ColumnItemProps) {
  return (
    <div
      className={cn(
        'flex items-center gap-3 p-3 rounded-lg border bg-card transition-all',
        isDragging && 'shadow-lg scale-[1.02]',
        !isVisible && 'opacity-60'
      )}
    >
      {/* Drag handle */}
      <div
        {...dragHandleProps}
        className="cursor-grab hover:bg-muted rounded p-1"
      >
        <GripVertical className="h-4 w-4 text-muted-foreground" />
      </div>

      {/* Column info */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="font-medium text-sm truncate">{column.name}</span>
          <Badge variant="secondary" className="text-xs shrink-0">
            {getTypeIcon(column.extraction_type)}
            <span className="ml-1">{getTypeLabel(column.extraction_type)}</span>
          </Badge>
        </div>
        <p className="text-xs text-muted-foreground truncate mt-0.5">
          {column.prompt}
        </p>
      </div>

      {/* Visibility toggle */}
      <Switch
        checked={isVisible}
        onCheckedChange={onToggleVisibility}
        disabled={isDeleting || isReprocessing}
      />

      {/* Actions menu */}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            disabled={isDeleting || isReprocessing}
          >
            {isDeleting || isReprocessing ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <MoreVertical className="h-4 w-4" />
            )}
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem onClick={onReprocess} disabled={isReprocessing}>
            <RefreshCw className="h-4 w-4 mr-2" />
            Reprocessar coluna
          </DropdownMenuItem>
          <DropdownMenuItem
            onClick={onDelete}
            disabled={isDeleting}
            className="text-destructive focus:text-destructive"
          >
            <Trash2 className="h-4 w-4 mr-2" />
            Excluir coluna
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}

export function ManageColumnsPanel({
  tableId,
  open,
  onClose,
  onAddColumn,
}: ManageColumnsPanelProps) {
  const {
    columns,
    columnOrder,
    visibleColumns,
    toggleColumnVisibility,
    removeColumn,
    reorderColumns,
    setActiveJob,
  } = useReviewTableStore();

  const [deletingColumnId, setDeletingColumnId] = useState<string | null>(null);
  const [reprocessingColumnId, setReprocessingColumnId] = useState<string | null>(
    null
  );
  const [confirmDelete, setConfirmDelete] = useState<DynamicColumn | null>(null);
  const [draggedId, setDraggedId] = useState<string | null>(null);

  // Get ordered columns
  const orderedColumns = React.useMemo(() => {
    return columnOrder
      .map((id) => columns.find((c) => c.id === id))
      .filter((c): c is DynamicColumn => c !== undefined);
  }, [columns, columnOrder]);

  const handleDeleteColumn = useCallback(async (column: DynamicColumn) => {
    setConfirmDelete(column);
  }, []);

  const confirmDeleteColumn = useCallback(async () => {
    if (!confirmDelete) return;

    setDeletingColumnId(confirmDelete.id);
    try {
      await apiClient.deleteDynamicColumn(tableId, confirmDelete.id);
      removeColumn(confirmDelete.id);
    } catch (error) {
      console.error('Error deleting column:', error);
    } finally {
      setDeletingColumnId(null);
      setConfirmDelete(null);
    }
  }, [tableId, confirmDelete, removeColumn]);

  const handleReprocessColumn = useCallback(
    async (columnId: string) => {
      setReprocessingColumnId(columnId);
      try {
        const job = await apiClient.reprocessColumn(tableId, columnId);
        setActiveJob(job);
      } catch (error) {
        console.error('Error reprocessing column:', error);
      } finally {
        setReprocessingColumnId(null);
      }
    },
    [tableId, setActiveJob]
  );

  // Simple drag and drop handlers
  const handleDragStart = useCallback(
    (e: React.DragEvent, columnId: string) => {
      setDraggedId(columnId);
      e.dataTransfer.effectAllowed = 'move';
    },
    []
  );

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent, targetId: string) => {
      e.preventDefault();
      if (!draggedId || draggedId === targetId) return;

      const currentOrder = [...columnOrder];
      const draggedIndex = currentOrder.indexOf(draggedId);
      const targetIndex = currentOrder.indexOf(targetId);

      if (draggedIndex === -1 || targetIndex === -1) return;

      // Remove dragged item and insert at target position
      currentOrder.splice(draggedIndex, 1);
      currentOrder.splice(targetIndex, 0, draggedId);

      reorderColumns(currentOrder);

      // Save to API
      apiClient.reorderColumns(tableId, currentOrder).catch(console.error);

      setDraggedId(null);
    },
    [draggedId, columnOrder, reorderColumns, tableId]
  );

  const handleDragEnd = useCallback(() => {
    setDraggedId(null);
  }, []);

  const handleToggleAllVisibility = useCallback(
    (visible: boolean) => {
      columns.forEach((col) => {
        const isCurrentlyVisible = visibleColumns.has(col.id);
        if (isCurrentlyVisible !== visible) {
          toggleColumnVisibility(col.id);
        }
      });
    },
    [columns, visibleColumns, toggleColumnVisibility]
  );

  return (
    <>
      <Sheet open={open} onOpenChange={(isOpen) => !isOpen && onClose()}>
        <SheetContent side="right" className="w-full sm:max-w-md p-0 flex flex-col">
          <SheetHeader className="px-6 py-4 border-b">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Columns3 className="h-5 w-5 text-primary" />
                <div>
                  <SheetTitle className="text-base">Gerenciar Colunas</SheetTitle>
                  <SheetDescription className="text-xs">
                    {columns.length} colunas | {visibleColumns.size} visiveis
                  </SheetDescription>
                </div>
              </div>
            </div>
          </SheetHeader>

          <div className="px-6 py-3 border-b flex items-center justify-between">
            <div className="flex gap-2">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => handleToggleAllVisibility(true)}
              >
                <Eye className="h-4 w-4 mr-1" />
                Mostrar todas
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => handleToggleAllVisibility(false)}
              >
                <EyeOff className="h-4 w-4 mr-1" />
                Ocultar todas
              </Button>
            </div>
            <Button size="sm" onClick={onAddColumn}>
              <Plus className="h-4 w-4 mr-1" />
              Nova
            </Button>
          </div>

          <ScrollArea className="flex-1 px-6 py-4">
            {orderedColumns.length === 0 ? (
              <div className="text-center py-12 text-muted-foreground">
                <Columns3 className="h-12 w-12 mx-auto mb-4 opacity-40" />
                <p className="font-medium">Nenhuma coluna criada</p>
                <p className="text-sm mt-1">
                  Adicione colunas para extrair dados dos documentos.
                </p>
                <Button className="mt-4" onClick={onAddColumn}>
                  <Plus className="h-4 w-4 mr-2" />
                  Adicionar Coluna
                </Button>
              </div>
            ) : (
              <div className="space-y-2">
                {orderedColumns.map((column) => (
                  <div
                    key={column.id}
                    draggable
                    onDragStart={(e) => handleDragStart(e, column.id)}
                    onDragOver={handleDragOver}
                    onDrop={(e) => handleDrop(e, column.id)}
                    onDragEnd={handleDragEnd}
                  >
                    <ColumnItem
                      column={column}
                      isVisible={visibleColumns.has(column.id)}
                      onToggleVisibility={() => toggleColumnVisibility(column.id)}
                      onDelete={() => handleDeleteColumn(column)}
                      onReprocess={() => handleReprocessColumn(column.id)}
                      isDeleting={deletingColumnId === column.id}
                      isReprocessing={reprocessingColumnId === column.id}
                      isDragging={draggedId === column.id}
                    />
                  </div>
                ))}
              </div>
            )}
          </ScrollArea>

          <div className="px-6 py-3 border-t text-xs text-muted-foreground text-center">
            Arraste as colunas para reordenar
          </div>
        </SheetContent>
      </Sheet>

      {/* Delete confirmation dialog */}
      <AlertDialog
        open={!!confirmDelete}
        onOpenChange={(open) => !open && setConfirmDelete(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Excluir coluna?</AlertDialogTitle>
            <AlertDialogDescription>
              Esta acao ira excluir a coluna &quot;{confirmDelete?.name}&quot; e todos os
              dados extraidos para ela. Esta acao nao pode ser desfeita.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={confirmDeleteColumn}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {deletingColumnId ? (
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
              ) : (
                <Trash2 className="h-4 w-4 mr-2" />
              )}
              Excluir
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
