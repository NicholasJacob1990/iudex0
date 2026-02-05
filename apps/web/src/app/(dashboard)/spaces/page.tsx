'use client';

import React, { useEffect, useState, useCallback } from 'react';
import {
  Plus,
  Users,
  Loader2,
  Layers,
  Calendar,
  ArrowRight,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { apiClient } from '@/lib/api-client';
import { toast } from 'sonner';
import { useRouter } from 'next/navigation';

interface SpaceItem {
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

export default function SpacesListPage() {
  const [spaces, setSpaces] = useState<SpaceItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState('');
  const [newDescription, setNewDescription] = useState('');
  const [creating, setCreating] = useState(false);
  const router = useRouter();

  const fetchSpaces = useCallback(async () => {
    try {
      const data = await apiClient.request('/spaces');
      setSpaces(data);
    } catch {
      toast.error('Erro ao carregar spaces');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSpaces();
  }, [fetchSpaces]);

  const handleCreate = async () => {
    if (!newName.trim()) {
      toast.error('Nome do space e obrigatorio');
      return;
    }
    setCreating(true);
    try {
      const created = await apiClient.request('/spaces/', {
        method: 'POST',
        body: {
          name: newName.trim(),
          description: newDescription.trim() || null,
        },
      });
      setSpaces((prev) => [created, ...prev]);
      setShowCreate(false);
      setNewName('');
      setNewDescription('');
      toast.success('Space criado com sucesso!');
      router.push(`/spaces/${created.id}`);
    } catch {
      toast.error('Erro ao criar space');
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="container mx-auto px-6 py-8 max-w-5xl">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Shared Spaces</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            Crie workspaces para compartilhar recursos com clientes e colaboradores externos
          </p>
        </div>
        <Button
          onClick={() => setShowCreate(true)}
          className="gap-2 bg-indigo-600 hover:bg-indigo-500 text-white"
        >
          <Plus className="h-4 w-4" />
          Criar Space
        </Button>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="h-8 w-8 text-indigo-500 animate-spin" />
        </div>
      ) : spaces.length === 0 ? (
        <div className="text-center py-20">
          <Users className="h-12 w-12 text-slate-300 mx-auto mb-4" />
          <h3 className="text-lg font-semibold text-slate-700 dark:text-slate-300 mb-2">
            Nenhum space criado
          </h3>
          <p className="text-slate-500 dark:text-slate-400 mb-6 max-w-md mx-auto">
            Shared Spaces permitem que voce convide clientes externos para visualizar
            workflows, documentos e resultados de forma controlada.
          </p>
          <Button
            onClick={() => setShowCreate(true)}
            variant="outline"
            className="gap-2"
          >
            <Plus className="h-4 w-4" />
            Criar primeiro space
          </Button>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {spaces.map((space) => (
            <div
              key={space.id}
              className="group relative flex flex-col p-5 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 hover:border-indigo-300 dark:hover:border-indigo-700 transition-all cursor-pointer hover:shadow-lg hover:shadow-indigo-500/5"
              onClick={() => router.push(`/spaces/${space.id}`)}
            >
              {/* Color accent bar */}
              <div
                className="absolute top-0 left-4 right-4 h-1 rounded-b-full"
                style={{
                  backgroundColor: space.branding?.primary_color || '#6366f1',
                }}
              />

              <div className="flex items-start gap-3 mb-3 mt-1">
                <div
                  className="h-10 w-10 rounded-lg flex items-center justify-center shrink-0"
                  style={{
                    backgroundColor: (space.branding?.primary_color || '#6366f1') + '20',
                  }}
                >
                  <Users
                    className="h-5 w-5"
                    style={{
                      color: space.branding?.primary_color || '#6366f1',
                    }}
                  />
                </div>
                <div className="flex-1 min-w-0">
                  <h3 className="font-semibold text-slate-800 dark:text-slate-200 truncate">
                    {space.name}
                  </h3>
                  {space.description && (
                    <p className="text-xs text-slate-500 dark:text-slate-400 line-clamp-2 mt-0.5">
                      {space.description}
                    </p>
                  )}
                </div>
              </div>

              <div className="flex items-center gap-4 mt-auto pt-3 border-t border-slate-100 dark:border-slate-800">
                <div className="flex items-center gap-1.5 text-xs text-slate-500">
                  <Users className="h-3.5 w-3.5" />
                  <span>{space.member_count} membros</span>
                </div>
                <div className="flex items-center gap-1.5 text-xs text-slate-500">
                  <Layers className="h-3.5 w-3.5" />
                  <span>{space.resource_count} recursos</span>
                </div>
              </div>

              <div className="flex items-center gap-1.5 text-[10px] text-slate-400 mt-2">
                <Calendar className="h-3 w-3" />
                <span>
                  {new Date(space.created_at).toLocaleDateString('pt-BR')}
                </span>
              </div>

              <div className="absolute top-1/2 right-3 -translate-y-1/2 opacity-0 group-hover:opacity-100 transition-opacity">
                <ArrowRight className="h-4 w-4 text-indigo-400" />
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Create Dialog */}
      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Criar novo Space</DialogTitle>
            <DialogDescription>
              Um space permite compartilhar workflows, documentos e resultados com clientes externos.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div>
              <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5 block">
                Nome do Space
              </label>
              <Input
                placeholder="Ex: Caso XYZ - Cliente ABC"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleCreate()}
              />
            </div>
            <div>
              <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5 block">
                Descricao (opcional)
              </label>
              <Input
                placeholder="Breve descricao do space..."
                value={newDescription}
                onChange={(e) => setNewDescription(e.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowCreate(false)}>
              Cancelar
            </Button>
            <Button
              onClick={handleCreate}
              disabled={creating || !newName.trim()}
              className="bg-indigo-600 hover:bg-indigo-500 text-white gap-2"
            >
              {creating && <Loader2 className="h-4 w-4 animate-spin" />}
              Criar Space
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
