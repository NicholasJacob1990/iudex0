'use client';

import { useState, useRef, useEffect, useMemo } from 'react';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import {
  Send,
  Sparkles,
  ChevronDown,
  Paperclip,
  AtSign,
  Hash,
  Globe,
  Brain,
  Zap,
  BookOpen,
  PanelRight,
  FileText,
  ShieldCheck,
  SlidersHorizontal,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { SlashCommandMenu, type SystemCommand } from './slash-command-menu';
import { AtCommandMenu } from './at-command-menu';
import type { PredefinedPrompt } from '@/data/prompts';
import type { CustomPrompt } from '@/components/dashboard/prompt-customization';
import { useContextStore } from '@/stores/context-store';
import { useCanvasStore } from '@/stores';
import apiClient from '@/lib/api-client';
import { useChatStore } from '@/stores/chat-store';
import { getModelConfig, type ModelId } from '@/config/models';
import { toast } from 'sonner';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { ModelSelector } from './model-selector';
import { Slider } from '@/components/ui/slider';
import { useModelAttachmentLimits } from '@/lib/use-model-attachment-limits';

type AnyPrompt = PredefinedPrompt | CustomPrompt | SystemCommand;

interface ChatInputProps {
  onSend: (content: string) => void;
  disabled?: boolean;
  placeholder?: string;
}

export function ChatInput({ onSend, disabled, placeholder }: ChatInputProps) {
  const [content, setContent] = useState('');
  const [style, setStyle] = useState('Formal');
  const [showSlashMenu, setShowSlashMenu] = useState(false);
  const [showAtMenu, setShowAtMenu] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const { setActiveTab, addItem, items: contextItems } = useContextStore();
  const [attachmentAdvanced, setAttachmentAdvanced] = useState(false);
  const {
    chatMode,
    selectedModels,
    selectedModel,
    mcpToolCalling,
    setMcpToolCalling,
    mcpUseAllServers,
    setMcpUseAllServers,
    mcpServerLabels,
    setMcpServerLabels,
    webSearch,
    setWebSearch,
    multiQuery,
    setMultiQuery,
    breadthFirst,
    setBreadthFirst,
    searchMode,
    setSearchMode,
    perplexitySearchMode,
    setPerplexitySearchMode,
    perplexitySearchType,
    setPerplexitySearchType,
    perplexitySearchContextSize,
    setPerplexitySearchContextSize,
    perplexitySearchClassifier,
    setPerplexitySearchClassifier,
    perplexityDisableSearch,
    setPerplexityDisableSearch,
    perplexityStreamMode,
    setPerplexityStreamMode,
    perplexitySearchDomainFilter,
    setPerplexitySearchDomainFilter,
    perplexitySearchLanguageFilter,
    setPerplexitySearchLanguageFilter,
    perplexitySearchRecencyFilter,
    setPerplexitySearchRecencyFilter,
    perplexitySearchAfterDate,
    setPerplexitySearchAfterDate,
    perplexitySearchBeforeDate,
    setPerplexitySearchBeforeDate,
    perplexityLastUpdatedAfter,
    setPerplexityLastUpdatedAfter,
    perplexityLastUpdatedBefore,
    setPerplexityLastUpdatedBefore,
    perplexitySearchMaxResults,
    setPerplexitySearchMaxResults,
    perplexitySearchMaxTokens,
    setPerplexitySearchMaxTokens,
    perplexitySearchMaxTokensPerPage,
    setPerplexitySearchMaxTokensPerPage,
    perplexitySearchCountry,
    setPerplexitySearchCountry,
    perplexitySearchRegion,
    setPerplexitySearchRegion,
    perplexitySearchCity,
    setPerplexitySearchCity,
    perplexitySearchLatitude,
    setPerplexitySearchLatitude,
    perplexitySearchLongitude,
    setPerplexitySearchLongitude,
    perplexityReturnImages,
    setPerplexityReturnImages,
    perplexityReturnVideos,
    setPerplexityReturnVideos,
    researchPolicy,
    setResearchPolicy,
    denseResearch,
    setDenseResearch,
    deepResearchProvider,
    setDeepResearchProvider,
    deepResearchModel,
    setDeepResearchModel,
    deepResearchEffort,
    setDeepResearchEffort,
    deepResearchSearchFocus,
    setDeepResearchSearchFocus,
    deepResearchDomainFilter,
    setDeepResearchDomainFilter,
    deepResearchSearchAfterDate,
    setDeepResearchSearchAfterDate,
    deepResearchSearchBeforeDate,
    setDeepResearchSearchBeforeDate,
    deepResearchLastUpdatedAfter,
    setDeepResearchLastUpdatedAfter,
    deepResearchLastUpdatedBefore,
    setDeepResearchLastUpdatedBefore,
    deepResearchCountry,
    setDeepResearchCountry,
    deepResearchLatitude,
    setDeepResearchLatitude,
    deepResearchLongitude,
    setDeepResearchLongitude,
    reasoningLevel,
    setReasoningLevel,
    verbosity,
    setVerbosity,
    thinkingBudget,
    setThinkingBudget,
    modelOverrides,
    setModelOverride,
    setSelectedModels,
    setChatMode,
    setShowMultiModelComparator,
    ragAdvancedMode: advancedRagMode,
    setRagAdvancedMode: setAdvancedRagMode,
    adaptiveRouting,
    setAdaptiveRouting,
    cragGate,
    setCragGate,
    hydeEnabled,
    setHydeEnabled,
    graphRagEnabled,
    setGraphRagEnabled,
    argumentGraphEnabled,
    setArgumentGraphEnabled,
    graphHops,
    setGraphHops,
    ragScope,
    setRagScope,
    attachmentMode,
    setAttachmentMode,
    setPendingCanvasContext,
    thesis,
    setThesis,
    useTemplates,
    templateFilters,
    templateId,
    templateName,
    setTemplateId,
    setTemplateName,
    setUseTemplates,
    setTemplateFilters,
  } = useChatStore();

  const [templatePopoverOpen, setTemplatePopoverOpen] = useState(false);
  const [templateTab, setTemplateTab] = useState<'structure' | 'base'>('structure');
  const [templateQuery, setTemplateQuery] = useState('');
  const [templates, setTemplates] = useState<any[]>([]);
  const [templatesLoading, setTemplatesLoading] = useState(false);
  const [mcpServers, setMcpServers] = useState<Array<{ label: string; url: string }>>([]);
  const [mcpServersLoading, setMcpServersLoading] = useState(false);

  const toggleMcpServerLabel = (label: string, enabled: boolean) => {
    const next = new Set(Array.isArray(mcpServerLabels) ? mcpServerLabels : []);
    if (enabled) next.add(label);
    else next.delete(label);
    setMcpServerLabels(Array.from(next));
  };

  const refreshMcpServers = async () => {
    setMcpServersLoading(true);
    try {
      const res = await apiClient.getMcpServers();
      const list = Array.isArray(res?.servers) ? res.servers : [];
      setMcpServers(
        list
          .map((s: any) => ({
            label: String(s?.label || '').trim(),
            url: String(s?.url || '').trim(),
          }))
          .filter((s: any) => s.label && s.url)
      );
    } catch {
      setMcpServers([]);
    } finally {
      setMcpServersLoading(false);
    }
  };

  const activeModelIds = useMemo(() => {
    const base =
      chatMode === 'multi-model'
        ? selectedModels
        : selectedModels.length > 0
          ? [selectedModels[0]]
          : selectedModel
            ? [selectedModel]
            : [];
    return Array.from(new Set(base.filter(Boolean)));
  }, [chatMode, selectedModels, selectedModel]);
  const showPerModelOverrides = chatMode === 'multi-model' && activeModelIds.length > 0;

  const filteredTemplates = useMemo(() => {
    const query = templateQuery.trim().toLowerCase();
    if (!query) return templates;
    return templates.filter((item) => {
      const name = String(item?.name || item?.title || '').toLowerCase();
      const docType = String(item?.document_type || '').toLowerCase();
      return name.includes(query) || docType.includes(query);
    });
  }, [templateQuery, templates]);

  const updateTemplateFilters = (patch: Record<string, any>) => {
    setTemplateFilters({ ...(templateFilters || {}), ...patch });
  };

  useEffect(() => {
    if (!templatePopoverOpen) return;
    if (templates.length > 0) return;
    setTemplatesLoading(true);
    apiClient
      .getTemplates(0, 50)
      .then((data) => setTemplates(data.templates || []))
      .catch(() => setTemplates([]))
      .finally(() => setTemplatesLoading(false));
  }, [templatePopoverOpen, templates.length]);

  useEffect(() => {
    if (!mcpToolCalling) return;
    if (mcpServers.length > 0) return;
    refreshMcpServers();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mcpToolCalling]);

  const handleSelectTemplate = (model: any) => {
    if (!model?.id) return;
    setTemplateId(model.id);
    setTemplateName(model.name || model.title || null);
    setTemplatePopoverOpen(false);
    toast.success(`Template "${model.name || model.title || 'selecionado'}" aplicado.`);
  };

  const handleClearTemplate = () => {
    setTemplateId(null);
    setTemplateName(null);
    toast.info('Template removido.');
  };

  const DEFAULT_COMPARE_MODELS = ['gpt-5.2', 'claude-4.5-sonnet', 'gemini-3-flash'];
  const contextCount = contextItems.length;
  const primaryModelId =
    selectedModels.length === 1 ? String(selectedModels[0] || '').toLowerCase() : '';
  const isPerplexitySonarSelected = ['sonar', 'sonar-pro', 'sonar-reasoning-pro'].includes(
    primaryModelId
  );
  const isSonarProSelected = primaryModelId === 'sonar-pro';
  const isPerplexityDeepSelected = primaryModelId === 'sonar-deep-research';
  const isSharedSearchMode = webSearch && (searchMode === 'shared' || searchMode === 'perplexity');
  const enableDeepResearchParams = denseResearch && deepResearchProvider === 'perplexity';
  const showPerplexitySonarParams = webSearch && isPerplexitySonarSelected && !isSharedSearchMode;
  const showPerplexitySearchApiParams = webSearch && isSharedSearchMode && !isPerplexityDeepSelected;
  const showSearchFocusInSearchApi = showPerplexitySearchApiParams && !showPerplexitySonarParams;
  const hasModelParamOptions =
    showPerplexitySonarParams || showPerplexitySearchApiParams || enableDeepResearchParams;
  const isClaudeSelected = primaryModelId.startsWith('claude');
  const claudeBudgetRange = primaryModelId.includes('sonnet') ? '0-31999' : '0-63999';
  const claudeBudgetFlavor = primaryModelId.includes('sonnet') ? 'Claude Sonnet' : 'Claude Opus';
  const claudeBudgetHint = `${claudeBudgetRange} (${claudeBudgetFlavor})`;
  const isGpt52Selected = primaryModelId.startsWith('gpt-5.2');
  const isGeminiProSelected = primaryModelId === 'gemini-3-pro';
  const isGeminiFlashSelected =
    primaryModelId.includes('flash') && primaryModelId.startsWith('gemini');
  const hasSingleModel = selectedModels.length === 1;
  const showThinkingParams = hasSingleModel && !isPerplexitySonarSelected && !isPerplexityDeepSelected;
  const showPerplexitySettings = advancedRagMode && showPerplexitySonarParams;
  const perplexitySettingsEnabled = showPerplexitySonarParams;
  const contextChipBase =
    'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold transition-colors';
  const contextChipActive = 'border-emerald-200 bg-emerald-500/10 text-emerald-600';
  const contextChipInactive = 'border-slate-200 text-slate-500 hover:bg-slate-100';
  const attachmentChipLabel =
    attachmentMode === 'auto'
      ? 'Auto'
      : attachmentMode === 'prompt_injection'
        ? 'Injeção'
        : 'RAG local';
  const attachmentChipActiveState = attachmentMode === 'auto' || attachmentMode === 'rag_local';
  const attachmentLimits = useModelAttachmentLimits(selectedModels);
  const attachmentModels = attachmentLimits.perModel;
  const hasAttachmentModel = attachmentModels.length > 0;
  const attachmentCountLabel =
    attachmentMode === 'prompt_injection'
      ? `até ${attachmentLimits.injectionMaxFiles} arquivo(s)`
      : attachmentMode === 'rag_local'
        ? `até ${attachmentLimits.ragLocalMaxFiles} arquivo(s)`
        : `até ${attachmentLimits.injectionMaxFiles} (injeção) / ${attachmentLimits.ragLocalMaxFiles} (RAG)`;
  const recencyOptions: { value: '' | 'day' | 'week' | 'month' | 'year'; label: string }[] = [
    { value: '', label: 'Sem filtro' },
    { value: 'day', label: '24h' },
    { value: 'week', label: '7d' },
    { value: 'month', label: '30d' },
    { value: 'year', label: '1 ano' },
  ];
  const wrapTooltip = (
    enabled: boolean,
    trigger: JSX.Element,
    content: string,
    side: 'right' | 'top' | 'bottom' | 'left' = 'right'
  ) => {
    if (!enabled) return trigger;
    return (
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>{trigger}</TooltipTrigger>
          <TooltipContent side={side} className="max-w-xs text-xs">
            {content}
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    );
  };

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

      <div className="group relative flex flex-col gap-2 rounded-3xl border border-slate-200/80 bg-white p-2.5 shadow-sm focus-within:border-emerald-400/70 focus-within:ring-2 focus-within:ring-emerald-400/20 transition-all">
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
                  className="rounded-full border border-emerald-200 bg-white px-2 py-1 text-[10px] font-semibold text-emerald-700 hover:bg-emerald-50"
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
                className="rounded-full border border-slate-200 bg-white px-2 py-1 text-[10px] font-semibold text-slate-600 hover:bg-slate-50"
              >
                Instrução livre
              </button>
            </div>
          </div>
        )}
        <div className="flex flex-col gap-2 px-2">
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => setAttachmentMode('rag_local')}
              className={cn(
                contextChipBase,
                attachmentChipActiveState ? contextChipActive : contextChipInactive
              )}
            >
              <BookOpen className="h-3 w-3" />
              {attachmentChipLabel}
              <span className="text-[9px] text-muted-foreground/70">({contextCount})</span>
            </button>
            <button
              type="button"
              onClick={() => setWebSearch(!webSearch)}
              className={cn(contextChipBase, webSearch ? contextChipActive : contextChipInactive)}
            >
              <Globe className="h-3 w-3" />
              Web
            </button>
            <button
              type="button"
              onClick={() => setDenseResearch(!denseResearch)}
              className={cn(
                contextChipBase,
                denseResearch ? contextChipActive : contextChipInactive
              )}
            >
              <Brain className="h-3 w-3" />
              Deep research
            </button>
            <button
              type="button"
              onClick={() => setMcpToolCalling(!mcpToolCalling)}
              className={cn(
                contextChipBase,
                mcpToolCalling ? contextChipActive : contextChipInactive
              )}
              title="Permite que o modelo execute ferramentas via conectores MCP"
            >
              <Zap className="h-3 w-3" />
              MCP
            </button>
          </div>
          <div className="flex items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-2 py-1">
            <span className="text-[10px] font-semibold uppercase text-muted-foreground">
              Objetivo
            </span>
            <input
              value={thesis}
              onChange={(e) => setThesis(e.target.value)}
              placeholder="Defina a tese/objetivo"
              className="flex-1 bg-transparent text-[11px] text-foreground placeholder:text-muted-foreground focus:outline-none"
            />
          </div>
        </div>
        <textarea
          ref={textareaRef}
          value={content}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          placeholder={
            placeholder ||
            "Descreva a minuta que você precisa... (Digite '/' para prompts, '@' para contexto)"
          }
          className="min-h-[72px] w-full resize-none bg-transparent px-3 py-2.5 text-[15px] placeholder:text-muted-foreground/70 focus:outline-none disabled:opacity-50"
          disabled={disabled}
          rows={1}
          data-testid="chat-input"
        />

        <div className="flex flex-wrap items-center gap-2 px-2 pb-1">
          <div className="flex flex-wrap items-center gap-1 min-w-0">
            {/* Visible toggle (low-friction discovery) */}
            <div className="flex items-center gap-1 rounded-lg border border-slate-200 bg-slate-50 px-2 py-1">
              <Switch
                checked={chatMode === 'multi-model'}
                onCheckedChange={(v) => handleCompareToggle(!!v)}
                className="scale-75"
              />
              <span className="text-[10px] font-semibold text-muted-foreground">
                Comparar modelos
              </span>
              <span className="hidden sm:inline text-[9px] text-muted-foreground/70">
                2–3 respostas em paralelo
              </span>
            </div>

            <ModelSelector />

            <Popover open={templatePopoverOpen} onOpenChange={setTemplatePopoverOpen}>
              <PopoverTrigger asChild>
                <Button
                  variant="ghost"
                  size="sm"
                  className={cn(
                    'h-7 gap-1 rounded-full px-2 text-[10px] font-medium transition-colors',
                    templateId
                      ? 'text-emerald-600 bg-emerald-500/10'
                      : 'text-slate-500 hover:bg-slate-100 hover:text-slate-700'
                  )}
                >
                  <FileText className="h-3 w-3" />
                  <span className="max-w-[140px] truncate">
                    {templateName ? `Template: ${templateName}` : 'Template'}
                  </span>
                  <ChevronDown className="h-3 w-3 opacity-50" />
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-80 p-3 space-y-3" align="start">
                <div className="flex items-center rounded-full bg-slate-100 p-1 text-[10px] font-semibold text-slate-500">
                  <button
                    type="button"
                    onClick={() => setTemplateTab('structure')}
                    className={cn(
                      'flex-1 rounded-full px-2 py-1 transition',
                      templateTab === 'structure'
                        ? 'bg-white text-slate-700 shadow-sm'
                        : 'hover:text-slate-700'
                    )}
                  >
                    Estrutura
                  </button>
                  <button
                    type="button"
                    onClick={() => setTemplateTab('base')}
                    className={cn(
                      'flex-1 rounded-full px-2 py-1 transition',
                      templateTab === 'base'
                        ? 'bg-white text-slate-700 shadow-sm'
                        : 'hover:text-slate-700'
                    )}
                  >
                    Base / RAG
                  </button>
                </div>

                {templateTab === 'structure' ? (
                  <>
                    <div className="space-y-1">
                      <Label className="text-xs font-semibold text-muted-foreground">
                        Buscar template
                      </Label>
                      <Input
                        value={templateQuery}
                        onChange={(e) => setTemplateQuery(e.target.value)}
                        placeholder="Digite o nome do template"
                        className="h-8"
                      />
                    </div>

                    <div className="max-h-56 space-y-1 overflow-y-auto">
                      {templatesLoading ? (
                        <p className="text-xs text-muted-foreground">Carregando templates...</p>
                      ) : filteredTemplates.length === 0 ? (
                        <p className="text-xs text-muted-foreground">Nenhum template encontrado.</p>
                      ) : (
                        filteredTemplates.map((item) => {
                          const isActive = templateId === item.id;
                          return (
                            <button
                              key={item.id}
                              type="button"
                              onClick={() => handleSelectTemplate(item)}
                              className={cn(
                                'flex w-full items-center justify-between rounded-lg border px-2 py-2 text-left text-xs transition',
                                isActive
                                  ? 'border-emerald-200 bg-emerald-500/10 text-emerald-700'
                                  : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50'
                              )}
                            >
                              <span className="truncate font-semibold">
                                {item.name || item.title || 'Template'}
                              </span>
                              <span className="ml-2 text-[10px] text-muted-foreground">
                                {item.document_type || 'Modelo'}
                              </span>
                            </button>
                          );
                        })
                      )}
                    </div>

                    <div className="flex items-center justify-between">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={handleClearTemplate}
                        disabled={!templateId}
                      >
                        Limpar
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => {
                          window.location.href = '/models';
                        }}
                      >
                        Abrir biblioteca
                      </Button>
                    </div>
                  </>
                ) : (
                  <div className="space-y-3">
                    <div className="flex items-center justify-between rounded-lg border border-slate-200 bg-slate-50 px-2 py-2">
                      <div>
                        <Label className="text-xs font-semibold text-slate-600">
                          Usar modelos no RAG
                        </Label>
                        <p className="text-[10px] text-muted-foreground">
                          Inclui pecas modelo na busca contextual.
                        </p>
                      </div>
                      <Switch checked={useTemplates} onCheckedChange={setUseTemplates} />
                    </div>

                    <div className={cn('grid gap-2', !useTemplates && 'opacity-50')}>
                      <Input
                        value={templateFilters?.tipoPeca || ''}
                        onChange={(e) => updateTemplateFilters({ tipoPeca: e.target.value })}
                        placeholder="Tipo (ex: peticao_inicial)"
                        className="h-8"
                        disabled={!useTemplates}
                      />
                      <div className="grid grid-cols-2 gap-2">
                        <Input
                          value={templateFilters?.area || ''}
                          onChange={(e) => updateTemplateFilters({ area: e.target.value })}
                          placeholder="Area"
                          className="h-8"
                          disabled={!useTemplates}
                        />
                        <Input
                          value={templateFilters?.rito || ''}
                          onChange={(e) => updateTemplateFilters({ rito: e.target.value })}
                          placeholder="Rito"
                          className="h-8"
                          disabled={!useTemplates}
                        />
                      </div>
                      <div className="flex items-center gap-2 text-[11px] text-slate-600">
                        <Checkbox
                          checked={!!templateFilters?.apenasClauseBank}
                          onCheckedChange={(checked) =>
                            updateTemplateFilters({ apenasClauseBank: Boolean(checked) })
                          }
                          disabled={!useTemplates}
                        />
                        Apenas Clause Bank
                      </div>
                    </div>
                  </div>
                )}
              </PopoverContent>
            </Popover>

            {/* Canvas Toggle */}
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="sm"
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
                      'h-7 gap-1 rounded-full px-2 text-[10px] font-medium transition-colors',
                      useCanvasStore((s) => s.state) !== 'hidden'
                        ? 'text-emerald-600 bg-emerald-500/10'
                        : 'text-slate-500 hover:bg-slate-100 hover:text-slate-700'
                    )}
                  >
                    <PanelRight className="h-3.5 w-3.5" />
                    <span className="hidden sm:inline">Canvas</span>
                  </Button>
                </TooltipTrigger>
                <TooltipContent side="top" className="text-xs">
                  Abrir/fechar o painel de edição do documento
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>

            {/* AI Controls */}
            <div className="h-4 w-[1px] bg-slate-200 mx-1" />

            <Popover>
              <PopoverTrigger asChild>
                <Button
                  variant="ghost"
                  size="sm"
                  className={cn(
                    'h-7 gap-1 rounded-full px-2 text-[10px] font-medium transition-colors',
                    webSearch || denseResearch
                      ? 'text-emerald-600 bg-emerald-500/10'
                      : 'text-slate-500 hover:bg-slate-100 hover:text-slate-700'
                  )}
                >
                  {denseResearch ? <Brain className="h-3 w-3" /> : <Globe className="h-3 w-3" />}
                  {denseResearch ? 'Deep Research' : webSearch ? 'Web Search' : 'Sem Web'}
                  <ChevronDown className="h-3 w-3 opacity-50" />
                </Button>
              </PopoverTrigger>
              <PopoverContent
                className="w-80 max-h-[70vh] overflow-y-auto p-4 pr-3 space-y-4 overscroll-contain"
                align="start"
                sideOffset={8}
                collisionPadding={12}
              >
                <div className="space-y-4">
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <div className="flex flex-col gap-0.5">
                        <Label className="text-sm font-medium">Decisão de pesquisa</Label>
                        <span className="text-xs text-muted-foreground">
                          Auto pode ativar Web/Deep quando necessário
                        </span>
                      </div>
                      <div className="flex items-center gap-1">
                        <button
                          type="button"
                          onClick={() => setResearchPolicy('auto')}
                          className={cn(
                            'rounded-full border px-2 py-1 text-[10px] font-semibold transition-colors',
                            researchPolicy === 'auto'
                              ? 'border-emerald-200 bg-emerald-500/15 text-emerald-700'
                              : 'border-slate-200 text-slate-500 hover:bg-slate-100 hover:text-slate-700'
                          )}
                        >
                          Auto
                        </button>
                        <button
                          type="button"
                          onClick={() => setResearchPolicy('force')}
                          className={cn(
                            'rounded-full border px-2 py-1 text-[10px] font-semibold transition-colors',
                            researchPolicy === 'force'
                              ? 'border-emerald-200 bg-emerald-500/15 text-emerald-700'
                              : 'border-slate-200 text-slate-500 hover:bg-slate-100 hover:text-slate-700'
                          )}
                        >
                          Manual
                        </button>
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center justify-between">
                    <div className="flex flex-col gap-0.5">
                      <Label className="text-sm font-medium">Web Search</Label>
                      <span className="text-xs text-muted-foreground">
                        Contexto de ate 20 fontes (Rápido)
                      </span>
                    </div>
                    <Switch checked={webSearch} onCheckedChange={setWebSearch} />
                  </div>

                  <div className="flex items-center justify-between">
                    <div className="flex flex-col gap-0.5">
                      <Label className="text-sm font-medium">MCP tools</Label>
                      <span className="text-xs text-muted-foreground">
                        Conectores para tools externas (estilo ChatGPT/Claude)
                      </span>
                    </div>
                    <Switch checked={mcpToolCalling} onCheckedChange={setMcpToolCalling} />
                  </div>
                  {mcpToolCalling && (
                    <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-700 space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="font-semibold">Conectores</span>
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          className="h-7 px-2 text-[11px]"
                          onClick={refreshMcpServers}
                          disabled={mcpServersLoading}
                        >
                          {mcpServersLoading ? 'Carregando...' : 'Atualizar'}
                        </Button>
                      </div>
                      {mcpServersLoading ? (
                        <div className="text-muted-foreground">Carregando conectores...</div>
                      ) : mcpServers.length > 0 ? (
                        <div className="space-y-2">
                          <div className="flex items-center justify-between gap-3">
                            <div className="flex flex-col">
                              <span className="font-medium">Usar todos</span>
                              <span className="text-[11px] text-muted-foreground">
                                Desative para escolher conectores específicos
                              </span>
                            </div>
                            <Switch checked={mcpUseAllServers} onCheckedChange={setMcpUseAllServers} />
                          </div>

                          {!mcpUseAllServers && (
                            <div className="space-y-1">
                              {mcpServers.map((s) => {
                                const checked = (mcpServerLabels || []).includes(s.label);
                                return (
                                  <div key={s.label} className="flex items-center justify-between gap-2">
                                    <div className="flex items-center gap-2 min-w-0">
                                      <Checkbox
                                        checked={checked}
                                        onCheckedChange={(v) => toggleMcpServerLabel(s.label, Boolean(v))}
                                      />
                                      <span className="truncate font-medium">{s.label}</span>
                                    </div>
                                    <span className="truncate text-[11px] text-muted-foreground">{s.url}</span>
                                  </div>
                                );
                              })}
                              {(mcpServerLabels || []).length === 0 && (
                                <div className="text-[11px] text-amber-700">
                                  Se nenhum conector for selecionado, o MCP fica desativado para esta mensagem.
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      ) : (
                        <div className="text-muted-foreground">
                          Nenhum MCP server configurado no backend.
                        </div>
                      )}
                    </div>
                  )}

                  <div className={cn('space-y-2', !webSearch && 'opacity-50')}>
                    <div className="flex items-center gap-2">
                      {wrapTooltip(
                        advancedRagMode,
                        <Label
                          className={cn('text-sm font-medium', advancedRagMode && 'cursor-help')}
                        >
                          Modo de busca
                        </Label>,
                        'Define como a busca web é executada no Modo Chat e no Modo Minuta. Compartilhada usa o WebSearchService (Perplexity Search API quando disponível) e repassa o mesmo contexto para todos.',
                        'right'
                      )}
                    </div>
                    <div className="flex flex-wrap gap-1">
                      {wrapTooltip(
                        advancedRagMode,
                        <button
                          type="button"
                          disabled={!webSearch}
                          onClick={() => setSearchMode('shared')}
                          className={cn(
                            'rounded-full border px-2 py-1 text-[10px] font-semibold transition-colors',
                            searchMode === 'shared'
                              ? 'border-emerald-200 bg-emerald-500/15 text-emerald-700'
                              : 'border-slate-200 text-slate-500 hover:bg-slate-100 hover:text-slate-700',
                            !webSearch && 'pointer-events-none'
                          )}
                        >
                          Compartilhada
                        </button>,
                        'Uma única busca alimenta todos os modelos. Perplexity Search API quando disponível (com fallback). Mais rápida e consistente.',
                        'right'
                      )}
                      {wrapTooltip(
                        advancedRagMode,
                        <button
                          type="button"
                          disabled={!webSearch}
                          onClick={() => setSearchMode('native')}
                          className={cn(
                            'rounded-full border px-2 py-1 text-[10px] font-semibold transition-colors',
                            searchMode === 'native'
                              ? 'border-emerald-200 bg-emerald-500/15 text-emerald-700'
                              : 'border-slate-200 text-slate-500 hover:bg-slate-100 hover:text-slate-700',
                            !webSearch && 'pointer-events-none'
                          )}
                        >
                          Nativa por modelo
                        </button>,
                        'Cada modelo usa a busca do próprio provedor. Maior cobertura, mais custo e latência.',
                        'right'
                      )}
                      {wrapTooltip(
                        advancedRagMode,
                        <button
                          type="button"
                          disabled={!webSearch}
                          onClick={() => setSearchMode('hybrid')}
                          className={cn(
                            'rounded-full border px-2 py-1 text-[10px] font-semibold transition-colors',
                            searchMode === 'hybrid'
                              ? 'border-emerald-200 bg-emerald-500/15 text-emerald-700'
                              : 'border-slate-200 text-slate-500 hover:bg-slate-100 hover:text-slate-700',
                            !webSearch && 'pointer-events-none'
                          )}
                        >
                          Híbrida
                        </button>,
                        'Usa busca compartilhada quando necessário; se todos suportarem nativo, usa nativa.',
                        'right'
                      )}
                    </div>
                  </div>

                  <div className="flex items-center justify-between">
                    <div className="flex flex-col gap-0.5">
                      <div className="flex items-center gap-2">
                        {wrapTooltip(
                          advancedRagMode,
                          <Label
                            className={cn('text-sm font-medium', advancedRagMode && 'cursor-help')}
                          >
                            Multi-query
                          </Label>,
                          'Gera variações da pergunta para aumentar o recall. Afeta Web Search e RAG (KB/anexos).',
                          'right'
                        )}
                      </div>
                      <span className="text-xs text-muted-foreground">
                        Reformula a pergunta automaticamente
                      </span>
                    </div>
                    <Switch checked={multiQuery} onCheckedChange={setMultiQuery} />
                  </div>

                  <div
                    className={cn('flex items-center justify-between', !webSearch && 'opacity-50')}
                  >
                    <div className="flex flex-col gap-0.5">
                      <div className="flex items-center gap-2">
                        {wrapTooltip(
                          advancedRagMode,
                          <Label
                            className={cn('text-sm font-medium', advancedRagMode && 'cursor-help')}
                          >
                            Breadth-first
                          </Label>,
                          'Ativa um fluxo com subagentes para perguntas amplas. Mais cobertura, mais lento.',
                          'right'
                        )}
                      </div>
                      <span className="text-xs text-muted-foreground">
                        Indicado para questões longas/complexas
                      </span>
                    </div>
                    <Switch
                      checked={breadthFirst}
                      onCheckedChange={setBreadthFirst}
                      disabled={!webSearch}
                    />
                  </div>

                  {showPerplexitySettings && (
                    <div
                      className={cn(
                        'space-y-3 rounded-2xl border border-slate-200 bg-white/70 p-3',
                        !perplexitySettingsEnabled && 'opacity-50 pointer-events-none'
                      )}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex flex-col gap-0.5">
                          <Label className="text-sm font-medium">Perplexity Sonar (Chat)</Label>
                          <span className="text-xs text-muted-foreground">
                            Ajustes do chat web-grounded
                          </span>
                        </div>
                        <span className="rounded-full bg-slate-100 px-2 py-1 text-[9px] font-semibold text-slate-600">
                          ADV
                        </span>
                      </div>

                      <div className="space-y-2">
                        <Label className="text-xs font-semibold uppercase text-slate-500">
                          Escopo da busca
                        </Label>
                        <div className="flex flex-wrap gap-1">
                          <button
                            type="button"
                            onClick={() => setPerplexitySearchMode('web')}
                            className={cn(
                              'inline-flex items-center gap-1 rounded-full border px-2 py-1 text-[10px] font-semibold transition-colors',
                              perplexitySearchMode === 'web'
                                ? 'border-emerald-200 bg-emerald-500/15 text-emerald-700'
                                : 'border-slate-200 text-slate-500 hover:bg-slate-100 hover:text-slate-700'
                            )}
                          >
                            <Globe className="h-3 w-3" />
                            Web
                          </button>
                          <button
                            type="button"
                            onClick={() => setPerplexitySearchMode('academic')}
                            className={cn(
                              'inline-flex items-center gap-1 rounded-full border px-2 py-1 text-[10px] font-semibold transition-colors',
                              perplexitySearchMode === 'academic'
                                ? 'border-emerald-200 bg-emerald-500/15 text-emerald-700'
                                : 'border-slate-200 text-slate-500 hover:bg-slate-100 hover:text-slate-700'
                            )}
                          >
                            <BookOpen className="h-3 w-3" />
                            Acadêmico
                          </button>
                          <button
                            type="button"
                            onClick={() => setPerplexitySearchMode('sec')}
                            className={cn(
                              'inline-flex items-center gap-1 rounded-full border px-2 py-1 text-[10px] font-semibold transition-colors',
                              perplexitySearchMode === 'sec'
                                ? 'border-emerald-200 bg-emerald-500/15 text-emerald-700'
                                : 'border-slate-200 text-slate-500 hover:bg-slate-100 hover:text-slate-700'
                            )}
                          >
                            <ShieldCheck className="h-3 w-3" />
                            SEC
                          </button>
                        </div>
                      </div>

                      {isSonarProSelected && (
                        <div className="space-y-2">
                          <Label className="text-xs font-semibold uppercase text-slate-500">
                            Search type (Sonar Pro)
                          </Label>
                          <div className="flex flex-wrap gap-1">
                            {(['fast', 'pro', 'auto'] as const).map((mode) => (
                              <button
                                key={mode}
                                type="button"
                                onClick={() => setPerplexitySearchType(mode)}
                                className={cn(
                                  'rounded-full border px-2 py-1 text-[10px] font-semibold transition-colors',
                                  perplexitySearchType === mode
                                    ? 'border-emerald-200 bg-emerald-500/15 text-emerald-700'
                                    : 'border-slate-200 text-slate-500 hover:bg-slate-100 hover:text-slate-700'
                                )}
                              >
                                {mode === 'fast' ? 'Fast' : mode === 'pro' ? 'Pro' : 'Auto'}
                              </button>
                            ))}
                          </div>
                        </div>
                      )}

                      {isPerplexitySonarSelected && (
                        <div className="space-y-2">
                          <Label className="text-xs font-semibold uppercase text-slate-500">
                            Search context size
                          </Label>
                          <div className="flex flex-wrap gap-1">
                            {(['low', 'medium', 'high'] as const).map((size) => (
                              <button
                                key={size}
                                type="button"
                                onClick={() => setPerplexitySearchContextSize(size)}
                                className={cn(
                                  'rounded-full border px-2 py-1 text-[10px] font-semibold transition-colors',
                                  perplexitySearchContextSize === size
                                    ? 'border-emerald-200 bg-emerald-500/15 text-emerald-700'
                                    : 'border-slate-200 text-slate-500 hover:bg-slate-100 hover:text-slate-700'
                                )}
                              >
                                {size === 'low' ? 'Low' : size === 'medium' ? 'Medium' : 'High'}
                              </button>
                            ))}
                          </div>
                        </div>
                      )}

                      {isPerplexitySonarSelected && (
                        <div className="grid grid-cols-1 gap-2">
                          {isSonarProSelected && (
                            <div className="flex items-center justify-between rounded-xl border border-slate-200 bg-slate-50 px-3 py-2">
                              <div>
                                <p className="text-[11px] font-semibold text-slate-700">
                                  Classificador automático
                                </p>
                                <p className="text-[10px] text-slate-500">
                                  Habilita roteamento Fast/Pro
                                </p>
                              </div>
                              <Switch
                                checked={perplexitySearchClassifier}
                                onCheckedChange={setPerplexitySearchClassifier}
                              />
                            </div>
                          )}
                          <div className="flex items-center justify-between rounded-xl border border-slate-200 bg-slate-50 px-3 py-2">
                            <div>
                              <p className="text-[11px] font-semibold text-slate-700">
                                Desativar busca
                              </p>
                              <p className="text-[10px] text-slate-500">
                                Resposta sem pesquisa web
                              </p>
                            </div>
                            <Switch
                              checked={perplexityDisableSearch}
                              onCheckedChange={setPerplexityDisableSearch}
                            />
                          </div>
                        </div>
                      )}

                      {isPerplexitySonarSelected && (
                        <div className="space-y-2">
                          <Label className="text-xs font-semibold uppercase text-slate-500">
                            Stream mode
                          </Label>
                          <div className="flex flex-wrap gap-1">
                            {(['full', 'concise'] as const).map((mode) => (
                              <button
                                key={mode}
                                type="button"
                                onClick={() => setPerplexityStreamMode(mode)}
                                className={cn(
                                  'rounded-full border px-2 py-1 text-[10px] font-semibold transition-colors',
                                  perplexityStreamMode === mode
                                    ? 'border-emerald-200 bg-emerald-500/15 text-emerald-700'
                                    : 'border-slate-200 text-slate-500 hover:bg-slate-100 hover:text-slate-700'
                                )}
                              >
                                {mode === 'full' ? 'Full' : 'Concise'}
                              </button>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}

                  <div className="flex items-center justify-between">
                    <div className="flex flex-col gap-0.5">
                      <div className="flex items-center gap-2">
                        <Label className="text-sm font-medium">Deep Research</Label>
                        <span className="px-1.5 py-0.5 rounded bg-emerald-500/15 text-emerald-700 text-[9px] font-bold">
                          ALPHA
                        </span>
                      </div>
                      <span className="text-xs text-muted-foreground">
                        Agente Autônomo (Lento, +Custos)
                      </span>
                    </div>
                    <Switch checked={denseResearch} onCheckedChange={setDenseResearch} />
                  </div>

                  <div className={cn('space-y-2', !denseResearch && 'opacity-50')}>
                    <div className="flex items-center gap-2">
                      {wrapTooltip(
                        advancedRagMode,
                        <Label
                          className={cn('text-sm font-medium', advancedRagMode && 'cursor-help')}
                        >
                          Backend do Deep Research
                        </Label>,
                        'Escolhe qual provedor executa o Deep Research no fluxo LangGraph. Auto usa o melhor disponível; Perplexity usa Sonar Deep Research; Google usa o agente Deep Research do Gemini. (Os outros modelos Sonar são para Chat/answers web-grounded, não para este modo Deep Research.)',
                        'right'
                      )}
                    </div>
                    <div className="flex flex-wrap gap-1">
                      <button
                        type="button"
                        disabled={!denseResearch}
                        onClick={() => setDeepResearchProvider('auto')}
                        className={cn(
                          'rounded-full border px-2 py-1 text-[10px] font-semibold transition-colors',
                          deepResearchProvider === 'auto'
                            ? 'border-emerald-200 bg-emerald-500/15 text-emerald-700'
                            : 'border-slate-200 text-slate-500 hover:bg-slate-100 hover:text-slate-700',
                          !denseResearch && 'pointer-events-none'
                        )}
                      >
                        Auto
                      </button>
                      <button
                        type="button"
                        disabled={!denseResearch}
                        onClick={() => setDeepResearchProvider('perplexity')}
                        className={cn(
                          'rounded-full border px-2 py-1 text-[10px] font-semibold transition-colors',
                          deepResearchProvider === 'perplexity'
                            ? 'border-emerald-200 bg-emerald-500/15 text-emerald-700'
                            : 'border-slate-200 text-slate-500 hover:bg-slate-100 hover:text-slate-700',
                          !denseResearch && 'pointer-events-none'
                        )}
                      >
                        Perplexity
                      </button>
                      <button
                        type="button"
                        disabled={!denseResearch}
                        onClick={() => setDeepResearchProvider('google')}
                        className={cn(
                          'rounded-full border px-2 py-1 text-[10px] font-semibold transition-colors',
                          deepResearchProvider === 'google'
                            ? 'border-emerald-200 bg-emerald-500/15 text-emerald-700'
                            : 'border-slate-200 text-slate-500 hover:bg-slate-100 hover:text-slate-700',
                          !denseResearch && 'pointer-events-none'
                        )}
                      >
                        Google
                      </button>
                    </div>

                    {deepResearchProvider === 'perplexity' && (
                      <div className={cn('space-y-1', !denseResearch && 'pointer-events-none')}>
                        <Label className="text-xs font-medium text-muted-foreground">
                          Modelo (Perplexity Deep Research)
                        </Label>
                        <div className="flex flex-wrap gap-1">
                          <button
                            type="button"
                            disabled={!denseResearch}
                            onClick={() => setDeepResearchModel('sonar-deep-research')}
                            className={cn(
                              'rounded-full border px-2 py-1 text-[10px] font-semibold transition-colors',
                              deepResearchModel === 'sonar-deep-research'
                                ? 'border-emerald-200 bg-emerald-500/15 text-emerald-700'
                                : 'border-slate-200 text-slate-500 hover:bg-slate-100 hover:text-slate-700',
                              !denseResearch && 'pointer-events-none'
                            )}
                            title="sonar-deep-research"
                          >
                            Sonar Deep Research
                          </button>
                        </div>
                        <span className="text-[10px] text-muted-foreground">
                          Este backend usa apenas{' '}
                          <span className="font-mono">sonar-deep-research</span>.
                        </span>
                      </div>
                    )}
                  </div>

                  <div className="h-[1px] bg-slate-200" />

                  <div className="space-y-2">
                    <Label className="text-sm font-medium">Nível de Raciocínio (Thinking)</Label>
                    <div className="flex gap-1 rounded-lg bg-slate-100 p-1">
                      {(['low', 'medium', 'high'] as const).map((level) => (
                        <button
                          key={level}
                          onClick={() => setReasoningLevel(level)}
                          className={cn(
                            'flex-1 px-2 py-1.5 text-xs font-medium rounded-md transition-all',
                            reasoningLevel === level
                              ? 'bg-emerald-600/15 text-emerald-700 shadow-sm'
                              : 'text-slate-500 hover:bg-slate-100 hover:text-slate-700'
                          )}
                        >
                          {level === 'low' ? 'Rápido' : level === 'medium' ? 'Médio' : 'Profundo'}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="space-y-2">
                    <Label className="text-sm font-medium">Verbosidade</Label>
                    <div className="flex gap-1 rounded-lg bg-slate-100 p-1">
                      {(['low', 'medium', 'high'] as const).map((level) => (
                        <button
                          key={level}
                          onClick={() => setVerbosity(level)}
                          className={cn(
                            'flex-1 px-2 py-1.5 text-xs font-medium rounded-md transition-all',
                            verbosity === level
                              ? 'bg-emerald-600/15 text-emerald-700 shadow-sm'
                              : 'text-slate-500 hover:bg-slate-100 hover:text-slate-700'
                          )}
                        >
                          {level === 'low' ? 'Baixa' : level === 'medium' ? 'Media' : 'Alta'}
                        </button>
                      ))}
                    </div>
                  </div>

                  {showPerModelOverrides && (
                    <div className="space-y-2">
                      <Label className="text-sm font-medium">Overrides por modelo</Label>
                      <div className="space-y-2">
                        {activeModelIds.map((modelId) => {
                          const cfg = getModelConfig(modelId as ModelId);
                          const override = modelOverrides?.[modelId] || {};
                          const overrideVerbosity = override.verbosity || '';
                          const overrideBudget = override.thinkingBudget ?? '';
                          const isSonnet = String(modelId).includes('claude-4.5-sonnet');
                          const budgetHint = isSonnet ? '0-31999' : '0-63999';
                          return (
                            <div key={modelId} className="rounded-md border p-2 text-[11px] space-y-2">
                              <div className="font-semibold">{cfg?.label || modelId}</div>
                              <div className="flex gap-1 rounded-lg bg-slate-100 p-1">
                                {(['auto', 'low', 'medium', 'high'] as const).map((level) => (
                                  <button
                                    key={level}
                                    onClick={() =>
                                      setModelOverride(modelId, {
                                        verbosity: level === 'auto' ? undefined : level,
                                      })
                                    }
                                    className={cn(
                                      'flex-1 px-2 py-1 text-[10px] font-medium rounded-md transition-all',
                                      (level === 'auto' ? !overrideVerbosity : overrideVerbosity === level)
                                        ? 'bg-emerald-600/15 text-emerald-700 shadow-sm'
                                        : 'text-slate-500 hover:bg-slate-100 hover:text-slate-700'
                                    )}
                                  >
                                    {level === 'auto'
                                      ? 'Auto'
                                      : level === 'low'
                                        ? 'Baixa'
                                        : level === 'medium'
                                          ? 'Media'
                                          : 'Alta'}
                                  </button>
                                ))}
                              </div>
                              <Input
                                value={overrideBudget}
                                onChange={(e) =>
                                  setModelOverride(modelId, { thinkingBudget: e.target.value })
                                }
                                placeholder={`Auto (${budgetHint})`}
                                inputMode="numeric"
                                className="h-8 text-xs"
                              />
                            </div>
                          );
                        })}
                      </div>
                      <span className="text-[10px] text-muted-foreground">
                        Overrides so se aplicam no modo Comparar modelos.
                      </span>
                    </div>
                  )}

                  <div className="h-[1px] bg-slate-200" />

                  <div className="flex items-center justify-between">
                    <div className="flex flex-col gap-0.5">
                      <div className="flex items-center gap-2">
                        <Label className="text-sm font-medium">Comparar modelos (Chat)</Label>
                        <span className="px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-400 text-[9px] font-bold">
                          ON
                        </span>
                      </div>
                      <span className="text-xs text-muted-foreground">
                        Respostas paralelas; não é o Modo Minuta (Agentes)
                      </span>
                    </div>
                    <Switch
                      checked={chatMode === 'multi-model'}
                      onCheckedChange={(value) => handleCompareToggle(!!value)}
                    />
                  </div>

                  <div className="h-[1px] bg-slate-200" />

                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <Label className="text-xs font-bold uppercase text-muted-foreground flex items-center gap-2">
                        <Zap className="h-3 w-3" /> RAG
                      </Label>
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] text-muted-foreground">Auto</span>
                        <Switch checked={advancedRagMode} onCheckedChange={setAdvancedRagMode} />
                        <span className="text-[10px] text-muted-foreground">Avançado</span>
                      </div>
                    </div>
                    <p className="text-[10px] text-muted-foreground">
                      {advancedRagMode
                        ? 'Ajustes avançados para precisão e profundidade. Passe o mouse nos nomes para ver detalhes técnicos.'
                        : 'RAG auto: busca trechos relevantes e responde com base neles. Rápido e indicado para a maioria dos casos.'}
                    </p>

                    {advancedRagMode && (
                      <>
                        <div className="flex items-center justify-between">
                          <div className="flex flex-col gap-0.5">
                            {wrapTooltip(
                              advancedRagMode,
                              <Label
                                className={cn(
                                  'text-sm font-medium',
                                  advancedRagMode && 'cursor-help'
                                )}
                              >
                                Estratégia automática
                              </Label>,
                              'Nome tecnico: Adaptive Routing. Escolhe automaticamente a melhor estrategia por secao.',
                              'right'
                            )}
                            <span className="text-xs text-muted-foreground">
                              Recomendado para a maioria dos casos
                            </span>
                          </div>
                          <Switch checked={adaptiveRouting} onCheckedChange={setAdaptiveRouting} />
                        </div>

                        <div className="flex items-center justify-between">
                          <div className="flex flex-col gap-0.5">
                            {wrapTooltip(
                              advancedRagMode,
                              <Label
                                className={cn(
                                  'text-sm font-medium',
                                  advancedRagMode && 'cursor-help'
                                )}
                              >
                                Rascunho inteligente
                              </Label>,
                              'HyDE (Hypothetical Document Embeddings). Cria um rascunho para recuperar melhor quando a pergunta e vaga.',
                              'right'
                            )}
                            <span className="text-xs text-muted-foreground">
                              Ajuda quando a pergunta é vaga
                            </span>
                          </div>
                          <Switch checked={hydeEnabled} onCheckedChange={setHydeEnabled} />
                        </div>

                        <div className="flex items-center justify-between">
                          <div className="flex flex-col gap-0.5">
                            {wrapTooltip(
                              advancedRagMode,
                              <Label
                                className={cn(
                                  'text-sm font-medium',
                                  advancedRagMode && 'cursor-help'
                                )}
                              >
                                Verificacao extra
                              </Label>,
                              'CRAG (Corrective RAG). Reavalia a qualidade das evidencias antes de responder.',
                              'right'
                            )}
                            <span className="text-xs text-muted-foreground">
                              Checagem extra das fontes
                            </span>
                          </div>
                          <Switch checked={cragGate} onCheckedChange={setCragGate} />
                        </div>

                        <div className="space-y-2 pt-2 border-t border-slate-200/70">
                          <div className="flex items-center justify-between">
                            <div className="flex flex-col gap-0.5">
                              {wrapTooltip(
                                advancedRagMode,
                                <Label
                                  className={cn(
                                    'text-sm font-medium',
                                    advancedRagMode && 'cursor-help'
                                  )}
                                >
                                  Relacoes entre fatos
                                </Label>,
                                'GraphRAG. Conecta documentos e conceitos relacionados para ampliar o contexto. Profundidade define os saltos nas relacoes.',
                                'right'
                              )}
                              <span className="text-xs text-muted-foreground">
                                Conecta documentos e conceitos relacionados
                              </span>
                            </div>
                            <Switch
                              checked={graphRagEnabled}
                              onCheckedChange={setGraphRagEnabled}
                            />
                          </div>
                          {graphRagEnabled && (
                            <div className="space-y-2 px-1 pt-1 animate-in zoom-in-95">
                              <div className="flex justify-between items-center text-[10px]">
                                <span className="text-emerald-600">Profundidade: {graphHops}</span>
                              </div>
                              <Slider
                                value={[graphHops]}
                                onValueChange={([v]) => setGraphHops(v)}
                                max={5}
                                min={1}
                                step={1}
                              />
                              <div className="flex items-center justify-between pt-2">
                                <div className="flex flex-col gap-0.5">
                                  {wrapTooltip(
                                    advancedRagMode,
                                    <Label
                                      className={cn(
                                        'text-sm font-medium',
                                        advancedRagMode && 'cursor-help'
                                      )}
                                    >
                                      Contraditório (ArgumentRAG)
                                    </Label>,
                                    'Organiza alegações pró/contra e evidências associadas (quando disponíveis).',
                                    'right'
                                  )}
                                  <span className="text-xs text-muted-foreground">
                                    Pro/contra com evidências
                                  </span>
                                </div>
                                <Switch
                                  checked={argumentGraphEnabled}
                                  onCheckedChange={setArgumentGraphEnabled}
                                />
                              </div>
                            </div>
                          )}
                        </div>
                      </>
                    )}
                  </div>

                  {/* RAG Scope Selector */}
                  <div className="space-y-2 pt-3 border-t border-slate-200">
                    <div className="flex flex-col gap-2">
                      {wrapTooltip(
                        advancedRagMode,
                        <Label
                          className={cn(
                            'text-xs font-bold uppercase text-muted-foreground',
                            advancedRagMode && 'cursor-help'
                          )}
                        >
                          Escopo de Busca
                        </Label>,
                        'Define quais documentos a IA pode consultar: apenas anexos do caso, base global, ou ambos.',
                        'right'
                      )}
                      <div className="grid grid-cols-3 gap-1">
                        <button
                          type="button"
                          onClick={() => setRagScope('case_only')}
                          className={cn(
                            'px-2 py-1.5 text-xs rounded-md transition-colors',
                            ragScope === 'case_only'
                              ? 'bg-amber-100 text-amber-800 border border-amber-300'
                              : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                          )}
                        >
                          Só Caso
                        </button>
                        <button
                          type="button"
                          onClick={() => setRagScope('case_and_global')}
                          className={cn(
                            'px-2 py-1.5 text-xs rounded-md transition-colors',
                            ragScope === 'case_and_global'
                              ? 'bg-emerald-100 text-emerald-800 border border-emerald-300'
                              : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                          )}
                        >
                          Caso + Global
                        </button>
                        <button
                          type="button"
                          onClick={() => setRagScope('global_only')}
                          className={cn(
                            'px-2 py-1.5 text-xs rounded-md transition-colors',
                            ragScope === 'global_only'
                              ? 'bg-blue-100 text-blue-800 border border-blue-300'
                              : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                          )}
                        >
                          Só Global
                        </button>
                      </div>
                      <span className="text-[10px] text-muted-foreground">
                        {ragScope === 'case_only' && 'Busca apenas nos documentos anexados ao caso'}
                        {ragScope === 'case_and_global' && 'Busca nos anexos do caso e na base global (leis, jurisprudência)'}
                        {ragScope === 'global_only' && 'Ignora anexos, busca apenas na base global'}
                      </span>
                    </div>
                  </div>

                  <div className="space-y-2 pt-3 border-t border-slate-200">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        {wrapTooltip(
                          attachmentAdvanced,
                          <Label
                            className={cn(
                              'text-xs font-bold uppercase text-muted-foreground',
                              attachmentAdvanced && 'cursor-help'
                            )}
                          >
                            Anexos no contexto
                          </Label>,
                          'Escolha como os anexos serao usados pela IA: busca (RAG) ou injecao direta do texto.',
                          'right'
                        )}
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] text-muted-foreground">Auto</span>
                        <Switch
                          checked={attachmentAdvanced}
                          onCheckedChange={setAttachmentAdvanced}
                        />
                        <span className="text-[10px] text-muted-foreground">Avançado</span>
                      </div>
                    </div>

                    <div className="grid gap-2">
                      <div className="flex items-center justify-between gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                        <div className="flex items-center gap-2">
                          {wrapTooltip(
                            attachmentAdvanced,
                            <button
                              type="button"
                              onClick={() => setAttachmentMode('auto')}
                              className={cn(
                                'h-6 px-2 rounded-md text-[10px] font-semibold transition-all',
                                attachmentMode === 'auto'
                                  ? 'bg-emerald-200 text-slate-900'
                                  : 'bg-slate-200 text-slate-600 hover:bg-slate-300'
                              )}
                            >
                              Auto (recomendado)
                            </button>,
                            'Usa injecao direta para poucos arquivos curtos; caso contrario, usa RAG local.',
                            'left'
                          )}
                          <span className="text-[10px] text-muted-foreground">
                            Decide por tamanho e tipo
                          </span>
                        </div>
                      </div>

                      {attachmentAdvanced && (
                        <>
                          <div className="flex items-center justify-between gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                            <div className="flex items-center gap-2">
                              {wrapTooltip(
                                attachmentAdvanced,
                                <button
                                  type="button"
                                  onClick={() => setAttachmentMode('rag_local')}
                                  className={cn(
                                    'h-6 px-2 rounded-md text-[10px] font-semibold transition-all',
                                    attachmentMode === 'rag_local'
                                      ? 'bg-emerald-200 text-slate-900'
                                      : 'bg-slate-200 text-slate-600 hover:bg-slate-300'
                                  )}
                                >
                                  RAG Local
                                </button>,
                                'Pros: recupera trechos relevantes e reduz alucinacao. Contras: pode ser mais lento e depende de indexacao.',
                                'left'
                              )}
                              <span className="text-[10px] text-muted-foreground">
                                Mais preciso para fatos/citações
                              </span>
                            </div>
                          </div>

                          <div className="flex items-center justify-between gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                            <div className="flex items-center gap-2">
                              {wrapTooltip(
                                attachmentAdvanced,
                                <button
                                  type="button"
                                  onClick={() => setAttachmentMode('prompt_injection')}
                                  className={cn(
                                    'h-6 px-2 rounded-md text-[10px] font-semibold transition-all',
                                    attachmentMode === 'prompt_injection'
                                      ? 'bg-emerald-200 text-slate-900'
                                      : 'bg-slate-200 text-slate-600 hover:bg-slate-300'
                                  )}
                                >
                                  Injecao direta
                                </button>,
                                'Pros: simples e imediato. Contras: consome muitos tokens e pode truncar documentos grandes.',
                                'left'
                              )}
                              <span className="text-[10px] text-muted-foreground">
                                Rápido para poucos arquivos
                              </span>
                            </div>
                          </div>
                        </>
                      )}
                    </div>

                    <div className="rounded-lg border border-dashed border-slate-200 bg-white/80 px-3 py-2 text-[10px] text-muted-foreground">
                      <div className="font-semibold text-slate-600">
                        {hasAttachmentModel
                          ? attachmentModels.length > 1
                            ? 'Limites por modelo'
                            : `Limites do ${attachmentModels[0].label}`
                          : 'Limites de anexos'}
                      </div>
                      {hasAttachmentModel ? (
                        <div className="mt-1 space-y-1">
                          {attachmentModels.map((model) => (
                            <div key={model.id}>
                              {model.label}: até {model.maxLabel} / arquivo
                            </div>
                          ))}
                          {attachmentModels.length > 1 && (
                            <div className="text-[10px] text-muted-foreground">
                              Limite efetivo (multi-modelo): {attachmentLimits.effectiveMaxLabel} /
                              arquivo
                            </div>
                          )}
                          <div>Quantidade: {attachmentCountLabel}</div>
                          <div>Tipos: {attachmentLimits.typesLabel}</div>
                        </div>
                      ) : (
                        <div className="mt-1">Selecione um modelo para ver os limites.</div>
                      )}
                    </div>
                  </div>
                </div>
              </PopoverContent>
            </Popover>

            <Popover>
              <PopoverTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  title="Parâmetros por modelo"
                  className={cn(
                    'h-7 w-7 rounded-full transition-colors',
                    hasModelParamOptions
                      ? 'text-emerald-600 bg-emerald-500/10'
                      : 'text-slate-500 hover:bg-slate-100 hover:text-slate-700'
                  )}
                >
                  <SlidersHorizontal className="h-3.5 w-3.5" />
                </Button>
              </PopoverTrigger>
              <PopoverContent
                className="w-[380px] max-h-[70vh] overflow-y-auto p-4 pr-3 space-y-4 overscroll-contain"
                align="start"
                sideOffset={8}
                collisionPadding={12}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex flex-col gap-0.5">
                    <Label className="text-sm font-medium">Parâmetros por modelo</Label>
                    <span className="text-xs text-muted-foreground">
                      Ajustes de raciocínio e parâmetros avançados
                    </span>
                  </div>
                  <span className="rounded-full bg-slate-100 px-2 py-1 text-[9px] font-semibold text-slate-600">
                    ADV
                  </span>
                </div>

                <div className="space-y-3 rounded-2xl border border-slate-200 bg-white/70 p-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex flex-col gap-0.5">
                      <Label className="text-sm font-medium">Parâmetros de raciocínio</Label>
                      <span className="text-xs text-muted-foreground">
                        Variam conforme o modelo selecionado
                      </span>
                    </div>
                    <span className="rounded-full bg-slate-100 px-2 py-1 text-[9px] font-semibold text-slate-600">
                      THINK
                    </span>
                  </div>

                  {!hasSingleModel && (
                    <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-[11px] text-slate-600">
                      No modo Comparar modelos, use overrides por modelo abaixo.
                    </div>
                  )}

                  {showPerModelOverrides && (
                    <div className="space-y-2">
                      {activeModelIds.map((modelId) => {
                        const cfg = getModelConfig(modelId as ModelId);
                        const override = modelOverrides?.[modelId] || {};
                        const lower = String(modelId || '').toLowerCase();
                        const isClaude = lower.startsWith('claude');
                        const isGpt52 = lower.startsWith('gpt-5.2');
                        const isGpt5 = lower.startsWith('gpt-5') && !isGpt52;
                        const isGeminiPro = lower === 'gemini-3-pro';
                        const isGeminiFlash = lower === 'gemini-3-flash';
                        const overrideReasoning = override.reasoningLevel;

                        const thinkingOptions = isGpt52
                          ? (['none', 'low', 'medium', 'high', 'xhigh'] as const)
                          : isGpt5
                            ? (['minimal', 'low', 'medium', 'high'] as const)
                            : isGeminiPro
                              ? (['low', 'high'] as const)
                              : isGeminiFlash
                                ? (['minimal', 'low', 'medium', 'high'] as const)
                                : null;

                        const budgetHint = lower.includes('sonnet') ? '0-31999' : '0-63999';

                        return (
                          <div key={modelId} className="rounded-md border p-2 text-[11px] space-y-2">
                            <div className="font-semibold">{cfg?.label || modelId}</div>

                            {thinkingOptions && (
                              <div className="space-y-2">
                                <Label className="text-[10px] font-semibold uppercase text-slate-500">
                                  {isGeminiPro || isGeminiFlash
                                    ? 'Thinking level'
                                    : 'Reasoning effort'}
                                </Label>
                                <div className="flex flex-wrap gap-1">
                                  <button
                                    type="button"
                                    onClick={() => setModelOverride(modelId, { reasoningLevel: undefined })}
                                    className={cn(
                                      'rounded-full border px-2 py-1 text-[10px] font-semibold transition-colors',
                                      !overrideReasoning
                                        ? 'border-emerald-200 bg-emerald-500/15 text-emerald-700'
                                        : 'border-slate-200 text-slate-500 hover:bg-slate-100 hover:text-slate-700'
                                    )}
                                  >
                                    Auto
                                  </button>
                                  {thinkingOptions.map((level) => (
                                    <button
                                      key={level}
                                      type="button"
                                      onClick={() => setModelOverride(modelId, { reasoningLevel: level })}
                                      className={cn(
                                        'rounded-full border px-2 py-1 text-[10px] font-semibold transition-colors',
                                        overrideReasoning === level
                                          ? 'border-emerald-200 bg-emerald-500/15 text-emerald-700'
                                          : 'border-slate-200 text-slate-500 hover:bg-slate-100 hover:text-slate-700'
                                      )}
                                    >
                                      {String(level).toUpperCase()}
                                    </button>
                                  ))}
                                </div>
                              </div>
                            )}

                            {isClaude && (
                              <div className="space-y-2">
                                <Label className="text-[10px] font-semibold uppercase text-slate-500">
                                  Thinking budget (Claude)
                                </Label>
                                <Input
                                  value={override.thinkingBudget ?? ''}
                                  onChange={(e) =>
                                    setModelOverride(modelId, { thinkingBudget: e.target.value })
                                  }
                                  placeholder={`Auto (${budgetHint})`}
                                  inputMode="numeric"
                                  className="h-8 text-xs"
                                />
                              </div>
                            )}

                            <div className="space-y-2">
                              <Label className="text-[10px] font-semibold uppercase text-slate-500">
                                Verbosidade
                              </Label>
                              <div className="flex gap-1 rounded-lg bg-slate-100 p-1">
                                {(['auto', 'low', 'medium', 'high'] as const).map((level) => (
                                  <button
                                    key={level}
                                    onClick={() =>
                                      setModelOverride(modelId, {
                                        verbosity: level === 'auto' ? undefined : level,
                                      })
                                    }
                                    className={cn(
                                      'flex-1 px-2 py-1 text-[10px] font-medium rounded-md transition-all',
                                      (level === 'auto'
                                        ? !override.verbosity
                                        : override.verbosity === level)
                                        ? 'bg-emerald-600/15 text-emerald-700 shadow-sm'
                                        : 'text-slate-500 hover:bg-slate-100 hover:text-slate-700'
                                    )}
                                  >
                                    {level === 'auto'
                                      ? 'Auto'
                                      : level === 'low'
                                        ? 'Baixa'
                                        : level === 'medium'
                                          ? 'Media'
                                          : 'Alta'}
                                  </button>
                                ))}
                              </div>
                            </div>
                          </div>
                        );
                      })}
                      <span className="text-[10px] text-muted-foreground">
                        Overrides so se aplicam no modo Comparar modelos.
                      </span>
                    </div>
                  )}

                  {showThinkingParams && isClaudeSelected && (
                    <div className="space-y-2">
                      <Label className="text-xs font-semibold uppercase text-slate-500">
                        Thinking budget (Claude 4.5)
                      </Label>
                      <Input
                        value={thinkingBudget}
                        onChange={(e) => setThinkingBudget(e.target.value)}
                        placeholder="Auto"
                        inputMode="numeric"
                        className="h-8 text-xs"
                      />
                      <span className="text-[10px] text-muted-foreground">
                        Define budget_tokens para ativar thinking. Deve ser menor que max_tokens.
                      </span>
                      <span className="text-[10px] text-muted-foreground">
                        Intervalo: {claudeBudgetHint}
                      </span>
                    </div>
                  )}

                  {showThinkingParams && isGpt52Selected && (
                    <div className="space-y-2">
                      <Label className="text-xs font-semibold uppercase text-slate-500">
                        Reasoning level (GPT‑5.2)
                      </Label>
                      <div className="flex flex-wrap gap-1">
                        {(['none', 'low', 'medium', 'high', 'xhigh'] as const).map((level) => (
                          <button
                            key={level}
                            type="button"
                            onClick={() => setReasoningLevel(level)}
                            className={cn(
                              'rounded-full border px-2 py-1 text-[10px] font-semibold transition-colors',
                              reasoningLevel === level
                                ? 'border-emerald-200 bg-emerald-500/15 text-emerald-700'
                                : 'border-slate-200 text-slate-500 hover:bg-slate-100 hover:text-slate-700'
                            )}
                          >
                            {level === 'none' ? 'None' : level.toUpperCase()}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}

                  {showThinkingParams && isGeminiProSelected && (
                    <div className="space-y-2">
                      <Label className="text-xs font-semibold uppercase text-slate-500">
                        Thinking level (Gemini 3 Pro)
                      </Label>
                      <div className="flex flex-wrap gap-1">
                        {(['low', 'high'] as const).map((level) => (
                          <button
                            key={level}
                            type="button"
                            onClick={() => setReasoningLevel(level)}
                            className={cn(
                              'rounded-full border px-2 py-1 text-[10px] font-semibold transition-colors',
                              reasoningLevel === level
                                ? 'border-emerald-200 bg-emerald-500/15 text-emerald-700'
                                : 'border-slate-200 text-slate-500 hover:bg-slate-100 hover:text-slate-700'
                            )}
                          >
                            {level === 'low' ? 'Low' : 'High'}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}

                  {showThinkingParams && isGeminiFlashSelected && (
                    <div className="space-y-2">
                      <Label className="text-xs font-semibold uppercase text-slate-500">
                        Thinking level (Gemini 3 Flash)
                      </Label>
                      <div className="flex flex-wrap gap-1">
                        {(['minimal', 'low', 'medium', 'high'] as const).map((level) => (
                          <button
                            key={level}
                            type="button"
                            onClick={() => setReasoningLevel(level)}
                            className={cn(
                              'rounded-full border px-2 py-1 text-[10px] font-semibold transition-colors',
                              reasoningLevel === level
                                ? 'border-emerald-200 bg-emerald-500/15 text-emerald-700'
                                : 'border-slate-200 text-slate-500 hover:bg-slate-100 hover:text-slate-700'
                            )}
                          >
                            {level === 'minimal' ? 'Minimal' : level === 'low' ? 'Low' : level === 'medium' ? 'Medium' : 'High'}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                </div>

                <div className="space-y-3 rounded-2xl border border-slate-200 bg-white/70 p-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex flex-col gap-0.5">
                      <Label className="text-sm font-medium">Verbosidade</Label>
                      <span className="text-xs text-muted-foreground">
                        Controla o nível de detalhe da resposta
                      </span>
                    </div>
                    <span className="rounded-full bg-slate-100 px-2 py-1 text-[9px] font-semibold text-slate-600">
                      STYLE
                    </span>
                  </div>

                  <div className="flex gap-1 rounded-lg bg-slate-100 p-1">
                    {(['low', 'medium', 'high'] as const).map((level) => (
                      <button
                        key={level}
                        onClick={() => setVerbosity(level)}
                        className={cn(
                          'flex-1 px-2 py-1.5 text-xs font-medium rounded-md transition-all',
                          verbosity === level
                            ? 'bg-emerald-600/15 text-emerald-700 shadow-sm'
                            : 'text-slate-500 hover:bg-slate-100 hover:text-slate-700'
                        )}
                      >
                        {level === 'low' ? 'Baixa' : level === 'medium' ? 'Media' : 'Alta'}
                      </button>
                    ))}
                  </div>
                </div>

                {!hasModelParamOptions && (
                  <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-[11px] text-slate-600">
                    Para opções específicas do Perplexity: ative Web Search, selecione um modelo Sonar (chat)
                    ou habilite Deep Research (Perplexity).
                  </div>
                )}

                {showPerplexitySonarParams && (
                  <div className="space-y-3 rounded-2xl border border-slate-200 bg-white/70 p-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex flex-col gap-0.5">
                        <Label className="text-sm font-medium">Perplexity Sonar (Chat)</Label>
                        <span className="text-xs text-muted-foreground">
                          Chat web-grounded com fontes
                        </span>
                      </div>
                      <span className="rounded-full bg-slate-100 px-2 py-1 text-[9px] font-semibold text-slate-600">
                        SONAR
                      </span>
                    </div>

                    <div className="space-y-2">
                      <Label className="text-xs font-semibold uppercase text-slate-500">
                        Search focus
                      </Label>
                      <div className="flex flex-wrap gap-1">
                        {(['web', 'academic', 'sec'] as const).map((mode) => (
                          <button
                            key={mode}
                            type="button"
                            onClick={() => setPerplexitySearchMode(mode)}
                            className={cn(
                              'rounded-full border px-2 py-1 text-[10px] font-semibold transition-colors',
                              perplexitySearchMode === mode
                                ? 'border-emerald-200 bg-emerald-500/15 text-emerald-700'
                                : 'border-slate-200 text-slate-500 hover:bg-slate-100 hover:text-slate-700'
                            )}
                          >
                            {mode === 'web' ? 'Web' : mode === 'academic' ? 'Acadêmico' : 'SEC'}
                          </button>
                        ))}
                      </div>
                    </div>

                    <div className="space-y-2">
                      <Label className="text-xs font-semibold uppercase text-slate-500">
                        Search context size
                      </Label>
                      <div className="flex flex-wrap gap-1">
                        {(['low', 'medium', 'high'] as const).map((size) => (
                          <button
                            key={size}
                            type="button"
                            onClick={() => setPerplexitySearchContextSize(size)}
                            className={cn(
                              'rounded-full border px-2 py-1 text-[10px] font-semibold transition-colors',
                              perplexitySearchContextSize === size
                                ? 'border-emerald-200 bg-emerald-500/15 text-emerald-700'
                                : 'border-slate-200 text-slate-500 hover:bg-slate-100 hover:text-slate-700'
                            )}
                          >
                            {size === 'low' ? 'Low' : size === 'medium' ? 'Medium' : 'High'}
                          </button>
                        ))}
                      </div>
                    </div>

                    {isSonarProSelected && (
                      <div className="space-y-2">
                        <Label className="text-xs font-semibold uppercase text-slate-500">
                          Search type (Sonar Pro)
                        </Label>
                        <div className="flex flex-wrap gap-1">
                          {(['fast', 'pro', 'auto'] as const).map((mode) => (
                            <button
                              key={mode}
                              type="button"
                              onClick={() => setPerplexitySearchType(mode)}
                              className={cn(
                                'rounded-full border px-2 py-1 text-[10px] font-semibold transition-colors',
                                perplexitySearchType === mode
                                  ? 'border-emerald-200 bg-emerald-500/15 text-emerald-700'
                                  : 'border-slate-200 text-slate-500 hover:bg-slate-100 hover:text-slate-700'
                              )}
                            >
                              {mode === 'fast' ? 'Fast' : mode === 'pro' ? 'Pro' : 'Auto'}
                            </button>
                          ))}
                        </div>
                      </div>
                    )}

                    <div className="grid gap-2">
                      <div className="space-y-1">
                        <Label className="text-[10px] font-semibold uppercase text-slate-500">
                          Search domain filter
                        </Label>
                        <Input
                          value={perplexitySearchDomainFilter}
                          onChange={(e) => setPerplexitySearchDomainFilter(e.target.value)}
                          placeholder="ex: stf.jus.br, -pinterest.com"
                          className="h-8 text-xs"
                        />
                      </div>
                      <div className="space-y-1">
                        <Label className="text-[10px] font-semibold uppercase text-slate-500">
                          Language filter
                        </Label>
                        <Input
                          value={perplexitySearchLanguageFilter}
                          onChange={(e) => setPerplexitySearchLanguageFilter(e.target.value)}
                          placeholder="ex: pt,en"
                          className="h-8 text-xs"
                        />
                      </div>
                    </div>

                    <div className="space-y-2">
                      <Label className="text-xs font-semibold uppercase text-slate-500">
                        Recency filter
                      </Label>
                      <div className="flex flex-wrap gap-1">
                        {recencyOptions.map((opt) => (
                          <button
                            key={opt.value || 'all'}
                            type="button"
                            onClick={() => setPerplexitySearchRecencyFilter(opt.value)}
                            className={cn(
                              'rounded-full border px-2 py-1 text-[10px] font-semibold transition-colors',
                              perplexitySearchRecencyFilter === opt.value
                                ? 'border-emerald-200 bg-emerald-500/15 text-emerald-700'
                                : 'border-slate-200 text-slate-500 hover:bg-slate-100 hover:text-slate-700'
                            )}
                          >
                            {opt.label}
                          </button>
                        ))}
                      </div>
                    </div>

                    <div className="grid gap-2">
                      <div className="grid grid-cols-2 gap-2">
                        <div className="space-y-1">
                          <Label className="text-[10px] font-semibold uppercase text-slate-500">
                            Published after
                          </Label>
                          <Input
                            type="date"
                            value={perplexitySearchAfterDate}
                            onChange={(e) => setPerplexitySearchAfterDate(e.target.value)}
                            className="h-8 text-xs"
                          />
                        </div>
                        <div className="space-y-1">
                          <Label className="text-[10px] font-semibold uppercase text-slate-500">
                            Published before
                          </Label>
                          <Input
                            type="date"
                            value={perplexitySearchBeforeDate}
                            onChange={(e) => setPerplexitySearchBeforeDate(e.target.value)}
                            className="h-8 text-xs"
                          />
                        </div>
                      </div>
                      <div className="grid grid-cols-2 gap-2">
                        <div className="space-y-1">
                          <Label className="text-[10px] font-semibold uppercase text-slate-500">
                            Last updated after
                          </Label>
                          <Input
                            type="date"
                            value={perplexityLastUpdatedAfter}
                            onChange={(e) => setPerplexityLastUpdatedAfter(e.target.value)}
                            className="h-8 text-xs"
                          />
                        </div>
                        <div className="space-y-1">
                          <Label className="text-[10px] font-semibold uppercase text-slate-500">
                            Last updated before
                          </Label>
                          <Input
                            type="date"
                            value={perplexityLastUpdatedBefore}
                            onChange={(e) => setPerplexityLastUpdatedBefore(e.target.value)}
                            className="h-8 text-xs"
                          />
                        </div>
                      </div>
                    </div>

                    <div className="grid gap-2">
                      <div className="grid grid-cols-2 gap-2">
                        <div className="space-y-1">
                          <Label className="text-[10px] font-semibold uppercase text-slate-500">
                            Max results
                          </Label>
                          <Input
                            type="number"
                            min={1}
                            max={20}
                            value={perplexitySearchMaxResults}
                            onChange={(e) => setPerplexitySearchMaxResults(e.target.value)}
                            placeholder="1-20"
                            className="h-8 text-xs"
                          />
                        </div>
                        <div className="space-y-1">
                          <Label className="text-[10px] font-semibold uppercase text-slate-500">
                            Max tokens/page
                          </Label>
                          <Input
                            type="number"
                            min={1}
                            max={1_000_000}
                            value={perplexitySearchMaxTokensPerPage}
                            onChange={(e) => setPerplexitySearchMaxTokensPerPage(e.target.value)}
                            placeholder="2048"
                            className="h-8 text-xs"
                          />
                        </div>
                      </div>
                      <div className="space-y-1">
                        <Label className="text-[10px] font-semibold uppercase text-slate-500">
                          Max tokens (total)
                        </Label>
                        <Input
                          type="number"
                          min={1}
                          max={1_000_000}
                          value={perplexitySearchMaxTokens}
                          onChange={(e) => setPerplexitySearchMaxTokens(e.target.value)}
                          placeholder="25000"
                          className="h-8 text-xs"
                        />
                      </div>
                    </div>

                    <div className="grid gap-2">
                      <div className="grid grid-cols-3 gap-2">
                        <div className="space-y-1">
                          <Label className="text-[10px] font-semibold uppercase text-slate-500">
                            Country
                          </Label>
                          <Input
                            value={perplexitySearchCountry}
                            onChange={(e) => setPerplexitySearchCountry(e.target.value)}
                            placeholder="BR"
                            className="h-8 text-xs"
                          />
                        </div>
                        <div className="space-y-1">
                          <Label className="text-[10px] font-semibold uppercase text-slate-500">
                            Region
                          </Label>
                          <Input
                            value={perplexitySearchRegion}
                            onChange={(e) => setPerplexitySearchRegion(e.target.value)}
                            placeholder="SP"
                            className="h-8 text-xs"
                          />
                        </div>
                        <div className="space-y-1">
                          <Label className="text-[10px] font-semibold uppercase text-slate-500">
                            City
                          </Label>
                          <Input
                            value={perplexitySearchCity}
                            onChange={(e) => setPerplexitySearchCity(e.target.value)}
                            placeholder="São Paulo"
                            className="h-8 text-xs"
                          />
                        </div>
                      </div>
                      <div className="grid grid-cols-2 gap-2">
                        <div className="space-y-1">
                          <Label className="text-[10px] font-semibold uppercase text-slate-500">
                            Latitude
                          </Label>
                          <Input
                            type="number"
                            step="0.0001"
                            value={perplexitySearchLatitude}
                            onChange={(e) => setPerplexitySearchLatitude(e.target.value)}
                            placeholder="-23.5505"
                            className="h-8 text-xs"
                          />
                        </div>
                        <div className="space-y-1">
                          <Label className="text-[10px] font-semibold uppercase text-slate-500">
                            Longitude
                          </Label>
                          <Input
                            type="number"
                            step="0.0001"
                            value={perplexitySearchLongitude}
                            onChange={(e) => setPerplexitySearchLongitude(e.target.value)}
                            placeholder="-46.6333"
                            className="h-8 text-xs"
                          />
                        </div>
                      </div>
                    </div>

                    <div className="grid grid-cols-1 gap-2">
                      <div className="flex items-center justify-between rounded-xl border border-slate-200 bg-slate-50 px-3 py-2">
                        <div>
                          <p className="text-[11px] font-semibold text-slate-700">Return images</p>
                          <p className="text-[10px] text-slate-500">Incluir imagens na busca</p>
                        </div>
                        <Switch
                          checked={perplexityReturnImages}
                          onCheckedChange={setPerplexityReturnImages}
                        />
                      </div>
                      <div className="flex items-center justify-between rounded-xl border border-slate-200 bg-slate-50 px-3 py-2">
                        <div>
                          <p className="text-[11px] font-semibold text-slate-700">Return videos</p>
                          <p className="text-[10px] text-slate-500">
                            Incluir videos nos resultados
                          </p>
                        </div>
                        <Switch
                          checked={perplexityReturnVideos}
                          onCheckedChange={setPerplexityReturnVideos}
                        />
                      </div>
                    </div>

                    <div className="grid grid-cols-1 gap-2">
                      {isSonarProSelected && (
                        <div className="flex items-center justify-between rounded-xl border border-slate-200 bg-slate-50 px-3 py-2">
                          <div>
                            <p className="text-[11px] font-semibold text-slate-700">
                              Classificador automático
                            </p>
                            <p className="text-[10px] text-slate-500">
                              Habilita roteamento Fast/Pro
                            </p>
                          </div>
                          <Switch
                            checked={perplexitySearchClassifier}
                            onCheckedChange={setPerplexitySearchClassifier}
                          />
                        </div>
                      )}
                      <div className="flex items-center justify-between rounded-xl border border-slate-200 bg-slate-50 px-3 py-2">
                        <div>
                          <p className="text-[11px] font-semibold text-slate-700">
                            Desativar busca
                          </p>
                          <p className="text-[10px] text-slate-500">Resposta sem pesquisa web</p>
                        </div>
                        <Switch
                          checked={perplexityDisableSearch}
                          onCheckedChange={setPerplexityDisableSearch}
                        />
                      </div>
                    </div>

                    <div className="space-y-2">
                      <Label className="text-xs font-semibold uppercase text-slate-500">
                        Stream mode
                      </Label>
                      <div className="flex flex-wrap gap-1">
                        {(['full', 'concise'] as const).map((mode) => (
                          <button
                            key={mode}
                            type="button"
                            onClick={() => setPerplexityStreamMode(mode)}
                            className={cn(
                              'rounded-full border px-2 py-1 text-[10px] font-semibold transition-colors',
                              perplexityStreamMode === mode
                                ? 'border-emerald-200 bg-emerald-500/15 text-emerald-700'
                                : 'border-slate-200 text-slate-500 hover:bg-slate-100 hover:text-slate-700'
                            )}
                          >
                            {mode === 'full' ? 'Full' : 'Concise'}
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>
                )}

                {showPerplexitySearchApiParams && (
                  <div className="space-y-3 rounded-2xl border border-slate-200 bg-white/70 p-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex flex-col gap-0.5">
                        <Label className="text-sm font-medium">
                          Perplexity Search API (Compartilhada)
                        </Label>
                        <span className="text-xs text-muted-foreground">
                          Filtros da busca compartilhada
                        </span>
                      </div>
                      <span className="rounded-full bg-slate-100 px-2 py-1 text-[9px] font-semibold text-slate-600">
                        API
                      </span>
                    </div>

                    {showSearchFocusInSearchApi && (
                      <div className="space-y-2">
                        <Label className="text-xs font-semibold uppercase text-slate-500">
                          Search focus
                        </Label>
                        <div className="flex flex-wrap gap-1">
                          {(['web', 'academic', 'sec'] as const).map((mode) => (
                            <button
                              key={mode}
                              type="button"
                              onClick={() => setPerplexitySearchMode(mode)}
                              className={cn(
                                'rounded-full border px-2 py-1 text-[10px] font-semibold transition-colors',
                                perplexitySearchMode === mode
                                  ? 'border-emerald-200 bg-emerald-500/15 text-emerald-700'
                                  : 'border-slate-200 text-slate-500 hover:bg-slate-100 hover:text-slate-700'
                              )}
                            >
                              {mode === 'web' ? 'Web' : mode === 'academic' ? 'Acadêmico' : 'SEC'}
                            </button>
                          ))}
                        </div>
                      </div>
                    )}

                    <div className="grid gap-2">
                      <div className="space-y-1">
                        <Label className="text-[10px] font-semibold uppercase text-slate-500">
                          Search domain filter
                        </Label>
                        <Input
                          value={perplexitySearchDomainFilter}
                          onChange={(e) => setPerplexitySearchDomainFilter(e.target.value)}
                          placeholder="ex: stf.jus.br, -pinterest.com"
                          className="h-8 text-xs"
                        />
                      </div>
                      <div className="space-y-1">
                        <Label className="text-[10px] font-semibold uppercase text-slate-500">
                          Language filter
                        </Label>
                        <Input
                          value={perplexitySearchLanguageFilter}
                          onChange={(e) => setPerplexitySearchLanguageFilter(e.target.value)}
                          placeholder="ex: pt,en"
                          className="h-8 text-xs"
                        />
                      </div>
                    </div>

                    <div className="space-y-2">
                      <Label className="text-xs font-semibold uppercase text-slate-500">
                        Recency filter
                      </Label>
                      <div className="flex flex-wrap gap-1">
                        {recencyOptions.map((opt) => (
                          <button
                            key={opt.value || 'all'}
                            type="button"
                            onClick={() => setPerplexitySearchRecencyFilter(opt.value)}
                            className={cn(
                              'rounded-full border px-2 py-1 text-[10px] font-semibold transition-colors',
                              perplexitySearchRecencyFilter === opt.value
                                ? 'border-emerald-200 bg-emerald-500/15 text-emerald-700'
                                : 'border-slate-200 text-slate-500 hover:bg-slate-100 hover:text-slate-700'
                            )}
                          >
                            {opt.label}
                          </button>
                        ))}
                      </div>
                    </div>

                    <div className="grid gap-2">
                      <div className="grid grid-cols-2 gap-2">
                        <div className="space-y-1">
                          <Label className="text-[10px] font-semibold uppercase text-slate-500">
                            Published after
                          </Label>
                          <Input
                            type="date"
                            value={perplexitySearchAfterDate}
                            onChange={(e) => setPerplexitySearchAfterDate(e.target.value)}
                            className="h-8 text-xs"
                          />
                        </div>
                        <div className="space-y-1">
                          <Label className="text-[10px] font-semibold uppercase text-slate-500">
                            Published before
                          </Label>
                          <Input
                            type="date"
                            value={perplexitySearchBeforeDate}
                            onChange={(e) => setPerplexitySearchBeforeDate(e.target.value)}
                            className="h-8 text-xs"
                          />
                        </div>
                      </div>
                      <div className="grid grid-cols-2 gap-2">
                        <div className="space-y-1">
                          <Label className="text-[10px] font-semibold uppercase text-slate-500">
                            Last updated after
                          </Label>
                          <Input
                            type="date"
                            value={perplexityLastUpdatedAfter}
                            onChange={(e) => setPerplexityLastUpdatedAfter(e.target.value)}
                            className="h-8 text-xs"
                          />
                        </div>
                        <div className="space-y-1">
                          <Label className="text-[10px] font-semibold uppercase text-slate-500">
                            Last updated before
                          </Label>
                          <Input
                            type="date"
                            value={perplexityLastUpdatedBefore}
                            onChange={(e) => setPerplexityLastUpdatedBefore(e.target.value)}
                            className="h-8 text-xs"
                          />
                        </div>
                      </div>
                    </div>

                    <div className="grid gap-2">
                      <div className="grid grid-cols-3 gap-2">
                        <div className="space-y-1">
                          <Label className="text-[10px] font-semibold uppercase text-slate-500">
                            Country
                          </Label>
                          <Input
                            value={perplexitySearchCountry}
                            onChange={(e) => setPerplexitySearchCountry(e.target.value)}
                            placeholder="BR"
                            className="h-8 text-xs"
                          />
                        </div>
                        <div className="space-y-1">
                          <Label className="text-[10px] font-semibold uppercase text-slate-500">
                            Region
                          </Label>
                          <Input
                            value={perplexitySearchRegion}
                            onChange={(e) => setPerplexitySearchRegion(e.target.value)}
                            placeholder="SP"
                            className="h-8 text-xs"
                          />
                        </div>
                        <div className="space-y-1">
                          <Label className="text-[10px] font-semibold uppercase text-slate-500">
                            City
                          </Label>
                          <Input
                            value={perplexitySearchCity}
                            onChange={(e) => setPerplexitySearchCity(e.target.value)}
                            placeholder="São Paulo"
                            className="h-8 text-xs"
                          />
                        </div>
                      </div>
                      <div className="grid grid-cols-2 gap-2">
                        <div className="space-y-1">
                          <Label className="text-[10px] font-semibold uppercase text-slate-500">
                            Latitude
                          </Label>
                          <Input
                            type="number"
                            step="0.0001"
                            value={perplexitySearchLatitude}
                            onChange={(e) => setPerplexitySearchLatitude(e.target.value)}
                            placeholder="-23.5505"
                            className="h-8 text-xs"
                          />
                        </div>
                        <div className="space-y-1">
                          <Label className="text-[10px] font-semibold uppercase text-slate-500">
                            Longitude
                          </Label>
                          <Input
                            type="number"
                            step="0.0001"
                            value={perplexitySearchLongitude}
                            onChange={(e) => setPerplexitySearchLongitude(e.target.value)}
                            placeholder="-46.6333"
                            className="h-8 text-xs"
                          />
                        </div>
                      </div>
                    </div>

                    <div className="grid grid-cols-1 gap-2">
                      <div className="flex items-center justify-between rounded-xl border border-slate-200 bg-slate-50 px-3 py-2">
                        <div>
                          <p className="text-[11px] font-semibold text-slate-700">
                            Return images
                          </p>
                          <p className="text-[10px] text-slate-500">Incluir imagens na busca</p>
                        </div>
                        <Switch
                          checked={perplexityReturnImages}
                          onCheckedChange={setPerplexityReturnImages}
                        />
                      </div>
                      <div className="flex items-center justify-between rounded-xl border border-slate-200 bg-slate-50 px-3 py-2">
                        <div>
                          <p className="text-[11px] font-semibold text-slate-700">Return videos</p>
                          <p className="text-[10px] text-slate-500">
                            Incluir videos nos resultados
                          </p>
                        </div>
                        <Switch
                          checked={perplexityReturnVideos}
                          onCheckedChange={setPerplexityReturnVideos}
                        />
                      </div>
                    </div>
                  </div>
                )}

                {enableDeepResearchParams && (
                  <div className="space-y-3 rounded-2xl border border-slate-200 bg-white/70 p-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex flex-col gap-0.5">
                        <Label className="text-sm font-medium">Perplexity Deep Research</Label>
                        <span className="text-xs text-muted-foreground">
                          Pesquisa multi-etapas e raciocinio profundo
                        </span>
                      </div>
                      <span className="rounded-full bg-slate-100 px-2 py-1 text-[9px] font-semibold text-slate-600">
                        DR
                      </span>
                    </div>

                    <div className="space-y-2">
                      <Label className="text-xs font-semibold uppercase text-slate-500">
                        Reasoning effort
                      </Label>
                      <div className="flex flex-wrap gap-1">
                        {(['low', 'medium', 'high'] as const).map((level) => (
                          <button
                            key={level}
                            type="button"
                            onClick={() => setDeepResearchEffort(level)}
                            className={cn(
                              'rounded-full border px-2 py-1 text-[10px] font-semibold transition-colors',
                              deepResearchEffort === level
                                ? 'border-emerald-200 bg-emerald-500/15 text-emerald-700'
                                : 'border-slate-200 text-slate-500 hover:bg-slate-100 hover:text-slate-700'
                            )}
                          >
                            {level === 'low' ? 'Low' : level === 'medium' ? 'Medium' : 'High'}
                          </button>
                        ))}
                      </div>
                    </div>

                    <div className="space-y-2">
                      <Label className="text-xs font-semibold uppercase text-slate-500">
                        Search focus
                      </Label>
                      <div className="flex flex-wrap gap-1">
                        <button
                          type="button"
                          onClick={() => setDeepResearchSearchFocus('')}
                          className={cn(
                            'rounded-full border px-2 py-1 text-[10px] font-semibold transition-colors',
                            deepResearchSearchFocus === ''
                              ? 'border-emerald-200 bg-emerald-500/15 text-emerald-700'
                              : 'border-slate-200 text-slate-500 hover:bg-slate-100 hover:text-slate-700'
                          )}
                        >
                          Auto
                        </button>
                        {(['web', 'academic', 'sec'] as const).map((mode) => (
                          <button
                            key={mode}
                            type="button"
                            onClick={() => setDeepResearchSearchFocus(mode)}
                            className={cn(
                              'rounded-full border px-2 py-1 text-[10px] font-semibold transition-colors',
                              deepResearchSearchFocus === mode
                                ? 'border-emerald-200 bg-emerald-500/15 text-emerald-700'
                                : 'border-slate-200 text-slate-500 hover:bg-slate-100 hover:text-slate-700'
                            )}
                          >
                            {mode === 'web' ? 'Web' : mode === 'academic' ? 'Acadêmico' : 'SEC'}
                          </button>
                        ))}
                      </div>
                    </div>

                    <div className="space-y-1">
                      <Label className="text-[10px] font-semibold uppercase text-slate-500">
                        Search domain filter
                      </Label>
                      <Input
                        value={deepResearchDomainFilter}
                        onChange={(e) => setDeepResearchDomainFilter(e.target.value)}
                        placeholder="ex: stf.jus.br, -pinterest.com"
                        className="h-8 text-xs"
                      />
                    </div>

                  <div className="grid grid-cols-2 gap-2">
                    <div className="space-y-1">
                      <Label className="text-[10px] font-semibold uppercase text-slate-500">
                        Published after
                      </Label>
                      <Input
                        type="date"
                        value={deepResearchSearchAfterDate}
                        onChange={(e) => setDeepResearchSearchAfterDate(e.target.value)}
                        className="h-8 text-xs"
                      />
                    </div>
                    <div className="space-y-1">
                      <Label className="text-[10px] font-semibold uppercase text-slate-500">
                        Published before
                      </Label>
                      <Input
                        type="date"
                        value={deepResearchSearchBeforeDate}
                        onChange={(e) => setDeepResearchSearchBeforeDate(e.target.value)}
                        className="h-8 text-xs"
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-2">
                    <div className="space-y-1">
                      <Label className="text-[10px] font-semibold uppercase text-slate-500">
                        Last updated after
                      </Label>
                      <Input
                        type="date"
                        value={deepResearchLastUpdatedAfter}
                        onChange={(e) => setDeepResearchLastUpdatedAfter(e.target.value)}
                        className="h-8 text-xs"
                      />
                    </div>
                    <div className="space-y-1">
                      <Label className="text-[10px] font-semibold uppercase text-slate-500">
                        Last updated before
                      </Label>
                      <Input
                        type="date"
                        value={deepResearchLastUpdatedBefore}
                        onChange={(e) => setDeepResearchLastUpdatedBefore(e.target.value)}
                        className="h-8 text-xs"
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-3 gap-2">
                    <div className="space-y-1">
                      <Label className="text-[10px] font-semibold uppercase text-slate-500">
                        Country
                      </Label>
                      <Input
                        value={deepResearchCountry}
                        onChange={(e) => setDeepResearchCountry(e.target.value)}
                        placeholder="BR"
                        className="h-8 text-xs"
                      />
                    </div>
                    <div className="space-y-1">
                      <Label className="text-[10px] font-semibold uppercase text-slate-500">
                        Latitude
                      </Label>
                      <Input
                        type="number"
                        step="0.0001"
                        value={deepResearchLatitude}
                        onChange={(e) => setDeepResearchLatitude(e.target.value)}
                        placeholder="-23.5505"
                        className="h-8 text-xs"
                      />
                    </div>
                    <div className="space-y-1">
                      <Label className="text-[10px] font-semibold uppercase text-slate-500">
                        Longitude
                      </Label>
                      <Input
                        type="number"
                        step="0.0001"
                        value={deepResearchLongitude}
                        onChange={(e) => setDeepResearchLongitude(e.target.value)}
                        placeholder="-46.6333"
                        className="h-8 text-xs"
                      />
                    </div>
                  </div>
                </div>
                )}
              </PopoverContent>
            </Popover>

            <div className="h-4 w-[1px] bg-slate-200 mx-1" />

            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7 rounded-full text-slate-500 hover:bg-slate-100 hover:text-slate-700"
              onClick={handleAttachClick}
              type="button"
            >
              <Paperclip className="h-3.5 w-3.5" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7 rounded-full text-slate-500 hover:bg-slate-100 hover:text-slate-700"
            >
              <AtSign className="h-3.5 w-3.5" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7 rounded-full text-slate-500 hover:bg-slate-100 hover:text-slate-700"
            >
              <Hash className="h-3.5 w-3.5" />
            </Button>
          </div>

          <div className="ml-auto flex items-center">
            <Button
              onClick={handleSend}
              disabled={!content.trim() || disabled}
              size="icon"
              className={cn(
                'h-8 w-8 rounded-lg transition-all',
                content.trim()
                  ? 'bg-emerald-600 text-white hover:bg-emerald-500 shadow-lg shadow-emerald-500/20'
                  : 'bg-slate-100 text-slate-400 hover:bg-slate-100'
              )}
              data-testid="chat-send"
            >
              <Send className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </div>
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
