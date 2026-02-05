'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { Lock, Plus, Trash2, Loader2 } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { apiClient } from '@/lib/api-client';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface WorkflowPermission {
  id: string;
  workflow_id: string;
  user_id: string | null;
  organization_id: string | null;
  build_access: string;
  run_access: string;
  granted_by: string;
  granted_at: string | null;
}

interface PermissionsDialogProps {
  workflowId: string;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const BUILD_OPTIONS = [
  { value: 'none', label: 'Nenhum' },
  { value: 'view', label: 'Visualizar' },
  { value: 'edit', label: 'Editar' },
  { value: 'full', label: 'Completo' },
] as const;

const RUN_OPTIONS = [
  { value: 'none', label: 'Nenhum' },
  { value: 'run', label: 'Executar' },
] as const;

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function PermissionsDialog({ workflowId }: PermissionsDialogProps) {
  const [open, setOpen] = useState(false);
  const [permissions, setPermissions] = useState<WorkflowPermission[]>([]);
  const [loading, setLoading] = useState(false);

  // New permission form
  const [newUserId, setNewUserId] = useState('');
  const [newBuild, setNewBuild] = useState('none');
  const [newRun, setNewRun] = useState('none');
  const [granting, setGranting] = useState(false);

  const fetchPermissions = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiClient.request(`/workflows/${workflowId}/permissions`);
      setPermissions(Array.isArray(data) ? data : []);
    } catch (err) {
      toast.error('Erro ao carregar permissoes');
    } finally {
      setLoading(false);
    }
  }, [workflowId]);

  useEffect(() => {
    if (open) {
      fetchPermissions();
    }
  }, [open, fetchPermissions]);

  const handleGrant = async () => {
    if (!newUserId.trim()) {
      toast.error('Informe o ID do usuario');
      return;
    }
    if (newBuild === 'none' && newRun === 'none') {
      toast.error('Selecione pelo menos um nivel de acesso');
      return;
    }
    setGranting(true);
    try {
      await apiClient.request(`/workflows/${workflowId}/permissions`, {
        method: 'POST',
        body: {
          user_id: newUserId.trim(),
          build_access: newBuild,
          run_access: newRun,
        },
      });
      toast.success('Permissao concedida');
      setNewUserId('');
      setNewBuild('none');
      setNewRun('none');
      await fetchPermissions();
    } catch (err) {
      toast.error('Erro ao conceder permissao');
    } finally {
      setGranting(false);
    }
  };

  const handleRevoke = async (userId: string) => {
    try {
      await apiClient.request(`/workflows/${workflowId}/permissions/${userId}`, {
        method: 'DELETE',
      });
      toast.success('Permissao revogada');
      setPermissions((prev) => prev.filter((p) => p.user_id !== userId));
    } catch (err) {
      toast.error('Erro ao revogar permissao');
    }
  };

  const buildLabel = (value: string) =>
    BUILD_OPTIONS.find((o) => o.value === value)?.label ?? value;

  const runLabel = (value: string) =>
    RUN_OPTIONS.find((o) => o.value === value)?.label ?? value;

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm" className="gap-1.5">
          <Lock className="h-4 w-4" />
          Permissoes
        </Button>
      </DialogTrigger>

      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Permissoes do Workflow</DialogTitle>
          <DialogDescription>
            Gerencie quem pode construir e executar este workflow.
          </DialogDescription>
        </DialogHeader>

        <Tabs defaultValue="current" className="w-full">
          <TabsList className="w-full">
            <TabsTrigger value="current" className="flex-1">
              Atuais
            </TabsTrigger>
            <TabsTrigger value="add" className="flex-1">
              Adicionar
            </TabsTrigger>
          </TabsList>

          {/* ── Current permissions ─────────────────────────────── */}
          <TabsContent value="current" className="space-y-3 mt-4">
            {loading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
              </div>
            ) : permissions.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-8">
                Nenhuma permissao concedida ainda.
              </p>
            ) : (
              <div className="space-y-2 max-h-64 overflow-y-auto">
                {permissions.map((perm) => (
                  <div
                    key={perm.id}
                    className="flex items-center justify-between rounded-lg border p-3 text-sm"
                  >
                    <div className="flex-1 min-w-0">
                      <p className="font-medium truncate">
                        {perm.user_id ?? 'Organizacao'}
                      </p>
                      <div className="flex gap-3 text-xs text-muted-foreground mt-1">
                        <span>Build: {buildLabel(perm.build_access)}</span>
                        <span>Run: {runLabel(perm.run_access)}</span>
                      </div>
                    </div>
                    {perm.user_id && (
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-destructive hover:text-destructive"
                        onClick={() => handleRevoke(perm.user_id!)}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    )}
                  </div>
                ))}
              </div>
            )}
          </TabsContent>

          {/* ── Add new permission ──────────────────────────────── */}
          <TabsContent value="add" className="space-y-4 mt-4">
            <div className="space-y-2">
              <label className="text-sm font-medium">ID do Usuario</label>
              <Input
                placeholder="ID ou email do usuario"
                value={newUserId}
                onChange={(e) => setNewUserId(e.target.value)}
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <label className="text-sm font-medium">Acesso Build</label>
                <Select value={newBuild} onValueChange={setNewBuild}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {BUILD_OPTIONS.map((opt) => (
                      <SelectItem key={opt.value} value={opt.value}>
                        {opt.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <label className="text-sm font-medium">Acesso Run</label>
                <Select value={newRun} onValueChange={setNewRun}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {RUN_OPTIONS.map((opt) => (
                      <SelectItem key={opt.value} value={opt.value}>
                        {opt.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <Button
              onClick={handleGrant}
              disabled={granting}
              className="w-full gap-1.5"
            >
              {granting ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Plus className="h-4 w-4" />
              )}
              Conceder Acesso
            </Button>
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}
