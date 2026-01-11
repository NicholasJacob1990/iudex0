'use client';

import { useState } from 'react';
import { Folder, FolderOpen, ChevronRight, ChevronDown, Plus, MoreVertical, Share2, Users } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';

interface FolderNode {
    id: string;
    name: string;
    children?: FolderNode[];
    isShared?: boolean;
}

const mockFolders: FolderNode[] = [
    {
        id: '1',
        name: 'Processos Trabalhistas',
        children: [
            { id: '1-1', name: 'Reclamações' },
            { id: '1-2', name: 'Recursos' },
        ],
    },
    {
        id: '2',
        name: 'Contratos',
        children: [
            { id: '2-1', name: 'Locação' },
            { id: '2-2', name: 'Prestação de Serviços' },
        ],
    },
    { id: '3', name: 'Pareceres' },
];

const mockSharedFolders: FolderNode[] = [
    { id: 's1', name: 'Compartilhado - Equipe', isShared: true },
    { id: 's2', name: 'Compartilhado - Cliente X', isShared: true },
];

export function LibrarySidebar() {
    const [expandedFolders, setExpandedFolders] = useState<Set<string>>(new Set(['1', '2']));
    const [selectedFolder, setSelectedFolder] = useState<string | null>(null);
    const [isCreating, setIsCreating] = useState(false);
    const [newFolderName, setNewFolderName] = useState('');

    const toggleFolder = (folderId: string) => {
        const newExpanded = new Set(expandedFolders);
        if (newExpanded.has(folderId)) {
            newExpanded.delete(folderId);
        } else {
            newExpanded.add(folderId);
        }
        setExpandedFolders(newExpanded);
    };

    const handleCreateFolder = () => {
        if (!newFolderName.trim()) {
            toast.error('Digite um nome para a pasta');
            return;
        }
        toast.success(`Pasta "${newFolderName}" criada!`);
        setNewFolderName('');
        setIsCreating(false);
    };

    const handleFolderAction = (action: string, folderName: string) => {
        toast.info(`${action}: ${folderName}`);
    };

    const renderFolder = (folder: FolderNode, level: number = 0) => {
        const isExpanded = expandedFolders.has(folder.id);
        const hasChildren = folder.children && folder.children.length > 0;
        const isSelected = selectedFolder === folder.id;

        return (
            <div key={folder.id}>
                <div
                    className={cn(
                        "group flex items-center justify-between rounded-lg px-2 py-1.5 text-sm transition-colors cursor-pointer",
                        isSelected ? "bg-primary/10 text-primary font-semibold" : "hover:bg-sand/50 text-foreground"
                    )}
                    style={{ paddingLeft: `${level * 12 + 8}px` }}
                    onClick={() => setSelectedFolder(folder.id)}
                >
                    <div className="flex items-center gap-1.5 flex-1 min-w-0">
                        {hasChildren && (
                            <button
                                onClick={(e) => {
                                    e.stopPropagation();
                                    toggleFolder(folder.id);
                                }}
                                className="p-0.5 hover:bg-white/50 rounded"
                            >
                                {isExpanded ? (
                                    <ChevronDown className="h-3.5 w-3.5" />
                                ) : (
                                    <ChevronRight className="h-3.5 w-3.5" />
                                )}
                            </button>
                        )}
                        {!hasChildren && <div className="w-4" />}
                        {isExpanded ? (
                            <FolderOpen className="h-4 w-4 flex-shrink-0 text-primary" />
                        ) : (
                            <Folder className="h-4 w-4 flex-shrink-0 text-muted-foreground" />
                        )}
                        <span className="truncate">{folder.name}</span>
                        {folder.isShared && <Share2 className="h-3 w-3 text-blue-500 flex-shrink-0" />}
                    </div>
                    <DropdownMenu>
                        <DropdownMenuTrigger asChild onClick={(e) => e.stopPropagation()}>
                            <button className="opacity-0 group-hover:opacity-100 p-1 hover:bg-white rounded transition-opacity">
                                <MoreVertical className="h-3.5 w-3.5" />
                            </button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                            <DropdownMenuItem onClick={() => handleFolderAction('Criar subpasta', folder.name)}>
                                <Plus className="mr-2 h-4 w-4" />
                                Criar subpasta
                            </DropdownMenuItem>
                            <DropdownMenuItem onClick={() => handleFolderAction('Renomear', folder.name)}>
                                Renomear
                            </DropdownMenuItem>
                            <DropdownMenuItem onClick={() => handleFolderAction('Compartilhar', folder.name)}>
                                <Share2 className="mr-2 h-4 w-4" />
                                Compartilhar
                            </DropdownMenuItem>
                            <DropdownMenuItem
                                onClick={() => handleFolderAction('Excluir', folder.name)}
                                className="text-destructive"
                            >
                                Excluir
                            </DropdownMenuItem>
                        </DropdownMenuContent>
                    </DropdownMenu>
                </div>
                {isExpanded && hasChildren && (
                    <div>
                        {folder.children!.map((child) => renderFolder(child, level + 1))}
                    </div>
                )}
            </div>
        );
    };

    return (
        <div className="w-64 h-full flex flex-col rounded-3xl border border-white/70 bg-white/95 shadow-soft overflow-hidden">
            {/* Header */}
            <div className="p-4 border-b border-outline/20">
                <h3 className="font-display text-lg text-foreground mb-3">Pastas</h3>
                <Button
                    size="sm"
                    variant="outline"
                    className="w-full rounded-full gap-2 text-xs"
                    onClick={() => setIsCreating(true)}
                >
                    <Plus className="h-3 w-3" />
                    Nova Pasta
                </Button>
            </div>

            {/* Folder Tree */}
            <div className="flex-1 overflow-y-auto p-3 space-y-1">
                {/* New Folder Input */}
                {isCreating && (
                    <div className="mb-3 space-y-2">
                        <Input
                            placeholder="Nome da pasta"
                            value={newFolderName}
                            onChange={(e) => setNewFolderName(e.target.value)}
                            onKeyDown={(e) => {
                                if (e.key === 'Enter') handleCreateFolder();
                                if (e.key === 'Escape') setIsCreating(false);
                            }}
                            className="h-8 text-xs"
                            autoFocus
                        />
                        <div className="flex gap-2">
                            <Button size="sm" onClick={handleCreateFolder} className="flex-1 h-7 text-xs">
                                Criar
                            </Button>
                            <Button size="sm" variant="outline" onClick={() => setIsCreating(false)} className="flex-1 h-7 text-xs">
                                Cancelar
                            </Button>
                        </div>
                    </div>
                )}

                {/* Minha Biblioteca */}
                <div className="mb-4">
                    <div className="px-2 py-1 text-[10px] font-semibold uppercase text-muted-foreground">
                        Minha Biblioteca
                    </div>
                    {mockFolders.map((folder) => renderFolder(folder))}
                </div>

                {/* Compartilhados */}
                <div>
                    <div className="px-2 py-1 text-[10px] font-semibold uppercase text-muted-foreground flex items-center gap-1">
                        <Users className="h-3 w-3" />
                        Compartilhados
                    </div>
                    {mockSharedFolders.map((folder) => renderFolder(folder))}
                </div>
            </div>
        </div>
    );
}
