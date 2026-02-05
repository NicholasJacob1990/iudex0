'use client';

import { useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useQueryClient } from '@tanstack/react-query';
import { prefetchFns } from '@/lib/prefetch';
import {
  BookCheck,
  Copy,
  MoreHorizontal,
  Share2,
  Trash2,
  Users,
  Clock,
  FileText,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { cn } from '@/lib/utils';
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
import { type Playbook, AREA_LABELS, PARTY_PERSPECTIVE_LABELS } from '../hooks';

interface PlaybookCardProps {
  playbook: Playbook;
  onDelete: (id: string) => void;
  onDuplicate: (playbook: Playbook) => void;
  onShare: (playbook: Playbook) => void;
}

const statusConfig: Record<string, { label: string; className: string }> = {
  ativo: {
    label: 'Ativo',
    className: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
  },
  rascunho: {
    label: 'Rascunho',
    className: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400',
  },
  arquivado: {
    label: 'Arquivado',
    className: 'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400',
  },
};

export function PlaybookCard({ playbook, onDelete, onDuplicate, onShare }: PlaybookCardProps) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  const handlePrefetch = useCallback(() => {
    try { prefetchFns.playbookDetail(queryClient, playbook.id); } catch { /* silencioso */ }
  }, [queryClient, playbook.id]);

  const status = statusConfig[playbook.status] || statusConfig.rascunho;

  return (
    <div
      className="group relative flex flex-col gap-3 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-5 transition-all duration-200 hover:border-indigo-300 dark:hover:border-indigo-700 hover:shadow-md cursor-pointer"
      onClick={() => router.push(`/playbooks/${playbook.id}`)}
      onMouseEnter={handlePrefetch}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <div className="h-10 w-10 rounded-lg bg-indigo-100 dark:bg-indigo-500/20 flex items-center justify-center shrink-0">
            <BookCheck className="h-5 w-5 text-indigo-600 dark:text-indigo-400" />
          </div>
          <div className="min-w-0">
            <h3 className="font-semibold text-slate-800 dark:text-slate-200 truncate">
              {playbook.name}
            </h3>
            <p className="text-xs text-slate-500 dark:text-slate-400 truncate mt-0.5">
              {playbook.description}
            </p>
          </div>
        </div>

        <DropdownMenu>
          <DropdownMenuTrigger asChild onClick={(e) => e.stopPropagation()}>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 opacity-0 group-hover:opacity-100 transition-opacity shrink-0"
            >
              <MoreHorizontal className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" onClick={(e) => e.stopPropagation()}>
            <DropdownMenuItem onClick={() => onDuplicate(playbook)}>
              <Copy className="mr-2 h-4 w-4" />
              Duplicar
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => onShare(playbook)}>
              <Share2 className="mr-2 h-4 w-4" />
              Compartilhar
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              onClick={() => setShowDeleteConfirm(true)}
              className="text-red-600 dark:text-red-400"
            >
              <Trash2 className="mr-2 h-4 w-4" />
              Excluir
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      {/* Badges */}
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="secondary" className="text-[10px] font-medium">
          {AREA_LABELS[playbook.area] || playbook.area}
        </Badge>
        <Badge className={cn('text-[10px] font-medium border-0', status.className)}>
          {status.label}
        </Badge>
        {playbook.party_perspective && playbook.party_perspective !== 'neutro' && (
          <Badge
            variant="outline"
            className="text-[10px] font-medium border-indigo-200 text-indigo-600 dark:border-indigo-700 dark:text-indigo-400"
          >
            {PARTY_PERSPECTIVE_LABELS[playbook.party_perspective]}
          </Badge>
        )}
        {playbook.is_template && (
          <Badge variant="outline" className="text-[10px] font-medium">
            Template
          </Badge>
        )}
      </div>

      {/* Footer info */}
      <div className="flex items-center gap-4 text-[11px] text-slate-400 dark:text-slate-500 mt-auto pt-2 border-t border-slate-100 dark:border-slate-800">
        <span className="flex items-center gap-1">
          <FileText className="h-3 w-3" />
          {playbook.rule_count} regra{playbook.rule_count !== 1 ? 's' : ''}
        </span>
        <span className="flex items-center gap-1">
          <Clock className="h-3 w-3" />
          {new Date(playbook.updated_at).toLocaleDateString('pt-BR')}
        </span>
        {playbook.is_shared && (
          <span className="flex items-center gap-1">
            <Users className="h-3 w-3" />
            Compartilhado
          </span>
        )}
      </div>

      <AlertDialog open={showDeleteConfirm} onOpenChange={setShowDeleteConfirm}>
        <AlertDialogContent onClick={(e) => e.stopPropagation()}>
          <AlertDialogHeader>
            <AlertDialogTitle>Excluir playbook</AlertDialogTitle>
            <AlertDialogDescription>
              Tem certeza que deseja excluir &quot;{playbook.name}&quot;? Esta acao nao pode ser desfeita.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                onDelete(playbook.id);
                setShowDeleteConfirm(false);
              }}
              className="bg-red-600 hover:bg-red-500 text-white"
            >
              Excluir
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
