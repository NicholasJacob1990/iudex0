'use client';

import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { Sparkles, Send, Mic, Loader2, PlusCircle, Settings2, Hash, Library, ChevronUp, ChevronDown, User, Scale } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { RichTooltip } from '@/components/ui/rich-tooltip';
import { useChatStore, useContextStore } from '@/stores';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';
import { PREDEFINED_PROMPTS, type PredefinedPrompt } from '@/data/prompts';
import { ContextSelector } from '@/components/dashboard/context-selector';
import { SlashCommandMenu, type SystemCommand } from '@/components/chat/slash-command-menu';
import apiClient from '@/lib/api-client';

export function PromptFooter() {
  const {
    currentChat,
    sendMessage,
    isSending,
    chatMode,
    setChatMode,
    selectedModels,
    setSelectedModels,
    setShowMultiModelComparator
  } = useChatStore();
  const { sources, setSearch, search, toggleSource, toggleMeta } = useContextStore();
  const [prompt, setPrompt] = useState('');
  const [effort, setEffort] = useState(5);
  const [mode, setMode] = useState<'curto' | 'longo'>('curto');
  const [profile, setProfile] = useState('Sem perfil');
  const [interactionMode, setInteractionMode] = useState<'Chat' | 'Minuta'>('Minuta');
  const [maxTokens, setMaxTokens] = useState(12000);
  const [showSlashMenu, setShowSlashMenu] = useState(false);
  const [customPrompts, setCustomPrompts] = useState<PredefinedPrompt[]>([]);
  const [customTemplate, setCustomTemplate] = useState('');
  const [customName, setCustomName] = useState('');
  const [customDescription, setCustomDescription] = useState('');
  const [showCustomBuilder, setShowCustomBuilder] = useState(false);
  const [contextMentions, setContextMentions] = useState<{ id: string; label: string; description?: string }[]>([]);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const modeTooltips = {
    Chat: {
      title: 'Modo Chat',
      description: 'Conversa livre e rápida. Ideal para tirar dúvidas pontuais ou pedir resumos.',
      badge: 'Respostas diretas',
      icon: <User className="h-3.5 w-3.5" />,
    },
    Minuta: {
      title: 'Modo Minuta',
      description: 'Geração de documentos complexos com múltiplos agentes verificando a consistência jurídica.',
      badge: 'Documentos longos',
      icon: <Scale className="h-3.5 w-3.5" />,
    },
  };
  const [collapsed, setCollapsed] = useState(() => {
    try {
      if (typeof window === 'undefined') return true;
      const v = localStorage.getItem('iudex_minuta_footer_collapsed');
      return v === null ? true : v === 'true';
    } catch {
      return true;
    }
  });

  const allPrompts = useMemo(() => [...PREDEFINED_PROMPTS, ...customPrompts], [customPrompts]);

  useEffect(() => {
    let mounted = true;
    const loadMentions = async () => {
      try {
        const data = await apiClient.getLibrarians(0, 10);
        if (!mounted) return;
        const mentions = (data.librarians || []).map((librarian: any) => ({
          id: librarian.id,
          label: `@${librarian.name}`,
          description: librarian.description,
        }));
        setContextMentions(mentions);
      } catch {
        // Silencioso
      }
    };
    loadMentions();
    return () => {
      mounted = false;
    };
  }, []);

  const tokenPreview = useMemo(() => {
    const tokens = prompt.split(/\s+/).filter(Boolean).length * 1.3;
    return Math.min(maxTokens, Math.round(tokens));
  }, [prompt, maxTokens]);

  const DEFAULT_COMPARE_MODELS = ['gpt-5.2', 'claude-4.5-sonnet', 'gemini-3-flash'];
  const handleSetChatMode = (next: 'standard' | 'multi-model') => {
    if (next === 'multi-model') {
      const nextModels =
        selectedModels.length >= 2
          ? selectedModels
          : selectedModels.length === 1
            ? [selectedModels[0], DEFAULT_COMPARE_MODELS.find((m) => m !== selectedModels[0]) || 'gpt-5.2']
            : DEFAULT_COMPARE_MODELS.slice(0, 3);
      setSelectedModels(nextModels);
      setShowMultiModelComparator(true);
      setChatMode('multi-model');
      toast.success('Modo do chat: Comparar modelos');
      return;
    }
    if (selectedModels.length > 1) setSelectedModels([selectedModels[0]]);
    setChatMode('standard');
    toast.info('Modo do chat: Normal');
  };

  const filteredSources = useMemo(
    () => sources.filter((source) => source.label.toLowerCase().includes(search.toLowerCase())),
    [sources, search]
  );

  const handleSubmit = async () => {
    if (!prompt.trim()) {
      toast.info('Digite instruções para gerar a minuta.');
      return;
    }

    if (!currentChat) {
      toast.info('Abra uma conversa para enviar instruções.');
      return;
    }

    try {
      await sendMessage(prompt);
      setPrompt('');
    } catch (error) {
      // erros tratados no interceptor
    }
  };

  const handlePromptChange = (value: string) => {
    setPrompt(value);
    if (value.endsWith('/')) {
      setShowSlashMenu(true);
    } else if (!value.includes('/')) {
      setShowSlashMenu(false);
    }
  };

  const handleSelectPrompt = (promptOption: PredefinedPrompt | SystemCommand) => {
    if ('action' in promptOption) {
      const action = promptOption.action as string;
      if (action.startsWith('set-model:')) {
        const modelId = action.split(':')[1];
        setSelectedModels([modelId]);
        setChatMode('standard');
        toast.success(`Modelo alterado para ${promptOption.name.replace('Mudar para ', '')}`);
      } else if (action === 'set-mode:multi-model') {
        handleSetChatMode('multi-model');
      } else if (action === 'set-mode:standard') {
        handleSetChatMode('standard');
      }
      setPrompt('');
      setShowSlashMenu(false);
      textareaRef.current?.focus();
      return;
    }

    const cleaned = prompt.endsWith('/') ? prompt.slice(0, -1).trimEnd() : prompt.trimEnd();
    const spacer = cleaned ? ' ' : '';
    setPrompt(`${cleaned}${spacer}${promptOption.template}`);
    setShowSlashMenu(false);
    textareaRef.current?.focus();
  };

  const handleAddCustomPrompt = () => {
    if (!customName.trim() || !customTemplate.trim()) {
      toast.info('Dê nome e texto para salvar um prompt personalizado.');
      return;
    }

    const newPrompt: PredefinedPrompt = {
      id: `custom-${Date.now()}`,
      category: 'Personalizados',
      name: customName.trim(),
      description: customDescription.trim() || 'Prompt criado por você',
      template: customTemplate.trim(),
    };

    setCustomPrompts((prev) => [...prev, newPrompt]);
    setCustomName('');
    setCustomTemplate('');
    setCustomDescription('');
    setShowCustomBuilder(false);
    toast.success('Prompt salvo para uso rápido.');
  };

  const appendMention = (label: string) => {
    setPrompt((prev) => {
      const spacer = prev.endsWith(' ') || prev.length === 0 ? '' : ' ';
      return `${prev}${spacer}${label} `;
    });
    textareaRef.current?.focus();
  };

  return (
    <footer className="sticky bottom-0 z-30 w-full border-t border-outline/60 bg-panel/90 px-6 py-3 backdrop-blur-2xl">
      {/* Collapsed header (keeps Minuta chat/canvas visible) */}
      <div className="mb-2 flex items-center justify-between gap-3 rounded-2xl border border-white/70 bg-white/85 px-3 py-2 shadow-soft">
        <div className="flex items-center gap-2 text-xs font-semibold text-foreground">
          <Sparkles className="h-4 w-4 text-primary" />
          <span>Contexto & Geração</span>
          <span className="hidden md:inline text-[11px] font-medium text-muted-foreground">
            (expanda para anexar fontes e enviar instruções)
          </span>
        </div>
        <div className="flex items-center gap-2">
          {/* Always-visible chat mode toggle (discoverability) */}
          <div className="flex items-center gap-1 rounded-full border border-outline/40 bg-white/80 p-0.5">
            <RichTooltip
              title="Modo Chat"
              description="Conversa livre e rápida. Ideal para tirar dúvidas pontuais ou pedir resumos."
              badge="1 resposta por vez"
              icon={<User className="h-3.5 w-3.5" />}
            >
              <Button
                type="button"
                size="sm"
                variant={chatMode !== 'multi-model' ? 'secondary' : 'ghost'}
                className="h-7 rounded-full px-2 text-[11px]"
                onClick={() => handleSetChatMode('standard')}
              >
                <User className="mr-1.5 h-3.5 w-3.5" />
                <span className="hidden sm:inline">Normal</span>
              </Button>
            </RichTooltip>
            <RichTooltip
              title="Comparar modelos"
              description="Respostas paralelas para avaliar argumentos e escolher a melhor abordagem."
              badge="2–3 respostas"
              icon={<Scale className="h-3.5 w-3.5" />}
            >
              <Button
                type="button"
                size="sm"
                variant={chatMode === 'multi-model' ? 'secondary' : 'ghost'}
                className="h-7 rounded-full px-2 text-[11px]"
                onClick={() => handleSetChatMode('multi-model')}
              >
                <Scale className="mr-1.5 h-3.5 w-3.5" />
                <span className="hidden sm:inline">Comparar</span>
              </Button>
            </RichTooltip>
          </div>
          <span className="hidden md:inline text-[11px] text-muted-foreground">
            Tokens: <strong className="text-primary">{tokenPreview}/{maxTokens}</strong>
          </span>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-8 rounded-full"
            onClick={() => {
              const next = !collapsed;
              setCollapsed(next);
              try { localStorage.setItem('iudex_minuta_footer_collapsed', String(next)); } catch { /* noop */ }
            }}
          >
            {collapsed ? (
              <>
                <ChevronUp className="mr-2 h-4 w-4" />
                Expandir
              </>
            ) : (
              <>
                <ChevronDown className="mr-2 h-4 w-4" />
                Recolher
              </>
            )}
          </Button>
        </div>
      </div>

      {!collapsed && (
        <div className="rounded-3xl border border-white/80 bg-white/90 p-4 shadow-soft space-y-4">
        <div className="space-y-2">
          <ContextSelector />

          <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
            <span className="chip bg-sand text-foreground">Use @ para ativar bibliotecas salvas</span>
            {contextMentions.map((mention) => (
              <RichTooltip
                key={mention.id}
                title={`Ativar ${mention.label}`}
                description={mention.description || 'Ative agentes especialistas para revisar pontos específicos da sua minuta.'}
                badge="Bibliotecário"
                icon={<Library className="h-3.5 w-3.5" />}
              >
                <button
                  type="button"
                  onClick={() => appendMention(mention.label)}
                  className="rounded-full border border-outline/50 bg-white px-3 py-1 font-semibold transition hover:border-primary hover:text-primary"
                >
                  {mention.label}
                </button>
              </RichTooltip>
            ))}
          </div>
        </div>

        <div className="group relative flex flex-col gap-2 rounded-2xl border border-outline/40 bg-white/80 p-2 shadow-inner focus-within:border-primary/40">
          {showSlashMenu && (
            <SlashCommandMenu
              onSelect={handleSelectPrompt}
              onClose={() => setShowSlashMenu(false)}
              prompts={allPrompts}
            />
          )}

          <textarea
            ref={textareaRef}
            rows={3}
            className="w-full resize-none rounded-xl bg-transparent px-3 py-2 text-sm focus-visible:outline-none"
            placeholder="Instruções ao Iudex para geração da minuta... (Digite '/' para prompts ou '@' para contextos salvos)"
            value={prompt}
            onChange={(e) => handlePromptChange(e.target.value)}
          />

          <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between px-1 pb-1">
            <div className="flex flex-wrap items-center gap-2">
              <ModeToggle label="Perfil" options={['Sem perfil', 'Redação jurídica 01', 'Meu estilo']} value={profile} onChange={setProfile} />
              <ModeToggle label="Saída" options={['curto', 'longo']} value={mode} onChange={setMode} />
              <ModeToggle
                label="Modo"
                options={['Chat', 'Minuta']}
                value={interactionMode}
                onChange={setInteractionMode}
                tooltips={modeTooltips}
              />
            </div>

            <div className="flex items-center gap-2">
              <Button variant="ghost" size="sm" className="h-8 rounded-full text-xs" onClick={() => setShowCustomBuilder((prev) => !prev)}>
                <PlusCircle className="mr-2 h-3.5 w-3.5" />
                Personalizar prompt
              </Button>
              <Button variant="ghost" size="icon" className="rounded-2xl border-white/70 bg-white">
                <Mic className="h-4 w-4" />
              </Button>
              <Button
                className="rounded-2xl bg-gradient-to-r from-primary to-rose-400 px-6 font-semibold text-primary-foreground shadow-soft"
                onClick={handleSubmit}
                disabled={isSending}
              >
                {isSending ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Gerando
                  </>
                ) : (
                  <>
                    <Sparkles className="mr-2 h-4 w-4" />
                    Gerar minuta
                  </>
                )}
              </Button>
              <Button variant="ghost" size="icon" onClick={handleSubmit} disabled={isSending}>
                <Send className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </div>

        {showCustomBuilder && (
          <div className="rounded-2xl border border-outline/40 bg-white/80 p-3 space-y-2">
            <div className="flex flex-col gap-2 md:flex-row md:items-center md:gap-4">
              <Input
                placeholder="Nome do prompt"
                value={customName}
                onChange={(e) => setCustomName(e.target.value)}
                className="h-9"
              />
              <Input
                placeholder="Descrição rápida"
                value={customDescription}
                onChange={(e) => setCustomDescription(e.target.value)}
                className="h-9"
              />
            </div>
            <textarea
              className="w-full rounded-xl border border-outline/40 bg-white px-3 py-2 text-sm focus-visible:outline-none"
              rows={3}
              placeholder="Cole ou escreva o template do seu prompt personalizado..."
              value={customTemplate}
              onChange={(e) => setCustomTemplate(e.target.value)}
            />
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
                <Hash className="h-3 w-3" />
                Prompts salvos aparecem ao digitar &quot;/&quot;
              </div>
              <Button size="sm" className="rounded-full" onClick={handleAddCustomPrompt}>
                Salvar prompt
              </Button>
            </div>
          </div>
        )}

        <div className="flex flex-wrap items-center gap-3 text-xs font-medium text-muted-foreground">
          <div className="flex items-center gap-2">
            <span className="chip bg-sand text-foreground">
              Tokens <strong className="ml-1 text-primary">{tokenPreview}/{maxTokens}</strong>
            </span>
            <div className="flex items-center gap-2 rounded-full border border-outline/50 bg-white/80 px-3 py-1">
              <span className="uppercase text-[10px] text-muted-foreground">Limite</span>
              <input
                type="range"
                min={4000}
                max={50000}
                step={1000}
                value={maxTokens}
                onChange={(e) => setMaxTokens(Number(e.target.value))}
                className="h-1 w-28 accent-primary"
              />
              <span className="text-primary">{Math.round(maxTokens / 1000)}k</span>
            </div>
            <span className="chip bg-lavender/60 text-foreground">
              Esforço{' '}
              <input
                type="range"
                min={1}
                max={5}
                value={effort}
                onChange={(e) => setEffort(Number(e.target.value))}
                className="ml-2 h-1 w-20 cursor-pointer accent-primary"
              />
              <span className="ml-1 text-primary">{effort}</span>
            </span>
          </div>

          <div className="chip bg-white text-foreground">
            Contexto ativo:{' '}
            {sources.filter((s) => s.enabled).map((s) => s.label).join(', ') || 'sem contexto'}
          </div>
          <div className="chip bg-white text-foreground">
            Perfil: {profile} • Modo: {interactionMode}
          </div>
        </div>
        </div>
      )}
    </footer>
  );
}

