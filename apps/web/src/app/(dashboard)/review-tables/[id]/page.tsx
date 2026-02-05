'use client';

import * as React from 'react';
import { useEffect, useCallback, useState, useMemo } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  DropdownMenuCheckboxItem,
  DropdownMenuLabel,
} from '@/components/ui/dropdown-menu';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import {
  MessageCircle,
  Columns3,
  Filter,
  Download,
  Plus,
  Wand2,
  ChevronLeft,
  Loader2,
  MoreHorizontal,
  Trash2,
  RefreshCw,
  FileText,
  Settings,
  Play,
  Eye,
  EyeOff,
} from 'lucide-react';
import { toast } from 'sonner';
import apiClient from '@/lib/api-client';
import { useReviewTableStore } from '@/stores/review-table-store';
import { VirtualTable } from '@/components/review-tables/virtual-table';
import { ColumnBuilderModal } from '@/components/review-tables/column-builder-modal';
import { AskTableDrawer } from '@/components/review-tables/ask-table-drawer';
import { ManageColumnsPanel } from '@/components/review-tables/manage-columns-panel';
import { VerificationStats } from '@/components/review-tables/verification-stats';
import { ExtractionProgress } from '@/components/review-tables/extraction-progress';
import type { DynamicColumn, ExtractionJob } from '@/types/review-table';

