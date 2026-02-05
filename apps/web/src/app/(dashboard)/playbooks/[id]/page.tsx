'use client';

import { useState, useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import {
  ArrowLeft,
  Plus,
  Loader2,
  Play,
  Settings,
  Save,
  BookCheck,
  FileText,
  Download,
  History,
  Clock,
  User,
  ChevronDown,
  ChevronRight,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';
import { PlaybookRuleEditor } from '../components/playbook-rule-editor';
import { PlaybookRuleForm } from '../components/playbook-rule-form';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  type Playbook,
  type PlaybookRule,
  type PlaybookArea,
  type PlaybookStatus,
  type PlaybookVersionEntry,
  AREA_LABELS,
  usePlaybook,
  usePlaybookRules,
  useUpdatePlaybook,
  useCreateRule,
  useUpdateRule,
  useDeleteRule,
  usePlaybookVersions,
  getPlaybookExportUrl,
} from '../hooks';

// ============================================================================
// Version History Timeline Component
// ============================================================================

type EditorTab = 'rules' | 'versions';

function formatVersionDate(dateStr: string): string {
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString('pt-BR', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return dateStr;
  }
}

function VersionTimelineEntry({
  version,
  isFirst,
}: {
  version: PlaybookVersionEntry;
  isFirst: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const rulesCount = version.previous_rules?.length ?? 0;

  return (
    <div className="relative flex gap-3">
      {/* Timeline dot + line */}
      <div className="flex flex-col items-center">
        <div
          className={cn(
            'w-3 h-3 rounded-full border-2 shrink-0 mt-1',
            isFirst
              ? 'border-indigo-500 bg-indigo-500'
              : 'border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900'
          )}
        />
        <div className="w-px flex-1 bg-slate-200 dark:bg-slate-700" />
      </div>

      {/* Content */}
      <div className="pb-6 flex-1 min-w-0">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="text-sm font-medium text-slate-700 dark:text-slate-300">
              Versao {version.version_number}
            </p>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
              {version.changes_summary}
            </p>
          </div>
          {isFirst && (
            <Badge className="shrink-0 text-[10px] bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-400 border-0">
              Atual
            </Badge>
          )}
        </div>

        <div className="flex items-center gap-3 mt-2 text-[11px] text-slate-400">
          <span className="flex items-center gap-1">
            <Clock className="h-3 w-3" />
            {formatVersionDate(version.created_at)}
          </span>
          {version.changed_by_email && (
            <span className="flex items-center gap-1">
              <User className="h-3 w-3" />
              {version.changed_by_email}
            </span>
          )}
        </div>

        {/* Expandable previous rules snapshot */}
        {rulesCount > 0 && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="flex items-center gap-1 mt-2 text-[11px] text-indigo-500 hover:text-indigo-600 transition-colors"
          >
            {expanded ? (
              <ChevronDown className="h-3 w-3" />
            ) : (
              <ChevronRight className="h-3 w-3" />
            )}
            {rulesCount} regra(s) nesta versao
          </button>
        )}
        {expanded && rulesCount > 0 && (
          <div className="mt-2 space-y-1">
            {version.previous_rules.map((rule: any, idx: number) => (
              <div
                key={rule.id ?? idx}
                className="text-[11px] text-slate-500 dark:text-slate-400 bg-slate-50 dark:bg-slate-800/50 rounded px-2 py-1"
              >
                <span className="font-medium">{rule.rule_name ?? rule.name ?? `Regra ${idx + 1}`}</span>
                {rule.clause_type && (
                  <span className="text-slate-400 ml-1">({rule.clause_type})</span>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function PlaybookVersionTimeline({ playbookId }: { playbookId: string }) {
  const { data: versions, isLoading } = usePlaybookVersions(playbookId);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-5 w-5 text-indigo-500 animate-spin" />
      </div>
    );
  }

  const sortedVersions = [...(versions ?? [])].sort(
    (a, b) => b.version_number - a.version_number
  );

  if (sortedVersions.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-slate-200 dark:border-slate-700 p-12 text-center">
        <History className="h-10 w-10 text-slate-300 mx-auto mb-3" />
        <p className="text-sm text-slate-500 dark:text-slate-400 mb-1">
          Nenhuma versao registrada
        </p>
        <p className="text-xs text-slate-400 max-w-sm mx-auto">
          Versoes sao criadas automaticamente quando regras sao adicionadas, editadas ou removidas.
        </p>
      </div>
    );
  }

  return (
    <ScrollArea className="h-[600px] pr-2">
      <div className="space-y-0">
        {sortedVersions.map((v, idx) => (
          <VersionTimelineEntry key={v.id} version={v} isFirst={idx === 0} />
        ))}
      </div>
    </ScrollArea>
  );
}

// ============================================================================
// Main Editor Page
// ============================================================================

export default function PlaybookEditorPage() {
  const params = useParams();
  const router = useRouter();
  const playbookId = params.id as string;

  const { data: playbook, isLoading: playbookLoading } = usePlaybook(playbookId);
  const { data: rules, isLoading: rulesLoading } = usePlaybookRules(playbookId);
  const updatePlaybook = useUpdatePlaybook();
  const createRule = useCreateRule();
  const updateRule = useUpdateRule();
  const deleteRule = useDeleteRule();

  const [showRuleForm, setShowRuleForm] = useState(false);
  const [showMetadata, setShowMetadata] = useState(true);
  const [activeTab, setActiveTab] = useState<EditorTab>('rules');

  // Local metadata state
  const [editName, setEditName] = useState('');
  const [editDescription, setEditDescription] = useState('');
  const [editArea, setEditArea] = useState<PlaybookArea>('outro');
  const [editScope, setEditScope] = useState('');
  const [editStatus, setEditStatus] = useState<PlaybookStatus>('rascunho');

  // Sync local state when playbook data loads or changes
  useEffect(() => {
    if (playbook) {
      setEditName(playbook.name);
      setEditDescription(playbook.description);
      setEditArea(playbook.area);
      setEditScope(playbook.scope);
      setEditStatus(playbook.status);
    }
  }, [playbook]);

  const handleSaveMetadata = async () => {
    if (!editName.trim()) return;
    try {
      await updatePlaybook.mutateAsync({
        id: playbookId,
        name: editName.trim(),
        description: editDescription.trim(),
        area: editArea,
        scope: editScope.trim(),
        status: editStatus,
      });
      toast.success('Metadados salvos');
    } catch {
      toast.error('Erro ao salvar metadados');
    }
  };

  const handleCreateRule = async (data: Omit<PlaybookRule, 'id' | 'created_at' | 'updated_at'>) => {
    await createRule.mutateAsync(data);
  };

  const handleUpdateRule = async (data: Partial<PlaybookRule> & { id: string; playbook_id: string }) => {
    await updateRule.mutateAsync(data);
  };

  const handleDeleteRule = async (ruleId: string) => {
    await deleteRule.mutateAsync({ ruleId, playbookId });
  };

  const isLoading = playbookLoading || rulesLoading;

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-8 w-8 text-indigo-500 animate-spin" />
      </div>
    );
  }

  if (!playbook) {
    return (
      <div className="text-center py-20">
        <BookCheck className="h-12 w-12 text-slate-300 mx-auto mb-4" />
        <p className="text-slate-500 dark:text-slate-400 mb-4">Playbook nao encontrado</p>
        <Button variant="outline" onClick={() => router.push('/playbooks')} className="gap-2">
          <ArrowLeft className="h-4 w-4" />
          Voltar para Playbooks
        </Button>
      </div>
    );
  }

  const sortedRules = [...(rules || playbook.rules || [])].sort((a, b) => a.order - b.order);

  const statusConfig: Record<string, { label: string; className: string }> = {
    ativo: { label: 'Ativo', className: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400' },
    rascunho: { label: 'Rascunho', className: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400' },
    arquivado: { label: 'Arquivado', className: 'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400' },
  };

  return (
    <div className="container mx-auto max-w-6xl space-y-6">
      {/* Top bar */}
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => router.push('/playbooks')}
            className="shrink-0"
          >
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-xl font-bold text-slate-800 dark:text-slate-200">
                {playbook.name}
              </h1>
              <Badge className={cn('text-[10px] border-0', statusConfig[playbook.status]?.className)}>
                {statusConfig[playbook.status]?.label}
              </Badge>
            </div>
            <p className="text-xs text-slate-500">
              {AREA_LABELS[playbook.area]} | {sortedRules.length} regra(s)
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            className="gap-1.5"
            onClick={() => setShowMetadata(!showMetadata)}
          >
            <Settings className="h-3.5 w-3.5" />
            {showMetadata ? 'Ocultar' : 'Metadados'}
          </Button>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="sm" className="gap-1.5">
                <Download className="h-3.5 w-3.5" />
                Exportar
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem asChild>
                <a
                  href={getPlaybookExportUrl(playbookId, 'json')}
                  download
                  className="cursor-pointer"
                >
                  Exportar como JSON
                </a>
              </DropdownMenuItem>
              <DropdownMenuItem asChild>
                <a
                  href={getPlaybookExportUrl(playbookId, 'pdf')}
                  download
                  className="cursor-pointer"
                >
                  Exportar como PDF
                </a>
              </DropdownMenuItem>
              <DropdownMenuItem asChild>
                <a
                  href={getPlaybookExportUrl(playbookId, 'docx')}
                  download
                  className="cursor-pointer"
                >
                  Exportar como DOCX
                </a>
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
          <Button
            variant="outline"
            size="sm"
            className={cn(
              'gap-1.5',
              activeTab === 'versions' && 'bg-indigo-50 border-indigo-300 text-indigo-700 dark:bg-indigo-900/20 dark:border-indigo-700 dark:text-indigo-400'
            )}
            onClick={() => setActiveTab(activeTab === 'versions' ? 'rules' : 'versions')}
          >
            <History className="h-3.5 w-3.5" />
            {activeTab === 'versions' ? 'Voltar as Regras' : 'Historico'}
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="gap-1.5"
            onClick={() => router.push(`/playbooks/${playbookId}/analyze`)}
          >
            <Play className="h-3.5 w-3.5" />
            Analisar Contrato
          </Button>
          <Button
            size="sm"
            className="gap-1.5 bg-indigo-600 hover:bg-indigo-500 text-white"
            onClick={() => setShowRuleForm(true)}
          >
            <Plus className="h-3.5 w-3.5" />
            Nova Regra
          </Button>
        </div>
      </div>

      <div className={cn('grid gap-6', showMetadata ? 'lg:grid-cols-[300px_1fr]' : '')}>
        {/* Left panel: Metadata */}
        {showMetadata && (
          <div className="space-y-4 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-5">
            <h3 className="text-sm font-semibold text-slate-600 dark:text-slate-300 flex items-center gap-2">
              <FileText className="h-4 w-4" />
              Metadados
            </h3>

            <div className="space-y-3">
              <div className="space-y-1.5">
                <Label className="text-xs">Nome</Label>
                <Input
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  className="h-8 text-sm"
                />
              </div>

              <div className="space-y-1.5">
                <Label className="text-xs">Descricao</Label>
                <Textarea
                  value={editDescription}
                  onChange={(e) => setEditDescription(e.target.value)}
                  rows={3}
                  className="text-sm"
                />
              </div>

              <div className="space-y-1.5">
                <Label className="text-xs">Area</Label>
                <Select value={editArea} onValueChange={(v) => setEditArea(v as PlaybookArea)}>
                  <SelectTrigger className="h-8 text-sm">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {(Object.entries(AREA_LABELS) as [PlaybookArea, string][]).map(([key, label]) => (
                      <SelectItem key={key} value={key}>
                        {label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-1.5">
                <Label className="text-xs">Escopo</Label>
                <Input
                  value={editScope}
                  onChange={(e) => setEditScope(e.target.value)}
                  className="h-8 text-sm"
                  placeholder="Ex: Contratos SaaS"
                />
              </div>

              <div className="space-y-1.5">
                <Label className="text-xs">Status</Label>
                <Select value={editStatus} onValueChange={(v) => setEditStatus(v as PlaybookStatus)}>
                  <SelectTrigger className="h-8 text-sm">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="rascunho">Rascunho</SelectItem>
                    <SelectItem value="ativo">Ativo</SelectItem>
                    <SelectItem value="arquivado">Arquivado</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <Button
                size="sm"
                className="w-full gap-1.5 mt-2"
                onClick={handleSaveMetadata}
                disabled={updatePlaybook.isPending || !editName.trim()}
              >
                {updatePlaybook.isPending ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Save className="h-3.5 w-3.5" />
                )}
                Salvar Metadados
              </Button>
            </div>
          </div>
        )}

        {/* Right panel: Rules or Version History */}
        <div className="space-y-3">
          {activeTab === 'rules' ? (
            <>
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold text-slate-600 dark:text-slate-300">
                  Regras de Revisao ({sortedRules.length})
                </h3>
              </div>

              {sortedRules.length === 0 ? (
                <div className="rounded-xl border border-dashed border-slate-200 dark:border-slate-700 p-12 text-center">
                  <BookCheck className="h-10 w-10 text-slate-300 mx-auto mb-3" />
                  <p className="text-sm text-slate-500 dark:text-slate-400 mb-3">
                    Nenhuma regra adicionada ainda
                  </p>
                  <p className="text-xs text-slate-400 mb-4 max-w-sm mx-auto">
                    Adicione regras com posicoes preferidas, alternativas e criterios de rejeicao
                    para cada tipo de clausula que deseja revisar.
                  </p>
                  <Button
                    onClick={() => setShowRuleForm(true)}
                    className="gap-2 bg-indigo-600 hover:bg-indigo-500 text-white"
                  >
                    <Plus className="h-4 w-4" />
                    Adicionar Primeira Regra
                  </Button>
                </div>
              ) : (
                <div className="space-y-2">
                  {sortedRules.map((rule) => (
                    <PlaybookRuleEditor
                      key={rule.id}
                      rule={rule}
                      onUpdate={handleUpdateRule}
                      onDelete={handleDeleteRule}
                    />
                  ))}
                </div>
              )}
            </>
          ) : (
            <>
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold text-slate-600 dark:text-slate-300 flex items-center gap-2">
                  <History className="h-4 w-4" />
                  Historico de Versoes
                </h3>
              </div>
              <PlaybookVersionTimeline playbookId={playbookId} />
            </>
          )}
        </div>
      </div>

      {/* Rule form dialog */}
      <PlaybookRuleForm
        open={showRuleForm}
        onOpenChange={setShowRuleForm}
        playbookId={playbookId}
        onSubmit={handleCreateRule}
      />
    </div>
  );
}
