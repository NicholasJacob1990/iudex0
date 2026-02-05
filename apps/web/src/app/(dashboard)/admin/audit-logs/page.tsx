'use client';

import React, { useCallback, useEffect, useState } from 'react';
import {
  Download,
  Filter,
  Loader2,
  Search,
  Shield,
  ChevronLeft,
  ChevronRight,
  Calendar,
  User,
  Activity,
  FileText,
  X,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { toast } from 'sonner';
import { apiClient } from '@/lib/api-client';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface AuditLogEntry {
  id: string;
  user_id: string;
  user_name: string | null;
  user_email: string | null;
  action: string;
  resource_type: string;
  resource_id: string | null;
  details: Record<string, unknown> | null;
  ip_address: string | null;
  created_at: string;
}

interface AuditStats {
  period_days: number;
  total: number;
  by_action: Record<string, number>;
  by_resource_type: Record<string, number>;
  top_users: Array<{ user_id: string; name: string; count: number }>;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const ACTION_OPTIONS = [
  { value: '', label: 'Todas as ações' },
  { value: 'create', label: 'Criar' },
  { value: 'read', label: 'Ler' },
  { value: 'update', label: 'Atualizar' },
  { value: 'delete', label: 'Excluir' },
  { value: 'export', label: 'Exportar' },
  { value: 'share', label: 'Compartilhar' },
  { value: 'login', label: 'Login' },
  { value: 'analyze', label: 'Analisar' },
];

const RESOURCE_TYPE_OPTIONS = [
  { value: '', label: 'Todos os recursos' },
  { value: 'playbook', label: 'Playbook' },
  { value: 'corpus_project', label: 'Projeto Corpus' },
  { value: 'review_table', label: 'Tabela de Revisão' },
  { value: 'document', label: 'Documento' },
  { value: 'chat', label: 'Chat' },
  { value: 'dms', label: 'DMS' },
  { value: 'user', label: 'Usuário' },
  { value: 'organization', label: 'Organização' },
];

const ACTION_COLORS: Record<string, string> = {
  create: 'bg-green-100 text-green-800',
  read: 'bg-blue-100 text-blue-800',
  update: 'bg-amber-100 text-amber-800',
  delete: 'bg-red-100 text-red-800',
  export: 'bg-purple-100 text-purple-800',
  share: 'bg-indigo-100 text-indigo-800',
  login: 'bg-slate-100 text-slate-800',
  analyze: 'bg-cyan-100 text-cyan-800',
};

const ACTION_LABELS: Record<string, string> = {
  create: 'Criar',
  read: 'Ler',
  update: 'Atualizar',
  delete: 'Excluir',
  export: 'Exportar',
  share: 'Compartilhar',
  login: 'Login',
  analyze: 'Analisar',
};

const RESOURCE_LABELS: Record<string, string> = {
  playbook: 'Playbook',
  corpus_project: 'Projeto Corpus',
  review_table: 'Tabela de Revisão',
  document: 'Documento',
  chat: 'Chat',
  dms: 'DMS',
  user: 'Usuário',
  organization: 'Organização',
};

const PAGE_SIZE = 50;

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function AdminAuditLogsPage() {
  const [logs, setLogs] = useState<AuditLogEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [offset, setOffset] = useState(0);
  const [stats, setStats] = useState<AuditStats | null>(null);
  const [loadingStats, setLoadingStats] = useState(true);

  // Filters
  const [filterAction, setFilterAction] = useState('');
  const [filterResourceType, setFilterResourceType] = useState('');
  const [filterUserId, setFilterUserId] = useState('');
  const [filterDateFrom, setFilterDateFrom] = useState('');
  const [filterDateTo, setFilterDateTo] = useState('');
  const [showFilters, setShowFilters] = useState(false);

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, string | number> = {
        limit: PAGE_SIZE,
        offset,
      };
      if (filterAction) params.action = filterAction;
      if (filterResourceType) params.resource_type = filterResourceType;
      if (filterUserId) params.user_id = filterUserId;
      if (filterDateFrom) params.date_from = new Date(filterDateFrom).toISOString();
      if (filterDateTo) params.date_to = new Date(filterDateTo + 'T23:59:59').toISOString();

      const data = await apiClient.getAuditLogs(params);
      setLogs(data.items);
      setTotal(data.total);
    } catch (err: any) {
      if (err?.response?.status === 403) {
        toast.error('Acesso restrito a administradores.');
      } else {
        toast.error('Erro ao carregar audit logs.');
      }
    } finally {
      setLoading(false);
    }
  }, [offset, filterAction, filterResourceType, filterUserId, filterDateFrom, filterDateTo]);

  const fetchStats = useCallback(async () => {
    setLoadingStats(true);
    try {
      const data = await apiClient.getAuditLogStats(30);
      setStats(data);
    } catch {
      // Stats are optional, don't show error
    } finally {
      setLoadingStats(false);
    }
  }, []);

  useEffect(() => {
    fetchLogs();
  }, [fetchLogs]);

  useEffect(() => {
    fetchStats();
  }, [fetchStats]);

  const handleExportCsv = async () => {
    try {
      const params: Record<string, string> = {};
      if (filterAction) params.action = filterAction;
      if (filterResourceType) params.resource_type = filterResourceType;
      if (filterUserId) params.user_id = filterUserId;
      if (filterDateFrom) params.date_from = new Date(filterDateFrom).toISOString();
      if (filterDateTo) params.date_to = new Date(filterDateTo + 'T23:59:59').toISOString();

      const blob = await apiClient.exportAuditLogsCsv(params);
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `audit_logs_${new Date().toISOString().slice(0, 10)}.csv`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      toast.success('Exportação CSV realizada com sucesso.');
    } catch {
      toast.error('Erro ao exportar audit logs.');
    }
  };

  const clearFilters = () => {
    setFilterAction('');
    setFilterResourceType('');
    setFilterUserId('');
    setFilterDateFrom('');
    setFilterDateTo('');
    setOffset(0);
  };

  const hasActiveFilters = filterAction || filterResourceType || filterUserId || filterDateFrom || filterDateTo;

  const totalPages = Math.ceil(total / PAGE_SIZE);
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;

  return (
    <div className="flex flex-col gap-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-indigo-100 rounded-lg">
            <Shield className="h-6 w-6 text-indigo-600" />
          </div>
          <div>
            <h1 className="text-2xl font-bold">Audit Logs</h1>
            <p className="text-sm text-muted-foreground">
              Rastreamento de todas as ações realizadas na plataforma
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setShowFilters(!showFilters)}
          >
            <Filter className="mr-2 h-4 w-4" />
            Filtros
            {hasActiveFilters && (
              <Badge variant="secondary" className="ml-2">
                Ativo
              </Badge>
            )}
          </Button>
          <Button variant="outline" size="sm" onClick={handleExportCsv}>
            <Download className="mr-2 h-4 w-4" />
            Exportar CSV
          </Button>
        </div>
      </div>

      {/* Stats Cards */}
      {!loadingStats && stats && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
                <Activity className="h-4 w-4" />
                Total (30 dias)
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stats.total.toLocaleString('pt-BR')}</div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
                <User className="h-4 w-4" />
                Logins
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">
                {(stats.by_action['login'] || 0).toLocaleString('pt-BR')}
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
                <FileText className="h-4 w-4" />
                Documentos
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">
                {(stats.by_resource_type['document'] || 0).toLocaleString('pt-BR')}
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
                <User className="h-4 w-4" />
                Usuários ativos
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stats.top_users.length}</div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Filters Panel */}
      {showFilters && (
        <Card className="p-4">
          <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-5 gap-4">
            <div>
              <label className="text-xs font-medium text-muted-foreground mb-1 block">
                Ação
              </label>
              <Select
                value={filterAction || 'all'}
                onValueChange={(v) => { setFilterAction(v === 'all' ? '' : v); setOffset(0); }}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Todas as ações" />
                </SelectTrigger>
                <SelectContent>
                  {ACTION_OPTIONS.map((opt) => (
                    <SelectItem key={opt.value || 'all'} value={opt.value || 'all'}>
                      {opt.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <label className="text-xs font-medium text-muted-foreground mb-1 block">
                Tipo de Recurso
              </label>
              <Select
                value={filterResourceType || 'all'}
                onValueChange={(v) => { setFilterResourceType(v === 'all' ? '' : v); setOffset(0); }}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Todos os recursos" />
                </SelectTrigger>
                <SelectContent>
                  {RESOURCE_TYPE_OPTIONS.map((opt) => (
                    <SelectItem key={opt.value || 'all'} value={opt.value || 'all'}>
                      {opt.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <label className="text-xs font-medium text-muted-foreground mb-1 block">
                Data Início
              </label>
              <Input
                type="date"
                value={filterDateFrom}
                onChange={(e) => { setFilterDateFrom(e.target.value); setOffset(0); }}
              />
            </div>
            <div>
              <label className="text-xs font-medium text-muted-foreground mb-1 block">
                Data Fim
              </label>
              <Input
                type="date"
                value={filterDateTo}
                onChange={(e) => { setFilterDateTo(e.target.value); setOffset(0); }}
              />
            </div>
            <div>
              <label className="text-xs font-medium text-muted-foreground mb-1 block">
                ID do Usuário
              </label>
              <Input
                placeholder="ID do usuário..."
                value={filterUserId}
                onChange={(e) => { setFilterUserId(e.target.value); setOffset(0); }}
              />
            </div>
          </div>
          {hasActiveFilters && (
            <div className="mt-3 flex justify-end">
              <Button variant="ghost" size="sm" onClick={clearFilters}>
                <X className="mr-1 h-3 w-3" />
                Limpar filtros
              </Button>
            </div>
          )}
        </Card>
      )}

      {/* Table */}
      <Card>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/50">
                <th className="text-left p-3 font-medium text-muted-foreground">Data</th>
                <th className="text-left p-3 font-medium text-muted-foreground">Usuário</th>
                <th className="text-left p-3 font-medium text-muted-foreground">Ação</th>
                <th className="text-left p-3 font-medium text-muted-foreground">Recurso</th>
                <th className="text-left p-3 font-medium text-muted-foreground">IP</th>
                <th className="text-left p-3 font-medium text-muted-foreground">Detalhes</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={6} className="p-8 text-center">
                    <Loader2 className="h-6 w-6 animate-spin mx-auto text-muted-foreground" />
                  </td>
                </tr>
              ) : logs.length === 0 ? (
                <tr>
                  <td colSpan={6} className="p-8 text-center text-muted-foreground">
                    Nenhum registro encontrado.
                  </td>
                </tr>
              ) : (
                logs.map((log) => (
                  <tr key={log.id} className="border-b hover:bg-muted/30 transition-colors">
                    <td className="p-3 whitespace-nowrap">
                      <div className="flex items-center gap-1 text-xs">
                        <Calendar className="h-3 w-3 text-muted-foreground" />
                        {new Date(log.created_at).toLocaleDateString('pt-BR')}
                      </div>
                      <div className="text-xs text-muted-foreground">
                        {new Date(log.created_at).toLocaleTimeString('pt-BR')}
                      </div>
                    </td>
                    <td className="p-3">
                      <div className="font-medium text-sm">{log.user_name || 'Desconhecido'}</div>
                      <div className="text-xs text-muted-foreground">{log.user_email || log.user_id}</div>
                    </td>
                    <td className="p-3">
                      <Badge
                        variant="secondary"
                        className={ACTION_COLORS[log.action] || 'bg-gray-100 text-gray-800'}
                      >
                        {ACTION_LABELS[log.action] || log.action}
                      </Badge>
                    </td>
                    <td className="p-3">
                      <div className="text-sm">
                        {RESOURCE_LABELS[log.resource_type] || log.resource_type}
                      </div>
                      {log.resource_id && (
                        <div className="text-xs text-muted-foreground font-mono truncate max-w-[200px]">
                          {log.resource_id}
                        </div>
                      )}
                    </td>
                    <td className="p-3">
                      <span className="text-xs font-mono text-muted-foreground">
                        {log.ip_address || '-'}
                      </span>
                    </td>
                    <td className="p-3">
                      {log.details ? (
                        <span
                          className="text-xs text-muted-foreground truncate block max-w-[250px] cursor-help"
                          title={JSON.stringify(log.details, null, 2)}
                        >
                          {Object.keys(log.details).join(', ')}
                        </span>
                      ) : (
                        <span className="text-xs text-muted-foreground">-</span>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {total > PAGE_SIZE && (
          <div className="flex items-center justify-between border-t p-3">
            <div className="text-sm text-muted-foreground">
              Mostrando {offset + 1} - {Math.min(offset + PAGE_SIZE, total)} de{' '}
              {total.toLocaleString('pt-BR')} registros
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              >
                <ChevronLeft className="h-4 w-4" />
                Anterior
              </Button>
              <span className="text-sm text-muted-foreground">
                Página {currentPage} de {totalPages}
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={offset + PAGE_SIZE >= total}
                onClick={() => setOffset(offset + PAGE_SIZE)}
              >
                Próxima
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}
