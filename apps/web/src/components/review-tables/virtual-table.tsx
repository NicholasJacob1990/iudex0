'use client';

import * as React from 'react';
import { useCallback, useMemo, useRef, useState, useEffect } from 'react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import {
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  FileText,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  Loader2,
} from 'lucide-react';
import { TableCell } from './table-cell';
import { useReviewTableStore } from '@/stores/review-table-store';
import apiClient from '@/lib/api-client';
import type {
  DynamicColumn,
  ReviewTableDocument,
  CellExtraction,
} from '@/types/review-table';

interface VirtualTableProps {
  tableId: string;
  className?: string;
  onDocumentClick?: (documentId: string) => void;
}

// Row height in pixels
const ROW_HEIGHT = 48;
// Header height in pixels
const HEADER_HEIGHT = 44;
// Minimum column width
const MIN_COLUMN_WIDTH = 150;
// Document name column width
const DOC_NAME_COLUMN_WIDTH = 250;
// Number of rows to render outside viewport (buffer)
const OVERSCAN = 5;
// Page size for pagination fallback
const PAGE_SIZE = 50;

export function VirtualTable({
  tableId,
  className,
  onDocumentClick,
}: VirtualTableProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const [containerHeight, setContainerHeight] = useState(600);
  const [selectedRows, setSelectedRows] = useState<Set<string>>(new Set());

  const {
    documents,
    columns,
    cells,
    visibleColumns,
    columnOrder,
    sortColumn,
    sortDirection,
    isLoadingCells,
    showVerifiedOnly,
    showLowConfidenceOnly,
    setSortColumn,
    toggleSortDirection,
    updateCell,
  } = useReviewTableStore();

  // Get visible columns in order
  const orderedVisibleColumns = useMemo(() => {
    return columnOrder
      .filter((id) => visibleColumns.has(id))
      .map((id) => columns.find((c) => c.id === id))
      .filter((c): c is DynamicColumn => c !== undefined);
  }, [columnOrder, visibleColumns, columns]);

  // Get sorted and filtered documents
  const sortedDocuments = useMemo(() => {
    let docs = [...documents];

    // Apply filters (simplified - only show/hide filters for now)
    if (showVerifiedOnly) {
      docs = docs.filter((doc) => {
        for (const column of columns) {
          const cell = cells.get(`${doc.id}:${column.id}`);
          if (cell && !cell.is_verified) return false;
        }
        return true;
      });
    }

    if (showLowConfidenceOnly) {
      docs = docs.filter((doc) => {
        for (const column of columns) {
          const cell = cells.get(`${doc.id}:${column.id}`);
          if (cell && cell.confidence < 0.5) return true;
        }
        return false;
      });
    }

    // Apply sorting
    if (sortColumn) {
      docs.sort((a, b) => {
        const cellA = cells.get(`${a.id}:${sortColumn}`);
        const cellB = cells.get(`${b.id}:${sortColumn}`);
        const valueA = cellA?.value ?? '';
        const valueB = cellB?.value ?? '';

        let comparison = 0;
        if (typeof valueA === 'number' && typeof valueB === 'number') {
          comparison = valueA - valueB;
        } else {
          comparison = String(valueA).localeCompare(String(valueB));
        }
        return sortDirection === 'asc' ? comparison : -comparison;
      });
    }

    return docs;
  }, [documents, columns, cells, sortColumn, sortDirection, showVerifiedOnly, showLowConfidenceOnly]);

  // Calculate total rows
  const totalRows = sortedDocuments.length;

  // Calculate visible range with overscan
  const visibleRange = useMemo(() => {
    const startIndex = Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) - OVERSCAN);
    const endIndex = Math.min(
      totalRows,
      Math.ceil((scrollTop + containerHeight) / ROW_HEIGHT) + OVERSCAN
    );
    return { startIndex, endIndex };
  }, [scrollTop, containerHeight, totalRows]);

  // Get visible rows
  const visibleRows = useMemo(() => {
    return sortedDocuments.slice(visibleRange.startIndex, visibleRange.endIndex);
  }, [sortedDocuments, visibleRange]);

  // Handle scroll
  const handleScroll = useCallback((e: React.UIEvent<HTMLDivElement>) => {
    setScrollTop(e.currentTarget.scrollTop);
  }, []);

  // Handle container resize
  useEffect(() => {
    if (!containerRef.current) return;

    const resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setContainerHeight(entry.contentRect.height - HEADER_HEIGHT);
      }
    });

    resizeObserver.observe(containerRef.current);
    return () => resizeObserver.disconnect();
  }, []);

  // Handle sort
  const handleSort = useCallback(
    (columnId: string) => {
      if (sortColumn === columnId) {
        toggleSortDirection();
      } else {
        setSortColumn(columnId);
      }
    },
    [sortColumn, setSortColumn, toggleSortDirection]
  );

  // Handle cell verification
  const handleVerifyCell = useCallback(
    async (cellId: string, verified: boolean, correction?: string) => {
      const updatedCell = await apiClient.verifyCell(
        tableId,
        cellId,
        verified,
        correction
      );
      updateCell(updatedCell);
    },
    [tableId, updateCell]
  );

  // Handle row selection
  const handleSelectRow = useCallback((documentId: string, selected: boolean) => {
    setSelectedRows((prev) => {
      const next = new Set(prev);
      if (selected) {
        next.add(documentId);
      } else {
        next.delete(documentId);
      }
      return next;
    });
  }, []);

  const handleSelectAll = useCallback(
    (selected: boolean) => {
      if (selected) {
        setSelectedRows(new Set(sortedDocuments.map((d) => d.id)));
      } else {
        setSelectedRows(new Set());
      }
    },
    [sortedDocuments]
  );

  const allSelected =
    selectedRows.size > 0 && selectedRows.size === sortedDocuments.length;
  const someSelected = selectedRows.size > 0 && !allSelected;

  // Calculate total width
  const totalWidth =
    DOC_NAME_COLUMN_WIDTH +
    48 + // Checkbox column
    orderedVisibleColumns.length * MIN_COLUMN_WIDTH;

  // Get cell for document and column
  const getCell = useCallback(
    (docId: string, colId: string): CellExtraction | undefined => {
      const key = `${docId}:${colId}`;
      return cells.get(key);
    },
    [cells]
  );

  return (
    <div
      ref={containerRef}
      className={cn(
        'relative border rounded-lg bg-background overflow-hidden',
        className
      )}
    >
      {/* Horizontal scroll container */}
      <div className="overflow-x-auto">
        <div style={{ minWidth: totalWidth }}>
          {/* Header */}
          <div
            className="sticky top-0 z-10 flex bg-muted/80 backdrop-blur border-b"
            style={{ height: HEADER_HEIGHT }}
          >
            {/* Checkbox column */}
            <div className="flex items-center justify-center w-12 shrink-0 border-r">
              <Checkbox
                checked={allSelected}
                // indeterminate does not exist on Checkbox; using a workaround
                onCheckedChange={handleSelectAll}
                aria-label="Selecionar todos"
              />
            </div>

            {/* Document name column */}
            <div
              className="flex items-center px-3 gap-2 font-medium text-sm border-r"
              style={{ width: DOC_NAME_COLUMN_WIDTH }}
            >
              <FileText className="h-4 w-4 text-muted-foreground shrink-0" />
              <span className="truncate">Documento</span>
            </div>

            {/* Dynamic columns */}
            {orderedVisibleColumns.map((column) => (
              <div
                key={column.id}
                className="flex items-center px-3 gap-1 font-medium text-sm border-r cursor-pointer hover:bg-accent/50 transition-colors"
                style={{ width: MIN_COLUMN_WIDTH }}
                onClick={() => handleSort(column.id)}
              >
                <span className="truncate flex-1">{column.name}</span>
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <div className="shrink-0">
                        {sortColumn === column.id ? (
                          sortDirection === 'asc' ? (
                            <ArrowUp className="h-4 w-4" />
                          ) : (
                            <ArrowDown className="h-4 w-4" />
                          )
                        ) : (
                          <ArrowUpDown className="h-4 w-4 text-muted-foreground/50" />
                        )}
                      </div>
                    </TooltipTrigger>
                    <TooltipContent>
                      <p>Ordenar por {column.name}</p>
                    </TooltipContent>
                  </Tooltip>
                </TooltipProvider>
              </div>
            ))}
          </div>

          {/* Scrollable body */}
          <div
            className="overflow-y-auto"
            style={{ height: containerHeight }}
            onScroll={handleScroll}
          >
            {/* Virtual spacer for rows before visible range */}
            <div style={{ height: visibleRange.startIndex * ROW_HEIGHT }} />

            {/* Visible rows */}
            {visibleRows.map((document, index) => (
              <div
                key={document.id}
                className={cn(
                  'flex border-b hover:bg-muted/30 transition-colors',
                  selectedRows.has(document.id) && 'bg-primary/5'
                )}
                style={{ height: ROW_HEIGHT }}
              >
                {/* Checkbox */}
                <div className="flex items-center justify-center w-12 shrink-0 border-r">
                  <Checkbox
                    checked={selectedRows.has(document.id)}
                    onCheckedChange={(checked) =>
                      handleSelectRow(document.id, !!checked)
                    }
                    aria-label={`Selecionar ${document.name}`}
                  />
                </div>

                {/* Document name */}
                <div
                  className="flex items-center px-3 gap-2 border-r"
                  style={{ width: DOC_NAME_COLUMN_WIDTH }}
                >
                  <FileText className="h-4 w-4 text-muted-foreground shrink-0" />
                  <button
                    className="truncate text-sm text-left hover:text-primary hover:underline transition-colors"
                    onClick={() => onDocumentClick?.(document.id)}
                  >
                    {document.name}
                  </button>
                </div>

                {/* Cells */}
                {orderedVisibleColumns.map((column) => (
                  <div
                    key={column.id}
                    className="flex items-center border-r"
                    style={{ width: MIN_COLUMN_WIDTH }}
                  >
                    <TableCell
                      cell={getCell(document.id, column.id)}
                      column={column}
                      documentName={document.name}
                      onVerify={handleVerifyCell}
                      showConfidence={true}
                      isLoading={isLoadingCells}
                    />
                  </div>
                ))}
              </div>
            ))}

            {/* Virtual spacer for rows after visible range */}
            <div
              style={{
                height: (totalRows - visibleRange.endIndex) * ROW_HEIGHT,
              }}
            />
          </div>
        </div>
      </div>

      {/* Empty state */}
      {sortedDocuments.length === 0 && !isLoadingCells && (
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="text-center text-muted-foreground">
            <FileText className="h-12 w-12 mx-auto mb-4 opacity-40" />
            <p className="font-medium">Nenhum documento encontrado</p>
            <p className="text-sm mt-1">
              Adicione documentos a esta tabela para comecar a extrair dados.
            </p>
          </div>
        </div>
      )}

      {/* Loading state */}
      {isLoadingCells && sortedDocuments.length > 0 && (
        <div className="absolute bottom-4 right-4 flex items-center gap-2 px-3 py-1.5 bg-primary text-primary-foreground rounded-full text-xs shadow-lg">
          <Loader2 className="h-3 w-3 animate-spin" />
          <span>Carregando celulas...</span>
        </div>
      )}
    </div>
  );
}

