'use client';

import { useState, useCallback } from 'react';
import {
  Plus,
  BookCheck,
  Loader2,
  Search,
  Sparkles,
  LayoutGrid,
  List,
  Filter,
  Trophy,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { AnimatedContainer } from '@/components/ui/animated-container';
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
import { useRouter } from 'next/navigation';
import { PlaybookCard } from './components/playbook-card';
import { CreatePlaybookDialog } from './components/create-playbook-dialog';
import { PlaybookShareDialog, type ShareSettings } from './components/playbook-share-dialog';
import { GenerateFromContracts } from './components/generate-from-contracts';
import { ImportFromDocument } from './components/import-from-document';
import { ExtractWinningLanguage } from './components/extract-winning-language';
import {
  type Playbook,
  type PlaybookArea,
  type PlaybookStatus,
  AREA_LABELS,
  usePlaybooks,
  useCreatePlaybook,
  useDeletePlaybook,
  useUpdatePlaybook,
} from './hooks';

export default function PlaybooksPage() {
  const router = useRouter();
  const [search, setSearch] = useState('');
  const [areaFilter, setAreaFilter] = useState<PlaybookArea | 'all'>('all');
  const [statusFilter, setStatusFilter] = useState<PlaybookStatus | 'all'>('all');
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid');
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [generateDialogOpen, setGenerateDialogOpen] = useState(false);
  const [importDocumentDialogOpen, setImportDocumentDialogOpen] = useState(false);
  const [winningLanguageDialogOpen, setWinningLanguageDialogOpen] = useState(false);
  const [shareDialogOpen, setShareDialogOpen] = useState(false);
  const [selectedPlaybook, setSelectedPlaybook] = useState<Playbook | null>(null);
  const [activeTab, setActiveTab] = useState('my');
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);

  const filters = {
    area: areaFilter !== 'all' ? areaFilter : undefined,
    status: statusFilter !== 'all' ? statusFilter : undefined,
    search: search || undefined,
  };

  const { data: playbooks, isLoading } = usePlaybooks(filters);
  const createMutation = useCreatePlaybook();
  const deleteMutation = useDeletePlaybook();
  const updateMutation = useUpdatePlaybook();

  const handleCreateFromScratch = async (data: {
    name: string;
    description: string;
    area: PlaybookArea;
    scope: string;
  }) => {
    const result = await createMutation.mutateAsync(data);
    router.push(`/playbooks/${result.id}`);
  };

  const handleCreateFromTemplate = async (templateId: string, data: { name: string; area: PlaybookArea }) => {
    const result = await createMutation.mutateAsync({
      ...data,
      from_template_id: templateId,
    });
    router.push(`/playbooks/${result.id}`);
  };

  const handleDelete = useCallback((id: string) => {
    setDeleteConfirmId(id);
  }, []);

  const handleConfirmDelete = useCallback(async () => {
    if (!deleteConfirmId) return;
    await deleteMutation.mutateAsync(deleteConfirmId);
    setDeleteConfirmId(null);
  }, [deleteConfirmId, deleteMutation]);

  const handleDuplicate = async (playbook: Playbook) => {
    const result = await createMutation.mutateAsync({
      name: `${playbook.name} (copia)`,
      description: playbook.description,
      area: playbook.area,
      scope: playbook.scope,
    });
    router.push(`/playbooks/${result.id}`);
  };

  const handleShare = (playbook: Playbook) => {
    setSelectedPlaybook(playbook);
    setShareDialogOpen(true);
  };

  const handleShareSubmit = async (playbookId: string, settings: ShareSettings) => {
    // Update playbook scope and template settings
    const scopeMap: Record<string, string> = {
      private: 'personal',
      org: 'organization',
      public: 'public',
    };
    await updateMutation.mutateAsync({
      id: playbookId,
      scope: scopeMap[settings.shareScope] ?? 'personal',
      is_template: settings.isTemplate,
    });
  };

  const handleGenerateComplete = (playbookId: string) => {
    router.push(`/playbooks/${playbookId}`);
  };

  const handleImportDocumentComplete = (playbookId: string) => {
    router.push(`/playbooks/${playbookId}`);
  };

  const handleWinningLanguageComplete = (playbookId: string) => {
    router.push(`/playbooks/${playbookId}`);
  };

  const myPlaybooks = (playbooks || []).filter((p) => !p.is_template);
  const templatePlaybooks = (playbooks || []).filter((p) => p.is_template);

  return (
    <div className="container mx-auto max-w-6xl space-y-6">
      {/* Header */}
      <AnimatedContainer>
        <div className="flex flex-col gap-4 rounded-3xl border border-white/70 bg-white/95 dark:bg-slate-900/95 dark:border-slate-700 p-6 shadow-soft lg:flex-row lg:items-center lg:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase text-muted-foreground">Playbooks</p>
            <h1 className="font-display text-3xl text-foreground">
              Regras de revisao de contratos.
            </h1>
            <p className="text-sm text-muted-foreground">
              Crie playbooks com posicoes preferidas, alternativas e criterios de rejeicao para revisao automatizada.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              className="rounded-full gap-2"
              onClick={() => setWinningLanguageDialogOpen(true)}
            >
              <Trophy className="h-4 w-4 text-amber-500" />
              Extrair Winning Language
            </Button>
            <Button
              variant="outline"
              className="rounded-full gap-2"
              onClick={() => setGenerateDialogOpen(true)}
            >
              <Sparkles className="h-4 w-4 text-indigo-500" />
              Gerar a partir de Contratos
            </Button>
            <Button
              className="rounded-full bg-indigo-600 hover:bg-indigo-500 text-white gap-2"
              onClick={() => setCreateDialogOpen(true)}
            >
              <Plus className="h-4 w-4" />
              Novo Playbook
            </Button>
          </div>
        </div>
      </AnimatedContainer>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[200px] max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Buscar playbooks..."
            className="pl-9"
          />
        </div>
        <Select
          value={areaFilter}
          onValueChange={(v) => setAreaFilter(v as PlaybookArea | 'all')}
        >
          <SelectTrigger className="w-[180px]">
            <Filter className="h-3.5 w-3.5 mr-2 text-slate-400" />
            <SelectValue placeholder="Area" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Todas as areas</SelectItem>
            {(Object.entries(AREA_LABELS) as [PlaybookArea, string][]).map(([key, label]) => (
              <SelectItem key={key} value={key}>
                {label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select
          value={statusFilter}
          onValueChange={(v) => setStatusFilter(v as PlaybookStatus | 'all')}
        >
          <SelectTrigger className="w-[150px]">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Todos</SelectItem>
            <SelectItem value="ativo">Ativo</SelectItem>
            <SelectItem value="rascunho">Rascunho</SelectItem>
            <SelectItem value="arquivado">Arquivado</SelectItem>
          </SelectContent>
        </Select>
        <div className="flex rounded-lg border border-slate-200 dark:border-slate-700 overflow-hidden ml-auto">
          <button
            onClick={() => setViewMode('grid')}
            className={`p-2 transition-colors ${
              viewMode === 'grid'
                ? 'bg-indigo-50 text-indigo-600 dark:bg-indigo-500/20 dark:text-indigo-400'
                : 'text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800'
            }`}
          >
            <LayoutGrid className="h-4 w-4" />
          </button>
          <button
            onClick={() => setViewMode('list')}
            className={`p-2 transition-colors ${
              viewMode === 'list'
                ? 'bg-indigo-50 text-indigo-600 dark:bg-indigo-500/20 dark:text-indigo-400'
                : 'text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800'
            }`}
          >
            <List className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="my" className="gap-1.5">
            <BookCheck className="h-3.5 w-3.5" />
            Meus Playbooks
            {myPlaybooks.length > 0 && (
              <Badge variant="secondary" className="text-[10px] h-5 px-1.5">
                {myPlaybooks.length}
              </Badge>
            )}
          </TabsTrigger>
          <TabsTrigger value="templates" className="gap-1.5">
            Templates
            {templatePlaybooks.length > 0 && (
              <Badge variant="secondary" className="text-[10px] h-5 px-1.5">
                {templatePlaybooks.length}
              </Badge>
            )}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="my" className="mt-4">
          {isLoading ? (
            <div className="flex items-center justify-center py-20">
              <Loader2 className="h-8 w-8 text-indigo-500 animate-spin" />
            </div>
          ) : myPlaybooks.length === 0 ? (
            <div className="text-center py-20">
              <BookCheck className="h-12 w-12 text-slate-300 mx-auto mb-4" />
              <p className="text-slate-500 dark:text-slate-400 mb-2">
                Nenhum playbook criado ainda
              </p>
              <p className="text-xs text-slate-400 mb-4 max-w-md mx-auto">
                Playbooks permitem definir regras de revisao com posicoes preferidas, alternativas e criterios
                de rejeicao para analise automatizada de contratos.
              </p>
              <div className="flex justify-center gap-2">
                <Button
                  variant="outline"
                  className="gap-2"
                  onClick={() => setGenerateDialogOpen(true)}
                >
                  <Sparkles className="h-4 w-4 text-indigo-500" />
                  Gerar com IA
                </Button>
                <Button
                  onClick={() => setCreateDialogOpen(true)}
                  className="gap-2 bg-indigo-600 hover:bg-indigo-500 text-white"
                >
                  <Plus className="h-4 w-4" />
                  Criar Playbook
                </Button>
              </div>
            </div>
          ) : (
            <div
              className={
                viewMode === 'grid'
                  ? 'grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4'
                  : 'space-y-3'
              }
            >
              {myPlaybooks.map((playbook) => (
                <PlaybookCard
                  key={playbook.id}
                  playbook={playbook}
                  onDelete={handleDelete}
                  onDuplicate={handleDuplicate}
                  onShare={handleShare}
                />
              ))}
            </div>
          )}
        </TabsContent>

        <TabsContent value="templates" className="mt-4">
          {isLoading ? (
            <div className="flex items-center justify-center py-20">
              <Loader2 className="h-8 w-8 text-indigo-500 animate-spin" />
            </div>
          ) : templatePlaybooks.length === 0 ? (
            <div className="text-center py-20">
              <BookCheck className="h-12 w-12 text-slate-300 mx-auto mb-4" />
              <p className="text-slate-500 dark:text-slate-400">
                Nenhum template disponivel
              </p>
              <p className="text-xs text-slate-400 mt-1">
                Templates sao playbooks compartilhados que podem ser usados como ponto de partida.
              </p>
            </div>
          ) : (
            <div
              className={
                viewMode === 'grid'
                  ? 'grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4'
                  : 'space-y-3'
              }
            >
              {templatePlaybooks.map((playbook) => (
                <PlaybookCard
                  key={playbook.id}
                  playbook={playbook}
                  onDelete={handleDelete}
                  onDuplicate={handleDuplicate}
                  onShare={handleShare}
                />
              ))}
            </div>
          )}
        </TabsContent>
      </Tabs>

      {/* Dialogs */}
      <CreatePlaybookDialog
        open={createDialogOpen}
        onOpenChange={setCreateDialogOpen}
        onCreateFromScratch={handleCreateFromScratch}
        onCreateFromTemplate={handleCreateFromTemplate}
        onCreateFromContracts={() => {
          setCreateDialogOpen(false);
          setGenerateDialogOpen(true);
        }}
        onImportFromDocument={() => {
          setCreateDialogOpen(false);
          setImportDocumentDialogOpen(true);
        }}
        onExtractWinningLanguage={() => {
          setCreateDialogOpen(false);
          setWinningLanguageDialogOpen(true);
        }}
      />

      <PlaybookShareDialog
        open={shareDialogOpen}
        onOpenChange={setShareDialogOpen}
        playbook={selectedPlaybook}
        onShare={handleShareSubmit}
      />

      <GenerateFromContracts
        open={generateDialogOpen}
        onOpenChange={setGenerateDialogOpen}
        onComplete={handleGenerateComplete}
      />

      <ImportFromDocument
        open={importDocumentDialogOpen}
        onOpenChange={setImportDocumentDialogOpen}
        onComplete={handleImportDocumentComplete}
      />

      <ExtractWinningLanguage
        open={winningLanguageDialogOpen}
        onOpenChange={setWinningLanguageDialogOpen}
        onComplete={handleWinningLanguageComplete}
      />

      <AlertDialog open={!!deleteConfirmId} onOpenChange={(open) => !open && setDeleteConfirmId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Excluir playbook</AlertDialogTitle>
            <AlertDialogDescription>
              Tem certeza que deseja excluir este playbook? Esta acao nao pode ser desfeita.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleConfirmDelete}
              className="bg-red-600 hover:bg-red-500 text-white"
            >
              Excluir
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
