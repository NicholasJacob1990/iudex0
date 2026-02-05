'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import {
  Table2,
  FileSpreadsheet,
  Plus,
  Download,
  RefreshCw,
  Loader2,
  CheckCircle2,
  Clock,
  AlertCircle,
  ArrowLeft,
  Search,
  ChevronRight,
  Eye,
  Check,
  X,
  Pencil,
  MessageSquare,
  Send,
  FileText,
  Zap,
  Briefcase,
  Building2,
  FileSignature,
  ShoppingCart,
  History,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { AnimatedContainer } from '@/components/ui/animated-container';
import { toast } from 'sonner';
import Link from 'next/link';
import { useAuthStore } from '@/stores/auth-store';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ColumnDef {
  name: string;
  type: string;
  extraction_prompt: string;
}

interface ReviewTemplate {
  id: string;
  name: string;
  description: string | null;
  area: string | null;
  columns: ColumnDef[];
  is_system: boolean;
  created_at: string;
}

interface CellEdit {
  edited_by: string;
  edited_at: string;
  verified: boolean;
}

interface ReviewTableRow {
  document_id: string;
  document_name: string;
  columns: Record<string, string>;
  column_meta?: {
    confidence?: Record<string, number>;
    source_excerpt?: Record<string, string>;
  };
  _edits?: Record<string, CellEdit>;
}

interface QuerySourceRef {
  document_id: string;
  document_name: string;
  column_name: string | null;
}

interface QueryResult {
  answer: string;
  sources: QuerySourceRef[];
}

// Identifica célula sendo editada
interface EditingCell {
  documentId: string;
  columnName: string;
}

interface CellHistoryEntry {
  document_id: string;
  column_name: string;
  old_value: string;
  new_value: string;
  changed_by: string;
  changed_at: string;
}

interface ReviewTableData {
  id: string;
  template_id: string;
  template_name: string | null;
  name: string;
  status: string;
  document_ids: string[];
  results: ReviewTableRow[];
  total_documents: number;
  processed_documents: number;
  accuracy_score: number | null;
  error_message: string | null;
  created_at: string;
}

interface CorpusDocument {
  id: string;
  name: string;
  status: string;
}

interface CorpusDocumentListResponse {
  items: CorpusDocument[];
  total: number;
  page: number;
  per_page: number;
}

interface OrgTeam {
  id: string;
  name: string;
  description?: string | null;
}

