'use client';

import { useState, KeyboardEvent, useRef, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Send, Sparkles, ChevronDown, Paperclip, AtSign, Hash, Globe, Brain, Zap, HelpCircle } from 'lucide-react';
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
}

export function ChatInput({ onSend, disabled }: ChatInputProps) {
  const [content, setContent] = useState('');
  const [style, setStyle] = useState('Formal');
  const [showSlashMenu, setShowSlashMenu] = useState(false);
  const [showAtMenu, setShowAtMenu] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const { setActiveTab, addItem } = useContextStore();
  const [advancedRagMode, setAdvancedRagMode] = useState(false);
  const {
    chatMode,
    selectedModels,
    webSearch, setWebSearch,
    denseResearch, setDenseResearch,
    reasoningLevel, setReasoningLevel,
    setSelectedModels, setChatMode,
    setShowMultiModelComparator,
    adaptiveRouting, setAdaptiveRouting,
    cragGate, setCragGate,
    hydeEnabled, setHydeEnabled,
    graphRagEnabled, setGraphRagEnabled,
    graphHops, setGraphHops,
    useMultiAgent, setUseMultiAgent,
    attachmentMode, setAttachmentMode,
    setPendingCanvasContext
  } = useChatStore();

  const DEFAULT_COMPARE_MODELS = ['gpt-5.2', 'claude-4.5-sonnet', 'gemini-3-flash'];

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

  // Context-aware chat from Canvas
  const [canvasContext, setCanvasContext] = useState<{ text: string; action: 'improve' | 'shorten' | null } | null>(null);

  useEffect(() => {
    // Subscribe to canvas store changes
    const checkCanvasContext = () => {
      import('@/stores/canvas-store').then(({ useCanvasStore }) => {
        const { selectedText, pendingAction } = useCanvasStore.getState();
        if (selectedText) {
          setCanvasContext({ text: selectedText, action: pendingAction });
        } else {
          setCanvasContext(null);
        }
      });
    };
    checkCanvasContext();
    const interval = setInterval(checkCanvasContext, 500);
    return () => clearInterval(interval);
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
    let messageContent = content;
    if (canvasContext?.text) {
      if (chatMode === 'standard') {
        setPendingCanvasContext(canvasContext);
      } else {
        setPendingCanvasContext(null);
      }
      const actionPrefix = canvasContext.action === 'improve'
        ? 'Melhore este trecho: '
        : canvasContext.action === 'shorten'
          ? 'Resuma este trecho: '
          : 'Sobre este trecho: ';
      messageContent = `${actionPrefix}"${canvasContext.text}"\n\n${content}`;

      // Clear canvas context after use
      import('@/stores/canvas-store').then(({ useCanvasStore }) => {
        useCanvasStore.getState().clearSelectedText();
      });
      setCanvasContext(null);
    }

    onSend(messageContent);
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

      <div className="group relative flex flex-col gap-2 rounded-xl border border-white/10 bg-white/5 p-2 shadow-sm focus-within:border-indigo-500/50 focus-within:ring-1 focus-within:ring-indigo-500/50 transition-all">
        {/* Context Banner - shows when text is selected from Canvas */}
        {canvasContext?.text && (
          <div className="flex items-center gap-2 px-2 py-1.5 bg-indigo-500/10 border border-indigo-500/20 rounded-lg text-xs">
            <Sparkles className="h-3 w-3 text-indigo-500" />
            <span className="text-indigo-600 font-medium">
              {canvasContext.action === 'improve' ? 'Melhorando' : canvasContext.action === 'shorten' ? 'Resumindo' : 'Contexto'}:
            </span>
            <span className="text-muted-foreground truncate flex-1">
              "{canvasContext.text.slice(0, 60)}{canvasContext.text.length > 60 ? '...' : ''}"
            </span>
            <Button
              variant="ghost"
              size="sm"
              className="h-5 w-5 p-0 text-muted-foreground hover:text-destructive"
              onClick={() => {
                import('@/stores/canvas-store').then(({ useCanvasStore }) => {
                  useCanvasStore.getState().clearSelectedText();
                });
                setCanvasContext(null);
              }}
            >
              ×
            </Button>
          </div>
        )}
        <textarea
          ref={textareaRef}
          value={content}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          placeholder="Descreva a minuta que você precisa... (Digite '/' para prompts, '@' para contexto)"
          className="min-h-[60px] w-full resize-none bg-transparent px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none disabled:opacity-50"
          disabled={disabled}
          rows={1}
        />

        <div className="flex items-center justify-between px-2 pb-1">
          <div className="flex items-center gap-1">

            {/* Visible toggle (low-friction discovery) */}
            <div className="flex items-center gap-1 rounded-lg border border-white/10 bg-white/5 px-2 py-1">
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
            <div className="h-4 w-[1px] bg-white/10 mx-1" />

            <Popover>
              <PopoverTrigger asChild>
                <Button variant="ghost" size="sm" className={cn("h-7 gap-1 rounded-full px-2 text-[10px] font-medium transition-colors", (webSearch || denseResearch) ? "text-indigo-400 bg-indigo-500/10" : "text-muted-foreground hover:bg-white/10 hover:text-foreground")}>
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

                  <div className="flex items-center justify-between">
                    <div className="flex flex-col gap-0.5">
                      <div className="flex items-center gap-2">
                        <Label className="text-sm font-medium">Deep Research</Label>
                        <span className="px-1.5 py-0.5 rounded bg-indigo-500/20 text-indigo-400 text-[9px] font-bold">ALPHA</span>
                      </div>
                      <span className="text-xs text-muted-foreground">Agente Autônomo (Lento, +Custos)</span>
                    </div>
                    <Switch checked={denseResearch} onCheckedChange={setDenseResearch} />
                  </div>

                  <div className="h-[1px] bg-white/10" />

                  <div className="space-y-2">
                    <Label className="text-sm font-medium">Nível de Raciocínio (Thinking)</Label>
                    <div className="flex gap-1 p-1 bg-white/5 rounded-lg">
                      {(['low', 'medium', 'high'] as const).map((level) => (
                        <button
                          key={level}
                          onClick={() => setReasoningLevel(level)}
                          className={cn(
                            "flex-1 px-2 py-1.5 text-xs font-medium rounded-md transition-all",
                            reasoningLevel === level
                              ? "bg-indigo-600/20 text-indigo-400 shadow-sm"
                              : "text-muted-foreground hover:bg-white/5 hover:text-foreground"
                          )}
                        >
                          {level === 'low' ? 'Rápido' : level === 'medium' ? 'Médio' : 'Profundo'}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="h-[1px] bg-white/10" />

                  <div className="flex items-center justify-between">
                    <div className="flex flex-col gap-0.5">
                      <div className="flex items-center gap-2">
                        <Label className="text-sm font-medium">Comitê de Agentes</Label>
                        <span className="px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-400 text-[9px] font-bold">ON</span>
                      </div>
                      <span className="text-xs text-muted-foreground">Debate multi-modelo (GPT + Claude + Gemini)</span>
                    </div>
                    <Switch checked={useMultiAgent} onCheckedChange={setUseMultiAgent} />
                  </div>

                  <div className="h-[1px] bg-white/10" />

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
                        ? 'Configure técnicas avançadas de busca (Adaptive, HyDE, CRAG, GraphRAG).'
                        : 'Modo simplificado. Ative "Avançado" para mais controle.'}
                    </p>

                    {advancedRagMode && (
                      <>
                        <div className="flex items-center justify-between">
                          <div className="flex flex-col gap-0.5">
                            <Label className="text-sm font-medium">Roteamento Inteligente</Label>
                            <span className="text-xs text-muted-foreground">Escolhe estratégia por seção</span>
                          </div>
                          <Switch checked={adaptiveRouting} onCheckedChange={setAdaptiveRouting} />
                        </div>

                        <div className="flex items-center justify-between">
                          <div className="flex flex-col gap-0.5">
                            <Label className="text-sm font-medium">Busca por Texto Hipotético</Label>
                            <span className="text-xs text-muted-foreground">HyDE - melhora busca semântica</span>
                          </div>
                          <Switch checked={hydeEnabled} onCheckedChange={setHydeEnabled} />
                        </div>

                        <div className="flex items-center justify-between">
                          <div className="flex flex-col gap-0.5">
                            <Label className="text-sm font-medium">Filtro de Qualidade</Label>
                            <span className="text-xs text-muted-foreground">CRAG - evita fontes fracas</span>
                          </div>
                          <Switch checked={cragGate} onCheckedChange={setCragGate} />
                        </div>

                        <div className="space-y-2 pt-2 border-t border-white/5">
                          <div className="flex items-center justify-between">
                            <div className="flex flex-col gap-0.5">
                              <Label className="text-sm font-medium">Busca por Conexões</Label>
                              <span className="text-xs text-muted-foreground">GraphRAG - relações entre leis</span>
                            </div>
                            <Switch checked={graphRagEnabled} onCheckedChange={setGraphRagEnabled} />
                          </div>
                          {graphRagEnabled && (
                            <div className="space-y-2 px-1 pt-1 animate-in zoom-in-95">
                              <div className="flex justify-between items-center text-[10px]">
                                <span className="text-indigo-400">Hops: {graphHops}</span>
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

                  <div className="space-y-2 pt-3 border-t border-white/10">
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
                      <div className="flex items-center justify-between gap-2 rounded-lg border border-white/10 bg-white/5 px-3 py-2">
                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            onClick={() => setAttachmentMode('rag_local')}
                            className={cn(
                              "h-6 px-2 rounded-md text-[10px] font-semibold transition-all",
                              attachmentMode === 'rag_local'
                                ? "bg-indigo-600 text-white"
                                : "bg-white/10 text-muted-foreground hover:bg-white/20"
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

                      <div className="flex items-center justify-between gap-2 rounded-lg border border-white/10 bg-white/5 px-3 py-2">
                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            onClick={() => setAttachmentMode('prompt_injection')}
                            className={cn(
                              "h-6 px-2 rounded-md text-[10px] font-semibold transition-all",
                              attachmentMode === 'prompt_injection'
                                ? "bg-indigo-600 text-white"
                                : "bg-white/10 text-muted-foreground hover:bg-white/20"
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

            <div className="h-4 w-[1px] bg-white/10 mx-1" />

            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7 rounded-full text-muted-foreground hover:bg-white/10 hover:text-foreground"
              onClick={handleAttachClick}
              type="button"
            >
              <Paperclip className="h-3.5 w-3.5" />
            </Button>
            <Button variant="ghost" size="icon" className="h-7 w-7 rounded-full text-muted-foreground hover:bg-white/10 hover:text-foreground">
              <AtSign className="h-3.5 w-3.5" />
            </Button>
            <Button variant="ghost" size="icon" className="h-7 w-7 rounded-full text-muted-foreground hover:bg-white/10 hover:text-foreground">
              <Hash className="h-3.5 w-3.5" />
            </Button>
          </div>

          <Button
            onClick={handleSend}
            disabled={!content.trim() || disabled}
            size="icon"
            className={cn(
              "h-8 w-8 rounded-lg transition-all",
              content.trim()
                ? "bg-indigo-600 text-white hover:bg-indigo-500 shadow-lg shadow-indigo-500/20"
                : "bg-white/5 text-muted-foreground hover:bg-white/10"
            )}
          >
            <Send className="h-4 w-4" />
          </Button>
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
      <div className="pointer-events-none absolute -inset-px -z-10 rounded-2xl bg-gradient-to-r from-indigo-500/20 via-purple-500/20 to-indigo-500/20 opacity-0 blur-xl transition-opacity duration-500 group-focus-within:opacity-100" />
    </div>
  );
}
