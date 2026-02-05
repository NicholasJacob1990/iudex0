'use client';

import { useState } from 'react';
import {
  ChevronDown,
  ChevronUp,
  GripVertical,
  Trash2,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
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
import {
  type PlaybookRule,
  SEVERITY_COLORS,
  SEVERITY_LABELS,
  REJECT_ACTION_LABELS,
} from '../hooks';

interface PlaybookRuleEditorProps {
  rule: PlaybookRule;
  onUpdate: (rule: Partial<PlaybookRule> & { id: string; playbook_id: string }) => void;
  onDelete: (ruleId: string) => void;
  dragHandleProps?: Record<string, unknown>;
}

export function PlaybookRuleEditor({
  rule,
  onUpdate,
  onDelete,
  dragHandleProps,
}: PlaybookRuleEditorProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  const severityBarColors: Record<string, string> = {
    baixa: 'bg-green-500',
    media: 'bg-yellow-500',
    alta: 'bg-orange-500',
    critica: 'bg-red-500',
  };

  return (
    <div
      className={cn(
        'group rounded-xl border transition-all duration-200',
        rule.is_active
          ? 'border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900'
          : 'border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/50 opacity-60'
      )}
    >
      {/* Severity indicator bar */}
      <div
        className={cn(
          'h-1 rounded-t-xl transition-colors',
          severityBarColors[rule.severity] || 'bg-slate-300'
        )}
      />

      {/* Header - always visible */}
      <div
        className="flex items-center gap-3 px-4 py-3 cursor-pointer"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        {/* Drag handle */}
        <div
          className="cursor-grab opacity-0 group-hover:opacity-50 hover:!opacity-100 transition-opacity"
          {...dragHandleProps}
          onClick={(e) => e.stopPropagation()}
        >
          <GripVertical className="h-4 w-4 text-slate-400" />
        </div>

        {/* Rule info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h4 className="font-medium text-sm text-slate-800 dark:text-slate-200 truncate">
              {rule.name}
            </h4>
            <Badge variant="outline" className="text-[10px] shrink-0">
              {rule.clause_type}
            </Badge>
            <Badge className={cn('text-[10px] border-0 shrink-0', SEVERITY_COLORS[rule.severity])}>
              {SEVERITY_LABELS[rule.severity]}
            </Badge>
          </div>
          {!isExpanded && (
            <p className="text-xs text-slate-500 dark:text-slate-400 truncate mt-0.5">
              {rule.preferred_position}
            </p>
          )}
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2 shrink-0">
          <div
            className="flex items-center gap-1.5"
            onClick={(e) => e.stopPropagation()}
          >
            <Switch
              checked={rule.is_active}
              onCheckedChange={(checked) =>
                onUpdate({ id: rule.id, playbook_id: rule.playbook_id, is_active: checked })
              }
              className="scale-75"
            />
            <span className="text-[10px] text-slate-400 hidden sm:block">
              {rule.is_active ? 'Ativa' : 'Inativa'}
            </span>
          </div>
          {isExpanded ? (
            <ChevronUp className="h-4 w-4 text-slate-400" />
          ) : (
            <ChevronDown className="h-4 w-4 text-slate-400" />
          )}
        </div>
      </div>

      {/* Expanded content */}
      {isExpanded && (
        <div className="px-4 pb-4 space-y-4 border-t border-slate-100 dark:border-slate-800 pt-4">
          {/* Preferred position */}
          <div>
            <label className="text-xs font-semibold text-slate-600 dark:text-slate-300 uppercase tracking-wider mb-1.5 block">
              Posicao Preferida
            </label>
            <div className="rounded-lg bg-green-50 dark:bg-green-900/10 border border-green-200 dark:border-green-800 p-3 text-sm text-slate-700 dark:text-slate-300">
              {rule.preferred_position}
            </div>
          </div>

          {/* Fallback positions */}
          <div>
            <label className="text-xs font-semibold text-slate-600 dark:text-slate-300 uppercase tracking-wider mb-1.5 block">
              Posicoes Alternativas ({rule.fallback_positions.length})
            </label>
            <div className="space-y-2">
              {rule.fallback_positions.map((pos, idx) => (
                <div
                  key={idx}
                  className="rounded-lg bg-yellow-50 dark:bg-yellow-900/10 border border-yellow-200 dark:border-yellow-800 p-3 text-sm text-slate-700 dark:text-slate-300"
                >
                  <span className="text-[10px] font-bold text-yellow-600 dark:text-yellow-400 mr-2">
                    ALT {idx + 1}
                  </span>
                  {pos}
                </div>
              ))}
              {rule.fallback_positions.length === 0 && (
                <p className="text-xs text-slate-400 italic">Nenhuma posicao alternativa definida</p>
              )}
            </div>
          </div>

          {/* Rejected positions */}
          <div>
            <label className="text-xs font-semibold text-slate-600 dark:text-slate-300 uppercase tracking-wider mb-1.5 block">
              Posicoes Rejeitadas ({rule.rejected_positions.length})
            </label>
            <div className="space-y-2">
              {rule.rejected_positions.map((pos, idx) => (
                <div
                  key={idx}
                  className="rounded-lg bg-red-50 dark:bg-red-900/10 border border-red-200 dark:border-red-800 p-3 text-sm text-slate-700 dark:text-slate-300"
                >
                  <span className="text-[10px] font-bold text-red-600 dark:text-red-400 mr-2">
                    REJ {idx + 1}
                  </span>
                  {pos}
                </div>
              ))}
              {rule.rejected_positions.length === 0 && (
                <p className="text-xs text-slate-400 italic">Nenhuma posicao rejeitada definida</p>
              )}
            </div>
          </div>

          {/* Action on reject + Guidance */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="text-xs font-semibold text-slate-600 dark:text-slate-300 uppercase tracking-wider mb-1.5 block">
                Acao ao Rejeitar
              </label>
              <div className="rounded-lg bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 p-3 text-sm text-slate-700 dark:text-slate-300">
                {REJECT_ACTION_LABELS[rule.reject_action]}
              </div>
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-600 dark:text-slate-300 uppercase tracking-wider mb-1.5 block">
                Severidade
              </label>
              <div className="rounded-lg bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 p-3 text-sm text-slate-700 dark:text-slate-300">
                <Badge className={cn('text-xs border-0', SEVERITY_COLORS[rule.severity])}>
                  {SEVERITY_LABELS[rule.severity]}
                </Badge>
              </div>
            </div>
          </div>

          {/* Guidance notes */}
          {rule.guidance_notes && (
            <div>
              <label className="text-xs font-semibold text-slate-600 dark:text-slate-300 uppercase tracking-wider mb-1.5 block">
                Notas de Orientacao
              </label>
              <div className="rounded-lg bg-blue-50 dark:bg-blue-900/10 border border-blue-200 dark:border-blue-800 p-3 text-sm text-slate-700 dark:text-slate-300 italic">
                {rule.guidance_notes}
              </div>
            </div>
          )}

          {/* Actions */}
          <div className="flex justify-end pt-2">
            <Button
              variant="ghost"
              size="sm"
              className="text-red-500 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-950 gap-1.5"
              onClick={(e) => {
                e.stopPropagation();
                setShowDeleteConfirm(true);
              }}
            >
              <Trash2 className="h-3.5 w-3.5" />
              Remover regra
            </Button>
          </div>
        </div>
      )}

      <AlertDialog open={showDeleteConfirm} onOpenChange={setShowDeleteConfirm}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Remover regra</AlertDialogTitle>
            <AlertDialogDescription>
              Tem certeza que deseja remover a regra &quot;{rule.name}&quot;? Esta acao nao pode ser desfeita.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                onDelete(rule.id);
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
