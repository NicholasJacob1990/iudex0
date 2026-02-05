'use client';

import { useState, useEffect } from 'react';
import { Users, Globe, Lock, Copy, Check, X, Loader2, Eye, Pencil } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { toast } from 'sonner';
import {
  type Playbook,
  type PlaybookShareInfo,
  usePlaybook,
  useSharePlaybook,
  useUpdateShare,
  useRemoveShare,
} from '../hooks';

export type SharePermission = 'view' | 'edit';

interface PlaybookShareDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  playbook: Playbook | null;
  onShare: (playbookId: string, settings: ShareSettings) => void;
}

export interface ShareSettings {
  isShared: boolean;
  shareScope: 'private' | 'org' | 'public';
  sharedEmails: string[];
  isTemplate: boolean;
}

export function PlaybookShareDialog({
  open,
  onOpenChange,
  playbook,
  onShare,
}: PlaybookShareDialogProps) {
  const [shareScope, setShareScope] = useState<'private' | 'org' | 'public'>(
    playbook?.is_shared ? 'org' : 'private'
  );
  const [emailInput, setEmailInput] = useState('');
  const [emailPermission, setEmailPermission] = useState<SharePermission>('view');
  const [isTemplate, setIsTemplate] = useState(playbook?.is_template || false);
  const [copied, setCopied] = useState(false);

  // Fetch full playbook details with shares
  const { data: fullPlaybook } = usePlaybook(open ? playbook?.id : undefined);
  const sharePlaybookMutation = useSharePlaybook();
  const updateShareMutation = useUpdateShare();
  const removeShareMutation = useRemoveShare();

  // Extract shares from full playbook data
  const currentShares: PlaybookShareInfo[] = fullPlaybook?.shares ?? [];

  // Sync state when playbook prop changes
  useEffect(() => {
    if (playbook) {
      setShareScope(playbook.is_shared ? 'org' : 'private');
      setIsTemplate(playbook.is_template || false);
      setEmailInput('');
      setEmailPermission('view');
    }
  }, [playbook]);

  if (!playbook) return null;

  const handleAddEmail = async () => {
    const email = emailInput.trim().toLowerCase();
    if (!email || !email.includes('@')) {
      toast.error('Informe um e-mail valido');
      return;
    }

    try {
      await sharePlaybookMutation.mutateAsync({
        playbookId: playbook.id,
        userEmail: email,
        permission: emailPermission,
      });
      setEmailInput('');
    } catch {
      // Error toast is handled by the mutation
    }
  };

  const handleUpdatePermission = async (shareId: string, permission: SharePermission) => {
    try {
      await updateShareMutation.mutateAsync({
        playbookId: playbook.id,
        shareId,
        permission,
      });
    } catch {
      // Error toast is handled by the mutation
    }
  };

  const handleRemoveShare = async (shareId: string) => {
    try {
      await removeShareMutation.mutateAsync({
        playbookId: playbook.id,
        shareId,
      });
    } catch {
      // Error toast is handled by the mutation
    }
  };

  const handleCopyLink = async () => {
    const url = `${window.location.origin}/playbooks/${playbook.id}`;
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
      toast.success('Link copiado');
    } catch {
      toast.error('Falha ao copiar link');
    }
  };

  const handleSubmit = () => {
    onShare(playbook.id, {
      isShared: shareScope !== 'private',
      shareScope,
      sharedEmails: currentShares
        .filter((s) => s.shared_with_email)
        .map((s) => s.shared_with_email!),
      isTemplate,
    });
    onOpenChange(false);
  };

  const isAdding = sharePlaybookMutation.isPending;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Compartilhar Playbook</DialogTitle>
          <DialogDescription>
            Configure o compartilhamento de &ldquo;{playbook.name}&rdquo;.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-5 py-2">
          {/* Visibility */}
          <div className="space-y-3">
            <Label>Visibilidade</Label>
            <div className="grid gap-2">
              <button
                onClick={() => setShareScope('private')}
                className={`flex items-center gap-3 p-3 rounded-lg border text-left transition-all ${
                  shareScope === 'private'
                    ? 'border-indigo-400 bg-indigo-50 dark:bg-indigo-500/10'
                    : 'border-slate-200 dark:border-slate-700'
                }`}
              >
                <Lock className="h-4 w-4 text-slate-500" />
                <div>
                  <p className="text-sm font-medium">Privado</p>
                  <p className="text-[11px] text-slate-500">Apenas voce pode acessar</p>
                </div>
              </button>
              <button
                onClick={() => setShareScope('org')}
                className={`flex items-center gap-3 p-3 rounded-lg border text-left transition-all ${
                  shareScope === 'org'
                    ? 'border-indigo-400 bg-indigo-50 dark:bg-indigo-500/10'
                    : 'border-slate-200 dark:border-slate-700'
                }`}
              >
                <Users className="h-4 w-4 text-slate-500" />
                <div>
                  <p className="text-sm font-medium">Organizacao</p>
                  <p className="text-[11px] text-slate-500">Todos da sua organizacao podem acessar</p>
                </div>
              </button>
              <button
                onClick={() => setShareScope('public')}
                className={`flex items-center gap-3 p-3 rounded-lg border text-left transition-all ${
                  shareScope === 'public'
                    ? 'border-indigo-400 bg-indigo-50 dark:bg-indigo-500/10'
                    : 'border-slate-200 dark:border-slate-700'
                }`}
              >
                <Globe className="h-4 w-4 text-slate-500" />
                <div>
                  <p className="text-sm font-medium">Publico</p>
                  <p className="text-[11px] text-slate-500">Qualquer usuario pode acessar via link</p>
                </div>
              </button>
            </div>
          </div>

          {/* Share with specific emails */}
          {shareScope !== 'private' && (
            <div className="space-y-3">
              <Label>Convidar por e-mail</Label>
              <div className="flex gap-2">
                <Input
                  value={emailInput}
                  onChange={(e) => setEmailInput(e.target.value)}
                  placeholder="email@exemplo.com"
                  onKeyDown={(e) => e.key === 'Enter' && handleAddEmail()}
                  className="flex-1"
                />
                <Select
                  value={emailPermission}
                  onValueChange={(v) => setEmailPermission(v as SharePermission)}
                >
                  <SelectTrigger className="w-[120px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="view">
                      <span className="flex items-center gap-1.5">
                        <Eye className="h-3 w-3" />
                        Visualizar
                      </span>
                    </SelectItem>
                    <SelectItem value="edit">
                      <span className="flex items-center gap-1.5">
                        <Pencil className="h-3 w-3" />
                        Editar
                      </span>
                    </SelectItem>
                  </SelectContent>
                </Select>
                <Button
                  variant="outline"
                  onClick={handleAddEmail}
                  disabled={isAdding}
                >
                  {isAdding ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    'Adicionar'
                  )}
                </Button>
              </div>

              {/* Current shares list */}
              {currentShares.length > 0 && (
                <div className="space-y-2 mt-3">
                  <p className="text-xs text-slate-500 font-medium">
                    Compartilhado com {currentShares.length} {currentShares.length === 1 ? 'pessoa' : 'pessoas'}
                  </p>
                  <div className="space-y-1.5 max-h-[160px] overflow-y-auto">
                    {currentShares.map((share) => (
                      <div
                        key={share.id}
                        className="flex items-center justify-between gap-2 px-3 py-2 rounded-lg bg-slate-50 dark:bg-slate-800/50 border border-slate-100 dark:border-slate-700"
                      >
                        <span className="text-sm text-slate-700 dark:text-slate-300 truncate flex-1">
                          {share.shared_with_email ?? share.shared_with_org_id ?? 'Organizacao'}
                        </span>
                        <div className="flex items-center gap-1.5">
                          <Select
                            value={share.permission}
                            onValueChange={(v) =>
                              handleUpdatePermission(share.id, v as SharePermission)
                            }
                          >
                            <SelectTrigger className="h-7 w-[110px] text-xs">
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="view">
                                <span className="flex items-center gap-1">
                                  <Eye className="h-3 w-3" />
                                  Visualizar
                                </span>
                              </SelectItem>
                              <SelectItem value="edit">
                                <span className="flex items-center gap-1">
                                  <Pencil className="h-3 w-3" />
                                  Editar
                                </span>
                              </SelectItem>
                            </SelectContent>
                          </Select>
                          <button
                            onClick={() => handleRemoveShare(share.id)}
                            className="p-1 rounded hover:bg-red-100 dark:hover:bg-red-900/30 text-slate-400 hover:text-red-500 transition-colors"
                            title="Remover compartilhamento"
                          >
                            <X className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Template toggle */}
          <div className="flex items-center justify-between rounded-lg border border-slate-200 dark:border-slate-700 p-3">
            <div>
              <p className="text-sm font-medium">Disponibilizar como template</p>
              <p className="text-[11px] text-slate-500">Outros usuarios poderao criar playbooks a partir deste.</p>
            </div>
            <Switch checked={isTemplate} onCheckedChange={setIsTemplate} />
          </div>

          {/* Copy link */}
          <Button variant="outline" className="w-full gap-2" onClick={handleCopyLink}>
            {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
            {copied ? 'Copiado!' : 'Copiar link'}
          </Button>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancelar
          </Button>
          <Button
            onClick={handleSubmit}
            className="bg-indigo-600 hover:bg-indigo-500 text-white"
          >
            Salvar Configuracoes
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
