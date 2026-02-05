'use client';

import React, { useCallback, useEffect } from 'react';
import { BookCheck, ChevronDown, Loader2, X } from 'lucide-react';
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
import { useChatStore } from '@/stores';
import {
  usePlaybooks,
  usePlaybookPrompt,
  AREA_LABELS,
  type Playbook,
  type PlaybookArea,
} from '../hooks';
import { toast } from 'sonner';
import { RichTooltip } from '@/components/ui/rich-tooltip';

/**
 * PlaybookSelector — dropdown para selecionar um Playbook na pagina /minuta.
 *
 * Quando o usuario seleciona um playbook:
 * 1. Busca a lista de playbooks ativos (usePlaybooks)
 * 2. Ao selecionar, busca o prompt formatado (usePlaybookPrompt)
 * 3. Armazena no chat store (selectedPlaybookId/Name/Prompt)
 * 4. O prompt e injetado automaticamente nas chamadas de sendMessage/startLangGraphJob
 */
export function PlaybookSelector() {
  const {
    selectedPlaybookId,
    selectedPlaybookName,
    selectedPlaybookPrompt,
    setSelectedPlaybook,
    clearPlaybook,
  } = useChatStore();

  // Fetch all active playbooks for the dropdown
  const { data: playbooks, isLoading: isLoadingList } = usePlaybooks();

  // Fetch prompt when a playbook is selected
  const {
    data: promptText,
    isLoading: isLoadingPrompt,
    isError: isPromptError,
  } = usePlaybookPrompt(selectedPlaybookId);

  // When prompt is fetched, update the store
  useEffect(() => {
    if (selectedPlaybookId && promptText && !selectedPlaybookPrompt) {
      setSelectedPlaybook(selectedPlaybookId, selectedPlaybookName, promptText);
    }
  }, [selectedPlaybookId, selectedPlaybookName, promptText, selectedPlaybookPrompt, setSelectedPlaybook]);

  // Handle prompt fetch error
  useEffect(() => {
    if (isPromptError && selectedPlaybookId) {
      toast.error('Erro ao carregar regras do playbook');
    }
  }, [isPromptError, selectedPlaybookId]);

  const handleSelect = useCallback(
    (playbook: Playbook) => {
      if (playbook.id === selectedPlaybookId) {
        // Deselect
        clearPlaybook();
        toast.info('Playbook removido da revisao');
        return;
      }

      // Set the playbook; prompt will be fetched by the usePlaybookPrompt hook
      setSelectedPlaybook(playbook.id, playbook.name, null);
      toast.success(`Playbook "${playbook.name}" ativado`);
    },
    [selectedPlaybookId, setSelectedPlaybook, clearPlaybook]
  );

  const handleClear = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      clearPlaybook();
      toast.info('Playbook removido da revisao');
    },
    [clearPlaybook]
  );

  const activePlaybooks = (playbooks || []).filter(
    (p) => p.status === 'ativo' || p.status === 'rascunho'
  );

  const isActive = !!selectedPlaybookId;
  const isLoading = isLoadingPrompt && !!selectedPlaybookId;

  return (
    <DropdownMenu>
      <RichTooltip
        title="Playbook de Revisao"
        description={
          isActive
            ? `Playbook "${selectedPlaybookName}" ativo. As regras serao aplicadas na revisao do contrato.`
            : 'Selecione um Playbook para aplicar regras de revisao contratual durante o chat.'
        }
        badge={isActive ? 'Ativo' : undefined}
        icon={<BookCheck className="h-3.5 w-3.5" />}
      >
        <DropdownMenuTrigger asChild>
          <Button
            variant="ghost"
            size="sm"
            className={cn(
              'h-8 gap-1.5 rounded-lg text-xs font-medium transition-all',
              isActive
                ? 'bg-emerald-50 text-emerald-700 hover:bg-emerald-100 border border-emerald-200'
                : 'text-slate-600 hover:text-slate-900'
            )}
          >
            {isLoading ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <BookCheck className="h-3.5 w-3.5" />
            )}
            {isActive ? (
              <>
                <span className="max-w-[120px] truncate">{selectedPlaybookName}</span>
                <button
                  onClick={handleClear}
                  className="ml-0.5 rounded-full p-0.5 hover:bg-emerald-200 transition-colors"
                  title="Remover playbook"
                >
                  <X className="h-3 w-3" />
                </button>
              </>
            ) : (
              <>
                <span className="hidden sm:inline">Playbook</span>
                <ChevronDown className="h-3 w-3 opacity-50" />
              </>
            )}
          </Button>
        </DropdownMenuTrigger>
      </RichTooltip>

      <DropdownMenuContent align="start" className="w-72">
        <div className="px-3 py-2 border-b border-slate-100">
          <p className="text-xs font-medium text-slate-900">Selecionar Playbook</p>
          <p className="text-[11px] text-slate-500 mt-0.5">
            Regras serao aplicadas na revisao do contrato
          </p>
        </div>

        {isLoadingList ? (
          <div className="flex items-center justify-center py-6">
            <Loader2 className="h-4 w-4 animate-spin text-slate-400" />
            <span className="ml-2 text-xs text-slate-500">Carregando playbooks...</span>
          </div>
        ) : activePlaybooks.length === 0 ? (
          <div className="px-3 py-4 text-center">
            <p className="text-xs text-slate-500">Nenhum playbook disponivel</p>
            <p className="text-[11px] text-slate-400 mt-1">
              Crie um playbook na pagina de Playbooks
            </p>
          </div>
        ) : (
          <>
            {isActive && (
              <>
                <DropdownMenuItem
                  onClick={() => clearPlaybook()}
                  className="text-xs text-slate-500 gap-2"
                >
                  <X className="h-3.5 w-3.5" />
                  Remover playbook ativo
                </DropdownMenuItem>
                <DropdownMenuSeparator />
              </>
            )}
            {activePlaybooks.map((playbook) => (
              <DropdownMenuItem
                key={playbook.id}
                onClick={() => handleSelect(playbook)}
                className={cn(
                  'flex flex-col items-start gap-1 py-2.5 cursor-pointer',
                  playbook.id === selectedPlaybookId && 'bg-emerald-50'
                )}
              >
                <div className="flex items-center gap-2 w-full">
                  <BookCheck
                    className={cn(
                      'h-3.5 w-3.5 flex-shrink-0',
                      playbook.id === selectedPlaybookId
                        ? 'text-emerald-600'
                        : 'text-slate-400'
                    )}
                  />
                  <span className="text-xs font-medium truncate flex-1">
                    {playbook.name}
                  </span>
                  <div className="flex items-center gap-1 flex-shrink-0">
                    <Badge
                      variant="outline"
                      className="text-[10px] px-1.5 py-0"
                    >
                      {AREA_LABELS[playbook.area as PlaybookArea] || playbook.area}
                    </Badge>
                    <Badge
                      variant="outline"
                      className="text-[10px] px-1.5 py-0 text-slate-500"
                    >
                      {playbook.rule_count} regra{playbook.rule_count !== 1 ? 's' : ''}
                    </Badge>
                  </div>
                </div>
                {playbook.description && (
                  <p className="text-[11px] text-slate-500 pl-5.5 line-clamp-1">
                    {playbook.description}
                  </p>
                )}
              </DropdownMenuItem>
            ))}
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
