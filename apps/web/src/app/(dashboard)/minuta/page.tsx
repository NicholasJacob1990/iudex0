'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
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
  Maximize2,
  Minimize2,
} from 'lucide-react';
import { toast } from 'sonner';
import { CanvasContainer, OutlineApprovalModal, MinutaSettingsDrawer } from '@/components/dashboard';
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

type HilSectionPolicy = 'none' | 'optional' | 'required';

const QUALITY_PROFILE_SPECS = [
  {
    id: 'rapido',
    label: 'Rápido',
    description: '1 rodada • meta seção: inativa, final ≥ 9.0 • HIL só no final.',
    targetSectionScore: 8.5,
    targetFinalScore: 9.0,
    maxRounds: 1,
    hilSectionPolicy: 'none',
    hilFinalRequired: true,
  },
  {
    id: 'padrao',
    label: 'Padrão',
    description: '2 rodadas • meta seção ≥ 9.0, final ≥ 9.4 • HIL por seção opcional + final.',
    targetSectionScore: 9.0,
    targetFinalScore: 9.4,
    maxRounds: 2,
    hilSectionPolicy: 'optional',
    hilFinalRequired: true,
  },
  {
    id: 'rigoroso',
    label: 'Rigoroso',
    description: '4 rodadas • meta seção ≥ 9.4, final ≥ 9.8 • HIL por seção obrigatório + final obrigatório.',
    targetSectionScore: 9.4,
    targetFinalScore: 9.8,
    maxRounds: 4,
    hilSectionPolicy: 'required',
    hilFinalRequired: true,
  },
  {
    id: 'auditoria',
    label: 'Auditoria',
    description: '6 rodadas • meta seção ≥ 9.6, final ≥ 10.0 • HIL por seção obrigatório + final obrigatório.',
    targetSectionScore: 9.6,
    targetFinalScore: 10.0,
    maxRounds: 6,
    hilSectionPolicy: 'required',
    hilFinalRequired: true,
  },
] as const;

type QualityProfileSpec = (typeof QUALITY_PROFILE_SPECS)[number];

const formatScoreLabel = (value: number) => value.toFixed(1);

const formatRoundsLabel = (value: number) => `${value} rodada${value === 1 ? '' : 's'}`;

const formatHilPolicyLabel = (policy: HilSectionPolicy, finalRequired: boolean) => {
  if (policy === 'none') {
    return finalRequired ? 'HIL só no final.' : 'Sem HIL.';
  }
  if (policy === 'optional') {
    return finalRequired ? 'HIL por seção opcional + final.' : 'HIL por seção opcional.';
  }
  return finalRequired ? 'HIL por seção obrigatório + final obrigatório.' : 'HIL por seção obrigatório.';
};