interface ModeToggleProps {
  label: string;
  options: string[];
  value?: string;
  onChange?: (value: any) => void;
  tooltips?: Record<
    string,
    {
      title: string;
      description: string;
      badge?: string;
      meta?: ReactNode;
      shortcut?: string;
      icon?: ReactNode;
    }
  >;
}

function ModeToggle({ label, options, value, onChange, tooltips }: ModeToggleProps) {
  const [internalValue, setInternalValue] = useState(options[0]);
  const currentValue = value ?? internalValue;

  return (
    <div className="flex items-center gap-2">
      <span className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</span>
      <div className="flex gap-1 rounded-full border border-outline/50 bg-white/80 p-1">
        {options.map((option) => {
          const active = option === currentValue;
          const tooltip = tooltips?.[option];

          if (tooltip) {
            return (
              <RichTooltip key={option} {...tooltip}>
                <button
                  type="button"
                  className={cn(
                    'rounded-full px-3 py-1 text-[11px] font-semibold capitalize transition',
                    active ? 'bg-primary text-primary-foreground' : 'text-muted-foreground'
                  )}
                  onClick={() => {
                    if (onChange) {
                      onChange(option as any);
                    } else {
                      setInternalValue(option);
                    }
                  }}
                >
                  {option}
                </button>
              </RichTooltip>
            );
          }

          return (
            <button
              key={option}
              type="button"
              className={cn(
                'rounded-full px-3 py-1 text-[11px] font-semibold capitalize transition',
                active ? 'bg-primary text-primary-foreground' : 'text-muted-foreground'
              )}
              onClick={() => {
                if (onChange) {
                  onChange(option as any);
                } else {
                  setInternalValue(option);
                }
              }}
            >
              {option}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function TogglePill({
  label,
  active,
  onClick,
  small,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
  small?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'rounded-full px-3 py-1 text-[11px] uppercase transition',
        active ? 'bg-primary text-primary-foreground' : 'bg-white text-muted-foreground',
        small && 'px-2'
      )}
    >
      {label}
    </button>
  );
}
