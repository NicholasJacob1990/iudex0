'use client';

import { useState } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Share2, Mail, Users, X, Copy, Link as LinkIcon } from 'lucide-react';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { toast } from 'sonner';

import apiClient from '@/lib/api-client';

interface ShareDialogProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    itemName?: string;
    itemType?: string;
    itemId?: string;
}

type PermissionLevel = 'view' | 'edit' | 'admin';

interface SharedUser {
    email: string;
    permission: PermissionLevel;
}

const permissionLabels: Record<PermissionLevel, string> = {
    view: 'Visualizar',
    edit: 'Editar',
    admin: 'Administrador',
};

const permissionDescriptions: Record<PermissionLevel, string> = {
    view: 'Pode apenas visualizar',
    edit: 'Pode visualizar e editar',
    admin: 'Controle total',
};

export function ShareDialog({ open, onOpenChange, itemName = 'Item', itemType = 'documento', itemId }: ShareDialogProps) {
    const [email, setEmail] = useState('');
    const [sharedUsers, setSharedUsers] = useState<SharedUser[]>([]);
    const [defaultPermission, setDefaultPermission] = useState<PermissionLevel>('view');
    const [shareLink, setShareLink] = useState('');
    const [linkGenerated, setLinkGenerated] = useState(false);

    const handleAddUser = () => {
        if (!email.trim()) {
            toast.error('Digite um email válido');
            return;
        }

        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        if (!emailRegex.test(email)) {
            toast.error('Email inválido');
            return;
        }

        if (sharedUsers.some((u) => u.email === email)) {
            toast.error('Usuário já adicionado');
            return;
        }

        setSharedUsers([...sharedUsers, { email, permission: defaultPermission }]);
        setEmail('');
        toast.success(`${email} adicionado`);
    };

    const handleRemoveUser = (email: string) => {
        setSharedUsers(sharedUsers.filter((u) => u.email !== email));
        toast.info(`${email} removido`);
    };

    const handleChangePermission = (email: string, permission: PermissionLevel) => {
        setSharedUsers(sharedUsers.map((u) => (u.email === email ? { ...u, permission } : u)));
        toast.success(`Permissão atualizada para ${permissionLabels[permission]}`);
    };

    const handleGenerateLink = async () => {
        try {
            if (!itemId) {
                // Fallback to mock if no itemId (e.g. for UI testing)
                const mockLink = `https://iudex.app/shared/${Math.random().toString(36).substring(7)}`;
                setShareLink(mockLink);
                setLinkGenerated(true);
                toast.success('Link de demonstração gerado (ID não fornecido)!');
                return;
            }

            const response = await apiClient.shareDocument(itemId);
            setShareLink(response.share_url);
            setLinkGenerated(true);
            toast.success('Link de compartilhamento gerado!');
        } catch (error) {
            console.error('Erro ao gerar link:', error);
            toast.error('Erro ao gerar link de compartilhamento');
        }
    };

    const handleCopyLink = () => {
        navigator.clipboard.writeText(shareLink);
        toast.success('Link copiado para a área de transferência');
    };

    const handleShare = async () => {
        if (sharedUsers.length === 0 && !linkGenerated) {
            toast.error('Adicione usuários ou gere um link de compartilhamento');
            return;
        }

        // If users were added, send to API
        if (sharedUsers.length > 0 && itemId && itemType) {
            try {
                const response = await fetch('/api/library/share', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    credentials: 'include',
                    body: JSON.stringify({
                        resource_id: itemId,
                        resource_type: itemType,
                        users: sharedUsers.map(u => ({
                            email: u.email,
                            permission: u.permission === 'admin' ? 'edit' : u.permission  // Map admin to edit for now
                        })),
                        groups: [],
                        message: null,
                    }),
                });

                if (!response.ok) {
                    throw new Error('Erro ao compartilhar recurso');
                }

                const data = await response.json();
                toast.success(data.message || `${itemType} compartilhado com sucesso!`);
            } catch (error) {
                console.error('Erro ao compartilhar:', error);
                toast.error('Erro ao compartilhar recurso');
                return;
            }
        } else {
            toast.success(`${itemType} compartilhado com sucesso!`);
        }

        onOpenChange(false);
    };

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="sm:max-w-2xl">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <Share2 className="h-5 w-5 text-primary" />
                        Compartilhar {itemType}: {itemName}
                    </DialogTitle>
                </DialogHeader>

                <div className="space-y-6 py-4">
                    {/* Add Users */}
                    <div className="space-y-3">
                        <Label className="text-sm font-semibold">Adicionar pessoas</Label>
                        <div className="flex gap-2">
                            <div className="relative flex-1">
                                <Mail className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
                                <Input
                                    placeholder="Digite o email..."
                                    value={email}
                                    onChange={(e) => setEmail(e.target.value)}
                                    onKeyDown={(e) => e.key === 'Enter' && handleAddUser()}
                                    className="pl-9"
                                />
                            </div>
                            <DropdownMenu>
                                <DropdownMenuTrigger asChild>
                                    <Button variant="outline" className="min-w-[120px]">
                                        {permissionLabels[defaultPermission]}
                                    </Button>
                                </DropdownMenuTrigger>
                                <DropdownMenuContent>
                                    {(Object.keys(permissionLabels) as PermissionLevel[]).map((perm) => (
                                        <DropdownMenuItem key={perm} onClick={() => setDefaultPermission(perm)}>
                                            <div>
                                                <div className="font-medium">{permissionLabels[perm]}</div>
                                                <div className="text-xs text-muted-foreground">
                                                    {permissionDescriptions[perm]}
                                                </div>
                                            </div>
                                        </DropdownMenuItem>
                                    ))}
                                </DropdownMenuContent>
                            </DropdownMenu>
                            <Button onClick={handleAddUser}>Adicionar</Button>
                        </div>
                    </div>

                    {/* Shared Users List */}
                    {sharedUsers.length > 0 && (
                        <div className="space-y-2">
                            <Label className="text-sm font-semibold">Pessoas com acesso</Label>
                            <div className="rounded-2xl border border-outline/30 bg-sand/20 p-3 space-y-2 max-h-[200px] overflow-y-auto">
                                {sharedUsers.map((user) => (
                                    <div
                                        key={user.email}
                                        className="flex items-center justify-between rounded-lg bg-white p-2 border border-outline/20"
                                    >
                                        <div className="flex items-center gap-2">
                                            <div className="h-8 w-8 rounded-full bg-primary/10 flex items-center justify-center">
                                                <Mail className="h-4 w-4 text-primary" />
                                            </div>
                                            <span className="text-sm font-medium">{user.email}</span>
                                        </div>
                                        <div className="flex items-center gap-2">
                                            <DropdownMenu>
                                                <DropdownMenuTrigger asChild>
                                                    <Button variant="ghost" size="sm" className="h-8 text-xs">
                                                        {permissionLabels[user.permission]}
                                                    </Button>
                                                </DropdownMenuTrigger>
                                                <DropdownMenuContent>
                                                    {(Object.keys(permissionLabels) as PermissionLevel[]).map((perm) => (
                                                        <DropdownMenuItem
                                                            key={perm}
                                                            onClick={() => handleChangePermission(user.email, perm)}
                                                        >
                                                            <div>
                                                                <div className="font-medium">{permissionLabels[perm]}</div>
                                                                <div className="text-xs text-muted-foreground">
                                                                    {permissionDescriptions[perm]}
                                                                </div>
                                                            </div>
                                                        </DropdownMenuItem>
                                                    ))}
                                                </DropdownMenuContent>
                                            </DropdownMenu>
                                            <Button
                                                variant="ghost"
                                                size="icon"
                                                className="h-8 w-8 text-muted-foreground hover:text-destructive"
                                                onClick={() => handleRemoveUser(user.email)}
                                            >
                                                <X className="h-4 w-4" />
                                            </Button>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Share Link */}
                    <div className="space-y-3">
                        <Label className="text-sm font-semibold">Link de compartilhamento</Label>
                        {!linkGenerated ? (
                            <Button
                                variant="outline"
                                className="w-full gap-2"
                                onClick={handleGenerateLink}
                            >
                                <LinkIcon className="h-4 w-4" />
                                Gerar link de compartilhamento
                            </Button>
                        ) : (
                            <div className="flex gap-2">
                                <Input value={shareLink} readOnly className="bg-sand/30" />
                                <Button variant="outline" size="icon" onClick={handleCopyLink}>
                                    <Copy className="h-4 w-4" />
                                </Button>
                            </div>
                        )}
                        <p className="text-xs text-muted-foreground">
                            Qualquer pessoa com o link poderá visualizar este {itemType}
                        </p>
                    </div>
                </div>

                <DialogFooter>
                    <Button variant="outline" onClick={() => onOpenChange(false)}>
                        Cancelar
                    </Button>
                    <Button onClick={handleShare}>Compartilhar</Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