export default function ReviewTablePage() {
  const params = useParams();
  const router = useRouter();
  const tableId = params.id as string;

  const [isExporting, setIsExporting] = useState(false);
  const [isStartingExtraction, setIsStartingExtraction] = useState(false);

  const {
    table,
    columns,
    documents,
    verificationStats,
    activeJob,
    isLoading,
    isChatOpen,
    isColumnBuilderOpen,
    showVerifiedOnly,
    showLowConfidenceOnly,
    visibleColumns,
    loadTable,
    setIsChatOpen,
    setIsColumnBuilderOpen,
    addColumn,
    setActiveJob,
    setShowVerifiedOnly,
    setShowLowConfidenceOnly,
    setVerificationStats,
    toggleColumnVisibility,
    clearTable,
  } = useReviewTableStore();

  const [isManageColumnsOpen, setIsManageColumnsOpen] = useState(false);

  // Load table data on mount
  useEffect(() => {
    loadTable(tableId).catch((error) => {
      console.error('Error loading table:', error);
      toast.error('Erro ao carregar tabela');
    });

    return () => {
      clearTable();
    };
  }, [tableId, loadTable, clearTable]);

  // Handle column creation
  const handleColumnCreated = useCallback(
    (column: DynamicColumn) => {
      addColumn(column);
      toast.success(`Coluna "${column.name}" criada com sucesso`);

      // Automatically start extraction for the new column
      apiClient
        .startExtraction(tableId, [column.id])
        .then((job) => {
          setActiveJob(job);
        })
        .catch((error) => {
          console.error('Error starting extraction:', error);
        });
    },
    [tableId, addColumn, setActiveJob]
  );

  // Handle start extraction for all columns
  const handleStartExtraction = useCallback(async () => {
    if (columns.length === 0) {
      toast.error('Adicione pelo menos uma coluna antes de iniciar a extracao');
      return;
    }

    setIsStartingExtraction(true);
    try {
      const job = await apiClient.startExtraction(tableId);
      setActiveJob(job);
      toast.success('Extracao iniciada');
    } catch (error) {
      console.error('Error starting extraction:', error);
      toast.error('Erro ao iniciar extracao');
    } finally {
      setIsStartingExtraction(false);
    }
  }, [tableId, columns.length, setActiveJob]);

  // Handle job completion
  const handleJobComplete = useCallback(async () => {
    // Refresh verification stats
    try {
      const stats = await apiClient.getVerificationStats(tableId);
      setVerificationStats(stats);
    } catch (error) {
      console.error('Error refreshing stats:', error);
    }
  }, [tableId, setVerificationStats]);

  // Toggle callbacks for verification filters
  const handleToggleVerifiedOnly = useCallback(() => {
    setShowVerifiedOnly(!showVerifiedOnly);
  }, [showVerifiedOnly, setShowVerifiedOnly]);

  const handleToggleLowConfidenceOnly = useCallback(() => {
    setShowLowConfidenceOnly(!showLowConfidenceOnly);
  }, [showLowConfidenceOnly, setShowLowConfidenceOnly]);

  // Handle export
  const handleExport = useCallback(
    async (format: 'csv' | 'xlsx' | 'json') => {
      setIsExporting(true);
      try {
        const blob = await apiClient.exportReviewTable(tableId, format);
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${table?.name || 'review-table'}.${format}`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        toast.success('Exportacao concluida');
      } catch (error) {
        console.error('Error exporting:', error);
        toast.error('Erro ao exportar tabela');
      } finally {
        setIsExporting(false);
      }
    },
    [tableId, table?.name]
  );

  // Handle document click
  const handleDocumentClick = useCallback((documentId: string) => {
    // TODO: Open document viewer
    console.log('Open document:', documentId);
  }, []);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <Loader2 className="h-8 w-8 animate-spin text-primary mx-auto mb-4" />
          <p className="text-muted-foreground">Carregando tabela...</p>
        </div>
      </div>
    );
  }

  if (!table) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <FileText className="h-12 w-12 text-muted-foreground/40 mx-auto mb-4" />
          <p className="font-medium">Tabela nao encontrada</p>
          <Button
            variant="outline"
            className="mt-4"
            onClick={() => router.push('/review-tables')}
          >
            <ChevronLeft className="h-4 w-4 mr-2" />
            Voltar para lista
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="border-b px-6 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Button
              variant="ghost"
              size="icon"
              onClick={() => router.push('/review-tables')}
            >
              <ChevronLeft className="h-5 w-5" />
            </Button>
            <div>
              <h1 className="text-xl font-semibold">{table.name}</h1>
              <p className="text-sm text-muted-foreground">
                {documents.length} documentos | {columns.length} colunas
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {/* Ask Table button */}
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="outline"
                    onClick={() => setIsChatOpen(true)}
                    className="gap-2"
                  >
                    <MessageCircle className="h-4 w-4" />
                    <span className="hidden sm:inline">Perguntar</span>
                  </Button>
                </TooltipTrigger>
                <TooltipContent>
                  <p>Faca perguntas sobre os dados da tabela</p>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>

            {/* Add Column button */}
            <Button onClick={() => setIsColumnBuilderOpen(true)} className="gap-2">
              <Wand2 className="h-4 w-4" />
              <span className="hidden sm:inline">Nova Coluna</span>
            </Button>

            {/* More actions */}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" size="icon">
                  <MoreHorizontal className="h-4 w-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuLabel>Acoes</DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={() => setIsManageColumnsOpen(true)}>
                  <Columns3 className="h-4 w-4 mr-2" />
                  Gerenciar colunas
                </DropdownMenuItem>
                <DropdownMenuItem
                  onClick={handleStartExtraction}
                  disabled={isStartingExtraction || columns.length === 0}
                >
                  {isStartingExtraction ? (
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  ) : (
                    <Play className="h-4 w-4 mr-2" />
                  )}
                  Reprocessar todos
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  onClick={() => handleExport('csv')}
                  disabled={isExporting}
                >
                  <Download className="h-4 w-4 mr-2" />
                  Exportar CSV
                </DropdownMenuItem>
                <DropdownMenuItem
                  onClick={() => handleExport('xlsx')}
                  disabled={isExporting}
                >
                  <Download className="h-4 w-4 mr-2" />
                  Exportar Excel
                </DropdownMenuItem>
                <DropdownMenuItem
                  onClick={() => handleExport('json')}
                  disabled={isExporting}
                >
                  <Download className="h-4 w-4 mr-2" />
                  Exportar JSON
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>
      </div>

      {/* Toolbar */}
      <div className="border-b px-6 py-3 flex items-center justify-between gap-4 flex-wrap">
        {/* Column visibility dropdown */}
        <div className="flex items-center gap-2">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="sm" className="gap-2">
                <Eye className="h-4 w-4" />
                Colunas
                <Badge variant="secondary" className="ml-1">
                  {visibleColumns.size}/{columns.length}
                </Badge>
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" className="w-56">
              <DropdownMenuLabel>Colunas visiveis</DropdownMenuLabel>
              <DropdownMenuSeparator />
              {columns.map((column) => (
                <DropdownMenuCheckboxItem
                  key={column.id}
                  checked={visibleColumns.has(column.id)}
                  onCheckedChange={() => toggleColumnVisibility(column.id)}
                >
                  {column.name}
                </DropdownMenuCheckboxItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>

          {/* Filter dropdown */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="sm" className="gap-2">
                <Filter className="h-4 w-4" />
                Filtros
                {(showVerifiedOnly || showLowConfidenceOnly) && (
                  <Badge variant="secondary" className="ml-1">
                    1
                  </Badge>
                )}
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start">
              <DropdownMenuCheckboxItem
                checked={showVerifiedOnly}
                onCheckedChange={setShowVerifiedOnly}
              >
                Apenas verificadas
              </DropdownMenuCheckboxItem>
              <DropdownMenuCheckboxItem
                checked={showLowConfidenceOnly}
                onCheckedChange={setShowLowConfidenceOnly}
              >
                Baixa confianca
              </DropdownMenuCheckboxItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>

        {/* Verification stats */}
        {verificationStats && (
          <VerificationStats
            stats={verificationStats}
            showVerifiedOnly={showVerifiedOnly}
            showLowConfidenceOnly={showLowConfidenceOnly}
            onToggleVerifiedOnly={handleToggleVerifiedOnly}
            onToggleLowConfidenceOnly={handleToggleLowConfidenceOnly}
          />
        )}
      </div>

      {/* Extraction progress */}
      {activeJob && (
        <div className="px-6 py-3 border-b">
          <ExtractionProgress
            tableId={tableId}
            job={activeJob}
            onJobComplete={handleJobComplete}
          />
        </div>
      )}

      {/* Main table */}
      <div className="flex-1 p-6 overflow-hidden">
        {columns.length === 0 ? (
          <div className="flex items-center justify-center h-full">
            <div className="text-center max-w-md">
              <Wand2 className="h-12 w-12 text-primary/40 mx-auto mb-4" />
              <h2 className="text-lg font-semibold mb-2">
                Comece adicionando colunas
              </h2>
              <p className="text-muted-foreground mb-4">
                Crie colunas descrevendo em linguagem natural quais informacoes
                voce deseja extrair de cada documento.
              </p>
              <Button onClick={() => setIsColumnBuilderOpen(true)}>
                <Wand2 className="h-4 w-4 mr-2" />
                Adicionar Primeira Coluna
              </Button>
            </div>
          </div>
        ) : (
          <VirtualTable
            tableId={tableId}
            className="h-full"
            onDocumentClick={handleDocumentClick}
          />
        )}
      </div>

      {/* Modals and Drawers */}
      <ColumnBuilderModal
        tableId={tableId}
        open={isColumnBuilderOpen}
        onClose={() => setIsColumnBuilderOpen(false)}
        onColumnCreated={handleColumnCreated}
      />

      <AskTableDrawer
        tableId={tableId}
        open={isChatOpen}
        onClose={() => setIsChatOpen(false)}
      />

      <ManageColumnsPanel
        tableId={tableId}
        open={isManageColumnsOpen}
        onClose={() => setIsManageColumnsOpen(false)}
        onAddColumn={() => {
          setIsManageColumnsOpen(false);
          setIsColumnBuilderOpen(true);
        }}
      />
    </div>
  );
}
