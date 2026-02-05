'use client';

import { useMemo, useState } from 'react';
import { Download, FileSpreadsheet } from 'lucide-react';
import { toast } from 'sonner';
import apiClient from '@/lib/api-client';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

type ExportFormat = 'csv' | 'xlsx';

export interface CorpusExportFilters {
  scope?: string;
  group_id?: string;
  collection?: string;
  search?: string;
  status?: string;
}

const COLUMN_LABELS: Record<string, string> = {
  id: 'ID',
  name: 'Nome',
  original_name: 'Arquivo original',
  collection: 'Coleção',
  scope: 'Escopo',
  status: 'Status',
  ingested_at: 'Ingerido em',
  expires_at: 'Expira em',
  file_type: 'Tipo',
  size_bytes: 'Tamanho',
  case_id: 'Caso',
  group_ids: 'Departamentos',
  jurisdiction: 'Jurisdição',
  source_id: 'Fonte regional',
};

const ALL_COLUMNS = Object.keys(COLUMN_LABELS);

const DEFAULT_COLUMNS = [
  'name',
  'collection',
  'scope',
  'status',
  'ingested_at',
  'file_type',
  'size_bytes',
];

function parseFilename(disposition: string | null, fallback: string) {
  if (!disposition) return fallback;
  const match = disposition.match(/filename="?([^";\n]+)"?/);
  return match?.[1] || fallback;
}

export function CorpusExportButton({
  filters,
  label = 'Exportar',
  size = 'sm',
  variant = 'outline',
}: {
  filters: CorpusExportFilters;
  label?: string;
  size?: React.ComponentProps<typeof Button>['size'];
  variant?: React.ComponentProps<typeof Button>['variant'];
}) {
  const [open, setOpen] = useState(false);
  const [format, setFormat] = useState<ExportFormat>('xlsx');
  const [selectedColumns, setSelectedColumns] = useState<string[]>(DEFAULT_COLUMNS);
  const [exporting, setExporting] = useState(false);

  const sortedColumns = useMemo(() => {
    const preferredOrder = [...DEFAULT_COLUMNS, ...ALL_COLUMNS.filter((c) => !DEFAULT_COLUMNS.includes(c))];
    return preferredOrder.filter((c) => ALL_COLUMNS.includes(c));
  }, []);

  const toggleColumn = (col: string) => {
    setSelectedColumns((prev) =>
      prev.includes(col) ? prev.filter((c) => c !== col) : [...prev, col]
    );
  };

  const handleReset = () => setSelectedColumns(DEFAULT_COLUMNS);

  const handleExport = async () => {
    if (selectedColumns.length === 0) {
      toast.error('Selecione ao menos uma coluna.');
      return;
    }
    setExporting(true);
    try {
      const params = new URLSearchParams();
      params.set('format', format);
      params.set('columns', selectedColumns.join(','));
      if (filters.scope) params.set('scope', filters.scope);
      if (filters.group_id) params.set('group_id', filters.group_id);
      if (filters.collection) params.set('collection', filters.collection);
      if (filters.search) params.set('search', filters.search);
      if (filters.status) params.set('status', filters.status);

      const res = await apiClient.fetchWithAuth(`/corpus/documents/export?${params.toString()}`, {
        method: 'GET',
        headers: {},
      });
      if (!res.ok) throw new Error(`Erro ${res.status}`);

      const blob = await res.blob();
      const fallback = `corpus_documents.${format}`;
      const filename = parseFilename(res.headers.get('Content-Disposition'), fallback);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);

      toast.success('Export concluído.');
      setOpen(false);
    } catch (e: any) {
      toast.error(e?.message || 'Falha ao exportar.');
    } finally {
      setExporting(false);
    }
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant={variant} size={size} className="rounded-full gap-2">
          <Download className="h-4 w-4" />
          {label}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[360px] p-0" align="end" sideOffset={8}>
        <div className="px-4 py-3 border-b border-slate-100">
          <div className="flex items-center gap-2">
            <FileSpreadsheet className="h-4 w-4 text-muted-foreground" />
            <p className="text-sm font-medium text-foreground">Exportar inventário</p>
          </div>
          <p className="text-xs text-muted-foreground mt-1">
            Gere CSV/XLSX do corpus com colunas customizadas.
          </p>
        </div>

        <div className="px-4 py-3 space-y-3">
          <div className="space-y-1.5">
            <p className="text-xs font-medium text-muted-foreground">Formato</p>
            <Select value={format} onValueChange={(v) => setFormat(v as ExportFormat)}>
              <SelectTrigger className="rounded-xl h-9 text-sm">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="xlsx">Excel (.xlsx)</SelectItem>
                <SelectItem value="csv">CSV (.csv)</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <p className="text-xs font-medium text-muted-foreground">Colunas</p>
              <button
                type="button"
                className="text-[11px] text-primary hover:underline"
                onClick={handleReset}
              >
                Reset
              </button>
            </div>
            <ScrollArea className="h-48 rounded-xl border border-slate-200/60">
              <div className="p-2 space-y-1">
                {sortedColumns.map((col) => (
                  <label key={col} className="flex items-center gap-2 py-1 px-1.5 rounded-lg hover:bg-muted/30 cursor-pointer">
                    <Checkbox
                      checked={selectedColumns.includes(col)}
                      onCheckedChange={() => toggleColumn(col)}
                      className="h-3.5 w-3.5"
                    />
                    <span className="text-xs text-foreground">{COLUMN_LABELS[col] || col}</span>
                  </label>
                ))}
              </div>
            </ScrollArea>
            <p className="text-[11px] text-muted-foreground">
              {selectedColumns.length} coluna(s) selecionada(s)
            </p>
          </div>
        </div>

        <div className="px-4 py-3 border-t border-slate-100 bg-slate-50/50 flex justify-end">
          <Button
            className="rounded-full gap-2"
            onClick={handleExport}
            disabled={exporting}
          >
            {exporting ? (
              <span className="text-sm">Exportando…</span>
            ) : (
              <>
                <Download className="h-4 w-4" />
                Exportar
              </>
            )}
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}
