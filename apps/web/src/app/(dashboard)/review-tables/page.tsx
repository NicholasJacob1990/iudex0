'use client';

import * as React from 'react';
import { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
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
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Plus,
  Table,
  FileText,
  MoreVertical,
  Trash2,
  Search,
  Loader2,
  Calendar,
  Columns3,
  ShieldCheck,
} from 'lucide-react';
import { toast } from 'sonner';
import apiClient from '@/lib/api-client';
import type { ReviewTable } from '@/types/review-table';

export default function ReviewTablesPage() {
  const router = useRouter();
  const [tables, setTables] = useState<ReviewTable[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [newTableName, setNewTableName] = useState('');
  const [newTableDescription, setNewTableDescription] = useState('');
  const [deleteConfirm, setDeleteConfirm] = useState<ReviewTable | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  // Load tables callback
  const loadTables = useCallback(async () => {
    setIsLoading(true);
    try {
      const result = await apiClient.listReviewTables();
      setTables(result.tables || []);
    } catch (error) {
      console.error('Error loading tables:', error);
      toast.error('Erro ao carregar tabelas');
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Load tables on mount
  useEffect(() => {
    loadTables();
  }, [loadTables]);

  // Create new table
  const handleCreateTable = useCallback(async () => {
    if (!newTableName.trim()) {
      toast.error('Digite um nome para a tabela');
      return;
    }

    setIsCreating(true);
    try {
      const newTable = await apiClient.createReviewTable({
        name: newTableName.trim(),
        description: newTableDescription.trim() || undefined,
      });

      setTables((prev) => [newTable, ...prev]);
      setIsCreateDialogOpen(false);
      setNewTableName('');
      setNewTableDescription('');
      toast.success('Tabela criada com sucesso');

      // Navigate to the new table
      router.push(`/review-tables/${newTable.id}`);
    } catch (error) {
      console.error('Error creating table:', error);
      toast.error('Erro ao criar tabela');
    } finally {
      setIsCreating(false);
    }
  }, [newTableName, newTableDescription, router]);

  // Delete table
  const handleDeleteTable = useCallback(async () => {
    if (!deleteConfirm) return;

    setIsDeleting(true);
    try {
      await apiClient.deleteReviewTable(deleteConfirm.id);
      setTables((prev) => prev.filter((t) => t.id !== deleteConfirm.id));
      toast.success('Tabela excluida');
    } catch (error) {
      console.error('Error deleting table:', error);
      toast.error('Erro ao excluir tabela');
    } finally {
      setIsDeleting(false);
      setDeleteConfirm(null);
    }
  }, [deleteConfirm]);

  // Filter tables by search query
  const filteredTables = React.useMemo(() => {
    if (!searchQuery.trim()) return tables;
    const query = searchQuery.toLowerCase();
    return tables.filter(
      (table) =>
        table.name.toLowerCase().includes(query) ||
        table.description?.toLowerCase().includes(query)
    );
  }, [tables, searchQuery]);

  // Format date
  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString('pt-BR', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    });
  };

  return (
    <div className="container py-8 max-w-6xl">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-semibold">Review Tables</h1>
          <p className="text-muted-foreground mt-1">
            Extraia e analise dados de multiplos documentos
          </p>
        </div>

        <Dialog open={isCreateDialogOpen} onOpenChange={setIsCreateDialogOpen}>
          <DialogTrigger asChild>
            <Button>
              <Plus className="h-4 w-4 mr-2" />
              Nova Tabela
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Criar Nova Tabela</DialogTitle>
              <DialogDescription>
                Crie uma tabela para organizar e extrair dados de seus documentos.
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4 py-4">
              <div className="space-y-2">
                <Label htmlFor="name">Nome da tabela</Label>
                <Input
                  id="name"
                  value={newTableName}
                  onChange={(e) => setNewTableName(e.target.value)}
                  placeholder="Ex: Analise de Contratos Q4"
                  autoFocus
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="description">Descricao (opcional)</Label>
                <Textarea
                  id="description"
                  value={newTableDescription}
                  onChange={(e) => setNewTableDescription(e.target.value)}
                  placeholder="Descreva o objetivo desta tabela..."
                  rows={3}
                />
              </div>
            </div>
            <DialogFooter>
              <Button
                variant="outline"
                onClick={() => setIsCreateDialogOpen(false)}
                disabled={isCreating}
              >
                Cancelar
              </Button>
              <Button onClick={handleCreateTable} disabled={isCreating}>
                {isCreating ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    Criando...
                  </>
                ) : (
                  <>
                    <Plus className="h-4 w-4 mr-2" />
                    Criar Tabela
                  </>
                )}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      {/* Search */}
      <div className="relative mb-6">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <Input
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder="Buscar tabelas..."
          className="pl-10"
        />
      </div>

      {/* Tables grid */}
      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
        </div>
      ) : filteredTables.length === 0 ? (
        <div className="text-center py-12">
          <Table className="h-12 w-12 text-muted-foreground/40 mx-auto mb-4" />
          {tables.length === 0 ? (
            <>
              <h2 className="text-lg font-semibold mb-2">Nenhuma tabela criada</h2>
              <p className="text-muted-foreground mb-4">
                Crie sua primeira Review Table para comecar a extrair dados.
              </p>
              <Button onClick={() => setIsCreateDialogOpen(true)}>
                <Plus className="h-4 w-4 mr-2" />
                Criar Primeira Tabela
              </Button>
            </>
          ) : (
            <>
              <h2 className="text-lg font-semibold mb-2">
                Nenhuma tabela encontrada
              </h2>
              <p className="text-muted-foreground">
                Nenhuma tabela corresponde a sua busca.
              </p>
            </>
          )}
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {filteredTables.map((table) => (
            <Card
              key={table.id}
              className="cursor-pointer hover:border-primary/50 transition-colors group"
              onClick={() => router.push(`/review-tables/${table.id}`)}
            >
              <CardHeader className="pb-2">
                <div className="flex items-start justify-between">
                  <div className="flex-1 min-w-0">
                    <CardTitle className="text-base truncate">
                      {table.name}
                    </CardTitle>
                    {table.description && (
                      <CardDescription className="mt-1 line-clamp-2">
                        {table.description}
                      </CardDescription>
                    )}
                  </div>
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild onClick={(e) => e.stopPropagation()}>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 opacity-0 group-hover:opacity-100"
                      >
                        <MoreVertical className="h-4 w-4" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      <DropdownMenuItem
                        onClick={(e) => {
                          e.stopPropagation();
                          setDeleteConfirm(table);
                        }}
                        className="text-destructive focus:text-destructive"
                      >
                        <Trash2 className="h-4 w-4 mr-2" />
                        Excluir
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>
              </CardHeader>
              <CardContent className="pb-3">
                <div className="flex items-center gap-3 text-xs text-muted-foreground">
                  <div className="flex items-center gap-1">
                    <FileText className="h-3.5 w-3.5" />
                    <span>{table.document_ids?.length || 0} docs</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <Calendar className="h-3.5 w-3.5" />
                    <span>{formatDate(table.created_at)}</span>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Delete confirmation */}
      <AlertDialog
        open={!!deleteConfirm}
        onOpenChange={(open) => !open && setDeleteConfirm(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Excluir tabela?</AlertDialogTitle>
            <AlertDialogDescription>
              Esta acao ira excluir a tabela &quot;{deleteConfirm?.name}&quot; e todos os
              dados de extracao. Esta acao nao pode ser desfeita.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={isDeleting}>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDeleteTable}
              disabled={isDeleting}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {isDeleting ? (
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
              ) : (
                <Trash2 className="h-4 w-4 mr-2" />
              )}
              Excluir
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