// Pagination component for non-virtual fallback
export function TablePagination({
  currentPage,
  totalPages,
  onPageChange,
}: {
  currentPage: number;
  totalPages: number;
  onPageChange: (page: number) => void;
}) {
  return (
    <div className="flex items-center justify-center gap-2 py-4">
      <Button
        variant="outline"
        size="icon"
        className="h-8 w-8"
        onClick={() => onPageChange(1)}
        disabled={currentPage === 1}
      >
        <ChevronsLeft className="h-4 w-4" />
      </Button>
      <Button
        variant="outline"
        size="icon"
        className="h-8 w-8"
        onClick={() => onPageChange(currentPage - 1)}
        disabled={currentPage === 1}
      >
        <ChevronLeft className="h-4 w-4" />
      </Button>
      <span className="text-sm text-muted-foreground px-4">
        Pagina {currentPage} de {totalPages}
      </span>
      <Button
        variant="outline"
        size="icon"
        className="h-8 w-8"
        onClick={() => onPageChange(currentPage + 1)}
        disabled={currentPage === totalPages}
      >
        <ChevronRight className="h-4 w-4" />
      </Button>
      <Button
        variant="outline"
        size="icon"
        className="h-8 w-8"
        onClick={() => onPageChange(totalPages)}
        disabled={currentPage === totalPages}
      >
        <ChevronsRight className="h-4 w-4" />
      </Button>
    </div>
  );
}