// ---------------------------------------------------------------------------
// API helpers
// ---------------------------------------------------------------------------

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '/api';

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null;
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options?.headers,
    },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Erro ${res.status}`);
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// Status config
// ---------------------------------------------------------------------------

const statusConfig: Record<string, { label: string; icon: React.ComponentType<{ className?: string }>; color: string }> = {
  created: { label: 'Criada', icon: Clock, color: 'bg-slate-100 text-slate-700' },
  processing: { label: 'Processando', icon: Loader2, color: 'bg-blue-100 text-blue-700' },
  completed: { label: 'Concluida', icon: CheckCircle2, color: 'bg-emerald-100 text-emerald-700' },
  failed: { label: 'Falhou', icon: AlertCircle, color: 'bg-red-100 text-red-700' },
};

const areaLabels: Record<string, string> = {
  trabalhista: 'Trabalhista',
  ti: 'TI',
  societario: 'Societario',
  imobiliario: 'Imobiliario',
  empresarial: 'Empresarial',
  civil: 'Civil',
};

// Icones por area para os cards de workflow
const areaIcons: Record<string, React.ComponentType<{ className?: string }>> = {
  trabalhista: Briefcase,
  imobiliario: Building2,
  civil: FileSignature,
  ti: FileSpreadsheet,
  societario: FileText,
  empresarial: ShoppingCart,
};

// Cores de fundo por area
const areaColors: Record<string, string> = {
  trabalhista: 'from-blue-500/10 to-blue-600/5 border-blue-200/50',
  imobiliario: 'from-emerald-500/10 to-emerald-600/5 border-emerald-200/50',
  civil: 'from-purple-500/10 to-purple-600/5 border-purple-200/50',
  ti: 'from-cyan-500/10 to-cyan-600/5 border-cyan-200/50',
  societario: 'from-amber-500/10 to-amber-600/5 border-amber-200/50',
  empresarial: 'from-rose-500/10 to-rose-600/5 border-rose-200/50',
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function ReviewTablesPage() {
  const { user } = useAuthStore();

  // State
  const [view, setView] = useState<'list' | 'templates' | 'create' | 'detail'>('list');
  const [templates, setTemplates] = useState<ReviewTemplate[]>([]);
  const [reviews, setReviews] = useState<ReviewTableData[]>([]);
  const [selectedTemplate, setSelectedTemplate] = useState<ReviewTemplate | null>(null);
  const [selectedReview, setSelectedReview] = useState<ReviewTableData | null>(null);
  const [documents, setDocuments] = useState<CorpusDocument[]>([]);
  const [accessFilter, setAccessFilter] = useState<string>('org');
  const [myTeams, setMyTeams] = useState<OrgTeam[]>([]);
  const [teamsLoading, setTeamsLoading] = useState(false);
  const [selectedDocIds, setSelectedDocIds] = useState<string[]>([]);
  const [reviewName, setReviewName] = useState('');
  const [docSearch, setDocSearch] = useState('');
  const [loading, setLoading] = useState(false);
  const [loadingTemplates, setLoadingTemplates] = useState(false);
  const [loadingReviews, setLoadingReviews] = useState(false);
  const [exportingFormat, setExportingFormat] = useState<string | null>(null);

  // Inline cell editing state
  const [editingCell, setEditingCell] = useState<EditingCell | null>(null);
  const [editValue, setEditValue] = useState('');
  const [savingCell, setSavingCell] = useState(false);
  const editInputRef = useRef<HTMLTextAreaElement>(null);

  // Cell history state
  const [cellHistoryOpen, setCellHistoryOpen] = useState(false);
  const [cellHistoryEntries, setCellHistoryEntries] = useState<CellHistoryEntry[]>([]);
  const [cellHistoryLoading, setCellHistoryLoading] = useState(false);
  const [cellHistoryLabel, setCellHistoryLabel] = useState('');

  // Natural language query state
  const [queryInput, setQueryInput] = useState('');
  const [queryLoading, setQueryLoading] = useState(false);
  const [queryResult, setQueryResult] = useState<QueryResult | null>(null);

  // Workflows pre-construidos state
  const [systemTemplates, setSystemTemplates] = useState<ReviewTemplate[]>([]);
  const [loadingSystemTemplates, setLoadingSystemTemplates] = useState(false);
  const [workflowTemplate, setWorkflowTemplate] = useState<ReviewTemplate | null>(null);
  const [showWorkflowModal, setShowWorkflowModal] = useState(false);
  const [workflowDocSearch, setWorkflowDocSearch] = useState('');
  const [workflowDocs, setWorkflowDocs] = useState<CorpusDocument[]>([]);
  const [workflowSelectedDocs, setWorkflowSelectedDocs] = useState<string[]>([]);
  const [workflowName, setWorkflowName] = useState('');
  const [workflowLoading, setWorkflowLoading] = useState(false);

  useEffect(() => {
    if (!user?.organization_id) {
      setMyTeams([]);
      return;
    }
    setTeamsLoading(true);
    apiFetch<any[]>('/organizations/teams/mine')
      .then((res) => {
        const list = Array.isArray(res) ? res : [];
        setMyTeams(
          list
            .map((t: any) => ({
              id: String(t?.id || '').trim(),
              name: String(t?.name || '').trim(),
              description: t?.description ?? null,
            }))
            .filter((t: OrgTeam) => t.id && t.name)
        );
      })
      .catch(() => setMyTeams([]))
      .finally(() => setTeamsLoading(false));
  }, [user?.organization_id]);

  const buildCorpusDocumentsUrl = useCallback(
    (search: string) => {
      const params = new URLSearchParams();
      params.set('status', 'ingested');
      params.set('per_page', '100');
      const q = (search || '').trim();
      if (q) params.set('search', q);

      if (!user?.organization_id) {
        params.set('scope', 'private');
        return `/corpus/documents?${params.toString()}`;
      }

      if (accessFilter === 'org') {
        params.set('scope', 'private');
      } else if (accessFilter === 'group_all') {
        params.set('scope', 'group');
      } else {
        params.set('scope', 'group');
        params.set('group_id', accessFilter);
      }

      return `/corpus/documents?${params.toString()}`;
    },
    [accessFilter, user?.organization_id]
  );

  // Load system templates for workflows section
  const loadSystemTemplates = useCallback(async () => {
    setLoadingSystemTemplates(true);
    try {
      const data = await apiFetch<{ items: ReviewTemplate[] }>('/review-tables/templates/system');
      setSystemTemplates(data.items);
    } catch (err) {
      console.error('Erro ao carregar templates do sistema:', err);
    } finally {
      setLoadingSystemTemplates(false);
    }
  }, []);

  // Load documents for workflow modal
  const loadWorkflowDocs = useCallback(async () => {
    try {
      const data = await apiFetch<CorpusDocumentListResponse>(buildCorpusDocumentsUrl(workflowDocSearch));
      setWorkflowDocs(data.items || []);
    } catch (err) {
      console.error('Erro ao carregar documentos:', err);
    }
  }, [workflowDocSearch, buildCorpusDocumentsUrl]);

  // Open workflow modal for a template
  const handleOpenWorkflow = (tmpl: ReviewTemplate) => {
    setWorkflowTemplate(tmpl);
    setWorkflowSelectedDocs([]);
    setWorkflowName('');
    setShowWorkflowModal(true);
    // Load docs immediately
    loadWorkflowDocs();
  };

  // Create review from workflow (one-click)
  const handleCreateFromWorkflow = async () => {
    if (!workflowTemplate || workflowSelectedDocs.length === 0) {
      toast.error('Selecione ao menos um documento.');
      return;
    }
    setWorkflowLoading(true);
    try {
      const review = await apiFetch<ReviewTableData>('/review-tables/from-template', {
        method: 'POST',
        body: JSON.stringify({
          template_id: workflowTemplate.id,
          document_ids: workflowSelectedDocs,
          name: workflowName.trim() || undefined,
        }),
      });
      toast.success(`Review "${review.name}" criada. Processamento iniciado.`);
      setShowWorkflowModal(false);
      setWorkflowTemplate(null);
      setWorkflowSelectedDocs([]);
      setWorkflowName('');
      await loadReviews();
    } catch (err: any) {
      toast.error(err.message || 'Erro ao criar review.');
    } finally {
      setWorkflowLoading(false);
    }
  };

  // Load templates
  const loadTemplates = useCallback(async () => {
    setLoadingTemplates(true);
    try {
      const data = await apiFetch<{ items: ReviewTemplate[] }>('/review-tables/templates');
      setTemplates(data.items);
    } catch (err) {
      console.error('Erro ao carregar templates:', err);
    } finally {
      setLoadingTemplates(false);
    }
  }, []);

  // Load reviews
  const loadReviews = useCallback(async () => {
    setLoadingReviews(true);
    try {
      const data = await apiFetch<{ items: ReviewTableData[] }>('/review-tables');
      setReviews(data.items);
    } catch (err) {
      console.error('Erro ao carregar reviews:', err);
    } finally {
      setLoadingReviews(false);
    }
  }, []);

  // Load documents
  const loadDocuments = useCallback(async () => {
    try {
      const data = await apiFetch<CorpusDocumentListResponse>(buildCorpusDocumentsUrl(docSearch));
      setDocuments(data.items || []);
    } catch (err) {
      console.error('Erro ao carregar documentos:', err);
    }
  }, [docSearch, buildCorpusDocumentsUrl]);

  useEffect(() => {
    loadTemplates();
    loadReviews();
    loadSystemTemplates();
  }, [loadTemplates, loadReviews, loadSystemTemplates]);

  // Seed templates
  const handleSeedTemplates = async () => {
    try {
      await apiFetch('/review-tables/templates/seed', { method: 'POST' });
      toast.success('Templates carregados com sucesso.');
      await loadTemplates();
    } catch (err) {
      toast.error('Erro ao carregar templates.');
    }
  };

  // Create review
  const handleCreateReview = async () => {
    if (!selectedTemplate || selectedDocIds.length === 0 || !reviewName.trim()) {
      toast.error('Preencha todos os campos.');
      return;
    }
    setLoading(true);
    try {
      const review = await apiFetch<ReviewTableData>('/review-tables', {
        method: 'POST',
        body: JSON.stringify({
          template_id: selectedTemplate.id,
          document_ids: selectedDocIds,
          name: reviewName.trim(),
        }),
      });
      toast.success(`Review "${review.name}" criada. Processamento iniciado.`);
      setView('list');
      setSelectedTemplate(null);
      setSelectedDocIds([]);
      setReviewName('');
      await loadReviews();
    } catch (err: any) {
      toast.error(err.message || 'Erro ao criar review.');
    } finally {
      setLoading(false);
    }
  };

  // View review detail
  const handleViewReview = async (id: string) => {
    try {
      const review = await apiFetch<ReviewTableData>(`/review-tables/${id}`);
      setSelectedReview(review);
      setView('detail');
    } catch (err) {
      toast.error('Erro ao carregar review.');
    }
  };

  // Export
  const handleExport = async (id: string, format: 'csv' | 'xlsx') => {
    setExportingFormat(format);
    try {
      const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null;
      const res = await fetch(`${API_BASE}/review-tables/${id}/export?format=${format}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error('Erro na exportacao');

      // Extrair filename do header Content-Disposition, ou usar fallback
      const disposition = res.headers.get('Content-Disposition');
      let filename = `review.${format}`;
      if (disposition) {
        const match = disposition.match(/filename="?([^";\n]+)"?/);
        if (match?.[1]) filename = match[1];
      }

      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
      toast.success(`Exportado como ${format.toUpperCase()}.`);
    } catch {
      toast.error('Erro ao exportar.');
    } finally {
      setExportingFormat(null);
    }
  };

  // Refresh review
  const handleRefreshReview = async () => {
    if (!selectedReview) return;
    try {
      const review = await apiFetch<ReviewTableData>(`/review-tables/${selectedReview.id}`);
      setSelectedReview(review);
    } catch {
      toast.error('Erro ao atualizar.');
    }
  };

  // Start editing a cell
  const handleStartEdit = (documentId: string, columnName: string, currentValue: string) => {
    setEditingCell({ documentId, columnName });
    setEditValue(currentValue || '');
    // Focus will happen via useEffect
  };

  // Save cell edit (optimistic)
  const handleSaveCell = async (verified: boolean = false) => {
    if (!editingCell || !selectedReview) return;
    const { documentId, columnName } = editingCell;
    const previousResults = [...selectedReview.results];

    // Optimistic update
    const updatedResults = selectedReview.results.map((row) => {
      if (row.document_id === documentId) {
        return {
          ...row,
          columns: { ...row.columns, [columnName]: editValue },
          _edits: {
            ...(row._edits || {}),
            [columnName]: {
              edited_by: 'current_user',
              edited_at: new Date().toISOString(),
              verified,
            },
          },
        };
      }
      return row;
    });
    setSelectedReview({ ...selectedReview, results: updatedResults });
    setEditingCell(null);

    setSavingCell(true);
    try {
      await apiFetch(`/review-tables/${selectedReview.id}/cell`, {
        method: 'PATCH',
        body: JSON.stringify({
          document_id: documentId,
          column_name: columnName,
          new_value: editValue,
          verified,
        }),
      });
      toast.success('Célula atualizada.');
    } catch (err: any) {
      // Rollback
      setSelectedReview({ ...selectedReview, results: previousResults });
      toast.error(err.message || 'Erro ao salvar célula.');
    } finally {
      setSavingCell(false);
    }
  };

  // Toggle verified status
  const handleToggleVerified = async (documentId: string, columnName: string) => {
    if (!selectedReview) return;
    const row = selectedReview.results.find((r) => r.document_id === documentId);
    if (!row) return;

    const currentEdit = row._edits?.[columnName];
    const newVerified = !(currentEdit?.verified ?? false);
    const currentValue = row.columns[columnName] || '';

    const previousResults = [...selectedReview.results];

    // Optimistic update
    const updatedResults = selectedReview.results.map((r) => {
      if (r.document_id === documentId) {
        return {
          ...r,
          _edits: {
            ...(r._edits || {}),
            [columnName]: {
              edited_by: currentEdit?.edited_by || 'current_user',
              edited_at: new Date().toISOString(),
              verified: newVerified,
            },
          },
        };
      }
      return r;
    });
    setSelectedReview({ ...selectedReview, results: updatedResults });

    try {
      await apiFetch(`/review-tables/${selectedReview.id}/cell`, {
        method: 'PATCH',
        body: JSON.stringify({
          document_id: documentId,
          column_name: columnName,
          new_value: currentValue,
          verified: newVerified,
        }),
      });
      toast.success(newVerified ? 'Célula verificada.' : 'Verificação removida.');
    } catch (err: any) {
      setSelectedReview({ ...selectedReview, results: previousResults });
      toast.error(err.message || 'Erro ao atualizar verificação.');
    }
  };

  // Cancel editing
  const handleCancelEdit = () => {
    setEditingCell(null);
    setEditValue('');
  };

  // View cell history
  const handleViewCellHistory = async (documentId: string, columnName: string, docName: string) => {
    if (!selectedReview) return;
    setCellHistoryLabel(`${docName} - ${columnName}`);
    setCellHistoryOpen(true);
    setCellHistoryLoading(true);
    try {
      const data = await apiFetch<{ entries: CellHistoryEntry[] }>(
        `/review-tables/${selectedReview.id}/cell-history?document_id=${encodeURIComponent(documentId)}&column_name=${encodeURIComponent(columnName)}`
      );
      setCellHistoryEntries(data.entries || []);
    } catch {
      setCellHistoryEntries([]);
    } finally {
      setCellHistoryLoading(false);
    }
  };

  // Natural language query
  const handleQuery = async () => {
    if (!selectedReview || !queryInput.trim()) return;
    setQueryLoading(true);
    setQueryResult(null);
    try {
      const result = await apiFetch<QueryResult>(`/review-tables/${selectedReview.id}/query`, {
        method: 'POST',
        body: JSON.stringify({ question: queryInput.trim() }),
      });
      setQueryResult(result);
    } catch (err: any) {
      toast.error(err.message || 'Erro ao processar consulta.');
    } finally {
      setQueryLoading(false);
    }
  };

  // Focus edit input when editing starts
  useEffect(() => {
    if (editingCell && editInputRef.current) {
      editInputRef.current.focus();
      editInputRef.current.select();
    }
  }, [editingCell]);

  // ---------------------------------------------------------------------------
  // Render: Detail view (spreadsheet)
  // ---------------------------------------------------------------------------

  if (view === 'detail' && selectedReview) {
    const templateCols = templates.find((t) => t.id === selectedReview.template_id)?.columns || [];
    const colNames = templateCols.length > 0
      ? templateCols.map((c) => c.name)
      : selectedReview.results.length > 0
        ? Object.keys(selectedReview.results[0]?.columns || {})
        : [];

    const status = statusConfig[selectedReview.status] || statusConfig.created;
    const StatusIcon = status.icon;

    return (
      <div className="space-y-6">
        {/* Header */}
        <AnimatedContainer>
          <div className="rounded-3xl border border-white/70 bg-white/95 p-6 shadow-soft">
            <div className="flex items-center gap-3 mb-3">
              <Button
                variant="ghost"
                size="sm"
                className="rounded-full"
                onClick={() => { setView('list'); setSelectedReview(null); }}
              >
                <ArrowLeft className="h-4 w-4 mr-1" /> Voltar
              </Button>
            </div>
            <div className="flex items-center justify-between flex-wrap gap-4">
              <div>
                <p className="text-xs font-semibold uppercase text-muted-foreground">Review Table</p>
                <h1 className="font-display text-2xl text-foreground">{selectedReview.name}</h1>
                <div className="flex items-center gap-3 mt-2">
                  <Badge className={`rounded-full text-[10px] border-0 gap-1 ${status.color}`}>
                    <StatusIcon className={`h-3 w-3 ${selectedReview.status === 'processing' ? 'animate-spin' : ''}`} />
                    {status.label}
                  </Badge>
                  <span className="text-xs text-muted-foreground">
                    {selectedReview.processed_documents}/{selectedReview.total_documents} documentos
                  </span>
                  {selectedReview.accuracy_score != null && (
                    <span className="text-xs text-muted-foreground">
                      Confianca: {(selectedReview.accuracy_score * 100).toFixed(1)}%
                    </span>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  className="rounded-full gap-1"
                  onClick={handleRefreshReview}
                >
                  <RefreshCw className="h-3.5 w-3.5" /> Atualizar
                </Button>
                {selectedReview.status === 'completed' && (
                  <>
                    <Button
                      variant="outline"
                      size="sm"
                      className="rounded-full gap-1"
                      disabled={exportingFormat !== null}
                      onClick={() => handleExport(selectedReview.id, 'csv')}
                    >
                      {exportingFormat === 'csv' ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <Download className="h-3.5 w-3.5" />
                      )}
                      Exportar CSV
                    </Button>
                    <Button
                      size="sm"
                      className="rounded-full gap-1"
                      disabled={exportingFormat !== null}
                      onClick={() => handleExport(selectedReview.id, 'xlsx')}
                    >
                      {exportingFormat === 'xlsx' ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <FileSpreadsheet className="h-3.5 w-3.5" />
                      )}
                      Exportar Excel
                    </Button>
                  </>
                )}
              </div>
            </div>
          </div>
        </AnimatedContainer>

        {/* Natural Language Query Bar */}
        {selectedReview.results.length > 0 && (
          <div className="rounded-2xl border border-white/70 bg-white/95 p-4 shadow-soft">
            <div className="flex items-center gap-2 mb-2">
              <MessageSquare className="h-4 w-4 text-primary" />
              <p className="text-sm font-medium text-foreground">Perguntar sobre a tabela</p>
            </div>
            <div className="flex items-center gap-2">
              <Input
                className="rounded-xl flex-1"
                placeholder="Ex: Quais contratos têm prazo superior a 12 meses?"
                value={queryInput}
                onChange={(e) => setQueryInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    handleQuery();
                  }
                }}
                disabled={queryLoading}
              />
              <Button
                className="rounded-full gap-1"
                size="sm"
                onClick={handleQuery}
                disabled={queryLoading || !queryInput.trim()}
              >
                {queryLoading ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Send className="h-3.5 w-3.5" />
                )}
                Consultar
              </Button>
            </div>

            {/* Query Result */}
            {queryLoading && (
              <div className="mt-4 flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                Analisando dados da tabela...
              </div>
            )}
            {queryResult && !queryLoading && (
              <div className="mt-4 rounded-xl border border-primary/20 bg-primary/5 p-4">
                <p className="text-sm text-foreground whitespace-pre-wrap">{queryResult.answer}</p>
                {queryResult.sources.length > 0 && (
                  <div className="mt-3 border-t border-primary/10 pt-3">
                    <p className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground mb-2">
                      Fontes referenciadas
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      {queryResult.sources.map((src, i) => (
                        <Badge
                          key={i}
                          variant="outline"
                          className="rounded-full text-[10px] gap-1"
                        >
                          <FileText className="h-3 w-3" />
                          {src.document_name}
                          {src.column_name && (
                            <span className="text-muted-foreground">({src.column_name})</span>
                          )}
                        </Badge>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* Results Table */}
        <div className="rounded-2xl border border-white/70 bg-white/95 shadow-soft overflow-hidden">
          {selectedReview.results.length === 0 ? (
            <div className="flex flex-col items-center justify-center p-12 text-center">
              {selectedReview.status === 'processing' ? (
                <>
                  <Loader2 className="h-12 w-12 text-blue-400 animate-spin mb-4" />
                  <p className="text-sm font-medium text-foreground">Extraindo dados...</p>
                  <p className="text-xs text-muted-foreground mt-1">
                    {selectedReview.processed_documents} de {selectedReview.total_documents} documentos processados.
                  </p>
                </>
              ) : (
                <>
                  <Table2 className="h-12 w-12 text-muted-foreground/30 mb-4" />
                  <p className="text-sm font-medium text-foreground">Nenhum resultado ainda</p>
                  <p className="text-xs text-muted-foreground mt-1">
                    {selectedReview.error_message || 'Aguardando processamento.'}
                  </p>
                </>
              )}
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-outline/10 bg-muted/30">
                    <th className="px-4 py-3 text-left text-[10px] font-bold uppercase tracking-wider text-muted-foreground sticky left-0 bg-muted/30 z-10 min-w-[200px]">
                      Documento
                    </th>
                    {colNames.map((col) => (
                      <th key={col} className="px-4 py-3 text-left text-[10px] font-bold uppercase tracking-wider text-muted-foreground min-w-[180px]">
                        {col}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-outline/10">
                  {selectedReview.results.map((row, idx) => {
                    const edits = row._edits || {};
                    return (
                      <tr key={idx} className="hover:bg-muted/20 transition-colors">
                        <td className="px-4 py-3 font-medium text-foreground sticky left-0 bg-white/95 z-10">
                          <span className="truncate block max-w-[200px]" title={row.document_name}>
                            {row.document_name}
                          </span>
                        </td>
                        {colNames.map((col) => {
                          const isEditing =
                            editingCell?.documentId === row.document_id &&
                            editingCell?.columnName === col;
                          const cellEdit = edits[col];
                          const isVerified = cellEdit?.verified ?? false;
                          const cellValue = row.columns[col] || '';

                          return (
                            <td key={col} className="px-1 py-1 text-muted-foreground relative group">
                              {isEditing ? (
                                /* Edit mode */
                                <div className="flex flex-col gap-1 p-1">
                                  <Textarea
                                    ref={editInputRef}
                                    className="rounded-lg text-sm min-h-[60px] resize-y border-primary/50 focus:ring-primary/30"
                                    value={editValue}
                                    onChange={(e) => setEditValue(e.target.value)}
                                    onKeyDown={(e) => {
                                      if (e.key === 'Enter' && !e.shiftKey) {
                                        e.preventDefault();
                                        handleSaveCell(false);
                                      }
                                      if (e.key === 'Escape') {
                                        handleCancelEdit();
                                      }
                                    }}
                                  />
                                  <div className="flex items-center gap-1">
                                    <Button
                                      size="sm"
                                      variant="default"
                                      className="h-6 rounded-full text-[10px] gap-0.5 px-2"
                                      onClick={() => handleSaveCell(false)}
                                      disabled={savingCell}
                                    >
                                      <Check className="h-3 w-3" /> Salvar
                                    </Button>
                                    <Button
                                      size="sm"
                                      variant="default"
                                      className="h-6 rounded-full text-[10px] gap-0.5 px-2 bg-emerald-600 hover:bg-emerald-700"
                                      onClick={() => handleSaveCell(true)}
                                      disabled={savingCell}
                                    >
                                      <CheckCircle2 className="h-3 w-3" /> Verificar
                                    </Button>
                                    <Button
                                      size="sm"
                                      variant="ghost"
                                      className="h-6 rounded-full text-[10px] gap-0.5 px-2"
                                      onClick={handleCancelEdit}
                                    >
                                      <X className="h-3 w-3" /> Cancelar
                                    </Button>
                                  </div>
                                </div>
                              ) : (
                                /* Display mode */
                                <div
                                  className="flex items-start gap-1 px-3 py-2 rounded-lg cursor-pointer hover:bg-muted/40 transition-colors min-h-[40px]"
                                  onClick={() => handleStartEdit(row.document_id, col, cellValue)}
                                  title="Clique para editar"
                                >
                                  <span className="block max-w-[220px] flex-1" title={cellValue}>
                                    {cellValue || '-'}
                                  </span>
                                  <div className="flex items-center gap-0.5 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
                                    <Pencil className="h-3 w-3 text-muted-foreground/50" />
                                  </div>
                                  {/* Cell history icon (shown when cell was edited) */}
                                  {cellEdit && (
                                    <button
                                      className="shrink-0 p-0.5 rounded-full text-blue-500 hover:text-blue-700 transition-colors"
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        handleViewCellHistory(row.document_id, col, row.document_name);
                                      }}
                                      title="Ver historico de alteracoes"
                                    >
                                      <History className="h-3.5 w-3.5" />
                                    </button>
                                  )}
                                  {/* Verified badge */}
                                  <button
                                    className={`shrink-0 p-0.5 rounded-full transition-colors ${
                                      isVerified
                                        ? 'text-emerald-600 hover:text-emerald-700'
                                        : 'text-muted-foreground/30 hover:text-muted-foreground/60 opacity-0 group-hover:opacity-100'
                                    }`}
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      handleToggleVerified(row.document_id, col);
                                    }}
                                    title={isVerified ? 'Verificado - clique para remover' : 'Marcar como verificado'}
                                  >
                                    <CheckCircle2 className="h-3.5 w-3.5" />
                                  </button>
                                </div>
                              )}
                            </td>
                          );
                        })}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Cell History Dialog */}
        <Dialog open={cellHistoryOpen} onOpenChange={setCellHistoryOpen}>
          <DialogContent className="sm:max-w-[500px] max-h-[70vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <History className="h-5 w-5 text-blue-600" />
                Historico de alteracoes
              </DialogTitle>
              <DialogDescription>
                {cellHistoryLabel}
              </DialogDescription>
            </DialogHeader>

            {cellHistoryLoading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              </div>
            ) : cellHistoryEntries.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-8 text-center">
                <Clock className="h-10 w-10 text-muted-foreground/30 mb-3" />
                <p className="text-sm text-muted-foreground">Nenhum historico de alteracoes encontrado.</p>
              </div>
            ) : (
              <div className="space-y-3">
                {cellHistoryEntries.map((entry, idx) => (
                  <div key={idx} className="rounded-xl border border-outline/10 p-3 space-y-2">
                    <div className="flex items-center justify-between text-xs text-muted-foreground">
                      <span className="font-medium">{entry.changed_by}</span>
                      <span>{new Date(entry.changed_at).toLocaleString('pt-BR')}</span>
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                      <div>
                        <p className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground mb-1">Antes</p>
                        <div className="rounded-lg bg-red-50 border border-red-100 p-2 text-xs text-foreground min-h-[32px]">
                          {entry.old_value || <span className="text-muted-foreground italic">(vazio)</span>}
                        </div>
                      </div>
                      <div>
                        <p className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground mb-1">Depois</p>
                        <div className="rounded-lg bg-emerald-50 border border-emerald-100 p-2 text-xs text-foreground min-h-[32px]">
                          {entry.new_value || <span className="text-muted-foreground italic">(vazio)</span>}
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </DialogContent>
        </Dialog>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Render: Create view
  // ---------------------------------------------------------------------------

  if (view === 'create') {
    return (
      <div className="space-y-6">
        <AnimatedContainer>
          <div className="rounded-3xl border border-white/70 bg-white/95 p-6 shadow-soft">
            <div className="flex items-center gap-3 mb-3">
              <Button
                variant="ghost"
                size="sm"
                className="rounded-full"
                onClick={() => { setView('templates'); setSelectedTemplate(null); }}
              >
                <ArrowLeft className="h-4 w-4 mr-1" /> Voltar
              </Button>
            </div>
            <p className="text-xs font-semibold uppercase text-muted-foreground">Nova Review Table</p>
            <h1 className="font-display text-2xl text-foreground">
              {selectedTemplate?.name}
            </h1>
            {selectedTemplate?.description && (
              <p className="text-sm text-muted-foreground mt-1">{selectedTemplate.description}</p>
            )}
          </div>
        </AnimatedContainer>

        {/* Columns preview */}
        <div className="rounded-2xl border border-white/70 bg-white/95 p-5 shadow-soft">
          <p className="text-sm font-medium text-foreground mb-3">Colunas de extracao</p>
          <div className="flex flex-wrap gap-2">
            {selectedTemplate?.columns.map((col) => (
              <Badge key={col.name} variant="outline" className="rounded-full text-xs gap-1">
                {col.name}
                <span className="text-muted-foreground">({col.type})</span>
              </Badge>
            ))}
          </div>
        </div>

        {/* Review name */}
        <div className="rounded-2xl border border-white/70 bg-white/95 p-5 shadow-soft">
          <p className="text-sm font-medium text-foreground mb-3">Nome da review</p>
          <Input
            className="rounded-xl"
            placeholder="Ex: Contratos de trabalho Q1 2026"
            value={reviewName}
            onChange={(e) => setReviewName(e.target.value)}
          />
        </div>

        {/* Document selector */}
        <div className="rounded-2xl border border-white/70 bg-white/95 p-5 shadow-soft">
          <div className="flex items-center justify-between mb-3">
            <div>
              <p className="text-sm font-medium text-foreground">Selecionar documentos</p>
              <p className="text-xs text-muted-foreground">
                {selectedDocIds.length} documento(s) selecionado(s)
              </p>
            </div>
            <div className="flex items-center gap-2">
              {user?.organization_id && (
                <Select value={accessFilter} onValueChange={setAccessFilter}>
                  <SelectTrigger className="w-[220px] rounded-xl">
                    <SelectValue placeholder="Acesso" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="org">Organizacao (privado)</SelectItem>
                    <SelectItem value="group_all" disabled={teamsLoading || myTeams.length === 0}>
                      Meus departamentos
                    </SelectItem>
                    {myTeams.map((t) => (
                      <SelectItem key={t.id} value={t.id}>
                        {t.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
              <div className="relative w-64">
                <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  className="rounded-xl pl-9"
                  placeholder="Buscar documentos..."
                  value={docSearch}
                  onChange={(e) => setDocSearch(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && loadDocuments()}
                />
              </div>
            </div>
          </div>

          {documents.length === 0 ? (
            <div className="text-center py-8">
              <p className="text-sm text-muted-foreground">
                Nenhum documento encontrado. Busque ou envie documentos no Corpus.
              </p>
              <Button
                variant="outline"
                size="sm"
                className="mt-3 rounded-full"
                onClick={loadDocuments}
              >
                Buscar documentos
              </Button>
            </div>
          ) : (
            <div className="max-h-64 overflow-y-auto space-y-1">
              {documents.map((doc) => {
                const isSelected = selectedDocIds.includes(doc.id);
                return (
                  <div
                    key={doc.id}
                    className={`flex items-center gap-3 px-3 py-2 rounded-lg cursor-pointer transition-colors ${
                      isSelected ? 'bg-primary/10 border border-primary/30' : 'hover:bg-muted/30'
                    }`}
                    onClick={() => {
                      setSelectedDocIds((prev) =>
                        isSelected ? prev.filter((id) => id !== doc.id) : [...prev, doc.id]
                      );
                    }}
                  >
                    <div className={`h-4 w-4 rounded border-2 flex items-center justify-center ${
                      isSelected ? 'bg-primary border-primary' : 'border-muted-foreground/30'
                    }`}>
                      {isSelected && <CheckCircle2 className="h-3 w-3 text-white" />}
                    </div>
                    <span className="text-sm text-foreground truncate">{doc.name}</span>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Create button */}
        <div className="flex justify-end">
          <Button
            className="rounded-full gap-2"
            disabled={loading || selectedDocIds.length === 0 || !reviewName.trim()}
            onClick={handleCreateReview}
          >
            {loading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Table2 className="h-4 w-4" />
            )}
            Criar e processar
          </Button>
        </div>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Render: Templates view
  // ---------------------------------------------------------------------------

  if (view === 'templates') {
    return (
      <div className="space-y-6">
        <AnimatedContainer>
          <div className="rounded-3xl border border-white/70 bg-white/95 p-6 shadow-soft">
            <div className="flex items-center gap-3 mb-3">
              <Button
                variant="ghost"
                size="sm"
                className="rounded-full"
                onClick={() => setView('list')}
              >
                <ArrowLeft className="h-4 w-4 mr-1" /> Voltar
              </Button>
            </div>
            <p className="text-xs font-semibold uppercase text-muted-foreground">Selecionar Template</p>
            <h1 className="font-display text-2xl text-foreground">
              Escolha um modelo de extracao
            </h1>
            <p className="text-sm text-muted-foreground mt-1">
              Templates pre-construidos para areas do direito brasileiro, ou crie o seu.
            </p>
          </div>
        </AnimatedContainer>

        {loadingTemplates ? (
          <div className="space-y-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-32 rounded-2xl" />
            ))}
          </div>
        ) : templates.length === 0 ? (
          <div className="rounded-2xl border border-white/70 bg-white/95 p-12 shadow-soft text-center">
            <Table2 className="h-12 w-12 text-muted-foreground/30 mx-auto mb-4" />
            <p className="text-sm font-medium text-foreground">Nenhum template encontrado</p>
            <p className="text-xs text-muted-foreground mt-1">
              Carregue os templates pre-construidos do sistema.
            </p>
            <Button
              className="mt-4 rounded-full gap-2"
              onClick={handleSeedTemplates}
            >
              <Plus className="h-4 w-4" /> Carregar templates
            </Button>
          </div>
        ) : (
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {templates.map((tmpl) => (
              <div
                key={tmpl.id}
                className="rounded-2xl border border-white/70 bg-white/95 p-5 shadow-soft hover:shadow-md transition-shadow cursor-pointer group"
                onClick={() => {
                  setSelectedTemplate(tmpl);
                  setView('create');
                  loadDocuments();
                }}
              >
                <div className="flex items-start justify-between mb-3">
                  <div>
                    <h3 className="text-sm font-semibold text-foreground">{tmpl.name}</h3>
                    {tmpl.area && (
                      <Badge variant="outline" className="rounded-full text-[10px] mt-1">
                        {areaLabels[tmpl.area] || tmpl.area}
                      </Badge>
                    )}
                  </div>
                  <ChevronRight className="h-4 w-4 text-muted-foreground group-hover:text-foreground transition-colors" />
                </div>
                {tmpl.description && (
                  <p className="text-xs text-muted-foreground mb-3 line-clamp-2">{tmpl.description}</p>
                )}
                <div className="flex flex-wrap gap-1">
                  {tmpl.columns.slice(0, 5).map((col) => (
                    <Badge key={col.name} variant="secondary" className="rounded-full text-[10px]">
                      {col.name}
                    </Badge>
                  ))}
                  {tmpl.columns.length > 5 && (
                    <Badge variant="secondary" className="rounded-full text-[10px]">
                      +{tmpl.columns.length - 5}
                    </Badge>
                  )}
                </div>
                {tmpl.is_system && (
                  <div className="mt-3">
                    <Badge className="rounded-full text-[10px] bg-primary/10 text-primary border-0">
                      Iudex
                    </Badge>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Render: List view (default)
  // ---------------------------------------------------------------------------

  return (
    <div className="space-y-8">
      {/* Header */}
      <AnimatedContainer>
        <div className="rounded-3xl border border-white/70 bg-white/95 p-6 shadow-soft">
          <div className="flex items-center gap-3 mb-1">
            <Link
              href="/corpus"
              className="text-xs text-muted-foreground hover:text-foreground transition-colors"
            >
              Corpus
            </Link>
            <ChevronRight className="h-3 w-3 text-muted-foreground" />
            <span className="text-xs font-medium text-foreground">Review Tables</span>
          </div>
          <p className="text-xs font-semibold uppercase text-muted-foreground">Review Tables</p>
          <h1 className="font-display text-3xl text-foreground">
            Extracao estruturada de documentos
          </h1>
          <p className="text-sm text-muted-foreground">
            Selecione um template e documentos para extrair dados automaticamente em formato de tabela.
            Inspirado no Harvey AI Vault.
          </p>
        </div>
      </AnimatedContainer>

      {/* Actions */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Button
            className="rounded-full gap-2"
            onClick={() => setView('templates')}
          >
            <Plus className="h-4 w-4" /> Nova Review Table
          </Button>
        </div>
        <Button
          variant="outline"
          size="sm"
          className="rounded-full gap-1"
          onClick={loadReviews}
        >
          <RefreshCw className="h-3.5 w-3.5" /> Atualizar
        </Button>
      </div>

      {/* Workflows Pre-Construidos */}
      {systemTemplates.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-4">
            <Zap className="h-4 w-4 text-primary" />
            <h2 className="text-sm font-semibold text-foreground">Workflows Pre-Construidos</h2>
            <span className="text-xs text-muted-foreground">
              Selecione um modelo e aplique a seus documentos com um clique
            </span>
          </div>
          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {systemTemplates.map((tmpl) => {
              const AreaIcon = areaIcons[tmpl.area || ''] || FileText;
              const colorClass = areaColors[tmpl.area || ''] || 'from-slate-500/10 to-slate-600/5 border-slate-200/50';
              return (
                <div
                  key={tmpl.id}
                  className={`rounded-2xl border bg-gradient-to-br ${colorClass} p-4 shadow-soft hover:shadow-md transition-all cursor-pointer group hover:scale-[1.02]`}
                  onClick={() => handleOpenWorkflow(tmpl)}
                >
                  <div className="flex items-start justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <div className="h-8 w-8 rounded-xl bg-white/80 flex items-center justify-center shadow-sm">
                        <AreaIcon className="h-4 w-4 text-foreground" />
                      </div>
                      <div>
                        <h3 className="text-sm font-semibold text-foreground leading-tight">{tmpl.name}</h3>
                        {tmpl.area && (
                          <span className="text-[10px] text-muted-foreground">
                            {areaLabels[tmpl.area] || tmpl.area}
                          </span>
                        )}
                      </div>
                    </div>
                    <ChevronRight className="h-4 w-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
                  </div>
                  {tmpl.description && (
                    <p className="text-[11px] text-muted-foreground mb-2 line-clamp-2">{tmpl.description}</p>
                  )}
                  <div className="flex items-center gap-1.5">
                    <Badge variant="secondary" className="rounded-full text-[10px] bg-white/60">
                      {tmpl.columns.length} colunas
                    </Badge>
                    <Badge className="rounded-full text-[10px] bg-primary/10 text-primary border-0">
                      Iudex
                    </Badge>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {loadingSystemTemplates && systemTemplates.length === 0 && (
        <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-32 rounded-2xl" />
          ))}
        </div>
      )}

      {/* Workflow Modal - Selecionar documentos */}
      <Dialog open={showWorkflowModal} onOpenChange={setShowWorkflowModal}>
        <DialogContent className="sm:max-w-[600px] max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Zap className="h-5 w-5 text-primary" />
              {workflowTemplate?.name}
            </DialogTitle>
            <DialogDescription>
              {workflowTemplate?.description || 'Selecione os documentos para extrair dados automaticamente.'}
            </DialogDescription>
          </DialogHeader>

          {/* Template columns preview */}
          <div className="mt-2">
            <p className="text-xs font-medium text-muted-foreground mb-2">
              Colunas de extracao ({workflowTemplate?.columns.length})
            </p>
            <div className="flex flex-wrap gap-1.5">
              {workflowTemplate?.columns.slice(0, 8).map((col) => (
                <Badge key={col.name} variant="outline" className="rounded-full text-[10px] gap-1">
                  {col.name}
                  <span className="text-muted-foreground/70">({col.type})</span>
                </Badge>
              ))}
              {(workflowTemplate?.columns.length || 0) > 8 && (
                <Badge variant="outline" className="rounded-full text-[10px]">
                  +{(workflowTemplate?.columns.length || 0) - 8} mais
                </Badge>
              )}
            </div>
          </div>

          {/* Review name (optional) */}
          <div className="mt-3">
            <p className="text-xs font-medium text-muted-foreground mb-1.5">
              Nome da review (opcional)
            </p>
            <Input
              className="rounded-xl text-sm"
              placeholder={`Ex: ${workflowTemplate?.name} — Fev 2026`}
              value={workflowName}
              onChange={(e) => setWorkflowName(e.target.value)}
            />
          </div>

          {/* Document selector */}
          <div className="mt-3">
            <div className="flex items-center justify-between mb-2">
              <div>
                <p className="text-xs font-medium text-muted-foreground">Selecionar documentos</p>
                <p className="text-[10px] text-muted-foreground">
                  {workflowSelectedDocs.length} selecionado(s)
                </p>
              </div>
              <div className="flex items-center gap-2">
                {user?.organization_id && (
                  <Select value={accessFilter} onValueChange={setAccessFilter}>
                    <SelectTrigger className="w-[220px] rounded-xl h-8 text-xs">
                      <SelectValue placeholder="Acesso" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="org">Organizacao (privado)</SelectItem>
                      <SelectItem value="group_all" disabled={teamsLoading || myTeams.length === 0}>
                        Meus departamentos
                      </SelectItem>
                      {myTeams.map((t) => (
                        <SelectItem key={t.id} value={t.id}>
                          {t.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
                <div className="relative w-48">
                  <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    className="rounded-xl pl-8 text-xs h-8"
                    placeholder="Buscar..."
                    value={workflowDocSearch}
                    onChange={(e) => setWorkflowDocSearch(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && loadWorkflowDocs()}
                  />
                </div>
              </div>
            </div>

            {workflowDocs.length === 0 ? (
              <div className="text-center py-6 bg-muted/20 rounded-xl">
                <p className="text-xs text-muted-foreground">
                  Nenhum documento encontrado.
                </p>
                <Button
                  variant="outline"
                  size="sm"
                  className="mt-2 rounded-full text-xs"
                  onClick={loadWorkflowDocs}
                >
                  Buscar documentos
                </Button>
              </div>
            ) : (
              <div className="max-h-48 overflow-y-auto space-y-1 rounded-xl border border-outline/10 p-2">
                {workflowDocs.map((doc) => {
                  const isSelected = workflowSelectedDocs.includes(doc.id);
                  return (
                    <div
                      key={doc.id}
                      className={`flex items-center gap-2.5 px-2.5 py-1.5 rounded-lg cursor-pointer transition-colors text-xs ${
                        isSelected ? 'bg-primary/10 border border-primary/30' : 'hover:bg-muted/30'
                      }`}
                      onClick={() => {
                        setWorkflowSelectedDocs((prev) =>
                          isSelected ? prev.filter((id) => id !== doc.id) : [...prev, doc.id]
                        );
                      }}
                    >
                      <div className={`h-3.5 w-3.5 rounded border-2 flex items-center justify-center shrink-0 ${
                        isSelected ? 'bg-primary border-primary' : 'border-muted-foreground/30'
                      }`}>
                        {isSelected && <Check className="h-2.5 w-2.5 text-white" />}
                      </div>
                      <span className="text-foreground truncate">{doc.name}</span>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Action button */}
          <div className="flex justify-end gap-2 mt-4">
            <Button
              variant="outline"
              className="rounded-full"
              onClick={() => setShowWorkflowModal(false)}
            >
              Cancelar
            </Button>
            <Button
              className="rounded-full gap-2"
              disabled={workflowLoading || workflowSelectedDocs.length === 0}
              onClick={handleCreateFromWorkflow}
            >
              {workflowLoading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Zap className="h-4 w-4" />
              )}
              Extrair dados ({workflowSelectedDocs.length} doc{workflowSelectedDocs.length !== 1 ? 's' : ''})
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Reviews List */}
      <div className="rounded-2xl border border-white/70 bg-white/95 shadow-soft overflow-hidden">
        {loadingReviews ? (
          <div className="p-5 space-y-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-16 rounded-xl" />
            ))}
          </div>
        ) : reviews.length === 0 ? (
          <div className="flex flex-col items-center justify-center p-12 text-center">
            <Table2 className="h-12 w-12 text-muted-foreground/30 mb-4" />
            <p className="text-sm font-medium text-foreground">Nenhuma review table criada</p>
            <p className="text-xs text-muted-foreground mt-1">
              Crie uma nova review table selecionando um template e documentos.
            </p>
            <Button
              className="mt-4 rounded-full gap-2"
              onClick={() => setView('templates')}
            >
              <Plus className="h-4 w-4" /> Criar primeira review
            </Button>
          </div>
        ) : (
          <>
            {/* Header */}
            <div className="hidden lg:grid lg:grid-cols-12 gap-4 px-5 py-3 border-b border-outline/10 text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
              <div className="col-span-4">Nome</div>
              <div className="col-span-2">Template</div>
              <div className="col-span-2">Status</div>
              <div className="col-span-2">Progresso</div>
              <div className="col-span-2 text-right">Acoes</div>
            </div>

            {/* Rows */}
            <div className="divide-y divide-outline/10">
              {reviews.map((review) => {
                const st = statusConfig[review.status] || statusConfig.created;
                const StIcon = st.icon;
                return (
                  <div
                    key={review.id}
                    className="grid grid-cols-1 lg:grid-cols-12 gap-2 lg:gap-4 px-5 py-3 hover:bg-muted/30 transition-colors items-center"
                  >
                    <div className="col-span-4 flex items-center gap-3">
                      <Table2 className="h-4 w-4 text-primary shrink-0" />
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-foreground truncate">{review.name}</p>
                        <p className="text-[10px] text-muted-foreground">
                          {review.total_documents} documento(s)
                        </p>
                      </div>
                    </div>
                    <div className="col-span-2">
                      <span className="text-xs text-muted-foreground">
                        {review.template_name || '-'}
                      </span>
                    </div>
                    <div className="col-span-2">
                      <Badge className={`rounded-full text-[10px] border-0 gap-1 ${st.color}`}>
                        <StIcon className={`h-3 w-3 ${review.status === 'processing' ? 'animate-spin' : ''}`} />
                        {st.label}
                      </Badge>
                    </div>
                    <div className="col-span-2">
                      <div className="flex items-center gap-2">
                        <div className="flex-1 h-1.5 bg-muted rounded-full overflow-hidden">
                          <div
                            className="h-full bg-primary rounded-full transition-all"
                            style={{
                              width: `${review.total_documents > 0
                                ? (review.processed_documents / review.total_documents) * 100
                                : 0}%`,
                            }}
                          />
                        </div>
                        <span className="text-[10px] text-muted-foreground">
                          {review.processed_documents}/{review.total_documents}
                        </span>
                      </div>
                    </div>
                    <div className="col-span-2 flex items-center justify-end gap-1">
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 rounded-full"
                        onClick={() => handleViewReview(review.id)}
                        title="Visualizar"
                      >
                        <Eye className="h-3.5 w-3.5" />
                      </Button>
                      {review.status === 'completed' && (
                        <>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8 rounded-full"
                            disabled={exportingFormat !== null}
                            onClick={() => handleExport(review.id, 'csv')}
                            title="Exportar CSV"
                          >
                            <Download className="h-3.5 w-3.5" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8 rounded-full"
                            disabled={exportingFormat !== null}
                            onClick={() => handleExport(review.id, 'xlsx')}
                            title="Exportar Excel"
                          >
                            {exportingFormat === 'xlsx' ? (
                              <Loader2 className="h-3.5 w-3.5 animate-spin" />
                            ) : (
                              <FileSpreadsheet className="h-3.5 w-3.5" />
                            )}
                          </Button>
                        </>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