export default function MinutaPage() {
  const router = useRouter();
  const params = useParams<{ chatId?: string | string[] }>();
  const { isAuthenticated } = useAuthStore();
  const autoCreateAttemptedRef = useRef(false);
  const pageRootRef = useRef<HTMLDivElement>(null);
  const chatPanelRef = useRef<HTMLDivElement>(null);
  const canvasPanelRef = useRef<HTMLDivElement>(null);
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
    retryProgress,
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
    autoApproveHil,
    setAutoApproveHil,
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
    qualityMaxFinalReviewLoops,
    setQualityMaxFinalReviewLoops,
    qualityStyleRefineMaxRounds,
    setQualityStyleRefineMaxRounds,
    qualityMaxResearchVerifierAttempts,
    setQualityMaxResearchVerifierAttempts,
    qualityMaxRagRetries,
    setQualityMaxRagRetries,
    qualityRagRetryExpandScope,
    setQualityRagRetryExpandScope,
    recursionLimitOverride,
    setRecursionLimitOverride,
    strictDocumentGateOverride,
    setStrictDocumentGateOverride,
    hilSectionPolicyOverride,
    setHilSectionPolicyOverride,
    hilFinalRequiredOverride,
    setHilFinalRequiredOverride,
    documentChecklist,
    setDocumentChecklist,
    cragMinBestScoreOverride,
    setCragMinBestScoreOverride,
    cragMinAvgScoreOverride,
    setCragMinAvgScoreOverride,
    forceGranularDebate,
    setForceGranularDebate,
    maxDivergenceHilRounds,
    setMaxDivergenceHilRounds,
    formattingOptions,
    setFormattingOptions,
    chatMode,
    setChatMode,
    selectedModels,
    setSelectedModels,
    setShowMultiModelComparator,
    webSearch,
    webSearchModel,
    setWebSearchModel,
    denseResearch,
    deepResearchProvider,
    setDeepResearchProvider,
    deepResearchModel,
    setDeepResearchModel,
    reasoningLevel,
    setReasoningLevel,
    researchPolicy,
    setResearchPolicy,
    agentStrategistModel,
    setAgentStrategistModel,
    agentDrafterModels,
    setAgentDrafterModels,
    agentReviewerModels,
    setAgentReviewerModels,
    chatPersonality,
    setChatPersonality,
    cragGate,
    creativityMode,
    setCreativityMode,
    temperatureOverride,
    setTemperatureOverride,
  } = useChatStore();

  const { state: canvasState, showCanvas, hideCanvas, setState: setCanvasState, setActiveTab } = useCanvasStore();
  const { items: contextItems } = useContextStore();

  const [showFontes, setShowFontes] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [showAdvancedTuning, setShowAdvancedTuning] = useState(false);
  const [mode, setMode] = useState<GenerationMode>('multi-agent');
  const [chatPanelWidth, setChatPanelWidth] = useState(45);
  const [isResizing, setIsResizing] = useState(false);
  const splitContainerRef = useRef<HTMLDivElement>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [pendingFullscreenTarget, setPendingFullscreenTarget] = useState<'chat' | 'canvas' | 'split' | null>(null);

  const MAX_ROLE_MODELS = 3;
  const DEFAULT_COMPARE_MODELS = ['gpt-5.2', 'claude-4.5-sonnet', 'gemini-3-flash'];
  const agentModelOptions = listModels({ forAgents: true });
  const baseModelOptions = listModels({ forJuridico: true });
  const getModelLabel = (modelId: string) => {
    const found = agentModelOptions.find((m) => m.id === modelId)
      || baseModelOptions.find((m) => m.id === modelId);
    return found?.label || modelId;
  };
  const committeeModelIds = useMemo(
    () => Array.from(new Set([...(agentDrafterModels || []), ...(agentReviewerModels || [])])),
    [agentDrafterModels, agentReviewerModels]
  );
  const webSearchModelOptions = useMemo(
    () =>
      agentModelOptions.filter((m) =>
        ['openai', 'anthropic', 'google', 'perplexity'].includes(m.provider)
        && !m.capabilities.includes('deep_research')
      ),
    [agentModelOptions]
  );
  const expandScopeMode =
    qualityRagRetryExpandScope === null ? 'auto' : qualityRagRetryExpandScope ? 'on' : 'off';
  const hilSectionPolicyMode =
    hilSectionPolicyOverride === null ? 'auto' : hilSectionPolicyOverride;
  const hilFinalRequiredMode =
    hilFinalRequiredOverride === null ? 'auto' : hilFinalRequiredOverride ? 'on' : 'off';
  const canExpandScope = auditMode !== 'sei_only';
  const selectedProfileSpec =
    QUALITY_PROFILE_SPECS.find((profile) => profile.id === qualityProfile) ?? QUALITY_PROFILE_SPECS[1];
  const effectiveHilSectionPolicy = hilSectionPolicyOverride ?? selectedProfileSpec.hilSectionPolicy;
  const hasQualityOverrides =
    qualityTargetSectionScore != null
    || qualityTargetFinalScore != null
    || qualityMaxRounds != null
    || qualityMaxFinalReviewLoops != null
    || hilSectionPolicyOverride != null
    || hilFinalRequiredOverride != null
    || maxDivergenceHilRounds != null
    || forceGranularDebate;
  const qualityProfileMeta = hasQualityOverrides
    ? 'Valores ajustados pelos overrides abaixo.'
    : undefined;
  const buildProfileDescription = (profile: QualityProfileSpec) => {
    if (!hasQualityOverrides) {
      return profile.description;
    }
    const targetSectionScore = qualityTargetSectionScore ?? profile.targetSectionScore;
    const targetFinalScore = qualityTargetFinalScore ?? profile.targetFinalScore;
    const maxRounds = qualityMaxRounds ?? profile.maxRounds;
    const hilPolicy = hilSectionPolicyOverride ?? profile.hilSectionPolicy;
    const hilFinalRequired = hilFinalRequiredOverride ?? profile.hilFinalRequired;
    const extras: string[] = [];
    if (qualityMaxFinalReviewLoops != null) extras.push(`refino final: ${Math.floor(qualityMaxFinalReviewLoops)}`);
    if (maxDivergenceHilRounds != null) extras.push(`divergência HIL: ${Math.floor(maxDivergenceHilRounds)}`);
    if (forceGranularDebate) extras.push('granular: on');
    const sectionLabel =
      hilPolicy === 'none'
        ? 'meta seção: inativa'
        : `meta seção ≥ ${formatScoreLabel(targetSectionScore)}`;

    const base = `${formatRoundsLabel(maxRounds)} • ${sectionLabel}, final ≥ ${formatScoreLabel(targetFinalScore)} • ${formatHilPolicyLabel(hilPolicy, hilFinalRequired)}`;
    return extras.length > 0 ? `${base} • ${extras.join(' • ')}` : base;
  };
  const sectionScoreMeta =
    effectiveHilSectionPolicy === 'none' ? 'Sem efeito no perfil atual.' : undefined;
  const sectionScoreDescription =
    'Meta minima para cada secao antes de aceitar a saida. So aplica quando HIL por secao esta ativo; sobrescreve o perfil quando definida.';

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
    return Math.max(1, Math.min(6, Math.floor(value)));
  };
  const clampStyleRounds = (value: number | null) => {
    if (value === null) return null;
    return Math.max(0, Math.min(6, Math.floor(value)));
  };
  const clampRetry = (value: number | null) => {
    if (value === null) return null;
    return Math.max(0, Math.min(5, Math.floor(value)));
  };
  const clampCragScore = (value: number | null) => {
    if (value === null) return null;
    return Math.max(0, Math.min(1, value));
  };
  const clampTemperature = (value: number | null) => {
    if (value === null) return null;
    return Math.max(0, Math.min(1, value));
  };
  const clampDivergenceHilRounds = (value: number | null) => {
    if (value === null) return null;
    return Math.max(1, Math.min(5, Math.floor(value)));
  };
  const clampRecursionLimit = (value: number | null) => {
    if (value === null) return null;
    return Math.max(20, Math.min(500, Math.floor(value)));
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

  useEffect(() => {
    if (mode !== 'multi-agent') return;
    if (agentStrategistModel === selectedModel) return;
    setAgentStrategistModel(selectedModel);
  }, [mode, agentStrategistModel, selectedModel, setAgentStrategistModel]);

  // Sync context items to ChatStore
  useEffect(() => {
    setContext(contextItems);
  }, [contextItems, setContext]);

  // Ensure canvas is visible on initial mount only (not overriding user close action)
  useEffect(() => {
    showCanvas();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Track browser fullscreen state (ESC exits fullscreen)
  useEffect(() => {
    if (typeof document === 'undefined') return;
    const onChange = () => setIsFullscreen(!!document.fullscreenElement);
    onChange();
    document.addEventListener('fullscreenchange', onChange);
    return () => document.removeEventListener('fullscreenchange', onChange);
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

  // Layout mode: chat-only | split | canvas-only
  const layoutMode: 'chat' | 'split' | 'canvas' =
    canvasState === 'hidden' ? 'chat' : canvasState === 'expanded' ? 'canvas' : 'split';
  const chatActive = layoutMode !== 'canvas';
  const canvasActive = layoutMode !== 'chat';

  const fullscreenApi = useMemo(() => {
    if (typeof document === 'undefined') return { supported: false as const };
    const supported = typeof document.documentElement?.requestFullscreen === 'function';
    return { supported };
  }, []);

  const enterFullscreen = async (target?: HTMLElement | null) => {
    if (!fullscreenApi.supported) return;
    try {
      const el = target || pageRootRef.current || document.documentElement;
      // @ts-ignore
      await el.requestFullscreen?.();
    } catch {
      // ignore
    }
  };

  const exitFullscreen = async () => {
    if (typeof document === 'undefined') return;
    if (!document.fullscreenElement) return;
    try {
      await document.exitFullscreen();
    } catch {
      // ignore
    }
  };

  // Perform fullscreen requests only after the relevant panel is mounted.
  useEffect(() => {
    if (!pendingFullscreenTarget) return;
    if (typeof document === 'undefined') return;

    const targetEl =
      pendingFullscreenTarget === 'chat'
        ? chatPanelRef.current
        : pendingFullscreenTarget === 'canvas'
          ? canvasPanelRef.current
          : pageRootRef.current;

    if (!targetEl) return;

    (async () => {
      // If currently fullscreen on a different element, exit first (more compatible across browsers).
      if (document.fullscreenElement && document.fullscreenElement !== targetEl) {
        await exitFullscreen();
      }
      await enterFullscreen(targetEl);
      setPendingFullscreenTarget(null);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingFullscreenTarget, layoutMode]);

  const toggleChatMode = () => {
    // Chat button toggles between chat-only and split (sem forçar tela cheia)
    if (layoutMode === 'chat') {
      showCanvas();
      setCanvasState('normal');
      return;
    }
    hideCanvas();
  };

  const toggleCanvasMode = () => {
    // Canvas button toggles between canvas-only and split (sem forçar tela cheia)
    if (layoutMode === 'canvas') {
      showCanvas();
      setCanvasState('normal');
      return;
    }
    showCanvas();
    setCanvasState('expanded');
  };

  const layoutLabel =
    layoutMode === 'chat'
      ? 'Chat'
      : layoutMode === 'canvas'
        ? 'Canvas'
        : 'Tela dividida';

  const handleToggleFullscreen = () => {
    if (!fullscreenApi.supported) return;
    if (isFullscreen) {
      void exitFullscreen();
      return;
    }
    if (layoutMode === 'chat') {
      setPendingFullscreenTarget('chat');
      return;
    }
    if (layoutMode === 'canvas') {
      setPendingFullscreenTarget('canvas');
      return;
    }
    setPendingFullscreenTarget('split');
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
    <div ref={pageRootRef} className="flex h-full flex-1 min-h-0 flex-col gap-3">
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
                onClick={() => {
                  setMode('individual');
                  hideCanvas();
                }}
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

          <div className="flex items-center rounded-lg border border-slate-200 bg-slate-50 p-0.5">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className={cn("h-8 px-2 text-[11px]", chatActive && "bg-white shadow-sm")}
              onClick={toggleChatMode}
              title={
                layoutMode === 'chat'
                  ? "Voltar ao modo dividido (Chat + Canvas)"
                  : "Foco no Chat (oculta o Canvas)"
              }
            >
              Chat
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className={cn("h-8 px-2 text-[11px]", canvasActive && "bg-white shadow-sm")}
              onClick={toggleCanvasMode}
              title={
                layoutMode === 'canvas'
                  ? "Voltar ao modo dividido (Chat + Canvas)"
                  : "Foco no Canvas (oculta o Chat)"
              }
            >
              Canvas
            </Button>
          </div>

          {fullscreenApi.supported && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-8 px-2 text-[11px]"
              onClick={handleToggleFullscreen}
              title={isFullscreen ? "Sair da tela cheia" : `Tela cheia (${layoutLabel})`}
            >
              {isFullscreen ? <Minimize2 className="mr-1 h-3.5 w-3.5" /> : <Maximize2 className="mr-1 h-3.5 w-3.5" />}
              {isFullscreen ? "Sair" : "Tela cheia"}
            </Button>
          )}

          <Button
            variant="ghost"
            size="icon"
            className={cn("h-8 w-8 rounded-lg", showSettings && "bg-slate-100")}
            onClick={() => setShowSettings(!showSettings)}
            data-testid="settings-toggle"
          >
            <Settings2 className="h-4 w-4" />
          </Button>

          <Button
            variant="outline"
            size="sm"
            className="h-8 rounded-lg text-xs"
            onClick={handleStartNewMinuta}
            data-testid="minuta-new-chat"
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

      {/* Main Content Area - Resizable Layout */}
      <div
        ref={splitContainerRef}
        className="flex-1 h-full flex flex-row gap-0 min-h-0 overflow-hidden"
      >
        {/* Left Panel: Chat - Resizable via divider, hidden when canvas is expanded */}
        <div
          ref={chatPanelRef}
          className={cn(
            "relative flex flex-col min-w-0 bg-white/50 backdrop-blur-sm transition-[width,opacity,transform] duration-300 ease-in-out will-change-[width]",
            layoutMode === 'split' ? 'border-r border-slate-200/60' : '',
            canvasState === 'expanded' ? 'hidden w-0 opacity-0' : '',
            isFullscreen && pendingFullscreenTarget === 'chat' ? 'fixed inset-0 z-50 w-full h-full bg-white' : ''
          )}
          style={{
            width: canvasState === 'normal' ? `${chatPanelWidth}%` : '100%',
          }}
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
              {/* Retry Progress Indicator */}
              {retryProgress?.isRetrying && (
                <div className="mt-2 pt-2 border-t border-indigo-200/50">
                  <div className="flex items-center gap-2 text-xs">
                    <div className="flex h-4 w-4 items-center justify-center rounded-full bg-amber-100 text-amber-600 flex-shrink-0">
                      <Loader2 className="h-3 w-3 animate-spin" />
                    </div>
                    <span className="text-amber-700 font-medium">
                      Tentando novamente ({retryProgress?.progress || '...'})
                    </span>
                  </div>
                  {retryProgress?.reason && (
                    <p className="text-[10px] text-amber-600/80 mt-1 ml-6">
                      Razão: {retryProgress?.reason === 'missing_citations_for_jurisprudence'
                        ? 'Faltam citações de jurisprudência'
                        : retryProgress?.reason}
                    </p>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Chat Content */}
          <div className="flex-1 min-h-0 overflow-hidden flex flex-col">
            {activeChatId ? (
              <ChatInterface
                chatId={activeChatId}
                hideInput={false}
                autoCanvasOnDocumentRequest
                showCanvasButton
              />
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
              data-testid="fontes-toggle"
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
              <div
                className="max-h-[150px] overflow-y-auto p-3 bg-slate-50/50 space-y-1.5"
                data-testid="fontes-panel"
              >
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
            "min-h-0 h-full rounded-r-xl border border-l-0 border-slate-200/60 bg-white shadow-sm overflow-hidden transition-[flex-grow,width,opacity,transform] duration-300 ease-in-out",
            canvasState === 'expanded' ? "flex-1 rounded-xl border-l" : "flex-1"
          )}
            ref={canvasPanelRef}
          >
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

      {/* Settings Drawer (lateral direita) */}
      <MinutaSettingsDrawer
        open={showSettings}
        onOpenChange={setShowSettings}
        mode={mode}
        chatMode={chatMode}
        onSetChatMode={handleSetChatMode}
        chatPersonality={chatPersonality}
        setChatPersonality={setChatPersonality}
        documentType={useChatStore.getState().documentType || 'PETICAO_INICIAL'}
        setDocumentType={(t) => useChatStore.getState().setDocumentType(t)}
        minPages={minPages}
        maxPages={maxPages}
        setPageRange={setPageRange}
        resetPageRange={resetPageRange}
        formattingOptions={formattingOptions}
        setFormattingOptions={setFormattingOptions}
        reasoningLevel={(['low', 'medium', 'high'].includes(reasoningLevel) ? reasoningLevel : 'medium') as 'low' | 'medium' | 'high'}
        setReasoningLevel={setReasoningLevel}
        effortLevel={effortLevel}
        setEffortLevel={setEffortLevel}
        creativityMode={creativityMode}
        setCreativityMode={setCreativityMode}
        temperatureOverride={temperatureOverride}
        setTemperatureOverride={setTemperatureOverride}
        qualityProfile={qualityProfile}
        setQualityProfile={setQualityProfile}
        qualityTargetSectionScore={qualityTargetSectionScore}
        setQualityTargetSectionScore={setQualityTargetSectionScore}
        qualityTargetFinalScore={qualityTargetFinalScore}
        setQualityTargetFinalScore={setQualityTargetFinalScore}
        qualityMaxRounds={qualityMaxRounds}
        setQualityMaxRounds={setQualityMaxRounds}
        researchPolicy={researchPolicy}
        setResearchPolicy={setResearchPolicy}
        webSearch={webSearch}
        setWebSearch={(v) => useChatStore.getState().setWebSearch(v)}
        denseResearch={denseResearch}
        setDenseResearch={(v) => useChatStore.getState().setDenseResearch(v)}
        searchMode={searchMode}
        setSearchMode={setSearchMode}
        multiQuery={multiQuery}
        setMultiQuery={setMultiQuery}
        breadthFirst={breadthFirst}
        setBreadthFirst={setBreadthFirst}
        deepResearchProvider={deepResearchProvider}
        setDeepResearchProvider={setDeepResearchProvider}
        deepResearchModel={deepResearchModel}
        setDeepResearchModel={setDeepResearchModel}
        webSearchModel={webSearchModel}
        setWebSearchModel={setWebSearchModel}
        auditMode={auditMode}
        setAuditMode={setAuditMode}
        selectedModel={selectedModel}
        setSelectedModel={setSelectedModel}
        agentStrategistModel={agentStrategistModel}
        agentDrafterModels={agentDrafterModels}
        setAgentDrafterModels={setAgentDrafterModels}
        agentReviewerModels={agentReviewerModels}
        setAgentReviewerModels={setAgentReviewerModels}
        selectedModels={selectedModels}
        setSelectedModels={setSelectedModels}
        setShowMultiModelComparator={setShowMultiModelComparator}
        baseModelOptions={baseModelOptions}
        agentModelOptions={agentModelOptions}
        hilOutlineEnabled={hilOutlineEnabled}
        setHilOutlineEnabled={setHilOutlineEnabled}
        autoApproveHil={autoApproveHil}
        setAutoApproveHil={setAutoApproveHil}
        chatOutlineReviewEnabled={chatOutlineReviewEnabled}
        setChatOutlineReviewEnabled={setChatOutlineReviewEnabled}
        hilSectionPolicyOverride={hilSectionPolicyOverride}
        setHilSectionPolicyOverride={setHilSectionPolicyOverride}
        hilFinalRequiredOverride={hilFinalRequiredOverride}
        setHilFinalRequiredOverride={setHilFinalRequiredOverride}
        qualityMaxFinalReviewLoops={qualityMaxFinalReviewLoops}
        setQualityMaxFinalReviewLoops={setQualityMaxFinalReviewLoops}
        qualityStyleRefineMaxRounds={qualityStyleRefineMaxRounds}
        setQualityStyleRefineMaxRounds={setQualityStyleRefineMaxRounds}
        qualityMaxResearchVerifierAttempts={qualityMaxResearchVerifierAttempts}
        setQualityMaxResearchVerifierAttempts={setQualityMaxResearchVerifierAttempts}
        qualityMaxRagRetries={qualityMaxRagRetries}
        setQualityMaxRagRetries={setQualityMaxRagRetries}
        qualityRagRetryExpandScope={qualityRagRetryExpandScope}
        setQualityRagRetryExpandScope={setQualityRagRetryExpandScope}
        recursionLimitOverride={recursionLimitOverride}
        setRecursionLimitOverride={setRecursionLimitOverride}
        strictDocumentGateOverride={strictDocumentGateOverride}
        setStrictDocumentGateOverride={setStrictDocumentGateOverride}
        forceGranularDebate={forceGranularDebate}
        setForceGranularDebate={setForceGranularDebate}
        maxDivergenceHilRounds={maxDivergenceHilRounds}
        setMaxDivergenceHilRounds={setMaxDivergenceHilRounds}
        cragMinBestScoreOverride={cragMinBestScoreOverride}
        setCragMinBestScoreOverride={setCragMinBestScoreOverride}
        cragMinAvgScoreOverride={cragMinAvgScoreOverride}
        setCragMinAvgScoreOverride={setCragMinAvgScoreOverride}
        documentChecklist={documentChecklist}
        setDocumentChecklist={setDocumentChecklist}
      />
    </div>
  );
}
