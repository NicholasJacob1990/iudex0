'use client';

import { useEffect, useState } from 'react';
import {
  FileText,
  Upload,
  Trash2,
  RefreshCw,
  Search,
  Filter,
  CheckCircle2,
  Clock,
  AlertCircle,
  Loader2,
  FolderOpen,
  Plus,
  Database,
  BookOpen,
  ChevronRight,
  Home,
  Copy,
  AlertTriangle,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
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
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';
import {
  useCorpusDocuments,
  useDeleteCorpusDocument,
  useCorpusProjects,
  useCreateCorpusProject,
  useDeleteCorpusProject as useDeleteCorpusProjectMutation,
  useProjectFolders,
  useCreateProjectFolder,
  useMoveProjectDocument,
  useCheckDuplicates,
  useRemoveDocumentFromProject,
} from '../hooks/use-corpus';
import type {
  CorpusDocument,
  CorpusDocumentStatus,
  CorpusDocumentFilters,
  CorpusProject,
  CreateCorpusProjectPayload,
  DuplicatePair,
} from '../hooks/use-corpus';
import { formatDate, formatFileSize } from '@/lib/utils';
import { toast } from 'sonner';
import { CorpusUploadDialog } from './corpus-upload-dialog';
import { CorpusFolderTree } from './corpus-folder-tree';
import { CorpusDocumentViews } from './corpus-document-views';
import { CorpusViewControls, usePersistedViewPreferences } from './corpus-view-controls';
import type { CorpusViewMode, CorpusSortOption } from './corpus-view-controls';
import { CorpusExportButton } from './corpus-export-button';
import { useAuthStore } from '@/stores/auth-store';
import apiClient from '@/lib/api-client';

const statusConfig: Record<CorpusDocumentStatus, { label: string; icon: React.ComponentType<{ className?: string }>; color: string }> = {
  ingested: { label: 'Indexado', icon: CheckCircle2, color: 'bg-emerald-100 text-emerald-700' },
  pending: { label: 'Pendente', icon: Clock, color: 'bg-amber-100 text-amber-700' },
  processing: { label: 'Processando', icon: Loader2, color: 'bg-blue-100 text-blue-700' },
  failed: { label: 'Falhou', icon: AlertCircle, color: 'bg-red-100 text-red-700' },
};

type OrgTeam = { id: string; name: string };

// =============================================================================
// Create Project Dialog
// =============================================================================

function CreateProjectDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [isKnowledgeBase, setIsKnowledgeBase] = useState(false);
  const [projectScope, setProjectScope] = useState<string>('personal');

  const createProject = useCreateCorpusProject();

  const handleCreate = async () => {
    if (!name.trim()) {
      toast.error('Informe o nome do projeto.');
      return;
    }

    try {
      await createProject.mutateAsync({
        name: name.trim(),
        description: description.trim() || undefined,
        is_knowledge_base: isKnowledgeBase,
        scope: projectScope,
      });
      toast.success(`Projeto "${name}" criado com sucesso.`);
      onOpenChange(false);
      setName('');
      setDescription('');
      setIsKnowledgeBase(false);
      setProjectScope('personal');
    } catch {
      toast.error('Erro ao criar projeto.');
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[425px]">
        <DialogHeader>
          <DialogTitle>Novo Projeto de Corpus</DialogTitle>
          <DialogDescription>
            Crie um projeto para organizar documentos. Marque como Knowledge Base para disponibilizar para toda a equipe.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <Label htmlFor="project-name">Nome</Label>
            <Input
              id="project-name"
              placeholder="Ex: Contratos de TI 2026"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="rounded-xl"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="project-desc">Descricao (opcional)</Label>
            <Textarea
              id="project-desc"
              placeholder="Descricao do projeto..."
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="rounded-xl resize-none"
              rows={3}
            />
          </div>
          <div className="space-y-2">
            <Label>Escopo</Label>
            <Select value={projectScope} onValueChange={setProjectScope}>
              <SelectTrigger className="rounded-xl">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="personal">Pessoal</SelectItem>
                <SelectItem value="organization">Organizacao</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label htmlFor="kb-toggle">Knowledge Base</Label>
              <p className="text-[10px] text-muted-foreground">
                Disponibilizar para consulta de toda a equipe
              </p>
            </div>
            <Switch
              id="kb-toggle"
              checked={isKnowledgeBase}
              onCheckedChange={setIsKnowledgeBase}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} className="rounded-full">
            Cancelar
          </Button>
          <Button
            onClick={handleCreate}
            disabled={createProject.isPending || !name.trim()}
            className="rounded-full gap-2"
          >
            {createProject.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            Criar Projeto
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}


// =============================================================================
// Duplicates Dialog
// =============================================================================

function DuplicatesDialog({
  open,
  onOpenChange,
  projectId,
  projectName,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  projectId: string;
  projectName: string;
}) {
  const checkDuplicates = useCheckDuplicates();
  const removeDocument = useRemoveDocumentFromProject();
  const [duplicates, setDuplicates] = useState<DuplicatePair[]>([]);
  const [checked, setChecked] = useState(false);

  const handleCheck = async () => {
    try {
      const result = await checkDuplicates.mutateAsync({ projectId, threshold: 0.8 });
      setDuplicates(result.duplicates);
      setChecked(true);
      if (result.duplicates.length === 0) {
        toast.success('Nenhum documento duplicado encontrado.');
      }
    } catch {
      toast.error('Erro ao verificar duplicatas.');
    }
  };

  const [pendingRemove, setPendingRemove] = useState<{ documentId: string; documentName: string } | null>(null);

  const handleRemove = (documentId: string, documentName: string) => {
    setPendingRemove({ documentId, documentName });
  };

  const handleConfirmRemove = async () => {
    if (!pendingRemove) return;
    const { documentId, documentName } = pendingRemove;
    setPendingRemove(null);
    try {
      await removeDocument.mutateAsync({ projectId, documentId });
      setDuplicates((prev) =>
        prev.filter((d) => d.document_id_1 !== documentId && d.document_id_2 !== documentId)
      );
      toast.success(`"${documentName}" removido.`);
    } catch {
      toast.error('Erro ao remover documento.');
    }
  };

  return (
    <Dialog open={open} onOpenChange={(v) => { onOpenChange(v); if (!v) { setDuplicates([]); setChecked(false); } }}>
      <DialogContent className="sm:max-w-[600px] max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Copy className="h-5 w-5 text-amber-600" />
            Verificar Duplicatas
          </DialogTitle>
          <DialogDescription>
            Verificar documentos duplicados ou muito similares no projeto &quot;{projectName}&quot;.
          </DialogDescription>
        </DialogHeader>

        {!checked ? (
          <div className="flex flex-col items-center justify-center py-8 gap-4">
            <AlertTriangle className="h-12 w-12 text-amber-400" />
            <p className="text-sm text-muted-foreground text-center">
              A verificacao compara nomes e conteudos (hash) dos documentos do projeto para identificar duplicatas.
            </p>
            <Button
              onClick={handleCheck}
              disabled={checkDuplicates.isPending}
              className="rounded-full gap-2"
            >
              {checkDuplicates.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Search className="h-4 w-4" />
              )}
              Verificar agora
            </Button>
          </div>
        ) : duplicates.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-8 gap-3">
            <CheckCircle2 className="h-12 w-12 text-emerald-500" />
            <p className="text-sm font-medium text-foreground">Nenhuma duplicata encontrada</p>
            <p className="text-xs text-muted-foreground">Todos os documentos sao unicos.</p>
          </div>
        ) : (
          <div className="space-y-3">
            <p className="text-sm font-medium text-foreground">
              {duplicates.length} par(es) de duplicatas encontrado(s)
            </p>
            {duplicates.map((pair, idx) => (
              <div key={idx} className="rounded-xl border border-amber-200 bg-amber-50 p-4 space-y-2">
                <div className="flex items-center justify-between">
                  <Badge className="rounded-full text-[10px] bg-amber-200 text-amber-800 border-0">
                    {pair.match_type === 'exact_hash' ? 'Hash identico' : `${Math.round(pair.similarity * 100)}% similar`}
                  </Badge>
                </div>
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm text-foreground truncate flex-1">{pair.document_name_1}</span>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 rounded-full text-xs text-destructive hover:text-destructive shrink-0"
                      onClick={() => handleRemove(pair.document_id_1, pair.document_name_1)}
                      disabled={removeDocument.isPending}
                    >
                      <Trash2 className="h-3.5 w-3.5 mr-1" />
                      Remover
                    </Button>
                  </div>
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm text-foreground truncate flex-1">{pair.document_name_2}</span>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 rounded-full text-xs text-destructive hover:text-destructive shrink-0"
                      onClick={() => handleRemove(pair.document_id_2, pair.document_name_2)}
                      disabled={removeDocument.isPending}
                    >
                      <Trash2 className="h-3.5 w-3.5 mr-1" />
                      Remover
                    </Button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} className="rounded-full">
            Fechar
          </Button>
        </DialogFooter>

        <AlertDialog open={!!pendingRemove} onOpenChange={(v) => { if (!v) setPendingRemove(null); }}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Remover documento</AlertDialogTitle>
              <AlertDialogDescription>
                Deseja remover &quot;{pendingRemove?.documentName}&quot; do projeto?
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel className="rounded-full">Cancelar</AlertDialogCancel>
              <AlertDialogAction onClick={handleConfirmRemove} className="rounded-full bg-destructive text-destructive-foreground hover:bg-destructive/90">
                Remover
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </DialogContent>
    </Dialog>
  );
}


// =============================================================================
// Project Card (with folder support)
// =============================================================================

function ProjectCard({
  project,
  isSelected,
  onSelect,
  onDelete,
  onCheckDuplicates,
}: {
  project: CorpusProject;
  isSelected: boolean;
  onSelect: (id: string) => void;
  onDelete: (id: string, name: string) => void;
  onCheckDuplicates: (project: CorpusProject) => void;
}) {
  return (
    <div
      className={`group relative rounded-2xl border p-4 shadow-soft hover:shadow-md transition-all cursor-pointer ${
        isSelected
          ? 'border-primary/50 bg-primary/5'
          : 'border-white/70 bg-white/95'
      }`}
      onClick={() => onSelect(project.id)}
    >
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10">
            {project.is_knowledge_base ? (
              <BookOpen className="h-5 w-5 text-primary" />
            ) : (
              <FolderOpen className="h-5 w-5 text-primary" />
            )}
          </div>
          <div>
            <h3 className="text-sm font-semibold text-foreground">{project.name}</h3>
            {project.description && (
              <p className="text-[10px] text-muted-foreground line-clamp-1 mt-0.5">
                {project.description}
              </p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7 rounded-full text-amber-600 hover:text-amber-700"
            onClick={(e) => {
              e.stopPropagation();
              onCheckDuplicates(project);
            }}
            title="Verificar duplicatas"
          >
            <Copy className="h-3.5 w-3.5" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7 rounded-full text-destructive"
            onClick={(e) => {
              e.stopPropagation();
              onDelete(project.id, project.name);
            }}
            title="Excluir projeto"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>
      <div className="mt-3 flex items-center gap-2 flex-wrap">
        <Badge variant="outline" className="rounded-full text-[10px] gap-1">
          <Database className="h-3 w-3" />
          {project.document_count} docs
        </Badge>
        {project.is_knowledge_base && (
          <Badge className="rounded-full text-[10px] bg-violet-100 text-violet-700 border-0">
            Knowledge Base
          </Badge>
        )}
        <Badge variant="outline" className="rounded-full text-[10px]">
          {project.scope === 'organization' ? 'Org' : 'Pessoal'}
        </Badge>
      </div>
    </div>
  );
}


// =============================================================================
// Breadcrumb
// =============================================================================

function FolderBreadcrumb({
  folderPath,
  onNavigate,
}: {
  folderPath: string | null;
  onNavigate: (path: string | null) => void;
}) {
  if (!folderPath) return null;

  const parts = folderPath.split('/');

  return (
    <div className="flex items-center gap-1 text-sm overflow-x-auto">
      <button
        className="text-muted-foreground hover:text-primary transition-colors shrink-0"
        onClick={() => onNavigate(null)}
      >
        <Home className="h-4 w-4" />
      </button>
      {parts.map((part, index) => {
        const path = parts.slice(0, index + 1).join('/');
        const isLast = index === parts.length - 1;
        return (
          <span key={path} className="flex items-center gap-1 shrink-0">
            <ChevronRight className="h-3 w-3 text-muted-foreground" />
            <button
              className={`whitespace-nowrap ${
                isLast
                  ? 'font-medium text-foreground'
                  : 'text-muted-foreground hover:text-primary transition-colors'
              }`}
              onClick={() => onNavigate(path)}
            >
              {part}
            </button>
          </span>
        );
      })}
    </div>
  );
}


// =============================================================================
// Main Component
// =============================================================================

export function CorpusPrivateTab() {
  const { user } = useAuthStore();
  const [filters, setFilters] = useState<CorpusDocumentFilters>({
    scope: 'private',
    page: 1,
    per_page: 15,
  });
  const [accessFilter, setAccessFilter] = useState<string>('org');
  const [myTeams, setMyTeams] = useState<OrgTeam[]>([]);
  const [teamsLoading, setTeamsLoading] = useState(false);
  const [searchInput, setSearchInput] = useState('');
  const [uploadOpen, setUploadOpen] = useState(false);
  const [createProjectOpen, setCreateProjectOpen] = useState(false);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [selectedFolderPath, setSelectedFolderPath] = useState<string | null>(null);
  const [duplicatesProject, setDuplicatesProject] = useState<CorpusProject | null>(null);

  // Confirm delete dialog state
  const [confirmDelete, setConfirmDelete] = useState<{ id: string; name: string; type: 'document' | 'project' } | null>(null);

  // Move document dialog state
  const [moveDialog, setMoveDialog] = useState<{ docId: string; docName: string } | null>(null);
  const [moveTargetPath, setMoveTargetPath] = useState('');

  // Confirm remove duplicate dialog state
  const [confirmRemoveDuplicate, setConfirmRemoveDuplicate] = useState<{ documentId: string; documentName: string } | null>(null);

  // View preferences (persisted in localStorage)
  const { viewMode, setViewMode, sortOption, setSortOption } = usePersistedViewPreferences();

  const { data, isLoading } = useCorpusDocuments(filters);
  const { data: projectsData, isLoading: projectsLoading } = useCorpusProjects({ per_page: 50 });
  const deleteDocument = useDeleteCorpusDocument();
  const deleteProjectMutation = useDeleteCorpusProjectMutation();

  useEffect(() => {
    if (!user?.organization_id) {
      setMyTeams([]);
      return;
    }
    setTeamsLoading(true);
    apiClient
      .getMyOrgTeams()
      .then((res) => {
        const list = Array.isArray(res) ? res : [];
        setMyTeams(
          list
            .map((t: any) => ({ id: String(t?.id || '').trim(), name: String(t?.name || '').trim() }))
            .filter((t: OrgTeam) => t.id && t.name)
        );
      })
      .catch(() => setMyTeams([]))
      .finally(() => setTeamsLoading(false));
  }, [user?.organization_id]);

  // Folder hooks (only active when a project is selected)
  const { data: folderData } = useProjectFolders(selectedProjectId || '');
  const createFolder = useCreateProjectFolder();
  const moveDocument = useMoveProjectDocument();

  const handleSearch = () => {
    setFilters((prev) => ({
      ...prev,
      search: searchInput.trim() || undefined,
      page: 1,
    }));
  };

  const handleStatusFilter = (status: string) => {
    setFilters((prev) => ({
      ...prev,
      status: status === 'all' ? undefined : status as CorpusDocumentStatus,
      page: 1,
    }));
  };

  const handleCollectionFilter = (collection: string) => {
    setFilters((prev) => ({
      ...prev,
      collection: collection === 'all' ? undefined : collection,
      page: 1,
    }));
  };

  const handleAccessFilter = (value: string) => {
    setAccessFilter(value);
    setFilters((prev) => {
      if (value === 'org') {
        return { ...prev, scope: 'private', group_id: undefined, page: 1 };
      }
      if (value === 'group_all') {
        return { ...prev, scope: 'group', group_id: undefined, page: 1 };
      }
      return { ...prev, scope: 'group', group_id: value, page: 1 };
    });
  };

  const handleDelete = (id: string, name: string) => {
    setConfirmDelete({ id, name, type: 'document' });
  };

  const handleConfirmDelete = async () => {
    if (!confirmDelete) return;
    const { id, name, type } = confirmDelete;
    setConfirmDelete(null);

    if (type === 'document') {
      try {
        await deleteDocument.mutateAsync(id);
        toast.success(`"${name}" removido do corpus.`);
      } catch {
        toast.error('Erro ao remover documento.');
      }
    } else {
      try {
        await deleteProjectMutation.mutateAsync(id);
        toast.success(`Projeto "${name}" excluido.`);
        if (selectedProjectId === id) {
          setSelectedProjectId(null);
          setSelectedFolderPath(null);
        }
      } catch {
        toast.error('Erro ao excluir projeto.');
      }
    }
  };

  const handleDeleteProject = (id: string, name: string) => {
    setConfirmDelete({ id, name, type: 'project' });
  };

  const handleReindex = (id: string, name: string) => {
    toast.info(`Reindexando "${name}"...`);
    // TODO: Implementar chamada de reindexacao
  };

  const handleSelectProject = (projectId: string) => {
    if (selectedProjectId === projectId) {
      setSelectedProjectId(null);
      setSelectedFolderPath(null);
    } else {
      setSelectedProjectId(projectId);
      setSelectedFolderPath(null);
    }
  };

  const handleCreateFolder = async (folderPath: string) => {
    if (!selectedProjectId) return;
    try {
      await createFolder.mutateAsync({
        projectId: selectedProjectId,
        folderPath,
      });
      toast.success(`Pasta "${folderPath}" criada.`);
    } catch {
      toast.error('Erro ao criar pasta.');
    }
  };

  const handleMoveDocument = (docId: string, docName: string) => {
    setMoveDialog({ docId, docName });
    setMoveTargetPath('');
  };

  const handleConfirmMove = () => {
    if (!moveDialog || !selectedProjectId) return;
    const { docId, docName } = moveDialog;
    setMoveDialog(null);

    moveDocument.mutate(
      {
        projectId: selectedProjectId,
        documentId: docId,
        folderPath: moveTargetPath.trim() || null,
      },
      {
        onSuccess: () => toast.success(`"${docName}" movido com sucesso.`),
        onError: () => toast.error('Erro ao mover documento.'),
      }
    );
  };

  // Sort documents based on current sort option
  const sortDocuments = (docs: CorpusDocument[]) => {
    if (!docs) return [];
    const sorted = [...docs];
    switch (sortOption) {
      case 'oldest':
        sorted.sort((a, b) => {
          const da = a.ingested_at || '';
          const db_ = b.ingested_at || '';
          return da.localeCompare(db_);
        });
        break;
      case 'alpha':
        sorted.sort((a, b) => a.name.localeCompare(b.name));
        break;
      case 'recent':
      default:
        sorted.sort((a, b) => {
          const da = a.ingested_at || '';
          const db_ = b.ingested_at || '';
          return db_.localeCompare(da);
        });
        break;
    }
    return sorted;
  };

  const sortedDocuments = data?.items ? sortDocuments(data.items) : [];

  return (
    <div className="space-y-6">
      {/* Projects Section */}
      <div className="rounded-2xl border border-white/70 bg-white/95 p-4 shadow-soft">
        <div className="flex items-center justify-between mb-4">
          <div>
            <p className="text-sm font-medium text-foreground">Projetos</p>
            <p className="text-xs text-muted-foreground">
              Organize documentos em projetos. Clique para ver pastas e documentos.
            </p>
          </div>
          <Button
            className="rounded-full bg-primary text-primary-foreground gap-2"
            size="sm"
            onClick={() => setCreateProjectOpen(true)}
          >
            <Plus className="h-4 w-4" />
            Criar Projeto
          </Button>
        </div>

        {projectsLoading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-24 rounded-2xl" />
            ))}
          </div>
        ) : !projectsData?.items.length ? (
          <div className="flex flex-col items-center justify-center py-8 text-center">
            <FolderOpen className="h-10 w-10 text-muted-foreground/30 mb-3" />
            <p className="text-sm text-muted-foreground">Nenhum projeto ainda</p>
            <p className="text-xs text-muted-foreground mt-1">
              Crie um projeto para organizar seus documentos de corpus.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {projectsData.items.filter((project) =>
              !searchInput.trim() ||
              project.name.toLowerCase().includes(searchInput.trim().toLowerCase())
            ).map((project) => (
              <ProjectCard
                key={project.id}
                project={project}
                isSelected={selectedProjectId === project.id}
                onSelect={handleSelectProject}
                onDelete={handleDeleteProject}
                onCheckDuplicates={setDuplicatesProject}
              />
            ))}
          </div>
        )}
      </div>

      <CreateProjectDialog open={createProjectOpen} onOpenChange={setCreateProjectOpen} />

      {duplicatesProject && (
        <DuplicatesDialog
          open={!!duplicatesProject}
          onOpenChange={(v) => { if (!v) setDuplicatesProject(null); }}
          projectId={duplicatesProject.id}
          projectName={duplicatesProject.name}
        />
      )}

      {/* Folder sidebar + document area when project is selected */}
      {selectedProjectId && (
        <div className="flex gap-4">
          {/* Folder Tree Sidebar */}
          <div className="w-64 shrink-0 rounded-2xl border border-white/70 bg-white/95 shadow-soft overflow-hidden hidden md:block">
            <CorpusFolderTree
              folders={folderData?.folders || []}
              selectedPath={selectedFolderPath}
              onSelectFolder={setSelectedFolderPath}
              onCreateFolder={handleCreateFolder}
              rootDocumentCount={
                projectsData?.items.find((p) => p.id === selectedProjectId)?.document_count ?? 0
              }
            />
          </div>

          {/* Breadcrumb for mobile (instead of sidebar) */}
          <div className="flex-1 min-w-0 space-y-3">
            {selectedFolderPath && (
              <div className="rounded-xl border border-white/70 bg-white/95 px-4 py-2 shadow-soft">
                <FolderBreadcrumb
                  folderPath={selectedFolderPath}
                  onNavigate={setSelectedFolderPath}
                />
              </div>
            )}

            <div className="text-xs text-muted-foreground">
              Projeto selecionado — documentos filtrados pela pasta
            </div>
          </div>
        </div>
      )}

      {/* Actions Bar with View Controls */}
      <div className="rounded-2xl border border-white/70 bg-white/95 p-4 shadow-soft">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <p className="text-sm font-medium text-foreground">Documentos do escritorio</p>
            <p className="text-xs text-muted-foreground">
              Gerencie os documentos enviados pela sua organizacao. Administradores podem enviar, excluir e reindexar.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <CorpusViewControls
              viewMode={viewMode}
              onViewModeChange={setViewMode}
              sortOption={sortOption}
              onSortChange={setSortOption}
            />
            <CorpusExportButton
              filters={{
                scope: filters.scope,
                group_id: filters.group_id,
                collection: filters.collection,
                search: filters.search,
                status: filters.status,
              }}
            />
            <Button
              className="rounded-full bg-primary text-primary-foreground gap-2"
              onClick={() => setUploadOpen(true)}
            >
              <Upload className="h-4 w-4" />
              Enviar documento
            </Button>
          </div>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Buscar por nome do documento..."
            className="rounded-xl pl-9"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
          />
        </div>
        <div className="flex items-center gap-2">
          <Filter className="h-4 w-4 text-muted-foreground" />
          {user?.organization_id && (
            <Select onValueChange={handleAccessFilter} value={accessFilter}>
              <SelectTrigger className="w-[190px] rounded-xl">
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
          <Select onValueChange={handleStatusFilter} defaultValue="all">
            <SelectTrigger className="w-[140px] rounded-xl">
              <SelectValue placeholder="Status" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Todos</SelectItem>
              <SelectItem value="ingested">Indexado</SelectItem>
              <SelectItem value="pending">Pendente</SelectItem>
              <SelectItem value="processing">Processando</SelectItem>
              <SelectItem value="failed">Falhou</SelectItem>
            </SelectContent>
          </Select>
          <Select onValueChange={handleCollectionFilter} defaultValue="all">
            <SelectTrigger className="w-[160px] rounded-xl">
              <SelectValue placeholder="Colecao" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Todas</SelectItem>
              <SelectItem value="lei">Legislacao</SelectItem>
              <SelectItem value="jurisprudencia">Jurisprudencia</SelectItem>
              <SelectItem value="doutrina">Doutrina</SelectItem>
              <SelectItem value="pecas_modelo">Pecas Modelo</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* Documents — using multi-view component */}
      <CorpusDocumentViews
        documents={sortedDocuments}
        viewMode={viewMode}
        isLoading={isLoading}
        onDelete={handleDelete}
        onReindex={handleReindex}
        onMove={selectedProjectId ? handleMoveDocument : undefined}
      />

      {/* Pagination */}
      {data && (() => {
        const totalPages = Math.ceil(data.total / data.per_page);
        return totalPages > 1 ? (
          <div className="flex items-center justify-between rounded-2xl border border-white/70 bg-white/95 px-5 py-3 shadow-soft">
            <p className="text-xs text-muted-foreground">
              Mostrando {data.items.length} de {data.total} documentos
            </p>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                className="rounded-full text-xs"
                disabled={data.page <= 1}
                onClick={() => setFilters((prev) => ({ ...prev, page: (prev.page || 1) - 1 }))}
              >
                Anterior
              </Button>
              <span className="text-xs text-muted-foreground">
                {data.page} de {totalPages}
              </span>
              <Button
                variant="outline"
                size="sm"
                className="rounded-full text-xs"
                disabled={data.page >= totalPages}
                onClick={() => setFilters((prev) => ({ ...prev, page: (prev.page || 1) + 1 }))}
              >
                Proximo
              </Button>
            </div>
          </div>
        ) : null;
      })()}

      <CorpusUploadDialog
        open={uploadOpen}
        onOpenChange={setUploadOpen}
        defaultScope="private"
      />

      {/* Confirm delete AlertDialog */}
      <AlertDialog open={!!confirmDelete} onOpenChange={(v) => { if (!v) setConfirmDelete(null); }}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {confirmDelete?.type === 'project' ? 'Excluir projeto' : 'Excluir documento'}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {confirmDelete?.type === 'project'
                ? `Deseja realmente excluir o projeto "${confirmDelete?.name}"?`
                : `Deseja realmente excluir "${confirmDelete?.name}" do corpus?`}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel className="rounded-full">Cancelar</AlertDialogCancel>
            <AlertDialogAction onClick={handleConfirmDelete} className="rounded-full bg-destructive text-destructive-foreground hover:bg-destructive/90">
              Excluir
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Move document Dialog */}
      <Dialog open={!!moveDialog} onOpenChange={(v) => { if (!v) setMoveDialog(null); }}>
        <DialogContent className="sm:max-w-[425px]">
          <DialogHeader>
            <DialogTitle>Mover documento</DialogTitle>
            <DialogDescription>
              Mover &quot;{moveDialog?.docName}&quot; para qual pasta? Deixe vazio para a raiz.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2 py-4">
            <Label htmlFor="move-path">Caminho da pasta</Label>
            <Input
              id="move-path"
              placeholder='Ex: Contratos/2026'
              value={moveTargetPath}
              onChange={(e) => setMoveTargetPath(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleConfirmMove()}
              className="rounded-xl"
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setMoveDialog(null)} className="rounded-full">
              Cancelar
            </Button>
            <Button onClick={handleConfirmMove} className="rounded-full">
              Mover
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
