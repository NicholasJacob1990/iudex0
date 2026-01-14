'use client';

import { useState, useRef, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Send, Sparkles, ChevronDown, Paperclip, AtSign, Hash, Globe, Brain, Zap, HelpCircle, BookOpen } from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { SlashCommandMenu, type SystemCommand } from './slash-command-menu';
import { AtCommandMenu } from './at-command-menu';
import type { PredefinedPrompt } from '@/data/prompts';
import type { CustomPrompt } from '@/components/dashboard/prompt-customization';
import { useContextStore } from '@/stores/context-store';
import { useCanvasStore } from '@/stores';
import apiClient from '@/lib/api-client';
import { useChatStore } from '@/stores/chat-store';
import { toast } from 'sonner';
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { ModelSelector } from './model-selector';
import { Slider } from '@/components/ui/slider';
import { Network, Search, ShieldCheck } from 'lucide-react';


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
  const [advancedRagMode, setAdvancedRagMode] = useState(false);
  const {
    chatMode,
    selectedModels,
    webSearch, setWebSearch,
    multiQuery, setMultiQuery,
    breadthFirst, setBreadthFirst,
    searchMode, setSearchMode,
    denseResearch, setDenseResearch,
    reasoningLevel, setReasoningLevel,
    setSelectedModels, setChatMode,
    setShowMultiModelComparator,
    adaptiveRouting, setAdaptiveRouting,
    cragGate, setCragGate,
    hydeEnabled, setHydeEnabled,
    graphRagEnabled, setGraphRagEnabled,
    graphHops, setGraphHops,
    attachmentMode, setAttachmentMode,
    setPendingCanvasContext,
    thesis, setThesis
  } = useChatStore();

  const DEFAULT_COMPARE_MODELS = ['gpt-5.2', 'claude-4.5-sonnet', 'gemini-3-flash'];
  const contextCount = contextItems.length;
  const contextChipBase =
    "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold transition-colors";
  const contextChipActive = "border-emerald-200 bg-emerald-500/10 text-emerald-600";
  const contextChipInactive = "border-slate-200 text-slate-500 hover:bg-slate-100";

  const handleCompareToggle = (enabled: boolean) => {
    if (enabled) {
      // Ensure 2+ models selected for a real comparison
      const nextModels =
        selectedModels.length >= 2
          ? selectedModels
          : selectedModels.length === 1
            ? [selectedModels[0], DEFAULT_COMPARE_MODELS.find(m => m !== selectedModels[0]) || 'gpt-5.2']
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
        toast.success("Modo Multi-Modelo ativado");
      } else if (action === 'set-mode:standard') {
        setChatMode('standard');
        toast.success("Modo Padrão ativado");
      } else if (action.startsWith('insert-text:')) {
        const insertText = action.replace('insert-text:', '');
        const nextContent = content.endsWith('/')
          ? content.slice(0, -1) + insertText
          : insertText;
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
        <SlashCommandMenu
          onSelect={handleSelectPrompt}
          onClose={() => setShowSlashMenu(false)}
        />
      )}

      {showAtMenu && (
        <AtCommandMenu
          onSelect={handleSelectAt}
          onClose={() => setShowAtMenu(false)}
        />
      )}

      <div className="group relative flex flex-col gap-2 rounded-2xl border border-slate-200/80 bg-white p-2 shadow-sm focus-within:border-emerald-400/70 focus-within:ring-2 focus-within:ring-emerald-400/20 transition-all">
        {/* Context Banner - shows when text is selected from Canvas */}
        {selectedText && (
          <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/10 px-2 py-1.5 text-xs">
            <div className="flex items-center gap-2">
            <Sparkles className="h-3 w-3 text-emerald-600" />
            <span className="text-emerald-700 font-medium">
              {pendingAction === 'improve' ? 'Melhorando' : pendingAction === 'shorten' ? 'Resumindo' : 'Contexto'}:
            </span>
            <span className="text-muted-foreground truncate flex-1">
              {"\""}
              {selectedText.slice(0, 60)}
              {selectedText.length > 60 ? '...' : ''}
              {"\""}
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
                attachmentMode === 'rag_local' ? contextChipActive : contextChipInactive
              )}
            >
              <BookOpen className="h-3 w-3" />
              RAG local
              <span className="text-[9px] text-muted-foreground/70">({contextCount})</span>
            </button>
            <button
              type="button"
              onClick={() => setWebSearch(!webSearch)}
              className={cn(
                contextChipBase,
                webSearch ? contextChipActive : contextChipInactive
              )}
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
          </div>
          <div className="flex items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-2 py-1">
            <span className="text-[10px] font-semibold uppercase text-muted-foreground">Objetivo</span>
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
          placeholder={placeholder || "Descreva a minuta que você precisa... (Digite '/' para prompts, '@' para contexto)"}
          className="min-h-[60px] w-full resize-none bg-transparent px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none disabled:opacity-50"
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

            {/* AI Controls */}
            <div className="h-4 w-[1px] bg-slate-200 mx-1" />

            <Popover>
              <PopoverTrigger asChild>
                <Button variant="ghost" size="sm" className={cn("h-7 gap-1 rounded-full px-2 text-[10px] font-medium transition-colors", (webSearch || denseResearch) ? "text-emerald-600 bg-emerald-500/10" : "text-slate-500 hover:bg-slate-100 hover:text-slate-700")}>
                  {denseResearch ? <Brain className="h-3 w-3" /> : <Globe className="h-3 w-3" />}
                  {denseResearch ? "Deep Research" : (webSearch ? "Web Search" : "Offline")}
                  <ChevronDown className="h-3 w-3 opacity-50" />
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-80 p-4 space-y-4" align="start">
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <div className="flex flex-col gap-0.5">
                      <Label className="text-sm font-medium">Web Search</Label>
                      <span className="text-xs text-muted-foreground">Contexto de 10 fontes (Rápido)</span>
                    </div>
                    <Switch checked={webSearch} onCheckedChange={setWebSearch} />
                  </div>

                  <div className={cn("space-y-2", !webSearch && "opacity-50")}>
                    <div className="flex items-center gap-2">
                      <Label className="text-sm font-medium">Modo de busca</Label>
                      <TooltipProvider>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <HelpCircle className="h-3.5 w-3.5 text-muted-foreground cursor-help" />
                          </TooltipTrigger>
                          <TooltipContent side="right" className="max-w-xs text-xs">
                            Define como a busca web é executada no Modo Chat e no Modo Minuta.
                          </TooltipContent>
                        </Tooltip>
                      </TooltipProvider>
                    </div>
                    <div className="flex flex-wrap gap-1">
                      <TooltipProvider>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <button
                              type="button"
                              disabled={!webSearch}
                              onClick={() => setSearchMode('shared')}
                              className={cn(
                                "rounded-full border px-2 py-1 text-[10px] font-semibold transition-colors",
                                searchMode === 'shared'
                                  ? "border-emerald-200 bg-emerald-500/15 text-emerald-700"
                                  : "border-slate-200 text-slate-500 hover:bg-slate-100 hover:text-slate-700",
                                !webSearch && "pointer-events-none"
                              )}
                            >
                              Compartilhada
                            </button>
                          </TooltipTrigger>
                          <TooltipContent side="right" className="max-w-xs text-xs">
                            Uma única busca (pt‑BR + internacional) alimenta todos os modelos. Mais rápida e consistente.
                          </TooltipContent>
                        </Tooltip>
                      </TooltipProvider>
                      <TooltipProvider>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <button
                              type="button"
                              disabled={!webSearch}
                              onClick={() => setSearchMode('native')}
                              className={cn(
                                "rounded-full border px-2 py-1 text-[10px] font-semibold transition-colors",
                                searchMode === 'native'
                                  ? "border-emerald-200 bg-emerald-500/15 text-emerald-700"
                                  : "border-slate-200 text-slate-500 hover:bg-slate-100 hover:text-slate-700",
                                !webSearch && "pointer-events-none"
                              )}
                            >
                              Nativa por modelo
                            </button>
                          </TooltipTrigger>
                          <TooltipContent side="right" className="max-w-xs text-xs">
                            Cada modelo usa a busca do próprio provedor. Maior cobertura, mais custo e latência.
                          </TooltipContent>
                        </Tooltip>
                      </TooltipProvider>
                      <TooltipProvider>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <button
                              type="button"
                              disabled={!webSearch}
                              onClick={() => setSearchMode('hybrid')}
                              className={cn(
                                "rounded-full border px-2 py-1 text-[10px] font-semibold transition-colors",
                                searchMode === 'hybrid'
                                  ? "border-emerald-200 bg-emerald-500/15 text-emerald-700"
                                  : "border-slate-200 text-slate-500 hover:bg-slate-100 hover:text-slate-700",
                                !webSearch && "pointer-events-none"
                              )}
                            >
                              Híbrida
                            </button>
                          </TooltipTrigger>
                          <TooltipContent side="right" className="max-w-xs text-xs">
                            Usa busca compartilhada quando necessário; se todos suportarem nativo, usa nativa.
                          </TooltipContent>
                        </Tooltip>
                      </TooltipProvider>
                    </div>
                  </div>

                  <div className={cn("flex items-center justify-between", !webSearch && "opacity-50")}>
                    <div className="flex flex-col gap-0.5">
                      <div className="flex items-center gap-2">
                        <Label className="text-sm font-medium">Multi-query</Label>
                        <TooltipProvider>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <HelpCircle className="h-3.5 w-3.5 text-muted-foreground cursor-help" />
                            </TooltipTrigger>
                            <TooltipContent side="right" className="max-w-xs text-xs">
                              Gera variações da pergunta para aumentar o recall da pesquisa. Pode trazer mais fontes.
                            </TooltipContent>
                          </Tooltip>
                        </TooltipProvider>
                      </div>
                      <span className="text-xs text-muted-foreground">Busca várias reformulações automaticamente</span>
                    </div>
                    <Switch checked={multiQuery} onCheckedChange={setMultiQuery} disabled={!webSearch} />
                  </div>

                  <div className={cn("flex items-center justify-between", !webSearch && "opacity-50")}>
                    <div className="flex flex-col gap-0.5">
                      <div className="flex items-center gap-2">
                        <Label className="text-sm font-medium">Breadth-first</Label>
                        <TooltipProvider>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <HelpCircle className="h-3.5 w-3.5 text-muted-foreground cursor-help" />
                            </TooltipTrigger>
                            <TooltipContent side="right" className="max-w-xs text-xs">
                              Ativa um fluxo com subagentes para perguntas amplas. Mais cobertura, mais lento.
                            </TooltipContent>
                          </Tooltip>
                        </TooltipProvider>
                      </div>
                      <span className="text-xs text-muted-foreground">Indicado para questões longas/complexas</span>
                    </div>
                    <Switch checked={breadthFirst} onCheckedChange={setBreadthFirst} disabled={!webSearch} />
                  </div>

                  <div className="flex items-center justify-between">
                    <div className="flex flex-col gap-0.5">
                      <div className="flex items-center gap-2">
                        <Label className="text-sm font-medium">Deep Research</Label>
                        <span className="px-1.5 py-0.5 rounded bg-emerald-500/15 text-emerald-700 text-[9px] font-bold">ALPHA</span>
                      </div>
                      <span className="text-xs text-muted-foreground">Agente Autônomo (Lento, +Custos)</span>
                    </div>
                    <Switch checked={denseResearch} onCheckedChange={setDenseResearch} />
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
                            "flex-1 px-2 py-1.5 text-xs font-medium rounded-md transition-all",
                            reasoningLevel === level
                              ? "bg-emerald-600/15 text-emerald-700 shadow-sm"
                              : "text-slate-500 hover:bg-slate-100 hover:text-slate-700"
                          )}
                        >
                          {level === 'low' ? 'Rápido' : level === 'medium' ? 'Médio' : 'Profundo'}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="h-[1px] bg-slate-200" />

                  <div className="flex items-center justify-between">
                    <div className="flex flex-col gap-0.5">
                      <div className="flex items-center gap-2">
                        <Label className="text-sm font-medium">Comparar modelos (Chat)</Label>
                        <span className="px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-400 text-[9px] font-bold">ON</span>
                      </div>
                      <span className="text-xs text-muted-foreground">Respostas paralelas; não é o Modo Minuta (Agentes)</span>
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
                        <span className="text-[10px] text-muted-foreground">Básico</span>
                        <Switch checked={advancedRagMode} onCheckedChange={setAdvancedRagMode} />
                        <span className="text-[10px] text-muted-foreground">Avançado</span>
                      </div>
                    </div>
                    <p className="text-[10px] text-muted-foreground">
                      {advancedRagMode
                        ? 'Ajustes avançados para precisão e profundidade. Passe o mouse nos ícones para ver detalhes técnicos.'
                        : 'RAG básico: busca trechos relevantes e responde com base neles. Rápido e indicado para a maioria dos casos.'}
                    </p>

                    {advancedRagMode && (
                      <>
                        <div className="flex items-center justify-between">
                          <div className="flex flex-col gap-0.5">
                            <Label className="text-sm font-medium flex items-center gap-1">
                              Estratégia automática
                              <TooltipProvider>
                                <Tooltip>
                                  <TooltipTrigger asChild>
                                    <HelpCircle className="h-3 w-3 text-muted-foreground cursor-help" />
                                  </TooltipTrigger>
                                  <TooltipContent side="right" className="max-w-xs text-xs">
                                    <p>Nome técnico: Adaptive Routing. Escolhe automaticamente a melhor estratégia por seção.</p>
                                  </TooltipContent>
                                </Tooltip>
                              </TooltipProvider>
                            </Label>
                            <span className="text-xs text-muted-foreground">Recomendado para a maioria dos casos</span>
                          </div>
                          <Switch checked={adaptiveRouting} onCheckedChange={setAdaptiveRouting} />
                        </div>

                        <div className="flex items-center justify-between">
                          <div className="flex flex-col gap-0.5">
                            <Label className="text-sm font-medium flex items-center gap-1">
                              Rascunho inteligente
                              <TooltipProvider>
                                <Tooltip>
                                  <TooltipTrigger asChild>
                                    <HelpCircle className="h-3 w-3 text-muted-foreground cursor-help" />
                                  </TooltipTrigger>
                                  <TooltipContent side="right" className="max-w-xs text-xs">
                                    <p>HyDE (Hypothetical Document Embeddings). Cria um rascunho para recuperar melhor quando a pergunta é vaga.</p>
                                  </TooltipContent>
                                </Tooltip>
                              </TooltipProvider>
                            </Label>
                            <span className="text-xs text-muted-foreground">Ajuda quando a pergunta é vaga</span>
                          </div>
                          <Switch checked={hydeEnabled} onCheckedChange={setHydeEnabled} />
                        </div>

                        <div className="flex items-center justify-between">
                          <div className="flex flex-col gap-0.5">
                            <Label className="text-sm font-medium flex items-center gap-1">
                              Verificação extra
                              <TooltipProvider>
                                <Tooltip>
                                  <TooltipTrigger asChild>
                                    <HelpCircle className="h-3 w-3 text-muted-foreground cursor-help" />
                                  </TooltipTrigger>
                                  <TooltipContent side="right" className="max-w-xs text-xs">
                                    <p>CRAG (Corrective RAG). Reavalia a qualidade das evidências antes de responder.</p>
                                  </TooltipContent>
                                </Tooltip>
                              </TooltipProvider>
                            </Label>
                            <span className="text-xs text-muted-foreground">Checagem extra das fontes</span>
                          </div>
                          <Switch checked={cragGate} onCheckedChange={setCragGate} />
                        </div>

                        <div className="space-y-2 pt-2 border-t border-slate-200/70">
                          <div className="flex items-center justify-between">
                            <div className="flex flex-col gap-0.5">
                              <Label className="text-sm font-medium flex items-center gap-1">
                                Relações entre fatos
                                <TooltipProvider>
                                  <Tooltip>
                                    <TooltipTrigger asChild>
                                      <HelpCircle className="h-3 w-3 text-muted-foreground cursor-help" />
                                    </TooltipTrigger>
                                    <TooltipContent side="right" className="max-w-xs text-xs">
                                      <p>GraphRAG. Conecta documentos e conceitos relacionados para ampliar o contexto. Profundidade define os saltos nas relações.</p>
                                    </TooltipContent>
                                  </Tooltip>
                                </TooltipProvider>
                              </Label>
                              <span className="text-xs text-muted-foreground">Conecta documentos e conceitos relacionados</span>
                            </div>
                            <Switch checked={graphRagEnabled} onCheckedChange={setGraphRagEnabled} />
                          </div>
                          {graphRagEnabled && (
                            <div className="space-y-2 px-1 pt-1 animate-in zoom-in-95">
                              <div className="flex justify-between items-center text-[10px]">
                                <span className="text-emerald-600">Profundidade: {graphHops}</span>
                              </div>
                              <Slider
                                value={[graphHops]}
                                onValueChange={([v]) => setGraphHops(v)}
                                max={3} min={1} step={1}
                              />
                            </div>
                          )}
                        </div>
                      </>
                    )}
                  </div>

                  <div className="space-y-2 pt-3 border-t border-slate-200">
                    <div className="flex items-center gap-2">
                      <Label className="text-xs font-bold uppercase text-muted-foreground">Anexos no contexto</Label>
                      <TooltipProvider>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <HelpCircle className="h-3 w-3 text-muted-foreground cursor-help" />
                          </TooltipTrigger>
                          <TooltipContent side="right" className="max-w-xs text-xs">
                            Escolha como os anexos serão usados pela IA: busca (RAG) ou injeção direta do texto.
                          </TooltipContent>
                        </Tooltip>
                      </TooltipProvider>
                    </div>

                    <div className="grid gap-2">
                      <div className="flex items-center justify-between gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            onClick={() => setAttachmentMode('rag_local')}
                            className={cn(
                              "h-6 px-2 rounded-md text-[10px] font-semibold transition-all",
                              attachmentMode === 'rag_local'
                                ? "bg-emerald-600 text-white"
                                : "bg-slate-200 text-slate-600 hover:bg-slate-300"
                            )}
                          >
                            RAG Local
                          </button>
                          <span className="text-[10px] text-muted-foreground">Mais preciso para fatos/citações</span>
                        </div>
                        <TooltipProvider>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <HelpCircle className="h-3.5 w-3.5 text-muted-foreground cursor-help" />
                            </TooltipTrigger>
                            <TooltipContent side="left" className="max-w-xs text-xs">
                              Prós: recupera trechos relevantes e reduz alucinação. Contras: pode ser mais lento e depende de indexação.
                            </TooltipContent>
                          </Tooltip>
                        </TooltipProvider>
                      </div>

                      <div className="flex items-center justify-between gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            onClick={() => setAttachmentMode('prompt_injection')}
                            className={cn(
                              "h-6 px-2 rounded-md text-[10px] font-semibold transition-all",
                              attachmentMode === 'prompt_injection'
                                ? "bg-emerald-600 text-white"
                                : "bg-slate-200 text-slate-600 hover:bg-slate-300"
                            )}
                          >
                            Injeção direta
                          </button>
                          <span className="text-[10px] text-muted-foreground">Rápido para poucos arquivos</span>
                        </div>
                        <TooltipProvider>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <HelpCircle className="h-3.5 w-3.5 text-muted-foreground cursor-help" />
                            </TooltipTrigger>
                            <TooltipContent side="left" className="max-w-xs text-xs">
                              Prós: simples e imediato. Contras: consome muitos tokens e pode truncar documentos grandes.
                            </TooltipContent>
                          </Tooltip>
                        </TooltipProvider>
                      </div>
                    </div>
                  </div>
                </div>
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
            <Button variant="ghost" size="icon" className="h-7 w-7 rounded-full text-slate-500 hover:bg-slate-100 hover:text-slate-700">
              <AtSign className="h-3.5 w-3.5" />
            </Button>
            <Button variant="ghost" size="icon" className="h-7 w-7 rounded-full text-slate-500 hover:bg-slate-100 hover:text-slate-700">
              <Hash className="h-3.5 w-3.5" />
            </Button>
          </div>

          <div className="ml-auto flex items-center">
            <Button
              onClick={handleSend}
              disabled={!content.trim() || disabled}
              size="icon"
              className={cn(
                "h-8 w-8 rounded-lg transition-all",
                content.trim()
                  ? "bg-emerald-600 text-white hover:bg-emerald-500 shadow-lg shadow-emerald-500/20"
                  : "bg-slate-100 text-slate-400 hover:bg-slate-100"
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
        accept=".pdf,.docx,.doc,.txt,.rtf,.odt,.html,.htm,.png,.jpg,.jpeg"
        className="hidden"
        onChange={handleFileChange}
      />
      {/* Ambient Glow */}
      <div className="pointer-events-none absolute -inset-px -z-10 rounded-2xl bg-gradient-to-r from-emerald-400/20 via-emerald-200/20 to-emerald-500/20 opacity-0 blur-xl transition-opacity duration-500 group-focus-within:opacity-100" />
    </div>
  );
}
