'use client';

import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import { useAuthStore } from '@/stores/auth-store';
import apiClient from '@/lib/api-client';

type ExportToCorpusDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: (payload: { scope: 'group'; collection: string; group_ids: string[] }) => Promise<void> | void;
  loading?: boolean;
  itemCount: number;
  sourceLabel?: string;
};

const PRIVATE_COLLECTIONS = [
  { value: 'doutrina', label: 'Doutrina' },
  { value: 'pecas_modelo', label: 'Peças Modelo' },
  { value: 'juris', label: 'Jurisprudência' },
  { value: 'lei', label: 'Legislação' },
  { value: 'sei', label: 'SEI' },
];

export function ExportToCorpusDialog({
  open,
  onOpenChange,
  onConfirm,
  loading = false,
  itemCount,
  sourceLabel = 'documentos',
}: ExportToCorpusDialogProps) {
  const { user } = useAuthStore();
  const [collection, setCollection] = useState<string>('doutrina');
  const [teamsLoading, setTeamsLoading] = useState(false);
  const [myTeams, setMyTeams] = useState<Array<{ id: string; name: string }>>([]);
  const [groupIds, setGroupIds] = useState<string[]>([]);

  useEffect(() => {
    if (!open) return;
    setCollection('doutrina');
    setGroupIds([]);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    if (!user?.organization_id) {
      setMyTeams([]);
      return;
    }
    setTeamsLoading(true);
    apiClient
      .getMyOrgTeams()
      .then((res) => {
        const teams = Array.isArray(res) ? res : [];
        setMyTeams(
          teams
            .map((t: any) => ({
              id: String(t?.id || '').trim(),
              name: String(t?.name || '').trim(),
            }))
            .filter((t: any) => t.id && t.name)
        );
      })
      .catch(() => setMyTeams([]))
      .finally(() => setTeamsLoading(false));
  }, [open, user?.organization_id]);

  const handleConfirm = async () => {
    if (!groupIds.length) return;
    await onConfirm({ scope: 'group', collection, group_ids: groupIds });
  };

  const toggleGroup = (id: string) => {
    const gid = String(id || '').trim();
    if (!gid) return;
    setGroupIds((prev) => (prev.includes(gid) ? prev.filter((g) => g !== gid) : [...prev, gid]));
  };

  return (
    <Dialog open={open} onOpenChange={(next) => !loading && onOpenChange(next)}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Exportar para Corpus</DialogTitle>
          <DialogDescription>
            Enviar {itemCount} {sourceLabel} para indexação no Corpus (RAG).
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-2">
            <Label className="text-xs">Coleção</Label>
            <Select value={collection} onValueChange={setCollection}>
              <SelectTrigger className="rounded-xl">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PRIVATE_COLLECTIONS.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label className="text-xs">Departamentos (Group)</Label>
            {teamsLoading ? (
              <p className="text-xs text-muted-foreground">Carregando departamentos...</p>
            ) : myTeams.length > 0 ? (
              <div className="max-h-44 overflow-y-auto rounded-xl border p-3 space-y-2">
                {myTeams.map((team) => (
                  <label key={team.id} className="flex items-center gap-2 text-sm cursor-pointer">
                    <Checkbox
                      checked={groupIds.includes(team.id)}
                      onCheckedChange={() => toggleGroup(team.id)}
                      className="h-4 w-4"
                    />
                    <span className="text-xs">{team.name}</span>
                  </label>
                ))}
              </div>
            ) : (
              <p className="text-xs text-muted-foreground">
                Nenhum departamento disponível para exportação em group.
              </p>
            )}
          </div>
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            className="rounded-full"
            onClick={() => onOpenChange(false)}
            disabled={loading}
          >
            Cancelar
          </Button>
          <Button
            className="rounded-full"
            onClick={handleConfirm}
            disabled={loading || itemCount === 0 || groupIds.length === 0}
          >
            {loading ? 'Exportando...' : 'Exportar'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
