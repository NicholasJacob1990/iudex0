'use client';

import React, { useEffect, useState, useCallback } from 'react';
import { useParams, useRouter } from 'next/navigation';
import {
  ArrowLeft,
  Users,
  Layers,
  Settings,
  Plus,
  Loader2,
  Trash2,
  Mail,
  Copy,
  Check,
  Workflow,
  FileText,
  Play,
  Folder,
  Palette,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import { apiClient } from '@/lib/api-client';
import { toast } from 'sonner';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface SpaceDetail {
  id: string;
  organization_id: string;
  name: string;
  slug: string;
  description: string | null;
  branding: Record<string, string> | null;
  member_count: number;
  resource_count: number;
  created_by: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

interface SpaceMember {
  email: string;
  role: string;
  status: string;
  user_id: string | null;
  user_name: string | null;
  accepted_at: string | null;
  created_at: string;
}

interface SpaceResource {
  id: string;
  space_id: string;
  resource_type: string;
  resource_id: string;
  resource_name: string | null;
  added_by: string | null;
  added_at: string;
}

const RESOURCE_TYPE_ICONS: Record<string, React.ElementType> = {
  workflow: Workflow,
  document: FileText,
  run: Play,
  folder: Folder,
};

const RESOURCE_TYPE_LABELS: Record<string, string> = {
  workflow: 'Workflow',
  document: 'Documento',
  run: 'Execucao',
  folder: 'Pasta',
};

const ROLE_LABELS: Record<string, string> = {
  admin: 'Admin',
  contributor: 'Colaborador',
  viewer: 'Visualizador',
};

const ROLE_COLORS: Record<string, string> = {
  admin: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
  contributor: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400',
  viewer: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function SpaceDetailPage() {
  const params = useParams();
  const router = useRouter();
  const spaceId = params?.id as string;

  const [space, setSpace] = useState<SpaceDetail | null>(null);
  const [members, setMembers] = useState<SpaceMember[]>([]);
  const [resources, setResources] = useState<SpaceResource[]>([]);
  const [loading, setLoading] = useState(true);

  // Invite dialog state
  const [showInvite, setShowInvite] = useState(false);
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteRole, setInviteRole] = useState('viewer');
  const [inviteMessage, setInviteMessage] = useState('');
  const [inviting, setInviting] = useState(false);
  const [lastInviteToken, setLastInviteToken] = useState<string | null>(null);
  const [copiedToken, setCopiedToken] = useState(false);

  // Add resource dialog state
  const [showAddResource, setShowAddResource] = useState(false);
  const [resourceType, setResourceType] = useState('workflow');
  const [resourceId, setResourceId] = useState('');
  const [resourceName, setResourceName] = useState('');
  const [addingResource, setAddingResource] = useState(false);

  // Settings state
  const [editName, setEditName] = useState('');
  const [editDescription, setEditDescription] = useState('');
  const [editColor, setEditColor] = useState('#6366f1');
  const [saving, setSaving] = useState(false);

  const fetchSpace = useCallback(async () => {
    try {
      const data = await apiClient.request(`/spaces/${spaceId}`);
      setSpace(data);
      setEditName(data.name);
      setEditDescription(data.description || '');
      setEditColor(data.branding?.primary_color || '#6366f1');
    } catch {
      toast.error('Erro ao carregar space');
      router.push('/spaces');
    }
  }, [spaceId, router]);

  const fetchMembers = useCallback(async () => {
    try {
      const data = await apiClient.request(`/spaces/${spaceId}/members`);
      setMembers(data);
    } catch {
      // silencioso na primeira carga
    }
  }, [spaceId]);

  const fetchResources = useCallback(async () => {
    try {
      const data = await apiClient.request(`/spaces/${spaceId}/resources`);
      setResources(data);
    } catch {
      // silencioso
    }
  }, [spaceId]);

  useEffect(() => {
    Promise.all([fetchSpace(), fetchMembers(), fetchResources()]).finally(() =>
      setLoading(false)
    );
  }, [fetchSpace, fetchMembers, fetchResources]);

  // Handlers
  const handleInvite = async () => {
    if (!inviteEmail.trim()) return;
    setInviting(true);
    try {
      const result = await apiClient.request(`/spaces/${spaceId}/invite`, {
        method: 'POST',
        body: {
          email: inviteEmail.trim(),
          role: inviteRole,
          message: inviteMessage.trim() || null,
        },
      });
      setLastInviteToken(result.token);
      toast.success(`Convite enviado para ${inviteEmail}`);
      setInviteEmail('');
      setInviteMessage('');
      fetchMembers();
    } catch (err: any) {
      const detail = err?.response?.data?.detail || 'Erro ao enviar convite';
      toast.error(detail);
    } finally {
      setInviting(false);
    }
  };

  const handleCopyInviteLink = () => {
    if (!lastInviteToken) return;
    const link = `${window.location.origin}/spaces/join/${lastInviteToken}`;
    navigator.clipboard.writeText(link);
    setCopiedToken(true);
    setTimeout(() => setCopiedToken(false), 2000);
    toast.success('Link copiado!');
  };

  const handleRemoveMember = async (email: string) => {
    try {
      await apiClient.request(`/spaces/${spaceId}/members/${encodeURIComponent(email)}`, {
        method: 'DELETE',
      });
      setMembers((prev) => prev.filter((m) => m.email !== email));
      toast.success('Membro removido');
    } catch {
      toast.error('Erro ao remover membro');
    }
  };

  const handleAddResource = async () => {
    if (!resourceId.trim()) return;
    setAddingResource(true);
    try {
      const result = await apiClient.request(`/spaces/${spaceId}/resources`, {
        method: 'POST',
        body: {
          resource_type: resourceType,
          resource_id: resourceId.trim(),
          resource_name: resourceName.trim() || null,
        },
      });
      setResources((prev) => [result, ...prev]);
      setShowAddResource(false);
      setResourceId('');
      setResourceName('');
      toast.success('Recurso adicionado');
    } catch (err: any) {
      const detail = err?.response?.data?.detail || 'Erro ao adicionar recurso';
      toast.error(detail);
    } finally {
      setAddingResource(false);
    }
  };

  const handleRemoveResource = async (resId: string) => {
    try {
      await apiClient.request(`/spaces/${spaceId}/resources/${resId}`, {
        method: 'DELETE',
      });
      setResources((prev) => prev.filter((r) => r.id !== resId));
      toast.success('Recurso removido');
    } catch {
      toast.error('Erro ao remover recurso');
    }
  };

  const handleSaveSettings = async () => {
    setSaving(true);
    try {
      const updated = await apiClient.request(`/spaces/${spaceId}`, {
        method: 'PUT',
        body: {
          name: editName.trim(),
          description: editDescription.trim() || null,
          branding: { primary_color: editColor },
        },
      });
      setSpace(updated);
      toast.success('Configuracoes salvas');
    } catch {
      toast.error('Erro ao salvar');
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteSpace = async () => {
    if (!confirm('Deseja realmente desativar este space? Os convites serao revogados.')) return;
    try {
      await apiClient.request(`/spaces/${spaceId}`, { method: 'DELETE' });
      toast.success('Space desativado');
      router.push('/spaces');
    } catch {
      toast.error('Erro ao desativar space');
    }
  };

  if (loading || !space) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-8 w-8 text-indigo-500 animate-spin" />
      </div>
    );
  }

  const primaryColor = space.branding?.primary_color || '#6366f1';

  return (
    <div className="container mx-auto px-6 py-8 max-w-5xl">
      {/* Header */}
      <div className="mb-8">
        <button
          onClick={() => router.push('/spaces')}
          className="flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-700 dark:hover:text-slate-300 mb-4 transition-colors"
        >
          <ArrowLeft className="h-4 w-4" />
          Voltar para Spaces
        </button>
        <div className="flex items-start gap-4">
          <div
            className="h-12 w-12 rounded-xl flex items-center justify-center shrink-0"
            style={{ backgroundColor: primaryColor + '20' }}
          >
            <Users className="h-6 w-6" style={{ color: primaryColor }} />
          </div>
          <div className="flex-1 min-w-0">
            <h1 className="text-2xl font-bold text-slate-900 dark:text-white truncate">
              {space.name}
            </h1>
            {space.description && (
              <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                {space.description}
              </p>
            )}
            <div className="flex items-center gap-4 mt-2 text-xs text-slate-400">
              <span className="flex items-center gap-1">
                <Users className="h-3.5 w-3.5" />
                {space.member_count} membros
              </span>
              <span className="flex items-center gap-1">
                <Layers className="h-3.5 w-3.5" />
                {space.resource_count} recursos
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <Tabs defaultValue="resources" className="space-y-6">
        <TabsList className="grid w-full max-w-md grid-cols-3">
          <TabsTrigger value="resources" className="gap-1.5">
            <Layers className="h-4 w-4" />
            Recursos
          </TabsTrigger>
          <TabsTrigger value="members" className="gap-1.5">
            <Users className="h-4 w-4" />
            Membros
          </TabsTrigger>
          <TabsTrigger value="settings" className="gap-1.5">
            <Settings className="h-4 w-4" />
            Config
          </TabsTrigger>
        </TabsList>

        {/* ==================== RESOURCES TAB ==================== */}
        <TabsContent value="resources" className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-200">
              Recursos compartilhados
            </h2>
            <Button
              onClick={() => setShowAddResource(true)}
              size="sm"
              className="gap-1.5 bg-indigo-600 hover:bg-indigo-500 text-white"
            >
              <Plus className="h-3.5 w-3.5" />
              Adicionar
            </Button>
          </div>

          {resources.length === 0 ? (
            <div className="text-center py-16 border border-dashed border-slate-200 dark:border-slate-700 rounded-xl">
              <Layers className="h-10 w-10 text-slate-300 mx-auto mb-3" />
              <p className="text-sm text-slate-500">
                Nenhum recurso adicionado. Adicione workflows, documentos ou resultados.
              </p>
            </div>
          ) : (
            <div className="grid gap-3">
              {resources.map((res) => {
                const Icon = RESOURCE_TYPE_ICONS[res.resource_type] || Layers;
                return (
                  <div
                    key={res.id}
                    className="group flex items-center gap-3 p-4 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 transition-colors"
                  >
                    <div className="h-9 w-9 rounded-lg bg-slate-100 dark:bg-slate-800 flex items-center justify-center shrink-0">
                      <Icon className="h-4 w-4 text-slate-500" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="font-medium text-sm text-slate-800 dark:text-slate-200 truncate">
                        {res.resource_name || res.resource_id}
                      </p>
                      <p className="text-xs text-slate-400">
                        {RESOURCE_TYPE_LABELS[res.resource_type] || res.resource_type} &middot;{' '}
                        {new Date(res.added_at).toLocaleDateString('pt-BR')}
                      </p>
                    </div>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8 opacity-0 group-hover:opacity-100 text-red-500 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-950 transition-opacity"
                      onClick={() => handleRemoveResource(res.id)}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                );
              })}
            </div>
          )}
        </TabsContent>

        {/* ==================== MEMBERS TAB ==================== */}
        <TabsContent value="members" className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-200">
              Membros e convites
            </h2>
            <Button
              onClick={() => { setShowInvite(true); setLastInviteToken(null); }}
              size="sm"
              className="gap-1.5 bg-indigo-600 hover:bg-indigo-500 text-white"
            >
              <Mail className="h-3.5 w-3.5" />
              Convidar
            </Button>
          </div>

          {members.length === 0 ? (
            <div className="text-center py-16 border border-dashed border-slate-200 dark:border-slate-700 rounded-xl">
              <Users className="h-10 w-10 text-slate-300 mx-auto mb-3" />
              <p className="text-sm text-slate-500">
                Nenhum membro convidado. Convide clientes para compartilhar recursos.
              </p>
            </div>
          ) : (
            <div className="grid gap-3">
              {members.map((m) => (
                <div
                  key={m.email}
                  className="group flex items-center gap-3 p-4 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900"
                >
                  <div className="h-9 w-9 rounded-full bg-gradient-to-br from-indigo-400 to-purple-400 flex items-center justify-center shrink-0">
                    <span className="text-xs font-bold text-white">
                      {(m.user_name || m.email).charAt(0).toUpperCase()}
                    </span>
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="font-medium text-sm text-slate-800 dark:text-slate-200 truncate">
                      {m.user_name || m.email}
                    </p>
                    <p className="text-xs text-slate-400 truncate">
                      {m.email}
                    </p>
                  </div>
                  <span
                    className={`text-[10px] font-medium px-2 py-0.5 rounded-full ${ROLE_COLORS[m.role] || 'bg-slate-100 text-slate-600'}`}
                  >
                    {ROLE_LABELS[m.role] || m.role}
                  </span>
                  {m.status === 'pending' && (
                    <span className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400">
                      Pendente
                    </span>
                  )}
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8 opacity-0 group-hover:opacity-100 text-red-500 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-950 transition-opacity"
                    onClick={() => handleRemoveMember(m.email)}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              ))}
            </div>
          )}
        </TabsContent>

        {/* ==================== SETTINGS TAB ==================== */}
        <TabsContent value="settings" className="space-y-6">
          <div className="max-w-lg space-y-5">
            <div>
              <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5 block">
                Nome do Space
              </label>
              <Input
                value={editName}
                onChange={(e) => setEditName(e.target.value)}
              />
            </div>
            <div>
              <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5 block">
                Descricao
              </label>
              <Input
                value={editDescription}
                onChange={(e) => setEditDescription(e.target.value)}
                placeholder="Descricao opcional..."
              />
            </div>
            <div>
              <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5 block flex items-center gap-2">
                <Palette className="h-4 w-4" />
                Cor principal (branding)
              </label>
              <div className="flex items-center gap-3">
                <input
                  type="color"
                  value={editColor}
                  onChange={(e) => setEditColor(e.target.value)}
                  className="h-10 w-14 rounded-lg border border-slate-200 dark:border-slate-700 cursor-pointer"
                />
                <Input
                  value={editColor}
                  onChange={(e) => setEditColor(e.target.value)}
                  className="w-32"
                  maxLength={7}
                />
                <div
                  className="h-10 flex-1 rounded-lg"
                  style={{ backgroundColor: editColor }}
                />
              </div>
            </div>

            <div className="flex items-center gap-3 pt-4">
              <Button
                onClick={handleSaveSettings}
                disabled={saving}
                className="bg-indigo-600 hover:bg-indigo-500 text-white gap-2"
              >
                {saving && <Loader2 className="h-4 w-4 animate-spin" />}
                Salvar alteracoes
              </Button>
              <Button
                variant="outline"
                onClick={handleDeleteSpace}
                className="text-red-600 hover:text-red-700 hover:bg-red-50 dark:hover:bg-red-950 border-red-200 dark:border-red-800"
              >
                <Trash2 className="h-4 w-4 mr-1.5" />
                Desativar space
              </Button>
            </div>
          </div>
        </TabsContent>
      </Tabs>

      {/* ==================== INVITE DIALOG ==================== */}
      <Dialog open={showInvite} onOpenChange={setShowInvite}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Convidar para o Space</DialogTitle>
            <DialogDescription>
              Envie um convite por email. O convidado precisara de uma conta no Iudex para aceitar.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div>
              <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5 block">
                Email
              </label>
              <Input
                type="email"
                placeholder="cliente@exemplo.com"
                value={inviteEmail}
                onChange={(e) => setInviteEmail(e.target.value)}
              />
            </div>
            <div>
              <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5 block">
                Permissao
              </label>
              <div className="flex gap-2">
                {(['viewer', 'contributor', 'admin'] as const).map((role) => (
                  <button
                    key={role}
                    onClick={() => setInviteRole(role)}
                    className={`flex-1 text-xs font-medium py-2 px-3 rounded-lg border transition-colors ${
                      inviteRole === role
                        ? 'border-indigo-400 bg-indigo-50 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-300 dark:border-indigo-600'
                        : 'border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-400 hover:border-slate-300'
                    }`}
                  >
                    {ROLE_LABELS[role]}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5 block">
                Mensagem (opcional)
              </label>
              <Input
                placeholder="Mensagem personalizada..."
                value={inviteMessage}
                onChange={(e) => setInviteMessage(e.target.value)}
              />
            </div>

            {lastInviteToken && (
              <div className="p-3 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg">
                <p className="text-xs text-green-700 dark:text-green-400 mb-2 font-medium">
                  Convite criado! Compartilhe o link:
                </p>
                <div className="flex items-center gap-2">
                  <code className="flex-1 text-[10px] text-green-600 dark:text-green-300 truncate bg-green-100 dark:bg-green-900/30 px-2 py-1 rounded">
                    {window.location.origin}/spaces/join/{lastInviteToken}
                  </code>
                  <Button
                    size="icon"
                    variant="ghost"
                    className="h-7 w-7 shrink-0"
                    onClick={handleCopyInviteLink}
                  >
                    {copiedToken ? (
                      <Check className="h-3.5 w-3.5 text-green-600" />
                    ) : (
                      <Copy className="h-3.5 w-3.5" />
                    )}
                  </Button>
                </div>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowInvite(false)}>
              Fechar
            </Button>
            <Button
              onClick={handleInvite}
              disabled={inviting || !inviteEmail.trim()}
              className="bg-indigo-600 hover:bg-indigo-500 text-white gap-2"
            >
              {inviting && <Loader2 className="h-4 w-4 animate-spin" />}
              Enviar convite
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ==================== ADD RESOURCE DIALOG ==================== */}
      <Dialog open={showAddResource} onOpenChange={setShowAddResource}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Adicionar recurso ao Space</DialogTitle>
            <DialogDescription>
              Compartilhe um workflow, documento ou resultado com os membros deste space.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div>
              <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5 block">
                Tipo de recurso
              </label>
              <div className="flex gap-2">
                {(['workflow', 'document', 'run', 'folder'] as const).map((type) => {
                  const Icon = RESOURCE_TYPE_ICONS[type] || Layers;
                  return (
                    <button
                      key={type}
                      onClick={() => setResourceType(type)}
                      className={`flex-1 flex flex-col items-center gap-1 text-xs font-medium py-2.5 px-2 rounded-lg border transition-colors ${
                        resourceType === type
                          ? 'border-indigo-400 bg-indigo-50 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-300 dark:border-indigo-600'
                          : 'border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-400 hover:border-slate-300'
                      }`}
                    >
                      <Icon className="h-4 w-4" />
                      {RESOURCE_TYPE_LABELS[type]}
                    </button>
                  );
                })}
              </div>
            </div>
            <div>
              <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5 block">
                ID do recurso
              </label>
              <Input
                placeholder="Cole o ID do recurso aqui"
                value={resourceId}
                onChange={(e) => setResourceId(e.target.value)}
              />
            </div>
            <div>
              <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5 block">
                Nome (opcional, para exibicao)
              </label>
              <Input
                placeholder="Ex: Contrato de Servicos"
                value={resourceName}
                onChange={(e) => setResourceName(e.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowAddResource(false)}>
              Cancelar
            </Button>
            <Button
              onClick={handleAddResource}
              disabled={addingResource || !resourceId.trim()}
              className="bg-indigo-600 hover:bg-indigo-500 text-white gap-2"
            >
              {addingResource && <Loader2 className="h-4 w-4 animate-spin" />}
              Adicionar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
