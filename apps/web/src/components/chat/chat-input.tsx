'use client';

import React, { useState, useRef, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import {
  Send,
  Sparkles,
  Paperclip,
  PanelLeftClose,
  PanelLeftOpen,
  Columns2,
  Bookmark,
  Minimize2,
  Workflow,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { SlashCommandMenu, type SystemCommand } from './slash-command-menu';
import { AtCommandMenu } from './at-command-menu';
import type { PredefinedPrompt } from '@/data/prompts';
import type { CustomPrompt } from '@/components/dashboard/prompt-customization';
import { useContextStore } from '@/stores/context-store';
import { useCanvasStore } from '@/stores';
import apiClient from '@/lib/api-client';
import { useChatStore } from '@/stores/chat-store';
import { toast } from 'sonner';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { ModelSelector } from './model-selector';
import { SourcesBadge } from '@/components/chat/sources-badge';
import { DeepResearchButton } from '@/components/chat/deep-research-button';
import { ContextUsageBar } from '@/components/chat/context-usage-bar';
import { ModelParamsPopover } from '@/components/chat/model-params-popover';
import { TemplatePopover } from '@/components/chat/template-popover';
import { WorkflowPickerModal } from '@/components/library/workflow-picker-modal';

type AnyPrompt = PredefinedPrompt | CustomPrompt | SystemCommand;

interface ChatInputProps {
  onSend: (content: string) => void;
  disabled?: boolean;
  placeholder?: string;
  extraActions?: React.ReactNode;
}

export function ChatInput({ onSend, disabled, placeholder, extraActions }: ChatInputProps) {
  const [content, setContent] = useState('');
  const [style, setStyle] = useState('Formal');
  const [showSlashMenu, setShowSlashMenu] = useState(false);
  const [showAtMenu, setShowAtMenu] = useState(false);
  const [workflowPickerOpen, setWorkflowPickerOpen] = useState(false);
  const [textareaExpanded, setTextareaExpanded] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const DEFAULT_TEXTAREA_MIN_H = 66;
  const fileInputRef = useRef<HTMLInputElement>(null);
  const { setActiveTab, addItem, items: contextItems } = useContextStore();
  const {
    chatMode,
    selectedModels,
    setSelectedModels,
    setChatMode,
    setShowMultiModelComparator,
  } = useChatStore();

  const DEFAULT_COMPARE_MODELS = ['gpt-5.2', 'claude-4.5-sonnet', 'gemini-3-flash'];

  const handleCompareToggle = (enabled: boolean) => {
    if (enabled) {
      // Ensure 2+ models selected for a real comparison
      const nextModels =
        selectedModels.length >= 2
          ? selectedModels
          : selectedModels.length === 1
            ? [
                selectedModels[0],
                DEFAULT_COMPARE_MODELS.find((m) => m !== selectedModels[0]) || 'gpt-5.2',
              ]
            : DEFAULT_COMPARE_MODELS.slice(0, 3);

      setSelectedModels(nextModels);
      setShowMultiModelComparator(true);
      setChatMode('multi-model');
      toast.success('Comparar modelos ativado');
      return;
    }

    setChatMode('standard');
    toast.info('Comparar modelos desativado');
  };

  const selectedText = useCanvasStore((state) => state.selectedText);
  const pendingAction = useCanvasStore((state) => state.pendingAction);
  const clearSelectedText = useCanvasStore((state) => state.clearSelectedText);
  const setSelectedText = useCanvasStore((state) => state.setSelectedText);

  const prefill = (text: string) => {
    setContent(text);
    setShowSlashMenu(false);
    setShowAtMenu(false);
    textareaRef.current?.focus();
  };

  useEffect(() => {
    try {
      const pendingSkillCreatorPrompt = window.sessionStorage.getItem('iudex.skillCreator.prefill');
      const text = String(pendingSkillCreatorPrompt || '').trim();
      if (text) {
        prefill(text);
        window.sessionStorage.removeItem('iudex.skillCreator.prefill');
      }
    } catch {
      // Ignore prefill storage failures.
    }

    const handler = (event: Event) => {
      const detail = (event as CustomEvent<{ text?: string }>).detail;
      const text = String(detail?.text || '').trim();
      if (!text) return;
      prefill(text);
    };
    window.addEventListener('minuta:prefill-chat', handler as EventListener);
    return () => window.removeEventListener('minuta:prefill-chat', handler as EventListener);
  }, []);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }

    if (e.key === 'Escape') {
      setShowSlashMenu(false);
      setShowAtMenu(false);
    }
  };

  const handleAttachClick = () => {
    setActiveTab('files');
    fileInputRef.current?.click();
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    try {
      const response = await apiClient.uploadDocument(file, {});
      const newItem = {
        id: response.id || Math.random().toString(36).slice(2),
        type: 'file' as const,
        name: file.name,
        meta: response?.doc_metadata?.ocr_applied ? 'OCR aplicado' : undefined,
      };
      addItem(newItem);

      const { items } = useContextStore.getState();
      useChatStore.getState().setContext([...items, newItem]);
      toast.success('Arquivo anexado ao contexto.');
    } catch (error) {
      console.error('Upload failed:', error);
      toast.error('Erro ao anexar documento.');
    } finally {
      e.target.value = '';
    }
  };

  const handleSend = () => {
    if (!content.trim() || disabled) return;

    // Include canvas context if available
    onSend(content);
    setContent('');
    setShowSlashMenu(false);
    setShowAtMenu(false);
  };

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const value = e.target.value;
    setContent(value);

    // Slash menu logic
    if (value.endsWith('/')) {
      setShowSlashMenu(true);
      setShowAtMenu(false);
    } else if (value === '' || (!value.includes('/') && showSlashMenu)) {
      setShowSlashMenu(false);
    }

    // At menu logic
    if (value.endsWith('@')) {
      setShowAtMenu(true);
      setShowSlashMenu(false);
    } else if (value === '' || (!value.includes('@') && showAtMenu)) {
      setShowAtMenu(false);
    }
  };

  const handleSelectPrompt = (prompt: AnyPrompt) => {
    // Check if it's a system command
    if ('action' in prompt) {
      const action = prompt.action as string;
      if (action.startsWith('set-model:')) {
        const modelId = action.split(':')[1];
        setSelectedModels([modelId]);
        setChatMode('standard');
        toast.success(`Modelo alterado para ${prompt.name.replace('Mudar para ', '')}`);
      } else if (action === 'set-mode:multi-model') {
        setChatMode('multi-model');
        // Select default trio if needed, or keep selection if > 1
        toast.success('Modo Multi-Modelo ativado');
      } else if (action === 'set-mode:standard') {
        setChatMode('standard');
        toast.success('Modo Padrão ativado');
      } else if (action.startsWith('navigate:')) {
        const target = action.replace('navigate:', '').trim();
        if (target) {
          window.location.href = target;
          return;
        }
      } else if (action.startsWith('insert-text:')) {
        const insertText = action.replace('insert-text:', '');
        const nextContent = content.endsWith('/') ? content.slice(0, -1) + insertText : insertText;
        setContent(nextContent);
        setShowSlashMenu(false);
        textareaRef.current?.focus();
        return;
      }
      setContent(''); // Clear the slash command
      setShowSlashMenu(false);
      textareaRef.current?.focus();
      return;
    }

    const newContent = content.endsWith('/')
      ? content.slice(0, -1) + prompt.template
      : content + prompt.template;

    setContent(newContent);
    setShowSlashMenu(false);
    textareaRef.current?.focus();
  };

  const handleSelectAt = (value: string, label: string) => {
    // If value contains formatting like @[Name](id:type), use it directly
    // Otherwise use format @Label
    const insertValue = value.startsWith('@') ? value : `@${label}`;

    const newContent = content.endsWith('@')
      ? content.slice(0, -1) + insertValue + ' '
      : content + insertValue + ' ';

    setContent(newContent);
    setShowAtMenu(false);
    textareaRef.current?.focus();
  };

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`;
    }
  }, [content]);

  return (
    <div className="relative">
      {showSlashMenu && (
        <SlashCommandMenu onSelect={handleSelectPrompt} onClose={() => setShowSlashMenu(false)} />
      )}

      {showAtMenu && (
        <AtCommandMenu onSelect={handleSelectAt} onClose={() => setShowAtMenu(false)} />
      )}

      <div className="group relative flex flex-col gap-1.5 rounded-2xl border border-slate-200/80 bg-white p-2 shadow-sm transition-all focus-within:border-emerald-400/70 focus-within:ring-2 focus-within:ring-emerald-400/20 dark:border-slate-700 dark:bg-slate-900/95">
        {/* Context Banner - shows when text is selected from Canvas */}
        {selectedText && (
          <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/10 px-2 py-1.5 text-xs">
            <div className="flex items-center gap-2">
              <Sparkles className="h-3 w-3 text-emerald-600" />
              <span className="text-emerald-700 font-medium">
                {pendingAction === 'improve'
                  ? 'Melhorando'
                  : pendingAction === 'shorten'
                    ? 'Resumindo'
                    : 'Contexto'}
                :
              </span>
              <span className="text-muted-foreground truncate flex-1">
                {'"'}
                {selectedText.slice(0, 60)}
                {selectedText.length > 60 ? '...' : ''}
                {'"'}
              </span>
              <Button
                variant="ghost"
                size="sm"
                className="h-5 w-5 p-0 text-muted-foreground hover:text-destructive"
                onClick={clearSelectedText}
              >
                ×
              </Button>
            </div>

            {/* Quick actions (MinutaIA-style affordance): prefill prompt for selected text */}
            <div className="mt-2 flex flex-wrap gap-1">
              {[
                {
                  id: 'rewrite',
                  label: 'Reescrever',
                  prompt: `Reescreva o trecho selecionado mantendo o sentido e melhorando clareza e coesão.`,
                },
                {
                  id: 'shorten',
                  label: 'Enxugar',
                  prompt: `Enxugue o trecho selecionado, removendo redundâncias e mantendo o conteúdo essencial.`,
                },
                {
                  id: 'formalize',
                  label: 'Formalizar',
                  prompt: `Formalize o trecho selecionado em linguagem jurídica adequada, mantendo a objetividade.`,
                },
                {
                  id: 'ground',
                  label: 'Fundamentar',
                  prompt: `Inclua fundamentação jurídica no trecho selecionado (base legal e argumentos), sem inventar fatos. Se faltar contexto, pergunte antes.`,
                },
                {
                  id: 'ementa',
                  label: 'Ementa',
                  prompt: `Crie uma ementa/assunto em 2–3 linhas a partir do trecho selecionado.`,
                },
                {
                  id: 'verify',
                  label: 'Checar citações',
                  prompt: `Verifique e corrija eventuais citações jurídicas no trecho selecionado. Se alguma referência for incerta, marque como "verificar".`,
                },
              ].map((action) => (
                <button
                  key={action.id}
                  type="button"
                  onClick={() => {
                    setSelectedText(selectedText, action.id as any, null, null);
                    prefill(action.prompt);
                  }}
                  className="rounded-full border border-emerald-200 bg-white px-2 py-1 text-[10px] font-semibold text-emerald-700 hover:bg-emerald-50 dark:border-emerald-700/50 dark:bg-slate-900 dark:text-emerald-300 dark:hover:bg-emerald-900/30"
                >
                  {action.label}
                </button>
              ))}
              <button
                type="button"
                onClick={() => {
                  const text = `Edite o trecho selecionado conforme minha instrução a seguir:\n\n`;
                  prefill(text);
                }}
                className="rounded-full border border-slate-200 bg-white px-2 py-1 text-[10px] font-semibold text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800"
              >
                Instrução livre
              </button>
            </div>
          </div>
        )}
        <div className="relative">
          <textarea
            ref={textareaRef}
            value={content}
            onChange={handleChange}
            onKeyDown={handleKeyDown}
            onMouseUp={() => {
              if (textareaRef.current && textareaRef.current.offsetHeight > DEFAULT_TEXTAREA_MIN_H + 20) {
                setTextareaExpanded(true);
              }
            }}
            placeholder={
              placeholder ||
              "Descreva a minuta que você precisa... (Digite '/' para prompts, '@' para contexto)"
            }
            className={cn(
              'w-full resize-y bg-transparent px-3 py-2 text-[15px] placeholder:text-muted-foreground/70 focus:outline-none disabled:opacity-50',
              `min-h-[${DEFAULT_TEXTAREA_MIN_H}px]`,
              'max-h-[60vh]'
            )}
            style={{ minHeight: `${DEFAULT_TEXTAREA_MIN_H}px` }}
            disabled={disabled}
            rows={1}
            data-testid="chat-input"
          />
          {textareaExpanded && (
            <button
              type="button"
              onClick={() => {
                setTextareaExpanded(false);
                if (textareaRef.current) {
                  textareaRef.current.style.height = 'auto';
                  textareaRef.current.style.height = `${Math.max(DEFAULT_TEXTAREA_MIN_H, textareaRef.current.scrollHeight)}px`;
                }
              }}
              className="absolute right-1 top-1 flex h-5 w-5 items-center justify-center rounded bg-slate-100/80 text-slate-400 transition-colors hover:bg-slate-200/80 hover:text-slate-600 dark:bg-slate-800/80 dark:text-slate-500 dark:hover:bg-slate-700 dark:hover:text-slate-300"
              title="Restaurar tamanho padrão"
            >
              <Minimize2 className="h-3 w-3" />
            </button>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-1.5 px-1.5 pb-0.5">
          <div className="flex flex-wrap items-center gap-0.5 min-w-0">
            {/* Compare models toggle - minimal icon */}
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    type="button"
                    onClick={() => handleCompareToggle(chatMode !== 'multi-model')}
                    className={cn(
                      'flex items-center justify-center h-7 w-7 rounded-lg transition-colors',
                      chatMode === 'multi-model'
                        ? 'bg-amber-500/15 text-amber-600 border border-amber-300'
                        : 'text-muted-foreground/60 border border-transparent hover:bg-slate-100 hover:text-muted-foreground dark:hover:bg-slate-800'
                    )}
                  >
                    <Columns2 className="h-3.5 w-3.5" />
                  </button>
                </TooltipTrigger>
                <TooltipContent side="top" className="text-xs">
                  {chatMode === 'multi-model' ? 'Desativar comparação' : 'Comparar modelos (2–3 respostas)'}
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>

            <ModelSelector />

            <TemplatePopover />

            {/* Canvas Toggle */}
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    type="button"
                    onClick={() => {
                      const canvas = useCanvasStore.getState();
                      if (canvas.state === 'hidden') {
                        canvas.showCanvas();
                        canvas.setActiveTab('editor');
                      } else {
                        canvas.hideCanvas();
                      }
                    }}
                    className={cn(
                      'flex items-center justify-center h-7 w-7 rounded-lg transition-colors',
                      useCanvasStore((s) => s.state) !== 'hidden'
                        ? 'bg-indigo-500/15 text-indigo-600 border border-indigo-300'
                        : 'text-muted-foreground/60 border border-transparent hover:bg-slate-100 hover:text-muted-foreground dark:hover:bg-slate-800'
                    )}
                  >
                    {useCanvasStore((s) => s.state) !== 'hidden' ? (
                      <PanelLeftClose className="h-3.5 w-3.5" />
                    ) : (
                      <PanelLeftOpen className="h-3.5 w-3.5" />
                    )}
                  </button>
                </TooltipTrigger>
                <TooltipContent side="top" className="text-xs">
                  {useCanvasStore((s) => s.state) !== 'hidden' ? 'Fechar editor' : 'Abrir editor'}
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>

            {/* Sources & Research Controls - New unified components */}
            <div className="mx-0.5 h-4 w-[1px] bg-slate-200 dark:bg-slate-700" />

            {/* SourcesBadge - unified source selector (replaces web search toggle, MCP, RAG scope) */}
            <SourcesBadge />

            {/* DeepResearchButton - deep research controls */}
            <DeepResearchButton />

            <ModelParamsPopover />

            <div className="mx-0.5 h-4 w-[1px] bg-slate-200 dark:bg-slate-700" />


            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant='ghost'
                    size='icon'
                    className='h-7 w-7 rounded-full text-slate-500 hover:bg-slate-100 hover:text-slate-700 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-200'
                    onClick={() => setWorkflowPickerOpen(true)}
                    type='button'
                    title='Executar workflow'
                  >
                    <Workflow className='h-3.5 w-3.5' />
                  </Button>
                </TooltipTrigger>
                <TooltipContent side='top' className='text-xs'>
                  Executar workflow
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7 rounded-full text-slate-500 hover:bg-slate-100 hover:text-slate-700 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-200"
              onClick={handleAttachClick}
              type="button"
              title="Anexar arquivo"
            >
              <Paperclip className="h-3.5 w-3.5" />
            </Button>

            {/* Prompts salvos */}
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon"
                    className={cn(
                      'h-7 w-7 rounded-full transition-colors',
                      showSlashMenu
                        ? 'text-amber-600 bg-amber-500/10'
                        : 'text-slate-500 hover:bg-slate-100 hover:text-slate-700 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-200'
                    )}
                    onClick={() => setShowSlashMenu(!showSlashMenu)}
                    type="button"
                  >
                    <Bookmark className="h-3.5 w-3.5" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent side="top" className="text-xs">
                  Prompts salvos (ou digite /)
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          </div>

          {/* Extra actions (slot for page-specific controls) */}
          {extraActions}

          {/* Context bar + Send */}
          <div className="ml-auto flex items-center gap-1.5">
            <ContextUsageBar compact />
            <Button
              onClick={handleSend}
              disabled={!content.trim() || disabled}
              size="icon"
              className={cn(
                'h-7 w-7 rounded-lg transition-all',
                content.trim()
                  ? 'bg-emerald-600 text-white hover:bg-emerald-500 shadow-lg shadow-emerald-500/20'
                  : 'bg-slate-100 text-slate-400 hover:bg-slate-100 dark:bg-slate-800 dark:text-slate-500 dark:hover:bg-slate-800'
              )}
              data-testid="chat-send"
            >
              <Send className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </div>
      <WorkflowPickerModal
        open={workflowPickerOpen}
        onClose={() => setWorkflowPickerOpen(false)}
        runInput={content.trim() || undefined}
      />
      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf,.docx,.doc,.txt,.md,.rtf,.odt,.html,.htm,.zip,.png,.jpg,.jpeg,.gif,.bmp,.tiff,.tif"
        className="hidden"
        onChange={handleFileChange}
      />
      {/* Ambient Glow */}
      <div className="pointer-events-none absolute -inset-px -z-10 rounded-2xl bg-gradient-to-r from-emerald-400/20 via-emerald-200/20 to-emerald-500/20 opacity-0 blur-xl transition-opacity duration-500 group-focus-within:opacity-100" />
    </div>
  );
}
