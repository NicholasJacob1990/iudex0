'use client';

import { useEffect, useRef, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useChatStore, useCanvasStore } from '@/stores';
import { useAuthStore } from '@/stores/auth-store';
import { Button } from '@/components/ui/button';
import { ChatInterface, ChatInput } from '@/components/chat';
import {
  Sparkles,
  FileText,
  ChevronDown,
  ChevronUp,
  FileSearch,
  BookOpen,
  Users,
  User,
  CheckCircle2,
  Circle,
  Loader2,
  Settings2,
  Zap,
  Scale,
} from 'lucide-react';
import { toast } from 'sonner';
import { CanvasContainer, OutlineApprovalModal } from '@/components/dashboard';
import { useContextStore, type ContextItem } from '@/stores/context-store';
import { cn } from '@/lib/utils';
import { listModels } from '@/config/models';
import { type OutlineApprovalSection } from '@/components/dashboard/outline-approval-modal';
import { RichTooltip } from '@/components/ui/rich-tooltip';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
// Resizable panels via draggable divider

type GenerationMode = 'individual' | 'multi-agent';

export default function MinutaPage() {
  const router = useRouter();
  const params = useParams<{ chatId?: string | string[] }>();
  const { isAuthenticated } = useAuthStore();
  const autoCreateAttemptedRef = useRef(false);
  const routeChatId = (() => {
    const raw = params?.chatId as unknown;
    if (typeof raw === 'string') return raw;
    if (Array.isArray(raw) && typeof raw[0] === 'string') return raw[0];
    return null;
  })();

  const {
    currentChat,
    createChat,
    setCurrentChat,
    sendMessage,
    startAgentGeneration,
    isLoading,
    isSending,
    setContext,
    setUseMultiAgent,
    isAgentRunning,
    agentSteps,
    effortLevel,
    setEffortLevel,
    minPages,
    maxPages,
    setPageRange,
    resetPageRange,
    reviewData,
    submitReview,
    // Chat settings
    selectedModel,
    setSelectedModel,
    searchMode,
    setSearchMode,
    multiQuery,
    setMultiQuery,
    breadthFirst,
    setBreadthFirst,
    hilOutlineEnabled,
    setHilOutlineEnabled,
    chatOutlineReviewEnabled,
    setChatOutlineReviewEnabled,
    auditMode,
    setAuditMode,
    // Minuta-only (pipeline)
    qualityProfile,
    setQualityProfile,
    qualityTargetSectionScore,
    setQualityTargetSectionScore,
    qualityTargetFinalScore,
    setQualityTargetFinalScore,
    qualityMaxRounds,
    setQualityMaxRounds,
    strictDocumentGateOverride,
    setStrictDocumentGateOverride,
    documentChecklist,
    setDocumentChecklist,
    formattingOptions,
    setFormattingOptions,
    chatMode,
    setChatMode,
    selectedModels,
    setSelectedModels,
    setShowMultiModelComparator,
    webSearch,
    denseResearch,
    reasoningLevel,
    setReasoningLevel,
    agentStrategistModel,
    setAgentStrategistModel,
    agentDrafterModels,
    setAgentDrafterModels,
    agentReviewerModels,
    setAgentReviewerModels,
    chatPersonality,
    setChatPersonality,
  } = useChatStore();

  const { state: canvasState, showCanvas, setActiveTab } = useCanvasStore();
  const { items: contextItems } = useContextStore();

  const [showFontes, setShowFontes] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [mode, setMode] = useState<GenerationMode>('multi-agent');
  const [creativityMode, setCreativityMode] = useState<'rigoroso' | 'padrao' | 'criativo'>('padrao');
  const [chatPanelWidth, setChatPanelWidth] = useState(45);
  const [isResizing, setIsResizing] = useState(false);
  const splitContainerRef = useRef<HTMLDivElement>(null);

  const MAX_ROLE_MODELS = 3;
  const DEFAULT_COMPARE_MODELS = ['gpt-5.2', 'claude-4.5-sonnet', 'gemini-3-flash'];
  const agentModelOptions = listModels({ forAgents: true });
  const baseModelOptions = listModels({ forJuridico: true });

  const parseOptionalNumber = (value: string) => {
    const n = Number(String(value).replace(',', '.'));
    return Number.isFinite(n) ? n : null;
  };
  const clampScore = (value: number | null) => {
    if (value === null) return null;
    return Math.max(0, Math.min(10, value));
  };
  const clampRounds = (value: number | null) => {
    if (value === null) return null;
    return Math.max(1, Math.min(10, Math.floor(value)));
  };

  const [criticalChecklistText, setCriticalChecklistText] = useState('');
  const [nonCriticalChecklistText, setNonCriticalChecklistText] = useState('');

  const updateDocumentChecklist = (criticalText: string, nonCriticalText: string) => {
    const critical = criticalText
      .split('\n')
      .map((s) => s.trim())
      .filter(Boolean)
      .map((label) => ({ label, critical: true }));
    const nonCritical = nonCriticalText
      .split('\n')
      .map((s) => s.trim())
      .filter(Boolean)
      .map((label) => ({ label, critical: false }));
    setDocumentChecklist([...critical, ...nonCritical]);
  };

  const toggleAgentModel = (
    current: string[],
    modelId: string,
    setter: (models: string[]) => void,
    roleLabel: string
  ) => {
    if (current.includes(modelId)) {
      if (current.length === 1) return;
      setter(current.filter((m) => m !== modelId));
      return;
    }
    if (current.length >= MAX_ROLE_MODELS) {
      toast.info(`Limite de ${MAX_ROLE_MODELS} modelos para ${roleLabel}.`);
      return;
    }
    setter([...current, modelId]);
  };

  // Sync mode with store
  useEffect(() => {
    setUseMultiAgent(mode === 'multi-agent');
  }, [mode, setUseMultiAgent]);

  // Sync context items to ChatStore
  useEffect(() => {
    setContext(contextItems);
  }, [contextItems, setContext]);

  // Ensure canvas is visible on initial mount only (not overriding user close action)
  useEffect(() => {
    showCanvas();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!isResizing) return;
    const { style } = document.body;
    const prevCursor = style.cursor;
    const prevUserSelect = style.userSelect;
    style.cursor = 'col-resize';
    style.userSelect = 'none';
    return () => {
      style.cursor = prevCursor;
      style.userSelect = prevUserSelect;
    };
  }, [isResizing]);

  useEffect(() => {
    const container = splitContainerRef.current;
    if (!container) return;

    const clampWidth = () => {
      const rect = container.getBoundingClientRect();
      if (!rect.width) return;
      const minPx = 300;
      const maxPx = rect.width * 0.7;
      const currentPx = (chatPanelWidth / 100) * rect.width;
      const clampedPx = Math.min(Math.max(currentPx, minPx), maxPx);
      const nextPercent = (clampedPx / rect.width) * 100;
      if (Math.abs(nextPercent - chatPanelWidth) > 0.1) {
        setChatPanelWidth(nextPercent);
      }
    };

    clampWidth();
    window.addEventListener('resize', clampWidth);
    return () => window.removeEventListener('resize', clampWidth);
  }, [chatPanelWidth]);

  const updateChatWidthFromPointer = (clientX: number) => {
    const container = splitContainerRef.current;
    if (!container) return;
    const rect = container.getBoundingClientRect();
    if (!rect.width) return;
    const minPx = 300;
    const maxPx = rect.width * 0.7;
    const rawPx = clientX - rect.left;
    const clampedPx = Math.min(Math.max(rawPx, minPx), maxPx);
    setChatPanelWidth((clampedPx / rect.width) * 100);
  };

  const handleDividerPointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    if (canvasState !== 'normal') return;
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    setIsResizing(true);
    updateChatWidthFromPointer(event.clientX);
  };

  const handleDividerPointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    if (!isResizing) return;
    updateChatWidthFromPointer(event.clientX);
  };

  const handleDividerPointerUp = (event: React.PointerEvent<HTMLDivElement>) => {
    if (!isResizing) return;
    event.preventDefault();
    try {
      event.currentTarget.releasePointerCapture(event.pointerId);
    } catch {
      // noop
    }
    setIsResizing(false);
  };

  const activeChatId = routeChatId || currentChat?.id || null;
  const canUseApi =
    isAuthenticated ||
    (typeof window !== 'undefined' && !!localStorage.getItem('access_token'));

  // Auto-create chat on mount if none exists (apenas quando não há chatId na rota)
  useEffect(() => {
    if (autoCreateAttemptedRef.current) return;
    if (!canUseApi) return;
    if (!activeChatId && !currentChat && !isLoading) {
      autoCreateAttemptedRef.current = true;
      createChat('Nova Minuta').catch(() => {
        // Silent fail - user can create manually
      });
    }
  }, [activeChatId, currentChat, isLoading, createChat, canUseApi]);

  const handleStartNewMinuta = async () => {
    if (!canUseApi) {
      toast.info('Faça login para criar uma nova conversa.');
      router.push('/login');
      return;
    }
    try {
      const newChat = await createChat('Nova Minuta');
      toast.success('Nova conversa criada!');
      if (newChat?.id) {
        router.push(`/minuta/${newChat.id}`);
      }
    } catch (error) {
      // handled
    }
  };

  const handleGenerate = async () => {
    try {
      let chat = currentChat;
      if (!chat && activeChatId) {
        await setCurrentChat(activeChatId);
        chat = useChatStore.getState().currentChat;
      }
      if (!chat) {
        chat = await createChat('Nova Minuta');
      }
      await startAgentGeneration('Gerar minuta baseada nos documentos selecionados.');
    } catch (e) {
      // handled by store/toast
    }
  };

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
      return;
    }

    if (selectedModels.length > 1) setSelectedModels([selectedModels[0]]);
    setChatMode('standard');
  };

  // Agent step labels
  const getAgentLabel = (agent: string) => {
    switch (agent) {
      case 'strategist': return 'Estrategista';
      case 'researcher': return 'Pesquisador';
      case 'drafter': return 'Redator';
      case 'reviewer': return 'Revisor';
      case 'judge': return 'Juiz';
      default: return agent;
    }
  };

  // HIL Handlers
  const handleOutlineApprove = async (sections: OutlineApprovalSection[]) => {
    try {
      await submitReview({ approved: true, outline: sections });
      toast.success('Estrutura aprovada! Agentes iniciando redação...');
    } catch (e) {
      toast.error('Erro ao enviar aprovação.');
    }
  };

  const handleOutlineReject = async () => {
    try {
      await submitReview({ approved: false, comment: "Usuário cancelou no modal." });
      toast.info('Geração cancelada.');
    } catch (e) {
      toast.error('Erro ao rejeitar.');
    }
  };

  // Check if HIL modal should be shown
  const isChatOutlineReview = reviewData?.checkpoint === 'outline' && (reviewData as any)?.mode === 'chat';
  const showOutlineModal = (reviewData?.checkpoint === 'outline' || reviewData?.type === 'outline_review') && !isChatOutlineReview;
  const outlinePayload = reviewData?.review_data?.outline || reviewData?.outline || [];

  // Convert generic list to typed sections if needed
  const initialSections: OutlineApprovalSection[] = Array.isArray(outlinePayload)
    ? outlinePayload.map((s: string | any, i: number) =>
      typeof s === 'string' ? { id: `sect-${i}`, title: s } : s
    )
    : [];

  const handleOpenQuality = () => {
    showCanvas();
    setActiveTab('audit');
  };

  // Sync checklist textareas from store (once)
  useEffect(() => {
    const criticalText = (documentChecklist || [])
      .filter((item) => item.critical)
      .map((item) => item.label)
      .join('\n');
    const nonCriticalText = (documentChecklist || [])
      .filter((item) => !item.critical)
      .map((item) => item.label)
      .join('\n');

    if (!criticalChecklistText && criticalText) setCriticalChecklistText(criticalText);
    if (!nonCriticalChecklistText && nonCriticalText) setNonCriticalChecklistText(nonCriticalText);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [documentChecklist]);

  return (
    <div className="flex h-full flex-1 min-h-0 flex-col gap-3">
      {/* Compact Toolbar */}
      <div className="flex flex-none flex-wrap items-center justify-between gap-2 rounded-xl bg-white/90 border border-slate-200/60 px-4 py-2.5 shadow-sm">
        {/* Left: Mode controls */}
        <div className="flex flex-wrap items-center gap-3">
          {/* Generation Mode Toggle */}
          <div className="flex items-center rounded-lg border border-slate-200 bg-slate-50 p-0.5">
            <RichTooltip
              title="Modo Chat (Rápido)"
              description="Conversa livre e rápida. Ideal para tirar dúvidas pontuais ou pedir resumos."
              badge="1 modelo"
              icon={<Zap className="h-3.5 w-3.5" />}
            >
              <button
                onClick={() => setMode('individual')}
                className={cn(
                  "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-all",
                  mode === 'individual'
                    ? "bg-white text-slate-900 shadow-sm"
                    : "text-slate-500 hover:text-slate-700"
                )}
              >
                <Zap className="h-3.5 w-3.5" />
                Rápido
              </button>
            </RichTooltip>
            <RichTooltip
              title="Modo Minuta (Comitê)"
              description="Geração de documentos complexos com múltiplos agentes verificando a consistência jurídica."
              badge="Multi‑agente"
              icon={<Users className="h-3.5 w-3.5" />}
            >
              <button
                onClick={() => {
                  setMode('multi-agent');
                  showCanvas();
                }}
                className={cn(
                  "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-all",
                  mode === 'multi-agent'
                    ? "bg-indigo-600 text-white shadow-sm"
                    : "text-slate-500 hover:text-slate-700"
                )}
              >
                <Users className="h-3.5 w-3.5" />
                Comitê
              </button>
            </RichTooltip>
          </div>

          <div className="h-5 w-px bg-slate-200 hidden sm:block" />

          {/* Chat Mode Toggle */}
          <div className="flex items-center rounded-lg border border-slate-200 bg-slate-50 p-0.5">
            <RichTooltip
              title="Chat Normal"
              description="Conversa com um único modelo. Ideal para iterações rápidas."
              badge="1 resposta"
              icon={<User className="h-3.5 w-3.5" />}
            >
              <button
                onClick={() => handleSetChatMode('standard')}
                className={cn(
                  "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-all",
                  chatMode !== 'multi-model'
                    ? "bg-white text-slate-900 shadow-sm"
                    : "text-slate-500 hover:text-slate-700"
                )}
              >
                <User className="h-3.5 w-3.5" />
                Normal
              </button>
            </RichTooltip>
            <RichTooltip
              title="Comparar modelos"
              description="Respostas paralelas para avaliar argumentos e escolher a melhor abordagem."
              badge="2–3 respostas"
              icon={<Scale className="h-3.5 w-3.5" />}
            >
              <button
                onClick={() => handleSetChatMode('multi-model')}
                className={cn(
                  "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-all",
                  chatMode === 'multi-model'
                    ? "bg-amber-500 text-white shadow-sm"
                    : "text-slate-500 hover:text-slate-700"
                )}
              >
                <Scale className="h-3.5 w-3.5" />
                Comparar
              </button>
            </RichTooltip>
          </div>

          <div className="h-5 w-px bg-slate-200 hidden sm:block" />

          {/* Chat Personality Toggle */}
          <div className="flex items-center rounded-lg border border-slate-200 bg-slate-50 p-0.5">
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    onClick={() => setChatPersonality('juridico')}
                    className={cn(
                      "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-all",
                      chatPersonality === 'juridico'
                        ? "bg-emerald-600 text-white shadow-sm"
                        : "text-slate-500 hover:text-slate-700"
                    )}
                  >
                    <Scale className="h-3.5 w-3.5" />
                    Jurídico
                  </button>
                </TooltipTrigger>
                <TooltipContent>
                  <p>Linguagem técnica e formal.</p>
                </TooltipContent>
              </Tooltip>

              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    onClick={() => setChatPersonality('geral')}
                    className={cn(
                      "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-all",
                      chatPersonality === 'geral'
                        ? "bg-sky-500 text-white shadow-sm"
                        : "text-slate-500 hover:text-slate-700"
                    )}
                  >
                    <Sparkles className="h-3.5 w-3.5" />
                    Livre
                  </button>
                </TooltipTrigger>
                <TooltipContent>
                  <p>Assistente geral, sem formalidades jurídicas.</p>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          </div>
        </div>

        {/* Right: Actions */}
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            className="h-8 rounded-lg text-xs"
            onClick={handleOpenQuality}
          >
            <Scale className="mr-1.5 h-3.5 w-3.5" />
            Auditoria
          </Button>

          <Button
            variant="ghost"
            size="icon"
            className={cn("h-8 w-8 rounded-lg", showSettings && "bg-slate-100")}
            onClick={() => setShowSettings(!showSettings)}
          >
            <Settings2 className="h-4 w-4" />
          </Button>

          <Button
            variant="outline"
            size="sm"
            className="h-8 rounded-lg text-xs"
            onClick={handleStartNewMinuta}
          >
            <FileText className="mr-1.5 h-3.5 w-3.5" />
            Novo chat
          </Button>

          <Button
            size="sm"
            className="h-8 rounded-lg bg-indigo-600 text-xs hover:bg-indigo-700"
            onClick={handleGenerate}
            disabled={isSending || isLoading}
          >
            <Sparkles className="mr-1.5 h-3.5 w-3.5" />
            Gerar
          </Button>
        </div>
      </div>

      {/* Expanded Settings Panel */}
      {showSettings && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 rounded-xl border border-indigo-200/60 bg-indigo-50/30 px-4 py-3 animate-in slide-in-from-top-1 duration-200">
          {/* Document Type */}
          <div className="space-y-1.5">
            <RichTooltip
              title="Tipo de Documento"
              description="Define a estrutura e o vocabulário da peça. Ajuda a IA a seguir o formato jurídico esperado."
              badge="Minuta"
            >
              <label className="text-[10px] font-semibold uppercase text-indigo-700/70">Tipo de Documento</label>
            </RichTooltip>
            <select
              className="w-full text-xs h-8 rounded-lg border border-indigo-200/60 bg-white px-2.5 focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition"
              value={useChatStore.getState().documentType || 'PETICAO_INICIAL'}
              onChange={(e) => useChatStore.getState().setDocumentType(e.target.value)}
            >
              <option value="PETICAO_INICIAL">Petição Inicial</option>
              <option value="CONTESTACAO">Contestação</option>
              <option value="RECURSO">Recurso / Apelação</option>
              <option value="PARECER">Parecer Jurídico</option>
              <option value="MANDADO_SEGURANCA">Mandado de Segurança</option>
              <option value="HABEAS_CORPUS">Habeas Corpus</option>
              <option value="RECLAMACAO_TRABALHISTA">Reclamação Trabalhista</option>
              <option value="DIVORCIO">Divórcio Consensual</option>
              <option value="CONTRATO">Contrato</option>
              <option value="NOTA_TECNICA">Nota Técnica</option>
              <option value="SENTENCA">Sentença</option>
            </select>
          </div>

          {/* Effort Level */}
          <div className="space-y-1.5">
            <RichTooltip
              title="Nível de Rigor"
              description="Controla profundidade e tempo de geração. Níveis maiores trazem mais checagens e detalhe."
              badge="Qualidade"
            >
              <label className="text-[10px] font-semibold uppercase text-indigo-700/70">Nível de Rigor</label>
            </RichTooltip>
            <div className="flex items-center gap-0.5">
              {[1, 2, 3, 4, 5].map((level) => (
                <button
                  key={level}
                  onClick={() => setEffortLevel(level)}
                  className={cn(
                    "h-8 flex-1 rounded-md text-xs font-bold transition-all",
                    effortLevel >= level
                      ? "bg-indigo-600 text-white"
                      : "bg-white text-indigo-300 border border-indigo-200/60 hover:bg-indigo-50"
                  )}
                >
                  {level}
                </button>
              ))}
            </div>
          </div>

          {/* Creativity / Temperature */}
          <div className="space-y-1.5">
            <RichTooltip
              title="Criatividade (Temperatura)"
              description="Define o equilibrio entre fidelidade e fluidez no texto."
              badge="Estilo"
            >
              <label className="text-[10px] font-semibold uppercase text-indigo-700/70">Criatividade</label>
            </RichTooltip>
            <div className="flex items-center gap-0.5">
              {([
                {
                  id: 'rigoroso',
                  label: 'Rigoroso',
                  description: 'Segue estritamente fatos e modelos. Zero alucinação. Ideal para uso final.',
                },
                {
                  id: 'padrao',
                  label: 'Padrão',
                  description: 'Equilibrio entre precisao juridica e fluidez.',
                },
                {
                  id: 'criativo',
                  label: 'Criativo',
                  description: 'Maior fluidez na escrita. Util para brainstorms ou rascunhos iniciais.',
                },
              ] as const).map((option) => (
                <RichTooltip
                  key={option.id}
                  title={option.label}
                  description={option.description}
                  badge="Temperatura"
                >
                  <button
                    type="button"
                    onClick={() => setCreativityMode(option.id)}
                    className={cn(
                      "h-8 flex-1 rounded-md text-xs font-bold transition-all",
                      creativityMode === option.id
                        ? "bg-rose-500 text-white"
                        : "bg-white text-rose-300 border border-rose-200/60 hover:bg-rose-50"
                    )}
                  >
                    {option.label}
                  </button>
                </RichTooltip>
              ))}
            </div>
          </div>

          {/* Page Range */}
          <div className="space-y-1.5">
            <RichTooltip
              title="Intervalo de páginas"
              description="Limita o tamanho da minuta e habilita revisão de outline quando definido."
              badge="Tamanho"
            >
              <label className="text-[10px] font-semibold uppercase text-indigo-700/70">Intervalo de páginas</label>
            </RichTooltip>
            <div className="flex items-center justify-between text-[10px] text-slate-500">
              <span>{minPages > 0 || maxPages > 0 ? `${minPages}-${maxPages} págs` : 'Auto'}</span>
              {(minPages > 0 || maxPages > 0) && (
                <button
                  type="button"
                  onClick={() => resetPageRange()}
                  className="text-indigo-600 hover:text-indigo-700"
                >
                  limpar
                </button>
              )}
            </div>
            <div className="grid grid-cols-2 gap-2">
              <input
                type="number"
                min={0}
                className="w-full text-xs h-8 rounded-lg border border-indigo-200/60 bg-white px-2.5 focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition"
                placeholder="Mín."
                value={minPages === 0 ? '' : minPages}
                onChange={(e) => {
                  const next = parseInt(e.target.value, 10);
                  setPageRange({ minPages: Number.isNaN(next) ? 0 : next });
                }}
              />
              <input
                type="number"
                min={0}
                className="w-full text-xs h-8 rounded-lg border border-indigo-200/60 bg-white px-2.5 focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition"
                placeholder="Máx."
                value={maxPages === 0 ? '' : maxPages}
                onChange={(e) => {
                  const next = parseInt(e.target.value, 10);
                  setPageRange({ maxPages: Number.isNaN(next) ? 0 : next });
                }}
              />
            </div>
            <div className="flex items-center gap-1">
              <button
                type="button"
                className={cn(
                  "h-7 flex-1 rounded-md text-[10px] font-semibold transition-all",
                  minPages === 5 && maxPages === 8
                    ? "bg-indigo-600 text-white"
                    : "bg-white text-indigo-400 border border-indigo-200/60 hover:bg-indigo-50"
                )}
                onClick={() => setPageRange({ minPages: 5, maxPages: 8 })}
              >
                Curta
              </button>
              <button
                type="button"
                className={cn(
                  "h-7 flex-1 rounded-md text-[10px] font-semibold transition-all",
                  minPages === 10 && maxPages === 15
                    ? "bg-indigo-600 text-white"
                    : "bg-white text-indigo-400 border border-indigo-200/60 hover:bg-indigo-50"
                )}
                onClick={() => setPageRange({ minPages: 10, maxPages: 15 })}
              >
                Média
              </button>
              <button
                type="button"
                className={cn(
                  "h-7 flex-1 rounded-md text-[10px] font-semibold transition-all",
                  minPages === 20 && maxPages === 30
                    ? "bg-indigo-600 text-white"
                    : "bg-white text-indigo-400 border border-indigo-200/60 hover:bg-indigo-50"
                )}
                onClick={() => setPageRange({ minPages: 20, maxPages: 30 })}
              >
                Longa
              </button>
            </div>
          </div>

          {/* Reasoning Level */}
          <div className="space-y-1.5">
            <RichTooltip
              title="Nível de Raciocínio"
              description="Equilibra velocidade e profundidade: rápido, médio ou profundo."
              badge="Trade-off"
            >
              <label className="text-[10px] font-semibold uppercase text-indigo-700/70">Nível de Raciocínio</label>
            </RichTooltip>
            <div className="flex items-center gap-0.5">
              {(['low', 'medium', 'high'] as const).map((level) => (
                <button
                  key={level}
                  onClick={() => setReasoningLevel(level)}
                  className={cn(
                    "h-8 flex-1 rounded-md text-xs font-bold transition-all",
                    reasoningLevel === level
                      ? "bg-purple-600 text-white"
                      : "bg-white text-purple-300 border border-purple-200/60 hover:bg-purple-50"
                  )}
                >
                  {level === 'low' ? 'Rápido' : level === 'medium' ? 'Médio' : 'Profundo'}
                </button>
              ))}
            </div>
          </div>

          {/* Base Model (Chat only) */}
          {mode === 'individual' && (
            <div className="space-y-1.5">
              <RichTooltip
                title="Modelo base (Chat)"
                description="Define qual modelo responde no modo Chat de um único modelo."
                badge="Chat"
              >
                <label className="text-[10px] font-semibold uppercase text-indigo-700/70">Modelo base (Chat)</label>
              </RichTooltip>
              <select
                className="w-full text-xs h-8 rounded-lg border border-indigo-200/60 bg-white px-2.5 focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition"
                value={selectedModel}
                onChange={(e) => setSelectedModel(e.target.value)}
              >
                {baseModelOptions.map((m) => (
                  <option key={m.id} value={m.id}>{m.label}</option>
                ))}
              </select>
            </div>
          )}

          {/* Committee Models (Only if Multi-Agent) */}
          {mode === 'multi-agent' && (
            <div className="col-span-full space-y-2 pt-2 border-t border-indigo-200/40 mt-1">
              <label className="text-[10px] font-semibold uppercase text-indigo-700/70 flex items-center gap-2">
                <Users className="h-3 w-3" /> Modelos do Comitê de Agentes
              </label>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                {/* Strategist */}
                <div className="space-y-1">
                  <span className="text-[10px] text-slate-500 font-medium">Estrategista (Planejamento)</span>
                  <select
                    className="w-full text-[10px] h-7 rounded border border-indigo-200 bg-white"
                    value={agentStrategistModel}
                    onChange={(e) => setAgentStrategistModel(e.target.value)}
                  >
                    {agentModelOptions.map((model) => (
                      <option key={model.id} value={model.id}>
                        {model.label}
                      </option>
                    ))}
                  </select>
                </div>
                {/* Drafter */}
                <div className="space-y-1">
                  <span className="text-[10px] text-slate-500 font-medium">Redator (multi-seleção, máx 3)</span>
                  <div className="space-y-1 rounded border border-indigo-200 bg-white p-2">
                    {agentModelOptions.map((model) => (
                      <label
                        key={model.id}
                        className={cn(
                          "flex items-center gap-2 text-[10px] text-slate-600",
                          !agentDrafterModels.includes(model.id) && agentDrafterModels.length >= MAX_ROLE_MODELS
                            ? "opacity-60 cursor-not-allowed"
                            : "cursor-pointer"
                        )}
                      >
                        <input
                          type="checkbox"
                          className="rounded border-indigo-300 text-indigo-600 focus:ring-indigo-500/20 h-3 w-3"
                          checked={agentDrafterModels.includes(model.id)}
                          disabled={!agentDrafterModels.includes(model.id) && agentDrafterModels.length >= MAX_ROLE_MODELS}
                          onChange={() => toggleAgentModel(agentDrafterModels, model.id, setAgentDrafterModels, "redator")}
                        />
                        <span>{model.label}</span>
                      </label>
                    ))}
                  </div>
                </div>
                {/* Reviewer */}
                <div className="space-y-1">
                  <span className="text-[10px] text-slate-500 font-medium">Revisor (multi-seleção, máx 3)</span>
                  <div className="space-y-1 rounded border border-indigo-200 bg-white p-2">
                    {agentModelOptions.map((model) => (
                      <label
                        key={model.id}
                        className={cn(
                          "flex items-center gap-2 text-[10px] text-slate-600",
                          !agentReviewerModels.includes(model.id) && agentReviewerModels.length >= MAX_ROLE_MODELS
                            ? "opacity-60 cursor-not-allowed"
                            : "cursor-pointer"
                        )}
                      >
                        <input
                          type="checkbox"
                          className="rounded border-indigo-300 text-indigo-600 focus:ring-indigo-500/20 h-3 w-3"
                          checked={agentReviewerModels.includes(model.id)}
                          disabled={!agentReviewerModels.includes(model.id) && agentReviewerModels.length >= MAX_ROLE_MODELS}
                          onChange={() => toggleAgentModel(agentReviewerModels, model.id, setAgentReviewerModels, "revisor")}
                        />
                        <span>{model.label}</span>
                      </label>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Research Options */}
          <div className="space-y-1.5">
            <RichTooltip
              title="Pesquisa externa"
              description="Controla se a IA pode buscar fontes externas para embasar a resposta."
              badge="Contexto"
            >
              <label className="text-[10px] font-semibold uppercase text-indigo-700/70">Pesquisa</label>
            </RichTooltip>
            <div className="flex flex-col gap-1">
              <RichTooltip
                title="Web Search"
                description="Consulta fontes recentes na web para reforcar fatos e citar referencias."
                badge="Rapido"
              >
                <label className="flex items-center gap-2 text-xs cursor-pointer">
                  <input
                    type="checkbox"
                    className="rounded border-indigo-300 text-indigo-600 focus:ring-indigo-500/20 h-3.5 w-3.5"
                    checked={webSearch}
                    onChange={(e) => useChatStore.getState().setWebSearch(e.target.checked)}
                  />
                  <span className="text-slate-600">Web Search</span>
                </label>
              </RichTooltip>
              <RichTooltip
                title="Deep Research"
                description="Busca mais profunda e demorada com maior cobertura de fontes."
                badge="Cobertura"
              >
                <label className="flex items-center gap-2 text-xs cursor-pointer">
                  <input
                    type="checkbox"
                    className="rounded border-indigo-300 text-indigo-600 focus:ring-indigo-500/20 h-3.5 w-3.5"
                    checked={denseResearch}
                    onChange={(e) => useChatStore.getState().setDenseResearch(e.target.checked)}
                  />
                  <span className="text-slate-600">Deep Research</span>
                </label>
              </RichTooltip>
            </div>
            <div className={cn("mt-2 space-y-1", !webSearch && "opacity-60")}>
              <RichTooltip
                title="Modo de busca"
                description="Define se uma unica busca alimenta todos os modelos ou cada modelo busca por conta propria."
                badge="Estrategia"
              >
                <div className="text-[10px] font-semibold uppercase text-slate-500">Modo de busca</div>
              </RichTooltip>
              <div className="flex flex-wrap gap-1">
                {([
                  {
                    id: 'shared',
                    label: 'Compartilhada',
                    description: 'Uma unica busca alimenta todos os modelos. Mais rapida e consistente.',
                  },
                  {
                    id: 'native',
                    label: 'Nativa por modelo',
                    description: 'Cada modelo usa a busca do proprio provedor. Mais cobertura e custo.',
                  },
                  {
                    id: 'hybrid',
                    label: 'Hibrida',
                    description: 'Combina busca compartilhada com expansoes pontuais por modelo.',
                  },
                ] as const).map((opt) => (
                  <RichTooltip key={opt.id} title={opt.label} description={opt.description} badge="Busca">
                    <button
                      type="button"
                      disabled={!webSearch}
                      onClick={() => setSearchMode(opt.id)}
                      className={cn(
                        "rounded-full border px-2 py-1 text-[10px] font-semibold transition-colors",
                        searchMode === opt.id
                          ? "border-indigo-300 bg-indigo-500/15 text-indigo-700"
                          : "border-slate-200 text-slate-500 hover:text-slate-700 hover:bg-slate-50",
                        !webSearch && "pointer-events-none"
                      )}
                    >
                      {opt.label}
                    </button>
                  </RichTooltip>
                ))}
              </div>
              <RichTooltip
                title="Multi-query"
                description="Gera varias consultas para ampliar cobertura e reduzir vies."
                badge="Exploratorio"
              >
                <label className="mt-2 flex items-center gap-2 text-xs cursor-pointer">
                  <input
                    type="checkbox"
                    className="rounded border-indigo-300 text-indigo-600 focus:ring-indigo-500/20 h-3.5 w-3.5"
                    checked={multiQuery}
                    disabled={!webSearch}
                    onChange={(e) => setMultiQuery(e.target.checked)}
                  />
                  <span className="text-slate-600">Multi-query</span>
                </label>
              </RichTooltip>
              <RichTooltip
                title="Breadth-first"
                description="Prioriza variedade de fontes antes de aprofundar detalhes."
                badge="Cobertura"
              >
                <label className="flex items-center gap-2 text-xs cursor-pointer">
                  <input
                    type="checkbox"
                    className="rounded border-indigo-300 text-indigo-600 focus:ring-indigo-500/20 h-3.5 w-3.5"
                    checked={breadthFirst}
                    disabled={!webSearch}
                    onChange={(e) => setBreadthFirst(e.target.checked)}
                  />
                  <span className="text-slate-600">Breadth-first</span>
                </label>
              </RichTooltip>
            </div>
          </div>

          {/* Audit Mode (common) */}
          <div className="space-y-1.5">
            <RichTooltip
              title="Modo de auditoria"
              description="Controla se a verificacao se limita a Base local (RAG + ingestão) ou inclui fontes externas."
              badge="Compliance"
            >
              <label className="text-[10px] font-semibold uppercase text-indigo-700/70">Modo de auditoria</label>
            </RichTooltip>
            <div className="flex flex-wrap gap-1">
              <RichTooltip
                title="Somente Base local"
                description="Valida apenas referencias da base local (RAG + ingestão). Mais restritivo."
                badge="Restrito"
              >
                <button
                  type="button"
                  onClick={() => setAuditMode('sei_only')}
                  className={cn(
                    "rounded-full border px-2 py-1 text-[10px] font-semibold transition-colors",
                    auditMode === 'sei_only'
                      ? "border-indigo-300 bg-indigo-500/15 text-indigo-700"
                      : "border-slate-200 text-slate-500 hover:text-slate-700 hover:bg-slate-50"
                  )}
                >
                  Somente Base local
                </button>
              </RichTooltip>
              <RichTooltip
                title="Base local + fontes externas"
                description="Combina Base local (RAG + ingestão) com fontes externas para detectar inconsistencias."
                badge="Ampliada"
              >
                <button
                  type="button"
                  onClick={() => setAuditMode('research')}
                  className={cn(
                    "rounded-full border px-2 py-1 text-[10px] font-semibold transition-colors",
                    auditMode === 'research'
                      ? "border-indigo-300 bg-indigo-500/15 text-indigo-700"
                      : "border-slate-200 text-slate-500 hover:text-slate-700 hover:bg-slate-50"
                  )}
                >
                  Base local + fontes externas
                </button>
              </RichTooltip>
            </div>
          </div>

          {/* Control Options */}
          <div className="space-y-1.5">
            <RichTooltip
              title="Controle"
              description="Define pontos de revisao humana antes da geracao final."
              badge="Fluxo"
            >
              <label className="text-[10px] font-semibold uppercase text-indigo-700/70">Controle</label>
            </RichTooltip>
            {mode === 'individual' ? (
              <div className="space-y-1">
                {(() => {
                  const hasPageRange = minPages > 0 || maxPages > 0;
                  const canShow = hasPageRange && chatMode !== 'multi-model';
                  if (!canShow) {
                    return (
                      <RichTooltip
                        title="Revisar outline (pré-resposta)"
                        description="Disponivel apenas quando ha intervalo de paginas e o chat nao esta em Comparar modelos."
                        badge="Chat"
                      >
                        <p className="text-[10px] text-slate-500">
                          {chatMode === 'multi-model'
                            ? 'Revisão de outline é disponível apenas no Chat normal (1 modelo).'
                            : 'Defina um intervalo de páginas para habilitar revisão de outline.'}
                        </p>
                      </RichTooltip>
                    );
                  }
                  return (
                    <>
                      <RichTooltip
                        title="Revisar outline (pré-resposta)"
                        description="Pausa antes do streaming para aprovar ou editar a estrutura."
                        badge="Chat"
                        meta="Requer intervalo de paginas + Chat normal"
                      >
                        <label className="flex items-center gap-2 text-xs cursor-pointer">
                          <input
                            type="checkbox"
                            className="rounded border-indigo-300 text-indigo-600 focus:ring-indigo-500/20 h-3.5 w-3.5"
                            checked={chatOutlineReviewEnabled}
                            onChange={(e) => setChatOutlineReviewEnabled(e.target.checked)}
                          />
                          <span className="text-slate-600">Revisar outline (pré‑resposta)</span>
                        </label>
                      </RichTooltip>
                      <p className="text-[10px] text-slate-500">
                        Abre um modal para revisar/editar a estrutura antes do streaming.
                      </p>
                    </>
                  );
                })()}
              </div>
            ) : (
              <div className="space-y-1">
                <RichTooltip
                  title="Aprovar outline (HIL — Minuta)"
                  description="No comite de agentes, pausa para voce aprovar/editar a outline antes da redacao."
                  badge="Minuta"
                >
                  <label className="flex items-center gap-2 text-xs cursor-pointer">
                    <input
                      type="checkbox"
                      className="rounded border-indigo-300 text-indigo-600 focus:ring-indigo-500/20 h-3.5 w-3.5"
                      checked={hilOutlineEnabled}
                      onChange={(e) => setHilOutlineEnabled(e.target.checked)}
                    />
                    <span className="text-slate-600">Aprovar outline (HIL — Minuta)</span>
                  </label>
                </RichTooltip>
                <p className="text-[10px] text-slate-500">
                  No comitê de agentes, pausa para você aprovar/editar a outline antes da redação.
                </p>
              </div>
            )}
          </div>

          {/* Minuta-only: Qualidade + Gate + Checklist + Formatação */}
          {mode === 'multi-agent' && (
            <div className="col-span-full grid grid-cols-2 lg:grid-cols-4 gap-4 pt-2 border-t border-indigo-200/40">
              {/* Perfil de qualidade */}
              <div className="space-y-1.5 col-span-2">
                <RichTooltip
                  title="Perfil de qualidade"
                  description="Define rodadas, metas de nota e politica de HIL para a minuta."
                  badge="Minuta"
                >
                  <label className="text-[10px] font-semibold uppercase text-indigo-700/70">Perfil de qualidade</label>
                </RichTooltip>
                <div className="flex flex-wrap gap-1">
                  {([
                    {
                      id: 'rapido',
                      label: 'Rápido',
                      description: '1 rodada • meta seção ≥ 8.5, final ≥ 9.0 • HIL só no final.',
                    },
                    {
                      id: 'padrao',
                      label: 'Padrão',
                      description: '2 rodadas • meta seção ≥ 9.0, final ≥ 9.4 • HIL por seção opcional + final.',
                    },
                    {
                      id: 'rigoroso',
                      label: 'Rigoroso',
                      description: '4 rodadas • meta seção ≥ 9.4, final ≥ 9.8 • HIL por seção + final.',
                    },
                    {
                      id: 'auditoria',
                      label: 'Auditoria',
                      description: '6 rodadas • meta seção ≥ 9.6, final = 10.0 • HIL por seção obrigatório + final obrigatório.',
                    },
                  ] as const).map((p) => (
                    <RichTooltip key={p.id} title={p.label} description={p.description} badge="Perfil">
                      <button
                        type="button"
                        onClick={() => setQualityProfile(p.id)}
                        className={cn(
                          "rounded-full border px-2 py-1 text-[10px] font-semibold transition-colors",
                          qualityProfile === p.id
                            ? "border-indigo-300 bg-indigo-500/15 text-indigo-700"
                            : "border-slate-200 text-slate-500 hover:text-slate-700 hover:bg-slate-50"
                        )}
                      >
                        {p.label}
                      </button>
                    </RichTooltip>
                  ))}
                </div>
                <div className="grid grid-cols-3 gap-2 pt-2">
                  <div className="space-y-1">
                    <RichTooltip
                      title="Nota da seção"
                      description="Meta minima para cada secao antes de aceitar a saida. Sobrescreve o perfil quando definida."
                      badge="Override"
                    >
                      <div className="text-[10px] font-semibold uppercase text-slate-500">Nota seção</div>
                    </RichTooltip>
                    <input
                      type="number"
                      min={0}
                      max={10}
                      step={0.1}
                      className="w-full text-xs h-8 rounded-lg border border-indigo-200/60 bg-white px-2.5"
                      placeholder="Ex.: 9.2"
                      value={qualityTargetSectionScore ?? ''}
                      onChange={(e) => setQualityTargetSectionScore(clampScore(parseOptionalNumber(e.target.value)))}
                    />
                  </div>
                  <div className="space-y-1">
                    <RichTooltip
                      title="Nota final"
                      description="Meta minima para a nota global do documento. Sobrescreve o perfil quando definida."
                      badge="Override"
                    >
                      <div className="text-[10px] font-semibold uppercase text-slate-500">Nota final</div>
                    </RichTooltip>
                    <input
                      type="number"
                      min={0}
                      max={10}
                      step={0.1}
                      className="w-full text-xs h-8 rounded-lg border border-indigo-200/60 bg-white px-2.5"
                      placeholder="Ex.: 9.8"
                      value={qualityTargetFinalScore ?? ''}
                      onChange={(e) => setQualityTargetFinalScore(clampScore(parseOptionalNumber(e.target.value)))}
                    />
                  </div>
                  <div className="space-y-1">
                    <RichTooltip
                      title="Rodadas"
                      description="Limita o numero de iteracoes de melhoria. Sobrescreve o perfil quando definido."
                      badge="Override"
                    >
                      <div className="text-[10px] font-semibold uppercase text-slate-500">Rodadas</div>
                    </RichTooltip>
                    <input
                      type="number"
                      min={1}
                      max={10}
                      step={1}
                      className="w-full text-xs h-8 rounded-lg border border-indigo-200/60 bg-white px-2.5"
                      placeholder="Ex.: 3"
                      value={qualityMaxRounds ?? ''}
                      onChange={(e) => setQualityMaxRounds(clampRounds(parseOptionalNumber(e.target.value)))}
                    />
                  </div>
                </div>
              </div>

              {/* Gate documental */}
              <div className="space-y-1.5">
                <RichTooltip
                  title="Gate documental"
                  description="Define se a minuta bloqueia quando falta documento essencial."
                  badge="Minuta"
                >
                  <label className="text-[10px] font-semibold uppercase text-indigo-700/70">Gate documental</label>
                </RichTooltip>
                <div className="flex flex-wrap gap-1">
                  {([
                    { id: 'auto', label: 'Perfil', description: 'Segue o perfil de qualidade atual.' },
                    { id: 'on', label: 'Bloquear', description: 'Exige documentos obrigatorios antes de seguir.' },
                    { id: 'off', label: 'Ressalva', description: 'Permite continuar com aviso e sinalizacao.' },
                  ] as const).map((opt) => {
                    const modeValue =
                      strictDocumentGateOverride === null ? 'auto' : strictDocumentGateOverride ? 'on' : 'off';
                    return (
                      <RichTooltip key={opt.id} title={opt.label} description={opt.description} badge="Gate">
                        <button
                          type="button"
                          onClick={() => {
                            if (opt.id === 'auto') setStrictDocumentGateOverride(null);
                            if (opt.id === 'on') setStrictDocumentGateOverride(true);
                            if (opt.id === 'off') setStrictDocumentGateOverride(false);
                          }}
                          className={cn(
                            "rounded-full border px-2 py-1 text-[10px] font-semibold transition-colors",
                            modeValue === opt.id
                              ? "border-indigo-300 bg-indigo-500/15 text-indigo-700"
                              : "border-slate-200 text-slate-500 hover:text-slate-700 hover:bg-slate-50"
                          )}
                        >
                          {opt.label}
                        </button>
                      </RichTooltip>
                    );
                  })}
                </div>
              </div>

              {/* Formatação */}
              <div className="space-y-1.5">
                <RichTooltip
                  title="Formatação"
                  description="Adiciona elementos extras de estrutura e navegacao no documento."
                  badge="Saida"
                >
                  <label className="text-[10px] font-semibold uppercase text-indigo-700/70">Formatação</label>
                </RichTooltip>
                <div className="flex flex-col gap-1">
                  <RichTooltip
                    title="Incluir sumario"
                    description="Gera um indice automatico com secoes e paginacao."
                    badge="Navegacao"
                  >
                    <label className="flex items-center gap-2 text-xs cursor-pointer">
                      <input
                        type="checkbox"
                        className="rounded border-indigo-300 text-indigo-600 focus:ring-indigo-500/20 h-3.5 w-3.5"
                        checked={!!formattingOptions?.includeToc}
                        onChange={(e) => setFormattingOptions({ includeToc: e.target.checked })}
                      />
                      <span className="text-slate-600">Incluir sumário</span>
                    </label>
                  </RichTooltip>
                  <RichTooltip
                    title="Resumos por secao"
                    description="Cria um resumo curto ao final de cada secao."
                    badge="Sintese"
                  >
                    <label className="flex items-center gap-2 text-xs cursor-pointer">
                      <input
                        type="checkbox"
                        className="rounded border-indigo-300 text-indigo-600 focus:ring-indigo-500/20 h-3.5 w-3.5"
                        checked={!!formattingOptions?.includeSummaries}
                        onChange={(e) => setFormattingOptions({ includeSummaries: e.target.checked })}
                      />
                      <span className="text-slate-600">Resumos por seção</span>
                    </label>
                  </RichTooltip>
                  <RichTooltip
                    title="Tabela sintese"
                    description="Gera uma tabela final com pontos-chave e referencias."
                    badge="Sintese"
                  >
                    <label className="flex items-center gap-2 text-xs cursor-pointer">
                      <input
                        type="checkbox"
                        className="rounded border-indigo-300 text-indigo-600 focus:ring-indigo-500/20 h-3.5 w-3.5"
                        checked={!!formattingOptions?.includeSummaryTable}
                        onChange={(e) => setFormattingOptions({ includeSummaryTable: e.target.checked })}
                      />
                      <span className="text-slate-600">Tabela síntese</span>
                    </label>
                  </RichTooltip>
                </div>
              </div>

              {/* Checklist complementar */}
              <div className="space-y-1.5 col-span-full">
                <RichTooltip
                  title="Checklist complementar"
                  description="Itens extras para checagem automatica, alem da Base local (RAG + ingestão). Um item por linha."
                  badge="Validacao"
                >
                  <label className="text-[10px] font-semibold uppercase text-indigo-700/70">Checklist complementar</label>
                </RichTooltip>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1">
                    <RichTooltip
                      title="Itens criticos"
                      description="Faltas aqui indicam risco alto e podem bloquear a entrega."
                      badge="Critico"
                    >
                      <div className="text-[10px] font-semibold uppercase text-rose-600/70">Críticos</div>
                    </RichTooltip>
                    <textarea
                      rows={3}
                      className="w-full text-xs rounded-lg border border-indigo-200/60 bg-white px-2.5 py-2"
                      placeholder={"Ex.: Ata de licitação\nTED assinado\nHomologação"}
                      value={criticalChecklistText}
                      onChange={(e) => {
                        const next = e.target.value;
                        setCriticalChecklistText(next);
                        updateDocumentChecklist(next, nonCriticalChecklistText);
                      }}
                    />
                  </div>
                  <div className="space-y-1">
                    <RichTooltip
                      title="Itens nao criticos"
                      description="Avisos complementares para checagem, sem bloquear."
                      badge="Opcional"
                    >
                      <div className="text-[10px] font-semibold uppercase text-slate-500">Não críticos</div>
                    </RichTooltip>
                    <textarea
                      rows={3}
                      className="w-full text-xs rounded-lg border border-indigo-200/60 bg-white px-2.5 py-2"
                      placeholder={"Ex.: Numero de apoio\nMemorando complementar"}
                      value={nonCriticalChecklistText}
                      onChange={(e) => {
                        const next = e.target.value;
                        setNonCriticalChecklistText(next);
                        updateDocumentChecklist(criticalChecklistText, next);
                      }}
                    />
                  </div>
                </div>
                <p className="text-[10px] text-slate-500">
                  Itens adicionais para checagem automática (um por linha). Não substitui a base local (RAG + ingestão).
                </p>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Main Content Area - Resizable Layout */}
      <div
        ref={splitContainerRef}
        className="flex-1 h-full flex flex-row gap-0 min-h-0 overflow-hidden"
      >
        {/* Left Panel: Chat - Resizable via divider, hidden when canvas is expanded */}
        <div
          className={cn(
            "flex min-h-0 h-full flex-col rounded-l-xl border border-slate-200/60 bg-white shadow-sm overflow-hidden transition-all duration-300 font-google-sans-text",
            canvasState === 'expanded' && "hidden"
          )}
          style={{ width: canvasState === 'expanded' ? '0%' : `${chatPanelWidth}%`, minWidth: canvasState === 'expanded' ? '0px' : '300px', maxWidth: '70%' }}
        >
          {/* Mode Status Bar */}
          <div className="flex items-center justify-between gap-2 px-4 py-2.5 border-b border-slate-100 bg-slate-50/50">
            <div className="flex items-center gap-2">
              <div className={cn(
                "flex h-2 w-2 rounded-full",
                mode === 'multi-agent' ? "bg-indigo-500 animate-pulse" : "bg-emerald-500"
              )} />
              <span className={cn(
                "text-xs font-medium",
                mode === 'multi-agent' ? "text-indigo-600" : "text-emerald-600"
              )}>
                {mode === 'multi-agent' ? 'Comitê de Agentes' : 'Modo Direto'}
              </span>
            </div>
            {canvasState === 'hidden' && (
              <Button
                variant="outline"
                size="sm"
                className="h-7 text-[11px]"
                onClick={showCanvas}
              >
                <FileText className="mr-1 h-3.5 w-3.5" />
                Abrir canvas
              </Button>
            )}
          </div>

          {/* Agent Progress (Multi-Agent only) */}
          {mode === 'multi-agent' && isAgentRunning && agentSteps.length > 0 && (
            <div className="border-b border-indigo-100 bg-indigo-50/50 p-3">
              <h3 className="mb-2 text-[10px] font-semibold text-indigo-600 uppercase tracking-wider flex items-center justify-between">
                <span>Processo Multi-Agente</span>
                {agentSteps.some(s => s.status === 'working') && <Loader2 className="h-3 w-3 animate-spin" />}
              </h3>
              <div className="space-y-1.5 max-h-[120px] overflow-y-auto">
                {agentSteps.map((step) => (
                  <div key={step.id} className="flex items-center gap-2">
                    <div className={cn(
                      "flex h-4 w-4 items-center justify-center rounded-full flex-shrink-0",
                      step.status === 'completed' && "bg-emerald-100 text-emerald-600",
                      step.status === 'working' && "bg-indigo-100 text-indigo-600",
                      step.status === 'pending' && "bg-slate-100 text-slate-400",
                    )}>
                      {step.status === 'completed' && <CheckCircle2 className="h-3 w-3" />}
                      {step.status === 'working' && <Loader2 className="h-3 w-3 animate-spin" />}
                      {step.status === 'pending' && <Circle className="h-3 w-3" />}
                    </div>
                    <span className={cn(
                      "text-xs truncate",
                      step.status === 'working' ? "text-indigo-700 font-medium" : "text-slate-600"
                    )}>
                      {getAgentLabel(step.agent)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Chat Content */}
          <div className="flex-1 min-h-0 overflow-hidden flex flex-col">
            {activeChatId ? (
              <ChatInterface chatId={activeChatId} hideInput={false} />
            ) : (
              <>
                {/* Empty state message */}
                <div className="flex-1 flex flex-col items-center justify-center gap-4 p-6 text-center">
                  <div className={cn(
                    "rounded-2xl p-5",
                    mode === 'multi-agent' ? "bg-indigo-100" : "bg-slate-100"
                  )}>
                    {mode === 'multi-agent'
                      ? <Users className="h-10 w-10 text-indigo-400" />
                      : <Sparkles className="h-10 w-10 text-slate-400" />
                    }
                  </div>
                  <div>
                    <p className="text-base font-semibold text-slate-900 mb-1">Pronto para começar</p>
                    <p className="text-sm text-slate-500 max-w-[280px]">
                      {mode === 'multi-agent'
                        ? 'O comitê de agentes irá colaborar para gerar seu documento jurídico.'
                        : 'O modelo irá gerar seu documento diretamente.'}
                    </p>
                  </div>
                </div>
                {/* Chat Input always visible */}
                <div className="border-t bg-card p-3">
                  <ChatInput
                    onSend={async (content) => {
                      try {
                        const newChat = await createChat('Nova Minuta');
                        if (newChat) {
                          if (newChat?.id) router.push(`/minuta/${newChat.id}`);
                          await sendMessage(content);
                        }
                      } catch (e) {
                        toast.error('Erro ao enviar mensagem');
                      }
                    }}
                    disabled={isSending}
                  />
                </div>
              </>
            )}
          </div>

          {/* Fontes Panel (Collapsible) */}
          <div className="border-t border-slate-100">
            <button
              onClick={() => setShowFontes(!showFontes)}
              className="w-full flex items-center justify-between px-4 py-2.5 text-xs font-medium text-slate-500 hover:bg-slate-50 transition-colors"
            >
              <div className="flex items-center gap-2">
                <FileSearch className="h-4 w-4" />
                <span>Fontes RAG</span>
                <span className="text-[10px] bg-slate-100 px-2 py-0.5 rounded-full text-slate-600">
                  {contextItems.length}
                </span>
              </div>
              {showFontes ? <ChevronDown className="h-4 w-4" /> : <ChevronUp className="h-4 w-4" />}
            </button>

            {showFontes && (
              <div className="max-h-[150px] overflow-y-auto p-3 bg-slate-50/50 space-y-1.5">
                {contextItems.length > 0 ? (
                  contextItems.map((item: ContextItem, idx: number) => (
                    <div key={idx} className="flex items-center gap-2 text-sm p-2.5 rounded-lg bg-white border border-slate-100">
                      <BookOpen className="h-4 w-4 text-indigo-500 flex-shrink-0" />
                      <span className="truncate text-slate-600">{item.name || `Documento ${idx + 1}`}</span>
                    </div>
                  ))
                ) : (
                  <p className="text-xs text-slate-400 text-center py-3">
                    Nenhum documento no contexto.
                  </p>
                )}
              </div>
            )}
          </div>
        </div>

        {canvasState === 'normal' && (
          <div
            role="separator"
            aria-orientation="vertical"
            aria-label="Redimensionar painel"
            className={cn(
              "relative w-3 cursor-col-resize bg-transparent",
              "before:absolute before:left-1/2 before:top-0 before:h-full before:w-px before:-translate-x-1/2 before:bg-slate-200/80",
              isResizing && "bg-slate-100/80"
            )}
            onPointerDown={handleDividerPointerDown}
            onPointerMove={handleDividerPointerMove}
            onPointerUp={handleDividerPointerUp}
            onPointerCancel={handleDividerPointerUp}
          >
            <div className="absolute inset-0" />
          </div>
        )}

        {/* Right Panel: Canvas */}
        {canvasState !== 'hidden' && (
          <div className={cn(
            "min-h-0 h-full rounded-r-xl border border-l-0 border-slate-200/60 bg-white shadow-sm overflow-hidden transition-all duration-300",
            canvasState === 'expanded' ? "flex-1 rounded-xl border-l" : "flex-1"
          )}>
            <CanvasContainer />
          </div>
        )}
      </div>

      {/* HIL Modals */}
      <OutlineApprovalModal
        isOpen={showOutlineModal}
        onClose={handleOutlineReject}
        onApprove={handleOutlineApprove}
        onReject={handleOutlineReject}
        initialSections={initialSections}
        documentType={useChatStore.getState().documentType || 'Documento'}
      />
    </div>
  );
}
