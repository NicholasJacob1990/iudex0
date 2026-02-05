'use client';

import { useState } from 'react';
import {
  ChevronRight,
  ChevronDown,
  Folder,
  FolderOpen,
  FolderPlus,
  Home,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { ScrollArea } from '@/components/ui/scroll-area';
import { cn } from '@/lib/utils';
import type { FolderNode } from '../hooks/use-corpus';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface FolderTreeProps {
  folders: FolderNode[];
  selectedPath: string | null;
  onSelectFolder: (path: string | null) => void;
  onCreateFolder?: (path: string) => void;
  rootDocumentCount?: number;
}

// ---------------------------------------------------------------------------
// FolderTreeItem
// ---------------------------------------------------------------------------

function FolderTreeItem({
  node,
  depth,
  selectedPath,
  onSelectFolder,
  expandedPaths,
  toggleExpanded,
}: {
  node: FolderNode;
  depth: number;
  selectedPath: string | null;
  onSelectFolder: (path: string) => void;
  expandedPaths: Set<string>;
  toggleExpanded: (path: string) => void;
}) {
  const isExpanded = expandedPaths.has(node.path);
  const isSelected = selectedPath === node.path;
  const hasChildren = node.children.length > 0;

  return (
    <div>
      <button
        className={cn(
          'flex w-full items-center gap-1.5 rounded-lg px-2 py-1.5 text-left text-sm transition-colors hover:bg-muted/50',
          isSelected && 'bg-primary/10 text-primary font-medium'
        )}
        style={{ paddingLeft: `${depth * 16 + 8}px` }}
        onClick={() => onSelectFolder(node.path)}
      >
        {hasChildren ? (
          <button
            className="shrink-0 p-0.5 hover:bg-muted rounded"
            onClick={(e) => {
              e.stopPropagation();
              toggleExpanded(node.path);
            }}
          >
            {isExpanded ? (
              <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
            ) : (
              <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
            )}
          </button>
        ) : (
          <span className="w-5" />
        )}
        {isExpanded || isSelected ? (
          <FolderOpen className="h-4 w-4 shrink-0 text-primary" />
        ) : (
          <Folder className="h-4 w-4 shrink-0 text-muted-foreground" />
        )}
        <span className="truncate flex-1">{node.name}</span>
        {node.document_count > 0 && (
          <span className="text-[10px] text-muted-foreground tabular-nums">
            {node.document_count}
          </span>
        )}
      </button>

      {isExpanded && hasChildren && (
        <div>
          {node.children.map((child) => (
            <FolderTreeItem
              key={child.path}
              node={child}
              depth={depth + 1}
              selectedPath={selectedPath}
              onSelectFolder={onSelectFolder}
              expandedPaths={expandedPaths}
              toggleExpanded={toggleExpanded}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// CreateFolderDialog
// ---------------------------------------------------------------------------

function CreateFolderDialog({
  open,
  onOpenChange,
  onConfirm,
  parentPath,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: (path: string) => void;
  parentPath: string | null;
}) {
  const [folderName, setFolderName] = useState('');

  const handleCreate = () => {
    const trimmed = folderName.trim();
    if (!trimmed) return;

    const fullPath = parentPath ? `${parentPath}/${trimmed}` : trimmed;
    onConfirm(fullPath);
    setFolderName('');
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[380px]">
        <DialogHeader>
          <DialogTitle>Nova Pasta</DialogTitle>
          <DialogDescription>
            {parentPath
              ? `Criar sub-pasta em "${parentPath}"`
              : 'Criar pasta na raiz do projeto'}
          </DialogDescription>
        </DialogHeader>
        <div className="py-4">
          <Input
            placeholder="Nome da pasta"
            value={folderName}
            onChange={(e) => setFolderName(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleCreate()}
            className="rounded-xl"
            autoFocus
          />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} className="rounded-full">
            Cancelar
          </Button>
          <Button onClick={handleCreate} disabled={!folderName.trim()} className="rounded-full">
            Criar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// CorpusFolderTree (exported)
// ---------------------------------------------------------------------------

export function CorpusFolderTree({
  folders,
  selectedPath,
  onSelectFolder,
  onCreateFolder,
  rootDocumentCount = 0,
}: FolderTreeProps) {
  const [expandedPaths, setExpandedPaths] = useState<Set<string>>(new Set());
  const [createDialogOpen, setCreateDialogOpen] = useState(false);

  const toggleExpanded = (path: string) => {
    setExpandedPaths((prev) => {
      const next = new Set(prev);
      if (next.has(path)) {
        next.delete(path);
      } else {
        next.add(path);
      }
      return next;
    });
  };

  const handleCreateFolder = (path: string) => {
    onCreateFolder?.(path);
  };

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-3 py-2 border-b">
        <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Pastas
        </p>
        {onCreateFolder && (
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6 rounded-full"
            onClick={() => setCreateDialogOpen(true)}
            title="Nova pasta"
          >
            <FolderPlus className="h-3.5 w-3.5" />
          </Button>
        )}
      </div>

      <ScrollArea className="flex-1">
        <div className="py-1">
          {/* Root item */}
          <button
            className={cn(
              'flex w-full items-center gap-1.5 rounded-lg px-2 py-1.5 text-left text-sm transition-colors hover:bg-muted/50',
              selectedPath === null && 'bg-primary/10 text-primary font-medium'
            )}
            onClick={() => onSelectFolder(null)}
          >
            <span className="w-5" />
            <Home className="h-4 w-4 shrink-0" />
            <span className="truncate flex-1">Todos os documentos</span>
            {rootDocumentCount > 0 && (
              <span className="text-[10px] text-muted-foreground tabular-nums">
                {rootDocumentCount}
              </span>
            )}
          </button>

          {/* Folder tree */}
          {folders.map((folder) => (
            <FolderTreeItem
              key={folder.path}
              node={folder}
              depth={0}
              selectedPath={selectedPath}
              onSelectFolder={onSelectFolder}
              expandedPaths={expandedPaths}
              toggleExpanded={toggleExpanded}
            />
          ))}

          {folders.length === 0 && (
            <div className="px-3 py-6 text-center">
              <Folder className="h-8 w-8 text-muted-foreground/30 mx-auto mb-2" />
              <p className="text-xs text-muted-foreground">Nenhuma pasta</p>
            </div>
          )}
        </div>
      </ScrollArea>

      {onCreateFolder && (
        <CreateFolderDialog
          open={createDialogOpen}
          onOpenChange={setCreateDialogOpen}
          onConfirm={handleCreateFolder}
          parentPath={selectedPath}
        />
      )}
    </div>
  );
}
